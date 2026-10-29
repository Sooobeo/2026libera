import copy
import json

import numpy as np
import pytest

from research.v63.numerics import (
    calibrate, check_portfolio, displayed_covariance, generate_scenarios,
    pair_metrics, policy_weights, posterior, replacement_signals,
    solve_reference, tv,
)


@pytest.fixture(scope="module")
def calibration():
    return calibrate()


def test_raw_monthly_block_and_decimal_cache(calibration):
    assert calibration["observations"] == 120
    assert calibration["dates"][0] == "2016-01"
    assert calibration["dates"][-1] == "2025-12"
    assert calibration["raw_cache_max_abs_difference"] == 0
    assert np.linalg.eigvalsh(calibration["Sigma"]).min() > 0
    assert calibration["returns"].shape == (120, 12)


@pytest.mark.parametrize("r", [.5, 1., 2.])
def test_full_posterior_against_independent_joint_gaussian(r):
    m = np.array([.01, .03, -.02])
    V = np.array([[.3,.05,.08],[.05,.2,.01],[.08,.01,.4]])
    y, x = np.array([.1,.2,.3]), np.array([-.2,.3,.4])
    evidence = [dict(evidence_id="x", signal_id="own", indices=[0,1,2], values=x, precision=r)]
    actual = posterior(m,V,y,V,evidence)
    # Independent covariance conditioning instead of precision update.
    H = np.vstack([np.eye(3),np.eye(3)])
    R = np.zeros((6,6)); R[:3,:3]=V; R[3:,3:]=displayed_covariance(V/r)
    K = V@H.T@np.linalg.inv(H@V@H.T+R)
    expected = m+K@(np.r_[y,x]-H@m)
    assert np.max(np.abs(expected-actual["mean"])) < 1e-12
    assert np.max(np.abs(V-K@H@V-actual["covariance"])) < 1e-12


def test_partial_correlated_fragments_merge_without_double_count():
    m=np.zeros(3); V=np.array([[1,.3,.2],[.3,2,.4],[.2,.4,1.]])
    y=np.array([1.,0.,-1.]); x=[2.,4.]
    joined=[dict(evidence_id="all",signal_id="private",indices=[0,2],values=x,precision=2.)]
    fragments=[dict(evidence_id="a",signal_id="private",indices=[0],values=[2.],precision=2.),
               dict(evidence_id="b",signal_id="private",indices=[0,2],values=x,precision=2.)]
    one=posterior(m,V,y,V,joined); two=posterior(m,V,y,V,fragments)
    assert np.array_equal(one["mean"],two["mean"])
    H=np.eye(3)[[0,2]]
    base_mean=y/2; base_cov=V/2
    K=base_cov@H.T@np.linalg.inv(H@base_cov@H.T+H@(V/2)@H.T)
    expected=base_mean+K@(np.array(x)-H@base_mean)
    assert np.max(abs(expected-one["mean"])) < 1e-12


def test_missing_precision_and_conflicting_fragments_rejected():
    item=dict(evidence_id="a",signal_id="own",indices=[0],values=[1])
    with pytest.raises(ValueError,match="precision"):
        posterior(np.zeros(2),np.eye(2),np.zeros(2),np.eye(2),[item])
    item["precision"]=1
    conflict=dict(item,evidence_id="b",values=[2])
    with pytest.raises(ValueError,match="Conflicting"):
        posterior(np.zeros(2),np.eye(2),np.zeros(2),np.eye(2),[item,conflict])


def test_generation_separation_balance_and_reproducibility(calibration):
    cases, hidden = generate_scenarios(calibration,"main")
    cases2, hidden2 = generate_scenarios(calibration,"main")
    assert len(cases)==60
    assert all("theta" not in case for case in cases)
    assert np.array_equal(cases[1]["y"],cases2[1]["y"])
    assert np.array_equal(hidden[5]["theta"],hidden2[5]["theta"])
    changed = replacement_signals(calibration,cases,hidden)
    for r in [.5,1.,2.]:
        for fid in ["F01","F02","F03","F04"]:
            assert sum(c["r"]==r and c["fund_id"]==fid for c in changed)==5
    dev,_=generate_scenarios(calibration,"development")
    assert not np.array_equal(dev[0]["y"],cases[0]["y"])


def test_analytic_two_asset_oracle_and_ranges():
    # w1^2+(1-w1)^2<=.68 implies .2<=w1<=.8; maximizing w1 yields .8.
    ref=solve_reference([1.,0.],[.8,.2],np.eye(2))
    assert abs(ref["weights"][0]-.8)<1e-8
    assert ref["primal_dual_gap"]<=1e-9
    assert ref["coordinate_lower"][0] <= .8 <= ref["coordinate_upper"][0]
    assert ref["eta"] < 1e-6


def test_explicit_constraint_and_invalid_start():
    ref=solve_reference([1.,0.],[.7,.3],np.eye(2),[[1.,0.]],[.75],coordinate_ranges=False)
    assert ref["weights"][0] <= .70000001
    with pytest.raises(ValueError,match="Starting holdings"):
        solve_reference([1.,0.],[.8,.2],np.eye(2),[[1.,0.]],[.5])


def test_binding_explicit_rule_with_inactive_risk():
    ref=solve_reference([1.,0.],[.8,.2],np.diag([.1,1.]),[[1.,0.]],[.9])
    assert abs(ref["weights"][0]-.9)<1e-8
    assert ref["coordinate_lower"][0] <= .9 <= ref["coordinate_upper"][0]
    assert ref["primal_dual_gap"]<=1e-9
    assert ref["dual_risk"] == 0
    assert ref["feasibility"]["risk_residual"] < 0
    assert "global simplex linear upper bound" in ref["certificate"]


def test_nonunique_objective_ranges_are_preserved():
    ref=solve_reference([0.,0.],[.8,.2],np.eye(2))
    assert ref["coordinate_lower"][0] <= .2+1e-8
    assert ref["coordinate_upper"][0] >= .8-1e-8
    assert ref["one_percentage_point_width_diagnostic"]
    assert ref["eta"] > .25


def test_raw_weights_never_normalized_and_missing_not_fallback():
    h=np.array([.8,.2]); Sigma=np.eye(2)
    raw=np.array([.1,.1])
    check=check_portfolio(raw,h,Sigma)
    assert not check["valid"] and check["budget_residual"]==pytest.approx(-.8)
    assert np.array_equal(check["raw_weights"],raw)
    with pytest.raises(ValueError,match="Unattempted"):
        policy_weights(raw,h,Sigma,terminal_status="not_attempted")
    fallback=policy_weights(raw,h,Sigma,terminal_status="model_output_failure")
    assert fallback["fallback"] and np.array_equal(fallback["weights"],h)


def test_swapped_references_are_detected_and_uncertainty_conservative():
    vi,vj=np.array([.8,.2]),np.array([.2,.8])
    ri=dict(weights=vi,eta=.01); rj=dict(weights=vj,eta=.02)
    correct=pair_metrics(vi,vj,ri,rj)
    swapped=pair_metrics(vj,vi,ri,rj)
    assert correct["G"]==0 and correct["E"]==0
    assert swapped["G"]==0 and swapped["E"]>1
    assert swapped["E_interval"][0] < swapped["E"] < swapped["E_interval"][1]
    assert correct["A_interval"][0]==0


def test_nan_and_risk_breaches_remain_invalid():
    assert not check_portfolio([float("nan"),1],[.8,.2],np.eye(2))["valid"]
    assert "risk_cap" in check_portfolio([1.,0.],[.8,.2],np.eye(2))["failures"]


def test_negative_control_same_signal_in_all_four_labels(calibration):
    scenarios,_=generate_scenarios(calibration,"negative_control")
    for scenario in scenarios:
        signals=list(scenario["private_signals"].values())
        assert all(np.array_equal(signals[0],x) for x in signals)


def test_actual_twelve_dimensional_near_optimal_dual_ranges(calibration):
    h=np.random.Generator(np.random.PCG64(np.random.SeedSequence(81001))).dirichlet(np.ones(12)*3,size=4)[2]
    s=generate_scenarios(calibration)[0][5]
    evidence=[dict(evidence_id="x",signal_id="own",indices=list(range(12)),
                   values=s["private_signals"]["F03"],precision=s["r"])]
    post=posterior(calibration["m0"],calibration["V0"],s["y"],calibration["Omega0"],evidence)
    ref=solve_reference(post["mean"],h,calibration["Sigma"])
    assert ref["coordinate_dual_gap_max"]<=1e-9
    assert np.all(ref["coordinate_lower"] <= ref["weights"]+1e-9)
    assert np.all(ref["coordinate_upper"] >= ref["weights"]-1e-9)
    assert ref["independent_objective_abs_difference"]<=1e-9


def test_degenerate_minimum_variance_cap_exact_singleton_certificate():
    ref=solve_reference([1.,0.],[.5,.5],np.eye(2))
    assert ref["status"]=="exact_singleton_risk_set_certified"
    assert np.array_equal(ref["weights"],[.5,.5])
    assert ref["exact_risk_radius"]=="0"
    assert ref["primal_objective"]==.5
    assert ref["dual_bound"]>=.5
    assert ref["eta"]<1e-15


def test_selected_main_013_f02_r0_solver_and_coordinate_ranges(calibration):
    # The original unscaled SLSQP returned status 8 at this feasible optimum.
    # Coordinate 5 also has a risk-inactive affine vertex that the previous
    # positive-radius-only polisher missed. Retain all acceptance checks.
    from research.v63.build_run import load_profiles
    from research.v63.numerics import ROOT
    profile = load_profiles(ROOT / "data/v63_20261027/continuation_sources/profiles_v2.json", "A_B")["F02"]
    scenario = next(s for s in generate_scenarios(calibration, "main")[0]
                    if s["scenario_id"] == "main-013")
    mean = posterior(calibration["m0"], calibration["V0"], scenario["y"],
                     calibration["Omega0"], [])["mean"]
    ref = solve_reference(mean, profile["h"], calibration["Sigma"],
                          profile.get("A"), profile.get("b"))
    second = ref["independent_crosscheck"]
    assert second["success"] and second["feasibility"]["valid"]
    assert second["objective"] == pytest.approx(float(mean @ second["weights"]), abs=1e-15)
    assert ref["independent_objective_abs_difference"] <= 1e-9
    assert ref["primal_dual_gap"] <= 1e-9
    assert ref["coordinate_dual_gap_max"] <= 1e-9
    assert np.all(ref["coordinate_lower"] <= ref["weights"] + 1e-9)
    assert np.all(ref["coordinate_upper"] >= ref["weights"] - 1e-9)
