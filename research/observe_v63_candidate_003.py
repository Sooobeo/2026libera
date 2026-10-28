"""Read-only selected-candidate observer; writes only its own JSON and Korean HTML.

Usage: python -m research.observe_v63_candidate_003 [--config PATH] [--watch]
The default remains candidate 003; another candidate requires an explicit config.
No network, model requests, experiment-state writes, or process control.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
from datetime import datetime, timedelta, timezone
from html import escape
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.v63.campaign_control import TERMINAL_STATUSES, final_trace_path, task_request_cost

CONFIG = ROOT / 'data/v63_20261027/continuation/deployment/local_windows/candidate_003/campaign_config.json'
RECORD = ROOT / 'research/device_migration_20261027'
JSON_OUTPUT = RECORD / 'live_status.json'
HTML_OUTPUT = ROOT / '실험참고자료_20261027/05_새기기실행_20261027.html'
KST = timezone(timedelta(hours=9))
PHASES = (
    ('technical-smoke', '기술 점검', 5),
    ('paired-feasibility', '4펀드 실행 가능성', 20),
    ('development-pilot', '개발 파일럿', 240),
    ('B-main', '본실험 B', 2400),
    ('x-replacement', '전망 교체', 360),
    ('negative-control', '음성 대조', 192),
    ('A', '실제 문서 A', 40),
    ('C', '실제 문서 C', 40),
)
ACTIVE_STATES = {'starting', 'running', 'phase_verified'}
READ_RETRY_DELAYS = (0.05, 0.1, 0.2, 0.4, 0.8)
PROCESS_TIME_MARGIN = timedelta(seconds=30)
OUTPUT_REPLACE_RETRY_SECONDS = 30.0
STATUS_KO = {
    'starting': '시작 준비 중', 'running': '진행 중', 'phase_verified': '단계 검증 완료',
    'completed': '단계 종료', 'incomplete': '단계 미완료', 'not_attempted': '미시작',
    'prepared': '입력 준비됨', 'model_output_failure': '모델 출력 조건 실패',
    'operational_failure': '실행 오류', 'protocol_violation': '실험 규칙 점검 필요',
    'recovery_interrupted': '복구 점검 필요',
    'feasibility_complete_requires_measured_resource_review': '15·60단계 종료 — 자원 검토 대기',
    'stopped_campaign_requires_review': '캠페인 중단 — 점검 필요',
    'stopped_requires_review': '중단 — 점검 필요',
    'supervisor_process_not_running': '관리 프로세스 종료 — 기록 확인 필요',
    'supervisor_process_unverified': '관리 프로세스 실행 여부 확인 불가',
    'supervisor_state_unavailable': '상태 파일 확인 불가 — 관찰 계속',
    'supervisor_not_started': '관리 프로세스 기록 없음',
    'launching': '다음 작업 시작 중', 'phase_starting': '다음 단계 준비 중',
    'phase_completed': '단계 검증 완료', 'subprocess_finished': '작업 종료 기록 확인 중',
    'subprocess_interrupted': '작업 중단 기록 확인 중',
    'stopped_requires_review_or_same_identity_resume': '장기 관리자 중단 — 점검 또는 동일 후보 재개 필요',
    'guardian_completed': '장기 관리자 완료 기록 — 최종 보고 자료 확인 필요',
}


@contextmanager
def shared_reader(path):
    """Open with Windows read/write/delete sharing; hold the handle briefly."""
    path = Path(path)
    if os.name != 'nt':
        with path.open('r', encoding='utf-8-sig') as handle:
            yield handle
        return
    import msvcrt
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong,
                                  ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int
    handle = kernel.CreateFileW(str(path), 0x80000000, 0x7, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle(handle)
        raise
    with os.fdopen(descriptor, 'r', encoding='utf-8-sig') as stream:
        yield stream


def read(path, errors, *, required=False):
    path = Path(path)
    for attempt in range(len(READ_RETRY_DELAYS)+1):
        try:
            with shared_reader(path) as stream:
                content = stream.read()
            # Close the Windows handle before parsing or walking the document.
            return json.loads(content)
        except FileNotFoundError as exc:
            # An absent optional, immutable artifact needs no delayed retry.
            if not required:
                return None
            error = {'path':str(path.relative_to(ROOT)), 'error':'missing', 'detail':str(exc)}
        except (OSError, ValueError) as exc:
            error = {'path':str(path.relative_to(ROOT)), 'error':type(exc).__name__, 'detail':str(exc)}
        if attempt < len(READ_RETRY_DELAYS):
            time.sleep(READ_RETRY_DELAYS[attempt])
        else:
            errors.append({**error, 'attempts':attempt+1})
    return None


def windows_boot_time():
    """Estimate UTC boot time from monotonic Windows uptime, not a stored PID."""
    if os.name != 'nt':
        return None
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetTickCount64.argtypes = []
    kernel.GetTickCount64.restype = ctypes.c_ulonglong
    return datetime.now(timezone.utc)-timedelta(milliseconds=kernel.GetTickCount64())


def windows_process_info(pid):
    """Return liveness and actual creation time, closing every query handle."""
    class FileTime(ctypes.Structure):
        _fields_ = [('low', ctypes.c_ulong), ('high', ctypes.c_ulong)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel.GetExitCodeProcess.restype = ctypes.c_int
    kernel.GetProcessTimes.argtypes = [ctypes.c_void_p]+[ctypes.POINTER(FileTime)]*4
    kernel.GetProcessTimes.restype = ctypes.c_int
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return (False, None) if ctypes.get_last_error() == 87 else (None, None)
    try:
        code = ctypes.c_ulong()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            return None, None
        if code.value != 259:
            return False, None
        created, exited, kernel_time, user_time = (FileTime() for _ in range(4))
        if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                      ctypes.byref(kernel_time), ctypes.byref(user_time)):
            return True, None
        ticks = (created.high << 32)+created.low
        creation_time = datetime(1601, 1, 1, tzinfo=timezone.utc)+timedelta(microseconds=ticks//10)
        return True, creation_time
    finally:
        kernel.CloseHandle(handle)


def process_alive(pid, expected_started_at=None):
    """Check the original process across reboots/PID reuse, without controlling it."""
    if type(pid) is not int or pid <= 0:
        return False
    expected = None
    if expected_started_at is not None:
        try:
            expected = datetime.fromisoformat(expected_started_at)
            if expected.tzinfo is None or expected.utcoffset() is None:
                return None
            expected = expected.astimezone(timezone.utc)
            if expected > datetime.now(timezone.utc)+PROCESS_TIME_MARGIN:
                return None
        except (TypeError, ValueError, OverflowError):
            return None
    if os.name == 'nt':
        boot = windows_boot_time()
        if expected is not None and boot is not None and expected < boot-PROCESS_TIME_MARGIN:
            # Even an inaccessible/reused PID cannot represent a pre-boot
            # process. The margin covers the uptime-to-UTC estimate.
            return False
        alive, created = windows_process_info(pid)
        if alive is not True or expected is None:
            return alive
        if created is None or created > datetime.now(timezone.utc)+PROCESS_TIME_MARGIN:
            return None
        # started_at is recorded after interpreter startup. A much later
        # creation time proves that this PID belongs to another process.
        if created > expected+PROCESS_TIME_MARGIN:
            return False
        return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return None


def source_availability(config, readiness, errors):
    """Observe current raw bytes; keep the original audit as historical evidence."""
    historical = readiness.get('source_archive_availability') or {}
    manifest_path = ROOT / historical.get('manifest', {}).get('path', 'data/v63_20261027/continuation_sources/source_manifest_v2.json')
    manifest = read(manifest_path, errors)
    documents_path = ROOT / config.get('documents_path', 'data/v63_20261027/continuation_sources/documents_v2.json')
    documents = read(documents_path, errors)
    observed = {}

    def inspect(path, expected):
        path = (ROOT / path).resolve()
        if ROOT not in path.parents:
            errors.append({'path':str(path), 'error':'source_path_outside_workspace'})
            return {'present':None, 'sha256_matches':None}
        key = str(path)
        if key not in observed:
            try:
                if not path.is_file():
                    observed[key] = {'present':False, 'actual_sha256':None}
                else:
                    digest = hashlib.sha256()
                    with path.open('rb') as stream:
                        for block in iter(lambda:stream.read(1024*1024), b''):
                            digest.update(block)
                    observed[key] = {'present':True, 'actual_sha256':digest.hexdigest()}
            except OSError as exc:
                observed[key] = {'present':None, 'actual_sha256':None}
                errors.append({'path':str(path.relative_to(ROOT)), 'error':'source_availability_unverified', 'detail':str(exc)})
        result = observed[key]
        return {**result, 'sha256_matches':result['actual_sha256']==expected if result['present'] is True else None}

    source_rows = []
    if isinstance(manifest, dict):
        for row in manifest.get('sources', []):
            source_rows.append({**inspect(row['local_path'], row.get('sha256')),
                                'path':row['local_path'], 'active_profile_reference':bool(row.get('active_profile_reference'))})
    ac_rows = []
    if isinstance(documents, dict):
        for row in documents.get('documents', []):
            ac_rows.append({'document_id':row['document_id'], 'path':row['source_path'],
                            'expected_sha256':row['source_bytes_sha256'],
                            **inspect(row['source_path'], row['source_bytes_sha256'])})
    return {
        'observed_at_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'Current local file existence and exact-byte hashes against retained source references; not a new semantic or human source audit.',
        'manifest':historical.get('manifest'),
        'source_records':len(source_rows) if manifest is not None else None,
        'present_records':sum(row['present'] is True for row in source_rows) if manifest is not None else None,
        'hash_verified_records':sum(row['sha256_matches'] is True for row in source_rows) if manifest is not None else None,
        'missing_records':sum(row['present'] is False for row in source_rows) if manifest is not None else None,
        'unverified_records':sum(row['present'] is None for row in source_rows) if manifest is not None else None,
        'missing_active_profile_reference_records':sum(row['active_profile_reference'] and row['present'] is False for row in source_rows) if manifest is not None else None,
        'A_C_raw_source_files_present':sum(row['present'] is True for row in ac_rows) if documents is not None else None,
        'A_C_raw_source_files_hash_verified':sum(row['sha256_matches'] is True for row in ac_rows) if documents is not None else None,
        'A_C_raw_source_files_expected':len(ac_rows) if documents is not None else None,
        'A_C_raw_source_files':ac_rows,
        'historical_audit':{'path':str((RECORD/'input_readiness.json').relative_to(ROOT)),
                            'A_C_raw_source_files_present_at_that_time':historical.get('A_C_raw_source_files_present'),
                            'missing_records_at_that_time':historical.get('missing_records')},
    }


def power_settings_receipt(errors):
    paths = sorted(RECORD.glob('power_settings_*/receipt.json'))
    if not paths:
        return None
    path = paths[-1]
    receipt = read(path, errors)
    if not isinstance(receipt, dict):
        return None
    rows = {row.get('setting'):row for row in receipt.get('settings', [])}
    settings = ('STANDBYIDLE', 'HIBERNATEIDLE', 'LIDACTION')
    verified = receipt.get('verified_by_requery') is True and all(
        name in rows and all(type(rows[name].get('after', {}).get(mode)) is int and rows[name]['after'][mode]==0
                             for mode in ('AC','DC')) for name in settings)
    return {'path':str(path.relative_to(ROOT)), 'recorded_at_utc':receipt.get('recorded_at_utc'),
            'verified_no_idle_sleep_hibernate_or_lid_sleep_at_record_time':verified,
            'verified_no_display_idle_at_record_time':receipt.get('verified_by_requery') is True and
                all(type(rows.get('VIDEOIDLE',{}).get('after',{}).get(mode)) is int and
                    rows['VIDEOIDLE']['after'][mode]==0 for mode in ('AC','DC')),
            'scope':'Verified setting receipt at its recorded time; observer does not query or change OS power settings.',
            'settings':receipt.get('settings'),
            'restore_script':str((path.parent/'restore_previous_settings.ps1').relative_to(ROOT))}


def keepawake_receipt(run_id, errors):
    for path in sorted(RECORD.glob('keepawake_candidate*/status.json'), reverse=True):
        receipt = read(path, errors)
        if not isinstance(receipt, dict) or receipt.get('run_id') != run_id:
            continue
        alive = process_alive(receipt.get('pid'), receipt.get('started_at_utc'))
        try:
            updated = datetime.fromisoformat(receipt['updated_at_utc'])
            age = (datetime.now(timezone.utc)-updated).total_seconds()
            fresh = 0 <= age <= 120
        except (KeyError, TypeError, ValueError):
            fresh = False
        return {'path':str(path.relative_to(ROOT)),
                'launch_path':str((path.parent/'launch.json').relative_to(ROOT)),
                'pid':receipt.get('pid'), 'process_identity_alive':alive,
                'last_status':receipt.get('status'), 'updated_at_utc':receipt.get('updated_at_utc'),
                'fresh':fresh,
                'verified_active':alive is True and fresh and receipt.get('status')=='active',
                'api_events':receipt.get('api_events'),
                'scope':'Helper status and original process identity; not a new OS power-policy query or a guarantee against explicit user sleep.'}
    return None


def snapshot(config_path=CONFIG, previous=None):
    errors = []
    config_path = Path(config_path).resolve()
    if ROOT not in config_path.parents:
        raise ValueError('Candidate configuration is outside this workspace.')
    match = re.fullmatch(r'candidate_(\d+)', config_path.parent.name)
    if match is None:
        raise ValueError('Candidate configuration must be inside a candidate_<number> directory.')
    candidate = match.group(1)
    config = read(config_path, errors, required=True)
    selection = read(config_path.parent / 'selection_receipt.json', errors, required=True)
    if config is None or selection is None:
        raise ValueError('Candidate configuration/selection receipt is unavailable: '+str(errors))
    run_id = selection['new_run_id']
    if len(run_id) != 64 or any(c not in '0123456789abcdef' for c in run_id):
        raise ValueError('Invalid selected run ID.')
    output_root = (ROOT / config['output_root']).resolve()
    if ROOT not in output_root.parents:
        raise ValueError('Output root is outside this workspace.')
    run_root = output_root / 'runs' / run_id
    supervisor_path = output_root / 'development_supervisor' / run_id / 'state.json'
    supervisor = read(supervisor_path, errors, required=True)
    supervisor_state_fresh = supervisor is not None
    if supervisor is not None and not isinstance(supervisor, dict):
        errors.append({'path':str(supervisor_path.relative_to(ROOT)), 'error':'invalid_state_object'})
        supervisor = None
        supervisor_state_fresh = False
    if supervisor and supervisor.get('run_id') != run_id:
        errors.append({'path':str(supervisor_path.relative_to(ROOT)), 'error':'other_run_state_ignored'})
        supervisor = None
        supervisor_state_fresh = False
    if not supervisor_state_fresh:
        supervisor = (previous or {}).get('supervisor', {}) if (previous or {}).get('run_id') == run_id else {}
    supervisor = supervisor or {}
    pid = supervisor.get('supervisor_pid')
    alive = process_alive(pid, supervisor.get('started_at_utc')) if isinstance(pid, int) and pid > 0 else None
    boot_estimate = windows_boot_time()
    if not supervisor_state_fresh:
        status = 'supervisor_process_not_running' if alive is False else 'supervisor_state_unavailable'
        watch_should_continue = alive is not False
    else:
        status = supervisor.get('status', 'supervisor_process_unverified')
        watch_should_continue = status in ACTIVE_STATES and alive is not False
        if status in ACTIVE_STATES and alive is not True:
            status = 'supervisor_process_not_running' if alive is False else 'supervisor_process_unverified'
        elif status == 'supervisor_process_unverified':
            watch_should_continue = alive is not False
    controller_kind = 'development_supervisor'
    controller_state = supervisor
    controller_state_fresh = supervisor_state_fresh
    controller_alive = alive
    controller_reference_time = supervisor.get('started_at_utc')
    guardian_path = output_root / 'guardian' / run_id / 'checkpoint.json'
    guardian = read(guardian_path, errors)
    guardian_present = guardian is not None or guardian_path.exists()
    guardian_fresh = guardian is not None
    guardian_alive = None
    if guardian is not None and (not isinstance(guardian, dict) or guardian.get('run_id') != run_id):
        errors.append({'path':str(guardian_path.relative_to(ROOT)), 'error':'invalid_or_other_run_guardian_ignored'})
        guardian = None
        guardian_present = False
        guardian_fresh = False
    if guardian_present:
        if not guardian_fresh:
            guardian = (previous or {}).get('guardian') if (previous or {}).get('run_id') == run_id else None
        guardian = guardian or {}
        guardian_pid = guardian.get('pid')
        # Guardian started_at survives resumes. Its last heartbeat timestamp
        # is instead an upper bound on the current PID's creation time.
        guardian_reference = guardian.get('updated_at_utc')
        guardian_alive = process_alive(guardian_pid, guardian_reference) if type(guardian_pid) is int and guardian_pid > 0 else None
        controller_kind = 'guardian'
        controller_state = guardian
        controller_state_fresh = guardian_fresh
        controller_alive = guardian_alive
        controller_reference_time = guardian_reference
        if not guardian_fresh:
            status = 'supervisor_process_not_running' if guardian_alive is False else 'supervisor_state_unavailable'
            watch_should_continue = guardian_alive is not False
        else:
            status = guardian.get('status', 'supervisor_process_unverified')
            terminal_guardian = status in {'completed', 'stopped_requires_review_or_same_identity_resume'}
            watch_should_continue = not terminal_guardian and guardian_alive is not False
            if status == 'completed':
                status = 'guardian_completed'
            elif not terminal_guardian and guardian_alive is not True:
                status = 'supervisor_process_not_running' if guardian_alive is False else 'supervisor_process_unverified'
    progress = read(output_root / 'progress.json', errors)
    if progress and progress.get('run_id') != run_id:
        progress = None
    try:
        # Original attempt directories are under this run only; immutable
        # replay copies are stored separately by campaign_control.
        costs = task_request_cost(run_root)
    except (OSError, ValueError) as exc:
        costs = None
        errors.append({'path':str(run_root.relative_to(ROOT)), 'error':'request_accounting_unavailable', 'detail':str(exc)})
    tasks = []
    for identity in sorted(run_root.glob('*/*/input_identity.json')):
        task = identity.parent
        try:
            trace_path = final_trace_path(task)
            trace = read(trace_path, errors) if trace_path is not None else None
        except (OSError, ValueError, KeyError) as exc:
            trace = None
            errors.append({'path':str(task.relative_to(ROOT)), 'error':'trace_verification_failed', 'detail':str(exc)})
        tasks.append({'task':task.name, 'block':task.parent.name,
                      'terminal_status':trace.get('status') if trace else None,
                      'completed_stages':sum(s.get('status')=='completed' for s in trace.get('stages', [])) if trace else None})
    phases = []
    for phase, label, count in PHASES:
        phase_dir = output_root / 'phases' / run_id / phase
        measurement = read(phase_dir / 'measurements.json', errors)
        phase_status = (measurement or {}).get('status', 'not_attempted')
        if controller_state.get('phase') == phase and status == 'running':
            phase_status = 'running'
        elif controller_state.get('phase') == phase and (status.startswith('stopped_') or status.startswith('supervisor_')):
            phase_status = status
        elif measurement is None and (phase_dir / 'prepared_inputs.json').is_file():
            phase_status = 'prepared'
        phases.append({'phase':phase, 'label_ko':label, 'planned_trajectories':count,
                       'planned_logical_stages':count*3, 'status':phase_status,
                       'measurements':measurement})
    tests = read(RECORD / 'offline_tests_summary.json', errors) or {}
    test_analysis = read(RECORD / 'offline_tests_analysis.json', errors) or {}
    count = tests.get('counts', {})
    failures = count.get('failures')
    passed = (count.get('tests', 0)-count.get('failures', 0)-count.get('errors', 0)-count.get('skipped', 0)) if count else None
    readiness = read(RECORD / 'input_readiness.json', errors) or {}
    capacity = read(RECORD / 'input_capacity.json', errors) or {}
    freeze = read(ROOT / config['runtime_freeze_path'], errors, required=True) or {}
    now = datetime.now(timezone.utc)
    return {
        'schema':'libera_selected_candidate_readonly_observer_v1',
        'observed_at_utc':now.isoformat(), 'observed_at_kst':now.astimezone(KST).isoformat(),
        'candidate':candidate, 'run_id':run_id, 'status':status,
        'config_path':str(config_path.relative_to(ROOT)),
        'output_root':str(output_root.relative_to(ROOT)),
        'report_scope':'Current experiment progress only; not a final experiment result.',
        'observer_model_calls':0, 'observer_http_calls':0,
        'observer_writes':[str(JSON_OUTPUT.relative_to(ROOT)), str(HTML_OUTPUT.relative_to(ROOT))],
        'supervisor_alive':alive, 'supervisor_state_fresh':supervisor_state_fresh,
        'process_identity_evidence':{'expected_started_at_utc':controller_reference_time,
                                     'reference_kind':'guardian_last_heartbeat_creation_upper_bound' if controller_kind=='guardian' else 'supervisor_process_start',
                                     'boot_estimate_at_utc':boot_estimate.isoformat() if boot_estimate else None,
                                     'time_margin_seconds':PROCESS_TIME_MARGIN.total_seconds()},
        'supervisor_state_source':'current_read' if supervisor_state_fresh else ('last_known_snapshot' if supervisor else 'unavailable'),
        'watch_should_continue':watch_should_continue,
        'controller_kind':controller_kind, 'controller_state':controller_state,
        'controller_state_fresh':controller_state_fresh, 'controller_alive':controller_alive,
        'guardian':guardian if guardian_present else None, 'guardian_state_fresh':guardian_fresh if guardian_present else None,
        'guardian_alive':guardian_alive,
        'supervisor':supervisor, 'progress':progress, 'current_candidate_request_costs':costs,
        'tasks':tasks, 'terminal_trajectories':sum(t['terminal_status'] in TERMINAL_STATUSES for t in tasks),
        'phases':phases, 'main_auto_launch':None if controller_kind=='guardian' else supervisor.get('main_auto_launch', False),
        'main_transition_policy':'Guardian approval and phase gates control main; observer does not validate or issue approval.' if controller_kind=='guardian' else 'Development supervisor does not launch main.',
        'main_model_frozen':freeze.get('main_model_frozen'),
        'prior_device_summary':{
            'experimental_requests_recorded':selection['previous_experimental_generation_requests_recorded'],
            'engineering_requests_recorded':selection['previous_engineering_generation_requests_recorded'],
            'raw_files_expected':selection['previous_raw_files_expected'],
            'raw_files_available':selection['previous_raw_files_available'],
            'responses_reused_in_current_candidate':selection['previous_candidate_responses_reused'],
            'scope':selection['historical_cost_scope'],
        },
        'environment':{'python_version':selection['new_python_version'], 'model':freeze.get('model'),
                       'engine_revision':freeze.get('engine_revision'), 'context_tokens':freeze.get('context_tokens'),
                       'output_tokens':freeze.get('output_tokens')},
        'verification':{'suite_status':tests.get('status'), 'tests_passed':passed, 'tests_failed':failures,
                        'all_failures_are_missing_files':test_analysis.get('all_failures_are_missing_files'),
                        'input_checks_passed':readiness.get('checks_passed'), 'input_checks_failed':readiness.get('checks_failed'),
                        'input_capacity_status':capacity.get('status'), 'input_capacity_cases':capacity.get('cases')},
        'source_archive_availability':source_availability(config, readiness, errors),
        'power_settings_receipt':power_settings_receipt(errors),
        'keepawake_receipt':keepawake_receipt(run_id, errors),
        'human_review_mode':selection.get('human_review_mode'),
        'actual_independent_human_reviews_claimed':False,
        'observation_errors':errors,
    }


def display(value):
    return '미확인' if value is None else escape(str(value))


def artifact_link(path, label):
    path = Path(path)
    if not path.exists():
        return ''
    relative = os.path.relpath(path, HTML_OUTPUT.parent).replace(os.sep, '/')
    return '<li><a href="'+escape(quote(relative, safe='/.:'))+'">'+escape(label)+'</a></li>'


def render(value):
    supervisor = value['supervisor']
    controller = value.get('controller_state', supervisor)
    guardian_mode = value.get('controller_kind') == 'guardian'
    progress = value['progress'] or {}
    costs = value['current_candidate_request_costs'] or {}
    prior = value['prior_device_summary']
    verify = value['verification']
    env = value['environment']
    sources = value.get('source_archive_availability') or {}
    power = value.get('power_settings_receipt') or {}
    keepawake = value.get('keepawake_receipt') or {}
    candidate = escape(value['candidate'])
    config_path = ROOT / value['config_path']
    phase_rows = []
    for phase in value['phases']:
        measured = phase['measurements'] or {}
        terminal = measured.get('terminal_trajectories')
        if phase['phase'] == progress.get('phase') and terminal is None:
            terminal = progress.get('recorded_trajectories')
        phase_rows.append('<tr><td>'+escape(phase['label_ko'])+'</td><td>'+str(phase['planned_logical_stages'])+
                          '</td><td>'+display(terminal)+' / '+str(phase['planned_trajectories'])+'</td><td>'+
                          escape(STATUS_KO.get(phase['status'],phase['status']))+'</td></tr>')
    output_root = ROOT / value['output_root']
    supervisor_root = output_root / 'development_supervisor' / value['run_id']
    links = [
        (JSON_OUTPUT,'현재 관측 JSON'), (config_path,'후보 '+value['candidate']+' 실행 설정'),
        (config_path.parent/'selection_receipt.json','현재 후보 선택 기록'),
        (supervisor_root/'state.json','개발 관리자 상태'),
        (RECORD/'offline_tests_summary.json','전체 오프라인 검사 결과'),
        (RECORD/'offline_tests_analysis.json','누락 파일로 실패한 10개 검사 분석'),
        (RECORD/'input_readiness.json','실행 입력 47개 확인'),
        (RECORD/'input_capacity.json','20개 입력의 정확한 토큰 검사'),
        (RECORD/'followup/source_archive_recovery.json','공식 원문 복구 및 해시 대사 기록'),
        (RECORD/'paper_completion_request.json','실험 완료 및 논문 작성 요청 기록'),
        (ROOT/'실험참고자료_20261027/04_중지와재개_20261027.html','이전 기기 중지 기록'),
    ]
    if power:
        links.extend([(ROOT/power['path'],'절전·최대절전·화면·덮개 동작 설정 확인 기록'),
                      (ROOT/power['restore_script'],'이전 전원 설정 복원 스크립트')])
    if keepawake:
        links.extend([(ROOT/keepawake['path'],'실험 실행 중 전원 요청 helper 상태'),
                      (ROOT/keepawake['launch_path'],'전원 요청 helper 실행 기록')])
    guardian_root = output_root/'guardian'/value['run_id']
    for name, label in (('checkpoint.json','장기 관리자 현재 상태'),('heartbeat.json','장기 관리자 관측 시각'),
                        ('completion_receipt.json','장기 관리자 완료 영수증')):
        links.append((guardian_root/name, label))
    if supervisor.get('logs'):
        for name in ('technical-smoke.stdout.log','technical-smoke.stderr.log','paired-feasibility.stdout.log','paired-feasibility.stderr.log'):
            links.append((ROOT/supervisor['logs']/name, name))
    for phase in value['phases']:
        links.append((output_root/'phases'/value['run_id']/phase['phase']/'measurements.json',phase['label_ko']+' 측정 결과'))
    error_text = '' if not value['observation_errors'] else '<p class="notice">일부 관측 자료를 읽지 못했습니다. 해당 값은 미확인으로 표시하며 상세 내용은 관측 JSON에 보존했습니다.</p>'
    if not value.get('controller_state_fresh', value['supervisor_state_fresh']):
        error_text += '<p class="notice">이번 관측에서 관리자 상태 파일을 확인하지 못했습니다. 아래 단계 정보는 마지막으로 읽은 기록이 있을 때만 참고로 표시합니다. 실행 중단을 뜻하지 않으며, 프로세스 종료가 확인되지 않으면 관찰을 계속합니다.</p>'
    failure_text = ('실패 항목은 보존되지 않은 원출처·검사용 파일의 누락으로 분류되었습니다.'
                    if verify['all_failures_are_missing_files'] is True
                    else '실패 원인은 연결된 검사 기록에서 확인할 수 있습니다.')
    refresh = '<meta http-equiv="refresh" content="30">' if value['watch_should_continue'] else ''
    controller_text = ('현재 장기 관리자(guardian)의 단계 진행을 관측합니다. 개발 파일럿과 이후 본실험의 전환은 관리자에 연결된 승인·검증 기록을 따릅니다.'
                       if guardian_mode else '현재 개발 관리자는 15→60단계까지 실행하며, 다음 단계에는 실제 측정에 따른 자원 검토가 필요합니다.')
    current_task = progress.get('current_task') if progress.get('phase') == controller.get('phase') else None
    power_text = ''
    if power.get('verified_no_idle_sleep_hibernate_or_lid_sleep_at_record_time') is True:
        recorded = datetime.fromisoformat(power['recorded_at_utc']).astimezone(KST).isoformat()
        power_text = '<p>전원 연결·배터리 사용 모두 유휴 절전과 최대절전이 해제되었고, 덮개를 닫아도 절전하지 않도록 설정한 확인 기록이 있습니다. 확인 시각: '+escape(recorded)+' (한국 시간). 관찰기는 설정을 변경하지 않습니다.</p>'
        if power.get('verified_no_display_idle_at_record_time') is True:
            power_text += '<p>같은 확인 기록에서 화면 자동 꺼짐도 전원 연결·배터리 모두 해제했습니다.</p>'
    if keepawake.get('verified_active') is True:
        power_text += '<p>현재 실행 식별자에 연결된 전원 요청 helper가 실행 중입니다. 실제 실험 프로세스를 확인하는 동안 시스템·화면 유지 요청을 적용하고, 종료 또는 짧은 관리자 전환 유예가 끝나면 해제합니다. 강제 종료·재부팅이나 사용자가 선택한 절전까지 막는 기능은 아닙니다.</p>'
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{refresh}
<title>LIBERA v6.3 · 새 기기 실행 현황</title><style>
body{{margin:0;background:#f4f6f8;color:#1b2838;font:16px/1.75 "Malgun Gothic",sans-serif}}main{{max-width:1050px;margin:auto;padding:36px 24px 64px}}h1{{font-size:29px}}h2{{font-size:21px;margin-top:30px}}.box{{background:white;border:1px solid #d8e1e8;border-radius:9px;padding:18px 22px;margin:18px 0}}.current{{border-left:5px solid #287696}}.notice{{color:#80531b}}table{{border-collapse:collapse;width:100%;background:white}}th,td{{padding:10px 12px;text-align:left;border-bottom:1px solid #d8e1e8}}th{{background:#eaf0f4}}code{{overflow-wrap:anywhere}}a{{color:#075d83}}.muted{{color:#536474;font-size:14px}}li{{margin:6px 0}}
</style></head><body><main>
<h1>새 기기에서 이어가는 실험 · 후보 {candidate}</h1>
<div class="box current"><strong>{escape(STATUS_KO.get(value['status'],value['status']))}</strong>
<p>현재 단계: <code>{display(controller.get('phase'))}</code><br>현재 과제: <code>{display(current_task)}</code></p>
<p>이 페이지는 실험의 진행 기록입니다. 전체 실험의 최종 결과가 아닙니다.</p>
{power_text}
<p class="muted">관측: {escape(value['observed_at_kst'])} (한국 시간)<br>실행 식별자: <code>{escape(value['run_id'])}</code></p></div>
{error_text}
<h2>현재 기기에서 발생한 요청</h2><div class="box">
<p>영수증으로 확인된 생성 요청 <strong>{display(costs.get('confirmed_attempt_records'))}회</strong> · 아직 완료 영수증이 없는 요청 예약 <strong>{display(costs.get('uncertain_dispatch_requests'))}회</strong><br>
예산 집계 합계 {display(costs.get('generation_requests'))}회 · 종료된 궤적 {value['terminal_trajectories']}개</p>
<p class="muted">원요청 기록만 집계합니다. 진행 중인 요청은 미확정 예약에 포함될 수 있습니다. 도구 왕복·재시도 때문에 생성 요청 수와 논리 단계 수는 다를 수 있습니다. 관찰기는 모델·HTTP 요청을 보내지 않습니다.</p></div>
<h2>단계별 진행</h2><table><thead><tr><th>단계</th><th>계획 논리 단계</th><th>종료 궤적 / 계획</th><th>상태</th></tr></thead><tbody>{''.join(phase_rows)}</tbody></table>
<p class="muted">15·60단계는 720단계 개발 파일럿에 포함되는 부분집합입니다. 합산해 중복 집계하지 않습니다. {controller_text} 종료 궤적에는 모델 출력 조건 실패가 포함될 수 있습니다.</p>
<h2>기기 전환과 검증</h2><div class="box">
<p>현재 선택 영수증의 이전 실행 요약에는 실험 요청 {prior['experimental_requests_recorded']}회와 공학 점검 {prior['engineering_requests_recorded']}회가 기록되어 있습니다. 이전 기기 원기록 {prior['raw_files_expected']}개 중 이 기기에 있는 파일은 {prior['raw_files_available']}개이며, 후보 {candidate}에 재사용한 이전 응답은 {prior['responses_reused_in_current_candidate']}개입니다. 이전 집계와 현재 집계는 별도로 보존합니다.</p>
<p>환경: Python {display(env['python_version'])} · {display(env['model'])} · Ollama {display(env['engine_revision'])} · 문맥 {display(env['context_tokens'])} · 출력 상한 {display(env['output_tokens'])}토큰.</p>
<p>오프라인 검사 {display(verify['tests_passed'])}개 통과, {display(verify['tests_failed'])}개 실패. {failure_text} 전체 검사 통과로 표시하지 않습니다. 보존된 실행 입력 확인은 {display(verify['input_checks_passed'])}개 통과했고, 정확한 토크나이저로 {display(verify['input_capacity_cases'])}개 입력을 구성했습니다.</p>
<p>현재 A/C 원문 파일은 {display(sources.get('A_C_raw_source_files_present'))} / {display(sources.get('A_C_raw_source_files_expected'))}개가 있으며, 보존된 SHA와 바이트가 일치하는 파일은 {display(sources.get('A_C_raw_source_files_hash_verified'))}개입니다. 이 수치는 현재 파일을 확인한 값입니다. 최초 입력 감사 당시의 0개 기록은 과거 관측으로 보존합니다.</p>
<p>전체 원출처 보관본은 아직 복구되지 않았습니다. 해시가 유지된 프로필·문서 원문 단위를 사용하며, 일부 원문 파일의 복구를 원출처 재감사 완료로 간주하지 않습니다. 사람 감사 상태는 <code>user_assumed_completed</code>이고 실제 독립 감사 서명은 없습니다. C의 새 전망 자료는 공통 FOMC 문서에 한정됩니다.</p></div>
<h2>확인할 기록</h2><ul>{''.join(artifact_link(path,label) for path,label in links)}</ul>
<p class="muted">관찰 파일만 갱신합니다. 기존 중지 기록·실험 원응답·예산·최종 결과 상태는 변경하지 않습니다.</p>
</main></body></html>'''


def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.'+path.name+'.'+str(os.getpid())+'.tmp')
    with temporary.open('w', encoding='utf-8', newline='\n') as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    # Keep the already-fsynced temporary bytes unchanged across sharing-lock
    # retries. Failure leaves the old target and complete temporary file.
    deadline = time.monotonic()+OUTPUT_REPLACE_RETRY_SECONDS
    delay = 0.05
    while True:
        try:
            os.replace(temporary, path)
            return
        except OSError as exc:
            if os.name != 'nt' or getattr(exc, 'winerror', None) not in {5, 32, 33}:
                raise
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(delay, remaining))
            delay = min(delay*2, 0.5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=CONFIG,
                        help='Candidate campaign configuration JSON (default: candidate_003).')
    parser.add_argument('--watch', action='store_true', help='Refresh every 30 seconds while the development supervisor runs.')
    args = parser.parse_args()
    previous = read(JSON_OUTPUT, [])
    while True:
        value = snapshot(args.config, previous=previous)
        html = render(value)
        atomic_text(JSON_OUTPUT, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
        atomic_text(HTML_OUTPUT, html)
        print(json.dumps({'observed_at_utc':value['observed_at_utc'],'status':value['status'],
                          'request_costs':value['current_candidate_request_costs'],
                          'observer_model_calls':0},ensure_ascii=False), flush=True)
        if not args.watch or not value['watch_should_continue']:
            return
        previous = value
        time.sleep(30)


if __name__ == '__main__':
    main()
