"""One new source-free F0; immutable prior D0 and late review stay in place.

The three worker/transport functions below are byte-identical source copies of
the frozen remaining implementation. Only their local spec/gate namespace is new.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sector_remaining_runtime as old
import sector_remaining_gate as old_gate
from sector_remaining_awake import POWER_POLICY

base, prepare, prior, awake, contract = old.base, old.prepare, old.prior, old.awake, old.contract
remote, bench, ROOT = old.remote, old.bench, old.ROOT
CapacityFailure, STAGE_DEADLINE_SECONDS = old.CapacityFailure, old.STAGE_DEADLINE_SECONDS
validate_runtime, load_bundle, request_body = old.validate_runtime, old.load_bundle, old.request_body
artifact_ref, expected_stage_directory = old.artifact_ref, old.expected_stage_directory
validate_worker_location, check_token_capacity, value_sha = old.validate_worker_location, old.check_token_capacity, old.value_sha
DRAFT_ARTIFACTS = old.DRAFT_ARTIFACTS
paths, checked, require, timestamp = old_gate.paths, old_gate.checked, old_gate.require, old_gate.timestamp
same_ref, verify_nested_refs = old_gate.same_ref, old_gate.verify_nested_refs
PURPOSE = "pilot_last_final"
CASES = ("common_market_only__C",)
STAGE_ORDER = (CASES[0] + "__F0",)
STAGES_BY_CASE = {CASES[0]: ("F0",)}
EXTERNAL_GROUPS = old_gate.EXTERNAL_GROUPS
BOUND = (*old_gate.BOUND, "prior_remaining_gate_ref", "prior_remaining_terminal_ref",
         "prior_remaining_summary_ref", "prior_remaining_declaration_ref",
         "prior_remaining_cancel_ref", "prior_pause_checkpoint_ref", "resumption_design_ref", "last_finalizer_review_ref")
NEW_REVIEW_CODE = {"research/run_sector_last_final.py", "research/test_sector_last_final.py",
                   "research/last_final_20261026/runtime_adapter.py"}
REQUIRED_CODE = old_gate.REQUIRED_CODE | NEW_REVIEW_CODE | {
    "research/freeze_sector_last_final.py", "research/publish_last_final_review_ack.py",
    "research/finalize_sector_last_final.py", "research/test_finalize_sector_last_final.py"}
EXTRA_ROLES = {"stage_review", "allocation_math", "semantic_review", "semantic_validation",
               "root_review", "terminal", "summary", "declaration", "final_construction"}


def scope(value):
    expected = {"purpose": PURPOSE, "case_order": list(CASES), "stage_order": list(STAGE_ORDER),
        "max_generation_requests": 1, "historical_generation_requests": 10,
        "campaign_max_generation_requests": 11, "automatic_retries": 0, "post_final_calls": 0,
        "main_model_calls": 0, "main_allowed": False, "old_outputs_observed": True,
        "historical_first_attempt_results_unchanged": True, "analysis_role": "primary_exploratory",
        "excluded_new_main_execution": True, "explicit_retry_slots": [],
        "historical_explicit_retry_slots": ["fidelity_q2_2026__L__D0"]}
    for key, wanted in expected.items():
        require(type(value.get(key)) is type(wanted) and value[key] == wanted, "Last-final scope differs: " + key)
    require(base.canonical(value.get("power_policy")) == base.canonical(POWER_POLICY), "Unchanged battery policy required")


def validate_history(value):
    prior_gate = checked(value["prior_remaining_gate_ref"])
    old_gate.validate_gate(value["prior_remaining_gate_ref"]["path"], value["prior_remaining_gate_ref"]["sha256"])
    for key in old_gate.BOUND:
        if key not in ("runtime_ref", "protocol_ref"):
            require(same_ref(prior_gate.get(key), value[key]), "Earlier history changed: " + key)
    terminal = checked(value["prior_remaining_terminal_ref"])
    summary = checked(value["prior_remaining_summary_ref"])
    declaration = checked(value["prior_remaining_declaration_ref"])
    run = paths.workspace_path(declaration["run_directory"])
    require(run == paths.workspace_path("data/local_sector_runtime/v494_remaining_20261026"), "Exact interrupted prior namespace required")
    require(same_ref(declaration.get("review_gate"), value["prior_remaining_gate_ref"])
            and same_ref(terminal.get("summary_ref"), value["prior_remaining_summary_ref"])
            and same_ref(terminal.get("declaration_ref"), value["prior_remaining_declaration_ref"]), "Prior terminal identities differ")
    require(terminal.get("status") == "stopped_semantic_review_pending"
            and terminal.get("purpose") == "pilot_completion_resume"
            and terminal.get("awake_release", {}).get("status") == "released"
            and any(e.get("type") == "Cancelled" for e in terminal.get("errors", [])), "Preserve the user-cancelled released terminal")
    require(summary.get("purpose") == "pilot_completion_resume" and summary.get("status") == "stopped"
            and summary.get("case_order") == list(old_gate.CASES), "Prior remaining denominator changed")
    for obj in (summary, terminal):
        for key, expected in (("generation_requests_attempted", 4), ("automatic_retries", 0), ("main_model_calls", 0)):
            require(type(obj.get(key)) is int and obj[key] == expected, "Prior request accounting differs: " + key)
    require(summary.get("historical_generation_requests") == 6 and summary.get("campaign_generation_requests_attempted") == 10,
            "Six previous plus four remaining requests must stay ten")
    require([r.get("case_id") for r in summary.get("cases", [])] == list(old_gate.CASES), "Prior case rows differ")
    observed = [(r["case_id"] + "__" + s["stage"], s["status"], s["generation_requests_attempted"])
                for r in summary["cases"] for s in r.get("stages", [])]
    require(observed == [(name, "completed", 1) for name in old_gate.STAGE_ORDER[:-1]], "Only the four completed prior stages may be carried")
    require(all(type(s.get("generation_requests_attempted")) is int for row in summary["cases"] for s in row["stages"]),
            "Historical stage attempt counts must be integers")
    require(not (run / STAGE_ORDER[0]).exists(), "Previous C F0 must never have started")
    cancel = checked(value["prior_remaining_cancel_ref"], json_object=False)
    require(cancel == run / "CANCEL", "Original CANCEL identity required")
    pause = checked(value["prior_pause_checkpoint_ref"])
    verify_nested_refs(pause)
    require(paths.workspace_path(value["prior_pause_checkpoint_ref"]["path"])
            == paths.workspace_path("research/remaining_20261026/pause_checkpoint_20261026T0513.json"), "Original pause checkpoint required")
    return terminal, summary, declaration, prior_gate


def validated_external_draft(value, *, require_final=True):
    refs, extras = (value.get(k) for k in EXTERNAL_GROUPS)
    require(isinstance(refs, dict) and set(refs) == set(DRAFT_ARTIFACTS), "Five exact external draft artifacts required")
    required = EXTRA_ROLES if require_final else EXTRA_ROLES - {"final_construction"}
    require(isinstance(extras, dict) and set(extras) == required, "Exact late-reviewed draft evidence roles required")
    declaration = checked(value["prior_remaining_declaration_ref"])
    run, reports = (paths.workspace_path(declaration[k]) for k in ("run_directory", "output_root"))
    require(run == paths.workspace_path("data/local_sector_runtime/v494_remaining_20261026"), "Fixed prior draft run required")
    folder = run / (CASES[0] + "__D0")
    records = {}
    for role, filename in DRAFT_ARTIFACTS.items():
        require(paths.workspace_path(refs[role]["path"]) == folder / filename, "External D0 path/role substitution")
        records[role] = checked(refs[role])
    evidence = {key: checked(reference) for key, reference in extras.items()}
    expected = {"stage_review": folder / "stage_review.json", "allocation_math": reports / "allocation_math" / (CASES[0] + "__D0.json"),
        "terminal": reports / "terminal_receipt.json", "summary": run / "campaign_summary.json", "declaration": run / "campaign_declaration.json"}
    for key, target in expected.items():
        require(paths.workspace_path(extras[key]["path"]) == target, "External evidence location differs: " + key)
    for role, key in (("terminal", "prior_remaining_terminal_ref"), ("summary", "prior_remaining_summary_ref"), ("declaration", "prior_remaining_declaration_ref")):
        require(same_ref(extras[role], value[key]), "External history reference differs")
    require(not (folder / "external_review_ack.json").exists(), "Original missing ACK must not be backfilled after terminal")
    old_spec = records["worker_spec"]
    require(old_spec.get("case_id") == CASES[0] and old_spec.get("stage") == "D0"
            and paths.workspace_path(old_spec["run_directory"]) == run, "Only immutable control draft may be carried")
    old.validate_spec(old_spec)
    raw = records["response"]["message"]["content"]
    canonical_refs = {role: old.artifact_ref(folder / filename) for role, filename in DRAFT_ARTIFACTS.items()}
    require(all(same_ref(refs[k], canonical_refs[k]) for k in refs), "External normalized draft identities differ")
    probe = copy.deepcopy(old_spec)
    probe.update(stage="F0", raw_draft=raw, draft_artifacts=canonical_refs)
    old.validate_prior_draft(probe)
    review = evidence["stage_review"]
    require(review.get("case_id") == CASES[0] and review.get("stage") == "D0"
            and review.get("instrument_integrity_pass") is True, "Completed control instrument review required")
    for key in ("semantic_review", "root_review"):
        item = evidence[key]
        require(item.get("review_status") == "completed" and item.get("case_id") == CASES[0]
                and item.get("stage") == "D0" and same_ref(item.get("transport_ref"), refs["transport_result"]), "Completed same-draft late review required")
        for axis in ("errors", "consistency", "paper_topic"):
            ax = item.get("review_axes", {}).get(axis, {})
            require(ax.get("reviewed") is True and isinstance(ax.get("reason"), str) and ax["reason"].strip(), "Three completed late-review axes required")
        require(timestamp(evidence["terminal"]["at_utc"]) <= timestamp(item["completed_at_utc"]), "Late review chronology must remain explicit")
        verify_nested_refs(item)
    validation = evidence["semantic_validation"]
    require(validation.get("status") == "PASS" and type(validation.get("failed_checks_count")) is int
            and validation["failed_checks_count"] == 0
            and same_ref(validation.get("review_ref"), extras["semantic_review"])
            and same_ref(validation.get("transport_ref"), refs["transport_result"]), "Exact semantic reference/quote validation required")
    verify_nested_refs(validation)
    for key, role in (("worker_spec_ref", "worker_spec"), ("response_ref", "response")):
        require(same_ref(evidence["semantic_review"].get(key), refs[role]), "Semantic review draft binding differs")
    for key, role in (("stage_review_ref", "stage_review"), ("allocation_math_ref", "allocation_math")):
        require(same_ref(evidence["semantic_review"].get(key), extras[role]), "Semantic review diagnostic binding differs")
    loaded, cases = load_bundle()
    case = next(c for c in cases if c["case_id"] == CASES[0])
    require(case["arm"] == "C" and case["assigned_packet"] is None, "Source-free control condition required")
    final = contract.build_final_messages(draft_messages=case["messages"], raw_draft=raw,
        assigned_packet=case["assigned_packet"], prompt_contract=loaded["prompt_contract"], response_schema=loaded["response_schema"])
    require(final.get("ready") is True, "Immutable actual draft must permit final construction")
    if require_final:
        require(paths.workspace_path(extras["final_construction"]["path"]).is_relative_to(paths.workspace_path("research/last_final_20261026"))
                and base.canonical(final) == base.canonical(evidence["final_construction"]), "Prospective final construction differs from exact immutable contract")
    return {"raw_draft": raw, "draft_artifacts": refs, "old_spec": old_spec, "final": final,
            "external_evidence_refs": extras, "old_missing_ACK_retained": True}


def prepare_external():
    """Offline bootstrap, independent of the not-yet-written new protocol/gate.

    Caller exclusively saves final_construction in the new namespace, adds its
    exact artifact_ref to external_draft_evidence_refs, then writes the protocol.
    No file, service, process, model or old ACK mutation occurs here.
    """
    run = ROOT / "data/local_sector_runtime/v494_remaining_20261026"
    reports = ROOT / "research/remaining_20261026/run_reports"
    semantic = ROOT / "research/remaining_20261026/semantic"
    stem = CASES[0] + "__D0"
    folder = run / stem
    refs = {role: artifact_ref(folder / filename) for role, filename in DRAFT_ARTIFACTS.items()}
    extras = {"stage_review": artifact_ref(folder / "stage_review.json"),
        "allocation_math": artifact_ref(reports / "allocation_math" / (stem + ".json")),
        "semantic_review": artifact_ref(semantic / (stem + "_review.json")),
        "semantic_validation": artifact_ref(semantic / (stem + "_review_validation.json")),
        "root_review": artifact_ref(semantic / (stem + "_root_review.json")),
        "terminal": artifact_ref(reports / "terminal_receipt.json"),
        "summary": artifact_ref(run / "campaign_summary.json"),
        "declaration": artifact_ref(run / "campaign_declaration.json")}
    value = {"external_draft_refs": refs, "external_draft_evidence_refs": extras,
        **{"prior_remaining_" + key + "_ref": extras[key] for key in ("terminal", "summary", "declaration")}}
    carried = validated_external_draft(value, require_final=False)
    return {**value, "final_construction": carried["final"], "model_calls": 0, "old_ACK_modified": False}


def validate_reviews(reviews, frozen_at):
    require(isinstance(reviews, list) and len(reviews) >= 3, "Three completed separate prelaunch reviews required")
    seen_paths, seen_hashes, reviewed = set(), set(), set()
    for reference in reviews:
        review = checked(reference)
        path = paths.workspace_path(reference["path"])
        require(path not in seen_paths and reference["sha256"] not in seen_hashes,
                "Duplicate prospective review path or bytes")
        seen_paths.add(path); seen_hashes.add(reference["sha256"])
        require(review.get("status") == "PASS" and timestamp(review["completed_at_utc"]) <= frozen_at,
                "Completed pre-freeze review required")
        reviewed.update(paths.workspace_path(x["path"]).relative_to(ROOT).as_posix() for x in verify_nested_refs(review))
        for axis in ("errors", "consistency", "paper_topic"):
            ax = review.get("review_axes", {}).get(axis, {})
            require(ax.get("pass") is True and isinstance(ax.get("reason"), str) and ax["reason"].strip(), "All review axes require evidence")
    require(NEW_REVIEW_CODE.issubset(reviewed), "Reviews must bind current coordinator/adapter/tests")


def validate_gate(path, expected_sha=None, *, runtime=None, run_directory=None):
    gate, reference = paths.read(path, expected_sha)
    gate_ref = {k: reference[k] for k in ("path", "sha256")}
    require(gate.get("receipt_version") == "sector_last_final_gate_1" and gate.get("status") == "approved_for_last_final_before_generation"
            and gate.get("review_mode") == "AI_delegated_by_user", "New final-only delegated gate required")
    scope(gate)
    frozen = checked(gate.get("freeze_ref")); scope(frozen)
    require(frozen.get("freeze_version") == "sector_last_final_freeze_1" and frozen.get("status") == "frozen_for_pilot_last_final_only", "New final-only freeze required")
    for key in (*BOUND, *EXTERNAL_GROUPS, "run_directory", "output_root"):
        require(gate.get(key) == frozen.get(key), "Freeze binding differs: " + key)
    objects = {key: checked(gate[key], json_object=key != "prior_remaining_cancel_ref") for key in BOUND}
    terminal, _, declaration, prior_gate = validate_history(gate)
    carried = validated_external_draft(gate)
    run, reports = (paths.workspace_path(gate[k]) for k in ("run_directory", "output_root"))
    require(run == paths.workspace_path("data/local_sector_runtime/v494_last_final_20261026")
            and reports == paths.workspace_path("research/last_final_20261026/run_reports"), "Exact fresh last-final namespaces required")
    selected = objects["runtime_ref"]
    validate_runtime(selected)
    expected = copy.deepcopy(carried["old_spec"]["runtime"])
    expected["backend_evidence"][0] = selected["backend_evidence"][0]
    require(base.canonical(expected) == base.canonical(selected), "Only the owned service receipt may differ scientifically")
    if runtime is not None:
        require(base.canonical(runtime) == base.canonical(selected), "Caller runtime differs from freeze")
    protocol = objects["protocol_ref"]; scope(protocol)
    require(protocol.get("status") == "approved_design_for_prospective_last_final_freeze"
            and same_ref(protocol.get("prepared_manifest_ref"), gate["prepared_manifest_ref"])
            and same_ref(protocol.get("exact_math_policy_ref"), gate["finalizer_acceptance_ref"])
            and protocol.get("primary_final_allocation_endpoint") == "F0_derived_integer_allocation"
            and protocol.get("raw_diagnostics_required") is True, "Prospective unchanged exploratory endpoint required")
    for key in (*old_gate.BOUND, *BOUND[len(old_gate.BOUND):-1], *EXTERNAL_GROUPS):
        if key not in ("runtime_ref", "protocol_ref"):
            require(protocol.get(key) == gate[key], "Protocol history binding differs: " + key)
    acceptance = objects["finalizer_acceptance_ref"]
    require(acceptance.get("status") == "PASS" and acceptance.get("revision", {}).get("current_source_sha256")
            == remote.sha(ROOT / "research/finalize_sector_allocation.py"), "Unchanged accepted exact math required")
    ft, gt = timestamp(frozen["recorded_at_utc"]), timestamp(gate["recorded_at_utc"])
    require(timestamp(terminal["at_utc"]) <= timestamp(protocol["recorded_at_utc"]) <= ft <= gt, "Prospective chronology differs")
    for role in ("semantic_review", "semantic_validation", "root_review"):
        require(timestamp(checked(gate["external_draft_evidence_refs"][role])["completed_at_utc"]) <= timestamp(protocol["recorded_at_utc"]), "Protocol must follow actual late review")
    finalizer_review = objects["last_finalizer_review_ref"]
    require(finalizer_review.get("status") == "PASS" and timestamp(finalizer_review["completed_at_utc"]) <= ft, "Reviewed new finalizer required")
    reviewed_finalizer = verify_nested_refs(finalizer_review)
    require(any(paths.workspace_path(r["path"]) == ROOT / "research/finalize_sector_last_final.py" for r in reviewed_finalizer), "Finalizer review must bind current new source")
    code = frozen.get("code_refs", [])
    names = [checked(r, json_object=False).relative_to(ROOT).as_posix() for r in code]
    require(len(names) == len(set(names)) and REQUIRED_CODE.issubset(names), "All new and inherited executable sources must be frozen")
    code_map = {paths.workspace_path(r["path"]): r["sha256"] for r in code}
    old_frozen = checked(prior_gate["freeze_ref"])
    require(all(code_map.get(paths.workspace_path(r["path"])) == r["sha256"] for r in old_frozen["code_refs"]), "All65 inherited frozen references must remain exact")
    reviews = frozen.get("review_refs")
    require(reviews == gate.get("review_refs"), "Freeze/gate reviews differ")
    validate_reviews(reviews, ft)
    if run_directory is not None:
        require(paths.workspace_path(run_directory) == run, "Last-final worker namespace differs")
        current = remote.read(run / "campaign_declaration.json"); scope(current)
        started = remote.read(run / "execution_started.json")
        require(current.get("review_gate") == gate_ref and current.get("freeze_ref") == gate["freeze_ref"]
                and base.canonical(current.get("runtime")) == base.canonical(selected), "Actual declaration identity differs")
        for key in (*BOUND, *EXTERNAL_GROUPS):
            require(current.get(key) == gate[key], "Actual declaration reference differs: " + key)
        require(gt <= timestamp(current["created_at_utc"]) <= timestamp(started["at_utc"]), "Execution predates gate")
    return {"status": "prospective_last_final_gate_verified", "gate_ref": gate_ref, "freeze_ref": gate["freeze_ref"],
            "runtime_ref": gate["runtime_ref"], "protocol_ref": gate["protocol_ref"], "run_directory": str(run), "output_root": str(reports), "main_allowed": False}


def validate_prior_draft(spec):
    pinned = checked(spec["review_gate"])
    carried = validated_external_draft(pinned)
    refs = spec.get("draft_artifacts")
    require(isinstance(refs, dict) and set(refs) == set(DRAFT_ARTIFACTS)
            and all(same_ref(refs[k], carried["draft_artifacts"][k]) for k in refs), "Final draft artifacts differ")
    require(spec.get("raw_draft") == carried["raw_draft"], "Final draft text must remain exact")
    expected = copy.deepcopy(carried["old_spec"]["runtime"])
    expected["backend_evidence"][0] = spec["runtime"]["backend_evidence"][0]
    require(base.canonical(expected) == base.canonical(spec["runtime"]), "Historical scientific runtime differs")
    require(base.canonical(spec["body"]["messages"]) == base.canonical(carried["final"]["messages"]), "Final message history differs from fixed construction")
    return {"status": "explicit_external_completed_control_D0_artifacts_bound", "artifact_refs": refs,
            "external_evidence_refs": pinned["external_draft_evidence_refs"], "old_missing_ACK_retained": True,
            "raw_draft_utf8_sha256": hashlib.sha256(spec["raw_draft"].encode()).hexdigest()}


def validate_spec(spec):
    validate_runtime(spec["runtime"])
    validate_gate(spec["review_gate"]["path"], spec["review_gate"]["sha256"], runtime=spec["runtime"], run_directory=spec["run_directory"])
    require(spec.get("case_id") == CASES[0] and spec.get("stage") == "F0", "Only one control F0 is authorized")
    require(Path(spec["cancel_path"]).resolve() == paths.workspace_path(spec["run_directory"]) / "CANCEL", "New run CANCEL identity required")
    remote.validate_origin(spec["origin"])
    service = prepare.read(spec["runtime"]["backend_evidence"][0]["path"], spec["runtime"]["backend_evidence"][0]["sha256"])[0]
    require(spec["origin"] == service["origin"], "Owned service origin differs")
    provenance = validate_prior_draft(spec)
    loaded, cases = load_bundle()
    case = next(c for c in cases if c["case_id"] == CASES[0])
    final = contract.build_final_messages(draft_messages=case["messages"], raw_draft=spec["raw_draft"],
        assigned_packet=case["assigned_packet"], prompt_contract=loaded["prompt_contract"], response_schema=loaded["response_schema"])
    require(final["ready"] and base.canonical(spec["body"]) == base.canonical(request_body(spec["runtime"], final["messages"], loaded["response_schema"])), "Exact source-free F0 body required")
    require(type(spec["deadline_seconds"]) is int and spec["deadline_seconds"] == STAGE_DEADLINE_SECONDS, "Fixed4500second ceiling required")
    return {"status": "validated", "case_id": CASES[0], "stage": "F0", "body_value_sha256": value_sha(spec["body"]),
        "visible_evidence_ids": sorted(final["visible_evidence_ids_for_final"]), "expected_source_packet": None, "draft_provenance": provenance}


def worker(spec_path):
    spec = remote.read(spec_path)
    target = Path(spec_path).parent
    session = bench.ProbeSession(target, spec["origin"], spec["deadline_seconds"], 2)
    outcome = {"status": "started", "automatic_retries": 0, "main_model_calls": 0,
               "system_integrity_incident": False}
    started, phase, awake_token = time.monotonic(), "preflight", None

    def record_phase(value):
        with (target / "worker_phases.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"phase": value, "at_utc": remote.now()}) + "\n")
            handle.flush()

    try:
        record_phase(phase)
        validate_worker_location(spec, target)
        validation = validate_spec(spec)
        remote.save(target / "spec_validation.json", validation)
        awake_token = awake.acquire()
        remote.save(target / "awake_acquire.json", awake_token)
        if awake_token.get("status") != "active":
            raise RuntimeError("Temporary awake request could not be established")
        session.start_monitor()
        for phase in ("before_render", "before_generation"):
            record_phase(phase)
            if Path(spec["cancel_path"]).exists():
                raise remote.Cancelled("Cancellation requested")
            pin = bench.observe(spec["origin"], base.MODEL)
            base.assert_pin(pin)
            remote.save(target / ("pin_" + phase + ".json"), pin)
            if phase == "before_render":
                phase = "render"
                record_phase(phase)
                prior.render_call(session, spec["body"], spec["body"]["messages"][0]["content"])
                rendered = (target / "render_only/rendered_prompt.txt").read_bytes().decode("utf-8")
                phase = "exact_token_count"
                record_phase(phase)
                from sector_v491_tokenizer import count_rendered_tokens
                count = count_rendered_tokens(rendered, spec["runtime"]["tokenizer_config"])
                remote.save(target / "tokenizer_receipt.json", count)
                remote.save(target / "context_capacity.json", check_token_capacity(count, rendered, spec["runtime"]))
        phase = "generation"
        record_phase(phase)
        response = remote.stream_call(session, "/api/chat", spec["body"], "generation")
        if (response.get("model") != base.MODEL or response.get("message", {}).get("thinking")
                or response.get("message", {}).get("tool_calls") or response.get("done_reason") not in ("stop", "length")):
            raise RuntimeError("Unexpected generation envelope; original response retained")
        if response["done_reason"] == "length":
            outcome.update(status="output_limit_reached", continuation_eligible=False)
        else:
            phase = "response_validation"
            record_phase(phase)
            result = contract.validate_response(response.get("message", {}).get("content"),
                response_schema=spec["body"]["format"],
                visible_evidence_ids=validation["visible_evidence_ids"],
                expected_source_packet=validation["expected_source_packet"])
            remote.save(target / "response_contract_validation.json", result)
            if result["continuation_eligible"]:
                payload = contract.strict_json(spec["body"]["messages"][1]["content"])
                previous = contract.strict_json(spec["raw_draft"])["sectors"] if spec["stage"] == "F0" else None
                calculated = contract.evaluate_submission(result["parsed"], market=payload["common_market"],
                    visible_evidence_ids=validation["visible_evidence_ids"], endpoint_id=spec["stage"],
                    previous_sectors=previous)
                remote.save(target / "submission_calculation.json", calculated)
            outcome.update(status="completed" if result["continuation_eligible"] else "model_structure_failure",
                           continuation_eligible=result["continuation_eligible"],
                           arithmetic_valid=bool(result.get("arithmetic") and result["arithmetic"]["valid"]),
                           citation_visibility_valid=result["visibility_valid"])
    except BaseException as exc:
        remote_status = exc.result.get("status") if isinstance(exc, remote.RemoteCallError) else None
        cancelled = isinstance(exc, (KeyboardInterrupt, remote.Cancelled)) or remote_status == "cancelled"
        timeout = phase == "generation" and remote_status == "timeout"
        outcome.update(status="cancelled" if cancelled else "case_timeout" if timeout else "capacity_failure" if isinstance(exc, CapacityFailure) else "failed",
                       system_integrity_incident=not (cancelled or timeout), failure_phase=phase,
                       error_type=type(exc).__name__, error=str(exc), continuation_eligible=False)
    finally:
        session.stop_monitor()
        if awake_token is not None:
            released = awake.release(awake_token)
            remote.save(target / "awake_release.json", released)
            if released.get("status") != "released":
                outcome.update(status="awake_cleanup_not_confirmed", system_integrity_incident=True,
                               continuation_eligible=False)
        outcome.update(elapsed_seconds=time.monotonic() - started, **prior.call_accounting(target))
        remote.save(target / "worker_summary.json", outcome)
    return 0 if outcome["status"] == "completed" else 1


def supervise(spec_path, tick=None):
    target = Path(spec_path).parent
    spec = remote.read(spec_path)
    validate_worker_location(spec, target)
    validate_spec(spec)
    started, stopped = time.monotonic(), None
    with (target / "worker.console.log").open("xb") as log:
        process = subprocess.Popen([sys.executable, "-B", "-X", "utf8", str(Path(__file__).resolve()),
                                    "--worker", str(spec_path)], stdout=log, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            while process.poll() is None:
                if tick is not None:
                    tick()
                remaining = spec["deadline_seconds"] - (time.monotonic() - started)
                if Path(spec["cancel_path"]).exists():
                    stopped = "cancelled"; break
                if remaining <= 0:
                    stopped = "hard_deadline"; break
                time.sleep(min(0.05, remaining))
        except KeyboardInterrupt:
            stopped = "cancelled"
        except BaseException:
            # An offline exception must not leave an unobserved generator alive.
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            raise
        if stopped:
            process.kill(); process.wait(timeout=3)
        else:
            process.wait()
    result = {"status": stopped or "worker_exited", "worker_exit_code": process.returncode,
              "elapsed_seconds": time.monotonic() - started, "deadline_seconds": spec["deadline_seconds"],
              "deadline_scope": "Worker setup, rendering, tokenizer and generation; OS cleanup overhead excluded.",
              **prior.call_accounting(target)}
    summary = target / "worker_summary.json"
    if summary.is_file():
        try:
            result["worker"] = remote.read(summary)
        except (OSError, ValueError) as exc:
            result["worker_summary_error"] = str(exc)
    remote.save(target / "supervisor_result.json", result)
    return result


def run_transport(*, spec, target, server_log, tick=None):
    """At most one generation, with exclusive artifact names and cleanup."""
    validate_spec(spec)
    target, server_log = Path(target), Path(server_log)
    validate_worker_location(spec, target)
    if not server_log.is_file():
        raise ValueError("Existing owned server log must be retained")
    target.mkdir()  # Reservation precedes all HTTP; never reuse a stage directory.
    remote.save(target / "worker_spec.json", spec)
    remote.save(target / "authoritative_body.json", spec["body"])
    (target / "authoritative_body.bin").write_bytes(json.dumps(spec["body"], ensure_ascii=False, allow_nan=False).encode())
    before = server_log.read_bytes()
    remote.save(target / "server_log_before.json", {"path": str(server_log.resolve()), "bytes": len(before),
        "sha256": hashlib.sha256(before).hexdigest()})
    result, clean, preservation_error = None, None, None
    try:
        result = supervise(target / "worker_spec.json", tick=tick)
    except BaseException as exc:
        result = {"status": "cancelled" if isinstance(exc, KeyboardInterrupt) else "supervisor_failed",
                  "error_type": type(exc).__name__, "error": str(exc), **prior.call_accounting(target)}
    finally:
        try:
            clean = bench.unload_and_confirm(spec["origin"], base.MODEL)
        except Exception as exc:
            clean = {"status": "idle_not_confirmed", "error_type": type(exc).__name__, "error": str(exc)}
        try:
            remote.save(target / "unload_and_residency.json", clean)
            after = server_log.read_bytes()
            (target / "server_log_after_snapshot.bin").write_bytes(after)
            remote.save(target / "server_log_delta.json", {"original_prefix_retained": after.startswith(before),
                "prior_bytes": len(before), "after_bytes": len(after), "sha256": hashlib.sha256(after).hexdigest()})
        except Exception as exc:
            preservation_error = {"type": type(exc).__name__, "message": str(exc)}
    status = result.get("worker", {}).get("status", "worker_summary_missing") if result["status"] == "worker_exited" else result["status"]
    if clean["status"] != "no_resident_models_observed":
        status = "cleanup_not_confirmed"
    response_path = target / "http_0001_generation/response.json"
    response = None
    if response_path.is_file():
        try:
            response = remote.read(response_path)
        except (OSError, ValueError) as exc:
            preservation_error = {"type": type(exc).__name__, "message": str(exc)}
    if preservation_error:
        status = "artifact_preservation_failure"
    ordinary = {"completed", "model_structure_failure", "output_limit_reached", "case_timeout"}
    # A hard deadline with no reliable completed record is a global stop, rather
    # than permission to stack more requests on a possibly still loading model.
    receipt = {"status": status, "response": response, "supervisor": result,
               "response_artifact": artifact_ref(response_path) if response is not None else None,
               "system_integrity_incident": status not in ordinary,
               "continuation_eligible": status == "completed" and result["worker"].get("continuation_eligible", False),
               "artifact_preservation_error": preservation_error,
               **prior.call_accounting(target)}
    remote.save(target / "transport_result.json", receipt)
    return receipt




def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path, required=True)
    args = parser.parse_args()
    return worker(args.worker)


if __name__ == "__main__":
    raise SystemExit(main())
