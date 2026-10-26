"""Bind a new development pilot to reviewed recovery inputs before generation.

The October 19 gate remains historical evidence. This gate explicitly follows
inspection of those outputs and never re-labels them as a prospective new run.
"""
from __future__ import annotations

import json
from pathlib import Path

import sector_v492_review_gate as previous
import prepare_sector_v491 as paths
import remote_sector_runtime as remote

CASE_ORDER = previous.CASE_ORDER
CONTROLS = previous.CONTROLS
require = previous.require
timestamp = previous.timestamp
checked_ref = previous.checked_ref
canonical = previous.canonical
REQUIRED_CODE_PATHS = previous.REQUIRED_CODE_PATHS | {
    "research/sector_v494_runtime.py", "research/sector_v494_review_gate.py",
    "research/prepare_sector_v494.py", "research/review_sector_v494_stage.py",
    "research/run_v494_recovery.py", "research/build_v494_masked_review.py",
}
BOUND_REFS = previous.BOUND_REFS


def validate_review_gate(path, expected_sha=None, *, runtime=None, run_directory=None):
    gate, gate_ref = paths.read(path, expected_sha)
    require(gate.get("receipt_version") == "v494_development_gate_1"
            and gate.get("status") == "approved_for_pilot_before_generation"
            and gate.get("review_mode") == "AI_delegated_by_user", "new completed development review required")
    require(gate.get("main_allowed") is False and gate.get("pilot_cases") == CASE_ORDER, "five pilot cases only")
    require(gate.get("old_outputs_observed") is True and type(gate.get("new_run_research_calls_before_freeze")) is int
            and gate.get("new_run_research_calls_before_freeze") == 0,
            "development chronology must distinguish old observations and new run")
    instruction = gate.get("user_instruction", {})
    require(instruction.get("exact_text") == "다 진행해봐.\n배분,인용 오류 점검 및 새 파일럿 검증하는건 한 단계 할 때마다 오류,정합성, 소논문 주제와의 연결성이 너무 멀어지지 않는지 다 확인하면서 진행해",
            "current user scope must be accurately recorded")
    require(instruction.get("timestamp_kind") == "recorded_after_user_message", "record-time provenance required")
    objects = {name: checked_ref(gate.get(name)) for name in BOUND_REFS}
    old_ref = gate.get("historical_gate_ref")
    checked_ref(old_ref)
    previous.validate_review_gate(old_ref["path"], old_ref["sha256"])
    freeze = checked_ref(gate.get("freeze_ref"))
    require(freeze.get("freeze_version") == "v494_development_freeze_1"
            and freeze.get("protocol_version") == "4.9.4"
            and freeze.get("status") == "frozen_for_pilot_only"
            and freeze.get("main_allowed") is False, "new pilot-only freeze required")
    require(freeze.get("user_instruction") == instruction and freeze.get("case_order") == CASE_ORDER
            and canonical(freeze.get("controls")) == canonical(CONTROLS), "freeze scope/controls differ")
    for name in BOUND_REFS:
        require(gate[name] == freeze.get(name), "freeze binding differs: " + name)
    code_refs = freeze.get("code_refs", [])
    observed = []
    for ref in code_refs:
        p = checked_ref(ref, json_object=False)
        observed.append(p.relative_to(paths.ROOT).as_posix())
    require(len(observed) == len(set(observed)) and REQUIRED_CODE_PATHS.issubset(observed),
            "all inherited and revised executable code must be frozen")
    ft, gt = timestamp(freeze.get("recorded_at_utc")), timestamp(gate.get("recorded_at_utc"))
    require(timestamp(instruction.get("recorded_at_utc")) <= ft <= gt, "instruction/freeze/gate chronology differs")
    reviews = gate.get("stage_review_refs", [])
    require(len(reviews) >= 3 and reviews == freeze.get("stage_review_refs"), "three pre-output stage reviews required")
    for ref in reviews:
        review = checked_ref(ref)
        require(review.get("status") == "PASS" and timestamp(review.get("completed_at_utc")) <= ft,
                "completed pre-freeze review required")
        for axis in ("errors", "consistency", "paper_topic"):
            item = review.get("review_axes", {}).get(axis, {})
            require(item.get("pass") is True and previous.text(item.get("reason")), "stage review missing axis: " + axis)
        for evidence in review.get("input_refs", []):
            checked_ref(evidence, json_object=False)
    require(objects["input_protocol_ref"].get("protocol_version") == "4.9.1", "original common task retained")
    require(objects["evaluation_protocol_ref"].get("protocol_version") == "4.9.2", "unchanged descriptive rubric required")
    require(objects["source_review_ref"].get("status") == "completed_ai_preoutput_source_review", "original source review retained")
    require(objects["method_review_ref"].get("status") == "PASS", "prospective amendment review required")
    require(objects["prompt_contract_ref"].get("protocol_version") == "4.9.4", "new instruction version required")
    selected = objects["runtime_ref"]
    from sector_v494_runtime import validate_runtime
    validate_runtime(selected)
    selected_controls = {"backend": selected.get("backend"),
                         **{k: selected.get("options", {}).get(k) for k in ("num_thread", "num_ctx", "num_predict")},
                         "deadline_seconds": selected.get("deadline_seconds"),
                         "max_generation_requests": selected.get("pilot_max_generation_requests"),
                         "main_allowed": selected.get("main_allowed")}
    require(canonical(selected_controls) == canonical(CONTROLS) and selected.get("protocol_version") == "4.9.4"
            and selected.get("pilot_order") == CASE_ORDER and type(selected.get("options", {}).get("num_gpu")) is int
            and selected.get("options", {}).get("num_gpu") == 0,
            "reviewed CPU controls differ")
    if runtime is not None:
        require(canonical(runtime) == canonical(selected), "caller runtime differs from freeze")
    manifest = objects["prepared_manifest_ref"]
    require(manifest.get("protocol_version") == "4.9.4" and type(manifest.get("model_calls")) is int and manifest.get("model_calls") == 0
            and [c.get("case_id") for c in manifest.get("prepared_cases", [])] == CASE_ORDER,
            "five new offline inputs required")
    for case in manifest["prepared_cases"]:
        checked_ref({"path": case["path"], "sha256": case["sha256"]}, json_object=False)
    require(manifest.get("inputs", {}).get("prompt_contract") == gate["prompt_contract_ref"], "prompt identity mismatch")
    if run_directory is not None:
        run = paths.workspace_path(run_directory)
        declaration = remote.read(run / "pilot_declaration.json")
        started = remote.read(run / "execution_started.json")
        require(declaration.get("review_gate") == gate_ref and declaration.get("case_order") == CASE_ORDER
                and canonical(declaration.get("runtime")) == canonical(selected), "run differs from freeze")
        require(gt <= timestamp(declaration.get("created_at_utc")) <= timestamp(started.get("at_utc")),
                "freeze must precede this run")
    return {"status": "prospective_development_review_and_freeze_verified", "gate_ref": gate_ref,
            "freeze_ref": gate["freeze_ref"], "independent_human_review_completed": False,
            "old_outputs_observed": True, "scope": "Input/code identity and chronology, not semantic success."}
