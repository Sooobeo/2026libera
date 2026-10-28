"""Run candidate 003's bounded 15/60-stage development sequence, preserving logs.

No model selection, main approval, budget resets, or automatic failure retries.
The existing campaign owns request accounting and exact-response recovery.
"""
from datetime import datetime, timezone
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from research.v63.build_run import read_json, save_json, file_ref
from research.v63.campaign import runtime_identity
from research.v63.campaign_control import campaign_lock, immutable_json, verify_frozen_artifacts
from research.v63.longrun_guardian import check_phase_outputs

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'data/v63_20261027/continuation/deployment/local_windows/candidate_003/campaign_config.json'


def now():
    return datetime.now(timezone.utc).isoformat()


def completed_phase_review(root, config, run_id, phase, identity, context_tokens):
    """Validate completed work without rerunning its campaign or budget clock."""
    directory = root / config['output_root'] / 'phases' / run_id / phase
    measurements_path = directory / 'measurements.json'
    if not measurements_path.is_file():
        return None
    # A completed measurement is a claim to verify, never a reason to repair
    # or regenerate that phase. Hold the same lock as any campaign writer.
    with campaign_lock(root / config['output_root'] / 'runs' / run_id / '.campaign.lock'):
        measurements = read_json(measurements_path)
        if measurements.get('status') != 'completed':
            return None
        names = ('measurements.json', 'records.json', 'prepared_inputs.json',
                 'runtime_identity.json', 'frozen_runtime.json', 'budget_state.json')
        refs = {name: file_ref(directory / name, root) for name in names}
        if read_json(directory / 'runtime_identity.json') != identity:
            raise ValueError('Completed phase has a different saved runtime identity: ' + phase)
        frozen = read_json(directory / 'frozen_runtime.json')
        frozen_id, _ = runtime_identity(root, frozen,
            file_ref(root / config['tokenizer_config_path'], root), config['execution_amendment'])
        if frozen_id != run_id or frozen.get('execution_phase') != phase:
            raise ValueError('Completed phase has a different frozen runtime: ' + phase)
        verify_frozen_artifacts(root, directory / 'frozen_runtime.json')
        for name, expected in identity['code'].items():
            ref = file_ref(directory / 'source_snapshot' / name, root)
            if ref['sha256'] != expected:
                raise ValueError('Completed phase source snapshot changed: ' + name)
            refs['source_snapshot/' + name] = ref
        budget = read_json(directory / 'budget_state.json')
        if budget.get('limits') != config['phase_budgets'][phase]:
            raise ValueError('Completed phase budget limits changed: ' + phase)
        first_started = datetime.fromisoformat(budget['first_started_at_utc'])
        if first_started.utcoffset() is None:
            raise ValueError('Completed phase budget start must include its timezone: ' + phase)
        review = check_phase_outputs(root, config, run_id, phase,
                                     {'max_prompt_tokens': context_tokens})
        if refs != {name: file_ref(directory / name, root) for name in refs}:
            raise ValueError('Completed phase artifacts changed during review: ' + phase)
        return review, {
            'schema': 'libera_completed_development_phase_reuse_v1',
            'recorded_at_utc': now(), 'run_id': run_id, 'phase': phase,
            'reason': 'Existing completed phase passed unchanged-identity and phase-output gates.',
            'phase_artifacts': refs, 'original_budget_first_started_at_utc': budget['first_started_at_utc'],
            'original_phase_generation_requests': measurements['phase_generation_requests'],
            'original_cumulative_wall_seconds': measurements['cumulative_wall_seconds'],
            'campaign_child_launched': False, 'phase_artifacts_modified': False,
            'new_generation_requests': 0,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=CONFIG)
    args = parser.parse_args()
    config_path = args.config.resolve()
    config = read_json(config_path)
    freeze = read_json(ROOT / config['runtime_freeze_path'])
    selected = read_json(config_path.parent / 'selection_receipt.json')
    if selected['config'] != file_ref(config_path, ROOT):
        raise ValueError('Prepared candidate configuration changed.')
    run_id, _ = runtime_identity(ROOT, freeze, file_ref(ROOT / config['tokenizer_config_path'], ROOT), config['execution_amendment'])
    if run_id != selected['new_run_id'] or freeze['main_model_frozen'] is not False:
        raise ValueError('The separate development identity must remain unchanged and unfrozen for main.')
    out = ROOT / config['output_root'] / 'development_supervisor' / run_id
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    logs = out / stamp
    logs.mkdir(parents=True, exist_ok=False)
    if (out / 'state.json').is_file():
        save_json(logs / 'previous_supervisor_state.json', read_json(out / 'state.json'))
    state = {'schema': 'libera_bounded_development_supervisor_v1', 'run_id': run_id,
             'supervisor_pid': os.getpid(), 'started_at_utc': now(),
             'config': file_ref(config_path, ROOT), 'phases': ['technical-smoke', 'paired-feasibility'],
             'main_auto_launch': False, 'logs': str(logs.relative_to(ROOT)),
             'historical_responses_reused': 0, 'completed_phase_reviews': {}}

    def status(value, **fields):
        state.update(status=value, updated_at_utc=now(), **fields)
        save_json(out / 'state.json', state)

    with campaign_lock(out / '.supervisor.lock'):
        awake = False
        child = None
        try:
            if os.name == 'nt':
                awake = bool(ctypes.windll.kernel32.SetThreadExecutionState(0x80000001))
            status('starting', temporary_system_sleep_prevention=awake)
            for phase in state['phases']:
                current_freeze = read_json(ROOT / config['runtime_freeze_path'])
                current_id, current_identity = runtime_identity(ROOT, current_freeze, file_ref(ROOT / config['tokenizer_config_path'], ROOT), config['execution_amendment'])
                if (current_id != run_id or current_freeze['main_model_frozen'] is not False
                        or selected['config'] != file_ref(config_path, ROOT)):
                    raise ValueError('Candidate identity/configuration changed between development phases.')
                reused = completed_phase_review(ROOT, config, run_id, phase,
                                                current_identity, current_freeze['context_tokens'])
                if reused is not None:
                    review, evidence = reused
                    review_path = logs / (phase + '.review.json')
                    immutable_json(review_path, review)
                    evidence['review'] = file_ref(review_path, ROOT)
                    reuse_path = logs / (phase + '.reuse.json')
                    immutable_json(reuse_path, evidence)
                    state['completed_phase_reviews'][phase] = file_ref(review_path, ROOT)
                    state.setdefault('completed_phase_reuse', {})[phase] = file_ref(reuse_path, ROOT)
                    status('phase_reused_after_verification', phase=phase, campaign_pid=None)
                    continue
                command = [sys.executable, '-m', 'research.v63.campaign', str(config_path), '--phase', phase]
                with (logs / (phase + '.stdout.log')).open('wb') as stdout, (logs / (phase + '.stderr.log')).open('wb') as stderr:
                    child = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
                    status('running', phase=phase, campaign_pid=child.pid, command=command)
                    while child.poll() is None:
                        time.sleep(10)
                        status('running', phase=phase, campaign_pid=child.pid)
                if child.returncode:
                    status('stopped_campaign_requires_review', child_exit_code=child.returncode)
                    return child.returncode
                review = check_phase_outputs(ROOT, config, run_id, phase,
                                             {'max_prompt_tokens': freeze['context_tokens']})
                save_json(logs / (phase + '.review.json'), review)
                state['completed_phase_reviews'][phase] = file_ref(logs / (phase + '.review.json'), ROOT)
                status('phase_verified', phase=phase, child_exit_code=0)
            status('feasibility_complete_requires_measured_resource_review', campaign_pid=None,
                   next_step='Root reviews actual 15/60-stage measurements before issuing guardian resource approval.')
            return 0
        except BaseException as exc:
            status('stopped_requires_review', error_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            if child is not None and child.poll() is None:
                # A Windows venv launcher can have its own Python child. Stop
                # this owned process tree so a failed supervisor leaves no
                # orphan campaign issuing further requests. Raw HTTP evidence
                # remains intact; ambiguous in-flight attempts require review.
                if os.name == 'nt':
                    cleanup = subprocess.run(['taskkill.exe', '/PID', str(child.pid), '/T', '/F'],
                                             capture_output=True, text=True)
                    save_json(logs / 'owned_campaign_cleanup.json', {
                        'recorded_at_utc': now(), 'campaign_pid': child.pid,
                        'exit_code': cleanup.returncode, 'stdout': cleanup.stdout,
                        'stderr': cleanup.stderr, 'raw_evidence_deleted': False})
                else:
                    child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=10)
            if awake:
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


if __name__ == '__main__':
    raise SystemExit(main())
