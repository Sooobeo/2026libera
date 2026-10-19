"""Select a provisional CPU configuration from the declared synthetic probes.

No research outcomes enter this choice. A single observed faster condition is
only an operating candidate; cache/background confounding prevents speed claims.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import sector_v491_runtime as runtime
from sector_v491_tokenizer import GGUF_SHA256

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/local_sector_runtime/v491_cpu_preflight_20261019'


def main():
    candidates = []
    outcomes = []
    for folder in ('synthetic_large_input', 'synthetic_large_input_threads8'):
        target = BASE / folder
        supervisor = runtime.remote.read(target / 'supervisor_result.json')
        worker = supervisor.get('worker', {})
        cleanup = runtime.remote.read(target / 'cleanup.json')
        row = {'probe': folder, 'status': worker.get('status', supervisor['supervisor_status']),
               'supervisor_seconds': supervisor['elapsed_seconds'], 'cleanup': cleanup['status']}
        outcomes.append(row)
        if row['status'] == 'completed' and row['cleanup'] == 'no_resident_models_observed':
            candidates.append((row['supervisor_seconds'], target))
    if candidates:
        selected = min(candidates, key=lambda item: item[0])[1]
        basis = 'Lowest observed supervisor walltime among completed predeclared source-free large-input probes; provisional only.'
    else:
        selected = BASE / 'synthetic_smoke'
        basis = 'Both large-input probes failed; only the short CPU2 smoke supports a diagnostic configuration, not formal pilot feasibility.'
    spec = runtime.remote.read(selected / 'spec.json')
    refs = []
    for role, path in [('cpu_service', BASE / 'service_receipt.json'),
                       ('smoke_spec', selected / 'spec.json'),
                       ('smoke_result', selected / 'worker_summary.json')]:
        refs.append({'role': role, 'path': path.relative_to(ROOT).as_posix(), 'sha256': runtime.remote.sha(path)})
    value = runtime.candidate_runtime(backend='cpu', num_ctx=65536,
        num_thread=spec['body']['options']['num_thread'],
        tokenizer_config={'library_dir': str(Path(os.environ['LOCALAPPDATA']) / 'Programs/Ollama/lib/ollama'),
                          'gguf_path': str(Path.home() / '.ollama/models/blobs' / ('sha256-' + GGUF_SHA256))},
        backend_evidence=refs)
    runtime.validate_runtime(value)
    runtime.remote.save(ROOT / 'research/v491_runtime_candidate_20261019.json', value)
    receipt = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'selection_basis': basis, 'outcomes_all_preserved': outcomes,
        'selected_probe': selected.relative_to(ROOT).as_posix(),
        'num_thread': value['options']['num_thread'], 'num_ctx': 65536,
        'selected_backend': 'cpu', 'full_task_feasibility_validated': False,
        'human_review_completed': False, 'main_allowed': False, 'frozen': False,
        'confounders': ['Fixed order', 'OS file cache not evicted', 'Concurrent development and verification may consume CPU',
                       'Synthetic repeated inventory differs from task content', 'Diagnostic output cap32 differs from research cap8192'],
        'unchanged_research_controls': 'Same model/digest/template, common context, source conditions, schema, calculator, evaluation and8192output allowance.'}
    runtime.remote.save(ROOT / 'research/v491_runtime_selection_20261019.json', receipt)
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
