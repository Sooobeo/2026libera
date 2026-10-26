"""Independent numeric facts from a completed guarded semantic bundle.

No prose grading, generation, normalization of raw files or future-return claim.
Fraction arithmetic is independent of the accepted allocation finalizer.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, DecimalException, localcontext
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "research/completion_20261026"
CODES = ("10", "15", "20", "25", "30", "35", "40", "45", "50", "55", "60")
GUARD_PATH = REPORT_ROOT / "prepare_stage_semantic_audit.py"
GUARD_SHA = "3d9c36405ad7b86e212d99480976af154397096491a36b1e365ee8f355799a90"
MANIFEST_PATH = ROOT / "data/sector_protocol/v494_design_20261025/prepared/preparation_manifest.json"
MANIFEST_SHA = "8023f8b11ec9b1d43bf1b5b08ac37ccbab4ac5ab7ad7de28a9e93d8e67a4ef29"
CASES = ("ubs_june_2026__E", "ubs_june_2026__L", "common_market_only__C")


def strict(text, exact=False):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    def constant(value):
        raise ValueError("Nonfinite JSON constant")
    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("JSON float exceeds finite machine range")
        return number
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant,
                      **({"parse_float": Decimal, "parse_int": Decimal} if exact else {"parse_float": finite_float}))


def path_of(value):
    path = Path(value)
    path = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Artifact outside workspace")
    return path


def read(path, exact=False):
    path = path_of(path)
    data = path.read_bytes()
    value = strict(data.decode("utf-8-sig"), exact=exact)
    if path.read_bytes() != data:
        raise ValueError("Artifact changed during read")
    return value, {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}


def bound(reference, expected=None):
    if not isinstance(reference, dict) or set(reference) != {"path", "sha256"}:
        raise ValueError("Exact artifact reference required")
    if expected is not None and path_of(reference["path"]) != path_of(expected):
        raise ValueError("Wrong artifact role or stage")
    value, actual = read(reference["path"])
    if reference["sha256"] != actual["sha256"]:
        raise ValueError("Artifact hash mismatch")
    return value, actual


def fraction(value, limit=512):
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, str)):
        raise ValueError("Exact decimal numeric value required")
    number = Decimal(value)
    if (not number.is_finite() or len(number.as_tuple().digits) > limit
            or abs(number.as_tuple().exponent) > limit or abs(number.adjusted()) > limit):
        raise ValueError("Numeric value outside finite bounded policy")
    return Fraction(number)


def ratio(value):
    value = Fraction(value)
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def decimal_display(value, precision=60):
    value = Fraction(value)
    with localcontext() as context:
        context.prec = precision
        return str(Decimal(value.numerator) / Decimal(value.denominator))


def square_root(value):
    value = Fraction(value)
    if value < 0:
        raise ValueError("Negative variance; no clipping applied")
    with localcontext() as context:
        context.prec = 60
        return (Decimal(value.numerator) / Decimal(value.denominator)).sqrt()


def direction(delta):
    return "above" if delta > 0 else "below" if delta < 0 else "equal"


def independent_allocation(raw):
    result = {"status": "unavailable", "raw_sum": None, "rows": [], "automatic_prose_grade": False}
    try:
        parsed = strict(raw, exact=True)
        rows = parsed.get("sectors") if isinstance(parsed, dict) else None
        if not isinstance(rows, list) or len(rows) != 11:
            raise ValueError("Exactly eleven sector rows required")
        weights = {}
        for row in rows:
            if not isinstance(row, dict) or row.get("sector_code") not in CODES or row["sector_code"] in weights:
                raise ValueError("Noncanonical or duplicate sector")
            if not isinstance(row.get("weight"), Decimal):
                raise ValueError("Weight must be a finite JSON number")
            weights[row["sector_code"]] = fraction(row["weight"])
        total = sum(weights.values(), Fraction())
        result.update(raw_sum=ratio(total), raw_sum_decimal=decimal_display(total),
                      raw_budget_residual=ratio(total - 1), raw_budget_within_1e_6=abs(total - 1) <= Fraction(1, 1000000),
                      raw_negative_codes=[c for c in CODES if weights[c] < 0],
                      raw_above_one_codes=[c for c in CODES if weights[c] > 1],
                      raw_weights={c: ratio(weights[c]) for c in CODES})
        if any(v < 0 for v in weights.values()) or total <= 0:
            raise ValueError("Nonnegative complete vector and positive total required for derived math")
        shares = {c: weights[c] / total for c in CODES}
        quota = {c: 10000 * shares[c] for c in CODES}
        units = {c: quota[c].numerator // quota[c].denominator for c in CODES}
        remainder = 10000 - sum(units.values())
        order = sorted(CODES, key=lambda c: (quota[c] - units[c], -CODES.index(c)), reverse=True)
        for code in order[:remainder]:
            units[code] += 1
        if sum(units.values()) != 10000:
            raise ArithmeticError("Independent budget invariant failed")
        result.update(status="mathematically_scalable_vector", normalization_multiplier=ratio(1 / total),
                      normalization_applied=total != 1, independent_total_units=10000,
                      remainder_recipients=order[:remainder], rows=[{
                          "sector_code": c, "raw_weight": ratio(weights[c]), "raw_weight_decimal": decimal_display(weights[c]),
                          "normalized_weight": ratio(shares[c]), "independent_units": units[c],
                          "independent_weight": ratio(Fraction(units[c], 10000)),
                          "normalization_delta": ratio(shares[c] - weights[c]),
                          "quantization_delta": ratio(Fraction(units[c], 10000) - shares[c])} for c in CODES])
    except (ValueError, TypeError, KeyError, DecimalException, OverflowError, RecursionError) as error:
        result["reason"] = str(error)
    return result


def unratio(value):
    return Fraction(int(value["numerator"]), int(value["denominator"]))


def compare_sidecar(independent, sidecar, transport_status):
    expected = transport_status == "completed" and independent["status"] == "mathematically_scalable_vector"
    result = {"accepted_endpoint_expected_available": expected,
              "independent_math_is_not_transport_or_semantic_validation": True,
              "sidecar_status": sidecar.get("status"), "matches": False}
    if not expected:
        result["matches"] = sidecar.get("status") == "unavailable"
        result["comparison_scope"] = "Availability status only; no accepted derived numerical vector exists."
        result["reason"] = "Transport/structure eligibility or mathematical vector eligibility prevents an accepted endpoint."
        return result
    expected_units = {r["sector_code"]: r["independent_units"] for r in independent["rows"]}
    try:
        actual_rows = sidecar.get("rows", [])
        actual_units = {r.get("sector_code"): r.get("final_units") for r in actual_rows}
        actual_by_code = {r["sector_code"]: r for r in actual_rows}
        result.update(independent_units=expected_units, sidecar_units=actual_units)
        result["matches"] = (sidecar.get("status") == "finalized" and len(actual_rows) == 11
                             and all(type(value) is int for value in actual_units.values())
                             and actual_units == expected_units and sidecar.get("final_total_units") == 10000
                             and fraction(sidecar["raw_sum_exact_decimal"], limit=2048) == unratio(independent["raw_sum"])
                             and unratio(sidecar["normalization_multiplier_exact"]) == unratio(independent["normalization_multiplier"])
                             and sidecar["normalization_applied"] is independent["normalization_applied"]
                             and all(fraction(actual_by_code[r["sector_code"]]["raw_weight_exact_decimal"], limit=2048) == unratio(r["raw_weight"])
                                     and unratio(actual_by_code[r["sector_code"]]["normalized_weight_exact"]) == unratio(r["normalized_weight"])
                                     and unratio(actual_by_code[r["sector_code"]]["normalization_delta_exact"]) == unratio(r["normalization_delta"])
                                     and unratio(actual_by_code[r["sector_code"]]["rounding_delta_exact"]) == unratio(r["quantization_delta"])
                                     for r in independent["rows"]))
    except (ValueError, TypeError, KeyError, AttributeError, ZeroDivisionError, DecimalException) as error:
        result["malformed_sidecar_numeric_fields"] = str(error)
    return result


def market_arrays(market):
    order = market.get("sector_codes")
    if not isinstance(order, list) or len(order) != 11 or set(order) != set(CODES):
        raise ValueError("Explicit unique eleven-sector order required")
    arrays = ("sector_names", "tickers", "daily_mean_return", "daily_volatility",
              "annualized_volatility_diagnostic", "lookback_compound_return", "benchmark_reported_weights_percent")
    for key in arrays:
        if not isinstance(market.get(key), list) or len(market[key]) != 11:
            raise ValueError("Eleven ordered values required: " + key)
    for key in ("covariance", "correlation"):
        if (not isinstance(market.get(key), list) or len(market[key]) != 11
                or any(not isinstance(row, list) or len(row) != 11 for row in market[key])):
            raise ValueError("Eleven by eleven ordered matrix required: " + key)
    if set(market.get("baseline_weights", {})) != set(CODES):
        raise ValueError("Complete code-keyed baseline required")
    return order


def resolve_pointer(value, pointer):
    for part in pointer.strip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def market_facts(market, index):
    order = market_arrays(market)
    if index.get("matrix_reference_table", {}).get("shared", {}).get("sector_order") != order:
        raise ValueError("Fact-index matrix sector order differs")
    annual = fraction(market["annualization_trading_days"])
    covariance = [[fraction(v) for v in row] for row in market["covariance"]]
    facts, ids = [], set()
    for table in index["fact_tables"]:
        for values in table["rows"]:
            if len(values) != len(table["columns"]):
                raise ValueError("Fact-table row width mismatch")
            row = {**table.get("shared", {}), **dict(zip(table["columns"], values))}
            identifier, pointer, code = row["fact_id"], row["common_market_json_pointer"], row.get("sector_code")
            if identifier in ids:
                raise ValueError("Duplicate numeric fact ID")
            ids.add(identifier)
            if code is not None:
                if code not in order:
                    raise ValueError("Unknown fact sector")
                parts = pointer.strip("/").split("/")
                if isinstance(market.get(parts[0]), list) and (len(parts) != 2 or int(parts[1]) != order.index(code)):
                    raise ValueError("Fact pointer assigns the wrong array sector")
                if parts[0] == "baseline_weights" and parts != ["baseline_weights", code]:
                    raise ValueError("Fact pointer assigns the wrong baseline sector")
            value = fraction(resolve_pointer(market, pointer))
            facts.append({"fact_id": identifier, "sector_code": code, "metric": row["metric"],
                          "unit": row["unit"], "period": row["period"], "common_market_pointer": pointer,
                          "visible_exact": ratio(value), "visible_decimal": decimal_display(value),
                          "percent_equivalent": decimal_display(value * 100) if row["unit"] in {
                              "decimal_weight", "daily_decimal_return", "annual_decimal_return", "decimal_return_over_window"} else None,
                          "verification_scope": "Exact visible input value; not a raw daily-series recomputation."})
    rows = []
    for i, code in enumerate(order):
        observed_daily = fraction(market["daily_volatility"][i])
        observed_annual = fraction(market["annualized_volatility_diagnostic"][i])
        daily = square_root(covariance[i][i])
        yearly = square_root(annual * covariance[i][i])
        with localcontext() as context:
            context.prec = 60
            daily_difference = daily - Decimal(decimal_display(observed_daily))
            yearly_difference = yearly - Decimal(decimal_display(observed_annual))
        rows.append({"sector_code": code, "array_index": i, "sector_name": market["sector_names"][i],
                     "ticker": market["tickers"][i], "covariance_diagonal_pointer": f"/covariance/{i}/{i}",
                     "daily_sd_from_visible_covariance": str(daily),
                     "daily_sd_minus_visible_approx": str(daily_difference),
                     "annual_sd_from_visible_covariance": str(yearly),
                     "annual_sd_minus_visible_approx": str(yearly_difference)})
    symmetry = max(abs(covariance[i][j] - covariance[j][i]) for i in range(11) for j in range(11))
    correlation_rows = []
    for i in range(11):
        for j in range(11):
            denominator = covariance[i][i] * covariance[j][j]
            with localcontext() as context:
                context.prec = 60
                calculated = Decimal(decimal_display(covariance[i][j])) / square_root(denominator) if denominator > 0 else None
                difference = calculated - Decimal(decimal_display(fraction(market["correlation"][i][j]))) if calculated is not None else None
            correlation_rows.append({"left_sector": order[i], "right_sector": order[j], "matrix_indices": [i, j],
                                     "covariance_visible_exact": ratio(covariance[i][j]),
                                     "correlation_recomputed_approx": str(calculated) if calculated is not None else None,
                                     "minus_visible_correlation_approx": str(difference) if difference is not None else None})
    baseline = {c: fraction(market["baseline_weights"][c]) for c in order}
    return {"sector_order": order, "numeric_fact_table": facts, "sector_internal_checks": rows,
            "covariance_symmetry_max_abs": ratio(symmetry), "matrix_internal_checks": correlation_rows,
            "baseline_diagnostics": portfolio_diagnostics(baseline, market, "supplied_serialized_comparison_benchmark"),
            "source_metadata": {key: market[key] for key in ("return_observations", "lookback_return_dates", "covariance_ddof",
                                  "units", "covariance_unit", "annualization_trading_days", "cutoff_exclusive")},
            "unrecomputed": ["The visible payload has no 60 by 11 daily return observations. Daily means, sample covariance and 60-day compounded returns cannot be recomputed from raw time series here.",
                             "The 60-day compounded return is not inferred from mean*60 or (1+mean)^60.",
                             "No portfolio 60-day compounded return is inferred without a rebalancing/holdings path."],
            "approximation": "Quadratic forms use exact fractions of serialized input decimals; square roots/correlations are 60-digit Decimal approximations to those inputs, not extra source precision."}


def portfolio_diagnostics(weights, market, label):
    order = market_arrays(market)
    variance = sum((weights[a] * fraction(market["covariance"][i][j]) * weights[b]
                    for i, a in enumerate(order) for j, b in enumerate(order)), Fraction())
    mean = sum((weights[c] * fraction(market["daily_mean_return"][i]) for i, c in enumerate(order)), Fraction())
    annual = fraction(market["annualization_trading_days"])
    total = sum(weights.values(), Fraction())
    return {"representation": label, "weight_sum_exact": ratio(total), "weighted_visible_daily_mean_exact": ratio(mean),
            "daily_quadratic_variance_exact": ratio(variance),
            "daily_sd_approx": str(square_root(variance)) if variance >= 0 else None,
            "annualized_sd_approx": str(square_root(annual * variance)) if variance >= 0 else None,
            "interpretation": "Historical quadratic diagnostic of the explicitly labelled weight representation. Raw exposures whose sum differs from one are not a fully-invested portfolio. This is not expected future return or realized post-decision performance.",
            "compounded_portfolio_return": None,
            "compounded_return_reason": "Daily paths and a holdings/rebalancing rule are absent; no inference from sector means or a weighted sum of compounded returns."}


def allocation_comparisons(current, prior, market):
    if current["status"] != "mathematically_scalable_vector":
        return {"status": "unavailable", "reason": "No scalable current vector; no invented derived values."}
    order = market_arrays(market)
    current_rows = {r["sector_code"]: r for r in current["rows"]}
    prior_rows = {r["sector_code"]: r for r in prior["rows"]} if prior and prior["status"] == "mathematically_scalable_vector" else {}
    reported = {c: fraction(market["benchmark_reported_weights_percent"][i]) for i, c in enumerate(order)}
    reported_total = sum(reported.values(), Fraction())
    rows = []
    for code in CODES:
        row = current_rows[code]
        raw, derived = unratio(row["raw_weight"]), unratio(row["independent_weight"])
        comparators = {"supplied_serialized_baseline": fraction(market["baseline_weights"][code]),
                       "reported_benchmark_percent_div100": reported[code] / 100,
                       "exact_reported_sum_normalization": reported[code] / reported_total}
        deltas = None
        if code in prior_rows:
            raw_delta = raw - unratio(prior_rows[code]["raw_weight"])
            derived_delta = derived - unratio(prior_rows[code]["independent_weight"])
            deltas = {"raw_change_exact": ratio(raw_delta), "derived_change_exact": ratio(derived_delta),
                      "raw_change_direction": direction(raw_delta), "derived_change_direction": direction(derived_delta),
                      "direction_changed_by_external_math": direction(raw_delta) != direction(derived_delta)}
        rows.append({"sector_code": code, "own_D0_to_current": deltas,
                     "benchmark_relations": {name: {"comparator_exact": ratio(value), "raw_difference": ratio(raw - value),
                        "derived_difference": ratio(derived - value), "raw_direction": direction(raw - value),
                        "derived_direction": direction(derived - value),
                        "direction_changed_by_external_math": direction(raw - value) != direction(derived - value)}
                         for name, value in comparators.items()}})
    vectors = {"raw_submitted_exposures": {c: unratio(current_rows[c]["raw_weight"]) for c in CODES},
               "proportionally_normalized_diagnostic": {c: unratio(current_rows[c]["normalized_weight"]) for c in CODES},
               "independent_integer_weight_diagnostic": {c: unratio(current_rows[c]["independent_weight"]) for c in CODES}}
    return {"status": "numeric_facts_only", "sector_rows": rows,
            "portfolio_diagnostics": [portfolio_diagnostics(w, market, name) for name, w in vectors.items()],
            "benchmark_precision_limit": "Directions use exact serialized decimals and distinguish reported percentages from normalized comparison weights; no discretionary near-neutral category or economic-significance judgment.",
            "benchmark_reported_total_percent_exact": ratio(reported_total)}


def rebuild_guarded_bundle(stage_dir):
    if hashlib.sha256(GUARD_PATH.read_bytes()).hexdigest() != GUARD_SHA:
        raise ValueError("Frozen semantic guard source changed")
    spec = importlib.util.spec_from_file_location("completion_numeric_guard", GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.prepare(stage_dir)


def read_bound_math(directory, declaration, math_path):
    spec, spec_ref = read(directory / "worker_spec.json")
    transport, transport_ref = read(directory / "transport_result.json")
    stage_name = spec["case_id"] + "__" + spec["stage"]
    expected_math = path_of(declaration["output_root"]) / "allocation_math" / (stage_name + ".json")
    if directory.name != stage_name or path_of(math_path) != expected_math:
        raise ValueError("Math sidecar is not this stage's declared report path")
    sidecar, sidecar_ref = read(math_path)
    if (sidecar.get("case_id") != spec["case_id"] or sidecar.get("stage") != spec["stage"]
            or sidecar.get("observed_transport_status") != transport.get("status")):
        raise ValueError("Math sidecar case/stage/transport mismatch")
    required_refs = [spec_ref, transport_ref]
    if sidecar.get("status") == "finalized":
        required_refs.append(transport["response_artifact"])
        _, review_ref = read(directory / "stage_review.json")
        required_refs.append(review_ref)
    for required in required_refs:
        if not any(path_of(r["path"]) == path_of(required["path"]) and r["sha256"] == required["sha256"]
                   for r in sidecar.get("input_refs", [])):
            raise ValueError("Math sidecar omits current stage artifact binding")
    refs = [spec_ref, transport_ref, sidecar_ref]
    for reference in sidecar.get("input_refs", []):
        _, actual = bound(reference)
        refs.append(actual)
    return sidecar, refs


def implementation_ref():
    path = Path(__file__).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def audit_bundle(bundle_path, math_path):
    bundle, bundle_ref = read(bundle_path)
    if (bundle.get("version") != "completion_semantic_bundle_1" or bundle.get("purpose") != "pilot_completion"
            or bundle.get("status") != "prepared_for_semantic_reading" or bundle.get("case_id") not in CASES
            or bundle.get("stage") not in {"D0", "F0"}
            or bundle.get("observed_transport_status") not in {"completed", "model_structure_failure"}):
        raise ValueError("Completed guarded semantic bundle required; no partial/live text use")
    stage_name = bundle["case_id"] + "__" + bundle["stage"]
    matches = [r for r in bundle["refs"] if path_of(r["path"]).name == "worker_spec.json"
               and path_of(r["path"]).parent.name == stage_name]
    if len(matches) != 1:
        raise ValueError("Exactly one current worker-spec binding required")
    directory = path_of(matches[0]["path"]).parent
    regenerated = rebuild_guarded_bundle(directory)
    comparable = lambda value: {k: v for k, v in value.items() if k != "created_at_utc"}
    if comparable(bundle) != comparable(regenerated):
        raise ValueError("Bundle differs from freshly guarded saved stage")
    refs = [bundle_ref]
    for reference in bundle["refs"]:
        path = path_of(reference["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != reference["sha256"]:
            raise ValueError("Bundle reference changed")
        refs.append({"path": str(path), "sha256": reference["sha256"]})
    spec, spec_ref = bound(matches[0])
    transport, transport_ref = read(directory / "transport_result.json")
    declaration, declaration_ref = read(directory.parent / "campaign_declaration.json")
    sidecar, math_refs = read_bound_math(directory, declaration, math_path)
    refs.extend(math_refs)
    raw = bundle["raw_final_or_draft_text"]
    if hashlib.sha256(raw.encode()).hexdigest() != bundle["raw_response_content_sha256"]:
        raise ValueError("Raw text digest mismatch")
    initial = strict(spec["body"]["messages"][1]["content"], exact=True)
    current = independent_allocation(raw)
    prior = independent_allocation(bundle["own_prior_text"]) if bundle.get("own_prior_text") is not None else None
    prior_comparison = None
    if prior is not None:
        prior_dir = directory.parent / (bundle["case_id"] + "__D0")
        prior_math_path = path_of(declaration["output_root"]) / "allocation_math" / (bundle["case_id"] + "__D0.json")
        prior_sidecar, prior_refs = read_bound_math(prior_dir, declaration, prior_math_path)
        refs.extend(prior_refs)
        prior_comparison = compare_sidecar(prior, prior_sidecar, "completed")
    result = {"version": "completion_independent_numeric_audit_1", "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "numeric_facts_prepared_not_semantic_grade", "case_id": bundle["case_id"], "stage": bundle["stage"],
              "independent_current_allocation": current, "independent_own_D0_allocation": prior,
              "accepted_sidecar_comparison": compare_sidecar(current, sidecar, transport["status"]),
              "accepted_own_D0_sidecar_comparison": prior_comparison,
              "visible_market_facts": market_facts(initial["common_market"], initial["public_numeric_fact_index"]),
              "raw_and_derived_relations": allocation_comparisons(current, prior, initial["common_market"]),
              "input_refs": refs + [declaration_ref], "implementation_ref": implementation_ref(), "model_calls": 0, "service_calls": 0,
              "raw_artifacts_modified": False, "semantic_claims_graded": 0,
              "coverage": {"numerical_reference_facts_only": True, "prose_claim_occurrences_extracted": 0,
                           "source_entailment_or_macro_claims_graded": 0, "raw_daily_observations_available": False,
                           "sidecar_match_is_not_semantic_success": True},
              "review_axes": {"errors": "Independent arithmetic facts and sidecar agreement are explicit; prose errors remain for actual review.",
                              "consistency": "Completed semantic guard repeated, exact artifact hashes and sector-array order verified.",
                              "paper_topic": "Numbers support evidence-to-reason-to-allocation reading; no automatic source-entailment or overall score."}}
    for reference in result["input_refs"]:
        if hashlib.sha256(path_of(reference["path"]).read_bytes()).hexdigest() != reference["sha256"]:
            raise ValueError("Input changed during independent numeric audit")
    return result


def static_report(prepared_path):
    manifest, manifest_ref = read(MANIFEST_PATH)
    if manifest_ref["sha256"] != MANIFEST_SHA:
        raise ValueError("Frozen prepared manifest changed")
    path = path_of(prepared_path)
    rows = [r for r in manifest["prepared_cases"] if r["case_id"] in CASES and path_of(r["path"]) == path]
    if len(rows) != 1:
        raise ValueError("Declared completion prepared input required")
    messages, input_ref = bound({k: rows[0][k] for k in ("path", "sha256")})
    payload = strict(messages[1]["content"], exact=True)
    return {"version": "completion_static_visible_numeric_facts_1", "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "static_input_facts_only", "model_outputs_read": 0, "model_calls": 0, "service_calls": 0,
            "visible_market_facts": market_facts(payload["common_market"], payload["public_numeric_fact_index"]),
            "input_refs": [manifest_ref, input_ref], "implementation_ref": implementation_ref(), "semantic_claims_graded": 0}


def safe(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [safe(item) for item in value]
    if isinstance(value, dict):
        return {key: safe(item) for key, item in value.items()}
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--bundle", type=Path)
    group.add_argument("--prepared-input", type=Path)
    parser.add_argument("--math-sidecar", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if bool(args.bundle) != bool(args.math_sidecar):
        parser.error("Completed bundle requires --math-sidecar; static input does not accept it")
    output = path_of(args.output)
    if output.exists() or not output.is_relative_to(REPORT_ROOT):
        raise ValueError("New exclusive completion report path required")
    result = audit_bundle(args.bundle, args.math_sidecar) if args.bundle else static_report(args.prepared_input)
    encoded = json.dumps(safe(result), ensure_ascii=True, allow_nan=False, indent=2) + "\n"
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(encoded)
    print(json.dumps({"status": result["status"], "output": str(output), "model_calls": 0}))


if __name__ == "__main__":
    main()
