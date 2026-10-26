"""Single final control response after an explicit user resumption; no retries."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid
import run_sector_remaining as previous
from sector_remaining_awake import CoordinatorAwake as PriorAwake
from last_final_20261026 import runtime_adapter as runtime
gate = runtime
ROOT = runtime.ROOT
VERSION = "sector_last_final_coordinator_1"
CASES, STAGE_ORDER, STAGES_BY_CASE = gate.CASES, gate.STAGE_ORDER, gate.STAGES_BY_CASE
REVIEW_ACK_TIMEOUT_SECONDS = 1800
MAX_OPERATIONAL_SECONDS = 4500 + 1800 + 1800

class CoordinatorAwake(PriorAwake):
    def __init__(self, emit, *, api=None):
        super().__init__(emit, api=api)
        self.expires = datetime.now(timezone.utc) + timedelta(seconds=MAX_OPERATIONAL_SECONDS)

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
    expected = set(STAGE_ORDER)
    extra = sorted(p.name for p in run.iterdir() if p.is_dir() and p.name.endswith(("__D0", "__F0")) and p.name not in expected)
    if extra:
        issues.append({"unexpected_stage_directories": extra})
    for case_id in CASES:
        row = {"case_id": case_id, "stages": [], "status": "not_attempted_after_stop"}
        for stage in STAGES_BY_CASE[case_id]:
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
        if [(s["stage"], s["status"], s["generation_requests_attempted"]) for s in row["stages"]] == [(stage, "completed", 1) for stage in STAGES_BY_CASE[case_id]]:
            row["status"] = "remaining_stages_completed_semantic_review_pending"
            row["global_stop_does_not_erase_completed_transports"] = True
        cases.append(row)
    return make_summary(cases, stopped=True, accounting_issues=issues, recovery_cause=failure)




def validate_external_review_ack(ack, *, spec, folder, math_path):
    if spec.get("case_id") != CASES[0] or spec.get("stage") != "F0":
        raise ValueError("Only the new control F0 may be acknowledged")
    if ack.get("schema_version") != "sector_last_final_stage_external_review_ack_1":
        raise ValueError("New final-only acknowledgement schema required")
    compatible = dict(ack, schema_version="sector_remaining_stage_external_review_ack_1")
    return previous.validate_external_review_ack(compatible, spec=spec, folder=folder, math_path=math_path)


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


def make_summary(cases, *, stopped, **extra):
    stages = [s for c in cases for s in c["stages"]]
    if (len(cases) != 1 or cases[0]["case_id"] != CASES[0] or len(stages) > 1
            or any(s.get("stage") != "F0" or type(s.get("generation_requests_attempted")) is not int
                   or s["generation_requests_attempted"] not in (0, 1) for s in stages)):
        raise ValueError("Exactly one declared final slot with zero or one attempt required")
    attempted = sum(s["generation_requests_attempted"] for s in stages)
    return {"version": VERSION, "purpose": gate.PURPOSE, "at_utc": now(),
        "status": "stopped" if stopped else "attempt_sequence_finished", "case_order": list(CASES),
        "stage_order": list(STAGE_ORDER), "cases": cases, "generation_requests_attempted": attempted,
        "max_generation_requests": 1, "historical_generation_requests": 10,
        "campaign_generation_requests_attempted": 10 + attempted, "campaign_max_generation_requests": 11,
        "automatic_retries": 0, "post_final_calls": 0, "main_model_calls": 0,
        "segment_planned_final_cells": 1, "original_planned_final_cells": 5,
        "historical_first_attempt_results_unchanged": True, "analysis_role": "primary_exploratory",
        "excluded_new_main_execution": True, "old_missing_ACK_retained": True, **extra}


def sequence(declaration, run, reports, ownership, *, transport=None, reviewer=None, finalizer=None, review_waiter=None):
    transport = transport or runtime.run_transport
    review_waiter = review_waiter or wait_for_external_review
    if reviewer is None:
        from review_sector_v494_stage import review_and_record as reviewer
    if finalizer is None:
        from finalize_sector_allocation import finalize_stage as finalizer
    row = {"case_id": CASES[0], "stages": [], "status": "not_attempted_after_stop",
           "external_completed_D0_carried_by_reference": True}
    cancel = run / "CANCEL"
    (reports / "allocation_math").mkdir()
    if cancel.exists():
        return make_summary([row], stopped=True)
    ownership.pulse(force=True, stage_start=True)
    gate.validate_gate(declaration["review_gate"]["path"], declaration["review_gate"]["sha256"],
                       runtime=declaration["runtime"], run_directory=run)
    carried = gate.validated_external_draft(declaration)
    loaded, _ = runtime.load_bundle()
    spec = {"origin": declaration["origin"], "runtime": declaration["runtime"],
        "case_id": CASES[0], "stage": "F0", "raw_draft": carried["raw_draft"],
        "draft_artifacts": carried["draft_artifacts"], "run_directory": str(run),
        "review_gate": declaration["review_gate"],
        "body": runtime.request_body(declaration["runtime"], carried["final"]["messages"], loaded["response_schema"]),
        "cancel_path": str(cancel), "deadline_seconds": declaration["runtime"]["deadline_seconds"]}
    folder = run / STAGE_ORDER[0]
    event(reports, "stage_started", case_id=CASES[0], stage="F0", overall_cell_attempt=1,
          overall_stage_attempt=1, segment_stage_attempt=1, historical_generation_requests=10,
          body_value_sha256=runtime.value_sha(spec["body"]))
    result = transport(spec=spec, target=folder, server_log=declaration["server_log"], tick=ownership.pulse)
    review = reviewer(spec, folder, result)
    math = finalizer(folder)
    math_path = reports / "allocation_math" / (folder.name + ".json")
    write_json(math_path, math)
    event(reports, "stage_review_completed", case_id=CASES[0], stage="F0",
          transport_ref=ref(folder / "transport_result.json"), review_ref=ref(folder / "stage_review.json"),
          math_sidecar_ref=ref(math_path), instrument_integrity_pass=review["instrument_integrity_pass"],
          semantic_support="pending_separate_AI_reading", raw_model_content_modified=False)
    ack = review_waiter(spec=spec, folder=folder, math_path=math_path, ownership=ownership, cancel=cancel)
    event(reports, "stage_external_review_acknowledged", case_id=CASES[0], stage="F0", **ack)
    row["stages"].append({"stage": "F0", "status": result["status"],
        "generation_requests_attempted": result["generation_requests_attempted"],
        "continuation_eligible": result["continuation_eligible"]})
    halt = result["system_integrity_incident"] or not review["instrument_integrity_pass"] or result["status"] == "cancelled"
    row["status"] = ("stopped_for_integrity_or_cancellation" if halt else
                     "last_final_completed_and_reviewed" if result["continuation_eligible"] else "incomplete_first_final_attempt_retained")
    write_json(run / (CASES[0] + "__case_summary.json"), row)
    return make_summary([row], stopped=halt or cancel.exists())




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
    if (args.origin != service["origin"] or not Path(args.server_log).is_file()
            or Path(args.server_log).resolve().parent != Path(selected["backend_evidence"][0]["path"]).resolve().parent
            or Path(args.server_log).name not in ("server.stdout.log", "server.stderr.log")):
        raise ValueError("Owned origin or preserved server log missing")
    # Reserve both fresh trees before issuing any HTTP or power request.
    reports.mkdir(parents=True)
    (reports / "events").mkdir()
    run.mkdir(parents=True)
    gate_object = read(args.review_gate)
    declaration = {key: gate_object[key] for key in (*gate.BOUND, *gate.EXTERNAL_GROUPS, "stage_order", "power_policy", "freeze_ref", "run_directory", "output_root",
        "purpose", "case_order", "max_generation_requests", "historical_generation_requests",
        "campaign_max_generation_requests", "automatic_retries", "post_final_calls", "main_allowed", "old_outputs_observed", "explicit_retry_slots", "historical_explicit_retry_slots",
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
    terminal = {"version": VERSION, "at_utc": now(), "purpose": "pilot_last_final",
        "status": "stopped_semantic_review_pending" if errors or summary is None or summary["status"] == "stopped" else "completed_semantic_review_pending",
        "run_directory": str(run), "output_root": str(reports), "declaration_ref": ref(run / "campaign_declaration.json"),
        "summary_ref": ref(run / "campaign_summary.json") if summary is not None else None,
        "generation_requests_attempted": summary["generation_requests_attempted"] if summary is not None else None,
        "errors": errors, "awake_release": release, "automatic_retries": 0, "main_model_calls": 0,
        "semantic_review": "see_exact_stage_acknowledgement_or_recorded_failure", "historical_first_attempt_results_unchanged": True,
        "service_cleanup": "pending_root_verified_idle_owned_shutdown", "model_content_modified": False,
        "review_axes": {"errors": "Transport, instrument and raw-allocation diagnostics retained after every stage.",
            "consistency": "New final-only namespace, exact external control D0, unchanged frozen controls and ten prior attempts.",
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
