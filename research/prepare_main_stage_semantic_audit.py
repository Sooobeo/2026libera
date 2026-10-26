"""Read-only unmasked evidence bundle for one durable prospective-main stage.

No generation, normalization, scoring or automatic source-rating interpretation.
The live continuation preparer and frozen main sources remain unchanged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PURE_HELPER = ROOT / "research/continuation_20261026/prepare_stage_semantic_audit.py"
PURE_HELPER_SHA = "efb82936ee541f187d8b352a1a28afa8ecea3d83401439a6e92a82df9731fb04"
if hashlib.sha256(PURE_HELPER.read_bytes()).hexdigest() != PURE_HELPER_SHA:
    raise ValueError("Stable pure-parser helper changed")
_spec = importlib.util.spec_from_file_location("_stable_semantic_parser", PURE_HELPER)
_pure = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pure)
strict = _pure.strict  # Pure parsing only; no old globals or preparation entrypoint changed.

CASES = ("fidelity_q3_2026__E", "fidelity_q3_2026__L", "ubs_july_2026__E", "ubs_july_2026__L", "common_market_only__C")
RUBRIC = {"path": "research/v492_evaluation_protocol_20261019_r2.json",
          "sha256": "807def444cc36d4a702321401a52e653b3f9a304383911e13f3c0389183086f1"}


def path_of(path):
    path = Path(path)
    path = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Path outside workspace")
    return path


def read(path):
    path = path_of(path)
    raw = path.read_bytes()
    value = strict(raw.decode("utf-8-sig"))
    if raw != path.read_bytes():
        raise ValueError("Artifact changed while reading")
    return value, {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}


def bound(reference, expected=None):
    path = path_of(reference["path"])
    if expected is not None and path != path_of(expected):
        raise ValueError("Bound artifact belongs to another run, case or role")
    value, actual = read(path)
    if actual["sha256"] != reference["sha256"]:
        raise ValueError("Bound artifact hash mismatch")
    return value, actual


def validate_main_spec(spec, directory):
    import sector_main_runtime as runtime
    runtime.validate_spec(spec)
    runtime.validate_worker_location(spec, directory)


def same_ref(left, right):
    return path_of(left["path"]) == path_of(right["path"]) and left["sha256"] == right["sha256"]


def prepare(stage_directory, math_sidecar=None):
    directory = path_of(stage_directory)
    run = directory.parent
    case, stage = directory.name.rsplit("__", 1)
    if case not in CASES or stage not in {"D0", "F0"}:
        raise ValueError("Only a declared main5 D0/F0 stage is supported")
    declaration, declaration_ref = read(run / "campaign_declaration.json")
    if (declaration.get("purpose") != "main" or declaration.get("main_allowed") is not True
            or declaration.get("case_order") != list(CASES)
            or declaration.get("max_generation_requests") != 10 or declaration.get("automatic_retries") != 0
            or path_of(declaration["run_directory"]) != run):
        raise ValueError("Explicit prospective main declaration required")
    # Do not open worker messages or saved response text for a pending/failed stage.
    transport, transport_ref = read(directory / "transport_result.json")
    review, review_ref = read(directory / "stage_review.json")
    if review.get("case_id") != case or review.get("stage") != stage:
        raise ValueError("Stage review identity mismatch")
    result = {"version": "main_stage_semantic_bundle_1", "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "case_id": case, "stage": stage, "purpose": "main", "masking": "unmasked_stagewise_audit",
              "status": "unavailable_for_completed_output_review", "semantic_review_status": "not_assessed",
              "observed_transport_status": transport.get("status"), "model_calls": 0, "service_calls": 0,
              "input_artifacts_modified": False, "normalization_performed": False,
              "refs": [declaration_ref, transport_ref, review_ref]}
    if transport.get("status") not in {"completed", "model_structure_failure"} or review.get("instrument_integrity_pass") is not True:
        result["reason"] = "No bound normal-completion reading; partial/missing text is not extracted as a completed output."
        return result
    if type(transport.get("generation_requests_attempted")) is not int or transport["generation_requests_attempted"] != 1:
        raise ValueError("Exactly one main stage request required")
    spec, spec_ref = read(directory / "worker_spec.json")
    if spec.get("case_id") != case or spec.get("stage") != stage or path_of(spec["run_directory"]) != run:
        raise ValueError("Worker case/stage/run mismatch")
    if spec.get("review_gate") != declaration["review_gate"]:
        raise ValueError("Worker authority differs from campaign")
    gate, gate_ref = bound(declaration["review_gate"])
    if (gate.get("purpose") != "main" or gate.get("status") != "approved_for_main_before_generation"
            or gate.get("main_allowed") is not True or gate.get("case_order") != list(CASES)):
        raise ValueError("Candidate or continuation authority cannot authorize main")
    validate_main_spec(spec, directory)  # Full frozen source/settings/prior-history/main gate validation; file-only.
    response, response_ref = bound(transport["response_artifact"], directory / "http_0001_generation/response.json")
    if (response != transport.get("response") or response.get("done") is not True
            or response.get("done_reason") != "stop" or not isinstance(response.get("message", {}).get("content"), str)):
        raise ValueError("No exact normally stopped response envelope")
    for reference in review.get("input_refs", []):
        _, actual = bound(reference)
        result["refs"].append(actual)
    for required in (spec_ref, transport_ref, response_ref):
        if not any(same_ref(required, item) for item in review.get("input_refs", [])):
            raise ValueError("Stage review omits a required current input")
    manifest, manifest_ref = bound(declaration["prepared_manifest_ref"])
    prepared = manifest["prepared_cases"]
    if [row["case_id"] for row in prepared] != list(CASES):
        raise ValueError("Prepared main inventory differs")
    row = next(row for row in prepared if row["case_id"] == case)
    expected_messages, prepared_ref = bound({key: row[key] for key in ("path", "sha256")})
    messages = spec["body"]["messages"]
    if len(messages) != (2 if stage == "D0" else 4) or messages[:2] != expected_messages:
        raise ValueError("Prepared own initial history differs")
    initial = strict(messages[1]["content"])
    current = strict(messages[3]["content"]) if stage == "F0" else initial
    expected_source = None if case.endswith("__C") or (stage == "D0" and case.endswith("__L")) else case.rsplit("__", 1)[0]
    if (current.get("institution_document") or {}).get("source_id") != expected_source:
        raise ValueError("Actual stage source identity/timing differs")
    prior_text = None
    if stage == "F0":
        prior, prior_ref = bound(spec["draft_artifacts"]["response"], run / (case + "__D0") / "http_0001_generation/response.json")
        prior_text = prior["message"]["content"]
        if (prior.get("done") is not True or prior.get("done_reason") != "stop"
                or prior_text != spec["raw_draft"] or messages[2] != {"role": "assistant", "content": prior_text}):
            raise ValueError("Actual own completed D0 text differs")
        result["refs"].append(prior_ref)
    raw = response["message"]["content"]
    try:
        strict(raw)
        parse_error = None
    except (ValueError, TypeError) as error:
        parse_error = str(error)
    sidecar = None
    if math_sidecar is not None:
        if path_of(math_sidecar).is_relative_to(run):
            raise ValueError("Derived sidecar must remain outside raw run")
        sidecar, sidecar_ref = read(math_sidecar)
        if sidecar.get("case_id") != case or sidecar.get("stage") != stage:
            raise ValueError("Math sidecar belongs to another case or stage")
        sidecar_refs = sidecar.get("input_refs", [])
        for required in (spec_ref, transport_ref):
            if not any(same_ref(required, item) for item in sidecar_refs):
                raise ValueError("Math sidecar does not bind this raw stage")
        if sidecar.get("status") == "finalized" and not any(same_ref(response_ref, item) for item in sidecar_refs):
            raise ValueError("Finalized math sidecar omits exact raw response")
        for reference in sidecar_refs:
            _, actual = bound(reference)
            result["refs"].append(actual)
        result["refs"].append(sidecar_ref)
    _, rubric_ref = bound(RUBRIC)
    result["refs"] += [spec_ref, gate_ref, response_ref, manifest_ref, prepared_ref, rubric_ref]
    result.update(status="prepared_for_semantic_reading", semantic_review_status="pending_actual_AI_reading",
                  raw_response_text=raw, raw_response_content_sha256=hashlib.sha256(raw.encode()).hexdigest(),
                  output_parse_diagnostic=parse_error, own_prior_raw_text=prior_text,
                  common_system_instruction=messages[0]["content"], actual_initial_payload=initial,
                  actual_current_payload=current, observed_math_sidecar=sidecar,
                  math_sidecar_scope="Read-only input binding checked when supplied; math not recomputed here, no normalization claim and no grounds for raw prose truth.",
                  rubric_ref=rubric_ref, coverage={"semantic_rows_read": 0, "numeric_claims_checked": None, "automatic_semantic_scores": False},
                  review_axes={"errors": "Raw output and parse diagnostics retained; actual claim audit pending.",
                               "consistency": "Explicit main authority, actual source/history and current saved-response refs checked.",
                               "paper_topic": "Institution evidence -> interpretation -> stated reason -> raw allocation is the review object; semantic verdict pending."},
                  limitations=["Unmasked Codex-assisted stage audit preparation; no independent-human or statistical-rater claim.",
                               "Full source/settings/request/prior-artifact proof relies on unchanged main runtime validate_spec, not a new relaxed gate.",
                               "A derived full-budget vector cannot validate an incorrect raw sum, citation or explanation."])
    for reference in result["refs"]:
        if hashlib.sha256(path_of(reference["path"]).read_bytes()).hexdigest() != reference["sha256"]:
            raise ValueError("Input changed during preparation")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-dir", type=Path, required=True)
    parser.add_argument("--math-sidecar", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = path_of(args.output)
    if output.exists() or not output.is_relative_to(ROOT / "research/continuation_20261026"):
        raise ValueError("New exclusive review path under continuation_20261026 required")
    result = prepare(args.stage_dir, args.math_sidecar)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "semantic_review_status": result["semantic_review_status"], "output": str(output)}))


if __name__ == "__main__":
    main()
