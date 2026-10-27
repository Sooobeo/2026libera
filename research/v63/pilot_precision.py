"""Descriptive development precision/cost report; never select a model or main N.

Run after all 12 x 4 x 5 x 1 development trajectories have eligible terminal
outcomes (720 planned stages, possibly fewer reached after early failure).
Partial pilots remain not ready. No calls or campaign files are changed.
"""
from __future__ import annotations
import argparse
import itertools
import json
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.stats import chi2, nct, t

from research.v63.evaluate import (ARMS, FUNDS, _hash_object, _replicate_metrics,
                                   index_records, load_trace, terminal_policy)
from research.v63.numerics import ROOT, jsonable, sha256, write_json

EFFECT_GRID=(0.,.1,.2,.35,.5,.8,1.)
TARGET_N=60


def _distribution(values):
    x=np.asarray(values,float)
    if not x.size:return {'n':0,'mean':None,'median':None,'p95':None,'max':None}
    if not np.isfinite(x).all():raise ValueError('Nonfinite diagnostic value')
    return dict(n=len(x),mean=float(x.mean()),median=float(np.median(x)),
                p95=float(np.quantile(x,.95)),max=float(x.max()))


def marginal_power(effect,sd,alpha,*,n=TARGET_N):
    """Conditional normal-population noncentral-t power; not empirical power."""
    if not np.isfinite([effect,sd,alpha]).all() or sd<=0:return None
    if n!=TARGET_N or not 0<alpha<1 or effect<0:raise ValueError('Invalid fixed-N sensitivity inputs')
    critical=t.ppf(1-alpha,n-1)
    return float(nct.sf(critical,n-1,effect*np.sqrt(n)/sd))


def iut_power_bounds(powers):
    """Frechet/union bounds, requiring no independence of IUT components."""
    if not powers or any(p is None for p in powers):return {'lower':None,'upper':None}
    if any(not 0<=p<=1 for p in powers):raise ValueError('Invalid marginal probability')
    return {'lower':max(0.,sum(powers)-(len(powers)-1)), 'upper':min(powers)}


def precision_summary(values,strata,*,effect_grid=EFFECT_GRID,component_alpha=.01):
    x=np.asarray(values,float);s=np.asarray(strata,float)
    if x.shape!=(12,) or not np.isfinite(x).all() or Counter(s)!={.5:4,1.:4,2.:4}:
        raise ValueError('Precision estimates require the frozen 12 scenarios, four per stratum')
    variance=float(np.var(x,ddof=1));sd=float(np.sqrt(variance));df=11
    sdlo=sd*np.sqrt(df/chi2.ppf(.975,df));sdhi=sd*np.sqrt(df/chi2.ppf(.025,df))
    per_stratum={str(r):dict(n=4,variance=float(np.var(x[s==r],ddof=1))) for r in (.5,1.,2.)}
    stratified_se60=float(np.sqrt(sum(v['variance']/20/9 for v in per_stratum.values())))
    curves=[]
    for d in effect_grid:
        effect=d*sd
        curves.append(dict(standardized_effect=float(d),hypothetical_effect_in_metric_units=float(effect),
            conditional_power=marginal_power(effect,sd,component_alpha),
            conditional_power_at_upper_sd=marginal_power(effect,float(sdhi),component_alpha)))
    return dict(independent_scenarios=12,paired_scenario_variance=variance,paired_scenario_sd=sd,
        cross_scenario_effect_mean_deliberately_not_summarized=True,per_precision_stratum=per_stratum,
        normal_homoskedastic_sd_interval95=[float(sdlo),float(sdhi)],
        sd_interval_is_model_based_not_distribution_free=True,
        projected_stratified_standard_error_at_N60=stratified_se60,
        projected_pooled_CI95_full_width_at_N60=float(2*t.ppf(.975,59)*sd/np.sqrt(60)),
        projected_pooled_CI95_full_width_at_upper_sd=float(2*t.ppf(.975,59)*sdhi/np.sqrt(60)),
        projected_multiplicity_component_two_sided_width=float(2*t.ppf(1-component_alpha/2,59)*sd/np.sqrt(60)),
        component_width_note='Component-specific sensitivity width at the stated alpha; not a simultaneous confidence region across all IUT components or all five claims.',
        power_status='zero_variance_not_testable' if sd==0 else 'conditional_sensitivity_only',
        component_alpha=component_alpha,sensitivity=curves,
        caution='Only 12 pilot scenarios: SD intervals assume independent normal homoskedastic scenario differences. Balanced-stratum SE is descriptive (four per pilot stratum); projected widths/power are conditional approximations, not guarantees.')


def _cost_report(policies,expected):
    usage=Counter();stage_status=Counter();elapsed=[];calls=[];inputs=0;outputs=0
    for p in policies.values():
        usage.update(p['usage']);stage_status.update(p.get('logical_stage_status_counts',{}));elapsed.append(p['elapsed_seconds']);calls.append(p['actual_model_calls'])
        u=p['usage'];inputs+=u.get('prompt_eval_count',u.get('input_tokens',u.get('prompt_tokens',0))) or 0
        outputs+=u.get('eval_count',u.get('output_tokens',u.get('completion_tokens',0))) or 0
    n=len(policies);factor=2400/n if n else None
    incomplete_usage=sum(p.get('generation_attempts_with_incomplete_token_usage',0) for p in policies.values())
    projection=None if not n else dict(main_trajectories=2400,main_independent_scenarios=60,replicates_per_fund=2,
        planned_main_logical_stages=7200,mean_cost_multiplier=factor,
        generation_requests=sum(calls)*factor,prompt_tokens=inputs*factor,generated_tokens=outputs*factor,
        serial_request_elapsed_seconds=sum(elapsed)*factor,token_totals_are_lower_bounds=incomplete_usage>0,
        assumption='Same arm mix, trajectory cost, failure/repair rate and input size as observed development. Sum of request latency is not measured wall time; concurrency and main-profile/document changes can invalidate this extrapolation.')
    return dict(observed_eligible_trajectories=n,planned_development_trajectories=expected,
        planned_development_stages=720,actual_model_calls=sum(calls),usage_by_original_key=dict(usage),
        logical_stage_status_counts=dict(stage_status),completed_logical_stages=stage_status.get('completed',0),
        reached_or_prepared_logical_stages=sum(n for status,n in stage_status.items() if status not in {'parent_failure','not_attempted'}),
        prompt_tokens=inputs,generated_tokens=outputs,elapsed_request_seconds=sum(elapsed),
        generation_attempts_with_incomplete_token_usage=incomplete_usage,
        token_totals_are_lower_bounds=incomplete_usage>0,
        trajectory_latency=_distribution(elapsed),trajectory_calls=_distribution(calls),
        conditional_main_projection=projection,money_cost=None,
        money_cost_reason='No price or compute/electricity tariff supplied; no monetary cost is invented.')


def pilot_report(records,reference_bank,frozen_scenarios,*,frozen_model_sha256,
                 allow_synthetic=False,runtime_metadata=None,effect_grid=EFFECT_GRID):
    scenarios=list(frozen_scenarios);ids=[s['scenario_id'] for s in scenarios];strata=[s['r'] for s in scenarios]
    if len(ids)!=12 or len(set(ids))!=12 or Counter(strata)!={.5:4,1.:4,2.:4}:
        raise ValueError('Prespecified development sample is exactly 12 unique scenarios, four per precision stratum')
    if any(not s.startswith('development-') for s in ids):raise ValueError('Development-only inputs required')
    if any(not np.isfinite(v) or v<0 for v in effect_grid):raise ValueError('Effect grid must be nonnegative and fixed independently of effect direction')
    rows=index_records(records,'B-development');expected=set(itertools.product(ids,FUNDS,ARMS,(1,)))
    if set(rows)-expected:raise ValueError('Unexpected pilot trajectory: one replicate per fund/arm/scenario; repeats cannot enlarge N')
    missing=sorted(expected-set(rows));nonterminal=[];policies={}
    for key,row in rows.items():
        sid,fid,arm,rep=key
        if sid not in reference_bank or fid not in reference_bank[sid]:
            nonterminal.append(dict(identity=key,status='missing_reference'));continue
        p=terminal_policy(row,reference_bank[sid][fid],frozen_model_sha256=frozen_model_sha256,allow_synthetic=allow_synthetic)
        if not p['eligible']:nonterminal.append(dict(identity=key,status=p['status']))
        else:
            trace,_=load_trace(row,allow_synthetic=allow_synthetic)
            incomplete_usage=0
            for call in trace.get('calls',[]):
                usage=(call.get('raw_response') or {}).get('usage') or {}
                has_input=any(usage.get(k) is not None for k in ('prompt_eval_count','input_tokens','prompt_tokens'))
                has_output=any(usage.get(k) is not None for k in ('eval_count','output_tokens','completion_tokens'))
                if call.get('generation_requests',1)>0 and not (has_input and has_output):incomplete_usage+=call.get('generation_requests',1)
            incomplete_usage+=sum(e.get('generation_requests',0) for e in trace.get('preflight_events',[]))
            p['generation_attempts_with_incomplete_token_usage']=incomplete_usage
            p['logical_stage_status_counts']=dict(Counter(s.get('status','unknown') for s in trace.get('stages',[])))
            policies[key]=p
    base=dict(status='pilot_not_ready',ready_for_precision_report=False,synthetic_verification=allow_synthetic,
        expected_trajectories=240,observed_records=len(rows),missing=missing,nonterminal=nonterminal,
        planned_independent_development_scenarios=12,main_N_fixed=60,main_replicates_fixed=2,
        scenario_order=ids,precision_strata=strata,fund_pairs_independent=False,replicates_independent=False,
        aggregation='Within each scenario and replicate, calculate four-fund and six-pair metrics first. The pilot has one replicate. The main experiment averages two replicate metrics within each of its 60 scenarios; no extra independent N.',
        runtime_metadata=runtime_metadata or {},
        repeated_generation_note='Temperature zero and a fixed seed can yield identical repeated outputs. Repeats are not independent scenarios and no 1/sqrt(2) variance benefit is assumed in the N60 projection.',
        cost=_cost_report(policies,240),frozen_model_sha256=frozen_model_sha256,
        policy='Descriptive resource/precision review only. Main N remains 60. Pilot effect signs and achieved significance must not select models, sample size or target effects.',
        cross_scenario_effect_mean_summary_reported=False,confirmatory_pvalues_computed=False,
        readiness_condition='All 240 trajectories have eligible terminal outcomes; early declared failures can leave planned stages unattempted. This does not assert that all 720 stage requests succeeded or occurred.',
        provenance={n:sha256(ROOT/'research/v63'/n) for n in ['pilot_precision.py','evaluate.py','numerics.py','statistics.py']})
    if missing or nonterminal:
        base['cost']['conditional_main_projection']=None
        base.update(reason='All 240 prespecified development trajectories must have actual eligible terminal attempts and references; missing/protocol-invalid slots are never filled with h.',precision=None)
        return jsonable(base)
    metrics={};validity={};reference_diagnostics={}
    for arm in ARMS:
        metrics[arm]=[];rates=[]
        for sid in ids:
            chosen={fid:policies[(sid,fid,arm,1)] for fid in FUNDS}
            metrics[arm].append(_replicate_metrics(chosen,reference_bank[sid],arm)['metrics'])
            rates.append(float(np.mean([p['raw_valid'] for p in chosen.values()])))
        rate=float(np.mean(rates));se=float(np.std(rates,ddof=1)/np.sqrt(12));half=float(t.ppf(.975,11)*se)
        validity[arm]=dict(valid_terminal_raw_outputs=sum(policies[(sid,fid,arm,1)]['raw_valid'] for sid in ids for fid in FUNDS),
            attempted_trajectories=48,rate=rate,scenario_rates=rates,
            scenario_cluster_t_interval95=[max(0.,rate-half),min(1.,rate+half)] if se>0 else None,
            interval_caution='Approximate t interval across 12 scenario means; 48 fund trajectories are not independent Bernoulli samples. Zero observed cluster variance is not a precision guarantee; its interval is withheld.')
    def values(arm,key):return np.array([v[key] for v in metrics[arm]])
    def gain(a,b):return np.array([np.mean([np.asarray(reference_bank[sid][fid]['full']['mu'])@(policies[(sid,fid,a,1)]['weights']-policies[(sid,fid,b,1)]['weights']) for fid in FUNDS]) for sid in ids])
    def mitigation(a,b):return {'baseline_G_lower':values(b,'G_full_lower'),'E_decrease_lower':values(b,'E_full_lower')-values(a,'E_full_upper'),
                               'exact_R_decrease':gain(a,b),'A_decrease_lower':values(b,'A_full_lower')-values(a,'A_full_upper')}
    components={'H1':{'G_available_lower':values('C-context','G_available_lower'),'R_available_lower':values('C-context','R_available_lower')},'H2':mitigation('R1','R0')}
    for a,b in [('R1','R2'),('R1','R3'),('R2','R3')]:
        components[f'H3_{a}_{b}:{a}_better']=mitigation(a,b);components[f'H3_{a}_{b}:{b}_better']=mitigation(b,a)
    precision={}
    for claim,comp in components.items():
        alpha=.005 if claim.startswith('H3_') else .01
        out={name:precision_summary(v,strata,effect_grid=effect_grid,component_alpha=alpha) for name,v in comp.items()}
        joint=[]
        for ix,d in enumerate(effect_grid):
            power=[v['sensitivity'][ix]['conditional_power'] for v in out.values()]
            lowpower=[v['sensitivity'][ix]['conditional_power_at_upper_sd'] for v in out.values()]
            joint.append(dict(standardized_effect=float(d),conditional_iut_power=iut_power_bounds(power),
                              conditional_iut_power_at_upper_sd=iut_power_bounds(lowpower)))
        precision[claim]=dict(components=out,joint_sensitivity=joint,component_alpha=alpha,
            multiplicity='Conservative sufficient Holm threshold .05/5; timing directions additionally divide by two. IUT requires every component. Marginal powers combine by Frechet bounds, never by assumed independence.',
            effect_interpretation='Hypothetical common standardized beneficial effect in every component of this one direction; not an estimate of observed effects. Opposite timing directions are separate hypothetical alternatives.')
    paired={}
    for a,b in itertools.combinations(ARMS,2):
        paired[a+'|'+b]={key:dict(variance=float(np.var(values(a,key)-values(b,key),ddof=1)),n=12) for key in ['D_full','G_full','E_full','A_full','R_full']}
    for view in ('full',*ARMS):
        refs=[reference_bank[sid][fid]['full' if view=='full' else 'available'] for sid in ids for fid in FUNDS]
        refs=[(r if view=='full' else r[view])['reference'] for r in refs]
        reference_diagnostics[view]=dict(eta_TV=_distribution([r['eta'] for r in refs]),
            regret_interval_width=_distribution([r['dual_bound']-r['primal_objective']+2e-9 for r in refs]),
            repeated_reference_views_are_not_independent=True)
    base.update(status='synthetic_verification_only' if allow_synthetic else 'development_precision_descriptive_ready',
        ready_for_precision_report=True,precision=precision,paired_difference_variances=paired,
        raw_output_validity=validity,terminal_counts=dict(Counter(p['status'] for p in policies.values())),
        reference_bounds=reference_diagnostics,scenario_metric_rows=metrics,
        scenario_metric_rows_role='Evaluator diagnostics remain fully disclosed, so a reader can derive effect means; this report deliberately supplies no effect-direction summary or selection recommendation.',
        sensitivity_grid_fixed_before_pilot_completion=list(effect_grid),
        independent_scenarios=12,input_fingerprint=_hash_object([ids,strata,reference_bank]),
        model_or_N_recommendation=None)
    return jsonable(base)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--records',type=Path,required=True);p.add_argument('--reference-bank',type=Path,required=True);p.add_argument('--scenarios',type=Path,required=True);p.add_argument('--model-sha256',required=True);p.add_argument('--runtime-metadata',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--allow-synthetic',action='store_true');a=p.parse_args()
    read=lambda f:json.loads(f.read_text(encoding='utf-8-sig'))
    result=pilot_report(read(a.records),read(a.reference_bank),read(a.scenarios),frozen_model_sha256=a.model_sha256,allow_synthetic=a.allow_synthetic,runtime_metadata=read(a.runtime_metadata) if a.runtime_metadata else None)
    write_json(a.output,result);print(json.dumps({k:result[k] for k in ['status','ready_for_precision_report','observed_records','main_N_fixed']}))


if __name__=='__main__':main()
