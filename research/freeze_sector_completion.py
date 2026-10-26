"""Freeze the three remaining pilot cells after review; never call a model."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import sector_completion_gate as validation

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "research/completion_20261026"
RUN = ROOT / "data/local_sector_runtime/v494_completion_20261026"
REPORTS = FOLDER / "run_reports"
REVIEW_NAMES = ("implementation_method_review.json", "orchestration_test_review.json",
                "completion_finalizer_review.json", "semantic_preparer_review.json",
                "root_prelaunch_review.json")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def ref(path):
    path = Path(path).resolve()
    return {"path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def main():
    if RUN.exists() or REPORTS.exists() or any((FOLDER / name).exists() for name in
            ("freeze.json", "review_gate.json", "freeze_validation.json")):
        raise FileExistsError("Fresh completion raw, report and freeze paths required")
    protocol = read(FOLDER / "protocol_and_review.json")
    validation.scope(protocol)
    validation.require(protocol.get("status") == "approved_design_for_prospective_completion_freeze",
                       "Final reviewed protocol required")
    refs = {key: protocol[key] for key in validation.BOUND if key not in
            ("runtime_ref", "protocol_ref", "finalizer_acceptance_ref", "completion_finalizer_review_ref")}
    refs.update(runtime_ref=ref(FOLDER / "runtime_candidate.json"),
                protocol_ref=ref(FOLDER / "protocol_and_review.json"),
                finalizer_acceptance_ref=protocol["exact_math_policy_ref"],
                completion_finalizer_review_ref=ref(FOLDER / "completion_finalizer_review.json"))
    for reference in refs.values():
        validation.checked(reference)
    review_refs = [ref(FOLDER / name) for name in REVIEW_NAMES]
    freeze_time = datetime.now(timezone.utc)
    validation.validate_reviews(review_refs, freeze_time)
    prior = read(ROOT / "research/continuation_20261026/freeze.json")
    code = {item["path"] for item in prior["code_refs"]} | set(validation.REQUIRED_CODE) | {
        "research/freeze_sector_completion.py",
        "research/publish_completion_review_ack.py",
        "research/finalize_sector_completion.py", "research/test_finalize_sector_completion.py",
        "research/completion_20261026/prepare_stage_semantic_audit.py",
        "research/completion_20261026/test_prepare_stage_semantic_audit.py",
        "research/continuation_20261026/prepare_stage_semantic_audit.py",
        "research/completion_20261026/runtime/start_isolated_cpu.ps1",
        "research/completion_20261026/runtime/stop_isolated_cpu.ps1",
    }
    scope_keys = ("purpose", "case_order", "max_generation_requests", "historical_generation_requests",
                  "campaign_max_generation_requests", "automatic_retries", "main_model_calls",
                  "main_allowed", "old_outputs_observed", "explicit_retry_slots",
                  "historical_explicit_retry_slots", "analysis_role", "excluded_new_main_execution",
                  "historical_first_attempt_results_unchanged")
    frozen = {key: protocol[key] for key in scope_keys}
    frozen.update(freeze_version="sector_completion_freeze_1", status="frozen_for_pilot_completion_only",
                  recorded_at_utc=freeze_time.isoformat(), run_directory=str(RUN), output_root=str(REPORTS),
                  code_refs=[ref(ROOT / name) for name in sorted(code)], review_refs=review_refs, **refs)
    write(FOLDER / "freeze.json", frozen)
    gate = {key: value for key, value in frozen.items()
            if key not in ("freeze_version", "status", "recorded_at_utc", "code_refs")}
    gate.update(receipt_version="sector_completion_gate_1", status="approved_for_completion_before_generation",
                review_mode="AI_delegated_by_user", recorded_at_utc=datetime.now(timezone.utc).isoformat(),
                freeze_ref=ref(FOLDER / "freeze.json"))
    write(FOLDER / "review_gate.json", gate)
    result = validation.validate_gate(FOLDER / "review_gate.json")
    write(FOLDER / "freeze_validation.json", result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
