"""Correct the excessive narrowing: institutional judgment is the main question.

The validated single-asset table remains an auxiliary diagnostic, not evidence
that the institution-specific strategic-heterogeneity experiment is complete.
"""
from pathlib import Path
from bs4 import BeautifulSoup
import shutil
import json

ROOT=Path(__file__).resolve().parents[1]
plan_path=ROOT/'plan/LIBERA_실험계획_20261017.html'
paper_path=ROOT/'paper/LIBERA_텀페이퍼_초안_20261017.html'
cfg_path=ROOT/'plan/LIBERA_실험설정_20261017.json'
snapshots=[(plan_path,ROOT/'plan/archive/LIBERA_실험계획_v3.4.html'),(cfg_path,ROOT/'plan/archive/LIBERA_실험설정_v3.4.json'),(paper_path,ROOT/'paper/archive/LIBERA_텀페이퍼_초안_v3.4.html')]
for src,dst in snapshots:
    if not dst.exists(): shutil.copy2(src,dst)
paper=BeautifulSoup(snapshots[2][1].read_text(encoding='utf-8'),'html.parser')
plan=BeautifulSoup(snapshots[0][1].read_text(encoding='utf-8'),'html.parser')
cfg=json.loads(snapshots[1][1].read_text(encoding='utf-8'))
def html(s): return BeautifulSoup(s,'html.parser')
def replace_p(soup,prefix,text):
    found=[p for p in soup.find_all('p') if p.get_text().startswith(prefix)]
    assert len(found)==1,(prefix,len(found))
    found[0].replace_with(html(text))

paper.select_one('.subtitle').string='기관별 근거가 요구하는 투자판단 차이와 업무 과정 설계'
paper.select_one('.meta').string='문헌 검토와 연구설계 소논문 · 2026년 10월 17일 v3.5 · 원논점 재정렬 / 주실험 모형 구체화 중'
paper.select_one('.status').clear()
paper.select_one('.status').append(html('<strong>연구 범위 정정.</strong> 단일 자산의 신호–행동 과제만으로 기관투자자의 판단 이질성을 검증할 수 없으므로, 이를 주실험으로 확정했던 v3.4의 결정을 수정했다. 주실험은 기관별 유효 정보·목적·제약이 요구하는 판단 차이를 다룬다. 공개 문서 과제와 기초 거래 과제는 근거 구축·보조 진단으로 유지한다. 자체 AI 실험은 아직 수행하지 않았다.'))
for a in paper.find_all('a'):
    if a.get_text()=='확정 범위를 반영한 실험계획 v3.4': a.string='논점을 재정렬한 실험계획 v3.5'
abstract=paper.select_one('#abstract p')
abstract.replace_with(html('<p>생성형 AI가 투자 업무를 지원할 때, 동일한 모델의 활용이 기관마다 달라야 할 판단까지 비슷하게 만들 수 있는가? 본 연구는 액티브 주식형 펀드를 맥락으로 공통 알고리즘, 금융 분야의 AI 활용, 조직의 업무 설계에 관한 문헌을 검토한다. 핵심 연구대상은 단순한 답변 유사성이 아니라 기관별 유효 정보·목적·제약이 요구하는 판단 차이의 보존이다. 이를 위해 같은 시장 상황에서 기관별 조건을 달리하고, 각 조건에서의 적정 판단을 기준으로 근거 제공 정책과 판단 품질을 비교하는 실험 구조를 제시한다. 공개 펀드 문서는 기관별 조건의 근거를 구축하는 데 사용하며, 정답이 단순한 단일 자산 거래 과제는 정보 반영의 보조 진단으로 구분한다. 현 단계에서는 기관별 기준 판단을 정당화할 문헌 모형과 입력의 연결을 확정해야 한다. 따라서 본 원고는 실험 전 연구설계이며, 실제 펀드의 전략 동질화나 완화효과를 입증한 결과를 제시하지 않는다.</p>'))
replace_p(paper,'확정된 연구 기여.','<p><strong>연구가 목표로 하는 기여.</strong> 같은 AI를 사용하는 환경에서 기관별 근거가 요구하는 투자판단 차이가 보존되는지 평가하고, 그 근거를 업무의 어느 단계에서 제공·유지하는 것이 판단 품질에 도움이 되는지 비교한다. 단일 신호를 맞게 읽는 능력만으로 이 기여가 달성됐다고 볼 수 없으며, 기관별 조건이 실제 기준 판단을 바꾸는 주실험이 필요하다.</p>')

design='''<section id="design"><h2>4. 연구방법과 주실험의 필수 구조</h2>
<h3>4.1. 연구 규모를 줄이면서 유지해야 할 대상</h3>
<p>연구의 중심 대상은 기관별 조건이 서로 다른 투자판단이다. 기관 수, 자산 수, 제공 시점의 종류를 줄일 수는 있지만, 기관별 차이가 평가 기준을 바꾸는 구조를 제거하면 다른 연구가 된다. 따라서 같은 시장정보와 같은 AI를 사용하되, 기관마다 유효한 정보·목적·제약 중 적어도 하나가 판단 문제에 실제로 작용하도록 설계한다. 기관명, 문체 또는 목적식에 사용하지 않는 초기 보유 비중만 바꾸는 것은 이 요건을 충족하지 않는다.</p>
<h3>4.2. 기관별 적정 판단 기준</h3>
<p>평가 기준은 모든 기관의 정보를 합친 전지적 정답이 아니라 각 기관에 주어진 정보와 목적·제약에서의 적정 판단이다. 공개 공시로 확인한 제한은 적용 대상·분모·예외까지 보존하고, 정성적인 운용 설명을 임의의 기대수익률이나 위험회피 계수로 변환하지 않는다. 수치 모형이 필요하면 선행논문의 식·정보 구조·설정을 직접 확인하고, 공개자료에서 계산한 값과 연구자의 새 설계 선택을 구분한다.</p>
<p>기관별로 계산한 기준이 실제로 다른 판단을 요구하는지 먼저 검증한다. 최적해가 여러 개라면 같은 답이 두 기관에서 모두 최적일 가능성도 확인해야 한다. 각 최적해 집합에서 임의로 한 점을 골라 둘의 거리를 필요한 차이라고 정의하지 않는다. 공통된 최적 답이 가능한 사례에서는 AI가 같은 결과를 냈다는 사실만으로 실패라고 판정하지 않는다.</p>
<h3>4.3. 대응 비교와 정보 제공 정책</h3>
<p>같은 시장 상황에서 기관별 조건을 받은 AI의 판단을 비교하고, 동일 기관 안에서는 다른 요소를 유지한 채 유효한 근거만 바꾼 대응 입력으로 정보 반응을 확인한다. 근거의 내용은 같게 두고 처음부터 제공·유지하는 정책과 최종 재검토 때 제공하는 정책을 비교한다. 모든 정책에서 최종 선택지를 다시 열어 두며, 원래 근거가 없던 단계에서 사실이나 수치를 만들어 내도록 요구하지 않는다.</p>
<p>이 실험의 질문은 ‘자료를 늦게 받은 AI가 문제를 맞히는가’에 그치지 않는다. 기관별로 달라야 할 권고가 공통 AI 아래에서 불필요하게 같아지는지, 그리고 근거 제공 정책이 그 차이와 기관별 품질을 함께 보존하는지다. 필요한 차이의 소실과 각 기관의 목적상 손실·제약 위반을 함께 보고한다. 단순한 다양성 증가를 개선으로 평가하지 않는다.</p>
<h3>4.4. 공개 문서와 보조 거래 과제의 역할</h3>
<div class="table-wrap"><table><caption>표 1. 원주제를 위한 증거 구조</caption><thead><tr><th>구성</th><th>역할</th><th>현재 상태</th></tr></thead><tbody>
<tr><td>A 공개 펀드 문서</td><td>기관별 조건의 출처·정확성·적용 범위 확인</td><td>공식 자료 후보를 확보했으며 버전·정답표 검증 필요</td></tr>
<tr><td>기관별 투자판단 주실험</td><td>조건에 따라 필요한 판단 차이와 경제적 품질을 비교</td><td>논문 모형과 기관별 입력 연결을 구체화해야 함</td></tr>
<tr><td>B1 단일 자산 과제</td><td>명확한 신호의 활용과 실행 절차에 관한 보조 진단</td><td>255개 이력·510개 신호 조건의 기준 답 준비; AI 미실행</td></tr>
</tbody></table></div>
<p>Hansen과 Lee(<a href="#ref-hansen">2025</a>)의 환경 I에 기반한 보조 과제는 신호별 최적 행동이 단순하다. 이 과제의 성공이나 실패를 기관의 전략적 이질성 보존으로 바꾸어 해석하지 않는다. A의 문서 정확성과 B1의 신호 활용 성과를 합쳐 실제 펀드의 동질화 완화가 입증됐다고 결론 내릴 수도 없다. 두 과제는 주실험을 준비하고 오류를 진단하는 보조 증거다.</p>
<h3>4.5. 현재 남아 있는 설계 과제</h3>
<p>주실험의 핵심 미완료 항목은 기관별 정보·목적·제약이 각각 어떤 식과 입력을 통해 기준 판단을 달리 만드는지다. 이 연결이 확인되기 전에는 특정 산업 분류나 공통 최적화식을 골랐다는 이유만으로 설계가 완성됐다고 기록하지 않는다. 현재 원고는 검증할 구조와 그 요건을 명시하며, 근거가 확인된 모형으로 채워 넣은 뒤 실제 실행 조건을 고정할 예정이다.</p>
<p>같은 모델 안의 정책 비교는 해당 환경에서의 정보 전달 효과를 식별한다. ‘공통모델을 채택했기 때문에 동질화가 발생했다’는 인과효과까지 주장하려면 비사용 또는 모델 다양성 비교가 추가로 필요하다. 이 두 주장을 구분하는 한계는 원주제를 다른 과제로 바꾸는 것이 아니라 실제 비교가 허용하는 결론의 경계를 정하는 것이다.</p>
</section>'''
paper.find(id='design').replace_with(html(design))
paper.find(id='limits').replace_with(html('''<section id="limits"><h2>7. 한계와 후속 연구</h2><p>현재 원고에는 자체 AI 실험 결과가 없으며, 기관별 기준 판단을 정당화할 모형과 입력의 연결도 구체화 중이다. 준비된 수익률·배분 계산과 B1의 기준 답은 도구 검증이며 주가설의 증거가 아니다. 이 미완료 상태를 좁은 거래 과제의 결과로 대신하거나 한계 문구만 붙여 넘기지 않는다.</p><p>공개 문서는 실제 비공개 전망 전체를 나타내지 않는다. 통제된 기관별 판단 실험을 완성해도 실제 운용사의 행동·수익률·시장 위험에 대한 일반화에는 추가 검증이 필요하다. 그러나 기관별로 다른 판단 기준을 유지한 통제 실험이라면, 정보 반영과 업무 설계라는 연구질문을 직접 검증하는 제한된 증거를 제공할 수 있다.</p><p>실험 결과의 차이를 확인하지 못한 경우에는 과제의 난이도, 효과 추정의 정밀도, 모델과 입력의 범위를 함께 보고한다. 단순한 보조 과제에서 정답률이 높다는 사실은 일반적인 동질화 위험의 부재를 뜻하지 않는다. 본실험 결과를 본 뒤 유리한 조건으로 교체하지 않으며 무효과와 반대 결과도 보존한다.</p></section>'''))
replace_p(paper,'본 연구는 액티브 주식형 펀드의 정보처리 문제를 출발점으로 삼고,','<p>본 연구는 액티브 주식형 펀드의 정보처리 문제를 출발점으로 삼고, 기관별 근거가 요구하는 판단 차이와 기관별 품질을 함께 평가하는 실험 구조를 제시했다. 공개 문서 검증과 단일 자산 거래 과제는 그 구조를 준비·진단하는 보조 수단이다. 다음 과제는 기관별 적정 판단의 차이를 정당화할 논문 모형과 입력을 연결하여 주실험을 완성하는 것이다.</p>')
paper.find(id='appendix').replace_with(html('''<section id="appendix"><h2>부록. 범위 정정과 제출 준비</h2><p>v3.4에서는 A 공개 문서와 B1 최소 거래 과제를 주실험 범위로 확정했으나, 이는 기관별 투자판단이라는 주제를 충분히 검증하지 못한다는 지적에 따라 정정했다. 연구 주제는 유지하고 A·B1의 역할을 보조 증거로 조정한다. 실제 펀드 전체의 운용을 재현하는 것과 단순 신호 과제만 수행하는 것 사이에는, 기관별 조건을 통제한 투자판단 실험이라는 설계가 있다.</p><p><a href="https://app.notion.com/p/2026-agent-conference/LIBERA-3e00589711408053a7e5ff9a0c4ba804">학술제 개요</a>에 따른 11월 1일 페이퍼 제출과 11월 6일 피칭 일정은 유지한다. 우선 주실험의 모형·입력 연결을 확인하고, 그 구조를 유지하면서 자산 수·비교 정책·모델 수를 줄여 실행 범위를 정한다. 논문 근거가 확인되지 않은 수치를 추가하거나 보조 실험을 주가설의 검증으로 포장하지 않는다.</p></section>'''))

plan.title.string='LIBERA 연구계획 v3.5 — 기관별 판단 이질성 주실험 복원'
plan.select_one('.eyebrow').string='LIBERA · MAIN QUESTION REALIGNMENT · VERSION 3.5'
plan.select_one('.meta').string='2026-10-17 · 과도한 범위 축소 정정 · 주실험 모형·입력 연결 구체화 중'
for node in plan.find_all(string=True):
    if 'v3.4' in str(node): node.replace_with(str(node).replace('v3.4','v3.5'))
for box in plan.header.select('.decision'): box.decompose()
plan.header.append(html('<p class="decision"><strong>범위 정정:</strong> A＋B1만을 주실험으로 확정했던 판단을 수정한다. 단순 신호–행동 과제는 기관별 투자판단의 이질성을 대신하지 못한다. 원주제를 유지하고 B1은 보조 진단으로 보존한다. 다음 핵심 작업은 기관별 조건이 실제로 다른 기준 판단을 요구하는 논문 모형과 입력을 확정하는 것이다.</p>'))
plan.find(id='evidence').replace_with(html('''<section id="evidence"><h2>3. 주실험에 반드시 남아야 할 구조</h2><ol><li>기관별 유효 정보·목적·제약 중 적어도 하나가 실제 판단 기준에 작용해야 한다.</li><li>각 기관의 조건에서 적정 판단을 정의하고, 같아도 되는 사례와 달라야 하는 사례를 구별해야 한다. 복수 최적해의 공통 부분도 확인한다.</li><li>같은 모델·시장상황에서 근거 제공 정책을 대응 비교하고, 필요한 차이의 보존과 기관별 품질을 함께 평가해야 한다.</li></ol><p>A는 기관별 조건의 공개 근거를 구축하는 역할, B1은 기초 정보 반영을 진단하는 역할이다. 두 과제의 성과를 합쳐 기관별 투자판단 동질화를 입증했다고 볼 수 없다. 연구 규모를 줄일 때는 자산·기관·모델·단계의 수를 조정하고 위 구조는 유지한다.</p></section>'''))
plan.find(id='protocol').replace_with(html('''<section id="protocol"><h2>4. 비교할 것은 기관별로 필요한 판단 차이</h2><p>공통 시장 상황을 고정한 채 기관별 정보·목적·제약에서 계산한 적정 판단을 비교한다. 동일 기관 안에서는 다른 조건을 유지하고 유효 근거만 교체해 AI가 필요한 방향으로 반응하는지 확인한다. 근거의 내용은 같게 두고 초기 제공과 후기 재검토 정책을 비교한다. 최종 정보와 선택지는 정책 사이에 동일하게 유지한다.</p><p>같은 답이 여러 기관에서 모두 최적일 수 있다면 수렴은 실패가 아니다. AI의 차이가 크더라도 각 기관에서 나쁜 선택이라면 개선이 아니다. 기관별 목표상 손실 또는 제약 위반을 차이 지표와 함께 평가한다. 주실험에 쓸 구체적인 식·입력·자산 체계는 이 요건을 만족하는 논문 모형을 확인한 뒤 확정한다.</p><p>같은 모델만 사용하는 비교의 결론은 그 환경에서의 근거 전달 정책 효과다. 공통모델 채택 자체의 인과효과나 시장 전체의 금융안정 효과를 직접 추정한 것으로 서술하지 않는다.</p></section>'''))
plan.find(id='choices').replace_with(html('''<section id="choices"><h2>5. 다음에 확정할 항목</h2><div class="table-wrap"><table><thead><tr><th>항목</th><th>확정 기준</th></tr></thead><tbody><tr><td>기관별 차이의 원천</td><td>공개 근거가 있는 목적·제약 또는 논문이 정의한 유효 정보 차이. 이름·초기 비중 차이만으로 대체 불가.</td></tr><tr><td>적정 판단의 식</td><td>각 기관의 조건이 실제 식과 입력에 들어가야 하며 복수 최적해와 합리적 수렴을 처리해야 함.</td></tr><tr><td>실행 규모</td><td>위 구조를 보존한 채 자산·기관·모델·정책 수를 줄임. 연구 현상 자체를 단순 신호 추종으로 바꾸지 않음.</td></tr><tr><td>모델·자료</td><td>모델 버전과 논문 설정 확인, 공식 문서의 버전·날짜·출처를 동결한 뒤 실행.</td></tr></tbody></table></div><p>사용자에게 같은 범위를 다시 고르도록 요청하지 않는다. 원주제를 유지한다는 기준 아래 모형·입력의 연결을 먼저 검증한다.</p></section>'''))
plan.find(id='plain').replace_with(html('''<section id="plain"><h2>2. 원주제에 맞는 실험을 쉽게 설명하면</h2><p>같은 시장에서도 서로 다른 근거와 조건을 가진 기관들은 다른 투자를 선택하는 것이 적절할 수 있다. 연구자는 먼저 각 기관에 주어진 조건에서 어느 판단이 적절한지 확인한다. 그런 다음 같은 AI가 각 기관을 도울 때 그 차이를 반영하는지 본다.</p><p>핵심 비교에서는 기관별 근거를 처음부터 주거나 마지막 재검토 때 준다. 마지막에는 같은 기관의 두 조건이 동일한 자료를 알고 모든 선택을 다시 할 수 있다. 이때 기관마다 달라야 할 판단이 하나의 공통 답으로 좁혀지고 품질도 나빠지는지, 근거를 일찍 제공하면 그 문제가 줄어드는지 평가한다.</p><p>단순한 좋은 신호·나쁜 신호에 따라 매수·매도하는 과제는 실행 절차를 점검하는 데 유용하지만 이 주실험을 대신하지 않는다. 실제 운용사의 전체 업무를 재현할 필요는 없어도, 기관별로 다른 판단 기준이라는 핵심 구조는 남겨야 한다.</p></section>'''))
plan.find(id='numbers').replace_with(html('''<section id="numbers"><h2>6. 기존 수치 모형의 위치</h2><p>P/Q 배분식은 같은 입력의 계산 정확도를 점검하는 부록이다. 기관별 정보·목적·제약이 식에 들어가지 않으면 원주제의 평가 모형이 되지 않는다. Hansen–Lee 환경 I의 255개 이력·510개 신호 조건도 보조 정답표로 보존한다. 해당 숫자는 이론 경로의 전수 목록이며 독립 시장 표본이 아니다.</p><p>주실험 모형은 기관별 기준 판단을 정당화하는 근거가 확인된 뒤 확정한다. 논문 직접 조건, 데이터 계산값, 연구자의 설계 선택을 구별하며 아직 확인되지 않은 수치를 채워 넣지 않는다.</p></section>'''))
plan.find(id='delivery').replace_with(html('''<section id="delivery"><h2>8. 진행 순서</h2><p><strong>현재:</strong> 원주제와 최소 거래 과제의 불일치를 인정하고 주실험 확정 표현을 정정했다. 공개 문서 출처 목록과 보조 기준 답은 보존했다. AI 실험은 수행하지 않았다.</p><p><strong>다음:</strong> 기관별 유효 정보·목적·제약이 기준 판단을 달리 만드는 논문 모형을 확인한다. 공개자료와 연결할 수 있는 범위에서 주실험을 구체화하고, 핵심 구조를 보존하면서 실행 규모를 줄인다. 이후 모델·자료·프롬프트와 분석 규칙을 고정하고 실험을 실행한다.</p><p><strong>제출 전:</strong> 실제 결과에 맞춰 초록·결과·논의·한계를 작성한다. 보조 과제의 성과를 주가설의 증거로 승격하지 않는다. 11월 1일 페이퍼, 11월 6일 피칭 일정에 맞춰 논증과 발표를 정리한다.</p></section>'''))

cfg['protocol_version']='3.5'
cfg['previous_protocol']='archive/LIBERA_실험설정_v3.4.json'
cfg['status']='original_institutional_judgment_question_preserved; narrowed_B1_main_design_reclassified_as_auxiliary; main_benchmark_pending'
cfg['active_main_experiment']=None
cfg['scope_correction']={'date':'2026-10-17','trigger':'user questioned whether narrowing conflicts with paper topic','reason':'A documentary accuracy plus B1 signal following does not test institution-specific warranted judgment heterogeneity','primary_objective_unchanged':True,'main_requirements':['institution-specific valid information/objective/constraints enter the decision problem','institution-conditioned normative benchmark and overlapping-optimum handling','paired evidence-policy comparison with heterogeneity and institution-specific quality'], 'B1_role':'auxiliary only'}
cfg['user_scope_decision']['qualification']='A+B1-only main interpretation superseded after user questioned topic alignment; original topic retained'
cfg['recommendation']['status']='A+B1-only main recommendation withdrawn as insufficient for original question'
cfg['recommendation']['recommended_evidence_scope']=['institution_conditioned_judgment_main_experiment_pending','A_public_evidence_support','B1_auxiliary_diagnostic']
cfg['module_roles']['B1']='auxiliary basic information-use diagnostic; not main hypothesis evidence'
cfg['module_roles']['B2']='institution-conditioned main decision structure required; full real-fund replication not required'
cfg['B1_protocol']['status']='validated auxiliary reference table; no AI run'
cfg['B1_protocol']['selected_for_main_experiment']=False
cfg['analysis']['main_call_count']=None
cfg['analysis']['auxiliary_B1_base_response_opportunities']=cfg['analysis'].pop('planned_base_response_opportunities',4590)
cfg['analysis']['primary_quality']='not frozen until institution-conditioned model is verified'
cfg['analysis']['primary_heterogeneity']='warranted differences in institution-conditioned judgment, not generic signal-action distinction'
cfg['gates_before_main']['scope_selected']=False
cfg['gates_before_main']['original_question_preserved']=True
cfg['gates_before_main']['institution_conditioned_benchmark_validated']=False
cfg['completed']['scope_selected_A_plus_B1']=False
cfg['completed']['B1_auxiliary_reference_prepared']=True
cfg['completed']['AI_responses']=0
paper_path.write_text(str(paper)+'\n',encoding='utf-8')
plan_path.write_text(str(plan)+'\n',encoding='utf-8')
cfg_path.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('v3.5: original question retained; single-asset benchmark is auxiliary; main model is not falsely marked ready.')
