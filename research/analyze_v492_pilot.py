"""Offline arithmetic report for a completed, first-attempt v4.9.2 pilot.

No model calls, semantic coding, allocation repair, normalization, or retries.
The five planned finals remain the denominator even when none is observed.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator

VERSION = "analyze_v492_pilot_1"
ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "research/v492_evaluation_protocol_20261019_r2.json"
PROTOCOL_SHA = "807def444cc36d4a702321401a52e653b3f9a304383911e13f3c0389183086f1"
SCHEMA = "data/sector_protocol/v491_design_20261019/response_schema.json"
SCHEMA_SHA = "944a232de9f4a1e9ae672b172196aa906077ee03c3f6bf2ab06ad032d6d0b147"
CODES = ("10", "15", "20", "25", "30", "35", "40", "45", "50", "55", "60")
CASES = tuple(s + "__" + a for s in ("fidelity_q2_2026", "ubs_june_2026")
              for a in ("E", "L")) + ("common_market_only__C",)
STAGES = ("D0", "F0")
TOLERANCE = 1e-6
POLICY = {
    "ko": "보존된 응답 전체가 단일 JSON 객체로 파싱되고 11개 원시 비중이 완전·유한·비음수이며 합계 허용오차를 통과하면 거리를 계산한다. 설명 필드 schema 오류와 length 종료는 별도 표시하며 의미적 성공이나 정상 완료로 승격하지 않는다. 불완전 텍스트에서 부분 벡터를 추출하거나 보정하지 않는다.",
    "en": "Distance eligibility uses the entire preserved JSON object and complete finite nonnegative raw eleven-vector passing the budget tolerance. Explanatory schema failure and length stop are separate flags, not semantic or completion success. No partial-vector extraction from incomplete text and no repair.",
    "raw_allocation_validity": "The existing calculator also flags weights above one as invalid. The frozen distance eligibility explicitly requires nonnegative weights and budget tolerance; above-one is reported separately, without silently adding a stricter distance exclusion.",
    "numeric_arithmetic": "Budget eligibility uses math.fsum and the inherited 1e-6 tolerance. Distances and signed differences additionally retain exact decimal values from the serialized raw JSON numbers; they are never normalized.",
    "limits": ["No semantic score or composite score", "No institutional numeric gold weights",
               "No p-values, bootstrap intervals, population causal effects or equivalence claims",
               "D0 and eleven sectors are not independent replications",
               "One shared C is not four independent controls",
               "Equal-weight, GMV and market reference are diagnostic comparators, not strategy winners"],
}


def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_loads(raw, *, decimal=False):
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError("duplicate_JSON_key")
            result[k] = v
        return result
    def constant(value):
        raise ValueError("nonfinite_JSON_constant:" + value)
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant,
                       **({"parse_float": Decimal, "parse_int": Decimal} if decimal else {}))
    if not decimal:
        json.dumps(value, allow_nan=False)
    return value


def read_json(path):
    raw = Path(path).read_bytes()
    return strict_loads(raw.decode("utf-8-sig")), {"path": str(Path(path).resolve()), "sha256": sha_bytes(raw)}


def pinned(path, digest):
    value, ref = read_json(path)
    if ref["sha256"] != digest:
        raise ValueError("frozen_input_hash_mismatch:" + str(path))
    return value, ref


def exact_decimal(value):
    """All inputs originate in finite decimal JSON, so a terminating result exists."""
    value = Fraction(value)
    with localcontext() as ctx:
        ctx.prec = len(str(abs(value.numerator))) + len(str(value.denominator)) + 10
        return format(Decimal(value.numerator) / Decimal(value.denominator), "f")


def vector_metrics(parsed, exact_parsed=None):
    rows = parsed.get("sectors") if isinstance(parsed, dict) else None
    exact_rows = exact_parsed.get("sectors") if isinstance(exact_parsed, dict) else rows
    recognized, unknown, malformed = [], [], 0
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                malformed += 1
            elif type(row.get("sector_code")) is not str or row["sector_code"] not in CODES:
                code = row.get("sector_code")
                unknown.append(code if isinstance(code, str) else "noncanonical_code_type")
            else:
                recognized.append(row)
    else:
        malformed = 1
    counts = Counter(row["sector_code"] for row in recognized)
    missing = [c for c in CODES if counts[c] == 0]
    duplicate = [c for c in CODES if counts[c] > 1]
    values, exact, bad = {}, {}, []
    exact_index = {r.get("sector_code"): r for r in exact_rows if isinstance(r, dict)
                   and isinstance(r.get("sector_code"), str)} if isinstance(exact_rows, list) else {}
    for row in recognized:
        code, value = row["sector_code"], row.get("weight")
        if counts[code] != 1:
            continue
        try:
            ok = type(value) in (int, float) and math.isfinite(float(value))
        except (OverflowError, ValueError):
            ok = False
        if not ok:
            bad.append(code)
            continue
        values[code] = value
        exact[code] = Fraction(str(exact_index[code]["weight"]))
    complete = not (missing or duplicate or unknown or malformed or bad) and len(values) == 11
    negative = [c for c in CODES if c in values and values[c] < 0]
    above = [c for c in CODES if c in values and values[c] > 1]
    total = residual = None
    if complete:
        try:
            total = math.fsum(values[c] for c in CODES)
            residual = total - 1 if math.isfinite(total) else None
            if residual is None:
                total = None
        except OverflowError:
            pass
    budget = residual is not None and abs(residual) <= TOLERANCE
    reasons = (["incomplete_or_nonfinite_vector"] if not complete else [])
    if negative:
        reasons.append("negative_raw_weight")
    if not budget:
        reasons.append("budget_check_failed_or_unavailable")
    eligible = complete and not negative and budget
    exact_sum = sum(exact.values(), Fraction()) if complete else None
    return {"complete_vector": bool(complete), "missing_codes": missing, "duplicate_codes": duplicate,
            "unknown_codes": unknown, "malformed_rows": malformed, "invalid_numeric_codes": bad,
            "negative_weight_codes": negative, "above_one_weight_codes": above,
            "raw_weights": values, "raw_weights_exact_decimal": {c: exact_decimal(v) for c, v in exact.items()},
            "zero_weight_codes": [c for c in CODES if c in values and values[c] == 0],
            "positive_weight_codes": [c for c in CODES if c in values and values[c] > 0],
            "raw_sum": total, "raw_budget_residual": residual,
            "raw_sum_exact_decimal": exact_decimal(exact_sum) if exact_sum is not None else None,
            "raw_residual_exact_decimal": exact_decimal(exact_sum - 1) if exact_sum is not None else None,
            "budget_check_passed": bool(budget), "sum_tolerance": TOLERANCE,
            "valid_raw_allocation": bool(eligible and not above), "distance_eligible": bool(eligible),
            "distance_null_reasons": reasons, "normalized_or_repaired": False}


def parse_output(raw, schema):
    result = {"parseable": False, "schema_valid": False, "schema_errors": [],
              "raw_text_sha256": sha_bytes(raw.encode("utf-8")) if isinstance(raw, str) else None,
              "vector": vector_metrics(None)}
    try:
        if not isinstance(raw, str):
            raise ValueError("assistant_content_not_text")
        value = strict_loads(raw)
        if not isinstance(value, dict):
            raise ValueError("entire_response_not_single_JSON_object")
        precise = strict_loads(raw, decimal=True)
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        result["parse_error"] = str(exc)
        result["vector"]["distance_null_reasons"] = ["entire_response_JSON_unavailable"]
        return result
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda e: str(list(e.path)))
    result.update(parseable=True, schema_valid=not errors,
                  schema_errors=[{"path": list(e.path), "message": e.message} for e in errors],
                  vector=vector_metrics(value, precise), reported_source_id=value.get("source_id"))
    return result


def compare(left, right, left_id, right_id):
    """left minus right; raw deltas survive invalid budget, distances do not."""
    result = {"left": left_id, "right": right_id, "distance": None,
              "distance_exact_decimal": None, "raw_difference": None,
              "raw_difference_exact_decimal": None, "null_reasons": [],
              "left_raw_sum": left.get("raw_sum"), "right_raw_sum": right.get("raw_sum"),
              "normalized_or_repaired": False}
    if left.get("complete_vector") and right.get("complete_vector"):
        delta = {c: Fraction(left["raw_weights_exact_decimal"][c]) -
                    Fraction(right["raw_weights_exact_decimal"][c]) for c in CODES}
        result["raw_difference_exact_decimal"] = {c: exact_decimal(v) for c, v in delta.items()}
        # An unrepresentable binary-float delta remains exact text, never Infinity.
        result["raw_difference"] = {c: float(v) if abs(v) <= Fraction(str(float.fromhex("0x1.fffffffffffffp+1023"))) else None
                                    for c, v in delta.items()}
    for name, item in ((left_id, left), (right_id, right)):
        if not item.get("distance_eligible"):
            result["null_reasons"].append({"vector": name, "reasons": item.get("distance_null_reasons", ["missing_vector"])})
    if not result["null_reasons"]:
        distance = sum((abs(v) for v in delta.values()), Fraction()) / 2
        result["distance"], result["distance_exact_decimal"] = float(distance), exact_decimal(distance)
        result["interpretation"] = ("total_variation_of_exact_unit_sum_raw_vectors" if
            Fraction(left["raw_sum_exact_decimal"]) == Fraction(right["raw_sum_exact_decimal"]) == 1 else
            "numerical_approximation_to_total_variation_raw_sums_not_exactly_one")
    else:
        result["interpretation"] = "no_valid_portfolio_distance; any raw component differences are arithmetic diagnostics only"
    return result


def declared_evidence_ids(value):
    found = set()
    if isinstance(value, dict):
        for name in ("fact_id", "evidence_id"):
            if isinstance(value.get(name), str):
                found.add(value[name])
        columns, rows = value.get("columns"), value.get("rows")
        if isinstance(columns, list) and isinstance(rows, list):
            for row in rows:
                if isinstance(row, list) and len(row) == len(columns):
                    found.update(declared_evidence_ids(dict(zip(columns, row))))
        for child in value.values():
            found.update(declared_evidence_ids(child))
    elif isinstance(value, list):
        for child in value:
            found.update(declared_evidence_ids(child))
    return found


def stage_evidence(spec):
    messages = spec["body"]["messages"]
    # Never collect evidence declarations from the model's prior assistant text.
    payloads = [strict_loads(m["content"]) for m in messages if m.get("role") == "user"]
    visible, source_ids = set(), []
    for payload in payloads:
        for key in ("common_context", "common_market", "public_numeric_fact_index", "institution_document",
                    "actual_draft_calculator_feedback"):
            if key in payload:
                visible.update(declared_evidence_ids(payload[key]))
        if "institution_document" in payload:
            source_ids.append(payload["institution_document"].get("source_id"))
    return visible, source_ids


def citation_diagnostics(raw, allowed):
    value, cited, malformed = strict_loads(raw), [], []
    def walk(item, path):
        if isinstance(item, dict):
            for key, child in item.items():
                if key in ("source_evidence_ids", "decision_evidence_ids", "evidence_ids"):
                    if isinstance(child, list) and all(isinstance(x, str) for x in child):
                        cited.extend({"path": path + [key], "id": x} for x in child)
                    else:
                        malformed.append(path + [key])
                else:
                    walk(child, path + [key])
        elif isinstance(item, list):
            for index, child in enumerate(item):
                walk(child, path + [index])
    walk(value, [])
    return {"allowed_id_count": len(allowed), "citation_occurrences": len(cited),
            "unavailable_citations": [x for x in cited if x["id"] not in allowed],
            "malformed_id_fields": malformed, "semantic_support_verified": False}


def load_stage(run_dir, case, stage, record, schema, artifacts):
    count = record.get("generation_requests_attempted", 0) if record else 0
    if type(count) is not int or count not in (0, 1):
        raise ValueError("stage_attempt_count_must_be_zero_or_one")
    target = run_dir / (case + "__" + stage)
    visible_source = case.endswith("__E") or (case.endswith("__L") and stage == "F0")
    expected_source = case.rsplit("__", 1)[0] if visible_source else None
    result = {"case_id": case, "stage": stage, "source_conditioned": visible_source,
              "source_fidelity_applicability": "AI_review_pending" if visible_source else "not_applicable",
              "generation_requests_attempted": count, "attempted": count == 1,
              "recorded_status": record.get("status") if record else "not_attempted",
              "transport_complete": False, "response_done": None, "done_reason": None,
              "readable_partial": False, "infrastructure_failure": False,
              "artifact_integrity_failure": False,
              "system_integrity_incident": None,
              "response_artifact_bound": False, "citation_visibility": None,
              **parse_output(None, schema)}
    if record and record.get("status") not in ("completed", "model_structure_failure", "output_limit_reached", "not_attempted"):
        result["infrastructure_failure"] = True
    result["partial_artifacts"] = []
    for filename in (("http_0001_generation/assembled_text.json", "http_0001_generation/events.jsonl") if count else ()):
        path = target / filename
        if path.is_file():
            saved = path.read_bytes()
            ref = {"path": str(path.resolve()), "sha256": sha_bytes(saved), "bytes": len(saved)}
            artifacts.append(ref)
            result["partial_artifacts"].append(ref)
            if filename.endswith("assembled_text.json"):
                try:
                    assembled = strict_loads(saved.decode("utf-8-sig"))
                    # Availability only: never parse the assembled text as an allocation.
                    result["partial_text_available"] = (isinstance(assembled, dict) and
                        isinstance(assembled.get("content"), str) and bool(assembled["content"]))
                    result["partial_thinking_available"] = (isinstance(assembled, dict) and
                        isinstance(assembled.get("thinking"), str) and bool(assembled["thinking"]))
                except (ValueError, UnicodeError):
                    result["partial_text_available"] = False
            elif filename.endswith("events.jsonl"):
                complete_lines, content_fragments = 0, 0
                for line in saved.splitlines():
                    try:
                        event = strict_loads(line.decode("utf-8"))
                        message = event.get("event", {}).get("message", {})
                        complete_lines += 1
                        if isinstance(message.get("content"), str) and message["content"]:
                            content_fragments += 1
                    except (ValueError, UnicodeError, AttributeError):
                        pass  # The incomplete line remains in the hashed raw file.
                result["partial_event_complete_lines"] = complete_lines
                result["partial_event_content_fragments"] = content_fragments
    if count == 0:
        result["missing_reason"] = "generation_not_attempted"
        result["unexpected_response_without_attempt"] = (target / "http_0001_generation/response.json").exists()
        if record and (target / "transport_result.json").is_file():
            try:
                transport, ref = read_json(target / "transport_result.json")
                artifacts.append(ref)
                if not isinstance(transport, dict) or type(transport.get("generation_requests_attempted")) is not int or transport["generation_requests_attempted"] != 0:
                    raise ValueError("zero_call_transport_accounting_mismatch")
                result["transport_status"] = transport.get("status")
                result["system_integrity_incident"] = transport.get("system_integrity_incident")
                result["infrastructure_failure"] = result["infrastructure_failure"] or transport.get("system_integrity_incident") is True
            except (OSError, ValueError, TypeError) as exc:
                result["artifact_issue"] = str(exc)
                result["artifact_integrity_failure"] = True
        return result
    def read(name):
        value, ref = read_json(target / name)
        artifacts.append(ref)
        return value, ref
    try:
        transport, _ = read("transport_result.json")
        if not isinstance(transport, dict):
            raise ValueError("transport_record_not_object")
        if type(transport.get("generation_requests_attempted")) is not int or transport["generation_requests_attempted"] != count:
            raise ValueError("transport_attempt_accounting_mismatch")
        result["transport_status"] = transport.get("status")
        result["system_integrity_incident"] = transport.get("system_integrity_incident")
        result["infrastructure_failure"] = result["infrastructure_failure"] or transport.get("system_integrity_incident") is True or transport.get("status") == "case_timeout"
        response_path = target / "http_0001_generation/response.json"
        if not response_path.is_file() and transport.get("response") is None and transport.get("response_artifact") is None:
            result["missing_reason"] = "no_preserved_whole_response_from_first_attempt"
            result["readable_partial"] = result.get("partial_text_available", False) or result.get("partial_event_content_fragments", 0) > 0
            result["vector"]["distance_null_reasons"] = ["entire_response_JSON_unavailable"]
            return result
        response, response_ref = read("http_0001_generation/response.json")
        if not isinstance(response, dict) or not isinstance(response.get("message"), dict):
            raise ValueError("response_envelope_or_message_not_object")
        expected = transport.get("response_artifact")
        bound = isinstance(expected, dict) and expected.get("sha256") == response_ref["sha256"] and Path(expected.get("path", "")).resolve() == Path(response_ref["path"])
        bound = bound and response == transport.get("response")
        result["response_artifact_bound"] = bool(bound)
        if not bound:
            raise ValueError("response_artifact_binding_failed")
        result["response_done"], result["done_reason"] = response.get("done"), response.get("done_reason")
        result["transport_complete"] = response.get("done") is True
        raw = response.get("message", {}).get("content")
        spec, _ = read("worker_spec.json")
        if spec.get("case_id") != case or spec.get("stage") != stage:
            raise ValueError("worker_spec_case_stage_mismatch")
        allowed, supplied = stage_evidence(spec)
        result["supplied_source_ids"] = supplied
        result["C_source_free_input"] = not supplied if case.endswith("__C") else None
        if (set(supplied) != {expected_source} if visible_source else bool(supplied)):
            raise ValueError("actual_source_visibility_differs_from_declared_stage")
        result.update(parse_output(raw, schema))
        result["readable_partial"] = isinstance(raw, str) and bool(raw) and (response.get("done") is not True or response.get("done_reason") == "length")
        if result["parseable"]:
            result["citation_visibility"] = citation_diagnostics(raw, allowed)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result["artifact_issue"] = str(exc)
        result["artifact_integrity_failure"] = True
        if not result["response_artifact_bound"]:
            result["vector"]["distance_null_reasons"] = ["preserved_bound_response_unavailable"]
        elif not result["parseable"]:
            result["vector"]["distance_null_reasons"] = ["stage_input_identity_unavailable"]
    return result


def aggregate(stage_rows, references):
    lookup = {(r["case_id"], r["stage"]): r for r in stage_rows}
    finals = [lookup[(case, "F0")] for case in CASES]
    def vec(case, stage="F0"):
        return lookup[(case, stage)]["vector"]
    def pair(a, b):
        return compare(vec(a), vec(b), a + ":F0", b + ":F0")
    fe, fl, ue, ul, control = CASES
    within = [pair(fe, fl), pair(ue, ul)]
    between = [pair(fe, ue), pair(fl, ul)]
    dd = {"value": None, "exact_decimal": None, "null_reasons": []}
    if all(p["distance"] is not None for p in between):
        diff = Fraction(between[0]["distance_exact_decimal"]) - Fraction(between[1]["distance_exact_decimal"])
        dd.update(value=float(diff), exact_decimal=exact_decimal(diff))
    else:
        dd["null_reasons"] = [r for p in between for r in p["null_reasons"]]
    dd["interpretation"] = "descriptive difference of two distances; not a causal difference-in-differences estimate"
    reference_metrics = {r["reference_id"]: vector_metrics({"sectors": [{"sector_code": c, "weight": r["weights"][c]} for c in CODES]}) for r in references}
    reference_pairs = {c: {name: compare(vec(c), v, c + ":F0", name) for name, v in reference_metrics.items()} for c in CASES}
    def counts(rows):
        return {"planned": len(rows), "attempted": sum(r["attempted"] for r in rows),
                "not_attempted": sum(not r["attempted"] for r in rows),
                "infrastructure_failure": sum(r["infrastructure_failure"] for r in rows),
                "artifact_integrity_failure": sum(r["artifact_integrity_failure"] for r in rows),
                "recorded_completed": sum(r["recorded_status"] == "completed" for r in rows),
                "transport_complete": sum(r["transport_complete"] for r in rows),
                "readable_partial": sum(r["readable_partial"] for r in rows),
                "parseable": sum(r["parseable"] for r in rows),
                "schema_valid": sum(r["schema_valid"] for r in rows),
                "complete_vector": sum(r["vector"]["complete_vector"] for r in rows),
                "valid_raw_allocation": sum(r["vector"]["valid_raw_allocation"] for r in rows),
                "distance_eligible": sum(r["vector"]["distance_eligible"] for r in rows)}
    return {"denominators": {"planned_cases": 5, "planned_final_sector_rows": 55,
                "planned_source_conditioned_rows": 44, "planned_no_source_control_rows": 11,
                "planned_stage_slots": 10, "shared_C_count": 1},
            "final_coverage": counts(finals), "all_stage_coverage": counts(stage_rows),
            "eligible_within_source_pairs": sum(p["distance"] is not None for p in within),
            "eligible_between_source_pairs": sum(p["distance"] is not None for p in between),
            "within_source": within, "between_sources": between, "difference_of_distances": dd,
            "shared_control_comparisons": [pair(c, control) for c in CASES[:-1]],
            "reference_comparisons": reference_pairs,
            "own_D0_F0": [compare(vec(c), vec(c, "D0"), c + ":F0", c + ":D0") for c in CASES],
            "semantic_review": "Not performed by this arithmetic analyzer; no source tendency or claim-support score inferred."}


def analyze(run_dir):
    run_dir = Path(run_dir).resolve()
    # This gate is deliberately checked before any model-output artifact opens.
    summary_path = run_dir / "pilot_summary.json"
    if not summary_path.is_file():
        raise ValueError("pilot_summary.json absent: live or incomplete runs cannot be analyzed")
    summary, summary_ref = read_json(summary_path)
    if summary.get("status") not in ("stopped", "pilot_attempt_sequence_finished"):
        raise ValueError("pilot_summary_is_not_a_completed_attempt_sequence")
    if [row.get("case_id") for row in summary.get("cases", [])] != list(CASES):
        raise ValueError("summary_must_retain_all_five_planned_cases_in_declared_order")
    for field in ("main_model_calls", "automatic_retries", "post_final_calls"):
        if type(summary.get(field)) is not int or summary[field] != 0:
            raise ValueError("summary_violates_first_attempt_pilot_scope:" + field)
    protocol, protocol_ref = pinned(ROOT / PROTOCOL, PROTOCOL_SHA)
    schema, schema_ref = pinned(ROOT / SCHEMA, SCHEMA_SHA)
    comp_ref = protocol["computational_references_ref"]
    comp, comp_actual = pinned(ROOT / comp_ref["path"], comp_ref["sha256"])
    if set(r["reference_id"] for r in comp["references"]) != {"equal_weight", "long_only_minimum_variance", "existing_market_benchmark"}:
        raise ValueError("unexpected_reference_set")
    artifacts, stages = [summary_ref], []
    for case in summary["cases"]:
        records = case.get("stages", [])
        if [r.get("stage") for r in records] not in ([], ["D0"], ["D0", "F0"]):
            raise ValueError("invalid_or_duplicate_stage_order")
        by_stage = {r["stage"]: r for r in records}
        for stage in STAGES:
            stages.append(load_stage(run_dir, case["case_id"], stage, by_stage.get(stage), schema, artifacts))
    total = sum(r["generation_requests_attempted"] for r in stages)
    if type(summary.get("generation_requests_attempted")) is not int or total != summary["generation_requests_attempted"] or total > 10:
        raise ValueError("aggregate_attempt_accounting_mismatch")
    if sha_bytes(summary_path.read_bytes()) != summary_ref["sha256"]:
        raise ValueError("completion_summary_changed_during_analysis")
    return {"analyzer_version": VERSION, "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "run_directory": str(run_dir), "evaluation_protocol_ref": protocol_ref,
            "response_schema_ref": schema_ref, "computational_references_ref": comp_actual,
            "analyzer_ref": {"path": str(Path(__file__).resolve()), "sha256": sha_bytes(Path(__file__).read_bytes())},
            "scope": "completed pilot first attempts only; prospective main remains separate",
            "policy": POLICY, "generation_requests_made_by_analyzer": 0,
            "input_artifacts": artifacts, "stage_records": stages, **aggregate(stages, comp["references"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; use a new receipt filename")
    result = analyze(args.run_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"output": str(args.output.resolve()), "final_coverage": result["final_coverage"]}))


if __name__ == "__main__":
    main()
