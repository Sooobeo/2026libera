"""Record verified background-observer launch; never launches or scores models."""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import watch_v492_postpilot as watcher
from research_progress_log import append, read_verified

ROOT = Path(__file__).resolve().parents[1]
CONFIG = 'research/v492_postpilot_config_20261019_r2.json'
CONFIG_SHA = '412034bff24f6d1b403e76e70245b20c191462a8837989fe20237f43001acc02'
PRECHECK = 'research/v492_postpilot_launch_preflight_20261019.json'
ACCEPTANCE = 'research/v492_postpilot_launch_acceptance_20261019.json'
HANDOFF = 'research/v492_postpilot_handoff_20261019.json'
SNAPSHOT = 'research/v492_postpilot_launch_status_snapshot_20261019.json'
RECEIPTS = [
    'research/v492_analyzer_verification_20261019.json',
    'research/v492_masked_review_verification_20261019_r2.json',
    'research/v492_postpilot_watcher_unit_review_20261019.json',
    'research/v492_postprocessing_integration_20261019_r2.json',
]
CODE_SHA = {
    'research/analyze_v492_pilot.py': '841c1f941e2c39165f84f51f5df283ca7a3c5727de285d4ad56edfa50166529f',
    'research/build_v492_masked_review.py': 'f4f9295a657892431d76b79310b3af229dc5bc7d972b098adb10ff5dd29a1f77',
    'research/stop_sector_v492_cpu.ps1': '065b97e1d4005e8ab55eff1f3c9be553fa897b075896d50ccc318386ad74f308',
    'research/watch_v492_postpilot.py': 'f431a1b147a1f5b6053821820042074464dbd12bf592f3ece455e9b84ed583b9',
}


def now():
    return datetime.now(timezone.utc).isoformat()


def ref(name):
    return watcher.ref(ROOT, name)


def read(name):
    return watcher.read(ROOT / name)


def write_new(name, value):
    with (ROOT / name).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def verified_inputs():
    assert ref(CONFIG)['sha256'] == CONFIG_SHA, 'Configuration differs'
    config = read(CONFIG)
    for name, expected in CODE_SHA.items():
        assert ref(name)['sha256'] == expected, 'Code differs: ' + name
    results = [read(name) for name in RECEIPTS]
    for result in results:
        assert result['status'] == 'PASS', 'Verification did not pass'
        for item in watcher.refs_in(result):
            watcher.checked(ROOT, item)
    analyzer, masked, unit, integration = results
    execution = next(c for c in analyzer['checks'] if c['id'] == 'synthetic_execution')
    assert execution['tests_run'] == 20 and execution['exit_code'] == 0
    assert masked['tests']['observed_tests'] == 15 and masked['tests']['exit_code'] == 0
    assert 'Ran 15 tests' in masked['tests']['stderr'] and masked['tests']['stderr'].strip().endswith('OK')
    assert unit['exit_code'] == 0 and unit['signal'] is None and unit['input_hashes_unchanged'] is True
    assert 'Ran 15 tests' in unit['stderr'] and unit['stderr'].strip().endswith('OK')
    assert len(integration['checks']) == 14 and all(c['pass'] is True for c in integration['checks'])
    assert integration['config_ref'] == ref(CONFIG)
    assert integration['model_calls'] == 0 and integration['shutdown_performed'] is False
    assert integration['actual_model_output_content_read'] is False
    for role, item in config['scripts'].items():
        assert integration['script_refs'][role] == item
    watcher.preflight(ROOT, config)
    return config


def precheck():
    config = verified_inputs()
    result = watcher.watch(ROOT, CONFIG, CONFIG_SHA, dry_run=True)
    assert result['status'] == 'dry_run_validated_no_commands'
    status = ROOT / config['status_path']
    assert not status.exists() and not status.with_name(status.name + '.lock').exists(), 'Already launched'
    assert not (ROOT / config['run_dir'] / 'pilot_summary.json').exists(), 'Pilot already terminal; inspect before launch'
    receipt = {
        'status': 'PASS_for_background_observer_launch', 'recorded_at_utc': now(),
        'review_mode': 'AI_technical_check_not_independent_human_validation',
        'verification_counts': {'analyzer_unit_tests': 20, 'masked_unit_tests': 15, 'watcher_unit_tests': 15, 'actual_integration_checks': 14},
        'input_refs': [ref(CONFIG)] + [ref(p) for p in CODE_SHA] + [ref(p) for p in RECEIPTS],
        'recorder_ref': ref('research/record_v492_postpilot_launch.py'),
        'dry_run': result, 'generation_requests': 0, 'shutdown_performed': False,
        'actual_model_output_content_read': False, 'pilot_complete': False,
        'semantic_review': 'pending_after_pilot', 'visual_qa': 'deferred_until_machine_idle',
    }
    write_new(PRECHECK, receipt)
    return ref(PRECHECK)


def process_identity(pid):
    """Query only the explicitly owned PID, without enumerating other processes."""
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise OSError(ctypes.get_last_error(), 'Cannot query owned PID ' + str(pid))
    try:
        exit_code, length = wintypes.DWORD(), wintypes.DWORD(32768)
        image = ctypes.create_unicode_buffer(length.value)
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            raise OSError(ctypes.get_last_error(), 'Cannot read process status')
        if not kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length)):
            raise OSError(ctypes.get_last_error(), 'Cannot read owned executable')
        return {'pid': pid, 'alive': exit_code.value == 259, 'executable': image.value}
    finally:
        kernel.CloseHandle(handle)


def stage_metadata(run):
    result = []
    for folder in sorted(run.iterdir()):
        if folder.is_dir() and folder.name.endswith(('__D0', '__F0')) and not (folder / 'supervisor_result.json').exists():
            phase_path = folder / 'worker_phases.jsonl'
            phases = [json.loads(line) for line in phase_path.read_text(encoding='utf8').splitlines()] if phase_path.exists() else []
            stream = folder / 'http_0001_generation/events.jsonl'
            item = {'stage_directory': folder.name, 'last_phase': phases[-1] if phases else None,
                    'stream_path': stream.relative_to(ROOT).as_posix(), 'stream_exists': stream.exists()}
            if stream.exists():
                stat = stream.stat()
                item.update(stream_bytes=stat.st_size, stream_modified_ns=stat.st_mtime_ns)
            result.append(item)
    return result


def record_launch(session_id):
    config = verified_inputs()
    preflight = read(PRECHECK)
    assert preflight['status'] == 'PASS_for_background_observer_launch'
    watcher.checked(ROOT, preflight['recorder_ref'])
    for item in preflight['input_refs']:
        watcher.checked(ROOT, item)
    status_path = ROOT / config['status_path']
    status_bytes = status_path.read_bytes()
    status = json.loads(status_bytes)
    lock_path = status_path.with_name(status_path.name + '.lock')
    lock = watcher.read(lock_path)
    assert status['state'] in ('waiting_pilot_summary', 'waiting_valid_completed_pilot_summary')
    assert status['pid'] == lock['pid'] and status['config_ref'] == lock['config_ref'] == ref(CONFIG)
    assert status['model_calls'] == 0 and status['semantic_evaluation'] == 'pending'
    observer = process_identity(status['pid'])
    assert observer['alive'] and Path(observer['executable']).resolve() == Path(config['python_executable']).resolve()
    service = read(config['service_ref']['path'])
    service_process = process_identity(service['pid'])
    assert service_process['alive'] and Path(service_process['executable']).resolve() == Path(service['executable']).resolve()
    run = ROOT / config['run_dir']
    assert not (run / 'pilot_summary.json').exists(), 'Pilot became terminal; record its real state separately'
    before = stage_metadata(run)
    time.sleep(2)
    after = stage_metadata(run)
    assert after, 'No active stage metadata; investigate without cancelling model'
    old = {r['stage_directory']: r for r in before}
    for row in after:
        row['stream_grew_during_observation'] = row.get('stream_bytes', 0) > old.get(row['stage_directory'], {}).get('stream_bytes', 0)
    with (ROOT / SNAPSHOT).open('xb') as stream:
        stream.write(status_bytes)
    receipt = {
        'status': 'background_watcher_launched_pilot_still_in_progress', 'recorded_at_utc': now(),
        'review_mode': 'AI_technical_check_not_independent_human_validation',
        'watcher_exec_session': session_id, 'watcher_process': observer, 'owned_service_process': service_process,
        'watcher_state_observed': status['state'], 'watcher_poll_seconds': status['poll_seconds'],
        'pilot_terminal_summary_present': False, 'active_stage_metadata': after,
        'active_stage_evidence_limit': 'Only process identity, phase metadata and stream file sizes/timestamps inspected; no response content opened. File growth evidences activity, not semantic correctness.',
        'input_refs': [ref(PRECHECK), ref(CONFIG), ref(SNAPSHOT), ref(lock_path)] + [ref(p) for p in CODE_SHA] + [ref(p) for p in RECEIPTS],
        'automatic_postprocessing': ['deterministic_arithmetic_report_once', 'masked_review_bundle_once', 'owned_idle_service_cleanup_once_if_confirmed'],
        'generation_requests_by_this_setup': 0, 'main_calls_by_this_setup': 0, 'generation_retries': 0,
        'actual_model_output_content_read': False, 'semantic_review': 'pending_after_pilot',
        'visual_qa': 'deferred_until_machine_idle', 'pilot_results_complete': False,
        'main_experiment_authorized_by_watcher': False, 'raw_attempts_preserved': True,
        'no_archive_or_delete': True, 'frozen_files_changed_by_setup': False,
    }
    write_new(ACCEPTANCE, receipt)
    ledger = ROOT / 'research/v492_process_20261019.jsonl'
    event = append('postpilot_background_observer_started', 'running',
        'Current analyzer 20 tests, masked packaging 15 tests, watcher 15 tests and actual integration 14 checks passed. One background observer now waits for the completed five-case pilot summary; no result/semantic-success claim. It will attempt arithmetic and masked packaging once, then guarded owned-idle cleanup even if a postprocessor fails. Semantic review and deferred visual QA remain pending.',
        [ROOT / ACCEPTANCE, ROOT / CONFIG] + [ROOT / p for p in RECEIPTS], path=ledger)
    assert read_verified(ledger)[-1]['event_sha256'] == event['event_sha256']
    paths = set([PRECHECK, ACCEPTANCE, SNAPSHOT, CONFIG] + RECEIPTS + list(CODE_SHA) + [
        'research/record_v492_postpilot_launch.py', 'research/v492_postpilot_watcher_observation_note_20261019.json',
        'research/test_analyze_v492_pilot.py', 'research/test_v492_masked_review.py', 'research/test_watch_v492_postpilot.py',
        'research/verify_v492_postprocessing_integration.py', 'research/verify_v492_postprocessing_integration_r2.py',
        'research/v492_postprocessing_integration_20261019.json', 'research/v492_postpilot_config_20261019.json',
        'research/v492_masked_review_verification_20261019.json',
    ])
    history = ROOT / 'research/artifacts/v492_masked_review_history_20261019'
    paths.update(p.relative_to(ROOT).as_posix() for p in history.rglob('*') if p.is_file())
    handoff = {'status': 'background_handoff_ready_pilot_in_progress', 'recorded_at_utc': now(),
        'watcher_exec_session': session_id, 'watcher_pid': status['pid'],
        'immutable_artifacts': [ref(p) for p in sorted(paths)],
        'append_only_ledger_event': event, 'live_status_path': config['status_path'],
        'live_status_is_mutable_and_not_an_immutable_hash_target': True,
        'pending': ['pilot_completion', 'postprocessor_execution_and_receipts', 'AI_assisted_semantic_review', 'deferred_visual_QA'],
        'no_model_output_content_read_during_setup': True, 'generation_requests_by_setup': 0,
        'main_frozen': False, 'pilot_completed': False}
    write_new(HANDOFF, handoff)
    return {'acceptance': ref(ACCEPTANCE), 'handoff': ref(HANDOFF), 'watcher_pid': status['pid'], 'exec_session': session_id}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['precheck', 'record'])
    parser.add_argument('--session-id', type=int)
    args = parser.parse_args()
    if args.mode == 'record' and args.session_id is None:
        parser.error('--session-id is required for the actual launched observer')
    try:
        result = precheck() if args.mode == 'precheck' else record_launch(args.session_id)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        error_name = 'research/v492_postpilot_setup_error_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json'
        write_new(error_name, {'status': 'attention_required_no_automatic_retry', 'recorded_at_utc': now(),
            'mode': args.mode, 'error_type': type(exc).__name__, 'error': str(exc),
            'watcher_may_already_be_running': args.mode == 'record', 'exec_session': args.session_id,
            'generation_requests_by_recorder': 0, 'shutdown_requests_by_recorder': 0,
            'instruction': 'Inspect the existing observer and artifacts; never launch a second observer automatically.'})
        raise
