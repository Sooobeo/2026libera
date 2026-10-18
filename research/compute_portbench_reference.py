"""Prepare public-FF12 transfer cases for PortBench v6 Appendix C.1 T5.

No model/API calls are made. This is an input/reference prototype, not a
replication of PortBench's original multi-asset dataset or an investment replay.

Run from the repository root:
    python research/compute_portbench_reference.py --self-check
    python research/compute_portbench_reference.py

Input: data/french/ff12_daily.json from prepare_public_inputs.py, with ISO dates,
ordered columns and decimal daily total returns. Output includes every selected
window's supplied mean/covariance, target weights and numerical diagnostics.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import scipy
from scipy.optimize import minimize


ROOT = Path(__file__).resolve().parents[1]
PAPER_URL = "https://arxiv.org/html/2605.27887v6"
COLUMNS = ["NoDur", "Durbl", "Manuf", "Enrgy", "Chems", "BusEq", "Telcm",
           "Utils", "Shops", "Hlth", "Money", "Other"]
LOOKBACK = 60
ANNUALIZATION = 252
RF = 0.04
# Numerical implementation settings, not empirical/paper-optimized constants.
SLSQP_FTOL = 1e-12
SLSQP_MAXITER = 2000
FEASIBILITY_TOL = 1e-8
KKT_TOL = 1e-7
RELATIVE_GAP_TOL = 1e-7


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sharpe(weights: np.ndarray, excess: np.ndarray, covariance: np.ndarray) -> float:
    variance = float(weights @ covariance @ weights)
    if variance <= 0:
        raise ValueError("Positive variance is required for the T5 ratio")
    return float(excess @ weights / math.sqrt(variance))


def weight_checks(weights: np.ndarray) -> dict[str, Any]:
    residual = abs(float(weights.sum()) - 1.0)
    minimum = float(weights.min())
    return {"sum": float(weights.sum()), "sum_residual": residual,
            "minimum": minimum,
            "long_only_sum_one_verified": residual <= FEASIBILITY_TOL
            and minimum >= -FEASIBILITY_TOL}


def convex_certificate(z: np.ndarray, q: np.ndarray, b: np.ndarray) -> dict[str, Any]:
    """Numerically check KKT and a feasible convex-QP dual lower bound.

    QP: min z'Qz, b'z=1, z>=0. With L=f-lambda(b'z-1)-nu'z,
    lambda=2f at the optimum; nu>=0. A dual feasible pair gives the
    lower bound lambda - (lambda*b+nu)'Q^-1(lambda*b+nu)/4.
    Floating point checks are not an exact-arithmetic certificate.
    """
    value = float(z @ q @ z)
    gradient = 2 * q @ z
    multiplier = 2 * value
    reduced = gradient - multiplier * b
    nonnegative_multiplier = np.maximum(reduced, 0.0)
    t = multiplier * b + nonnegative_multiplier
    dual = multiplier - float(t @ np.linalg.solve(q, t)) / 4
    scale = max(1.0, float(np.linalg.norm(gradient, ord=np.inf)),
                abs(multiplier) * float(np.linalg.norm(b, ord=np.inf)))
    eq = abs(float(b @ z) - 1)
    negative = max(0.0, -float(z.min()))
    dual_violation = max(0.0, -float(reduced.min())) / scale
    complementarity = float(np.max(np.abs(z * reduced))) / max(1.0, abs(value))
    relative_gap = (value - dual) / max(1.0, abs(value))
    verified = (eq <= FEASIBILITY_TOL and negative <= FEASIBILITY_TOL
                and dual_violation <= KKT_TOL and complementarity <= KKT_TOL
                and -RELATIVE_GAP_TOL <= relative_gap <= RELATIVE_GAP_TOL)
    return {"scaled_primal_objective": value, "scaled_dual_lower_bound": dual,
            "relative_primal_dual_gap": relative_gap,
            "equality_residual": eq, "negative_variable_residual": negative,
            "scaled_dual_violation": dual_violation,
            "scaled_complementarity_residual": complementarity,
            "kkt_and_gap_numerically_verified": verified,
            "certification_scope": "floating-point feasibility/KKT/duality checks; not formal exact arithmetic"}


def max_sharpe_reference(mu: np.ndarray, covariance: np.ndarray) -> dict[str, Any]:
    """Global reformulation for positive achievable excess; vertex otherwise.

    If a=mu-rf has a positive entry, a positive optimum is achievable. Scale
    a=s*b. Maximizing positive Sharpe is equivalent to min z'Qz with b'z=1,
    z>=0, where Q is covariance scaled by a positive scalar. Recover
    w=z/sum(z). This is a convex QP, so KKT suffices for global optimality.

    If a<=0, let m=min_i(-a_i/sd_i). The norm triangle inequality implies
    (-a)'w >= m*sum(w_i*sd_i) >= m*sd(w), so no mixture beats the vertex
    with maximum a_i/sd_i. Zero-excess cases are included.
    """
    n = len(mu)
    excess = mu - RF
    covariance = (covariance + covariance.T) / 2
    eigenvalues = np.linalg.eigvalsh(covariance)
    minimum_eigenvalue = float(eigenvalues.min())
    result: dict[str, Any] = {
        "annual_excess_means": excess.tolist(),
        "all_asset_excess_means_nonpositive": bool(np.all(excess <= 0)),
        "covariance_minimum_eigenvalue": minimum_eigenvalue,
        "covariance_positive_definite": minimum_eigenvalue > 0,
        "covariance_condition_number": float(eigenvalues.max() / minimum_eigenvalue)
        if minimum_eigenvalue > 0 else None,
    }
    fallback = np.full(n, 1 / n)
    if not np.all(np.isfinite(mu)) or not np.all(np.isfinite(covariance)):
        raise ValueError("Nonfinite mean/covariance")
    if minimum_eigenvalue <= 0:
        result.update(weights=fallback.tolist(), status="equal_weight_fallback",
                      fallback_reason="covariance is not positive definite; no shrinkage silently added",
                      reference_optimality_verified=False, solver_attempts=[])
        result["weight_checks"] = weight_checks(fallback)
        result["sharpe"] = sharpe(fallback, excess, covariance) if float(fallback @ covariance @ fallback) > 0 else None
        return result

    if np.all(excess <= 0):
        vertex_scores = excess / np.sqrt(np.diag(covariance))
        selected = int(np.argmax(vertex_scores))
        weights = np.zeros(n)
        weights[selected] = 1.0
        result.update(weights=weights.tolist(), sharpe=float(vertex_scores[selected]),
                      status="verified_nonpositive_excess_vertex",
                      reference_optimality_verified=True, selected_vertex=selected,
                      all_vertex_sharpes=vertex_scores.tolist(), solver_attempts=[],
                      verification="global norm triangle inequality for all a_i<=0")
        result["weight_checks"] = weight_checks(weights)
        return result

    qscale = float(np.max(np.diag(covariance)))
    ascale = float(np.max(np.abs(excess)))
    q = covariance / qscale
    b = excess / ascale
    positive = np.flatnonzero(b > 0)
    # A best-positive-Sharpe vertex is a deterministic feasible starting point.
    ranking = positive[np.argsort(-(excess[positive] / np.sqrt(np.diag(covariance)[positive])))]
    attempts = []
    best = None
    for index in ranking:
        initial = np.zeros(n)
        initial[index] = 1 / b[index]
        solved = minimize(
            lambda z: float(z @ q @ z), initial,
            jac=lambda z: 2 * q @ z,
            constraints=[{"type": "eq", "fun": lambda z: float(b @ z - 1),
                          "jac": lambda z: b}],
            bounds=[(0.0, None)] * n, method="SLSQP",
            options={"ftol": SLSQP_FTOL, "maxiter": SLSQP_MAXITER},
        )
        z = np.maximum(np.asarray(solved.x), 0.0)
        denominator = float(b @ z)
        if denominator <= 0 or not np.all(np.isfinite(z)):
            attempts.append({"starting_vertex": int(index), "success": bool(solved.success),
                             "message": str(solved.message), "numerically_verified": False})
            continue
        z = z / denominator
        # Polish the discovered active set by its equality-constrained solution.
        # Accept only after full (including inactive coordinates) KKT verification.
        support = np.flatnonzero(z > 1e-9 * max(1.0, float(z.max())))
        if len(support):
            try:
                candidate_active = np.linalg.solve(q[np.ix_(support, support)], b[support])
                normalization = float(b[support] @ candidate_active)
                if normalization > 0 and np.all(candidate_active >= 0):
                    polished = np.zeros(n)
                    polished[support] = candidate_active / normalization
                    if convex_certificate(polished, q, b)["kkt_and_gap_numerically_verified"]:
                        z = polished
            except np.linalg.LinAlgError:
                pass
        certificate = convex_certificate(z, q, b)
        weights = z / float(z.sum())
        checks = weight_checks(weights)
        verified = (bool(solved.success) and certificate["kkt_and_gap_numerically_verified"]
                    and checks["long_only_sum_one_verified"])
        attempts.append({"starting_vertex": int(index), "success": bool(solved.success),
                         "message": str(solved.message), "iterations": int(solved.nit),
                         "numerically_verified": verified})
        if verified:
            best = (weights, certificate, checks)
            break
    result["solver_attempts"] = attempts
    result["positive_excess_scaling"] = ascale
    result["covariance_scaling"] = qscale
    if best is None:
        result.update(weights=fallback.tolist(), sharpe=sharpe(fallback, excess, covariance),
                      status="equal_weight_fallback", reference_optimality_verified=False,
                      fallback_reason="no converged SLSQP result passed primal/dual/KKT checks",
                      weight_checks=weight_checks(fallback))
    else:
        weights, certificate, checks = best
        result.update(weights=weights.tolist(), sharpe=sharpe(weights, excess, covariance),
                      status="verified_positive_excess_convex_qp",
                      reference_optimality_verified=True, weight_checks=checks,
                      convex_certificate=certificate)
    return result


def score_t5_response(response: Any, target: list[float], columns: list[str]) -> dict[str, Any]:
    """T5 cosine on an explicit JSON weight vector; missing/unparseable -> zero.

    Accept a vector, an asset-keyed mapping, or {"weights": vector/mapping}.
    Do not normalize, repair, or replace proposed weights. Feasibility is reported
    separately because Appendix C.1 does not specify an extra infeasibility
    penalty for a parseable vector. Negative raw cosines remain visible; handling
    such invalid parseable answers must be frozen before an actual LLM study.
    """
    try:
        parsed = json.loads(response) if isinstance(response, str) else response
        if isinstance(parsed, dict) and "weights" in parsed:
            parsed = parsed["weights"]
        if isinstance(parsed, dict):
            if set(parsed) != set(columns):
                raise ValueError("asset keys must match")
            parsed = [parsed[key] for key in columns]
        if not isinstance(parsed, (list, tuple)) or len(parsed) != len(target):
            raise ValueError("weight length mismatch")
        if any(isinstance(value, bool) or not isinstance(value, (float, int)) for value in parsed):
            raise ValueError("weights must be JSON numbers")
        weights = np.asarray(parsed, dtype=float)
        reference = np.asarray(target, dtype=float)
        if not np.all(np.isfinite(weights)) or np.linalg.norm(weights) == 0:
            raise ValueError("weights must be finite and nonzero")
        cosine = float(weights @ reference / (np.linalg.norm(weights) * np.linalg.norm(reference)))
        # Roundoff-only clipping to the mathematical cosine range.
        cosine = max(-1.0, min(1.0, cosine))
        return {"parseable": True, "score": cosine, "weight_checks": weight_checks(weights),
                "extra_constraint_penalty_applied": False}
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return {"parseable": False, "score": 0.0, "reason": str(exc)}


def self_check() -> dict[str, Any]:
    q = np.diag([0.04, 0.09, 0.16])
    excess = np.array([0.08, 0.12, 0.04])
    expected = np.linalg.solve(q, excess)
    expected /= expected.sum()
    solved = max_sharpe_reference(excess + RF, q)
    assert solved["reference_optimality_verified"]
    assert np.allclose(solved["weights"], expected, atol=1e-7)
    binding = max_sharpe_reference(np.array([0.14, -0.06, -0.16]), q)
    assert binding["reference_optimality_verified"]
    assert np.allclose(binding["weights"], [1, 0, 0], atol=1e-7)
    nonpositive = max_sharpe_reference(np.array([0.01, -0.01, -0.03]), q)
    assert nonpositive["status"] == "verified_nonpositive_excess_vertex"
    assert np.argmax(nonpositive["weights"]) == 0
    zero = max_sharpe_reference(np.array([RF, 0.01, -0.03]), q)
    assert zero["sharpe"] == 0
    bad_covariance = max_sharpe_reference(np.array([0.1, 0.2, 0.3]), np.zeros((3, 3)))
    assert bad_covariance["status"] == "equal_weight_fallback"
    assert not bad_covariance["reference_optimality_verified"]
    assert score_t5_response("not JSON", [1, 0, 0], ["a", "b", "c"])["score"] == 0
    assert score_t5_response({"weights": [1, 0, 0]}, [1, 0, 0], ["a", "b", "c"])["score"] == 1
    return {"status": "passed", "checks": ["analytic diagonal positive optimum",
            "binding long-only optimum", "nonpositive excess global vertex",
            "zero excess optimum", "non-SPD failure is not called oracle",
            "unparseable response scores zero", "target cosine equals one"]}


def month_sequence(start: str, end: str) -> list[str]:
    first = datetime.strptime(start, "%Y-%m")
    last = datetime.strptime(end, "%Y-%m")
    if first > last:
        raise ValueError("start month follows end month")
    months = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=ROOT / "data/french/ff12_daily.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/reference_portbench")
    parser.add_argument("--start-month", default="2015-01")
    parser.add_argument("--end-month", default="2025-12")
    parser.add_argument("--self-check", action="store_true", help="run analytic checks only, without input data")
    args = parser.parse_args()
    checked = self_check()
    if args.self_check:
        print(json.dumps(checked, ensure_ascii=False, indent=2))
        return
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    dates, columns = payload["dates"], payload["columns"]
    if columns != COLUMNS or payload["units"] != "decimal_daily_return":
        raise ValueError("Expected the agreed FF12 columns and decimal_daily_return units")
    if not dates or dates != sorted(set(dates)):
        raise ValueError("Input dates must be nonempty, sorted and unique")
    for date in dates:
        datetime.strptime(date, "%Y-%m-%d")
    returns = np.asarray(payload["returns"], dtype=float)
    if returns.shape != (len(dates), len(columns)):
        raise ValueError("Input return matrix shape mismatch")
    monthly_last = {date[:7]: index for index, date in enumerate(dates)}
    months = month_sequence(args.start_month, args.end_month)
    cases = []
    for month in months:
        if month not in monthly_last:
            raise ValueError(f"Missing decision month: {month}")
        last_index = monthly_last[month]
        first_index = last_index - LOOKBACK + 1
        if first_index < 0:
            raise ValueError(f"Insufficient prehistory for {month}: need {LOOKBACK} returns")
        daily = returns[first_index:last_index + 1]
        if not np.all(np.isfinite(daily)):
            raise ValueError(f"Missing/nonfinite return in {month}; no filling or window extension")
        mu = ANNUALIZATION * daily.mean(axis=0)
        covariance = ANNUALIZATION * np.cov(daily, rowvar=False, ddof=1)
        reference = max_sharpe_reference(mu, covariance)
        cases.append({"case_id": f"FF12_T5_{month}", "decision_date": dates[last_index],
                      "month": month, "lookback_start": dates[first_index],
                      "lookback_end": dates[last_index], "lookback_dates": dates[first_index:last_index + 1],
                      "lookback_observations": len(daily), "annual_mean": mu.tolist(),
                      "annual_sample_covariance": covariance.tolist(),
                      "annual_risk_free_rate": RF, "reference": reference})
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / payload.get("source_manifest", "data/french/manifest.json")
    source_manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    created = datetime.now(timezone.utc).isoformat()
    common = {
        "schema_version": "1.0", "created_at_utc": created,
        "status": "preselection_data_and_reference_prototype_no_llm_runs",
        "paper": {"title": "PortBench", "version": "v6 2026-10-09", "url": PAPER_URL,
                  "sections": ["Appendix C.1 T5", "Appendix B.2 annualization"]},
        "scope": "FF12 transfer of T5 objective/scoring; not original PortBench data reproduction, backtest, actual tradable assets, or evidence of LLM performance",
        "columns": columns,
        "provenance_labels": {
            "direct_paper_conditions": ["long-only fully invested maximum Sharpe", "60-return lookback", "4 percent annual risk-free rate", "cosine scoring; missing/unparseable answers zero", "equal-weight fallback if numerical optimization fails"],
            "reported_annualization_convention": "252, Appendix B.2 covariance baselines; applied to both mean and covariance",
            "estimation_implementation": "arithmetic sample mean and unbiased sample covariance ddof=1; numerical convention is explicit, not an additional optimized paper constant",
            "new_transfer_choices": ["public FF12 value-weighted dividend-inclusive daily returns replace original multi-asset data", "one case at each month-end 2015-01 through 2025-12; 132 is a calendar count, not power/sample-size recommendation"],
            "derived_solver": "positive-excess convex reformulation and all-nonpositive-excess vertex theorem preserve T5 objective; not the original authors' optimization implementation",
            "implementation_only": "SLSQP settings, numerical tolerances, active-set polishing and provenance hashes are implementation verification choices, not paper-recommended empirical parameters",
        },
        "inputs": {"path": str(args.input.resolve()), "sha256": sha256(args.input),
                   "date_first": dates[0], "date_last": dates[-1], "source_id": payload.get("source_id"),
                   "source_header": payload.get("source_header"),
                   "source_manifest_path": str(manifest_path.resolve()),
                   "source_manifest_sha256": sha256(manifest_path) if manifest_path.exists() else None,
                   "source_manifest": source_manifest},
        "configuration": {"lookback": LOOKBACK, "annualization": ANNUALIZATION, "sample_covariance_ddof": 1,
                          "annual_risk_free_rate": RF, "month_start": args.start_month,
                          "month_end": args.end_month, "window_includes_decision_close": True,
                          "no_future_returns_used": True, "covariance_shrinkage": False,
                          "turnover_cap": None, "transaction_cost_objective": False,
                          "slsqp_ftol": SLSQP_FTOL, "slsqp_maxiter": SLSQP_MAXITER,
                          "feasibility_tolerance": FEASIBILITY_TOL, "kkt_tolerance": KKT_TOL,
                          "relative_gap_tolerance": RELATIVE_GAP_TOL},
        "software": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
                     "script_path": str(Path(__file__).resolve()), "script_sha256": sha256(Path(__file__))},
        "self_check": checked,
        "scoring_contract": {"helper": "score_t5_response", "score": "cosine of explicit JSON weight vector and target; unparseable/missing zero",
                             "feasibility": "separate check, no undocumented additional scoring penalty",
                             "parseable_invalid_answers": "raw cosine retained; exact policy for negative/otherwise invalid parseable answers must be frozen before LLM evaluation",
                             "model_outputs_created": False},
    }
    full = {**common, "case_count": len(cases), "cases": cases}
    full_path = args.output_dir / "ff12_t5_references.json"
    full_path.write_text(json.dumps(full, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    negative = [case["decision_date"] for case in cases
                if case["reference"]["all_asset_excess_means_nonpositive"]]
    fallback_dates = [case["decision_date"] for case in cases
                      if not case["reference"]["reference_optimality_verified"]]
    certificates = [case["reference"]["convex_certificate"] for case in cases
                    if "convex_certificate" in case["reference"]]
    summary = {**{key: common[key] for key in ("schema_version", "created_at_utc", "status", "scope", "paper")},
               "case_count": len(cases), "first_decision_date": cases[0]["decision_date"],
               "last_decision_date": cases[-1]["decision_date"],
               "status_counts": dict(Counter(case["reference"]["status"] for case in cases)),
               "verified_reference_count": len(cases) - len(fallback_dates),
               "equal_weight_fallback_dates": fallback_dates,
               "fallback_warning": "Equal-weight fallback is the published failure policy, not a verified optimum",
               "all_nonpositive_excess_dates": negative,
               "maximum_sum_residual": max(case["reference"]["weight_checks"]["sum_residual"] for case in cases),
               "minimum_weight": min(case["reference"]["weight_checks"]["minimum"] for case in cases),
               "minimum_covariance_eigenvalue": min(case["reference"]["covariance_minimum_eigenvalue"] for case in cases),
               "maximum_convex_relative_gap": max((abs(item["relative_primal_dual_gap"]) for item in certificates), default=None),
               "maximum_scaled_kkt_dual_violation": max((item["scaled_dual_violation"] for item in certificates), default=None),
               "maximum_scaled_kkt_complementarity": max((item["scaled_complementarity_residual"] for item in certificates), default=None),
               "self_check": checked, "llm_runs": 0,
               "reference_file": full_path.name, "reference_file_sha256": sha256(full_path)}
    (args.output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with (args.output_dir / "weights.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["case_id", "decision_date", "lookback_start", "status", "verified", "annual_sharpe", *columns])
        for case in cases:
            item = case["reference"]
            writer.writerow([case["case_id"], case["decision_date"], case["lookback_start"], item["status"],
                             item["reference_optimality_verified"], item["sharpe"], *item["weights"]])
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
