"""Write a control-inclusive plan and a consistent full pre-main term-paper draft."""
from datetime import datetime, timezone
import html
import json
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'plan/LIBERA_대조군포함_실험계획_v4.9.2_20261019.html'
PAPER = ROOT / 'paper/LIBERA_텀페이퍼_초안_v4.9.2_20261019.html'

DESIGN = '''<p>같은 모델·시장상황·업무·11개 산업·출력 형식을 사용한다. Fidelity와 UBS 각각에 E(초안부터 기관 자료 제공), L(최종 검토 때 처음 제공)을 적용하고, 기관 자료를 끝까지 제공하지 않는 공통 대조군 C를 추가한다. 따라서 한 자료 묶음의 사례는 5개이며, 각 사례의 초안 D0와 첫 최종안 F0를 합쳐 최대 10번 생성한다. 이 수는 실험 구조에서 정해지며 통계적 검정력을 보장하는 표본 크기가 아니다.</p>
<div class="table-wrap"><table><thead><tr><th>조건</th><th>초안 D0</th><th>계산 검토 후 첫 최종안 F0</th><th>알아보는 것</th></tr></thead><tbody>
<tr><td>Fidelity E · UBS E</td><td>공통상황 + 해당 기관 자료</td><td>자기 초안 + 실제 계산 피드백 + 해당 기관 자료</td><td>처음부터 기관 근거를 받은 배분</td></tr>
<tr><td>Fidelity L · UBS L</td><td>공통상황만</td><td>자기 초안 + 실제 계산 피드백 + 처음 제공되는 해당 기관 자료</td><td>초안을 만든 뒤 기관 근거를 받은 배분</td></tr>
<tr><td>공통 대조군 C</td><td>공통상황만</td><td>자기 초안 + 실제 계산 피드백, 기관 자료 없음</td><td>기관 근거를 받지 않은 동일 AI의 전략 제안</td></tr>
</tbody></table></div>
<p>C도 두 단계를 거치므로, 초안 하나를 다른 조건의 최종안과 비교하지 않는다. L과 C의 초안 입력이 같더라도 별도로 생성하고 각자의 원문을 사용한다. 모든 최종 단계에는 동일한 조건부 지시문을 쓰며, 기관 자료가 제공된 경우에만 해당 견해를 해석하도록 한다. 계산기는 비중을 정하거나 고쳐 주지 않고 실제 초안의 수치와 제약을 검사한다.</p>
<p>C는 하나의 공통 관측치다. 두 기관과 각각 비교한다고 대조군 표본이 두 개가 되지 않는다. C와 E/L의 차이는 기관 문서의 존재와 그에 따른 입력 길이·노출 차이를 포함한다. E와 L은 정보 제공 시점뿐 아니라 초안 이력과 노출 횟수도 달라진다. 따라서 결과를 순수한 기억·앵커링 또는 정보 의미만의 인과효과로 해석하지 않는다.</p>
<p>개발 자료는 Fidelity 2026년 2분기·UBS 6월, 본실험 자료는 미리 선택한 Fidelity 3분기·UBS 7월이다. 같은 기준 시장상황을 적용하는 문서조건부 사례로서, 과거 기관이 이후 시장통계를 이미 알고 있었다고 가정하지 않는다. 본실험은 예비실험의 실행 가능성과 해당 자료 검토를 확인한 뒤 별도로 동결한다.</p>
<p>실행 후보는 Qwen3.5-4B의 Q4_K_M 양자화 모델과 Ollama 0.35.1이다. 온도 0과 최대 출력 8,192토큰은 PortBench v6 §3.1을 참고한 기존 설정을 유지한다. 이 논문의 모델·사고모드·전체 실험을 재현한 것은 아니며, 본 과제는 사고모드를 끄고 작은 양자화 모델 하나를 관찰한다. 정확한 모델 파일·템플릿·샘플러·입력은 실행 전 해시와 설정으로 고정한다.</p>
<p>노트북 CPU 8스레드, 문맥 65,536토큰과 단계당 최대 4,500초는 하드웨어 운영 설정이다. 측정된 입력 처리·짧은 출력 속도로 최대 허용 길이를 단순 외삽한 약 70.5분을 75분 상한으로 올려 잡았다. 6토큰 출력에서 얻은 속도이므로 실제 소요 시간이나 완료를 보장하지 않는다. 이 상한은 논문에서 검증된 최적값이나 기대 소요 시간이 아니다. 출력 내용·허용량을 줄이지 않으며 용량 초과·시간 초과를 원래 실패로 기록한다.</p>'''

EVALUATION = '''<p>평가에서는 세 가지를 구분한다. 첫째, 허용된 11개 산업 코드가 한 번씩 존재하는지와 원비중의 합계·음수·중복을 계산한다. 모든 산업 행을 요구하므로 이 항목은 개별 종목 선택 능력이나 기관의 실제 보유종목 복원 점수가 아니다. 둘째, 모델이 말한 비중 증가·감소 및 기준 대비 방향이 실제 숫자와 맞는지 확인한다. 셋째, 공개된 사실·단위·기간과 계산 가능한 수치를 대조한다. 공개되지 않은 기관별 정답 비중과의 일치율은 계산하지 않는다.</p>
<p>기관 자료의 의미를 읽었는지, 그 근거가 실제 배분과 연결되는지는 AI 보조 서술 코딩으로 평가한다. 각 판단에는 출력 구절·자료 위치·계산값·판정 이유·불확실성을 남긴다. 범주는 근거 있는 연결, 근거 없거나 모순되는 연결, 미해결, 누락 또는 평가 불가로 나눈다. 항목을 임의 비중으로 합쳐 총점을 만들지 않는다. 합계 오류나 잘못된 인용도 원출력으로 보존하며 재생성·정규화·대체하지 않는다.</p>
<p>Fidelity의 Overweight/Underweight와 UBS의 Attractive/Neutral은 각 원문의 뜻과 범위로 읽는다. Attractive를 특정 초과비중으로, Neutral을 정확한 시장비중으로 강제 변환하지 않는다. 근거를 정확히 설명하고 합리적 이유로 다른 선택을 했다면 단순한 불일치만으로 오류라고 하지 않는다. C는 기관 자료를 받지 않았으므로 기관 견해 충실성은 해당 없음이다. 다만 받지 않은 기관 발언을 지어내면 근거 없는 귀속으로 기록한다.</p>
<p>사람 두 명의 검토는 필수 조건에서 제외한다. 사용자 위임에 따라 AI가 원문과 사전 기준을 점검하며, 이를 독립 사람 검증이나 평가자 간 신뢰도 확보로 표현하지 않는다. 각 자료 묶음의 11개 산업 비교와 사실 기준은 그 묶음의 출력 전에 확정한다. 공통 평가식과 본실험 자료 선택은 첫 예비출력 전에 고정한다. E/L/C 표지와 실행순서를 제거한 검토본으로 개별 답변을 먼저 검토하되, 내용으로 조건이 드러날 수 있으므로 완전한 맹검은 아니다. 같은 계열 AI의 반복 검토가 편향 제거를 보장하지 않음을 명시한다.</p>
<p>유효한 원배분 사이의 거리는 d(w,v)=0.5Σ|wᵢ−vᵢ|로 기술한다. 기관별 E/L, 같은 절차의 Fidelity/UBS, 각 기관·절차와 공통 C의 비교를 모두 보고한다. C와 멀다는 이유만으로 기관 근거 반영이 더 좋다고 판단하지 않는다. 작은 수치 합계 잔차를 허용한 벡터의 거리는 수치적 근삿값이며 원비중을 정규화하지 않는다. 산업 행이나 여러 비교쌍을 독립 표본으로 늘리거나 유의성 검정을 하지 않는다.</p>
<p>분모는 예정된 최종안 5개·산업 행 55개이다. 그중 기관 자료 조건은 44행, C는 11행이다. 실제 시도·완료·읽을 수 있는 부분 응답·유효 배분·비교 가능한 쌍을 함께 보고한다. C가 없으면 C 비교는 미관측으로 남기고, E/L 중 유효한 쌍만 별도로 기술한다. 누락을 거리 0이나 기준 포트폴리오로 채우지 않는다. 장치·전송·용량 실패는 기관 판단을 무시했다는 증거로 해석하지 않는다.</p>'''

REFERENCES = '''<p>기관 정보가 없는 공통 대조군은 <a href="https://www.ifo.de/DocDL/cesifo1_wp11862.pdf">Hornuf 등의 투자배분 실험(2025, §3.3·Table 3)</a>의 정보조건 비교와 <a href="https://arxiv.org/html/2605.27887v6">PortBench v6(2026, Appendix D.4)</a>의 정보 제거 비교를 본 과제에 적용한 것이다. 두 단계 C와 5개 사례의 조합 자체는 연구자의 설계이며 해당 논문을 그대로 재현하거나 적정 표본 수를 입증한 것은 아니다.</p>
<p>동일비중과 공매도 없는 최소분산 참고안은 <a href="https://arxiv.org/html/2605.27887v6#A3.SS4">PortBench v6 Appendix C.4</a>의 전통 전략을 적용했다. AI 의미 평가의 편향·한계와 나머지 근거는 <a href="../research/v492_evaluation_methods_review_20261019.json">원문·방법 검토 기록</a>에 정리했다. 새로운 수치 위험선호, 수익률 목표나 기관 평가어의 비중 환산표는 도입하지 않았다.</p>'''


def main():
    refs = json.loads((ROOT / 'research/v492_computational_references_20261019.json').read_text(encoding='utf-8'))
    table = '<div class="table-wrap"><table><thead><tr><th>산업</th><th>동일비중</th><th>최소분산 참고안</th></tr></thead><tbody>'
    equal, gmv = refs['references'][:2]
    names = ['에너지', '소재', '산업재', '경기소비재', '필수소비재', '헬스케어', '금융', '정보기술', '커뮤니케이션', '유틸리티', '부동산']
    for code, name in zip(refs['sector_codes'], names):
        table += f'<tr><td>{name}</td><td>{100*equal["weights"][code]:.2f}%</td><td>{100*gmv["weights"][code]:.2f}%</td></tr>'
    table += '</tbody></table></div>'
    baseline = '''<p>기관별로 유일한 최적 배분을 계산한 것은 아니다. 기관이 공개한 목적함수·기대수익·위험 한도와 11개 정답 비중이 없기 때문이다. AI가 기관 견해와 공통상황을 해석해 제안하는 배분은 그 조건에서의 권고안이다. 계산 참고안 두 개는 AI 없이 재현되며 기관별 자료를 읽지 않는다.</p>
<p>동일비중은 각 산업에 1/11을 배분한다. 최소분산은 주어진 과거 공분산 Σ에 대해 wᵀΣw를 최소화하되 비중은 0 이상이고 합은 1로 제한한다. 과거 60개 일별 관측값을 그대로 사용하며 미래 수익률·위험회피계수·산업별 상한을 새로 추정하지 않는다. 이 목적에서의 수학적 최적해이지 미래 수익이나 기관 전략의 최적해가 아니다.</p>''' + table + '''<p>표는 보기 위해 소수 둘째 자리까지 반올림했다. 원비중과 계산식은 <a href="../research/v492_computational_references_20261019.json">계산 기록</a>에 보존했다. 전 범위 후보 계산과 별도 수치 최적화가 같은 결과를 냈다. 이 숫자들은 모델 입력에 정답으로 제공하지 않으며, 과거 자료로 계산한 위험을 미래 손실 확률로 부르지 않는다.</p>'''
    status = '기관 원문과 공통상황의 AI 사전 검토 및 계산 참고안은 준비했다. 새 C 대조군을 포함한 예비실험 실행과 본실험은 아직 결과가 없는 준비 단계다. 실행 완료 여부와 실패는 별도 원본 기록으로 갱신한다.'
    summary_file = ROOT / 'research/v492_pilot_execution_report_20261019.json'
    if summary_file.exists():
        report = json.loads(summary_file.read_text(encoding='utf-8'))
        status = html.escape(report['reader_status_ko'])
    styles = 'body{font:16px/1.85 "Malgun Gothic",sans-serif;color:#203039;background:#f5f7f9;margin:0}main{max-width:1050px;padding:36px;margin:auto;background:white}h1{line-height:1.4}h2{margin-top:38px}a{color:#175c75}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:12px;border-bottom:1px solid #d7e0e5;text-align:left;vertical-align:top}.table-wrap{overflow:auto}.notice{background:#eef5f7;border-left:4px solid #26778a;padding:16px}p{word-break:keep-all;overflow-wrap:anywhere}@media(max-width:650px){main{padding:22px 16px}h1{font-size:27px}td,th{min-width:100px}}'
    document = '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LIBERA v4.9.2 대조군 포함 계획</title><style>' + styles + '</style></head><body><main><p>2026-10-19 · v4.9.2 · 사람 검토 필수 규칙 수정 · 기관 자료 없는 C 대조군 추가</p><h1>기관 자료가 AI의 산업배분을 바꾸는가</h1><p class="notice">' + status + '</p><h2>무엇과 무엇을 비교하는가</h2>' + DESIGN + '<h2>계산 참고안은 무엇인가</h2>' + baseline + '<h2>어떻게 평가하는가</h2>' + EVALUATION + '<h2>논문 주제와 연결</h2><p>동일 AI를 사용하더라도 기관별 공개 판단이 실제 선택과 설명에 보존되는지를 조사한다. C는 공통 시장상황만으로 나오는 제안을 보여 주므로 기관 문서 제공 후 무엇이 달라졌는지 해석할 기준이 된다. 그러나 두 기관·한 시장·한 모델의 사례로 시장 전체의 획일화나 투자성과를 입증하지는 않는다.</p><h2>근거와 기록</h2>' + REFERENCES + '<p><a href="../paper/LIBERA_텀페이퍼_초안_v4.9.2_20261019.html">수정한 텀페이퍼 전체 초안</a> · <a href="../research/v492_evaluation_protocol_20261019.json">새 평가 규칙</a> · <a href="../research/v492_source_review_20261019.json">기관 원문 AI 검토</a></p></main></body></html>'
    document = document.replace('v492_evaluation_protocol_20261019.json', 'v492_evaluation_protocol_20261019_r2.json')
    PLAN.write_text(document, encoding='utf-8', newline='\n')
    soup = BeautifulSoup((ROOT / 'paper/LIBERA_텀페이퍼_초안_v4.9.1_20261019.html').read_text(encoding='utf-8'), 'html.parser')
    original_common = str(soup.select_one('#common-context-method'))
    original_common = original_common.replace('달라지는 것은 기관 자료의 최초 제공 시점과 그에 따라 형성된 초안 이력이다.', 'E/L 사이에서는 기관 자료의 최초 제공 시점과 그에 따라 형성된 초안 이력이 달라진다. C와의 비교에서는 기관 자료를 제공하는지 자체가 달라진다.')
    for node in soup.select('#literature p'):
        if '최종 단계에는 같은 기관 자료를 양쪽에 제공' in node.get_text():
            for text_node in list(node.find_all(string=True)):
                if '최종 단계에는 같은 기관 자료를 양쪽에 제공' in str(text_node):
                    text_node.replace_with(str(text_node).replace('최종 단계에는 같은 기관 자료를 양쪽에 제공', 'E/L의 최종 단계에는 같은 기관 자료를 양쪽에 제공'))
    def replace_section(identifier, heading, body):
        old = soup.select_one('#' + identifier)
        replacement = BeautifulSoup(f'<section id="{identifier}"><h2>{heading}</h2>{body}</section>', 'html.parser').section
        old.replace_with(replacement)
    soup.title.string = '공통 생성형 AI의 기관별 공개 투자판단 반영 · LIBERA v4.9.2'
    soup.select_one('header .eyebrow').string = 'LIBERA 2026 · VERSION 4.9.2'
    soup.select_one('header .status').string = status
    header_links = soup.select('header nav a')
    for link, href in zip(header_links, ('../plan/LIBERA_대조군포함_실험계획_v4.9.2_20261019.html', '../research/v492_evaluation_protocol_20261019_r2.json', '../research/v492_process_20261019.jsonl')):
        link['href'] = href
    if soup.select_one('.subtitle'):
        soup.select_one('.subtitle').string = '기관 자료 미제공 대조군과 초안 전후 자료 제공을 비교하는 산업배분 사례연구'
    abstract = soup.select_one('.abstract')
    if abstract:
        abstract.clear()
        abstract.append(BeautifulSoup('<h2>초록</h2><p>본 연구는 공통 생성형 AI가 서로 다른 기관의 공개 투자판단을 산업배분 제안에 어떻게 반영하는지 조사한다. 공통 업무·시장상황 아래 Fidelity와 UBS 자료의 조기·후기 제공 네 사례와 기관 자료를 끝까지 주지 않는 동일 AI 대조군 한 사례를 비교한다. 각 사례는 초안과 계산 검토 후 첫 최종안으로 구성한다. 계산으로 확인되는 산업·비중·수치의 정확성과 AI가 보조 분류한 근거–선택 연결을 구분하며, 실제 기관의 최적 비중을 정답으로 가정하지 않는다. 이 초안은 본실험 전 설계 문서로 효과나 투자성과를 결론으로 제시하지 않는다.</p>', 'html.parser'))
    replace_section('framework', '3. 연구질문과 관측의 연결', '<p>첫째, 서로 다른 기관 자료의 근거가 AI의 설명과 산업별 배분에 보존되는가. 둘째, 기관 자료를 받지 않은 동일 AI의 대조군 C와 비교하면 어떤 선택·설명이 달라지는가. 셋째, 자료를 초안 전부터 주는 E와 최종 검토 때 처음 주는 L의 절차 차이는 어떻게 나타나는가. 관측 대상은 보이는 근거와 원비중이며 내부 인지 기제나 시장 전체의 인과효과가 아니다.</p>')
    replace_section('design', '4. 자료와 비교 절차', original_common + DESIGN)
    replace_section('evaluation', '5. 평가와 사전 해석 규칙', EVALUATION + '<h3>계산 참고안과 기관 최적배분의 구별</h3>' + baseline + REFERENCES)
    replace_section('readiness', '6. 개발 이력과 준비 상태', '<p>' + status + '</p><p>기존 v4.8·v4.9.1의 실행 실패와 CPU 진단은 개발 이력으로 보존한다. 새 v4.9.2 결과로 합치지 않는다. 원문22개 산업행·11개 기관 비교와 거시자료를 AI가 사전에 검토했다. 사람 두 명의 서명이나 평가 합의를 작성하지 않았으며 AI 검토의 한계를 기록했다.</p><p>모델·입력·평가·코드·실행순서는 예비출력 전에 파일 해시로 묶는다. 이는 로컬 사전 확정 기록이며 외부 사전등록이나 연구 타당성의 보증은 아니다. 본실험 원문 선택은 미리 유지하되, 그 의미 검토를 예비실험 뒤에 수행한다면 해당 시점을 공개한다.</p>')
    replace_section('implications', '7. 예상 기여와 해석의 한계', '<p>기여는 기관별 공개 근거를 AI의 선택까지 추적하고, 공통상황만 제공한 대조군 및 정보 제공 절차와 비교하는 업무 검토 방법에 있다. 서로 다른 배분을 무조건 더 좋은 결과로, 비슷한 배분을 무조건 판단 소실로 보지 않는다.</p><p>두 기관·하나의 시장상황·작은 양자화 모델에 대한 사례이며, 기관의 사적 목표·실제 보유·고유 최적배분을 관측하지 않는다. 현재 빈티지의 과거 가격, 짧은 위험 추정창, 문서 날짜와 척도의 차이가 한계다. AI 의미 코딩은 사람 검증을 받지 않았고 같은 계열 보조 에이전트의 교차 확인을 독립 평가자 신뢰도로 해석할 수 없다. 기관 문서 제공은 입력 길이와 노출도 함께 바꾸며 C 한 관측값의 재사용은 표본 수를 늘리지 않는다.</p><p>개별 수치 검증과 문서에 근거한 해석은 연구의 추적 가능성을 높이지만, 실험의 유의미성이나 긍정적 결과를 미리 보장하지 않는다. 유효한 비교쌍이 확보되지 않으면 해당 연구질문은 미답으로 보고한다.</p>')
    replace_section('conclusion', '8. 결론', '<p>본 연구는 기관의 공개 판단, 공통 시장상황과 실제 산업배분의 연결을 살피는 사례연구를 제안한다. 기관 자료 없는 동일 AI 대조군을 추가하여 정보 미제공과 조기·후기 제공을 구분하고, 계산 가능한 사실과 잠정적인 AI 의미 평가를 나누어 기록한다. 본실험 전 단계이므로 기관 근거 보존이나 투자성과에 대한 실증 결론은 제시하지 않는다.</p>')
    replace_section('appendix', '부록 · 입력과 재현 자료', '<p><a href="../plan/LIBERA_대조군포함_실험계획_v4.9.2_20261019.html">대조군 포함 실험계획</a> · <a href="../research/v492_evaluation_protocol_20261019.json">평가 규칙</a> · <a href="../research/v492_source_review_20261019.json">AI 원문 검토</a> · <a href="../research/v492_computational_references_20261019.json">계산 참고안</a></p><p>본실험 결과·저자 정보·제출 규정 최종 점검을 완료한 제출본은 아니다. v4.9.1 문서는 이전 설계로 별도 보존한다.</p>')
    if soup.footer:
        soup.footer.string = 'v4.9.2 · E/L 기관 자료 조건 네 개 + 공통 C 대조군 하나 · AI 보조 평가 · 본실험 전 초안'
    for node in soup.find_all(string=True):
        if node.parent.name not in ('script', 'style') and 'v4.9.1' in str(node):
            # Only the version badge/header is relabeled; citations/history stay historical.
            if node.parent.name in ('span',) or node.parent.get('class') in (['eyebrow'], ['pill']):
                node.replace_with(str(node).replace('v4.9.1', 'v4.9.2'))
    PAPER.write_text(str(soup).replace('v492_evaluation_protocol_20261019.json', 'v492_evaluation_protocol_20261019_r2.json'), encoding='utf-8', newline='\n')
    print(json.dumps({'plan': PLAN.relative_to(ROOT).as_posix(), 'paper': PAPER.relative_to(ROOT).as_posix(),
                      'recorded_at_utc': datetime.now(timezone.utc).isoformat()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
