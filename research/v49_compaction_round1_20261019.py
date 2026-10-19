"""Offline independent design-integrity checks; no served model calls."""
import copy
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'research'))
from sector_response_schema import _errors
from compact_sector_prompt import restore_market
from v49_compaction_review_20261019 import restore_index, restore_packet, canonical


def read(p):
    return json.loads((ROOT / p).read_text(encoding='utf-8-sig'))


def ref(p):
    p = Path(p)
    return {'path': p.as_posix(), 'sha256': hashlib.sha256((ROOT / p).read_bytes()).hexdigest()}


class HtmlInventory(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.links = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'a' and 'href' in attrs:
            self.links.append(attrs['href'])

    def handle_data(self, data):
        self.text.append(data)


def main():
    config_path = next((ROOT / 'plan').glob('*v4.9_20261019.json')).relative_to(ROOT)
    config = read(config_path)
    base = Path('data/sector_protocol/v49_design_20261019')
    schema = read(base / 'response_schema.json')
    contract = read(base / 'prompt_contract.json')
    evaluation = read('research/v49_evaluation_protocol_20261019.json')
    compact = read(base / 'public_compact_candidate.json')
    old_market = read('data/sector_protocol/v48_pilot_20261018/market_input.json')
    old_registry = read('data/sector_protocol/v48_pilot_20261018/public_numeric_registry.json')
    checks = []

    def check(name, condition, detail=None):
        checks.append({'name': name, 'pass': bool(condition), 'detail': detail})

    check('budget_has_four_cases_per_split',
          len(config['sources']['pilot']) * len(config['arms']) == config['budget']['cases_per_split'] == 4)
    check('main_and_pilot_have_same_case_counts', len(config['sources']['main']) == len(config['sources']['pilot']) == 2)
    check('complete_split_has_eight_calls', config['budget']['max_calls_per_split'] == 4 * len(config['stages']) == 8)
    check('pilot_main_total_max_sixteen_calls', config['budget']['pilot_and_main_max_core_calls'] == 2 * 8)
    check('no_post_final_calls', config['budget']['post_final_calls'] == 0)
    check('sectors_are_exact_original_eleven', config['sectors'] == old_market['sector_codes'] and len(config['sectors']) == 11)
    check('final_packet_refresh_and_position_shared', all(config['final_controls'][key] for key in (
        'same_final_source_packet_bytes','same_market_input','same_final_instruction_and_schema',
        'same_model_and_sampler','same_calculator_policy','same_final_packet_position')))
    check('generated_history_difference_disclosed', config['final_controls']['same_generated_history'] is False)
    check('same_packet_position_means_block_order_not_absolute_tokens',
          'absolute token positions and history lengths differ' in config['final_controls']['packet_position_meaning'])
    required_validators = config['semantic_validators_required_before_execution']
    check('explicit_unique_sector_validator_gate', any('unique allowed sector codes' in line for line in required_validators))
    check('explicit_L_D0_null_source_validator_gate', any('source_id and source_label null' in line for line in required_validators))
    check('explicit_calculator_adapter_and_request_visibility_gates',
          any('extracted unchanged' in line for line in required_validators)
          and any('exclude all unassigned packets and evaluator artifacts' in line for line in required_validators))
    check('independent_late_drafts_not_shared', 'No shared L draft' in config['draft_policy'])
    check('final_complete_source_refresh_planned', 'same assigned packet freshly supplied' == config['source_exposure']['E']['F0']
          and 'assigned packet first supplied' == config['source_exposure']['L']['F0'])
    check('L_D0_identity_absence_in_design', 'no source identity' in config['source_exposure']['L']['D0']
          and 'source_id=null' in contract['D0_instruction'] and 'source_label=null' in contract['D0_instruction'])
    check('aggregate_never_authorized_for_model_input', config['data']['aggregate_candidate_model_visible'] is False
          and 'never send the aggregate' in config['data']['visibility_rule'])
    check('compact_reference_matches_actual_file', config['data']['compact_candidate'] == ref(base / 'public_compact_candidate.json'))
    check('common_market_roundtrip_exact', canonical(restore_market(compact['common_market'])) == canonical(old_market))
    original_index = restore_index(compact['public_numeric_fact_index'])
    check('all_58_scalar_fact_coordinates_preserved', len(original_index['rows']) == len(old_registry['rows']) == 58)
    for original, projected in zip(old_registry['rows'], original_index['rows']):
        value = old_market
        for key in original['source_json_pointer'].lstrip('/').split('/'):
            key = key.replace('~1','/').replace('~0','~')
            value = value[int(key)] if isinstance(value, list) else value[key]
        expected = [original[key] for key in ('fact_id','sector_code','metric','unit','period','source_json_pointer')]
        check('fact_preserved_' + original['fact_id'],
              canonical(projected) == canonical(expected) and canonical(value) == canonical(original['value']))
    check('both_full_matrices_available', len(original_index['matrix_references']) == 2
          and all(len(compact['common_market'][key]) == 11
                  and all(len(row) == 11 for row in compact['common_market'][key]) for key in ['covariance','correlation']))
    for split, sources in config['sources'].items():
        for source in sources:
            original = read(f'data/sector_documents/packets/{split}/{source}.json')
            check('complete_packet_roundtrip_' + source,
                  canonical(restore_packet(compact['public_source_packets'][source])) == canonical(original))
    check('all_model_calls_zero_and_design_unfrozen', all(config['current_state'][key] == 0
          for key in ['v49_model_calls','v49_pilot_calls','v49_main_calls'])
          and config['current_state']['frozen'] is False and config['current_state']['runner_implemented'] is False)
    check('backend_context_not_falsely_selected', config['model']['selected_backend'] is None
          and config['model']['selected_context_tokens'] is None and config['model']['runtime_validated'] is False)
    check('explicit_finite_case_inference', evaluation['inference'].startswith('Finite descriptive cases;'))
    check('invalid_comparisons_not_imputed', 'No zero distance' in evaluation['denominators']['missing'])
    check('eval_final_denominator_44_not_44_independent_samples',
          evaluation['expected_sector_rows_per_final_split'] == 4 * 11
          and 'dependent components' in config['unit'])

    # Use the existing strict supported-subset validator. The optional external
    # jsonschema library is absent; this does not claim backend grammar support.
    example = {'source_id': None, 'sectors': [
        {'sector_code': code, 'source_label': None,
         'source_reading': 'Synthetic structure test: source unavailable.',
         'source_evidence_ids': [], 'source_stance': 'not_available',
         'weight': 1 / 11, 'decision_reason': 'Synthetic structure test only.',
         'decision_evidence_ids': []} for code in config['sectors']],
        'alternatives': 'Synthetic test only.', 'risk_discussion': 'Synthetic test only.',
        'unresolved': [], 'submitted_constraints': []}
    check('synthetic_L_D0_complete_eleven_passes_structure', not _errors(example, schema))
    for name, value in [('boolean_weight', True), ('nonfinite_weight', float('nan'))]:
        bad = copy.deepcopy(example); bad['sectors'][0]['weight'] = value
        check('reject_' + name, bool(_errors(bad, schema)))
    for n in [10, 12]:
        bad = copy.deepcopy(example)
        bad['sectors'] = bad['sectors'][:n] if n < 11 else bad['sectors'] + [copy.deepcopy(bad['sectors'][0])]
        check('reject_' + str(n) + '_sector_rows', bool(_errors(bad, schema)))
    bad = copy.deepcopy(example); bad['sectors'][0]['sector_code'] = '99'
    check('reject_unknown_sector_code', bool(_errors(bad, schema)))
    bad = copy.deepcopy(example); bad['sectors'][0]['decision_reason'] = ''
    check('reject_empty_decision_reason', bool(_errors(bad, schema)))
    bad = copy.deepcopy(example); bad['hidden_evaluator_answer'] = 'test'
    check('reject_unlisted_response_field', bool(_errors(bad, schema)))
    bad = copy.deepcopy(example); bad['sectors'][1]['sector_code'] = bad['sectors'][0]['sector_code']
    check('schema_limit_duplicate_codes_demonstrated', not _errors(bad, schema),
          '11 rows alone do not enforce all 11 codes once. Separate coverage validation is required.')
    bad = copy.deepcopy(example); bad['source_id'] = 'SYNTHETIC_FORBIDDEN_L_D0_ID'
    check('schema_limit_L_D0_identity_demonstrated', not _errors(bad, schema),
          'Generic shared schema is phase-neutral. Separate L-D0 source visibility/identity validation is required.')
    check('schema_minmax_eleven_applies_to_F0', schema['properties']['sectors']['minItems'] == schema['properties']['sectors']['maxItems'] == 11)

    changed = subprocess.run(['git','diff','HEAD','--name-only','-z'], cwd=ROOT,
                             check=True, capture_output=True).stdout.decode('utf-8').split('\0')
    changed = [p for p in changed if p]
    check('no_preexisting_tracked_file_changed_from_HEAD', not changed, changed)
    manifest = read('data/sector_protocol/v48_pilot_r2_20261018/manifest.json')
    software_checks = []
    for name, expected in manifest['software_hashes'].items():
        actual = ref('research/' + name)
        software_checks.append({**actual, 'expected_sha256': expected})
        check('frozen_v48_software_' + name, actual['sha256'] == expected)
    reviewed = [config_path, base / 'prompt_contract.json', base / 'response_schema.json',
                base / 'public_compact_candidate.json', 'research/build_v49_compact_plan.py',
                'research/v49_evaluation_protocol_20261019.json',
                'research/v49_human_review_template_20261019.json',
                'research/v49_compaction_review_20261019.json']
    html_inventory = []
    pending_links = []
    for folder in ['plan', 'paper']:
        html_path = next((ROOT / folder).glob('*v4.9_20261019.html'))
        relative = html_path.relative_to(ROOT)
        raw = html_path.read_text(encoding='utf-8')
        parser = HtmlInventory(); parser.feed(raw); parser.close()
        plain = ' '.join(parser.text)
        check(folder + '_HTML_has_no_replacement_character', '\ufffd' not in raw)
        check(folder + '_HTML_has_one_open_close_document', raw.lower().count('<html') == 1 and raw.lower().count('</html>') == 1)
        check(folder + '_HTML_unique_section_ids', len(parser.ids) == len(set(parser.ids)))
        check(folder + '_HTML_has_no_execution_result_claim', 'v4.9' in plain and '아직 실행하지 않았다' in plain
              if folder == 'paper' else 'v4.9 모델 호출은 0회' in plain)
        if folder == 'plan':
            check('plan_HTML_has_eight_call_four_cell_budget', '본실험 최대 8회 생성' in plain
                  and all(name in plain for name in ['Fidelity–E','Fidelity–L','UBS–E','UBS–L']))
            check('plan_HTML_has_schema_limit_and_remaining_work', '출력 스키마만으로' in plain
                  and '계산기 연결을 별도로 구현해야' in plain)
            check('plan_HTML_marks_absolute_token_position_difference', '절대 토큰 위치까지 같다는 의미는 아니다' in plain)
            check('plan_HTML_measured_bytes_not_tokens', '25,178바이트' in plain and '20,617바이트' in plain
                  and '18.1%' in plain)
        links = []
        for href in parser.links:
            parsed = urlsplit(href)
            if parsed.scheme in ['http', 'https']:
                links.append({'href': href, 'kind': 'external_reference', 'online_verification_in_this_audit': False})
                continue
            target = (html_path.parent / unquote(parsed.path)).resolve() if parsed.path else html_path.resolve()
            check(folder + '_link_stays_within_workspace_' + href,
                  target == ROOT.resolve() or ROOT.resolve() in target.parents)
            expected_handoff = target == (ROOT / 'research/v49_handoff_20261019.json').resolve()
            if not target.exists() and expected_handoff:
                pending_links.append({'source': relative.as_posix(), 'href': href,
                                      'status': 'root_final_handoff_will_be_created'})
                check(folder + '_expected_final_handoff_link_target', True,
                      'Explicit pending final artifact, not represented as an existing verified target.')
            else:
                check(folder + '_local_link_exists_' + href, target.exists())
            if parsed.fragment:
                target_parser = parser
                if target != html_path.resolve() and target.exists():
                    target_parser = HtmlInventory(); target_parser.feed(target.read_text(encoding='utf-8'))
                check(folder + '_fragment_exists_' + href, unquote(parsed.fragment) in target_parser.ids)
            links.append({'href': href, 'kind': 'local', 'target_exists': target.exists()})
        html_inventory.append({'file': ref(relative), 'section_ids': parser.ids,
                               'link_count': len(parser.links), 'links': links})
        reviewed.append(relative)
    report = {'round': 1, 'status': 'PASS' if all(c['pass'] for c in checks) else 'FAIL',
              'scope': 'Design integrity and offline structural checks only; not runtime or scientific-outcome certification.',
              'online_model_calls': 0, 'reviewed_artifacts': [ref(p) for p in reviewed],
              'checks': checks, 'check_count': len(checks),
              'html_integrity': html_inventory, 'explicit_pending_final_links': pending_links,
              'frozen_software_references': software_checks,
              'required_before_execution': [
                  {'id': 'unique_sector_validation', 'status': 'not_implemented',
                   'action': 'Require every public sector code exactly once independently of JSON schema; retain invalid raw responses.'},
                  {'id': 'L_D0_source_boundary_validation', 'status': 'not_implemented',
                   'action': 'Verify source-free L-D0 request and null source identity/labels, no source citations and not_available stance in output. Record violations without silently correcting.'},
                  {'id': 'new_schema_calculator_adapter', 'status': 'not_implemented',
                   'action': 'Map the new sectors rows into unchanged raw sector_code/weight calculator inputs without any weight transformation; preserve separate source and decision citations.'},
                  {'id': 'request_and_token_feasibility', 'status': 'not_measured',
                   'action': 'Build and validate exact E/L served requests, assigned-only packets, preserved history, real token counts, complete draft-final runtime and output bounds before freeze.'},
                  {'id': 'backend_schema_support', 'status': 'not_measured',
                   'action': 'The local strict validator tested the supported JSON-schema subset; acceptance by the actual backend grammar remains to be checked.'}
              ],
              'interpretation': 'PASS means the reviewable design is internally consistent and preserves inputs. Explicit unfinished execution gates remain. No experimental result or guaranteed allocation observability is asserted.'}
    target = ROOT / 'research/v49_round1_integrity_check_20261019.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'check_count': len(checks),
                      'failed': [c for c in checks if not c['pass']], 'output': str(target)}))


if __name__ == '__main__':
    main()
