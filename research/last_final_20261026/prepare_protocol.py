"""Prospectively bind the sole unattempted control final to reviewed evidence."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'research'))
from last_final_20261026 import runtime_adapter as a

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--finalizer-review', type=Path, required=True)
    args = parser.parse_args()
    prior = ROOT / 'research/remaining_20261026'
    frozen, old_protocol = read(prior / 'freeze.json'), read(prior / 'protocol_and_review.json')
    binding, design = read(HERE / 'external_draft_binding.json'), read(HERE / 'resumption_design.json')
    refs = {k: frozen[k] for k in a.BOUND if k in frozen and k != 'protocol_ref'}
    for key in ('prior_remaining_gate_ref', 'prior_remaining_terminal_ref', 'prior_remaining_summary_ref',
                'prior_remaining_declaration_ref', 'prior_remaining_cancel_ref', 'prior_pause_checkpoint_ref'):
        refs[key] = design[key]
    refs.update(runtime_ref=a.artifact_ref(HERE / 'runtime_candidate.json'),
                resumption_design_ref=a.artifact_ref(HERE / 'resumption_design.json'),
                last_finalizer_review_ref=a.artifact_ref(args.finalizer_review))
    value = {
        'version': 'last_final_operational_amendment_1',
        'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'approved_design_for_prospective_last_final_freeze',
        'purpose': 'pilot_last_final',
        'case_order': ['common_market_only__C'], 'stage_order': ['common_market_only__C__F0'],
        'max_generation_requests': 1, 'historical_generation_requests': 10,
        'campaign_max_generation_requests': 11, 'automatic_retries': 0, 'post_final_calls': 0,
        'main_model_calls': 0, 'main_allowed': False, 'old_outputs_observed': True,
        'explicit_retry_slots': [], 'historical_explicit_retry_slots': ['fidelity_q2_2026__L__D0'],
        'analysis_role': 'primary_exploratory', 'excluded_new_main_execution': True,
        'historical_first_attempt_results_unchanged': True,
        'raw_diagnostics_required': True, 'primary_final_allocation_endpoint': 'F0_derived_integer_allocation',
        'power_policy': frozen['power_policy'], **refs,
        'exact_math_policy_ref': frozen['finalizer_acceptance_ref'],
        'external_draft_refs': binding['external_draft_refs'],
        'external_draft_evidence_refs': binding['external_draft_evidence_refs'],
        'research_question': old_protocol['research_question'],
        'data_timing': old_protocol['data_timing'], 'endpoint_contract': old_protocol['endpoint_contract'],
        'claims_and_limits': old_protocol['claims_and_limits'],
        'unchanged_instrument': {
            k: v for k, v in old_protocol['unchanged_instrument'].items()
            if k not in {'allowed_new_code_scope', 'dynamic_F0_rule'}
        },
        'operational_runtime_exception': {
            'allowed_runtime_value_change': 'backend_evidence[0] only for the new verified owned CPU service; all other typed values unchanged',
            'new_code_scope': 'One-final orchestration/provenance/gate and offline audit adapters; original generation functions and scientific contract unchanged',
            'awake_expiry_seconds': 8100, 'permanent_power_settings_changed': False,
        },
        'user_authorization': {'exact_user_instruction': '마저 다 끝내봐',
                               'scope': 'Resume only the saved last control final, then full reporting, archive and local commit.'},
        'chronology_and_disclosure': {
            'previous_stop': '2026-10-26T05:13:33.571533+00:00',
            'reason': 'Explicit user pause during C D0 external semantic review; no C F0 generation was attempted.',
            'historical_requests': {'original': 3, 'continuation': 2, 'completion': 1, 'remaining': 4},
            'review_completed_after_terminal': ['C D0 semantic review', 'C D0 root review'],
            'old_ACK_published': False, 'old_CANCEL_or_terminal_changed': False,
            'final_construction': 'New provenance file is rebuilt with the unchanged contract from exact saved own D0; all4messages checked before generation.',
            'study_role_and_math_amendment': 'Original five cases are primary exploratory evidence; derived100% endpoint and role amended after early outputs. No new Q3/July main is run.',
        },
        'review_requirements': {
            'stage_review_axes': ['errors', 'consistency', 'paper_topic'],
            'full_current_semantic_review_before_terminal_ack': True,
            'semantic_success_required': False, 'raw_errors_retained': True,
            'review_timeout_seconds': 1800, 'no_retry_or_repair_after_F0': True,
        },
    }
    a.scope(value)
    a.validated_external_draft(value)
    a.verify_nested_refs(value)
    output = HERE / 'protocol_and_review.json'
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': 'prospective_protocol_prepared', 'protocol_ref': a.artifact_ref(output), 'model_calls': 0}))

if __name__ == '__main__':
    main()
