"""Build the dated common-context design. Offline preparation, never inference.

Preserves v4.9 and all historical execution records. Run after the source audit
and mandate-basis artifacts exist. Draft previews are prepared inputs, not runs.
"""
from __future__ import annotations
import copy
import hashlib
import html
import json
from pathlib import Path

from bs4 import BeautifulSoup
from v49_compaction_review_20261019 import table, untab

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/sector_protocol/v491_design_20261019'
CONTEXT = ROOT / 'data/sector_context/v491_20261019'
CONFIG = ROOT / 'plan/LIBERA_실험설정_v4.9.1_20261019.json'
PLAN = ROOT / 'plan/LIBERA_공통상황포함_실험계획_v4.9.1_20261019.html'
METHOD = ROOT / 'paper/LIBERA_소논문_방법개정안_v4.9.1_20261019.html'
PAPER = ROOT / 'paper/LIBERA_텀페이퍼_초안_v4.9.1_20261019.html'


def read(p):
    return json.loads((ROOT / p).read_text(encoding='utf-8-sig'))


def save(p, value):
    p = ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')


def ref(p):
    p = ROOT / p
    return {'path': p.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}


def write_html(p, value):
    p.write_text(value+'\n', encoding='utf-8', newline='\n')


def operating_brief():
    # Exact 12-month condition exists in Hornuf Table A1. Selecting this one
    # condition and the equity-sleeve scope are local adaptations, not its result.
    facts = [
        ('CTX:task', 'This is a hypothetical research assignment to recommend a new US equity-sector sleeve, not to impersonate any institution or infer its private mandate.'),
        ('CTX:date', 'Use a 2026-07-17 decision reference and only supplied observations and public releases before that date. This is a documentary retrospective case, not a point-in-time trading replay.'),
        ('CTX:horizon', 'The allocation judgment horizon is 12 months. This is not a 12-month realized-return test. Document view dates and horizons remain those of their respective sources.'),
        ('CTX:objective', 'Propose a reasoned allocation intended for capital appreciation over the stated horizon, explaining diversification and risk-return trade-offs relative to the common sector benchmark. No required return or unique optimal allocation is specified.'),
        ('CTX:risk', 'The hypothetical assignment accepts equity-market loss risk and provides no capital guarantee. No numerical risk-aversion coefficient, volatility ceiling, loss budget or sector cap is supplied. Do not invent one; discuss remaining risk and uncertainty.'),
        ('CTX:starting_state', 'This is new money assigned to an equity sleeve with no existing sector holdings. Recommend target weights, not trades from current holdings. The S&P sector benchmark is only a comparison anchor and is not the starting portfolio.'),
        ('CTX:universe', 'Use exactly the supplied 11 GICS sector baskets, with one row for each sector including zero weights. The submitted allocation must be long-only, unlevered and fully invested: raw weights sum to one. Individual stocks, cash, bonds and derivatives are outside this sleeve task.'),
        ('CTX:scope', 'The deliverable is an allocation proposal for review, not a trade order or a whole-client financial plan. Transaction costs, turnover, tax optimization, withdrawals and actual client suitability are not measured. Do not invent missing client or liquidity requirements.'),
        ('CTX:liquidity_and_ESG', 'For this hypothetical sleeve there are no scheduled withdrawals during the judgment horizon and no separate ESG exclusion. These are declared task assumptions, not observed facts about a real institution or customer.'),
        ('CTX:evidence_use', 'Use dated market observations and any institution packet currently supplied. Published outlook ratings are not binding weight constraints or target holdings. Explain justified adoption, qualification or departure and any age/horizon mismatch. Do not assume the outlook author had observed later common market releases.'),
    ]
    return {
        'assignment_type': 'hypothetical_new_US_equity_sector_sleeve',
        'decision_reference_date': '2026-07-17',
        'information_cutoff_exclusive': '2026-07-17',
        'judgment_horizon_months': 12,
        'horizon_end_reference': '2027-07-17',
        'decision_type': 'new_target_allocation_not_rebalancing',
        'existing_sector_holdings': None,
        'existing_holdings_meaning': 'No sector portfolio exists within this new-money task; null is not unknown actual institutional holdings.',
        'benchmark_role': 'comparison_only_not_holdings_not_gold',
        'numeric_risk_limit': None,
        'numeric_utility_coefficient': None,
        'required_return': None,
        'evidence_items': [{'evidence_id': eid, 'statement': text, 'evidence_type': 'declared_research_task_not_empirical_institution_fact'} for eid, text in facts],
    }


def prepare_design():
    macro = read('data/sector_context/v491_20261019/market_context.json')
    basis = read('research/v491_mandate_basis_20261019.json')
    if not macro.get('facts') or not basis:
        raise ValueError('Audited macro facts and mandate basis required')
    model_macro = {k: copy.deepcopy(macro[k]) for k in ('packet_id', 'cutoff_exclusive',
        'cutoff_timezone', 'decision_information_date', 'role', 'information_policy')}
    model_macro['fact_table'] = table(macro['facts'])
    model_macro['representation'] = 'Each row inherits shared fields; columns identify row positions. All source fact fields are retained losslessly. Literature selection audit is outside model input.'
    if untab(model_macro['fact_table']) != macro['facts']:
        raise ValueError('Macro fact factoring changed information')
    context = {'protocol_version': '4.9.1', 'operating_brief': operating_brief(), 'market_context': model_macro}
    save(CONTEXT/'common_context.json', context)

    candidate = read('data/sector_protocol/v49_design_20261019/public_compact_candidate.json')
    candidate['status'] = 'offline_common_context_candidate_not_a_model_request'
    candidate['common_context'] = context
    candidate['common_market']['baseline_derivation'] = (
        'Each reported percentage divided by the reported 99.9 total, solely to obtain an exact '
        'sum-one COMPARISON benchmark. It is not current holdings, a starting portfolio, '
        'additional source precision, or institutional target weights. Model outputs are never normalized.')
    candidate['meaning'] = 'Offline aggregate only. Build a case using exactly its assigned source packet. Never send this aggregate to a model.'
    save(OUT/'public_compact_candidate.json', candidate)

    schema = read('data/sector_protocol/v49_design_20261019/response_schema.json')
    text = {'type': 'string', 'minLength': 1}
    fields = {'market_and_mandate_reading': text, 'allocation_implication': text,
              'evidence_ids': {'type': 'array', 'items': text}, 'limitations': text}
    schema['properties']['context_assessment'] = {
        'type': 'object', 'properties': fields, 'required': list(fields), 'additionalProperties': False}
    schema['required'].append('context_assessment')
    save(OUT/'response_schema.json', schema)

    contract = read('data/sector_protocol/v49_design_20261019/prompt_contract.json')
    contract['protocol_version'] = '4.9.1'
    contract['status'] = 'offline_buildable_contract_not_live_runtime_validated'
    contract['system'] += (
        ' Follow the common operating brief: new money allocated to an equity sleeve over a 12-month judgment horizon. '
        'The benchmark is a comparison anchor, never actual holdings. Do not fabricate institutional objectives or client risk limits. '
        'Read public release dates separately from observation periods; do not call a quarter annualized growth rate a year-over-year rate. '
        'A macro observation is evidence for discussion, not a compulsory sector-weight signal or a forecast. '
        'In context_assessment, explain the common market and mandate, their implications for your allocation, visible evidence IDs, '
        'and limitations including source age or horizon mismatch when relevant. Do not claim that an older report knew a later release. '
        'You need not cite every supplied indicator or force a nonzero portfolio change; support the claims you actually make.')
    contract['D0_instruction'] += (
        ' The common_context is available from this first task in every case. Consider the task objective, horizon and '
        'new-money status together with historical sector diagnostics and dated macro facts. '
        'Give the required context_assessment without assuming that the source report is current as of every market observation.')
    contract['F0_instruction'] += (
        ' Keep the same operating brief, macro snapshot and benchmark in the retained history. '
        'Explain how current supplied market evidence interacts with the dated source view; '
        'do not silently reinterpret the source view as a later publication or a binding mandate.')
    contract['public_input'] = 'Identical common_market, public_numeric_fact_index and common_context in every D0; all retained verbatim for F0.'
    contract['implementation'] = 'research/sector_v491_contract.py'
    contract['no_semantic_success_gate'] = 'Input leakage fails closed. Output citation/label errors are recorded outcomes, not reasons to drop an otherwise readable draft. Schema/vector readability and arithmetic validity are separate.'
    save(OUT/'prompt_contract.json', contract)

    config = read('plan/LIBERA_실험설정_v4.9_20261019.json')
    config['protocol_version'] = '4.9.1'
    config['status'] = 'context_complete_offline_preparation_pending_live_runtime_human_review_freeze'
    config['prior_protocol'] = ref('plan/LIBERA_실험설정_v4.9_20261019.json')
    config['research_question_ko'] = '공통 운용 과제와 동일한 시장상황에서 AI는 기관별 공개 산업판단을 근거 있는 배분 제안에 어떻게 반영하며, 자료의 초안 전후 제공에 따라 그 연결이 어떻게 달라지는가?'
    config['final_controls']['same_operating_brief_from_D0'] = True
    config['final_controls']['same_dated_macro_context_from_D0'] = True
    config['data']['compact_candidate'] = ref(OUT/'public_compact_candidate.json')
    config['data']['common_context'] = ref(CONTEXT/'common_context.json')
    config['data']['macro_source_audit'] = ref('research/v491_macro_source_audit_20261019.json')
    config['data']['baseline'] = 'Common S&P500 sector comparison benchmark only; new-money task has no existing sector portfolio'
    config['task'] = operating_brief()
    config['task_basis'] = ref('research/v491_mandate_basis_20261019.json')
    config['evaluation_path'] = 'research/v491_evaluation_protocol_20261019.json'
    config['schema_path'] = (OUT/'response_schema.json').relative_to(ROOT).as_posix()
    config['prompt_contract_path'] = (OUT/'prompt_contract.json').relative_to(ROOT).as_posix()
    config['offline_contract_implementation'] = 'research/sector_v491_contract.py'
    config['model']['runtime_validated'] = False
    config['current_state'] = {'v491_model_calls': 0, 'v491_pilot_calls': 0, 'v491_main_calls': 0,
        'independent_human_review_completed': False, 'frozen': False,
        'offline_prompt_and_calculator_contract_implemented': True, 'live_v491_runner_validated': False}
    config['failure_policy'] = ('No retries or replacement. Draft transport, JSON/schema or complete finite-vector failure prevents the dependent final. '
        'Raw-sum failures and unsupported output citations/labels remain measured outcomes and do not censor readable drafts. '
        'The input visibility boundary is enforced before requests. Never supply hidden reference facts to correct model claims.')
    config['pre_main_requirements'] = ['ordered offline evidence/implementation/topic checks',
        'supported backend with exact full-history token feasibility and no truncation',
        'separately logged four-case pilot under this context',
        'independent human source/meaning review',
        'freeze exact inputs, model, evaluation, execution order and resource ceilings']
    save(CONFIG, config)

    evaluation = read('research/v49_evaluation_protocol_20261019.json')
    evaluation['protocol_version'] = '4.9.1'
    evaluation['common_task'] = ref(CONTEXT/'common_context.json')
    evaluation['dimensions']['context_use'] = {
        'assess': ['correct decision date versus release date and observation period',
                   '12-month judgment horizon without claiming realized 12-month performance',
                   'new-money allocation with benchmark used only as comparison',
                   'supplied macro observations distinguished from forecasts and later information',
                   'explicit supported connection between common context, source view and actual allocation',
                   'report age and horizon mismatch acknowledged without fabricating updated institutional views',
                   'no invented risk coefficient, numeric risk limit, private objective or holdings'],
        'categories': ['supported_link', 'unsupported_or_contradictory_link', 'unresolved', 'missing_or_not_assessable'],
        'rule': 'Evaluate claims actually made. Merely listing facts is not application. Do not require a citation count, a predetermined macro-to-sector direction, or mechanically different weights.',
        'no_composite_score': True}
    evaluation['descriptive_comparisons']['benchmark'] = 'Descriptive comparison only. It is neither current holdings nor a non-AI arm. Distance to it is active allocation, not trading turnover.'
    evaluation['not_identified'] += ['12-month realized investment performance', 'transaction-cost-adjusted rebalancing quality',
        'whole-investor suitability', 'macro-context addition effect without a no-context arm']
    evaluation['context_temporal_scope'] = 'Same July snapshot is used even with older pilot reports. This is a frozen-document task, not a simulation that authors saw later macro releases.'
    evaluation['outcome_preservation'] = config['failure_policy']
    evaluation['common_anchor_limit'] = 'A shared benchmark and common objective can rationally produce similar weights; output similarity alone cannot show loss of institutional judgment.'
    save('research/v491_evaluation_protocol_20261019.json', evaluation)

    template = read('research/v49_human_review_template_20261019.json')
    template['protocol_version'] = '4.9.1'
    template['common_context'] = ref(CONTEXT/'common_context.json')
    template['semantic_fields'] += ['context_assessment_quote', 'context_use', 'source_age_and_horizon', 'benchmark_not_holdings']
    template['context_review_before_outputs'] = {'macro_release_dates_and_values': None, 'task_vs_institution_fact_distinction': None,
        'report_date_and_horizon_scope': None, 'reviewer_1': None, 'reviewer_2': None, 'resolution': None}
    save('research/v491_human_review_template_20261019.json', template)
    return context, candidate, contract, schema


def context_section(macro):
    # Show each supplied fact without an added narrative recommending industries.
    rows = []
    labels = {
        'MACRO_FED_TARGET_20260617': '연방기금금리 목표범위',
        'MACRO_CPI_HEADLINE_MOM_202606': '소비자물가 전월 대비 · 계절조정',
        'MACRO_CPI_HEADLINE_YOY_202606': '소비자물가 전년 대비 · 비조정',
        'MACRO_CPI_CORE_YOY_202606': '근원 소비자물가 전년 대비 · 비조정',
        'MACRO_UNEMPLOYMENT_202606': '실업률 · 계절조정',
        'MACRO_NONFARM_CHANGE_202606': '비농업 고용 전월 증감 · 계절조정',
        'MACRO_REAL_GDP_Q1_2026_THIRD': '실질 GDP 전기 대비 연율 · 계절조정 · 3차 추계',
    }
    for f in macro['facts']:
        label = labels.get(f['evidence_id'], f.get('label', f['evidence_id']))
        value = f.get('value')
        if isinstance(value, dict):
            display = f"{value['lower']:.2f}–{value['upper']:.2f}%"
        elif f['evidence_id'] == 'MACRO_NONFARM_CHANGE_202606':
            display = f'{value:+,}명'
        else:
            display = f'{value:g}%'
        period = f.get('observation_period', f.get('period', ''))
        release = f.get('publication_date', f.get('release_date', ''))
        url = f.get('source_url', '')
        rows.append('<tr><td>'+html.escape(str(label))+'</td><td>'+html.escape(display)+
                    '</td><td>'+html.escape(str(period))+'</td><td><a href="'+html.escape(url, quote=True)+'">'+html.escape(str(release))+'</a></td></tr>')
    return '''<section id="context"><h2>공통 업무와 시장상황: AI가 실제로 받는 조건</h2>
<p><strong>업무:</strong> 새로 맡긴 미국 주식 투자금을 11개 산업 바구니에 배분하는 제안서를 만든다. 판단 기준일은 2026년 7월 17일이며, 7월 16일까지의 가격과 7월 17일 전에 발표된 아래 공개 통계를 사용한다. 이 자료는 모든 E/L 사례의 초안부터 동일하게 들어간다.</p>
<p><strong>목적과 기간:</strong> 12개월을 내다보고 자본증식을 위한 배분을 제안하되, 분산과 위험의 대가를 설명한다. 12개월은 Hornuf 등의 Table A1에 사용된 1·6·12개월 중 채택한 조건이다. 최적 기간이라는 뜻이 아니며 12개월 후 수익률을 이번 연구에서 측정한다는 뜻도 아니다. 기존 포트폴리오를 고치는 과제가 아니므로 실제 보유 비중과 거래회전율을 가정하지 않는다.</p>
<p><strong>위험과 제약:</strong> 주식시장 손실 가능성을 수용하는 가상 주식 투자 과제다. 차입·공매도 없이 주어진 산업에 전액 배분하고 비중 합계는 100%가 되어야 한다. 허용손실률·위험회피계수·산업별 상한·목표수익률은 정하지 않았다. 공개 전망에서 알 수 없는 기관의 목적이나 임의 숫자를 만들어 넣지 않고, 남은 불확실성과 위험–수익 상충을 설명하게 한다. 이는 고객의 전체 재산에 대한 투자 적합성 평가가 아니다.</p>
<p><strong>현재 보유상태:</strong> 신규 자금이므로 기존 산업 보유분은 없다. S&amp;P 500 산업 비중은 비교 기준이며 기관의 현재 보유량이나 정답 배분이 아니다. 기준과 얼마나 다르게 제안했는지는 설명하지만, 그 거리를 실제 매매량이나 비용으로 부르지 않는다.</p>
<p>가상 업무의 조건으로 해당 기간의 예정된 인출과 별도 ESG 제외조건은 없다고 명시한다. 실제 고객·기관의 사정이라는 뜻은 아니다. 돈의 액수는 임의로 만들지 않고 맡긴 주식 투자금의 비중으로 제안한다.</p>
<div class="table"><table><thead><tr><th>공통 공개 지표</th><th>발표 값</th><th>관측 기간</th><th>발표일·공식 출처</th></tr></thead><tbody>'''+''.join(rows)+'''</tbody></table></div>
<p>이 표에 기존 산업별 수익률·변동성·상관관계·공분산과 기준 산업비중이 함께 제공된다. 각 지표는 발표일과 관측기간을 따로 기록한다. 분기 GDP의 전기 대비 연율, CPI의 전월·전년 변화율, 실업률의 수준을 섞지 않는다. 전부 같은 달의 지표라는 뜻도 아니다.</p>
<p>기관 보고서가 먼저 발표되고 시장 지표가 나중에 발표된 경우, AI는 그 차이를 명시하며 현재 주어진 시장자료와 기존 전망을 함께 검토한다. 기관이 나중 정보를 이미 알고 있었다고 바꾸어 쓰면 오류다. 개발용 Q2·6월 문서에도 같은 7월 상황을 쓰므로, 이를 과거 운용의 실시간 재현이라고 하지 않는다. 기존 ETF 조정가격은 현재 수집본이라는 한계도 유지한다.</p>
<p>시장 상황은 연구자가 특정 산업 매수를 지시하는 서술로 만들지 않았다. AI가 무엇을 근거로 어떤 선택을 했는지 평가하며, 모든 지표를 인용하거나 비중을 반드시 바꾸도록 강요하지 않는다. 공통상황 추가의 효과 자체는 별도 대조군이 없어 추정하지 않는다.</p>
<p class="note">근거: <a href="https://arxiv.org/html/2605.27887v6">PortBench v6 §2.1·Appendix B·H.1</a>의 시장·거시·포트폴리오 상황 구성, <a href="https://www.ifo.de/DocDL/cesifo1_wp11862.pdf">Hornuf 등 §3·Table A1</a>의 투자자 조건과 판단기간. 개별 미국 공식 지표의 선택과 신규 주식 부문 과제는 우리 연구의 적용 선택이다. <a href="../research/v491_mandate_basis_20261019.json">선택 근거표</a> · <a href="../research/v491_macro_source_audit_20261019.json">공식 통계 출처·시점 검증</a> · <a href="../data/sector_context/v491_20261019/common_context.json">실제 공통 입력 JSON</a></p>
<p class="note"><a href="https://arxiv.org/html/2503.09647v5">Quek 등(2025), §§3–4</a>는 산업배분 입력에 금리·물가·고용·성장 범주와 CPI·비농업고용을 사용하며 공식 발표일을 기준으로 정보를 제한한다. <a href="https://arxiv.org/html/2608.30110v1">LiveMacroEval(2026), Appendix D Table 2</a>는 GDP 전기비 연율·CPI 전년비·고용 증감·실업률의 단위와 정의를 구분한다. 여기서는 발표된 사실을 배경정보로 쓰며, 그 연구의 예측 목표·매매전략·수익률·비중 규칙을 가져오지 않는다. 7개 항목이 최적 조합이라고 주장하지 않는다.</p>
</section>'''


def replace_section(soup, section_id, markup):
    old = soup.find(id=section_id)
    if old is None:
        raise ValueError('Missing section '+section_id)
    old.replace_with(BeautifulSoup(markup, 'html.parser').section)


def prepare_documents(context):
    raw = (ROOT/'plan/LIBERA_축소실험계획_v4.9_20261019.html').read_text('utf-8')
    # Preserve historical v4.9 references unless the corresponding artifact is replaced.
    raw = raw.replace('v4.9', 'v4.9.1')
    raw = raw.replace('LIBERA_축소실험계획_v4.9.1_20261019.html', PLAN.name)
    raw = raw.replace('v49_evaluation_protocol_20261019', 'v491_evaluation_protocol_20261019')
    raw = raw.replace('v49_human_review_template_20261019', 'v491_human_review_template_20261019')
    raw = raw.replace('v49_design_20261019', 'v491_design_20261019')
    soup = BeautifulSoup(raw, 'html.parser')
    soup.find(id='plain').insert_after(BeautifulSoup(context_section(read('data/sector_context/v491_20261019/market_context.json')), 'html.parser').section)
    soup.nav.append(BeautifulSoup('<a href="#context">공통 업무·시장상황</a>', 'html.parser'))
    for p in soup.select('#plain p')[:2]:
        fragment = str(p).replace('시장자료', '공통 업무·시장자료')
        p.replace_with(BeautifulSoup(fragment, 'html.parser').p)
    for td in soup.select('#design td'):
        if '공통 시장자료' in td.get_text():
            td.string = td.get_text().replace('공통 시장자료', '공통 업무·시장자료')
    outdated = soup.select_one('#output p.note')
    outdated.replace_with(BeautifulSoup('''<p class="note">새 오프라인 코드가 단계별 자료 선택, 11개 고유 산업·유한 비중 검사, 원배분 계산과 최종 이력 보존을 연결한다. 출력의 잘못된 등급·인용은 평가할 오류로 남기며, 읽을 수 있는 초안을 의미 정답 여부로 탈락시키지 않는다. 입력 단계에서는 다른 기관·평가자 자료를 차단한다. 실제 모델 전송과 장치 안정성은 별도 실행 검증 대상이다.</p>''', 'html.parser').p)
    soup.find(id='output').append(BeautifulSoup('''<p>공통 <code>context_assessment</code>에는 업무·시장 해석, 실제 배분에 대한 함의, 근거 ID와 한계를 기록한다. 산업별 판단 11행은 유지하며, 전 산업에 같은 거시 설명을 반복하도록 요구하지 않는다.</p>''', 'html.parser').p)
    soup.find(id='outcomes').append(BeautifulSoup('''<p><strong>공통상황 활용 평가:</strong> 기준일·발표일·관측기간, 신규자금 상태, 12개월 판단기간을 정확히 이해했는지, 시장 근거와 기관 전망을 비교한 설명이 실제 비중과 맞는지 본다. 사실 나열, 근거 없는 업종 방향, 보고서 날짜 바꾸기, 가짜 보유량·위험한도는 구분하여 기록한다. 지표 인용 개수나 임의 가중점수는 사용하지 않는다. 공통 목적과 기준비중이 같아 합리적으로 비슷한 배분이 나올 수 있다는 대안 설명을 유지한다.</p>''', 'html.parser').p)
    soup.find(id='cost').append(BeautifulSoup('''<p class="note">위 바이트 비교는 v4.9의 표현 압축에 한정된 과거 측정이다. v4.9.1에는 업무·거시 자료와 출력 필드가 추가되므로 그 감소율을 새 전체 입력이나 속도에 적용하지 않는다. 호출 상한은 여전히 묶음당 8회다.</p>''', 'html.parser').p)
    replace_section(soup, 'gates', '''<section id="gates"><h2>9. 검증과 실행 전 남은 조건</h2>
<p>검증은 순서대로 진행한다. 1차는 공개 원문·발표일·단위·입력 일치와 오프라인 코드, 2차는 논문 근거 및 전체 계획·소논문·평가의 논리, 3차는 앞선 수정 반영 후 주제 연결과 반례를 확인한다. 결과는 <a href="../research/v491_validation_round1_20261019.json">1차</a>, <a href="../research/v491_validation_round2_20261019.json">2차</a>, <a href="../research/v491_validation_round3_20261019.json">3차</a>에 기록한다. AI 검증은 독립 사람 검토나 실제 모델 성공의 증거가 아니다.</p>
<p>공통 업무·시장 입력, 모델용 초안 메시지, 최종 메시지 조립·검사 코드와 평가명세를 준비했다. 실제 전송 백엔드와 전체 이력의 토큰·메모리 검증, 새 조건의 네 사례 예비실험, 두 사람의 출처·의미 검토, 실행순서·자원한도·모델을 포함한 본실험 동결은 남아 있다. 현재 모델 호출·본실험 결과는 0건이다.</p>
<p>자료가 늘어난 이후 속도를 추정하지 않는다. 예비실험은 E가 이기는지나 근거가 맞는지로 설계를 고르는 과정이 아니다. 실행 실패와 관측 가능한 결과를 분리하고, 본실험 결과를 본 뒤 지표·산업·문서를 바꾸지 않는다.</p></section>''')
    soup.find(id='files').append(BeautifulSoup('''<ul><li><a href="../paper/'''+PAPER.name+'''">공통상황을 통합한 텀페이퍼 전체 초안</a></li><li><a href="../data/sector_protocol/v491_design_20261019/prepared/preparation_manifest.json">초안 입력 8건의 파일·동일성 기록</a> — 예비 4건·본 4건의 준비 입력이며 생성 결과가 아니다.</li><li><a href="../research/sector_v491_contract.py">오프라인 입력·최종안 조립·검사 코드</a> · <a href="../research/v491_handoff_20261019.json">최종 인계 기록</a></li></ul>''', 'html.parser'))
    for link in soup.select('a[href]'):
        link['href'] = link['href'].replace('v491_validation_round1_20261019.json', 'v491_validation_round1_20261019_r2.json').replace('v491_validation_round2_20261019.json', 'v491_validation_round2_20261019_r2.json')
    write_html(PLAN, str(soup))

    old_method = (ROOT/'paper/LIBERA_소논문_방법개정안_v4.9_20261019.html').read_text('utf-8')
    old_method = old_method.replace('v4.9', 'v4.9.1').replace('LIBERA_축소실험계획_v4.9.1_20261019.html', PLAN.name)
    method = BeautifulSoup(old_method, 'html.parser')
    h = next(x for x in method.find_all('h2') if x.get_text() == '자료와 비교 절차')
    context_prose = '''<div id="common-context-method"><h3>공통 업무와 시점이 확인된 시장상황</h3>
<p>모든 사례에는 초안부터 동일한 가상 업무지시와 시장상황을 제공한다. 업무는 신규 미국 주식 투자자금을 11개 산업에 전액 배분하는 제안이며, 기존 보유분 조정이나 실제 기관의 사적 운용지침 재현이 아니다. 판단 기준일은 2026년 7월 17일, 판단기간은 12개월이다. 기간은 Hornuf 등의 Table A1에서 사용한 조건 중 선택했으며 최적성이나 기관별 실제 투자기간을 뜻하지 않는다. 목적은 자본증식을 위한 배분과 분산·위험의 상충을 설명하는 것이다. 차입·공매도 없는 완전투자를 요구하지만, 공개 자료에서 확인되지 않는 위험회피계수·허용손실률·수익률 목표·산업별 상한은 만들지 않는다.</p>
<p>공통 시장입력에는 기존 산업 ETF의 역사적 수익률과 공분산, 기준 산업비중에 더해 기준일 전 발표된 연준 정책금리, BLS 물가·고용, BEA GDP 통계를 제공한다. 각 사실의 관측기간·발표일·단위·수치·공식 출처와 보존된 원문을 연결한다. 시장·거시·포트폴리오 상황을 함께 제공하는 구조는 PortBench v6 Appendix B와 H.1을 참고한 것이며, 개별 공식 지표 선택은 본 과제로의 적용이다. 연구자의 경기 판정이나 산업별 매수 정답은 입력에 추가하지 않는다.</p>
<p>S&amp;P 500 산업 비중은 공통 비교 기준이다. 신규 자금 과제에는 기존 산업 보유분이 없으므로 기준 대비 비중 차이를 거래회전율로 해석하지 않는다. 보고서 날짜와 시장자료 날짜가 다를 수 있으며, 나중에 발표된 통계를 기관이 이미 알고 있었다고 간주하지 않는다. 개발용 문서에도 동일한 시장 상황을 적용한다. 이는 사후 문서조건부 사례이며, 현재 수집한 ETF 조정가격까지 포함한 완전한 시점별 거래 재현은 아니다.</p>
<p>가상 업무에서는 기간 내 예정 인출과 별도 ESG 제외조건을 두지 않는다. 이는 실제 기관의 특성이라는 진술이 아니라 공통 업무를 명확히 하기 위한 연구 설정이다. 금리·물가·고용·성장 범주는 Quek 등의 산업배분 연구(2025, §§3–4), 지표 정의·단위는 LiveMacroEval(2026, Appendix D Table 2)을 함께 참고했다. GDP 사용은 Quek 연구의 PMI를 그대로 복제한 것이 아니며, 이 7개 사실이 최적 정보조합임을 입증한 것도 아니다.</p>
<p>공통상황은 모든 초안에서 같고 최종 단계까지 원문 그대로 보존된다. 달라지는 것은 기관 자료의 최초 제공 시점과 그에 따라 형성된 초안 이력이다. 따라서 공통상황 추가의 효과 자체를 식별하거나 초기 노출의 순수한 인지 기제만 분리했다고 주장하지 않는다.</p></div>'''
    h.insert_before(BeautifulSoup(context_prose, 'html.parser').div)
    mh = next(x for x in method.find_all('h2') if x.get_text() == '측정과 해석')
    mh.insert_after(BeautifulSoup('''<p>추가한 공통상황 해석 필드에서는 업무·시장 읽기, 배분 함의, 근거와 한계를 구분한다. 평가자는 날짜·기간·단위, 신규자금 상태, 공개 전망과 운용목적의 구별 및 설명과 실제 비중의 연결을 검토한다. 특정 지표의 인용 횟수, 임의 거시신호 점수나 사전 정답 비중으로 평가하지 않는다. 공통 목적과 비교 기준 때문에 비중이 합리적으로 유사해질 가능성도 남긴다.</p>''', 'html.parser').p)
    method.main.append(BeautifulSoup('<p class="meta"><a href="'+PAPER.name+'">전체 텀페이퍼 초안</a> · <a href="../research/v491_evaluation_protocol_20261019.json">수정 평가명세</a> · <a href="../research/v491_macro_source_audit_20261019.json">공식 통계 검증</a></p>', 'html.parser').p)
    macro_reference = '''<li id="ref-livemacro">Zhao, X., Zhang, R., Ye, L., Cao, R., Xie, P., &amp; Chava, S. (2026). <i>Can LLMs take the pulse of the economy? A real-time evaluation of LLM nowcasts on macroeconomic indicators</i> (Version 1) [Preprint]. arXiv. <a href="https://arxiv.org/abs/2608.30110v1">원문</a></li>'''
    method.main.find('ul').append(BeautifulSoup(macro_reference, 'html.parser').li)
    method.main.find('ul').append(BeautifulSoup('''<li>Quek, R. W. H., Vittori, E., Ong, K., Mao, R., Cambria, E., &amp; Mengaldo, G. (2025). <i>Leveraging LLMs for top-down sector allocation in automated trading</i> (Version 5) [Preprint]. arXiv. <a href="https://arxiv.org/html/2503.09647v5">원문</a></li>''', 'html.parser').li)
    write_html(METHOD, str(method))

    # Merge methods into an entire paper so the user need not assemble fragments.
    full = BeautifulSoup((ROOT/'paper/LIBERA_텀페이퍼_초안_v4.8.1_20261019_r3.html').read_text('utf-8'), 'html.parser')
    full.title.string = '공통 생성형 AI의 기관별 공개 투자판단 반영 · LIBERA v4.9.1'
    full.h1.string = '공통 생성형 AI의 기관별 공개 투자판단 반영'
    if full.footer is not None:
        full.footer.string = 'v4.9.1 · 현재 실험 규칙: 공통 업무·시장상황 아래 E/L × 초안 D0·첫 최종안 F0. 이전 버전과 실패 원문은 별도 개발 이력으로 보존한다.'
    full.select_one('.subtitle').string = '동일한 업무·시장상황에서 초안 전후 근거 제공을 비교하는 산업배분 사례연구'
    if full.select_one('.eyebrow'):
        full.select_one('.eyebrow').string = 'LIBERA 2026 · VERSION 4.9.1'
    full.select_one('.status').string = '공통상황·두 단계 설계 통합 초안 · 실제 실행 및 독립 사람 검토 전 · 본실험 0건'
    full.header.select_one('.meta').string = '2026년 10월 19일 · 문헌 검토와 실험 전 설계 · 저자 정보 제출 전 기입'
    full.header.nav.clear()
    full.header.nav.append(BeautifulSoup('<a href="../plan/'+PLAN.name+'">전체 실험계획·쉬운 설명</a> <a href="../research/v491_evaluation_protocol_20261019.json">평가명세</a> <a href="../research/v491_process_20261019.jsonl">과정 기록</a>', 'html.parser'))
    abstract = full.select_one('.abstract')
    abstract.clear()
    abstract.append(BeautifulSoup('''<h2>초록</h2><p>공통 생성형 AI가 기관별 투자판단을 반영하는가는 문구의 유사성이나 원문 등급 복사만으로 평가할 수 없다. 본 연구는 공통 알고리즘과 금융 AI 문헌을 검토하고, 동일한 가상 운용 과제와 시장상황에서 Fidelity와 UBS의 공개 산업전망을 활용하는 미국 11개 산업 배분 사례를 설계한다. 신규 주식 투자자금에 대한 12개월 판단기간과 시점이 확인된 공개 거시자료를 공통으로 제공하고, 기관 자료를 초안 전부터 제공하는 E와 초안 후 처음 제공하는 L을 비교한다. 각 사례는 초안과 첫 최종안 두 단계로 구성하며, 최종 단계에는 동일 기관 자료를 양쪽에 제공한다. 사실·출처 충실성, 공통상황 활용, 근거와 실제 비중의 연결, 원배분의 산술 유효성을 분리하여 평가한다. 현재는 자료·입력·평가를 준비한 단계이며 새 본실험 결과는 없다. 이 설계는 두 문서 사례의 근거 전달과 검토 절차를 분석하며 실제 기관의 운용목적, 투자성과 또는 시장 전체 동질화의 인과효과를 추정하지 않는다.</p><p class="meta">주제어: 생성형 AI, 조직 의사결정, 산업 배분, 공통 시장상황, 근거 반영</p>''', 'html.parser'))
    # Remove obsolete auxiliary-task commitment while preserving theory review.
    lit = str(full.find(id='literature'))
    lit = lit.replace('Salcher 등(2026)의 목적함수와 위험선호 계수는 FF12 수치 보조 과제에 사용한다. 이 보조 과제가 기관 문서의 전략적 판단 전체를 대표하지는 않는다.', 'Salcher 등(2026)의 목적함수 기반 접근은 수치 목표가 명시된 과제의 참고 사례지만, 본 축소 실험에는 FF12 보조 과제나 기관별 위험계수를 추가하지 않는다.')
    replace_section(full, 'literature', lit)
    full.find(id='literature').append(BeautifulSoup('''<h3>2.6. 공통상황과 정보 제공 시점의 통제</h3><p>Laban 등(<a href="#ref-laban">2025</a>)의 다중 대화 연구는 정보 제공 순서와 마지막 정보 재제공을 구분할 방법상 선례다. 이를 참고하여 초안 전후 최초 제공을 비교하되 최종 단계에는 같은 기관 자료를 양쪽에 제공한다. 두 단계는 본 연구의 최소 비교 구조이며 논문이 검증한 최적 단계 수는 아니다. Quek 등(<a href="#ref-quek">2025</a>)은 산업배분의 거시정보 범주와 공식 발표일 통제를, <a href="https://arxiv.org/html/2608.30110v1">LiveMacroEval(2026)</a>은 GDP·물가·고용 변수 정의와 단위 구별의 근거를 제공한다. 이들 연구의 효과 크기나 매매전략을 본 과제의 성과 근거로 이전하지 않는다.</p>''', 'html.parser'))
    replace_section(full, 'framework', '''<section id="framework"><h2>3. 연구질문과 관측의 연결</h2><p>연구질문은 동일한 업무·시장상황에서 공통 AI가 기관별 공개 산업판단을 근거 있는 배분에 어떻게 반영하며, 자료를 초안 전후 언제 처음 제공하는지에 따라 그 연결이 달라지는가이다. 기관 자료의 정확한 해석, 자체 판단의 이유와 실제 비중을 구분하여 관찰한다. 공통 업무와 비교 기준은 통제조건이고 기관 자료와 최초 제공 절차가 비교의 대상이다.</p><p>이는 조직의 판단 근거가 AI 권고로 전달되는 업무 과정이라는 논점을 관측 가능한 범위로 구체화한다. 실제 기관의 사적 목표·보유상태·전체 전략을 측정하는 것은 아니다. 자료의 의미 차이는 모델 출력 이전에 11개 산업 모두에서 검토하며, 평가어휘가 다르다고 필요한 배분 차이가 존재한다고 단정하지 않는다. 공통 목적과 시장상황에 근거한 유사한 배분도 가능한 결과다.</p></section>''')
    # Collect method paragraphs by heading, avoiding duplication of the methods-only notice.
    def method_body(title):
        heading = next(x for x in method.find_all('h2') if x.get_text() == title)
        nodes=[]
        for node in heading.next_siblings:
            if getattr(node, 'name', None) == 'h2': break
            nodes.append(str(node))
        return ''.join(nodes)
    macro_table = str(BeautifulSoup(context_section(read('data/sector_context/v491_20261019/market_context.json')), 'html.parser').select_one('div.table')).replace('class="table"', 'class="table-wrap"')
    replace_section(full, 'design', '<section id="design"><h2>4. 자료와 비교 절차</h2>'+context_prose+macro_table+method_body('자료와 비교 절차')+'</section>')
    replace_section(full, 'evaluation', '<section id="evaluation"><h2>5. 평가와 사전 해석 규칙</h2>'+method_body('측정과 해석')+'</section>')
    # Historical evidence remains in the previous immutable paper, linked here.
    replace_section(full, 'readiness', '''<section id="readiness"><h2>6. 개발 이력과 준비 상태</h2><p>기존 v4.8 개발에서는 입력 누적·시간 제한·Vulkan 장치 오류와 원비중 합계 오류가 관측됐다. 이는 두 단계와 중복 축소를 선택한 개발상의 근거다. 이전 실패를 새 설계의 결과로 재분류하거나 합산하지 않는다. <a href="LIBERA_텀페이퍼_초안_v4.8.1_20261019_r3.html#readiness">당시 시도·실패·한계의 원기록</a>을 보존했다.</p><p>v4.9.1은 공통 업무와 공식 거시자료, 기관별 입력 선택, 초안 검사·최종 이력 조립과 평가명세를 준비한 상태다. 예비자료는 Fidelity Q2와 UBS June, 본자료는 Q3와 July다. 자료 묶음마다 네 사례·사례당 두 단계로 최대 8회 생성하며 최종안 뒤 추가 수정은 하지 않는다. 준비한 JSON 파일은 모델 응답이 아니고 현재 새 설계의 모델 호출과 본실험 결과는 0건이다.</p><p>실제 백엔드와 전체 이력의 토큰·메모리 검증, 새 조건의 네 사례 예비실험, 두 사람의 독립 출처·의미 검토, 모델·입력·평가·실행 순서·자원한도 동결 후 본실험을 진행한다. AI의 세 차례 자체검토는 사람 검토나 실행 성공을 대신하지 않는다. 본문에는 관측하지 않은 결과표나 가설 지지 결론을 넣지 않았다.</p></section>''')
    replace_section(full, 'implications', '<section id="implications"><h2>7. 예상 기여와 해석의 한계</h2>'+method_body('개발 이력, 한계와 후속 과제')+'''<p>추가한 거시자료는 의사결정 과제를 구체화하지만, 공통상황 유무를 별도 비교하지 않으므로 그 추가가 품질을 높였다는 효과는 추정하지 않는다. 신규 주식 부문 과제는 전체 고객 자산의 적합성, 거래비용이나 세후 성과를 평가하지 않는다. 12개월은 판단의 시간 범위이며 사후 수익률 관찰기간이 아니다. 공통 기준비중은 모든 조건에 같은 기준점을 제공하므로 유사한 결과의 대안 설명이 된다. 상이한 보고서 날짜·전망기간과 현재 수집된 조정가격의 시점 한계도 남는다.</p></section>''')
    replace_section(full, 'conclusion', '''<section id="conclusion"><h2>8. 결론</h2><p>공통 생성형 AI의 활용을 평가하려면 근거가 제공되었다는 사실과 그 근거가 실제 권고에 반영되었다는 판단을 구별해야 한다. 본 연구는 동일한 업무·시장상황에서 공개 기관자료의 최초 제공 시점을 달리하고, 근거 해석과 산업 비중의 연결을 확인하는 비교 절차를 제안한다. 이는 경제·경영학적으로 정보에 따른 자본 배분과 AI 업무의 검토 절차를 연결하는 제한된 사례 설계다. 실험 전 단계이므로 초기 제공의 우월성이나 동질화의 발생 여부를 결론내리지 않는다. 후속 실행에서는 실패·무차이·근거 있는 유사성도 포함하여 사전 규칙에 따라 보고한다.</p></section>''')
    refs = full.find(id='references')
    refs.select_one('p.note').string = 'APA 저자–연도 체계의 작업 서지. 기존 이론·금융 문헌은 2026년 10월 18일까지 확인한 범위를 유지하고, 이번 업무·시장상황과 두 단계 설계의 추가 근거는 10월 19일 확인했다. 학술 논문·프리프린트·정책 보고서를 구별한다.'
    for old_id in ('ref-v47-uptake', 'ref-v47-symbolic'):
        old_ref = refs.find(id=old_id)
        if old_ref is not None and old_ref.select_one('.refnote') is not None:
            old_ref.select_one('.refnote').string = '과거 개발 설계의 비평·수정 절차를 검토한 문헌이다. 현재 v4.9.1은 초안과 첫 최종안 두 단계이며 최종안 뒤 추가 수정은 채택하지 않는다.'
    refs.select_one('ul').append(BeautifulSoup('''<li id="ref-laban">Laban, P., Hayashi, H., Zhou, Y., &amp; Neville, J. (2025). <i>LLMs get lost in multi-turn conversation</i> [Preprint]. arXiv. <a href="https://arxiv.org/abs/2505.06120v1">원문</a></li>''', 'html.parser').li)
    refs.select_one('ul').append(BeautifulSoup(macro_reference, 'html.parser').li)
    refs.append(BeautifulSoup('''<p>이번 개정의 업무·거시자료 구성은 <a href="https://arxiv.org/html/2605.27887v6">PortBench v6 (2026-10-09), Appendix B·H.1</a> 및 <a href="https://www.ifo.de/DocDL/cesifo1_wp11862.pdf">Hornuf, Streich, Töllich (2025), §3·Table A1</a>에 근거한다. 새로운 조건의 채택·적용 범위는 <a href="../research/v491_mandate_basis_20261019.json">선택 근거표</a>, 공식 통계는 <a href="../research/v491_macro_source_audit_20261019.json">발표본·출처 검증표</a>에 기록했다. 선행 문헌은 기존 초안의 검토 범위를 이어받았으며 이번 개정에서 모두 새로 검증했다고 주장하지 않는다.</p>''', 'html.parser').p)
    replace_section(full, 'appendix', '<section id="appendix"><h2>부록 · 입력과 재현 자료</h2><p><a href="../plan/'+PLAN.name+'">공통상황 포함 실험계획</a> · <a href="../data/sector_context/v491_20261019/common_context.json">공통 업무·시장 입력</a> · <a href="../data/sector_protocol/v491_design_20261019/prepared/preparation_manifest.json">사례별 초안 준비 기록</a> · <a href="../research/v491_handoff_20261019.json">검증·인계 기록</a></p><p>이 문서는 실험 전 텀페이퍼 전체 초안이다. 실험 결과, 독립 사람 검토, 저자 정보와 제출 규정 최종 점검을 완료한 제출본은 아니다.</p></section>')
    write_html(PAPER, str(full))


def main():
    context, candidate, contract, schema = prepare_design()
    prepare_documents(context)
    print(json.dumps({'protocol':'4.9.1', 'common_context':ref(CONTEXT/'common_context.json'),
        'plan':ref(PLAN), 'paper':ref(PAPER), 'model_calls':0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
