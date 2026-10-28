"""Freeze the Windows atomic-write fix as a new candidate; retain interrupted 003."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

from research.v63.build_run import read_json, save_json, file_ref
from research.v63.campaign import runtime_identity
from research.v63.campaign_control import task_request_cost

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/v63_20261027/continuation/deployment/local_windows'
RECORD = ROOT / 'research/device_migration_20261027'
DEST = BASE / 'candidate_004'


def main():
    if DEST.exists():
        raise ValueError('Candidate 004 already exists; never replace a frozen candidate.')
    prior = read_json(BASE / 'candidate_003/selection_receipt.json')
    config = read_json(BASE / 'candidate_003/campaign_config.json')
    freeze = read_json(BASE / 'candidate_003/runtime_candidate.json')
    old_run = ROOT / config['output_root'] / 'runs' / prior['new_run_id']
    costs = task_request_cost(old_run)
    if costs != {'generation_requests': 2, 'confirmed_attempt_records': 1, 'uncertain_dispatch_requests': 1}:
        raise ValueError('Interrupted candidate request inventory changed; review before freezing.')
    attempt = old_run / 'B-development/development-001__F03__R0__1/http/attempt_000002'
    if not (attempt / 'generation.dispatch_started.json').is_file() or (attempt / 'generation.response.bin').exists():
        raise ValueError('Unexpected second-attempt boundary.')
    old_supervisor = ROOT / config['output_root'] / 'development_supervisor' / prior['new_run_id']
    cleanup = list(old_supervisor.rglob('owned_campaign_cleanup.json'))
    if len(cleanup) != 1 or read_json(cleanup[0])['exit_code'] != 0:
        raise ValueError('Owned campaign cleanup must be verified.')
    verification = read_json(RECORD / 'atomic_write_fix_verification.json')
    if verification['status'] != 'passed':
        raise ValueError('Windows atomic-write regression checks must pass.')
    old_files = [file_ref(p, ROOT) for p in sorted(old_run.rglob('*')) if p.is_file() and p.name != '.campaign.lock']
    interrupted = {
        'schema': 'libera_interrupted_candidate_retention_v1',
        'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'run_id': prior['new_run_id'], 'status': 'retained_interrupted_no_automatic_retry',
        'cause': 'Windows sharing violation while replacing supervisor heartbeat JSON; owned campaign was terminated.',
        'request_costs': costs, 'saved_original_responses': 1,
        'second_request': 'Sent and canceled according to server logs; no client response/attempt receipt. Preserve one uncertain reservation; no synthetic response or operational-success reclassification.',
        'old_budget_reset': False, 'raw_evidence_deleted': False,
        'source_snapshot_preserved': True,
        'cleanup': file_ref(cleanup[0], ROOT), 'original_artifacts': old_files,
        'first_generation_receipt': read_json(old_run / 'B-development/development-001__F03__R0__1/http/attempt_000001/generation.receipt.json'),
        'fix_verification': file_ref(RECORD / 'atomic_write_fix_verification.json', ROOT),
        'selection_reason': 'Infrastructure correction only. Investment outputs, effect sizes and p-values are not selection inputs.',
    }
    save_json(RECORD / 'candidate003_interruption.json', interrupted)
    env = deepcopy(freeze['execution_environment'])
    env['candidate_id'] = 'windows_cpu_atomic_write_fix_004'
    env['selection_basis'] = interrupted['selection_reason']
    freeze.update(execution_environment=env, main_model_frozen=False,
                  selection_stage='Candidate 004: Windows transient-sharing fix; fresh 15/60/720 development gates. Interrupted 003 responses are retained and excluded.')
    config.update(runtime_freeze_path=(DEST / 'runtime_candidate.json').relative_to(ROOT).as_posix(),
                  execution_environment_path=(DEST / 'execution_environment.json').relative_to(ROOT).as_posix(),
                  tokenizer_config_path=(DEST / 'tokenizer_config.json').relative_to(ROOT).as_posix())
    DEST.mkdir(parents=True, exist_ok=False)
    for name, data in [('campaign_config.json', config), ('runtime_candidate.json', freeze),
                       ('execution_environment.json', env), ('tokenizer_config.json', read_json(BASE / 'candidate_003/tokenizer_config.json'))]:
        save_json(DEST / name, data)
    run_id, identity = runtime_identity(ROOT, freeze, file_ref(DEST / 'tokenizer_config.json', ROOT), config['execution_amendment'])
    record = deepcopy(prior)
    record.update(recorded_at_utc=datetime.now(timezone.utc).isoformat(),
                  status='windows_atomic_write_fix_candidate_prepared', candidate='004',
                  previous_run_id=prior['new_run_id'], new_run_id=run_id,
                  previous_experimental_generation_requests_recorded=prior['previous_experimental_generation_requests_recorded'] + costs['generation_requests'],
                  previous_uncertain_dispatch_reservations=costs['uncertain_dispatch_requests'],
                  previous_recorded_http_seconds_lower_bound=prior['previous_recorded_http_seconds_lower_bound'] + interrupted['first_generation_receipt']['elapsed_seconds'],
                  historical_cost_scope='Previous device summaries (14 experimental + 5 engineering), plus interrupted candidate 003: one closed original response and one sent/canceled request retained as an uncertain reservation. Neither candidate contributes observations to 004.',
                  prior_evidence=prior['prior_evidence'] + [file_ref(RECORD / 'candidate003_interruption.json', ROOT)],
                  interruption_fix=file_ref(RECORD / 'atomic_write_fix_verification.json', ROOT),
                  retained_server_note='The same isolated server remains alive. Its prompt cache may be warm after the interrupted run; no cold-cache timing claim is made.',
                  source_identity=identity, config=file_ref(DEST / 'campaign_config.json', ROOT),
                  new_budget_note='Separate code identity after an infrastructure fix. Preserve all original 002/003 clocks and calls; 004 starts its own phase clock on first execution.')
    save_json(DEST / 'selection_receipt.json', record)
    save_json(RECORD / 'candidate004_selection_receipt.json', record)
    print(json.dumps({'status': record['status'], 'run_id': run_id, 'old_requests_retained': costs, 'model_calls': 0}))


if __name__ == '__main__':
    main()
