"""Freeze this preparation handoff, never the pending research experiment."""
from __future__ import annotations
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from research_progress_log import append, read_verified

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / 'research/v491_runtimeprep_process_20261019.jsonl'
OUT = ROOT / 'research/v491_runtimeprep_handoff_20261019.json'


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8-sig'))


def ref(path):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    return {'path': path.relative_to(ROOT).as_posix(),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'bytes': path.stat().st_size}


def main():
    if OUT.exists():
        raise ValueError('Delivery already saved; preserve it and use a new revision')
    prior = read('research/v491_handoff_20261019.json')
    for item in prior['exact_delivery_files']:
        if ref(item['path'])['sha256'] != item['sha256']:
            raise ValueError('Previous reviewed delivery changed: ' + item['path'])
    validations = [
        'research/v491_runtime_round1_20261019_r2.json',
        'research/v491_runtime_round2_token_review_20261019_r2.json',
        'research/v491_runtimeprep_round3_20261019.json',
        'research/v491_runtime_methods_review_20261019_r2.json',
        'research/artifacts/v491_runtimeprep_20261019/human_pack_round1.json',
        'research/artifacts/v491_runtimeprep_20261019/human_pack_round2.json',
        'research/artifacts/v491_runtimeprep_20261019/human_pack_round3.json',
        'research/artifacts/v491_runtimeprep_20261019/status_visual_review.json',
    ]
    for name in validations:
        if read(name)['status'].upper() != 'PASS':
            raise ValueError('Unresolved validation: ' + name)
    report_name = 'research/v491_runtimeprep_report_20261019.json'
    report = read(report_name)
    if report['pilot_generation_requests'] or report['main_generation_requests']:
        raise ValueError('Unexpected research generation')
    round3 = read(validations[2])
    for item in (round3['reviewed_runtime'], round3['reviewed_report'], round3['reviewed_candidate']):
        if ref(item['path'])['sha256'] != item['sha256']:
            raise ValueError('Final integration target changed')
    diff_check = subprocess.run(['git', 'diff', '--check'], cwd=ROOT, capture_output=True, text=True)
    if diff_check.returncode:
        raise ValueError(diff_check.stdout + diff_check.stderr)
    existing_phases = {row['phase'] for row in read_verified(LEDGER)}
    events = [
        ('cpu_comparison_and_token_checks_completed',
         'All three source-free engineering requests retained. Long prompt13380: CPU2 supervisor876.374s, CPU8 supervisor465.034s. CPU8 selected provisionally; actual institutional output/full F0 feasibility remains untested. Eight schema-included D0 renders fit; no research generation.',
         ['research/v491_runtime_selection_20261019.json', 'research/v491_token_review_20261019_r2.json', report_name]),
        ('runtime_three_verification_rounds_completed',
         'Implementation tests, independent technical recheck and root121-check integration audit passed; independent methods review also passed. Earlier finding and correction snapshots retained. These checks do not substitute for two independent human original-source reviews.',
         validations[:4]),
        ('runtime_preparation_delivery_ready',
         'Human review forms remain blank. Status HTML and review-pack visuals checked; owned11435diagnostic service stopped, existing11434listener preserved. Research generation0, pilot human gate pending, main not frozen. Code, raw evidence archives and append-only process chain retained.',
         [report_name, *validations[4:], 'plan/LIBERA_실행준비현황_v4.9.1_20261019.html']),
    ]
    for phase, detail, paths in events:
        if phase not in existing_phases:
            append(phase, 'completed', detail, [ROOT / p for p in paths], path=LEDGER)
    ledger = read_verified(LEDGER)
    for event in ledger:
        for item in event['reference_files']:
            if ref(item['path'])['sha256'] != item['sha256']:
                raise ValueError('Process reference changed: ' + item['path'])
    raw = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=ROOT)
    paths = sorted(p.decode('utf-8') for p in raw.split(b'\0') if p)
    if any(not p.startswith(('research/', 'plan/', 'data/local_sector_runtime/v491_cpu_preflight_20261019/')) for p in paths):
        raise ValueError('Unexpected unrelated file in preparation delivery')
    python_checked = 0
    for name in paths:
        if name.endswith('.py'):
            ast.parse((ROOT / name).read_text(encoding='utf-8-sig'), filename=name)
            python_checked += 1
    exact_files = [ref(p) for p in paths]
    handoff = {
        'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'preparation_completed_waiting_for_independent_human_review',
        'baseline_git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'prior_handoff': ref('research/v491_handoff_20261019.json'),
        'prior_exact_files_preserved': len(prior['exact_delivery_files']),
        'runtime_verification_rounds': [ref(p) for p in validations[:3]],
        'independent_methods_review': ref(validations[3]),
        'human_pack_and_visual_verifications': [ref(p) for p in validations[4:]],
        'engineering_summary': ref(report_name),
        'reader_status_page': ref('plan/LIBERA_실행준비현황_v4.9.1_20261019.html'),
        'human_forms': [ref('research/v491_human_review_pack_20261019_' + slot + '.html') for slot in ('R1', 'R2')],
        'engineering_generation_requests': 3,
        'pilot_generation_requests': 0,
        'main_generation_requests': 0,
        'human_review_completed': False,
        'full_task_runtime_feasibility_demonstrated': False,
        'main_protocol_frozen': False,
        'remaining_sequence': [
            'Two independent people complete pilot source/common-context forms without seeing model outputs; preserve both forms and reconcile reasons.',
            'Validate completed human gate, start a new owned CPU service, prepare the four-case pilot with the saved CPU8 candidate.',
            'Run first D0/F0 attempts only, retaining failures and actual input-size, memory and latency evidence; assess complete-case availability.',
            'Complete main-source human review and freeze exact evaluation/runtime/order before any main generation.',
        ],
        'process_ledger': ref(LEDGER), 'ledger_events': len(ledger), 'ledger_chain_verified': True,
        'new_python_files_syntax_checked': python_checked,
        'tracked_diff_whitespace_check_passed': True,
        'exact_new_delivery_files': exact_files,
        'new_delivery_file_count_excluding_this_handoff': len(exact_files),
        'new_delivery_bytes_excluding_this_handoff': sum(p['bytes'] for p in exact_files),
        'archive_note': 'Ignored raw evidence is preserved in SHA256-verified CPU and tokenizer ZIPs; no model weights or browser profiles are included.',
        'scientific_scope': 'Same market/task, institution-specific public evidence, early versus late presentation and own-draft revision. Descriptive two-source, one-model cases; no claim about market-wide convergence, profitability or general causal effects.',
    }
    OUT.write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    if any(ref(row['path']) != row for row in exact_files):
        raise ValueError('Delivery changed while writing handoff')
    print(json.dumps({'status': handoff['status'], 'delivery_files': len(exact_files),
                      'bytes': handoff['new_delivery_bytes_excluding_this_handoff'],
                      'ledger_events': len(ledger), 'python_syntax_files': python_checked,
                      'pilot_calls': 0, 'main_calls': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
