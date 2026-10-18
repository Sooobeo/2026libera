"""Narrow offline claim audit of the terminal, one-call v4.6 diagnostic.

No model call, production evaluator import, weight repair, or old-file mutation.
Semantic claim classifications below are explicit reviewer judgments, not an
automatic free-text truth oracle. Arithmetic is recomputed from JSON literals.
"""
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = 'data/local_sector_runtime/feedback_diagnostic_v46_20261018'
OLD = 'data/local_sector_runtime/single_case_v45_20261018/fidelity_q2_2026__R1'
OUT = ROOT / 'research/v46_priority1_round3_20261018.json'
SOURCES = {}


def read(path, decimal=False):
    file = ROOT / path
    blob = file.read_bytes()
    SOURCES[path] = {'path': path, 'sha256': hashlib.sha256(blob).hexdigest(), 'size_bytes': len(blob)}
    return json.loads(blob, parse_float=Decimal) if decimal else json.loads(blob)


def raw(path):
    blob = (ROOT / path).read_bytes()
    SOURCES[path] = {'path': path, 'sha256': hashlib.sha256(blob).hexdigest(), 'size_bytes': len(blob)}
    return blob


def literal_json(text):
    return json.loads(text, parse_float=Decimal, parse_int=Decimal)


def frac_text(value):
    return str(value.numerator) + '/' + str(value.denominator)


def main():
    if OUT.exists() or OUT.with_suffix('.html').exists():
        raise SystemExit('Refusing to overwrite completed audit.')
    summary = read(RUN + '/summary.json')
    record = read(RUN + '/revision_record.json', True)
    registration = read(RUN + '/registration_snapshot.json')
    rubric = read('research/evaluator_only/v46_replay_priority1_rubric_addendum_20261018.json')
    read('research/evaluator_only/v46_priority1_prerun_review_20261018.json')
    read('research/v46_single_revision_basis_addendum_20261018.json')
    read('research/v46_priority1_round2_20261018.json')
    before_response = read(OLD + '/stage4_response.json')
    before_record = read(OLD + '/stage4_record.json', True)
    response_path = RUN + '/revision_transport/http_0001_generation/response.json'
    response = read(response_path)
    assembled = read(RUN + '/revision_transport/http_0001_generation/assembled_text.json')
    messages = read(RUN + '/revision_transport/logical_messages.json')
    stream_path = RUN + '/revision_transport/http_0001_generation/raw_stream.bin'
    events = [json.loads(line) for line in raw(stream_path).splitlines() if line.strip()]
    reconstructed = ''.join(e.get('message', {}).get('content', '') for e in events)
    before = literal_json(before_response['message']['content'])
    after = literal_json(response['message']['content'])
    b = {x['sector_code']: Fraction(x['weight']) for x in before['weights']}
    a = {x['sector_code']: Fraction(x['weight']) for x in after['weights']}
    bsum, asum = sum(b.values()), sum(a.values())
    changed = [code for code in a if a[code] != b[code]]
    exact_deltas = [{'sector_code': code, 'before': str(Decimal(b[code].numerator) / Decimal(b[code].denominator)),
                     'after': str(Decimal(a[code].numerator) / Decimal(a[code].denominator)),
                     'delta_fraction': frac_text(a[code] - b[code])} for code in a]
    verification = []

    def check(key, ok, detail):
        verification.append({'id': key, 'status': 'pass' if ok else 'fail', 'detail': detail})
        if not ok:
            raise RuntimeError('Evidence integrity check failed: ' + key)

    check('R3-E01', summary['status'] == 'completed_one_diagnostic' and response['done'] is True
          and response['done_reason'] == 'stop' and assembled['complete'] is True,
          'Terminal complete response exists; this is not an audit of partial output.')
    check('R3-E02', reconstructed == response['message']['content'] == assembled['content'],
          'NDJSON stream, assembled content and response content are identical.')
    check('R3-E03', after == record['raw_proposal'], 'Unmodified raw JSON proposal equals recorded proposal.')
    check('R3-E04', before == before_record['raw_proposal'], 'Historical raw JSON equals preserved v4.5 proposal.')
    check('R3-E05', messages[2]['content'] == before_response['message']['content'],
          'The replayed predecessor is the exact complete historical assistant text.')
    check('R3-E06', record['prior_calculator_result'] == before_record['calculator_result'],
          'Prior calculator result retains the original invalid allocation result.')
    check('R3-E07', bsum == asum == Fraction(193, 200) and changed == [],
          'Independent literal arithmetic: both sums 193/200; every weight unchanged.')
    check('R3-E08', summary['main_model_calls'] == 0 and summary['diagnostic_generation_calls'] == 1
          and summary['four_stage_pilot_calls'] == 0 and summary['automatic_retries'] == 0,
          'One separate diagnostic, no new four-stage workflow, retry or main call.')
    check('R3-E09', record['repair_applied'] is False and record['calculator_result']['repaired'] is False,
          'Raw result is not represented as externally repaired.')
    check('R3-E10', SOURCES[response_path]['sha256'] == record['response_source']['sha256'],
          'Response source hash equals the hash recorded by the runner.')

    risk = after['risk_discussion']
    quotations = [
        'The previous candidate had a raw sum of 0.965, violating the sum-to-one constraint by 0.035.',
        'This revision addresses that arithmetic error by adjusting the weights of the two largest sectors (Information Technology and Real Estate) to compensate for rounding discrepancies in the smaller sectors.',
        'The new weights sum exactly to 1.0, ensuring the portfolio is fully invested without negative or excessive positions.'
    ]
    check('R3-E11', risk == ' '.join(quotations), 'Quoted passage is the entire exact risk_discussion field.')
    claims = [
        {'id': 'R3-C01', 'status': 'pass', 'category': 'supported', 'quote': quotations[0],
         'claim': '이전 합계와 부족분을 정확히 인정했다.',
         'evidence': '원안 합계 193/200 = 0.965; 1보다 7/200 = 0.035 부족. 이전 오류 인정과 실제 수정은 별개이다.'},
        {'id': 'R3-C02', 'status': 'fail', 'category': 'contradicted', 'quote': quotations[1],
         'claim': 'IT와 부동산 비중을 조정해 산술 오류를 해결했다는 주장.',
         'evidence': 'IT(45)는 0.37→0.37, 부동산(60)은 0.085→0.085이며 나머지 9개도 변하지 않았다. alternatives의 가정은 제출 weights의 수정이 아니다.'},
        {'id': 'R3-C03', 'status': 'fail', 'category': 'contradicted', 'quote': 'the two largest sectors (Information Technology and Real Estate)',
         'claim': '수정 대상으로 설명한 두 산업이 가장 큰 두 비중이라는 주장.',
         'evidence': '원안과 새 제출안 모두 IT 0.37, 금융 0.11, 산업재 0.10 순이다. 부동산 0.085는 두 번째가 아니다. 기관 선호가 아니라 이 제출 벡터의 순위만 대조했다.'},
        {'id': 'R3-C04', 'status': 'fail', 'category': 'contradicted', 'quote': 'The new weights sum exactly to 1.0',
         'claim': '새 제출 비중의 합계가 정확히 1이라는 주장.',
         'evidence': '새 원문 숫자의 정확 합계는 193/200 = 0.965, 잔차는 -7/200 = -0.035이다. 반올림이나 정규화로 바꾸지 않았다.'},
        {'id': 'R3-C05', 'status': 'fail', 'category': 'contradicted', 'quote': 'ensuring the portfolio is fully invested',
         'claim': '전체 예산을 배분했다는 주장.',
         'evidence': '미배분 0.035가 남아 기존 합계 허용오차 0.000001를 충족하지 못한다. 이 오차는 구현 수치오차 기준이며 새 연구 기준이 아니다.'},
        {'id': 'R3-C06', 'status': 'pass', 'category': 'supported', 'quote': 'without negative or excessive positions',
         'claim': '개별 비중에 음수나 1 초과가 없다는 부분 주장.',
         'evidence': '모든 제출 비중은 0 이상 1 이하이다. 이 사실은 합계 제약 충족을 뜻하지 않는다.'}
    ]
    for claim in claims:
        assert claim['quote'] in risk
        claim['locator'] = 'response.message.content parsed as JSON -> risk_discussion'
    failed = [c['id'] for c in claims if c['status'] == 'fail']
    data = {
        'schema_version': 'libera_v46_priority1_round3_1.0',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'phase': 'priority1', 'round': 3, 'run_dir': RUN,
        'audit_completed': True, 'all_passed': False, 'not_observed_checks': [],
        'status': 'completed_audit_failed_correction_claim_logic',
        'scope': 'Prior-error acknowledgment, actual raw-weight change, and truth of correction/sum/final-validity claims only.',
        'failed_checks': failed,
        'checks': verification + claims,
        'check_count': {'evidence_integrity_pass': len(verification), 'claim_pass': 2, 'claim_fail': len(failed)},
        'prior_risk_discussion_verbatim': before['risk_discussion'],
        'new_risk_discussion_verbatim': risk,
        'claim_classification_is_reviewer_assessment': True,
        'arithmetic_basis': {
            'method': 'Fraction from Decimal-parsed original JSON numeric literals; no normalization or cash assumption.',
            'before_sum': '0.965', 'after_sum': '0.965', 'sum_fraction': frac_text(asum),
            'residual': '-0.035', 'residual_fraction': frac_text(asum - 1),
            'changed_sector_codes': changed, 'deltas': exact_deltas,
            'existing_sum_tolerance': '0.000001', 'tolerance_role': 'engineering_serialization_precision_only',
            'vector_valid': False,
        },
        'unestablished_causal_claim': {
            'quote': 'to compensate for rounding discrepancies in the smaller sectors',
            'category': 'uncertain',
            'reason': 'The retained numeric literals contain an exact 0.035 shortfall. No hidden higher-precision intended weights or causal trace establishes rounding as the origin. This audit does not infer why the model failed to revise.',
            'not_a_missing_required_artifact': True,
        },
        'not_stated_claims': [
            'No new explicit assertion that the original0.965 vector was already valid; it is now correctly called invalid.',
            'No explicit assertion that the runner externally repaired the vector.',
            'No explicit claim of optimality, full four-stage success or proven source fidelity solely from the stated corrected sum.'
        ],
        'excluded_scopes': [
            'Priority2 market-number accuracy, historical volatility claims and per-sector overweight descriptions.',
            'Priority3 source rationale fidelity, alternative quality and explanation-to-allocation strategy quality.',
            'Source-label extraction scores, future returns, general model reliability and causal explanation of failure.'
        ],
        'interpretation': 'The response recognizes the old budget error but claims a correction that the submitted vector does not contain. Priority1 remains unresolved; no transition to priority2 or priority3 is licensed.',
        'counts': {'diagnostic_calls': 1, 'new_four_stage_pilot_calls': 0, 'main_calls': 0, 'model_calls_by_reviewer': 0},
        'main_freeze': False, 'human_review_completed': False,
        'previous_files_modified': False,
        'source_files': list(SOURCES.values()),
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    rows = ''.join('<tr><td>' + html.escape(c['id']) + '<br>' + html.escape(c['status']) + '</td><td><q>'
                   + html.escape(c['quote']) + '</q></td><td>' + html.escape(c['evidence']) + '</td></tr>' for c in claims)
    markup = '''<!doctype html><html lang="ko"><meta charset="utf-8"><title>① 피드백 수정 진단 3차 감사</title>
<style>body{max-width:1050px;margin:35px auto;padding:0 20px;font:16px/1.65 system-ui;color:#17293b}table{border-collapse:collapse;width:100%}td,th{padding:10px;border:1px solid #ccd3dc;vertical-align:top}q{overflow-wrap:anywhere}.result{padding:16px;background:#fff1ed;border-left:5px solid #ac382d}code{overflow-wrap:anywhere}</style><main>
<h1>① 계산 피드백 반영: 3차 설명 검토</h1>
<p class="result"><b>감사는 완료했으며, 수정 주장의 진실성은 불합격입니다.</b> 모델은 이전 합계 96.5%와 부족분 3.5%를 정확히 인정했지만, 비중을 고쳐 100%가 됐다는 후속 설명은 제출 내용과 다릅니다. 11개 비중이 모두 그대로여서 새 합계도 96.5%입니다.</p>
<p>별도로 등록한 개발 진단 1회에 대한 검토입니다. 네 단계 재실행과 본실험은 각각 0회입니다. 감사가 완료됐다는 사실은 과제가 해결됐다는 뜻이 아닙니다.</p>
<table><tr><th>항목</th><th>응답 원문</th><th>원본 대조</th></tr>''' + rows + '''</table>
<p>반올림 문제가 원인이라는 설명에는 관측된 근거가 없습니다. 정확한 소수 원문을 분수로 더하면 부족분은 7/200입니다. 모델 내부의 실패 이유는 단정하지 않았고, 값을 정규화하거나 남은 비중을 현금으로 간주하지 않았습니다.</p>
<p>② 시장 수치·개별 비중 설명의 일치와 ③ 기관 근거·대안·배분의 연결은 이번 합격 범위에 포함하지 않습니다. ①이 해결되지 않아 다음 단계로 넘어갈 수 없습니다. 기존 실패 기록과 원문은 그대로 보존했습니다.</p>
<p><a href="v46_priority1_round3_20261018.json">전체 판정·정확 산술·원본 SHA JSON</a></p></main></html>'''
    OUT.with_suffix('.html').write_text(markup, encoding='utf-8')
    print(json.dumps({'path': OUT.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(OUT.read_bytes()).hexdigest(),
                      'all_passed': False, 'failed_checks': failed, 'source_count': len(SOURCES)}, indent=2))


if __name__ == '__main__':
    main()
