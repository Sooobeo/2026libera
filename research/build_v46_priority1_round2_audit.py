"""Offline independent arithmetic audit for the one-call v4.6 diagnostic.

No model/client/runtime imports. Exact Fraction arithmetic starts from decimal
JSON literals. Raw values are never normalized, repaired or treated as cash.
The audit reports failures and missing observations; it never retries a model.
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
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'data/sector_protocol/evaluation_spec.json'
RUBRIC = ROOT / 'research/evaluator_only/v46_replay_priority1_rubric_addendum_20261018.json'


def strict_json(text):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('Duplicate JSON key: ' + key)
            value[key] = item
        return value
    def constant(value):
        raise ValueError('Nonfinite JSON literal: ' + value)
    return json.loads(text, object_pairs_hook=unique, parse_float=Decimal,
                      parse_int=Decimal, parse_constant=constant)


def number(value):
    return isinstance(value, Decimal) and value.is_finite()


def exact_text(value):
    if value is None:
        return None
    value = Fraction(value)
    with localcontext() as context:
        context.prec = max(100, len(str(abs(value.numerator))) + len(str(value.denominator)) + 5)
        return format(Decimal(value.numerator) / Decimal(value.denominator), 'f')


def structural_errors(value, schema, path='$'):
    """Independent validation of the JSON-schema subset in the frozen schema."""
    if 'anyOf' in schema:
        return [] if any(not structural_errors(value, s, path) for s in schema['anyOf']) else [path + ': anyOf']
    allowed = schema['type'] if isinstance(schema['type'], list) else [schema['type']]
    types = {'object': isinstance(value, dict), 'array': isinstance(value, list),
             'string': isinstance(value, str), 'number': number(value), 'null': value is None}
    if not any(types[t] for t in allowed):
        return [path + ': type']
    errors = []
    if 'enum' in schema and value not in schema['enum']:
        errors.append(path + ': enum')
    if isinstance(value, dict):
        errors.extend(path + ': missing ' + key for key in schema.get('required', []) if key not in value)
        for key, item in value.items():
            if key in schema.get('properties', {}):
                errors.extend(structural_errors(item, schema['properties'][key], path + '.' + key))
            elif schema.get('additionalProperties') is False:
                errors.append(path + ': unexpected ' + key)
    elif isinstance(value, list):
        if len(value) < schema.get('minItems', 0) or len(value) > schema.get('maxItems', math.inf):
            errors.append(path + ': length')
        for index, item in enumerate(value):
            errors.extend(structural_errors(item, schema['items'], f'{path}[{index}]'))
    elif isinstance(value, str) and len(value) < schema.get('minLength', 0):
        errors.append(path + ': length')
    return errors


def arithmetic(rows, codes, tolerance):
    if not isinstance(rows, list):
        return {'valid': False, 'reason': 'weights_not_array', 'values': {}, 'sum': None}
    observed = [r.get('sector_code') if isinstance(r, dict) else None for r in rows]
    counts = Counter(c for c in observed if isinstance(c, str))
    missing = [c for c in codes if counts[c] == 0]
    duplicates = [c for c in codes if counts[c] > 1]
    unknown = [c for c in observed if not isinstance(c, str) or c not in codes]
    values, invalid, negative, above = {}, [], [], []
    for row in rows:
        if not isinstance(row, dict):
            continue
        code, raw = row.get('sector_code'), row.get('weight')
        if code not in codes or counts[code] != 1:
            continue
        if not number(raw):
            invalid.append(code)
            continue
        values[code] = Fraction(raw)
        if raw < 0:
            negative.append(code)
        if raw > 1:
            above.append(code)
    complete = len(rows) == len(codes) and not missing and not duplicates and not unknown and not invalid
    total = sum(values.values(), Fraction(0)) if len(values) == len(codes) else None
    residual = total - 1 if total is not None else None
    valid = bool(complete and not negative and not above and residual is not None and abs(residual) <= Fraction(tolerance))
    return {'valid': valid, 'complete': complete, 'missing_codes': missing,
            'duplicate_codes': duplicates, 'unknown_codes': unknown,
            'invalid_numbers': invalid, 'negative_codes': negative, 'above_one_codes': above,
            'values': values, 'sum': total, 'residual': residual}


def public_arithmetic(result):
    return {key: ({c: exact_text(v) for c, v in value.items()} if key == 'values'
                  else exact_text(value) if key in ('sum', 'residual') else value)
            for key, value in result.items()}


def constraint_checks(proposal, values, codes, visible_ids):
    findings, seen = [], set()
    constraints = proposal.get('submitted_constraints')
    if not isinstance(constraints, list):
        return [{'valid': False, 'reason': 'constraints_not_array'}]
    for item in constraints:
        if not isinstance(item, dict):
            findings.append({'valid': False, 'reason': 'constraint_not_object'})
            continue
        identifier, code = item.get('constraint_id'), item.get('sector_code')
        kind, bound, evidence = item.get('kind'), item.get('bound'), item.get('evidence_ids')
        valid_shape = (isinstance(identifier, str) and bool(identifier) and identifier not in seen
                       and code in codes and kind in ('sector_min_weight', 'sector_max_weight')
                       and number(bound) and 0 <= bound <= 1
                       and isinstance(evidence, list) and bool(evidence)
                       and all(isinstance(e, str) and e in visible_ids for e in evidence))
        if not valid_shape or code not in values:
            findings.append({'constraint_id': identifier, 'valid': False, 'reason': 'invalid_or_unevaluable_constraint'})
            continue
        seen.add(identifier)
        violation = max(Fraction(0), values[code] - Fraction(bound) if kind == 'sector_max_weight' else Fraction(bound) - values[code])
        findings.append({'constraint_id': identifier, 'sector_code': code, 'kind': kind,
                         'valid': violation == 0, 'exact_violation': exact_text(violation)})
    return findings


def build(run_dir):
    run_dir = Path(run_dir).resolve()
    observed_files = {}
    def read(path, decimal=False):
        path = Path(path).resolve()
        raw = path.read_bytes()
        observed_files[path] = hashlib.sha256(raw).hexdigest()
        text = raw.decode('utf-8-sig')
        return strict_json(text) if decimal else json.loads(text)
    summary = read(run_dir / 'summary.json')
    if not summary.get('finished_at_utc') or summary.get('status') in ('not_started', 'running', 'attempted'):
        raise ValueError('Terminal settled summary is required; no premature PASS report')
    spec = read(SPEC, decimal=True)
    read(RUBRIC)
    codes = list(spec['taxonomy']['codes_and_names'])
    tolerance = spec['engineering_checks']['sum_tolerance']
    manifest = read(run_dir / 'manifest_snapshot.json')
    invocation = read(run_dir / 'invocation.json')
    prepared = Path(invocation['manifest']['path']).parent
    read(prepared / 'manifest.json')
    schema = read(prepared / 'response_schema.json', decimal=True)
    old_response = read(prepared / 'prior_response.json')
    old_record = read(prepared / 'prior_record.json', decimal=True)
    old = strict_json(old_response['message']['content'])
    old_math = arithmetic(old['weights'], codes, tolerance)
    original_stage4 = ROOT / 'data/local_sector_runtime/single_case_v45_20261018/fidelity_q2_2026__R1/stage4_record.json'
    original = read(original_stage4, decimal=True)
    original_response = read(original_stage4.with_name('stage4_response.json'))
    checks = []
    def check(identifier, passed, detail):
        checks.append({'id': identifier, 'status': 'not_observed' if passed is None else 'pass' if passed else 'fail', 'detail': detail})
    check('P1-R2-01', old == old_record['raw_proposal'] == original['raw_proposal'] and
          old_response['message']['content'] == original_response['message']['content'],
          'Predecessor content and exact decimal values agree with immutable v4.5 sources.')
    check('P1-R2-02', old_math['sum'] == Fraction(965, 1000) and old_math['residual'] == Fraction(-35, 1000)
          and not old_math['valid'] and old_record['calculator_result'] == original['calculator_result'],
          'Independently verified original sum0.965, residual-0.035 and invalidity; original calculator values unchanged.')
    check('P1-R2-03', summary.get('diagnostic_generation_calls') == 1 and summary.get('automatic_retries') == 0
          and summary.get('four_stage_pilot_calls') == 0 and summary.get('main_model_calls') == 0,
          'Recorded scope is one diagnostic call with no automatic retry, new four-stage pilot or main call.')
    response_path = run_dir / 'revision_transport/http_0001_generation/response.json'
    record_path = run_dir / 'revision_record.json'
    final_math, deltas, constraints, error = None, None, None, None
    completed = summary.get('status') == 'completed_one_diagnostic' and record_path.is_file() and response_path.is_file()
    check('P1-R2-04', completed, 'Complete terminal revision and original response are required for correction acceptance.')
    if completed:
        response = read(response_path)
        record = read(record_path, decimal=True)
        try:
            proposal = strict_json(response['message']['content'])
            errors = structural_errors(proposal, schema)
            check('P1-R2-05', response.get('done') is True and response.get('done_reason') == 'stop' and not errors,
                  {'meaning': 'Independent strict JSON/schema validation; no prefix repair.', 'structure_errors': errors})
            check('P1-R2-06', proposal == record['raw_proposal'] and
                  record['calculator_arguments']['weights'] == proposal['weights'] and
                  record['calculator_arguments']['submitted_constraints'] == proposal['submitted_constraints'],
                  'Calculator arguments and record equal literal raw model output; no host weight change.')
            final_math = arithmetic(proposal.get('weights'), codes, tolerance)
            check('P1-R2-07', final_math.get('complete') is True,
                  'Exactly eleven canonical public sector codes, once each, with finite numeric raw weights.')
            check('P1-R2-08', not final_math.get('negative_codes') and not final_math.get('above_one_codes') and final_math.get('complete') is True,
                  'Every model-authored weight satisfies the original long-only0..1 bounds.')
            check('P1-R2-09', final_math['valid'],
                  {'meaning': 'Exact raw sum satisfies the inherited engineering tolerance.',
                   'exact_sum': exact_text(final_math.get('sum')), 'exact_residual': exact_text(final_math.get('residual')),
                   'tolerance': str(tolerance), 'tolerance_basis': 'Existing serialization precision only; no new effect threshold.'})
            calc = record['calculator_result']
            if len(final_math['values']) == len(codes):
                float_sum = math.fsum(float(final_math['values'][c]) for c in codes)
                calc_agrees = (calc['allocation']['valid'] is final_math['valid'] and
                               float(calc['allocation']['raw_sum']) == float_sum and
                               float(calc['allocation']['raw_budget_residual']) == float_sum - 1)
                deltas = {c: final_math['values'][c] - old_math['values'][c] for c in codes}
            else:
                float_sum, calc_agrees = None, calc['allocation']['valid'] is False
            check('P1-R2-10', calc_agrees,
                  {'meaning': 'Exact independent validity and separately recomputed binary-float sums match recorded calculator.', 'binary_float_sum': float_sum})
            visible = set(original['visible_evidence_ids'])
            constraints = constraint_checks(proposal, final_math['values'], codes, visible)
            constraints_ok = all(c['valid'] for c in constraints)
            check('P1-R2-11', constraints_ok,
                  {'meaning': 'All submitted numerical constraints are well-formed/evaluable/satisfied. IDs available in public packet are not proof of source entailment.', 'checks': constraints})
            changed = deltas is not None and any(deltas.values())
            check('P1-R2-12', changed and sum(deltas.values(), Fraction(0)) == final_math['sum'] - old_math['sum'],
                  'An actual raw vector change occurs; exact total change equals new sum minus0.965. No minimum sector delta or target sector is prescribed.')
            check('P1-R2-13', record['repair_applied'] is False and calc['repaired'] is False
                  and calc['allocation']['normalized_or_repaired'] is False,
                  'Recorded host repair flags are false; output/argument identity is independently checked above. Full execution provenance belongs to round1.')
            expected_acceptance = final_math['valid'] and constraints_ok and calc['market_diagnostics']['status'] != 'invalid_market'
            check('P1-R2-14', summary.get('numeric_acceptance') is expected_acceptance and
                  record['assessment']['numeric_acceptance'] is expected_acceptance and expected_acceptance,
                  'Independent numeric acceptance agrees with record and summary, and is true. This does not imply semantic acceptance.')
        except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
            error = f'{type(exc).__name__}: {exc}'
            check('P1-R2-PARSE', False, 'No repair was attempted: ' + error)
    for identifier in [f'P1-R2-{n:02d}' for n in range(5, 15)]:
        if not any(c['id'] == identifier for c in checks):
            check(identifier, None, 'Required complete raw data unavailable or strict parsing/structure failed; not scored as passing.')
    check('P1-R2-15', summary.get('priority1_solved') is False and summary.get('human_semantic_pass') is False,
          'Runner did not self-authorize the three-review gate or independent human approval.')
    observed_files[Path(__file__).resolve()] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for path, digest in observed_files.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Audit input changed during review: ' + str(path))
    source_files = [{'path': p.relative_to(ROOT).as_posix(), 'sha256': digest}
                    for p, digest in sorted(observed_files.items(), key=lambda item: str(item[0]))]
    report = {
        'schema_version': 'v46_priority1_independent_arithmetic_round2_v1',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'phase': 'priority1', 'round': 2, 'run_dir': run_dir.relative_to(ROOT).as_posix(),
        'audit_completed': True, 'all_passed': all(c['status'] == 'pass' for c in checks),
        'scope': 'Independent raw arithmetic and existing format contract for one known-failure development correction only.',
        'failed_checks': [c['id'] for c in checks if c['status'] == 'fail'],
        'not_observed_checks': [c['id'] for c in checks if c['status'] == 'not_observed'],
        'check_count': len(checks), 'checks': checks, 'source_files': source_files,
        'prior': public_arithmetic(old_math),
        'revised': public_arithmetic(final_math) if final_math else None,
        'exact_weight_changes': {c: exact_text(v) for c, v in deltas.items()} if deltas else None,
        'exact_total_weight_change': exact_text(sum(deltas.values(), Fraction(0))) if deltas else None,
        'schema_or_parse_error': error,
        'decision_scope': 'This audit alone never sets priority1 accepted. Round1 provenance and round3 correction-claim truth must also pass for the same settled summary and revision record.',
        'not_claimed': ['Optimal or source-exact weights', 'Source rationale quality', 'Historical market-number accuracy',
                        'Four-stage workflow repair', 'R1/R4 causal effect', 'General model reliability', 'Main readiness or authorization'],
        'model_calls_by_auditor': 0, 'raw_files_changed': 0, 'main_model_calls': 0,
        'no_normalization_or_cash_imputation': True,
        'independence': 'Fraction arithmetic and schema validation are implemented here without importing the runner, portfolio engine or model client. No hidden labels are used.'}
    return report


def render(report):
    esc = lambda value: html.escape(str(value))
    revised = report['revised'] or {}
    rows = ''.join(f'<tr><td>{esc(c["id"])}</td><td>{esc(c["status"])}</td><td>{esc(c["detail"])}</td></tr>' for c in report['checks'])
    changes = report['exact_weight_changes'] or {}
    weights = ''.join(f'<tr><td>{esc(code)}</td><td>{esc(report["prior"]["values"].get(code))}</td><td>{esc(revised.get("values",{}).get(code))}</td><td>{esc(delta)}</td></tr>' for code, delta in changes.items())
    return f'''<!doctype html><html lang="ko"><meta charset="utf-8"><title>① 독립 산술 검증</title>
<style>body{{font:16px/1.7 system-ui;max-width:1100px;margin:40px auto;padding:0 24px;color:#172331}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{padding:9px;border:1px solid #cbd5df;text-align:left;vertical-align:top}}code{{overflow-wrap:anywhere}}.note{{background:#edf3f7;padding:16px}}</style>
<h1>① 계산 피드백 수정 진단 — 2차 독립 산술 검증</h1>
<p><strong>이 감사 판정: {esc('PASS' if report['all_passed'] else 'PASS 아님')}</strong> · 검사 {report['check_count']}개</p>
<p>원안 합계 <strong>{esc(report['prior']['sum'])}</strong> → 새 원안 합계 <strong>{esc(revised.get('sum','미관측'))}</strong>. 새 잔차 {esc(revised.get('residual','미관측'))}.</p>
<p class="note">모델 원문의 숫자를 그대로 분수로 계산했습니다. 외부 정규화·현금 대입은 없습니다. 이 판정은 별도 개발 진단의 산술 범위이며, 수정 설명의 진실성·배분 근거·원래 4단계 전체의 성공을 승인하지 않습니다. 같은 결과의 1차·3차 검증까지 통과해야 ①의 진행 조건을 충족합니다.</p>
<p>실행 경로: <code>{esc(report['run_dir'])}</code></p>
<h2>원안의 실제 변경</h2><table><thead><tr><th>GICS 코드</th><th>이전</th><th>수정 원안</th><th>변경량</th></tr></thead><tbody>{weights}</tbody></table>
<h2>검증 기록</h2><table><thead><tr><th>ID</th><th>상태</th><th>근거와 범위</th></tr></thead><tbody>{rows}</tbody></table>
<p>실제 모델 호출 0회 · 원본 변경 0개 · 본실험 실행 0회. 상세 원본 경로와 SHA256은 같은 이름의 JSON에 보존했습니다.</p></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output-json', type=Path, required=True)
    args = parser.parse_args()
    report = build(args.run_dir)
    output = args.output_json.resolve(); page = output.with_suffix('.html')
    if output.exists() or page.exists():
        raise FileExistsError('Audit artifacts are new-only; do not overwrite a prior review')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, allow_nan=False, indent=2); stream.write('\n')
    with page.open('x', encoding='utf-8') as stream:
        stream.write(render(report))
    print(json.dumps({'path': str(output), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                      'all_passed': report['all_passed'], 'failed_checks': report['failed_checks'],
                      'not_observed_checks': report['not_observed_checks']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
