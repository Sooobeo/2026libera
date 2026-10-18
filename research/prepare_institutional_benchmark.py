"""Prepare LIBERA's institution-mandate benchmark without executing an AI model.

Salcher et al. (2026), Section 3.2, Eq. (6), supplies the full-investment
quadratic objective and gamma=1,3,5.  We add the nonnegative-weight constraint
used, for a different objective, in PortBench v6 Appendix C.1 T5.  This is an
explicit LIBERA combination, not a replication of either complete experiment.
Only the 625 existing training-moment records are read into the output cases;
future test data and the old unrestricted optimal weights are not copied.

The reference solver is a primal active-set quadratic-program solver.  It
solves the equality-constrained problem on each candidate face and checks the
global KKT conditions.  Positive-definite covariance gives strict concavity
and uniqueness.  A separate SLSQP solve is an implementation cross-check.
These are float64 numerical certificates, not exact-arithmetic proofs.

Run from the project root:
  python research/prepare_institutional_benchmark.py prepare
  python research/prepare_institutional_benchmark.py evaluate \
    --case-id INST-W0001-G1 --response-file response.json
The response file contains {"weights": [12 numeric weights]}.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import platform
from typing import Any

import numpy as np
import scipy
from scipy.optimize import minimize


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data/french/salcher_quadratic_empirical_references.json"
DEFAULT_OUTPUT = ROOT / "data/institutional"
GAMMAS = (1, 3, 5)
PAIRS = ((1, 3), (1, 5), (3, 5))
EPS = np.finfo(np.float64).eps
NUMERICAL_FACTOR = 2048
# Shared with the workflow runner; parsing/serialization engineering allowance,
# not a portfolio constraint chosen from an experiment or a paper effect size.
RESPONSE_SUM_TOLERANCE = 1e-6


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ArithmeticError(message)


def utility(w: np.ndarray, mu: np.ndarray, cov: np.ndarray, gamma: int) -> float:
    return float(mu @ w - gamma / 2 * (w @ cov @ w))


def precision_bounds(mu: np.ndarray, cov: np.ndarray, gamma: int, w: np.ndarray) -> tuple[float, float]:
    """Machine-precision checks only; these are not effect or sample cutoffs."""
    primal = NUMERICAL_FACTOR * EPS * len(mu) * max(1.0, float(np.linalg.norm(w, ord=1)))
    scale = max(
        np.finfo(float).tiny,
        float(np.linalg.norm(mu, ord=np.inf)),
        gamma * float(np.linalg.norm(cov, ord=np.inf)) * max(1.0, float(np.linalg.norm(w, ord=1))),
    )
    dual = NUMERICAL_FACTOR * EPS * len(mu) * scale
    return float(primal), float(dual)


def kkt_certificate(w: np.ndarray, mu: np.ndarray, cov: np.ndarray, gamma: int) -> dict[str, Any]:
    gradient = mu - gamma * (cov @ w)
    active = np.flatnonzero(w > 0)
    primal_tol, dual_tol = precision_bounds(mu, cov, gamma, w)
    if not len(active):
        return {"passed": False, "reason": "empty support"}
    multiplier = float(np.mean(gradient[active]))
    inactive = np.flatnonzero(w == 0)
    equality = abs(float(w.sum()) - 1)
    lower = max(0.0, -float(w.min()))
    stationarity = float(np.max(np.abs(gradient[active] - multiplier)))
    inactive_violation = max(0.0, float(np.max(gradient[inactive] - multiplier))) if len(inactive) else 0.0
    complementarity = float(np.max(np.abs(w * (multiplier - gradient))))
    raw_frank_wolfe_gap = float(np.max(gradient) - gradient @ w)
    passed = (
        np.all(np.isfinite(w)) and equality <= primal_tol and lower == 0
        and stationarity <= dual_tol and inactive_violation <= dual_tol
        and complementarity <= dual_tol
    )
    return {
        "passed": bool(passed),
        "equality_multiplier": multiplier,
        "weight_sum_residual": equality,
        "minimum_weight": float(w.min()),
        "active_stationarity_residual": stationarity,
        "inactive_dual_violation": inactive_violation,
        "complementarity_residual": complementarity,
        "raw_frank_wolfe_gap": raw_frank_wolfe_gap,
        "numerical_primal_tolerance": primal_tol,
        "numerical_dual_tolerance": dual_tol,
        "active_face_indices": active.tolist(),
        "scope": "Float64 KKT residual check for the globally concave simplex problem; not a formal exact-arithmetic certificate.",
    }


def solve_face(mu: np.ndarray, cov: np.ndarray, gamma: int, support: list[int]) -> np.ndarray:
    """Solve the restricted equality KKT system, without clipping its solution."""
    n, k = len(mu), len(support)
    result = np.zeros(n)
    if k == 1:
        result[support[0]] = 1.0
        return result
    matrix = np.zeros((k + 1, k + 1))
    matrix[:k, :k] = gamma * cov[np.ix_(support, support)]
    matrix[:k, k] = 1
    matrix[k, :k] = 1
    rhs = np.concatenate((mu[support], [1.0]))
    result[support] = np.linalg.solve(matrix, rhs)[:k]
    return result


def simplex_reference(mu: np.ndarray, cov: np.ndarray, gamma: int) -> tuple[np.ndarray, dict[str, Any]]:
    """Primal active-set solver: feasible boundary steps, face solves, dual entry."""
    n = len(mu)
    first = int(np.argmax(mu - gamma / 2 * np.diag(cov)))
    w = np.zeros(n)
    w[first] = 1
    support = [first]
    boundary_steps = 0
    additions = 0
    # Finite-state algorithm guard, not an experimental condition or statistic.
    for iteration in range(1, 5001):
        face = solve_face(mu, cov, gamma, support)
        negative = [i for i in support if face[i] < 0]
        if negative:
            ratios = [(float(w[i] / (w[i] - face[i])), i) for i in negative]
            alpha, blocker = min(ratios)
            require(0 <= alpha <= 1, "Active-set step left the feasible segment")
            w = w + alpha * (face - w)
            # The blocking bound is part of the QP algorithm, not a repair of
            # an AI answer or clipping of an unrestricted portfolio.
            w[blocker] = 0
            support.remove(blocker)
            primal_tol, _ = precision_bounds(mu, cov, gamma, w)
            for i in tuple(support):
                if w[i] < 0:
                    require(w[i] >= -primal_tol, "Reference boundary arithmetic infeasible")
                    w[i] = 0
                    support.remove(i)
            boundary_steps += 1
            continue
        w = face
        support = [i for i in support if w[i] > 0]
        gradient = mu - gamma * cov @ w
        multiplier = float(np.mean(gradient[support]))
        inactive = [i for i in range(n) if i not in support]
        _, dual_tol = precision_bounds(mu, cov, gamma, w)
        if inactive:
            entering = max(inactive, key=lambda i: gradient[i])
            if gradient[entering] > multiplier + dual_tol:
                support.append(entering)
                support.sort()
                additions += 1
                continue
        certificate = kkt_certificate(w, mu, cov, gamma)
        require(certificate["passed"], f"Reference KKT failed: {certificate}")
        certificate.update({
            "active_set_iterations": iteration,
            "boundary_steps": boundary_steps,
            "entering_constraints_released": additions,
            "face_solution_refined": True,
        })
        return w, certificate
    raise ArithmeticError("Reference active-set algorithm exceeded its numerical guard")


def slsqp_crosscheck(mu: np.ndarray, cov: np.ndarray, gamma: int, reference: np.ndarray) -> dict[str, Any]:
    n = len(mu)
    result = minimize(
        lambda w: -100 * utility(w, mu, cov, gamma),
        np.full(n, 1 / n),
        jac=lambda w: -100 * (mu - gamma * cov @ w),
        method="SLSQP",
        bounds=[(0.0, 1.0)] * n,
        constraints={"type": "eq", "fun": lambda w: float(w.sum() - 1), "jac": lambda w: np.ones(n)},
        options={"ftol": 1e-12, "maxiter": 1000},
    )
    return {
        "success": bool(result.success), "status": int(result.status), "iterations": int(result.nit),
        "message": str(result.message),
        "maximum_weight_difference_to_face_reference": float(np.max(np.abs(result.x - reference))),
        "utility_shortfall_to_face_reference": utility(reference, mu, cov, gamma) - utility(result.x, mu, cov, gamma),
        "independent_solver_only_not_the_reference_certificate": True,
    }


def validate_response(weights: Any, n: int, sum_tolerance: float = RESPONSE_SUM_TOLERANCE) -> np.ndarray:
    if not isinstance(weights, (list, tuple, np.ndarray)) or len(weights) != n:
        raise ValueError(f"Expected exactly {n} weights in the published industry order")
    if any(isinstance(x, (bool, str)) for x in weights):
        raise ValueError("Weights must be numeric; booleans and numeric strings are invalid")
    try:
        w = np.asarray(weights, dtype=float)
    except (TypeError, ValueError) as error:
        raise ValueError("Weights must be a numeric vector") from error
    if w.shape != (n,) or not np.all(np.isfinite(w)):
        raise ValueError("Weights must be a finite one-dimensional vector")
    if np.any(w < 0) or np.any(w > 1):
        raise ValueError("Invalid long-only weights: every raw weight must lie in [0,1]")
    if not np.isfinite(sum_tolerance) or not 0 <= sum_tolerance < 1:
        raise ValueError("Invalid engineering sum-one tolerance")
    if abs(float(w.sum()) - 1) > sum_tolerance:
        raise ValueError("Raw weights do not sum to one; no normalization or repair is applied")
    return w


def case_arrays(case: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, int, np.ndarray]:
    market = case["model_visible"]["public_market_data"]
    mu = np.asarray(market["mean_excess_return"], dtype=float)
    cov = np.asarray(market["sample_covariance_ddof_1"], dtype=float)
    gamma = int(case["model_visible"]["institution_mandate"]["gamma"])
    optimum = np.asarray(case["evaluator_only"]["reference_weights"], dtype=float)
    return mu, cov, gamma, optimum


def evaluate_weights(case: dict[str, Any], weights: Any, *, sum_tolerance: float = RESPONSE_SUM_TOLERANCE) -> dict[str, Any]:
    """Evaluate raw feasible weights; never normalize, clip or otherwise repair."""
    mu, cov, gamma, optimum = case_arrays(case)
    w = validate_response(weights, len(mu), sum_tolerance)
    reference_utility = utility(optimum, mu, cov, gamma)
    candidate_utility = utility(w, mu, cov, gamma)
    direct_loss = reference_utility - candidate_utility
    d = w - optimum
    gradient = mu - gamma * cov @ optimum
    quadratic_term = float(gamma / 2 * (d @ cov @ d))
    boundary_term = float(-gradient @ d)
    _, tolerance = precision_bounds(mu, cov, gamma, w)
    budget_residual = float(w.sum() - 1)
    multiplier = float(case["evaluator_only"]["numerical_KKT_certificate"]["equality_multiplier"])
    budget_objective_allowance = abs(multiplier * budget_residual) + tolerance
    require(direct_loss >= -budget_objective_allowance, "Candidate improves the reference beyond its budget-residual allowance")
    require(abs(direct_loss - quadratic_term - boundary_term) <= tolerance, "Constrained regret expansion failed")
    return {
        "case_id": case["case_id"], "valid": True,
        "raw_weights": w.tolist(), "raw_weight_sum": float(w.sum()),
        "raw_budget_residual_minus_one": budget_residual,
        "engineering_sum_tolerance": sum_tolerance,
        "budget_residual_objective_allowance": budget_objective_allowance,
        "negative_raw_regret_explained_by_allowed_budget_residual": bool(direct_loss < -tolerance and direct_loss >= -budget_objective_allowance),
        "candidate_training_utility": candidate_utility,
        "reference_training_utility": reference_utility,
        "utility_regret_direct": direct_loss,
        "total_variation_to_reference": float(np.abs(d).sum() / 2),
        "constrained_loss_expansion": {"quadratic_term": quadratic_term, "boundary_linear_term": boundary_term, "identity_residual": abs(direct_loss - quadratic_term - boundary_term), "numerical_tolerance": tolerance},
        "regret_not_clipped": True,
        "scope": "Supplied training-input objective; no future-return or AI-observation claim.",
    }


def evaluate_pair(case_i: dict[str, Any], case_j: dict[str, Any], weights_i: Any, weights_j: Any, *, sum_tolerance: float = RESPONSE_SUM_TOLERANCE) -> dict[str, Any]:
    if case_i["window_id"] != case_j["window_id"]:
        raise ValueError("Institution pairs must share the same market-data window")
    if case_i["case_id"] == case_j["case_id"]:
        raise ValueError("Institution pair must contain different mandates")
    _, _, gamma_i, star_i = case_arrays(case_i)
    _, _, gamma_j, star_j = case_arrays(case_j)
    w_i, w_j = validate_response(weights_i, len(star_i), sum_tolerance), validate_response(weights_j, len(star_j), sum_tolerance)
    target_delta, candidate_delta = star_i - star_j, w_i - w_j
    d_star = float(np.abs(target_delta).sum() / 2)
    d_observed = float(np.abs(candidate_delta).sum() / 2)
    return {
        "window_id": case_i["window_id"], "gammas": [gamma_i, gamma_j],
        "reference_distance_D_star": d_star,
        "candidate_distance_D": d_observed,
        "pair_response_error": float(np.abs(candidate_delta - target_delta).sum() / 2),
        "distance_reduction_G_descriptive": d_star - d_observed,
        "interpretation": "Positive G describes reduced distance; it alone is not a welfare loss or proof of harmful homogenization. Use response error and institution-specific utility regret together.",
    }


def pair_classification(w_i: np.ndarray, w_j: np.ndarray, mu: np.ndarray, cov: np.ndarray, gamma_i: int, gamma_j: int) -> dict[str, Any]:
    support_i, support_j = np.flatnonzero(w_i > 0), np.flatnonzero(w_j > 0)
    cross_i = kkt_certificate(w_i, mu, cov, gamma_j)
    cross_j = kkt_certificate(w_j, mu, cov, gamma_i)
    both_cross_pass = cross_i["passed"] and cross_j["passed"]
    same_vertex = (len(support_i) == len(support_j) == 1 and support_i[0] == support_j[0] and w_i[support_i[0]] == w_j[support_j[0]] == 1)
    if same_vertex:
        require(both_cross_pass, "Identical vertices failed mutual KKT")
        label = "same_vertex_mutual_KKT_verified"
    elif both_cross_pass and np.array_equal(w_i, w_j):
        label = "same_nonvertex_numerical_mutual_KKT"
    elif both_cross_pass:
        label = "unresolved_tiny_difference_both_cross_KKT_pass"
    else:
        label = "distinct_cross_KKT_rejects_shared_optimum"
    return {
        "classification": label,
        "distance_D_star": float(np.abs(w_i - w_j).sum() / 2),
        "same_vertex_index": int(support_i[0]) if same_vertex else None,
        "i_weights_satisfy_j_KKT": cross_i["passed"],
        "j_weights_satisfy_i_KKT": cross_j["passed"],
        "cross_inactive_dual_violations": [cross_i.get("inactive_dual_violation"), cross_j.get("inactive_dual_violation")],
        "cross_active_stationarity_residuals": [cross_i.get("active_stationarity_residual"), cross_j.get("active_stationarity_residual")],
        "no_experimental_distance_cutoff_used": True,
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for row in rows), encoding="utf-8")


def source_metadata() -> dict[str, Any]:
    author = "https://github.com/salcherlukas/Lost_in_Translation/blob/14c3a4c9567da966de5a4f7b9e5ef9ea6cff99fe"
    return {
        "salcher_paper": "https://onlinelibrary.wiley.com/doi/10.1002/for.70134",
        "salcher_locations": "Section 3.2 Eq.(6), full investment quadratic utility; Tables 2-5 gamma=1,3,5; Sections 4.1 and 6 monthly FF12 excess returns 1964-2023 and rolling 60/36-month windows.",
        "units_author_code": author + "/code/functions/data.R",
        "gamma_author_code": author + "/code/00_setup.R",
        "covariance_implementation_distinction": "Use the existing paper-text sample covariance (ddof=1), not the author's code-only 0.2 diagonal shrinkage mode.",
        "portbench_paper": "https://arxiv.org/html/2605.27887v6",
        "portbench_location": "Appendix C.1 T5 supplies long-only weights and sum-one constraints for a maximum-Sharpe objective. Only those feasible-set conditions are borrowed; its 4% rate, daily lookback, objective, scoring and fallback are not used.",
        "libera_extension": "A combination of Salcher quadratic utility with PortBench's long-only simplex, interpreted as three fictional equity-sector mandates. This is not a full replication, an estimate of actual institutions' preferences, or a private-forecast model.",
    }


def prepare(input_path: Path, output_dir: Path) -> dict[str, Any]:
    raw_bytes = input_path.read_bytes()
    source = json.loads(raw_bytes)
    dataset = source["summary"]["dataset"]
    require(dataset["units"] == "decimal_monthly_return", "Input units must be monthly decimal returns")
    columns = dataset["industries"]
    source_windows = source["windows"]
    require(len(source_windows) == 625 and len(columns) == 12, "Expected all 625 existing FF12 windows")
    cases, windows = [], []
    pair_stats = defaultdict(list)
    pair_counts = defaultdict(Counter)
    classifications = defaultdict(list)
    baseline_regrets = defaultdict(list)
    max_residuals = defaultdict(float)
    slsqp_differences, slsqp_gaps = [], []
    eigmins, conditions, active_iterations = [], [], []
    monotonic_checks = []
    total_slsqp_success = 0
    all_three_same_vertex = []
    all_three_numerically_same = []
    for source_window in source_windows:
        window_id = int(source_window["window_id"])
        forecast = source_window["training_forecast"]
        mu = np.asarray(forecast["mean_excess_return"], dtype=float)
        cov = np.asarray(forecast["sample_covariance_ddof_1"], dtype=float)
        require(mu.shape == (12,) and cov.shape == (12, 12) and np.all(np.isfinite(mu)) and np.all(np.isfinite(cov)), "Invalid moment dimensions/values")
        require(np.array_equal(cov, cov.T), "Input sample covariance must be symmetric")
        eig = np.linalg.eigvalsh(cov)
        require(eig[0] > 0, f"Window {window_id}: covariance not positive definite")
        np.linalg.cholesky(cov)
        eigmins.append(float(eig[0])); conditions.append(float(eig[-1] / eig[0]))
        market = {
            "training_window": source_window["training_window"],
            "industry_order": columns,
            "units": "decimal_monthly_excess_return",
            "mean_excess_return": mu.tolist(),
            "sample_covariance_ddof_1": cov.tolist(),
        }
        current = {}
        for gamma in GAMMAS:
            optimum, certificate = simplex_reference(mu, cov, gamma)
            crosscheck = slsqp_crosscheck(mu, cov, gamma, optimum)
            total_slsqp_success += int(crosscheck["success"])
            slsqp_differences.append(crosscheck["maximum_weight_difference_to_face_reference"])
            slsqp_gaps.append(crosscheck["utility_shortfall_to_face_reference"])
            active_iterations.append(certificate["active_set_iterations"])
            for field in ("weight_sum_residual", "active_stationarity_residual", "inactive_dual_violation", "complementarity_residual"):
                max_residuals[field] = max(max_residuals[field], certificate[field])
            current[gamma] = {
                "schema_version": "1.0", "case_id": f"INST-W{window_id:04d}-G{gamma}",
                "window_id": window_id,
                "model_visible": {
                    "public_market_data": market,
                    "institution_mandate": {
                        "gamma": gamma,
                        "objective": "Maximize mu.T @ w - gamma/2 * (w.T @ Sigma @ w).",
                        "constraints": "All 12 weights are nonnegative and sum to one. No cash, short positions, added costs, risk cap or extra weight cap.",
                        "scope": "Fictional institution's equity-sector allocation mandate; not an inferred preference of a real fund.",
                    },
                },
                "evaluator_only": {
                    "reference_weights": optimum.tolist(),
                    "reference_training_utility": utility(optimum, mu, cov, gamma),
                    "training_expected_excess_return": float(mu @ optimum),
                    "training_variance": float(optimum @ cov @ optimum),
                    "covariance_minimum_eigenvalue": float(eig[0]),
                    "unique_optimum_reason": "gamma>0 and positive-definite Sigma make the objective strictly concave on the nonempty convex simplex.",
                    "numerical_KKT_certificate": certificate,
                    "independent_SLSQP_crosscheck": crosscheck,
                },
            }
        equal_weight = np.full(12, 1 / 12)
        blind = np.asarray(current[3]["evaluator_only"]["reference_weights"])
        for gamma, case in current.items():
            optimum = case["evaluator_only"]["reference_weights"]
            oracle = evaluate_weights(case, optimum)
            require(oracle["utility_regret_direct"] == 0 and oracle["total_variation_to_reference"] == 0, "Oracle score not zero")
            diagnostics = {}
            for name, baseline in (("equal_weight", equal_weight), ("gamma_3_blind", blind)):
                score = evaluate_weights(case, baseline)
                diagnostics[name] = score
                baseline_regrets[(name, gamma)].append(score["utility_regret_direct"])
            if gamma == 3:
                require(diagnostics["gamma_3_blind"]["utility_regret_direct"] == 0, "gamma3 blind own-mandate loss not zero")
            case["evaluator_only"]["deterministic_baseline_diagnostics"] = diagnostics
            cases.append(case)
        pair_records = []
        for gamma_i, gamma_j in PAIRS:
            star_i = np.asarray(current[gamma_i]["evaluator_only"]["reference_weights"])
            star_j = np.asarray(current[gamma_j]["evaluator_only"]["reference_weights"])
            classification = pair_classification(star_i, star_j, mu, cov, gamma_i, gamma_j)
            key = f"{gamma_i}-{gamma_j}"
            pair_counts[key][classification["classification"]] += 1
            classifications[key].append({"window_id": window_id, **classification})
            pair_stats[key].append(classification["distance_D_star"])
            oracle_pair = evaluate_pair(current[gamma_i], current[gamma_j], star_i, star_j)
            blind_pair = evaluate_pair(current[gamma_i], current[gamma_j], blind, blind)
            require(oracle_pair["pair_response_error"] == oracle_pair["distance_reduction_G_descriptive"] == 0, "Oracle pair check")
            require(blind_pair["candidate_distance_D"] == 0, "Blind institution distance must be zero")
            require(blind_pair["pair_response_error"] == blind_pair["reference_distance_D_star"] == blind_pair["distance_reduction_G_descriptive"], "Blind pair expected identity")
            pair_records.append({"gammas": [gamma_i, gamma_j], **classification, "deterministic_gamma_3_blind_pair": blind_pair})
        labels = [r["classification"] for r in pair_records]
        if all(label == "same_vertex_mutual_KKT_verified" for label in labels):
            all_three_same_vertex.append(window_id)
        if all(label in ("same_vertex_mutual_KKT_verified", "same_nonvertex_numerical_mutual_KKT") for label in labels):
            all_three_numerically_same.append(window_id)
        variances = [current[g]["evaluator_only"]["training_variance"] for g in GAMMAS]
        means = [current[g]["evaluator_only"]["training_expected_excess_return"] for g in GAMMAS]
        _, monotonic_tol = precision_bounds(mu, cov, max(GAMMAS), np.ones(12) / 12)
        require(all(a >= b - monotonic_tol for a, b in zip(variances, variances[1:])), "Risk-aversion variance monotonicity failed")
        require(all(a >= b - monotonic_tol for a, b in zip(means, means[1:])), "Risk-aversion expected-return monotonicity failed")
        monotonic_checks.append(True)
        windows.append({
            "window_id": window_id, "public_market_data": market,
            "case_ids": [current[g]["case_id"] for g in GAMMAS],
            "pair_references_evaluator_only": pair_records,
        })
    require(len(cases) == 1875 and len(windows) == 625, "Coverage was lost")
    require(len({c["case_id"] for c in cases}) == len(cases), "Duplicate case ID")
    summary = {
        "schema_version": "1.0",
        "status": "prepared_numerically_KKT_verified_references_no_AI_experiment_run",
        "source": source_metadata(),
        "dataset": dataset,
        "training_window_months": 60, "window_count": len(windows), "gammas": list(GAMMAS), "case_count": len(cases),
        "coverage_rule": "All 625 existing Salcher empirical 60/36-eligible windows, without effect-based selection. Only their training moments enter this benchmark; future test moments, test dates and old unrestricted weights are excluded from output cases.",
        "training_window_coverage": {"first": windows[0]["public_market_data"]["training_window"], "last": windows[-1]["public_market_data"]["training_window"]},
        "not_independent_samples": "The 625 rolling windows overlap; 1875 mandate cases are not independent observations or a paper-backed sample-size/power recommendation.",
        "formula": {
            "utility": "U_gamma(w)=mu.T w-gamma/2*w.T Sigma w; w>=0, sum(w)=1.",
            "reference": "Unique maximizer of the supplied training-moment objective on the simplex.",
            "primary_utility_regret": "U_gamma(w_star)-U_gamma(w), evaluated directly without clipping.",
            "correct_constrained_expansion": "With d=w-w_star: regret=gamma/2*d.T Sigma d-gradient_U(w_star).T d. The boundary linear term is generally nonzero. The old unrestricted pure-quadratic loss identity is not used.",
            "reference_pair_distance": "D_star=.5*||w_i_star-w_j_star||_1",
            "pair_response_error": ".5*||(w_i-w_j)-(w_i_star-w_j_star)||_1",
            "distance_reduction_G": "G=D_star-.5*||w_i-w_j||_1; descriptive only, interpreted jointly with response error and utility regret.",
        },
        "pair_reference_summary": {key: {"windows": len(values), "mean_D_star": float(np.mean(values)), "median_D_star": float(np.median(values)), "minimum_D_star": float(np.min(values)), "maximum_D_star": float(np.max(values)), "classifications": dict(pair_counts[key]), "unresolved_window_ids": [r["window_id"] for r in classifications[key] if r["classification"].startswith("unresolved")]} for key, values in pair_stats.items()},
        "all_three_same_vertex": {"count": len(all_three_same_vertex), "window_ids": all_three_same_vertex},
        "all_three_numerically_same": {"count": len(all_three_numerically_same), "window_ids": all_three_numerically_same},
        "same_optimum_policy": "Classify identical vertices with mutual KKT as shared optima. Other pairs require mutual KKT; residual-small but unequal vectors are labeled unresolved, not declared identical by an arbitrary distance cutoff. Preserve all windows. D_star=0 gives no evidence that equal AI portfolios erase normative heterogeneity; distance ratios at zero are undefined.",
        "numerical_verification": {
            "all_1875_reference_KKT_checks_passed": True,
            "all_625_covariances_positive_definite": True,
            "minimum_covariance_eigenvalue": min(eigmins), "maximum_covariance_condition_number": max(conditions),
            "KKT_maximum_residuals": dict(max_residuals),
            "active_set_maximum_iterations": max(active_iterations),
            "independent_SLSQP_successes": total_slsqp_success,
            "independent_SLSQP_maximum_weight_difference": max(slsqp_differences),
            "independent_SLSQP_maximum_utility_shortfall": max(slsqp_gaps),
            "risk_aversion_return_and_variance_monotonicity_all_passed": all(monotonic_checks),
            "oracle_zero_scores_all_passed": True,
            "equal_weight_and_gamma3_blind_regret_nonnegative_to_machine_precision": True,
            "gamma3_blind_has_zero_candidate_pair_distance_and_response_error_equal_D_star": True,
            "precision_note": "Numerical feasibility and KKT tolerances are derived from float64 machine epsilon, dimension and input scale (factor 2048). SLSQP uses objective scale100, ftol1e-12,maxiter1000 as implementation checks, not paper-sourced experimental conditions. No AI response is normalized or repaired.",
            "formal_certification_limit": "Global uniqueness follows mathematically from positive-definite Sigma and gamma>0; this implementation checks its prerequisites and KKT numerically, not with interval or exact arithmetic.",
        },
        "deterministic_baselines": {f"{name}_gamma_{gamma}": {"cases": len(values), "mean_utility_regret": float(np.mean(values)), "minimum_utility_regret": float(np.min(values)), "maximum_utility_regret": float(np.max(values))} for (name, gamma), values in baseline_regrets.items()},
        "baseline_interpretation": "Oracle, equal weight and mandate-blind gamma3 are deterministic sanity checks, not observations of any AI model. gamma3 blind applies the gamma3 optimum to all three mandates, so its missing mandate response is known by construction.",
        "prompt_exposure": {
            "allowed": ["model_visible.public_market_data", "model_visible.institution_mandate only at the assigned onset stage and later"],
            "runner_only_never_serialize_to_model": ["case_id", "window_id", "evaluator_only", "reference_weights", "pair_references_evaluator_only"],
            "metadata_leak_warning": "case_id contains gamma. Institution labels must not reveal gamma before the assigned onset stage. The external solver's optimum, utility scores and pair classifications are never model inputs.",
            "workflow_scope": "R1/R4/FRESH packet construction, stage tasks and AI execution are prepared elsewhere. Before a mandate is revealed no unique institution-specific allocation objective is supplied; intermediate draft outputs have no institution-specific oracle score.",
        },
        "evaluation_policy": {"response_sum_one_absolute_tolerance": RESPONSE_SUM_TOLERANCE, "sum_tolerance_provenance": "LIBERA runner engineering allowance for response serialization; not a paper-sourced treatment condition. The raw budget residual is retained and scored without repair. A possible negative raw regret attributable to the small budget mismatch is explicitly flagged using the reference equality multiplier.", "raw_invalid_weights": "Reject missing, nonnumeric, nonfinite, negative, above-one or wrong-length vectors and weight sums outside the explicit engineering allowance; never normalize, clip or impute a portfolio.", "economic_scope": "Fictional institution-specific equity-sector mandates; not actual fund preference estimates, privileged institutional forecasts, game-theoretic strategic interaction or realized financial stability."},
        "first_window": {"window_id": windows[0]["window_id"], "training_window": windows[0]["public_market_data"]["training_window"], "references_by_gamma": {str(c["model_visible"]["institution_mandate"]["gamma"]): {"weights": c["evaluator_only"]["reference_weights"], "utility": c["evaluator_only"]["reference_training_utility"], "active_face": c["evaluator_only"]["numerical_KKT_certificate"]["active_face_indices"]} for c in cases[:3]}, "pairs": windows[0]["pair_references_evaluator_only"]},
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "cases.jsonl", cases)
    write_jsonl(output_dir / "windows.jsonl", windows)
    write_json(output_dir / "summary.json", summary)
    files = {}
    for name in ("cases.jsonl", "windows.jsonl", "summary.json"):
        path = output_dir / name
        files[name] = {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest = {
        "schema_version": "1.0", "status": summary["status"],
        "input": {"path": str(input_path.resolve()), "sha256": hashlib.sha256(raw_bytes).hexdigest(), "fields_read": ["summary.dataset", "windows[].window_id", "windows[].training_window", "windows[].training_forecast.mean_excess_return", "windows[].training_forecast.sample_covariance_ddof_1"]},
        "generator": "research/prepare_institutional_benchmark.py", "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "runtime": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "source": source_metadata(), "outputs": files,
        "reproduce": "python research/prepare_institutional_benchmark.py prepare",
        "external_AI_or_network_calls": 0,
    }
    write_json(output_dir / "manifest.json", manifest)
    return {"status": summary["status"], "windows": len(windows), "cases": len(cases), "all_KKT_passed": True, "pair_reference_summary": summary["pair_reference_summary"], "all_three_same_vertex_count": len(all_three_same_vertex), "AI_calls": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    prep.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--cases", type=Path, default=DEFAULT_OUTPUT / "cases.jsonl")
    evaluate.add_argument("--case-id", required=True)
    supplied = evaluate.add_mutually_exclusive_group(required=True)
    supplied.add_argument("--response-file", type=Path)
    supplied.add_argument("--weights-json")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.input, args.output_dir)
    else:
        case = None
        for line in args.cases.read_text(encoding="utf-8").splitlines():
            candidate = json.loads(line)
            if candidate["case_id"] == args.case_id:
                case = candidate
                break
        if case is None:
            parser.error(f"Unknown case ID {args.case_id}")
        try:
            if args.response_file:
                response = json.loads(args.response_file.read_text(encoding="utf-8"))
                weights = response["weights"]
            else:
                weights = json.loads(args.weights_json)
            result = evaluate_weights(case, weights)
        except (ValueError, KeyError, TypeError) as error:
            parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
