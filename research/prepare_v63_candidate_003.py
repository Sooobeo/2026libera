"""Create a separate development candidate on the replacement Windows device.

Never reconstruct or reuse candidate 002's unavailable experimental responses.
Run with the newly provisioned task-local Python environment. No model calls.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path, PureWindowsPath
import platform
import subprocess

from research.v63.build_run import read_json, save_json, file_ref
from research.v63.campaign import runtime_identity

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/v63_20261027/continuation/deployment/local_windows'
DEST = BASE / 'candidate_003'
RECORD = ROOT / 'research/device_migration_20261027'
PACKAGES = ('numpy', 'scipy', 'cvxpy', 'clarabel', 'scikit-learn', 'rank-bm25', 'jsonschema')


def sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    if DEST.exists():
        raise ValueError('Candidate 003 already exists; inspect it instead of replacing it.')
    config = read_json(BASE / 'candidate_002/campaign_config.json')
    old = read_json(BASE / 'candidate_002/runtime_candidate.json')
    tokenizer = read_json(BASE / 'tokenizer_config.json')
    old_root = PureWindowsPath(config['workspace_root'])

    def relocated(path):
        return str(ROOT.joinpath(*PureWindowsPath(path).relative_to(old_root).parts))

    tokenizer['library_path'] = relocated(tokenizer['library_path'])
    tokenizer['gguf_path'] = relocated(tokenizer['gguf_path'])
    for library in tokenizer['libraries']:
        library['path'] = relocated(library['path'])
    checks = [(ROOT / item['path'], item['sha256'])
              for item in old['execution_environment']['binary_artifacts']]
    checks += [(Path(item['path']), item['sha256']) for item in tokenizer['libraries']]
    checks += [(Path(tokenizer['gguf_path']), tokenizer['gguf_sha256']),
               (ROOT / 'tmp/v63_local_ollama/models/manifests/registry.ollama.ai/library/qwen3/1.7b', old['model_sha256'])]
    for path, expected in checks:
        if not path.is_file() or sha_file(path) != expected:
            raise ValueError('Missing or changed pinned asset: ' + str(path))
    hardware = json.loads(subprocess.check_output([
        'powershell.exe', '-NoProfile', '-Command',
        '[ordered]@{cpu=(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors);'
        'memory=(Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory)} | ConvertTo-Json -Depth 4'
    ], text=True))
    environment = deepcopy(old['execution_environment'])
    environment.update(
        candidate_id='windows_cpu_device_migration_003',
        python_version=platform.python_version(),
        python_packages={name: importlib.metadata.version(name) for name in PACKAGES},
        cpu=hardware['cpu'], physical_memory_KiB=hardware['memory']['TotalVisibleMemorySize'],
        launcher=file_ref(ROOT / 'research/start_v63_local_ollama.ps1', ROOT),
        selection_basis='Replacement device requested by user. Same verified model and inference settings; no effect size, p-value or investment outcome used for selection.')
    environment['server_environment']['OLLAMA_MODELS'] = str(ROOT / 'tmp/v63_local_ollama/models')
    freeze = deepcopy(old)
    freeze.update(execution_environment=environment, main_model_frozen=False,
                  selection_stage='Candidate 003: new-device development restart, 15 then 60 then 720 stages. Previous-device responses are unavailable and are not reused.')
    config.update(workspace_root=str(ROOT),
                  tokenizer_config_path=(DEST / 'tokenizer_config.json').relative_to(ROOT).as_posix(),
                  runtime_freeze_path=(DEST / 'runtime_candidate.json').relative_to(ROOT).as_posix(),
                  execution_environment_path=(DEST / 'execution_environment.json').relative_to(ROOT).as_posix())
    pause_path = ROOT / 'data/v63_20261027/continuation/user_pause_20261027.json'
    pause = read_json(pause_path)
    raw_manifest_path = ROOT / 'data/v63_20261027/continuation/pause_20261027/raw_http_manifest.json'
    raw_manifest = read_json(raw_manifest_path)
    prior_cost_path = ROOT / 'data/v63_20261027/continuation/deployment/prior_candidate_002_cost_ledger.json'
    prior = read_json(prior_cost_path)
    DEST.mkdir(parents=True, exist_ok=False)
    for name, value in [('tokenizer_config.json', tokenizer), ('runtime_candidate.json', freeze),
                        ('execution_environment.json', environment), ('campaign_config.json', config)]:
        save_json(DEST / name, value)
    run_id, identity = runtime_identity(ROOT, freeze, file_ref(DEST / 'tokenizer_config.json', ROOT), config['execution_amendment'])
    if run_id == pause['run_id']:
        raise ValueError('Replacement device must have a separate identity.')
    record = {
        'schema': 'libera_device_migration_v1', 'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'new_device_development_candidate_prepared',
        'user_instruction': '지금 다른 기기에서 진행하는거라 실험에 필요한 환경이 따로 있다면 새로 만들거나 여기에 설치되어있는거 찾아야할거야',
        'previous_run_id': pause['run_id'], 'new_run_id': run_id,
        'old_workspace_root': str(old_root), 'new_workspace_root': str(ROOT),
        'old_python_version': old['execution_environment']['python_version'],
        'new_python_version': environment['python_version'],
        'previous_raw_files_expected': len(raw_manifest),
        'previous_raw_files_available': sum((ROOT / path).is_file() for path in raw_manifest),
        'previous_candidate_responses_reused': 0,
        'previous_experimental_generation_requests_recorded': prior['experimental_generation_requests'] + pause['current_candidate_confirmed_generation_requests'],
        'previous_engineering_generation_requests_recorded': prior['engineering_generation_requests'],
        'previous_recorded_http_seconds_lower_bound': prior['recorded_http_seconds_lower_bound'],
        'historical_cost_scope': 'Previous candidates only; counts from preserved summary receipts. Original HTTP bytes absent on this device. Candidate 002 timing is unknown and is not invented.',
        'prior_evidence': [file_ref(path, ROOT) for path in (pause_path, raw_manifest_path, prior_cost_path)],
        'old_budget_and_pause_modified': False,
        'new_phase_budgets': config['phase_budgets'],
        'new_budget_note': 'Separate candidate: first-start time is created only on its first phase execution. This does not renew or reset candidate 002 budgets.',
        'main_model_frozen': False, 'model_calls_by_preparation': 0,
        'human_review_mode': 'user_assumed_completed', 'actual_independent_human_reviews_claimed': False,
        'input_readiness': file_ref(RECORD / 'input_readiness.json', ROOT),
        'source_archive_limitation': 'Execution uses preserved hash-verified profiles and embedded document units. Downloaded source originals are absent here; no new source-original or independent human audit is claimed.',
        'source_identity': identity,
        'config': file_ref(DEST / 'campaign_config.json', ROOT),
    }
    save_json(DEST / 'selection_receipt.json', record)
    save_json(RECORD / 'migration_receipt.json', record)
    print(json.dumps({'status': record['status'], 'run_id': run_id,
                      'python_version': environment['python_version'], 'model_calls': 0}))


if __name__ == '__main__':
    main()
