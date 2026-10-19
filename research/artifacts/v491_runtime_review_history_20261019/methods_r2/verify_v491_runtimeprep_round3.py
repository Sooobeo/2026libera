"""Final integration audit of saved evidence; no inference or human answers."""
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from unittest.mock import patch

import sector_v491_runtime as runtime
from sector_v491_human_gate import FORM_REFS, validate_human_gate
from restore_research_artifacts import restore

ROOT = Path(__file__).resolve().parents[1]
checks = []


def load(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8-sig'))


def check(label, condition):
    checks.append({'check': label, 'pass': bool(condition)})


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def ref(path):
    return {'path': path, 'sha256': sha(path)}


def main():
    for row in load('research/v491_handoff_20261019.json')['exact_delivery_files']:
        check('prior preserved: ' + row['path'], sha(row['path']) == row['sha256'])
    for report_name in ('research/v491_runtime_round1_20261019.json',
                        'research/v491_runtime_round2_token_review_20261019.json'):
        report = load(report_name)
        check(report_name + ' PASS', report['status'] == 'PASS')
        for row in report.get('implementation_refs', []):
            check('review-bound implementation: ' + row['path'], sha(row['path']) == row['sha256'])
    candidate = load('research/v491_runtime_candidate_20261019.json')
    runtime.validate_runtime(candidate)
    check('actual diagnostic-bound runtime validates', True)
    check('main and freeze remain disabled', candidate['main_allowed'] is False and candidate['frozen'] is False)
    loaded, cases = runtime.load_bundle()
    check('exact four pilot cases', len(cases) == 4 and tuple(c['case_id'] for c in cases) == runtime.CASES)
    check('pilot sources only', {c['source_id'] for c in cases} == set(runtime.PILOT_SOURCES))
    for row in FORM_REFS:
        form = load(row['path'])
        check('human form hash: ' + row['path'], sha(row['path']) == row['sha256'])
        check('human answers all blank: ' + row['path'], all(v is None for v in form['answers'].values()))
    forbidden_calls = []
    def no_http(*args, **kwargs):
        forbidden_calls.append(str(args[:2]))
        raise AssertionError('No HTTP is allowed in the final offline gate audit')
    target = ROOT / 'tmp/v491_blank_gate_should_never_create'
    if target.exists():
        raise ValueError('Expected absent gate-test destination')
    gate_path = 'research/v491_human_review_pack_20261019_gate_blank.json'
    with patch.object(runtime.remote, 'api_json', side_effect=no_http):
        try:
            runtime.prepare_pilot(ROOT / 'research/v491_runtime_candidate_20261019.json', target,
                'http://127.0.0.1:11435', ROOT / 'data/local_sector_runtime/v491_cpu_preflight_20261019/server.stderr.log', gate_path)
        except ValueError as exc:
            check('actual blank gate blocks prepare', 'completed human receipt' in str(exc))
        else:
            check('actual blank gate blocks prepare', False)
    check('no HTTP and no misleading pilot directory created', not forbidden_calls and not target.exists())
    token = load('research/v491_token_review_20261019_r2.json')
    check('all8 actual schema-included rendered D0 fit', len(token['actual_D0_cases']) == 8 and all(c['fits_with_output_reserve'] for c in token['actual_D0_cases']))
    report = load('research/v491_runtimeprep_report_20261019.json')
    check('research generation counts remain zero', report['pilot_generation_requests'] == report['main_generation_requests'] == 0)
    check('human review and freeze not fabricated', report['independent_human_review_completed'] is False and report['research_frozen'] is False)
    check('exactly3 separately declared engineering attempts', report['engineering_generation_requests'] == 3)
    source_ids = [x['source_id'] for x in cases] + ['fidelity_q3_2026', 'ubs_july_2026']
    for row in report['engineering_probes']:
        base = 'data/local_sector_runtime/v491_cpu_preflight_20261019/' + row['probe_id']
        spec = load(base + '/spec.json')
        request = load(base + '/http_0001_latency_probe/request.json')
        prompt = json.dumps(spec['body']['messages'])
        check('actual diagnostic HTTP payload equals declaration: ' + row['probe_id'], request['body'] == spec['body'])
        check('no institutional content in diagnostic: ' + row['probe_id'], not any(s in prompt for s in source_ids) and not re.search(r'\b(?:fidelity|ubs)\b', prompt, re.I) and 'synthetic' in prompt.lower())
        check('CPU/ctx diagnostic controls: ' + row['probe_id'], spec['body']['options']['num_gpu'] == 0 and spec['body']['options']['num_ctx'] == 65536)
        check('awake released and residency empty: ' + row['probe_id'], row['awake_release'] == 'released' and row['cleanup'] == 'no_resident_models_observed')
        if row['worker_status'] == 'completed' and row['prompt_tokens_exact_preflight'] is not None:
            check('native versus actual provider count: ' + row['probe_id'], row['prompt_tokens_exact_preflight'] == row['metrics'].get('prompt_eval_count'))
    manifest = ROOT / report['archive_manifest']['path']
    verified = restore(manifest, ROOT)
    check('every CPU evidence archive member verified', verified['verified_files'] > 0)
    with __import__('zipfile').ZipFile(ROOT / token['evidence_archive']['path']) as bundle:
        check('token archive and every member verified', sha(token['evidence_archive']['path']) == token['evidence_archive']['sha256'] and all(hashlib.sha256(bundle.read(r['path'])).hexdigest() == r['sha256'] for r in token['evidence_files']))
    checks_out = {'round': 3, 'status': 'PASS' if all(r['pass'] for r in checks) else 'FAIL',
        'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Root integration/evidence/research-gate audit; not independent human semantic review.',
        'model_calls': 0, 'checks': checks, 'check_count': len(checks),
        'preceding_rounds': [ref('research/v491_runtime_round1_20261019.json'), ref('research/v491_runtime_round2_token_review_20261019.json')],
        'reviewed_runtime': ref('research/sector_v491_runtime.py'),
        'reviewed_report': ref('research/v491_runtimeprep_report_20261019.json'),
        'reviewed_candidate': ref('research/v491_runtime_candidate_20261019.json')}
    out = ROOT / 'research/v491_runtimeprep_round3_20261019.json'
    out.write_text(json.dumps(checks_out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'status': checks_out['status'], 'checks': len(checks), 'failed': [r for r in checks if not r['pass']]}))
    if checks_out['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
