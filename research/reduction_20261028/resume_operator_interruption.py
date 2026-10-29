"""Explicit, one-off continuation of an operator-cancelled request.

Prior raw attempts remain immutable and counted. This does not retry model
output failures. Completed responses are verified and replayed without new
generation; the one cancelled request requires this recorded user instruction.
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
import shutil
import subprocess
import sys
import time

from research.v63.build_run import file_ref, make_numeric_callbacks
from research.v63.campaign import runtime_identity
from research.v63.campaign_control import campaign_lock, final_trace_path, immutable_json, verify_frozen_artifacts, atomic_json, TERMINAL_STATUSES, task_request_cost, budget_elapsed
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
TASK_ID = 'main-001__F01__R3__1'
PHASE = OUT / 'phases' / RUN_ID / 'B-main'
TASK = OUT / 'runs' / RUN_ID / 'B-main' / TASK_ID
RESUME = TASK / 'recovery_operator_001'
HISTORY = PHASE / 'recovery_inputs' / TASK_ID / 'operator_001_history'
AUTH = RESUME / 'operator_resume_authorization.json'
STATE = OUT / 'operator_resume_state.json'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def hashes(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob('*')) if p.is_file()}


def verify_and_prepare():
    config = read(CONFIG)
    freeze = read(PHASE / 'frozen_runtime.json')
    computed, identity = runtime_identity(ROOT, read(ROOT / config['runtime_freeze_path']),
                                        file_ref(ROOT / config['tokenizer_config_path'], ROOT), config['execution_amendment'], config)
    if computed != RUN_ID:
        raise ValueError('Original source or configuration changed; continuation refused.')
    verify_frozen_artifacts(ROOT, PHASE / 'frozen_runtime.json')
    case = read(TASK / 'input_case.json')
    entry = read(TASK / 'input_identity.json')['entry']
    expected = sha(canonical({'input': entry['input_sha256'], 'arm': entry['arm'],
                              'replicate': entry['replicate'], 'identity': identity}))
    if read(TASK / 'input_identity.json')['sha256'] != expected:
        raise ValueError('Frozen input identity mismatch.')
    if final_trace_path(TASK) is not None:
        raise ValueError('Task already has a terminal trace; do not regenerate it.')
    previous = RecoveryClient(TASK / 'http', freeze, None, history_quiescent=True)
    if len(previous.attempts) != 2 or previous.attempts[0].response is None or not previous.attempts[1].error:
        raise ValueError('History is not the expected complete stage 1 plus operator-interrupted stage 2.')
    cancelled = TASK / 'http/attempt_000002'
    if (cancelled / 'generation.response.bin').exists() or (cancelled / 'attempt_receipt.json').exists():
        raise ValueError('Cancelled request acquired a response/receipt; inspect instead of reissuing.')
    raw_request = (cancelled / 'runner_request.bin').read_bytes()
    stage_request = (TASK / 'trajectory/stage2_round0_request.json').read_text(encoding='utf-8')
    if canonical(json.loads(stage_request)).encode() != raw_request:
        raise ValueError('Cancelled stage 2 request differs from its saved runner request.')
    source_hashes = hashes(TASK / 'http')
    RESUME.mkdir(exist_ok=True)
    authorization = {
        'schema': 'libera_explicit_operator_cancel_continuation_v1', 'run_id': RUN_ID, 'task_id': TASK_ID,
        'user_instruction': '그니까 실패라는게 실험이잘못된게 아니라 그냥 모델이 잘못말한거지? 결과 내는 데에는 문제가 없는거지? 그런거면 그냥 계속 진행해 / 엉 그냥 계속 진행해',
        'reason': 'Assistant stopped the campaign while considering an output fix; user clarified that model failures should be retained and original execution continued.',
        'automatic_retry': False, 'changes_to_prompts_schemas_model_design_or_failure_policy': False,
        'all_completed_trajectories_reused': 12, 'failed_model_outputs_regenerated': 0,
        'normal_recovery_block_reason': previous.attempts[1].error,
        'cancelled_request_sha256': hashlib.sha256(raw_request).hexdigest(),
        'cancelled_request_disposition': 'Preserve and count the cancelled attempt; explicitly reissue its unchanged bytes once, without discarding any observed model output.',
        'prior_http_file_hashes': source_hashes,
        'script': file_ref(Path(__file__), ROOT),
    }
    immutable_json(AUTH, authorization)
    if not HISTORY.exists():
        HISTORY.mkdir(parents=True)
        shutil.copytree(TASK / 'http/attempt_000001', HISTORY / 'attempt_000001')
        immutable_json(HISTORY / 'operator_history_manifest.json', {
            'authorization': file_ref(AUTH, ROOT),
            'replayed_completed_attempts': ['attempt_000001'],
            'preserved_cancelled_attempt': str(cancelled),
            'excluded_cancelled_attempt_reason': previous.attempts[1].error,
        })
    replay = RecoveryClient(HISTORY, freeze, None, history_quiescent=True)
    replayed = replay((TASK / 'http/attempt_000001/runner_request.bin').read_bytes())
    if replayed.get('new_generation_requests') != 0:
        raise ValueError('Completed prefix did not replay without generation.')
    return config, freeze, case, raw_request, source_hashes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    with campaign_lock(OUT / 'runs' / RUN_ID / '.campaign.lock'):
        config, freeze, case, cancelled_raw, source_hashes = verify_and_prepare()
        if args.prepare_only:
            atomic_json(STATE, {'status': 'prepared_explicit_continuation', 'run_id': RUN_ID,
                               'authorization': str(AUTH), 'new_generation_requests': 0})
            print(json.dumps({'status': 'prepared', 'completed_prefix_verified': True, 'new_generation_requests': 0}))
            return 0
        if (RESUME / 'http').exists() or (RESUME / 'trajectory').exists():
            raise ValueError('This explicitly authorized continuation has already started; do not reissue again.')
        budget_state = read(PHASE / 'budget_state.json')
        if budget_elapsed(budget_state) >= budget_state['limits']['max_wall_seconds']:
            raise ValueError('Persisted campaign time budget is exhausted.')
        if task_request_cost(OUT / 'runs' / RUN_ID)['generation_requests'] + 6 > budget_state['limits']['max_generation_requests']:
            raise ValueError('Insufficient persisted generation budget.')
        atomic_json(STATE, {'status': 'running_explicit_continuation', 'run_id': RUN_ID, 'task_id': TASK_ID,
                           'authorization': str(AUTH), 'started_at_utc': datetime.now(timezone.utc).isoformat()})
        transport = OllamaTransport(config['origin'], freeze, RESUME / 'http')
        new_calls = 0
        def live(raw):
            nonlocal new_calls
            if new_calls == 0 and raw != cancelled_raw:
                raise ProtocolViolation('Explicit continuation changed the cancelled request bytes.')
            if new_calls and raw == cancelled_raw:
                raise ProtocolViolation('The cancelled request may be explicitly reissued only once.')
            if hashes(TASK / 'http') != source_hashes:
                raise ProtocolViolation('Original HTTP evidence changed during continuation.')
            new_calls += 1
            return transport(raw)
        client = RecoveryClient(HISTORY, freeze, live, history_quiescent=True)
        tools, check = make_numeric_callbacks(case)
        native = NativeTokenizer(read(ROOT / config['tokenizer_config_path']))
        try:
            trace = run_trajectory(case['baseline'], case['retrieval'], 'R3', client, tools, check, freeze,
                                   output_dir=RESUME / 'trajectory',
                                   count_rendered_request=lambda request: transport.render_and_count(request, native), engineering=False)
        finally:
            native.close()
        atomic_json(RESUME / 'recovery_receipt.json', client.recovery_receipt())
        if hashes(TASK / 'http') != source_hashes:
            raise ValueError('Original HTTP evidence changed.')
        if trace['status'] not in TERMINAL_STATUSES:
            raise ValueError('Explicit continuation did not reach an allowed terminal state: ' + trace['status'])
        trace_path = RESUME / 'trajectory/trace.json'
        immutable_json(TASK / 'trace_pointer.json', {'relative_path': trace_path.relative_to(TASK).as_posix(),
                                                   'sha256': hashlib.sha256(trace_path.read_bytes()).hexdigest()})
        atomic_json(STATE, {'status': 'interrupted_task_resolved', 'run_id': RUN_ID, 'task_id': TASK_ID,
                           'trajectory_status': trace['status'], 'new_generation_requests': new_calls,
                           'original_cancelled_attempt_retained_and_counted': True})
    # The unchanged campaign now reuses all terminal traces and continues normally.
    old_active = read(OUT / 'active_execution.json')['receipt_path']
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with (OUT / 'supervisor.stdout.log').open('wb') as stdout, (OUT / 'supervisor.stderr.log').open('wb') as stderr:
        process = subprocess.Popen([sys.executable, '-u', str(ROOT / 'research/reduction_20261028/run_selected_main_timed.py')],
                                   cwd=ROOT, stdout=stdout, stderr=stderr, creationflags=flags)
    for _ in range(100):
        if read(OUT / 'active_execution.json')['receipt_path'] != old_active:
            break
        if process.poll() is not None:
            raise ValueError('Campaign supervisor exited before publishing its new receipt.')
        time.sleep(.1)
    else:
        raise ValueError('Campaign supervisor did not publish its new receipt.')
    notice = OUT / 'notifications' / RUN_ID
    with (notice / 'observer.stdout.log').open('wb') as stdout, (notice / 'observer.stderr.log').open('wb') as stderr:
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
        atomic_json(STATE, {'status': 'explicit_continuation_blocked', 'run_id': RUN_ID,
                           'error': repr(exc), 'recorded_at_utc': datetime.now(timezone.utc).isoformat()})
        raise
