"""Verify an explicitly delegated AI review and a pre-output pilot freeze.

This is not independent human review. It checks artifact identity, completeness,
and declared AI findings; semantic validity still depends on the documented
review. User delegation changes the reviewer requirement, not the data boundary.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import prepare_sector_v491 as paths
import remote_sector_runtime as remote
from sector_engine import SECTOR_CODES

CASE_ORDER = ["fidelity_q2_2026__E", "fidelity_q2_2026__L", "ubs_june_2026__E", "ubs_june_2026__L", "common_market_only__C"]
CONTROLS = {"backend": "cpu", "num_thread": 8, "num_ctx": 65536, "num_predict": 8192,
            "deadline_seconds": 4500, "max_generation_requests": 10, "main_allowed": False}
BOUND_REFS = ("input_protocol_ref", "evaluation_protocol_ref", "source_review_ref", "method_review_ref",
              "prompt_contract_ref", "prepared_manifest_ref", "runtime_ref")
REQUIRED_CODE_PATHS = {
    "research/sector_v492_runtime.py", "research/sector_v492_review_gate.py", "research/sector_v492_contract.py",
    "research/prepare_sector_v492.py", "research/sector_v491_runtime.py", "research/sector_v491_contract.py",
    "research/prepare_sector_v491.py", "research/sector_v491_tokenizer.py", "research/sector_engine.py",
    "research/local_sector_single_case.py", "research/remote_sector_runtime.py", "research/benchmark_sector_latency.py",
    "research/probe_ollama_runtime.py", "research/sector_v48_transport.py", "research/sector_v48_main_awake.py",
}


def require(condition, message):
    if not condition:
        raise ValueError("Delegated AI pre-output gate: " + message)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def timestamp(value):
    require(text(value), "UTC timestamp is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0, "timestamp must explicitly use UTC")
    require(parsed <= datetime.now(timezone.utc), "future timestamp is invalid")
    return parsed


def checked_ref(ref, *, json_object=True):
    require(isinstance(ref, dict) and text(ref.get("path")), "artifact reference path required")
    digest = ref.get("sha256")
    require(isinstance(digest, str) and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), "exact SHA256 required")
    path = paths.workspace_path(ref["path"])
    require(remote.sha(path) == digest, "artifact changed: " + str(ref["path"]))
    return paths.read(path, digest)[0] if json_object else path


def validate_review_gate(path, expected_sha=None, *, runtime=None, run_directory=None):
    gate, gate_ref = paths.read(path, expected_sha)
    require(gate.get("receipt_version") == "v492_ai_preoutput_gate_1"
            and gate.get("status") == "approved_for_pilot_before_generation"
            and gate.get("review_mode") == "AI_delegated_by_user", "completed delegated-AI receipt required")
    require(gate.get("main_allowed") is False and gate.get("pilot_cases") == CASE_ORDER, "five pilot cases only")
    instruction = gate.get("user_instruction", {})
    require(instruction.get("exact_text") == "걍 다 너한테 맞길게 평가규칙 저거 아님"
            and instruction.get("timestamp_kind") == "recorded_after_user_message" and text(instruction.get("scope")),
            "actual user delegation and honest record-time provenance required")
    instruction_time = timestamp(instruction.get("recorded_at_utc"))
    objects = {name: checked_ref(gate.get(name)) for name in BOUND_REFS}
    freeze = checked_ref(gate.get("freeze_ref"))
    require(freeze.get("freeze_version") == "v492_pilot_preoutput_freeze_1"
            and freeze.get("protocol_version") == "4.9.2" and freeze.get("status") == "frozen_for_pilot_only"
            and freeze.get("purpose") == "pilot_only", "completed pre-output freeze required")
    require(freeze.get("user_instruction") == instruction and freeze.get("case_order") == CASE_ORDER
            and canonical(freeze.get("controls")) == canonical(CONTROLS), "freeze delegation/order/controls differ")
    for name in BOUND_REFS:
        require(gate[name] == freeze.get(name), "freeze binding differs: " + name)
    code_refs = freeze.get("code_refs")
    require(isinstance(code_refs, list), "frozen implementation references required")
    observed_paths = []
    for ref in code_refs:
        source_path = checked_ref(ref, json_object=False)
        observed_paths.append(source_path.relative_to(paths.ROOT).as_posix())
    require(len(observed_paths) == len(set(observed_paths)) and REQUIRED_CODE_PATHS.issubset(observed_paths), "required implementation code is not frozen")
    freeze_time = timestamp(freeze.get("recorded_at_utc"))
    gate_time = timestamp(gate.get("recorded_at_utc"))
    require(instruction_time <= freeze_time <= gate_time, "delegation/freeze/gate chronology is inconsistent")
    protocol = objects["input_protocol_ref"]
    require(protocol.get("protocol_version") == "4.9.1", "unchanged original task/input protocol must remain explicit")
    evaluation = objects["evaluation_protocol_ref"]
    require(evaluation.get("protocol_version") == "4.9.2", "amended evaluation protocol version required")
    method = objects["method_review_ref"]
    require(method.get("status") == "PASS", "recorded method/topic review must pass before freezing")
    prompt = objects["prompt_contract_ref"]
    require(prompt.get("protocol_version") == "4.9.2" and text(prompt.get("F0_instruction")), "shared v4.9.2 final instruction required")
    source = objects["source_review_ref"]
    require(source.get("protocol_version") == "4.9.2" and source.get("review_mode") == "AI_delegated_by_user"
            and source.get("status") == "completed_ai_preoutput_source_review"
            and source.get("independent_human_review_completed") is False
            and source.get("reviewed_before_research_outputs") is True
            and type(source.get("research_generation_calls_observed")) is int and source["research_generation_calls_observed"] == 0
            and source.get("material_changes_required") is False, "completed AI source review without unresolved material revision required")
    require(timestamp(source.get("completed_at_utc")) <= freeze_time, "source review must precede freeze")
    source_refs = source.get("input_refs")
    require(isinstance(source_refs, list) and bool(source_refs), "reviewed source files must be identified")
    for ref in source_refs:
        checked_ref(ref, json_object=False)
    rows = source.get("pilot_source_reviews")
    expected_rows = {(sid, code) for sid in ("fidelity_q2_2026", "ubs_june_2026") for code in SECTOR_CODES}
    require(isinstance(rows, list) and len(rows) == 22 and
            {(row.get("source_id"), row.get("sector_code")) for row in rows} == expected_rows, "all 22 source-sector reviews required")
    for row in rows:
        evidence, assessment = row.get("original_evidence", {}), row.get("paraphrase_assessment", {})
        require(text(row.get("original_rating")) and text(row.get("interpretation"))
                and text(row.get("source_packet_evidence_id"))
                and type(evidence.get("page")) is int and evidence["page"] >= 1
                and all(text(evidence.get(key)) for key in ("evidence_id", "rating_visual_locator", "rationale_paraphrase"))
                and text(assessment.get("status")) and text(assessment.get("reason")),
                "every source-sector review needs explicit meaning, original locator and paraphrase assessment")
    comparisons = source.get("pilot_source_comparisons")
    require(isinstance(comparisons, list) and [row.get("sector_code") for row in comparisons] == list(SECTOR_CODES), "all 11 source comparisons required")
    require(all(text(row.get("decision")) and text(row.get("evidence_and_reason")) and text(row.get("scope_limit")) for row in comparisons),
            "source comparison findings and limitations must be explicit")
    require(isinstance(source.get("unresolved"), list), "uncertainty record must be retained")
    review = gate.get("review", {})
    require(review.get("reviewer") == "Codex" and review.get("source_meaning_checked") is True
            and review.get("topic_alignment_checked") is True and isinstance(review.get("limitations"), list)
            and bool(review["limitations"]) and all(text(x) for x in review["limitations"]), "AI review findings and limitations required")
    require(timestamp(review.get("completed_at_utc")) <= freeze_time, "AI review must precede freeze")
    selected_runtime = objects["runtime_ref"]
    selected_controls = {"backend": selected_runtime.get("backend"),
                         **{key: selected_runtime.get("options", {}).get(key) for key in ("num_thread", "num_ctx", "num_predict")},
                         "deadline_seconds": selected_runtime.get("deadline_seconds"),
                         "max_generation_requests": selected_runtime.get("pilot_max_generation_requests"),
                         "main_allowed": selected_runtime.get("main_allowed")}
    require(canonical(selected_controls) == canonical(CONTROLS)
            and selected_runtime.get("protocol_version") == "4.9.2"
            and selected_runtime.get("pilot_order") == CASE_ORDER
            and type(selected_runtime.get("options", {}).get("num_gpu")) is int
            and selected_runtime["options"]["num_gpu"] == 0, "frozen runtime does not implement the declared controls")
    if runtime is not None:
        require(canonical(runtime) == canonical(selected_runtime), "caller runtime differs from frozen runtime")
    manifest = objects["prepared_manifest_ref"]
    require(manifest.get("protocol_version") == "4.9.2" and type(manifest.get("model_calls")) is int and manifest.get("model_calls") == 0
            and [case.get("case_id") for case in manifest.get("prepared_cases", [])] == CASE_ORDER, "exact five-case offline preparation required")
    for case in manifest["prepared_cases"]:
        checked_ref({"path": case["path"], "sha256": case["sha256"]}, json_object=False)
    require(manifest.get("inputs", {}).get("prompt_contract") == gate["prompt_contract_ref"], "prepared prompt version differs from frozen prompt")
    if run_directory is not None:
        run = paths.workspace_path(run_directory)
        declaration = remote.read(run / "pilot_declaration.json")
        started = remote.read(run / "execution_started.json")
        require(declaration.get("review_gate") == gate_ref and declaration.get("case_order") == CASE_ORDER
                and canonical(declaration.get("runtime")) == canonical(selected_runtime), "worker run declaration differs from freeze")
        require(gate_time <= timestamp(declaration.get("created_at_utc")) <= timestamp(started.get("at_utc")),
                "review and freeze must precede coordinator execution start")
    return {"status": "delegated_AI_review_and_preoutput_freeze_verified", "gate_ref": gate_ref,
            "freeze_ref": gate["freeze_ref"], "review_mode": "AI_delegated_by_user",
            "independent_human_review_completed": False,
            "scope": "Verified file identities, chronology and explicit AI findings; not independent human review or proof of semantic correctness."}
