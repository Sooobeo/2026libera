"""Offline v4.9.1 message construction and deterministic submission checks.

Dependencies: numpy (through sector_engine), jsonschema 4.26.0. No file reads,
network requests, model calls, evaluator imports, normalization or retries occur
here. Caller-supplied inputs must come from the versioned public input bundle.
Output meaning/citation mistakes are recorded, not censored by a success gate.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any

from jsonschema import Draft202012Validator

from sector_engine import ENGINE_VERSION, SECTOR_CODES, calculate_portfolio, validate_weights

CONTRACT_VERSION = "sector_v491_contract_1"


def canonical_json(value: Any) -> str:
    """Stable bytes, while preserving explicit message-block insertion order."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _sha(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def strict_json(text: str) -> Any:
    """Reject duplicate keys, nonstandard constants, fences and trailing text."""
    if not isinstance(text, str):
        raise ValueError("response must be the original text")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON object key: " + key)
            result[key] = value
        return result

    def constant(value):
        raise ValueError("nonfinite JSON constant: " + value)

    value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    # 1e400 is standard JSON notation but becomes an unusable Python infinity.
    canonical_json(value)
    return value


def _rows(table: dict) -> list[dict]:
    if not isinstance(table, dict):
        raise ValueError("compact table must be an object")
    columns, rows, shared = table.get("columns"), table.get("rows"), table.get("shared", {})
    if (not isinstance(columns, list) or any(not isinstance(x, str) for x in columns)
            or len(set(columns)) != len(columns)
            or not isinstance(rows, list) or not isinstance(shared, dict)
            or set(columns).intersection(shared)):
        raise ValueError("invalid compact table declaration")
    expanded = []
    for row in rows:
        if not isinstance(row, list) or len(row) != len(columns):
            raise ValueError("invalid compact table row length")
        expanded.append({**shared, **dict(zip(columns, row))})
    return expanded


def _pointer(value: Any, pointer: str) -> Any:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("public evidence pointer must be absolute")
    try:
        for segment in pointer[1:].split("/"):
            key = segment.replace("~1", "/").replace("~0", "~")
            value = value[int(key)] if isinstance(value, list) else value[key]
    except (KeyError, ValueError, TypeError, IndexError) as exc:
        raise ValueError("public evidence pointer does not resolve") from exc
    return value


def evidence_ids(value: Any) -> set[str]:
    """Collect only declared fact/evidence IDs, including lossless table rows."""
    result = set()
    if isinstance(value, dict):
        for name in ("fact_id", "evidence_id"):
            if name in value:
                if not isinstance(value[name], str) or not value[name]:
                    raise ValueError("evidence IDs must be nonempty strings")
                result.add(value[name])
        if "columns" in value and "rows" in value:
            for row in _rows(value):
                for name in ("fact_id", "evidence_id"):
                    if name in row:
                        if not isinstance(row[name], str) or not row[name]:
                            raise ValueError("evidence IDs must be nonempty strings")
                        result.add(row[name])
        for item in value.values():
            result.update(evidence_ids(item))
    elif isinstance(value, list):
        for item in value:
            result.update(evidence_ids(item))
    return result


def _public_common(market: dict, index: dict, context: dict) -> set[str]:
    """Fail closed on invalid fact pointers and obvious aggregate/gold injection."""
    if not all(isinstance(x, dict) for x in (market, index, context)):
        raise ValueError("common market, index and context must be objects")
    if tuple(market.get("sector_codes", [])) != tuple(SECTOR_CODES):
        raise ValueError("common market must use the fixed ordered 11-sector universe")
    if not isinstance(context.get("operating_brief"), dict) or not isinstance(context.get("market_context"), dict):
        raise ValueError("common context requires operating_brief and market_context")
    prohibited = {"public_source_packets", "institution_document", "assigned_packet", "evaluator_only", "gold"}

    def inspect(value):
        if isinstance(value, dict):
            if prohibited.intersection(value):
                raise ValueError("aggregate/source/evaluator content is not common input")
            for item in value.values():
                inspect(item)
        elif isinstance(value, list):
            for item in value:
                inspect(item)

    for value in (market, index, context):
        inspect(value)
        canonical_json(value)
    records = []
    if "fact_tables" in index:
        for table in index["fact_tables"]:
            records.extend(_rows(table))
    elif "rows" in index:
        records.extend(_rows(index))
    if "matrix_reference_table" in index:
        records.extend(_rows(index["matrix_reference_table"]))
    records.extend(index.get("matrix_references", []))
    seen = set()
    for row in records:
        fid = row.get("fact_id")
        if not isinstance(fid, str) or not fid.startswith("M:") or fid in seen:
            raise ValueError("market fact IDs must be unique M: IDs")
        pointer = row.get("common_market_json_pointer", row.get("source_json_pointer"))
        canonical_json(_pointer(market, pointer))
        seen.add(fid)
    if not seen or seen != evidence_ids(index):
        raise ValueError("all declared market evidence must resolve to actual market values")
    context_ids = evidence_ids(context)
    if seen.intersection(context_ids):
        raise ValueError("context evidence IDs must not shadow market IDs")
    return seen | context_ids


def _packet(packet: dict) -> set[str]:
    if (not isinstance(packet, dict) or not isinstance(packet.get("source_id"), str)
            or not packet["source_id"] or "public_source_packets" in packet
            or not isinstance(packet.get("rating_vocabulary"), list)):
        raise ValueError("exactly one assigned public packet is required")
    vocabulary = packet["rating_vocabulary"]
    if (not vocabulary or any(not isinstance(x, str) or not x for x in vocabulary)
            or len(set(vocabulary)) != len(vocabulary)):
        raise ValueError("assigned source vocabulary must contain unique nonempty labels")
    canonical_json(packet)
    rows = (_rows(packet["evidence_table"]) if "evidence_table" in packet
            else packet.get("evidence_passages", []))
    ids = []
    for row in rows:
        if row.get("source_id", packet["source_id"]) != packet["source_id"]:
            raise ValueError("packet passage contains another source identity")
        eid = row.get("evidence_id")
        if not isinstance(eid, str) or not eid.startswith(packet["source_id"] + ":"):
            raise ValueError("packet evidence must be source-qualified")
        ids.append(eid)
    if not ids or len(set(ids)) != len(ids) or set(ids) != evidence_ids(packet):
        raise ValueError("packet evidence IDs must be unique and declared in passages")
    return set(ids)


def select_public_inputs(candidate: dict, source_id: str) -> dict:
    """Allowlist extraction; never return the aggregate source corpus metadata."""
    packet = candidate["public_source_packets"][source_id]
    if packet.get("source_id") != source_id:
        raise ValueError("selected source key and packet identity disagree")
    _packet(packet)
    return copy.deepcopy({"common_market": candidate["common_market"],
                          "public_numeric_fact_index": candidate["public_numeric_fact_index"],
                          "assigned_packet": packet})


def build_draft_messages(*, arm: str, assigned_packet: dict, common_market: dict,
                         public_numeric_fact_index: dict, common_context: dict,
                         prompt_contract: dict, response_schema: dict) -> list[dict]:
    if arm not in ("E", "L"):
        raise ValueError("arm must be E or L")
    if any(not isinstance(prompt_contract.get(key), str) or not prompt_contract[key].strip()
           for key in ("system", "D0_instruction", "F0_instruction")):
        raise ValueError("complete common system/draft/final instructions are required")
    _packet(assigned_packet)
    _public_common(common_market, public_numeric_fact_index, common_context)
    Draft202012Validator.check_schema(response_schema)
    payload = {"stage": "D0", "task": prompt_contract["D0_instruction"],
               "common_context": common_context, "common_market": common_market,
               "public_numeric_fact_index": public_numeric_fact_index,
               "response_schema": response_schema}
    if arm == "E":
        payload["institution_document"] = assigned_packet
    # Arm, source assignment and case metadata are never inserted separately.
    return [{"role": "system", "content": prompt_contract["system"]},
            {"role": "user", "content": canonical_json(payload)}]


def _citation_lists(value: Any, path: str = ""):
    if isinstance(value, dict):
        for key, item in value.items():
            location = path + "/" + key
            if key == "evidence_ids" or key.endswith("_evidence_ids"):
                yield location, item
            else:
                yield from _citation_lists(item, location)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _citation_lists(item, path + "/" + str(i))


def extract_raw_weights(parsed: dict) -> list[dict]:
    """Preserve submitted row order and exact numeric values; never fill rows."""
    return [{"sector_code": row["sector_code"], "weight": row["weight"]}
            for row in parsed["sectors"]]


def validate_response(raw_text: str, *, response_schema: dict,
                      visible_evidence_ids: list[str] | set[str],
                      expected_source_packet: dict | None = None) -> dict:
    """Separate readability from visibility, arithmetic and semantic outcomes."""
    report = {"parsed": None, "parse_valid": False, "schema_valid": False,
              "complete_vector": False, "structural_valid": False,
              "visibility_valid": False, "contract_valid": False,
              "continuation_eligible": False, "errors": [], "visibility_errors": [],
              "source_label_diagnostics": [], "arithmetic": None,
              "semantic_support": "requires_independent_review_not_automatically_certified"}
    try:
        obj = strict_json(raw_text)
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        report["errors"].append({"kind": "json_parse", "message": str(exc)})
        return report
    report.update(parsed=obj, parse_valid=True)
    Draft202012Validator.check_schema(response_schema)
    errors = sorted(Draft202012Validator(response_schema).iter_errors(obj),
                    key=lambda e: str(list(e.absolute_path)))
    report["errors"].extend({"kind": "schema", "path": list(e.absolute_path), "message": e.message}
                            for e in errors)
    report["schema_valid"] = not errors
    if errors:
        return report
    weights = extract_raw_weights(obj)
    allocation = validate_weights(weights)
    complete = (len(weights) == len(SECTOR_CODES)
                and not any(allocation[k] for k in ("missing_codes", "duplicate_codes", "unknown_codes",
                                                    "malformed_rows", "nonfinite_or_nonnumeric_codes")))
    report.update(complete_vector=complete, structural_valid=complete,
                  continuation_eligible=complete, arithmetic=allocation)
    if not complete:
        report["errors"].append({"kind": "vector", "message": "need exactly 11 unique finite numeric sector weights"})
    visible = set(visible_evidence_ids)
    source_ids = _packet(expected_source_packet) if expected_source_packet is not None else set()
    if not source_ids.issubset(visible):
        raise ValueError("expected source packet must already be visible to the model")
    wanted = expected_source_packet["source_id"] if expected_source_packet else None
    if obj["source_id"] != wanted:
        report["visibility_errors"].append({"kind": "source_identity", "reported": obj["source_id"], "expected": wanted})
    for path, ids in _citation_lists(obj):
        unknown = sorted(set(ids) - visible)
        if unknown:
            report["visibility_errors"].append({"kind": "unavailable_evidence", "path": path, "ids": unknown})
        if path.endswith("/source_evidence_ids"):
            wrong_kind = sorted(set(ids) - source_ids)
            if wrong_kind:
                report["visibility_errors"].append({"kind": "not_assigned_source_evidence", "path": path, "ids": wrong_kind})
    for row in obj["sectors"]:
        if expected_source_packet is None:
            if row["source_label"] is not None or row["source_stance"] != "not_available" or row["source_evidence_ids"]:
                report["visibility_errors"].append({"kind": "source_not_yet_available", "sector_code": row["sector_code"]})
        elif row["source_label"] not in expected_source_packet["rating_vocabulary"]:
            report["source_label_diagnostics"].append({"sector_code": row["sector_code"],
                                                      "label": row["source_label"], "kind": "outside_source_vocabulary"})
    report["visibility_valid"] = not report["visibility_errors"]
    report["contract_valid"] = complete and report["visibility_valid"]
    return report


def evaluate_submission(parsed: dict, *, market: dict, visible_evidence_ids: list[str] | set[str],
                        endpoint_id: str = "D0", previous_sectors: list[dict] | None = None) -> dict:
    """Use only submitted weights and visible evidence; no semantic feedback."""
    if endpoint_id not in ("D0", "F0"):
        raise ValueError("endpoint must be D0 or F0; no post-final repair endpoint")
    weights = extract_raw_weights(parsed)
    calc = calculate_portfolio(weights, market=market, visible_evidence_ids=sorted(visible_evidence_ids),
                               submitted_constraints=parsed.get("submitted_constraints", []))
    allocation = calc["allocation"]
    lineage = {"calculation_id": "C:" + endpoint_id, "endpoint_id": endpoint_id,
               "submitted_vector_sha256": _sha(weights), "market_values_sha256": _sha(market),
               "engine_version": ENGINE_VERSION, "contract_version": CONTRACT_VERSION,
               "hash_scope": "ordered raw sector_code/weight records; unchanged values"}
    facts = []

    def fact(name, value, metric, unit="decimal_weight", code=None, formula=None, period=None):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return
        facts.append({"fact_id": f"C:{endpoint_id}:{name}", "value": value, "metric": metric,
                      "unit": unit, "sector_code": code, "formula": formula, "period": period,
                      "candidate_id": endpoint_id, "data_version": lineage["submitted_vector_sha256"],
                      "market_data_version": lineage["market_values_sha256"],
                      "valid_raw_allocation": allocation["valid"]})

    fact("sum", allocation["raw_sum"], "raw_weight_sum", formula="sum(w)")
    fact("budget_residual", allocation["raw_budget_residual"], "raw_budget_residual", formula="sum(w)-1")
    baseline = calc["market_diagnostics"].get("baseline")
    active = baseline.get("raw_active_weights") if baseline else None
    if active:
        for code, value in active.items():
            fact("active_weight:" + code, value, "raw_weight_minus_benchmark", code=code, formula="w-benchmark")
    risk = calc["market_diagnostics"].get("risk") if allocation["valid"] else None
    if risk:
        fact("variance", risk["raw_variance"], "historical_portfolio_variance",
             unit=risk["covariance_unit"], formula="w^T Sigma w", period=market.get("lookback_return_dates"))
        fact("volatility", risk["volatility"], "historical_portfolio_standard_deviation",
             unit="daily_decimal_return", formula="sqrt(w^T Sigma w)", period=market.get("lookback_return_dates"))
    deltas = None
    if previous_sectors is not None:
        previous = extract_raw_weights({"sectors": previous_sectors})
        prev_check = validate_weights(previous)
        if allocation["weights_by_code"] is not None and prev_check["weights_by_code"] is not None:
            deltas = {}
            for code in SECTOR_CODES:
                value = allocation["weights_by_code"][code] - prev_check["weights_by_code"][code]
                deltas[code] = value if math.isfinite(value) else None
                fact("weight_delta:" + code, value, "raw_current_minus_previous_weight", code=code, formula="w_current-w_previous")
            lineage["previous_vector_sha256"] = _sha(previous)
    return {"endpoint_id": endpoint_id, "lineage": lineage, "allocation": allocation,
            "submitted_constraint_checks": calc["submitted_constraint_checks"],
            "constraint_scope": "arithmetic and citation visibility only; no source entailment certification",
            "market_validation": {"status": calc["market_diagnostics"]["status"], "errors": calc["market_diagnostics"]["errors"]},
            "raw_active_weights": active, "raw_weight_deltas": deltas,
            "valid_portfolio_historical_risk": risk, "facts": facts,
            "repaired": False, "gold_access": False,
            "interpretation": "This is actual prior-candidate arithmetic, not a forecast, semantic judgment, mandate, initial holding or verification of any later vector."}


def build_final_messages(*, draft_messages: list[dict], raw_draft: str,
                         assigned_packet: dict, prompt_contract: dict,
                         response_schema: dict) -> dict:
    """Retain exact D0 history; calculate actual feedback; append one F0 request.

    Returns messages plus an offline receipt. Receipt diagnostics never become
    model-visible. This function does not call a model or choose an output.
    """
    if (not isinstance(draft_messages, list) or len(draft_messages) != 2
            or draft_messages[0] != {"role": "system", "content": prompt_contract["system"]}
            or draft_messages[1].get("role") != "user"):
        raise ValueError("exact original two-message D0 history is required")
    payload = strict_json(draft_messages[1]["content"])
    allowed = {"stage", "task", "common_context", "common_market", "public_numeric_fact_index", "response_schema", "institution_document"}
    if (set(payload) - allowed or payload.get("stage") != "D0"
            or payload.get("task") != prompt_contract["D0_instruction"]
            or payload.get("response_schema") != response_schema):
        raise ValueError("D0 history does not match this prompt/schema contract")
    visible = _public_common(payload["common_market"], payload["public_numeric_fact_index"], payload["common_context"])
    source_ids = _packet(assigned_packet)
    draft_packet = payload.get("institution_document")
    if draft_packet is not None:
        if canonical_json(draft_packet) != canonical_json(assigned_packet):
            raise ValueError("final source packet differs from the early assigned packet")
        visible.update(source_ids)
    validation = validate_response(raw_draft, response_schema=response_schema,
                                   visible_evidence_ids=visible, expected_source_packet=draft_packet)
    if not validation["continuation_eligible"]:
        return {"ready": False, "messages": None, "draft_validation": validation,
                "reason": "draft_has_no_schema_valid_complete_finite_vector", "model_calls": 0}
    feedback = evaluate_submission(validation["parsed"], market=payload["common_market"],
                                   visible_evidence_ids=visible, endpoint_id="D0")
    final_payload = {"stage": "F0", "task": prompt_contract["F0_instruction"],
                     "actual_draft_calculator_feedback": feedback,
                     "institution_document": assigned_packet}
    messages = copy.deepcopy(draft_messages)
    messages.append({"role": "assistant", "content": raw_draft})
    messages.append({"role": "user", "content": canonical_json(final_payload)})
    return {"ready": True, "messages": messages, "draft_validation": validation,
            "draft_feedback": feedback,
            "visible_evidence_ids_for_final": sorted(visible | source_ids | evidence_ids(feedback)),
            "source_packet_sha256": _sha(assigned_packet), "model_calls": 0,
            "final_policy": "one F0 request; first response retained; no automatic retry or repair"}
