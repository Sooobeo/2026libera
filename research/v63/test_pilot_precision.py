"""Synthetic verification only: no empirical output or model calls."""
import copy
import itertools
import numpy as np
import pytest
from research.v63.pilot_precision import (ARMS,FUNDS,pilot_report,precision_summary,
                                         marginal_power,iut_power_bounds)


def fixture():
    scenarios=[dict(scenario_id=f'development-{i+1:03d}',r=(.5,1.,2.)[i%3]) for i in range(12)]
    bank={};rows=[]
    for i,s in enumerate(scenarios):
        sid=s['scenario_id'];bank[sid]={}
        for j,fid in enumerate(FUNDS):
            h=np.eye(12)[0];v=np.eye(12)[j];mu=v*(.01+i*.0001)
            ref=dict(weights=v.tolist(),primal_objective=float(v@mu),dual_bound=float(v@mu)+1e-10,eta=.001)
            full=dict(mu=mu.tolist(),reference=ref,evidence_ids=['source'])
            bank[sid][fid]=dict(h=h.tolist(),Sigma=np.eye(12).tolist(),A=[],b=[],r=s['r'],full=full,
                               available={a:copy.deepcopy(full) for a in ARMS})
        for fid,arm in itertools.product(FUNDS,ARMS):
            j=FUNDS.index(fid);amount=(ARMS.index(arm)+1)*(i+1)/100
            w=(1-amount)*np.eye(12)[j]+amount*np.eye(12)[0]
            trace=dict(engineering_only=True,fund_id=fid,arm=arm,status='completed',effective_weights=w.tolist(),
                actual_model_calls=3,calls=[dict(elapsed_seconds=.1,raw_response=dict(model_sha256='synthetic-pinned',finish_reason='stop',usage={'prompt_eval_count':100,'eval_count':10})) for _ in range(3)],
                stages=[dict(stage=k,status='completed',exposed_evidence_ids=['source'],raw_output={'weights':w.tolist()} if k==3 else {}) for k in (1,2,3)])
            rows.append(dict(block='B-development',scenario=sid,fund_id=fid,arm=arm,replicate=1,trace=trace))
    return rows,bank,scenarios


def run(rows,bank,scenarios):
    return pilot_report(rows,bank,scenarios,frozen_model_sha256='synthetic-pinned',allow_synthetic=True,
                        runtime_metadata={'temperature':0,'seed':1001})


def test_complete_synthetic_pilot_keeps_N_and_costs():
    out=run(*fixture())
    assert out['status']=='synthetic_verification_only' and out['ready_for_precision_report']
    assert out['independent_scenarios']==12 and out['main_N_fixed']==60
    assert not out['replicates_independent'] and not out['confirmatory_pvalues_computed']
    assert out['model_or_N_recommendation'] is None
    assert out['cost']['actual_model_calls']==720
    assert out['cost']['prompt_tokens']==72000
    assert out['cost']['generated_tokens']==7200
    assert not out['cost']['token_totals_are_lower_bounds']
    assert out['cost']['conditional_main_projection']['generation_requests']==7200
    assert out['cost']['conditional_main_projection']['serial_request_elapsed_seconds']==pytest.approx(720.)
    assert set(out['precision'])=={'H1','H2','H3_R1_R2:R1_better','H3_R1_R2:R2_better','H3_R1_R3:R1_better','H3_R1_R3:R3_better','H3_R2_R3:R2_better','H3_R2_R3:R3_better'}
    assert out['precision']['H2']['component_alpha']==.01
    assert out['precision']['H3_R1_R2:R1_better']['component_alpha']==.005


def test_partial_pilot_never_estimates_power_or_fills_h():
    rows,bank,scenarios=fixture();out=run(rows[:5],bank,scenarios)
    assert out['status']=='pilot_not_ready' and out['precision'] is None
    assert len(out['missing'])==235 and out['cost']['actual_model_calls']==15
    assert not out['ready_for_precision_report']


def test_extra_replicate_does_not_enlarge_N():
    rows,bank,scenarios=fixture();extra=copy.deepcopy(rows[0]);extra['replicate']=2
    with pytest.raises(ValueError,match='one replicate'):run(rows+[extra],bank,scenarios)


def test_exact_paired_regret_variance_aggregates_funds_within_scenario():
    rows,bank,scenarios=fixture();out=run(rows,bank,scenarios)
    # R1/R0 differ by .01*(i+1); three of four funds have nonzero mu gain.
    differences=[-.75*(.01+i*.0001)*(i+1)/100 for i in range(12)]
    component=out['precision']['H2']['components']['exact_R_decrease']
    assert component['paired_scenario_variance']==pytest.approx(np.var(differences,ddof=1))
    assert component['independent_scenarios']==12


def test_failure_uses_terminal_h_but_protocol_violation_is_not_ready():
    rows,bank,scenarios=fixture();r=rows[1];r['trace']['status']='model_output_failure';r['trace']['effective_weights']=bank[r['scenario']][r['fund_id']]['h']
    out=run(rows,bank,scenarios)
    assert out['terminal_counts']['model_output_failure']==1
    assert out['raw_output_validity'][r['arm']]['valid_terminal_raw_outputs']==47
    r['trace']['status']='protocol_violation';out=run(rows,bank,scenarios)
    assert not out['ready_for_precision_report'] and len(out['nonterminal'])==1


def test_sd_uncertainty_power_and_IUT_bounds():
    strata=[(.5,1.,2.)[i%3] for i in range(12)]
    out=precision_summary(np.arange(12)/100,strata)
    assert out['normal_homoskedastic_sd_interval95'][0]<out['paired_scenario_sd']<out['normal_homoskedastic_sd_interval95'][1]
    curves=out['sensitivity'];assert all(a['conditional_power']<=b['conditional_power'] for a,b in zip(curves,curves[1:]))
    assert all(a['conditional_power_at_upper_sd']<=a['conditional_power']+1e-12 for a in curves)
    assert marginal_power(0,1,.01)==pytest.approx(.01)
    assert iut_power_bounds([.8,.8,.8,.8])=={'lower':pytest.approx(.2),'upper':.8}
    assert iut_power_bounds([.2,.8])=={'lower':0.,'upper':.2}
    assert precision_summary(np.zeros(12),strata)['power_status']=='zero_variance_not_testable'
    assert marginal_power(.1,0,.01) is None


def test_real_mode_rejects_synthetic_traces_and_drift():
    rows,bank,scenarios=fixture()
    with pytest.raises(ValueError,match='Inline traces'):pilot_report(rows,bank,scenarios,frozen_model_sha256='synthetic-pinned')
    rows[0]['trace']['calls'][0]['raw_response']['model_sha256']='wrong'
    with pytest.raises(ValueError,match='unpinned'):run(rows,bank,scenarios)


def test_missing_token_receipts_are_not_recorded_as_known_zero_cost():
    rows,bank,scenarios=fixture();rows[0]['trace']['calls'][0]['raw_response']['usage']=None
    out=run(rows,bank,scenarios)
    assert out['cost']['generation_attempts_with_incomplete_token_usage']==1
    assert out['cost']['token_totals_are_lower_bounds']
    assert out['cost']['conditional_main_projection']['token_totals_are_lower_bounds']
