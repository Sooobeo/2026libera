"""Prepare the separate recent FF12 numerical control; never run an AI model.

This LIBERA adaptation combines PortBench v6's 2024--2025 QA test years
(not its dynamic-pipeline evaluation period or 60-trading-day lookback) with
Salcher et al.'s 60-month estimation window, quadratic objective, and gamma
values 1, 3, 5. Long-only full investment is borrowed separately from
PortBench C.1 T5. The result is a numerical auxiliary control, not the
documentary/strategic main experiment or a replication of either paper.

Each reference month indexes a retrospective task using preceding monthly
observations from today's revised data. It is NOT a reconstruction of the
information actually published at the beginning of that historical month.
There is no future-return evaluation or future block reservation.

Run: python research/prepare_recent_industry_control.py
Only data/institutional_recent is written. Existing core data and workflow
artifacts are neither replaced nor imported as execution pipelines.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import platform

import numpy as np
import scipy

from prepare_institutional_benchmark import (
    GAMMAS, PAIRS, NUMERICAL_FACTOR, RESPONSE_SUM_TOLERANCE,
    evaluate_pair, evaluate_weights, kkt_certificate, pair_classification,
    precision_bounds, require, simplex_reference, slsqp_crosscheck, utility,
    write_json, write_jsonl,
)


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/french/monthly_returns.json"
OUTPUT = ROOT / "data/institutional_recent"
EXPECTED_COLUMNS = ["NoDur", "Durbl", "Manuf", "Enrgy", "Chems", "BusEq",
                    "Telcm", "Utils", "Shops", "Hlth", "Money", "Other"]
LOOKBACK = 60
REFERENCE_MONTHS = [f"{year}-{month:02d}" for year in (2024, 2025) for month in range(1, 13)]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def month_index(label: str) -> int:
    year, month = map(int, label.split("-"))
    require(1 <= month <= 12, f"Invalid month {label}")
    return year * 12 + month - 1


def source_metadata() -> dict:
    return {
        "salcher": {
            "url": "https://onlinelibrary.wiley.com/doi/full/10.1002/for.70134",
            "locators": "Section 3.2 Eq.(6), Tables 1-5 quadratic gamma=1,3,5; Section 4.1 60-month means/covariances.",
            "adopted": "Monthly decimal excess returns, 60-month sample moments, quadratic utility and gamma values.",
            "not_adopted": "1964-2023 full period, future 36-month evaluation, unrestricted-short optimum, code-only covariance shrinkage.",
        },
        "portbench": {
            "url": "https://arxiv.org/html/2605.27887v6",
            "locators": "Appendix B.2 QA test years 2024-2025; Appendix C.1 T5 long-only full-investment feasible set.",
            "adopted": "2024-2025 QA evaluation-year range as the calendar precedent, and long-only sum-one feasibility.",
            "not_adopted": "Its dynamic 2024 normal-period backtest, 60-trading-day lookback, max-Sharpe objective, constant annual 4% risk-free rate, or scoring weights.",
        },
        "french": {
            "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html",
            "industry_construction": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_12_ind_port.html",
            "adopted": "Value-weighted monthly total returns for 12 industry baskets and date-matched monthly risk-free returns.",
            "limits": "Industry membership changes historically. Current revised CIZ vintage; not historical point-in-time releases or fixed constituent baskets.",
        },
        "provenance": "LIBERA_adaptation combining distinct paper conditions; not one published unified protocol.",
        "researcher_choices": "24 monthly reference tasks, no future evaluation, three fictional mandates, auxiliary-control role, deterministic numerical baselines.",
        "engineering_tolerances": "Float64/KKT tolerances, SLSQP convergence settings and response serialization tolerance are implementation choices, not paper-derived behavioral parameters.",
    }


def load_selected_input() -> tuple[dict, dict, np.ndarray, np.ndarray, np.ndarray]:
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    ff, rf = data["datasets"]["FF12"], data["risk_free"]
    require(ff["columns"] == EXPECTED_COLUMNS, "Unexpected FF12 order")
    require(ff["units"] == rf["units"] == "decimal_monthly_return", "Return unit mismatch")
    require(len(ff["dates"]) == len(ff["value_weighted_total_returns"]), "FF12 date/value length mismatch")
    require(len(rf["dates"]) == len(rf["values"]), "RF date/value length mismatch")
    require(len(set(ff["dates"])) == len(ff["dates"]), "Duplicate FF12 date")
    require(len(set(rf["dates"])) == len(rf["dates"]), "Duplicate RF date")
    rf_map = dict(zip(rf["dates"], rf["values"]))
    selected = [(d, r) for d, r in zip(ff["dates"], ff["value_weighted_total_returns"])
                if "2019-01" <= d <= "2025-11"]
    dates = [d for d, _ in selected]
    require(len(dates) == 83 and dates[0] == "2019-01" and dates[-1] == "2025-11", "Selected date coverage mismatch")
    require(all(month_index(b) - month_index(a) == 1 for a, b in zip(dates, dates[1:])), "Nonconsecutive monthly data")
    require(all(d in rf_map for d in dates), "Missing same-month RF observation")
    total = np.asarray([r for _, r in selected], dtype=float)
    require(rf["columns"] == ["RF"], "Unexpected risk-free column definition")
    risk_free_rows = np.asarray([rf_map[d] for d in dates], dtype=float)
    require(risk_free_rows.shape == (83, 1), "Unexpected source RF row dimensions")
    risk_free = risk_free_rows[:, 0]
    require(total.shape == (83, 12) and risk_free.shape == (83,), "Unexpected selected dimensions")
    require(np.all(np.isfinite(total)) and np.all(np.isfinite(risk_free)), "Missing/nonfinite selected input")
    excess = total - risk_free[:, None]
    selected_record = {
        "schema_version": "1.0", "status": "frozen_numerical_auxiliary_control_input_not_AI_results",
        "source_sha256": sha256(INPUT), "source_path": "data/french/monthly_returns.json",
        "industry_order": EXPECTED_COLUMNS, "dates": dates, "monthly_observations": 83,
        "total_return_units": "decimal_monthly_return", "excess_return_units": "decimal_monthly_excess_return",
        "value_weighted_total_returns": total.tolist(), "risk_free": risk_free.tolist(),
        "excess_returns": excess.tolist(), "excess_conversion": "FF12 total return minus RF for exactly the same calendar month, once; no annualization.",
        "ff12_source_header": ff["source_header"], "rf_source_header": rf["source_header"],
        "source_manifest": data.get("source_manifest"), "rf_definition": rf.get("definition"),
        "vintage_scope": "Current revised source frozen for this artifact; no reconstruction of historical publication dates. No future return enters any task.",
    }
    return data, selected_record, total, risk_free, excess


def prepare() -> dict:
    source, selected, total, risk_free, excess = load_selected_input()
    cases, windows = [], []
    pair_records = defaultdict(list)
    baseline_losses = defaultdict(list)
    max_residuals = defaultdict(float)
    slsqp_records, eigenvalues = [], []
    same_all, unresolved = [], []
    for index, reference_month in enumerate(REFERENCE_MONTHS):
        dates = selected["dates"][index:index + LOOKBACK]
        returns = excess[index:index + LOOKBACK]
        require(len(dates) == LOOKBACK and month_index(reference_month) - month_index(dates[-1]) == 1, "Lookback boundary mismatch")
        mu = returns.mean(axis=0)
        cov = np.cov(returns, rowvar=False, ddof=1)
        require(cov.shape == (12, 12) and np.array_equal(cov, cov.T), "Invalid covariance")
        eig = np.linalg.eigvalsh(cov)
        require(eig[0] > 0, f"Non-SPD covariance at {reference_month}")
        np.linalg.cholesky(cov)
        eigenvalues.append(eig)
        window_id = index + 1
        market = {
            "training_window": {"start": dates[0], "end": dates[-1], "months": LOOKBACK},
            "industry_order": EXPECTED_COLUMNS, "units": "decimal_monthly_excess_return",
            "mean_excess_return": mu.tolist(), "sample_covariance_ddof_1": cov.tolist(),
        }
        current = {}
        for gamma in GAMMAS:
            optimum, certificate = simplex_reference(mu, cov, gamma)
            crosscheck = slsqp_crosscheck(mu, cov, gamma, optimum)
            _, dual_tol = precision_bounds(mu, cov, gamma, optimum)
            require(crosscheck["success"], f"SLSQP failed at {reference_month}, gamma {gamma}")
            require(abs(crosscheck["utility_shortfall_to_face_reference"]) <= dual_tol,
                    f"SLSQP objective disagreement at {reference_month}, gamma {gamma}")
            crosscheck["absolute_objective_agreement_tolerance"] = dual_tol
            crosscheck["objective_agreement_passed"] = True
            slsqp_records.append(crosscheck)
            for field in ("weight_sum_residual", "active_stationarity_residual", "inactive_dual_violation", "complementarity_residual"):
                max_residuals[field] = max(max_residuals[field], certificate[field])
            case = {
                "schema_version": "1.0", "case_id": f"RECENT-CONTROL-W{window_id:02d}-G{gamma}",
                "window_id": window_id, "reference_month": reference_month,
                "role": "numerical_auxiliary_control_not_documentary_strategy_main",
                "model_visible": {
                    "public_market_data": market,
                    "institution_mandate": {
                        "gamma": gamma, "objective": "Maximize mu.T @ w - gamma/2 * (w.T @ Sigma @ w).",
                        "constraints": "All 12 weights are nonnegative and sum to one. No cash, short positions, transaction costs or extra industry cap.",
                        "scope": "Fictional explicit quantitative mandate, not an actual institution's inferred risk preference.",
                    },
                },
                "evaluator_only": {
                    "reference_weights": optimum.tolist(), "reference_training_utility": utility(optimum, mu, cov, gamma),
                    "training_expected_excess_return": float(mu @ optimum), "training_variance": float(optimum @ cov @ optimum),
                    "numerical_KKT_certificate": certificate, "independent_SLSQP_crosscheck": crosscheck,
                    "covariance_minimum_eigenvalue": float(eig[0]),
                },
            }
            zero = evaluate_weights(case, optimum)
            require(zero["utility_regret_direct"] == zero["total_variation_to_reference"] == 0, "Nonzero oracle self-score")
            current[gamma] = case
        blind = np.asarray(current[3]["evaluator_only"]["reference_weights"])
        for gamma, case in current.items():
            diagnostics = {}
            for name, weights in (("equal_weight", np.full(12, 1 / 12)), ("gamma_3_blind", blind)):
                score = evaluate_weights(case, weights)
                diagnostics[name] = score
                baseline_losses[(name, gamma)].append(score["utility_regret_direct"])
            case["evaluator_only"]["deterministic_baseline_diagnostics"] = diagnostics
            cases.append(case)
        pairs = []
        for ga, gb in PAIRS:
            wa, wb = [np.asarray(current[g]["evaluator_only"]["reference_weights"]) for g in (ga, gb)]
            classification = pair_classification(wa, wb, mu, cov, ga, gb)
            gold = evaluate_pair(current[ga], current[gb], wa, wb)
            blind_score = evaluate_pair(current[ga], current[gb], blind, blind)
            require(gold["pair_response_error"] == gold["distance_reduction_G_descriptive"] == 0, "Oracle pair mismatch")
            require(blind_score["candidate_distance_D"] == 0 and blind_score["pair_response_error"] == blind_score["reference_distance_D_star"], "Blind pair identity mismatch")
            record = {"gammas": [ga, gb], **classification, "gamma_3_blind_pair": blind_score}
            pairs.append(record)
            pair_records[f"{ga}-{gb}"].append(record)
            if classification["classification"].startswith("unresolved"):
                unresolved.append({"window_id": window_id, "gammas": [ga, gb]})
        if all(p["classification"].startswith("same_") for p in pairs):
            same_all.append(window_id)
        means = [current[g]["evaluator_only"]["training_expected_excess_return"] for g in GAMMAS]
        variances = [current[g]["evaluator_only"]["training_variance"] for g in GAMMAS]
        _, tol = precision_bounds(mu, cov, max(GAMMAS), np.full(12, 1 / 12))
        require(all(a >= b - tol for values in (means, variances) for a, b in zip(values, values[1:])), "Risk-aversion monotonicity failed")
        windows.append({"window_id": window_id, "reference_month": reference_month, "public_market_data": market,
                        "case_ids": [current[g]["case_id"] for g in GAMMAS], "pair_references_evaluator_only": pairs})
    require(len(cases) == 72 and len(windows) == 24, "Coverage loss")
    require(len({c["case_id"] for c in cases}) == 72, "Duplicate case ID")
    summary = {
        "schema_version": "1.0", "status": "prepared_verified_numerical_auxiliary_control_no_AI_results",
        "role": "numerical_auxiliary_control_not_documentary_strategy_main",
        "scope_ko": "최근 24개 기준월의 과거 60개월 통계에 대해 가상 기관의 명시된 수치 목적을 따르는지 확인하기 위한 보조 과제. 실제 월초 투자·문서해석·전략형성의 역사적 재현이 아니다.",
        "sources": source_metadata(), "reference_months": REFERENCE_MONTHS,
        "input_period": [selected["dates"][0], selected["dates"][-1]], "input_months": 83,
        "industry_order": EXPECTED_COLUMNS, "training_months": LOOKBACK, "windows": 24, "gammas": list(GAMMAS), "cases": 72,
        "first_training_window": windows[0]["public_market_data"]["training_window"],
        "last_training_window": windows[-1]["public_market_data"]["training_window"],
        "future_observations_used": 0, "future_months_reserved": 0,
        "calendar_interpretation": "Reference-month index only. Current revised source vintage does not establish prior-month public availability on historical month-start dates.",
        "selection_rule": "All 24 months of 2024-2025 retained before AI execution; no selection by reference separation or model performance.",
        "overlap": "Adjacent windows share 59 of 60 months. These are 24 fixed overlapping scenarios, not 24 independent market samples or 72 observed institutions.",
        "objective": "U_gamma(w)=mu.T @ w-gamma/2*(w.T @ Sigma @ w); w>=0, sum(w)=1.",
        "reference_interpretation": "Conditional optimum for supplied estimated statistics; not true future returns, actual fund holdings, or realized profitability.",
        "same_optimum_policy": "Keep every case including shared optima; equality of recommended portfolios is not harmful convergence when the conditional optima coincide.",
        "pair_reference_summary": {key: {
            "windows": len(rows), "classifications": dict(Counter(r["classification"] for r in rows)),
            "mean_D_star": float(np.mean([r["distance_D_star"] for r in rows])),
            "median_D_star": float(np.median([r["distance_D_star"] for r in rows])),
            "minimum_D_star": min(r["distance_D_star"] for r in rows),
            "maximum_D_star": max(r["distance_D_star"] for r in rows),
        } for key, rows in pair_records.items()},
        "all_three_shared_optimum": {"count": len(same_all), "window_ids": same_all}, "unresolved_pairs": unresolved,
        "numerical_verification": {
            "all_reference_KKT_checks_passed": True, "KKT_checks": 72, "all_covariances_SPD": True, "covariance_checks": 24,
            "minimum_covariance_eigenvalue": min(float(e[0]) for e in eigenvalues),
            "maximum_covariance_condition_number": max(float(e[-1] / e[0]) for e in eigenvalues),
            "KKT_maximum_residuals": dict(max_residuals), "independent_SLSQP_successes": 72,
            "independent_SLSQP_maximum_absolute_utility_gap": max(abs(r["utility_shortfall_to_face_reference"]) for r in slsqp_records),
            "independent_SLSQP_maximum_weight_difference": max(r["maximum_weight_difference_to_face_reference"] for r in slsqp_records),
            "oracle_zero_scores_and_blind_pair_identities_passed": True,
            "risk_aversion_return_and_variance_monotonicity_passed": True,
            "precision_note": f"Imported float64 engineering checks: KKT factor {NUMERICAL_FACTOR}; SLSQP objective scale 100, ftol 1e-12, maxiter 1000. No effect-size threshold; not formal exact-arithmetic certification.",
        },
        "deterministic_baselines": {f"{name}_gamma_{gamma}": {"cases": len(values), "mean_utility_regret": float(np.mean(values)), "minimum_utility_regret": min(values), "maximum_utility_regret": max(values)} for (name, gamma), values in baseline_losses.items()},
        "baseline_scope": "Equal weight and mandate-blind gamma3 are constructed diagnostic portfolios, not AI or human observations.",
        "conditional_workload_if_legacy_four_stage_policy_is_used": {"R1_R4_final_outputs": 144, "R1_R4_stage_calls": 576, "FRESH_outputs_and_calls": 72, "total_final_outputs": 216, "total_stage_calls": 648, "status": "arithmetic only; no recent workflow runpack or AI execution created by this generator"},
        "model_exposure": "Only model_visible payloads may be used; identifiers, reference months, reference answers, pair classifications and all evaluator_only fields remain evaluator metadata unless a separately reviewed prompt explicitly defines otherwise.",
        "memory_limitation": "Historical data may overlap model pretraining. Inputs exclude future observations, but this is not proof of unseen data, no leakage, historical information-set reconstruction, or genuine future prediction.",
        "AI_calls": 0, "AI_results": 0, "human_runs": 0,
        "response_sum_tolerance_if_imported_evaluator_is_used": RESPONSE_SUM_TOLERANCE,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_json(OUTPUT / "selected_input.json", selected)
    write_jsonl(OUTPUT / "cases.jsonl", cases)
    write_jsonl(OUTPUT / "windows.jsonl", windows)
    write_json(OUTPUT / "summary.json", summary)
    verification = verify_saved_outputs()
    write_json(OUTPUT / "verification.json", verification)
    names = ["selected_input.json", "cases.jsonl", "windows.jsonl", "summary.json", "verification.json"]
    solver_path = ROOT / "research/prepare_institutional_benchmark.py"
    manifest = {
        "schema_version": "1.0", "status": summary["status"], "sources": source_metadata(),
        "input": {"path": "data/french/monthly_returns.json", "sha256": sha256(INPUT),
                  "full_source_first_month": source["datasets"]["FF12"]["dates"][0], "full_source_last_month": source["datasets"]["FF12"]["dates"][-1],
                  "fields_used": ["datasets.FF12.columns", "datasets.FF12.dates", "datasets.FF12.value_weighted_total_returns", "risk_free.dates", "risk_free.values"],
                  "selected_dates": ["2019-01", "2025-11"]},
        "generator": {"path": "research/prepare_recent_industry_control.py", "sha256": sha256(Path(__file__))},
        "imported_numerical_helpers": {"path": "research/prepare_institutional_benchmark.py", "sha256": sha256(solver_path), "original_prepare_not_called": True},
        "outputs": {name: {"bytes": (OUTPUT / name).stat().st_size, "sha256": sha256(OUTPUT / name)} for name in names},
        "runtime": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "reproduce": "python research/prepare_recent_industry_control.py", "network_calls": 0, "AI_calls": 0,
        "legacy_core_mutation": "This generator only writes data/institutional_recent; it does not modify data/institutional, data/workflow or their generators.",
    }
    write_json(OUTPUT / "manifest.json", manifest)
    return {"status": summary["status"], "windows": 24, "cases": 72, "verification": verification,
            "pair_reference_summary": summary["pair_reference_summary"], "all_three_shared_optimum": summary["all_three_shared_optimum"],
            "numerical_verification": summary["numerical_verification"], "manifest_sha256": sha256(OUTPUT / "manifest.json"), "AI_calls": 0}


def verify_saved_outputs() -> dict:
    """Re-read serialized artifacts and recompute moments from the raw source.

    The independent moment check uses a centered matrix product rather than
    np.cov; numerical references receive a second KKT check after serialization.
    """
    _, selected, total, risk_free, excess = load_selected_input()
    saved_input = json.loads((OUTPUT / "selected_input.json").read_text(encoding="utf-8"))
    require(saved_input == selected, "Selected input roundtrip mismatch")
    cases = [json.loads(line) for line in (OUTPUT / "cases.jsonl").read_text(encoding="utf-8").splitlines()]
    windows = [json.loads(line) for line in (OUTPUT / "windows.jsonl").read_text(encoding="utf-8").splitlines()]
    require(len(cases) == 72 and len(windows) == 24, "Serialized coverage mismatch")
    max_cov_residual = 0.0
    for case in cases:
        index = case["window_id"] - 1
        r = total[index:index + LOOKBACK] - risk_free[index:index + LOOKBACK, None]
        require(np.array_equal(r, excess[index:index + LOOKBACK]), "RF alignment mismatch")
        mu = np.sum(r, axis=0) / LOOKBACK
        centered = r - mu
        cov = centered.T @ centered / (LOOKBACK - 1)
        market = case["model_visible"]["public_market_data"]
        saved_cov = np.asarray(market["sample_covariance_ddof_1"])
        saved_mu = np.asarray(market["mean_excess_return"])
        require(np.array_equal(mu, saved_mu), "Mean reconstruction mismatch")
        residual = float(np.max(np.abs(cov - saved_cov)))
        max_cov_residual = max(max_cov_residual, residual)
        tolerance = np.finfo(float).eps * LOOKBACK * max(float(np.linalg.norm(cov, np.inf)), np.finfo(float).tiny)
        require(residual <= tolerance, "Independent covariance reconstruction mismatch")
        gamma = case["model_visible"]["institution_mandate"]["gamma"]
        w = np.asarray(case["evaluator_only"]["reference_weights"])
        require(kkt_certificate(w, mu, cov, gamma)["passed"], "Saved reference failed independently reconstructed KKT")
        require(REFERENCE_MONTHS[index] == case["reference_month"], "Reference date mismatch")
        expected = {"start": selected["dates"][index], "end": selected["dates"][index + LOOKBACK - 1], "months": LOOKBACK}
        require(market["training_window"] == expected, "Input window mismatch")
        require(month_index(expected["end"]) < month_index(case["reference_month"]), "Future observation leak")
    require([w["reference_month"] for w in windows] == REFERENCE_MONTHS, "Window reference-month coverage mismatch")
    return {"all_passed": True, "cases_read_back": 72, "windows_read_back": 24,
            "source_RFs_matched_by_month": True, "raw_source_reconstruction_passed": True,
            "independent_centered_product_covariance_maximum_residual": max_cov_residual,
            "post_serialization_KKT_checks": 72, "future_input_checks": 72,
            "AI_observations": 0, "scope": "Numerical artifact verification only, not empirical strategy or model validation."}


if __name__ == "__main__":
    print(json.dumps(prepare(), ensure_ascii=False, indent=2, allow_nan=False))
