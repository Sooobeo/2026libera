"""Guarded last-final-stage numeric wrapper; no changes to accepted arithmetic."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = Path(__file__).resolve().parent
PURE_PATH = ROOT / "research/completion_20261026/audit_stage_numerics.py"
PURE_SHA = "10ee4d79fdcdebd1adbdf3bba2278464e044bad6b19248aa601b4ed60daaa8b9"
GUARD_PATH = REPORT_ROOT / "prepare_stage_semantic_audit.py"
GUARD_SHA = "77e4509ef7f504825ea735eff4f0a8644631c4f8853566daa8e18ea77d5e57a3"
SLOTS = ("common_market_only__C__F0",)


def pinned_module(path, digest, name):
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError("Pinned offline audit source changed")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pure = pinned_module(PURE_PATH, PURE_SHA, "accepted_completion_numeric_facts")


def rebuild_guarded_bundle(directory):
    return pinned_module(GUARD_PATH, GUARD_SHA, "last_final_numeric_semantic_guard").prepare(directory)


def audit_bundle(bundle_path, math_path):
    bundle, bundle_ref = pure.read(bundle_path)
    slot = str(bundle.get("case_id")) + "__" + str(bundle.get("stage"))
    if (bundle.get("version") != "last_final_semantic_bundle_1" or bundle.get("purpose") != "pilot_last_final"
            or bundle.get("status") != "prepared_for_semantic_reading" or slot not in SLOTS
            or bundle.get("observed_transport_status") not in {"completed", "model_structure_failure"}):
        raise ValueError("Completed remaining semantic bundle required; no partial/live text use")
    matches = [r for r in bundle["refs"] if pure.path_of(r["path"]).name == "worker_spec.json"
               and pure.path_of(r["path"]).parent.name == slot]
    if len(matches) != 1:
        raise ValueError("Exactly one current stage worker-spec binding required")
    directory = pure.path_of(matches[0]["path"]).parent
    regenerated = rebuild_guarded_bundle(directory)
    comparable = lambda value: {k: v for k, v in value.items() if k != "created_at_utc"}
    if comparable(bundle) != comparable(regenerated):
        raise ValueError("Bundle differs from freshly guarded last-final stage")
    refs = [bundle_ref]
    for reference in bundle["refs"]:
        path = pure.path_of(reference["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != reference["sha256"]:
            raise ValueError("Bound remaining audit input changed")
        refs.append({"path": str(path), "sha256": reference["sha256"]})
    spec, sr = pure.bound(matches[0])
    transport, tr = pure.read(directory / "transport_result.json")
    declaration, dr = pure.read(directory.parent / "campaign_declaration.json")
    sidecar, mr = pure.read_bound_math(directory, declaration, math_path)
    refs.extend([sr, tr, dr, *mr])
    raw = bundle["raw_final_or_draft_text"]
    if hashlib.sha256(raw.encode("utf-8")).hexdigest() != bundle["raw_response_content_sha256"]:
        raise ValueError("Raw response text digest mismatch")
    current = pure.independent_allocation(raw)
    prior = prior_comparison = None
    if bundle["stage"] == "F0":
        prior_dir = pure.path_of(bundle["own_D0_stage_directory"])
        if prior_dir.name != bundle["case_id"] + "__D0":
            raise ValueError("Own D0 stage identity differs")
        prior_declaration, pdr = pure.bound(bundle["own_D0_declaration_ref"], prior_dir.parent / "campaign_declaration.json")
        if pure.path_of(prior_declaration["run_directory"]) != prior_dir.parent:
            raise ValueError("Own D0 declaration run differs")
        external = bundle["case_id"] == "common_market_only__C"
        if (bundle["own_D0_origin"] != ("fixed_previous_remaining_segment" if external else "same_last_final_run")
                or (prior_dir.parent == directory.parent) != (not external)):
            raise ValueError("External versus same-run D0 provenance differs")
        prior = pure.independent_allocation(bundle["own_prior_text"])
        prior_math = pure.path_of(prior_declaration["output_root"]) / "allocation_math" / (prior_dir.name + ".json")
        prior_sidecar, prior_refs = pure.read_bound_math(prior_dir, prior_declaration, prior_math)
        refs.extend([pdr, *prior_refs])
        prior_comparison = pure.compare_sidecar(prior, prior_sidecar, "completed")
    initial = pure.strict(spec["body"]["messages"][1]["content"], exact=True)
    result = {"version": "last_final_independent_numeric_audit_1", "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "numeric_facts_prepared_not_semantic_grade", "purpose": "pilot_last_final",
              "case_id": bundle["case_id"], "stage": bundle["stage"], "own_D0_origin": bundle.get("own_D0_origin"),
              "own_D0_stage_directory": bundle.get("own_D0_stage_directory"),
              "independent_current_allocation": current, "independent_own_D0_allocation": prior,
              "accepted_sidecar_comparison": pure.compare_sidecar(current, sidecar, transport["status"]),
              "accepted_own_D0_sidecar_comparison": prior_comparison,
              "visible_market_facts": pure.market_facts(initial["common_market"], initial["public_numeric_fact_index"]),
              "raw_and_derived_relations": pure.allocation_comparisons(current, prior, initial["common_market"]),
              "input_refs": refs, "implementation_refs": [
                  {"path": str(Path(__file__).resolve()), "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
                  {"path": str(PURE_PATH), "sha256": PURE_SHA}, {"path": str(GUARD_PATH), "sha256": GUARD_SHA}],
              "model_calls": 0, "service_calls": 0, "raw_artifacts_modified": False, "semantic_claims_graded": 0,
              "coverage": {"raw_daily_observations_available": False, "automatic_prose_grade": False,
                           "sidecar_match_is_not_semantic_success": True},
              "review_axes": {
                  "errors": "Exact raw arithmetic, derived units and current/own-D0 sidecar comparisons remain separate from prose support.",
                  "consistency": "Last-final guard re-executed; fixed external C D0 with preserved stopped-terminal ACK gap declaration and math are independently bound.",
                  "paper_topic": "Numerical reference facts support source-to-reason-to-allocation review without changing model history or claiming causal effects."}}
    for reference in result["input_refs"] + result["implementation_refs"]:
        if hashlib.sha256(pure.path_of(reference["path"]).read_bytes()).hexdigest() != reference["sha256"]:
            raise ValueError("Bound numeric audit artifact changed during preparation")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--math-sidecar", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = pure.path_of(args.output)
    if output.exists() or not output.is_relative_to(REPORT_ROOT):
        raise ValueError("New exclusive last-final report path required")
    result = audit_bundle(args.bundle, args.math_sidecar)
    encoded = json.dumps(pure.safe(result), ensure_ascii=True, allow_nan=False, indent=2) + "\n"
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(encoded)
    print(json.dumps({"status": result["status"], "output": str(output), "model_calls": 0}))


if __name__ == "__main__":
    main()
