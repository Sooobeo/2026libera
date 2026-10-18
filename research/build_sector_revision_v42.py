"""Integrate the prepared documentary corpus, market inputs and executable protocol.

Rebuilds from the preserved v4.1 documents, leaving the original proposal intact.
Does not execute an AI model or invent observed results.
"""
from pathlib import Path
import hashlib
import json
import shutil
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/'plan/LIBERA_실험계획_20261017.html'
PAPER=ROOT/'paper/LIBERA_텀페이퍼_초안_20261017.html'
CONFIG=ROOT/'plan/LIBERA_실험설정_20261017.json'
REV=ROOT/'research/design_revision_20261017'

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def archive(p):
    a=p.parent/'archive'/p.name.replace('_20261017','_v4.1')
    a.parent.mkdir(exist_ok=True)
    if not a.exists():shutil.copy2(p,a)
    return a
for p in (PLAN,PAPER,CONFIG):archive(p)

framework='''<section id="framework"><h2>3. 개념과 연구질문</h2>
<p>본 연구는 공통 생성형 AI가 기관별 판단의 차이를 최종 결정에 반영하는 문제를 주식부문 안의 산업 배분에서 다룬다. 산업 선택은 어느 경제활동에 자본을 더 배정할지 결정하므로 상경·경영학의 자원 배분 및 조직 의사결정과 연결된다. 원제안서도 산업별 비중을 분석 단위로 삼았다. 개별 종목 선택은 본 질문을 검증하기 위한 필수조건이 아니다.</p>
<p>다만 실제 확보한 문서는 Fidelity의 전략가 전망과 UBS CIO의 House View다. 따라서 직접 관찰하는 기관별 특성은 <strong>공개된 산업 판단과 그 근거</strong>이며, 기관 전체의 투자목적·고객 위험선호·법적 운용제약을 측정했다고 주장하지 않는다. 논문의 제목도 이 범위에 맞게 ‘투자판단’으로 구체화했다. 더 넓은 전략적 이질성은 문제의식이고, 이번 사례는 그중 문서화된 판단의 전달 경로를 검토한다.</p>
<p>연구질문은 동일한 시장자료·AI·계산 절차에서 기관별 산업 판단이 배분 제안의 근거로 보존되는가, 그리고 문서를 처음부터 제공하는 R1과 최종 검토에서 제공하는 R4의 결과가 어떻게 다른가다. 비중의 수렴 자체는 오류가 아니다. 원문 판단의 누락·왜곡, 선택을 설명하는 근거, 실제 제안 비중을 함께 관찰한다. 기관 간 차이가 커지는 것 역시 성공의 정의가 아니다.</p></section>'''

design='''<section id="design"><h2>4. 연구방법과 준비 상태</h2>
<h3>4.1. 투자 대상과 자료</h3>
<p>문서 본과제는 미국 주식의 <strong>11개 GICS 산업군</strong>으로 고정한다. 에너지·소재·산업재·경기소비재·필수소비재·헬스케어·금융·정보기술·커뮤니케이션·유틸리티·부동산이다. 실제 공개가격을 연결할 바구니는 각각 XLE·XLB·XLI·XLY·XLP·XLV·XLF·XLK·XLC·XLU·XLRE다. AI는 이 바구니들의 비중을 정하며 바구니 내부 기업을 다시 선정하지 않는다. Quek 등(2025, v5)의 GICS 11개 산업 배분, L. Chen 등(2026)의 섹터 ETF 과제가 이 단위의 논문 선례다. 해당 연구의 시장·과제 전체를 재현하는 것은 아니다.</p>
<p>본과제 문서는 Fidelity Q3 2026 산업전망과 UBS July 2026 House View 두 개다. 형식 점검용 예비 문서는 Fidelity Q2와 UBS June이다. 각 출처의 원래 평가 단어·핵심 근거·쪽수·공개일·파일 해시를 기록한 근거 패킷을 만들었다. 입력은 연구자가 선별·요약한 짧은 문장이다. 따라서 원문 전체에서 스스로 검색하는 능력이나 장문 검색 성능을 측정하지 않는다. 평가용 추출 기준표는 별도 파일이며 온라인 실행 코드가 읽지 않는다. 자동 교차 점검과 별개로 사람의 독립 원문 검토를 위한 빈 검토지도 준비했으며, 사람 검토는 아직 완료되지 않았다.</p>
<p>공통 자료 마감은 2026년 7월 17일로 두고 가격 관측은 직전 7월 16일 종가까지 사용한다. 이는 논문의 실험 상수가 아니라 문서 공개일을 반영한 연구 운영 날짜다. Fidelity Q3 공개일은 7월 16일, UBS July 발행일은 6월 22일이고 UBS 산업표 기준일은 6월 18일이다. Fidelity 산업표에는 존재하지 않는 날짜 ‘6/31/26’이 인쇄되어 있어 원문 그대로 오류 표시했다. 두 문서를 동일 시점의 최신 의견이라고 단정하지 않는다. 현재 내려받은 자료를 이용한 날짜 기록 사례이며 당시의 투자 실행·정보집합을 완전히 복원한 백테스트가 아니다.</p>
<h3>4.2. 공통 시장 기준과 위험</h3>
<p>공통 기준 배분은 Fidelity Q3 2쪽에 실린 2026년 6월 30일 S&amp;P 500 산업 비중이다. 이는 Fidelity가 실제 보유하거나 권고한 비중이 아니다. 공표값 합계가 반올림으로 99.9%이므로 원값을 보존하고 각 값을 99.9로 나눈 계산용 비중을 별도로 둔다. 이 정규화는 연구자의 투자 의견이 아니라 예산 합계 처리를 위한 산술 조정이다. 양 기관·양 절차에 동일한 기준을 사용한다.</p>
<p>시장은 공통 직전 60거래일 수익률과 표본 공분산으로 요약한다. 길이 60과 연율화 252는 PortBench의 시장 입력·위험 계산에 근거한다(Zhao et al., 2026, 부록 B.2). Yahoo의 수정종가를 이용한 수익률은 공급자가 현재 수정한 배당·분할 반영 가격의 수익률 대용치다. 매매비용을 반영한 실현 수익이나 미래 예측 정답으로 부르지 않는다. 최근 기간이어도 ETF 구성종목은 바뀔 수 있으나, 본과제는 당시 ETF 가격을 쓰므로 오늘의 보유종목을 과거에 소급 적용하지 않는다.</p>
<p>기관별 위험 성향을 임의의 숫자로 만들지 않는다. 문서에 수치 위험 한도가 없으면 ‘미제시’로 기록한다. 공통 실행 조건은 비중의 비음수와 합계 1이며 주식부문 예산을 배분한다. 위험은 수익률 하락 여부 하나로 채점하지 않고 공통 과거자료에서 계산한 변동성, 집중 및 상관 구조를 토대로 설명하게 한다. 변동성은 손실 확률과 다르고, 이 값이 낮다고 전략이 더 적절하다고 단정하지 않는다.</p>
<h3>4.3. 업무 절차와 계산 비교</h3>
<p>각 실행은 ① 시장·문서 해석 ② 대안·위험 비교 ③ 잠정 비중 제안 ④ 최종 재검토의 네 단계다. R1은 첫 단계에서, R4는 마지막 단계에서만 기관 패킷을 받는다. R4의 앞 단계에는 기관의 정체와 기준표를 전달하지 않는다. 시장정보와 공통 제약은 처음부터 동일하며, 공개된 문서와 이전 응답의 대화 이력을 유지한다. 마지막 단계에는 양 조건에 같은 외부 사실이 주어지지만 앞선 판단과 계산 피드백은 경로에 따라 달라질 수 있다.</p>
<p>각 단계의 제출 비중을 같은 계산기가 검사하고 다음 단계 전에 결과를 돌려준다. 비중 합계, 허용 산업, 공통 기준 대비 비중 변화, 과거 공분산에 따른 위험을 계산한다. 기관 문서의 의미를 대신 해석해 정답 비중을 만들거나 자동으로 수정하지 않는다. 도구는 이미 공개된 근거와 모델이 제출한 조건만 받는다. 숨겨진 평가 기준표나 R4에 아직 공개되지 않은 제약을 조회하지 않는다. 최종 제안은 수정 전 상태로 저장한다. 이렇게 계산은 AI 양 조건의 공통 지원 도구이고, <strong>주된 대조는 R1 대 R4</strong>다. 계산기 자체를 완전한 기관 전략의 정답 대조군으로 사용하지 않는다.</p>
<p>본과제의 최소 사례 묶음은 출처 2개 × 절차 2개로 네 실행이며, 예비 묶음도 네 실행이다. 실행 하나에 네 모델 응답을 요청한다. 이 수는 준비한 자료의 구성에서 나온 운영 규모이며 논문에서 검정력을 보장받은 표본 수가 아니다. 11개 산업이나 네 단계 응답을 독립 기관 표본으로 세지 않는다. 앞선 시점 문서를 쓰는 예비과제에도 같은 시장 입력을 주어 형식을 점검하므로 예비과제는 과거 운용 재현이 아니다. 동일 기관의 유사 문장을 포함해 예비·본과제 간 독립성에도 한계가 있다.</p>
<h3>4.4. 평가 항목과 해석</h3>
<p>평가는 단일 가중 점수로 합치지 않는다. 첫째, 허용 산업 11개를 모두 명시하고 유한한 비음수 비중의 합계가 1인지 확인한다. 0%를 쓰는 것은 허용한다. ‘종목 존재 여부’는 여기서 ‘허용 산업 식별 및 누락 여부’로 바뀐다. 둘째, 출처별 11개 원문 평가 단어를 정확하게 보존했는지 계산한다. 오류·누락·중복은 분모에서 제거하지 않는다. 이 수치는 문서 해석의 기계적 정확도이며 전략의 품질 점수가 아니다. 인용 ID와 해당 산업의 연결도 별도로 확인하되, 인용이 있다는 사실만으로 문장의 의미가 원문과 일치한다고 판정하지 않는다.</p>
<p>셋째, 각 산업의 제안 비중에서 공통 기준 비중을 뺀 값을 기록한다. Fidelity의 Overweight/Underweight와 부호가 맞는지 연속값으로 제시하되, 이는 그 견해를 채택했을 때의 경향 진단이다. Neutral은 정확한 기준 비중을 강제하지 않고 UBS Attractive는 Overweight로 변환하지 않는다. 문서의 판단과 다른 배분도 위험·분산 또는 다른 공개 근거로 정당화될 수 있다. 따라서 정성 근거를 읽는 검토에서 ‘원문이 지지함·모순됨·원문에 없음·판단 유보’를 구분하며, 이 검토는 사람이 완료한 결과로 가장하지 않는다.</p>
<p>넷째, 같은 출처의 R1/R4 비중 차이와 같은 절차 안의 두 출처 비중 차이를 d(w,v)=½Σ|w−v|로 기록한다. 이 거리식은 PortBench의 비중 비교에 사용된 형태이며 여기서는 정답 근접도가 아닌 기술적 거리로 활용한다. 두 비중이 모두 유효할 때만 계산하고 누락을 거리 0으로 바꾸지 않는다. 기관 간 거리가 줄어도 원문 판단과 선택 근거가 보존되면 해로운 동질화라고 부르지 않는다. 전략과의 연결은 등급 복사 점수 하나가 아니라 판단→근거→비중의 연쇄에서 검토한다.</p>
<p>유효성·원문 등급·인용 범위·비중 거리의 계산식과 실패 처리는 구현했다. 의미 검토 기준을 포함한 최종 평가규칙은 예비 응답을 점검한 뒤 본 응답을 보기 전에 해시와 함께 동결한다(Nosek et al., 2018). 결과를 보고 새 지표·제외 규칙을 추가하면 탐색적 분석이라고 표시한다. JSON 실패나 출력 길이 초과는 자동 재질문으로 숨기지 않고 원문과 실패를 보존한다. 아직 실행하지 않은 작업은 관측된 AI 오류와 구분한다.</p>
<h3>4.5. 수치 보조 과제와 모델 조건</h3>
<p>정확한 비중 일치는 독립 목적함수가 있는 보조 과제에서 확인한다. 공개 FF12의 2024년 1월–2025년 12월 24개 기준월, 각각 직전 60개월, γ=1·3·5를 이용해 Uγ(w)=μᵀw−γwᵀΣw/2를 최대화하는 72개 기준 답을 준비했다. 기간은 PortBench QA 평가 연도, 추정 길이와 γ는 Salcher 등(2026)에 근거한 연구자 조합이다. 원 논문과 달리 비음수 조건을 더한 응용이며 실제 기관의 γ 추정이 아니다. 72개 해의 KKT 및 독립 계산 검증을 통과했다. 이는 AI 실행 결과가 아니고 문서 과제의 전략적 타당성을 대신 입증하지 않는다. 인접 창의 중첩과 수정 데이터의 한계도 유지한다.</p>
<p>목표 모델은 PortBench에서 평가한 Qwen3.6-35B-A3B이며 temperature=0, 최대 출력 8,192토큰, thinking 활성화를 따른다. 현재 컴퓨터에는 해당 모델이 설치되어 있지 않다. 실행 전 모델 파일 해시·양자화·대화 템플릿·엔진 버전·문맥 길이를 기록해야 한다. 작은 설치 모델로 바꾼 결과를 같은 논문 조건이라고 보고하지 않는다. 본과제용 실행기·사후 평가기는 준비했으며 실제 AI 예비·본실험 응답은 아직 0건이다.</p></section>'''

plain='''<section id="plain"><h2>실험을 처음부터 끝까지 설명하면</h2>
<p>이번 실험에서 AI는 미국 주식에 배정된 돈을 11개 산업 바구니에 나눠 담는 담당자다. 예를 들어 금융 바구니와 헬스케어 바구니에 각각 얼마를 배정할지 정한다. 삼성전자나 애플 같은 개별 회사를 고르는 과제는 아니다. 바구니 안의 기업을 우리가 고정한 것도 아니다. 실제 섹터 ETF의 공개가격을 시장자료로 사용한다.</p>
<p>먼저 AI에게 모든 산업의 같은 최근 시장자료와 시장 평균에 해당하는 산업 비중을 준다. 그리고 Fidelity 또는 UBS가 산업을 어떻게 보고 있는지 담은 문서를 준다. Fidelity는 유틸리티를 Underweight로, UBS는 Attractive로 평가한다. 하지만 표현의 의미가 달라 곧바로 ‘한 기관은 2%, 다른 기관은 10%가 정답’이라고 정하지 않는다. AI가 각 문서의 뜻을 읽고, 시장자료와 함께 고려해 자기 배분을 제안하게 한다.</p>
<p>한쪽 AI는 시작할 때부터 그 문서를 본다. 다른 쪽은 시장자료만으로 잠정안을 만든 다음 마지막에 같은 문서를 받는다. 둘 다 해석하고, 대안을 비교하고, 잠정 비중을 만들고, 마지막으로 재검토한다. 중간마다 같은 계산기가 비중 합계와 위험 수치를 알려주지만 어떤 기관의 전략이 옳은지 대신 결정하지 않는다.</p>
<p>마지막에 ‘두 답이 얼마나 비슷한가’만 보지 않는다. 문서의 판단을 바꾸어 읽었는지, 올바른 근거를 붙였는지, 기준보다 산업 비중을 늘리거나 줄인 이유가 문서와 연결되는지를 함께 본다. 마지막에 문서를 받은 AI가 앞서 만든 안을 유지하면서 문서까지 잘못 인용한다면 업무 절차의 문제를 의심할 수 있다. 반대로 비슷한 비중이라도 근거를 충실히 반영했다면 동질화의 실패라고 하지 않는다. 이것이 학술제의 ‘AI가 조직의 의사결정을 어떻게 바꾸며 어떤 절차로 대응할 것인가’와 연결되는 부분이다.</p></section>'''

limits='''<section id="limits"><h2>7. 한계와 후속 연구</h2>
<p>두 공개 전망은 기관 전체의 전략을 대표하는 표본이 아니다. Fidelity 전략가와 UBS CIO라는 서로 다른 조직단위·평가척도·관측일이 결합되어 있다. 기관별 근본적 선호의 차이나 시장 전체의 알고리즘 동질화를 식별하지 않는다. 두 출처와 한 시장 입력은 기술적 사례연구에 적합하며 통계적으로 일반화 가능한 효과 크기·유의성을 보장하지 않는다.</p>
<p>문서는 연구자가 선별·요약했고, 평가 단어도 명시되어 있다. 따라서 실제 보고서의 복잡성, 장문 검색, 사적정보 처리보다 쉬울 수 있다. 같은 기관의 이전 문서를 예비과제로 쓰므로 내용이 완전히 독립적인 검증도 아니다. Fidelity 판단표의 날짜 오타, 공통 벤치마크의 반올림, ETF와 전략가의 미국 3,000종목 분석 범위 차이, 공급자가 수정한 과거 가격을 모두 기록한다. 자료의 원문 해석을 독립적으로 검토하는 절차가 남아 있다.</p>
<p>정성적 산업 전망에는 유일한 정답 비중이 없고, 근거에 맞는 비중 범위도 직접 주어지지 않는다. 자동 채점은 등급·식별자·산술·인용 위치를 확인하며 자유서술의 의미를 보증하지 않는다. 인간 검토 또는 검증된 별도 판정 절차 없이 인용 일치율을 전략의 충실도로 확대 해석할 수 없다. 특정 산업 비중이 0이라는 사실도 자동으로 판단 누락을 뜻하지 않는다.</p>
<p>R1/R4는 정보 제공 시점, 대화 내 위치, 이후 활용 기회를 함께 바꾼다. 최종 외부 사실은 같아도 모델이 만든 이력과 계산 피드백은 다를 수 있다. 따라서 기억·고착을 단독 원인으로 결론내리지 않는다. AI를 쓰지 않는 비교집단이나 서로 다른 모델의 집단이 없으므로 공통 AI 도입 자체의 인과효과도 식별하지 않는다. 직접 제공한 근거의 사용을 검증하며 실제 RAG 검색 성능을 주장하지 않는다.</p>
<p>주식·채권·현금의 전체 배분, 개별 종목 선택, 실제 기관의 사적정보·위험 한도, 미래 수익률은 검증 범위 밖이다. 수치 보조 과제의 최적해도 주어진 과거 추정치에 조건부다. 이런 한계 안에서 본 사례는 투자판단이 문서에서 제안 비중으로 전달되는 절차를 구체적으로 기록한다는 의미를 가진다. 관측 결과가 나오기 전에는 어느 절차의 우월성도 주장하지 않는다.</p></section>'''

conclusion='''<section id="conclusion"><h2>8. 결론</h2>
<p>공통 AI 아래에서 기관별 판단이 보존되는지를 검토하려면 답변의 유사성보다 출처의 판단, 그 판단을 사용한 설명, 최종 배분 선택을 연결해야 한다. 본 연구는 공개 산업전망과 미국 11개 산업 바구니로 이 연결을 관찰하는 실험 전 사례 설계를 마련했다. 처음부터 근거를 제공하는 절차와 마지막에 제공하는 절차에 동일한 계산 지원을 적용한다.</p>
<p>문서·시장 입력·실행기·기계적 평가기는 준비했으나 실제 모델 응답과 독립적인 사람 검토 결과는 아직 없다. 예비 실행과 평가규칙 동결 후에도 두 문서 사례의 결과를 전체 기관의 전략이나 시장 위험으로 일반화하지 않는다. 상경·경영학적 기여는 공통 기술을 쓰는 조직이 고유한 판단 근거를 최종 결정에 전달하도록 업무 절차와 검토 책임을 어떻게 구성할지 분석하는 데 있다.</p></section>'''

candidates='''<section id="candidates"><h2>남은 선택과 권고</h2>
<table><thead><tr><th>선택이 필요한 부분</th><th>후보와 이유</th><th>현재 처리</th></tr></thead><tbody>
<tr><td>실제 모델 실행 환경</td><td><strong>Qwen3.6-35B-A3B를 실행할 GPU 서버</strong>: 모델 파일·엔진을 고정하기 좋으나 접근 가능한 서버와 비용 조건이 필요하다. <strong>현재 PC의 Ollama</strong>: 같은 35B 모델의 Q4_K_M 버전은 약 23GB 추가 다운로드가 필요하며 현재 약 32GB RAM 환경의 메모리 여유·속도를 실측해야 한다. 양자화는 논문 조건의 구현상 변경으로 기록한다.</td><td>모델 종류는 유지. 논문 설정에 가까운 재현을 우선하면 GPU 환경을 권고한다. 현재 실행기는 Ollama용이며 서버 선택 시 서버 어댑터 확인이 추가로 필요하다. 소형 설치 모델은 기술 점검용 후보일 뿐 본실험 대체로 자동 선택하지 않는다.</td></tr>
<tr><td>소논문의 주장 범위</td><td><strong>두 기관 문서의 사례연구</strong>: 현재 자료로 출처의 판단과 업무 절차를 구체적으로 분석할 수 있다. <strong>여러 시점·기관으로 확장</strong>: 일반화 범위를 늘릴 여지가 있으나 같은 평가척도와 공개 시점의 자료를 추가 확보해야 하고, 독립 사례 수는 별도 설계가 필요하다.</td><td>현재는 사례연구로 작성했다. 확대를 위해 임의로 ‘30회면 충분’ 같은 수를 만들지 않았다. 기존 소논문의 조직 의사결정 문제의식은 유지한다.</td></tr>
<tr><td>판단 설명의 의미 평가</td><td><strong>원문을 보는 독립 검토자</strong>: 원문이 지지하는 설명인지 판단하고 이견을 기록할 수 있다. <strong>별도 모델 판정</strong>: 자동화에 유리하나 판정 모델의 편향과 타당성 검증이 추가로 필요하다.</td><td>원문·빈 검토지·기계적 기준표를 준비했다. 사람 검토 완료로 표시하지 않았으며, AI 판정기를 임의 도입하지 않았다.</td></tr>
</tbody></table><p>산업 분류·기관 자료·위험계수의 처리·기준 비중·R1/R4 비교·계산 지원·자동 평가 방식은 더 이상 선택을 미루는 항목이 아니다. 실행 환경 선택과 실제 예비 검토가 끝나면 본과제 입력·평가기준·모델 버전을 함께 동결한다.</p></section>'''

appendix='''<section id="appendix"><h2>부록. 준비 산출물과 재현 순서</h2>
<p>완료한 산출물은 <a href="../data/sector_documents/corpus_card.json">4개 문서의 코퍼스 카드</a>, <a href="../data/sector_market/market_input.json">공통 시장 입력</a>, <a href="../data/sector_protocol/evaluation_spec.json">평가 규칙</a>, <a href="../data/sector_protocol/workflow_manifest.json">실행 목록</a>, <a href="../data/sector_documents/blind_review_worksheet.html">독립 추출 검토지</a>다. 원문 PDF·가격 응답·해시는 보존한다. <a href="../research/design_revision_20261017/parameter_basis_v42.json">수치·식·연구 운영 결정의 근거 대조표</a>에서 논문 직접값, 연구자 응용, 출처 관측값, 산술 허용오차를 구분했다.</p>
<p>실행 순서는 자료 준비 → 계산·정보경계 검사 → 실제 예비 실행 → 원문·설명 검토 및 평가규칙 확정 → 입력·모델·규칙 해시 동결 → 본과제 실행 → 독립 사후 채점이다. 지금은 실제 예비 실행 전까지 준비했다. 자동 검증은 연구 설계 전체나 자유서술 평가의 타당성을 인증하지 않는다.</p>
<pre>python research/prepare_sector_documents.py
python research/prepare_sector_market.py
python research/run_sector_workflow.py prepare
python research/run_sector_workflow.py verify
python -m unittest discover -s research -p test_sector_engine.py
python research/run_sector_workflow.py preflight
# 실행 가능한 모델 버전 고정 후:
python research/run_sector_workflow.py run --split pilot --runtime data/sector_protocol/runtime_candidate.json --output data/sector_runs/pilot_001
python research/evaluate_sector_runs.py data/sector_runs/pilot_001
# 실제 예비 검토 기록을 작성한 뒤 freeze, 이후 --split main으로 실행.</pre>
<p>2026년 11월 1일 텀페이퍼, 11월 6일 발표 일정과 APA 인용을 따른다. 확인한 개요에 없는 분량·파일형식·자체 결과 필수 여부를 임의로 정하지 않았다. 저자·소속은 제출 전에 기입해야 한다. 이 파일은 결과를 꾸며 넣지 않은 문헌 검토 및 실험 전 소논문이다.</p></section>'''

def replace(soup,sid,html):
    tag=BeautifulSoup(html,'html.parser').find('section')
    old=soup.find(id=sid)
    if old:old.replace_with(tag)
    else:soup.find('article').append(tag) if soup.find('article') else soup.find('main').append(tag)

cfg=read(archive(CONFIG));cfg['protocol_version']='4.2';cfg['status']='materials_and_software_prepared; awaiting_target_runtime_and_actual_pilot; no_AI_results'
cfg['research_question']='Does a common AI preserve source-specific public sector judgments in justified equity-sector allocations, and how does early versus late evidence provision change that reflection?'
cfg['main'].update({'status':'data_and_software_prepared; pilot_not_run; main_not_frozen','taxonomy':{'finalized':True,'selected':'GICS 11','sector_codes':['10','15','20','25','30','35','40','45','50','55','60'],'no_FF12_conversion':True},
 'period':{'recent_only':True,'finalized':True,'common_cutoff':'2026-07-17','price_last_date':'2026-07-16','claim':'retrospective document-conditioned case, not point-in-time trading replay','fidelity_invalid_view_date_preserved':'6/31/26'},
 'main_documents':['fidelity_q3_2026','ubs_july_2026'],'pilot_documents':['fidelity_q2_2026','ubs_june_2026'],
 'representation':'Researcher-selected short paraphrased evidence, original labels, source IDs and page locators; not full-document retrieval.',
 'baseline':'Reported 2026-06-30 S&P500 sector weights, sum99.9%, original preserved and normalized for common arithmetic; not institution holdings/targets',
 'calculation':'Implemented pure calculator; automatic same feedback between stages; no repair or hidden-reference access',
 'paths':{'documents':'../data/sector_documents/corpus_card.json','market':'../data/sector_market/market_input.json','calculator':'../research/sector_engine.py','runner':'../research/run_sector_workflow.py'},
 'pending':['target runtime selected, installed and version pinned','actual pilot and independent semantic/source review','pre-main rubric and input freeze','main responses and offline evaluation'],
 'gold_visibility':'Offline provisional references mechanically cross-checked; independent human review pending; never read by online runner.'})
cfg['workflow'].update({'planned_main_case_count':4,'planned_pilot_case_count':4,'calls_per_complete_case':4,'inference':'descriptive case study; two source documents, not powered population experiment','same_final_facts':True,'same_generated_history':False})
cfg['evaluation'].update({'status':'mechanical_spec_and_scorer_implemented; semantic_review_pending; freeze_after_pilot_before_main','spec':'../data/sector_protocol/evaluation_spec.json','primary_rating_scope':'source label preservation only, not strategy quality','no_exact_weight_gold_for_documentary_task':True,'semantic_categories':['supported','contradicted','not_stated','uncertain'],'semantic_scoring_automated':False})
cfg['model']['runtime_ready']=False;cfg['model']['runtime_candidate']='../data/sector_protocol/runtime_candidate.json'
cfg['results']={'ai_runs':0,'human_runs':0,'main_execution_ready':False,'material_preparation_complete':True,'software_tests_only':True}
cfg['previous_protocol']='archive/LIBERA_실험설정_v4.1.json';write(CONFIG,cfg)

paper=BeautifulSoup(archive(PAPER).read_text(encoding='utf-8'),'html.parser')
paper.h1.string='공통 생성형 AI는 기관별 투자판단을 보존하는가?'
paper.title.string='공통 생성형 AI는 기관별 투자판단을 보존하는가?'
paper.find(class_='eyebrow').string='LIBERA 2026 · TERM PAPER · VERSION 4.2'
paper.find(class_='subtitle').string='공개 산업전망과 근거 제공 시점에 관한 산업 배분 사례 설계'
abstract=paper.find(class_='abstract').find('p')
abstract.string='공통 생성형 AI가 기관별 투자판단을 최종 권고에 반영하는가는 답변의 유사성만으로 판단할 수 없다. 본 연구는 알고리즘 동질화와 금융 AI 문헌을 검토하고, 미국 11개 GICS 산업군에 대한 공개 전망과 시장자료로 실험 전 사례 설계를 제시한다. Fidelity 전략가와 UBS CIO의 판단을 연구자가 정리한 근거 패킷을 사용하며, 문서를 처음부터 제공하는 절차와 마지막에 제공하는 절차를 동일한 모델·계산 지원 아래 비교한다. 원문 평가의 보존, 인용 범위, 배분 근거와 산업 비중을 분리해 관찰하고 정성 전망에 유일한 정답 비중을 부여하지 않는다. 정확한 수치 실행은 별도의 FF12 보조 과제로 검증한다. 자료·실행기·기계적 평가기를 준비했으나 실제 AI 응답과 독립 사람 검토 결과는 없다. 두 문서 사례로 전체 기관 전략이나 공통 AI 도입의 인과효과를 일반화하지 않으며, 연구의 기여는 조직의 판단 근거가 최종 배분에 전달되는 절차를 검토하는 데 있다.'
for sid,body in [('framework',framework),('design',design),('limits',limits),('conclusion',conclusion),('appendix',appendix)]:replace(paper,sid,body)
for p in paper.find(id='intro').find_all('p'):
    if '본실험의 원자료·분류·평가규칙은' in p.get_text():p.string='원제안서의 산업 배분 단위를 유지하면서, 공개 산업 판단이 선택에 반영되는 문서 사례와 명시적 목적을 계산하는 보조 과제를 구별한다. 11개 GICS 산업과 실제 공개자료, 실행·평가 도구를 준비했으며 실제 모델 예비 실행과 기준 확정이 남아 있다.'
    if '경제학적으로는 선호와 위임' in p.get_text():p.string='경제학적으로는 서로 다른 정보와 판단에 따른 자원 배분의 문제이며, 경영학적으로는 AI를 사용하는 업무에서 근거 전달과 재검토를 조직하는 문제다. 이번에 확보한 자료는 기관의 공개 산업 전망이므로 전체 운용목적이나 고객 위험선호의 측정으로 확대하지 않는다. 이하에서는 상반된 선행연구, 조작적 정의, 공개자료, 반론 및 대응 방향을 연결한다.'
paper.find(class_='abstract').find(class_='small').clear();paper.find(class_='abstract').find(class_='small').append('주제어: 생성형 AI, 산업 배분, 기관별 투자판단, 알고리즘 동질화, 업무 설계')
refs=paper.find(id='references').find('ul')
newrefs=[('ref-quek','Quek, R. W. H., Vittori, E., Ong, K., Mao, R., Cambria, E., &amp; Mengaldo, G. (2025). <i>Leveraging LLMs for top-down sector allocation in automated trading</i> (Version 5) [Preprint]. arXiv. <a href="https://arxiv.org/html/2503.09647v5">원문</a>'),
 ('ref-fidelity26','Fidelity Investments. (2026). <i>Quarterly sector and investment research update: Q3 2026</i> [Strategist report]. <a href="https://clearingcustody.fidelity.com/app/proxy/content?literatureURL=/9906006.PDF">공식 원문</a>'),
 ('ref-ubs26','UBS Chief Investment Office Global Wealth Management. (2026, June 22). <i>UBS House View: Investment strategy guide, July 2026</i>. <a href="https://advisors.ubs.com/mediahandler/media/816396/UBS%20House%20View%20for%20July%202026.pdf">공식 원문</a>')]
for rid,html in newrefs:
    if not paper.find(id=rid):refs.append(BeautifulSoup(f'<li id="{rid}">{html}</li>','html.parser').li)
items=refs.find_all('li',recursive=False)
for item in items:item.extract()
for item in sorted(items,key=lambda x:x.get_text().lower()):refs.append(item)
for el in paper.find_all(string=True):
    corrected=el.replace('필요한 정보 반응과 경제적 품질을 함께 비교','근거 충실성·실행 유효성·과거 위험 진단을 함께 비교')
    corrected=corrected.replace('이번 조작의 직접적인 근거를 제공한다','기관별 입력과 배분 반응을 연결하는 방법론적 선례를 제공한다')
    corrected=corrected.replace('AI의 제안과 계산시스템의 수정 결과','AI의 원안과 계산 피드백을 받은 AI의 후속 제안')
    corrected=corrected.replace('AI의 후속 제안를','AI의 후속 제안을')
    corrected=corrected.replace('v4.1 · 산업 단위 확정 / 문서 본실험 준비 중','v4.2 · 자료·실행·평가 코드 준비 / 실제 예비 실행 전')
    if corrected!=el:el.replace_with(corrected)
PAPER.write_text(str(paper),encoding='utf-8')

plan=BeautifulSoup(archive(PLAN).read_text(encoding='utf-8'),'html.parser')
for sid,body in [('plain',plain),('framework',framework),('design',design),('appendix',appendix),('candidates',candidates)]:replace(plan,sid,body)
for el in plan.find_all(string=True):
    if 'v4.1' in el or 'VERSION 4.1' in el:el.replace_with(el.replace('v4.1','v4.2').replace('VERSION 4.1','VERSION 4.2'))
plan.h1.string='11개 산업으로 진행하는 기관 문서 기반 AI 배분 실험'
for el in plan.find_all(string=True):
    if '산업 단위는 확정, 문서 본실험은 준비 중이다.' in el:
        el.replace_with(el.replace('산업 단위는 확정, 문서 본실험은 준비 중이다.','11개 산업·자료·실행·평가 코드는 준비했다. 실제 모델 예비 실행과 평가규칙 동결은 남아 있다.'))
for a in plan.find_all('a',href=True):
    if a.get_text(strip=True)=='산업 전망 문서 후보':a['href']='../data/sector_documents/corpus_card.json';a.string='선정 문서와 코퍼스'
market=read(ROOT/'data/sector_market/market_input.json')
golds=[json.loads(x) for x in (ROOT/'data/sector_documents/evaluator_only/reference_annotations.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
gold_by_id={g['source_id']:g for g in golds}
names=['에너지','소재','산업재','경기소비재','필수소비재','헬스케어','금융','정보기술','커뮤니케이션','유틸리티','부동산']
table='<h3>실제로 선택할 11개 산업</h3><table><thead><tr><th>산업</th><th>ETF</th><th>공표 시장 기준(%)</th><th>Fidelity Q3</th><th>UBS July</th></tr></thead><tbody>'
for code,name,ticker in zip(market['sector_codes'],names,market['tickers']):
    original=market['benchmark_reported_weights_percent']
    pct=original[code] if isinstance(original,dict) else original[market['sector_codes'].index(code)]
    table+=f'<tr><td>{name}</td><td>{ticker}</td><td>{pct:g}</td><td>{gold_by_id["fidelity_q3_2026"]["sector_ratings"][code]["rating"]}</td><td>{gold_by_id["ubs_july_2026"]["sector_ratings"][code]["rating"]}</td></tr>'
table+='</tbody></table><p>기준 비중은 S&amp;P 500의 2026년 6월 30일 공표값으로 합계가 99.9%다. 계산에는 비례 정규화한 합계 100%의 값을 쓴다. 이 표는 AI에게 요구하는 목표 비중이 아니다. 서로 다른 두 기관의 평가 단어를 같은 의미로 환산하지 않는다.</p>'
for child in list(BeautifulSoup(table,'html.parser').contents):plan.find(id='plain').append(child)
PLAN.write_text(str(plan),encoding='utf-8')

ledger={'version':'4.2','principle':'No unsupported research constants disguised as paper values. Data observations and operational choices are explicitly distinguished.', 'items':[
 {'item':'GICS11 / sector ETFs','kind':'paper_supported_design','basis':'https://arxiv.org/html/2503.09647v5','locator':'section4; Appendix9.3','adaptation':'Our selected US sector ETFs/documents are not the paper sample'},
 {'item':'60 trading-day return window and 252 annualization','kind':'direct_paper_values','basis':'https://arxiv.org/html/2605.27887v6','locator':'AppendixB.2','adaptation':'US sector ETF case rather than 183-series multi-asset benchmark'},
 {'item':'Qwen3.6-35B-A3B; temperature0;8192;thinking','kind':'direct_paper_model_and_settings','basis':'https://arxiv.org/html/2605.27887v6','locator':'section3.1','adaptation':'Exact weights/runtime/quantization not yet pinned'},
 {'item':'half L1 weight distance','kind':'paper_formula_adapted','basis':'https://arxiv.org/html/2605.27887v6','locator':'section2.2','adaptation':'Descriptive distance, not proximity to a unique correct strategy'},
 {'item':'2026-07-17 cutoff; 2sources;4runs;4stages','kind':'LIBERA_operating_design_not_paper_constants','reason':'Document release dates, paired source roster and interpretation-comparison-proposal-reconsideration workflow. No power claim.'},
 {'item':'SP500 sector weights2026-06-30, sum99.9','kind':'observed_official_source_values','basis':'https://clearingcustody.fidelity.com/app/proxy/content?literatureURL=/9906006.PDF','locator':'PDFp2','adaptation':'Divide original percentages by99.9 for a common comparator; not institutional targetweights'},
 {'item':'gamma1,3,5;60monthly;quadratic utility','kind':'direct_paper_values_auxiliary_only','basis':'https://onlinelibrary.wiley.com/doi/full/10.1002/for.70134','adaptation':'Long-only added;2024-25QAyears from PortBench; not true institution risk aversion'},
 {'item':'sum tolerance1e-6;matrix tolerance1e-12','kind':'numerical_engineering_checks','reason':'Serialization and matrix validation, not empirical success thresholds or institution behavior'},
 {'item':'131072context;900second timeout;fixedcallorder','kind':'runtime_engineering_candidate','basis':'https://huggingface.co/Qwen/Qwen3.6-35B-A3B','reason':'128K model-card context recommendation; timeout and schedule not paper research constants'},
 {'item':'separate pilot then freeze; limited content independence','kind':'paper_supported_method','basis':'https://www.pnas.org/doi/10.1073/pnas.1708274114','adaptation':'Same institutions and related wording across vintages. No external preregistration is claimed; local protocol hash lock only'}]}
write(REV/'parameter_basis_v42.json',ledger)
write(REV/'revision_manifest_v42.json',{'version':'4.2','AI_results':False,'files':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (PLAN,PAPER,CONFIG)}})
print('v4.2 plan, term-paper draft, config and parameter ledger written; AI calls=0')
