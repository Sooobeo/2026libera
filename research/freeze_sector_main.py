"""Freeze already reviewed main inputs without running a model or changing them."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import sector_main_gate as validation

ROOT = Path(__file__).resolve().parents[1]
CONTINUATION = ROOT / "research/continuation_20261026"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def ref(path):
    path = validation.paths.workspace_path(path)
    return {"path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def reviewed_sources(review_paths, freeze_time):
    if len(review_paths) < 3 or len(set(review_paths)) != len(review_paths):
        raise ValueError("At least three distinct completed main reviews required")
    if len({ref(path)["sha256"] for path in review_paths}) != len(review_paths):
        raise ValueError("Duplicated review content cannot count as separate reviews")
    covered = set()
    for path in review_paths:
        review = read(path)
        if review.get("status") != "PASS" or validation.timestamp(review["completed_at_utc"]) > freeze_time:
            raise ValueError("Reviews must pass before the prospective freeze")
        for axis in ("errors", "consistency", "paper_topic"):
            item = review.get("review_axes", {}).get(axis, {})
            if item.get("pass") is not True or not isinstance(item.get("reason"), str) or not item["reason"].strip():
                raise ValueError("Every main review must address all three axes")
        for reference in validation.verify_nested_refs(review):
            covered.add(validation.paths.workspace_path(reference["path"]).relative_to(ROOT).as_posix())
    required = {"research/run_sector_main.py", "research/sector_main_runtime.py",
                "research/sector_main_gate.py", "research/sector_main_awake.py",
                "research/test_sector_main.py", "research/freeze_sector_main.py",
                "research/finalize_sector_campaign.py", "research/finalize_sector_allocation.py"}
    if not required.issubset(covered):
        raise ValueError("Current execution, freeze and finalizer source hashes must be reviewed: "
                         + ", ".join(sorted(required - covered)))
    return covered


def freeze(args):
    protocol_path, runtime_path, operating_path = [validation.paths.workspace_path(p)
        for p in (args.protocol, args.runtime, args.operating_review)]
    folder, run, reports = [validation.paths.workspace_path(p)
        for p in (args.freeze_dir, args.run_dir, args.output_root)]
    review_paths = [validation.paths.workspace_path(p) for p in args.review]
    if run.exists() or reports.exists():
        raise FileExistsError("Main raw and execution-report directories must be fresh")
    if any((folder / name).exists() for name in ("freeze.json", "review_gate.json", "freeze_validation.json")):
        raise FileExistsError("A freeze attempt already exists; preserve it")
    if (run == reports or run in reports.parents or reports in run.parents
            or folder.is_relative_to(run) or folder.is_relative_to(reports)):
        raise ValueError("Main inputs, raw evidence and execution reports must be separate")
    protocol, runtime, operating = map(read, (protocol_path, runtime_path, operating_path))
    validation.scope(protocol)
    terminal_path = CONTINUATION / "run_reports/terminal_receipt.json"
    summary_path = ROOT / "data/local_sector_runtime/v494_continuation_20261026/campaign_summary.json"
    terminal, summary = read(terminal_path), read(summary_path)
    validation.validate_operating_review(operating, terminal, summary, ref(terminal_path), ref(summary_path))
    validation.verify_nested_refs(operating)
    from sector_main_runtime import validate_runtime
    validate_runtime(runtime)
    refs = {
        "runtime_ref": ref(runtime_path), "protocol_ref": ref(protocol_path),
        "prepared_manifest_ref": ref(ROOT / "data/sector_protocol/v495_main_candidate_20261025/prepared/preparation_manifest.json"),
        "continuation_gate_ref": ref(CONTINUATION / "review_gate.json"),
        "continuation_terminal_ref": ref(terminal_path), "continuation_summary_ref": ref(summary_path),
        "continuation_operating_review_ref": ref(operating_path),
        "main_D0_preflight_ref": ref(CONTINUATION / "main_preflight/d0_capacity_r1/summary.json"),
        "finalizer_acceptance_ref": ref(ROOT / "research/recovery_20261025/allocation_finalization_acceptance_r2.json"),
        "campaign_finalizer_review_ref": ref(CONTINUATION / "campaign_finalizer_review.json"),
    }
    if protocol.get("prepared_manifest_ref") != refs["prepared_manifest_ref"] or protocol.get("continuation_operating_review_ref") != refs["continuation_operating_review_ref"]:
        raise ValueError("Protocol must bind current main inputs and actual operating review")
    freeze_time = datetime.now(timezone.utc)
    reviewed_sources(review_paths, freeze_time)
    inherited = read(CONTINUATION / "freeze.json")["code_refs"]
    code_paths = {validation.paths.workspace_path(item["path"]).relative_to(ROOT).as_posix() for item in inherited}
    for item in inherited:
        validation.checked(item, json_object=False)
    code_paths |= validation.REQUIRED_CODE | {"research/freeze_sector_main.py"}
    frozen = {"freeze_version": "sector_main_freeze_1", "status": "frozen_for_main_only",
        "purpose": "main", "recorded_at_utc": freeze_time.isoformat(),
        "run_directory": str(run), "output_root": str(reports), "case_order": list(validation.CASES),
        "max_generation_requests": 10, "automatic_retries": 0, "main_allowed": True,
        **refs, "code_refs": [ref(ROOT / name) for name in sorted(code_paths)],
        "review_refs": [ref(path) for path in review_paths]}
    folder.mkdir(parents=True, exist_ok=True)
    write(folder / "freeze.json", frozen)
    gate = {key: value for key, value in frozen.items()
            if key not in ("freeze_version", "status", "recorded_at_utc", "code_refs")}
    gate.update(receipt_version="sector_main_gate_1", status="approved_for_main_before_generation",
                review_mode="AI_delegated_by_user", recorded_at_utc=datetime.now(timezone.utc).isoformat(),
                freeze_ref=ref(folder / "freeze.json"))
    write(folder / "review_gate.json", gate)
    verified = validation.validate_gate(folder / "review_gate.json")
    write(folder / "freeze_validation.json", verified)
    return verified


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("protocol", "runtime", "operating-review", "freeze-dir", "run-dir", "output-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--review", type=Path, action="append", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("Explicit --execute only after completed operating and implementation reviews")
    print(json.dumps(freeze(args), ensure_ascii=False))


if __name__ == "__main__":
    main()
