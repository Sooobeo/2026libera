"""Durable one-shot coordinator for the v4.9.4 development pilot.

Launch explicitly in a hidden independent process. No resume, replacement,
generation retry, semantic scorer or service shutdown is implemented here.
Events use unique exclusive files, never a mutable replacement status file.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
VERSION = "run_v494_recovery_1"
CASES = tuple(s + "__" + arm for s in ("fidelity_q2_2026", "ubs_june_2026")
              for arm in ("E", "L")) + ("common_market_only__C",)
DEVELOPMENT = (
    "v4.9.4 prompt development after inspection of v4.9.2 pilot outputs. "
    "The frozen v4.9.2 r2 evaluation is reused; historical outputs remain separate, "
    "never replaced or pooled as identical replications."
)


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def ref(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write_json(path, value):
    """Exclusive durable artifact; never replace an existing name."""
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def event(output_root, kind, **fields):
    filename = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "_" + uuid.uuid4().hex + ".json"
    target = Path(output_root) / "events" / filename
    write_json(target, {"event": kind, "at_utc": now(), "wrapper_version": VERSION, **fields})
    return ref(target)


def error_record(exc):
    return {"type": type(exc).__name__, "message": str(exc)}


def ensure_unchanged(reference):
    if ref(reference["path"]) != reference:
        raise ValueError("Artifact changed after coordinator start: " + reference["path"])


def validate_locations(run_dir, output_root):
    run_dir, output_root = Path(run_dir).resolve(), Path(output_root).resolve()
    if not run_dir.is_relative_to(ROOT) or not output_root.is_relative_to(ROOT):
        raise ValueError("Run and reports must be inside the workspace")
    if run_dir == output_root or run_dir in output_root.parents or output_root in run_dir.parents:
        raise ValueError("Run and reports must be separate directory trees")
    if run_dir.exists() or output_root.exists():
        raise FileExistsError("Run and report directories must both be new; no resume or retry")
    return run_dir, output_root


def recover_terminal_summary(run_dir, failure):
    """Account for existing artifacts after the synchronous runtime has unwound.

    Missing transport receipts are explicitly recovery observations with no
    completed-response binding. Existing raw output/receipts are never altered.
    No network/process operation is performed. Caller must own the newly created
    run and call this only after run_pilot has returned/raised, not while live.
    """
    run_dir = Path(run_dir).resolve()
    summary_path = run_dir / "pilot_summary.json"
    if summary_path.exists():
        return {"created": False, "summary_ref": ref(summary_path)}
    declaration = read(run_dir / "pilot_declaration.json")
    if (declaration.get("purpose") != "pilot_only"
            or declaration.get("case_order") != list(CASES)
            or declaration.get("max_generation_requests") != 10
            or declaration.get("main_model_calls") != 0
            or declaration.get("automatic_retries") != 0):
        raise ValueError("Recovery requires the exact declared no-retry pilot")
    cases, issues, transport_recovery_refs = [], [], []
    expected_dirs = {case + "__" + stage for case in CASES for stage in ("D0", "F0")}
    unexpected = [p.name for p in run_dir.iterdir()
                  if p.is_dir() and p.name.endswith(("__D0", "__F0")) and p.name not in expected_dirs]
    if unexpected:
        issues.append({"kind": "unexpected_stage_directories", "names": unexpected})
    for case in CASES:
        stages = []
        for stage in ("D0", "F0"):
            folder = run_dir / (case + "__" + stage)
            if not folder.exists():
                continue
            request_paths = sorted(folder.glob("http_*_generation/request.json"))
            durable_count = len(request_paths)
            transport_path = folder / "transport_result.json"
            if transport_path.exists():
                transport = read(transport_path)
                recorded_count = transport.get("generation_requests_attempted")
                if type(recorded_count) is not int or recorded_count < 0:
                    raise ValueError("Transport has invalid generation request accounting")
                if recorded_count != durable_count:
                    issues.append({"kind": "transport_request_envelope_count_mismatch", "case_id": case,
                                   "stage": stage, "transport_count": recorded_count, "envelope_count": durable_count})
                count = max(recorded_count, durable_count)
                status = transport.get("status", "transport_status_missing")
                eligible = transport.get("continuation_eligible") is True
            else:
                count, eligible = durable_count, False
                status = "coordinator_exception_recovered"
                recovered = {
                    "status": status, "generation_requests_attempted": count,
                    "continuation_eligible": False, "system_integrity_incident": True,
                    "response": None, "response_artifact": None,
                    "recovery_provenance": {"wrapper_version": VERSION, "at_utc": now(),
                        "cause": failure, "request_envelopes": [ref(p) for p in request_paths],
                        "scope": "Offline accounting after coordinator exception. Not an original transport receipt, not completion or response verification."},
                }
                write_json(transport_path, recovered)
                transport_recovery_refs.append(ref(transport_path))
            if count > 1:
                issues.append({"kind": "multiple_attempts_recorded", "case_id": case, "stage": stage, "count": count})
            stages.append({"stage": stage, "status": status, "generation_requests_attempted": count,
                           "continuation_eligible": eligible})
        if stages and stages[0]["stage"] != "D0":
            issues.append({"kind": "final_without_draft_stage", "case_id": case})
        cases.append({"case_id": case, "stages": stages,
                      "status": "stopped_for_integrity_or_cancellation" if stages else "not_attempted_after_stop"})
    summary = {
        "status": "stopped", "cases": cases,
        "generation_requests_attempted": sum(s["generation_requests_attempted"] for c in cases for s in c["stages"]),
        "main_model_calls": 0, "automatic_retries": 0, "post_final_calls": 0,
        "AI_preoutput_review_completed": declaration.get("AI_preoutput_review_completed") is True,
        "review_mode": declaration.get("review_mode"), "independent_human_review_completed": False,
        "frozen_for_pilot": declaration.get("frozen_for_pilot") is True, "main_frozen": False,
        "recovery_provenance": {"wrapper_version": VERSION, "at_utc": now(), "cause": failure,
            "declaration_ref": ref(run_dir / "pilot_declaration.json"), "accounting_issues": issues,
            "created_missing_transport_receipts": transport_recovery_refs,
            "accounting_scope": "Preserved request envelopes and existing transport receipts; mismatches are retained, never inferred successes.",
            "no_claim_of_complete_capture_after_OS_or_machine_failure": True},
        "interpretation": "Recovered terminal accounting after coordinator exception; semantic review pending. No output repaired or completion fabricated.",
    }
    write_json(summary_path, summary)
    return {"created": True, "summary_ref": ref(summary_path), "accounting_issues": issues}


def execute(args, *, runtime_module=None, analyzer=None, masked_builder=None):
    run_dir, output_root = validate_locations(args.run_dir, args.output_root)
    # Fail on absent start inputs before creating any run or issuing requests.
    inputs = {"runtime": ref(args.runtime), "review_gate": ref(args.review_gate), "server_log": ref(args.server_log)}
    scripts = {name: ref(ROOT / "research" / filename) for name, filename in {
        "runtime": "sector_v494_runtime.py", "wrapper": "run_v494_recovery.py",
        "analysis": "analyze_v492_pilot.py", "masked": "build_v494_masked_review.py"}.items()}
    output_root.mkdir(parents=True)
    (output_root / "events").mkdir()
    event(output_root, "coordinator_started", run_directory=str(run_dir), pid=os.getpid(),
          origin=args.origin, inputs=inputs, scripts=scripts, protocol_version="4.9.4",
          development_context=DEVELOPMENT, semantic_review="pending_actual_AI_reading")
    errors, steps, owned_run = [], [], False
    execution_failure = None
    try:
        if runtime_module is None:
            import sector_v494_runtime as runtime_module
        ensure_unchanged(scripts["runtime"])
        runtime_module.prepare_pilot(args.runtime, run_dir, args.origin, args.server_log, args.review_gate)
        owned_run = True
        event(output_root, "pilot_prepared", declaration_ref=ref(run_dir / "pilot_declaration.json"))
        runtime_module.run_pilot(run_dir)
        event(output_root, "attempt_sequence_returned", summary_ref=ref(run_dir / "pilot_summary.json"))
    except BaseException as exc:
        execution_failure = error_record(exc)
        errors.append({"step": "execution", **execution_failure})
        event(output_root, "execution_exception", error=execution_failure,
              semantic_review="pending_actual_AI_reading", no_retry=True)
        # If preparation itself failed, do not write into a run whose ownership
        # was never established, even if an incomplete directory is present.
    if owned_run and not (run_dir / "pilot_summary.json").exists():
        try:
            recovered = recover_terminal_summary(run_dir, execution_failure or {"type": "MissingTerminalSummary", "message": "runtime returned without summary"})
            steps.append({"step": "terminal_recovery", "status": "completed", **recovered})
            event(output_root, "terminal_summary_recovered", **recovered)
        except BaseException as exc:
            error = {"step": "terminal_recovery", **error_record(exc)}
            errors.append(error)
            event(output_root, "terminal_recovery_failed", error=error)
    summary_path = run_dir / "pilot_summary.json"
    if owned_run and summary_path.is_file():
        # Both processors are offline; failure of one does not suppress the other.
        for kind in ("analysis", "masked"):
            try:
                ensure_unchanged(scripts[kind])
                ensure_unchanged(inputs["review_gate"])
                ensure_unchanged(inputs["runtime"])
                if kind == "analysis":
                    if analyzer is None:
                        from analyze_v492_pilot import analyze as analyzer
                    result = analyzer(run_dir)
                    path = output_root / "arithmetic_analysis.json"
                    write_json(path, result)
                    outcome = {"artifact": ref(path), "final_coverage": result.get("final_coverage")}
                else:
                    if masked_builder is None:
                        from build_v494_masked_review import build as masked_builder
                    outcome = masked_builder(run_dir, output_root / "judge_bundle", output_root / "private_mapping")
                step = {"step": kind, "status": "completed_offline_only", "result": outcome}
                steps.append(step)
                event(output_root, "postprocessing_completed", **step, semantic_review="pending_actual_AI_reading")
            except BaseException as exc:
                error = {"step": kind, **error_record(exc)}
                errors.append(error)
                steps.append({"step": kind, "status": "failed_no_retry", "error": error})
                event(output_root, "postprocessing_failed", error=error, no_retry=True)
    cleanup = {
        "status": "pending_verified_idle_and_ownership_cleanup", "service_stop_attempted": False,
        "reason": "The wrapper does not own service shutdown. Runtime records per-stage unload; a separate helper must verify current idle state and exact service ownership before stopping it.",
    }
    summary = None
    if owned_run and summary_path.is_file():
        try:
            summary = read(summary_path)
        except (OSError, ValueError) as exc:
            errors.append({"step": "terminal_summary_read", **error_record(exc)})
    status = ("completed_with_errors_attention_required" if errors else
              "stopped_semantic_review_pending" if summary and summary.get("status") == "stopped" else
              "completed_semantic_review_pending")
    terminal = {
        "wrapper_version": VERSION, "protocol_version": "4.9.4", "at_utc": now(), "status": status,
        "run_directory": str(run_dir), "output_root": str(output_root), "development_context": DEVELOPMENT,
        "summary_ref": ref(summary_path) if owned_run and summary_path.is_file() else None,
        "generation_requests_attempted": summary.get("generation_requests_attempted") if summary else None,
        "steps": steps, "errors": errors, "service_cleanup": cleanup,
        "semantic_review": {"status": "pending_actual_AI_reading", "performed_by_wrapper": False,
                            "independent_human_review_completed": False, "no_composite_score": True},
        "stagewise_checks": {
            "errors": {"status": "attention_required" if errors else "offline_checks_completed", "details": errors,
                       "output_errors_are_measured_results": True},
            "integrity": {"status": "inspect_receipts_if_recovered" if execution_failure else "runtime_and_offline_receipts_recorded",
                          "no_retries": True, "no_response_repair": True, "no_mutable_status_replacement": True},
            "topic": {"status": "scope_preserved_semantic_review_pending",
                      "question": "Institution evidence to stated interpretation, decision reasons and observable allocation; E/L timing and source-free C.",
                      "arithmetic_success_is_not_semantic_success_or_main_gate": True},
        },
        "main_execution_started": False,
        "main_readiness": "Not inferred from arithmetic success or failure; separate review of auditable execution and unresolved research-question coverage is required.",
    }
    write_json(output_root / "terminal_receipt.json", terminal)
    event(output_root, "coordinator_terminal", terminal_ref=ref(output_root / "terminal_receipt.json"))
    return terminal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("runtime", "run-dir", "server-log", "review-gate", "output-root"):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--origin", required=True)
    args = parser.parse_args()
    result = execute(args)
    print(json.dumps({"status": result["status"], "output_root": result["output_root"],
                      "semantic_review": result["semantic_review"]["status"]}, ensure_ascii=False))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
