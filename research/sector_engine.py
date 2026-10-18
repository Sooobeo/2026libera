"""LIBERA documentary sector task: pure arithmetic and separate offline scoring.

No network, file reads, hidden corpus or model calls occur in these functions.
Only calculate_portfolio is in MODEL_TOOL_FUNCTIONS. A runner must supply the
stage's visible evidence IDs itself; model arguments cannot enlarge that set.
This module never repairs, normalizes, clips, or optimizes a submitted portfolio.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from typing import Any

import numpy as np

ENGINE_VERSION = "4.2.0"
SECTORS = {
    "10": "Energy", "15": "Materials", "20": "Industrials",
    "25": "Consumer Discretionary", "30": "Consumer Staples",
    "35": "Health Care", "40": "Financials", "45": "Information Technology",
    "50": "Communication Services", "55": "Utilities", "60": "Real Estate",
}
SECTOR_CODES = tuple(SECTORS)
# Engineering serialization/linear-algebra checks, not behavioral thresholds.
SUM_TOLERANCE = 1e-6
MATRIX_TOLERANCE = 1e-12


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        out = float(value)
    except (OverflowError, ValueError, TypeError):
        return None
    return out if math.isfinite(out) else None


def _ids(value: Any) -> list[str] | None:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x for x in value):
        return None
    if len(value) != len(set(value)):
        return None
    return value


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def parse_response(raw: Any) -> dict:
    """Strict JSON parsing; duplicate JSON keys are not silently overwritten."""
    def pairs(items):
        answer = {}
        for key, value in items:
            if key in answer:
                raise ValueError("duplicate JSON key")
            answer[key] = value
        return answer

    def constant(_):
        raise ValueError("non-finite JSON number")

    if not isinstance(raw, str):
        return {"ok": False, "value": None, "error": "response_not_text"}
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, TypeError, OverflowError, RecursionError):
        return {"ok": False, "value": None, "error": "invalid_or_ambiguous_JSON"}
    if not isinstance(value, dict):
        return {"ok": False, "value": None, "error": "response_not_object"}
    return {"ok": True, "value": value, "error": None}


def _index_rows(rows: Any) -> dict:
    """Preserve duplicates as invalid entries; never select a preferred row."""
    if not isinstance(rows, list):
        return {"rows": {}, "missing": list(SECTOR_CODES), "duplicates": [],
                "unknown": [], "malformed_count": 1, "container_valid": False}
    recognized = []
    unknown = []
    malformed = 0
    for row in rows:
        if not isinstance(row, dict):
            malformed += 1
            continue
        code = row.get("sector_code")
        if not isinstance(code, str) or code not in SECTORS:
            # Avoid unbounded repr() on malformed objects or huge integers.
            unknown.append(code if isinstance(code, str) else "noncanonical_code_type")
            continue
        recognized.append((code, row))
    counts = Counter(code for code, _ in recognized)
    return {
        "rows": {code: row for code, row in recognized if counts[code] == 1},
        "missing": [code for code in SECTOR_CODES if counts[code] == 0],
        "duplicates": [code for code in SECTOR_CODES if counts[code] > 1],
        "unknown": unknown, "malformed_count": malformed, "container_valid": True,
    }


def validate_weights(rows: Any) -> dict:
    """Require all 11 codes, including explicitly zero-weight sectors."""
    index = _index_rows(rows)
    values = {}
    invalid_numbers, negative, above_one = [], [], []
    for code, row in index["rows"].items():
        value = _number(row.get("weight"))
        if value is None:
            invalid_numbers.append(code)
            continue
        values[code] = value
        if value < 0:
            negative.append(code)
        if value > 1:
            above_one.append(code)
    total = None
    if len(values) == len(SECTORS):
        try:
            total = math.fsum(values.values())
        except OverflowError:
            total = None
    if total is not None and not math.isfinite(total):
        total = None
    residual = total - 1 if total is not None else None
    valid = (index["container_valid"] and not index["missing"]
             and not index["duplicates"] and not index["unknown"]
             and index["malformed_count"] == 0 and not invalid_numbers
             and not negative and not above_one and residual is not None
             and abs(residual) <= SUM_TOLERANCE)
    return {
        "valid": bool(valid), "missing_codes": index["missing"],
        "duplicate_codes": index["duplicates"], "unknown_codes": index["unknown"],
        "malformed_rows": index["malformed_count"],
        "nonfinite_or_nonnumeric_codes": invalid_numbers,
        "negative_weight_codes": negative, "above_one_weight_codes": above_one,
        "raw_sum": total, "raw_budget_residual": residual,
        "sum_tolerance": SUM_TOLERANCE,
        "tolerance_role": "engineering_serialization_precision_only",
        "weights_by_code": values if valid else None,
        "normalized_or_repaired": False,
    }


def _check_constraints(values: dict | None, constraints: Any, visible_ids: set[str]) -> dict:
    if constraints is None:
        constraints = []
    if not isinstance(constraints, list):
        return {"valid_request": False, "errors": ["constraints_not_list"], "checks": []}
    errors, checks = [], []
    seen = set()
    for position, item in enumerate(constraints):
        if not isinstance(item, dict):
            errors.append({"index": position, "error": "constraint_not_object"})
            continue
        code, kind = item.get("sector_code"), item.get("kind")
        bound = _number(item.get("bound"))
        eids = _ids(item.get("evidence_ids"))
        identifier = item.get("constraint_id")
        error = None
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            error = "missing_or_duplicate_constraint_id"
        elif not isinstance(code, str) or code not in SECTORS:
            error = "unknown_sector"
        elif kind not in ("sector_min_weight", "sector_max_weight"):
            error = "unsupported_constraint_kind"
        elif bound is None or not 0 <= bound <= 1:
            error = "invalid_bound"
        elif eids is None or not eids or not set(eids).issubset(visible_ids):
            error = "unavailable_or_invalid_constraint_evidence"
        if error:
            errors.append({"index": position, "error": error})
            continue
        seen.add(identifier)
        raw = values.get(code) if values is not None else None
        violation = (max(0.0, raw - bound) if kind == "sector_max_weight"
                     else max(0.0, bound - raw)) if raw is not None else None
        checks.append({"constraint_id": identifier, "sector_code": code, "kind": kind,
                       "bound": bound, "raw_weight": raw, "violation": violation,
                       "evaluable": raw is not None, "evidence_ids": eids})
    return {"valid_request": not errors, "errors": errors, "checks": checks,
            "interpretation": "Checks supplied constraints only; does not verify their document interpretation."}


def _market_diagnostics(values: dict | None, market: Any) -> dict:
    if market is None:
        return {"status": "not_supplied", "baseline": None, "risk": None, "errors": []}
    if not isinstance(market, dict):
        return {"status": "invalid_market", "baseline": None, "risk": None,
                "errors": ["market_not_object"]}
    errors, baseline, risk = [], None, None
    # Baseline is a public, explicit comparator, never a strategic ground truth.
    supplied_baseline = market.get("baseline_weights")
    if supplied_baseline is not None:
        if isinstance(supplied_baseline, dict):
            baseline_check = validate_weights([{"sector_code": k, "weight": v}
                                               for k, v in supplied_baseline.items()])
        else:
            baseline_check = validate_weights(supplied_baseline)
        if not baseline_check["valid"]:
            errors.append("invalid_baseline_weights")
        elif values is not None:
            b = baseline_check["weights_by_code"]
            tilt = {code: values[code] - b[code] for code in SECTOR_CODES}
            baseline = {"baseline_id": market.get("baseline_id"), "weights": b,
                        "raw_active_weights": tilt,
                        "raw_half_L1_distance": math.fsum(abs(x) for x in tilt.values()) / 2,
                        "baseline_budget_residual": baseline_check["raw_budget_residual"],
                        "interpretation": "descriptive_comparator_not_unique_correct_strategy"}
    supplied_covariance = market.get("covariance")
    if supplied_covariance is not None:
        codes = market.get("sector_codes")
        unit = market.get("covariance_unit")
        try:
            if (not isinstance(codes, list) or len(codes) != len(SECTORS)
                    or any(not isinstance(c, str) for c in codes)
                    or set(codes) != set(SECTOR_CODES)):
                raise ValueError("covariance_code_order")
            if not _text(unit):
                raise ValueError("covariance_unit_required")
            if (not isinstance(supplied_covariance, list)
                    or len(supplied_covariance) != len(SECTORS)
                    or any(not isinstance(row, list) or len(row) != len(SECTORS)
                           or any(_number(x) is None for x in row)
                           for row in supplied_covariance)):
                raise ValueError("covariance_numeric_shape")
            cov = np.asarray(supplied_covariance, dtype=float)
            if not np.allclose(cov, cov.T, atol=MATRIX_TOLERANCE, rtol=0):
                raise ValueError("covariance_not_symmetric")
            min_eigenvalue = float(np.linalg.eigvalsh(cov).min())
            if min_eigenvalue < -MATRIX_TOLERANCE:
                raise ValueError("covariance_not_positive_semidefinite")
            if values is not None:
                w = np.array([values[code] for code in codes])
                with np.errstate(over="ignore", invalid="ignore"):
                    variance = float(w @ cov @ w)
                if not math.isfinite(variance):
                    raise ValueError("nonfinite_portfolio_variance")
                risk = {"raw_variance": variance,
                        "volatility": math.sqrt(variance) if variance >= 0 else None,
                        "covariance_unit": unit, "annualized": False,
                        "negative_roundoff_retained": variance < 0,
                        "minimum_covariance_eigenvalue": min_eigenvalue,
                        "interpretation": "estimated_variability_not_downside_loss_or_future_performance"}
        except (ValueError, TypeError, OverflowError, np.linalg.LinAlgError):
            errors.append("invalid_covariance_or_units")
    return {"status": "invalid_market" if errors else "ok", "baseline": baseline,
            "risk": risk, "errors": errors}


def calculate_portfolio(weights: Any, market: Any = None,
                        visible_evidence_ids: Any = None,
                        submitted_constraints: Any = None) -> dict:
    """Model-facing pure arithmetic; trusted runner supplies visible IDs/market.

    Models may submit weights and parsed constraints; the runner must NOT let the
    model override its frozen market packet or stage visibility capability.
    This tool never receives gold, opens files, retrieves facts or repairs weights.
    """
    visible = _ids([] if visible_evidence_ids is None else visible_evidence_ids)
    if visible is None:
        return {"ok": False, "error": "invalid_visible_evidence_ids", "repaired": False}
    validity = validate_weights(weights)
    constraint_checks = _check_constraints(validity["weights_by_code"],
                                          submitted_constraints, set(visible))
    market_checks = _market_diagnostics(validity["weights_by_code"], market)
    return {"ok": (validity["valid"] and constraint_checks["valid_request"]
                   and market_checks["status"] != "invalid_market"),
            "engine_version": ENGINE_VERSION, "allocation": validity,
            "submitted_constraint_checks": constraint_checks,
            "market_diagnostics": market_checks, "repaired": False,
            "gold_access": False,
            "scope": "arithmetic_on_currently_supplied_inputs_only"}


MODEL_TOOL_FUNCTIONS = {"calculate_sector_portfolio": calculate_portfolio}


def validate_gold(gold: Any) -> dict:
    """Reject incomplete evaluator setup; never shrink the 11-sector denominator."""
    if not isinstance(gold, dict) or not _text(gold.get("source_id")):
        raise ValueError("Gold requires source_id")
    vocabulary = _ids(gold.get("rating_vocabulary"))
    ratings = gold.get("sector_ratings")
    evidence = gold.get("evidence_index")
    if not vocabulary or not isinstance(ratings, dict) or set(ratings) != set(SECTOR_CODES):
        raise ValueError("Gold requires vocabulary and exactly 11 sector ratings")
    if not isinstance(evidence, dict):
        raise ValueError("Gold evidence index required")
    for eid, item in evidence.items():
        if (not _text(eid) or not isinstance(item, dict)
                or item.get("source_id") != gold["source_id"]):
            raise ValueError("Invalid gold evidence identity")
        codes = _ids(item.get("sector_codes"))
        claims = _ids(item.get("claims"))
        if (not codes or not set(codes).issubset(SECTOR_CODES) or not claims
                or not set(claims).issubset({"rating", "reason", "constraint", "scope", "rating_semantics"})):
            raise ValueError("Invalid gold evidence scope")
    for code, item in ratings.items():
        if not isinstance(item, dict) or item.get("rating") not in vocabulary:
            raise ValueError("Invalid source-specific gold label")
        ids = _ids(item.get("evidence_ids"))
        if not ids or any(eid not in evidence or code not in evidence[eid]["sector_codes"]
                          or "rating" not in evidence[eid]["claims"] for eid in ids):
            raise ValueError("Gold rating lacks appropriate source evidence")
        if "reason_evidence_ids" in item:
            reason_ids = _ids(item["reason_evidence_ids"])
            if reason_ids is None or any(eid not in evidence or code not in evidence[eid]["sector_codes"]
                                        or "reason" not in evidence[eid]["claims"] for eid in reason_ids):
                raise ValueError("Invalid gold reason evidence")
    constraints = _check_constraints(None, gold.get("constraints", []), set(evidence))
    if not constraints["valid_request"]:
        raise ValueError("Invalid gold constraints")
    for item in gold.get("constraints") or []:
        for eid in item["evidence_ids"]:
            if ("constraint" not in evidence[eid]["claims"]
                    or item["sector_code"] not in evidence[eid]["sector_codes"]):
                raise ValueError("Gold constraint lacks scoped constraint evidence")
    return gold


def _citation_check(eids: Any, code: str, claim: str, gold: dict,
                    allowed: list[str] | None = None) -> dict:
    ids = _ids(eids)
    if ids is None or not ids:
        return {"valid": False, "status": "missing_or_invalid_citation_list"}
    for eid in ids:
        item = gold["evidence_index"].get(eid)
        if item is None:
            return {"valid": False, "status": "unknown_evidence_id"}
        if code not in item["sector_codes"] or (claim != "allocation_context" and claim not in item["claims"]):
            return {"valid": False, "status": "wrong_sector_or_claim_scope"}
        if allowed is not None and eid not in allowed:
            return {"valid": False, "status": "not_a_rating_reference_for_this_sector"}
    return {"valid": True, "status": "citation_identity_and_scope_match_only"}


def score_response(response: Any, gold: dict, market: Any = None) -> dict:
    """OFFLINE only. Correct labels, citation identity and allocation stay separate.

    A valid citation does not prove the model's free-text reason is supported;
    semantic reason evaluation requires an independent documented review.
    """
    validate_gold(gold)
    source_ok = isinstance(response, dict) and response.get("source_id") == gold["source_id"]
    obj = response if isinstance(response, dict) else {}
    index = _index_rows(obj.get("interpretations"))
    rows = []
    for code in SECTOR_CODES:
        item = index["rows"].get(code)
        expected = gold["sector_ratings"][code]
        predicted = item.get("rating") if item is not None else None
        canonical = predicted.strip() if isinstance(predicted, str) else None
        label_valid = canonical in gold["rating_vocabulary"]
        correct = bool(source_ok and item is not None and label_valid
                       and canonical == expected["rating"])
        citation = _citation_check(item.get("evidence_ids") if item else None,
                                   code, "rating", gold, expected["evidence_ids"])
        reason_ids = item.get("reason_evidence_ids", item.get("evidence_ids")) if item else None
        # An explicitly empty gold reason list means the selected source does not
        # separately state a reason. Never turn that into an AI error or silently
        # fall back to its rating passage as a reason reference.
        gold_reason_ids = expected.get("reason_evidence_ids", [eid for eid, ev in gold["evidence_index"].items()
            if code in ev["sector_codes"] and "reason" in ev["claims"]])
        reason_expected = bool(gold_reason_ids)
        reason_citation = (_citation_check(reason_ids, code, "reason", gold, gold_reason_ids)
                           if reason_expected else {"valid": None, "status": "not_separately_stated_in_selected_source"})
        rows.append({"sector_code": code, "expected_rating": expected["rating"],
                     "predicted_rating": canonical, "label_valid_for_source": label_valid,
                     "label_correct": correct, "missing": code in index["missing"],
                     "duplicate": code in index["duplicates"],
                     "rating_citation_valid": bool(source_ok and item is not None and citation["valid"]),
                     "rating_citation_status": citation["status"],
                     "reason_text_present": _text(item.get("reason")) if item else False,
                     "reason_expected_in_selected_source": reason_expected,
                     "reason_citation_valid": (bool(source_ok and item is not None and reason_citation["valid"])
                                               if reason_expected else None),
                     "reason_citation_status": reason_citation["status"]})
    validity = validate_weights(obj.get("weights"))
    market_checks = _market_diagnostics(validity["weights_by_code"], market)
    constraints = _check_constraints(validity["weights_by_code"], gold.get("constraints", []),
                                     set(gold["evidence_index"]))
    weight_index = _index_rows(obj.get("weights"))
    allocation_reason_records = []
    for code in SECTOR_CODES:
        item = weight_index["rows"].get(code)
        citation = _citation_check(item.get("evidence_ids") if item else None, code, "allocation_context", gold)
        allocation_reason_records.append({"sector_code": code,
            "rationale_present": _text(item.get("rationale")) if item else False,
            "citation_valid": bool(source_ok and item is not None and citation["valid"]),
            "citation_status": citation["status"],
            "semantic_support": "not_automatically_scored_requires_independent_review"})
    # Only source-declared OW/UW semantics can receive a signed-tilt diagnostic.
    # No generic sentiment conversion: Attractive is not Overweight.
    direction = []
    baseline = market_checks.get("baseline")
    semantics = gold.get("allocation_semantics", {})
    if (source_ok and validity["valid"] and baseline is not None
            and semantics.get("kind") == "benchmark_relative_tilt"
            and semantics.get("baseline_id") == baseline["baseline_id"]):
        mapping = semantics.get("label_directions", {})
        if any(k not in gold["rating_vocabulary"] or v not in (-1, 0, 1)
               or isinstance(v, bool) for k, v in mapping.items()):
            raise ValueError("Invalid source-specific tilt semantics")
        for code in SECTOR_CODES:
            label = gold["sector_ratings"][code]["rating"]
            if label not in mapping:
                continue
            target_direction = mapping[label]
            tilt = baseline["raw_active_weights"][code]
            direction.append({"sector_code": code, "source_label": label,
                "expected_direction_if_adopted": target_direction, "raw_active_weight": tilt,
                "signed_tilt": target_direction * tilt if target_direction else None,
                "absolute_tilt_for_neutral": abs(tilt) if target_direction == 0 else None,
                "classification": "continuous_diagnostic_not_strategy_pass_fail"})
    correct_count = sum(item["label_correct"] for item in rows)
    return {
        "engine_version": ENGINE_VERSION, "source_id": gold["source_id"],
        "response_source_id_matches": source_ok,
        "primary_rating": {"correct": correct_count, "expected": len(SECTORS),
                           "accuracy": correct_count / len(SECTORS)},
        "interpretation_structure": {k: v for k, v in index.items() if k != "rows"},
        "rating_records": rows,
        "evidence": {"rating_citation_valid_count": sum(x["rating_citation_valid"] for x in rows),
                     "reason_citation_valid_count": sum(x["reason_citation_valid"] is True for x in rows),
                     "reason_citation_expected": sum(x["reason_expected_in_selected_source"] for x in rows),
                     "reason_not_stated_sector_codes": [x["sector_code"] for x in rows if not x["reason_expected_in_selected_source"]],
                     "reason_text_present_count": sum(x["reason_text_present"] for x in rows),
                     "expected": len(SECTORS),
                     "semantic_reason_support": "requires_independent_review_not_inferred_from_citation_ID"},
        "allocation": validity, "document_constraint_checks": constraints,
        "market_diagnostics": market_checks,
        "allocation_rationale_records": allocation_reason_records,
        "source_tilt_diagnostics": direction,
        "no_unique_correct_weights": True, "composite_score": None,
        "raw_response_must_be_retained_by_runner": True,
    }


def score_text(raw: str, gold: dict, market: Any = None) -> dict:
    parsed = parse_response(raw)
    scored = score_response(parsed["value"] if parsed["ok"] else None, gold, market)
    scored["parse_status"] = {"ok": parsed["ok"], "error": parsed["error"]}
    return scored


def score_bundle(responses: Any, golds: list[dict], market: Any = None) -> dict:
    """Aggregate a prespecified source roster; missing/duplicate sources stay in denominator."""
    for gold in golds:
        validate_gold(gold)
    expected = [gold["source_id"] for gold in golds]
    if not expected or len(expected) != len(set(expected)):
        raise ValueError("Distinct nonempty expected source roster required")
    records = responses if isinstance(responses, list) else []
    by_source = {}
    unexpected = 0
    for record in records:
        sid = record.get("source_id") if isinstance(record, dict) else None
        if not isinstance(sid, str) or sid not in expected:
            unexpected += 1
        else:
            by_source.setdefault(sid, []).append(record)
    scores = []
    for gold in golds:
        candidates = by_source.get(gold["source_id"], [])
        score = score_response(candidates[0] if len(candidates) == 1 else None, gold, market)
        score["source_response_status"] = ("present" if len(candidates) == 1 else
                                           "missing" if not candidates else "duplicate")
        scores.append(score)
    total = len(SECTORS) * len(golds)
    correct = sum(score["primary_rating"]["correct"] for score in scores)
    return {"sources": scores, "primary_rating": {"correct": correct, "expected": total,
            "accuracy": correct / total}, "unexpected_source_records": unexpected,
            "composite_score": None}


def allocation_distance(left: Any, right: Any) -> dict:
    """Same-source workflow or inter-source descriptive distance, never welfare."""
    a, b = validate_weights(left), validate_weights(right)
    if not a["valid"] or not b["valid"]:
        return {"evaluable": False, "raw_half_L1_distance": None,
                "left_valid": a["valid"], "right_valid": b["valid"],
                "missing_pairs_are_not_zero": True}
    delta = {code: b["weights_by_code"][code] - a["weights_by_code"][code]
             for code in SECTOR_CODES}
    return {"evaluable": True, "raw_half_L1_distance": math.fsum(abs(x) for x in delta.values()) / 2,
            "right_minus_left": delta,
            "left_budget_residual": a["raw_budget_residual"],
            "right_budget_residual": b["raw_budget_residual"],
            "interpretation": "descriptive_only_no_quality_or_harm_inference"}


def paired_workflow_distances(responses: dict, source_ids: tuple[str, str]) -> dict:
    """Require four valid allocations for the inter-source R4-minus-R1 contrast.

    responses = {source_id: {"R1": response_object, "R4": response_object}}.
    Missing/invalid pairs remain missing, while individual within-source pairs
    can still be reported if both of their allocations are valid.
    """
    if len(source_ids) != 2 or source_ids[0] == source_ids[1]:
        raise ValueError("Two distinct source IDs required")
    def weights(source, arm):
        source_rows = responses.get(source, {})
        row = source_rows.get(arm) if isinstance(source_rows, dict) else None
        return row.get("weights") if isinstance(row, dict) and row.get("source_id") == source else None
    within = {source: allocation_distance(weights(source, "R1"), weights(source, "R4"))
              for source in source_ids}
    between = {arm: allocation_distance(weights(source_ids[0], arm), weights(source_ids[1], arm))
               for arm in ("R1", "R4")}
    joint = all(item["evaluable"] for item in between.values())
    return {"within_source": within, "between_sources": between,
            "four_valid_allocations": joint,
            "between_source_distance_R4_minus_R1": (
                between["R4"]["raw_half_L1_distance"] - between["R1"]["raw_half_L1_distance"]
                if joint else None),
            "interpretation": "Difference alone does not establish harmful convergence."}
