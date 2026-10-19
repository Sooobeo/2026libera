"""Build a versioned two-stage study DESIGN; no model calls or frozen-file edits."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/sector_protocol/v49_design_20261019'
CONFIG = ROOT / 'plan/LIBERA_실험설정_v4.9_20261019.json'
EVAL = ROOT / 'research/v49_evaluation_protocol_20261019.json'
CODES = ['10','15','20','25','30','35','40','45','50','55','60']
SOURCES = {'pilot':['fidelity_q2_2026','ubs_june_2026'],
           'main':['fidelity_q3_2026','ubs_july_2026']}


def read(p):
    return json.loads((ROOT / p).read_text(encoding='utf-8-sig'))


def save(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')


def ref(p):
    return {'path':str(p),'sha256':hashlib.sha256((ROOT/p).read_bytes()).hexdigest()}


def schema():
    text={'type':'string','minLength':1}
    ids={'type':'array','items':text}
    fields={'sector_code':{'type':'string','enum':CODES},
            'source_label':{'type':['string','null']},
            'source_reading':text,
            'source_evidence_ids':ids,
            'source_stance':{'type':'string','enum':['adopt','qualify','depart','undetermined','not_available']},
            'weight':{'type':'number'},'decision_reason':text,'decision_evidence_ids':ids}
    old=read('data/sector_protocol/v48_pilot_r2_20261018/schemas/R1_stage4.json')
    props={'source_id':{'type':['string','null']},
           'sectors':{'type':'array','minItems':11,'maxItems':11,
                      'items':{'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}},
           'alternatives':text,'risk_discussion':text,'unresolved':ids,
           'submitted_constraints':old['properties']['submitted_constraints']}
    return {'type':'object','properties':props,'required':list(props),'additionalProperties':False}


def main():
    parent=read('plan/LIBERA_실험설정_v4.8_20261018.json')
    config={
      'protocol_version':'4.9', 'as_of_date':'2026-10-19',
      'status':'reviewable_design_not_runtime_validated_not_frozen',
      'research_question_ko':'공통 AI가 기관별 공개 산업 판단을 근거 있는 배분에 보존하는가? 초안 작성 전에 기관 자료를 제공하는 절차와 최종 검토 때 처음 제공하는 절차에서 그 반영이 어떻게 다른가?',
      'claim_scope':'Two-source, single-model documentary case comparison under one market snapshot; not population inference or a test of market-wide harmful homogenization.',
      'prior_protocol':ref('plan/LIBERA_실험설정_v4.8_20261018.json'),
      'historical_run_policy':'Preserve all v4.8 failures. Do not pool old/new trajectories, relabel old attempts or select best outputs.',
      'sources':SOURCES,
      'unit':'one prespecified source document under one workflow condition; sectors and turns are dependent components',
      'arms':['E','L'], 'stages':['D0','F0'], 'sectors':CODES,
      'source_exposure':{'E':{'D0':'assigned packet','F0':'same assigned packet freshly supplied'},
                         'L':{'D0':'no source identity, packet, labels or institutional facts','F0':'assigned packet first supplied'}},
      'final_controls':{'same_final_source_packet_bytes':True,'same_market_input':True,
                        'same_final_instruction_and_schema':True,'same_model_and_sampler':True,
                        'same_calculator_policy':True,'same_final_packet_position':True,
                        'packet_position_meaning':'Same final-message block order; absolute token positions and history lengths differ.',
                        'own_complete_draft_history_retained':True,'same_generated_history':False},
      'estimand':'Early prior exposure plus its generated draft/history versus first exposure at final review, conditional on a common final evidence refresh. Not pure memory, anchoring, exposure-count or position effect.',
      'draft_policy':'Each case generates its own full 11-sector provisional raw allocation and evidence-linked rationale. No shared L draft and no reset or summary of previous responses.',
      'final_policy':'First final response F0 is primary. Retain exact raw draft, actual draft arithmetic feedback, and a fresh complete assigned source packet. Never append post-F0 repair.',
      'calculator_policy':'Same deterministic checker in both arms, using only the submitted raw draft and already visible facts. No automatic normalization, residual fill, optimization target, hidden source constraints or semantic verdict.',
      'failure_policy':'No automatic generation retries or replacement of a failed case. Preserve readable/partial output and infrastructure failure separately. Draft transport/schema failure prevents its dependent final call; draft arithmetic error alone does not prevent final review if the complete vector is readable.',
      'budget':{'cases_per_split':4,'core_calls_per_complete_case':2,'max_calls_per_split':8,
                'post_final_calls':0,'pilot_and_main_max_core_calls':16,
                'runtime_diagnostics_counted_separately':True,
                'old_core_calls_per_split':16,'old_max_calls_per_split':24,
                'basis':'Arithmetic of the local design, not a paper-derived optimum or power calculation. No latency reduction is claimed.'},
      'data':{'taxonomy':'GICS11','baseline':'Existing common S&P500 sector baseline, not source holdings or targets',
              'market_cutoff':parent['main']['period'],
              'public_data_only':True,'not_point_in_time_trading_replay':True,
              'packet_scope':'Existing researcher paraphrases, original rating labels, source IDs and page locators. Original PDFs remain available for review.',
              'compact_candidate':ref('data/sector_protocol/v49_design_20261019/public_compact_candidate.json'),
              'aggregate_candidate_model_visible':False,
              'visibility_rule':'Select exactly the assigned public packet; never send the aggregate containing all pilot/main sources.'},
      'model':{'name':parent['model']['primary_target'],'ollama_tag':parent['model']['ollama_tag'],
               'served_digest_reference':parent['model']['exact_served_revision'],
               'same_model_in_all_cells':True,'thinking':False,'temperature':0,
               'options_reference_not_new_runtime_selection':parent['model']['explicit_request_options'],
               'selected_backend':None,'selected_context_tokens':None,'runtime_validated':False,
               'output_limit_candidate':8192,
               'output_limit_basis':'PortBench v6 section3.1 transfer, not Qwen4B two-stage optimality. FinVector700 is not adopted for this richer task.',
               'context_selection_rule':'Before main freeze, measure exact rendered model tokens including retained draft, actual feedback, refreshed packet, template and allowed output. Choose a supported capacity covering the full bound without truncation; log memory and completion. Do not estimate tokens from bytes.',
               'backend_rule':'Isolate recorded Vulkan failure; compare supported backend operation only as separately logged engineering diagnostics. No GPU stability claim from byte compaction.'},
      'evaluation_path':'research/v49_evaluation_protocol_20261019.json',
      'schema_path':'data/sector_protocol/v49_design_20261019/response_schema.json',
      'prompt_contract_path':'data/sector_protocol/v49_design_20261019/prompt_contract.json',
      'semantic_validators_required_before_execution':['exactly11 unique allowed sector codes, not merely11 rows','finite numeric weights excluding booleans','L D0 source_id and source_label null, source_stance not_available, source_evidence_ids empty','E D0 and every F0 bound to assigned source, citations resolved only against already visible evidence','new sectors records extracted unchanged into existing calculator weights input','actual requests exclude all unassigned packets and evaluator artifacts'],
      'prohibited_heuristics':['rating-to-fixed-weight mapping','institution-specific invented gamma','invented return/confidence/cap','weighted composite quality score','until-success reruns','successful-pair-only conclusion','post-hoc selection of sectors or documents'],
      'pre_main_requirements':['lossless input and visibility audit','same-task backend and full-token feasibility','completed separate four-case pilot accounting','outcome-blinded source/meaning review','versioned prompt/calculator/evaluator implementation checks','freeze exact inputs, model, evaluation, execution order and resource ceilings'],
      'four_way_allocation_observability':'The complete main E/L by source allocation contrast requires four valid F0 portfolios. Otherwise report available prespecified pairs and missing contrasts, and do not claim the allocation question fully answered.',
      'source_contrast_observability':'Complete all11 source comparisons before model outputs. Do not infer substantive conflict from different rating vocabularies. If no meaningful source distinction is supported, between-source preservation is not identified; do not fabricate one.',
      'outcome_blind_readiness':'Do not require E to win, larger source distance, correct reasoning or every response to be arithmetically valid as a prompt tuning target. Distinguish a runnable instrument from observed valid contrasts.',
      'current_state':{'v49_model_calls':0,'v49_pilot_calls':0,'v49_main_calls':0,'independent_human_review_completed':False,'frozen':False,'runner_implemented':False}
    }
    save(CONFIG,config)
    save(OUT/'response_schema.json',schema())
    system=("You are preparing a public-document-conditioned US equity-sector allocation for a research task. "
      "Use only visible supplied evidence. Return the required JSON with exactly one row per listed sector, including zero weights. "
      "Choose long-only weights summing to one; raw numbers will be checked, never silently corrected. "
      "Separate the source's published meaning from your own judgment. Public outlooks are not private mandates or published target weights. "
      "Do not convert ratings into compulsory numerical weights or invent expected returns, risk aversion or constraints. "
      "Explain adoption, qualification or reasoned departure using supporting and competing visible evidence. "
      "Distinguish historical return/risk observations from forecasts and identify unsupported or unresolved claims. "
      "Discuss a meaningful alternative and risk trade-off. Do not repeat the same prose in source_reading and decision_reason. "
      "Shortness has no score; necessary meaning and evidence may not be dropped. A table's shared fields apply to every row, columns name row positions. "
      "No hidden evaluator labels or answers are available.")
    draft=("Prepare a provisional allocation using the evidence currently supplied. "
      "For each sector, source_reading states the source's actual meaning and any missing source rationale; "
      "decision_reason explains the chosen weight relative to the common baseline and credible alternatives. "
      "If no institution packet is supplied, use source_id=null, source_label=null, source_stance=not_available, "
      "and empty source_evidence_ids. Explicitly say institutional evidence is unavailable; do not guess it. "
      "Cite existing visible evidence IDs. Own calculations are unverified model derivations unless actual calculator evidence exists.")
    final=("Reconsider your exact provisional allocation using the complete assigned institution packet supplied in this final message, "
      "the common market evidence in history, and the actual arithmetic feedback on your draft. "
      "Produce the first and only final allocation; it will not be followed by a repair request. "
      "Give each sector's source meaning, source stance, raw final weight, and a decision reason linking evidence, risk, alternatives "
      "and the submitted weight. Explain retention or revision without claiming a change absent from the numbers. "
      "Supported disagreement with a source is allowed; copied ratings alone do not establish preserved judgment. "
      "Do not cite draft calculator facts as verification of the new final vector. New claims derived from final weights remain to be checked.")
    contract={'protocol_version':'4.9','status':'design_text_not_a_served_request','system':system,
              'D0_instruction':draft,'F0_instruction':final,
              'F0_order':['same instruction','actual own-draft calculator feedback','fresh assigned source packet'],
              'history':'Keep the verbatim system/user/draft messages. No deletion, summarization, silent truncation or reset.',
              'public_input':'same common_market and same reversible public_numeric_fact_index representation in every D0',
              'output_schema':'response_schema.json supplied via API format and a single common readable contract; feasibility must be verified against the served backend',
              'source_selection':'E D0 assigned only; L D0 no identity; F0 assigned only in both arms',
              'generator_calls':0}
    save(OUT/'prompt_contract.json',contract)
    evaluation={
      'protocol_version':'4.9','status':'prespecified_candidate_pending_human_review_and_freeze',
      'primary_endpoint':'F0 first final raw submission; D0 is process evidence, not another independent observation',
      'expected_cases_per_split':4,'expected_sector_rows_per_final_split':44,
      'dimensions':{
       'source_fidelity':{'assess':['correct source, label, meaning, scope and stated rationale','unsupported attribution','missing source rationale acknowledged'],
                          'rule':'Original labels remain source-specific. Overweight and Attractive are not equated.'},
       'evidence_decision_link':{'assess':['literal source meaning','stated adoption/qualification/departure','supporting and competing visible evidence','actual final weight and baseline-relative assertion','claimed draft-to-final change versus actual delta'],
                                'categories':['supported_link','unsupported_or_contradictory_link','unresolved','missing_or_not_assessable'],
                                'rule':'Human-evaluated evidence chain. A justified departure can be supported; no compulsory source target or hidden-thought inference.'},
       'arithmetic_execution':{'assess':['attempted','transport_complete','parseable','11 unique sectors','finite numbers excluding booleans','raw sum and residual','negative and above-one weights','source-supported explicit constraints'],
                               'sum_tolerance':1e-6,'tolerance_basis':'Inherited numerical precision convention, not a paper-derived behavioral threshold.',
                               'raw_repair':False},
       'numeric_fidelity':{'assess':['subject','metric','value','unit','period','source_id','version','formula/input lineage'],
                           'rule':'Verify claimed numbers against visible facts and actual candidate calculations; IDs alone do not prove support.'}},
      'blind_review':{'before_generation':'All11 source comparison rows, factual anchors and rubric must be reviewed before model outputs; source differences never chosen from outcomes.',
                     'after_generation':'Mask arm and run-order labels in final-output review. Provide corresponding source evidence, common market facts and draft only when assessing change. Actual content may reveal exposure, so masking is imperfect.',
                     'reviewers':'Use two separately working human readers for source meaning and semantic judgments; retain disagreements before reconciliation. This is a local quality-control choice, not two new samples.',
                     'AI_review_status':'Preparatory AI cross-checks are not completed independent human review.'},
      'descriptive_comparisons':{
       'within_source':'For each fixed source, compare E versus L category counts/row-level evidence and allocation distance; no pooled significance test.',
       'between_sources':'For each arm compare full portfolios only alongside the pre-output source contrast matrix; similarity is not automatically homogenization.',
       'distance_formula':'TV(w_a,w_b)=0.5*sum(abs(w_a[k]-w_b[k]))',
       'distance_domain':'Only valid complete nonnegative sum-one raw vectors. This is distance between outputs, not distance to an institutional gold allocation.',
       'difference_of_distances':'TV(F_E,U_E)-TV(F_L,U_L), descriptive only, requires all four valid F0 vectors. A positive sign is not by itself improvement.',
       'change':'For each valid draft-final pair, delta=F0-D0; verify claimed increases/decreases. Invalid draft permits only explicitly raw arithmetic differences, not valid-portfolio change statistics.',
       'benchmark':'Common market baseline is a descriptive anchor, not strategic ground truth or a non-AI treatment arm.'},
      'denominators':{'planned_cases':4,'planned_final_sector_rows':44,
                      'report':['not_attempted','infrastructure_failure','completed','readable_partial','parseable','complete_vector','valid_raw_allocation','eligible_within_source_pairs','eligible_between_source_pairs'],
                      'missing':'No zero distance, benchmark replacement, normalization or inferred strategy for invalid/missing outputs.',
                      'claims':'Report claim count and output coverage; producing less text cannot mechanically count as stronger preservation.'},
      'inference':'Finite descriptive cases; no p-values, bootstrap confidence intervals, population effect, equivalence claim, or sample size inflation from 11 sectors/two turns.',
      'interpretation':{
       'supported_difference':'Source meanings differ, claims are supported, stated choices agree with actual weights: evidence of preservation within these cases.',
       'same_weights_different_supported_reasons':'Possible shared allocation with distinct justifications; not automatically loss of judgment.',
       'different_weights_unsupported_reasons':'Diversity alone is not fidelity.',
       'no_E_L_difference':'No observed procedural contrast in these cases, not proof of equivalence or absence of anchoring.',
       'no_valid_pairs':'Allocation comparison unobserved. Describe interpretation/feasibility diagnostics; do not present the primary allocation question as answered.',
       'infrastructure_failure':'Execution incident, not evidence that the model ignored institutional preferences.'},
      'not_identified':['true institutional holdings or private objectives','required institution-specific optimal weights','harmful market-wide convergence','profitability or causal investment losses','pure memory/anchoring mechanism','RAG retrieval advantage','causal shared-AI-adoption effect'],
      'no_composite_score':True,'no_outcome_driven_filtering':True,
      'pilot_main_separation':'Q2/June remains development evidence; Q3/July is held out from model runs, not unseen by human data preparation. Same-source/same-market dependence remains.'
    }
    save(EVAL,evaluation)
    inventory=read('research/evaluator_only/v48_source_comparison_20261018.json')
    template={'protocol_version':'4.9','visibility':'evaluator_only_never_model_input',
              'status':'blank_human_review_template','source_comparison':inventory['splits'],
              'semantic_fields':['case_id','sector_code','source_reading_quote','decision_reason_quote','weight','source_fidelity','evidence_decision_link','numeric_fidelity','reviewer','disagreement'],
              'all_sectors_prespecified':True,'independent_human_review_completed':False}
    save(ROOT/'research/v49_human_review_template_20261019.json',template)
    print(json.dumps({'config':CONFIG.name,'schema':'response_schema.json','main_calls':0,'files_written':5}))


if __name__=='__main__':
    main()
