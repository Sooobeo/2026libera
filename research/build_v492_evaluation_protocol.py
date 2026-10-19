"""Amend the local evaluation contract before any v4.9.2 generated response."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8-sig'))


def ref(name):
    return {'path': name, 'sha256': hashlib.sha256((ROOT / name).read_bytes()).hexdigest()}


def main():
    target = ROOT / 'research/v492_evaluation_protocol_20261019_r2.json'
    if target.exists():
        raise ValueError('Preserve the first pre-output protocol; use a new revision')
    method_name = 'research/v492_evaluation_methods_review_20261019.json'
    methods = read(method_name)
    original = 'research/v491_evaluation_protocol_20261019.json'
    protocol = copy.deepcopy(read(original))
    protocol.update(protocol_version='4.9.2', status='ready_for_local_pilot_freeze_no_outputs_yet',
        recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        supersedes_evaluation_ref=ref(original), user_direction_ref=ref('research/v492_user_instruction_20261019.json'),
        prior_preoutput_draft_ref=ref('research/v492_evaluation_protocol_20261019.json'),
        methods_basis_ref=ref(method_name), computational_references_ref=ref('research/v492_computational_references_20261019.json'),
        source_review_ref=ref('research/v492_source_review_20261019.json'),
        expected_cases_per_split=5, expected_sector_rows_per_final_split=55,
        source_conditioned_final_rows=44, no_source_control_final_rows=11,
        independent_human_review_completed=False, paper_guaranteed_semantic_validity=False,
        main_execution_allowed=False)
    protocol['design'] = copy.deepcopy(methods['prespecified_design'])
    protocol['design']['count_scope'] = 'Pilot and prospective main each use five cells. Only the pilot is authorized by this freeze; the main stays disabled.'
    protocol['dimensions']['source_fidelity']['C_rule'] = 'Source fidelity not applicable when none was supplied; invented institutional attribution remains an unsupported claim.'
    protocol['dimensions']['evidence_decision_link']['rule'] = 'AI-assisted descriptive evidence-chain coding, not independent human validation. A supported departure may be justified; no compulsory target or hidden-thought inference.'
    protocol['operational_evaluation_layers'] = methods['evaluation_layers']
    protocol['blind_review'] = {
        'before_generation': 'Review all11 source-comparison rows and factual anchors for the evaluated split before any output of that split; locally freeze evaluation, input versions and code. Pilot source selection remains Q2/June; main remains preselected Q3/July.',
        'reviewers': 'User-delegated Codex AI-assisted review; no mandatory two-person gate and no fabricated human forms.',
        'after_generation': methods['ai_review_protocol']['individual_first'],
        'masking': methods['ai_review_protocol']['masking'],
        'AI_review_status': 'Unvalidated AI semantic coding. Same-family assistant agents are not independent humans or independent statistical raters.',
        'disagreement': methods['ai_review_protocol']['disagreement'],
        'no_composite_score': True,
    }
    protocol['ai_review_protocol'] = copy.deepcopy(methods['ai_review_protocol'])
    protocol['ai_review_protocol']['pre_output'] = protocol['blind_review']['before_generation']
    protocol['descriptive_comparisons'] = methods['descriptive_comparisons']
    protocol['computational_references'] = methods['computational_references']
    protocol['denominators'].update(planned_cases=5, planned_final_sector_rows=55,
        planned_source_conditioned_rows=44, planned_no_source_control_rows=11,
        maximum_generation_requests=10, shared_C_count=1)
    protocol['contrast_priority'] = [
        'Institution-specific evidence-to-allocation links and the E/L differences between the two source-conditioned institutions.',
        'Matched-stage common-only C versus each E/L final: availability of institutional evidence, never simply distance-is-better.',
        'Within-institution E versus L: information timing/exposure/history workflow contrast.',
        'Equal-weight, minimum-variance and market-reference distances/risk diagnostics; not institution-specific correctness or strategic-performance rankings.',
    ]
    protocol['interpretation']['no_valid_control'] = 'C comparisons remain unobserved if C or the matched source final is missing/invalid; valid E/L source comparisons can still be described with their own denominators.'
    protocol['interpretation']['same_as_C'] = 'Same allocation as C alone does not establish ignored source meaning; compare exact supported reasoning and source-choice links.'
    protocol['interpretation']['different_from_C'] = 'A changed allocation alone does not establish appropriate use of the institution document; require traceable reasoning and factual support.'
    protocol['not_identified'] += [
        'Human-validated semantic score or inter-rater reliability',
        'Pure semantic information effect separated from prompt length and exposure',
        'Institution-specific optimal numeric portfolio',
    ]
    protocol['researcher_choices_not_paper_constants'] = [
        'One fixed market snapshot, two preselected institutions and one common-only control: resource/scope choice, not a power calculation.',
        'Five cells arise from2sources*2timings+1sharedcontrol; two turns yield at most10calls. These are design counts, not estimated constants.',
        'AI semantic categories and no composite score are declared local operationalizations, not validated borrowed scales.',
        'CPU8/context65536/deadline4500seconds are engineering settings. The75minute ceiling rounds up a scenario extrapolating the observed prefilling/decoding rates to57344input+8192output tokens; six-token decoding measurement is not a reliable runtime guarantee. Numerical tolerances check computation, not investment suitability.',
    ]
    target.write_text(json.dumps(protocol, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'path': target.relative_to(ROOT).as_posix(), 'cases': 5, 'rows': 55,
                      'source_rows': 44, 'C_rows': 11, 'calls_max': 10, 'human_review_claimed': False}))


if __name__ == '__main__':
    main()
