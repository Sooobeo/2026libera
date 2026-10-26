"""Prospective gate for one explicitly authorized pilot continuation segment."""
from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path

import prepare_sector_v491 as paths
import sector_v494_runtime as original
from sector_v494_review_gate import validate_review_gate as historical_gate

CASES = ("fidelity_q2_2026__L", "ubs_june_2026__E", "ubs_june_2026__L", "common_market_only__C")
BOUND = ("runtime_ref", "protocol_ref", "historical_gate_ref", "historical_terminal_ref",
         "historical_summary_ref", "prepared_manifest_ref", "finalizer_acceptance_ref")
REQUIRED_CODE = {"research/sector_continuation_gate.py", "research/sector_continuation_runtime.py",
                 "research/sector_continuation_awake.py", "research/run_sector_continuation.py",
                 "research/finalize_sector_allocation.py", "research/finalize_sector_campaign.py",
                 "research/review_sector_v494_stage.py"}


def require(value, message):
    if not value:
        raise ValueError(message)


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "Timezone-aware timestamp required")
    return parsed


def checked(reference, *, json_object=True):
    require(isinstance(reference, dict) and set(reference) == {"path", "sha256"}, "Exact path/hash reference required")
    path = paths.workspace_path(reference["path"])
    require(original.remote.sha(path) == reference["sha256"], "Referenced bytes changed: " + str(path))
    return original.remote.read(path) if json_object else path


def scope(value, *, require_observed=True):
    require(value.get("purpose") == "pilot_continuation" and value.get("case_order") == list(CASES), "Exact remaining pilot cells required")
    for key, expected in (("max_generation_requests", 8), ("historical_generation_requests", 3),
                          ("campaign_max_generation_requests", 11), ("automatic_retries", 0)):
        require(type(value.get(key)) is int and value[key] == expected, "Wrong continuation accounting: " + key)
    require(value.get("main_allowed") is False and (not require_observed or value.get("old_outputs_observed") is True),
            "Main forbidden; observed-output continuation chronology must be explicit")
    require(value.get("explicit_retry_slots") == ["fidelity_q2_2026__L__D0"], "Only one specifically authorized historical retry")


def validate_gate(path, expected_sha=None, *, runtime=None, run_directory=None):
    gate, gate_ref = paths.read(path, expected_sha)
    gate_ref = {key: gate_ref[key] for key in ("path", "sha256")}
    require(gate.get("receipt_version") == "sector_continuation_gate_1"
            and gate.get("status") == "approved_for_continuation_before_generation"
            and gate.get("review_mode") == "AI_delegated_by_user", "Completed prospective AI continuation gate required")
    scope(gate)
    objects = {name: checked(gate.get(name)) for name in BOUND}
    frozen = checked(gate.get("freeze_ref"))
    require(frozen.get("freeze_version") == "sector_continuation_freeze_1"
            and frozen.get("status") == "frozen_for_pilot_continuation_only", "New continuation freeze required")
    scope(frozen)
    for name in BOUND:
        require(gate[name] == frozen.get(name), "Freeze reference differs: " + name)
    for name in ("run_directory", "output_root"):
        require(paths.workspace_path(gate[name]) == paths.workspace_path(frozen[name]), "Frozen output location differs")
    run, reports = (paths.workspace_path(gate[name]) for name in ("run_directory", "output_root"))
    require(run != reports and run not in reports.parents and reports not in run.parents, "Separate run/report trees required")
    history = objects["historical_gate_ref"]
    historical_gate(gate["historical_gate_ref"]["path"], gate["historical_gate_ref"]["sha256"])
    old_runtime = checked(history["runtime_ref"])
    selected = objects["runtime_ref"]
    original.validate_runtime(selected)
    old_scientific, new_scientific = copy.deepcopy(old_runtime), copy.deepcopy(selected)
    old_scientific["backend_evidence"][0] = new_scientific["backend_evidence"][0]
    require(old_scientific == new_scientific, "Only the newly owned CPU service receipt may change from historical runtime")
    if runtime is not None:
        require(runtime == selected, "Caller runtime differs from new freeze")
    require(gate["prepared_manifest_ref"] == history["prepared_manifest_ref"], "Original prepared inputs must remain exact")
    protocol = objects["protocol_ref"]
    scope(protocol, require_observed=False)
    require(protocol.get("historical_first_attempt_results_unchanged") is True, "Original first attempts remain immutable")
    terminal, summary = objects["historical_terminal_ref"], objects["historical_summary_ref"]
    require(terminal.get("status") == "stopped_semantic_review_pending"
            and terminal.get("summary_ref") is not None, "Historical interrupted terminal receipt required")
    require(paths.workspace_path(terminal["summary_ref"]["path"]) == paths.workspace_path(gate["historical_summary_ref"]["path"])
            and terminal["summary_ref"]["sha256"] == gate["historical_summary_ref"]["sha256"], "Historical terminal/summary binding differs")
    require(summary.get("generation_requests_attempted") == 3
            and [row.get("case_id") for row in summary.get("cases", [])] == list(original.CASES), "Historical denominator/accounting differs")
    rows = summary["cases"]
    require([(s.get("stage"), s.get("status"), s.get("generation_requests_attempted")) for s in rows[0]["stages"]]
            == [("D0", "completed", 1), ("F0", "completed", 1)], "Completed Fidelity E must only be referenced")
    require([(s.get("stage"), s.get("status"), s.get("generation_requests_attempted")) for s in rows[1]["stages"]]
            == [("D0", "hard_deadline", 1)] and all(not row["stages"] for row in rows[2:]), "Historical remaining-cell status differs")
    code = frozen.get("code_refs", [])
    names = [checked(ref, json_object=False).relative_to(paths.ROOT).as_posix() for ref in code]
    require(len(names) == len(set(names)) and REQUIRED_CODE.issubset(names), "All new executable sources must be frozen")
    acceptance = objects["finalizer_acceptance_ref"]
    require(acceptance.get("status") == "PASS"
            and acceptance.get("revision", {}).get("current_source_sha256")
                == original.remote.sha(paths.ROOT / "research/finalize_sector_allocation.py"),
            "Accepted exact mathematical finalizer source required")
    ft, gt = timestamp(frozen["recorded_at_utc"]), timestamp(gate["recorded_at_utc"])
    require(ft <= gt, "Freeze must precede gate")
    reviews = frozen.get("review_refs")
    require(isinstance(reviews, list) and reviews and gate.get("review_refs") == reviews, "Bound pre-freeze reviews required")
    for reference in reviews:
        review = checked(reference)
        require(review.get("status") == "PASS" and timestamp(review["completed_at_utc"]) <= ft, "Completed pre-freeze review required")
        for axis in ("errors", "consistency", "paper_topic"):
            item = review.get("review_axes", {}).get(axis, {})
            require(item.get("pass") is True and isinstance(item.get("reason"), str) and item["reason"].strip(), "Review axis absent")
    if run_directory is not None:
        require(paths.workspace_path(run_directory) == run, "Worker run path differs from new freeze")
        declaration = original.remote.read(run / "campaign_declaration.json")
        started = original.remote.read(run / "execution_started.json")
        scope(declaration)
        require(declaration.get("review_gate") == gate_ref and declaration.get("freeze_ref") == gate["freeze_ref"]
                and declaration.get("runtime_ref") == gate["runtime_ref"] and declaration.get("protocol_ref") == gate["protocol_ref"]
                and declaration.get("runtime") == selected, "Declaration differs from continuation freeze")
        require(gt <= timestamp(declaration["created_at_utc"]) <= timestamp(started["at_utc"]), "Prospective chronology differs")
    return {"status": "prospective_continuation_gate_verified", "gate_ref": gate_ref, "freeze_ref": gate["freeze_ref"],
            "runtime_ref": gate["runtime_ref"], "protocol_ref": gate["protocol_ref"], "run_directory": str(run),
            "output_root": str(reports), "historical_first_attempt_results_unchanged": True, "main_allowed": False}
