"""Offline workflow preparation, message assembly, and strict final-answer scoring.

No network or model call is made. Gold is never passed to build_messages.
Examples (from repository root):
  python research/prepare_workflow_v4.py prepare
  python research/prepare_workflow_v4.py messages --run-id <id> --history prior.json
  python research/prepare_workflow_v4.py evaluate --responses responses.jsonl --output result.json

History is an array of previously returned assistant content strings (0..3).
Response JSONL: {"run_id":..., "status":"completed", "final_text":...}.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import Counter

from prepare_institutional_benchmark import evaluate_weights, evaluate_pair

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/workflow'
CONFIG_PATH = ROOT / 'plan/LIBERA_실험설정_20261017.json'
CASE_PATH = ROOT / 'data/institutional/cases.jsonl'
SYSTEM = '''You assist an investment institution with allocation within its equity sleeve.
Use only the market data and institution mandate supplied in this conversation.
Do not invent a missing mandate or infer a preference from a name, date, or a default investor profile.
The mandate may arrive in a later step. Before it is supplied, you may mark an allocation as pending.
The market quantities are monthly DECIMAL EXCESS returns and their sample covariance, not percentages or annual values.
Once the mandate is available, choose weights to maximize its exact stated objective subject to its constraints.
Every industry remains available at the final review. You may completely replace a provisional decision.
Do not use external search, external data, code execution, or an optimization tool.
The task concerns the stated estimated objective, not predicting future realized returns.
At the final stage, output a JSON object only, with weights in the supplied industry order,
mandate_used_gamma, mandate_evidence_id, and a short explanation.
Weights must be numeric and finite, each in [0,1], and sum to 1 (absolute serialization tolerance 0.000001).
Do not omit zero-weight industries. Do not output percentages such as 25 for 25 percent.
An intermediate answer is not the final submission.'''

STAGES = [
    'Stage 1 of 4: Interpret the supplied market data. Identify the institution objective if provided and explicitly note any missing objective. Do not assume a default mandate.',
    'Stage 2 of 4: Review the return-risk tradeoffs in the supplied market data using the information currently available. Do not invent missing institution information.',
    'Stage 3 of 4: Develop a provisional allocation if the mandate is available. If it is missing, you may leave the allocation pending and state what is needed. The final decision will remain fully open.',
    'Final review: Reconsider all information now available in this conversation and freely revise the entire allocation. Return JSON only: {"weights":[12 numeric values in industry_order],"mandate_used_gamma":numeric_value,"mandate_evidence_id":"MANDATE","explanation":"brief rationale tied to the provided objective"}.',
]

def digest(value):
    raw = value if isinstance(value, bytes) else value.encode('utf-8')
    return hashlib.sha256(raw).hexdigest()

def read_jsonl(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]

def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')

def write_jsonl(path, values):
    with path.open('w', encoding='utf-8', newline='\n') as f:
        for value in values:
            f.write(json.dumps(value, ensure_ascii=False, separators=(',',':'), allow_nan=False)+'\n')

def public_packets(case):
    # Explicit allow-list. Never serialize a complete case or evaluator_only.
    src = case['model_visible']
    market = {'evidence_id':'MARKET', **src['public_market_data']}
    mandate = {'evidence_id':'MANDATE', **src['institution_mandate']}
    return market, mandate

def user_contents(case, arm):
    market, mandate = public_packets(case)
    m = 'Public market data:\n'+json.dumps(market, ensure_ascii=False, allow_nan=False)
    g = '\nInstitution mandate:\n'+json.dumps(mandate, ensure_ascii=False, allow_nan=False)
    if arm == 'FRESH':
        return [m+g+'\n'+STAGES[3]]
    if arm not in ('R1','R4'):
        raise ValueError('Unknown arm')
    contents = []
    for i, task in enumerate(STAGES):
        content = (m+'\n' if i == 0 else '')+task
        if (arm == 'R1' and i == 0) or (arm == 'R4' and i == 3):
            content += g
        contents.append(content)
    return contents

def build_messages(run, assistant_history):
    if not isinstance(assistant_history, list) or not all(isinstance(s,str) for s in assistant_history):
        raise ValueError('History must contain only captured assistant content strings')
    n = len(assistant_history)
    if n >= len(run['stage_user_contents']):
        raise ValueError('Run has no remaining stage')
    msgs = [{'role':'system','content':SYSTEM}]
    for i in range(n+1):
        msgs.append({'role':'user','content':run['stage_user_contents'][i]})
        if i < n:
            msgs.append({'role':'assistant','content':assistant_history[i]})
    return msgs

def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    cfg = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    cases = read_jsonl(CASE_PATH)
    assert len(cases) == cfg['main']['institution_cases']
    # Deterministic scheduling only, unrelated to treatment values or randomness inference.
    ordered_cases = sorted(cases, key=lambda c:(digest('LIBERA-v4-window-order:'+str(c['window_id'])),digest('LIBERA-v4-gamma-order:'+c['case_id'])))
    runs=[]
    for c in ordered_cases:
        arms=['R1','R4']
        if int(digest('LIBERA-v4-arm-order:'+c['case_id'])[:2],16) % 2:
            arms.reverse()
        for arm in arms:
            runs.append({'run_id':digest('LIBERA-v4:'+c['case_id']+':'+arm)[:24],
                         'runner_only':{'case_id':c['case_id'],'window_id':c['window_id'],'arm':arm,'campaign':'main'},
                         'stage_user_contents':user_contents(c,arm)})
    for c in ordered_cases:
        runs.append({'run_id':digest('LIBERA-v4:'+c['case_id']+':FRESH')[:24],
                     'runner_only':{'case_id':c['case_id'],'window_id':c['window_id'],'arm':'FRESH','campaign':'diagnostic'},
                     'stage_user_contents':user_contents(c,'FRESH')})
    assert len({r['run_id'] for r in runs})==5625
    for offset in range(0,3750,6):
        block=runs[offset:offset+6]
        assert len({r['runner_only']['window_id'] for r in block})==1
        assert len({r['runner_only']['case_id'] for r in block})==3
        assert Counter(r['runner_only']['arm'] for r in block)=={'R1':3,'R4':3}
    by_case={c['case_id']:c for c in cases}
    for run in runs:
        c=by_case[run['runner_only']['case_id']]
        arm=run['runner_only']['arm']
        content=run['stage_user_contents']
        assert sum(s.count('"evidence_id": "MANDATE"') for s in content)==1
        assert sum(s.count('"evidence_id": "MARKET"') for s in content)==1
        if arm=='R4':
            assert all('"gamma"' not in s and 'Institution mandate:' not in s for s in content[:3])
        for step in range(len(content)):
            msgs=build_messages(run,['AUDIT_ONLY_HISTORY_NOT_MODEL_OUTPUT']*step)
            serialized=json.dumps(msgs)
            assert c['case_id'] not in serialized and run['run_id'] not in serialized
            assert 'evaluator_only' not in serialized and 'reference_weights' not in serialized
            assert 'test_window' not in serialized
        assert public_packets(c)[1]['gamma'] in cfg['main']['gammas']
    for c in cases:
        early, late=user_contents(c,'R1'),user_contents(c,'R4')
        # Same facts eventually available; placement differs, as documented.
        mandate=json.dumps(public_packets(c)[1],ensure_ascii=False,allow_nan=False)
        assert mandate in early[0] and mandate in late[3]
        assert early[1:3] == late[1:3]
    write_jsonl(OUT/'runs.jsonl',runs)
    write_json(OUT/'prompt_spec.json',{'language':'English for all arms; LIBERA operational choice','system':SYSTEM,'stage_tasks':STAGES,'metadata_policy':'runner_only and run_id must never be passed to model','history_policy':'retain complete actual assistant history; do not summarize, truncate, or import other runs','budget_policy':'same model settings at every call; count thinking and output budget using frozen backend semantics'})
    example=cases[0]
    write_json(OUT/'example_packets.json',{'label':'actual public inputs, not AI responses','public_market':public_packets(example)[0],'mandates':[public_packets(c)[1] for c in cases if c['window_id']==example['window_id']],'note':'These packets are supplied separately according to onset; never show all mandates together to a model run.'})
    hashes={p.name:digest(p.read_bytes()) for p in [OUT/'runs.jsonl',OUT/'prompt_spec.json',OUT/'example_packets.json']}
    manifest={'protocol_version':cfg['protocol_version'],'status':'offline preparation only; no model request sent','model_calls':0,
              'runs':len(runs),'main_runs':3750,'diagnostic_runs':1875,'planned_response_calls':sum(len(r['stage_user_contents']) for r in runs),
              'main_response_calls':15000,'diagnostic_response_calls':1875,
              'case_sha256':digest(CASE_PATH.read_bytes()),'protocol_sha256':digest(CONFIG_PATH.read_bytes()),
              'sha256':hashes,'execution_order':'625 complete market-window blocks of all three gammas x two policies; hashed block and gamma order, paired policy runs adjacent in hashed order; FRESH separate diagnostic campaign',
              'run_ready':False,'remaining_runtime_gate':'verify fixed target model access and immutable model/backend manifest; no silent substitution',
              'validation':{'all_runs_checked':len(runs),'complete_six_run_main_blocks':625,'mandate_appears_once':True,'market_appears_once':True,'R4_no_early_gamma':True,'no_gold_or_future_window_or_run_metadata_in_messages':True,'same_final_facts':True,'full_history_assembly':True}}
    write_json(OUT/'manifest.json',manifest)
    return manifest

def strict_object(text):
    def unique(pairs):
        obj={}
        for k,v in pairs:
            if k in obj:
                raise ValueError('Duplicate JSON key')
            obj[k]=v
        return obj
    obj=json.loads(text,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON')),object_pairs_hook=unique)
    if not isinstance(obj,dict):
        raise ValueError('Final JSON must be an object')
    required={'weights','mandate_used_gamma','mandate_evidence_id','explanation'}
    if set(obj)!=required:
        raise ValueError('Final JSON keys differ from required schema')
    gamma=obj['mandate_used_gamma']
    if isinstance(gamma,bool) or not isinstance(gamma,(float,int)) or not math.isfinite(gamma):
        raise ValueError('Reported gamma must be a finite number')
    if not isinstance(obj['mandate_evidence_id'],str) or not isinstance(obj['explanation'],str):
        raise ValueError('Evidence and explanation must be strings')
    return obj

def describe(values):
    values=[float(v) for v in values]
    return {'n':len(values),'mean':statistics.fmean(values) if values else None,'median':statistics.median(values) if values else None,'min':min(values) if values else None,'max':max(values) if values else None}

def evaluate(responses_path, output_path):
    cfg=json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    runs=read_jsonl(OUT/'runs.jsonl')
    cases={c['case_id']:c for c in read_jsonl(CASE_PATH)}
    index={r['run_id']:r for r in runs}
    records=read_jsonl(responses_path)
    responses={}
    for row in records:
        if row.get('run_id') not in index or row['run_id'] in responses:
            raise ValueError('Unknown or duplicate run_id')
        responses[row['run_id']]=row
    scored=[]
    for run in runs:
        meta=run['runner_only']; c=cases[meta['case_id']]
        row=responses.get(run['run_id'])
        result={'run_id':run['run_id'],**meta,'gamma':c['model_visible']['institution_mandate']['gamma']}
        if row is None:
            result.update({'valid':False,'status':'missing'})
        elif row.get('status')!='completed':
            result.update({'valid':False,'status':'execution_failure','reported_status':row.get('status')})
        else:
            try:
                obj=strict_object(row['final_text'])
                result.update(evaluate_weights(c,obj['weights'],sum_tolerance=cfg['numeric_implementation']['feasibility_sum_tolerance']))
                # Explicit mention is a separate compliance diagnostic, not proof of actual use.
                result.update({'status':'scored','reported_gamma_matches':obj['mandate_used_gamma']==result['gamma'],'evidence_id_matches':obj['mandate_evidence_id']=='MANDATE'})
            except (ValueError,TypeError,KeyError,OverflowError,RecursionError) as ex:
                result.update({'valid':False,'status':'invalid_final','error':str(ex)})
        scored.append(result)
    grouped={}
    for arm in ['R1','R4','FRESH']:
        for gamma in cfg['main']['gammas']:
            rows=[s for s in scored if s['arm']==arm and s['gamma']==gamma]
            valid=[s for s in rows if s['valid']]
            grouped[f'{arm}:gamma={gamma}']={'planned':len(rows),'status_counts':dict(Counter(s['status'] for s in rows)),'valid':len(valid),'utility_regret':describe(s['utility_regret_direct'] for s in valid),'TV_to_reference':describe(s['total_variation_to_reference'] for s in valid)}
    lookup={(s['case_id'],s['arm']):s for s in scored}
    paired=[]
    for cid,c in cases.items():
        a,b=lookup[(cid,'R1')],lookup[(cid,'R4')]
        if a['valid'] and b['valid']:
            paired.append({'case_id':cid,'gamma':a['gamma'],'R4_minus_R1_utility_regret':b['utility_regret_direct']-a['utility_regret_direct'],'R4_minus_R1_TV':b['total_variation_to_reference']-a['total_variation_to_reference']})
    pair_rows=[]
    windows=read_jsonl(ROOT/'data/institutional/windows.jsonl')
    reference_pairs={(w['window_id'],tuple(p['gammas'])):p for w in windows for p in w['pair_references_evaluator_only']}
    by_window={}
    for c in cases.values():
        by_window.setdefault(c['window_id'],{})[c['model_visible']['institution_mandate']['gamma']]=c
    for wid,mapping in by_window.items():
        for gi,gj in [(1,3),(1,5),(3,5)]:
            ci,cj=mapping[gi],mapping[gj]
            for arm in ['R1','R4','FRESH']:
                ri,rj=lookup[(ci['case_id'],arm)],lookup[(cj['case_id'],arm)]
                reference=reference_pairs[(wid,(gi,gj))]
                classification=reference['classification']
                stratum=('shared' if classification.startswith('same_') else 'distinct' if classification.startswith('distinct_') else 'unresolved')
                item={'window_id':wid,'gamma_pair':[gi,gj],'arm':arm,'both_valid':ri['valid'] and rj['valid'],'reference_classification':classification,'stratum':stratum}
                if item['both_valid']:
                    item.update(evaluate_pair(ci,cj,ri['raw_weights'],rj['raw_weights'],sum_tolerance=cfg['numeric_implementation']['feasibility_sum_tolerance']))
                pair_rows.append(item)
    pair_lookup={(r['window_id'],tuple(r['gamma_pair']),r['arm']):r for r in pair_rows}
    pair_differences=[]
    pair_summaries={}
    for pair in [(1,3),(1,5),(3,5)]:
        for wid in by_window:
            early=pair_lookup[(wid,pair,'R1')]
            late=pair_lookup[(wid,pair,'R4')]
            # Four actual final answers must exist, on the same market window.
            if early['both_valid'] and late['both_valid']:
                pair_differences.append({'window_id':wid,'gamma_pair':list(pair),'stratum':early['stratum'],
                                         'R4_minus_R1_pair_response_error':late['pair_response_error']-early['pair_response_error'],
                                         'R4_minus_R1_distance_reduction_G':late['distance_reduction_G_descriptive']-early['distance_reduction_G_descriptive']})
        for stratum in ['all','distinct','shared','unresolved']:
            eligible=[r for r in pair_rows if r['arm']=='R1' and tuple(r['gamma_pair'])==pair and (stratum=='all' or r['stratum']==stratum)]
            differences=[r for r in pair_differences if tuple(r['gamma_pair'])==pair and (stratum=='all' or r['stratum']==stratum)]
            pair_summaries[f'{pair[0]}-{pair[1]}:{stratum}']={
                'planned_windows':len(eligible),'four_output_complete_windows':len(differences),
                'R4_minus_R1_response_error':describe(r['R4_minus_R1_pair_response_error'] for r in differences),
                'R4_minus_R1_G':describe(r['R4_minus_R1_distance_reduction_G'] for r in differences)}
    individual_differences={str(g):{'planned':625,'both_policy_valid':sum(p['gamma']==g for p in paired),'R4_minus_R1_utility_regret':describe(p['R4_minus_R1_utility_regret'] for p in paired if p['gamma']==g),'R4_minus_R1_TV':describe(p['R4_minus_R1_TV'] for p in paired if p['gamma']==g)} for g in cfg['main']['gammas']}
    result={'status':'evaluation of supplied response file; not generated by this script','response_file_sha256':digest(responses_path.read_bytes()),'planned_runs':len(runs),'supplied_records':len(records),'groups':grouped,'individual_paired_complete_n':len(paired),'individual_paired_summaries':individual_differences,'paired_individual_differences':paired,'pair_paired_summaries':pair_summaries,'paired_pair_differences':pair_differences,'pair_level_records':pair_rows,'individual_records':scored,'inference':'descriptive fixed corpus only; individual policy contrasts require both responses, and pair policy contrasts require all four responses on the same window; all missing/invalid denominators remain visible'}
    write_json(output_path,result)
    return {'output':str(output_path),'supplied_records':len(records),'planned_runs':len(runs)}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('prepare')
    m=sub.add_parser('messages');m.add_argument('--run-id',required=True);m.add_argument('--history',type=Path)
    e=sub.add_parser('evaluate');e.add_argument('--responses',required=True,type=Path);e.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    if args.command=='prepare':
        value=prepare()
    elif args.command=='messages':
        run=next(r for r in read_jsonl(OUT/'runs.jsonl') if r['run_id']==args.run_id)
        history=json.loads(args.history.read_text(encoding='utf-8')) if args.history else []
        value=build_messages(run,history)
    else:
        value=evaluate(args.responses,args.output)
    print(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False))

if __name__=='__main__':
    main()
