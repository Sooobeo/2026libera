"""Record the user's A+B1 choice without inventing experimental results."""
from pathlib import Path
from bs4 import BeautifulSoup
import json
import shutil
import hashlib

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'plan'
PAPER = ROOT / 'paper'
plan_path = PLAN / 'LIBERA_실험계획_20261017.html'
paper_path = PAPER / 'LIBERA_텀페이퍼_초안_20261017.html'
config_path = PLAN / 'LIBERA_실험설정_20261017.json'
(PAPER / 'archive').mkdir(exist_ok=True)
snapshots = [
    (plan_path, PLAN / 'archive/LIBERA_실험계획_v3.3.html'),
    (config_path, PLAN / 'archive/LIBERA_실험설정_v3.3.json'),
    (paper_path, PAPER / 'archive/LIBERA_텀페이퍼_초안_v3.3.html'),
]
for src, dst in snapshots:
    if not dst.exists():
        shutil.copy2(src, dst)
paper = BeautifulSoup(snapshots[2][1].read_text(encoding='utf-8'), 'html.parser')
plan = BeautifulSoup(snapshots[0][1].read_text(encoding='utf-8'), 'html.parser')
config = json.loads(snapshots[1][1].read_text(encoding='utf-8'))

def fragment(markup):
    return BeautifulSoup(markup, 'html.parser')

def replace_paragraph(soup, prefix, html):
    matches = [p for p in soup.find_all('p') if p.get_text().startswith(prefix)]
    assert len(matches) == 1, (prefix, len(matches))
    matches[0].replace_with(fragment(html))

def append_section(soup, section_id, html):
    soup.find(id=section_id).append(fragment(html))

paper.find('p', class_='subtitle').string = '공개 펀드 문서와 통제된 거래 과제를 통한 정보 반영 검증'
paper.find('p', class_='meta').string = '문헌 검토와 연구설계 소논문 · 2026년 10월 17일 v3.4 · A＋B1 범위 확정 / 자체 실험 전'
paper.select_one('.status').append(fragment('<p><strong>확정한 수행 범위:</strong> A 공개 펀드 문서 검증과 B1 최소 거래 실험. 실제 펀드의 다산업 배분(B2)은 이번 연구에서 제외하고 후속 연구로 둔다.</p>'))
paper.find('a', string='수정 실험계획 v3.3').string = '확정 범위를 반영한 실험계획 v3.4'

replace_paragraph(paper, 'B1의 권고 후보는', '<p>B1은 Hansen과 Lee(<a href="#ref-hansen">2025</a>, §4)의 환경 I를 바탕으로 수행한다. 공개 거래이력과 가격을 고정하고 두 사적신호가 요구하는 매수·매도 선택을 비교한다. <strong>이는 필요한 신호–행동 구분이 업무 과정에서 보존되는지를 보는 최소 실험이다.</strong> 실제 펀드의 산업별 배분과 복잡한 정보 집계를 검증하는 실험으로 해석하지 않는다. 경제 조건은 논문에서 가져오고, 고정 이력 재생과 제공 시점 처치는 본 연구의 확장으로 표시한다.</p>')
for td in paper.find_all('td'):
    if td.get_text().startswith('I: 사건확률'):
        td.string = 'I: 사건확률 ρ=1, 정보보유 비율 μ=1을 사용한다. II: ρ=0.15, μ=0.95는 합리적 수렴을 다룰 후속 확장으로 이번 주실험에서 제외한다. 원문 §4.2.'

replace_paragraph(paper, '원문은 두 신호에 대한', '<p>한 대화가 한 신호만 받게 하고, 공개 이력과 가격은 정책 사이에 고정한다. 원문의 8회기에서 정상적으로 정보를 반영하는 매수·매도 경로의 길이 0~7 이력을 전수 구성하면 255개 이력이 된다. 각 이력의 두 신호를 짝지어 510개 입력 사례를 구성한다. 이는 논문의 표본 수를 재사용한 것이 아니라 논문 규칙에서 도출한 유한한 평가 목록이며, 전수열거는 LIBERA의 설계다. 보류가 발생하는 실제 AI 시장경로 전체를 포함하지 않는다. 응답 선택에는 보류를 유지한다.</p>')
replace_paragraph(paper, '실험을 쉽게 설명하면', '<p>실험을 쉽게 설명하면, 같은 시장 상황을 보는 분석 담당자에게 서로 다른 추가자료를 주고 AI의 권고가 그 차이에 맞게 달라지는지 확인하는 일이다. 이번 환경에서는 좋은 신호에 매수, 나쁜 신호에 매도가 최적인 만큼 필요한 구분이 명확하다. 관심은 어려운 계산을 풀 수 있느냐보다 이 명확한 구분조차 여러 업무 단계를 거치며 놓치는가에 있다. 서로 다른 신호가 같은 행동을 정당화하는 환경의 검증은 후속 연구로 남긴다.</p>')
append_section(paper, 'design', '<h3>4.5. 고정 이력의 평가와 기본 능력 진단</h3><p>주요 비교는 같은 신호·이력·가격의 R1(첫 단계 제공)과 R4(최종 재검토 직전 제공)다. 자료를 모두 주고 이전 초안 없이 한 번에 답하게 하는 FRESH를 진단 조건으로 추가한다. FRESH는 기본 과제 이해의 기준점이며, 응답 기회가 다른 만큼 R1·R4와 비용이 같은 처치라고 보지 않는다. FRESH에서부터 실패하면 제공 시점 효과와 기초 과제 수행 실패를 구별해 해석한다. 모든 조건의 신호 카드에는 평가용 최적 행동이나 계산된 조건부 기대가치를 넣지 않는다.</p><p>회기별 이력 확률과 해당 이력에서의 신호 확률로 기대이익 손실을 가중한다. 필요한 행동 차이의 보존은 두 신호를 짝지어 이력 확률로 평가한다. 회기별 결과를 우선 보고하고, 전체 요약은 회기에 같은 비중을 두는 평가 대상으로 정의한다. 이 평균 방식도 연구자의 분석 선택이다. 255개 이력이나 510개 입력을 독립적으로 관측한 시장 표본으로 간주하지 않으며, 고정 목록의 기술적 결과와 모델 실행의 변동성을 구분한다.</p><p>사적신호를 아직 받지 않은 단계에서는 근거 부족을 표시할 수 있게 한다. 초기 권고를 반드시 확정하게 하거나 없는 신호를 추정하게 하지 않는다. 최종 단계에서는 세 행동 중 하나와 사용한 근거를 요구한다. 이름 변경과 동일 입력 재생은 구현·출력 안정성을 점검하는 개발 진단이며, 서로 다른 신호가 같은 최적 행동을 요구하는 경제적 대조를 대신하지 않는다.</p>')

replace_paragraph(paper, '최소 거래 과제는 정보 활용을', '<p>최소 거래 과제는 필요한 정보 구분을 명확하게 평가하지만 실제 펀드의 다자산 배분, 위험 관리, 위임계약을 표현하지 못한다. 특히 환경 I에서는 신호별 최적 행동이 단순하므로 복잡한 베이지안 계산 능력이나 합리적 군집행동을 검증했다고 주장하지 않는다. 공개 문서 과제와 거래 과제에서 각각 좋은 성능을 얻더라도 실제 기관의 전략적 이질성이 보존됐다는 증거로 합산할 수 없다. 이번 연구는 이 한계를 인정하고 B2 배분 확장을 후속 과제로 분리한다.</p>')
append_section(paper, 'limits', '<p>과제가 쉬워 모든 조건에서 최적 행동을 선택하는 천장효과가 나타날 수 있다. 이 경우 결론은 ‘해당 모델과 명확한 정보환경에서는 늦은 제공으로 인한 필요한 구분의 소실을 관측하지 못했다’는 범위에 머문다. 일반적인 동질화 위험이나 제공 시점의 중요성이 없다고 단정하지 않는다. 효과가 나오지 않았다는 이유로 본실험 도중 더 어려운 과제나 유리한 모델로 교체하지 않으며, 복잡한 환경의 확장은 별도 설계·보고한다.</p>')
append_section(paper, 'framework', '<p><strong>확정된 연구 기여.</strong> 경제적 최적 행동이 명확한 동일 시장조건에서, 근거의 최초 제공 시점과 후속 검토 기회가 필요한 행동 차이의 보존과 기대이익 손실에 미치는 영향을 검증하도록 설계한다. 공개 문서 과제는 근거 취득의 정확성을, 통제 거래 과제는 제공된 근거의 행동 반영을 평가한다. 이 두 관리 과정을 구분하는 것이 본 연구의 직접적인 기여이며, 실제 펀드의 성과나 시장 안정성 개선은 이 설계가 입증할 결과에 포함하지 않는다.</p>')

for tr in paper.select('#appendix tbody tr'):
    cells=tr.find_all('td')
    if cells and cells[0].get_text()=='본실험의 범위':
        cells[0].string='확정된 범위'
        cells[1].string='A 공개 문서 검증＋B1 최소 거래 실험. 사용자가 2026-10-17 선택했다.'
        cells[2].string='B2 실제 펀드 산업 배분은 이번 제출 범위에서 제외하고 후속 연구로 둔다.'
    elif cells and cells[0].get_text()=='정보 제공 시점':
        cells[0].string='설계에 반영한 비교'
        cells[1].string='R1 대 R4를 주비교로 하고 FRESH를 기본 능력 진단으로 둔다.'
        cells[2].string='R2/R3 중간 단계는 이번 최소 설계에서 제외한다. 이러한 정책 구성은 LIBERA의 설계다.'
    elif cells and cells[0].get_text()=='산업·배분식':
        cells[0].string='이번 연구에서 결정하지 않는 항목'
        cells[2].string='B2 확장 때 선택할 산업·배분식이다. 이번 A＋B1 실험의 선행 조건으로 요구하지 않는다.'
replace_paragraph(paper, '11월 1일까지의 작업 순서는', '<p>11월 1일까지의 작업 순서는 확정된 A＋B1 범위에 따라 공개 문서의 시점·출처 검증 → 거래 기준 답 검산 → 모델·실행 환경 확인 → 개발 진단과 파일럿 → 분석 규칙 고정 → 본실험 → 실제 결과에 맞춘 원고 수정이다. 이는 연구 일정 제안이며 논문에서 차용한 수치 조건이 아니다. 모델 응답을 얻기 전에는 효과·유의성·성공률을 보고하지 않는다.</p>')

# Plan: turn the scope choice into a recorded decision, retaining the other honest gates.
plan.title.string = 'LIBERA 연구계획 v3.4 — A 공개 문서＋B1 최소 거래 실험 확정'
plan.select_one('.eyebrow').string = 'LIBERA · SELECTED SCOPE · VERSION 3.4'
plan.select_one('.meta').string = '2026-10-17 · A＋B1 범위 확정 · 기준 답과 실행 자료 준비 / AI 본실험 전'
for node in plan.find_all(string=True):
    if 'v3.3' in str(node):
        node.replace_with(str(node).replace('v3.3','v3.4'))
plan.header.append(fragment('<p class="decision"><strong>사용자 선택 반영:</strong> 공개 펀드 문서 검증(A)＋최소 거래 실험(B1)으로 진행한다. 이번 B1은 환경 I의 R1/R4 비교와 FRESH 진단을 준비한다. 실제 펀드의 산업 배분(B2), 환경 II와 중간 제공 단계는 후속 확장이다.</p>'))
replace_paragraph(plan, '먼저 논문에 있는', '<p>논문 기반 단일 자산의 매수·매도·보류 과제를 사용한다. 필요한 신호별 행동 차이가 분명한 환경 I를 우선 검증한다. 실제 펀드 문서에서는 운용 규칙과 출처를 정확히 찾고 반영하는지 별도로 확인한다. 신호가 달라도 같은 행동이 합리적인 환경 II는 이번 주실험에 포함하지 않는다. 이 범위에서 관측한 결과를 실제 펀드의 최적 산업 배분이나 시장 전체의 동질화 효과로 확장하지 않는다.</p>')
replace_paragraph(plan, '원제안서의 주제는 선택지로', '<p>원제안서의 정보 보존 문제를 유지하고 <strong>이번 직접 검증 범위는 A＋B1으로 확정했다.</strong> B1은 최적 행동이 명확한 환경에서 신호–행동 구분이 업무 단계에 따라 유지되는지 평가한다. A와 B1의 결과는 구분하여 보고하며, 두 결과를 합쳐 실제 펀드 RAG의 동질화 완화 효과를 입증했다고 주장하지 않는다.</p>')
replace_paragraph(plan, '주된 비교 후보는', '<p>주비교는 R1(처음부터 제공·유지)과 R4(최종 재검토 직전 제공)로 준비한다. 상황 해석 → 선택지 평가 → 권고안 → 재검토의 네 단계는 LIBERA의 설계다. FRESH는 동일 최종 자료로 한 번에 답하는 진단 조건이며, R1·R4와 응답 수를 맞춘 주처치가 아니다. R2/R3는 이번 최소 설계에서 제외한다. 신호를 아직 받지 않은 단계에서는 근거 부족을 표시하도록 허용한다.</p>')
for tr in plan.select('#choices tbody tr'):
    cells=tr.find_all('td')
    if not cells: continue
    label=cells[0].get_text()
    if label=='실험이 뒷받침할 주장':
        cells[0].string='확정: 주장 범위'
        cells[1].string='A＋B1: 공개 근거 처리와 필요한 신호–행동 구분의 보존.'
        cells[2].string='B2는 후속 연구. 이번에는 산업·목표 비중·배분 목적식을 선택하지 않는다.'
    elif label=='업무정책 비교의 폭':
        cells[0].string='구체화: 정책 비교'
        cells[1].string='R1 대 R4＋FRESH 진단. 근거 내용과 최종 정보를 맞춘다.'
        cells[2].string='중간 제공 단계는 이번 설계에서 제외한다. 신규 업무정책 처치임을 명시한다.'
    elif label=='B1의 고정 시장 상황':
        cells[0].string='구체화: 평가 목록'
        cells[1].string='환경 I의 이론적 기준 경로 255개와 두 신호 510개 사례. 8회기 규칙에서 계산한다.'
        cells[2].string='전수열거는 새 설계이며 독립 시장 표본 255개라는 의미가 아니다. 실제 AI가 만든 경로는 포함하지 않는다.'
    elif label in ['B2 또는 계산 부록의 산업','B2의 배분 평가식']:
        tr.decompose()
replace_paragraph(plan, '분량·지정 양식은', '<p>범위 선택은 완료했다. 남은 실무 결정은 모델의 고정 버전·실행 자원과 공개 문서 적격성이다. 실제 AI 실행 전에 입력·출력 규칙과 분석 계획을 동결한다. 산업이나 P/Q 배분식을 이번 본실험을 위한 선택으로 되돌리지 않는다.</p>')
replace_paragraph(plan, '전수열거 후보는', '<p>전수열거 목록은 정상적으로 정보를 반영하는 이론적 경로에 한정된다. 회기별 이력 확률과 신호 확률을 구분해 계산하며, 평균 손실은 실제 신호 분포로 가중한다. 신호쌍의 필요한 행동 차이는 이력 확률로 평가한다. 전체 요약에 회기 동일 비중을 쓰는 것은 LIBERA의 평가 대상 정의이며 원논문의 추정치를 재현한 것이 아니다. 환경 II는 후속 연구로 남긴다.</p>')
replace_paragraph(plan, '실험 전:', '<p><strong>실험 전:</strong> A＋B1 범위 선택은 완료했다. 기준 답·자료 패킷을 검증한 뒤 모델 접근과 실행 조건을 확인하고 개발 진단·파일럿을 수행한다. 본실험 결과를 보기 전에 반복·비용·분석 규칙을 고정한다. 로컬에 설치된 모델이라는 이유만으로 논문 조건을 확인하지 않고 주모델로 대체하지 않는다.</p>')
replace_paragraph(plan, '현재 권고:', '<p class="decision"><strong>확정된 방향:</strong> 문헌·공개 문서 검증＋좁은 B1 실험. 의미는 한계를 적는 데만 있지 않고, 경제적 정답이 명확한 상황에서 정보 전달 정책의 효과를 직접 비교하는 데 있다. 모든 조건이 잘 풀어도 해당 환경의 천장효과를 보고하며, 효과가 나오는 설정으로 본실험을 바꾸지 않는다.</p>')
append_section(plan, 'protocol', '<p>환경 I에서 좋은 신호와 나쁜 신호는 항상 다른 최적 행동을 요구한다. 따라서 이번 결과는 필요한 구분의 보존에 관한 것이며, 복잡한 정보 집계나 합리적 수렴의 판별 능력에 관한 것은 아니다. 실패율과 유효 신호쌍의 비율을 함께 보고하고, FRESH를 포함해 어떤 단계에서 과제 수행이 어려워지는지 진단한다.</p>')

config['protocol_version']='3.4'
config['previous_protocol']='archive/LIBERA_실험설정_v3.3.json'
config['status']='A_plus_B1_scope_selected; reference_and_material_preparation; no_LLM_experiment_run'
config['active_main_experiment']={'modules':['A_public_document_validation','B1_Treatment_I_information_response'], 'state':'preparation_not_run'}
config['user_scope_decision']={'date':'2026-10-17','selected':'A+B1','statement':'전자로 가자','excluded_from_current_scope':['B2_portfolio_allocation']}
config['recommendation']['status']='A+B1 selected by user; operational minimum specified for preparation'
config['recommendation']['conditional_extension']='B2_future_research_only'
config['recommendation']['selected_onset_comparison']=['R1','R4']
config['recommendation']['diagnostic_condition']='FRESH'
config['selection_required']=[r for r in config['selection_required'] if r['stage'] in ['model_and_resources','document_sample']]
config['module_roles']['B2']='out of current scope; future research'
config['module_roles']['C']='optional documentary extension; not required for initial A+B1 claim'
config['B1_protocol']=config.pop('B1_candidate')
b=config['B1_protocol']
b['status']='Treatment I finite reference set selected for preparation'
b['selected_treatment']='I'
b['additional_rational_convergence_layer']='II future research, not in current main scope'
b['main_history_sample']='all 255 ordered BUY/SELL normative prefixes of lengths 0 through 7'
b['sample_size']={'history_states':255,'signal_cases':510,'independent_market_samples':None}
b['sample_size_provenance']='derived finite task count from 8-round paper horizon; enumeration is LIBERA design, not paper N'
b['history_candidates']['I_normative_path_enumeration']['status']='selected for preparation'
b['historical_model_adoption_effect_identified']=False
b['ceiling_interpretation']='no loss observed in this simple information environment; not a conclusion that homogenization risk is absent'
config['workflow_policy']['onset']={'R1':1,'R4':4}
config['workflow_policy']['diagnostic_FRESH']='one final response from full identical information without prior drafts; not a stage-count-matched treatment'
config['workflow_policy']['before_signal']='allow missing-evidence state, never force guessed private signal or premature choice'
config['analysis']['round_summary']='report per-round theoretical-history/signal-weighted results; equal-round grand mean is explicit LIBERA estimand'
config['analysis']['primary_heterogeneity']='paired signal-action distinction within the same fixed history; not institution-level portfolio diversity'
config['analysis']['planned_base_response_opportunities']=4590
config['analysis']['base_count_derivation']='255 histories * 2 signals * (4 R1 responses + 4 R4 responses + 1 FRESH response); excludes repetitions and A module'
config['analysis']['main_call_count']=None
config['gates_before_main']['scope_selected']=True
config['gates_before_main'].pop('B2_heterogeneous_benchmark_if_in_scope',None)
config['gates_before_main']['B1_materials_and_model_frozen']=False
config['runtime_inventory']={
    'checked_on':'2026-10-17',
    'existing_ollama_models':['gemma4:e4b-it-qat','gemma3:4b','qwen3.5:9b','hermes-qwen3.5-4b:latest','qwen3.5:4b'],
    'named_paper_model_installed':False,
    'primary_model_selected':None,
    'note':'inventory only; no generation or model download performed; no API secrets stored'
}

# Only mark preparation work complete when its independently generated artifacts exist.
summary_path=ROOT/'data/hansen/summary.json'
if summary_path.exists():
    summary=json.loads(summary_path.read_text(encoding='utf-8'))
    config['B1_protocol']['reference_artifacts_present']=True
    config['B1_protocol']['reference_summary_path']='data/hansen/summary.json'
else:
    config['B1_protocol']['reference_artifacts_present']=False
materials_path=ROOT/'data/hansen/workflow_manifest.json'
if materials_path.exists():
    materials=json.loads(materials_path.read_text(encoding='utf-8'))
    config['B1_protocol']['workflow_materials_path']='data/hansen/workflow_manifest.json'
    config['B1_protocol']['workflow_materials_generated']=True
for k, rel in [('hansen_reference_summary','data/hansen/summary.json'),('hansen_workflow_manifest','data/hansen/workflow_manifest.json'),('A_source_inventory','data/documentary/source_inventory.json')]:
    p=ROOT/rel
    if p.exists():
        config['artifacts'][k]={'path':rel,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
config['completed']['scope_selected_A_plus_B1']=True
config['completed']['AI_responses']=0

paper_path.write_text(str(paper)+'\n',encoding='utf-8')
plan_path.write_text(str(plan)+'\n',encoding='utf-8')
config_path.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Updated manuscript and protocol to v3.4; A+B1 selected; model experiment not run.')
