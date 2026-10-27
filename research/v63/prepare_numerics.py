"""Generate immutable-to-model signal ledgers and offline synthetic QA only."""
from __future__ import annotations

import importlib.metadata
import json
import platform
import time
import traceback
import warnings
from pathlib import Path

import numpy as np

from research.v63.numerics import (
    ROOT, calibrate, generate_scenarios, replacement_signals, posterior,
    solve_reference, pair_metrics, write_json, sha256,
)


def main():
    started = time.perf_counter()
    out = ROOT / "data/v63_20261027/numerical"
    calibration = calibrate()
    write_json(out / "calibration.json", calibration)
    blocks = {}
    for block in ("development", "main", "negative_control"):
        signals, hidden = generate_scenarios(calibration, block)
        # These ledgers contain all funds, and must NEVER be model input files.
        write_json(out / "evaluator_only" / f"{block}_signals.json", signals)
        write_json(out / "evaluator_only" / f"{block}_latent_theta.json", hidden)
        blocks[block] = (signals, hidden)
    replacement = replacement_signals(calibration, *blocks["main"])
    write_json(out / "evaluator_only/replacement_signals.json", replacement)
    # Only synthetic numerical fixtures, never the actual four funds' h.
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence(81001)))
    profiles = rng.dirichlet(np.ones(12) * 3, size=4)
    fixtures = dict(role="synthetic numerical verification only; NOT actual fund holdings",
                    seed=81001, h=profiles, main_eligible=False)
    write_json(out / "synthetic_verification_profiles.json", fixtures)
    checks, references = [], []
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        for s in blocks["development"][0]:
            for j, h in enumerate(profiles):
                fid = f"F{j+1:02d}"
                evidence = [dict(evidence_id=f"{s['scenario_id']}-{fid}-x", signal_id=fid,
                                 indices=list(range(12)), values=s["private_signals"][fid], precision=s["r"])]
                post = posterior(calibration["m0"],calibration["V0"],s["y"],calibration["Omega0"],evidence)
                entry = dict(scenario_id=s["scenario_id"], fixture_id=f"synthetic-{j+1}", r=s["r"])
                try:
                    ref = solve_reference(post["mean"],h,calibration["Sigma"])
                    entry.update(status="passed", objective=ref["primal_objective"],
                                 primal_dual_gap=ref["primal_dual_gap"], eta=ref["eta"],
                                 independent_difference=ref["independent_objective_abs_difference"])
                    references.append(dict(**entry, mu=post["mean"], reference=ref))
                except Exception as exc:
                    entry.update(status="failed", error=f"{type(exc).__name__}: {exc}")
                checks.append(entry)
        warning_summary = sorted(set(str(w.message) for w in captured))
    # Deliberately degenerate cap: generic conic output cannot be silently accepted.
    try:
        boundary = solve_reference([1.,0.],[.5,.5],np.eye(2))
        boundary_result = dict(status="certified", result=boundary)
    except Exception as exc:
        boundary_result = dict(status="explicit_evaluator_failure_before_model_request",
                               error=f"{type(exc).__name__}: {exc}",
                               implication="Do not run any affected real profile until an independently certified boundary solver is available.")
    write_json(out / "synthetic_references.json", references)
    write_json(out / "verification.json", dict(
        role="offline numerical implementation verification; zero LLM calls; not B/A/C results",
        passed=sum(x["status"]=="passed" for x in checks), failed=sum(x["status"]=="failed" for x in checks),
        checks=checks, minimum_variance_boundary=boundary_result, warnings=warning_summary,
        elapsed_seconds=time.perf_counter()-started,
        actual_fund_holdings_available=False, main_reference_audit_complete=False,
        signal_preparation=dict(development=12,main=60,negative_control=8,replacement=60),
        no_main_execution=True,
        sources=["https://www.cvxpy.org/tutorial/solvers/index.html",
                 "https://scikit-learn.org/stable/modules/generated/sklearn.covariance.LedoitWolf.html",
                 calibration["source_url"]]))
    packages = ["numpy","scipy","cvxpy","clarabel","scikit-learn","pytest"]
    write_json(out / "environment.json",dict(python=platform.python_version(),
        executable="tmp/v63_numerics_venv/Scripts/python.exe",
        packages={p:importlib.metadata.version(p) for p in packages}))
    (ROOT / "research/v63/requirements-numerics.txt").write_text(
        "\n".join(f"{p}=={importlib.metadata.version(p)}" for p in packages)+"\n",encoding="utf-8")
    files = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "manifest.json")
    write_json(out / "manifest.json", dict(
        state="prepared signals and numerical QA, NOT experimental completion",
        protocol_sha256=sha256(ROOT / "plan/LIBERA_실험설정_v6.3_20261027.json"),
        files=[dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha256(p)) for p in files],
        all_fund_signal_and_latent_ledgers="evaluator_only; no model or retrieval access",
        pending=["audited actual fund profiles", "reference audit on those profiles", "human audit", "runtime/model freeze", "actual model requests"]))
    print(json.dumps(dict(passed=sum(x["status"]=="passed" for x in checks),
                          failed=sum(x["status"]=="failed" for x in checks),
                          elapsed_seconds=time.perf_counter()-started)))


if __name__ == "__main__":
    main()
