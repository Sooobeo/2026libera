"""Offline independent arithmetic and reference-ID audit of completed v4.4 stages.

Never imports the allocation/scoring engine, opens a model endpoint, repairs model
output, or writes raw artifacts. Requires a terminal run summary before reporting.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODES = ('10', '15', '20', '25', '30', '35', '40', '45', '50', '55', '60')
SOURCE = 'fidelity_q2_2026'
CASE = SOURCE + '__R1'


def reject_constant(value):
    raise ValueError('Nonfinite JSON constant: ' + value)


def unique_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('Duplicate JSON key: ' + key)
        obj[key] = value
    return obj


def parse(text):
    return json.loads(text, parse_float=Decimal, parse_int=int,
                      object_pairs_hook=unique_pairs, parse_constant=reject_constant)


def read(path):
    return parse(Path(path).read_text(encoding='utf-8-sig'))


def numeric(value):
    return not isinstance(value, bool) and isinstance(value, (int, Decimal))


def rat(value):
    if not numeric(value):
        raise ValueError('Expected an original JSON number')
    return Fraction(value)


def decimal(value):
    with localcontext() as ctx:
        ctx.prec = 80
        return Decimal(value.numerator) / Decimal(value.denominator)


def exact(value):
    return {'fraction': str(value), 'decimal_80_digits': str(decimal(value))}


def square_root(value):
    if value < 0:
        return None
    with localcontext() as ctx:
        ctx.prec = 80
        return str(decimal(value).sqrt())


def difference(exact_value, observed):
    if not numeric(observed):
        return {'observed': observed, 'observed_minus_independent_exact': None}
    return {'observed': str(observed),
            'observed_minus_independent_exact': exact(rat(observed) - exact_value)}


def index_rows(rows):
    if not isinstance(rows, list):
        return {}, {'container_valid': False, 'missing_codes': list(CODES),
                    'duplicate_codes': [], 'unknown_codes': [], 'malformed_rows': 1}
    recognized, unknown, malformed = [], [], 0
    for row in rows:
        if not isinstance(row, dict):
            malformed += 1
            continue
        code = row.get('sector_code')
        if not isinstance(code, str) or code not in CODES:
            unknown.append(code if isinstance(code, str) else 'noncanonical_code_type')
        else:
            recognized.append((code, row))
    counts = Counter(code for code, _ in recognized)
    return ({code: row for code, row in recognized if counts[code] == 1},
            {'container_valid': True, 'missing_codes': [c for c in CODES if counts[c] == 0],
             'duplicate_codes': [c for c in CODES if counts[c] > 1],
             'unknown_codes': unknown, 'malformed_rows': malformed})


def citation(ids, code, claim, gold, allowed=None):
    if (not isinstance(ids, list) or not ids or any(not isinstance(x, str) or not x for x in ids)
            or len(ids) != len(set(ids))):
        return {'valid': False, 'status': 'missing_or_invalid_citation_list'}
    for eid in ids:
        ev = gold['evidence_index'].get(eid)
        if ev is None:
            return {'valid': False, 'status': 'unknown_evidence_id'}
        if code not in ev['sector_codes'] or (claim != 'allocation_context' and claim not in ev['claims']):
            return {'valid': False, 'status': 'wrong_sector_or_claim_scope'}
        if allowed is not None and eid not in allowed:
            return {'valid': False, 'status': 'not_a_rating_reference_for_this_sector'}
    return {'valid': True, 'status': 'citation_identity_and_scope_match_only'}


def references(proposal, gold):
    rows, structure = index_rows(proposal.get('interpretations'))
    weights, _ = index_rows(proposal.get('weights'))
    source_ok = proposal.get('source_id') == gold['source_id']
    records = []
    for code in CODES:
        row, expected = rows.get(code, {}), gold['sector_ratings'][code]
        label = row.get('rating')
        normalized = label.strip() if isinstance(label, str) else None
        rating_citation = citation(row.get('evidence_ids'), code, 'rating', gold, expected['evidence_ids'])
        allowed_reason = expected.get('reason_evidence_ids', [eid for eid, ev in gold['evidence_index'].items()
            if code in ev['sector_codes'] and 'reason' in ev['claims']])
        reason_citation = (citation(row.get('reason_evidence_ids', row.get('evidence_ids')),
            code, 'reason', gold, allowed_reason) if allowed_reason else
            {'valid': None, 'status': 'not_separately_stated_in_selected_source'})
        weight_citation = citation(weights.get(code, {}).get('evidence_ids'), code, 'allocation_context', gold)
        records.append({'sector_code': code, 'expected_rating': expected['rating'],
            'raw_rating': label, 'label_after_existing_whitespace_rule': normalized,
            'label_correct': bool(source_ok and code in rows and normalized in gold['rating_vocabulary']
                                  and normalized == expected['rating']),
            'rating_evidence_ids': row.get('evidence_ids'),
            'rating_citation_valid': bool(source_ok and code in rows and rating_citation['valid']),
            'rating_citation_status': rating_citation['status'],
            'reason_citation_valid': (bool(source_ok and code in rows and reason_citation['valid'])
                                      if allowed_reason else None),
            'reason_citation_status': reason_citation['status'],
            'allocation_evidence_ids': weights.get(code, {}).get('evidence_ids'),
            'allocation_citation_valid': bool(source_ok and code in weights and weight_citation['valid']),
            'allocation_citation_status': weight_citation['status']})
    return {'source_id_matches': source_ok, 'structure': structure,
            'correct_labels': sum(x['label_correct'] for x in records), 'fixed_label_denominator': 11,
            'rating_citation_valid_count': sum(x['rating_citation_valid'] for x in records),
            'reason_citation_valid_count': sum(x['reason_citation_valid'] is True for x in records),
            'reason_citation_expected': sum(x['reason_citation_valid'] is not None for x in records),
            'records': records,
            'meaning': 'Existing fixed reference labels and citation identity/scope only; not strategy quality or semantic entailment.'}


def arithmetic(proposal, market, recorded):
    rows, structure = index_rows(proposal.get('weights'))
    values = {c: rat(row['weight']) for c, row in rows.items() if numeric(row.get('weight'))}
    structure.update(nonnumeric_codes=[c for c, row in rows.items() if not numeric(row.get('weight'))],
                     negative_codes=[c for c, value in values.items() if value < 0],
                     above_one_codes=[c for c, value in values.items() if value > 1])
    result = {'structure': structure, 'no_normalization_or_repair': True,
              'all_11_numeric_weights': set(values) == set(CODES),
              'engine_allocation_valid': recorded['allocation']['valid'],
              'engine_sum_tolerance': str(recorded['allocation'].get('sum_tolerance')),
              'tolerance_interpretation': 'Existing 1e-6 serialization check only, never a behavioral rule or new audit acceptance cutoff.'}
    if set(values) != set(CODES):
        result.update(exact_sum=None, exact_budget_residual=None, active_weights=None, risk=None)
        return result
    total = sum(values.values(), Fraction())
    baseline = {c: rat(market['baseline_weights'][c]) for c in CODES}
    active = {c: values[c] - baseline[c] for c in CODES}
    baseline_record = recorded.get('market_diagnostics', {}).get('baseline') or {}
    risk_record = recorded.get('market_diagnostics', {}).get('risk') or {}
    order = market['sector_codes']
    if tuple(order) != CODES or len(market['covariance']) != 11 or any(len(row) != 11 for row in market['covariance']):
        raise ValueError('Unexpected covariance order or shape')
    cov = [[rat(x) for x in row] for row in market['covariance']]
    variance = sum((values[order[i]] * cov[i][j] * values[order[j]]
                    for i in range(11) for j in range(11)), Fraction())
    annualization = rat(market['annualization_trading_days'])
    half_l1 = sum(map(abs, active.values()), Fraction()) / 2
    result.update(exact_sum=exact(total), exact_budget_residual=exact(total - 1),
        exactly_full_investment=(total == 1),
        recorded_sum_comparison=difference(total, recorded['allocation'].get('raw_sum')),
        recorded_budget_residual_comparison=difference(total - 1, recorded['allocation'].get('raw_budget_residual')),
        exact_baseline_sum=exact(sum(baseline.values(), Fraction())),
        exact_baseline_budget_residual=exact(sum(baseline.values(), Fraction()) - 1),
        active_weights={c: {'weight': exact(values[c]), 'supplied_baseline': exact(baseline[c]),
            'active_weight': exact(active[c]),
            'calculator_comparison': difference(active[c], baseline_record.get('raw_active_weights', {}).get(c))}
            for c in CODES},
        half_l1_distance=exact(half_l1),
        half_l1_calculator_comparison=difference(half_l1, baseline_record.get('raw_half_L1_distance')),
        risk={'covariance_unit': market['covariance_unit'], 'daily_variance_exact': exact(variance),
              'daily_volatility_80_digits': square_root(variance),
              'daily_variance_calculator_comparison': difference(variance, risk_record.get('raw_variance')),
              'daily_volatility_calculator_record': str(risk_record.get('volatility')),
              'annualization_factor_from_market': str(annualization),
              'annualized_variance_derived_exact': exact(variance * annualization),
              'annualized_volatility_derived_80_digits': square_root(variance * annualization),
              'annualized_values_are_audit_derivations_not_engine_daily_output': True,
              'meaning': 'w-transpose covariance w on frozen historical inputs; not future loss probability or strategic optimality.'})
    return result


def source_file(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'size_bytes': path.stat().st_size}


def inspect_incomplete_transport(run, stage, paths):
    """Describe captured bytes only. Never turn a prefix into a scored answer."""
    transport = run / f'stage{stage}_transport'
    http = transport / 'http_0001_generation'
    request = http / 'request.json'
    if not request.is_file():
        return {'status': 'generation_not_started', 'completed_response': None,
                'ratings_weights_and_risk': None}
    for relative in ('authoritative_body.json', 'supervisor_result.json',
                     'unload_and_residency.json', 'http_0001_generation/request.json',
                     'http_0001_generation/raw_stream.bin', 'http_0001_generation/events.jsonl'):
        path = transport / relative
        if path.is_file():
            paths.append(path)
    raw_path = http / 'raw_stream.bin'
    data = raw_path.read_bytes() if raw_path.is_file() else None
    events, unparsed_lines = [], []
    if data is not None:
        for number, line in enumerate(data.splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = parse(line.decode('utf-8'))
                if not isinstance(value, dict):
                    raise ValueError('Non-object stream event')
                events.append(value)
            except (ValueError, UnicodeDecodeError) as exc:
                unparsed_lines.append({'line': number, 'byte_count': len(line),
                                       'reason': type(exc).__name__})
    content = ''.join(x.get('message', {}).get('content', '') for x in events)
    event_path = http / 'events.jsonl'
    recorded_events = [read_event['event'] for read_event in
                      [parse(line) for line in event_path.read_text(encoding='utf-8').splitlines() if line.strip()]] if event_path.is_file() else None
    try:
        complete_json = isinstance(parse(content), dict)
    except (ValueError, TypeError):
        complete_json = False
    return {'status': 'generation_attempted_without_completed_workflow_record',
        'raw_stream_bytes': len(data) if data is not None else None,
        'parseable_stream_events': len(events), 'unparsed_lines': unparsed_lines,
        'terminal_done_true_events': sum(x.get('done') is True for x in events),
        'event_log_matches_parseable_raw_events': recorded_events == events if recorded_events is not None else None,
        'partial_content_character_count': len(content),
        'partial_content_utf8_sha256': hashlib.sha256(content.encode()).hexdigest(),
        'partial_content_prefix_240_characters': content[:240],
        'partial_content_is_complete_json_object': complete_json,
        'workflow_or_http_completed_response_file_present': (http / 'response.json').is_file(),
        'supervisor': read(transport / 'supervisor_result.json') if (transport / 'supervisor_result.json').is_file() else None,
        'ratings_weights_and_risk': None,
        'scoring_policy': 'The partial prefix is preserved, not repaired or evaluated as a completed interpretation/allocation. No zero score is assigned.'}


def audit(run):
    run = Path(run).resolve()
    summary_path = run / 'summary.json'
    if not summary_path.is_file():
        raise RuntimeError('Terminal summary not yet present; no final audit is created')
    summary = read(summary_path)
    if not summary.get('finished_at_utc') or summary.get('status') in ('started', 'attempted', 'not_started'):
        raise RuntimeError('Run has not produced a terminal summary')
    invocation, manifest = read(run / 'invocation.json'), read(run / 'manifest_snapshot.json')
    prepared = Path(invocation['manifest_path']).parent
    market_path, packet_path = prepared / 'market_input.json', prepared / 'model_packet.json'
    for name, path in [('market_input.json', market_path), ('model_packet.json', packet_path)]:
        if source_file(path)['sha256'] != manifest['inputs'][name]:
            raise ValueError('Prepared source no longer matches run snapshot: ' + name)
    market, packet = read(market_path), read(packet_path)
    gold_path = ROOT / 'data/sector_documents/evaluator_only/reference_annotations.jsonl'
    gold = [parse(line) for line in gold_path.read_text(encoding='utf-8-sig').splitlines()
            if line.strip() and parse(line).get('source_id') == SOURCE]
    if len(gold) != 1 or set(gold[0]['sector_ratings']) != set(CODES):
        raise ValueError('Expected the fixed full 11-sector evaluator reference')
    gold = gold[0]
    paths = [summary_path, run / 'invocation.json', run / 'manifest_snapshot.json',
             market_path, packet_path, gold_path, Path(__file__)]
    stages, observations, consistency = [], [], []
    for n in range(1, 5):
        record_path = run / CASE / f'stage{n}_record.json'
        if not record_path.is_file():
            partial = inspect_incomplete_transport(run, n, paths)
            if partial.get('event_log_matches_parseable_raw_events') is False:
                consistency.append({'stage': n, 'issue': 'partial_event_log_differs_from_parseable_raw_stream'})
            stages.append({'stage': n, 'status': 'no_completed_workflow_record',
                'numeric_or_label_result': None,
                'incomplete_transport_observations': partial,
                'scope': 'Missing completion is not a fabricated zero-score or a repaired response.'})
            continue
        response_path = run / CASE / f'stage{n}_response.json'
        transport = run / f'stage{n}_transport/http_0001_generation'
        paths.extend([record_path, response_path, transport / 'response.json',
                      transport / 'events.jsonl', transport / 'raw_stream.bin', transport / 'request.json'])
        record, response, http_response = read(record_path), read(response_path), read(transport / 'response.json')
        if response != http_response:
            consistency.append({'stage': n, 'issue': 'workflow_response_differs_from_captured_HTTP_response'})
        raw_events = [parse(line) for line in (transport / 'raw_stream.bin').read_text(encoding='utf-8').splitlines() if line.strip()]
        content_from_events = ''.join(x.get('message', {}).get('content', '') for x in raw_events)
        raw_content = http_response['message']['content']
        if content_from_events != raw_content:
            consistency.append({'stage': n, 'issue': 'raw_stream_content_differs_from_assembled_response'})
        proposal = parse(raw_content)
        if proposal != record['raw_proposal']:
            consistency.append({'stage': n, 'issue': 'record_proposal_differs_from_original_JSON_numeric_values'})
        if proposal.get('weights', []) != record['calculator_arguments']['weights']:
            consistency.append({'stage': n, 'issue': 'calculator_weight_arguments_differ_from_original_JSON'})
        refs = references(proposal, gold)
        maths = arithmetic(proposal, market, record['calculator_result'])
        if refs['correct_labels'] != 11:
            observations.append({'stage': n, 'type': 'label_mismatch_or_omission',
                'correct': refs['correct_labels'], 'fixed_denominator': 11})
        if refs['rating_citation_valid_count'] != 11:
            observations.append({'stage': n, 'type': 'rating_citation_identity_or_scope_mismatch',
                'valid': refs['rating_citation_valid_count'], 'fixed_denominator': 11,
                'semantic_entailment_not_evaluated': True})
        if n >= 3 and not maths['all_11_numeric_weights']:
            observations.append({'stage': n, 'type': 'required_allocation_not_complete'})
        if n >= 3 and not maths['engine_allocation_valid']:
            observations.append({'stage': n, 'type': 'existing_calculator_allocation_validity_false',
                'independent_structure': maths['structure'], 'new_acceptance_threshold': None})
        if maths.get('exact_budget_residual') and not maths.get('exactly_full_investment'):
            observations.append({'stage': n, 'type': 'nonzero_exact_budget_residual',
                'residual': maths['exact_budget_residual'], 'not_automatically_failed_by_new_threshold': True})
        stages.append({'stage': n, 'status': 'completed_record_independently_examined',
            'raw_content_utf8_sha256': hashlib.sha256(raw_content.encode()).hexdigest(),
            'done_reason': response.get('done_reason'), 'reference_checks': refs, 'arithmetic': maths,
            'early_empty_weights_permitted': n < 3,
            'recorded_calculator_ok': record['calculator_result']['ok'],
            'submitted_constraints': proposal.get('submitted_constraints', [])})
    completed = sum(x['status'] == 'completed_record_independently_examined' for x in stages)
    if completed != summary.get('completed_workflow_stages'):
        consistency.append({'issue': 'observed_completed_record_count_differs_from_summary'})
    if summary.get('main_model_calls') != 0 or summary.get('main_freeze') is not False:
        consistency.append({'issue': 'one_case_pilot_scope_or_main_freeze_differs_from_prespecification'})
    covariance = [[rat(x) for x in row] for row in market['covariance']]
    symmetry_residual = max(abs(covariance[i][j] - covariance[j][i]) for i in range(11) for j in range(11))
    reported = [rat(x) for x in market['benchmark_reported_weights_percent']]
    total_reported = sum(reported, Fraction())
    baseline_derivation = {c: {'exact_ratio_of_reported_percentages': exact(reported[i] / total_reported),
        'supplied_baseline_minus_ratio': exact(rat(market['baseline_weights'][c]) - reported[i] / total_reported)}
        for i, c in enumerate(CODES)}
    return {'schema_version': 'libera_v44_single_case_round2_1.0',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'run_directory': str(run), 'case_id': CASE,
        'review_status': 'completed_with_consistency_findings' if consistency else 'completed_no_consistency_mismatch',
        'review_scope': 'Independent exact arithmetic and existing mechanical label/citation rules on completed records only; no engine import, repair, model call or new quality score.',
        'run_status': summary['status'], 'completed_workflow_records_reviewed': completed,
        'run_counts': {k: summary.get(k) for k in ['generation_requests_attempted', 'http_streams_completed',
            'completed_workflow_stages', 'generation_stages_not_started', 'main_model_calls',
            'cases_with_generation_attempt', 'completed_cases', 'automatic_retries']},
        'stages': stages, 'model_observations': observations, 'consistency_findings': consistency,
        'market_checks': {'covariance_unit': market['covariance_unit'],
            'exact_max_symmetry_residual': exact(symmetry_residual),
            'PSD_scope': 'Existing engine PSD tolerance is 1e-12 for numerical validation only; this audit does not turn it into a behavioral acceptance rule.',
            'reported_benchmark_percent_sum': exact(total_reported),
            'baseline_derivation_audit': baseline_derivation},
        'reference_status': gold['reference_status'], 'human_semantic_review': 'pending_separate_round3_and_human_review',
        'limits': ['Each stage belongs to one same case and is not an independent sample.',
                  'Labels use the prespecified fixed 11-sector denominator; citation IDs verify identity/scope, not entailment.',
                  'Under the existing allocation citation rule, every cited ID must include the row sector. A cross-sector comparison can therefore fail this mechanical scope check without proving a reasoning or strategy error; semantic review is separate and the rule is not changed after observing results.',
                  'Weights have no unique institution-provided numeric gold. Differences or directional departures are descriptive.',
                  'All exact arithmetic uses JSON decimal literals as rational numbers. Calculator binary-floating differences are disclosed continuously without inventing a pass threshold.',
                  'Missing/failed stages are not imputed. No R1-versus-R4 effect or population conclusion follows from this one R1 case.'],
        'main_frozen': False, 'model_calls_by_reviewer': 0,
        'source_files': [source_file(p) for p in dict.fromkeys(paths)]}


def render(report):
    esc = html.escape
    rows = []
    for s in report['stages']:
        if s['status'] != 'completed_record_independently_examined':
            partial = s.get('incomplete_transport_observations', {})
            label = ('생성 시도 후 미완료 — 수치·등급 판정 불가' if
                     partial.get('status') == 'generation_attempted_without_completed_workflow_record'
                     else '미시작 — 수치·등급 판정 미관측')
            rows.append(f'<tr><td>{s["stage"]}</td><td colspan="4">{label}</td></tr>')
            continue
        ar = s['arithmetic']; refs = s['reference_checks']
        total = ar.get('exact_sum', {}).get('fraction') if ar.get('exact_sum') else '비중 미제출'
        residual = ar.get('exact_budget_residual', {}).get('fraction') if ar.get('exact_budget_residual') else '미관측'
        rows.append(f'<tr><td>{s["stage"]}</td><td>{refs["correct_labels"]}/11</td>'
                    f'<td>{refs["rating_citation_valid_count"]}/11</td><td>{esc(total)}</td><td>{esc(residual)}</td></tr>')
    final = next((s for s in report['stages'] if s['stage'] == 4 and s.get('arithmetic')), None)
    details = ''
    if final and final['arithmetic'].get('active_weights'):
        weights = final['arithmetic']['active_weights']; weight_rows = []
        for code in CODES:
            w = weights[code]
            weight_rows.append(f'<tr><td>{code}</td><td>{float(Decimal(w["weight"]["decimal_80_digits"])) * 100:.6f}%</td>'
                f'<td>{float(Decimal(w["active_weight"]["decimal_80_digits"])) * 100:+.6f}%p</td></tr>')
        risk = final['arithmetic']['risk']
        details = '<h2>최종 비중의 독립 재계산</h2><table><tr><th>GICS</th><th>비중</th><th>기준비중과 차이</th></tr>' + ''.join(weight_rows) + '</table>'
        details += f'<p>일간 분산 w′Σw: {esc(risk["daily_variance_exact"]["decimal_80_digits"])}. 일간 공분산을 사용했고, 이는 미래 손실확률이 아닙니다.</p>'
    consistency = ('기록 간 불일치 ' + str(len(report['consistency_findings'])) + '건') if report['consistency_findings'] else '기록 간 대조에서 불일치 없음'
    no_completed = ('<p><b>이번 실행에서는 계산 가능한 완성 답변이 없습니다.</b> 첫 단계의 부분 문자열은 보존했지만 완성 JSON으로 고치거나 0점으로 환산하지 않았습니다. 비중 합계·위험·등급 정확도는 모두 계산 불가이며, 뒤의 세 단계는 실행되지 않았습니다.</p>'
                    if report['completed_workflow_records_reviewed'] == 0 else '')
    return '<!doctype html><html lang="ko"><meta charset="utf-8"><title>LIBERA v4.4 2차 독립 검증</title><style>body{max-width:920px;margin:40px auto;padding:0 20px;font:16px/1.7 system-ui;color:#172334}table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #ddd;text-align:left}code{overflow-wrap:anywhere}h2{margin-top:30px}</style><main>' + \
        f'<h1>단일 예비사례: 2차 독립 검증</h1><p>실행 상태: <b>{esc(report["run_status"])}</b>. 완료 기록 {report["completed_workflow_records_reviewed"]}개와 보존된 시도 기록을 대조했습니다. {consistency}.</p>' + no_completed + \
        '<p>등급은 기존 평가표의 11개 산업 기준입니다. 근거 ID가 맞더라도 설명의 의미가 옳다는 뜻은 아니며, 비중에도 유일한 정답은 없습니다. 다른 산업과 비교한 근거는 기존의 산업별 ID 규칙에 맞지 않을 수 있으나, 이것만으로 논리·전략 오류라고 판단하지 않습니다. 의미 검토는 별도입니다. 1·2단계는 비중을 제출하지 않아도 됩니다.</p>' + \
        '<table><tr><th>단계</th><th>등급 일치</th><th>등급 근거 ID·범위</th><th>정확한 비중 합</th><th>합−1</th></tr>' + ''.join(rows) + '</table>' + details + \
        '<p>완성된 비중이 있을 때에만 원문 소수를 유리수로 바꾸어 합계·기준비중 차이·분산을 독립 계산하도록 설계했습니다. 새로운 합격 기준은 만들지 않았습니다. 본실험 0회이며, 이 한 사례로 전략 성능이나 기관 일반의 행동을 판단할 수 없습니다.</p>' + \
        '<p><a href="v44_single_case_round2_20261018.json">정확한 수치·원본 해시·전체 검증 JSON</a></p></main></html>'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output-stem', type=Path, default=ROOT / 'research/v44_single_case_round2_20261018')
    args = parser.parse_args()
    report = audit(args.run_dir)
    json_path, html_path = args.output_stem.with_suffix('.json'), args.output_stem.with_suffix('.html')
    if json_path.exists() or html_path.exists():
        raise FileExistsError('Audit outputs are immutable; use a new output stem for a subsequent review')
    with json_path.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        handle.write('\n')
    with html_path.open('x', encoding='utf-8') as handle:
        handle.write(render(report))
    print(json.dumps({'path': str(json_path), 'sha256': source_file(json_path)['sha256'],
                      'review_status': report['review_status'], 'reviewed_stages': report['completed_workflow_records_reviewed'],
                      'consistency_findings': len(report['consistency_findings'])}))


if __name__ == '__main__':
    main()
