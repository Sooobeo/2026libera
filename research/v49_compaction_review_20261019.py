"""Offline lossless representation audit; never imports evaluator or model APIs.

Only new v4.9 candidate files are written. This is not an executable experiment
or a guarantee that a shorter representation changes model behaviour neutrally.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/sector_protocol/v49_design_20261019'
VERSION = 'v49_lossless_table_candidate_20261019'


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8-sig'))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)


def size(value):
    return len(canonical(value).encode('utf-8'))


def ref(path):
    p = ROOT / path
    return {'path': path, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}


def table(rows):
    """Factor only exactly equal typed JSON values shared by every row."""
    if not rows:
        return {'shared': {}, 'columns': [], 'rows': []}
    keys = list(rows[0])
    if any(set(row) != set(keys) for row in rows):
        raise ValueError('Heterogeneous row keys')
    shared = {key: copy.deepcopy(rows[0][key]) for key in keys
              if all(canonical(row[key]) == canonical(rows[0][key]) for row in rows)}
    columns = [key for key in keys if key not in shared]
    return {'shared': shared, 'columns': columns,
            'rows': [[copy.deepcopy(row[key]) for key in columns] for row in rows]}


def untab(value):
    columns, shared = value['columns'], value['shared']
    if len(set(columns)) != len(columns) or set(columns) & set(shared):
        raise ValueError('Invalid table column structure')
    result = []
    for row in value['rows']:
        if len(row) != len(columns):
            raise ValueError('Invalid table row length')
        result.append({**copy.deepcopy(shared),
                       **dict(zip(columns, copy.deepcopy(row)))})
    return result


def compact_index(index):
    result = copy.deepcopy(index)
    columns = result.pop('columns')
    source_rows = result.pop('rows')
    groups = {}
    for position, raw in enumerate(source_rows):
        row = dict(zip(columns, raw))
        row['_original_position'] = position
        key = canonical([row['metric'], row['unit'], row['period']])
        groups.setdefault(key, []).append(row)
    result['fact_tables'] = [table(rows) for rows in groups.values()]
    result['original_columns'] = columns
    result['matrix_reference_table'] = table(result.pop('matrix_references'))
    result['representation'] = VERSION
    return result


def restore_index(index):
    result = copy.deepcopy(index)
    result.pop('representation')
    columns = result.pop('original_columns')
    rows = [row for group in result.pop('fact_tables') for row in untab(group)]
    rows.sort(key=lambda row: row['_original_position'])
    result['columns'] = columns
    result['rows'] = [[row[key] for key in columns] for row in rows]
    result['matrix_references'] = untab(result.pop('matrix_reference_table'))
    return result


def compact_packet(packet):
    result = copy.deepcopy(packet)
    result['evidence_table'] = table(result.pop('evidence_passages'))
    result['sector_table'] = table(result.pop('sectors'))
    result['representation'] = VERSION
    return result


def restore_packet(packet):
    result = copy.deepcopy(packet)
    result.pop('representation')
    result['evidence_passages'] = untab(result.pop('evidence_table'))
    result['sectors'] = untab(result.pop('sector_table'))
    return result


def compact_feedback(feedback):
    result = copy.deepcopy(feedback)
    groups = {}
    for position, original in enumerate(result.pop('facts')):
        row = copy.deepcopy(original)
        if '_original_position' in row:
            raise ValueError('Reserved position key')
        row['_original_position'] = position
        groups.setdefault(canonical(sorted(row)), []).append(row)
    result['fact_tables'] = [table(rows) for rows in groups.values()]
    result['representation'] = VERSION
    return result


def restore_feedback(feedback):
    result = copy.deepcopy(feedback)
    result.pop('representation')
    rows = [row for group in result.pop('fact_tables') for row in untab(group)]
    rows.sort(key=lambda row: row['_original_position'])
    for row in rows:
        row.pop('_original_position')
    result['facts'] = rows
    return result


def delta(before, after):
    b, a = size(before), size(after)
    return {'original_canonical_utf8_bytes': b, 'candidate_canonical_utf8_bytes': a,
            'bytes_saved': b-a, 'reduction_percent': round(100*(b-a)/b, 3)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    runtime_root = 'data/local_sector_runtime/pilot_v48_guarded_20261019/'
    request_path = runtime_root + 'fidelity_q2_2026__R1/C1/authoritative_body.json'
    request = read(request_path)
    first = json.loads(request['messages'][1]['content'])
    compact = copy.deepcopy(first)
    compact['public_numeric_fact_index'] = compact_index(first['public_numeric_fact_index'])
    compact['institution_document'] = compact_packet(first['institution_document'])
    restored = copy.deepcopy(compact)
    restored['public_numeric_fact_index'] = restore_index(compact['public_numeric_fact_index'])
    restored['institution_document'] = restore_packet(compact['institution_document'])
    checks = {'complete_first_payload_exact_typed_json_roundtrip': canonical(restored) == canonical(first)}
    packet_paths = [f'data/sector_documents/packets/{split}/{name}.json'
                    for split, names in [('pilot', ['fidelity_q2_2026','ubs_june_2026']),
                                         ('main', ['fidelity_q3_2026','ubs_july_2026'])]
                    for name in names]
    packets = {}
    packet_sizes = {}
    for path in packet_paths:
        packet = read(path)
        candidate = compact_packet(packet)
        packets[packet['source_id']] = candidate
        checks[packet['source_id'] + '_all_metadata_passages_dates_ratings_preserved'] = (
            canonical(restore_packet(candidate)) == canonical(packet))
        packet_sizes[packet['source_id']] = delta(packet, candidate)
    feedback_sizes = []
    feedback_examples = {}
    message_inventory = []
    for position, message in enumerate(request['messages']):
        message_inventory.append({'position': position, 'role': message['role'],
                                  'content_utf8_bytes': len(message['content'].encode('utf-8'))})
        if message['role'] != 'user':
            continue
        content = json.loads(message['content'])
        if 'calculator_feedback' not in content:
            continue
        feedback = content['calculator_feedback']
        candidate = compact_feedback(feedback)
        endpoint = feedback['endpoint_id']
        checks[endpoint + '_all_calculator_values_lineage_preserved'] = (
            canonical(restore_feedback(candidate)) == canonical(feedback))
        feedback_sizes.append({'endpoint': endpoint, **delta(feedback, candidate)})
        feedback_examples[endpoint] = candidate
    candidate_path = 'data/sector_protocol/v49_design_20261019/public_compact_candidate.json'
    candidate = {'status': 'offline_candidate_not_frozen_not_sent',
                 'representation': VERSION, 'online_model_calls': 0,
                 'common_market': first['common_market'],
                 'public_numeric_fact_index': compact['public_numeric_fact_index'],
                 'public_source_packets': packets,
                 'meaning': 'Tables reconstruct every original field value; no rationale, weight, evaluator label or new fact is supplied.'}
    (ROOT / candidate_path).write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    report = {
        'status': 'PASS' if all(checks.values()) else 'FAIL',
        'artifact_type': 'offline_compaction_design_review', 'version': VERSION,
        'online_model_calls': 0, 'runtime_files_modified': False,
        'method': 'Exact typed-JSON equality verified after deterministic table factoring and restoration; no rounding, passage rewriting, label translation or selected-sector omission.',
        'source_references': [ref(request_path)] + [ref(p) for p in packet_paths] + [ref('research/compact_sector_prompt.py'), ref('research/sector_v48_contract.py'), ref('research/run_sector_v48.py')],
        'candidate': ref(candidate_path), 'checks': checks,
        'measurements': {
            'measure': 'Canonical UTF-8 bytes, not tokens, KV-cache memory, latency, or actual v4.9 model prompts.',
            'numeric_index': delta(first['public_numeric_fact_index'], compact['public_numeric_fact_index']),
            'source_packets': packet_sizes,
            'r1_stage1_user_payload_same_schema_same_task': delta(first, compact),
            'calculator_feedback': feedback_sizes,
            'observed_r1_C1_message_inventory': message_inventory,
            'v49_true_prompt_tokens': None, 'v49_measured_runtime': None,
            'token_estimate_performed': False,
        },
        'findings': [
            'The existing v4.8 runner already removed the exact duplicate sample covariance matrix and baseline array. These are not new v4.9 savings.',
            'The 58 public scalar-fact rows repeat metric, unit and period; grouping equal metadata is reversible while every fact ID and source JSON pointer remains visible.',
            'Public packets repeat source_id and representation for every passage. Factoring these does not shorten or paraphrase passage text.',
            'Calculator facts repeat full candidate and market hashes, candidate identity and source-scope metadata. Factoring identical row fields removes repetition without changing calculator numbers or evidence IDs.',
            'Full response schemas repeat in each stage task; previous responses and calculator messages accumulate. Removing intermediate stages changes the workflow and must be registered as a new design, not described as byte-equivalent v4.8.',
            'There is no automatic runtime improvement guarantee: a shorter encoding can change model parsing difficulty, and the observed Vulkan device loss has no proven cause.'
        ],
        'two_stage_execution_specification': {
            'comparison': 'Early document at draft E versus late document at final review L. Final review in both arms has identical public market values and the assigned document.',
            'draft': 'Both arms submit all 11 raw weights plus evidence-linked reasons, alternatives, risks and unknowns. E also interprets the assigned document; L must have source_id null and no guessed institutional interpretation.',
            'between_stages': 'Apply the same pure arithmetic calculator to the raw draft in both arms. Supply only actual draft facts, no suggested weights, hidden annotations or semantic verdict.',
            'final': 'Retain the exact draft content and calculator evidence in the conversation; L receives its assigned full document now. Ask for all 11 final raw weights, preserved or revised reasons and evidence IDs. Freeze the first final output as the endpoint.',
            'failure': 'No automatic retries, normalization, forced correction or successful-case replacement. Record every planned case, partial response, arithmetic error and infrastructure interruption separately.',
            'source_boundary': 'The candidate file collects all packets for offline inspection only. A runner must select exactly the assigned packet; never send the packet collection or another institution to a case.',
            'output_schema': 'Keep evidence interpretation and actual allocation rationale as separately assessable fields. Exact weight or word-count limits are not inferred from literature or compression gains.',
            'preflight': 'Before freeze, check exact source visibility, full 11-sector coverage and facts/units/date identity; measure actual model-tokenized longest input and complete two-stage generation. Hardware/time ceilings require measured feasibility, not invented paper authority.'
        },
        'interpretation_pitfalls': [
            'The source packets are researcher paraphrases of selected public sections, not complete documents or private institutional mandates; the paraphrases and source limits must remain disclosed.',
            'Fidelity Overweight/Underweight and UBS Attractive are different constructs. Do not convert Attractive to a mandatory above-benchmark weight or assume identical ratings imply identical targets.',
            'There are no published exact target weights in these selected sections; absolute distance from an invented institutional target is not an eligible outcome.',
            'The common historical market packet is a documentary retrospective comparison, not contemporaneous investor replay or prospective return prediction.',
            'E/L changes when evidence can influence drafting and subsequent revision. It identifies a workflow contrast conditional on the chosen model and cases, not a pure memory or anchoring mechanism.',
            'A document-free common draft can be reused for both late-arm source branches only if explicitly preregistered as one shared counterfactual initial state. It changes dependence and is not two independent late-arm drafts.',
            'If all final allocations fail, evidence/rationale observations can still be reported, but valid-portfolio differentiation is unobserved. It cannot be guaranteed in advance.',
            'A material representation change can alter model behaviour even with exact fact preservation; do not pool v4.8 and v4.9 outputs as unchanged replicates.'
        ],
        'scope_limit': 'This audit establishes deterministic input preservation only. It is not source factual verification, human semantic review, experimental power, performance validation or confirmation of the research hypothesis.'
    }
    report_path = ROOT / 'research/v49_compaction_review_20261019.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'checks': len(checks), 'measurements': report['measurements']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
