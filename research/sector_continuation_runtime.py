"""New worker namespace for an explicitly frozen v4.9.4 continuation.

The exact worker/render/token/generation/cleanup logic is copied from the frozen
v494 implementation; the gate, four-cell scope and coordinator pulse hook differ.
No historical file is modified and no automatic retry entrypoint exists.
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
import sector_v494_runtime as original
from sector_continuation_gate import CASES, validate_gate

base, prepare, prior, awake, contract = original.base, original.prepare, original.prior, original.awake, original.contract
remote, bench = original.remote, original.bench
ROOT, STAGE_DEADLINE_SECONDS = original.ROOT, original.STAGE_DEADLINE_SECONDS
CapacityFailure = original.CapacityFailure
validate_runtime, load_bundle, request_body = original.validate_runtime, original.load_bundle, original.request_body

DRAFT_ARTIFACTS = {
    "response": "http_0001_generation/response.json",
    "worker_spec": "worker_spec.json", "worker_summary": "worker_summary.json",
    "supervisor_result": "supervisor_result.json", "transport_result": "transport_result.json",
}


def artifact_ref(path):
    path = prepare.workspace_path(path)
    return {"path": str(path), "sha256": remote.sha(path)}


def expected_stage_directory(spec):
    root = prepare.workspace_path(spec["run_directory"])
    return root / (spec["case_id"] + "__" + spec["stage"])


def validate_worker_location(spec, directory):
    if Path(directory).resolve() != expected_stage_directory(spec):
        raise ValueError("Worker artifact directory must belong to this run, case and stage")


def prior_draft_refs(run_directory, case_id):
    root = prepare.workspace_path(run_directory) / (case_id + "__D0")
    return {role: artifact_ref(root / filename) for role, filename in DRAFT_ARTIFACTS.items()}


def validate_prior_draft(spec):
    """Bind actual D0 bytes/completion, not merely a self-consistent caller draft.

    This detects accidental substitution/provenance loss. It does not certify
    authenticity against an operator who deliberately fabricates all files.
    """
    refs = spec.get("draft_artifacts")
    if not isinstance(refs, dict) or set(refs) != set(DRAFT_ARTIFACTS):
        raise ValueError("Final requires exact prior D0 artifact references")
    root = prepare.workspace_path(spec["run_directory"]) / (spec["case_id"] + "__D0")
    records = {}
    for role, filename in DRAFT_ARTIFACTS.items():
        ref = refs[role]
        if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
            raise ValueError("Prior D0 artifact requires path and SHA256")
        digest = ref["sha256"]
        if (not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)
                or prepare.workspace_path(ref["path"]) != (root / filename).resolve()):
            raise ValueError("Prior draft must be the same run/case D0 artifact with an exact hash")
        records[role], _ = prepare.read(ref["path"], digest)
    original_spec = records["worker_spec"]
    if (original_spec.get("stage") != "D0" or original_spec.get("case_id") != spec["case_id"]
            or prepare.workspace_path(original_spec.get("run_directory", "")) != prepare.workspace_path(spec["run_directory"])
            or original_spec.get("origin") != spec["origin"]
            or base.canonical(original_spec.get("runtime")) != base.canonical(spec["runtime"])
            or original_spec.get("review_gate") != spec["review_gate"]):
        raise ValueError("Prior D0 execution identity or declared conditions differ")
    validate_spec(original_spec)
    response = records["response"]
    if (response.get("model") != base.MODEL or response.get("done") is not True
            or response.get("done_reason") != "stop" or response.get("message", {}).get("content") != spec["raw_draft"]
            or response.get("message", {}).get("thinking") or response.get("message", {}).get("tool_calls")):
        raise ValueError("Raw draft must equal the completed pinned D0 response content exactly")
    worker, supervisor, transport = [records[k] for k in ("worker_summary", "supervisor_result", "transport_result")]
    if (worker.get("status") != "completed" or worker.get("continuation_eligible") is not True
            or worker.get("system_integrity_incident") is not False
            or supervisor.get("status") != "worker_exited" or type(supervisor.get("worker_exit_code")) is not int
            or supervisor.get("worker_exit_code") != 0
            or base.canonical(supervisor.get("worker")) != base.canonical(worker)
            or transport.get("status") != "completed" or transport.get("continuation_eligible") is not True
            or transport.get("system_integrity_incident") is not False
            or base.canonical(transport.get("response")) != base.canonical(response)
            or base.canonical(transport.get("supervisor")) != base.canonical(supervisor)
            or transport.get("response_artifact") != refs["response"]):
        raise ValueError("Prior D0 worker, supervisor and cleanup/continuation records must agree")
    for record in (worker, supervisor, transport):
        if type(record.get("generation_requests_attempted")) is not int or record["generation_requests_attempted"] != 1:
            raise ValueError("Prior D0 must record exactly one generation attempt")
    return {"status": "same_run_case_completed_D0_artifacts_bound", "artifact_refs": refs,
            "raw_draft_utf8_sha256": hashlib.sha256(spec["raw_draft"].encode("utf-8")).hexdigest(),
            "scope": "Artifact identity and internal consistency; not protection against deliberate file fabrication."}


def value_sha(value):
    return hashlib.sha256(contract.canonical_json(value).encode("utf-8")).hexdigest()


def validate_spec(spec):
    validate_runtime(spec["runtime"])
    gate_sha = spec["review_gate"].get("sha256")
    if not isinstance(gate_sha, str) or len(gate_sha) != 64 or any(c not in "0123456789abcdef" for c in gate_sha):
        raise ValueError("Worker must pin an exact completed delegated-AI review gate hash")
    validate_gate(spec["review_gate"]["path"], spec["review_gate"]["sha256"],
                         runtime=spec["runtime"], run_directory=spec["run_directory"])
    if Path(spec["cancel_path"]).resolve() != prepare.workspace_path(spec["run_directory"]) / "CANCEL":
        raise ValueError("Cancellation path must belong to this continuation run")
    remote.validate_origin(spec["origin"])
    service = prepare.read(spec["runtime"]["backend_evidence"][0]["path"],
                           spec["runtime"]["backend_evidence"][0]["sha256"])[0]
    if spec["origin"] != service["origin"]:
        raise ValueError("Runtime origin differs from the recorded isolated CPU service")
    if spec["stage"] not in ("D0", "F0") or spec["case_id"] not in CASES:
        raise ValueError("Only declared pilot D0/F0 stages are permitted")
    expected_stage_directory(spec)
    loaded, cases = load_bundle()
    case = next(c for c in cases if c["case_id"] == spec["case_id"])
    schema = loaded["response_schema"]
    messages = case["messages"]
    provenance = None
    if spec["stage"] == "F0":
        provenance = validate_prior_draft(spec)
        final = contract.build_final_messages(draft_messages=messages, raw_draft=spec["raw_draft"],
            assigned_packet=case["assigned_packet"], prompt_contract=loaded["prompt_contract"], response_schema=schema)
        if not final["ready"]:
            raise ValueError("Actual draft does not permit dependent final")
        messages = final["messages"]
    elif spec.get("raw_draft") is not None or "draft_artifacts" in spec:
        raise ValueError("Draft stage cannot contain an earlier response")
    if base.canonical(spec["body"]) != base.canonical(request_body(spec["runtime"], messages, schema)):
        raise ValueError("API body differs from exact assigned request, controls or retained history")
    if type(spec["deadline_seconds"]) is not int or spec["deadline_seconds"] != STAGE_DEADLINE_SECONDS:
        raise ValueError("Declared engineering ceiling is 4500 seconds")
    payload = contract.strict_json(messages[1]["content"])
    visible = contract.evidence_ids(payload["common_context"]) | contract.evidence_ids(payload["public_numeric_fact_index"])
    source_visible = case["arm"] != "C" and (spec["stage"] == "F0" or case["arm"] == "E")
    if source_visible:
        visible |= contract.evidence_ids(case["assigned_packet"])
    if spec["stage"] == "F0":
        visible = set(final["visible_evidence_ids_for_final"])
    return {"status": "validated", "case_id": spec["case_id"], "stage": spec["stage"],
            "body_value_sha256": value_sha(spec["body"]), "visible_evidence_ids": sorted(visible),
            "expected_source_packet": case["assigned_packet"] if source_visible else None,
            "draft_provenance": provenance}


def check_token_capacity(receipt, rendered, runtime):
    count = receipt.get("token_count")
    if type(count) is not int or count <= 0:
        raise ValueError("Exact native tokenizer count is required")
    if receipt.get("rendered_utf8_sha256") != hashlib.sha256(rendered.encode("utf-8")).hexdigest():
        raise ValueError("Tokenizer evidence is not for the exact rendered history")
    if (receipt.get("model_digest") != base.DIGEST or receipt.get("template_sha256") != base.TEMPLATE
            or receipt.get("method") != "exact_installed_libllama_vocab_only"
            or receipt.get("add_special") is not True or receipt.get("parse_special") is not True
            or type(receipt.get("generation_calls")) is not int or receipt.get("generation_calls") != 0):
        raise ValueError("Tokenizer receipt does not match the pinned native tokenization contract")
    from sector_v491_tokenizer import GGUF_SHA256, LIBRARY_HASHES
    if receipt.get("gguf_sha256") != GGUF_SHA256 or receipt.get("library_hashes") != LIBRARY_HASHES:
        raise ValueError("Tokenizer GGUF/library provenance differs from installed pin")
    total = count + runtime["options"]["num_predict"]
    if total > runtime["options"]["num_ctx"]:
        raise CapacityFailure("Full exact history plus allowed output exceeds context; no generation or truncation")
    return {"status": "exact_request_fits_declared_context", "prompt_tokens": count,
            "allowed_output_tokens": runtime["options"]["num_predict"],
            "total_required_tokens": total, "context_tokens": runtime["options"]["num_ctx"],
            "scope": "This actual request only; not a worst-case bound for an unknown future response."}


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
