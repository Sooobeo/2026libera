"""Read-only review after every first-attempt stage, before the next stage.

Instrument defects halt the run. Invalid allocations, unsupported IDs or source
fields remain model outcomes and do not authorize retries or outcome filtering.
Semantic source support still requires the separately recorded AI reading.
"""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path

import remote_sector_runtime as remote
import sector_v492_contract as contract
import sector_v491_contract as original


def ref(path):
    p = Path(path).resolve()
    return {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def review_and_record(spec, stage_dir, result):
    folder = Path(stage_dir)
    expected_source = None
    final_user = contract.strict_json(spec["body"]["messages"][-1]["content"])
    draft_user = contract.strict_json(spec["body"]["messages"][1]["content"])
    if spec["stage"] == "F0":
        expected_source = final_user.get("institution_document")
    else:
        expected_source = draft_user.get("institution_document")
    source_expected = not spec["case_id"].endswith("__C") and (spec["stage"] == "F0" or spec["case_id"].endswith("__E"))
    checks = {
        "stage_directory_matches_case": folder.resolve() == (Path(spec["run_directory"]) / (spec["case_id"] + "__" + spec["stage"])).resolve(),
        "at_most_one_first_attempt": type(result.get("generation_requests_attempted")) is int and result["generation_requests_attempted"] in (0, 1),
        "source_timing_matches_design": bool(expected_source) == source_expected,
        "common_task_schema_visible": all(k in draft_user for k in ("common_context", "common_market", "public_numeric_fact_index", "response_schema")),
        "saved_request_equals_authoritative_request": remote.read(folder / "worker_spec.json") == spec,
        "saved_transport_equals_returned_transport": remote.read(folder / "transport_result.json") == result,
    }
    refs = [ref(folder / name) for name in ("worker_spec.json", "transport_result.json")]
    diagnostics = {"stage_status": result.get("status"), "semantic_support": "pending_separate_AI_reading"}
    response_file = folder / "http_0001_generation/response.json"
    if response_file.is_file():
        response = remote.read(response_file)
        refs.append(ref(response_file))
        expected_ref = result.get("response_artifact")
        checks["response_exactly_bound"] = (expected_ref == ref(response_file) and response == result.get("response"))
        raw = response.get("message", {}).get("content", "")
        try:
            parsed = json.loads(raw, parse_float=Decimal, parse_int=Decimal,
                                parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON: " + value)),
                                object_pairs_hook=strict_pairs)
            rows = parsed["sectors"]
            weights = [r["weight"] for r in rows]
            if not all(isinstance(w, Decimal) and w.is_finite() for w in weights):
                raise ValueError("weights are not finite numbers")
            total = sum(weights, Decimal(0))
            complete = len(rows) == 11 and {r["sector_code"] for r in rows} == set(contract.SECTOR_CODES)
            diagnostics.update(raw_sum_decimal=str(total), raw_budget_residual_decimal=str(total - 1),
                               all_eleven_unique_codes=complete,
                               arithmetic_valid=complete and all(0 <= w <= 1 for w in weights) and abs(total - 1) <= Decimal("0.000001"),
                               reported_source_id=parsed.get("source_id"),
                               source_identity_matches=parsed.get("source_id") == (expected_source["source_id"] if expected_source else None))
            diagnostics["exact_decimal_budget_valid"] = diagnostics["arithmetic_valid"]
            frozen_check = original.validate_weights(contract.extract_raw_weights(contract.strict_json(raw)))
            diagnostics["arithmetic_valid"] = frozen_check["valid"]
            diagnostics["decimal_vs_frozen_float_tolerance_difference"] = diagnostics["exact_decimal_budget_valid"] != frozen_check["valid"]
            diagnostics["eligibility_rule"] = "Frozen binary-float validator; exact Decimal sum is a separate diagnostic, including tolerance-boundary differences."
            visible = contract.evidence_ids(draft_user["common_context"]) | contract.evidence_ids(draft_user["public_numeric_fact_index"])
            if expected_source:
                visible |= contract.evidence_ids(expected_source)
            if spec["stage"] == "F0":
                visible |= contract.evidence_ids(final_user["actual_draft_calculator_feedback"])
            citations = []
            for field, ids in original._citation_lists(parsed):
                unknown = sorted(set(ids) - visible)
                if unknown:
                    citations.append({"field": field, "ids": unknown})
            diagnostics["unavailable_citation_ids"] = citations
            diagnostics["outside_source_rating_vocabulary"] = [r["sector_code"] for r in rows
                if expected_source and r.get("source_label") not in expected_source["rating_vocabulary"]]
            validation_file = folder / "response_contract_validation.json"
            if validation_file.exists():
                validation = remote.read(validation_file)
                refs.append(ref(validation_file))
                arithmetic = validation.get("arithmetic")
                if isinstance(arithmetic, dict):
                    recorded_sum = arithmetic.get("raw_sum")
                    if recorded_sum is not None:
                        checks["independent_sum_matches_worker"] = abs(Decimal(str(recorded_sum)) - total) <= Decimal("0.000000000001")
                    else:
                        checks["worker_sum_unavailable_only_for_incomplete_vector"] = not complete
                        diagnostics["complete_vector_sum_comparison"] = "unavailable_for_missing_duplicate_or_unknown_codes"
                    checks["frozen_eligibility_matches_worker"] = diagnostics["arithmetic_valid"] == arithmetic.get("valid")
                else:
                    diagnostics["worker_arithmetic_unavailable_due_to_schema"] = not validation.get("schema_valid", False)
                if result.get("status") == "completed":
                    checks["completed_stage_has_readable_validation"] = validation.get("continuation_eligible") is True
            elif result.get("status") == "completed":
                checks["completed_stage_has_readable_validation"] = False
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            diagnostics["raw_response_not_complete_numeric_json"] = type(exc).__name__ + ": " + str(exc)
            if result.get("status") == "completed":
                checks["completed_response_independently_parseable"] = False
            # Malformed model output is an observation; it is not a new request.
    elif result.get("status") == "completed":
        checks["completed_stage_has_response"] = False
    passed = all(checks.values())
    review = {
        "version": "v494_per_stage_review_1", "recorded_at_utc": remote.now(),
        "case_id": spec["case_id"], "stage": spec["stage"],
        "instrument_integrity_pass": passed, "checks": checks, "diagnostics": diagnostics,
        "input_refs": refs, "review_axes": {
            "errors": {"instrument_pass": passed, "model_failures_retained": True,
                       "reason": "One first attempt, exact response binding and independent raw sum/ID checks; no corrections or success-driven retries."},
            "consistency": {"pass": passed, "reason": "Saved request/response and source timing checked against the same frozen case."},
            "paper_topic": {"pass": checks["source_timing_matches_design"] and checks["common_task_schema_visible"],
                            "reason": "Institution evidence, stated source reading and actual sector allocation remain the objects of comparison under E/L/C. Numeric validity is reported separately from preservation of institutional meaning.",
                            "semantic_output_verdict": "pending_separate_AI_reading"}},
        "generation_calls": 0, "normalization": False, "retry_authorized": False,
        "limitations": "A valid ID does not establish entailment or factual correctness. Topic boundary checks do not certify semantic success. Failed/missing responses remain in planned denominators."
    }
    remote.save(folder / "stage_review.json", review)
    return review
