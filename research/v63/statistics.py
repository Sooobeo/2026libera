"""Scenario-level v6.3 inference. These functions never manufacture missing runs.

Inputs are conservative, scenario-averaged metrics, calculated per replicate
before aggregation. Outcomes must include the four funds and both replicates.
This module is independent of the model-facing runtime.
"""
from __future__ import annotations
import numpy as np
from scipy.stats import t

ARMS=('R0','R1','R2','R3','C-context')
CLAIMS=('H1','H2','H3_R1_R2','H3_R1_R3','H3_R2_R3')

def one_sided_positive(values):
    x=np.asarray(values,dtype=float)
    if x.ndim!=1 or len(x)<2 or not np.isfinite(x).all():
        return {'p':1.0,'testable':False,'reason':'incomplete_or_nonfinite_sample'}
    se=float(np.std(x,ddof=1)/np.sqrt(len(x)))
    if np.ptp(x)==0 or se==0 or not np.isfinite(se):
        return {'p':1.0,'testable':False,'reason':'zero_variance'}
    statistic=float(np.mean(x)/se)
    return {'p':float(t.sf(statistic,len(x)-1)), 'testable':True,
            'n':len(x),'mean':float(np.mean(x)),'se':se,'t':statistic}

def holm(pvalues,alpha=.05):
    if set(pvalues)!=set(CLAIMS):
        raise ValueError('The confirmatory family must retain all five claims.')
    if not all(np.isfinite(p) and 0<=p<=1 for p in pvalues.values()):
        raise ValueError('Invalid p-value.')
    ordered=sorted(pvalues,key=lambda k:(pvalues[k],k))
    running=0.; out={}
    for index,key in enumerate(ordered):
        running=max(running,min(1.,(len(ordered)-index)*pvalues[key]))
        out[key]={'p':float(pvalues[key]),'p_holm':float(running),'reject':running<=alpha}
    return {key:out[key] for key in CLAIMS}

def joint_positive(components):
    tests={key:one_sided_positive(values) for key,values in components.items()}
    return {'p':max(x['p'] for x in tests.values()),'components':tests}

def directional_mitigation(candidate,baseline,exact_delta_regret):
    """A-minus-B upper bounds <0 become positive evidence after negation."""
    return joint_positive({
        'baseline_lower_G_positive':baseline['G_full_lower'],
        'decrease_E':np.asarray(baseline['E_full_lower'])-np.asarray(candidate['E_full_upper']),
        'decrease_R':-np.asarray(exact_delta_regret),
        'decrease_A':np.asarray(baseline['A_full_lower'])-np.asarray(candidate['A_full_upper'])})

def confirmatory_family(metrics,exact_delta_regret,*,frozen_scenario_ids,frozen_strata):
    """Require 60 complete scenarios; never replace unattempted runs by h.

    exact_delta_regret['R1|R0'] contains mu_full @ (w_R0-w_R1),
    averaged over funds and replicates, not a difference of fstar estimates.
    The ordered scenario IDs and precision strata must come from the input
    manifest frozen before the first main request, never from observed outputs.
    terminal_statuses has shape (60, 8), ordered by the four funds and repeats.
    """
    if set(metrics)!=set(ARMS):
        raise ValueError('All five arms are required.')
    ids=list(frozen_scenario_ids)
    if len(ids)!=60 or len(set(ids))!=60:
        raise ValueError('Frozen manifest must contain exactly 60 unique scenarios.')
    strata=np.asarray(frozen_strata,dtype=float)
    if strata.shape!=(60,) or not np.isfinite(strata).all() or {
            float(r):int(np.sum(strata==r)) for r in np.unique(strata)}!={.5:20,1.:20,2.:20}:
        raise ValueError('Frozen strata must contain precision .5/1/2 exactly 20 times each.')
    allowed_terminal={'completed','model_output_failure','operational_failure'}
    keys=('G_full_lower','E_full_lower','E_full_upper','A_full_lower','A_full_upper')
    for arm,data in metrics.items():
        these=list(data['scenario_ids'])
        if these!=ids:
            raise ValueError('Scenario IDs/order differ from the frozen input manifest.')
        arm_strata=np.asarray(data.get('scenario_strata',[]),dtype=float)
        if arm_strata.shape!=(60,) or not np.array_equal(arm_strata,strata):
            raise ValueError('Scenario precision strata differ from the frozen input manifest.')
        terminal=np.asarray(data.get('terminal_statuses',[]),dtype=object)
        if terminal.shape!=(60,8) or not all(isinstance(s,str) and s in allowed_terminal for s in terminal.flat):
            raise ValueError('Every fund/replicate must have an eligible terminal outcome; unattempted/protocol violations are incomplete.')
        if any(n!=8 for n in data['attempted_fund_replicates']) or len(data['attempted_fund_replicates'])!=60:
            raise ValueError('Each scenario must have all 4 funds x 2 replicates attempted.')
        for key in keys:
            x=np.asarray(data[key],float)
            if x.shape!=(60,) or not np.isfinite(x).all():
                raise ValueError('Missing or invalid scenario metrics: '+key)
    for key in ('G_available_lower','R_available_lower'):
        x=np.asarray(metrics['C-context'][key],float)
        if x.shape!=(60,) or not np.isfinite(x).all(): raise ValueError('Invalid H1 metric.')
    def delta(a,b):
        if a+'|'+b in exact_delta_regret: x=np.asarray(exact_delta_regret[a+'|'+b],float)
        elif b+'|'+a in exact_delta_regret: x=-np.asarray(exact_delta_regret[b+'|'+a],float)
        else: raise ValueError('Exact paired regret difference missing.')
        if x.shape!=(60,) or not np.isfinite(x).all(): raise ValueError('Invalid exact regret difference.')
        return x
    results={
        'H1':joint_positive({'G_available_lower':metrics['C-context']['G_available_lower'],
                             'R_available_lower':metrics['C-context']['R_available_lower']}),
        'H2':directional_mitigation(metrics['R1'],metrics['R0'],delta('R1','R0'))}
    for a,b in [('R1','R2'),('R1','R3'),('R2','R3')]:
        ab=directional_mitigation(metrics[a],metrics[b],delta(a,b))
        ba=directional_mitigation(metrics[b],metrics[a],delta(b,a))
        results['H3_'+a+'_'+b]={'p':min(1.,2*min(ab['p'],ba['p'])),
            'directions':{a+'_better':ab,b+'_better':ba}}
    adjusted=holm({key:value['p'] for key,value in results.items()})
    for key in results: results[key].update(adjusted[key])
    return {'status':'analyzed','independent_units':60,'scenario_ids':ids,'scenario_strata':strata.tolist(),'claims':results,
            'interpretation':'Nonsignificance is not evidence of equivalence. Recommendations also require failure/fallback checks.'}

def stratified_bootstrap(values,strata,resamples=10000,seed=7001):
    x=np.asarray(values,float); s=np.asarray(strata)
    if x.ndim<1 or len(x)!=len(s) or not np.isfinite(x).all(): raise ValueError('Invalid bootstrap input.')
    if len(x)!=60 or {float(r):int(sum(s==r)) for r in np.unique(s)}!={.5:20,1.:20,2.:20}:
        raise ValueError('Prespecified 3 x 20 scenario strata required.')
    rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence(seed)))
    index=np.concatenate([rng.choice(np.flatnonzero(s==r),size=(resamples,sum(s==r)),replace=True)
                          for r in np.unique(s)],axis=1)
    means=x[index].mean(axis=1)
    return {'lower':np.quantile(means,.025,axis=0).tolist(),
            'upper':np.quantile(means,.975,axis=0).tolist(),'resamples':resamples,
            'unit':'whole scenario','simultaneous':False,'seed':seed}

def pair_metrics(weights,references):
    """Point diagnostics; compute for each replicate, then average the metrics."""
    w=np.asarray(weights,float); v=np.asarray(references,float)
    if w.shape!=(4,12) or v.shape!=w.shape or not np.isfinite(w).all() or not np.isfinite(v).all():
        raise ValueError('Four finite 12-industry vectors required.')
    rows=[]
    for i in range(4):
        for j in range(i+1,4):
            d=.5*np.abs(w[i]-w[j]).sum(); ds=.5*np.abs(v[i]-v[j]).sum()
            g=ds-d; e=.5*np.abs((w[i]-w[j])-(v[i]-v[j])).sum()
            rows.append({'i':i,'j':j,'D':float(d),'D_star':float(ds),'G':float(g),'A':float(abs(g)),'E':float(e)})
    return {'pairs':rows,**{key:float(np.mean([row[key] for row in rows])) for key in ['D','D_star','G','A','E']}}
