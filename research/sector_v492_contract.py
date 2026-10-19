"""Offline v4.9.2 contract: E/L source timing and a source-free C control.

The original v4.9.1 file is immutable. Its deterministic arithmetic and public
input validators are reused; this module owns the revised message constructors
and accurately labels semantic evaluation as unvalidated AI assistance.
No file reads, HTTP requests, inference, retries or output repair occur here.
"""
from __future__ import annotations

import copy
from typing import Any

from jsonschema import Draft202012Validator

import sector_v491_contract as prior

CONTRACT_VERSION = "sector_v492_contract_1"
SECTOR_CODES = prior.SECTOR_CODES
canonical_json = prior.canonical_json
strict_json = prior.strict_json
evidence_ids = prior.evidence_ids
extract_raw_weights = prior.extract_raw_weights


def select_public_inputs(candidate: dict, source_id: str | None) -> dict:
    """Select one public packet, or select only common inputs for C."""
    if source_id is not None:
        return prior.select_public_inputs(candidate, source_id)
    return copy.deepcopy({
        "common_market": candidate["common_market"],
        "public_numeric_fact_index": candidate["public_numeric_fact_index"],
        "assigned_packet": None,
    })


def _instructions(prompt_contract: dict) -> None:
    if not isinstance(prompt_contract, dict) or any(
        not isinstance(prompt_contract.get(key), str)
        or not prompt_contract[key].strip()
        for key in ("system", "D0_instruction", "F0_instruction")
    ):
        raise ValueError("complete common system/draft/final instructions are required")


def build_draft_messages(*, arm: str, assigned_packet: dict | None,
                         common_market: dict, public_numeric_fact_index: dict,
                         common_context: dict, prompt_contract: dict,
                         response_schema: dict) -> list[dict]:
    """C_D0 equals L_D0 byte for byte for otherwise identical common inputs."""
    if arm not in ("E", "L", "C"):
        raise ValueError("arm must be E, L or C")
    _instructions(prompt_contract)
    if arm == "C":
        if assigned_packet is not None:
            raise ValueError("C cannot have an assigned institutional packet")
    else:
        prior._packet(assigned_packet)
    prior._public_common(common_market, public_numeric_fact_index, common_context)
    Draft202012Validator.check_schema(response_schema)
    payload = {
        "stage": "D0", "task": prompt_contract["D0_instruction"],
        "common_context": common_context, "common_market": common_market,
        "public_numeric_fact_index": public_numeric_fact_index,
        "response_schema": response_schema,
    }
    if arm == "E":
        payload["institution_document"] = assigned_packet
    return [{"role": "system", "content": prompt_contract["system"]},
            {"role": "user", "content": canonical_json(payload)}]


def validate_response(raw_text: str, *, response_schema: dict,
                      visible_evidence_ids: list[str] | set[str],
                      expected_source_packet: dict | None = None) -> dict:
    result = prior.validate_response(
        raw_text, response_schema=response_schema,
        visible_evidence_ids=visible_evidence_ids,
        expected_source_packet=expected_source_packet,
    )
    result["semantic_support"] = "unvalidated_AI_assisted_review_not_automatically_certified"
    for error in result["visibility_errors"]:
        if error.get("kind") == "source_not_yet_available":
            error["kind"] = "source_not_supplied_for_this_stage"
    return result


def evaluate_submission(parsed: dict, *, market: dict,
                        visible_evidence_ids: list[str] | set[str],
                        endpoint_id: str = "D0",
                        previous_sectors: list[dict] | None = None) -> dict:
    result = prior.evaluate_submission(
        parsed, market=market, visible_evidence_ids=visible_evidence_ids,
        endpoint_id=endpoint_id, previous_sectors=previous_sectors,
    )
    result["lineage"]["contract_version"] = CONTRACT_VERSION
    return result


def build_final_messages(*, draft_messages: list[dict], raw_draft: str,
                         assigned_packet: dict | None, prompt_contract: dict,
                         response_schema: dict) -> dict:
    """Append a single conditional F0 to the exact own D0 and its arithmetic.

    None denotes C: D0 must not contain an institutional packet and F0 does not
    add one. E/L use the supplied packet. Runtime binds the declared case/arm,
    stored D0 provenance and exact bundle independently before calling this.
    """
    _instructions(prompt_contract)
    if (not isinstance(draft_messages, list) or len(draft_messages) != 2
            or any(not isinstance(message, dict)
                   or set(message) != {"role", "content"}
                   for message in draft_messages)
            or draft_messages[0] != {"role": "system", "content": prompt_contract["system"]}
            or draft_messages[1].get("role") != "user"):
        raise ValueError("exact original two-message D0 history is required")
    payload = strict_json(draft_messages[1]["content"])
    required = {"stage", "task", "common_context", "common_market",
                "public_numeric_fact_index", "response_schema"}
    if (not isinstance(payload, dict) or not required.issubset(payload)
            or set(payload) - (required | {"institution_document"})
            or payload.get("stage") != "D0"
            or payload.get("task") != prompt_contract["D0_instruction"]
            or canonical_json(payload.get("response_schema")) != canonical_json(response_schema)):
        raise ValueError("D0 history does not match this prompt/schema contract")
    visible = prior._public_common(payload["common_market"],
                                   payload["public_numeric_fact_index"],
                                   payload["common_context"])
    draft_packet = payload.get("institution_document")
    if assigned_packet is None:
        if "institution_document" in payload:
            raise ValueError("C final cannot remove a packet present in its D0")
        source_ids = set()
    else:
        source_ids = prior._packet(assigned_packet)
        if "institution_document" in payload:
            if canonical_json(draft_packet) != canonical_json(assigned_packet):
                raise ValueError("final source packet differs from the early assigned packet")
            visible.update(source_ids)
    validation = validate_response(
        raw_draft, response_schema=response_schema,
        visible_evidence_ids=visible, expected_source_packet=draft_packet,
    )
    if not validation["continuation_eligible"]:
        return {"ready": False, "messages": None, "draft_validation": validation,
                "reason": "draft_has_no_schema_valid_complete_finite_vector",
                "model_calls": 0}
    feedback = evaluate_submission(validation["parsed"], market=payload["common_market"],
                                   visible_evidence_ids=visible, endpoint_id="D0")
    final_payload = {"stage": "F0", "task": prompt_contract["F0_instruction"],
                     "actual_draft_calculator_feedback": feedback}
    if assigned_packet is not None:
        final_payload["institution_document"] = assigned_packet
    messages = copy.deepcopy(draft_messages)
    messages.append({"role": "assistant", "content": raw_draft})
    messages.append({"role": "user", "content": canonical_json(final_payload)})
    return {
        "ready": True, "messages": messages, "draft_validation": validation,
        "draft_feedback": feedback,
        "visible_evidence_ids_for_final": sorted(visible | source_ids | evidence_ids(feedback)),
        "source_packet_sha256": prior._sha(assigned_packet) if assigned_packet is not None else None,
        "model_calls": 0,
        "final_policy": "one F0 request; first response retained; no automatic retry or repair",
    }
