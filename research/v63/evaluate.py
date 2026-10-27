"""v6.3 reference construction and trace-to-policy/statistics pipeline.

Inputs are frozen run identities and real terminal traces. Synthetic tests are
explicitly marked; missing or protocol-invalid runs never become hold-h results.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from collections import Counter
from pathlib import Path

import numpy as np

from research.v63.numerics import (ROOT, check_portfolio, jsonable, pair_metrics,
    posterior, regret_bounds, sha256, solve_reference, tv, write_json)
from research.v63.statistics import ARMS, CLAIMS, confirmatory_family, stratified_bootstrap

FUNDS=tuple(f"F{i:02d}" for i in range(1,5))
TERMINAL={"completed","model_output_failure","operational_failure"}


def code_provenance():
    return {p:sha256(ROOT/p) for p in ["research/v63/evaluate.py","research/v63/numerics.py","research/v63/statistics.py"]}


def _hash_object(value):
    return hashlib.sha256(json.dumps(jsonable(value),sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


def build_reference_bank(calibration,scenarios,profiles,retrieved_evidence,*,progress=None):
    """Build canonical references BEFORE model outputs, with no outcome filtering.

    profiles={fund_id:{h,A?,b?}}. retrieved_evidence[scenario_id][fund_id]
    contains exactly the exposed atomic fragments accepted by posterior().
    R1/R2/R3 final views reuse one reference; C-context reuses full information.
    All fragments are checked against that fund's frozen synthetic signal.
    """
    bank={};cache={};Sigma=np.asarray(calibration["Sigma"])
    for scenario in scenarios:
        sid=scenario["scenario_id"]
        if sid in bank: raise ValueError("Duplicate scenario in frozen input")
        bank[sid]={}
        for fid,profile in profiles.items():
            h=np.asarray(profile["h"],float);A=profile.get("A");b=profile.get("b")
            if h.shape!=(12,): raise ValueError("Require exactly 12 holdings weights")
            x=np.asarray(scenario["private_signals"][fid],float)
            exposed=retrieved_evidence[sid][fid]
            if len({item.get("signal_id") for item in exposed})>1:
                raise ValueError("Own-fund fragments must represent one correlated private signal")
            for item in exposed:
                if item.get("precision")!=scenario["r"]:
                    raise ValueError("Retrieved precision differs from frozen own signal")
                for k,value in zip(item.get("indices",[]),item.get("values",[])):
                    if not isinstance(k,int) or not 0<=k<12 or float(value)!=x[k]:
                        raise ValueError("Retrieved observation is not the frozen own-fund signal")
            full=[dict(evidence_id=f"{sid}:{fid}:full",signal_id=fid,
                       indices=list(range(12)),values=x,precision=scenario["r"])]
            def view(evidence):
                p=posterior(calibration["m0"],calibration["V0"],scenario["y"],calibration["Omega0"],evidence)
                key=_hash_object([p["mean"],h,Sigma,A,b])
                if key not in cache:
                    cache[key]=solve_reference(p["mean"],h,Sigma,A,b)
                return dict(mu=p["mean"],covariance=p["covariance"],reference=cache[key],
                            evidence_ids=[x["evidence_id"] for x in evidence],reference_input_sha256=key)
            f=view(full);r0=view([]);retrieved=view(exposed)
            bank[sid][fid]=dict(h=h,Sigma=Sigma,A=A,b=b,r=scenario["r"],full=f,
                available={"R0":r0,"R1":retrieved,"R2":retrieved,"R3":retrieved,"C-context":f},
                reference_role="conditional research task; not fund-manager optimum",
                source_profile_sha256=_hash_object(profile))
            if progress: progress(sid,fid,len(cache))
    return jsonable(bank)


def _record_key(record):
    return (record["scenario"],record["fund_id"],record["arm"],int(record["replicate"]))


def index_records(records,block=None):
    result={}
    for row in records:
        if block is not None and row.get("block")!=block: continue
        key=_record_key(row)
        if key in result: raise ValueError(f"Duplicate trajectory identity: {key}")
        result[key]=row
    return result


def load_trace(record,*,allow_synthetic=False):
    if "trace" in record:
        if not allow_synthetic: raise ValueError("Inline traces are accepted only for marked synthetic verification")
        trace=record["trace"]
        source=dict(path=None,sha256=_hash_object(trace),synthetic=True)
    else:
        path=Path(record["trace_path"])
        if not path.is_absolute():path=ROOT/path
        if not path.is_file(): return None,dict(path=str(path),missing=True)
        digest=sha256(path)
        if record.get("trace_sha256") and record["trace_sha256"]!=digest:
            raise ValueError("Trace hash differs from recorded terminal artifact")
        trace=json.loads(path.read_text(encoding="utf-8-sig"))
        source=dict(path=str(path),sha256=digest,synthetic=False)
    if trace.get("engineering_only") and not allow_synthetic:
        raise ValueError("Engineering mocks cannot enter empirical analysis")
    if trace.get("arm")!=record["arm"] or trace.get("fund_id")!=record["fund_id"]:
        raise ValueError("Trace identity differs from schedule row")
    return trace,source


def terminal_policy(record,profile,*,frozen_model_sha256,allow_synthetic=False):
    if not isinstance(frozen_model_sha256,str) or not frozen_model_sha256:
        raise ValueError("A nonempty frozen model snapshot hash is required")
    trace,source=load_trace(record,allow_synthetic=allow_synthetic)
    if trace is None: return dict(status="not_attempted",eligible=False,source=source)
    status=trace.get("status","not_attempted")
    if status not in TERMINAL:
        return dict(status=status,eligible=False,source=source)
    calls=trace.get("calls",[])
    if not calls: raise ValueError("Terminal outcome without any actual request attempt")
    for call in calls:
        response=call.get("raw_response")
        if response and response.get("finish_reason")!="incomplete" and response.get("model_sha256")!=frozen_model_sha256:
            raise ValueError("Terminal trace contains an unpinned model snapshot")
    h=np.asarray(profile["h"],float);Sigma=np.asarray(profile["Sigma"],float)
    A,b=profile.get("A"),profile.get("b")
    if not check_portfolio(h,h,Sigma,A,b)["valid"]:raise ValueError("Infeasible h cannot supply fallback")
    stages=trace.get("stages",[])
    raw_final=next((s.get("raw_output",{}).get("weights") for s in stages if s.get("stage")==3 and isinstance(s.get("raw_output"),dict)),None)
    validation=check_portfolio(raw_final,h,Sigma,A,b) if raw_final is not None else None
    if status=="completed":
        if validation is None or not validation["valid"]:
            raise ValueError("Completed trace has no valid final raw weights; declare evaluator/runtime reanalysis")
        weights=np.asarray(raw_final,float);fallback=False
    else:
        weights=h.copy();fallback=True
    supplied=trace.get("effective_weights")
    if supplied is None or not np.array_equal(np.asarray(supplied,float),weights):
        raise ValueError("Runtime effective weights differ from raw-or-h policy")
    diagnostics=[]
    for stage in stages:
        row={k:stage[k] for k in ("stage","status","reason","unexposed_citation_ids") if k in stage}
        output=stage.get("raw_output")
        if isinstance(output,dict) and "weights" in output:
            row["raw_validation"]=check_portfolio(output["weights"],h,Sigma,A,b)
            if stage.get("stage")==2 and "change_from_h" in output:
                row["change_from_h_max_abs_error"]=float(np.max(np.abs(np.asarray(output["change_from_h"])-(np.asarray(output["weights"])-h))))
        diagnostics.append(row)
    reached=max((int(s["stage"]) for s in stages if "exposed_evidence_ids" in s),default=0)
    onset={"R0":None,"R1":1,"R2":2,"R3":3,"C-context":1}[record["arm"]]
    available_key=record["arm"] if onset is not None and reached>=onset else "R0"
    usage=Counter()
    for call in calls:
        for key,value in (call.get("raw_response",{}).get("usage") or {}).items():
            if isinstance(value,(int,float)):usage[key]+=value
    return dict(status=status,eligible=True,weights=weights,fallback=fallback,
                raw_valid=status=="completed",raw_final=raw_final,validation=validation,
                actual_model_calls=trace.get("actual_model_calls",len(calls)),
                elapsed_seconds=sum(float(c.get("elapsed_seconds",0)) for c in calls),
                usage=dict(usage),stage_diagnostics=diagnostics,source=source,
                available_reference_key=available_key,last_attempted_stage=reached)


def _replicate_metrics(policies,profiles,arm):
    full_pairs=[];available_pairs=[];full_regret=[];available_regret=[]
    for fid in FUNDS:
        p=policies[fid];profile=profiles[fid];full=profile["full"];avail=profile["available"][p["available_reference_key"]]
        for dest,view in ((full_regret,full),(available_regret,avail)):
            mu=np.asarray(view["mu"]);w=p["weights"];ref=view["reference"]
            dest.append(dict(fund_id=fid,point=float(mu@(np.asarray(ref["weights"])-w)),
                             interval=regret_bounds(mu,w,ref),fallback=p["fallback"]))
    for i,j in itertools.combinations(FUNDS,2):
        wi,wj=policies[i]["weights"],policies[j]["weights"]
        fallback=policies[i]["fallback"] or policies[j]["fallback"]
        for dest,key in ((full_pairs,"full"),(available_pairs,"available")):
            a=profiles[i][key] if key=="full" else profiles[i][key][policies[i]["available_reference_key"]]
            b=profiles[j][key] if key=="full" else profiles[j][key][policies[j]["available_reference_key"]]
            metrics=pair_metrics(wi,wj,a["reference"],b["reference"])
            dest.append(dict(fund_i=i,fund_j=j,fallback_involved=fallback,**metrics))
    result={}
    for name,pairs,regrets in (("full",full_pairs,full_regret),("available",available_pairs,available_regret)):
        for key in ("D","Dstar","G","E","A"):
            result[f"{key}_{name}"]=float(np.mean([p[key] for p in pairs]))
        for key in ("Dstar","G","E","A"):
            for ix,label in enumerate(("lower","upper")):
                result[f"{key}_{name}_{label}"]=float(np.mean([p[key+"_interval"][ix] for p in pairs]))
        result[f"R_{name}"]=float(np.mean([r["point"] for r in regrets]))
        result[f"R_{name}_lower"]=float(np.mean([r["interval"][0] for r in regrets]))
        result[f"R_{name}_upper"]=float(np.mean([r["interval"][1] for r in regrets]))
        result[f"unidentified_reference_pair_fraction_{name}"]=float(np.mean([p["Dstar_interval"][0]<=0 for p in pairs]))
    result["information_set_distance_component"]=result["G_full"]-result["G_available"]
    result["fallback_fund_fraction"]=float(np.mean([p["fallback"] for p in policies.values()]))
    result["fallback_pair_fraction"]=float(np.mean([p["fallback_involved"] for p in full_pairs]))
    result["G_full_fallback_pair_contribution"]=sum(p["G"] for p in full_pairs if p["fallback_involved"])/6
    result["G_full_valid_pair_contribution"]=sum(p["G"] for p in full_pairs if not p["fallback_involved"])/6
    result["R_full_fallback_contribution"]=sum(r["point"] for r in full_regret if r["fallback"])/4
    result["R_full_valid_contribution"]=sum(r["point"] for r in full_regret if not r["fallback"])/4
    result["valid_only_pair_count"]=sum(not p["fallback_involved"] for p in full_pairs)
    valid_pairs=[p for p in full_pairs if not p["fallback_involved"]]
    valid_diagnostics={key:float(np.mean([p[key] for p in valid_pairs])) if valid_pairs else None for key in ("G","E","A")}
    return dict(metrics=result,full_pairs=full_pairs,available_pairs=available_pairs,
                full_regret=full_regret,available_regret=available_regret,
                valid_only_diagnostics=valid_diagnostics)


def _incomplete(missing,nonterminal,expected,observed):
    return dict(status="incomplete_no_confirmatory_analysis",expected_trajectories=expected,
        observed_records=observed,missing=missing,nonterminal=nonterminal,
        claims={claim:dict(p=1.,p_holm=1.,reject=False,not_testable=True,reason="incomplete planned sample") for claim in CLAIMS},
        source_hashes=code_provenance(),not_attempted_filled_with_h=False)


def evaluate_main(records,reference_bank,frozen_scenarios,*,frozen_model_sha256,
                  allow_synthetic=False,bootstrap_resamples=10000):
    ids=[s["scenario_id"] for s in frozen_scenarios];strata=[s["r"] for s in frozen_scenarios]
    if len(ids)!=60 or len(set(ids))!=60 or Counter(strata)!={.5:20,1.:20,2.:20}:
        raise ValueError("Require original frozen 60 scenarios with 20 per precision stratum")
    rows=index_records(records,"B-main")
    expected=set(itertools.product(ids,FUNDS,ARMS,(1,2)))
    extras=set(rows)-expected
    if extras:raise ValueError(f"Unregistered main trajectories: {sorted(extras)[:3]}")
    missing=sorted(expected-set(rows));policies={};nonterminal=[]
    for key,row in rows.items():
        sid,fid,arm,rep=key
        p=terminal_policy(row,reference_bank[sid][fid],frozen_model_sha256=frozen_model_sha256,allow_synthetic=allow_synthetic)
        policies[key]=p
        if not p["eligible"]:nonterminal.append(dict(identity=key,status=p["status"]))
    if missing or nonterminal:return _incomplete(missing,nonterminal,len(expected),len(rows))
    metrics={};replicate_rows=[]
    for arm in ARMS:
        data=dict(scenario_ids=ids.copy(),scenario_strata=list(strata),terminal_statuses=[],attempted_fund_replicates=[8]*60)
        for sid in ids:
            per_rep=[]
            for rep in (1,2):
                selected={fid:policies[(sid,fid,arm,rep)] for fid in FUNDS}
                r=_replicate_metrics(selected,reference_bank[sid],arm)
                per_rep.append(r["metrics"])
                replicate_rows.append(dict(scenario=sid,arm=arm,replicate=rep,**r))
            for key in per_rep[0]:data.setdefault(key,[]).append(float(np.mean([r[key] for r in per_rep])))
            data["terminal_statuses"].append([policies[(sid,fid,arm,rep)]["status"] for fid in FUNDS for rep in (1,2)])
        metrics[arm]=data
    exact={}
    for a,b in itertools.combinations(ARMS,2):
        exact[a+"|"+b]=[float(np.mean([
            np.asarray(reference_bank[sid][fid]["full"]["mu"])@(policies[(sid,fid,b,rep)]["weights"]-policies[(sid,fid,a,rep)]["weights"])
            for fid in FUNDS for rep in (1,2)])) for sid in ids]
    inference=confirmatory_family(metrics,exact,frozen_scenario_ids=ids,frozen_strata=strata)
    summaries={}
    for arm,data in metrics.items():
        keys=[k for k,v in data.items() if k not in ("scenario_ids","scenario_strata","terminal_statuses","attempted_fund_replicates")]
        matrix=np.array([data[k] for k in keys]).T
        ci=stratified_bootstrap(matrix,strata,resamples=bootstrap_resamples)
        summaries[arm]={key:dict(mean=float(np.mean(data[key])),lower95=ci["lower"][j],upper95=ci["upper"][j]) for j,key in enumerate(keys)}
    diagnostics=[dict(identity=key,**{k:v for k,v in p.items() if k!="weights"}) for key,p in policies.items()]
    totals=Counter(p["status"] for p in policies.values());usage=Counter()
    for p in policies.values():usage.update(p["usage"])
    return jsonable(dict(status="synthetic_verification_only" if allow_synthetic else "completed_confirmatory_analysis",
        trajectories=len(expected),independent_scenarios=60,fund_pairs_independent=False,replicates_independent=False,
        aggregation="compute pair/absolute/regret metrics within each replicate, then average replicates within scenario",
        terminal_counts=dict(totals),actual_model_calls=sum(p["actual_model_calls"] for p in policies.values()),
        elapsed_request_seconds=sum(p["elapsed_seconds"] for p in policies.values()),usage=dict(usage),
        metrics=metrics,scenario_summaries=summaries,replicate_metrics=replicate_rows,
        exact_regret_differences=exact,inference=inference,trajectory_diagnostics=diagnostics,
        bootstrap=dict(resamples=bootstrap_resamples,seed=7001,unit="whole scenario",stratified=True,simultaneous=False),
        input_fingerprint=_hash_object([ids,strata,reference_bank]),frozen_model_sha256=frozen_model_sha256,
        source_hashes=code_provenance(),interpretation="Conditional research task, not an institution's actual optimum. Failure/fallback contributions are separately disclosed."))


def evaluate_counterfactual(main_records,replacement_records,main_bank,replacement_bank,assignments,
                            *,frozen_model_sha256,allow_synthetic=False):
    baseline=index_records(main_records,"B-main");replacement=index_records(replacement_records,"x-replacement")
    expected={(a["scenario_id"],a["fund_id"],arm,rep) for a in assignments for arm in ("R1","R3","C-context") for rep in (1,2)}
    if len(assignments)!=60 or len(expected)!=360:raise ValueError("Require all 60 frozen replacement assignments")
    if len({a["scenario_id"] for a in assignments})!=60 or {a["scenario_id"] for a in assignments}!=set(main_bank):
        raise ValueError("Replacement assignments must cover every main scenario exactly once")
    if not allow_synthetic:
        allocation=Counter((main_bank[a["scenario_id"]][a["fund_id"]]["r"],a["fund_id"]) for a in assignments)
        if allocation!={(r,fid):5 for r in (.5,1.,2.) for fid in FUNDS}:
            raise ValueError("Replacement assignments must target each fund five times within each precision stratum")
    for a in assignments:
        sid,fid=a["scenario_id"],a["fund_id"]
        for key in ("h","Sigma","A","b"):
            if _hash_object(main_bank[sid][fid].get(key))!=_hash_object(replacement_bank[sid][fid].get(key)):
                raise ValueError("Counterfactual changed a held-fixed profile field")
        for other in FUNDS:
            if other!=fid and _hash_object(main_bank[sid][other]["full"]["mu"])!=_hash_object(replacement_bank[sid][other]["full"]["mu"]):
                raise ValueError("Counterfactual changed another fund's private information")
    if set(replacement)-expected:raise ValueError("Unregistered replacement trajectory")
    missing=sorted(expected-set(replacement));rows=[];nonterminal=[]
    for key in sorted(expected & set(replacement)):
        if key not in baseline:missing.append(key);continue
        sid,fid,arm,rep=key
        pa=terminal_policy(baseline[key],main_bank[sid][fid],frozen_model_sha256=frozen_model_sha256,allow_synthetic=allow_synthetic)
        pb=terminal_policy(replacement[key],replacement_bank[sid][fid],frozen_model_sha256=frozen_model_sha256,allow_synthetic=allow_synthetic)
        if not pa["eligible"] or not pb["eligible"]:nonterminal.append(key);continue
        ra=main_bank[sid][fid]["full"]["reference"];rb=replacement_bank[sid][fid]["full"]["reference"]
        actual=pb["weights"]-pa["weights"];reference=np.asarray(rb["weights"])-np.asarray(ra["weights"])
        error=tv(actual,reference);eta=ra["eta"]+rb["eta"]
        ids_a=main_bank[sid][fid]["available"][pa["available_reference_key"]].get("evidence_ids")
        ids_b=replacement_bank[sid][fid]["available"][pb["available_reference_key"]].get("evidence_ids")
        rows.append(dict(identity=key,response_error=error,response_error_interval=[max(0,error-eta),error+eta],
                         actual_change_tv=float(.5*np.abs(actual).sum()),reference_change_tv=float(.5*np.abs(reference).sum()),
                         zero_reference_change=bool(np.all(reference==0)),fallback_a=pa["fallback"],fallback_b=pb["fallback"],
                         both_raw_valid=pa["raw_valid"] and pb["raw_valid"],retrieved_logical_ids_unchanged=ids_a==ids_b))
    status="incomplete_no_confirmatory_analysis" if missing or nonterminal else ("synthetic_verification_only" if allow_synthetic else "completed_secondary_analysis")
    summaries={}
    if not missing and not nonterminal:
        sids=[a["scenario_id"] for a in assignments]
        strata=[main_bank[a["scenario_id"]][a["fund_id"]].get("r") for a in assignments]
        for arm in ("R1","R3","C-context"):
            values=[float(np.mean([r["response_error"] for r in rows if r["identity"][0]==sid and r["identity"][2]==arm])) for sid in sids]
            summary=dict(scenario_ids=sids,response_error_scenario_means=values,mean=float(np.mean(values)),independent_units=60)
            if None not in strata:
                summary["bootstrap95"]=stratified_bootstrap(values,strata)
            summaries[arm]=summary
    return dict(status=status,expected=360,rows=rows,missing=missing,nonterminal=nonterminal,
                scenario_summaries=summaries,zero_reference_change_retained=True,source_hashes=code_provenance())


def evaluate_negative_control(records,reference_bank,scenario_ids,*,frozen_model_sha256,allow_synthetic=False):
    labels=tuple(f"N{i:02d}" for i in range(1,5));arms=("R1","R3","C-context")
    indexed=index_records(records,"negative-control")
    expected=set(itertools.product(scenario_ids,labels,arms,(1,2)))
    if len(scenario_ids)!=8 or len(expected)!=192:raise ValueError("Require eight fixed negative-control scenarios")
    if set(indexed)-expected:raise ValueError("Unregistered negative-control trajectory")
    missing=sorted(expected-set(indexed));nonterminal=[];rows=[]
    for sid in scenario_ids:
        for arm in arms:
            canonical=reference_bank[sid][labels[0]]
            for label in labels[1:]:
                other=reference_bank[sid][label]
                for key in ("h","Sigma","A","b"):
                    if _hash_object(canonical.get(key))!=_hash_object(other.get(key)):
                        raise ValueError("Negative-control profiles differ beyond label")
                if _hash_object(canonical["full"]["mu"])!=_hash_object(other["full"]["mu"]) or _hash_object(canonical["full"]["reference"]["weights"])!=_hash_object(other["full"]["reference"]["weights"]):
                    raise ValueError("Negative controls must reuse one canonical reference")
                for key in ("mu","reference"):
                    if _hash_object(canonical["available"][arm][key])!=_hash_object(other["available"][arm][key]):
                        raise ValueError("Negative-control available information/reference differs across labels")
            for rep in (1,2):
                hashes=[indexed[(sid,label,arm,rep)].get("normalized_input_sha256") for label in labels if (sid,label,arm,rep) in indexed]
                if not allow_synthetic and hashes and (any(not h for h in hashes) or len(set(hashes))!=1):
                    raise ValueError("Negative-control normalized model-input hashes are absent or differ")
                ps={}
                for label in labels:
                    key=(sid,label,arm,rep)
                    if key not in indexed:continue
                    p=terminal_policy(indexed[key],reference_bank[sid][label],frozen_model_sha256=frozen_model_sha256,allow_synthetic=allow_synthetic)
                    if p["eligible"]:ps[label]=p
                    else:nonterminal.append(dict(identity=key,status=p["status"]))
                if len(ps)!=4:continue
                for i,j in itertools.combinations(labels,2):
                    ref=canonical["full"]["reference"]
                    row=pair_metrics(ps[i]["weights"],ps[j]["weights"],ref,ref)
                    mu=np.asarray(canonical["full"]["mu"])
                    row["mean_full_regret"]=float(np.mean([mu@(np.asarray(ref["weights"])-ps[label]["weights"]) for label in (i,j)]))
                    row["mean_full_regret_interval"]=np.mean([regret_bounds(mu,ps[label]["weights"],ref) for label in (i,j)],axis=0).tolist()
                    rows.append(dict(scenario=sid,arm=arm,replicate=rep,label_i=i,label_j=j,
                                     fallback_involved=ps[i]["fallback"] or ps[j]["fallback"],**row))
    status="incomplete_no_confirmatory_analysis" if missing or nonterminal else ("synthetic_verification_only" if allow_synthetic else "completed_secondary_analysis")
    summaries={}
    if not missing and not nonterminal:
        for arm in arms:
            scenario_rows=[]
            for sid in scenario_ids:
                subset=[r for r in rows if r["scenario"]==sid and r["arm"]==arm]
                scenario_rows.append(dict(scenario=sid,**{key:float(np.mean([r[key] for r in subset])) for key in ("D","G","E","A","mean_full_regret")}))
            summaries[arm]=dict(scenarios=scenario_rows,independent_units=8,
                means={key:float(np.mean([r[key] for r in scenario_rows])) for key in ("D","G","E","A","mean_full_regret")})
    return dict(status=status,expected=192,rows=rows,missing=missing,nonterminal=nonterminal,
                scenario_summaries=summaries,
                interpretation="Observed distance measures label or generation variability; not by itself an economic error.",source_hashes=code_provenance())


def evaluate_actual_documents(records,profiles,*,frozen_model_sha256,source_catalog=None,allow_synthetic=False):
    """A/C mechanical/source trace audit; deliberately no numerical weight gold.

    profiles[module][fund_id] supplies h/Sigma/A/b. source_catalog[evidence_id]
    may supply fund_id, publication_date, value, unit, date, source_url. Literal
    mismatches are sent for semantic review, not declared economic errors.
    """
    indexed=index_records(records,"actual-documents")
    expected=set(itertools.product(("A","C"),FUNDS,ARMS,(1,2)))
    if set(indexed)-expected:raise ValueError("Unregistered A/C trajectory")
    missing=sorted(expected-set(indexed));nonterminal=[];rows=[];facts=[]
    catalog=source_catalog or {}
    for key in sorted(expected & set(indexed)):
        module,fid,arm,rep=key
        p=terminal_policy(indexed[key],profiles[module][fid],frozen_model_sha256=frozen_model_sha256,allow_synthetic=allow_synthetic)
        if not p["eligible"]:nonterminal.append(dict(identity=key,status=p["status"]));continue
        trace,_=load_trace(indexed[key],allow_synthetic=allow_synthetic)
        cutoff={"A":"2026-03-31","C":"2026-06-30"}[module]
        for stage in trace.get("stages",[]):
            output=stage.get("raw_output")
            if not isinstance(output,dict):continue
            for cited in output.get("evidence",[]):
                eid=cited.get("evidence_id");gold=catalog.get(eid)
                fact=dict(identity=key,stage=stage["stage"],evidence_id=eid,
                          exposed=eid in stage.get("exposed_evidence_ids",[]),
                          source_fact_scored=gold is not None)
                if gold is not None:
                    candidates=gold.get("facts")
                    if candidates:
                        comparisons=[{field:cited.get(field)==candidate[field] for field in ("value","unit","date") if field in candidate} for candidate in candidates]
                        exact=[i for i,c in enumerate(comparisons) if c and all(c.values())]
                        best=max(range(len(comparisons)),key=lambda i:sum(comparisons[i].values()))
                        field_matches=comparisons[exact[0] if exact else best]
                    else:
                        comparisons=[];exact=[]
                        field_matches={field:cited.get(field)==gold[field] for field in ("value","unit","date") if field in gold}
                    fact.update(source_url=gold.get("source_url"),
                        correct_fund_attribution=gold.get("fund_id") in (fid,"COMMON"),
                        publication_within_cutoff=bool(gold.get("publication_date") and gold["publication_date"]<=cutoff and (module!="C" or gold["publication_date"]>"2026-03-31")),
                        correct_period=gold.get("period",module)==module,
                        literal_field_matches=field_matches,
                        numeric_fact_scored=bool(candidates or "value" in gold),
                        matching_source_fact_indices=exact)
                    fact["requires_semantic_review"]=bool(gold.get("semantic_review_required")) or not all(field_matches.values()) or (bool(candidates) and not exact)
                else:fact["not_scored_reason"]="No independently grounded source fact record supplied"
                facts.append(fact)
        rows.append(dict(identity=key,status=p["status"],fallback=p["fallback"],raw_valid=p["raw_valid"],
                         validation=p["validation"],stage_diagnostics=p["stage_diagnostics"],
                         allocation_change_from_h_tv=tv(p["weights"],profiles[module][fid]["h"]),
                         actual_model_calls=p["actual_model_calls"],usage=p["usage"],source=p["source"]))
    status="incomplete_no_confirmatory_analysis" if missing or nonterminal else ("synthetic_verification_only" if allow_synthetic else "completed_actual_document_audit")
    return jsonable(dict(status=status,expected_trajectories=80,rows=rows,fact_checks=facts,missing=missing,
        nonterminal=nonterminal,exact_allocation_gold=False,regret_evaluation_applied=False,
        qualitative_text_converted_to_synthetic_signals=False,
        fact_scoring_coverage=(sum(f["source_fact_scored"] for f in facts)/len(facts)) if facts else None,
        semantic_direction_and_mandate_audit="Not inferred from numeric validity or literal source matching; retain reviewer annotations separately",
        source_hashes=code_provenance()))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("bundle",type=Path,help="JSON with records/reference_bank/frozen_scenarios/frozen_model_sha256")
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();bundle=json.loads(args.bundle.read_text(encoding="utf-8-sig"))
    result=evaluate_main(bundle["records"],bundle["reference_bank"],bundle["frozen_scenarios"],
                         frozen_model_sha256=bundle["frozen_model_sha256"])
    result["bundle_sha256"]=sha256(args.bundle)
    write_json(args.output,result)


if __name__=="__main__":main()
