"""Offline exact arithmetic for the bounded v4.7 planner/executor diagnostic.

Planner empty weights mean no allocation submitted. Only executor weights are
tested for financial feasibility. No model/client/portfolio-engine imports.
"""
from datetime import datetime, timezone
from fractions import Fraction
import argparse
import hashlib
import json
import math
from pathlib import Path

import build_v46_priority1_round2_audit as independent

ROOT = Path(__file__).resolve().parents[1]


def planning_contract(proposal, record, schema):
    errors = independent.structural_errors(proposal, schema)
    empty = isinstance(proposal, dict) and proposal.get('weights') == []
    return {'structure_errors': errors, 'empty_weights': empty,
            'no_portfolio_calculation': record.get('calculator_called') is False,
            'financial_acceptance_unassigned': record.get('financial_acceptance') is None,
            'reported_role_valid': record.get('planner_contract_satisfied') is True,
            'valid': not errors and empty and record.get('calculator_called') is False
                     and record.get('financial_acceptance') is None
                     and record.get('planner_contract_satisfied') is True}


def build(run_dir):
    run_dir = Path(run_dir).resolve()
    files, checks = {}, []
    def read(path, decimal=False):
        path = Path(path).resolve(); raw = path.read_bytes()
        files[path] = hashlib.sha256(raw).hexdigest()
        return independent.strict_json(raw.decode('utf-8-sig')) if decimal else json.loads(raw.decode('utf-8-sig'))
    def check(identifier, passed, detail):
        checks.append({'id': identifier, 'status': 'not_observed' if passed is None else 'pass' if passed else 'fail', 'detail': detail})
    summary = read(run_dir / 'summary.json')
    if not summary.get('finished_at_utc') or summary.get('status') in ('not_started', 'attempted', 'running'):
        raise ValueError('A terminal settled summary is required')
    invocation = read(run_dir / 'invocation.json')
    prepared = Path(invocation['manifest']['path']).parent
    read(run_dir / 'manifest_snapshot.json'); read(prepared / 'manifest.json')
    schema_plan = read(prepared / 'schema_planner.json', True)
    schema_final = read(prepared / 'schema_executor.json', True)
    spec = read(ROOT / 'data/sector_protocol/evaluation_spec.json', True)
    codes = list(spec['taxonomy']['codes_and_names'])
    tolerance = spec['engineering_checks']['sum_tolerance']
    for name in ('v47_priority1_planner_executor_prerun_addendum_20261018.json',
                 'v47_prerun_typography_note_correction_20261018.json'):
        read(ROOT / 'research/evaluator_only' / name)
    v45_dir = ROOT / 'data/local_sector_runtime/single_case_v45_20261018/fidelity_q2_2026__R1'
    v46_dir = ROOT / 'data/local_sector_runtime/feedback_diagnostic_v46_20261018'
    v45_record = read(v45_dir / 'stage4_record.json', True)
    v45_response = read(v45_dir / 'stage4_response.json')
    v46_record = read(v46_dir / 'revision_record.json', True)
    v46_response = read(v46_dir / 'revision_transport/http_0001_generation/response.json')
    old_record = read(prepared / 'prior_record.json', True)
    old_response = read(prepared / 'prior_response.json')
    old = independent.strict_json(old_response['message']['content'])
    old_math = independent.arithmetic(old['weights'], codes, tolerance)
    earlier = independent.strict_json(v45_response['message']['content'])
    earlier_math = independent.arithmetic(earlier['weights'], codes, tolerance)
    transition = read(prepared / 'prior_delta_feedback.json', True)
    check('P1B-R2-01', old == old_record['raw_proposal'] == v46_record['raw_proposal'] and
          old_response['message']['content'] == v46_response['message']['content'],
          'Frozen v4.6 predecessor text/decimal values match the original raw response and record.')
    check('P1B-R2-02', not old_math['valid'] and old_math['sum'] == Fraction(965, 1000)
          and old_math['residual'] == Fraction(-35, 1000),
          'Independently confirmed invalid predecessor sum0.965 and residual-0.035.')
    transition_rows = transition.get('rows', [])
    transition_codes = [r.get('sector_code') for r in transition_rows]
    transition_ok = len(transition_rows) == len(codes) and set(transition_codes) == set(codes)
    if transition_ok:
        for row in transition_rows:
            code = row['sector_code']
            transition_ok = transition_ok and (
                Fraction(row['old_weight']) == earlier_math['values'][code] and
                Fraction(row['new_weight']) == old_math['values'][code] and
                Fraction(row['delta']) == old_math['values'][code] - earlier_math['values'][code] == 0)
        transition_ok = (transition_ok
            and Fraction(transition['old_raw_sum']) == earlier_math['sum'] == Fraction(transition['new_raw_sum']) == old_math['sum']
            and transition['old_raw_budget_residual'] == v45_record['calculator_result']['allocation']['raw_budget_residual']
            and transition['new_raw_budget_residual'] == v46_record['calculator_result']['allocation']['raw_budget_residual'])
    check('P1B-R2-03', transition_ok, 'Every visible v4.5-to-v4.6 delta is independently0; both original sums match. No corrected vector is used.')
    check('P1B-R2-04', summary.get('diagnostic_generation_calls') == 2 and summary.get('automatic_retries') == 0
          and summary.get('four_stage_pilot_calls') == 0 and summary.get('main_model_calls') == 0,
          'Success requires the registered one planner plus one executor, no retry and no new four-stage/main calls; fewer calls remain a stopped diagnostic.')
    plan, plan_contract, final_math, deltas, constraints = None, None, None, None, None
    plan_path = run_dir / 'plan_record.json'
    plan_response_path = run_dir / 'planner_transport/http_0001_generation/response.json'
    if plan_path.is_file() and plan_response_path.is_file():
        plan_record = read(plan_path, True); plan_response = read(plan_response_path)
        try:
            plan = independent.strict_json(plan_response['message']['content'])
            plan_contract = planning_contract(plan, plan_record, schema_plan)
            check('P1B-R2-05', plan_response.get('done') is True and plan_response.get('done_reason') == 'stop'
                  and not plan_contract['structure_errors'],
                  {'meaning': 'Complete planner response independently passes existing strict shape.', 'structure_errors': plan_contract['structure_errors']})
            check('P1B-R2-06', plan == plan_record['raw_proposal'] and plan_contract['empty_weights'],
                  'Planner raw weights are exactly[] and preserved; no allocation is inferred from prose or a zero-vector replacement.')
            check('P1B-R2-07', plan_contract['valid'] and plan_record.get('repair_applied') is False,
                  'Plan is explicitly not submitted: no calculator call and financial_acceptance=null. No planning sum or valid-portfolio flag is assigned.')
        except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
            check('P1B-R2-PLAN', False, f'No planner text repair: {type(exc).__name__}: {exc}')
    record_path = run_dir / 'revision_record.json'
    response_path = run_dir / 'executor_transport/http_0001_generation/response.json'
    complete = summary.get('status') == 'completed_plan_execute_diagnostic' and record_path.is_file() and response_path.is_file()
    check('P1B-R2-08', complete, 'A completed original executor response and revision record are required; a plan alone cannot pass.')
    if complete:
        record = read(record_path, True); response = read(response_path)
        try:
            proposal = independent.strict_json(response['message']['content'])
            errors = independent.structural_errors(proposal, schema_final)
            check('P1B-R2-09', response.get('done') is True and response.get('done_reason') == 'stop' and not errors,
                  {'meaning': 'Executor raw JSON passes independent parsing and existing final schema.', 'structure_errors': errors})
            check('P1B-R2-10', proposal == record['raw_proposal'] and record['calculator_arguments']['weights'] == proposal['weights']
                  and record['calculator_arguments']['submitted_constraints'] == proposal['submitted_constraints'],
                  'Model-written raw proposal, stored proposal and calculator arguments are identical.')
            final_math = independent.arithmetic(proposal.get('weights'), codes, tolerance)
            check('P1B-R2-11', final_math.get('complete') is True, 'All11 public sector codes occur once with finite numeric weights.')
            check('P1B-R2-12', final_math.get('complete') is True and not final_math.get('negative_codes') and not final_math.get('above_one_codes'),
                  'Original long-only0..1 bounds hold without repair.')
            check('P1B-R2-13', final_math['valid'], {'meaning': 'Exact final raw arithmetic satisfies the inherited sum rule.',
                  'sum': independent.exact_text(final_math.get('sum')), 'residual': independent.exact_text(final_math.get('residual')),
                  'sum_tolerance': str(tolerance), 'tolerance_role': 'Existing engineering serialization precision only.'})
            calc = record['calculator_result']
            if len(final_math['values']) == len(codes):
                float_sum = math.fsum(float(final_math['values'][c]) for c in codes)
                agrees = calc['allocation']['valid'] is final_math['valid'] and float(calc['allocation']['raw_sum']) == float_sum and float(calc['allocation']['raw_budget_residual']) == float_sum - 1
                deltas = {c: final_math['values'][c] - old_math['values'][c] for c in codes}
            else:
                float_sum, agrees = None, calc['allocation']['valid'] is False
            check('P1B-R2-14', agrees, {'meaning': 'Independent exact validity and separately recomputed float arithmetic agree with recorded calculator.', 'float_sum': float_sum})
            constraints = independent.constraint_checks(proposal, final_math['values'], codes, set(v45_record['visible_evidence_ids']))
            constraints_ok = all(row['valid'] for row in constraints)
            check('P1B-R2-15', constraints_ok, {'meaning': 'Submitted numerical bounds are valid/evaluable/satisfied; source entailment is not inferred from an ID.', 'checks': constraints})
            changed = deltas is not None and any(deltas.values())
            check('P1B-R2-16', changed and sum(deltas.values(), Fraction(0)) == final_math['sum'] - old_math['sum'],
                  'Actual executor vector changes from v4.6; exact delta sum equals new sum minus old sum. Planning text itself is not a change.')
            check('P1B-R2-17', record['repair_applied'] is False and calc['repaired'] is False and calc['allocation']['normalized_or_repaired'] is False,
                  'No repair is recorded and raw/argument identity is checked; full provenance remains round1.')
            expected = final_math['valid'] and constraints_ok and calc['market_diagnostics']['status'] != 'invalid_market'
            check('P1B-R2-18', expected and summary.get('numeric_acceptance') is expected and record['assessment']['numeric_acceptance'] is expected,
                  'Independent numeric acceptance agrees with both stored flags and is true; no semantic inference follows.')
        except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
            check('P1B-R2-FINAL', False, f'No executor text repair: {type(exc).__name__}: {exc}')
    for n in list(range(5, 8)) + list(range(9, 19)):
        identifier = f'P1B-R2-{n:02d}'
        if not any(c['id'] == identifier for c in checks):
            check(identifier, None, 'Required complete role output unavailable or strict parsing failed; not a passing empty set.')
    check('P1B-R2-19', summary.get('priority1_solved') is False and summary.get('human_semantic_pass') is False,
          'Runner did not self-approve the user-required three-audit gate or human review.')
    for path in (Path(__file__).resolve(), Path(independent.__file__).resolve()):
        files[path] = hashlib.sha256(path.read_bytes()).hexdigest()
    for path, digest in files.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Artifact changed during audit: ' + str(path))
    return {
        'schema_version': 'v47_priority1_plan_execute_independent_arithmetic_round2_v1',
        'created_at_utc': datetime.now(timezone.utc).isoformat(), 'phase': 'priority1', 'round': 2,
        'run_dir': run_dir.relative_to(ROOT).as_posix(), 'audit_completed': True,
        'all_passed': all(c['status'] == 'pass' for c in checks),
        'scope': 'Independent raw arithmetic and role-specific format for one planner/executor development diagnostic; no main or original four-stage success claim.',
        'failed_checks': [c['id'] for c in checks if c['status'] == 'fail'],
        'not_observed_checks': [c['id'] for c in checks if c['status'] == 'not_observed'],
        'checks': checks, 'check_count': len(checks),
        'source_files': [{'path': p.relative_to(ROOT).as_posix(), 'sha256': digest} for p, digest in sorted(files.items(), key=lambda item: str(item[0]))],
        'prior': independent.public_arithmetic(old_math),
        'planner': {'contract': plan_contract, 'allocation_submitted': False if plan_contract and plan_contract['empty_weights'] else None,
                    'allocation_sum': None, 'financial_validity': None, 'meaning': 'Intentional empty planning weights are not a zero vector or successful portfolio.'},
        'revised': independent.public_arithmetic(final_math) if final_math else None,
        'exact_weight_changes': {c: independent.exact_text(v) for c, v in deltas.items()} if deltas else None,
        'exact_total_weight_change': independent.exact_text(sum(deltas.values(), Fraction(0))) if deltas else None,
        'no_normalization_or_cash_imputation': True, 'model_calls_by_auditor': 0, 'raw_files_changed': 0,
        'main_model_calls': 0, 'priority1_gate_decided_here': False,
        'limits': ['Planner future intentions are not actual execution.', 'Only executor is a new submitted allocation.',
                   'Source reasons and market-number truth are reserved for later priorities.',
                   'Two calls/three audits are not independent samples or the original four-stage workflow.',
                   'One same-case development result cannot establish causal improvement or general reliability.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output-json', type=Path, required=True)
    args = parser.parse_args(); report = build(args.run_dir)
    output = args.output_json.resolve(); page = output.with_suffix('.html')
    if output.exists() or page.exists():
        raise FileExistsError('Audit artifacts must be new; existing records are immutable')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, allow_nan=False, indent=2); stream.write('\n')
    text = independent.render(report).replace('① 계산 피드백 수정 진단 — 2차 독립 산술 검증', '①B 계획·실행 분리 진단 — 2차 독립 산술 검증')
    note = '<p class="note">계획 단계의 weights=[]는 배분 미제출이며 합계·금융 유효성은 평가하지 않습니다. 아래 비중과 수정 판정은 실행 단계의 최종 원안에만 해당합니다.</p>'
    text = text.replace('<h2>원안의 실제 변경</h2>', note + '<h2>원안의 실제 변경</h2>')
    with page.open('x', encoding='utf-8') as stream:
        stream.write(text)
    print(json.dumps({'path': str(output), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                      'all_passed': report['all_passed'], 'failed_checks': report['failed_checks'],
                      'not_observed_checks': report['not_observed_checks']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
