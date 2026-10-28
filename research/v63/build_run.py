"""Build immutable per-fund inputs from real source-qualified profiles.

No hidden ledger is ever copied into a model input. Human-review assumption is
explicitly bound to the user's amendment; source/data requirements stay intact.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import numpy as np

from research.v63 import numerics
from research.v63.retrieval import (AtomicUnit,Document,TokenCounter,b_documents,retrieve,canonical,sha)
from research.v63.runtime import planned_schedule,BASE_FIELDS,AC_BASE_FIELDS
from research.v63.campaign_control import atomic_json

PHASES=('technical-smoke','paired-feasibility','development-pilot','B-main','x-replacement','negative-control','A','C')

def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def save_json(path,value):atomic_json(path,numerics.jsonable(value))
def file_ref(path,root):
    path=Path(path).resolve();return {'path':path.relative_to(Path(root).resolve()).as_posix(),'sha256':numerics.sha256(path)}

def profile_errors(profile):
    errors=[]
    if profile.get('scientific_ready') is not True:errors.append('scientific_ready_not_certified')
    for field in ('complete_holdings','nav_reconciled','publication_verified'):
        if profile.get(field) is not True:errors.append(field)
    if profile.get('starting_constraints_verified',profile.get('mandatory_rules_verified')) is not True:
        errors.append('mandatory_rule_translation_not_verified')
    coverage=profile.get('coverage',profile.get('sic_coverage'))
    if isinstance(coverage,bool) or not isinstance(coverage,(float,int)) or not np.isfinite(coverage) or not .9<=coverage<=1:
        errors.append('SIC_coverage_below_90_percent_or_unknown')
    w=np.asarray(profile.get('h',[]),float)
    if w.shape!=(12,) or not np.isfinite(w).all() or w.min() <0 or abs(w.sum()-1)>1e-9:errors.append('invalid_h')
    if not profile.get('source_evidence_ids'):errors.append('missing_source_evidence_ids')
    if not profile.get('objective') or not isinstance(profile.get('mandatory_constraints'),list):errors.append('mandatory_baseline_missing')
    if 'A' not in profile or 'b' not in profile:errors.append('explicit_constraint_translation_missing')
    return errors

def load_profiles(path,period,*,funds=None):
    data=read_json(path);rows=data['profiles'] if isinstance(data,dict) else data
    eligible=[row for row in rows if row.get('period')==period and (funds is None or row['fund_id'] in funds)]
    if len({row['fund_id'] for row in eligible})!=len(eligible):raise ValueError('Duplicate fund-period source profiles.')
    chosen={row['fund_id']:row for row in eligible}
    if funds is not None and set(chosen)!=set(funds):raise ValueError('Missing real source profiles: '+str(sorted(set(funds)-set(chosen))))
    errors={fund:profile_errors(profile) for fund,profile in chosen.items() if profile_errors(profile)}
    if errors:raise ValueError('Source gates remain unsatisfied: '+canonical(errors))
    if not chosen:raise ValueError('No eligible real fund profile for '+period)
    return chosen

def select_phase_schedule(phase,smoke_fund_id,config=None):
    if phase not in PHASES:raise ValueError('Unknown campaign phase.')
    all_rows=planned_schedule()
    if phase=='technical-smoke':
        return [r for r in all_rows if r['block']=='B-development' and r['scenario']=='development-001' and r['fund_id']==smoke_fund_id]
    if phase=='paired-feasibility':return [r for r in all_rows if r['block']=='B-development' and r['scenario']=='development-001']
    if phase=='development-pilot':return [r for r in all_rows if r['block']=='B-development']
    if phase in {'A','C'}:return [r for r in all_rows if r['block']=='actual-documents' and r['module']==phase]
    if phase == 'B-main' and config and config.get('main_direct_design'):
        design=config['main_direct_design']
        levels={float(x) for x in design['precision_levels']}
        per_level=int(design['samples_per_precision'])
        replicates=int(design.get('replicates',1))
        arms=design.get('arms',list(('R0','R1','R2','R3','C-context')))
        if len(set(arms))!=len(arms) or not arms or set(arms)-{'R0','R1','R2','R3','C-context'}:
            raise ValueError('Invalid direct-main material conditions.')
        selected=[];counts={level:0 for level in levels}
        for index in range(60):
            level=(0.5,1.0,2.0)[index%3]
            if level in counts and counts[level] < per_level:
                selected.append(f'main-{index+1:03d}');counts[level]+=1
        if any(value != per_level for value in counts.values()):
            raise ValueError('Requested direct-main precision sample is unavailable.')
        return [{**row,'replicate':1} for row in all_rows
                if row['block']=='B-main' and row['scenario'] in selected and row['replicate']<=replicates and row['arm'] in arms]
    return [r for r in all_rows if r['block']==phase]

def project_rule(rule):
    """Preserve complete audited semantics; keep duplicate provenance outside baseline."""
    return {key:deepcopy(value) for key,value in rule.items() if key not in {'source_excerpt','source_url','source_line'}}

def load_mandate_units(path):
    if path is None:return {}
    rows=read_json(path)['profiles'];result={}
    for row in rows:
        key='|'.join((row['fund_id'],row['period'],row['evidence_id']))
        if key in result:raise ValueError('Duplicate semantic source partition.')
        result[key]=row
    return result

def original_rule_units(profile,rule,partitions):
    """Source excerpts retain exact primary slices; scope can repeat without loss."""
    excerpt=rule.get('source_excerpt')
    if not excerpt:return []
    key='|'.join((profile.get('source_fund_id',profile['fund_id']),profile['period'],rule['evidence_id']))
    row=(partitions or {}).get(key)
    if row is None:pieces=[{'text':excerpt,'shared_context':''}]
    else:
        if row['source_excerpt_sha256']!=sha(excerpt) or row['source_document_id']!=rule['source_document_id']:
            raise ValueError('Semantic source partition does not match original rule.')
        pieces=row['units'];cursor=0
        for part in pieces:
            if part['original_start']!=cursor or part['text']!=excerpt[part['original_start']:part['original_end']]:
                raise ValueError('Semantic partition is not an exact contiguous source slice.')
            cursor=part['original_end']
        if cursor!=len(excerpt) or ''.join(part['text'] for part in pieces)!=excerpt:
            raise ValueError('Semantic partition omitted source text.')
    return [AtomicUnit(canonical({'evidence_id':rule['evidence_id'],'source_document_id':rule['source_document_id'],
                                 'source_excerpt_part':part['text'],'shared_context':part.get('shared_context','')}),
                       (rule['evidence_id'],)) for part in pieces]

def baseline_for(profile,calibration,scenario,module,fund_id=None):
    label=fund_id or profile['fund_id'];h=np.asarray(profile['h']);sigma=np.asarray(calibration['Sigma'])
    check=numerics.check_portfolio(h,h,sigma,profile['A'],profile['b'],solver=True)
    if not check['valid']:raise ValueError('Infeasible real starting holdings: '+label)
    result={'fund_id':label,'objective':deepcopy(profile['objective']),
            'mandatory_constraints':[project_rule(rule) for rule in profile['mandatory_constraints']],'h':h.tolist(),
            'risk_cap':float(h@sigma@h),'Sigma':sigma.tolist(),'industries':list(numerics.INDUSTRIES),'module':module}
    if len(profile['A']):
        result['mandatory_constraints'].append({'type':'source_derived_exact_FF12_linear_constraints',
            'rows':[{'coefficients':list(coefficients),'upper_bound':float(bound)} for coefficients,bound in zip(profile['A'],profile['b'])],
            'source_evidence_ids':profile['source_evidence_ids'],'meaning':'Every row requires coefficients dot raw_weights <= upper_bound.'})
    if module=='B':result.update({k:numerics.jsonable(calibration[k]) for k in ('m0','V0','Omega0')},y=numerics.jsonable(scenario['y']))
    if set(result)!=(BASE_FIELDS if module=='B' else AC_BASE_FIELDS):raise ValueError('Visible baseline schema mismatch.')
    return result

def evidence_registry(scenario,fund_id):
    x=scenario['private_signals'][fund_id];prefix=f"{scenario['scenario_id']}/{fund_id}"
    return {f'{prefix}/X/{code}':{'evidence_id':f'{prefix}/X/{code}','signal_id':prefix+'/x',
              'indices':[i],'values':[float(x[i])],'precision':float(scenario['r'])}
            for i,code in enumerate(numerics.INDUSTRIES)}

def b_input(profile,calibration,scenario,tokenizer,fund_id=None,mandate_units=None):
    fund=fund_id or profile['fund_id'];period='development' if scenario['scenario_id'].startswith('development-') else 'B'
    visible=baseline_for(profile,calibration,scenario,'B',fund)
    facts=[AtomicUnit(canonical({'objective':visible['objective']})),AtomicUnit(canonical({'h':visible['h']}))]
    for rule in visible['mandatory_constraints']:
        facts.append(AtomicUnit(canonical({'mandatory_constraint':rule})))
    documents={}
    for rule in profile['mandatory_constraints']:
        facts.extend(original_rule_units(profile,rule,mandate_units))
        if rule.get('source_document_id') and rule.get('source_url'):
            documents[rule['source_document_id']]=rule['source_url']
    facts.extend(AtomicUnit(canonical({'source_document_id':doc_id,'source_url':url})) for doc_id,url in sorted(documents.items()))
    docs=b_documents(fund,scenario['scenario_id'],scenario['private_signals'][fund],scenario['r'],scenario['signal_date'],facts,period=period)
    registry=evidence_registry(scenario,fund)
    retrieval=retrieve(docs,fund,scenario['signal_date'],period,tokenizer,gold_ids=registry)
    return {'baseline':visible,'retrieval':retrieval,'evidence_registry':registry,
            'constraints':{'A':profile['A'],'b':profile['b']},'source_evidence_ids':profile['source_evidence_ids']}

def actual_document_input(profile,calibration,module,documents_path,tokenizer):
    inventory=read_json(documents_path);rows=inventory['documents'] if isinstance(inventory,dict) else inventory
    cutoff={'A':'2026-03-31','C':'2026-06-30'}[module]
    docs=[];gold=[]
    for row in rows:
        if row.get('fund_id') not in {'COMMON',profile['fund_id']} or row.get('period')!=module:continue
        if row.get('role')=='mandatory_rule':continue  # mandatory rules are present in every arm's baseline
        if module=='C' and row.get('publication_date','')<='2026-03-31':continue
        if row.get('publication_date','')>cutoff:continue
        if row.get('source_eligibility_verified') is not True:raise ValueError('Unverified source in A/C corpus: '+row.get('document_id','?'))
        if row.get('text_is_original_eligible_section') is not True:raise ValueError('A/C corpus must retain eligible original sections.')
        units=tuple(AtomicUnit(u['text'],tuple(u.get('evidence_ids',[]))) for u in row['units'])
        docs.append(Document(row['document_id'],row['fund_id'],row['publication_date'],module,'official_text',row.get('header',''),units,row['source_url']))
        all_ids={e for u in units for e in u.evidence_ids}
        selected=row.get('retrieval_gold_evidence_ids',sorted(all_ids))
        if not isinstance(selected,list) or not set(selected)<=all_ids:raise ValueError('Explicit retrieval gold IDs are not source units.')
        gold.extend(selected)
    result=retrieve(docs,profile['fund_id'],cutoff,module,tokenizer,gold_ids=gold)
    return {'baseline':baseline_for(profile,calibration,None,module),'retrieval':result,'evidence_registry':{},
            'constraints':{'A':profile['A'],'b':profile['b']},'source_evidence_ids':profile['source_evidence_ids']}

def make_numeric_callbacks(case):
    base=case['baseline'];h=np.asarray(base['h']);sigma=np.asarray(base['Sigma']);constraints=case['constraints']
    def check(raw):return numerics.jsonable(numerics.check_portfolio(raw,h,sigma,constraints['A'],constraints['b']))
    def tools(name,args,exposed):
        ids=args.get('exposed_evidence_ids',[])
        if not set(ids).issubset(exposed):return {'error':'Evidence not exposed.'}
        if name=='posterior':
            if base['module']!='B':return {'error':'Synthetic posterior tool unavailable for real qualitative documents.'}
            if any(e not in case['evidence_registry'] for e in ids):return {'error':'Only fully disclosed numeric observations have a posterior update.'}
            observations=[case['evidence_registry'][e] for e in ids]
            p=numerics.posterior(base['m0'],base['V0'],base['y'],base['Omega0'],observations)
            return numerics.jsonable({'mean':p['mean'],'covariance':p['covariance'],'evidence_ids':p['exposed_evidence_ids']})
        if name=='check_portfolio':
            c=check(args.get('raw_weights'))
            return {'valid':c['valid'],'sum':float(1+c['budget_residual']) if c.get('budget_residual') is not None else None,
                    'budget_residual':c.get('budget_residual'),'variance':c.get('risk'),'risk_cap':c.get('risk_cap'),
                    'constraint_violations':c.get('failures',[])}
        return {'error':'Unknown calculator.'}
    return tools,check

def build_phase(root,config,phase,tokenizer):
    """Return model-facing inputs and evaluator-only scenario metadata separately."""
    root=Path(root);funds=[config['smoke_fund_id']] if phase=='technical-smoke' else [f'F{i:02d}' for i in range(1,5)]
    period='development' if phase in PHASES[:3] else ('C' if phase=='C' else 'A_B')
    profiles=load_profiles(root/config['profiles_path'],period,funds=funds)
    mandate_units=load_mandate_units(root/config['mandate_atomic_units_path']) if config.get('mandate_atomic_units_path') else {}
    calibration=numerics.calibrate(root)
    generator_block='development' if phase in PHASES[:3] else ('negative_control' if phase=='negative-control' else 'main')
    scenarios,hidden=numerics.generate_scenarios(calibration,generator_block)
    replacements=[]
    if phase=='x-replacement':
        replacements=numerics.replacement_signals(calibration,scenarios,hidden)
        for s,replacement in zip(scenarios,replacements):s['private_signals'][replacement['fund_id']]=replacement['replacement_x']
    lookup={s['scenario_id']:s for s in scenarios};schedule=select_phase_schedule(phase,config['smoke_fund_id'],config)
    cases={};entries=[];reference_profiles={}
    for row in schedule:
        key=row['scenario']+'__'+row['fund_id'];fund=row['fund_id']
        if key not in cases:
            if phase in {'A','C'}:
                cases[key]=actual_document_input(profiles[fund],calibration,phase,root/config['documents_path'],tokenizer)
            elif phase=='negative-control':
                index=int(row['scenario'].rsplit('-',1)[1])-1;source=f'F{index%4+1:02d}'
                scenario=deepcopy(lookup[row['scenario']]);same=scenario['private_signals']['F01']
                scenario['private_signals']={f'N{i:02d}':same.copy() for i in range(1,5)}
                profile=deepcopy(profiles[source]);profile['source_fund_id']=source;profile['fund_id']=fund
                cases[key]=b_input(profile,calibration,scenario,tokenizer,fund_id=fund,mandate_units=mandate_units)
            else:cases[key]=b_input(profiles[fund],calibration,lookup[row['scenario']],tokenizer,mandate_units=mandate_units)
        case=cases[key]
        entries.append({**row,'case_id':key,'input_sha256':sha(canonical(case))})
    return {'phase':phase,'profiles':profiles,'calibration':calibration,'scenarios_evaluator_only':scenarios,
            'hidden_evaluator_only':hidden,'cases':cases,'entries':entries,
            'replacement_assignments':[{'scenario_id':r['scenario_id'],'fund_id':r['fund_id']} for r in replacements],
            'logical_stages':len(entries)*3,'human_review_mode':'user_assumed_completed','mandate_units_audit':mandate_units}
