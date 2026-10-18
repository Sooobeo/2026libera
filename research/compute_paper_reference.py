"""Compute Salcher et al. (2026) quadratic-utility numerical references.

This is a calculation prototype, without LLM/API calls. The primary reference
maximizes the objective formed from the TRAINING moments given to the model.
Future 36-month test moments supply separate ex-post diagnostics only.

The paper-text sample-covariance implementation and the authors' September 17
replication-code implementation are deliberately kept as different modes.
Neither has a long-only restriction, trading costs, clipping, or a risk cap.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
AUTHOR_COMMIT = "14c3a4c9567da966de5a4f7b9e5ef9ea6cff99fe"
AUTHOR_ROOT = (
    "https://github.com/salcherlukas/Lost_in_Translation/blob/"
    + AUTHOR_COMMIT
)
GAMMAS = (1, 3, 5)
TRAIN_MONTHS, TEST_MONTHS = 60, 36
EPS = np.finfo(np.float64).eps


def json_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tolerance(*scales: float) -> float:
    """Floating-point verification bound; not an experimental effect threshold."""
    return float(512 * EPS * max(1.0, *(abs(float(x)) for x in scales)))


def covariance_info(matrix: np.ndarray) -> dict:
    eigenvalues = np.linalg.eigvalsh(matrix)
    if not np.all(np.isfinite(matrix)) or eigenvalues[0] <= 0:
        raise ValueError("Covariance is not finite and positive definite.")
    np.linalg.cholesky(matrix)
    return {
        "minimum_eigenvalue": float(eigenvalues[0]),
        "maximum_eigenvalue": float(eigenvalues[-1]),
        "spectral_condition_number": float(eigenvalues[-1] / eigenvalues[0]),
        "cholesky_passed": True,
    }


def author_covariance(sample_covariance: np.ndarray) -> tuple[np.ndarray, dict]:
    """Match ridge_inverse() from the pinned author code, including its ridge."""
    result = 0.8 * sample_covariance + 0.2 * np.diag(np.diag(sample_covariance))
    minimum = float(np.linalg.eigvalsh(result)[0])
    added_ridge = abs(minimum) + 1e-4 if minimum < 1e-6 else 0.0
    if added_ridge:
        result = result + np.eye(result.shape[0]) * added_ridge
    return result, {
        "code_only_diagonal_shrinkage_intensity": 0.2,
        "eigenvalue_before_optional_ridge": minimum,
        "code_only_ridge_trigger": "minimum_eigenvalue < 1e-6",
        "added_diagonal_ridge": added_ridge,
    }


def utility(w: np.ndarray, mu: np.ndarray, cov: np.ndarray, gamma: int) -> float:
    return float(mu @ w - gamma / 2 * (w @ cov @ w))


def quadratic_reference(mu: np.ndarray, cov: np.ndarray, gamma: int) -> tuple[np.ndarray, dict]:
    """Solve Eq. (7) without forming an inverse or clipping any weight."""
    ones = np.ones(mu.size)
    inverse_mu = np.linalg.solve(cov, mu)
    inverse_ones = np.linalg.solve(cov, ones)
    multiplier = float((ones @ inverse_mu - gamma) / (ones @ inverse_ones))
    weights = (inverse_mu - multiplier * inverse_ones) / gamma
    gradient = mu - gamma * cov @ weights
    kkt_residual = float(np.max(np.abs(gradient - multiplier)))
    investment_residual = float(abs(np.sum(weights) - 1))
    kkt_tol = tolerance(
        np.linalg.norm(mu, ord=np.inf),
        gamma * np.linalg.norm(cov, ord=np.inf) * np.linalg.norm(weights, ord=np.inf),
    )
    investment_tol = tolerance(np.linalg.norm(weights, ord=1))
    if kkt_residual > kkt_tol or investment_residual > investment_tol:
        raise ArithmeticError("Training/full-investment KKT verification failed.")
    return weights, {
        "equality_multiplier": multiplier,
        "maximum_gradient_equality_residual": kkt_residual,
        "weight_sum_residual": investment_residual,
        "gradient_check_tolerance": kkt_tol,
        "weight_sum_check_tolerance": investment_tol,
        "passed": True,
    }


def loss_identity(
    optimum: np.ndarray,
    candidate: np.ndarray,
    mu: np.ndarray,
    cov: np.ndarray,
    gamma: int,
) -> dict:
    """For sum-one weights, U(w*)-U(w) = gamma/2 (w-w*)' S (w-w*)."""
    difference = candidate - optimum
    direct = utility(optimum, mu, cov, gamma) - utility(candidate, mu, cov, gamma)
    quadratic = float(gamma / 2 * (difference @ cov @ difference))
    error = abs(direct - quadratic)
    bound = tolerance(
        direct,
        quadratic,
        utility(optimum, mu, cov, gamma),
        utility(candidate, mu, cov, gamma),
    )
    if abs(float(np.sum(candidate) - 1)) > tolerance(np.linalg.norm(candidate, ord=1)):
        raise ArithmeticError("Loss-identity candidate does not sum to one.")
    if error > bound or direct < -bound or quadratic < -bound:
        raise ArithmeticError("Quadratic-utility loss identity failed.")
    return {
        "utility_loss_direct": direct,
        "utility_loss_quadratic_identity": quadratic,
        "absolute_identity_residual": error,
        "verification_tolerance": bound,
        "passed": True,
    }


def realized_sharpe(w: np.ndarray, mu: np.ndarray, cov: np.ndarray) -> float:
    return float((mu @ w) / np.sqrt(w @ cov @ w))


def calendar_months(start: str, count: int) -> list[str]:
    year, month = map(int, start.split("-"))
    offset = year * 12 + month - 1
    return [f"{(offset + i) // 12:04d}-{(offset + i) % 12 + 1:02d}" for i in range(count)]


def generate(input_path: Path, output_path: Path, summary_path: Path) -> dict:
    source = json.loads(input_path.read_text(encoding="utf-8"))
    dates, columns = source["dates"], source["columns"]
    returns = np.asarray(source["returns"], dtype=np.float64)
    if dates != calendar_months("1964-01", 720) or returns.shape != (720, 12):
        raise ValueError("Expected 720 consecutive months (1964-01..2023-12) and 12 industries.")
    if len(columns) != 12 or len(set(columns)) != 12 or not np.isfinite(returns).all():
        raise ValueError("Industry labels or monthly decimal excess returns are invalid.")
    if source.get("units") != "decimal_monthly_return":
        raise ValueError("Input units must explicitly be decimal_monthly_return.")

    equal_weight = np.full(12, 1 / 12)
    cases = []
    arrays = {mode: {g: [] for g in GAMMAS} for mode in ("paper_text_sample", "author_code_shrink_02")}
    diagnostic_maxima = {"weight_sum_residual": 0.0, "gradient_residual": 0.0, "loss_identity_residual": 0.0}
    mode_differences = {g: [] for g in GAMMAS}
    ridge_activations = 0

    for start in range(720 - TRAIN_MONTHS - TEST_MONTHS + 1):
        train_end, test_end = start + TRAIN_MONTHS, start + TRAIN_MONTHS + TEST_MONTHS
        train, test = returns[start:train_end], returns[train_end:test_end]
        mu_train, mu_test = train.mean(axis=0), test.mean(axis=0)
        sample_train, sample_test = np.cov(train, rowvar=False, ddof=1), np.cov(test, rowvar=False, ddof=1)
        shrunk_train, shrink_details = author_covariance(sample_train)
        ridge_activations += int(shrink_details["added_diagonal_ridge"] > 0)
        case = {
            "window_id": start + 1,
            "training_window": {"start": dates[start], "end": dates[train_end - 1], "months": TRAIN_MONTHS},
            "test_window": {"start": dates[train_end], "end": dates[test_end - 1], "months": TEST_MONTHS},
            "training_forecast": {
                "mean_excess_return": mu_train.tolist(),
                "sample_covariance_ddof_1": sample_train.tolist(),
                "sample_covariance_checks": covariance_info(sample_train),
            },
            "ex_post_only": {
                "not_model_input": True,
                "mean_excess_return": mu_test.tolist(),
                "sample_covariance_ddof_1": sample_test.tolist(),
                "sample_covariance_checks": covariance_info(sample_test),
                "perfect_foresight_quadratic_reference_by_gamma": {},
            },
            "author_code_covariance_details": shrink_details,
            "reference_modes": {},
        }
        test_references = {}
        for gamma in GAMMAS:
            test_weights, test_checks = quadratic_reference(mu_test, sample_test, gamma)
            test_references[gamma] = test_weights
            diagnostic_maxima["weight_sum_residual"] = max(diagnostic_maxima["weight_sum_residual"], test_checks["weight_sum_residual"])
            diagnostic_maxima["gradient_residual"] = max(diagnostic_maxima["gradient_residual"], test_checks["maximum_gradient_equality_residual"])
            case["ex_post_only"]["perfect_foresight_quadratic_reference_by_gamma"][str(gamma)] = {
                "weights": test_weights.tolist(),
                "utility_on_test_moments": utility(test_weights, mu_test, sample_test, gamma),
                "monthly_sharpe": realized_sharpe(test_weights, mu_test, sample_test),
                "checks": test_checks,
                "role": "ex-post diagnostic; never the primary input-reflection target or a prompt input",
            }

        for mode, cov in (("paper_text_sample", sample_train), ("author_code_shrink_02", shrunk_train)):
            case["reference_modes"][mode] = {
                "objective_covariance": cov.tolist(),
                "covariance_checks": covariance_info(cov),
                "by_gamma": {},
            }
            for gamma in GAMMAS:
                weights, checks = quadratic_reference(mu_train, cov, gamma)
                train_identity = loss_identity(weights, equal_weight, mu_train, cov, gamma)
                ex_post_identity = loss_identity(test_references[gamma], weights, mu_test, sample_test, gamma)
                record = {
                    "input_forecast_optimum_weights": weights.tolist(),
                    "primary_reference_utility": utility(weights, mu_train, cov, gamma),
                    "primary_role": "optimum of the supplied TRAINING mean/covariance objective, not future returns",
                    "checks": checks,
                    "training_equal_weight_diagnostic": train_identity,
                    "weight_summary": {
                        "minimum": float(weights.min()), "maximum": float(weights.max()),
                        "negative_count": int(np.sum(weights < 0)),
                        "gross_leverage_sum_abs": float(np.linalg.norm(weights, ord=1)),
                    },
                    "ex_post_only": {
                        "not_model_input": True,
                        "utility_on_test_moments": utility(weights, mu_test, sample_test, gamma),
                        "utility_loss_to_perfect_foresight": ex_post_identity,
                        "monthly_sharpe_on_test_moments": realized_sharpe(weights, mu_test, sample_test),
                        "sharpe_gap_to_perfect_foresight_quadratic": (
                            realized_sharpe(test_references[gamma], mu_test, sample_test)
                            - realized_sharpe(weights, mu_test, sample_test)
                        ),
                        "sharpe_gap_note": "May be negative: quadratic-utility optimum does not maximize Sharpe ratio.",
                    },
                }
                case["reference_modes"][mode]["by_gamma"][str(gamma)] = record
                arrays[mode][gamma].append(weights)
                diagnostic_maxima["weight_sum_residual"] = max(diagnostic_maxima["weight_sum_residual"], checks["weight_sum_residual"])
                diagnostic_maxima["gradient_residual"] = max(diagnostic_maxima["gradient_residual"], checks["maximum_gradient_equality_residual"])
                diagnostic_maxima["loss_identity_residual"] = max(
                    diagnostic_maxima["loss_identity_residual"],
                    train_identity["absolute_identity_residual"],
                    ex_post_identity["absolute_identity_residual"],
                )
        for gamma in GAMMAS:
            sample_w = arrays["paper_text_sample"][gamma][-1]
            shrink_w = arrays["author_code_shrink_02"][gamma][-1]
            mode_differences[gamma].append(float(np.linalg.norm(sample_w - shrink_w, ord=1)))
            for mode, cov, candidate in (
                ("paper_text_sample", sample_train, shrink_w),
                ("author_code_shrink_02", shrunk_train, sample_w),
            ):
                alternative_identity = loss_identity(
                    arrays[mode][gamma][-1], candidate, mu_train, cov, gamma
                )
                case["reference_modes"][mode]["by_gamma"][str(gamma)]["alternative_mode_training_loss"] = alternative_identity
                diagnostic_maxima["loss_identity_residual"] = max(
                    diagnostic_maxima["loss_identity_residual"], alternative_identity["absolute_identity_residual"]
                )
        cases.append(case)

    mode_summaries = {}
    for mode in arrays:
        mode_summaries[mode] = {}
        for gamma, values in arrays[mode].items():
            values = np.asarray(values)
            gross = np.abs(values).sum(axis=1)
            mode_summaries[mode][str(gamma)] = {
                "windows": int(values.shape[0]),
                "windows_with_any_negative_weight": int(np.any(values < 0, axis=1).sum()),
                "fraction_windows_with_any_negative_weight": float(np.any(values < 0, axis=1).mean()),
                "fraction_individual_weights_negative": float((values < 0).mean()),
                "minimum_weight_all_windows": float(values.min()),
                "maximum_weight_all_windows": float(values.max()),
                "gross_leverage_mean": float(gross.mean()),
                "gross_leverage_median": float(np.median(gross)),
                "gross_leverage_maximum": float(gross.max()),
            }

    provenance = {
        "paper": "Salcher, Stoeckl, Hanke (2026), Lost in Translation? Risk-Adjusting RMSE for Economic Forecast Performance",
        "paper_url": "https://onlinelibrary.wiley.com/doi/full/10.1002/for.70134",
        "paper_sections": ["3.2 equations (6) and (7)", "4.1", "6"],
        "author_code_commit": AUTHOR_COMMIT,
        "author_code_date": "2026-09-17",
        "author_code_urls": {
            "configuration": AUTHOR_ROOT + "/code/00_setup.R",
            "portfolios": AUTHOR_ROOT + "/code/functions/portfolios.R",
            "window_evaluation": AUTHOR_ROOT + "/code/functions/sharpe_gap.R",
            "implementation_notes": AUTHOR_ROOT + "/README.md",
        },
        "input_path": str(input_path.resolve()),
        "input_sha256": sha256(input_path),
        "input_units": source["units"],
        "input_metadata": {key: value for key, value in source.items() if key not in {"dates", "returns", "risk_free", "total_returns"}},
        "script_sha256": sha256(Path(__file__)),
        "python_version": platform.python_version(), "numpy_version": np.__version__,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "original_data_vintage": "Paper author says April 2025. This computation uses the separately recorded current downloaded vintage; values can differ.",
    }
    distinctions = [
        "Primary input-reflection reference uses supplied training moments. Future test optimum is an ex-post diagnostic only.",
        "paper_text_sample follows the paper-text sample-covariance objective. It does not reproduce the authors' code-only 0.20 diagonal shrinkage.",
        "author_code_shrink_02 follows the pinned replication-code covariance for forecast weights, including its optional numerical ridge. These constants are code-derived, not direct paper-text choices.",
        "Both modes use unshrunk test sample covariance for perfect-foresight diagnostics, matching the pinned author code.",
        "The 625 actual-data rolling windows overlap heavily. They are not 625 independent situations, simulated paths, LLM observations, or a sample-size recommendation.",
        "No short-sale restriction, risk cap, transaction cost or weight clipping is introduced. Negative weights and large gross leverage are retained.",
        "This computes only the quadratic-utility subset, not all 13 strategies or all published tables/figures. Current data revisions also prevent claiming exact numeric paper replication.",
        "Research question, main experiment, private/public information construction, stage policies, and model execution remain unfrozen.",
    ]
    summary = {
        "status": "paper_calculation_prototype_completed_main_design_not_frozen",
        "paid_or_model_api_calls": 0,
        "dataset": {"start": dates[0], "end": dates[-1], "months": 720, "industries": columns, "units": source["units"]},
        "training_months": TRAIN_MONTHS, "test_months": TEST_MONTHS,
        "overlapping_actual_data_windows": len(cases),
        "gammas_direct_paper_table_values": list(GAMMAS),
        "formula": {
            "objective": "U_gamma(w) = mu_hat.T w - gamma/2 * w.T S w; sum(w)=1; w in R^12",
            "solution": "w_star = solve(S, mu_hat - lambda*1)/gamma; lambda=(1.T solve(S,mu_hat)-gamma)/(1.T solve(S,1))",
            "main_regret_identity": "U_train(w_star)-U_train(w) = gamma/2*(w-w_star).T S_train (w-w_star), for any sum-one w",
            "sample_covariance": "ddof=1",
            "code_covariance": "S=0.8*sample_covariance+0.2*diag(sample_covariance), plus code-defined ridge only if triggered",
        },
        "mode_summary": mode_summaries,
        "code_only_optional_ridge_activated_windows": ridge_activations,
        "implementation_weight_L1_differences": {
            str(g): {"mean": float(np.mean(v)), "maximum": float(np.max(v))} for g, v in mode_differences.items()
        },
        "numerical_checks": {"all_passed": True, "maxima": diagnostic_maxima, "scope": "float64 algebra checks, not formal exact-arithmetic certification"},
        "first_window": {
            "training_window": cases[0]["training_window"], "test_window": cases[0]["test_window"],
            "input_forecast_optima": {
                mode: {g: value["input_forecast_optimum_weights"] for g, value in content["by_gamma"].items()}
                for mode, content in cases[0]["reference_modes"].items()
            },
        },
        "distinctions_and_limitations": distinctions,
        "provenance": provenance,
        "full_reference_output": str(output_path.resolve()),
    }
    json_write(output_path, {"schema_version": "1.0", "summary": summary, "windows": cases})
    json_write(summary_path, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/french/ff12_excess_calibration_1964_2023.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data/french/salcher_quadratic_empirical_references.json")
    parser.add_argument("--summary", type=Path, default=ROOT / "data/french/salcher_quadratic_reference_summary.json")
    args = parser.parse_args()
    summary = generate(args.input, args.output, args.summary)
    print(json.dumps({
        "status": summary["status"], "windows": summary["overlapping_actual_data_windows"],
        "checks": summary["numerical_checks"], "mode_summary": summary["mode_summary"],
        "output": str(args.output.resolve()), "summary": str(args.summary.resolve()),
    }, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
