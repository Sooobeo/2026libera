"""Create one prospectively reviewed continuation freeze; never launch a model."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import sector_continuation_gate as validation

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "research/continuation_20261026"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def ref(path):
    path = Path(path).resolve()
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def main():
    if any((FOLDER / name).exists() for name in ("freeze.json", "review_gate.json", "freeze_validation.json")):
        raise FileExistsError("A continuation freeze already exists")
    protocol = read(FOLDER / "protocol_and_review.json")
    validation.scope(protocol, require_observed=False)
    old = ROOT / "research/recovery_20261025"
    refs = {
        "runtime_ref": ref(FOLDER / "runtime_candidate.json"),
        "protocol_ref": ref(FOLDER / "protocol_and_review.json"),
        "historical_gate_ref": ref(old / "review_gate.json"),
        "historical_terminal_ref": ref(old / "new_pilot/terminal_receipt.json"),
        "historical_summary_ref": ref(ROOT / "data/local_sector_runtime/v494_pilot_20261025/pilot_summary.json"),
        "prepared_manifest_ref": ref(ROOT / "data/sector_protocol/v494_design_20261025/prepared/preparation_manifest.json"),
        "finalizer_acceptance_ref": ref(old / "allocation_finalization_acceptance_r2.json"),
    }
    review_paths = [FOLDER / "implementation_method_review.json", FOLDER / "orchestration_test_review.json",
                    FOLDER / "campaign_finalizer_review.json"]
    reviews = [read(p) for p in review_paths]
    freeze_time = datetime.now(timezone.utc)
    for review in reviews:
        if review.get("status") != "PASS":
            raise ValueError("Completed passing bounded reviews required")
        if validation.timestamp(review["completed_at_utc"]) > freeze_time:
            raise ValueError("Review must precede prospective freeze")
        for axis in ("errors", "consistency", "paper_topic"):
            axis_review = review.get("review_axes", {}).get(axis, {})
            if axis_review.get("pass") is not True or not isinstance(axis_review.get("reason"), str) or not axis_review["reason"].strip():
                raise ValueError("Missing required review axis")
    def review_refs(value):
        if isinstance(value, dict):
            if "path" in value and "sha256" in value:
                yield value
            for item in value.values():
                yield from review_refs(item)
        elif isinstance(value, list):
            for item in value:
                yield from review_refs(item)
    reviewed_paths = set()
    for review in reviews:
        for reference in review_refs(review):
            path = validation.paths.workspace_path(reference["path"])
            if ref(path)["sha256"] != reference["sha256"]:
                raise ValueError("Reviewed source changed: " + str(path))
            reviewed_paths.add(path.relative_to(ROOT).as_posix())
    if not {"research/run_sector_continuation.py", "research/sector_continuation_runtime.py",
            "research/sector_continuation_gate.py", "research/sector_continuation_awake.py",
            "research/finalize_sector_campaign.py", "research/finalize_sector_allocation.py"}.issubset(reviewed_paths):
        raise ValueError("Every execution/finalizer source needs a current reviewed hash")
    code = {r["path"] for r in read(old / "pilot_freeze.json")["code_refs"]}
    code |= set(validation.REQUIRED_CODE) | {
        "research/finalize_sector_campaign.py", "research/freeze_sector_continuation.py",
        "research/test_sector_continuation.py", "research/test_finalize_sector_campaign.py",
        "research/continuation_20261026/runtime/start_isolated_cpu.ps1",
        "research/continuation_20261026/runtime/stop_isolated_cpu.ps1",
    }
    frozen = {"freeze_version": "sector_continuation_freeze_1",
        "status": "frozen_for_pilot_continuation_only", "purpose": "pilot_continuation",
        "recorded_at_utc": freeze_time.isoformat(),
        "run_directory": str(ROOT / "data/local_sector_runtime/v494_continuation_20261026"),
        "output_root": str(FOLDER / "run_reports"), "case_order": list(validation.CASES),
        "max_generation_requests": 8, "historical_generation_requests": 3,
        "campaign_max_generation_requests": 11, "automatic_retries": 0,
        "main_allowed": False, "old_outputs_observed": True,
        "explicit_retry_slots": ["fidelity_q2_2026__L__D0"], **refs,
        "code_refs": [ref(ROOT / p) for p in sorted(code)],
        "review_refs": [ref(p) for p in review_paths]}
    write(FOLDER / "freeze.json", frozen)
    gate = {k: v for k, v in frozen.items() if k not in ("freeze_version", "status", "recorded_at_utc", "code_refs")}
    gate.update(receipt_version="sector_continuation_gate_1", status="approved_for_continuation_before_generation",
                review_mode="AI_delegated_by_user", recorded_at_utc=datetime.now(timezone.utc).isoformat(),
                freeze_ref=ref(FOLDER / "freeze.json"))
    write(FOLDER / "review_gate.json", gate)
    result = validation.validate_gate(FOLDER / "review_gate.json")
    write(FOLDER / "freeze_validation.json", result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
