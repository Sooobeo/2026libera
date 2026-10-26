"""Freeze exactly one new source-free C F0; no model or service calls."""
from datetime import datetime, timezone
import copy
import hashlib
import json
from pathlib import Path

from last_final_20261026 import runtime_adapter as validation

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "research/last_final_20261026"
RUN = ROOT / "data/local_sector_runtime/v494_last_final_20261026"
REPORTS = FOLDER / "run_reports"
REVIEW_NAMES = ("orchestration_test_review.json", "last_finalizer_review.json",
    "independent_prelaunch_review.json", "root_prelaunch_review.json", "freeze_publisher_review.json")
SUPPORT_CODE = {
    "research/last_final_20261026/test_freeze_publish.py",
    "research/last_final_20261026/runtime/start_isolated_cpu.ps1",
    "research/last_final_20261026/runtime/stop_isolated_cpu.ps1",
    "research/last_final_20261026/runtime/prepare_runtime.py",
    "research/last_final_20261026/prepare_external_binding.py",
    "research/last_final_20261026/prepare_protocol.py",
}
SCOPE_KEYS = ("purpose", "case_order", "stage_order", "power_policy", "max_generation_requests",
    "historical_generation_requests", "campaign_max_generation_requests", "automatic_retries",
    "main_model_calls", "post_final_calls", "main_allowed", "old_outputs_observed", "explicit_retry_slots",
    "historical_explicit_retry_slots", "analysis_role", "excluded_new_main_execution",
    "historical_first_attempt_results_unchanged")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def ref(path):
    path = Path(path).resolve()
    return {"path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write(path, value):
    content = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def freeze():
    if RUN.exists() or REPORTS.exists() or any((FOLDER / name).exists() for name in
            ("freeze.json", "review_gate.json", "freeze_validation.json")):
        raise FileExistsError("Fresh last-final raw, report and freeze paths required")
    protocol = read(FOLDER / "protocol_and_review.json")
    validation.scope(protocol)
    validation.require(protocol.get("status") == "approved_design_for_prospective_last_final_freeze",
                       "Final reviewed protocol required")
    refs = {key: protocol[key] for key in validation.BOUND if key not in
            ("runtime_ref", "protocol_ref", "last_finalizer_review_ref")}
    refs.update(runtime_ref=ref(FOLDER / "runtime_candidate.json"),
                protocol_ref=ref(FOLDER / "protocol_and_review.json"),
                last_finalizer_review_ref=ref(FOLDER / "last_finalizer_review.json"))
    validation.require(validation.same_ref(refs["finalizer_acceptance_ref"], protocol["exact_math_policy_ref"]),
                       "Accepted math identity differs")
    for key, reference in refs.items():
        validation.checked(reference, json_object=key != "prior_remaining_cancel_ref")
        if key != "protocol_ref":
            validation.require(validation.same_ref(protocol.get(key), reference), "Protocol identity differs: " + key)
    groups = {name: protocol[name] for name in validation.EXTERNAL_GROUPS}
    for group in groups.values():
        validation.verify_nested_refs(group)
    authority = {**protocol, **refs, **groups}
    _, _, _, prior_gate = validation.validate_history(authority)
    carried = validation.validated_external_draft(authority)
    runtime = read(FOLDER / "runtime_candidate.json")
    validation.validate_runtime(runtime)
    expected = copy.deepcopy(carried["old_spec"]["runtime"])
    expected["backend_evidence"][0] = runtime["backend_evidence"][0]
    validation.require(validation.base.canonical(expected) == validation.base.canonical(runtime),
                       "Only the isolated service identity may change")
    review_refs = [ref(FOLDER / name) for name in REVIEW_NAMES]
    freeze_time = datetime.now(timezone.utc)
    validation.validate_reviews(review_refs, freeze_time)
    prior = validation.checked(prior_gate["freeze_ref"])
    # Check each old hash before calculating current refs: never silently re-freeze changed history.
    inherited = {validation.checked(item, json_object=False).relative_to(ROOT).as_posix()
                 for item in prior["code_refs"]}
    code = inherited | set(validation.REQUIRED_CODE) | SUPPORT_CODE
    frozen = {key: protocol[key] for key in SCOPE_KEYS}
    frozen.update(freeze_version="sector_last_final_freeze_1", status="frozen_for_pilot_last_final_only",
        recorded_at_utc=freeze_time.isoformat(), run_directory=str(RUN), output_root=str(REPORTS),
        code_refs=[ref(ROOT / name) for name in sorted(code)], review_refs=review_refs, **refs, **groups)
    write(FOLDER / "freeze.json", frozen)
    gate = {key: value for key, value in frozen.items()
            if key not in ("freeze_version", "status", "recorded_at_utc", "code_refs")}
    gate.update(receipt_version="sector_last_final_gate_1", status="approved_for_last_final_before_generation",
        review_mode="AI_delegated_by_user", recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        freeze_ref=ref(FOLDER / "freeze.json"))
    write(FOLDER / "review_gate.json", gate)
    result = validation.validate_gate(FOLDER / "review_gate.json")
    write(FOLDER / "freeze_validation.json", result)
    return result


def main():
    print(json.dumps(freeze(), ensure_ascii=False))


if __name__ == "__main__":
    main()
