"""Deterministic allocation finalization, kept separate from model submissions.

Proportionally scale a complete nonnegative vector, then allocate exactly 10,000
integer units by largest remainder. One unit is 0.01 percentage point. The integer
vector is the final allocation; exact normalized ratios are intermediate evidence.
No inference, clipping, missing-sector filling, or rewriting of model explanations.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, DecimalException
from fractions import Fraction
import hashlib
import json
from pathlib import Path

VERSION = "sector_allocation_finalizer_1"
CODES = ("10", "15", "20", "25", "30", "35", "40", "45", "50", "55", "60")
TOTAL_UNITS = 10000
NUMERIC_RESOURCE_LIMIT = 512
ROOT = Path(__file__).resolve().parents[1]


def strict_json(raw, *, exact=False):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_JSON_key:" + key)
            result[key] = value
        return result

    def constant(value):
        raise ValueError("nonfinite_JSON_constant:" + value)

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant,
                      **({"parse_float": Decimal, "parse_int": Decimal} if exact else {}))


def ratio(value):
    value = Fraction(value)
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def bounded_decimal(value):
    return (isinstance(value, Decimal) and value.is_finite()
            and len(value.as_tuple().digits) <= NUMERIC_RESOURCE_LIMIT
            and abs(value.as_tuple().exponent) <= NUMERIC_RESOURCE_LIMIT
            and abs(value.adjusted()) <= NUMERIC_RESOURCE_LIMIT)


def scaled_decimal(integer, places):
    sign = "-" if integer < 0 else ""
    integer = abs(integer)
    if places == 0:
        return sign + str(integer)
    whole, part = divmod(integer, 10 ** places)
    return f"{sign}{whole}.{part:0{places}d}"


def terminating_decimal(value):
    """Exact finite-decimal rendering; reject nonterminating ratios explicitly."""
    value = Fraction(value)
    denominator, twos, fives = value.denominator, 0, 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        raise ValueError("nonterminating_ratio_requires_fraction_representation")
    places = max(twos, fives)
    integer = value.numerator * (10 ** places // value.denominator)
    return scaled_decimal(integer, places)


def _constraints(parsed, raw, normalized, units):
    """Audit submitted bounds without pretending normalization solves them."""
    bounds = parsed.get("submitted_constraints", [])
    if not isinstance(bounds, list):
        return {"status": "unassessable", "reason": "submitted_constraints_not_array"}
    records, seen = [], set()
    for index, bound in enumerate(bounds):
        if (not isinstance(bound, dict) or not isinstance(bound.get("constraint_id"), str)
                or not bound["constraint_id"] or bound["constraint_id"] in seen
                or bound.get("sector_code") not in CODES
                or bound.get("kind") not in ("sector_min_weight", "sector_max_weight")
                or not bounded_decimal(bound.get("bound"))
                or not 0 <= bound["bound"] <= 1
                or not isinstance(bound.get("evidence_ids"), list) or not bound["evidence_ids"]
                or any(not isinstance(eid, str) or not eid for eid in bound["evidence_ids"])):
            records.append({"index": index, "status": "unassessable",
                            "reason": "malformed_or_duplicate_constraint_identity_bound_or_evidence"})
            continue
        seen.add(bound["constraint_id"])
        code, minimum, limit = bound["sector_code"], bound["kind"] == "sector_min_weight", Fraction(bound["bound"])
        def satisfies(value):
            return value >= limit if minimum else value <= limit
        records.append({"index": index, "constraint_id": bound.get("constraint_id"),
                        "sector_code": code, "kind": bound["kind"], "bound_exact": ratio(limit),
                        "claimed_evidence_ids": bound["evidence_ids"],
                        "evidence_visibility_and_support": "not_verified_by_budget_finalizer",
                        "status": "checked_without_enforcement",
                        "raw_satisfied": satisfies(raw[code]),
                        "normalized_satisfied": satisfies(normalized[code]),
                        "final_satisfied": satisfies(Fraction(units[code], TOTAL_UNITS))})
    return {"status": "checked_without_enforcement", "records": records,
            "unassessable_count": sum(r["status"] == "unassessable" for r in records),
            "final_violations": [r["index"] for r in records if r.get("final_satisfied") is False],
            "scope": "Budget finalization is not an optimizer for submitted bounds and does not verify source support; original claims and violations remain visible."}


def finalize_content(raw):
    result = {"version": VERSION, "status": "unavailable", "reasons": [],
              "rows": [], "generation_calls": 0, "original_content_modified": False,
              "policy": {"normalization": "positive_sum_proportional_scaling",
                         "rounding": "largest_remainder_to_10000_integer_units",
                         "tie_order": list(CODES), "one_unit_percentage_points": "0.01",
                         "final_allocation_representation": "integer_units_over_10000",
                         "numeric_resource_limit": {"coefficient_digits": NUMERIC_RESOURCE_LIMIT,
                                                    "absolute_exponent": NUMERIC_RESOURCE_LIMIT,
                                                    "absolute_adjusted_exponent": NUMERIC_RESOURCE_LIMIT,
                                                    "on_excess": "unavailable_without_clipping"},
                         "above_one_raw_weights": "retained_as_raw_error_but_scalable",
                         "no_claim_of_semantic_repair": True}}
    try:
        if not isinstance(raw, str):
            raise ValueError("assistant_content_not_text")
        if len(raw) > 2000000:
            raise ValueError("engineering_resource_limit:response_length")
        result["raw_content_sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        parsed = strict_json(raw, exact=True)
        if not isinstance(parsed, dict):
            raise ValueError("entire_response_not_single_JSON_object")
        rows = parsed.get("sectors")
        if not isinstance(rows, list) or len(rows) != len(CODES):
            raise ValueError("exactly_eleven_sector_rows_required")
        weights = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("sector_row_not_object")
            code, value = row.get("sector_code"), row.get("weight")
            if not isinstance(code, str) or code not in CODES:
                raise ValueError("unknown_or_noncanonical_sector_code")
            if code in weights:
                raise ValueError("duplicate_sector_code:" + code)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError("weight_not_finite_JSON_number:" + code)
            if not bounded_decimal(value):
                raise ValueError("engineering_resource_limit:weight_numeric_size:" + code)
            if value < 0:
                raise ValueError("negative_weight:" + code)
            weights[code] = Fraction(value)
        if set(weights) != set(CODES):
            raise ValueError("incomplete_sector_vector")
        total = sum(weights.values(), Fraction())
        if total <= 0:
            raise ValueError("positive_weight_sum_required")
        normalized = {code: weights[code] / total for code in CODES}
        quotas = {code: normalized[code] * TOTAL_UNITS for code in CODES}
        units = {code: quotas[code].numerator // quotas[code].denominator for code in CODES}
        remaining = TOTAL_UNITS - sum(units.values())
        rank = sorted(CODES, key=lambda code: (-(quotas[code] - units[code]), CODES.index(code)))
        if not 0 <= remaining < len(CODES):
            raise ArithmeticError("largest_remainder_residual_outside_proven_range")
        recipients = rank[:remaining]
        for code in recipients:
            units[code] += 1
        if sum(units.values()) != TOTAL_UNITS or any(unit < 0 for unit in units.values()):
            raise ArithmeticError("final_integer_budget_invariant_failed")
        result.update(status="finalized", raw_sum_exact_decimal=terminating_decimal(total),
                      raw_budget_residual_exact_decimal=terminating_decimal(total - 1),
                      raw_budget_residual_percentage_points=terminating_decimal((total - 1) * 100),
                      raw_budget_within_1e_6=abs(total - 1) <= Fraction(1, 1000000),
                      raw_above_one_codes=[c for c in CODES if weights[c] > 1],
                      normalization_applied=total != 1, normalization_multiplier_exact=ratio(1 / total),
                      rounding_unit_recipients=recipients,
                      final_total_units=TOTAL_UNITS, final_total_weight_exact_decimal="1.0000",
                      final_total_percent="100.00")
        for code in CODES:
            final = Fraction(units[code], TOTAL_UNITS)
            result["rows"].append({"sector_code": code,
                "raw_weight_exact_decimal": terminating_decimal(weights[code]),
                "normalized_weight_exact": ratio(normalized[code]),
                "final_units": units[code], "final_weight_decimal": scaled_decimal(units[code], 4),
                "final_percent": scaled_decimal(units[code], 2),
                "normalization_delta_exact": ratio(normalized[code] - weights[code]),
                "rounding_delta_exact": ratio(final - normalized[code]),
                "total_delta_exact_decimal": terminating_decimal(final - weights[code])})
        result["submitted_constraint_diagnostics"] = _constraints(parsed, weights, normalized, units)
        result["interpretation_limits"] = [
            "The normalized ratios preserve raw relative proportions; integer rounding can break exact ties or set a tiny positive weight to zero.",
            "Raw model arithmetic failures remain failures of the raw submission. Budget repair is not evidence that original explanations or citations were correct.",
            "Normalization can change above/below-benchmark and D0-to-F0 directions; inspect raw and derived comparisons separately.",
            "This post-start user-directed derived allocation does not replace the frozen raw pilot endpoint or missing-case denominator."]
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, DecimalException, UnicodeError) as exc:
        result.update(status="unavailable", rows=[], reasons=[str(exc)])
    return result


def read_artifact(path):
    path = Path(path).resolve()
    data = path.read_bytes()
    return strict_json(data.decode("utf-8-sig")), {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}


def finalize_stage(stage_dir):
    """Use only a completed, bound response; never inspect an active stream."""
    stage_dir = Path(stage_dir).resolve()
    transport, transport_ref = read_artifact(stage_dir / "transport_result.json")
    spec, spec_ref = read_artifact(stage_dir / "worker_spec.json")
    if (stage_dir.name != spec["case_id"] + "__" + spec["stage"]
            or stage_dir.parent != Path(spec["run_directory"]).resolve()):
        raise ValueError("stage_directory_identity_mismatch")
    common = {"case_id": spec["case_id"], "stage": spec["stage"],
              "input_refs": [transport_ref, spec_ref],
              "observed_transport_status": transport.get("status"),
              "generation_requests_attempted": transport.get("generation_requests_attempted"),
              "stage_role": "derived_final_allocation" if spec["stage"] == "F0" else "draft_diagnostic_not_a_final_submission"}
    if type(common["generation_requests_attempted"]) is not int or common["generation_requests_attempted"] not in (0, 1):
        raise ValueError("first_attempt_only_accounting_required")
    if transport.get("status") != "completed":
        return {**common, "status": "unavailable", "reasons": ["normal_completed_transport_required"],
                "rows": [], "generation_calls": 0, "original_content_modified": False}
    response, response_ref = read_artifact(stage_dir / "http_0001_generation/response.json")
    if (transport.get("response_artifact") != response_ref or transport.get("response") != response
            or transport.get("generation_requests_attempted") != 1
            or transport.get("system_integrity_incident") is not False
            or transport.get("continuation_eligible") is not True
            or transport.get("artifact_preservation_error") is not None
            or transport.get("accounting_artifact_errors") != {}
            or transport.get("unexpected_generation_evidence_in_render") is not False
            or response.get("model") != spec["body"]["model"]
            or response.get("message", {}).get("role") != "assistant"
            or response.get("message", {}).get("thinking")
            or response.get("message", {}).get("tool_calls")
            or response.get("done") is not True or response.get("done_reason") != "stop"):
        raise ValueError("completed_response_binding_or_status_mismatch")
    review, review_ref = read_artifact(stage_dir / "stage_review.json")
    if (review.get("case_id") != spec["case_id"] or review.get("stage") != spec["stage"]
            or review.get("instrument_integrity_pass") is not True
            or response_ref not in review.get("input_refs", [])
            or spec_ref not in review.get("input_refs", []) or transport_ref not in review.get("input_refs", [])):
        raise ValueError("completed_stage_integrity_review_binding_mismatch")
    common["input_refs"] += [response_ref, review_ref]
    result = {**finalize_content(response.get("message", {}).get("content")), **common}
    for reference in common["input_refs"]:
        if hashlib.sha256(Path(reference["path"]).read_bytes()).hexdigest() != reference["sha256"]:
            raise ValueError("source_artifact_changed_during_finalization")
    return result


def compare_finalized(left, right):
    result = {"left": left["case_id"] + ":" + left["stage"],
              "right": right["case_id"] + ":" + right["stage"],
              "status": "unavailable", "total_variation_exact": None,
              "final_unit_differences": None,
              "scope": "Derived integer allocations only; no claim about original model arithmetic or explanation correctness."}
    if left["status"] != "finalized" or right["status"] != "finalized":
        result["reasons"] = [{"side": name, "reasons": item.get("reasons", [])}
                             for name, item in (("left", left), ("right", right))
                             if item["status"] != "finalized"]
        return result
    lmap = {r["sector_code"]: r["final_units"] for r in left["rows"]}
    rmap = {r["sector_code"]: r["final_units"] for r in right["rows"]}
    delta = {c: lmap[c] - rmap[c] for c in CODES}
    distance = Fraction(sum(abs(v) for v in delta.values()), 2 * TOTAL_UNITS)
    result.update(status="computed", total_variation_exact=ratio(distance),
                  total_variation_exact_decimal=terminating_decimal(distance),
                  final_unit_differences=delta)
    return result


def finalize_run(run_dir):
    """After termination, retain all ten slots and five planned final allocations."""
    run_dir = Path(run_dir).resolve()
    summary, summary_ref = read_artifact(run_dir / "pilot_summary.json")
    cases = ("fidelity_q2_2026__E", "fidelity_q2_2026__L", "ubs_june_2026__E",
             "ubs_june_2026__L", "common_market_only__C")
    if summary.get("status") not in ("stopped", "pilot_attempt_sequence_finished"):
        raise ValueError("terminal_run_summary_required")
    if [row.get("case_id") for row in summary.get("cases", [])] != list(cases):
        raise ValueError("all_five_declared_cases_required")
    for field in ("main_model_calls", "automatic_retries", "post_final_calls"):
        if type(summary.get(field)) is not int or summary[field] != 0:
            raise ValueError("pilot_first_attempt_scope_required:" + field)
    stages = []
    expected_dirs, attempted = set(), 0
    for case in summary["cases"]:
        records = case.get("stages", [])
        names = [r["stage"] for r in records]
        if names not in ([], ["D0"], ["D0", "F0"]):
            raise ValueError("unexpected_stage_sequence")
        records_by_stage = {r["stage"]: r for r in records}
        for stage in ("D0", "F0"):
            directory = case["case_id"] + "__" + stage
            if stage in names:
                expected_dirs.add(directory)
                item = finalize_stage(run_dir / directory)
                record = records_by_stage[stage]
                if (type(record.get("generation_requests_attempted")) is not int
                        or item["generation_requests_attempted"] != record["generation_requests_attempted"]
                        or item["observed_transport_status"] != record["status"]):
                    raise ValueError("summary_transport_accounting_mismatch")
                attempted += item["generation_requests_attempted"]
                stages.append(item)
            else:
                stages.append({"case_id": case["case_id"], "stage": stage,
                               "status": "unavailable", "reasons": ["not_attempted"], "rows": []})
    observed_dirs = {p.name for p in run_dir.iterdir() if p.is_dir() and p.name.endswith(("__D0", "__F0"))}
    if observed_dirs != expected_dirs:
        raise ValueError("summary_stage_directory_accounting_mismatch")
    if type(summary.get("generation_requests_attempted")) is not int or attempted != summary["generation_requests_attempted"] or attempted > 10:
        raise ValueError("aggregate_attempt_accounting_mismatch")
    if hashlib.sha256(Path(summary_ref["path"]).read_bytes()).hexdigest() != summary_ref["sha256"]:
        raise ValueError("terminal_summary_changed_during_finalization")
    lookup = {(item["case_id"], item["stage"]): item for item in stages}
    def pair(left, right):
        return compare_finalized(lookup[(left, "F0")], lookup[(right, "F0")])
    return {"version": VERSION, "run_summary_ref": summary_ref, "stage_records": stages,
            "planned_final_allocations": 5, "planned_stage_slots": 10,
            "first_attempt_requests": attempted,
            "finalized_finals": sum(s["stage"] == "F0" and s["status"] == "finalized" for s in stages),
            "derived_comparisons": {
                "within_source": [pair(cases[0], cases[1]), pair(cases[2], cases[3])],
                "between_source": [pair(cases[0], cases[2]), pair(cases[1], cases[3])],
                "shared_control": [pair(case, cases[-1]) for case in cases[:-1]],
                "own_D0_F0": [compare_finalized(lookup[(case, "F0")], lookup[(case, "D0")]) for case in cases]},
            "scope": "Post-start user-requested derived arithmetic supplement; raw frozen evaluation remains unchanged.",
            "generation_calls": 0, "missing_finals_replaced": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--stage-dir", type=Path)
    source.add_argument("--run-dir", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source_dir = (args.stage_dir or args.run_dir).resolve()
    raw_root = source_dir.parent if args.stage_dir else source_dir
    output = args.output.resolve()
    if output == raw_root or output.is_relative_to(raw_root):
        parser.error("Derived output must be separate from immutable raw artifacts")
    result = finalize_stage(source_dir) if args.stage_dir else finalize_run(source_dir)
    result.update(created_at_utc=datetime.now(timezone.utc).isoformat(),
                  finalizer_ref={"path": str(Path(__file__).resolve()),
                                 "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    # Fully serialize before exclusive creation, including escaped lone surrogate
    # values from untrusted JSON, so serialization cannot leave a partial receipt.
    encoded = (json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(encoded)
    print(json.dumps({"output": str(output), "status": result.get("status"),
                      "finalized_finals": result.get("finalized_finals"), "generation_calls": 0}))


if __name__ == "__main__":
    main()
