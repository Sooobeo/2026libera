"""Read-only final-run numerical audit; writes only this audit directory."""
import os
for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "1"
from collections import Counter
from datetime import datetime, timezone
import csv
import hashlib
import itertools
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import numpy as np
from research.v63.numerics import check_portfolio, jsonable
from research.v64_reduced.policy import normalize_and_check

RUN_ID = "b713cc4533c2f5b18e165f51592ca8f89223977fd1e15aee202adff8bbca6b54"
PHASE = ROOT / "data/v64_20261028/main_only_results/phases" / RUN_ID / "B-main"
OUT = Path(__file__).resolve().parent
CACHE = {}
DIGESTS = {}


def read(path):
    path = Path(path).resolve()
    if path not in CACHE:
        data = path.read_bytes()
        DIGESTS[path] = hashlib.sha256(data).hexdigest()
        CACHE[path] = json.loads(data.decode("utf-8-sig"))
    return CACHE[path]


def digest(path):
    path = Path(path).resolve()
    if path not in DIGESTS:
        DIGESTS[path] = hashlib.sha256(path.read_bytes()).hexdigest()
    return DIGESTS[path]


def canonical(value):
    return json.dumps(jsonable(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def tv(a, b):
    return float(np.abs(np.asarray(a) - np.asarray(b)).sum() / 2)


def csv_write(name, rows):
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()})


def stage_class(normalization):
    if normalization.get("postprocessed_valid"):
        return "raw_valid" if normalization["raw_valid"] else "normalized_rescue"
    return "fallback"


def main():
    analysis = read(PHASE / "analysis.json")
    measures = read(PHASE / "measurements.json")
    records = read(PHASE / "records.json")
    freeze = read(PHASE / "frozen_runtime.json")
    bank = read(PHASE / "evaluator_only/reference_bank.json")
    scenarios = read(PHASE / "evaluator_only/frozen_scenarios.json")
    package = read(PHASE / "prepared_inputs.json")
    assert analysis["status"] == "completed_descriptive_analysis"
    assert analysis["runtime_identity_sha256"] == RUN_ID
    assert measures["terminal_trajectories"] == len(records) == 160
    for path, expected in analysis["input_hashes"].items():
        if path.endswith("trace.json"):
            read(ROOT / path)
        assert digest(ROOT / path) == expected, path
    for path, expected in analysis["provenance"].items():
        assert digest(ROOT / path) == expected, path
    precision = {s["scenario_id"]: s["r"] for s in scenarios}
    diagnostics = {tuple(d["identity"]): d for d in analysis["trajectory_diagnostics"]}
    entries = {(e["block"], e["scenario"], e["fund_id"], e["arm"], e["replicate"]): e for e in package["entries"]}
    rows, call_rows = [], []
    effective = {}
    stage_vectors = {}
    final_failure = Counter()
    raw_failure = Counter()
    normalized_failure = Counter()
    all_stage_failure = Counter()
    for record in records:
        identity = tuple(record[k] for k in ("block", "scenario", "fund_id", "arm", "replicate"))
        assert entries[identity]["input_sha256"] == record["input_sha256"]
        trace = read(record["trace_path"])
        assert digest(record["trace_path"]) == record["trace_sha256"]
        assert not trace["engineering_only"]
        assert trace["status"] == record["trajectory_status"]
        sid, fid, arm = record["scenario"], record["fund_id"], record["arm"]
        profile = bank[sid][fid]
        h = np.asarray(profile["h"], float)
        check = lambda w: check_portfolio(w, h, profile["Sigma"], profile.get("A"), profile.get("b"))
        stages = {s["stage"]: s for s in trace["stages"]}
        assert set(stages) == {1, 2, 3}
        norms = {}
        raw = {}
        for st in (2, 3):
            raw[st] = np.asarray(stages[st]["raw_output"]["weights"], float)
            norms[st] = normalize_and_check(stages[st]["raw_output"]["weights"], profile["h"], check)
            assert canonical(norms[st]) == canonical(stages[st]["normalization"]), (identity, st)
            all_stage_failure[(st, norms[st]["failure_reason"] or "valid")] += 1
        w = np.asarray(norms[3]["effective_weights"])
        assert np.array_equal(w, trace["effective_weights"])
        assert bool(norms[3]["postprocessed_valid"]) == (trace["status"] == "completed")
        assert bool(norms[3]["raw_valid"]) == trace["raw_output_valid"]
        d = diagnostics[identity]
        assert bool(norms[3]["fallback"]) == d["fallback"]
        effective[(sid, fid, arm)] = w
        stage_vectors[(sid, fid, arm)] = np.asarray(norms[2]["effective_weights"])
        tools = [tool for stage in stages.values() for tool in stage.get("tools", [])]
        claims = [stages[st]["raw_output"].get("calculator_check", {}) for st in (2, 3)]
        full = profile["full"]
        regret = float(np.asarray(full["mu"]) @ (np.asarray(full["reference"]["weights"]) - w))
        h_regret = float(np.asarray(full["mu"]) @ (np.asarray(full["reference"]["weights"]) - h))
        final_failure[norms[3]["failure_reason"] or "valid"] += 1
        raw_failure.update(stages[3]["raw_weight_check"]["failures"])
        normalized_failure.update((norms[3].get("normalized_check") or {}).get("failures", []))
        row = dict(scenario=sid, r=precision[sid], fund=fid, arm=arm,
                   status=trace["status"], final_class=stage_class(norms[3]),
                   raw_valid=norms[3]["raw_valid"], rescued=norms[3]["postprocessed_valid"] and not norms[3]["raw_valid"],
                   policy_valid=norms[3]["postprocessed_valid"], fallback=norms[3]["fallback"],
                   final_failure_reason=norms[3]["failure_reason"],
                   raw_failure_flags=stages[3]["raw_weight_check"]["failures"],
                   normalized_failure_flags=(norms[3].get("normalized_check") or {}).get("failures", []),
                   final_raw_sum=float(raw[3].sum()), final_raw_minimum=float(raw[3].min()),
                   raw_equal_h_1e12=bool(np.max(np.abs(raw[3] - h)) <= 1e-12),
                   raw_equal_negative_h_1e12=bool(np.max(np.abs(raw[3] + h)) <= 1e-12),
                   raw_equal_h_exact=bool(np.array_equal(raw[3], h)),
                   raw_equal_negative_h_exact=bool(np.array_equal(raw[3], -h)),
                   effective_equal_h_1e12=bool(np.max(np.abs(w - h)) <= 1e-12),
                   effective_change_from_h_tv=tv(w, h), full_regret=regret, hold_h_full_regret=h_regret,
                   stage2_class=stage_class(norms[2]), stage2_valid=norms[2]["postprocessed_valid"],
                   stage2_failure_reason=norms[2]["failure_reason"],
                   stage2_raw_equal_h_1e12=bool(np.max(np.abs(raw[2] - h)) <= 1e-12),
                   stage2_raw_equal_negative_h_1e12=bool(np.max(np.abs(raw[2] + h)) <= 1e-12),
                   stage2_to3_effective_change_tv=tv(norms[2]["effective_weights"], w),
                   stage2_to3_raw_exactly_unchanged=bool(np.array_equal(raw[2], raw[3])),
                   actual_calculator_tool_calls=len(tools),
                   calculator_claimed_performed=sum(c.get("performed") is True for c in claims),
                   calculator_claimed_valid=sum(c.get("valid") is True for c in claims),
                   model_response_records=len(trace["calls"]),
                   unexposed_citation_candidate_count=len(d["unexposed_citation_candidates"]),
                   trace_path=str(Path(record["trace_path"]).relative_to(ROOT)))
        rows.append(row)
        for c in trace["calls"]:
            response = c.get("raw_response") or {}
            assert response.get("model_sha256") == freeze["model_sha256"]
            call_rows.append(dict(scenario=sid, fund=fid, arm=arm, stage=c["stage"], roundtrip=c["roundtrip"],
                                  status=c["status"], replayed=c.get("replayed", False), elapsed_seconds=c["elapsed_seconds"],
                                  **(response.get("usage") or {})))
    arms = ["R0", "R1", "R2", "R3"]
    funds = ["F01", "F02", "F03", "F04"]
    scenario_rows, pair_rows = [], []
    max_metric_discrepancy = 0.0
    for sid, arm in itertools.product(sorted(precision), arms):
        pairs = []
        for i, j in itertools.combinations(funds, 2):
            wi, wj = effective[(sid, i, arm)], effective[(sid, j, arm)]
            vi, vj = [np.asarray(bank[sid][f]["full"]["reference"]["weights"]) for f in (i, j)]
            D, Dstar = tv(wi, wj), tv(vi, vj)
            ri = next(x for x in rows if x["scenario"] == sid and x["fund"] == i and x["arm"] == arm)
            rj = next(x for x in rows if x["scenario"] == sid and x["fund"] == j and x["arm"] == arm)
            partition = "fallback" if ri["fallback"] or rj["fallback"] else ("raw_valid" if ri["raw_valid"] and rj["raw_valid"] else "normalized_rescue")
            pair = dict(scenario=sid, r=precision[sid], arm=arm, fund_i=i, fund_j=j,
                        D_full=D, Dstar_full=Dstar, G_full=Dstar-D, E_full=tv(wi-wj, vi-vj), A_full=abs(Dstar-D),
                        hold_h_D=tv(bank[sid][i]["h"], bank[sid][j]["h"]), partition=partition)
            pairs.append(pair)
            pair_rows.append(pair)
        matching = [x for x in rows if x["scenario"] == sid and x["arm"] == arm]
        computed = {name: float(np.mean([x[name] for x in pairs])) for name in ("D_full", "Dstar_full", "G_full", "E_full", "A_full", "hold_h_D")}
        computed.update(R_full=float(np.mean([x["full_regret"] for x in matching])),
                        hold_h_R_full=float(np.mean([x["hold_h_full_regret"] for x in matching])),
                        mean_change_from_h_tv=float(np.mean([x["effective_change_from_h_tv"] for x in matching])),
                        raw_valid_count=sum(x["raw_valid"] for x in matching), rescued_count=sum(x["rescued"] for x in matching),
                        fallback_count=sum(x["fallback"] for x in matching))
        original = next(x for x in analysis["per_scenario"] if x["scenario"] == sid and x["arm"] == arm)
        for name in ("D_full", "Dstar_full", "G_full", "E_full", "A_full", "R_full"):
            delta = abs(computed[name] - original[name])
            max_metric_discrepancy = max(max_metric_discrepancy, delta)
            assert delta < 1e-12, (sid, arm, name, delta)
        computed.update(G_numerical_lower=original["G_full_lower"], G_numerical_upper=original["G_full_upper"],
                        R_numerical_lower=original["R_full_lower"], R_numerical_upper=original["R_full_upper"])
        scenario_rows.append(dict(scenario=sid, r=precision[sid], arm=arm, **computed))

    def summarize(arm, r=None):
        selected = [x for x in rows if x["arm"] == arm and (r is None or x["r"] == r)]
        stats = [x for x in scenario_rows if x["arm"] == arm and (r is None or x["r"] == r)]
        pairs = [x for x in pair_rows if x["arm"] == arm and (r is None or x["r"] == r)]
        result = dict(arm=arm, r="all" if r is None else r, trajectories=len(selected), independent_scenarios=len(stats), pair_rows=len(pairs))
        for name in ("raw_valid", "rescued", "policy_valid", "fallback", "raw_equal_h_1e12", "raw_equal_negative_h_1e12", "effective_equal_h_1e12", "stage2_valid", "stage2_to3_raw_exactly_unchanged", "actual_calculator_tool_calls", "calculator_claimed_performed", "calculator_claimed_valid"):
            result[name] = sum(x[name] for x in selected)
        for name in ("D_full", "Dstar_full", "G_full", "E_full", "A_full", "R_full", "hold_h_D", "hold_h_R_full", "G_numerical_lower", "G_numerical_upper"):
            result[name] = float(np.mean([x[name] for x in stats]))
        result["R_full_monthly_percentage_points"] = result["R_full"] * 100
        result["mean_change_from_h_tv"] = float(np.mean([x["effective_change_from_h_tv"] for x in selected]))
        result["mean_stage2_to3_effective_change_tv"] = float(np.mean([x["stage2_to3_effective_change_tv"] for x in selected]))
        result["valid_to_invalid"] = sum(x["stage2_valid"] and not x["policy_valid"] for x in selected)
        result["invalid_to_valid"] = sum(not x["stage2_valid"] and x["policy_valid"] for x in selected)
        result["valid_to_valid"] = sum(x["stage2_valid"] and x["policy_valid"] for x in selected)
        result["invalid_to_invalid"] = sum(not x["stage2_valid"] and not x["policy_valid"] for x in selected)
        result["negative_weight_failures"] = sum(x["final_failure_reason"] == "negative_weights" for x in selected)
        result["normalized_constraint_failures"] = sum(x["final_failure_reason"] == "normalized_constraints_failed" for x in selected)
        result["equal_effective_pair_count_1e12"] = sum(x["D_full"] <= 1e-12 for x in pairs)
        result["G_positive_scenarios"] = sum(x["G_full"] > 0 for x in stats)
        result["G_numerical_interval_positive_scenarios"] = sum(x["G_numerical_lower"] > 0 for x in stats)
        for label in ("raw_valid", "normalized_rescue", "fallback"):
            partition = [x for x in pairs if x["partition"] == label]
            result["pair_count_" + label] = len(partition)
            result["G_contribution_" + label] = sum(x["G_full"] for x in partition) / len(pairs)
        return result

    arm_summary = [summarize(arm) for arm in arms]
    strata_summary = [summarize(arm, r) for r, arm in itertools.product((.5, 2.), arms)]
    contrasts = []
    for baseline, arm in itertools.combinations(arms, 2):
        row = dict(baseline=baseline, arm=arm, independent_matched_scenarios=10)
        for name in ("D_full", "G_full", "E_full", "A_full", "R_full"):
            ds = [next(x[name] for x in scenario_rows if x["scenario"] == sid and x["arm"] == arm) - next(x[name] for x in scenario_rows if x["scenario"] == sid and x["arm"] == baseline) for sid in sorted(precision)]
            row[name + "_mean_difference"] = float(np.mean(ds))
            row[name + "_increase_scenarios"] = sum(x > 1e-12 for x in ds)
            row[name + "_decrease_scenarios"] = sum(x < -1e-12 for x in ds)
            row[name + "_ties_1e12"] = sum(abs(x) <= 1e-12 for x in ds)
        contrasts.append(row)
    transitions = [dict(arm=arm, r=r, stage2_class=a, stage3_class=b, count=sum(x["arm"] == arm and (r == "all" or x["r"] == r) and x["stage2_class"] == a and x["final_class"] == b for x in rows)) for arm, r, a, b in itertools.product(arms, ("all", .5, 2.), ("raw_valid", "normalized_rescue", "fallback"), ("raw_valid", "normalized_rescue", "fallback"))]
    aggregate = {k: sum(x[k] for x in rows) for k in ("raw_valid", "rescued", "policy_valid", "fallback", "raw_equal_h_1e12", "raw_equal_negative_h_1e12", "raw_equal_h_exact", "raw_equal_negative_h_exact", "effective_equal_h_1e12", "stage2_valid", "actual_calculator_tool_calls", "calculator_claimed_performed", "calculator_claimed_valid", "model_response_records")}
    result = dict(schema="libera_completed_main_numeric_audit_v1", run_id=RUN_ID,
                  generated_at_utc=datetime.now(timezone.utc).isoformat(),
                  status="verified", original_data_mutated=False, model_generation_requests=0,
                  checks={"analysis_input_hashes_verified": len(analysis["input_hashes"]), "trace_hashes_verified": len(records), "normalization_receipts_recomputed": 320, "scenario_metric_cells_recomputed": 40, "max_metric_abs_difference": max_metric_discrepancy, "current_analysis_provenance_matches": True},
                  source_analysis={"path": str((PHASE / "analysis.json").relative_to(ROOT)), "sha256": digest(PHASE / "analysis.json")},
                  source_measurements=measures, aggregate=aggregate,
                  final_failure_counts=dict(final_failure), raw_failure_flags=dict(raw_failure), normalized_failure_flags=dict(normalized_failure),
                  stage_failure_counts=[{"stage": st, "reason": reason, "count": n} for (st, reason), n in sorted(all_stage_failure.items())],
                  arm_summary=arm_summary, stratum_arm_summary=strata_summary, matched_scenario_contrasts=contrasts,
                  definitions={"D": "Mean of 6 pairwise TV distances between effective fund portfolios within each scenario, then equal mean over scenarios.", "Dstar": "Analogous TV distance between full-information constrained reference portfolios.", "G": "Dstar-D; positive means less pairwise heterogeneity than reference, negative means more. Signed differences can cancel across scenarios.", "E": "Mean TV(w_i-w_j, v_i-v_j), directional discrepancy of between-fund allocation vectors; can exceed 1.", "A": "Mean absolute pair-level distance error |Dstar-D|, not absolute value of aggregate G.", "R": "Mean full-posterior expected MONTHLY return opportunity loss mu_full dot (v_full-w), in decimal return units. Multiply by100 for percentage points,10000 for basis points. Not observed realized return.", "G_numerical_interval": "Near-optimal-reference numerical range, not a sampling confidence interval.", "equality_counts": "Absolute elementwise maximum error <=1e-12 unless explicitly suffixed exact.", "stage_validity": "External proportional normalization plus original constraints, regardless of text stage status completed.", "raw_validity": "Original numeric checks before external normalization; not proof of semantic reasoning accuracy."},
                  method_notes=[
                      "Independent units are 10 synthetic scenarios,5 perprecision; fund/pair/stage rows are not additional independent samples. All160 terminal outcomes are included.",
                      "R0 has common information but no fund-specific signal; R1/R2/R3 receive the same retrieved own-fund signal first at stages1/2/3 and retain prior history.",
                      "The full-information numerical reference is an evaluator benchmark, not a FULL model arm. No different-model or no-GenAI comparator identifies a causal effect of shared-model adoption.",
                      "Precision r controls synthetic signal-error covariance V0/r and is not an observed forecasting hit rate. Different r strata use distinct draws; cross-stratum contrasts are descriptive.",
                      "Policy estimates are for model+externalnormalization+hold-h fallback; original model behavior is separately reported. Failure rates and contributions are not post-hoc exclusion criteria.",
                      "Reference intervals quantify allowed near-optimal portfolio ambiguity only. No p-values, resampling confidence intervals, or original N60 confirmatory tests are applied.",
                      "All480 recorded stage responses are present. Cost ledger483 includes3 uncertain dispatches; it does not mean483 usable observations. Cumulative wall time includes interruptions; last phase process duration is not total experiment duration.",
                      "No independent human audit is claimed. FF12 cannot determine all issuer, country, currency, ownership and transaction-level mandate rules.",
                      "Calculator claims are output text fields; actual tool use is counted from structured tools records.",
                  ])
    (OUT / "numeric_audit.json").write_text(json.dumps(jsonable(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, data in (("arm_summary.csv", arm_summary), ("stratum_arm_summary.csv", strata_summary), ("trajectory_audit.csv", rows), ("scenario_metrics.csv", scenario_rows), ("pair_metrics.csv", pair_rows), ("stage_transition_summary.csv", transitions), ("matched_scenario_contrasts.csv", contrasts), ("model_call_audit.csv", call_rows)):
        csv_write(name, data)
    print(json.dumps({"status": "verified", "aggregate": aggregate, "arm_summary": arm_summary, "stratum_arm_summary": strata_summary, "failure_counts": dict(final_failure)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
