"""Final three pilot conditions in a new, prospectively bound segment; never resume a prior run.

Root launches this coordinator in its owned foreground/session. The coordinator
main thread owns temporary SYSTEM|DISPLAY wakefulness until finally cleanup.
No detached helper, main execution, semantic repair or automatic retry exists.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

import sector_completion_gate as gate
import sector_completion_runtime as runtime
from sector_completion_awake import CoordinatorAwake

ROOT = Path(__file__).resolve().parents[1]
VERSION = "sector_completion_coordinator_1"
CASES = gate.CASES


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def ref(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write_json(path, value):
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def event(folder, kind, **fields):
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "_" + uuid.uuid4().hex + ".json"
    path = folder / "events" / name
    write_json(path, {"event": kind, "at_utc": now(), "version": VERSION, **fields})
    return ref(path)


def locations(run_dir, output_root):
    run, reports = Path(run_dir).resolve(), Path(output_root).resolve()
    if (not run.is_relative_to(ROOT) or not reports.is_relative_to(ROOT)
            or run == reports or run in reports.parents or reports in run.parents):
        raise ValueError("Distinct workspace-contained run/report trees required")
    if run.exists() or reports.exists():
        raise FileExistsError("Both directories must be new; no resume, retry or replacement")
    return run, reports


def recover_summary(run, failure):
    """Offline accounting after the owned synchronous worker has unwound."""
    cases, issues = [], []
    expected = {case + "__" + stage for case in CASES for stage in ("D0", "F0")}
    extra = sorted(p.name for p in run.iterdir() if p.is_dir() and p.name.endswith(("__D0", "__F0")) and p.name not in expected)
    if extra:
        issues.append({"unexpected_stage_directories": extra})
    for case_id in CASES:
        row = {"case_id": case_id, "stages": [], "status": "not_attempted_after_stop"}
        for stage in ("D0", "F0"):
            folder = run / (case_id + "__" + stage)
            if not folder.exists():
                continue
            count = runtime.prior.call_accounting(folder)
            path = folder / "transport_result.json"
            if path.exists():
                transport = read(path)
                attempted = transport.get("generation_requests_attempted")
                if type(attempted) is not int or attempted not in (0, 1):
                    raise ValueError("Invalid preserved transport attempt count")
                if attempted != count["generation_requests_attempted"]:
                    issues.append({"case_id": case_id, "stage": stage, "transport_envelope_count_mismatch": True})
                attempts = max(attempted, count["generation_requests_attempted"])
            else:
                attempts = count["generation_requests_attempted"]
                transport = {"status": "coordinator_exception_recovered", "response": None,
                    "response_artifact": None, "system_integrity_incident": True,
                    "continuation_eligible": False, "artifact_preservation_error": failure,
                    **count, "recovery_provenance": {"at_utc": now(), "cause": failure,
                        "not_an_original_transport_receipt": True, "completed_response_claim": False}}
                write_json(path, transport)
            row["stages"].append({"stage": stage, "status": transport["status"],
                "generation_requests_attempted": attempts, "continuation_eligible": transport.get("continuation_eligible") is True})
            row["status"] = "stopped_for_integrity_or_cancellation"
        if [(s["stage"], s["status"], s["generation_requests_attempted"]) for s in row["stages"]] == [
                ("D0", "completed", 1), ("F0", "completed", 1)]:
            row["status"] = "two_stages_completed_semantic_review_pending"
            row["global_stop_does_not_erase_completed_transports"] = True
        cases.append(row)
    return make_summary(cases, stopped=True, accounting_issues=issues, recovery_cause=failure)


def make_summary(cases, *, stopped, **extra):
    attempted = sum(s["generation_requests_attempted"] for c in cases for s in c["stages"])
    if attempted > 6:
        raise RuntimeError("Continuation request budget exceeded")
    return {"version": VERSION, "purpose": "pilot_completion", "at_utc": now(),
            "status": "stopped" if stopped else "attempt_sequence_finished", "case_order": list(CASES),
            "cases": cases, "generation_requests_attempted": attempted,
            "max_generation_requests": 6, "historical_generation_requests": 5,
            "campaign_generation_requests_attempted": 5 + attempted, "campaign_max_generation_requests": 11,
            "automatic_retries": 0, "post_final_calls": 0, "main_model_calls": 0,
            "segment_planned_final_cells": 3, "original_planned_final_cells": 5,
            "historical_first_attempt_results_unchanged": True, "analysis_role": "primary_exploratory",
            "excluded_new_main_execution": True, "interpretation": "Completion segment accounting only; original and prior continuation attempts remain separate, and the five original conditions support a primary exploratory analysis.", **extra}


REVIEW_ACK_TIMEOUT_SECONDS = 1800


def bound_file(reference, expected=None):
    if (not isinstance(reference, dict) or set(reference) != {"path", "sha256"}
            or not isinstance(reference["path"], str) or not isinstance(reference["sha256"], str)
            or len(reference["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in reference["sha256"])):
        raise ValueError("Exact external review file reference required")
    path = Path(reference["path"]).resolve()
    if expected is not None and path != Path(expected).resolve():
        raise ValueError("External review reference identifies a different stage artifact")
    if ref(path)["sha256"] != reference["sha256"]:
        raise ValueError("External review reference bytes changed")
    return path


def validate_external_review_ack(ack, *, spec, folder, math_path):
    if (ack.get("schema_version") != "sector_completion_stage_external_review_ack_1"
            or ack.get("status") != "completed" or ack.get("case_id") != spec["case_id"]
            or ack.get("stage") != spec["stage"] or type(ack.get("model_calls")) is not int
            or ack["model_calls"] != 0 or ack.get("raw_model_content_modified") is not False):
        raise ValueError("Completed same-stage external review acknowledgement required")
    expected = {"worker_spec_ref": folder / "worker_spec.json", "transport_ref": folder / "transport_result.json",
                "stage_review_ref": folder / "stage_review.json", "allocation_math_ref": math_path}
    for key, path in expected.items():
        bound_file(ack.get(key), path)
    if runtime.base.canonical(read(expected["worker_spec_ref"])) != runtime.base.canonical(spec):
        raise ValueError("Preserved worker specification differs from the reviewed coordinator stage")
    semantic_path = bound_file(ack.get("semantic_review_ref"))
    semantic = read(semantic_path)
    if (semantic.get("review_status") != "completed" or semantic.get("case_id") != spec["case_id"]
            or semantic.get("stage") != spec["stage"]):
        raise ValueError("Semantic audit must be complete for this exact stage; negative findings remain allowed")
    bound_file(semantic.get("transport_ref"), expected["transport_ref"])
    if semantic["transport_ref"]["sha256"] != ack["transport_ref"]["sha256"]:
        raise ValueError("Semantic audit and acknowledgement bind different transport bytes")
    for axis in ("errors", "consistency", "paper_topic"):
        item = ack.get("review_axes", {}).get(axis, {})
        if item.get("reviewed") is not True or not isinstance(item.get("reason"), str) or not item["reason"].strip():
            raise ValueError("Every external review axis must be completed with a reason")
    return {"status": "external_review_completed", "semantic_review_ref": ack["semantic_review_ref"],
            "outcome_success_required": False, "model_calls": 0}


def wait_for_external_review(*, spec, folder, math_path, ownership, cancel,
                             timeout_seconds=REVIEW_ACK_TIMEOUT_SECONDS, monotonic=time.monotonic, sleep=time.sleep):
    if type(timeout_seconds) is not int or not 0 <= timeout_seconds <= REVIEW_ACK_TIMEOUT_SECONDS:
        raise ValueError("Review wait must stay within its fixed1800-second ceiling")
    deadline = monotonic() + timeout_seconds
    acknowledgement = folder / "external_review_ack.json"
    while True:
        if cancel.exists():
            raise runtime.remote.Cancelled("Cancellation requested during external stage review")
        ownership.pulse()
        if acknowledgement.exists():
            # Publish only after complete serialization: exclusive atomic link/rename
            # avoids exposing a half-written JSON. Existing acknowledgements cannot be repaired in place.
            value = read(acknowledgement)
            result = validate_external_review_ack(value, spec=spec, folder=folder, math_path=math_path)
            result["acknowledgement_ref"] = ref(acknowledgement)
            return result
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("Stage external review acknowledgement not completed within fixed ceiling; no next generation")
        sleep(min(0.25, remaining))


def sequence(declaration, run, reports, ownership, *, transport=None, reviewer=None, finalizer=None, review_waiter=None):
    review_waiter = review_waiter or wait_for_external_review
    transport = transport or runtime.run_transport
    if reviewer is None:
        from review_sector_v494_stage import review_and_record as reviewer
    if finalizer is None:
        from finalize_sector_allocation import finalize_stage as finalizer
    loaded, all_cases = runtime.load_bundle()
    cases = [case for case in all_cases if case["case_id"] in CASES]
    if [case["case_id"] for case in cases] != list(CASES):
        raise ValueError("Exact three-cell completion inventory required")
    summaries, halt = [], False
    cancel = run / "CANCEL"
    (reports / "allocation_math").mkdir()
    for case in cases:
        row = {"case_id": case["case_id"], "stages": [], "status": "not_attempted_after_stop"}
        if halt or cancel.exists():
            summaries.append(row)
            continue
        messages, raw_draft, draft_refs = case["messages"], None, None
        for stage in ("D0", "F0"):
            if cancel.exists():
                halt = True
                row["status"] = "cancelled_before_stage"
                break
            ownership.pulse(force=True, require_ac=True)
            gate.validate_gate(declaration["review_gate"]["path"], declaration["review_gate"]["sha256"],
                               runtime=declaration["runtime"], run_directory=run)
            spec = {"origin": declaration["origin"], "runtime": declaration["runtime"],
                "case_id": case["case_id"], "stage": stage, "raw_draft": raw_draft,
                "run_directory": str(run), "review_gate": declaration["review_gate"],
                "body": runtime.request_body(declaration["runtime"], messages, loaded["response_schema"]),
                "cancel_path": str(cancel), "deadline_seconds": declaration["runtime"]["deadline_seconds"]}
            if stage == "F0":
                spec["draft_artifacts"] = draft_refs
            folder = run / (case["case_id"] + "__" + stage)
            event(reports, "stage_started", case_id=case["case_id"], stage=stage,
                  overall_cell_attempt=1,
                  overall_stage_attempt=1,
                  segment_stage_attempt=1, body_value_sha256=runtime.value_sha(spec["body"]))
            result = transport(spec=spec, target=folder, server_log=declaration["server_log"], tick=ownership.pulse)
            review = reviewer(spec, folder, result)
            math = finalizer(folder)
            math_path = reports / "allocation_math" / (folder.name + ".json")
            write_json(math_path, math)
            event(reports, "stage_review_completed", case_id=case["case_id"], stage=stage,
                  transport_ref=ref(folder / "transport_result.json"), review_ref=ref(folder / "stage_review.json"),
                  math_sidecar_ref=ref(math_path), instrument_integrity_pass=review["instrument_integrity_pass"],
                  semantic_support="pending_separate_AI_reading", raw_model_content_modified=False)
            ack = review_waiter(spec=spec, folder=folder, math_path=math_path, ownership=ownership, cancel=cancel)
            event(reports, "stage_external_review_acknowledged", case_id=case["case_id"], stage=stage, **ack)
            row["stages"].append({"stage": stage, "status": result["status"],
                "generation_requests_attempted": result["generation_requests_attempted"],
                "continuation_eligible": result["continuation_eligible"]})
            if result["system_integrity_incident"] or not review["instrument_integrity_pass"] or result["status"] == "cancelled":
                halt = True
                row["status"] = "stopped_for_integrity_or_cancellation"
                break
            if not result["continuation_eligible"]:
                row["status"] = "incomplete_first_segment_attempt_retained"
                break
            if stage == "D0":
                raw_draft = result["response"]["message"]["content"]
                draft_refs = runtime.prior_draft_refs(run, case["case_id"])
                if result.get("response_artifact") != draft_refs["response"]:
                    raise ValueError("Actual new D0 response binding differs")
                final = runtime.contract.build_final_messages(draft_messages=case["messages"], raw_draft=raw_draft,
                    assigned_packet=case["assigned_packet"], prompt_contract=loaded["prompt_contract"],
                    response_schema=loaded["response_schema"])
                write_json(run / (case["case_id"] + "__final_construction.json"), final)
                if not final["ready"]:
                    raise ValueError("New D0 transport and F0 contract disagree")
                messages = final["messages"]
            else:
                row["status"] = "two_stages_completed_semantic_review_pending"
        summaries.append(row)
        write_json(run / (case["case_id"] + "__case_summary.json"), row)
    return make_summary(summaries, stopped=halt or cancel.exists())


def execute(args, *, awake_factory=CoordinatorAwake, transport=None, reviewer=None, finalizer=None, review_waiter=None):
    run, reports = locations(args.run_dir, args.output_root)
    selected = read(args.runtime)
    validated = gate.validate_gate(args.review_gate, runtime=selected)
    if run != Path(validated["run_directory"]) or reports != Path(validated["output_root"]):
        raise ValueError("CLI paths differ from new freeze")
    if ref(args.runtime)["sha256"] != validated["runtime_ref"]["sha256"]:
        raise ValueError("CLI runtime differs from frozen runtime")
    service = runtime.prepare.read(
        selected["backend_evidence"][0]["path"], selected["backend_evidence"][0]["sha256"])[0]
    if args.origin != service["origin"] or not Path(args.server_log).is_file():
        raise ValueError("Owned origin or preserved server log missing")
    # Reserve both fresh trees before issuing any HTTP or power request.
    reports.mkdir(parents=True)
    (reports / "events").mkdir()
    run.mkdir(parents=True)
    gate_object = read(args.review_gate)
    declaration = {key: gate_object[key] for key in (*gate.BOUND, "freeze_ref", "run_directory", "output_root",
        "purpose", "case_order", "max_generation_requests", "historical_generation_requests",
        "campaign_max_generation_requests", "automatic_retries", "main_allowed", "old_outputs_observed", "explicit_retry_slots", "historical_explicit_retry_slots",
        "analysis_role", "excluded_new_main_execution", "main_model_calls")}
    declaration.update(version=VERSION, created_at_utc=now(), runtime=selected, review_gate=validated["gate_ref"],
        origin=args.origin, server_log=str(Path(args.server_log).resolve()), main_model_calls=0,
        historical_first_attempt_results_unchanged=True, coordinator_pid=os.getpid(),
        runtime_identity="Original scientific controls; new owned isolated service receipt only.")
    write_json(run / "campaign_declaration.json", declaration)
    write_json(run / "execution_started.json", {"at_utc": now(), "coordinator_pid": os.getpid(), "no_resume_no_automatic_retry": True})
    emit = lambda kind, **fields: event(reports, kind, **fields)
    emit("coordinator_started", declaration_ref=ref(run / "campaign_declaration.json"), coordinator_pid=os.getpid())
    ownership, summary, errors, release = None, None, [], None
    try:
        ownership = awake_factory(emit)
        ownership.acquire()
        summary = sequence(declaration, run, reports, ownership, transport=transport, reviewer=reviewer, finalizer=finalizer, review_waiter=review_waiter)
    except BaseException as exc:
        failure = {"type": type(exc).__name__, "message": str(exc)}
        errors.append(failure)
        emit("coordinator_exception", error=failure, no_automatic_retry=True)
        try:
            summary = recover_summary(run, failure)
        except BaseException as recovery_exc:
            errors.append({"type": type(recovery_exc).__name__, "message": str(recovery_exc), "phase": "terminal_accounting"})
    finally:
        if ownership is not None:
            try:
                release = ownership.release()
            except BaseException as exc:
                release = {"status": "release_not_confirmed", "error_type": type(exc).__name__, "error": str(exc)}
            write_json(reports / "coordinator_awake_release.json", release)
            emit("coordinator_awake_release", receipt_ref=ref(reports / "coordinator_awake_release.json"))
            if release.get("status") not in ("released", "no_request_acquired"):
                errors.append({"type": "AwakeReleaseNotConfirmed", "message": str(release)})
    if summary is not None:
        if errors:
            summary["status"] = "stopped"
        write_json(run / "campaign_summary.json", summary)
    terminal = {"version": VERSION, "at_utc": now(), "purpose": "pilot_completion",
        "status": "stopped_semantic_review_pending" if errors or summary is None or summary["status"] == "stopped" else "completed_semantic_review_pending",
        "run_directory": str(run), "output_root": str(reports), "declaration_ref": ref(run / "campaign_declaration.json"),
        "summary_ref": ref(run / "campaign_summary.json") if summary is not None else None,
        "generation_requests_attempted": summary["generation_requests_attempted"] if summary is not None else None,
        "errors": errors, "awake_release": release, "automatic_retries": 0, "main_model_calls": 0,
        "semantic_review": "pending_separate_AI_reading", "historical_first_attempt_results_unchanged": True,
        "service_cleanup": "pending_root_verified_idle_owned_shutdown", "model_content_modified": False,
        "review_axes": {"errors": "Transport, instrument and raw-allocation diagnostics retained after every stage.",
            "consistency": "New namespace, bound same-run D0/F0, exact frozen controls and explicit historical attempt counts.",
            "paper_topic": "E/L evidence timing and source-free C remain unchanged; numeric normalization is a sidecar and cannot establish semantic success."}}
    write_json(reports / "terminal_receipt.json", terminal)
    emit("coordinator_terminal", terminal_ref=ref(reports / "terminal_receipt.json"))
    return terminal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("runtime", "run-dir", "server-log", "review-gate", "output-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--execute", action="store_true", help="Explicit root-owned launch only; no preparation auto-launch")
    args = parser.parse_args()
    if not args.execute:
        parser.error("Explicit --execute required after prospective freeze and root launch checks")
    result = execute(args)
    print(json.dumps({"status": result["status"], "output_root": result["output_root"]}, ensure_ascii=False), flush=True)
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
