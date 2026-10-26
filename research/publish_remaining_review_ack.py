"""Validate and atomically publish one completed external audit; no generation."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid

import run_sector_remaining as coordinator

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "data/local_sector_runtime/v494_remaining_20261026"
REPORTS = ROOT / "research/remaining_20261026/run_reports"
SEMANTIC = ROOT / "research/remaining_20261026/semantic"


def publish(stage_dir, review_path):
    stage_dir, review_path = Path(stage_dir).resolve(), Path(review_path).resolve()
    if stage_dir.parent != RUN or not review_path.is_relative_to(SEMANTIC):
        raise ValueError("This publisher is limited to this remaining run and semantic report tree")
    spec = coordinator.read(stage_dir / "worker_spec.json")
    if (not isinstance(spec.get("case_id"), str) or not isinstance(spec.get("stage"), str)
            or spec["case_id"] + "__" + spec["stage"] not in coordinator.STAGE_ORDER):
        raise ValueError("A declared remaining stage is required")
    if stage_dir.name != spec["case_id"] + "__" + spec["stage"]:
        raise ValueError("Stage folder and worker identity differ")
    review = coordinator.read(review_path)
    math_path = REPORTS / "allocation_math" / (stage_dir.name + ".json")
    ack = {"schema_version": "sector_remaining_stage_external_review_ack_1",
           "status": "completed", "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
           "case_id": spec["case_id"], "stage": spec["stage"],
           "worker_spec_ref": coordinator.ref(stage_dir / "worker_spec.json"),
           "transport_ref": coordinator.ref(stage_dir / "transport_result.json"),
           "stage_review_ref": coordinator.ref(stage_dir / "stage_review.json"),
           "allocation_math_ref": coordinator.ref(math_path),
           "semantic_review_ref": coordinator.ref(review_path),
           "review_axes": review.get("review_axes", {}),
           "model_calls": 0, "raw_model_content_modified": False,
           "outcome_success_required": False}
    coordinator.validate_external_review_ack(ack, spec=spec, folder=stage_dir, math_path=math_path)
    target = stage_dir / "external_review_ack.json"
    if target.exists():
        raise FileExistsError("An acknowledgement cannot be replaced")
    staging = SEMANTIC / (".ack_" + uuid.uuid4().hex + ".tmp")
    try:
        coordinator.write_json(staging, ack)
        # Hard-link creation is atomic and fails if target already exists.
        # The fully flushed source and target are on the same workspace volume.
        os.link(staging, target)
    finally:
        if staging.exists():
            staging.unlink()
    return {"status": "published", "acknowledgement_ref": coordinator.ref(target),
            "model_calls": 0, "outcome_success_required": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-dir", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(publish(args.stage_dir, args.review), ensure_ascii=False))


if __name__ == "__main__":
    main()
