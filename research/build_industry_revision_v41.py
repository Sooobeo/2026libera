"""Record the industry-unit decision and separate documentary design from numerical controls.

Preserves the v4 documents and all original proposal files. Does not run AI.
"""
from pathlib import Path
import hashlib
import json
import shutil
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
REV = ROOT / 'research/design_revision_20261017'
PLAN = ROOT / 'plan/LIBERA_실험계획_20261017.html'
PAPER = ROOT / 'paper/LIBERA_텀페이퍼_초안_20261017.html'
CONFIG = ROOT / 'plan/LIBERA_실험설정_20261017.json'


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def archived(path):
    target = path.parent / 'archive' / path.name.replace('_20261017', '_v4.0')
    target.parent.mkdir(exist_ok=True)
    if not target.exists():
        shutil.copy2(path, target)
    return target


for path in (PLAN, PAPER, CONFIG):
    archived(path)
old = json.loads(archived(CONFIG).read_text(encoding='utf-8'))
recent_summary = ROOT / 'data/institutional_recent/summary.json'
recent = json.loads(recent_summary.read_text(encoding='utf-8')) if recent_summary.exists() else None

sources = {
    'sector_task': 'https://arxiv.org/html/2603.22305v1',
    'profiles': 'https://www.ifo.de/DocDL/cesifo1_wp11862.pdf',
    'workflow': 'https://arxiv.org/html/2605.27887v6',
    'raw_vs_repaired': 'https://arxiv.org/html/2608.09988v1',
    'quadratic': 'https://onlinelibrary.wiley.com/doi/full/10.1002/for.70134',
    'french': 'https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_12_ind_port.html',
    'preregistration': 'https://www.pnas.org/doi/10.1073/pnas.1708274114',
    'official_document_template': 'https://www.sec.gov/files/form-n-1a.pdf',
}

config = {
    'protocol_version': '4.1',
    'as_of_date': '2026-10-17',
    'status': 'industry_unit_selected; documentary_main_under_preparation; no_AI_results',
    'previous_protocol': 'archive/LIBERA_실험설정_v4.0.json',
    'user_decision': 'Retain industry-level allocation if construct validity and research meaning are preserved.',
    'decision': {
        'unit': 'equity-sleeve industry/sector allocation',
        'selected': True,
        'reason': 'The original proposal already studies industry weights; allocation across sectors can encode institution-specific judgments without testing individual-stock selection.',
        'sufficiency_condition': 'Document interpretation must affect a genuine allocation choice; changing gamma alone is only a numerical control and does not establish strategic-judgment coverage.',
        'not_a_result': 'This is a design-level adequacy judgment, not a claim that treatment effects or sufficient statistical power have been observed.'
    },
    'research_question': 'Within a common fixed AI, are institution-specific documented objectives, applicable constraints and sector judgments reflected in equity-sector recommendations, and how does early versus late evidence provision change that reflection?',
    'main': {
        'module': 'documentary_sector_allocation',
        'status': 'design_draft; not ready for pilot or confirmatory execution',
        'unit': 'industry/sector basket, not individual stock',
        'taxonomy': {
            'finalized': False,
            'rule': 'Use one common taxonomy matching every included source and market input; no unsupported FF12-to-GICS conversion.',
            'current_numeric_control': 'FF12',
            'documentary_candidate': 'GICS 11 sectors, subject to source and public-return-series alignment',
            'reason': 'Official sector views commonly use GICS, while FF12 has different group boundaries. Choosing industry-level decisions does not prove the two taxonomies are interchangeable.'
        },
        'period': {'recent_only': True, 'finalized': False, 'candidate': 'A matched recent document vintage, with 2026 sector outlooks now being checked; no 2026 document is presented as known in 2024.'},
        'inputs': ['common market evidence in the same sector taxonomy', 'dated institution documents containing relevant objectives, applicable constraints or sector judgments', 'source locations and document identity'],
        'document_roles': 'Legal investment mandates, fund-manager commentary and house research views are distinct evidence types. A house outlook is not silently assigned to an unrelated fund as its mandate.',
        'risk_policy': 'Preserve qualitative preferences; retain only explicitly supported numerical limits, denominators and exceptions. Do not map real-fund prose to gamma.',
        'model_decisions': ['identify relevant document facts', 'compare sector allocation alternatives', 'propose sector weights and explain the evidence supporting departures from a common baseline when one is specified'],
        'gold_visibility': 'Independently reviewed extraction references and evaluator-only annotations are withheld from the evaluated model.',
        'calculation': 'Both arms will receive the same deterministic arithmetic and feasibility-checking facilities. Preserve interpretation, proposed weights, calculator inputs and any repaired weights separately. Tool interface has not yet been implemented.',
        'calculator_information_boundary': 'Tools may use only evidence already exposed in that run and model-submitted inputs. Before R4 receives its institution packet, tools cannot read hidden mandates, evaluator annotations or institution-specific constraints. Missing constraints remain unknown; no automatic gold-based repair, lookup or informative feasibility response is allowed.',
        'no_synthetic_real_facts': 'Do not invent institutional expected returns, confidence, sector caps or exact target weights from qualitative prose.',
        'pending': ['common source taxonomy and market-series mapping', 'same-vintage source eligibility and independent annotation', 'allocation baseline and genuinely discretionary choice definition', 'calculator interface', 'pilot corpus distinct from main corpus', 'primary rubric and scoring implementation']
    },
    'workflow': {
        'arms': ['R1', 'R4'],
        'stages': ['market and evidence interpretation', 'comparison of alternatives and risks', 'provisional sector allocation or pending', 'final reconsideration'],
        'mandate_or_evidence_onset': {'R1': 1, 'R4': 4},
        'same_final_facts': True,
        'same_model_and_calculation_facilities': True,
        'full_history_retained': True,
        'interpretation': 'Evidence-onset and subsequent-use workflow policy, including position and context age; not an isolated memory mechanism.',
        'retrieval': 'Directly supplied evidence first; actual retrieval quality remains a separate extension, not an executed RAG result.',
        'planned_main_case_count': None
    },
    'evaluation': {
        'status': 'candidate_dimensions; final rubric after separate pilot and before main responses',
        'dimensions': ['valid sector identifiers and feasible weights', 'evidence-grounded interpretation', 'explicit constraint compliance before repair', 'document-supported exposure tendencies', 'institution-specific response under matched workflow comparison'],
        'numeric_agreement': 'A unique exact-weight reference is used only for the independent numerical control. Public holdings or qualitative views do not specify universally correct strategic weights.',
        'convergence': 'Similarity alone is not failure. Report whether a convergence accompanies loss of relevant evidence or objective/constraint violations. Do not force differences when source judgments agree.',
        'counterfactuals': 'If constructed, change an explicitly identified condition while keeping others fixed and label these as synthetic task interventions, not real institution history.',
        'post_outcome_additions': 'Allowed only with explicit exploratory labeling; no outcome-informed confirmatory threshold or exclusions.',
        'no_arbitrary_composite_score': True
    },
    'numerical_control': {
        'role': 'auxiliary check of explicit objective implementation; cannot substitute for the documentary strategic task',
        'prepared': recent is not None,
        'path': '../data/institutional_recent/summary.json',
        'reference_months': ['2024-01', '2025-12'],
        'market_windows': 24,
        'lookback_months': 60,
        'input_coverage': ['2019-01', '2025-11'],
        'assets': old['main']['assets'],
        'gammas': [1, 3, 5],
        'institution_cases': 72,
        'objective': old['main']['objective'],
        'constraints': old['main']['constraints'],
        'data_status': 'Revised historical French data; retrospective controlled task, not point-in-time trading reconstruction.',
        'period_provenance': 'LIBERA adaptation: PortBench QA test years 2024-2025 plus Salcher 60-month lookback. Not PortBench pipeline replication.',
        'inference': 'Overlapping fixed cases; no independent-sample or power claim. Shared optima retained. No future returns used.'
    },
    'legacy_v4': {
        'benchmark': '../data/institutional/summary.json',
        'workflow': '../data/workflow/manifest.json',
        'role': 'historical numerical prototype, not the new documentary main task',
        'audit': '../research/audits/verification_v4.html',
        'audit_scope': 'The v4 two-round audit applies to archived v4 files and hashes only; it is not a certification of this revised documentary design.'
    },
    'model': old['model'],
    'submission': old['submission'],
    'sources': sources,
    'claims_not_identified': ['individual-stock selection skill', 'overall stocks/bonds/cash allocation', 'true future optimal portfolios', 'actual private information', 'causal effect of shared-model adoption', 'market-wide convergence or financial stability'],
    'results': {'ai_runs': 0, 'human_runs': 0, 'main_execution_ready': False}
}
write_json(CONFIG, config)

framework = '''<section id="framework"><h2>3. 개념과 연구질문</h2>
<p>본 연구의 의사결정 단위는 <strong>주식부문 안의 산업별 배분</strong>이다. 산업 배분은 특정 기업을 고르는 판단과 구별되지만, 어느 사업 영역에 자본을 더 배정할지 결정한다는 점에서 기관의 투자판단을 관찰할 수 있다. 원제안서 역시 산업별 목표 비중과 변경분을 실증 단위로 삼았다. 따라서 개별 종목 선택으로 확대하는 것이 주제 정합성의 필수조건은 아니다.</p>
<p>다만 기관마다 위험계수만 바꾸고 정해진 식을 풀게 하는 과제는 목적의 수치적 실행을 평가한다. 기관별 근거의 해석과 배분 선택을 다루려면 그 근거가 실제 선택에 작용할 수 있는 문서 과제를 별도로 구성해야 한다. 본 개정은 이를 본실험의 방향으로 정하고, 기존 계산 과제는 보조 검증으로 구분한다.</p>
<p>연구질문은 동일한 시장자료와 공통 AI 아래에서 기관별 문서의 목적·적용 가능한 제약·산업 판단이 최종 산업 배분에 반영되는가, 그리고 근거를 처음부터 제공·유지하는 절차와 최종 검토 때 제공하는 절차가 이 반영을 어떻게 바꾸는가다. 동일한 견해가 합리적인 경우도 있으므로 기관 간 비중의 차이 자체를 성과로 간주하지 않는다.</p>
<p>문서 과제에서는 확인 가능한 근거 누락·왜곡과 제약 위반을 판정하고, 배분 유사성은 별도로 보고한다. 독립적인 목적함수와 최적해가 있는 통제 과제에서만 최적안 대비 손실과 필요한 차이의 반응오차를 계산한다. 두 과제의 결과를 합쳐 실제 기관 전략의 최적성이나 공통 AI 도입 자체의 인과효과를 입증했다고 서술하지 않는다.</p></section>'''

design = '''<section id="design"><h2>4. 연구방법과 준비 상태</h2>
<h3>4.1. 산업 단위의 문서 기반 배분</h3>
<p>공통 시장자료와 기관별 원문을 제공하고, AI가 관련 목적·제약·판단 근거를 확인한 뒤 산업 배분 대안을 비교하여 비중을 제안하도록 설계한다. 단순 숫자 복사를 넘어 어떤 근거가 어느 산업 선택에 작용했는지 관찰할 수 있어야 한다. 산업 수준의 자산배분을 금융 언어모델의 의사결정 과제로 다룬 CN-Buzz2Portfolio(Chen et al., 2026)는 이 분석 단위의 선례다. 다만 중국시장 뉴스 기반 과제를 우리 기관 문서 과제로 옮기는 것은 새 설계이며 해당 연구의 재현이 아니다.</p>
<p>입력 문서는 투자설명서, 운용진 보고서, 기관의 산업 전망 등으로 구분한다. 법적 운용 제약, 특정 펀드의 견해, 운용사 전체 리서치의 견해는 동일하지 않다. 다른 조직단위의 문서를 한 펀드의 위임목적처럼 합치지 않는다. 원문에 없는 위험계수·예상수익률·상한·정확한 목표 비중을 만들어 넣지 않는다. 사람이 검토해 확정할 추출 기준표는 평가용으로 보관하고 AI 입력에서 제외한다. 이 사람 검토는 아직 수행되지 않았으며 자동화된 에이전트 점검과 구별한다.</p>
<h3>4.2. 분류 체계와 최근 시점</h3>
<p>산업 단위는 확정했지만 <strong>문서 본실험의 산업 분류는 아직 동결하지 않았다</strong>. 기존 수치 자료는 12개 FF12 산업이고, 검토 중인 공개 전망은 주로 11개 GICS 섹터다. 두 체계의 경계가 달라 단순 이름 치환을 하지 않는다. 동일 분류의 문서와 공개 시장자료를 연결할 수 있는 후보를 선택한 후 투자 대상을 고정한다. 종목 국적·통화·성장주 특성을 산업 비중으로 임의 환산하는 제약은 제외한다.</p>
<p>문서 과제도 최근 자료로 제한한다. 현재 2026년 기관별 산업 전망이 후보이며, 문서의 기준일·공개일·수정일과 전망의 기간을 구분해 맞춰야 한다. 아직 공통 자료 시점과 사례 수는 확정되지 않았다. 2026년 원문을 2024년 당시 알려진 정보처럼 사용하지 않는다. 기간 축소는 산업 바구니의 구성종목 변경을 없애는 조치가 아니며, 선택한 시기의 결과를 모든 시장 국면으로 일반화하지 않는다.</p>
<h3>4.3. 업무 절차와 계산의 역할</h3>
<p>같은 모델의 네 단계 업무에서 기관 문서를 처음 단계에 제공하는 R1과 마지막 검토 단계에 제공하는 R4를 비교한다. 이후 대화 이력은 유지하고 최종 사용 가능한 자료는 같게 한다. 이는 정보 제공 시점·위치·이후 활용 기회가 결합된 절차 비교다. 실제 검색 성능은 별도 검증 대상이며 직접 제공한 문서만으로 RAG 검색 효과를 입증하지 않는다.</p>
<p>두 조건에 동일한 산술·제약 확인 도구를 제공하는 방향으로 수정한다. AI의 문서 해석, 제안 비중, 계산기에 넘긴 입력, 계산 결과와 수정 여부를 따로 저장한다. 계산기가 고쳐 준 비중만 보고 AI가 지침을 이해했다고 판정하지 않는다(OpenPM; Cai et al., 2026). 도구 인터페이스와 새 본실험 실행 코드는 아직 구현 전이다.</p>
<p>계산 도구도 해당 실행에서 이미 공개된 자료와 AI가 전달한 입력만 사용한다. R4가 기관 문서를 받기 전에는 숨겨진 기관 제약·정답표를 읽거나 이를 이용해 비중을 고치거나 위반 여부를 알려 주지 않는다. 미제공 조건은 모르는 상태로 남겨 도구를 통한 조기 정보 누출을 방지한다.</p>
<h3>4.4. 평가 후보와 사전 확정</h3>
<p>평가 후보는 허용 산업 식별과 비중의 유효성, 원문 해석의 근거성, 명시적 제약 준수, 문서가 지지하는 배분 경향, 기관별 조건 변화에 대한 대응이다. 비중 경향의 방향은 출처로 정당화될 때만 채점하고, 정성적 전망에 없는 정확한 목표 비중을 정답으로 만들지 않는다. 공개 보유비중과의 유사성은 관찰된 배분의 재현 정도이며 유일한 최적 전략의 정확도가 아니다.</p>
<p>별도 예비실험에서 입력·출력·채점의 실행 가능성을 점검한 뒤 주평가지표, 결측·무효 응답 처리와 필요한 허용오차를 본실험 결과를 보기 전에 확정한다. 결과를 본 뒤 추가한 평가는 탐색적으로 표시한다. 파일럿에서 조정한 사례를 독립된 검증 사례로 다시 세지 않는다. 임의의 지표 가중치를 정해 단일 점수로 합치지 않는다.</p>
<h3>4.5. 최근 기간의 수치 보조 과제</h3>
<p>공개 FF12 수익률을 사용한 계산 검증은 2024년 1월부터 2025년 12월까지 24개 기준월로 좁힌다. 각 기준월 직전 60개월만 입력으로 사용한다. 첫 입력은 2019년 1월–2023년 12월, 마지막 입력은 2020년 12월–2025년 11월이다. 미래 수익률은 사용하지 않는다. PortBench의 2024–2025 QA 평가 연도와 Salcher 등의 60개월 추정 길이를 조합한 LIBERA 응용이며 PortBench 동적 과제의 재현은 아니다.</p>
<p>기초 조건은 γ=1·3·5와 Uγ(w)=μᵀw−γwᵀΣw/2, 비음수 비중, 합계 1이다. 24개 시장 입력과 세 목적을 조합한 72개 기준 답을 별도 폴더에 준비한다. 이는 실제 기관의 위험선호 측정치가 아니다. 인접 창은 60개월 중 59개월을 공유하므로 독립표본 수나 검정력을 주장하지 않는다. 같은 최적해가 나온 사례도 제거하지 않는다.</p>
<p>자료는 현재 내려받은 수정본이며 과거 각 월초에 실제 공개된 자료의 복원이 아니다. 따라서 회고적 통제 과제로 부르고 당시 매매 재현으로 설명하지 않는다. 이 과제는 식·단위·계산기·채점의 오류를 확인하는 보조 역할이며, 그 통과로 문서 기반 전략 판단의 타당성이 확보되는 것은 아니다.</p>
<h3>4.6. 완료와 미완료</h3>
<p>산업 단위, 원문 근거와 수치 기준의 역할 구분, R1/R4 비교 방향은 결정했다. 원문 후보와 입력·평가 템플릿을 확보했고 최근 수치 보조 자료를 준비한다. 문서 본실험의 공통 분류·시점·독립 검토표·계산 도구·파일럿·최종 평가규칙은 남아 있다. 자체 AI 실행 및 관측 결과는 아직 없다.</p></section>'''

limits = '''<section id="limits"><h2>7. 한계와 후속 연구</h2>
<p>본 연구는 주식부문 산업 배분에 한정한다. 개별 종목 선택, 기관 전체의 주식·채권·현금 배분, 실제 운용사의 비공개 정보와 모든 제약을 대표하지 않는다. 특히 공개 전망은 특정 조직단위의 판단으로서 위임목적이나 실제 거래와 구별해야 한다.</p>
<p>문서 기반 전략 판단에는 일반적으로 유일한 정답 비중이 없다. 출처·제약·정당화 가능한 반응은 검증하되, 공개 비중과의 차이를 투자 실패로 간주하지 않는다. 수치 보조 과제의 최적해는 지정된 추정치와 목적에 조건부이며 실제 미래 최적 포트폴리오가 아니다. 두 과제의 근거를 합쳐 더 넓은 인과 주장을 만들지 않는다.</p>
<p>최근 기간 제한은 시대적 범위를 줄인다. 짧은 기간에서 얻은 결과를 다양한 경기 국면에 일반화할 수 없고, 겹치는 수익률 창은 독립 시장 사례가 아니다. 수정 데이터와 모델의 과거 정보 학습 가능성도 남는다. 실제 시점 재현을 주장하려면 공개 가능 날짜와 자료 버전을 별도로 확인해야 한다.</p>
<p>R1/R4는 하나의 공통 AI 안에서 근거 전달 절차를 비교한다. 비사용 기관이나 서로 다른 모델을 쓰는 집단이 없으므로 공통 AI 도입의 인과효과를 식별하지 않는다. 제공 시점, 대화 위치, 활용 기회가 함께 달라지므로 기억 손실이나 고착을 단독 기제로 해석하지 않는다. 실제 검색은 아직 포함하지 않았다.</p>
<p>산업 단위를 유지할 수 있다는 개념적 판단과 실제 효과를 탐지할 수 있다는 통계적 주장은 다르다. 문서 간 차이와 과제 난이도를 예비실험에서 확인하고, 모두 같은 권고가 적절하거나 채점할 근거가 부족하면 그 제한을 보고해야 한다. 유의미한 효과나 충분한 검정력을 실험 전에 보장하지 않는다.</p></section>'''

conclusion = '''<section id="conclusion"><h2>8. 결론</h2>
<p>기관의 전략적 판단은 개별 종목뿐 아니라 산업 간 자본 배분에서도 관찰할 수 있다. 본 연구는 산업 단위를 유지하면서 기관별 문서의 근거가 배분 선택에 반영되는지, 그 반영이 업무 중 근거 제공 절차에 따라 달라지는지를 검토하는 방향으로 설계를 정리했다.</p>
<p>문서 해석 과제와 독립적인 정답을 계산할 수 있는 수치 통제 과제는 역할이 다르다. 전자는 공개 근거와 선택의 연결을, 후자는 명시된 목적의 수치적 실행을 평가한다. 어느 한쪽의 성과가 다른 쪽의 타당성을 자동으로 증명하지 않는다. 단순히 비중이 다르다는 사실보다 그 차이가 근거에 부합하고 제약을 지키는지를 함께 평가해야 한다.</p>
<p>이 원고는 문헌 검토와 실험 전 설계를 제시하며 자체 AI 결과를 보고하지 않는다. 공통 분류와 자료 시점을 맞춘 문서 코퍼스, 독립 검토표 및 파일럿을 마련한 뒤 본실험 평가규칙을 확정해야 한다. 학술제 논점과의 연결은 AI를 사용하는 기관이 고유한 목적과 판단 근거를 최종 결정에 반영하도록 어떤 업무 절차를 마련해야 하는가에 있다.</p></section>'''

appendix = '''<section id="appendix"><h2>부록. 이번 선택과 남은 준비</h2>
<div class="table-wrap"><table><thead><tr><th>항목</th><th>결정 또는 상태</th></tr></thead><tbody>
<tr><td>판단 단위</td><td>주식부문 산업 배분으로 확정. 개별 주식 선택으로 확대하지 않음.</td></tr>
<tr><td>산업 분류</td><td>수치 보조는 FF12. 문서 본실험은 동일 분류의 공식 문서·시장자료 확인 후 동결. GICS 11개가 후보.</td></tr>
<tr><td>위험 성향</td><td>실제 문서의 정성 표현과 명시 수치를 보존. γ 임의 환산 금지. 기존 γ는 가상 수치 보조에 한정.</td></tr>
<tr><td>최근 기간</td><td>수치 보조의 기준월은 2024–2025. 문서 본실험은 최근 공통 문서 시점 확인 중이며 아직 확정 전.</td></tr>
<tr><td>계산 도구</td><td>본실험의 두 조건에 동일 도구를 제공하는 설계. 원안과 계산 후 결과를 구분. 새 인터페이스 구현 전.</td></tr>
<tr><td>평가</td><td>후보 항목만 결정. 별도 예비실험 후 본실험을 보기 전에 기준 확정.</td></tr>
<tr><td>검증 기록</td><td>기존 두 차례 검증은 보존된 v4.0 파일에 한정. 개정된 문서 과제가 실행 준비됐다는 증거로 재사용하지 않음.</td></tr>
</tbody></table></div>
<p>제출 일정은 11월 1일 텀페이퍼와 11월 6일 발표이며, 최종 제출 양식과 자체 결과 요구는 확인된 규정의 범위를 넘어 추정하지 않는다. 저자 정보와 최종 문헌 형식은 제출 전에 점검한다.</p></section>'''

plain = '''<section id="plain"><h2>산업 단위에서 무엇을 실험하는가</h2>
<p>서로 다른 기관이 같은 AI에게 주식 투자금을 산업별로 나누는 일을 맡긴다. AI가 보는 시장자료는 같지만 각 기관이 제공한 목적과 판단 근거는 다르다. AI는 문서에서 적용할 내용을 찾고, 어떤 산업에 더 또는 덜 배정할지 비교하여 최종 비중을 제안한다. 원문이 지지하지 않는 숫자는 만들지 않는다.</p>
<p>같은 기관의 문서를 처음부터 받은 경우와 마지막 검토에서 받은 경우를 비교한다. 두 경우에 같은 계산 도구를 제공하고, 문서 해석과 처음 제안한 비중을 계산 결과와 따로 보관한다. 따라서 계산기가 오류를 고친 것을 AI의 해석 성공으로 오인하지 않는다.</p>
<p><strong>산업 단위는 연구 주제에 맞지만, 산업 단위라는 이유만으로 실험이 완성되는 것은 아니다.</strong> 기관별 근거가 선택에 작용하는 과제를 구성하고, 근거·제약 준수와 비중 변화를 함께 보아야 한다. 위험계수만 바꾼 기존 계산 실험은 이를 위한 보조 검증으로 둔다.</p></section>'''

abstract = '''공통 생성형 AI가 기관별 투자 근거를 최종 권고에 반영하는가는 답변 유사성만으로 판단할 수 없다. 본 연구는 금융 AI와 알고리즘 동질화에 관한 문헌을 검토하고, 주식부문 산업 배분을 분석 단위로 삼는 실험 전 설계를 제시한다. 같은 시장자료와 공통 모델 아래에서 기관별 문서를 처음부터 제공하는 절차와 최종 검토에서 제공하는 절차를 비교한다. 원문에 근거한 해석, 적용 가능한 제약의 준수, 배분 경향과 기관별 반응을 구분하여 평가하며, 두 조건의 계산 도구를 같게 두고 AI 원안과 계산 후 결과를 따로 기록한다. 정답 비중이 독립적으로 정의되는 FF12 수치 과제는 최근 24개 기준월의 보조 검증으로 구분한다. 산업 단위의 선택은 확정했지만 문서 본실험의 공통 분류·시점·검토표와 최종 채점 규칙은 준비 중이다. 자체 AI 결과는 없으며, 연구의 해석을 근거 전달과 산업 배분 판단의 연결에 한정한다.'''

paper = BeautifulSoup(archived(PAPER).read_text(encoding='utf-8'), 'html.parser')
for block in (framework, design, limits, conclusion, appendix):
    new = BeautifulSoup(block, 'html.parser').section
    paper.find('section', id=new['id']).replace_with(new)

intro = paper.find('section', id='intro')
for p in intro.find_all('p'):
    if any(word in p.get_text() for word in ('γ', '세 가상', '기준 배분을 독립', '위험선호가 다른', '계수만 다른')):
        p.decompose()
intro.append(BeautifulSoup('<p>원제안서의 산업 배분 단위를 유지하되, 기관별 문서의 근거가 선택에 반영되는 본실험과 명시적 목적을 계산하는 보조 과제를 구별한다. 산업 단위의 범위 결정은 완료했으며, 본실험의 원자료·분류·평가규칙은 예비실험 이전 준비 단계다.</p>', 'html.parser'))
literature = paper.find('section', id='literature')
for p in literature.find_all('p'):
    if 'Salcher' in p.get_text() and '결합' in p.get_text():
        p.clear()
        p.append('Zhao 등(2026)의 PortBench는 기준 배분 유사성, 투자자 조건 준수와 실현 성과를 구분한다. 이는 문서의 목적·근거 반영을 단일 비중 정답과 구분해야 한다는 선례다. Salcher 등(2026)의 목적함수와 위험선호 계수는 FF12 수치 보조 과제에 사용한다. 이 보조 과제가 기관 문서의 전략적 판단 전체를 대표하지는 않는다. 산업 배분의 직접적인 과제 선례인 CN-Buzz2Portfolio(Chen et al., 2026)와 원안·시스템 수정 결과를 구분하는 OpenPM(Cai et al., 2026)을 함께 참고하여 문서 본실험을 설계한다. 이는 서로 다른 연구를 조합한 LIBERA의 설계이며 단일 논문의 재현이 아니다.')
    if '헤지펀드' in p.get_text():
        for text in list(p.find_all(string=True)):
            if 'Chen 등' in text:
                text.replace_with(text.replace('Chen 등', 'Chen·Sialm·Xu'))

paper.find('section', id='alternatives').replace_with(BeautifulSoup('''<section id="alternatives"><h2>5. 반론과 대안적 설명</h2><p>기관의 권고가 비슷해졌다는 사실은 오류의 증거가 아니다. 원문의 관점이 같거나 같은 선택이 제약을 충족하면 수렴은 적절할 수 있다. 반대로 기관 간 차이가 커져도 근거 없는 비중이나 제약 위반을 낳으면 개선이 아니다. 원문에서 확인되는 차이, AI가 반영한 차이, 선택의 근거성을 구분해야 한다.</p><p>계산 실패가 문서 이해 실패로 보일 수 있으므로 공통 계산 도구를 사용하고 입력·원안·수정 결과를 분리한다. 또한 공개된 실제 배분과의 불일치는 기관의 미공개 정보와 시점 차이에서도 생길 수 있으므로 그것만으로 오답이라고 하지 않는다. 명시적 목적함수의 최적값 손실은 수치 통제 사례에만 적용한다.</p></section>''','html.parser').section)
paper.find('section', id='implications').replace_with(BeautifulSoup('''<section id="implications"><h2>6. 조직의 대응 방향</h2><p>초기 근거 제공이 기관 문서의 반영과 제약 준수를 함께 개선한다면, 시장 해석 단계부터 근거를 연결하고 최종 검토까지 유지하는 절차를 검토할 수 있다. 늦은 제공이 더 효과적이면 최종 재검토의 역할을 논의하고, 혼합 결과나 무차이는 그대로 보고한다. 아직 관측 결과가 없으므로 어느 절차도 효과가 확인된 해결책으로 제시하지 않는다.</p><p>실무적 함의는 산업별 비중의 다양성 자체를 높이는 것이 아니라 기관이 위임한 조건과 근거가 결정에 반영되는 과정을 검증하는 데 있다. AI의 제안과 계산시스템의 수정 결과를 분리하면 조직이 어떤 단계에서 검토 책임을 두어야 하는지 분석할 수 있다.</p></section>''','html.parser').section)

paper.select_one('.eyebrow').string = 'LIBERA 2026 · TERM PAPER · VERSION 4.1'
paper.select_one('.subtitle').string = '기관별 공개 근거의 해석과 주식부문 산업 배분 — 실험 전 설계'
abstract_heading = paper.find('h2', string='초록')
abstract_heading.find_next_sibling('p').string = abstract
paper.select_one('footer').string = 'LIBERA · 2026-10-17 · v4.1 · 산업 단위 확정 / 문서 본실험 준비 중 / AI 미실행'
for a in paper.select('a[href*="verification_v4"]'):
    a.string = '이전 v4 수치 설계의 검증 기록'
for a in paper.select('a[href*="evidence_ledger_v4"]'):
    a.string = '이전 v4 수치 조건의 근거 대조표'
paper.find('section',id='references').append(BeautifulSoup('''<p>Cai, X., Guo, M., Liu, J., Han, J., Guo, B., Long, Y., Chen, Y., Wu, B., Metaxas, D. N., &amp; Li, R. (2026). <em>OpenPM: Auditable point-in-time evaluation for LLM portfolio-management agents</em> [Preprint]. arXiv. <a href="https://arxiv.org/abs/2608.09988v1">https://arxiv.org/abs/2608.09988v1</a></p><p>Chen, L., Li, S., Yan, J., Liu, S., Yang, Q., &amp; Li, X. (2026). <em>CN-Buzz2Portfolio: A Chinese-market dataset and benchmark for LLM-based macro and sector asset allocation from daily trending financial news</em> [Preprint]. arXiv. <a href="https://arxiv.org/abs/2603.22305v1">https://arxiv.org/abs/2603.22305v1</a></p><p>Nosek, B. A., Ebersole, C. R., DeHaven, A. C., &amp; Mellor, D. T. (2018). The preregistration revolution. <em>Proceedings of the National Academy of Sciences, 115</em>(11), 2600–2606. <a href="https://doi.org/10.1073/pnas.1708274114">https://doi.org/10.1073/pnas.1708274114</a></p>''','html.parser'))
reference_section = paper.find('section', id='references')
reference_list = reference_section.find('ul')
for p in list(reference_section.find_all('p', recursive=False)):
    if p.get_text().startswith(('Cai,', 'Chen, L.,', 'Nosek,')):
        p.name = 'li'
        reference_list.append(p.extract())
for item in sorted(reference_list.find_all('li', recursive=False), key=lambda x: x.get_text().casefold()):
    reference_list.append(item.extract())
for text in list(paper.find_all(string=True)):
    if 'CN-Buzz2Portfolio' in text and 'Chen et al.' in text:
        text.replace_with(text.replace('Chen et al.', 'L. Chen et al.'))
PAPER.write_text(str(paper), encoding='utf-8')

css = paper.style.get_text()
plan = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>LIBERA 산업 단위 실험계획 v4.1</title><style>{css}</style></head><body><main class="wrap"><div class="eyebrow">LIBERA · INDUSTRY ALLOCATION · VERSION 4.1</div><h1>기관별 근거를 산업 배분에 반영하는 AI 업무 절차</h1><p>2026년 10월 17일 · 산업 단위 유지 결정 · 실험 전 설계</p><div class="callout"><strong>산업 단위는 확정, 문서 본실험은 준비 중이다.</strong> 기존 위험계수별 계산 검증은 보조 과제로 구분했다. 자체 AI 결과와 전략 판단 효과는 아직 없다.</div><nav><a href="../paper/LIBERA_텀페이퍼_초안_20261017.html">소논문 초안</a><a href="LIBERA_실험설정_20261017.json">개정 설정</a><a href="../research/design_revision_20261017/institution_packet_template.json">기관 문서 템플릿</a><a href="../research/design_revision_20261017/sector_document_candidates.json">산업 전망 문서 후보</a><a href="../data/institutional_recent/summary.json">최근 수치 보조 자료</a><a href="archive/LIBERA_실험계획_v4.0.html">이전 v4.0 계획</a></nav>{plain}{framework}{design}{appendix}<section id="references"><h2>이번 개정의 근거</h2><ul>'''
source_labels = {
    'sector_task': 'CN-Buzz2Portfolio (2026): 산업 배분 의사결정 과제',
    'profiles': 'Hornuf 외 (2025): 투자자 프로필과 기업 정보',
    'workflow': 'PortBench v6 (2026): 배분 평가와 기간 구분',
    'raw_vs_repaired': 'OpenPM (2026): AI 원안과 제약 적용 결과의 구분',
    'quadratic': 'Salcher 외 (2026): 수치 보조 과제의 목적함수',
    'french': 'French Data Library: 공개 산업 수익률의 구성 규칙',
    'preregistration': 'Nosek 외 (2018): 탐색과 검증의 구분',
    'official_document_template': 'SEC Form N-1A: 공식 투자설명서 항목',
}
for name, url in sources.items():
    plan += f'<li><a href="{url}">{source_labels[name]}</a></li>'
plan += '</ul><p>논문의 실험 조건, 공식 문서의 관측 사실, LIBERA가 조합한 설계 선택을 구분한다. 기관의 수치를 논문에서 만들어 가져왔다고 표현하지 않는다.</p></section><footer>v4.1 · 과거 v4 검증 기록은 당시 파일에만 적용 · AI 미실행</footer></main></body></html>'
PLAN.write_text(plan, encoding='utf-8')

note_path = REV / 'decision_note.json'
note = json.loads(note_path.read_text(encoding='utf-8'))
note['pending_choice'] = None
note['user_selected_unit'] = 'industry/sector allocation, conditional on construct validity; retained with documentary task requirements'
note['current_authority'] = '../../plan/LIBERA_실험설정_20261017.json (v4.1)'
note['status'] = 'industry_unit_selected; earlier alternatives remain research history'
note['active_protocol_note'] = 'The active plan and paper are now v4.1. Original v4.0 documents are archived; original numerical data and workflow remain historical prototypes. See current_authority for the active design.'
note['period_candidates'][0]['limitations'] = 'Recent evaluation still requires trailing estimation history. FF12 constituents still change. A separate 24-window, 72-case numerical control is now prepared in data/institutional_recent; it is not the documentary main task.'
note['period_candidates'][0]['estimation_history'] = 'Frozen retrospective indexing: for each reference month 2024-01 through 2025-12, use exactly the preceding 60 observation months. Data are currently revised values, not verified historical publication-time availability.'
note['document_recommendation']['unit'] = 'Identify the issuing institution and responsible organizational unit. Use a named fund/share class only for fund documents; distinguish a house research view from a fund mandate.'
note['implementation_state'].update(main_protocol_rewritten=True, new_market_data_downloaded=False)
note['implementation_state']['recent_control_recomputed_from_existing_snapshot'] = recent is not None
write_json(note_path, note)
write_json(REV / 'revision_manifest.json', {
    'version': '4.1', 'ai_runs': 0,
    'files': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (PLAN, PAPER, CONFIG)},
    'archived_v4': [str(archived(p).relative_to(ROOT)) for p in (PLAN, PAPER, CONFIG)],
    'source_roles': sources,
    'scope': 'Industry-unit and documentary-task design update; not completion of the full experiment.'
})
print(json.dumps({'version': '4.1', 'recent_control_prepared': recent is not None, 'ai_runs': 0, 'main_execution_ready': False}))
