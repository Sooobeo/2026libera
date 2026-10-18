"""Independent v4.5 audit: exact arithmetic plus the fixed 11-label endpoint.

Uses the frozen independent Fraction helpers, never the production scorer or
calculator. Reads saved artifacts only and requires a terminal run summary.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import html
import json
import math
from pathlib import Path

import audit_v44_single_case_round2 as independent

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'research/audit_v44_single_case_round2.py'
HELPER_SHA = 'ea264a1e531c6f481e3dc201a86abd3d73c4e57963c7e86be0414973af1fbaa4'
SPEC = ROOT / 'data/sector_protocol/evaluation_spec.json'
CODES = independent.CODES


def load_gold():
    path = ROOT / 'data/sector_documents/evaluator_only/reference_annotations.jsonl'
    rows = [independent.parse(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    selected = [x for x in rows if x.get('source_id') == independent.SOURCE]
    if len(selected) != 1 or set(selected[0]['sector_ratings']) != set(CODES):
        raise ValueError('Full prespecified evaluator reference is required')
    return selected[0]


def captured_proposal(run, stage):
    """A complete saved HTTP response is parseable or invalid; prefixes stay unavailable."""
    path = run / f'stage{stage}_transport/http_0001_generation/response.json'
    if not path.is_file():
        return None, {'status': 'no_complete_saved_HTTP_response', 'parseable_complete_object': False}, []
    response = independent.read(path)
    content = response.get('message', {}).get('content')
    meta = {'status': 'saved_HTTP_response', 'done_reason': response.get('done_reason'),
            'raw_content_utf8_sha256': hashlib.sha256(content.encode()).hexdigest() if isinstance(content, str) else None}
    try:
        proposal = independent.parse(content)
        if not isinstance(proposal, dict):
            raise ValueError('Response is not an object')
        meta['parseable_complete_object'] = True
        return proposal, meta, [path]
    except (ValueError, TypeError):
        meta.update(parseable_complete_object=False, parse_status='invalid_or_ambiguous_JSON')
        return None, meta, [path]


def fixed_endpoint(proposal, gold):
    if proposal is None:
        return {'correct': 0, 'expected': 11, 'accuracy_exact': '0',
                'reason': 'A missing or unparseable final response retains the original 11-label denominator.',
                'conditional_semantic_evaluability': 'not_applicable_no_complete_object'}
    refs = independent.references(proposal, gold)
    count = refs['correct_labels']
    return {'correct': count, 'expected': 11, 'accuracy_exact': str(Fraction(count, 11)),
            'reason': 'Exact original-source label, unique sector row and correct source identity, per the unchanged evaluation specification.',
            'conditional_semantic_evaluability': 'requires_separate_semantic_review_not_established_by_labels'}


def validity_without_engine(proposal, recorded):
    rows, structure = independent.index_rows(proposal.get('weights'))
    numbers, nonnumeric, negative, above = {}, [], [], []
    for code, row in rows.items():
        value = row.get('weight')
        if not independent.numeric(value):
            nonnumeric.append(code)
            continue
        try:
            as_float = float(value)
        except (ValueError, OverflowError):
            nonnumeric.append(code)
            continue
        if not math.isfinite(as_float):
            nonnumeric.append(code)
            continue
        numbers[code] = as_float
        if as_float < 0: negative.append(code)
        if as_float > 1: above.append(code)
    try:
        total = math.fsum(numbers.values()) if len(numbers) == 11 else None
    except OverflowError:
        total = None
    if total is not None and not math.isfinite(total):
        total = None
    residual = total - 1 if total is not None else None
    valid = bool(structure['container_valid'] and not structure['missing_codes']
        and not structure['duplicate_codes'] and not structure['unknown_codes']
        and not structure['malformed_rows'] and not nonnumeric and not negative and not above
        and residual is not None and abs(residual) <= 1e-6)
    observed = recorded.get('allocation', {}).get('valid')
    return {'valid': valid, 'engine_recorded_valid': observed,
            'matches_recorded_validity': valid == observed if isinstance(observed, bool) else None,
            'existing_sum_tolerance': '1e-6',
            'existing_negative_and_above_one_tolerance': '0',
            'tolerance_role': 'Existing numerical implementation rule, not a paper-derived behavioral rule or a new cutoff.',
            'binary_float_sum_comparable_to_existing_engine': total,
            'binary_float_residual_comparable_to_existing_engine': residual,
            'exact_rational_sum_and_residual': 'Reported separately in arithmetic; never substituted, normalized or rounded to zero.'}


def augment_numeric_comparison(stage, proposal, gold, market, recorded):
    arithmetic = stage['arithmetic']
    validity = validity_without_engine(proposal, recorded)
    arithmetic['independently_recomputed_existing_validity'] = validity
    invalid_vector = not validity['valid']
    algebra_scope = ('raw_invalid_vector_algebra_only_not_fully_invested_valid_portfolio_risk'
                     if invalid_vector else 'raw_allocation_admissible_under_existing_numeric_checks')
    arithmetic['interpretation_scope'] = algebra_scope
    arithmetic['raw_invalid_vector_algebra_only'] = invalid_vector
    arithmetic['unallocated_residual_handling'] = 'No automatic cash assumption, rescaling, normalization, leverage interpretation or repaired portfolio is introduced.'
    arithmetic['distance_comparability'] = ('Active weights and half-L1 remain algebraic differences of the supplied coordinates; do not treat this as a valid-allocation comparison or compare it as if both vectors were admissible portfolios.'
                                          if invalid_vector else 'Descriptive differences from the supplied comparator; not unique strategic truth or evidence of superior strategy.')
    if arithmetic.get('risk'):
        risk = arithmetic['risk']
        risk['interpretation_scope'] = algebra_scope
        risk['raw_invalid_vector_algebra_only'] = invalid_vector
        risk['not_fully_invested_valid_portfolio_risk'] = invalid_vector
        risk['no_automatic_cash_assumption'] = True
        risk['cross_valid_portfolio_comparability'] = ('not_established_for_invalid_raw_vector'
                                                      if invalid_vector else 'descriptive_same_input_covariance_only')
        observed = recorded.get('market_diagnostics', {}).get('risk') or {}
        value = observed.get('volatility')
        if independent.numeric(value) and risk['daily_volatility_80_digits'] is not None:
            with localcontext() as ctx:
                ctx.prec = 80
                risk['calculator_daily_volatility_minus_independent_80_digit_value'] = str(
                    Decimal(value) - Decimal(risk['daily_volatility_80_digits']))
        else:
            risk['calculator_daily_volatility_minus_independent_80_digit_value'] = None
    active = arithmetic.get('active_weights')
    if active:
        semantics = gold.get('allocation_semantics', {})
        allowed = (semantics.get('kind') == 'benchmark_relative_tilt'
                   and semantics.get('baseline_id') == market.get('baseline_id'))
        records = []
        if allowed:
            mapping = semantics.get('label_directions', {})
            for code in CODES:
                label = gold['sector_ratings'][code]['rating']
                direction = mapping.get(label)
                if direction not in (-1, 0, 1): continue
                tilt = Fraction(active[code]['active_weight']['fraction'])
                records.append({'sector_code': code, 'source_label': label,
                    'raw_active_weight': independent.exact(tilt),
                    'signed_tilt': independent.exact(direction * tilt) if direction else None,
                    'absolute_tilt_for_neutral': independent.exact(abs(tilt)) if direction == 0 else None})
        arithmetic['source_tilt_diagnostics'] = {'records': records,
            'meaning': 'Continuous descriptive reference-direction diagnostics only; no strategy pass/fail or unique weight target.'}
    return validity


def audit(run):
    if independent.source_file(HELPER)['sha256'] != HELPER_SHA:
        raise ValueError('Frozen independent arithmetic helper changed')
    run = Path(run).resolve()
    summary = independent.read(run / 'summary.json')
    if summary.get('protocol_version') != '4.5':
        raise ValueError('Do not pool protocol revisions: this report is v4.5 only')
    result = independent.audit(run)
    gold = load_gold()
    invocation = independent.read(run / 'invocation.json')
    market = independent.read(Path(invocation['manifest_path']).parent / 'market_input.json')
    extra_paths = [Path(__file__), SPEC]
    final_proposal = None
    for stage in result['stages']:
        number = stage['stage']
        proposal, observation, paths = captured_proposal(run, number)
        extra_paths.extend(paths)
        stage['captured_answer_observation'] = observation
        stage['fixed_denominator_extraction'] = fixed_endpoint(proposal, gold)
        if number == 4:
            final_proposal = proposal
        if proposal is None:
            stage['conditional_numeric_assessment'] = 'not_applicable_no_complete_proposal'
            continue
        record_path = run / independent.CASE / f'stage{number}_record.json'
        if record_path.is_file():
            recorded = independent.read(record_path)['calculator_result']
        else:
            recorded = {'allocation': {'valid': None, 'sum_tolerance': None}, 'market_diagnostics': {}}
            stage['reference_checks'] = independent.references(proposal, gold)
            stage['arithmetic'] = independent.arithmetic(proposal, market, recorded)
            stage['complete_raw_answer_without_completed_workflow_record'] = True
        validity = augment_numeric_comparison(stage, proposal, gold, market, recorded)
        stage['conditional_numeric_assessment'] = ('computed_on_unrepaired_raw_numbers' if
            stage['arithmetic']['all_11_numeric_weights'] else 'unavailable_incomplete_weight_vector')
        if validity['matches_recorded_validity'] is False:
            result['consistency_findings'].append({'stage': number,
                'issue': 'independent_existing_validity_differs_from_recorded_calculator'})
    prior_path = ROOT / 'data/local_sector_runtime/single_case_v44_20261018/summary.json'
    prior = independent.read(prior_path)
    if prior.get('protocol_version') != '4.4' or prior.get('completed_workflow_stages') != 0:
        raise ValueError('Expected preserved v4.4 zero-completed-stage attempt for denominator clarification')
    extra_paths.append(prior_path)
    final_endpoint = fixed_endpoint(final_proposal, gold)
    result.update(schema_version='libera_v45_single_case_round2_1.0', protocol_version='4.5',
        review_scope='Independent saved-output arithmetic and unchanged mechanical label/citation rules. The frozen independent helper is reused; production scoring/calculator code is not imported.',
        registered_final_extraction_endpoint=final_endpoint,
        denominator_clarification={
            'prior_v44_files_modified': False,
            'v44_failed_attempt_fixed_label_endpoint': {'correct': 0, 'expected': 11, 'accuracy_exact': '0'},
            'v44_conditional_semantic_and_numeric_assessment': 'not_applicable_no_completed_answer_or_allocation',
            'correction': 'The earlier v4.4 round2 report correctly left conditional semantic/numeric assessment unavailable, but did not separately report the registered failure-inclusive label endpoint. That endpoint is 0/11. This additive clarification preserves the original failure bytes and reviews.',
            'v45_final_endpoint_reported_separately': True,
            'no_pooling_across_protocol_revisions': True,
            'no_conversion_to_zero_strategy_quality_or_zero_risk': True},
        final_allocation_evaluability=('raw_completed_answer_present_see_numeric_checks' if final_proposal is not None
                                      else 'not_applicable_no_complete_final_response'),
        independent_arithmetic_helper={'path': HELPER.relative_to(ROOT).as_posix(), 'sha256': HELPER_SHA},
        review_status=('completed_with_consistency_findings' if result['consistency_findings']
                       else 'completed_no_consistency_mismatch'))
    existing = {x['path'] for x in result['source_files']}
    for path in extra_paths:
        record = independent.source_file(path)
        if record['path'] not in existing:
            result['source_files'].append(record); existing.add(record['path'])
    result['limits'].append('Stage scores are diagnostic repeated observations within one case. The registered final endpoint uses stage4 and includes failed/missing responses in its denominator; this is separate from conditional semantic and allocation evaluation.')
    result['limits'].append('For an invalid submitted weight vector, w-transpose covariance w, its square root, active weights and half-L1 are retained only as raw algebra. They are not the risk or comparison of a valid fully invested portfolio; no omitted weight is silently treated as cash, and no cross-valid-portfolio comparability is asserted.')
    return result


def render(result):
    esc = html.escape
    rows = []
    for s in result['stages']:
        endpoint = s['fixed_denominator_extraction']
        ar = s.get('arithmetic')
        observed = s['captured_answer_observation']['parseable_complete_object']
        count = str(endpoint['correct']) + '/11'
        note = ('완성 JSON 관측' if observed else '완성 답변 미관측')
        if ar and ar.get('exact_sum'):
            total, residual = ar['exact_sum']['fraction'], ar['exact_budget_residual']['fraction']
        else:
            total, residual = '계산 불가', '미관측'
        validity = (ar or {}).get('independently_recomputed_existing_validity')
        numeric_status = ('유효' if validity['valid'] else '무효 · 원문 벡터 산술만') if validity else '미평가'
        refs = s.get('reference_checks')
        ids = str(refs['rating_citation_valid_count']) + '/11' if refs else '완성 답변 없음'
        rows.append(f'<tr><td>{s["stage"]}</td><td>{note}</td><td>{count}</td><td>{ids}</td><td>{esc(total)}</td><td>{esc(residual)}</td><td>{numeric_status}</td></tr>')
    final = result['stages'][3]
    details = ''
    if final.get('arithmetic', {}).get('active_weights'):
        cells = []
        for code in CODES:
            values = final['arithmetic']['active_weights'][code]
            weight = float(Decimal(values['weight']['decimal_80_digits'])) * 100
            tilt = float(Decimal(values['active_weight']['decimal_80_digits'])) * 100
            cells.append(f'<tr><td>{code}</td><td>{weight:.6f}%</td><td>{tilt:+.6f}%p</td></tr>')
        risk = final['arithmetic']['risk']
        details = '<h2>최종 원문 비중과 독립 계산</h2><table><tr><th>GICS</th><th>비중</th><th>기준비중 차이</th></tr>' + ''.join(cells) + '</table>'
        if risk.get('raw_invalid_vector_algebra_only'):
            details += '<p><b>최종 비중 벡터는 기존 수치 요건에 맞지 않습니다.</b> 아래 w′Σw와 제곱근·기준비중 차이는 원문 벡터의 산술값일 뿐, 정상적으로 전액 투자한 포트폴리오의 위험이 아닙니다. 빠진 비중을 현금으로 간주하지 않았고 유효한 포트폴리오와 같은 조건의 위험 비교도 성립한다고 보지 않습니다.</p>'
            details += '<p>무효 원문 벡터의 일간 공분산 이차식 w′Σw: '
        else:
            details += '<p>일간 분산 w′Σw: '
        details += esc(risk['daily_variance_exact']['decimal_80_digits']) + '. 숫자 반올림 차이와 정확한 유리수 값은 JSON에 기록했습니다.</p>'
    endpoint = result['registered_final_extraction_endpoint']
    return '<!doctype html><html lang="ko"><meta charset="utf-8"><title>v4.5 단일사례 2차 독립 검증</title><style>body{max-width:1000px;margin:40px auto;padding:0 20px;font:16px/1.7 system-ui;color:#182a3c}table{border-collapse:collapse;width:100%}th,td{padding:9px;border-bottom:1px solid #ddd;text-align:left}p{overflow-wrap:anywhere}</style><main>' + \
        '<h1>v4.5: 2차 독립 산술·등급 검증</h1>' + \
        f'<p>실행 상태 <b>{esc(result["run_status"])}</b>, 완료 단계 {result["completed_workflow_records_reviewed"]}/4. 최종 응답의 고정 분모 등급 일치는 <b>{endpoint["correct"]}/11</b>입니다.</p>' + \
        '<p>실패한 v4.4는 기존 평가 규칙상 등급 추출 지표에 <b>0/11</b>로 포함됩니다. 반면 완성 답변이 없어 의미·비중·위험은 평가 불가였습니다. 이전 보고서의 조건부 평가와 실패 포함 지표를 구분하는 추가 설명이며, 원본은 수정하지 않았습니다. v4.4와 v4.5 결과도 합산하지 않습니다.</p>' + \
        '<table><tr><th>단계</th><th>관측 상태</th><th>등급 일치</th><th>등급 근거 ID</th><th>정확 비중 합</th><th>합−1</th><th>기존 수치 요건</th></tr>' + ''.join(rows) + '</table>' + details + \
        '<p>원문 숫자를 정규화하거나 고치지 않습니다. 정확한 합계·기준비중 차이·공분산 기반 분산과 변동성을 독립 재계산하며, 기존 1e−6 검사는 수치 구현 기준으로만 기록합니다. 등급·ID 일치는 전략 타당성을 입증하지 않습니다. 교차산업 비교 근거가 기존 산업별 ID 범위 규칙에 맞지 않아도 그것만으로 논리 오류라고 판단하지 않습니다.</p>' + \
        '<p>본실험 0회, 하나의 개발용 R1 사례입니다. 의미 검토는 별도 3차 검증으로 남기며, 형식 제약의 성공을 일반적 금융 판단 능력이나 전략 성능으로 확대하지 않습니다.</p>' + \
        '<p><a href="v45_single_case_round2_20261018.json">전체 수치·해시·검증 JSON</a></p></main></html>'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--output-stem', type=Path, default=ROOT / 'research/v45_single_case_round2_20261018')
    args = parser.parse_args()
    result = audit(args.run_dir)
    json_path, html_path = args.output_stem.with_suffix('.json'), args.output_stem.with_suffix('.html')
    if json_path.exists() or html_path.exists():
        raise FileExistsError('Preserve an existing immutable audit; choose a new output stem')
    with json_path.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False, default=str)
        handle.write('\n')
    with html_path.open('x', encoding='utf-8') as handle:
        handle.write(render(result))
    print(json.dumps({'path': str(json_path), 'sha256': independent.source_file(json_path)['sha256'],
                      'review_status': result['review_status'],
                      'final_fixed_label_endpoint': result['registered_final_extraction_endpoint']}))


if __name__ == '__main__':
    main()
