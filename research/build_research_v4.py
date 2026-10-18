"""Build the aligned research protocol and pre-experiment term paper.

This builds documents, not AI results. September originals are never modified.
"""
from pathlib import Path
from bs4 import BeautifulSoup
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'plan'
PAPER = ROOT / 'paper'
DATE = '2026-10-17'

for folder, stem, ext in [(PLAN, 'LIBERA_실험계획', 'html'),
                          (PLAN, 'LIBERA_실험설정', 'json'),
                          (PAPER, 'LIBERA_텀페이퍼_초안', 'html')]:
    (folder / 'archive').mkdir(exist_ok=True)
    archived = folder / 'archive' / f'{stem}_v3.5.{ext}'
    if not archived.exists():
        shutil.copy2(folder / f'{stem}_20261017.{ext}', archived)

base = BeautifulSoup((PAPER / 'archive/LIBERA_텀페이퍼_초안_v3.5.html').read_text(encoding='utf-8'), 'html.parser')
css = base.style.get_text() + '''
.wrap{max-width:1080px;margin:auto;padding:42px 30px}body{margin:0;font-family:"Malgun Gothic",sans-serif;color:#203039;background:#fff;line-height:1.85}h1{line-height:1.35;font-size:34px}h2{margin-top:48px}h3{margin-top:28px}a{color:#176b7a}nav{display:flex;flex-wrap:wrap;gap:12px 20px;margin:28px 0}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:12px;border-bottom:1px solid #dce3e7;vertical-align:top;text-align:left}th{background:#f1f5f6}.table-wrap{overflow-x:auto}.callout{padding:18px 22px;border-left:4px solid #237782;background:#f2f7f8}.muted{color:#52646e}.refnote{display:block;font-size:12px;color:#586b74}.toolbar{display:flex;flex-wrap:wrap;gap:18px;margin:20px 0}.pill{font-size:13px;color:#356571}.equation{white-space:normal}footer{margin-top:50px;border-top:1px solid #dce3e7;padding-top:18px;font-size:13px}@media(max-width:650px){.wrap{padding:24px 18px}h1{font-size:26px}th,td{min-width:130px}}@media print{.wrap{max-width:none;padding:0}.toolbar,nav{display:none}h1{font-size:22pt}h2{break-after:avoid}table{font-size:9pt}a{color:inherit}body{font-size:10pt}}
'''

sources = {
    'salcher': 'https://onlinelibrary.wiley.com/doi/full/10.1002/for.70134',
    'portbench': 'https://arxiv.org/html/2605.27887v6',
    'french': 'https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html',
    'hornuf': 'https://www.ifo.de/en/cesifo/publications/2025/working-paper/making-genai-smarter-evidence-portfolio-allocation-experiment',
    'schneider': 'https://doi.org/10.1016/j.frl.2025.107517',
}

config = {
    'protocol_version': '4.0', 'as_of_date': DATE,
    'status': 'main_design_and_public_data_benchmark_prepared; no_AI_experiment_results',
    'previous_protocol': 'archive/LIBERA_실험설정_v3.5.json',
    'active_main_experiment': 'institutional_mandate_conditioned_FF12_allocation',
    'research_question': 'Does a common fixed GenAI model preserve warranted differences in hypothetical institutional equity-sleeve allocation, and how does mandate-onset workflow change that performance?',
    'claim_scope': {
        'institutions': 'hypothetical explicit mandates, not calibrated real funds',
        'heterogeneity_source': 'risk preference gamma in delegated objective; not heterogeneous private forecasts',
        'decision': 'allocation within a fully invested equity sleeve across FF12 industries',
        'identified_comparison': 'early retained mandate versus late mandate under one fixed model; workflow policy including position and context age',
        'not_identified': ['causal effect of shared-model adoption', 'actual retrieval quality', 'real-fund convergence', 'market prices or financial stability', 'realized investment profitability', 'separate causal mechanisms of mandate recognition, memory loss and numerical optimization failure'],
    },
    'main': {
        'assets': ['NoDur','Durbl','Manuf','Enrgy','Chems','BusEq','Telcm','Utils','Shops','Hlth','Money','Other'],
        'data_source': sources['french'],
        'data_vintage': 'local manifest frozen on 2026-10-17; current revised CIZ data, not historical point-in-time vintage',
        'data_period': ['1964-01','2023-12'], 'monthly_observations': 720,
        'training_months': 60, 'reserved_future_months': 36,
        'window_selection': 'all 625 overlapping 60+36 month frames; future 36-month block never passed to model or oracle',
        'market_windows': 625, 'gammas': [1,3,5], 'institution_cases': 1875,
        'return_units': 'monthly decimal excess return; percent values divided by 100 then monthly RF subtracted',
        'mu': 'training sample mean of monthly industry excess returns',
        'Sigma': 'training sample covariance, ddof=1, without shrinkage',
        'objective': 'U_gamma(w)=mu.T@w-gamma/2*w.T@Sigma@w',
        'constraints': ['sum(w)=1','w>=0'],
        'oracle': 'independent constrained optimizer; SPD and KKT certification',
        'paper_basis': {'objective_gamma_data_frame': sources['salcher'], 'long_only_profile_conditioned_precedent': sources['portbench']},
        'adaptation': 'LIBERA combines Salcher quadratic preferences with long-only feasibility; not a published unified protocol replication',
        'reference_not_truth': 'optimizer of the stated estimated objective, not true future returns or a recommended real-world portfolio',
        'same_optimum_cases': 'retain all; classify using common optimum KKT certificates, never force different allocations',
    },
    'workflow': {
        'main_arms': ['R1','R4'], 'diagnostic_arm': 'FRESH',
        'stages': ['interpret provided facts and identify missing mandate', 'analyze market tradeoffs', 'draft provisional allocation or pending', 'fully reconsider and output final allocation'],
        'stage_count_main': 4,
        'mandate_inserted_at': {'R1':1,'R4':4,'FRESH':1},
        'mandate_text_occurrences_per_run': 1,
        'market_inserted_at': 1, 'full_history_retained': True,
        'final_available_facts_identical_within_case': True,
        'allow_pending_before_mandate': True, 'score_final_only': True,
        'new_conversation_per_case_and_arm': True,
        'no_cross_case_history_or_shared_memory': True,
        'model_visible_ids': False, 'evaluator_gold_visible': False,
        'external_search_or_solver_tools': False,
        'execution_order': '625 market-window complete blocks in deterministic hash order; each block contains all three gammas x two policies; gamma order and adjacent paired-policy order hashed independently. FRESH separate diagnostic campaign.',
        'execution_logging': 'retain scheduled sequence, actual timestamps, complete requests/responses, model/backend manifest and any deviation; stop and version a new campaign if model revision changes',
        'interpretation': 'onset, position and retention policy bundle; not isolated exposure-free timing effect',
    },
    'model': {
        'primary_target': 'Qwen3.6-35B-A3B',
        'basis': sources['portbench'], 'basis_locator': 'section 3.1',
        'temperature': 0, 'max_output_tokens': 8192, 'thinking': True,
        'exact_served_revision': None, 'runtime_ready': False,
        'note': 'paper-evaluated target selected; local access and immutable revision must be verified before any run. Do not silently substitute installed smaller models.',
        'backend_settings': 'freeze chat template, quantization, thinking implementation, sampling defaults, context limit, engine version, any seed and model hash in runtime manifest',
        'context_overflow': 'fail and record; no silent truncation or change to output token budget',
    },
    'analysis': {
        'population': 'fixed public-data benchmark, not an independent sample of institutions or market periods',
        'base_passes': 1,
        'base_pass_note': 'LIBERA deterministic-target census; temperature zero does not guarantee backend determinism. No stochastic reproducibility claim.',
        'main_final_outputs_planned': 3750, 'main_response_calls_planned': 15000,
        'fresh_final_outputs_planned': 1875, 'fresh_response_calls_planned': 1875,
        'total_response_calls_planned': 16875,
        'primary_quality': 'direct U_gamma(w_star)-U_gamma(w), by gamma',
        'primary_alignment': '0.5*L1((w_i-w_j)-(w_star_i-w_star_j)), by gamma pair',
        'descriptive_convergence': 'D_star-D_AI, where D=0.5*L1(w_i-w_j); sign alone is not failure evidence',
        'individual_distance': '0.5*L1(w-w_star)',
        'invalid_outputs': 'all-case failure rate; do not repair or assign fake utility. Individual policy contrasts require both answers; institution-pair policy contrasts require all four answers (two gammas x two policies) on the same window. Report planned, valid and excluded counts and invalid-rate asymmetry.',
        'negative_raw_gap_policy': 'retain signed direct gap and raw budget residual; flag tiny negative gaps explained by equality-multiplier times allowed budget mismatch. Do not clip or interpret them as beating the exact simplex optimum.',
        'aggregation': 'per-gamma and per-pair mean, median, full distribution, and paired R4-minus-R1 differences; any all-case average is equal-case descriptive, not social welfare',
        'strata': ['all windows','KKT-certified distinct optimum pairs','KKT-certified shared optimum pairs','numerically unresolved pairs if any'],
        'inference': 'descriptive finite-corpus comparison; no iid standard errors, p-values, power claim or automatic population generalization',
        'claim_rule': 'evaluate mandate-response error, direct utility loss, invalid outputs and signed convergence jointly. Mixed directions are mixed results; no composite score or arbitrary threshold. Complete-case differences describe that subset, not automatically the whole scheduled corpus. Recognizing gamma in prose is diagnostic only; it does not isolate recognition versus calculation failure.',
        'missingness': 'report every scheduled, completed, invalid, transport-failed and overflowed case; never replace a difficult case based on observed output',
        'transport_retry': 'no automatic retries; log failed request, mark missing, resolve infrastructure before a separately versioned full or prespecified resumed run',
        'auxiliary_FRESH': 'one-step full-information diagnostic, not a call-budget-matched causal arm',
    },
    'numeric_implementation': {'feasibility_sum_tolerance':1e-6,'negative_weights_allowed':False,'finite_values_required':True,'normalization_or_clipping':False,'tolerances_are':'engineering precision checks, not paper-derived behavioral treatment values'},
    'module_roles': {'A_public_documents':'contextual evidence and optional separate extraction extension; not actual institution inputs or gamma calibration','B1_Hansen':'auxiliary signal-use diagnostic only','P_Q_legacy':'archived numerical prototypes, not main estimand'},
    'alternatives': [
        {'candidate':'Black-Litterman institution-specific views','decision':'defer','reason':'public evidence does not independently identify per-institution views and confidence; using the tested LLM for gold views is circular'},
        {'candidate':'four real fund mandates converted to FF12 constraints','decision':'defer','reason':'issuer nationality, blue-chip status and denominators cannot be reconstructed from industry returns; gamma cannot be inferred from prose'},
        {'candidate':'full stock/bond/cash portfolio profiles','decision':'future robustness','reason':'closer to total risk choice but requires a different public asset universe and independent benchmark, not an undocumented addition to FF12'},
    ],
    'submission': {'term_paper_due':'2026-11-01','pitch':'2026-11-06','pitch_minutes':[5,10],'citation_style':'APA','source':'https://app.notion.com/p/2026-agent-conference/LIBERA-3e00589711408053a7e5ff9a0c4ba804','length_format_own_results_requirement':'not specified in available overview; do not infer exemption'},
    'results': {'ai_runs':0,'human_runs':0,'benchmark_preparation_only':True},
}

plain = '''<section id="plain"><h2>실험은 실제로 어떻게 진행되는가</h2>
<p>세 투자기관이 같은 AI에게 주식 투자금의 산업별 배분을 맡긴다고 생각하면 된다. 모두 같은 시장자료와 같은 12개 산업을 본다. 그러나 위임한 목표가 다르다. 한 기관은 수익을 얻기 위해 변동을 더 감수하고, 다른 기관은 같은 변동을 더 큰 비용으로 평가한다. 이를 느낌이나 기관 이름으로 표현하지 않고, 논문이 사용한 위험선호 계수 1·3·5를 계약 조건처럼 명시한다. 실제 펀드에 이 숫자를 붙이는 것이 아니라 가상 기관의 목적을 투명하게 정하는 것이다.</p>
<p>먼저 연구자가 공개 수익률로 각 산업의 평균 수익과 함께 움직이는 정도를 계산한다. AI와는 별개의 최적화 프로그램이 이 자료와 기관별 목적에 맞는 기준 비중을 구한다. 따라서 AI가 쓴 설명을 다시 AI에게 채점시키는 구조가 아니다. 여기서 정답이란 미래에 가장 돈을 많이 버는 투자안이 아니라, 실험에서 명시한 목적과 자료에 가장 잘 맞는 배분이다.</p>
<p>그다음 같은 기관의 일을 두 방식으로 맡긴다. R1에서는 기관의 목표를 첫 업무부터 알려 주고 대화에 계속 남긴다. R4에서는 시장 검토와 잠정안 작성까지 진행한 뒤 최종 검토에서 목표를 알려 준다. 목표를 모르는 동안에는 배분을 보류해도 된다. 두 방식 모두 시장 이해, 위험 검토, 잠정안, 최종 재검토라는 네 단계를 거치고, 마지막에는 같은 자료와 목표를 이용해 처음부터 다시 배분할 수 있다. 각 기관·방식의 대화는 독립적으로 시작한다.</p>
<p>최종적으로는 AI가 기관마다 얼마나 다른 답을 냈는지만 보지 않는다. 기관별로 달라야 할 배분 방향을 제대로 반영했는지, 각 기관의 목적에서 얼마나 손해를 봤는지, 비중의 합이나 공매도 금지 같은 조건을 지켰는지를 함께 본다. 목표가 달라도 같은 배분이 최적일 수 있으므로 그런 사례도 그대로 포함한다. 일찍 목표를 알려 주었을 때 필요한 차이를 더 정확히 반영하면서 손실도 작아진다면, 기관별 목표를 업무 초기에 연결하는 절차가 유용하다는 제한된 증거가 된다.</p>
</section>'''

methods = '''<section id="design"><h2>4. 연구방법과 실험설계</h2>
<h3>4.1. 기관의 이름이 아니라 위임목적을 다르게 한다</h3>
<p>본 실험의 기관은 실제 운용사 네 곳의 복제물이 아니라 위험선호가 명시된 세 가상 기관이다. 같은 AI, 같은 시장자료, 같은 투자 가능 산업과 제약 아래 목적함수의 위험선호 계수 γ만 1·3·5로 바꾼다. 이 값은 Salcher 등(<a href="#ref-salcher">2026</a>)의 quadratic utility 포트폴리오 비교에서 가져온다. 정성적인 ‘보수적·공격적’ 설명을 임의의 숫자로 환산하거나 실제 펀드에 귀속하지 않는다. 따라서 측정하는 기관별 차이의 원천은 사적 전망이 아니라 <strong>위임받은 투자목적</strong>이다.</p>
<p>금융기관의 이질성에는 전망·제약·보유자산 등 다른 원천도 있다. 그 전체를 한꺼번에 재현하는 대신, 목적의 차이가 적정 배분의 차이로 이어지는 식별 가능한 경로를 검증한다. 주식·채권·현금의 전체 자산배분이 아니라, 이미 주식에 배정된 투자금 내부의 산업 배분이다. 위험선호 차이를 전체 자산군 선택으로 검증한 연구와 동일한 과업이라고 해석하지 않는다.</p>
<h3>4.2. 공개자료와 기준 배분</h3>
<p>자료는 누구나 접근할 수 있는 Kenneth French Data Library의 12개 산업 포트폴리오와 무위험 수익률이다. Salcher 등의 자료 체계에 맞춰 1964년 1월부터 2023년 12월까지 720개월을 사용한다. 퍼센트 수익률을 소수로 바꾸고 같은 달의 무위험 수익률을 빼며, 과거 60개월의 표본평균 μ와 표본공분산 Σ를 계산한다. 산업은 NoDur, Durbl, Manuf, Enrgy, Chems, BusEq, Telcm, Utils, Shops, Hlth, Money, Other 전체를 사용한다. 특정 산업을 결과에 맞춰 고르지 않는다.</p>
<p>자료의 마지막 36개월을 남기는 기존 60＋36개월 프레임을 한 달씩 옮기면 625개 시장 조건이 나온다. 이 숫자는 검정력 계산이나 논문에서 정한 AI 표본 수가 아니라 공개자료 길이에서 산출한 전수 사례 수다. 뒤의 36개월은 이번 주실험에서 사용하지 않으며, AI와 기준 배분 계산 모두 앞의 60개월에서 나온 μ·Σ만 받는다. 마지막 학습 구간은 2016년 1월–2020년 12월이다. 프레임은 Salcher 등의 연구에서 가져왔지만 이를 고정 AI 평가 코퍼스로 전환한 것은 본 연구의 선택이다.</p>
<div class="equation">U<sub>γ</sub>(w) = μᵀw − (γ/2)wᵀΣw<br>w*<sub>γ</sub> = arg max U<sub>γ</sub>(w), &nbsp; Σ<sub>k</sub>w<sub>k</sub> = 1, &nbsp; w<sub>k</sub> ≥ 0</div>
<p>위 식은 기대수익에서 포트폴리오 분산에 비례하는 위험비용을 뺀 기준이다. γ가 클수록 같은 위험을 더 큰 비용으로 평가한다. 목적함수는 Salcher 등의 식 (6)에 기반하고, 공매도 없이 투자금 전부를 배분하는 제약은 PortBench의 long-only 구성과 연결한다. <strong>Salcher 등의 원래 quadratic 모형은 공매도를 허용하므로, 이번 결합은 LIBERA의 새 응용이지 한 논문을 그대로 재현한 실험이 아니다.</strong> 기관별 목적이 다른 기준 답을 요구할 수 있다는 설계 논리는 PortBench의 투자자 프로필별 평가와도 일치한다.</p>
<p>독립된 수치 프로그램으로 제약을 만족하는 최적해를 구하고 공분산의 양의 정부호성과 최적조건(KKT)을 확인한다. 양의 정부호이면 각 기관의 목적함수는 엄격히 오목하므로 해당 기관의 최적해는 하나다. 다만 기관 사이의 최적해는 같을 수 있다. 예를 들어 모든 위험선호 수준에서 같은 산업의 수익 우위가 충분히 크면 동일한 모서리 해가 최적일 수 있다. 같은 해인지도 최적조건으로 확인하며, 답의 다양성을 확보하려고 이런 사례를 제거하지 않는다.</p>
<p><strong>설계의 수치 작동 확인.</strong> 실제 내려받은 자료로 계산한 1,875개 기준 답은 모두 수치 최적조건 검증을 통과했다. 625개 중 83개 시장 조건에서는 세 기관의 최적 비중이 모두 같았으며 이를 보존했다. 첫 60개월(1964년 1월–1968년 12월)의 기준 배분은 아래와 같다. 이 표는 목적 차이가 배분 차이로 연결되는지 확인한 계산 예시이며 AI 실험 결과나 실제 펀드의 권고 비중이 아니다.</p>
<div class="table-wrap"><table><caption>기준 답의 계산 예시: 표시 비중은 반올림한 %, 정답 파일은 원래 정밀도로 저장</caption><thead><tr><th>가상 기관의 γ</th><th>Enrgy</th><th>BusEq</th><th>Other</th><th>나머지 9개 산업</th></tr></thead><tbody><tr><td>1</td><td>0</td><td>0</td><td>100</td><td>0</td></tr><tr><td>3</td><td>0</td><td>22.85</td><td>77.15</td><td>0</td></tr><tr><td>5</td><td>21.04</td><td>28.62</td><td>50.33</td><td>0</td></tr></tbody></table></div>
<h3>4.3. 제공 시점과 업무 이력의 대응 비교</h3>
<div class="table-wrap"><table><caption>표 1. 같은 기관·시장 조건에서 비교하는 업무 절차</caption><thead><tr><th>구분</th><th>R1: 초기 제공·유지</th><th>R4: 최종 검토 제공</th></tr></thead><tbody>
<tr><td>1. 조건 이해</td><td>시장자료와 기관 목표를 함께 받음</td><td>시장자료만 받고 목표의 부재를 표시할 수 있음</td></tr>
<tr><td>2. 위험 검토</td><td colspan="2">같은 지시로 자료와 불확실성을 검토. 각자 기존 대화는 유지.</td></tr>
<tr><td>3. 잠정안</td><td colspan="2">목표가 있으면 잠정 배분, 없으면 보류 가능. 이 단계는 정답 평가 대상이 아님.</td></tr>
<tr><td>4. 전면 재검토</td><td>처음 받은 목표가 대화에 남아 있음</td><td>동일한 목표 문서를 이때 처음 받음</td></tr>
<tr><td>최종 선택</td><td colspan="2">동일한 사실과 선택지를 이용해 12개 산업 비중을 새로 정함. 이전 잠정안 유지 의무 없음.</td></tr>
</tbody></table></div>
<p>목표 문서는 각 대화에 한 번만 직접 삽입하며 전체 대화를 유지한다. 기관 이름, γ가 드러나는 실행 식별자, 다른 기관의 답과 정답표는 모델에 전달하지 않는다. 네 단계의 과업·모델·출력 한도는 같다. 다만 목표의 토큰 위치, 대화 안에서 머문 기간, 이후 추론에 이용할 기회가 함께 달라진다. 따라서 추정 대상은 <strong>목표를 제공하기 시작하고 이력에 유지하는 업무 정책의 효과</strong>다. 노출과 위치의 영향을 제거한 순수한 시점 효과나 심리적 고착의 단독 효과로 해석하지 않는다.</p>
<p>네 단계는 논문에서 최적이라고 확인한 경험상수가 아니라, 원제안서의 ‘잠정안 이후에도 기관별 근거로 재검토할 수 있는가’를 검증하기 위한 새 처치의 정의다. 금융 모형과 모델 설정의 논문 근거를 이 신규 업무 절차의 효과가 이미 검증됐다는 근거로 바꾸지 않는다. 결과 역시 이 절차에 조건부로 해석한다.</p>
<p>실행은 같은 시장 조건의 세 γ와 두 정책을 여섯 대화의 완전한 묶음으로 구성한다. 시장 묶음 순서, 묶음 안의 γ 순서와 각 기관의 R1·R4 선후는 사전에 고정한 해시 규칙으로 배치하고, 동일 기관의 두 정책은 인접 실행한다. 모든 R1을 끝낸 뒤 R4를 수행하는 식으로 정책과 실행 시기를 겹치지 않는다. 예정 순서·실제 시간·모델 버전·이탈 기록을 보존한다. 각 대화는 별도 세션이며 묶음 간 모델 메모리를 공유하지 않는다.</p>
<p>모든 정보를 한 번에 주는 FRESH를 한 단계 진단으로 추가한다. 이는 모델이 완전한 조건 아래 배분 자체를 수행할 수 있는지 확인하는 보조 비교다. 네 단계 조건과 호출 수가 다르므로 동등 비용의 주 비교군으로 섞지 않는다. 정확한 목표 문서를 직접 제공하므로 이 실험은 검색 이후의 활용을 검증한다. 실제 검색기의 recall이나 RAG 시스템 전체의 성능을 측정하지 않는다.</p>
<h3>4.4. 평가: 필요한 차이와 각 기관의 손실</h3>
<p>기관 i의 최종 AI 비중을 w<sub>i</sub>, 같은 자료와 목적에서 계산한 기준 비중을 w*<sub>i</sub>라 한다. 먼저 각 기관의 목적상 손실 L<sub>i</sub> = U<sub>γi</sub>(w*<sub>i</sub>) − U<sub>γi</sub>(w<sub>i</sub>)를 직접 계산한다. 공매도 금지가 있는 이 모형에서는 비제약 quadratic 해의 단순 거리 항만으로 손실을 대신하지 않는다. 이는 명시한 추정 목적에서의 손실이며 실제 투자 수익의 손실은 아니다.</p>
<div class="equation">D*<sub>ij</sub> = ½‖w*<sub>i</sub> − w*<sub>j</sub>‖₁<br>D<sub>ij</sub> = ½‖w<sub>i</sub> − w<sub>j</sub>‖₁<br>E<sub>ij</sub> = ½‖(w<sub>i</sub> − w<sub>j</sub>) − (w*<sub>i</sub> − w*<sub>j</sub>)‖₁<br>G<sub>ij</sub> = D*<sub>ij</sub> − D<sub>ij</sub></div>
<p>D*는 기관별 목적이 요구하는 기준 차이, D는 실제 AI 답의 차이다. E는 단지 차이의 크기뿐 아니라 어느 산업의 비중을 어떻게 달리해야 하는지도 맞게 반영했는지 측정한다. G가 양수이면 기준보다 답이 더 가까워졌다는 뜻이지만, 그 부호 하나만으로 해로운 동질화라고 판정하지 않는다. E, 기관별 L, 제약 위반을 함께 확인한다. 반대로 답이 더 달라졌더라도 목적상 손실이 커지면 개선으로 보지 않는다. 이 지표 조합은 본 연구가 정의한 측정 체계이며 논문에서 검증된 단일 종합점수를 가져온 것이 아니다.</p>
<p>최종 답은 유한한 12개 비중, 음수 없음, 합계 1을 요구한다. 합계의 10<sup>−6</sup> 허용 오차는 수치 출력의 반올림을 다루는 구현 기준이다. 논문에서 정한 행동 조건이나 경제적 유의성 기준이 아니다. 자동 정규화나 음수 잘라내기는 하지 않는다. 허용 오차 안에서도 합계가 정확히 1이 아니면 직접 계산한 목적함수 차이가 작게 음수가 될 수 있다. 원래 비중의 합계 잔차와 부호 있는 차이를 남기고, 기준해의 예산 제약 승수로 설명되는 수치 오차인지 표시한다. 음수를 0으로 잘라내거나 최적해보다 좋은 투자 성과로 해석하지 않는다.</p>
<p>형식 오류·미응답·제약 위반 비율은 모든 예정 사례를 분모로 보고한다. 개별 기관의 R4−R1 손실 차이는 같은 기관·시장에 대한 두 답이 모두 유효해야 계산한다. 기관쌍의 E·D·G를 정책 간 대응 비교하려면 같은 시장의 두 기관 × 두 정책, 총 네 답이 모두 유효해야 한다. 정책마다 서로 다른 유효 사례의 평균을 빼서 대응 효과라고 부르지 않는다. 제외 수와 정책별 실패율을 함께 제시하고, 실패 사례에 임의의 손실값을 채우지 않는다.</p>
<p>유효 응답만의 수치 비교는 해당 공통 유효집합에 조건부인 결과다. 전체 예정 코퍼스의 품질 우월성으로 자동 확대하지 않는다. 답에 기재한 γ와 근거 ID는 별도의 형식·인식 진단으로 남기며 배분 점수를 대신하지 않는다. 목표를 정확히 인용했더라도 배분이 목적에 맞지 않을 수 있다.</p>
<h3>4.5. 분석 단위와 실행 범위</h3>
<p>625개 시장 조건과 세 목적을 모두 사용하면 기관 사례는 1,875개다. R1·R4의 최종 답은 3,750개이며, 각 네 단계이므로 예정 응답 호출은 15,000회다. FRESH는 1,875회로 총 16,875회다. 이는 한 번의 코퍼스 전수 평가에 필요한 호출 수이지 독립적인 인간 실험 표본 수가 아니다. 시장 구간이 서로 겹치므로 독립 표본 표준오차·p값·검정력 주장을 만들지 않는다.</p>
<p>기관별 γ와 기관 쌍별로 평균·중앙값·전체 분포, 같은 사례의 R4−R1 차이를 기술한다. 전체 코퍼스, 기준 답이 다른 쌍, 같은 쌍, 수치적으로 판정이 보류된 쌍을 구분한다. 관측 결과에 따라 특정 시장 구간을 빼지 않는다. 필요하면 전체 동일 가중 요약도 제시하되, 이는 사례 평균이지 기관 간 후생을 합산한 값이 아니다. 반응오차가 줄어도 손실이나 실패율이 악화되면 혼합 결과로 보고한다. 무차이는 절차의 동등성이나 실제 시장에서의 안전을 입증하지 않는다.</p>
<p>기본 모델은 PortBench v6에서 평가한 Qwen3.6-35B-A3B를 목표로 선정하고, 해당 연구의 temperature 0, thinking 활성화, 출력 한도 8,192토큰을 따른다. 실제 제공 모델의 불변 버전·실행 엔진·양자화·문맥 한도는 실행 전에 고정해야 한다. 현재 설치된 작은 모델을 같은 모델로 간주해 대체하지 않는다. temperature 0도 모든 백엔드에서 완전한 재현성을 보장하지 않으므로 원문 요청·응답·설정·시간·토큰·오류를 저장한다. 본 원고에는 아직 AI 응답이 없다.</p>
<h3>4.6. 공개 펀드 자료와 보조 과제</h3>
<p>Fidelity Contrafund, Vanguard PRIMECAP, Dodge &amp; Cox Stock Fund, T. Rowe Price Blue Chip Growth의 공개 문서는 실제 운용 목표와 규칙이 존재한다는 배경 자료 및 별도 문서 추출 과제의 후보로 보존한다. 성장주 특성, 해외 발행자 한도, 자산 분모를 FF12 산업 상한이나 γ로 자동 변환하지 않는다. 해당 자료의 역사적 버전과 정답표가 아직 동결되지 않았으므로 이번 주실험의 입력이나 완료된 문서 실험으로 표시하지 않는다.</p>
<p>Hansen–Lee 거래 과제의 255개 이력·510개 신호별 기준 답은 신호 활용을 점검하는 보조 자료다. 이 과제와 공개 문서 추출의 성과를 합쳐 기관별 산업 배분 실험을 대신하지 않는다. Black–Litterman 방식은 별도 후보로 검토했으나, 기관별 전망과 확신도를 공개자료에서 독립적으로 정해야 하는 문제가 남는다. 평가할 AI가 만든 전망을 그 AI의 정답으로 다시 사용하는 순환을 피하기 위해 주설계로 선택하지 않았다.</p>
</section>'''

framework = '''<section id="framework"><h2>3. 개념과 연구질문</h2>
<p>‘필요한 판단 차이’란 기관의 이름이나 표현이 달라 생기는 차이가 아니라, 명시된 목적과 제약 아래 최적 판단이 달라지는 경우다. 연구의 넓은 문제의식은 공통 생성형 AI가 기관별 조건을 최종 판단에 반영하는가다. 이번 조작은 그 조건 중 <strong>위임목적의 차이</strong>에 한정한다. 사적 전망을 가지고 있지만 무시하는 경우와, 투자자가 요구하는 위험 평가 기준을 반영하지 못하는 경우는 구별되는 메커니즘이다.</p>
<p>연구질문은 다음과 같다. 동일한 시장자료를 처리하는 공통 AI는 서로 다른 위임목적이 요구하는 주식부문 산업 배분 차이를 보존하는가? 목표를 처음부터 제공하고 대화에 유지하는 절차는 최종 검토 때 처음 제공하는 절차보다 그 차이의 반영과 기관별 목적상 품질을 개선하는가? 이 질문은 금융에서의 선호·위임 문제와 경영에서의 업무 설계·검토 절차를 연결한다.</p>
<p>사전 방향 가설은 초기 제공이 목표 반응오차와 기관별 목적상 손실을 줄인다는 것이다. 그러나 정보가 늦게 제시될수록 더 눈에 띄거나, 네 단계 업무가 불필요한 혼란을 늘릴 가능성도 있다. 반대 방향과 무차이도 그대로 보고한다. 단순 수렴, 목표를 제대로 반영하지 못하는 현상, 목적상 손실을 동반한 수렴을 구별한다. 목표가 달라도 같은 배분이 최적이면 같은 답을 실패로 채점하지 않는다.</p>
<p>본 연구가 제공할 수 있는 증거는 ‘공통모델을 쓰는 주어진 환경에서 어떤 정보 전달 절차가 위임목적을 더 잘 보존하는가’에 관한 것이다. 비사용 집단이나 다양한 모델을 쓰는 집단과 비교하지 않으므로, 공통모델의 도입 자체가 동질화를 일으켰다는 인과효과는 추정하지 않는다. 실제 검색은 생략하고 정답 근거를 직접 제공하므로, 검색 정확도에 관한 별도의 연구질문 역시 이번 주실험에서 분리한다.</p></section>'''

limits = '''<section id="limits"><h2>7. 한계와 후속 연구</h2>
<p>첫째, 가상 기관의 목적 차이는 실제 기관의 복잡한 정보·조직·보유자산을 대표하지 않는다. 실제 펀드의 위험선호를 추정한 연구도 아니다. 특히 FF12는 주식 내부의 산업 분류이므로 위험회피의 중요한 조정 수단인 주식·채권·현금 사이의 선택을 포함하지 않는다. 따라서 이번 연구가 직접 검증하는 것은 명시된 목적을 산업 비중에 반영하는 능력이다.</p>
<p>둘째, 기준 배분은 역사적 자료에서 추정한 평균과 공분산에 조건부인 규범적 해다. 평균 추정오차, 거래비용, 시장충격, 세금, 투자 가능 상품의 제약까지 반영한 실제 최적 투자안이 아니다. 최신 내려받기 자료에는 과거 수익률의 개정이 포함되며 역사적 시점에 알려졌던 자료를 복원하지 않는다. 과거 자료를 모델이 학습했을 가능성도 있다. 그러므로 미래 수익 예측이나 실제 매매 성과로 결론을 확장하지 않는다.</p>
<p>셋째, 고정 모델·고정 코퍼스 안의 절차 비교다. 중첩된 625개 구간을 독립 시장 표본으로 보지 않으며, 모델 간 일반화와 확률적 반복 변동도 이번 단일 전수 평가만으로 확정할 수 없다. 필요하면 별도 모델과 자료 체계에서 같은 절차를 재검증해야 한다. 오류가 거의 없는 천장 효과 또는 광범위한 계산 실패가 나타나면, 해당 조건에서 절차 차이를 판별하기 어려웠다고 보고한다.</p>
<p>넷째, 주 비교는 목표의 제공 시점뿐 아니라 대화 내 위치와 이용 이력을 함께 바꾼다. 심리적 고착이나 기억 손실을 단독으로 식별하지 않으며, 설명문에 목표를 인용했다는 사실만으로 올바르게 활용했다고 판정하지 않는다. 비중과 목적상 손실을 검증해야 한다. 직접 제공한 근거를 사용하는 실험은 RAG의 검색 실패를 평가하지 않는다.</p>
<p>다섯째, 최종 배분의 오류만으로 목표를 읽지 못한 경우, 기억하지 못한 경우, 목표를 알지만 수치 최적화를 수행하지 못한 경우를 분리할 수 없다. FRESH는 계산 가능성을 점검하는 보조 조건이지만 그 자체로 이 원인을 인과적으로 구분하지 않는다. 따라서 관측 결과는 목적 적합성과 업무 절차의 차이로 보고하며, 기관 고유 목표를 모델이 ‘삭제했다’는 심리적 기제의 증거로 단정하지 않는다.</p>
<p>후속 연구는 실제 종목 단위의 국적·통화·스타일 분류를 확보하여 기관별 공시 제약을 정확히 매핑하거나, 독립적으로 만든 사적 전망과 전체 자산군 선택을 도입할 수 있다. 모델 다양성과 비사용 비교도 별도로 필요하다. 이러한 확장은 현재 실험이 확인하지 못한 영역으로 남기며, 이번 결과를 실제 운용사 동질화나 시장 불안정의 증거로 확대하지 않는다.</p></section>'''

conclusion = '''<section id="conclusion"><h2>8. 결론</h2>
<p>공통 AI의 답이 비슷하다는 사실만으로 기관의 판단이 나빠졌다고 결론 내릴 수는 없다. 경제적으로 중요한 기준은 기관마다 달라야 할 판단이 실제로 달라지고, 같아도 되는 판단은 적절히 수렴하는가다. 선행연구가 제시한 상반된 결과를 고려하면, 동질화는 확인할 가설이며 결과의 전제가 아니다.</p>
<p>본 연구는 이 문제를 가상 기관의 명시적 위험선호와 공개 산업 수익률에 연결했다. 논문에 근거한 목적함수와 계수로 기관별 기준 배분을 독립 계산하고, 공통 AI에 그 목표를 언제 제공하는지 바꾸어 필요한 차이와 기관별 손실을 함께 평가하는 설계다. 단순 신호 추종을 넘어 실제 배분 판단을 평가하되, 기관별 정보 전체와 실제 시장 결과까지 설명한다고 주장하지 않는다.</p>
<p>현재 기여는 문헌 검토, 재현 가능한 기준 답과 업무 절차, 해석 범위가 연결된 실험 전 연구설계다. 자체 AI 결과는 아직 없다. 실험 이후에는 관측 방향에 따라 초기 목표 전달, 최종 검토 강화 또는 추가 검증의 필요성을 논의해야 한다. 학술제의 ‘AI가 재편하는 사회와 경제: 변화와 대응의 방향’이라는 주제에 대한 이 글의 응답은, AI 활용의 증가를 막연히 찬반으로 평가하기보다 기관이 위임한 목적이 실제 결정에 반영되는 절차를 검증하는 데 있다.</p></section>'''

appendix = '''<section id="appendix"><h2>부록. 선택 결과와 제출 전 작업</h2>
<div class="table-wrap"><table><thead><tr><th>실험의 어느 부분</th><th>선택한 구성과 이유</th><th>남겨 둔 후보</th></tr></thead><tbody>
<tr><td>기관별 차이</td><td>명시적 γ 1·3·5. 논문 수치이며 정답을 독립 계산 가능.</td><td>실제 펀드의 목적·제약은 종목 속성 매핑 후 확장. 사적 전망은 독립 생성 근거가 확보된 후 검토.</td></tr>
<tr><td>판단식·비중</td><td>long-only quadratic 목적의 최적해. 비중을 사람이 정하지 않음.</td><td>Black–Litterman은 기관별 전망·확신도 출처 문제로 보류.</td></tr>
<tr><td>산업</td><td>공개 FF12 전체. 선별하지 않아 임의 산업 선택을 피함.</td><td>채권·현금 포함 전체 배분은 별도 공개자료 설계 필요.</td></tr>
<tr><td>업무 절차</td><td>R1과 R4 네 단계 대응 비교. FRESH는 별도 계산 가능성 진단.</td><td>R2·R3 추가는 후속 확장. 현 주 비교의 방향을 보고 유리한 단계만 추가하지 않음.</td></tr>
<tr><td>실행 모델</td><td>논문에서 평가한 Qwen3.6-35B-A3B를 목표로 선정.</td><td>실제 접근·불변 버전 확보 필요. 접근이 안 되면 같은 논문 평가 모델 중 공개 접근 가능한 모델을 먼저 확인하고, 실행 전 설정을 새 버전으로 동결해야 함.</td></tr>
</tbody></table></div>
<p><a href="https://app.notion.com/p/2026-agent-conference/LIBERA-3e00589711408053a7e5ff9a0c4ba804">학술제 개요</a>에 따르면 페이퍼 제출은 11월 1일, 피칭은 11월 6일이며 발표는 5–10분, 인용은 APA 형식이다. 분량·제출 파일 형식·자체 실험 결과의 필수 여부는 확인한 개요에 명시되지 않았다. 따라서 이 HTML은 제출 준비용 소논문 초안이며 최종 접수 형식이 확정됐다는 뜻은 아니다.</p>
<p>주실험의 논리·수치 조건·자료·평가 규칙은 이번 버전에서 연결했다. 실제 실행 전에 모델 제공 환경과 정확한 버전을 기록하고, 입력 검증과 저장 경로를 확인한다. 실행 후에는 실패 사례까지 포함한 결과표를 만들고 초록·결과·논의를 관측 사실에 맞춰 수정한다. 미실행 상태의 원고를 실험 결과가 있는 논문처럼 제출하지 않는다. 실험 결과가 없는 형태로 제출할 경우에도 설계 논문이라는 성격을 명시하고 제출 규정을 확인해야 한다.</p>
</section>'''

refs_node = base.find(id='references')
ref_list = refs_node.find('ul') or refs_node.find('ol')
# Update bibliographic status against publisher metadata checked in round 1.
refs_node.find(id='ref-hedden').replace_with(BeautifulSoup('''<li id="ref-hedden">Hedden, B., &amp; Raghavan, M. (2026). Algorithmic monoculture and its critics. <i>Philosophical Perspectives</i>. Advance online publication. <a href="https://doi.org/10.1111/phpe.70018">https://doi.org/10.1111/phpe.70018</a><span class="refnote">2026년 9월 25일 정식 온라인 게재본 확인. 이전 arXiv 프리프린트 표기를 갱신.</span></li>''','html.parser'))
dell = refs_node.find(id='ref-dellacqua')
dell_html = str(dell).replace('<i>Organization Science</i>. Advance online publication.', '<i>Organization Science, 37</i>(2), 403–423.')
dell.replace_with(BeautifulSoup(dell_html,'html.parser'))
new_refs = '''
<li id="ref-salcher">Salcher, L., Stöckl, S., &amp; Hanke, M. (2026). Lost in translation? Risk-adjusting RMSE for economic forecast performance. <i>Journal of Forecasting, 45</i>(5), 2587–2605. <a href="https://doi.org/10.1002/for.70134">https://doi.org/10.1002/for.70134</a><span class="refnote">원문 §3.2 식 (6), 위험선호별 표, 자료 및 실증 설정 확인. 원래 quadratic 모형은 공매도 허용. LIBERA의 long-only 결합과 구분.</span></li>
<li id="ref-portbench">Zhao, Y., Chen, S., &amp; Su, N. (2026). <i>PortBench: A correlation-aware, full-pipeline benchmark for LLM-driven portfolio management</i> (Version 6) [Preprint]. arXiv. <a href="https://arxiv.org/html/2605.27887v6">https://arxiv.org/html/2605.27887v6</a><span class="refnote">2026년 10월 9일 v6. §2.2, §3.1, Appendix C.1 T5, C.2–C.3 확인.</span></li>
<li id="ref-schneider">Schneider, C. J., &amp; Yilmaz, Y. (2025). Stock portfolio selection based on risk appetite: Evidence from ChatGPT. <i>Finance Research Letters, 82</i>, 107517. <a href="https://doi.org/10.1016/j.frl.2025.107517">https://doi.org/10.1016/j.frl.2025.107517</a></li>
<li id="ref-hornuf">Hornuf, L., Streich, D. J., &amp; Töllich, N. (2025). <i>Making GenAI smarter: Evidence from a portfolio allocation experiment</i> (CESifo Working Paper No. 11862). <a href="https://www.ifo.de/en/cesifo/publications/2025/working-paper/making-genai-smarter-evidence-portfolio-allocation-experiment">공식 연구 페이지</a></li>
<li id="ref-french">French, K. R. (n.d.). <i>Data library</i> [Data set]. Dartmouth College. Retrieved October 17, 2026, from <a href="https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html">https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html</a><span class="refnote">이번 내려받기 버전과 SHA-256은 data/french/manifest.json에 기록. 과거 시점 데이터 빈티지와 구별.</span></li>
'''
ref_list.append(BeautifulSoup(new_refs, 'html.parser'))
for item in sorted(list(ref_list.find_all('li')),key=lambda x:x.get_text().casefold()):
    ref_list.append(item.extract())

literature = base.find(id='literature')
for text_node in list(literature.find_all(string=True)):
    if '검색의 정확성과 제공된 근거의 활용 능력도 분리해 평가한다.' in str(text_node):
        text_node.replace_with(str(text_node).replace('검색의 정확성과 제공된 근거의 활용 능력도 분리해 평가한다.','이번 주실험은 제공된 근거의 활용을 다루며, 실제 검색의 정확성은 별도 후속 문서 과제에서 검증할 부분이다.'))
literature.append(BeautifulSoup('''<h3>2.4. 투자자 목표를 보존하는 배분 평가</h3><p>투자자의 위험선호를 입력으로 다룬 금융 연구는 이번 조작의 직접적인 근거를 제공한다. Schneider와 Yilmaz(<a href="#ref-schneider">2025</a>)는 위험선호 조건에 따른 ChatGPT의 주식 포트폴리오를 비교한다. Hornuf 등(<a href="#ref-hornuf">2025</a>)은 위험선호·투자기간·ESG 선호가 다른 프로필에서 정보 제공과 배분의 관계를 다룬다. 특히 추가 정보가 항상 위임목적에 더 적합한 선택으로 이어진다고 가정할 수 없다는 점에서, 정보의 양과 목적 적합성을 구별해야 한다.</p><p>PortBench v6(<a href="#ref-portbench">2026</a>)는 투자자 프로필을 반영한 포트폴리오 평가를 제시한다. 본 연구는 이를 기관별 기준을 조건부로 정해야 한다는 선례로 사용한다. 다만 그 연구의 자산군 한도를 FF12 산업별 상한으로 바꾸지는 않는다. Salcher 등(<a href="#ref-salcher">2026</a>)의 목적함수·위험선호 계수와 공개자료 체계를 결합하여, 기관마다 다른 명시적 목적에 대한 AI의 반응을 독립된 기준 답과 비교한다. 이 결합의 새로움은 금융시장의 동질화를 처음 발견한다는 주장이 아니라, 규범적 배분 차이와 업무 절차를 연결하는 구체적인 평가 설계다.</p>''', 'html.parser'))

intro = base.find(id='intro')
paragraphs = intro.find_all('p', recursive=False)
for p in paragraphs[3:]:
    p.decompose()
intro.append(BeautifulSoup('''<p>이에 본 연구는 넓은 문제의식을 <strong>동일한 AI가 서로 다른 위임목적을 최종 투자 배분에 반영하는가</strong>라는 검증 가능한 질문으로 구체화한다. 공개 시장자료를 동일하게 주고, 논문에서 사용한 위험선호 계수만 다른 가상 기관을 둔다. 기관별 목적을 처음부터 제공하거나 최종 검토 때 제공하여, 필요한 산업 배분 차이와 기관별 목적상 품질이 어떻게 달라지는지 비교한다.</p><p>이는 모든 기관의 사적정보나 전체 운용전략을 재현하는 실험은 아니다. 그러나 기관별 차이가 실제 선택의 적정성을 바꾸는 금융 의사결정이라는 핵심 구조를 유지한다. 경제학적으로는 선호와 위임의 문제이며, 경영학적으로는 AI를 사용하는 업무에서 목표 전달과 재검토를 조직하는 문제다. 이하에서는 상반된 선행연구, 조작적 정의, 공개자료와 수치 모형, 반론 및 대응 방향을 연결한다.</p>''','html.parser'))

alternatives = str(base.find(id='alternatives'))
# Remove stale implication that the main experiment manipulates private signals.
alternatives = alternatives.replace('정보·신호가 달라도', '위임목적이 달라도')
alternatives = alternatives.replace('자료의 차이가 행동을 바꿔야 하는지부터 평가하고, 사적신호를 따르는 행동과 경제적으로 적절한 행동을 동일시하지 않는다.','목표의 차이가 배분을 바꿔야 하는지부터 평가한다. γ가 달라도 동일한 배분이 최적이면 수렴은 정상이며, 기관별 배분을 무조건 다르게 만드는 행동을 보상하지 않는다.')
implications = '''<section id="implications"><h2>6. 조직의 대응 방향</h2><p>초기 제공이 필요한 배분 차이를 더 정확히 반영하면서 기관별 목적상 손실과 실패율도 줄인다면, 시장 분석의 시작 단계부터 위임목적을 연결하고 후속 대화에 유지하는 절차를 검토할 근거가 된다. 분석 담당자는 목적의 출처와 적용 범위를 확인하고, 최종 승인자는 권고 비중이 해당 목적과 일치하는지 검토한다. 이는 관측될 결과에 조건부인 제안이지 이미 효과가 확인된 운영 지침이 아니다.</p><p>후기 제공이 더 낫다면 최종 검토에서 목표를 다시 확인하고 모든 선택을 재개방하는 절차가 유용할 수 있다. 답변 차이만 커지고 손실이나 실패율이 나빠진다면 동질화 완화의 성공으로 부르지 않는다. 차이가 확인되지 않아도 두 절차가 모든 상황에서 동등하다고 단정하지 않는다. 계산 실패가 많다면 먼저 배분 산출 도구를 개선하고 같은 목표 반영 질문을 다시 검증해야 한다.</p><p>이번 주실험은 정확한 목표 문서를 직접 넣는다. 따라서 실제 자료 관리와 검색의 품질은 별도로 확인해야 한다. 공식 문서에 규칙이 있어도 잘못된 버전이나 분모를 가져오면 정확한 목표 전달이 성립하지 않는다. 반대로 정확한 규칙을 주어도 권고가 목적에 맞지 않는다면 검색 이후의 활용과 검토 절차가 문제일 수 있다.</p><p>FSB(<a href="#ref-fsb26">2026</a>)의 최종 보고서는 AI 생애주기의 책임, 자료 품질과 검증·감독을 논의한다. 이러한 정책 맥락은 본 연구의 조직적 문제의식과 연결되지만, 특정 근거 제공 시점의 효과를 입증하는 학술적 실험 근거로 사용하지 않는다.</p></section>'''

title = '공통 생성형 AI는 기관별 투자목적을 보존하는가?'
subtitle = '위험선호가 다른 가상 기관의 주식부문 산업 배분과 목표 제공 절차'
abstract = '''<div class="abstract"><h2>초록</h2><p>공통 생성형 AI가 투자 업무에 사용될 때 중요한 문제는 답변이 얼마나 비슷한가를 넘어, 기관마다 다른 목적이 요구하는 판단 차이가 최종 권고에 반영되는가다. 본 연구는 알고리즘 동질화와 금융 AI에 관한 상반된 문헌을 검토하고, 이를 검증할 실험 전 연구설계를 제시한다. 공개된 12개 산업 수익률과 논문에서 사용한 quadratic 목적함수 및 위험선호 계수 1·3·5를 이용하여 가상 기관별 기준 배분을 독립 계산한다. 공매도 금지를 결합한 모형은 본 연구의 응용이다. 동일한 AI에 목표를 처음부터 제공·유지하는 절차와 최종 검토에서 제공하는 절차를 비교하고, 필요한 배분 차이에 대한 반응오차와 기관별 목적상 손실을 함께 평가한다. 목표가 달라도 동일한 배분이 최적인 사례를 포함하여 합리적 수렴을 실패와 구별한다. 현재는 자료·기준 답·실행 규칙을 준비한 단계이며 자체 AI 실험 결과는 없다. 실험의 해석은 명시적 위임목적의 보존과 업무 절차에 한정하며, 실제 운용사의 사적정보, 공통모델 도입 자체의 인과효과 또는 시장 안정성으로 확대하지 않는다.</p><p class="small"><strong>주제어:</strong> 생성형 AI, 기관별 투자목적, 알고리즘 동질화, 자산운용, 위험선호, 업무 설계</p></div>'''

def page(page_title, body):
    return '<!DOCTYPE html>\n<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+page_title+'</title><style>'+css+'</style></head><body><main class="wrap">'+body+'<footer>LIBERA · 2026-10-17 · v4.0 · 연구설계 및 기준 답 준비 / AI 실험 미실행</footer></main></body></html>'

paper_body = f'''<header><div class="eyebrow">LIBERA 2026 · TERM PAPER · VERSION 4.0</div><h1>{title}</h1><p class="subtitle">{subtitle}</p><p class="meta">문헌 검토와 실험설계 소논문 · 2026년 10월 17일 · 저자 정보 제출 전 기입</p><div class="status"><strong>실험 전 원고.</strong> 자체 AI 결과를 보고하지 않는다. 수치 최적화로 만든 기준 답은 실험 준비이며 AI의 판단을 관측한 결과가 아니다.</div><div class="toolbar"><button onclick="window.print()">인쇄 / PDF 저장</button><a href="../plan/LIBERA_실험계획_20261017.html">실험계획과 쉬운 설명</a><a href="../research/evidence_ledger_v4.json">조건별 근거 대조표</a><a href="../research/audits/verification_v4.html">두 차례 검증 기록</a></div></header>'''
paper_body += abstract
paper_body += '<nav>'+''.join(f'<a href="#{i}">{label}</a>' for i,label in [('intro','서론'),('literature','선행연구'),('framework','연구질문'),('design','방법'),('alternatives','반론'),('implications','대응'),('limits','한계'),('references','참고문헌')])+'</nav><article class="paper-body">'
paper_body += str(intro)+str(literature)+framework+methods+alternatives+implications+limits+conclusion+str(refs_node)+appendix+'</article>'
paper_body = paper_body.replace('PortBench v6(<a href="#ref-portbench">2026</a>)는','Zhao 등(<a href="#ref-portbench">2026</a>)의 PortBench v6는')
(PAPER/'LIBERA_텀페이퍼_초안_20261017.html').write_text(page(title,paper_body),encoding='utf-8')

parameter_rows = [
('위험선호와 식','γ = 1, 3, 5; U = μᵀw − γwᵀΣw/2','Salcher 등 (2026), §3.2 식 (6), 위험선호별 표'),
('자료·기간','FF12; 월별 소수 초과수익률; 1964–2023; 과거 60개월','Salcher 등의 자료 및 실증 프레임 + French 공개자료'),
('시장 사례 수','720 − 60 − 36 + 1 = 625; 전수 유지','자료 길이에서 계산한 LIBERA 코퍼스. 36개월은 예약만 하고 미사용'),
('공매도 금지','w ≥ 0, 합계 1','PortBench의 long-only 선례. quadratic 목적과 결합은 새 응용'),
('업무 조건','4단계; R1 대 R4; FRESH 별도','제안서의 업무 구조를 구체화한 LIBERA 설계. 논문에서 그대로 가져온 값이 아님'),
('모델 설정','목표 Qwen3.6-35B-A3B; T=0; thinking; 8,192토큰','PortBench v6 §3.1. 실제 불변 버전과 접근 확인은 실행 전 필요'),
('평가','직접 목적상 손실·배분 반응오차·제약 실패','목적함수에서 유도한 새 측정 체계. 종합점수 가중치 없음'),
('비중 오차 허용','합계 오차 ≤ 10⁻⁶; 음수 불허','구현 정밀도 기준. 경제적 유의성이나 논문 처치 수치가 아님'),
]
table = '<div class="table-wrap"><table><thead><tr><th>항목</th><th>확정 내용</th><th>근거의 성격</th></tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+x+'</td>' for x in r)+'</tr>' for r in parameter_rows)+'</tbody></table></div>'
plan_body = f'''<header><div class="eyebrow">LIBERA · RESEARCH PROTOCOL · VERSION 4.0</div><h1>기관별 투자목적을 보존하는<br>AI 업무 절차의 실험계획</h1><p class="meta">2026년 10월 17일 · 공개자료·논문 모형 연결 · 실제 AI 실행 전</p><p class="callout">주실험은 세 가상 기관의 <strong>주식부문 산업 배분</strong>이다. 기관별 목표가 실제 기준 비중에 작용하므로 원래의 ‘필요한 투자판단 차이’라는 논점을 유지한다. 실제 운용사의 사적정보 전체를 재현했다는 주장은 하지 않는다.</p><div class="toolbar"><a href="../paper/LIBERA_텀페이퍼_초안_20261017.html">소논문 초안</a><a href="LIBERA_실험설정_20261017.json">동결 설정</a><a href="../data/institutional/summary.json">기준 답 검증</a><a href="../data/workflow/manifest.json">프롬프트 묶음</a><a href="../research/audits/verification_v4.html">두 차례 검증</a></div></header>'''
plan_body = plan_body.replace('동결 설정','실험 설정')
plan_body += plain+'<section id="parameters"><h2>조건과 근거</h2><p>논문에서 직접 가져온 조건, 여러 연구를 연결한 새 설계, 공개자료에서 계산한 값, 수치 구현 허용 오차를 구별한다. 새 실험의 모든 선택이 기존 한 논문에 이미 정해져 있었다고 서술하지 않는다.</p>'+table+'</section>'+framework+methods+appendix
plan_body += '<section id="references"><h2>근거 문헌</h2>'+str(ref_list)+'</section>'
(PLAN/'LIBERA_실험계획_20261017.html').write_text(page('LIBERA 실험계획 v4.0',plan_body),encoding='utf-8')
(PLAN/'LIBERA_실험설정_20261017.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'built':['plan HTML','protocol JSON','term-paper HTML'],'version':config['protocol_version'],'AI_runs':0}))
