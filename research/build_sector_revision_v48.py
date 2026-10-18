"""Build the v4.8 research redesign. Offline only; does not run or freeze an experiment."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATE = '20261018'
PLAN = f'plan/LIBERA_실험계획_v4.8_{DATE}.html'
PAPER = f'paper/LIBERA_텀페이퍼_초안_v4.8_{DATE}.html'
CONFIG = f'plan/LIBERA_실험설정_v4.8_{DATE}.json'
FACTS = f'data/sector_protocol/v48_design_{DATE}/public_numeric_registry.json'
PROMPTS = f'data/sector_protocol/v48_design_{DATE}/prompt_contract.json'
INVENTORY = f'research/evaluator_only/v48_source_comparison_{DATE}.json'


def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8'))


def ref(path):
    return {'path': path, 'sha256': sha256((ROOT/path).read_bytes()).hexdigest()}


def write(path, value):
    p = ROOT/path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def section(key, title, body):
    return f'<section id="{key}"><h2>{title}</h2>{body}</section>'


def table(head, rows):
    return '<div class="table-wrap"><table><thead><tr>'+''.join(f'<th>{x}</th>' for x in head)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{x}</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def build_registry(market, codes):
    rows = []
    specs = [
        ('baseline_weights', 'normalized_baseline_weight', 'decimal_weight', ['2026-06-30']),
        ('daily_volatility', 'daily_return_standard_deviation', 'daily_decimal_return', market['lookback_return_dates']),
        ('annualized_volatility_diagnostic', 'annualized_return_standard_deviation', 'annual_decimal_return', market['lookback_return_dates']),
        ('lookback_compound_return', 'historical_compound_return', 'decimal_return_over_window', market['lookback_return_dates']),
        ('daily_mean_return', 'historical_mean_daily_return', 'daily_decimal_return', market['lookback_return_dates']),
    ]
    for key, metric, unit, period in specs:
        for i, code in enumerate(codes):
            value = market[key][code] if isinstance(market[key], dict) else market[key][i]
            rows.append({'fact_id': f'M:{key}:{code}', 'sector_code': code, 'metric': metric,
                         'unit': unit, 'period': period, 'value': value,
                         'source_json_pointer': f'/{key}/{code if isinstance(market[key], dict) else i}'})
    for key, metric, unit in [('baseline_annualized_volatility_diagnostic', 'baseline_annualized_return_standard_deviation', 'annual_decimal_return'),
                              ('return_observations', 'number_of_daily_returns', 'count'),
                              ('annualization_trading_days', 'annualization_multiplier', 'trading_days_per_year')]:
        rows.append({'fact_id': f'M:{key}', 'sector_code': None, 'metric': metric,
                     'unit': unit, 'period': market['lookback_return_dates'], 'value': market[key],
                     'source_json_pointer': f'/{key}'})
    write(FACTS, {'version': 'v4.8-design', 'status': 'offline_registry_prepared_runner_integration_pending',
                  'source': ref('data/sector_market/market_input.json'),
                  'source_chain': [ref('data/sector_market/manifest.json'), ref('data/sector_market/benchmark.json')],
                  'visibility': 'Same common facts for all cases from stage 1; contains no assigned institution or evaluator answer.',
                  'scope': 'Indexes existing public input values; adds no new observations, predicted returns or institutional targets.',
                  'rows': rows, 'matrix_fact_references': [
                      {'fact_id': 'M:covariance', 'source_json_pointer': '/covariance', 'unit': market['covariance_unit'], 'sector_order': codes},
                      {'fact_id': 'M:correlation', 'source_json_pointer': '/correlation', 'unit': 'unitless', 'sector_order': codes}],
                  'runtime_calculator_fact_policy': 'Future per-stage facts must carry call/stage/candidate ID, operation, actual input hashes, units and values. They are not static observations in this file.',
                  'narrative_check_policy': 'Match entity, period, metric, unit and stated precision, not number alone. A cited ID is not semantic validation. New self-derived quantities must cite already-visible input IDs and the formula, be marked pending verification, and never invent a not-yet-produced calculator fact ID.',
                  'online_model_calls': 0})


def build_inventory(codes):
    allowed_relationships = read(f'research/v48_review_template_{DATE}.json')['allowed_states']['inventory_relationship']
    result = {'version': 'v4.8-design', 'visibility': 'EVALUATOR_ONLY_NEVER_MODEL_INPUT',
              'status': 'source-only_inventory_prepared_independent_human_review_pending',
              'policy': 'Prepared before v4.8 outputs; no unique weight gold, no translation of UBS Attractive into Fidelity Overweight; comparison categories require source review.',
              'splits': {}, 'model_calls': 0}
    for split, sources in [('pilot', ['fidelity_q2_2026', 'ubs_june_2026']), ('main', ['fidelity_q3_2026', 'ubs_july_2026'])]:
        packets = [read(f'data/sector_documents/packets/{split}/{s}.json') for s in sources]
        rows = []
        for code in codes:
            records = []
            for p in packets:
                passages = [x for x in p['evidence_passages'] if x['evidence_id'].endswith(':sector:'+code)]
                records.append({'source_id': p['source_id'], 'passages': passages,
                                'rating_vocabulary': p['rating_vocabulary'], 'source_review': None})
            rows.append({'record_id': f'{split}:source_comparison:{code}', 'sector_code': code, 'sources': records, 'comparison': None,
                         'comparison_allowed': allowed_relationships,
                         'reviewer': None, 'review_evidence': None,
                         'warning': 'Different label vocabulary alone does not establish a substantive disagreement.'})
        result['splits'][split] = {'inputs': [ref(f'data/sector_documents/packets/{split}/{s}.json') for s in sources], 'rows': rows}
    write(INVENTORY, result)


def build():
    old_path = f'plan/LIBERA_실험설정_v4.7_{DATE}.json'
    old = read(old_path)
    codes = old['main']['taxonomy']['sector_codes']
    market = read('data/sector_market/market_input.json')
    build_registry(market, codes)
    build_inventory(codes)
    prompt_contract = {
        'version': 'v4.8-design', 'implementation_status': 'specification_not_integrated_into_online_runner',
        'top_level_fields': ['source_id','interpretations','weights','alternatives','risk_discussion','unresolved','submitted_constraints'],
        'structural_predecessor': ref('research/sector_response_schema.py'),
        'common_instructions': [
            'Use only the currently visible document, common market facts, prior visible responses and actual calculator output.',
            'Preserve the original source rating vocabulary. Public views are not legal mandates or exact target weights.',
            'In interpretations.reason explain what the cited source actually states; mark absent reasons rather than inventing them.',
            'In each weights.rationale state whether and how the source judgment is adopted, deferred or departed from; cite supplied reasons, explain relevant trade-offs, and connect the explanation to the actual weight relative to the common baseline.',
            'Before institution exposure, do not guess institution identity, labels or private preferences; state market-only basis.',
            'When quoting an externally supplied numerical fact, name its metric, sector, period and unit and cite its existing M: or actual calculator fact ID; do not relabel daily volatility as annual volatility or expected return.',
            'For a quantity you derive from the current proposed weights before the calculator runs, cite already-visible input IDs, identify the current proposed weights and formula, and mark the claim pending external verification. Never invent a future calculator fact ID.',
            'Alternative allocations need reasoned comparison, not an evaluator-supplied exact target. No minimum number of alternatives or invented numerical cap is imposed.',
            'If an alternative is described using numbers, give its full vector or identify the base vector and every change; otherwise do not claim that its total or portfolio risk has been verified.',
            'All weights are raw proposals. Do not claim correction or sum=1 without agreement with the submitted numbers.'
        ],
        'stages': [
            {'stage': 1, 'task': 'Interpret common market facts and any visible source judgments.', 'weights': 'empty or all 11', 'R1_source_visible': True, 'R4_source_visible': False},
            {'stage': 2, 'task': 'Compare defensible allocation alternatives, reasons and risks.', 'weights': 'empty or all 11', 'R1_source_visible': True, 'R4_source_visible': False},
            {'stage': 3, 'task': 'Submit a provisional allocation with evidence-linked rationale.', 'weights': 'all 11', 'R1_source_visible': True, 'R4_source_visible': False},
            {'stage': 4, 'task': 'Reconsider the proposal using all now-visible facts; state maintained or changed choices and why. This first final response is C0.', 'weights': 'all 11', 'R1_source_visible': True, 'R4_source_visible': True}
        ],
        'empty_weights_stage1_2': 'not_yet_proposed; no budget=0 violation and no valid portfolio risk; interpretation still reviewed',
        'core_failure_policy': 'A transport, JSON/schema, truncation or context-overflow failure ends that case without an automatic retry. Preserve all prior and partial raw responses; later planned stages are not_started, not additional attempted model failures. No C0 means no auxiliary repair.',
        'history': 'Keep visible content verbatim; no hidden thinking inspection, no silent truncation.',
        'feedback': 'Same pure calculator in both arms. Actual sums, violations, active weights, and valid-portfolio diagnostics only; never evaluator gold, semantic correction or suggested weights.',
        'source_visibility': 'One assigned source packet is first provided at stage 1 for R1 or stage 4 for R4; then remains in history. Offline source-comparison inventory is never provided.',
        'auxiliary_repair': {'candidate0': 'stage4 first final response', 'maximum_additional_calls': 2,
            'eligibility': 'C0 completed, structurally valid and exactly one finite weight for each of 11 sectors; abs(sum(w)-1)>1e-6 OR any(w<0 or w>1).',
            'feedback': 'Actual prior candidate, sum, signed residual, bound violations and prior-candidate weight deltas. No target allocation or semantic verdict.',
            'stop': 'First arithmetically valid candidate, C2, or first transport/schema/finite-vector failure; no restart.',
            'selection': 'Retain C0 as primary always; auxiliary terminal submission is last attempted response, never best-of selection.',
            'noneligible': 'Valid C0, no C0, transport or schema failure, or incomplete/nonfinite sector vector; report reason, do not retry.',
            'meaning': 'Bounded recovery policy; actual calls may differ across arms. Not equal realized compute or a causal repair-effect experiment.'},
        'main_model_calls': 0}
    write(PROMPTS, prompt_contract)

    config = {
        'protocol_version': '4.8', 'as_of_date': '2026-10-18',
        'status': 'redesign_and_offline_artifacts_prepared; runtime_integration_pilot_human_review_and_freeze_pending',
        'previous_protocol': ref(old_path),
        'research_question': old['research_question'],
        'research_claim_scope': 'Descriptive public-document case under one shared model; evidence-to-rationale-to-allocation preservation, conditional on the task and runtime.',
        'main': deepcopy(old['main']), 'workflow': deepcopy(old['workflow']),
        'model': deepcopy(old['model']), 'submission': deepcopy(old['submission']),
        'claims_not_identified': old['claims_not_identified'] + ['pure memory or anchoring mechanism', 'excess convergence relative to a uniquely necessary institutional weight difference'],
        'primary_output': {'candidate': 'C0', 'definition': 'First raw final response at workflow stage 4, separately for each R1/R4 case.',
                           'repair_replacement': False, 'weighted_composite_score': False,
                           'dimensions': ['source and numerical factual fidelity', 'evidence-rationale-allocation linkage and coverage', 'raw execution feasibility'],
                           'label_accuracy_role': 'auxiliary fact extraction diagnostic, not strategy quality'},
        'auxiliary_repair': deepcopy(prompt_contract['auxiliary_repair']),
        'budget': {'core_calls_per_complete_case': 4, 'max_auxiliary_calls_per_case': 2,
                   'max_calls_per_case': 6, 'planned_cases_each_split': 4,
                   'core_calls_each_split': 16, 'max_auxiliary_calls_each_split': 8,
                   'max_total_calls_each_split': 24,
                   'basis': '3 final candidates including C0 from Precise App I Table12; placement after LIBERA stage4 is local adaptation, not an optimal budget or exact replication.'},
        'evaluation': {'spec': f'research/v48_evaluation_protocol_{DATE}.json',
                       'template': f'research/v48_review_template_{DATE}.json',
                       'public_registry': FACTS, 'source_comparison_inventory': INVENTORY,
                       'no_unique_weight_gold': True, 'no_automatic_semantic_pass': True,
                       'scoring_implementation': 'Legacy mechanical scorer exists; v4.8 linkage/registry evaluation not integrated or human completed.',
                       'source_inventory_scope': 'All 11 sectors in both splits before new outputs; avoid selecting only visibly conflicting labels.',
                       'denominators': 'Report scheduled cases, generation-attempt cases, readable responses, complete vectors, valid allocations, and valid pairs separately. Meaningful rationale fragments can be reviewed even if budget invalid; otherwise missing, never inferred.'},
        'readiness_gate': {'version': 'v48_forward_only',
                           'requires': ['input/schema agreement', 'assigned-source exposure isolation', 'verbatim raw records and failure accounting', 'calculator and denominator correctness', 'numeric claims traceability', 'source and semantic review procedure', 'full four-case pilot before freeze'],
                           'does_not_require': ['every model answer has budget sum 1', 'all model reasoning is correct', 'R1 superiority', 'nonzero institution distance'],
                           'model_failure_is_outcome': True,
                           'insufficient_measurement_rule': 'If C0 allocations do not form valid pairs, weight-contrast outcomes remain unobserved. Report this without a zero-effect claim; do not substitute repaired candidates into primary comparison.',
                           'main_start': 'Only after versioned implementation checks, complete pilot accounting, independent human source review and frozen protocol. No main execution in this task.'},
        'current_execution': {'v48_model_calls': 0, 'v48_pilot_completed_cases': 0, 'main_completed_cases': 0,
                              'main_frozen': False, 'runtime_integration_complete': False, 'human_review_complete': False},
        'historical_development': {'v45_raw_sum': 0.965, 'v46_raw_sum': 0.965, 'v47_raw_sum': 0.975,
                                    'old_gate_outcome': 'failed; not retroactively passed',
                                    'records': [ref('research/v47_handoff_20261018.json'), ref('research/v47_priority1_round2_20261018.json'), ref('research/v47_priority1_round3_20261018.json')],
                                    'pool_with_v48': False},
        'numeric_supplement': {'path': 'data/institutional_recent/summary.json', 'reference_cases': 72,
                               'role': 'Appendix-only computed reference; not evidence of documentary strategy preservation or AI success.', 'ai_runs': 0},
        'parameter_provenance': {
            'paper_precedent': ['60 daily returns: PortBench Appendix C.1 T5; 252 annualization: C.4/F.9; transferred to sector ETF inputs', '8192 output limit: PortBench section3.1 transfer, not FinVector condition', 'non-thinking structured financial output and seed3407 value: FinVector section4.1; greedy translated to T=0 and Ollama seed application are backend adaptations', '3 total final candidates: Precise, adapted after stage4'],
            'local_design': ['4 workflow stages and R1/R4 onset from original LIBERA proposal, informed by staged portfolio workflow', '2 sources x 2 arms, one market context: data availability, no power claim', 'qualitative coding scheme: operational adaptation of E2A, not its validated taxonomy', 'calendar cutoffs and document choices'],
            'engineering_not_paper_behavioral_constants': ['Q4_K_M, context65536, batch512, threads2, 900s deadline, 1e-6 sum tolerance', 'runtime and exact template/digest pins; neutral penalties and sampler defaults; Ollama application of paper seed3407 does not ensure cross-engine equivalence'],
            'prohibited_heuristics': ['invented risk-aversion coefficient per institution', 'ratings mapped to target percentages', 'weighted strategy score or arbitrary pass rate', 'until-success retries or outcome-driven best-response selection']},
        'provenance': {'builder': 'research/build_sector_revision_v48.py',
                       'basis': f'research/v48_reference_basis_{DATE}.json',
                       'parameter_addendum': f'research/v48_parameter_reference_addendum_{DATE}.json',
                       'topic_basis': f'research/v48_topic_alignment_basis_{DATE}.json',
                       'prompt_contract': PROMPTS, 'model_calls_by_builder': 0},
    }
    config['main'].update({'status':'not_run', 'calculation':'Existing pure calculator retained conceptually; v4.8 empty-optional-proposal and fact-ID integration pending.',
                          'pending':['Integrate v4.8 contracts and registry with runner/scorer', 'Three implementation checks', 'Run and review all four v4.8 pilot cases', 'Independent human source/semantic review', 'Freeze before main; main not executed here'],
                          'runtime_policy':'No v4.8 online execution or main freeze yet.', 'gold_visibility':'Evaluator-only inventory and blank worksheets prepared; independent human review pending.'})
    config['main']['paths']['runner'] = None
    config['workflow'].update({'calls_per_complete_case':4, 'primary':'stage4 C0', 'auxiliary':'post-C0 bounded arithmetic revision only'})
    config['workflow']['stages'][2] = 'provisional sector allocation with all 11 sectors'
    config['model'].update({'runtime_ready':False, 'future_candidate_scope':'v4.8 retains observed v4.5 engine settings as candidate; new protocol integration unvalidated.',
                            'context_check_observed_stages':[], 'one_case_workflow_completed':False,
                            'protocol_version':'4.8-design', 'settings_observation_scope':'Engine settings observed in historical v4.5 only. No v4.8 request has run.'})
    write(CONFIG, config)

    old_paper = BeautifulSoup((ROOT/f'paper/LIBERA_텀페이퍼_초안_v4.7_{DATE}.html').read_text(encoding='utf-8'), 'html.parser')
    old_plan = BeautifulSoup((ROOT/f'plan/LIBERA_실험계획_v4.7_{DATE}.html').read_text(encoding='utf-8'), 'html.parser')
    style = old_paper.style.get_text() + '\n.callout{border-left:4px solid #175b67;padding:18px;background:#f2f7f8}.table-wrap{overflow-x:auto}details{margin:16px 0}summary{cursor:pointer;font-weight:700}'
    status = 'v4.8 재설계·오프라인 준비본 · 실행기 통합·전체 예비실험·독립 사람 검토·동결 전 · 본실험 0건'
    links = f'<nav><a href="../plan/LIBERA_실험계획_v4.8_{DATE}.html">실험계획·쉬운 설명</a><a href="../paper/LIBERA_텀페이퍼_초안_v4.8_{DATE}.html">소논문 초안</a><a href="../plan/LIBERA_실험설정_v4.8_{DATE}.json">개정 설정</a><a href="../research/v48_evaluation_protocol_{DATE}.json">평가명세</a><a href="../research/v48_reference_basis_{DATE}.json">논문 근거표</a><a href="../research/progress_{DATE}.html">과정 기록</a></nav>'

    plain = section('plain','실험을 줄글로 설명하면', '''
<p>AI에게 미국 주식에 쓸 돈을 에너지·금융·정보기술 등 11개 산업 바구니에 나누라고 요청한다. 개별 회사를 고르는 과제는 아니다. AI는 최근 시장자료와 시장의 산업별 기준 비중을 공통으로 받고, Fidelity 또는 UBS가 산업을 어떻게 보는지 담은 짧은 공개자료를 읽는다. 그 자료는 각 기관의 실제 보유비중이나 고객의 비밀 투자목표가 아니라 공개 전망이다.</p>
<p>같은 문서에 대해 두 번의 독립된 대화를 만든다. R1에서는 처음부터 문서를 읽고 시장을 해석한 다음 대안을 비교하고 잠정 비중을 만든다. R4에서는 시장자료만으로 그 세 단계를 거친 뒤, 마지막 검토에서 같은 문서를 받는다. 양쪽 모두 네 단계로 끝낸다. 같은 모델과 계산기를 사용하고, 계산기는 합계나 과거 변동성을 알려준다. 어떤 기관의 전략이 옳은지, 어느 산업에 몇 퍼센트를 넣을지는 대신 정하지 않는다.</p>
<p>마지막 답에서는 산업별로 문서가 무엇을 말했는지, 그 의견을 받아들였는지 또는 다르게 결정했는지, 왜 그런지, 실제로 기준보다 비중을 늘렸는지 줄였는지를 함께 읽는다. 예컨대 ‘정보기술을 기준보다 늘렸다’고 썼다면 실제 비중도 기준을 넘어야 한다. 기관 의견과 다르게 배분했더라도 제공된 근거와 위험·분산 고려로 설명할 수 있으면 곧바로 오답이라고 하지 않는다. 같은 비중을 냈다는 사실만으로 기관 판단이 사라졌다고도 하지 않는다.</p>
<p>네 번째 단계의 첫 최종답을 <strong>C0</strong>라고 부르고 주결과로 그대로 남긴다. C0는 새로운 대조군 이름이 아니다. 합계가 맞지 않는 등 산술 위반이 있으면 그 답도 실패 결과로 남긴다. 완전한 숫자 벡터가 있는 경우에 한해서 실제 계산 결과를 돌려주고 최대 두 번 고치게 하는 보조 절차를 둔다. 수정 뒤 답이 좋아져도 최초 답을 바꾸어 기록하지 않는다. 배분이 무효여도 읽을 수 있는 설명은 평가하되, 정상 포트폴리오의 비중 거리·위험으로 해석하지 않는다.</p>
<p>이 비교가 묻는 것은 ‘AI가 수익률 높은 종목을 맞히는가’가 아니라 <strong>조직의 판단 근거를 업무의 어느 단계에 연결해야 최종 선택까지 남는가</strong>다. 두 기관의 소수 문서 사례이므로 시장 전체의 동질화나 어느 절차의 보편적 우월성을 증명하는 실험으로 확대하지 않는다.</p>''')

    framework = section('framework','3. 연구질문과 관측의 연결', '''
<p>논문의 중심 질문은 공통 생성형 AI 아래 기관의 공개 산업 판단이 최종 배분 제안의 근거로 보존되는가이다. ‘판단 보존’은 문서 문구를 복사하거나 기관 간 비중을 억지로 다르게 만드는 일이 아니다. 원문을 정확히 이해하고, 그 판단을 채택하거나 유보·수정한 이유가 제시되며, 실제 제안이 그 설명과 맞는지를 함께 관찰한다. 산업 배분은 경제활동 사이의 자본 배정이며, 이 과정의 근거 전달과 재검토 책임은 경영학의 조직 의사결정 문제다.</p>
<p>원제안서의 전략적 이질성과 알고리즘 동질화는 상위 문제의식으로 유지한다. 다만 본 자료가 직접 보여주는 것은 공개된 두 전망의 판단 전달이다. 기관 전체의 선호·사적정보·실제 운용전략을 대표하지 않으며, 유일한 정답 비중이 없으므로 ‘필요한 차이보다 얼마나 더 수렴했는가’를 직접 추정하지 않는다.</p>'''+table(['연구질문','관측','허용되는 결론'],[
        ['기관의 판단이 선택까지 남는가','원문 판단 → 모델의 처리·이유 → 실제 비중의 연결, 누락·모순','해당 공개 문서의 근거 보존 또는 훼손 사례'],
        ['R1과 R4가 어떻게 다른가','같은 출처의 C0에서 사실·판단 연결·유효성·비중을 비교','최초 제공 시점과 후속 활용 기회를 묶은 업무 절차의 차이'],
        ['R1/R4에서 두 출처 제안의 유사성이 어떻게 다른가','각 절차의 유효 배분 간 거리와 출처별 근거 보존을 함께 검토','두 문서 사례의 제안 유사성; 시장 전체 동질화·피해 판정은 불가']])+'''
<p>문서 사이에 실제로 어떤 의견 차이가 있는지는 모델 결과를 보기 전에 11개 산업 전체의 원문 판단·근거를 나란히 정리한다. 평가 단어가 다르다는 이유만으로 실질적 견해 차이라고 확정하지 않는다. 이 목록은 평가자만 사용한다. 서로 비슷한 판단에는 비슷한 제안이 정당할 수 있고, 다른 판단에도 근거 있는 유보나 절충이 가능하다.</p>''')

    design = section('design','4. 자료와 비교 절차', '''
<h3>4.1. 공개자료와 산업 단위</h3><p>본사례는 Fidelity Q3 2026 산업전망과 UBS July 2026 House View, 예비사례는 Fidelity Q2와 UBS June이다. 출처마다 R1/R4를 적용하여 각 묶음은 네 사례가 된다. 이 수는 가용 문서의 구성에서 나온 연구 규모이며 검정력을 보장받은 표본 수가 아니다. 11개 산업, 네 단계, 사후 수정 횟수는 독립 기관 표본이 아니다.</p>
<p>미국 11개 GICS 산업의 공개 ETF 가격을 사용한다. Quek 등(2025, v5)의 산업 배분과 L. Chen 등(2026)의 섹터 ETF 과제는 분석 단위의 선례다. ETF 내부 기업을 직접 선택하지 않으므로 현재 구성종목을 과거에 소급하는 개별주식 표본 문제를 피할 수 있으나 ETF 구성과 추적 차이 자체가 사라지는 것은 아니다.</p>
<p>공통 자료 마감은 2026년 7월 17일, 가격의 마지막 관측은 7월 16일이다. 직전 60거래일은 PortBench 부록 C.1 T5의 다자산 입력을 산업 ETF로 전용한 것이고, 공분산·연율화 252는 부록 C.4·F.9의 계산 선례를 따른다. 기준 비중은 Fidelity Q3 2쪽의 6월 30일 S&amp;P 500 비중이다. 원래 합계 99.9%를 보존하고 계산용으로만 99.9로 나눈다. 기관의 실제 보유비중·정답 비중은 아니다. Yahoo 수정종가의 현재 내려받기 빈티지이며 당시 거래 가능 정보집합을 복원한 백테스트가 아니다.</p>
<p>Fidelity Q3 공개일은 7월 16일, UBS July 발행일은 6월 22일이고 산업표는 6월 18일 기준이다. Fidelity 산업표의 ‘6/31/26’ 오타도 보존한다. 양 기관의 동시점 최신 의견이라고 주장하지 않는다. 모델 입력은 연구자가 선별한 짧은 요약 패킷이며 원문 전체 검색 실험이 아니다. 원문·날짜·쪽수·파일 해시와 독립 사람 검토 상태를 따로 기록한다.</p>
<h3>4.2. 네 단계의 주비교</h3>'''+table(['단계','공통 과제','R1','R4'],[
        ['1','시장·현재 보이는 문서 해석','기관 문서 최초 제공','기관 문서·정체 미제공'],
        ['2','근거·대안·위험 비교','문서와 이전 이력 활용','시장자료와 이전 이력 활용'],
        ['3','잠정 산업 비중과 이유','기관 판단을 고려한 잠정안','시장자료만의 잠정안'],
        ['4','모든 공개 근거로 최종 재검토','이력 속 문서 재검토 → C0','기관 문서 최초 제공·재검토 → C0']])+'''
<p>첫 두 단계의 비중은 아직 제안하지 않았다면 빈 배열을 허용한다. 이 경우 ‘미제안’으로 기록하고 합계 0%의 잘못된 포트폴리오라고 피드백하지 않는다. 3·4단계에는 11개 산업을 한 번씩 명시하며 0% 배분도 허용한다. 완전한 유한 숫자 비중, 비음수, 상한 1, 합계 1을 공통 실행 조건으로 둔다. 기관 문서에 없는 위험회피계수·상한·수익률 전망을 만들어 넣지 않는다.</p>
<p>응답 형식은 기존 일곱 필드를 유지한다. interpretations.reason에는 원문 의미를, weights.rationale에는 채택·유보·다른 선택과 그 이유 및 실제 기준 대비 비중을 연결해 적도록 요구한다. alternatives에는 다른 선택과 상충 관계를 설명한다. 근거 ID만 복사했다고 의미가 정확한 것으로 처리하지 않는다. 모델의 숨겨진 사고를 평가하는 것이 아니라 제출된 설명을 평가한다.</p>
<p>각 단계의 실제 응답과 계산 피드백을 이력에 보존하고 다음 단계 전에 같은 계산 지원을 제공한다. R4가 기관 문서를 받기 전에는 해당 기관의 정체·평가표·숨겨진 제약이 피드백에 포함되지 않는다. 최종 외부 정보는 같지만 그 정보의 대화 위치, 활용 기간, 이후 검토 기회와 생성된 이력은 다르다. 따라서 R1/R4는 순수 기억·고착 메커니즘을 분리하는 실험이 아니다. 계산기는 공통 지원이며 주 대조는 R1과 R4다.</p>
<h3>4.3. 수치 근거와 사후 수정</h3><p>공통 시장 숫자에는 산업·지표·기간·단위·값·원자료 위치가 붙은 등록부를 연결한다. Reasoning Externalization(Kim et al., 2026, v2, §§3.4–4.1.2)의 근거 등록과 구조화 주장 대조를 적용하되, 자료와 모델은 다르고 자유서술 전체를 자동 인증하지 않는다. FinFIRST(W. Wang et al., 2026, §§2.2.2–2.3)의 추적 원칙에 따라 같은 숫자라도 대상·기간·지표가 다르면 일치로 세지 않는다. 이 등록부는 기존 입력 수치의 주소를 붙인 것이며 새로운 기관 목표나 예측치를 추가하지 않는다. 모델이 현재 제안으로 새로 계산한 값은 기존 입력 ID와 식을 밝히고 외부검증 전 주장으로 표시한다. 아직 발생하지 않은 계산기 결과의 ID를 만들지 않는다.</p>
<p><strong>C0가 주결과이고 추가 수정은 보조 분석이다.</strong> C0가 구조적으로 완전한 11개 유한 숫자 벡터를 냈지만 예산·범위 조건을 위반한 경우에만 실제 합계·잔차·위반·이전 비중 대비 변화를 돌려준다. C1, 필요하면 C2까지 최대 두 번 추가한다. 산술 유효안, C2 도달, 통신·형식·유한 벡터 실패 중 먼저 발생한 시점에서 종료한다. 유효한 C0나 형식 실패 C0는 이 산술 수정 대상이 아니다. 어느 산업에 얼마를 넣으라는 지시나 자동 정규화·클리핑은 하지 않는다.</p>
<p>최대 세 최종 후보(C0 포함)는 Yang 등(2026), Precise but Uncoupled 부록 I 표 12의 예산 선례다. 이를 기존 네 단계 뒤에 배치하는 것은 LIBERA의 변형이며 최적 반복 횟수나 논문 전체 재현이라는 뜻이 아니다. 실제 오류를 사용한 유한 수정은 Zhang 등(2026, §III-B)의 선례를 따른다. Yang 등의 단일 에이전트 반복에서 사용하는 compact memory와 달리 현재 설계는 전체 공개 이력을 유지한다. 동일한 시작·중단·상한 정책을 적용하지만 실제 추가 호출 수는 다를 수 있어 수정 효과의 인과 실험이나 동일 계산량 비교라고 하지 않는다.</p>
<p>완료 사례의 주과제는 네 호출, 보조 포함 최대 여섯 호출이다. 중간 통신·형식·문맥 초과 실패는 사전 규칙에 따라 해당 사례를 종료하고 남은 단계를 ‘미시작’으로 기록한다. 예비 네 사례는 주호출 최대 16회, 추가 최대 8회로 최대 24회다. 과거 개발 호출도 별도 비용 기록에 남긴다. 추가 수정이 끝나도 가장 좋은 답을 골라 최초 답과 바꾸지 않고 마지막 시도의 상태를 보고한다.</p>''')

    evaluation = section('evaluation','5. 평가와 사전 해석 규칙', '''
<p>단일 ‘전략 점수’를 만들지 않는다. E2A-Bench(X. Wang et al., 2026, §§3.1–3.4, 4.2)의 사실 근거·행동 이유·응답 범위 구분을 산업 배분에 맞춰 적용한다. 해당 논문의 매수·매도 판정, 신뢰도 임계값, NDR 종합점수를 그대로 가져오지 않는다. 아래 의미 범주는 이 원칙에 따른 LIBERA의 정성 코딩 규칙이며 이미 검증된 척도라는 주장은 하지 않는다.</p>'''+table(['평가 층','관찰 내용','실패·해석 처리'],[
        ['실행·산술','예정·요청·응답·파싱·완전 벡터·유효 배분, 합계 잔차','인프라/계약 오류와 모델 응답 오류를 구분; 원안 보존'],
        ['사실 보존','11개 원문 등급, 산업·출처·인용 범위, 수치의 기간·단위','등급 11개 고정 분모; 누락 제외 금지. 등급 정확도는 보조 지표'],
        ['판단→근거→선택','원문 뜻, 채택·유보·다른 선택, 상충 이유, 실제 비중과 설명의 일치','관측 가능한 설명은 산술 무효와 별개로 검토. 없는 설명은 누락; 불명확하면 판단 유보'],
        ['비교·거리','같은 출처 R1/R4 및 같은 절차의 출처 간 차이','C0 유효쌍에서만 거리. 전체 사례·유효 사례·유효쌍 수 동시 제시']])+'''
<p>의미 검토는 인용한 원문 구절, 모델의 실제 문장, 판정 이유, 검토자를 함께 남긴다. 원문이 지지하는지·모순되는지·말하지 않았는지·판독 불가인지와, 선택 설명이 실제 비중과 맞는지를 분리한다. 기관 의견과 다른 선택도 제공된 근거에 충실한 상충 고려가 있다면 정당한 대안일 수 있다. 반대로 단순히 ‘다양화했다’고 쓴 문장만으로 그 선택을 인증하지 않는다. 사람이 보기 전 자동 인용 점검을 사람 의미 검토로 표시하지 않는다.</p>
<p>비중의 정량 관측은 예산 잔차 e=Σw−1, 공통 기준 대비 a=w−b, 두 유효 배분의 거리 d(w,v)=½Σ|w−v|다. 거리식은 PortBench(v6, 부록 C.2 식 8)의 유사성 식에서 거리 부분을 전용한 것이며 여기서 v는 정답이 아닌 다른 제안이다. 같은 절차에서 두 출처 간 거리를 D<sub>R1</sub>, D<sub>R4</sub>라 하면 ΔD=D<sub>R4</sub>−D<sub>R1</sub>은 네 C0가 모두 유효할 때만 제시한다. 이는 기술통계이고 인과적 이중차분 추정이 아니다.</p>
<p>과거 위험은 유효 배분에서 σ<sub>daily</sub>(w)=√(w′Σ<sub>daily</sub>w), σ<sub>annual</sub>=√252·σ<sub>daily</sub>로 표시한다. 변동성은 손실확률이나 미래 성과가 아니다. 합계 허용오차 10<sup>−6</sup>은 컴퓨터 수치 정밀도이며 전략의 합격선이 아니다. 원문에 없는 비중 정답·위험선호 수치·평가 가중치는 추가하지 않는다.</p>
<p>모든 표는 예정 사례 수를 먼저 보이고, 응답/판독 가능 수와 조건부 평가 분모를 병기한다. 모델이 틀렸다는 이유로 예정 사례를 없애지 않는다. 다만 장비·코드 계약 오류를 모델 능력 실패로 섞지 않는다. 입력이나 실행 계약이 깨진 실행은 비교 해석을 중지하고 버전·영향 범위와 재실행 여부를 별도 기록한다.</p>
<p><strong>모든 C0 배분이 무효라면 비중 차이·수렴은 관측 불가다.</strong> 그 경우 설명 보존과 실행 실패만 보고하며 절차 효과가 없다거나 논문 전체 질문이 검증됐다고 하지 않는다. 수정 후 유효 배분이 생겨도 보조 결과로만 제시한다. 거리 감소만으로 해로운 동질화를, 거리 증가만으로 판단 보존 성공을 결론내리지 않는다.</p>''')

    readiness = section('readiness','6. 준비 상태와 다음 단계', '''
<p>이 버전은 문헌 검토를 반영한 재설계와 오프라인 입력·검토 서식이다. 새 평가명세·프롬프트 계약·수치 등록부·출처 간 비교 목록을 작성했지만 실행기 및 평가기에 통합한 뒤의 검증과 네 사례 예비실험은 아직 하지 않았다. v4.8 모델 호출은 0회이며 본실험도 0건이다. 설치된 모델은 Qwen3.5-4B의 Q4_K_M 실행본이고, 기존 실행에서 확인한 엔진 설정을 후보로 유지한다. 금융 논문의 기본 모델과 thinking 비활성화 선례를 참고하지만 양자화된 현재 실행의 성능을 그 논문 점수와 같다고 주장하지 않는다.</p>
<p>이전에는 산술 수정 성공을 후속 설계의 필수조건으로 묶었다. v4.8은 측정 체계의 정확성과 모델의 수행 결과를 분리한다. 원제안서도 JSON·합계 실패를 보존하고 실패율을 보고하며 복구 결과를 별도 표로 제시하도록 했다. Xiao 등(2026)의 <i>Trust, but Validate the Instrument</i>(v2, §§V–VII)의 측정 계약 검증 원칙을 참고하되 다른 분야의 평가 절차를 금융에 그대로 재현하는 것은 아니다. 과거 v4.5–4.7의 실패 판정을 소급하여 통과로 바꾸지 않는다.</p>'''+table(['순서','할 일','다음 단계로 가기 위한 검증'],[
        ['1 · 재설계','논문 질문·방법·평가·한계, 논문 근거, 공개 수치 주소와 검토지 정리','문서·명세 정합성 / 근거와 분모 / 주제 연결의 세 차례 자체 검토'],
        ['2 · 실행기 통합','R4 노출 차단, 미제안 상태, 근거 ID와 수치대조, C0 및 C1/C2 분리 구현','코드 계약 / 독립 산술·실패 경로 / 해석·기록의 세 검증'],
        ['3 · 전체 예비실험','두 예비 문서 × R1/R4를 고정 버전으로 실행하고 실패 포함 기록','입력·응답 보존 / 평가 재현 / 논리·논문 연결의 세 검증. 모델 정답을 강제하지 않음'],
        ['4 · 본실험 직전','독립 사람 원문 검토, 예비 결과에 따른 측정 가능 범위 보고, 규칙·해시 동결','미완료 검토를 표시하고 이후 변경은 탐색 분석으로 구별; 여기서는 본실험 미실행']])+'''
<p>문헌에서 가져온 실험 수치, 이 과제에 맞춘 설계 선택, PC 운영 설정을 구분한다. 60일·252·출력 상한 8192·최종 후보 3개에는 논문 선례가 있으나 과제·모델 간 전용임을 밝힌다. seed 3407 자체는 FinVector §4.1의 값이고 Ollama seed 필드에 적용하는 것은 엔진 변형으로, 동일 출력을 보장하지 않는다. 두 출처·네 단계·자료 날짜는 자료와 원제안서에 따른 설계다. 65,536 문맥 길이·900초 제한·스레드·배치·양자화·산술 허용오차는 관측 가능한 운영 설정이지 논문이 입증한 최적 수치가 아니다. 임의의 전략 정답이나 행동 임계값으로 사용하지 않는다.</p>''')

    choices = section('choices','선택안과 선택한 이유', table(['실험의 어느 부분인가','채택안','다른 후보와 이유'],[
        ['주결과','4단계 첫 최종안 C0','수정 후 답을 주결과로 쓰면 제공 절차와 추가 연산의 차이가 섞이므로 보조로 분리'],
        ['실패 뒤 수정','산술 무효의 완전한 C0만 최대 2회 사후 수정','단계별 반복은 R4 노출 위치·R1 활용 기회를 바꿈. 무제한 반복은 배제. 수정 없는 설계도 가능하나 현재는 회복 경로를 별도 관찰'],
        ['의미 평가','출처·수치·근거와 행동 연결을 분리한 검토지','등급만 채점하면 복사와 실제 반영을 구분 못함. 가중 종합점수는 근거 없는 가중치를 만들므로 미채택'],
        ['출력 형태','기존 7개 필드 안의 설명을 구체화','대규모 새 JSON 구조는 소형 모델의 형식 부담을 늘림. 형식 유지 선택은 구현 판단이며 성능 개선의 논문 결론이 아님'],
        ['사례 범위','공개 두 기관 전망 × R1/R4','실제 운용전략·종목 선택·수익 예측으로 넓히면 현재 자료가 뒷받침하지 못함'],
        ['실행 환경','현재 4B 실행본을 새 설계의 예비 후보로 유지','예비 결과로 비중 대비가 관측 불가이면 작은 다른 모델 또는 GPU의 큰 모델을 새 버전 후보로 검토. 성공 답을 얻기 위한 반복 교체는 하지 않음']])+'''
<p>지금 재설계 자체를 위해 새로 정해야 하는 전략 비중·가중치·기관 위험선호 수치는 없다. 독립 사람 검토자를 누가 맡을지와 최종 제출 분량·지정 양식은 아직 확정 정보가 필요하다. 현재 확인된 개요는 11월 1일 텀페이퍼 제출, 11월 6일 발표, APA 인용이다. 자체 검토 세 번은 사람 원문 검토를 대신하지 않으며 실험 결과가 제출 필수인지도 임의로 단정하지 않는다.</p>''')

    implications = section('implications','7. 예상 기여와 해석의 한계', '''
<p>연구의 기여는 어떤 산업에 더 투자하라는 처방이 아니라, 조직이 AI를 사용할 때 문서화된 판단의 전달 경로를 관찰 가능한 형태로 만드는 데 있다. 초기 제공이 근거 보존과 선택의 일치를 개선하는 사례가 나오면 초기 자료 연결과 후속 검토를 함께 설계할 이유를 논의할 수 있다. 최종 제공이 더 나은 사례나 혼합·불명확 결과가 나오면 그대로 보고한다. 결과 전에는 어느 절차도 입증된 해결책이 아니다.</p>
<p>같은 두 기관의 이전 문서를 개발에 사용했고 Fidelity Q2/R1은 반복 진단에 노출되었다. 예비 사례는 독립적인 확증 표본이 아니다. 두 문서와 한 시장 상태, 소형 양자화 모델 한 개만으로 기관 모집단·공통 AI 도입의 인과효과·시장 안정성을 일반화할 수 없다. 문서 요약, 서로 다른 공개일과 평가척도, 현재 빈티지 가격, 원문의 분석 종목과 공통 기준의 차이도 한계다.</p>
<p>정성 전망에는 유일한 비중 정답이 없다. 출처가 다른데 제안이 비슷하다는 사실만으로 필요한 다양성이 소실되었다고 할 수 없다. 본사례에서 원안의 비중 비교가 불가능하면 그 부분은 미검증으로 남는다. 설명을 평가할 수 있다는 이유로 배분 비교의 실패를 감추지 않는다. 후속 연구는 자료·기관·시장 상태·모델을 확대하고, 실제 검색과 비사용 비교군을 별도로 설계해야 한다.</p>''')

    conclusion = section('conclusion','8. 결론', '''
<p>본 소논문은 공통 생성형 AI와 조직 판단의 관계를 공개 산업전망의 해석에서 배분 제안까지 이어지는 사례 설계로 구체화한다. 원문 등급의 복사, 실행 가능한 숫자, 근거에 맞는 결정은 서로 다른 성질이므로 분리하여 관찰한다. R1/R4의 첫 최종안을 중심에 두고 복구는 보조로 구분함으로써, 산술 수정 능력이 논문의 질문을 대신하지 않도록 한다. 현재는 재설계 단계이며 문헌이 제안하는 방법의 타당성과 실제 모델이 수행한 결과를 구별한다.</p>''')

    appendix = section('appendix','부록 · 개발 기록과 재현 자료', '''
<p>v4.5의 단일 Fidelity Q2/R1 네 단계에서 최종 합계는 96.5%였다. v4.6의 한 번 수정도 96.5%, v4.7의 계획→실행 진단은 97.5%로 완전투자 조건을 충족하지 못했다. 과거 검증의 FAIL과 원응답은 보존한다. 이 값은 본실험 결과나 R1/R4 차이가 아니다. 새로운 준비 게이트를 정했다고 모델 오류가 해결된 것은 아니다.</p>
<p>별도 FF12 수치 과제는 2024–2025의 24개 월별 창과 위험회피계수 1·3·5에 대해 72개 계산 참조를 준비했다. AI의 72회 성공 결과가 아니다. 기관의 정성 판단을 그 계수로 바꾸지 않으며, 문서 판단 보존의 검증을 대신하지 않는다. 상세 수치 근거와 과거 설계는 이전 문서에 보존한다.</p>'''+f'''<ul>
<li><a href="../data/sector_protocol/v48_design_{DATE}/prompt_contract.json">v4.8 프롬프트·사후 수정 계약</a></li>
<li><a href="../{FACTS}">공개 수치 근거 등록부</a> · 기존 입력 수치를 재계산 없이 주소화</li>
<li><a href="../{INVENTORY}">평가자용 출처 비교 목록</a> · 온라인 모델 입력 금지, 사람 판정 미기입</li>
<li><a href="../research/v48_review_template_{DATE}.json">빈 의미·수치 검토지</a></li>
<li><a href="../research/v48_topic_alignment_basis_{DATE}.json">원제안서 및 주제 연결 근거</a></li>
<li><a href="../research/v48_parameter_reference_addendum_{DATE}.json">60일·252·출력 상한·seed의 정확한 논문 위치</a></li>
<li><a href="../research/v47_handoff_{DATE}.json">v4.7 전달·실패 기록</a> · <a href="../paper/LIBERA_텀페이퍼_초안_v4.7_{DATE}.html">이전 초안</a></li>
</ul>''')

    references = deepcopy(old_paper.select_one('#references'))
    for li in list(references.select('li')):
        t = li.get_text(' ',strip=True)
        if t.startswith('Zhu, D.'):
            li.decompose()
            continue
        notes = {
            'Kim, S.': 'v4.8 공통 수치 등록과 주장 추적의 방법 근거. §§3.4–4.1.2. 현재 실행기 통합은 미완료.',
            'Wang, W.': 'v4.8 출처·기간·단위·계산 경로 추적의 방법 근거. §§2.2.2–2.3. 자유서술 자동 인증이 아님.',
            'Wang, X.': 'v4.8 근거–판단 이유–행동 및 응답 범위 구분. §§3.1–3.4, 4.2. §4.3.3은 해당 근거 위치가 아님.',
            'Yang, C.-H.': '첫 최종안과 사후 회복 분리 및 최종 후보 총 3개의 선례: §§3.2–3.4, 부록 H·I 표 12. 4단계 뒤 적용과 전체 이력 유지 등은 LIBERA 변형.',
            'Zhao, Y.': '2026년 10월 9일 v6. §3.1(T=0, 8192), 부록 C.1 T5(60일), C.2 식 8(비중 유사성), C.4·F.9(공분산·연율화 252). 과제 간 전용이며 전체 재현이 아님.',
            'Zhang, J.': '실제 오류와 이전 제출을 사용한 유한 수정의 방법 선례: §III-B. PDDL 정답과 성과를 금융 과제로 전용하지 않음.'}
        for start, note in notes.items():
            if t.startswith(start):
                for n in li.select('.refnote'): n.decompose()
                span=old_paper.new_tag('span',attrs={'class':'refnote'});span.string=note;li.append(span)
    basis = read(f'research/v48_reference_basis_{DATE}.json')
    instrument = next(p for p in basis['papers'] if p['id']=='instrument')['bibliography']
    li = old_paper.new_tag('li')
    li.append(instrument['apa_text']+' ')
    a=old_paper.new_tag('a',href='https://arxiv.org/abs/2609.19844v2');a.string='원문 v2';li.append(a)
    span=old_paper.new_tag('span',attrs={'class':'refnote'});span.string='측정 계약과 모델 성능의 구별: §§V–VII. 다른 분야 방법론의 적용이며 금융 실험의 직접 재현이 아님.';li.append(span)
    references.select_one('ul').append(li)
    ref_list=references.select_one('ul')
    for item in sorted(list(ref_list.find_all('li',recursive=False)),key=lambda item:item.get_text().casefold()):
        ref_list.append(item.extract())
    intro = deepcopy(old_paper.select_one('#intro'))
    intro.find_all('p')[-1].string = '경제학적으로는 정보와 판단에 따른 자본 배분의 문제이며, 경영학적으로는 AI 업무의 근거 전달과 재검토 책임의 문제다. 공개 산업전망으로 관찰할 수 있는 범위에 연구질문을 맞추고, 두 문서의 R1/R4 사례에서 원문 판단·선택 이유·산업 비중의 관계를 검토한다. 자료와 오프라인 설계를 준비했으며 새 실행기 통합·전체 예비실험·사람 검토 및 본실험은 남아 있다.'
    literature = deepcopy(old_paper.select_one('#literature'))
    extra = BeautifulSoup('<h3>2.5. 정답 비중보다 근거와 행동의 연결</h3><p>E2A-Bench(X. Wang et al., 2026)는 유일한 투자 행동을 전제하지 않고 사실 근거와 행동 이유, 응답 범위를 나누어 평가한다. Reasoning Externalization(Kim et al., 2026)은 공통 수치 근거와 구조화된 주장의 추적을, FinFIRST(W. Wang et al., 2026)는 출처·정의·기간·단위의 연결을 구체화한다. 이를 통해 문서 등급을 정확히 복사했어도 선택을 설명하지 못하는 경우를 구별할 수 있다. 본 연구는 이러한 평가 원칙을 산업 배분에 적용하되 각 논문의 과제·모델·종합점수까지 재현했다고 주장하지 않는다.</p>','html.parser')
    literature.append(extra)
    abstract = '''<div class="abstract"><h2>초록</h2><p>공통 생성형 AI가 기관별 판단을 최종 선택에 반영하는가는 답변의 유사성이나 원문 등급 복사만으로 평가할 수 없다. 본 연구는 알고리즘 동질화 및 금융 AI 문헌을 검토하고, Fidelity와 UBS의 공개 산업전망을 사용하는 미국 11개 산업 배분 사례를 설계한다. 같은 시장자료·모델·계산 지원 아래 기관 문서를 처음 또는 마지막 단계에 제공하고, 네 번째 단계의 첫 최종안에서 원문 사실, 근거와 선택의 연결, 배분의 실행 가능성을 분리하여 관찰한다. 실패를 포함한 전체 사례를 보고하고 유효 배분쌍에서만 비중 차이를 계산한다. 제한된 사후 수정은 보조 분석으로 남기며 최초 답을 대체하지 않는다. 현재는 재설계와 오프라인 자료 준비 단계이고 새 절차의 실험 결과는 없다. 두 문서 사례가 공통 AI 도입의 인과효과나 시장 전체의 동질화를 식별하지는 않지만, 조직의 판단 근거가 AI 업무를 거쳐 결정에 전달되는 과정을 검토하는 틀을 제시한다.</p><p class="meta">주제어: 생성형 AI, 조직 의사결정, 산업 배분, 기관별 투자판단, 근거 보존</p></div>'''
    sectors = old_plan.select_one('#plain table')
    sectorsection = section('sectors','투자 대상 11개 산업', str(sectors)+'<p>공표 기준의 합계는 99.9%이며 계산용으로만 정규화한다. 표의 등급은 본과제 원문값이다. Fidelity와 UBS의 다른 평가 단어를 같은 척도로 바꾸지 않으며 실제 기관의 보유비중으로 해석하지 않는다.</p>')
    def document(title, subtitle, body):
        return f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · LIBERA v4.8</title><style>{style}</style></head><body><main class="paper-body"><header><div class="eyebrow">LIBERA 2026 · VERSION 4.8</div><h1>{title}</h1><p class="subtitle">{subtitle}</p><p class="meta">2026년 10월 18일 · 문헌 검토와 실험 전 설계 · 저자 정보 제출 전 기입</p><div class="status">{status}</div>{links}</header>{body}<footer>v4.8 · 이전 버전과 실패 원문을 보존한다. 자체 설계 검토는 독립 사람의 원문·결과 검토나 본실험 완료를 뜻하지 않는다.</footer></main></body></html>'
    (ROOT/PAPER).write_text(document('공통 생성형 AI는 기관별 투자판단을 보존하는가?', '공개 산업전망의 제공 절차와 근거–배분 연결에 관한 사례 설계', abstract+str(intro)+str(literature)+framework+design+evaluation+readiness+implications+conclusion+str(references)+appendix),encoding='utf-8')
    (ROOT/PLAN).write_text(document('기관의 판단이 AI 배분에 남는지 비교하는 실험', 'v4.8 재설계 · 최초 최종안 중심의 R1/R4 비교',plain+sectorsection+framework+design+evaluation+readiness+choices+implications+str(references)+appendix),encoding='utf-8')
    print(json.dumps({'plan':PLAN,'paper':PAPER,'config':CONFIG,'registry_facts':58,'model_calls':0},ensure_ascii=False))


if __name__ == '__main__':
    build()
