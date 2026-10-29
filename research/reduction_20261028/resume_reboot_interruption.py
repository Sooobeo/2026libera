"""One explicitly authorized reboot recovery, preserving damaged raw evidence.

Stage 1 content is recovered from the hash-verified downstream stage 2 request.
Lost provider telemetry is never invented. No frozen experimental source changes.
"""
import os
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from research.reduction_20261028.resume_operator_interruption import read, hashes
from research.v63.build_run import file_ref, make_numeric_callbacks
from research.v63.campaign import runtime_identity
from research.v63.campaign_control import (
    campaign_lock, final_trace_path, immutable_json, verify_frozen_artifacts,
    atomic_json, TERMINAL_STATUSES, task_request_cost, budget_elapsed,
)
from research.v63.exact_tokenizer import NativeTokenizer
from research.v63.ollama_transport import OllamaTransport
from research.v63.recovery import RecoveryClient
from research.v63.retrieval import canonical, sha
from research.v63.transport_errors import ProtocolViolation
from research.v64_reduced.runtime import run_trajectory

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data/v64_20261028/main_only_results'
CONFIG = OUT / 'direct_main_config.json'
RUN_ID = 'b713cc4533c2f5b18e165f51592ca8f89223977fd1e15aee202adff8bbca6b54'
TASK_ID = 'main-009__F03__R0__1'
PHASE = OUT / 'phases' / RUN_ID / 'B-main'
TASK = OUT / 'runs' / RUN_ID / 'B-main' / TASK_ID
RESUME = TASK / 'recovery_reboot_001'
AUTH = RESUME / 'reboot_resume_authorization.json'
STATE = OUT / 'reboot_resume_state.json'
CONFIG_HASH = 'e868b80e67afae04b5f261b4d8efbf6b7d8219d5da8cd56acfb3325adaff01b0'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_and_prepare():
    if digest(CONFIG.read_bytes()) != CONFIG_HASH:
        raise ValueError('Frozen configuration changed.')
    config, freeze = read(CONFIG), read(PHASE / 'frozen_runtime.json')
    computed, identity = runtime_identity(
        ROOT, read(ROOT / config['runtime_freeze_path']),
        file_ref(ROOT / config['tokenizer_config_path'], ROOT),
        config['execution_amendment'], config)
    if computed != RUN_ID:
        raise ValueError('Original source/model/configuration identity changed.')
    verify_frozen_artifacts(ROOT, PHASE / 'frozen_runtime.json')
    case = read(TASK / 'input_case.json')
    entry = read(TASK / 'input_identity.json')['entry']
    expected = sha(canonical({'input': entry['input_sha256'], 'arm': entry['arm'],
                              'replicate': entry['replicate'], 'identity': identity}))
    if read(TASK / 'input_identity.json')['sha256'] != expected or entry['arm'] != 'R0':
        raise ValueError('Frozen task identity differs.')
    if final_trace_path(TASK) is not None:
        raise ValueError('Task already has a terminal trace; no regeneration allowed.')
    records = read(PHASE / 'records.json')
    if len(records) != 83:
        raise ValueError('Unexpected saved checkpoint.')
    for row in records:
        raw = Path(row['trace_path']).read_bytes()
        if digest(raw) != row['trace_sha256'] or json.loads(raw)['status'] != row['trajectory_status']:
            raise ValueError('Previously completed trace changed.')
    previous = RecoveryClient(TASK / 'http', freeze, None, history_quiescent=True)
    if len(previous.attempts) != 2 or not all(a.error for a in previous.attempts):
        raise ValueError('History differs from observed reboot damage.')
    interrupted = TASK / 'http/attempt_000002'
    if (interrupted / 'generation.response.bin').exists() or (interrupted / 'attempt_receipt.json').exists():
        raise ValueError('Interrupted request has response evidence; do not reissue.')
    first_raw = (TASK / 'http/attempt_000001/runner_request.bin').read_bytes()
    first_receipt = read(TASK / 'http/attempt_000001/attempt_receipt.json')
    if first_receipt['runner_request_sha256'] != digest(first_raw) or first_receipt['model_sha256'] != freeze['model_sha256'] or first_receipt['generation_requests'] != 1:
        raise ValueError('Saved first request/identity receipt differs.')
    second = read(TASK / 'trajectory/stage2_round0_request.json')
    second_raw = canonical(second).encode('utf-8')
    adapter = object.__new__(OllamaTransport)
    adapter.freeze = deepcopy(freeze)
    translated = adapter._translate(second_raw)
    dispatch = read(interrupted / 'generation.dispatch_started.json')
    if digest(translated) != dispatch['request_sha256']:
        raise ValueError('Recovered stage 2 request does not match dispatched bytes.')
    first = json.loads(first_raw)
    if second['messages'][:3] != first['messages'] or len(second['messages']) != 5 or second['messages'][3]['role'] != 'assistant':
        raise ValueError('Stage 1 content is not the exact retained downstream history.')
    content = second['messages'][3]['content']
    if json.loads(content).get('kind') != 'final':
        raise ValueError('Unexpected stage 1 output form.')
    source_hashes = hashes(TASK / 'http')
    authorization = {
        'schema': 'libera_explicit_reboot_continuation_v1', 'run_id': RUN_ID, 'task_id': TASK_ID,
        'user_instruction': '컴퓨터 갑자기 재부팅돼서 껐다 켜졌는데 중단된 지점 확인하고 재개해',
        'windows_boot_time_kst_to_second': '2026-10-28T21:52:15+09:00',
        'windows_event_41_observed_kst_to_second': '2026-10-28T21:52:18+09:00',
        'automatic_retry': False, 'changed_model_prompts_design_or_failure_policy': False,
        'completed_trajectories_verified_and_reused': 83, 'model_output_failures_regenerated': 0,
        'normal_recovery_errors': [a.error for a in previous.attempts],
        'prior_http_file_hashes': source_hashes,
        'records_checkpoint': file_ref(PHASE / 'records.json', ROOT),
        'retained_stage2_request': file_ref(TASK / 'trajectory/stage2_round0_request.json', ROOT),
        'stage1_content_sha256': digest(content.encode('utf-8')),
        'stage1_request_sha256': digest(first_raw),
        'stage2_recovered_runner_request_sha256': digest(second_raw),
        'stage2_translated_request_sha256': digest(translated),
        'stage2_original_dispatch': dispatch,
        'disposition': 'Replay the exact retained stage 1 content; explicitly reissue unchanged stage 2 once. Preserve all damaged files and count original attempts.',
        'evidence_limit': 'Stage 1 original HTTP envelope, usage, durations and exact finish reason were lost. Retained downstream content and dispatch hash prove the continued conversation bytes, not lost telemetry.',
        'timing_limit': 'No exact interruption time inferred from reboot time. Original stage 1 generation time and interrupted request time are missing from request-duration totals; complete elapsed wall time includes downtime.',
        'script': file_ref(Path(__file__), ROOT),
    }
    RESUME.mkdir(exist_ok=True)
    immutable_json(AUTH, authorization)
    response = {
        'content': content, 'model_sha256': first_receipt['model_sha256'],
        'finish_reason': 'recovered_nonfailure_from_downstream_progression',
        'original_provider_finish_reason': None, 'usage': {},
        'transport_generation_requests': 1, 'new_generation_requests': 0,
        'replayed': True, 'source_elapsed_seconds': 0,
        'source_elapsed_seconds_known': False,
        'elapsed_accounting_note': 'Zero is an omitted-duration accounting placeholder, not a measured generation duration.',
        'transport_log': str(TASK / 'http/attempt_000001'),
        'recovery_provenance': file_ref(AUTH, ROOT),
    }
    immutable_json(RESUME / 'recovered_stage1_response.json', response)
    immutable_json(OUT / 'reboot_measurement_coverage.json', {
        'run_id': RUN_ID, 'recovery_authorization': file_ref(AUTH, ROOT),
        'token_and_request_duration_totals_complete': False,
        'missing_stage1_provider_usage_and_duration': TASK_ID,
        'stage1_response_content_preserved': True,
        'original_stage2_dispatch_retained_as_uncertain': True,
        'interpretation': 'Reported token and generation-duration sums cover available telemetry only; they are lower bounds. Overall wall time includes downtime. Reboot recovery must be disclosed with results.',
    })
    return config, freeze, case, first_raw, second_raw, source_hashes, response


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    with campaign_lock(OUT / 'runs' / RUN_ID / '.campaign.lock'):
        config, freeze, case, first_raw, second_raw, source_hashes, response = verify_and_prepare()
        if args.prepare_only:
            atomic_json(STATE, {'status': 'prepared', 'run_id': RUN_ID, 'task_id': TASK_ID,
                               'authorization': str(AUTH), 'new_generation_requests': 0})
            print(json.dumps({'status': 'prepared', 'verified_completed': 83,
                              'stage1_content_recovered': True, 'stage2_dispatch_hash_matched': True,
                              'new_generation_requests': 0}), flush=True)
            return 0
        if (RESUME / 'http').exists() or (RESUME / 'trajectory').exists():
            raise ValueError('This explicit recovery already started; no automatic repeat.')
        budget = read(PHASE / 'budget_state.json')
        if budget_elapsed(budget) >= budget['limits']['max_wall_seconds'] or task_request_cost(OUT / 'runs' / RUN_ID)['generation_requests'] + 6 > budget['limits']['max_generation_requests']:
            raise ValueError('Persisted budget exhausted.')
        atomic_json(STATE, {'status': 'running_explicit_reboot_continuation', 'run_id': RUN_ID,
                           'task_id': TASK_ID, 'authorization': str(AUTH),
                           'started_at_utc': datetime.now(timezone.utc).isoformat()})
        transport = OllamaTransport(config['origin'], freeze, RESUME / 'http')
        calls = 0
        def client(raw):
            nonlocal calls
            if hashes(TASK / 'http') != source_hashes:
                raise ProtocolViolation('Original HTTP evidence changed.')
            if calls == 0:
                if raw != first_raw:
                    raise ProtocolViolation('Reconstructed stage 1 request differs.')
                calls += 1
                return deepcopy(response)
            if (calls == 1 and raw != second_raw) or (calls > 1 and raw == second_raw):
                raise ProtocolViolation('Only one exact reissue of the interrupted stage 2 is authorized.')
            calls += 1
            value = transport(raw)
            # Flush newly saved operational evidence before moving to the next stage.
            for path in (RESUME / 'http').rglob('*'):
                if path.is_file():
                    with path.open('r+b') as handle:
                        os.fsync(handle.fileno())
            return value
        tools, check = make_numeric_callbacks(case)
        native = NativeTokenizer(read(ROOT / config['tokenizer_config_path']))
        try:
            trace = run_trajectory(case['baseline'], case['retrieval'], 'R0', client, tools, check, freeze,
                                   output_dir=RESUME / 'trajectory',
                                   count_rendered_request=lambda request: transport.render_and_count(request, native), engineering=False)
        finally:
            native.close()
        if hashes(TASK / 'http') != source_hashes or trace['status'] not in TERMINAL_STATUSES:
            raise ValueError('Recovery did not reach an allowed terminal state with preserved evidence.')
        trace['reboot_recovery_provenance'] = file_ref(AUTH, ROOT)
        trace['provider_usage_and_request_duration_complete'] = False
        trace_path = RESUME / 'trajectory/trace.json'
        atomic_json(trace_path, trace)
        immutable_json(TASK / 'trace_pointer.json', {'relative_path': trace_path.relative_to(TASK).as_posix(),
                                                   'sha256': digest(trace_path.read_bytes())})
        atomic_json(RESUME / 'recovery_receipt.json', {
            'authorization': file_ref(AUTH, ROOT), 'replayed_stage1_calls': 1,
            'new_live_calls': calls - 1, 'trajectory_status': trace['status'],
            'original_evidence_preserved': True, 'new_trace': file_ref(trace_path, ROOT),
        })
        atomic_json(STATE, {'status': 'interrupted_task_resolved', 'run_id': RUN_ID,
                           'task_id': TASK_ID, 'trajectory_status': trace['status']})
    old_active = read(OUT / 'active_execution.json')['receipt_path']
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with (RESUME / 'supervisor.stdout.log').open('xb') as stdout, (RESUME / 'supervisor.stderr.log').open('xb') as stderr:
        process = subprocess.Popen([sys.executable, '-u', str(ROOT / 'research/reduction_20261028/run_selected_main_timed.py')],
                                   cwd=ROOT, stdout=stdout, stderr=stderr, creationflags=flags)
    for _ in range(100):
        if read(OUT / 'active_execution.json')['receipt_path'] != old_active:
            break
        if process.poll() is not None:
            raise ValueError('Campaign supervisor exited before its new receipt.')
        time.sleep(.1)
    else:
        raise ValueError('Campaign supervisor did not publish its new receipt.')
    with (RESUME / 'notifier.stdout.log').open('xb') as stdout, (RESUME / 'notifier.stderr.log').open('xb') as stderr:
        notifier = subprocess.Popen(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-STA', '-File',
                                     str(ROOT / 'research/reduction_20261028/watch_main_notification.ps1')],
                                    cwd=ROOT, stdout=stdout, stderr=stderr, creationflags=flags)
    atomic_json(STATE, {'status': 'original_campaign_resumed', 'run_id': RUN_ID,
                       'supervisor_pid': process.pid, 'notification_pid': notifier.pid,
                       'resumed_at_utc': datetime.now(timezone.utc).isoformat()})
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        atomic_json(STATE, {'status': 'explicit_reboot_continuation_blocked', 'run_id': RUN_ID,
                           'error': repr(exc), 'recorded_at_utc': datetime.now(timezone.utc).isoformat()})
        raise
