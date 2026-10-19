"""Create the actual delegated-AI gate and run the final offline integration audit."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import sector_v492_runtime as runtime
import sector_v492_review_gate as gate_rules
from research_progress_log import append

ROOT = Path(__file__).resolve().parents[1]


def now():
    return datetime.now(timezone.utc).isoformat()


def read(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8-sig'))


def ref(name):
    return {'path': name, 'sha256': hashlib.sha256((ROOT / name).read_bytes()).hexdigest()}


def save(name, value):
    with (ROOT / name).open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')


def main():
    names = {
        'runtime': 'research/v492_runtime_candidate_20261019.json',
        'freeze': 'research/v492_pilot_freeze_20261019.json',
        'gate': 'research/v492_ai_review_gate_20261019.json',
        'audit': 'research/v492_runtime_round3_20261019.json',
    }
    if any((ROOT / name).exists() for name in names.values()):
        raise ValueError('A freeze attempt already exists; preserve it before creating a new revision')
    checks = []
    def check(label, value):
        checks.append({'check': label, 'pass': bool(value)})
        if not value:
            raise ValueError('Pre-output integration failed: ' + label)
    for name, collection in [('research/v491_handoff_20261019.json', 'exact_delivery_files'),
                             ('research/v491_runtimeprep_handoff_20261019.json', 'exact_new_delivery_files')]:
        for item in read(name)[collection]:
            check('previous delivery unchanged: ' + item['path'], ref(item['path'])['sha256'] == item['sha256'])
    reports = ['research/v492_runtime_round1_20261019.json',
               'research/v492_runtime_independent_review_20261019.json',
               'research/v492_final_acceptance_20261019.json',
               'research/v492_final_methods_review_20261019.json',
               'research/v492_computational_reference_review_20261019.json']
    for name in reports:
        record = read(name)
        check('review PASS: ' + name, record['status'].upper() == 'PASS')
        for key in ('artifact_refs', 'source_refs', 'input_refs'):
            for item in record.get(key, []):
                if isinstance(item, dict) and 'path' in item and 'sha256' in item:
                    check('review target preserved: ' + item['path'], ref(item['path'])['sha256'] == item['sha256'])
    old = read('research/v491_runtime_candidate_20261019.json')
    candidate = runtime.candidate_runtime(backend='cpu', num_ctx=65536, num_thread=8,
        tokenizer_config=old['tokenizer_config'], backend_evidence=old['backend_evidence'])
    runtime.validate_runtime(candidate)
    check('CPU8 actual measured candidate with4500s ceiling', candidate['deadline_seconds'] == 4500 and candidate['options']['num_predict'] == 8192 and candidate['main_allowed'] is False)
    loaded, cases = runtime.load_bundle()
    check('five exact independent trajectories', [case['case_id'] for case in cases] == gate_rules.CASE_ORDER)
    check('four source cases plus one null source control', len(cases) == 5 and cases[-1]['source_id'] is None and cases[-1]['assigned_packet'] is None)
    old_manifest = read('data/sector_protocol/v491_design_20261019/prepared/preparation_manifest.json')
    old_paths = {item['case_id'].split('/', 1)[1]: item['path'] for item in old_manifest['prepared_cases'] if item['split'] == 'pilot'}
    old_tokens = {item['case_id'].split('/', 1)[1]: item for item in read('research/v491_token_review_20261019_r2.json')['actual_D0_cases'] if item['case_id'].startswith('pilot/')}
    inherited_counts = []
    for case in cases:
        equivalent = case['case_id'] if case['arm'] != 'C' else 'fidelity_q2_2026__L'
        check('D0 content byte-equivalent to exact-tokenized input: ' + case['case_id'],
              runtime.base.canonical(case['messages']) == runtime.base.canonical(read(old_paths[equivalent])))
        token = old_tokens[equivalent]
        check('D0 fits output reserve: ' + case['case_id'], token['token_count'] + 8192 <= 65536)
        inherited_counts.append({'case_id': case['case_id'], 'equivalent_prior_case': equivalent,
                                 'exact_prompt_tokens': token['token_count'], 'new_render_calls': 0})
        body = runtime.request_body(candidate, case['messages'], loaded['response_schema'])
        check('schema and model controls unchanged: ' + case['case_id'], body['format'] == loaded['response_schema'] and body['options'] == candidate['options'] and body['think'] is False and body['truncate'] is False)
        if case['arm'] in ('L', 'C'):
            text = runtime.base.canonical(case['messages'])
            check('source-free D0 does not name either pilot source: ' + case['case_id'], not any(s in text for s in runtime.PILOT_SOURCES) and 'institution_document' not in text)
    evaluation = read('research/v492_evaluation_protocol_20261019_r2.json')
    check('5/55/44/11 denominators and no fabricated human review',
          evaluation['expected_cases_per_split'] == 5 and evaluation['expected_sector_rows_per_final_split'] == 55
          and evaluation['source_conditioned_final_rows'] == 44 and evaluation['no_source_control_final_rows'] == 11
          and evaluation['independent_human_review_completed'] is False)
    check('common reference values never become model input', all('long_only_minimum_variance' not in runtime.base.canonical(c['messages']) for c in cases))
    save(names['runtime'], candidate)
    refs = {
        'input_protocol_ref': ref('plan/LIBERA_실험설정_v4.9.1_20261019.json'),
        'evaluation_protocol_ref': ref('research/v492_evaluation_protocol_20261019_r2.json'),
        'source_review_ref': ref('research/v492_source_review_20261019.json'),
        'method_review_ref': ref('research/v492_final_acceptance_20261019.json'),
        'prompt_contract_ref': ref('data/sector_protocol/v492_design_20261019/prompt_contract.json'),
        'prepared_manifest_ref': ref('data/sector_protocol/v492_design_20261019/prepared/preparation_manifest.json'),
        'runtime_ref': ref(names['runtime']),
    }
    reviewed_at = now()
    extra_code = {'research/freeze_v492_pilot.py', 'research/start_sector_v492_cpu.ps1', 'research/stop_sector_v492_cpu.ps1',
                  'research/build_v492_computational_references.py', 'research/build_v492_evaluation_protocol.py'}
    freeze = {
        'freeze_version': 'v492_pilot_preoutput_freeze_1', 'protocol_version': '4.9.2',
        'status': 'frozen_for_pilot_only', 'recorded_at_utc': now(), 'purpose': 'pilot_only',
        'user_instruction': read('research/v492_user_instruction_20261019.json'), **refs,
        'code_refs': [ref(path) for path in sorted(gate_rules.REQUIRED_CODE_PATHS | extra_code)],
        'case_order': gate_rules.CASE_ORDER, 'controls': gate_rules.CONTROLS,
        'verification_refs': [ref(name) for name in reports],
        'resource_decision_ref': ref('research/v492_resource_decision_20261019.json'),
        'computational_references_ref': ref('research/v492_computational_references_20261019.json'),
        'local_record_only': True, 'external_preregistration': False,
        'research_generation_requests_before_freeze': 0, 'main_allowed': False,
    }
    save(names['freeze'], freeze)
    gate = {
        'receipt_version': 'v492_ai_preoutput_gate_1', 'status': 'approved_for_pilot_before_generation',
        'review_mode': 'AI_delegated_by_user', 'recorded_at_utc': now(),
        'user_instruction': freeze['user_instruction'], **refs, 'freeze_ref': ref(names['freeze']),
        'review': {'reviewer': 'Codex', 'completed_at_utc': reviewed_at, 'source_meaning_checked': True,
                   'topic_alignment_checked': True, 'limitations': [
                       'AI-assisted source/semantic review has not been validated by independent human raters.',
                       'Common model/context and a single shared C define descriptive cases, not population effects.',
                       'No institution-specific optimal portfolio or future performance benchmark is observed.',
                       'Engineering timing is uncertain; original failures and unattempted cells must remain visible.',
                   ]},
        'pilot_cases': gate_rules.CASE_ORDER, 'main_allowed': False,
    }
    save(names['gate'], gate)
    gate_result = gate_rules.validate_review_gate(names['gate'], runtime=candidate)
    check('actual completed AI gate validates before any output', gate_result['independent_human_review_completed'] is False)
    audit = {'round': 3, 'protocol_version': '4.9.2', 'status': 'PASS', 'recorded_at_utc': now(),
             'scope': 'Actual artifact, freeze, old-delivery, source-boundary and token-equivalence integration; not human validation or model completion.',
             'checks': checks, 'check_count': len(checks), 'model_calls': 0,
             'HTTP_calls': 0, 'pilot_calls': 0, 'main_calls': 0,
             'exact_D0_capacity_by_identity': inherited_counts,
             'F0_capacity': 'Unknown until actual own D0; native count and reserve are enforced by each worker.',
             'runtime_ref': ref(names['runtime']), 'freeze_ref': ref(names['freeze']), 'gate_ref': ref(names['gate']),
             'preceding_rounds': [ref(reports[0]), ref(reports[1])]}
    save(names['audit'], audit)
    append('pilot_protocol_frozen_after_three_checks', 'completed',
        'Five matched-stage E/L/C pilot cases frozen before output. Two implementation reviews plus final artifact integration passed. AI source review replaces rejected human gate honestly; no main or research output yet. CPU8/65536/8192 with4500second engineering ceiling.',
        [ROOT / names[k] for k in ('runtime', 'freeze', 'gate', 'audit')], path=ROOT / 'research/v492_process_20261019.jsonl')
    print(json.dumps({'status': 'PASS', 'checks': len(checks), 'case_count': len(cases), 'max_calls': 10,
                      'gate': names['gate'], 'pilot_calls': 0, 'main_calls': 0}))


if __name__ == '__main__':
    main()
