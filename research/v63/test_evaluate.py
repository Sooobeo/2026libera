"""All fixtures are synthetic software verification, never experimental output."""
import copy
import itertools

import numpy as np
import pytest

from research.v63.evaluate import (ARMS,FUNDS,build_reference_bank,evaluate_main,
    evaluate_counterfactual,evaluate_negative_control,terminal_policy)
from research.v63.evaluate import evaluate_actual_documents
from research.v63.numerics import calibrate,generate_scenarios


def reference(weights,mu,eta=0.):
    value=float(np.asarray(weights)@mu)
    return dict(weights=list(weights),primal_objective=value,dual_bound=value,eta=eta)


def profile(fid):
    index=int(fid[-2:])-1
    h=np.eye(12)[0];fullw=np.eye(12)[index];mu=fullw*.01
    full=dict(mu=mu.tolist(),reference=reference(fullw,mu),evidence_ids=["x"])
    r0=dict(mu=(h*.01).tolist(),reference=reference(h,h*.01),evidence_ids=[])
    return dict(h=h.tolist(),Sigma=np.eye(12).tolist(),A=None,b=None,full=full,
                available={a:(r0 if a=="R0" else full) for a in ARMS})


def trace(fid,arm,weights,*,status="completed",last_stage=3):
    stages=[dict(stage=s,status="completed",exposed_evidence_ids=["x"],
                 raw_output=dict(weights=list(weights)) if s==3 else {}) for s in range(1,last_stage+1)]
    if status!="completed":stages[-1]["status"]=status
    return dict(engineering_only=True,fund_id=fid,arm=arm,status=status,effective_weights=list(weights),
                actual_model_calls=last_stage,calls=[dict(status="response",elapsed_seconds=.01,
                raw_response=dict(model_sha256="synthetic-pinned",finish_reason="stop",usage={"input_tokens":1})) for _ in stages],stages=stages)


@pytest.fixture
def main_fixture():
    scenarios=[dict(scenario_id=f"main-{i+1:03d}",r=(.5,1.,2.)[i%3]) for i in range(60)]
    bank={s["scenario_id"]:{fid:profile(fid) for fid in FUNDS} for s in scenarios}
    rows=[]
    for s in scenarios:
        for fid,arm,rep in itertools.product(FUNDS,ARMS,(1,2)):
            w=bank[s["scenario_id"]][fid]["full"]["reference"]["weights"]
            rows.append(dict(block="B-main",scenario=s["scenario_id"],fund_id=fid,arm=arm,replicate=rep,
                             trace=trace(fid,arm,w)))
    return rows,bank,scenarios


def evaluate(rows,bank,scenarios):
    return evaluate_main(rows,bank,scenarios,frozen_model_sha256="synthetic-pinned",allow_synthetic=True,bootstrap_resamples=32)


def test_complete_trace_pipeline_oracle_identity(main_fixture):
    rows,bank,scenarios=main_fixture
    out=evaluate(rows,bank,scenarios)
    assert out["status"]=="synthetic_verification_only"
    assert out["trajectories"]==2400
    assert out["terminal_counts"]=={"completed":2400}
    assert np.max(np.abs(out["metrics"]["C-context"]["G_available"]))==0
    assert np.max(np.abs(out["metrics"]["C-context"]["R_available"]))==0
    assert len(out["inference"]["claims"])==5
    assert not out["inference"]["claims"]["H1"]["reject"]


def test_missing_or_protocol_invalid_not_filled_with_h(main_fixture):
    rows,bank,scenarios=main_fixture
    out=evaluate(rows[:-1],bank,scenarios)
    assert out["status"]=="incomplete_no_confirmatory_analysis"
    assert len(out["missing"])==1 and not out["not_attempted_filled_with_h"]
    rows[0]["trace"]["status"]="protocol_violation"
    out=evaluate(rows,bank,scenarios)
    assert len(out["nonterminal"])==1
    assert all(c["p"]==1 for c in out["claims"].values())


def test_terminal_failure_contributes_h_and_early_R3_has_R0_information(main_fixture):
    rows,bank,scenarios=main_fixture
    row=next(r for r in rows if r["scenario"]=="main-001" and r["arm"]=="R3" and r["fund_id"]=="F02" and r["replicate"]==1)
    row["trace"]=trace("F02","R3",bank["main-001"]["F02"]["h"],status="model_output_failure",last_stage=1)
    out=evaluate(rows,bank,scenarios)
    assert out["terminal_counts"]["model_output_failure"]==1
    assert out["metrics"]["R3"]["fallback_fund_fraction"][0]==.125
    diag=next(d for d in out["trajectory_diagnostics"] if tuple(d["identity"])==("main-001","F02","R3",1))
    assert diag["available_reference_key"]=="R0"
    assert out["metrics"]["R3"]["R_full"][0]>.001


def test_aggregation_before_weight_averaging_and_exact_regret(main_fixture):
    rows,bank,scenarios=main_fixture
    for row in rows:
        if row["scenario"]=="main-001" and row["arm"]=="R1" and row["replicate"]==2:
            index=int(row["fund_id"][-2:])-1
            row["trace"]=trace(row["fund_id"],"R1",np.eye(12)[3-index])
    out=evaluate(rows,bank,scenarios)
    assert out["metrics"]["R1"]["D_full"][0]==1.
    averaged=(np.eye(12)[:4]+np.eye(12)[[3,2,1,0]])/2
    naive=np.mean([.5*np.abs(averaged[i]-averaged[j]).sum() for i,j in itertools.combinations(range(4),2)])
    assert naive < out["metrics"]["R1"]["D_full"][0]
    assert out["exact_regret_differences"]["R1|R2"][0]==pytest.approx(.005)


def test_completed_raw_inconsistency_and_model_drift_rejected(main_fixture):
    rows,bank,scenarios=main_fixture
    rows[0]["trace"]["stages"][-1]["raw_output"]["weights"]=[.01]*12
    with pytest.raises(ValueError,match="valid final raw"):evaluate(rows,bank,scenarios)
    rows[0]["trace"]["calls"][0]["raw_response"]["model_sha256"]="changed"
    with pytest.raises(ValueError,match="unpinned"):evaluate(rows,bank,scenarios)


def test_counterfactual_zero_reference_change_retained(main_fixture):
    rows,bank,scenarios=main_fixture
    assignments=[dict(scenario_id=s["scenario_id"],fund_id=FUNDS[i%4]) for i,s in enumerate(scenarios)]
    replacements=[]
    for a in assignments:
        for row in rows:
            if row["scenario"]==a["scenario_id"] and row["fund_id"]==a["fund_id"] and row["arm"] in ("R1","R3","C-context"):
                replacements.append(dict(row,block="x-replacement"))
    out=evaluate_counterfactual(rows,replacements,bank,bank,assignments,frozen_model_sha256="synthetic-pinned",allow_synthetic=True)
    assert len(out["rows"])==360
    assert all(r["zero_reference_change"] and r["response_error"]==0 for r in out["rows"])


def test_negative_control_canonical_reference_and_labels():
    ids=[f"negative_control-{i+1:03d}" for i in range(8)]
    bank={sid:{f"N{i:02d}":profile("F01") for i in range(1,5)} for sid in ids}
    rows=[]
    for sid,label,arm,rep in itertools.product(ids,tuple(f"N{i:02d}" for i in range(1,5)),("R1","R3","C-context"),(1,2)):
        rows.append(dict(block="negative-control",scenario=sid,fund_id=label,arm=arm,replicate=rep,
                         trace=trace(label,arm,np.eye(12)[int(label[-2:])-1])))
    out=evaluate_negative_control(rows,bank,ids,frozen_model_sha256="synthetic-pinned",allow_synthetic=True)
    assert len(out["rows"])==8*3*2*6
    assert all(r["Dstar"]==0 and r["G"]==-r["D"] for r in out["rows"])
    bank[ids[0]]["N02"]["h"]=np.eye(12)[1].tolist()
    with pytest.raises(ValueError,match="profiles differ"):
        evaluate_negative_control(rows,bank,ids,frozen_model_sha256="synthetic-pinned",allow_synthetic=True)


def test_reference_bank_rejects_wrong_fund_evidence():
    c=calibrate();s=generate_scenarios(c,count=1)[0]
    profiles={"F01":dict(h=np.eye(12)[0])}
    evidence={s[0]["scenario_id"]:{"F01":[dict(evidence_id="bad",signal_id="F01",indices=[0],values=[99.],precision=.5)]}}
    with pytest.raises(ValueError,match="own-fund signal"):
        build_reference_bank(c,s,profiles,evidence)


def test_actual_documents_never_use_synthetic_weight_gold():
    profiles={module:{fid:profile(fid) for fid in FUNDS} for module in ("A","C")}
    rows=[]
    for module,fid,arm,rep in itertools.product(("A","C"),FUNDS,ARMS,(1,2)):
        t=trace(fid,arm,profiles[module][fid]["h"])
        t["stages"][-1]["raw_output"]["evidence"]=[dict(evidence_id="x",value="quoted",unit="text",date="2026-01-01")]
        rows.append(dict(block="actual-documents",scenario=module,fund_id=fid,arm=arm,replicate=rep,trace=t))
    out=evaluate_actual_documents(rows,profiles,frozen_model_sha256="synthetic-pinned",allow_synthetic=True)
    assert len(out["rows"])==80
    assert not out["exact_allocation_gold"] and not out["regret_evaluation_applied"]
    assert out["fact_scoring_coverage"]==0
    assert all(not f["source_fact_scored"] for f in out["fact_checks"])


def test_actual_document_fact_bundles_do_not_mix_values_units_or_periods():
    profiles={module:{fid:profile(fid) for fid in FUNDS} for module in ("A","C")}
    t=trace("F01","R1",profiles["C"]["F01"]["h"])
    t["stages"][-1]["raw_output"]["evidence"]=[dict(evidence_id="fact",value=2.2,unit="times",date="2026-06-17")]
    rows=[dict(block="actual-documents",scenario="C",fund_id="F01",arm="R1",replicate=1,trace=t)]
    catalog={"fact":dict(fund_id="COMMON",period="C",publication_date="2026-06-17",
        facts=[dict(value=2.2,unit="percent",date="2026-06-17"),dict(value=3.8,unit="times",date="2026-06-17")])}
    out=evaluate_actual_documents(rows,profiles,frozen_model_sha256="synthetic-pinned",source_catalog=catalog,allow_synthetic=True)
    checked=out["fact_checks"][0]
    assert checked["numeric_fact_scored"] and not checked["matching_source_fact_indices"]
    assert checked["requires_semantic_review"] and checked["publication_within_cutoff"]
    catalog["fact"]["publication_date"]="2026-03-18";catalog["fact"]["period"]="A"
    checked=evaluate_actual_documents(rows,profiles,frozen_model_sha256="synthetic-pinned",source_catalog=catalog,allow_synthetic=True)["fact_checks"][0]
    assert not checked["publication_within_cutoff"] and not checked["correct_period"]
