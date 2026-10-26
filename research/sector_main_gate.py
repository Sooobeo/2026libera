"""Fail-closed prospective main gate; a continuation gate cannot authorize main."""
from __future__ import annotations

import copy
from pathlib import Path

import sector_continuation_gate as continuation
import sector_v494_runtime as original

paths = continuation.paths
checked, require, timestamp = continuation.checked, continuation.require, continuation.timestamp
CASES = ("fidelity_q3_2026__E", "fidelity_q3_2026__L", "ubs_july_2026__E", "ubs_july_2026__L", "common_market_only__C")
BOUND = ("runtime_ref", "protocol_ref", "prepared_manifest_ref", "continuation_gate_ref",
         "continuation_terminal_ref", "continuation_summary_ref", "continuation_operating_review_ref",
         "main_D0_preflight_ref", "finalizer_acceptance_ref", "campaign_finalizer_review_ref")
MAIN_REVIEW_CODE = {
    "research/sector_main_gate.py", "research/sector_main_runtime.py", "research/sector_main_awake.py",
    "research/run_sector_main.py", "research/test_sector_main.py"}
REQUIRED_CODE = continuation.REQUIRED_CODE | MAIN_REVIEW_CODE | {
    "research/prepare_sector_v495_main.py", "research/freeze_sector_main.py"}


def scope(value):
    require(value.get("purpose") == "main" and value.get("case_order") == list(CASES)
            and value.get("main_allowed") is True, "Explicit five-case main scope required")
    require(type(value.get("max_generation_requests")) is int and value["max_generation_requests"] == 10
            and type(value.get("automatic_retries")) is int and value["automatic_retries"] == 0,
            "Exactly ten maximum main requests and no retries required")


def verify_nested_refs(value):
    """Bind referenced reviewed bytes, including actual method/test source refs."""
    found = []
    if isinstance(value, dict):
        if "path" in value and "sha256" in value:
            reference = {key: value[key] for key in ("path", "sha256")}
            checked(reference, json_object=False)
            found.append(reference)
        else:
            for child in value.values():
                found.extend(verify_nested_refs(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(verify_nested_refs(child))
    return found


def validate_reviews(reviews, frozen_at):
    """Require distinct complete reviews tied to the current main implementation."""
    require(isinstance(reviews, list) and len(reviews) >= 3, "Three bound main pre-freeze reviews required")
    review_paths, review_hashes, reviewed_code = set(), set(), set()
    for item in reviews:
        review = checked(item)
        path = paths.workspace_path(item["path"])
        require(path not in review_paths and item["sha256"] not in review_hashes,
                "Main review references must identify distinct paths and contents")
        review_paths.add(path)
        review_hashes.add(item["sha256"])
        require(review.get("status") == "PASS" and timestamp(review["completed_at_utc"]) <= frozen_at,
                "Completed main review required")
        for reference in verify_nested_refs(review):
            reviewed_code.add(paths.workspace_path(reference["path"]).relative_to(paths.ROOT).as_posix())
        for axis in ("errors", "consistency", "paper_topic"):
            evidence = review.get("review_axes", {}).get(axis, {})
            require(evidence.get("pass") is True and isinstance(evidence.get("reason"), str)
                    and evidence["reason"].strip(), "All three main review axes required")
    require(MAIN_REVIEW_CODE.issubset(reviewed_code), "Main reviews must cover all four current modules and their tests")


def validate_operating_review(review, terminal, summary, terminal_ref, summary_ref):
    require(review.get("status") == "PASS_FOR_PROSPECTIVE_MAIN_FREEZE"
            and review.get("coverage_reviewed") is True
            and review.get("all_attempted_stages_reviewed") is True
            and review.get("reviewed_case_order") == list(continuation.CASES), "Completed continuation coverage review required")
    require(review.get("operating_feasibility", {}).get("pass") is True
            and isinstance(review.get("operating_feasibility", {}).get("reason"), str)
            and review["operating_feasibility"]["reason"].strip()
            and review.get("unresolved_system_integrity_incidents") == []
            and review.get("ordinary_model_errors_are_outcomes") is True,
            "Unresolved operational failure prevents main; model errors are retained outcomes")
    require(type(review.get("main_generation_calls_before_review")) is int
            and review["main_generation_calls_before_review"] == 0, "Operating review must precede main generation")
    require(review.get("continuation_terminal_ref") == terminal_ref
            and review.get("continuation_summary_ref") == summary_ref, "Operating review must bind exact terminal records")
    require(terminal.get("purpose") == "pilot_continuation"
            and terminal.get("status") == "completed_semantic_review_pending"
            and terminal.get("errors") == [] and terminal.get("awake_release", {}).get("status") == "released",
            "Cleanly terminal continuation and explicit coordinator awake cleanup required")
    require(summary.get("purpose") == "pilot_continuation" and summary.get("status") == "attempt_sequence_finished"
            and summary.get("case_order") == list(continuation.CASES)
            and [c.get("case_id") for c in summary.get("cases", [])] == list(continuation.CASES),
            "All four independent continuation cells must have addressed coverage")
    attempts = 0
    for row in summary["cases"]:
        stages = row.get("stages", [])
        require([s.get("stage") for s in stages] in (["D0"], ["D0", "F0"]), "Unattempted independent cell is not resolved coverage")
        for item in stages:
            require(type(item.get("generation_requests_attempted")) is int and item["generation_requests_attempted"] == 1
                    and item.get("status") in {"completed", "model_structure_failure", "output_limit_reached", "case_timeout"},
                    "Only accounted non-system outcomes permit an operating review")
            attempts += 1
        if len(stages) == 2:
            require(stages[0]["status"] == "completed", "Final requires completed own draft")
        else:
            require(stages[0]["status"] != "completed", "Completed D0 with unexplained missing F0 is not resolved coverage")
    require(type(summary.get("generation_requests_attempted")) is int and summary["generation_requests_attempted"] == attempts
            and type(terminal.get("generation_requests_attempted")) is int and terminal["generation_requests_attempted"] == attempts
            and 4 <= attempts <= 8 and type(summary.get("main_model_calls")) is int and summary["main_model_calls"] == 0
            and type(summary.get("automatic_retries")) is int and summary["automatic_retries"] == 0
            and type(summary.get("post_final_calls")) is int and summary["post_final_calls"] == 0,
            "Continuation coverage request accounting differs")
    require(timestamp(terminal["at_utc"]) <= timestamp(review["completed_at_utc"]), "Operating review precedes terminal observation")
    # No condition requires a correct raw sum, citation, source interpretation,
    # normalized vector, or all four F0 responses. Those are measured outcomes.


def validate_gate(path, expected_sha=None, *, runtime=None, run_directory=None):
    gate, reference = paths.read(path, expected_sha)
    gate_ref = {key: reference[key] for key in ("path", "sha256")}
    require(gate.get("receipt_version") == "sector_main_gate_1"
            and gate.get("status") == "approved_for_main_before_generation"
            and gate.get("review_mode") == "AI_delegated_by_user", "Separate approved prospective main gate required")
    scope(gate)
    frozen = checked(gate.get("freeze_ref"))
    scope(frozen)
    require(frozen.get("freeze_version") == "sector_main_freeze_1" and frozen.get("status") == "frozen_for_main_only",
            "Separate main freeze required")
    objects = {key: checked(gate.get(key)) for key in BOUND}
    for key in BOUND:
        require(frozen.get(key) == gate[key], "Main freeze/gate reference differs: " + key)
    run, reports = (paths.workspace_path(gate[key]) for key in ("run_directory", "output_root"))
    require(run != reports and run not in reports.parents and reports not in run.parents, "Main run/report trees must be separate")
    for key in ("run_directory", "output_root"):
        require(frozen.get(key) == gate[key], "Main output scope differs")
    cont_gate_ref = gate["continuation_gate_ref"]
    continuation.validate_gate(cont_gate_ref["path"], cont_gate_ref["sha256"])
    cont_gate = objects["continuation_gate_ref"]
    for previous in (paths.workspace_path(cont_gate["run_directory"]),
                     paths.workspace_path(cont_gate["output_root"]),
                     paths.workspace_path("data/local_sector_runtime/v494_pilot_20261025")):
        require(not run.is_relative_to(previous) and not previous.is_relative_to(run)
                and not reports.is_relative_to(previous) and not previous.is_relative_to(reports),
                "Main cannot overlap pilot raw/report namespaces")
    terminal, summary = objects["continuation_terminal_ref"], objects["continuation_summary_ref"]
    terminal_summary_ref = terminal.get("summary_ref", {})
    require(paths.workspace_path(terminal_summary_ref.get("path", "")) == paths.workspace_path(gate["continuation_summary_ref"]["path"])
            and terminal_summary_ref.get("sha256") == gate["continuation_summary_ref"]["sha256"], "Terminal summary binding differs")
    operating = objects["continuation_operating_review_ref"]
    validate_operating_review(operating, terminal, summary, gate["continuation_terminal_ref"], gate["continuation_summary_ref"])
    verify_nested_refs(operating)
    protocol = objects["protocol_ref"]
    scope(protocol)
    require(protocol.get("status") == "approved_design_for_prospective_main_freeze"
            and protocol.get("prepared_manifest_ref") == gate["prepared_manifest_ref"]
            and protocol.get("continuation_operating_review_ref") == gate["continuation_operating_review_ref"]
            and protocol.get("primary_final_allocation_endpoint") == "F0_derived_integer_allocation"
            and protocol.get("raw_diagnostics_required") is True
            and type(protocol.get("main_model_calls_before_freeze")) is int and protocol["main_model_calls_before_freeze"] == 0,
            "Prospective explicit derived-primary/raw-diagnostic design required")
    candidate = checked(protocol.get("candidate_ref"))
    require(candidate.get("purpose") == "prospective_main_candidate" and candidate.get("main_allowed") is False
            and candidate.get("design", {}).get("case_order") == list(CASES)
            and candidate.get("input_binding", {}).get("prepared_manifest_ref") == gate["prepared_manifest_ref"],
            "Reviewed pre-generation main candidate must remain bound")
    verify_nested_refs(candidate["input_binding"])
    require(protocol.get("evaluation_protocol_ref")
            == candidate.get("endpoint_contract", {}).get("precedence_over_original_r2", {}).get("original_ref"),
            "Original raw r2 evaluation must be explicitly bound alongside the derived primary amendment")
    checked(protocol["evaluation_protocol_ref"])
    require(protocol.get("exact_math_policy_ref") == gate["finalizer_acceptance_ref"], "Main endpoint must bind adopted exact math acceptance")
    from sector_main_runtime import validate_runtime, scientific_runtime, load_bundle
    selected = objects["runtime_ref"]
    validate_runtime(selected)
    instrument = scientific_runtime(selected)
    original_controls = checked(candidate["scientific_controls"]["reference_runtime_ref"])
    expected_controls = copy.deepcopy(original_controls)
    expected_controls["backend_evidence"][0] = instrument["backend_evidence"][0]
    require(original.base.canonical(expected_controls) == original.base.canonical(instrument), "Main scientific controls differ from reviewed pilot instrument")
    if runtime is not None:
        require(original.base.canonical(runtime) == original.base.canonical(selected), "Worker runtime differs from main freeze")
    loaded, cases = load_bundle()
    require(objects["prepared_manifest_ref"] == loaded["preparation_manifest"] and len(cases) == 5, "Main prepared manifest differs")
    acceptance = objects["finalizer_acceptance_ref"]
    require(acceptance.get("status") == "PASS" and acceptance.get("revision", {}).get("current_source_sha256")
            == original.remote.sha(paths.ROOT / "research/finalize_sector_allocation.py"), "Accepted unchanged pure finalizer required")
    require(objects["campaign_finalizer_review_ref"].get("status") == "PASS", "Passing campaign finalizer review required")
    verify_nested_refs(objects["campaign_finalizer_review_ref"])
    preflight = objects["main_D0_preflight_ref"]
    require(preflight.get("status") == "PASS" and preflight.get("generation_requests_sent") == 0
            and preflight.get("unexpected_generation_evidence_observed") is False
            and [c.get("case_id") for c in preflight.get("case_reviews", [])] == list(CASES)
            and preflight.get("source_free_L_L_C_identical") is True
            and preflight.get("output_reserve_tokens") == 8192 and preflight.get("context_tokens") == 65536,
            "Exact main D0 render-only/token preflight required")
    verify_nested_refs(preflight)
    for observed, prepared in zip(preflight["case_reviews"], loaded["preparation_manifest"]["prepared_cases"]):
        expected_ref = {key: prepared[key] for key in ("path", "sha256")}
        require(observed.get("status") == "PASS" and observed.get("prepared_messages_ref") == expected_ref,
                "Each main preflight must bind its exact prepared D0 bytes")
        capacity = observed.get("capacity", {})
        count = capacity.get("prompt_tokens")
        require(type(count) is int and count > 0 and capacity.get("allowed_output_tokens") == 8192
                and capacity.get("total_required_tokens") == count + 8192 <= 65536
                and capacity.get("context_tokens") == 65536, "Main exact D0 capacity must preserve the full output reserve")
    ft, gt = timestamp(frozen["recorded_at_utc"]), timestamp(gate["recorded_at_utc"])
    require(timestamp(operating["completed_at_utc"]) <= timestamp(protocol["recorded_at_utc"]) <= ft <= gt,
            "Operating review, final protocol, freeze and gate must be prospective")
    code_refs = frozen.get("code_refs", [])
    names = [checked(item, json_object=False).relative_to(paths.ROOT).as_posix() for item in code_refs]
    require(len(names) == len(set(names)) and REQUIRED_CODE.issubset(names), "All main and inherited executable dependencies must be frozen")
    reviews = frozen.get("review_refs")
    require(gate.get("review_refs") == reviews, "Main freeze/gate review references differ")
    validate_reviews(reviews, ft)
    if run_directory is not None:
        require(paths.workspace_path(run_directory) == run, "Worker main namespace differs")
        declaration = original.remote.read(run / "campaign_declaration.json")
        started = original.remote.read(run / "execution_started.json")
        scope(declaration)
        require(declaration.get("review_gate") == gate_ref and declaration.get("freeze_ref") == gate["freeze_ref"]
                and declaration.get("runtime") == selected, "Main declaration binding differs")
        for key in BOUND:
            require(declaration.get(key) == gate[key], "Main declaration reference differs: " + key)
        require(gt <= timestamp(declaration["created_at_utc"]) <= timestamp(started["at_utc"]), "Main start predates its gate")
    return {"status": "prospective_main_gate_verified", "gate_ref": gate_ref, "freeze_ref": gate["freeze_ref"],
            "runtime_ref": gate["runtime_ref"], "protocol_ref": gate["protocol_ref"],
            "run_directory": str(run), "output_root": str(reports), "main_allowed": True}
