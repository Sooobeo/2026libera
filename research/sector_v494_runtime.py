"""Supervised v4.9.4 pilot only: five fixed cases, D0 then first F0.

``prepare`` is offline; ``run`` is explicit and never resumes/retries an attempt.
All full-history requests are rendered, counted using the pinned local tokenizer,
and checked for output headroom before generation. No main entrypoint exists.
Old immutable design files are inputs and are never modified by this module.
The user delegated pre-output review to AI; no human completion is fabricated.
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

import local_sector_single_case as base
import prepare_sector_v491 as prepare
import sector_v48_transport as prior
import sector_v48_main_awake as awake
import sector_v492_contract as contract
import sector_v491_runtime as inherited
import prepare_sector_v494 as preparation
from sector_v494_review_gate import validate_review_gate

remote, bench = base.remote, base.bench
ROOT = Path(__file__).resolve().parents[1]
VERSION = "sector_v494_runtime_1"
STAGE_DEADLINE_SECONDS = 4500
MANIFEST = preparation.MANIFEST
PILOT_SOURCES = ("fidelity_q2_2026", "ubs_june_2026")
CASES = tuple(source + "__" + arm for source in PILOT_SOURCES for arm in ("E", "L")) + ("common_market_only__C",)


class CapacityFailure(ValueError):
    """Instrument cannot retain this history and reserved output; no generation."""


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


def candidate_runtime(*, backend, num_ctx, tokenizer_config, backend_evidence, num_thread=8):
    """A declaration, not a claim that a backend/context has been validated."""
    options = base.OPTIONS.copy()
    options.update(num_ctx=num_ctx, num_gpu=0 if backend == "cpu" else 999, num_thread=num_thread)
    return {"runtime_version": VERSION, "protocol_version": "4.9.4", "input_protocol_version": "4.9.1",
            "model": base.MODEL, "digest": base.DIGEST, "template_sha256": base.TEMPLATE,
            "engine_version": base.ENGINE, "backend": backend,
            "options": options, "think": False, "truncate": False, "shift": False,
            "stream": True, "keep_alive": 0, "deadline_seconds": STAGE_DEADLINE_SECONDS,
            "renderer_policy": base.RENDERER_POLICY_ID,
            "tokenizer_config": tokenizer_config, "backend_evidence": backend_evidence,
            "resource_ceiling_basis": "CPU engineering scenario: maximum admissible prompt57344/observed29.287 prefill tokens per second +8192/observed3.619 decoded tokens per second +load is about70.4minutes; 4500seconds(75minutes) is a declared allowance, not a paper-derived optimum or performance guarantee. Decode rate was measured on only6tokens. No content/output shortening or retries.",
            "pilot_order": list(CASES), "pilot_max_generation_requests": 10,
            "main_allowed": False, "requires_frozen_AI_review_gate": True, "frozen": False}


def validate_runtime(runtime):
    if not isinstance(runtime, dict) or runtime.get("backend") != "cpu":
        raise ValueError("This reviewed runtime supports only the explicitly measured CPU backend")
    options = runtime.get("options", {})
    if type(options.get("num_thread")) is not int or options["num_thread"] != 8:
        raise ValueError("Only the explicitly measured CPU thread candidate 8 is permitted")
    context = options.get("num_ctx")
    if type(context) is not int or context != 65536:
        raise ValueError("The declared and measured 65536-token context is required")
    if not isinstance(runtime.get("tokenizer_config"), dict) or not runtime["tokenizer_config"]:
        raise ValueError("Pinned tokenizer configuration is required")
    evidence = runtime.get("backend_evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("Recorded backend evidence references are required")
    if [ref.get("role") for ref in evidence] != ["cpu_service", "smoke_spec", "smoke_result"]:
        raise ValueError("CPU service, exact synthetic request and completed smoke result references required")
    service, smoke, result = [prepare.read(ref["path"], ref["sha256"])[0] for ref in evidence]
    if (service.get("status") != "ready" or service.get("version") != base.ENGINE
            or service.get("require_request_num_gpu_zero") is not True
            or service.get("child_environment", {}).get("OLLAMA_VULKAN") != "0"
            or service.get("child_environment", {}).get("OLLAMA_IGPU_ENABLE") != "0"
            or smoke.get("origin") != service.get("origin")
            or smoke.get("body", {}).get("model") != base.MODEL
            or smoke.get("body", {}).get("options", {}).get("num_gpu") != 0
            or smoke.get("body", {}).get("options", {}).get("num_ctx") != context
            or smoke.get("body", {}).get("options", {}).get("num_thread") != options["num_thread"]
            or result.get("status") != "completed" or result.get("response_model") != base.MODEL
            or result.get("assessment_scope") != "not_graded_engineering_feasibility"):
        raise ValueError("Backend declaration must bind recorded CPU settings, chosen context and completed synthetic smoke")
    expected = candidate_runtime(backend=runtime["backend"], num_ctx=context,
        tokenizer_config=runtime["tokenizer_config"], backend_evidence=evidence, num_thread=options["num_thread"])
    if base.canonical(runtime) != base.canonical(expected):
        raise ValueError("Runtime differs from fixed controls; no silent parameter changes")


def load_bundle():
    manifest, _ = prepare.read(MANIFEST)
    if manifest.get("protocol_version") != "4.9.4" or [c.get("case_id") for c in manifest.get("prepared_cases", [])] != list(CASES):
        raise ValueError("Exactly five declared v4.9.4 pilot cases are required")
    loaded, cases = inherited.load_bundle()
    for name, ref in manifest["inputs"].items():
        path = prepare.workspace_path(ref["path"])
        if remote.sha(path) != ref["sha256"]:
            raise ValueError("Reviewed preparation input changed: " + name)
    prompt = prepare.read(manifest["inputs"]["prompt_contract"]["path"], manifest["inputs"]["prompt_contract"]["sha256"])[0]
    if prompt != preparation.reviewed_prompt():
        raise ValueError("The shared conditional final prompt differs from the declared amendment")
    loaded["prompt_contract"] = prompt
    cases.append({"case_id": "common_market_only__C", "source_id": None, "arm": "C",
                  "common_market": copy.deepcopy(cases[0]["common_market"]),
                  "public_numeric_fact_index": copy.deepcopy(cases[0]["public_numeric_fact_index"]), "assigned_packet": None})
    for case, prepared_case in zip(cases, manifest["prepared_cases"]):
        path = prepare.workspace_path(prepared_case["path"])
        if remote.sha(path) != prepared_case["sha256"]:
            raise ValueError("Prepared pilot message changed")
        messages = remote.read(path)
        if (prepared_case.get("split") != "pilot" or prepared_case.get("case_id") != case["case_id"]
                or prepared_case.get("source_id") != case["source_id"] or prepared_case.get("arm") != case["arm"]):
            raise ValueError("Only the five predetermined pilot cases are allowed")
        rebuilt = contract.build_draft_messages(arm=case["arm"], assigned_packet=case["assigned_packet"],
            common_market=case["common_market"], public_numeric_fact_index=case["public_numeric_fact_index"],
            common_context=loaded["common_context"], prompt_contract=loaded["prompt_contract"],
            response_schema=loaded["response_schema"])
        if messages != rebuilt:
            raise ValueError("Prepared messages differ from exact reconstructed public inputs")
        case["messages"] = messages
    if tuple(c["case_id"] for c in cases) != CASES:
        raise ValueError("Pilot inventory/order differs from explicit runtime declaration")
    return loaded, cases


def request_body(runtime, messages, schema):
    validate_runtime(runtime)
    body = {k: copy.deepcopy(runtime[k]) for k in
            ("model", "think", "truncate", "shift", "stream", "keep_alive", "options")}
    body.update(messages=copy.deepcopy(messages), format=copy.deepcopy(schema))
    return body


def validate_spec(spec):
    validate_runtime(spec["runtime"])
    gate_sha = spec["review_gate"].get("sha256")
    if not isinstance(gate_sha, str) or len(gate_sha) != 64 or any(c not in "0123456789abcdef" for c in gate_sha):
        raise ValueError("Worker must pin an exact completed delegated-AI review gate hash")
    validate_review_gate(spec["review_gate"]["path"], spec["review_gate"]["sha256"],
                         runtime=spec["runtime"], run_directory=spec["run_directory"])
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


def supervise(spec_path):
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


def run_transport(*, spec, target, server_log):
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
        result = supervise(target / "worker_spec.json")
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


def prepare_pilot(runtime_path, output_dir, origin, server_log, review_gate):
    runtime_path, output_dir = Path(runtime_path).resolve(), prepare.workspace_path(output_dir)
    runtime = remote.read(runtime_path)
    validate_runtime(runtime)
    gate_result = validate_review_gate(review_gate, runtime=runtime)
    loaded, cases = load_bundle()
    output_dir.mkdir()  # Existing run IDs never authorize a retry.
    record = {"runtime_version": VERSION, "created_at_utc": remote.now(), "purpose": "pilot_only",
              "runtime": runtime, "runtime_file": str(runtime_path), "runtime_sha256": remote.sha(runtime_path),
              "origin": remote.validate_origin(origin), "server_log": str(Path(server_log).resolve()),
              "prepared_manifest_sha256": remote.sha(MANIFEST), "case_order": list(CASES),
              "review_gate": gate_result["gate_ref"],
              "max_generation_requests": 10, "main_model_calls": 0,
              "AI_preoutput_review_completed": True, "review_mode": "AI_delegated_by_user",
              "independent_human_review_completed": False, "frozen_for_pilot": True, "main_frozen": False,
              "development_revision": "New prospectively frozen pilot after observing the interrupted 20261019 pilot; not a blind replication or a replacement for old evidence.",
              "automatic_retries": 0, "source_scope": "Two pilot documents only; main source packets are never model inputs."}
    remote.save(output_dir / "pilot_declaration.json", record)
    return record


def run_pilot(output_dir, transport=run_transport):
    target = Path(output_dir).resolve()
    declaration = remote.read(target / "pilot_declaration.json")
    if (declaration["purpose"] != "pilot_only" or declaration["case_order"] != list(CASES)
            or declaration["max_generation_requests"] != 10 or declaration["main_model_calls"] != 0):
        raise ValueError("Only the exact declared five-case pilot is authorized")
    runtime = declaration["runtime"]
    validate_runtime(runtime)
    validate_review_gate(declaration["review_gate"]["path"], declaration["review_gate"]["sha256"], runtime=runtime)
    if remote.sha(declaration["runtime_file"]) != declaration["runtime_sha256"]:
        raise ValueError("Runtime declaration changed after preparation")
    loaded, cases = load_bundle()
    remote.save(target / "execution_started.json", {"at_utc": remote.now(), "no_resume_no_retry": True})
    from review_sector_v494_stage import review_and_record
    summaries, halt = [], False
    cancel = target / "CANCEL"
    for case in cases:
        if halt or cancel.exists():
            summaries.append({"case_id": case["case_id"], "status": "not_attempted_after_stop", "stages": []})
            continue
        row = {"case_id": case["case_id"], "stages": []}
        messages, raw_draft, draft_artifacts = case["messages"], None, None
        for stage in ("D0", "F0"):
            if cancel.exists():
                halt = True; row["status"] = "cancelled_before_stage"; break
            spec = {"origin": declaration["origin"], "runtime": runtime, "case_id": case["case_id"],
                    "stage": stage, "raw_draft": raw_draft,
                    "run_directory": str(target),
                    "review_gate": declaration["review_gate"],
                    "body": request_body(runtime, messages, loaded["response_schema"]),
                    "cancel_path": str(cancel), "deadline_seconds": runtime["deadline_seconds"]}
            if stage == "F0":
                spec["draft_artifacts"] = draft_artifacts
            result = transport(spec=spec, target=target / (case["case_id"] + "__" + stage),
                               server_log=declaration["server_log"])
            stage_review = review_and_record(spec, target / (case["case_id"] + "__" + stage), result)
            if not stage_review["instrument_integrity_pass"]:
                result = dict(result, system_integrity_incident=True)
            row["stages"].append({"stage": stage, "status": result["status"],
                "generation_requests_attempted": result["generation_requests_attempted"],
                "continuation_eligible": result["continuation_eligible"]})
            if result["system_integrity_incident"] or result["status"] == "cancelled":
                halt = True; row["status"] = "stopped_for_integrity_or_cancellation"; break
            if not result["continuation_eligible"]:
                row["status"] = "incomplete_first_attempt_retained"; break
            raw_text = result["response"]["message"]["content"]
            if stage == "D0":
                raw_draft = raw_text
                draft_artifacts = prior_draft_refs(target, case["case_id"])
                if result.get("response_artifact") != draft_artifacts["response"]:
                    raise RuntimeError("Transport response reference differs from the actual saved D0 artifact")
                final = contract.build_final_messages(draft_messages=case["messages"], raw_draft=raw_draft,
                    assigned_packet=case["assigned_packet"], prompt_contract=loaded["prompt_contract"],
                    response_schema=loaded["response_schema"])
                remote.save(target / (case["case_id"] + "__final_construction.json"), final)
                if not final["ready"]:
                    raise RuntimeError("Transport/contract continuation disagreement; no dependent request")
                messages = final["messages"]
            else:
                row["status"] = "two_stages_completed_semantic_review_pending"
        summaries.append(row)
        remote.save(target / (case["case_id"] + "__case_summary.json"), row)
    attempted = sum(s["generation_requests_attempted"] for c in summaries for s in c["stages"])
    if attempted > 10:
        raise RuntimeError("Internal pilot budget invariant violated")
    summary = {"status": "stopped" if halt or cancel.exists() else "pilot_attempt_sequence_finished",
               "cases": summaries, "generation_requests_attempted": attempted,
               "main_model_calls": 0, "automatic_retries": 0, "post_final_calls": 0,
               "AI_preoutput_review_completed": True, "review_mode": "AI_delegated_by_user",
               "independent_human_review_completed": False, "frozen_for_pilot": True, "main_frozen": False,
               "interpretation": "Execution status is not semantic correctness or evidence of any hypothesis."}
    remote.save(target / "pilot_summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path)
    sub = parser.add_subparsers(dest="command")
    prep = sub.add_parser("prepare")
    prep.add_argument("--runtime", type=Path, required=True)
    prep.add_argument("--output-dir", type=Path, required=True)
    prep.add_argument("--origin", required=True)
    prep.add_argument("--server-log", type=Path, required=True)
    prep.add_argument("--review-gate", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.worker:
        return worker(args.worker)
    if args.command == "prepare":
        result = prepare_pilot(args.runtime, args.output_dir, args.origin, args.server_log, args.review_gate)
    elif args.command == "run":
        result = run_pilot(args.output_dir)
    else:
        parser.error("Choose explicit prepare or run")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
