"""Independent offline artifact/invariant audit for the v4.8 design, never model success."""
from pathlib import Path
import argparse
from hashlib import sha256
from datetime import datetime, timezone
import json
import math
import subprocess
from urllib.parse import unquote, urlparse
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
FILES=[
    'plan/LIBERA_실험계획_v4.8_20261018.html',
    'paper/LIBERA_텀페이퍼_초안_v4.8_20261018.html',
    'plan/LIBERA_실험설정_v4.8_20261018.json',
    'data/sector_protocol/v48_design_20261018/prompt_contract.json',
    'data/sector_protocol/v48_design_20261018/public_numeric_registry.json',
    'research/evaluator_only/v48_source_comparison_20261018.json',
    'research/v48_evaluation_protocol_20261018.json',
    'research/v48_review_template_20261018.json',
    'research/v48_reference_basis_20261018.json',
    'research/v48_topic_alignment_basis_20261018.json',
    'research/build_sector_revision_v48.py',
    'research/v48_parameter_reference_addendum_20261018.json',
]


def digest(path): return sha256((ROOT/path).read_bytes()).hexdigest()
def load(path): return json.loads((ROOT/path).read_text(encoding='utf-8'))


def audit(output):
    checks=[]
    def check(name, condition, evidence=None):
        checks.append({'id':name,'pass':bool(condition),'evidence':evidence})
    for p in FILES:
        s=(ROOT/p).read_text(encoding='utf-8')
        check('encoding:'+p,'\ufffd' not in s and '????' not in s)
        if p.endswith('.json'):
            def unique(pairs):
                d={}
                for k,v in pairs:
                    if k in d: raise ValueError('Duplicate key '+k)
                    d[k]=v
                return d
            json.loads(s,object_pairs_hook=unique,parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
            check('strict_json:'+p,True)
    config=load(FILES[2]);prompt=load(FILES[3]);registry=load(FILES[4]);inventory=load(FILES[5]);evaluation=load(FILES[6]);template=load(FILES[7])
    codes=config['main']['taxonomy']['sector_codes'];market=load('data/sector_market/market_input.json')
    check('public_sector_roster',codes==['10','15','20','25','30','35','40','45','50','55','60'])
    check('new_execution_zero',config['current_execution']=={'v48_model_calls':0,'v48_pilot_completed_cases':0,'main_completed_cases':0,'main_frozen':False,'runtime_integration_complete':False,'human_review_complete':False})
    check('top_level_contract_agreement',prompt['top_level_fields']==evaluation['response_contract']['keep_existing_seven_top_level_fields'])
    check('stage3_no_pending','pending' not in config['workflow']['stages'][2] and prompt['stages'][2]['weights']=='all 11')
    check('stage4_all11',prompt['stages'][3]['weights']=='all 11')
    check('R1_exposure',[s['stage'] for s in prompt['stages'] if s['R1_source_visible']]==[1,2,3,4])
    check('R4_exposure',[s['stage'] for s in prompt['stages'] if s['R4_source_visible']]==[4])
    check('optional_early_proposal',all(s['weights']=='empty or all 11' for s in prompt['stages'][:2]) and 'not_yet_proposed' in prompt['empty_weights_stage1_2'])
    check('core_failure_no_retry','without an automatic retry' in prompt['core_failure_policy'] and 'not_started' in prompt['core_failure_policy'])
    check('C0_primary',config['primary_output']['candidate']=='C0' and config['primary_output']['repair_replacement'] is False)
    check('repair_contract_config_equal',config['auxiliary_repair']==prompt['auxiliary_repair'])
    check('repair_budget',prompt['auxiliary_repair']['maximum_additional_calls']==evaluation['endpoint_policy']['post_C0_arithmetic_repair']['maximum_additional_generation_calls']==2)
    check('repair_explicit_numeric_boundary','abs(sum(w)-1)>1e-6 OR any(w<0 or w>1)' in prompt['auxiliary_repair']['eligibility'])
    check('call_arithmetic',config['budget']['max_total_calls_each_split']==4*(4+2)==24 and config['budget']['core_calls_each_split']==16)
    check('failures_outcomes_not_pass_gate',config['readiness_gate']['model_failure_is_outcome'] and 'every model answer has budget sum 1' in config['readiness_gate']['does_not_require'])
    check('no_composite_or_gold',config['primary_output']['weighted_composite_score'] is False and config['evaluation']['no_unique_weight_gold'] is True)
    check('source_hash_registry',digest(registry['source']['path'])==registry['source']['sha256'])
    ids=[]
    for row in registry['rows']:
        value=market
        for part in row['source_json_pointer'].strip('/').split('/'):
            value=value[int(part)] if isinstance(value,list) else value[part]
        check('registry_exact_value:'+row['fact_id'],type(value)==type(row['value']) and value==row['value'])
        check('registry_trace_tuple:'+row['fact_id'],bool(row['metric'] and row['unit'] and row['period']))
        ids.append(row['fact_id'])
    check('registry_unique58',len(ids)==len(set(ids))==58)
    check('registry_complete11each',all({r['sector_code'] for r in registry['rows'] if r['fact_id'].startswith('M:'+k+':')}==set(codes) for k in ['baseline_weights','daily_volatility','annualized_volatility_diagnostic','lookback_compound_return','daily_mean_return']))
    check('registry_no_assigned_source',not any(k in json.dumps(registry['rows']).lower() for k in ['fidelity','ubs','rating','evaluator']))
    check('registry_no_future_calc_facts',all(x.startswith('M:') for x in ids))
    for i,code in enumerate(codes):
        check('market_vol_covariance:'+code,math.isclose(market['daily_volatility'][i]**2,market['covariance'][i][i],rel_tol=1e-12))
        check('market_annualization:'+code,math.isclose(market['daily_volatility'][i]*math.sqrt(252),market['annualized_volatility_diagnostic'][i],rel_tol=1e-12))
    check('baseline_unit_sum',math.isclose(sum(market['baseline_weights'].values()),1,abs_tol=1e-12))
    b=market['baseline_weights_array'];cov=market['covariance']
    variance=sum(b[i]*cov[i][j]*b[j] for i in range(11) for j in range(11))
    check('baseline_risk_independent_recompute',math.isclose(math.sqrt(252*variance),market['baseline_annualized_volatility_diagnostic'],rel_tol=1e-12))
    recordids=[]
    for split,group in inventory['splits'].items():
        check('inventory_roster:'+split,[r['sector_code'] for r in group['rows']]==codes)
        for item in group['inputs']: check('inventory_source_hash:'+item['path'],digest(item['path'])==item['sha256'])
        source_packets={load(x['path'])['source_id']:load(x['path']) for x in group['inputs']}
        for row in group['rows']:
            recordids.append(row['record_id'])
            check('inventory_unjudged:'+row['record_id'],row['comparison'] is None and row['reviewer'] is None)
            check('inventory_states:'+row['record_id'],row['comparison_allowed']==template['allowed_states']['inventory_relationship'])
            for source in row['sources']:
                passages=source['passages'];p=source_packets[source['source_id']]
                check('inventory_exact_source:'+row['record_id']+':'+source['source_id'],len(passages)==1 and passages[0] in p['evidence_passages'])
    check('inventory_unique22',len(recordids)==len(set(recordids))==22)
    check('inventory_offline','EVALUATOR_ONLY' in inventory['visibility'] and 'never provided' in prompt['source_visibility'])
    check('human_blank',template['independent_human_review_completed'] is False and template['review_record']['reviewer']['reviewer_id'] is None)
    for key in ['source_stance_literal_states','claim_support_states','action_consistency_states']:
        target={'source_stance_literal_states':'literal_stance','claim_support_states':'assessment_status','action_consistency_states':'action_consistency'}[key]
        check('rubric_template:'+key,evaluation['evaluation_dimensions']['evidence_to_action'][key]==template['allowed_states'][target])
    for p in FILES[:2]:
        soup=BeautifulSoup((ROOT/p).read_text(encoding='utf-8'),'html.parser');txt=soup.get_text(' ',strip=True)
        docids=[x['id'] for x in soup.select('[id]')]
        check('html_unique_ids:'+p,len(docids)==len(set(docids)))
        check('html_state:'+p,all(x in txt for x in ['본실험 0건','v4.8 모델 호출은 0회','모든 C0 배분이 무효라면','비중 차이·수렴은 관측 불가']))
        check('html_no_stale_gate:'+p,all(x not in txt for x in ['① 미해결','① 해결 전','앞 단계 통과 후 전체','저자 서지 입력 대기']))
        check('html_budget:'+p,all(x in txt for x in ['최대 24회','C0 포함','최대 두 번','완료 사례']))
        check('html_core_topic:'+p,all(x in txt for x in ['조직','판단','배분','근거','소급하여 통과로 바꾸지']))
        for a in soup.select('a[href]'):
            href=a['href'];url=urlparse(href)
            if url.scheme or href.startswith('//'): continue
            target=(ROOT/p).parent/unquote(url.path) if url.path else ROOT/p
            check('local_link:'+p+':'+href,target.exists())
            if url.fragment and target.exists() and target.suffix=='.html':
                target_soup=BeautifulSoup(target.read_text(encoding='utf-8'),'html.parser')
                check('anchor:'+p+':'+href,target_soup.find(id=url.fragment) is not None)
    historical=load('research/v47_handoff_20261018.json')
    expected={
        'plan/LIBERA_실험계획_v4.7_20261018.html':'39f5d944944983435c5e27c204ae065d7066b1c5559aabfbb0129558571b7804',
        'paper/LIBERA_텀페이퍼_초안_v4.7_20261018.html':'160e77c616d4ad4e29613240e36e977b7cdd9882774da0bd7f5cd38f9875eb82',
        'plan/LIBERA_실험설정_v4.7_20261018.json':'f278aa9ab4d7a5b6548b7d9d5ac0e80d276dffc0d0333bd83020ed65708e5fd0',
        'research/run_sector_workflow.py':'5625450a4dcbe1aa717c9809bf4955c1ef6b10aab4f0c83ef05dc2eb2c123cfd'}
    for p,h in expected.items(): check('historical_immutable:'+p,digest(p)==h)
    report={'round':1,'scope':'Offline design artifacts, arithmetic, provenance and consistency. Not an online runtime test, model performance pass or human semantic review.',
            'created_at_utc':datetime.now(timezone.utc).isoformat(),
            'reviewer':'root deterministic audit with separately computed numerical identities',
            'inputs':[{'path':p,'sha256':digest(p)} for p in FILES],
            'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL',
            'check_count':len(checks),'pass_count':sum(x['pass'] for x in checks),
            'model_calls':0,'main_ready':False,'checks':checks}
    out=ROOT/output
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'pass_count':report['pass_count'],'check_count':len(checks),'failures':[x for x in checks if not x['pass']]},ensure_ascii=False))
    if report['status']!='PASS': raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='research/v48_design_round1_final_20261018.json')
    audit(parser.parse_args().output)
