"""Freeze the measured Vulkan candidate after the replacement PC restarted.

Historical attempts and budgets are retained; no lost responses are invented
or reused under a new hardware identity. This helper performs no model calls.
"""
from copy import deepcopy
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from research.v63.build_run import read_json, save_json, file_ref
from research.v63.campaign import runtime_identity
from research.v63.campaign_control import task_request_cost

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/v63_20261027/continuation/deployment/local_windows'
DEST = BASE / 'candidate_005'
RECORD = ROOT / 'research/device_migration_20261027'
FOLLOWUP = RECORD / 'followup_20261027'
PROBE = ROOT / 'data/v63_20261027/runtime/local_windows/vulkan_probe_20261027T094843038524Z'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revise-unstarted', action='store_true', help='Archive and revise an unlaunched candidate after prelaunch review.')
    args = parser.parse_args()
    previous_prelaunch = None
    if DEST.exists():
        if not args.revise_unstarted:
            raise ValueError('Candidate 005 already exists; inspect rather than replace it.')
        old_selection = read_json(DEST / 'selection_receipt.json')
        old_config = read_json(DEST / 'campaign_config.json')
        old_output = ROOT / old_config['output_root']
        if any((old_output / kind / old_selection['new_run_id']).exists() for kind in ('runs', 'phases', 'development_supervisor')):
            raise ValueError('An already launched identity cannot be revised in place.')
        backup = FOLLOWUP / ('candidate005_prelaunch_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        shutil.copytree(DEST, backup)
        previous_prelaunch = {'run_id': old_selection['new_run_id'], 'archive': str(backup.relative_to(ROOT)),
                              'reason': 'Prelaunch review corrected launcher lifecycle and inherited provenance labels; zero experimental requests under the archived draft identity.'}
    prior = read_json(BASE / 'candidate_004/selection_receipt.json')
    config = read_json(BASE / 'candidate_004/campaign_config.json')
    freeze = read_json(BASE / 'candidate_004/runtime_candidate.json')
    probe = read_json(RECORD / 'gpu_probe_summary.json')
    launch = read_json(PROBE / 'server_launch.json')
    evidence = read_json(FOLLOWUP / 'candidate004_review.json')
    reboot = read_json(FOLLOWUP / 'reboot_quiescence.json')
    old_run = ROOT / config['output_root'] / 'runs' / prior['new_run_id']
    costs = task_request_cost(old_run)
    if costs != {'generation_requests': 3, 'confirmed_attempt_records': 2, 'uncertain_dispatch_requests': 1}:
        raise ValueError('Interrupted candidate inventory changed; review before selection.')
    verified = evidence['verification']
    if (evidence['affected_run_id'] != prior['new_run_id']
            or evidence['status'] != 'verified_preserved_responses_resume_blocked_after_reboot'
            or evidence['costs'] != costs
            or verified['runtime_identity_matches'] is not True
            or verified['all_code_hashes_match'] is not True
            or verified['all_frozen_artifact_hashes_match'] is not True
            or verified['verified_replays'] != 2
            or verified['expected_missing_tail_blocked'] is not True):
        raise ValueError('Prior-candidate review does not verify this interrupted run.')
    if (probe['status'] != 'engineering_generation_completed'
            or probe['engineering_generation_requests'] != 1
            or probe['experimental_generation_requests'] != 0
            or probe['provider_token_count_matches_exact'] is not True
            or probe['model_sha256'] != freeze['model_sha256']
            or probe['loaded_model']['digest'] != freeze['model_sha256']
            or probe['origin'] != launch['origin']
            or probe['actual_gpu_layers_offloaded'] != probe['actual_model_layers']
            or probe['actual_gpu_layers_offloaded'] <= 0
            or probe['all_binary_hash_and_signature_checks_passed'] is not True
            or probe['loaded_model']['context_length'] != 32768
            or probe['loaded_model']['size_vram'] <= 0
            or probe['minimum_available_memory_bytes'] < 2 * 1024**3):
        raise ValueError('Measured GPU feasibility did not meet the declared engineering gate.')
    if reboot['old_campaign_and_inference_processes_present'] is not False:
        raise ValueError('Old execution has not been reconciled as stopped.')
    launcher = ROOT / 'research/start_v63_vulkan_ollama.ps1'
    if not launcher.is_file():
        raise ValueError('A reproducible isolated Vulkan launcher is required.')
    binaries = []
    for item in read_json(PROBE / 'binary_manifest.json'):
        actual = file_ref(Path(item['path']), ROOT)
        if actual['sha256'] != item['sha256']:
            raise ValueError('Pinned Vulkan binary changed: ' + item['path'])
        binaries.append({**actual, 'expected_publisher_substring': item['expected_publisher_substring']})
    tokenizer = read_json(BASE / 'candidate_004/tokenizer_config.json')
    old_assets = ROOT / 'tmp/v63_local_ollama'
    new_assets = ROOT / 'tmp/v63_vulkan_probe_20261027'

    def relocated(path):
        return str(new_assets / Path(path).relative_to(old_assets))

    tokenizer['library_path'] = relocated(tokenizer['library_path'])
    tokenizer['gguf_path'] = relocated(tokenizer['gguf_path'])
    for item in tokenizer['libraries']:
        item['path'] = relocated(item['path'])
        if file_ref(Path(item['path']), ROOT)['sha256'] != item['sha256']:
            raise ValueError('Tokenizer library differs after relocation.')
    if file_ref(Path(tokenizer['gguf_path']), ROOT)['sha256'] != tokenizer['gguf_sha256']:
        raise ValueError('Vulkan model bytes differ from the pinned model.')
    env = deepcopy(freeze['execution_environment'])
    env.update(candidate_id='windows_vulkan_arc140v_005', engine_revision='0.35.1',
               inference_engine='official Ollama 0.35.1 Windows portable Vulkan',
               server_environment=launch['environment'], binary_artifacts=binaries,
               server_environment_evidence=file_ref(PROBE / 'server_launch.json', ROOT),
               launcher=file_ref(launcher, ROOT),
               accelerator={'api': 'Vulkan', 'device': probe['gpu_device'],
                            'driver_version': probe['gpu_driver_version'], 'probe_layers_offloaded': probe['actual_gpu_layers_offloaded'],
                            'probe_context_tokens': 32768, 'probe': file_ref(RECORD / 'gpu_probe_summary.json', ROOT)},
               selection_basis='Measured speed, memory, full prompt coverage and exact native/provider token agreement only. No investment content, effect size, p-value or response quality was used.')
    freeze.update(execution_environment=env, main_model_frozen=False,
                  fixed_options={'num_thread': 8, 'num_gpu': -1, 'use_mmap': True, 'num_batch': 256},
                  selection_stage='Candidate 005: measured Vulkan hardware candidate. Fresh 15/60/720 development gates. Interrupted CPU candidate responses are retained and excluded.')
    config.update(origin=launch['origin'],
                  runtime_freeze_path=(DEST / 'runtime_candidate.json').relative_to(ROOT).as_posix(),
                  execution_environment_path=(DEST / 'execution_environment.json').relative_to(ROOT).as_posix(),
                  tokenizer_config_path=(DEST / 'tokenizer_config.json').relative_to(ROOT).as_posix())
    old_receipts = sorted(old_run.rglob('generation.receipt.json'))
    prior_known_seconds = sum(read_json(p)['elapsed_seconds'] for p in old_receipts)
    engineering_receipt = PROBE / 'http/attempt_000001/generation.receipt.json'
    historical = {
        'schema': 'libera_candidate005_historical_costs_v1',
        'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'All recorded earlier candidates plus one new Vulkan engineering probe; excludes candidate 005. Interrupted requests remain charged; no old response fills any 005 slot.',
        'experimental_generation_requests': prior['previous_experimental_generation_requests_recorded'] + costs['generation_requests'],
        'engineering_generation_requests': prior['previous_engineering_generation_requests_recorded'] + 1,
        'uncertain_dispatch_reservations': prior.get('previous_uncertain_dispatch_reservations', 0) + 1,
        'recorded_http_seconds_lower_bound': prior['previous_recorded_http_seconds_lower_bound'] + prior_known_seconds + read_json(engineering_receipt)['elapsed_seconds'],
        'unknown_duration_policy': 'Uncertain-request durations remain unknown. Their request reservations and original evidence are retained; this lower bound is not complete resource time.',
        'evidence': [file_ref(BASE / 'candidate_004/selection_receipt.json', ROOT),
                     file_ref(FOLLOWUP / 'candidate004_review.json', ROOT),
                     file_ref(FOLLOWUP / 'reboot_quiescence.json', ROOT),
                     file_ref(RECORD / 'gpu_probe_summary.json', ROOT),
                     file_ref(engineering_receipt, ROOT)] + [file_ref(p, ROOT) for p in old_receipts],
    }
    historical['generation_requests'] = historical['experimental_generation_requests'] + historical['engineering_generation_requests']
    historical_path = FOLLOWUP / 'candidate005_historical_costs.json'
    if args.revise_unstarted and historical_path.is_file():
        preserved = read_json(historical_path)
        if ({k: v for k, v in preserved.items() if k != 'recorded_at_utc'}
                != {k: v for k, v in historical.items() if k != 'recorded_at_utc'}):
            raise ValueError('Historical cost evidence changed during prelaunch review.')
        historical = preserved
    else:
        save_json(historical_path, historical)
    DEST.mkdir(parents=True, exist_ok=args.revise_unstarted)
    for name, value in [('campaign_config.json', config), ('runtime_candidate.json', freeze),
                        ('execution_environment.json', env), ('tokenizer_config.json', tokenizer)]:
        save_json(DEST / name, value)
    run_id, identity = runtime_identity(ROOT, freeze, file_ref(DEST / 'tokenizer_config.json', ROOT), config['execution_amendment'])
    record = deepcopy(prior)
    record.update(candidate='005', recorded_at_utc=datetime.now(timezone.utc).isoformat(),
                  status='measured_vulkan_development_candidate_prepared',
                  previous_run_id=prior['new_run_id'], new_run_id=run_id,
                  original_device_candidate002={'workspace_root': prior['old_workspace_root'],
                      'python_version': prior['old_python_version'],
                      'raw_files_expected': prior['previous_raw_files_expected'],
                      'raw_files_available_on_this_device': prior['previous_raw_files_available']},
                  old_workspace_root=config['workspace_root'],
                  old_python_version=freeze['execution_environment']['python_version'],
                  previous_raw_files_scope='Original-device candidate 002 only; these legacy counters do not describe the immediately preceding local candidate.',
                  previous_candidate_http_files_preserved=sum(1 for p in old_run.rglob('*') if p.is_file() and 'http' in p.parts),
                  previous_experimental_generation_requests_recorded=historical['experimental_generation_requests'],
                  previous_engineering_generation_requests_recorded=historical['engineering_generation_requests'],
                  previous_uncertain_dispatch_reservations=historical['uncertain_dispatch_reservations'],
                  previous_recorded_http_seconds_lower_bound=historical['recorded_http_seconds_lower_bound'],
                  historical_cost_scope=historical['scope'],
                  prior_evidence=prior['prior_evidence'] + [file_ref(FOLLOWUP / 'candidate005_historical_costs.json', ROOT)],
                  config=file_ref(DEST / 'campaign_config.json', ROOT), source_identity=identity,
                  retained_server_note='The measured isolated Vulkan server is reused after an explicit unload. OS cache state is uncontrolled; no cold-cache comparison is claimed.',
                  new_budget_note='New hardware identity has its own phase clock; the original candidate 002/003/004 clocks and dispatch reservations remain unchanged.',
                  model_calls_by_preparation=0, previous_candidate_responses_reused=0,
                  resource_probe=file_ref(RECORD / 'gpu_probe_summary.json', ROOT),
                  source_limitations_unchanged=True,
                  recovery_policy='Existing strict RecoveryClient. No new lost-response retry exception or invented response is introduced.')
    if previous_prelaunch:
        record['prelaunch_revision'] = previous_prelaunch
    save_json(DEST / 'selection_receipt.json', record)
    save_json(FOLLOWUP / 'candidate005_selection_receipt.json', record)
    print(json.dumps({'status': record['status'], 'run_id': run_id,
                      'historical_requests': historical['generation_requests'], 'model_calls': 0}))


if __name__ == '__main__':
    main()
