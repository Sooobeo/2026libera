"""Independent AI methods acceptance of the fixed v4.9.2 r2 protocol.

This is a local pre-output methods/technical check, not human validation,
external preregistration, live-model feasibility, or permission to run main.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research/v492_final_methods_review_20261019.json'


def load(path):
    return json.loads((ROOT / path).read_text(encoding='utf8'))


def ref(path):
    p = ROOT / path
    return {'path': p.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}


def main():
    if OUT.exists():
        raise SystemExit('Preserve the completed review; use a new revision for later changes.')
    protocol = 'research/v492_evaluation_protocol_20261019_r2.json'
    p = load(protocol)
    source = load('research/v492_source_review_20261019.json')
    math = load('research/v492_computational_reference_review_20261019.json')
    resource_path = 'research/v492_resource_decision_20261019.json'
    resource = load(resource_path)
    prep_path = 'data/sector_protocol/v492_design_20261019/prepared/preparation_manifest.json'
    prep = load(prep_path)
    checks = []

    def check(name, ok, reason):
        checks.append({'check': name, 'pass': bool(ok), 'reason': reason})

    for field in ['supersedes_evaluation_ref', 'user_direction_ref', 'prior_preoutput_draft_ref', 'methods_basis_ref', 'computational_references_ref', 'source_review_ref', 'common_task']:
        check(field + ': exact SHA binding', p[field] == ref(p[field]['path']), 'Read referenced bytes and recomputed SHA256.')
    check('five cases, 55 planned final rows, 44 source and 11 control rows',
          p['expected_cases_per_split'] == p['denominators']['planned_cases'] == 5 and p['expected_sector_rows_per_final_split'] == p['denominators']['planned_final_sector_rows'] == 55 and p['source_conditioned_final_rows'] == 44 and p['no_source_control_final_rows'] == 11,
          'Counts follow 2 sources × 2 timings + 1 shared C, with eleven sector rows per final. Rows are not independent samples.')
    check('maximum ten generations, one shared C and main disabled', p['denominators']['maximum_generation_requests'] == 10 and p['denominators']['shared_C_count'] == 1 and p['main_execution_allowed'] is False,
          'D0 and F0 are stages of one trajectory. The protocol does not authorize main.')
    check('C fidelity not applicable but unsupported attribution remains measurable', 'Not applicable' in p['design']['C']['source_fidelity_scoring'] and 'Unsupported' in p['design']['C']['source_fidelity_scoring'],
          'Failure to mention an institution never supplied is not a source-fidelity error.')
    check('single AI interpretation is honestly disclosed', p['independent_human_review_completed'] is False and p['paper_guaranteed_semantic_validity'] is False and 'Unvalidated AI' in p['blind_review']['AI_review_status'],
          'The user removed the local human prerequisite. Neither synthetic checks nor repeated AI review create human raters.')
    check('all source rows and cross-source comparisons complete before outputs', len(source['pilot_source_reviews']) == 22 and len(source['pilot_source_comparisons']) == 11 and source['reviewed_before_research_outputs'] is True and source['research_generation_calls_observed'] == 0,
          'Original PDFs, packet meanings and all comparisons were reviewed without observing v492 research outputs.')
    check('source semantics have no invented target allocation', all(x['required_target_weight'] is None for x in source['pilot_source_reviews']) and source['rubric_before_outputs']['source_target_weights'] is None,
          'Overweight and Attractive are not mapped to mandatory weights. The broad-market versus S&P universe difference remains explicit.')
    check('all seven shared macro anchors preserve dated facts', len(source['common_context_review']['factual_anchors']) == 7 and all(x['publication_date'] < '2026-07-17' for x in source['common_context_review']['factual_anchors']),
          'Observation periods, release dates, units and vintages are distinct. Older reports are not assumed to know later data.')
    check('AI review categories are descriptive without composite or semantic threshold', p['no_composite_score'] is True and p['operational_evaluation_layers'][-1]['no_semantic_pass_threshold'] is True,
          'Code tests establish arithmetic execution, not semantic validity. Missing/unresolved claims and coverage remain visible.')
    check('post-output amendments remain development', 'new version before main' in p['ai_review_protocol']['post_output_changes'],
          'No retroactive assertion that a changed rubric was prespecified.')
    check('distance formula and raw-sum domain stay separate from institutional correctness', p['descriptive_comparisons']['distance'] == 'd(w,v) = 0.5 * sum_i abs(w_i - v_i)' and 'do not renormalize' in p['descriptive_comparisons']['eligible_vectors'],
          'The borrowed distance is descriptive. Tolerated floating-point residuals do not imply exact probability-distance identities.')
    check('failed outputs and absent C never become zero distance', 'null plus reason' in p['descriptive_comparisons']['nulls'] and 'No retries' in p['outcome_preservation'] and 'no_valid_control' in p['interpretation'],
          'Reported denominators include unattempted and invalid outcomes. A technical failure does not show ignored institutional judgment.')
    check('C and computational references retain different roles', 'separate from the strategic AI control C' in p['computational_references']['role'] and math['status'] == 'PASS',
          'The saved 1/N and constrained GMV passed independent KKT/input checks; they cannot read macro prose or identify an institution optimum.')
    check('residual confounding and finite descriptive inference disclosed', 'prompt length' in p['design']['C']['remaining_confounding'] and 'no p-values' in p['inference'] and 'No repeated-run stability' in ' '.join(p['descriptive_comparisons']['no_inference']),
          'One common C, one model and one market scenario do not identify market-wide convergence, pure anchoring or population effects.')

    expected = ['fidelity_q2_2026__E', 'fidelity_q2_2026__L', 'ubs_june_2026__E', 'ubs_june_2026__L', 'common_market_only__C']
    check('offline preparation covers exactly five pilot cells without generation', [x['case_id'] for x in prep['prepared_cases']] == expected and prep['model_calls'] == 0 and prep['main_model_calls'] == 0,
          'Preparation is input construction and is not an experimental observation.')
    messages, payloads = {}, {}
    for case in prep['prepared_cases']:
        check(case['case_id'] + ': input file hash', ref(case['path'])['sha256'] == case['sha256'], 'The actual prepared message bytes match the offline manifest.')
        messages[case['case_id']] = load(case['path'])
        payloads[case['case_id']] = json.loads(messages[case['case_id']][1]['content'])
    check('C and both L drafts share identical supplied messages', messages[expected[1]] == messages[expected[3]] == messages[expected[4]],
          'They will be generated separately; equal input does not make their outputs the same observation.')
    core = ['common_market', 'common_context', 'public_numeric_fact_index', 'response_schema']
    check('all five D0 common payloads and schemas are identical', all(all(payloads[c][k] == payloads[expected[0]][k] for k in core) for c in expected),
          'Only the E drafts add their assigned institution packet.')
    check('C and L D0 have no institution packet or source IDs', all('institution_packet' not in payloads[c] and 'fidelity_q2_2026' not in messages[c][1]['content'] and 'ubs_june_2026' not in messages[c][1]['content'] for c in [expected[1], expected[3], expected[4]]),
          'The retained system describes conditional source handling but does not reveal an actual issuer.')

    probe = load(resource['observed_metrics_ref']['path'])['metrics']
    estimate = 57344 / probe['prompt_eval_tokens_per_second'] + 8192 / probe['eval_tokens_per_second'] + probe['load_duration_seconds']
    check('resource decision binds the actual source-neutral probe', resource['observed_metrics_ref'] == ref(resource['observed_metrics_ref']['path']) and resource['observed_output_tokens'] == probe['eval_count'] == 6,
          'The rate came from six generated tokens and is a coarse engineering scenario, not a full-task result.')
    check('resource ceiling math and disclosed allowance agree', resource['new_stage_ceiling_seconds'] == 4500 and resource['context'] == 65536 and resource['reserved_output_tokens'] == 8192 and resource['maximum_admissible_prompt_tokens'] == 57344 and abs(resource['scenario_seconds'] - estimate) < 1e-9 and resource['maximum_stage_ceiling_total_hours'] == 12.5,
          '4227.855 seconds = about 70.46 minutes; chosen 75-minute ceiling is engineering headroom, not a paper-derived condition or completion guarantee.')
    check('resource revision occurs before observed outputs without shrinking output allowance', resource['research_generation_requests_before_decision'] == 0 and resource['model_or_research_output_allowance_changed'] is False and 'deadline4500seconds' in ' '.join(p['researcher_choices_not_paper_constants']),
          'The evaluation r2 explicitly labels CPU/context/deadline as operational settings rather than measured scientific parameters.')

    preservation = []
    for handoff, field in [('research/v491_handoff_20261019.json', 'exact_delivery_files'), ('research/v491_runtimeprep_handoff_20261019.json', 'exact_new_delivery_files')]:
        entries = load(handoff)[field]
        mismatches = [x['path'] for x in entries if ref(x['path'])['sha256'] != x['sha256']]
        preservation.append({'handoff': ref(handoff), 'checked_files': len(entries), 'mismatches': mismatches})
        check(handoff + ': immutable historical files', not mismatches, 'Version changes are additions; old human forms and prior artifacts remain untouched.')
    paths = [protocol, 'research/v492_source_review_20261019.json', 'research/v492_computational_reference_review_20261019.json', 'research/v492_computational_references_20261019.json', 'research/v492_evaluation_methods_review_20261019.json', resource_path, prep_path, 'data/sector_protocol/v492_design_20261019/prompt_contract.json', 'research/v492_contract_verification_20261019.json']
    result = {'protocol_version': '4.9.2', 'status': 'PASS' if all(x['pass'] for x in checks) else 'FAIL',
              'completed_at_utc': datetime.now(timezone.utc).isoformat(),
              'review_mode': 'AI_technical_and_methods_check',
              'reviewer': 'Codex /root/v491_review_pack; separate task from protocol builder, not an independent human',
              'independent_human_review_completed': False,
              'scope': 'Fixed r2 evaluation/source/math/prepared-input/resource consistency. This does not establish live native-run feasibility, semantic scorer validity, or permission to run main.',
              'input_refs': [ref(x) for x in paths], 'checks': checks,
              'original_artifacts_preserved': preservation,
              'topic_acceptance': 'The narrowed empirical question remains the preservation of public institutional evidence in visible reasons and actual sector choices under a shared AI workflow. The added common-only C distinguishes the availability of institutional material; E/L examines provision schedule with history/exposure confounding. Numeric references give context rather than institution gold.',
              'source_review_limit': 'The same AI task authored the source review. This acceptance confirms its completeness and alignment, not a second independent semantic rater.',
              'literature_verification_scope': 'Reuses separately documented primary-paper methods review and the fresh PortBench formula confirmation recorded in the computation audit. No claim that all background literature was newly reread here.',
              'reader_documents': 'Separate editorial review reports initial stale v491 header/navigation and E/L-only wording. Reader-document repair is not evidence of new research outputs and is tracked separately.',
              'findings_requiring_protocol_revision': [], 'main_execution_allowed': False,
              'model_generation_calls_by_this_check': 0,
              'limitations': ['No independent human semantic validation.', 'No observed v492 research output was used to select this rubric or comparisons.', 'Source, date, universe and rating-scale mismatches remain disclosed.', 'Prior CPU throughput is not a promise of F0 completion.', 'Three checks are quality-control layers, not three independent measurements.']}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'path': OUT.relative_to(ROOT).as_posix(), 'status': result['status'], 'checks': len(checks), 'sha256': ref(OUT.relative_to(ROOT).as_posix())['sha256'], 'failed': [x['check'] for x in checks if not x['pass']]}, indent=2))
    if result['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
