"""Offline narrow plan/execution claim audit. No production engine/model call."""
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = 'data/local_sector_runtime/plan_execute_diagnostic_v47_20261018'
OLD = 'data/local_sector_runtime/feedback_diagnostic_v46_20261018'
OUT = ROOT / 'research/v47_priority1_round3_20261018.json'
SOURCES = {}


def blob(path):
    value = (ROOT / path).read_bytes()
    SOURCES[path] = {'path': path, 'sha256': hashlib.sha256(value).hexdigest(), 'size_bytes': len(value)}
    return value


def read(path, decimals=False):
    return json.loads(blob(path), parse_float=Decimal) if decimals else json.loads(blob(path))


def parse(value):
    return json.loads(value, parse_float=Decimal, parse_int=Decimal)


def display(value):
    return str(Decimal(value.numerator) / Decimal(value.denominator))


def main():
    if OUT.exists() or OUT.with_suffix('.html').exists():
        raise SystemExit('Refusing to overwrite settled audit.')
    summary = read(RUN + '/summary.json')
    plan_record = read(RUN + '/plan_record.json', True)
    record = read(RUN + '/revision_record.json', True)
    read(RUN + '/registration_snapshot.json')
    read(RUN + '/manifest_snapshot.json')
    for path in [
        'research/evaluator_only/v47_priority1_planner_executor_prerun_addendum_20261018.json',
        'research/evaluator_only/v47_prerun_typography_note_correction_20261018.json',
        'research/evaluator_only/v47_round3_prepared_scope_20261018.json',
        'research/v47_planner_executor_reference_20261018.json',
        'research/v47_reference_locator_erratum.json',
    ]:
        read(path)
    old_response = read(OLD + '/revision_transport/http_0001_generation/response.json')
    old_record = read(OLD + '/revision_record.json', True)
    old = parse(old_response['message']['content'])
    verify = []

    def check(key, ok, detail):
        verify.append({'id': key, 'status': 'pass' if ok else 'fail', 'detail': detail})
        if not ok:
            raise RuntimeError('Evidence check failed: ' + key)

    check('R3-E01', summary['status'] == 'completed_plan_execute_diagnostic'
          and summary['planner_completed'] and summary['executor_completed'], 'Both roles are terminal and complete.')
    texts, parsed = {}, {}
    for role in ['planner', 'executor']:
        prefix = RUN + '/' + role + '_transport/http_0001_generation/'
        response = read(prefix + 'response.json')
        assembled = read(prefix + 'assembled_text.json')
        events = [json.loads(line) for line in blob(prefix + 'raw_stream.bin').splitlines() if line.strip()]
        reconstructed = ''.join(e.get('message', {}).get('content', '') for e in events)
        texts[role] = response['message']['content']
        parsed[role] = parse(texts[role])
        check('R3-E02-' + role, response['done'] and response['done_reason'] == 'stop'
              and assembled['complete'] and texts[role] == assembled['content'] == reconstructed,
              role + ': raw NDJSON, assembled text and complete response match exactly.')
        target = plan_record if role == 'planner' else record
        check('R3-E03-' + role, parsed[role] == target['raw_proposal']
              and SOURCES[prefix + 'response.json']['sha256'] == target['response_source']['sha256'],
              role + ': record agrees with raw proposal and response hash.')
    plan, final = parsed['planner'], parsed['executor']
    messages = read(RUN + '/executor_transport/logical_messages.json')
    check('R3-E04', messages[5]['role'] == 'assistant' and messages[5]['content'] == texts['planner'],
          'Executor receives the entire unchanged plan text.')
    check('R3-E05', messages[2]['content'] == old_response['message']['content'],
          'Registered predecessor is the preserved complete v46 response.')
    check('R3-E06', plan['weights'] == [] and plan_record['calculator_called'] is False
          and plan_record['financial_acceptance'] is None,
          'Planning-role empty array was not calculated or labeled a portfolio success.')
    check('R3-E07', record['prior_calculator_result'] == old_record['calculator_result'],
          'Historical feedback still matches the actual invalid predecessor.')
    check('R3-E08', record['plan_source']['sha256'] == SOURCES[RUN + '/plan_record.json']['sha256'],
          'Final record refers to the exact preserved plan record.')
    b = {r['sector_code']: Fraction(r['weight']) for r in old['weights']}
    a = {r['sector_code']: Fraction(r['weight']) for r in final['weights']}
    bsum, asum = sum(b.values()), sum(a.values())
    delta = {code: a[code] - b[code] for code in b}
    check('R3-E09', bsum == Fraction(193, 200) and asum == Fraction(39, 40)
          and delta['45'] == Fraction(1, 100) and all(delta[c] == 0 for c in delta if c != '45'),
          'Literal arithmetic:0.965→0.975; only IT changes by0.010.')
    check('R3-E10', summary['diagnostic_generation_calls'] == 2 and summary['automatic_retries'] == 0
          and summary['main_model_calls'] == summary['four_stage_pilot_calls'] == 0,
          'Two diagnostic roles, no retry, no new four-stage workflow and no main call.')
    check('R3-E11', record['repair_applied'] is False and record['calculator_result']['repaired'] is False,
          'No host repair is represented as model correction.')

    # Conditional arithmetic about stated plan numbers is not a submitted plan vector.
    plan_endpoints = bsum + (Fraction('0.40') - b['45']) + (Fraction('0.075') - b['60'])
    plan_deltas = bsum + Fraction('0.003') - Fraction('0.010')
    claims = []

    def claim(key, role, field, quote, category, meaning, evidence, gate=None):
        assert quote in parsed[role][field], (key, quote)
        claims.append({'id': key, 'role': role, 'field': field, 'quote': quote,
                       'category': category, 'status': gate or ('pass' if category == 'supported' else 'fail'),
                       'meaning': meaning, 'evidence': evidence})

    claim('R3-P01', 'planner', 'alternatives', 'The previous allocation failed the sum-to-one constraint (raw sum 0.965).',
          'supported', '이전 원안 오류 인식', '원안 정확 합계0.965는 기존 합계 제약을 충족하지 않는다.')
    claim('R3-P02', 'planner', 'risk_discussion', 'The current plan is a hypothetical arithmetic correction, not a validated allocation.',
          'supported', '계획을 미검증 미래 산출물로 구분', 'weights=[]이고 아직 최종 배분을 제출하지 않았다. 이 문장을 수정 완료 주장으로 해석하지 않는다.')
    claim('R3-P03', 'planner', 'alternatives', 'increasing the weight of Information Technology (45) from 0.37 to 0.40 and reducing Real Estate (60) from 0.085 to 0.075 to close the 0.035 gap.',
          'contradicted', '명시한 두 변경으로 부족분0.035를 채운다는 조건부 산술 주장',
          '제시한 변경은 +0.030-0.010=+0.020이다. 다른 비중을 그대로 두면0.985이며0.015가 남는다. 이는 계획 문장의 조건부 계산이지 제출 벡터의 합계가 아니다.')
    claim('R3-P04', 'planner', 'risk_discussion', 'the proposed adjustment (IT +0.003, RE -0.010)',
          'contradicted', '같은 계획에 적힌 IT 변화량의 내부 불일치',
          '앞에서 제시한0.37→0.40은+0.030이다. +0.003은 그 차이와 다르며 두 서술 중 어느 쪽이 의도였는지 단정하지 않는다.')
    claim('R3-P05', 'planner', 'risk_discussion', 'shifting weight from the largest overweight position (IT) to the largest underweight position (RE)',
          'contradicted', '계획 안의 자금 이동 방향 불일치만 검토',
          'IT→RE라는 방향은 명시한 IT 증가·RE 감소와 반대이다. 이 판정은 기관등급 또는 최대 overweight/underweight의 정답 판정이 아니다.')
    claim('R3-F01', 'executor', 'risk_discussion', 'The previous allocation had a raw sum of 0.965, resulting in a budget residual of -0.035.',
          'supported', '이전 합계·잔차의 정확한 인정', '원안 정확 합계193/200, 잔차-7/200과 일치한다.')
    claim('R3-F02', 'executor', 'risk_discussion', 'increases Information Technology from 0.37 to 0.38',
          'supported', '실제 IT 변경 설명', '제출된 IT 비중은0.37→0.38로+0.010이며 실제 변경이 있다.')
    claim('R3-F03', 'executor', 'risk_discussion', 'Real Estate from 0.085 to 0.085 (no change in this specific revision step',
          'supported', 'RE가 그대로라는 명시적 괄호 설명', '문장 앞의 reduces는 부정확하지만 값과 바로 뒤 no change가 실제 변화0을 명시한다. 이 부분을 RE 감소 완료로 단정해 추가 실패시키지 않는다.')
    claim('R3-F04', 'executor', 'risk_discussion', 'This revision adjusts the weights to ensure the portfolio sums to exactly 1.0.',
          'contradicted', '최종 합계1 달성 주장', '실제 합계는39/40=0.975, 잔차는-1/40=-0.025이다. 허용오차1e-6을 넘는다.')
    claim('R3-F05', 'executor', 'risk_discussion', 'the total sum is corrected by re-calculating the largest sector weight to absorb the residual',
          'contradicted', 'IT 변경이 부족분 전체를 흡수했다는 주장', '실제 순증0.010은 원래 부족분0.035의 일부일 뿐이다. 잔여0.025를 수정했다고 볼 수 없다.')
    claim('R3-F06', 'executor', 'risk_discussion', 'the weight of Information Technology (45) is set to 0.38, which brings the total to 1.0.',
          'contradicted', '구체적인 새 IT 값이 총합1을 만든다는 주장', 'IT0.38이라는 값 자체는 맞지만 다른 제출 비중과 더한 합계는0.975이다.')
    failed = [c['id'] for c in claims if c['status'] == 'fail']
    data = {
        'schema_version': 'libera_v47_priority1_round3_1.0',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'phase': 'priority1', 'round': 3, 'run_dir': RUN,
        'audit_completed': True, 'all_passed': False, 'failed_checks': failed, 'not_observed_checks': [],
        'status': 'completed_audit_failed_plan_and_correction_claim_logic',
        'scope': 'Narrow historical-error, prospective-plan, actual-execution and final correction-claim truth only.',
        'checks': verify + claims,
        'check_count': {'evidence_pass': len(verify), 'claim_pass': sum(c['status']=='pass' for c in claims), 'claim_fail': len(failed)},
        'claim_classification_is_explicit_reviewer_assessment': True,
        'planning_status': {'allocation_submitted': False, 'weights': [], 'allocation_sum': None,
                            'financial_acceptance': None, 'full11vector_in_prose_observed': False,
                            'future_plan_not_completed_action': True},
        'arithmetic': {
            'method': 'Fraction from Decimal-parsed original numeric literals; no production calculator import.',
            'prior_sum_exact': display(bsum), 'final_sum_exact': display(asum),
            'prior_residual_exact': display(bsum-1), 'final_residual_exact': display(asum-1),
            'final_sum_fraction': str(asum), 'final_residual_fraction': str(asum-1),
            'changed_sector_codes': [c for c in delta if delta[c]],
            'sector_deltas': [{'sector_code': c, 'prior': display(b[c]), 'final': display(a[c]), 'delta': display(delta[c])} for c in b],
            'valid_raw_final_allocation': False, 'existing_sum_tolerance': '0.000001',
            'tolerance_role': 'Inherited numerical serialization tolerance, not new paper behavioral criterion.',
            'risk_assessed': False,
        },
        'plan_to_execution': {
            'planned_endpoints_in_alternatives': {'45': '0.40', '60': '0.075'},
            'planned_changes_in_risk_discussion': {'45': '+0.003', '60': '-0.010'},
            'actual_final': {'45': '0.38', '60': '0.085'},
            'actual_changes': {'45': '+0.010', '60': '0'},
            'conditional_sum_if_only_stated_endpoints_used': display(plan_endpoints),
            'conditional_sum_if_only_stated_deltas_used': display(plan_deltas),
            'conditional_sums_are_not_submitted_portfolios': True,
            'interpretation': 'Executor does not carry out either quantitative plan as stated. No unregistered equality-to-plan requirement is imposed: this deviation is recorded, while final raw invalidity and false corrected-sum claims establish failure independently.',
        },
        'verbatim_scoped_fields': {
            'planner_alternatives': plan['alternatives'], 'planner_risk_discussion': plan['risk_discussion'],
            'planner_unresolved': plan['unresolved'], 'executor_risk_discussion': final['risk_discussion'],
            'executor_unresolved': final['unresolved'],
        },
        'not_stated_or_uncertain': [
            'No explicit claim of full four-stage replay success, host-applied repair or optimal final allocation was identified.',
            'Unresolved risk/optimality caveats do not retract the explicit incorrect corrected-sum assertions.',
            'The model-internal reason for changing only IT by0.010 is not observed and is not inferred.',
        ],
        'excluded_scopes': [
            'Priority2 market values, historical volatility and general per-sector benchmark/weight explanations.',
            'Priority3 institutional-label/rationale fidelity, alternative quality and claimed preservation of institutional preferences.',
            'Future performance, optimality or general ability; no strategy composite score is assigned.'
        ],
        'conclusion': 'Actual numerical movement is observed, but the shortage remains and the corrected-sum claims are false. Priority1 remains unresolved. Priorities2/3 and main execution do not follow.',
        'counts': {'diagnostic_generation_calls': 2, 'new_four_stage_pilot_calls': 0, 'main_calls': 0, 'model_calls_by_reviewer': 0},
        'main_freeze': False, 'human_review_completed': False, 'previous_files_modified': False,
        'source_files': list(SOURCES.values()),
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    rows = ''.join('<tr><td>'+html.escape(c['id'])+'<br>'+c['status']+'</td><td><q>'+html.escape(c['quote'])+'</q></td><td>'+html.escape(c['evidence'])+'</td></tr>' for c in claims)
    markup = '''<!doctype html><html lang="ko"><meta charset="utf-8"><title>①B 계획·실행 3차 감사</title><style>body{max-width:1100px;margin:36px auto;padding:0 20px;font:16px/1.65 system-ui;color:#17293b}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd2da;padding:10px;vertical-align:top}.result{padding:16px;background:#fff2ed;border-left:5px solid #b44230}q{overflow-wrap:anywhere}</style><main><h1>①B 계획 후 실행: 3차 설명 감사</h1><p class="result"><b>감사 완료, 수정 주장 검토 불합격입니다.</b> 이번에는 IT 비중이37%에서38%로 실제 바뀌었습니다. 그러나 합계는96.5%→97.5%로 올라갔을 뿐, 여전히2.5%p가 부족합니다. 모델이 합계를100%로 고쳤다고 반복한 설명은 제출값과 다릅니다.</p><p>계획의 빈 weights는 의도된 미제출 상태입니다. 계획은 IT40%·부동산7.5%를 제시했지만 이 두 변경만으로도 합계는98.5%입니다. 실제 실행은 IT38%·부동산8.5%를 제출했습니다. 계획대로 실행해야 한다는 새 조건을 추가한 것이 아니라, 계획·실제 변경·수정 주장을 구분하여 대조했습니다.</p><table><tr><th>항목</th><th>원문</th><th>대조 결과</th></tr>''' + rows + '''</table><p>계획 문장의 IT+0.003은 앞의37%→40%와도 다릅니다. 자금 이동 방향의 상반된 서술도 기록했습니다. 반면 실행 응답의 부동산 값은8.5%→8.5%이고 바로 뒤에 변화가 없다고 명시해, 그 부분을 감소 완료라고 단정하지 않았습니다.</p><p>이번 범위는 이전 오류·변경 계획·실제 수정·합계 주장의 진실성입니다. 기관 근거·전략품질·시장수치 전반은 아직 판정하지 않았습니다. 실패 이유나 내부 추론은 단정하지 않습니다. 개발 진단2회, 본실험0회이며①이 미해결이므로②·③로 넘어가지 않습니다.</p><p><a href="v47_priority1_round3_20261018.json">전체 판정·정확 산술·동일 원본 해시 JSON</a></p></main></html>'''
    OUT.with_suffix('.html').write_text(markup, encoding='utf-8')
    print(json.dumps({'path': OUT.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(OUT.read_bytes()).hexdigest(),
                      'all_passed': False, 'source_count': len(SOURCES), 'failed_checks': failed}, indent=2))


if __name__ == '__main__':
    main()
