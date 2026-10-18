"""Offline main-only artifact loader; never authorizes or executes a main run.

The manifest remains the unapproved input *candidate*. A separately gated
runner writes execution snapshots; this reader retains those assertions and
their hashes without manufacturing human approval. Actual durable generation
requests are counted separately from this evaluator's zero model calls.

The artifact traversal is deliberately adapted from the pilot loader, not
activated by modifying its global source IDs. Shared neutral read/validation
helpers and the frozen pure scoring functions are imported unchanged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from evaluate_sector_v48 import evaluate_case, evaluate_bundle
from evaluate_sector_v48_artifacts import (ROOT, ENDPOINTS, read, digest, reference,
                                         _below, _validate_ref, _load_endpoint)

VERSION = "v4.8-main-offline-artifacts-1"
SOURCES = ("fidelity_q3_2026", "ubs_july_2026")
ROSTER = tuple({"case_id": source + "__" + arm, "source_id": source, "arm": arm, "split": "main"}
               for source in SOURCES for arm in ("R1", "R4"))
EXECUTION_SNAPSHOTS = ("main_execution_gate_snapshot.json", "main_execution_authorization_snapshot.json",
                       "human_source_review_snapshot.json")
EVALUATOR_MATERIAL_KEYS = ("reference_annotations", "source_verification", "design_handoff",
                           "evaluation_protocol", "review_template", "source_comparison")


def verify_evaluator_material_refs(materials, gold_path):
    """Fail before scoring if the candidate's offline criteria have changed.

    Metadata references stay outside the 32 public prompt files. This offline
    reader verifies bytes; the online gate only validates their metadata shape.
    No alternate annotation file is silently accepted, even with equal bytes.
    """
    if not isinstance(materials, dict) or set(materials) != set(EVALUATOR_MATERIAL_KEYS):
        raise ValueError("Exactly six candidate-bound evaluator material references are required")
    verified = {}
    for name in EVALUATOR_MATERIAL_KEYS:
        item = materials[name]
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise ValueError("Malformed evaluator material reference: " + name)
        path, expected = item["path"], item["sha256"]
        if (not isinstance(path, str) or not Path(path).is_absolute()
                or not isinstance(expected, str) or len(expected) != 64
                or any(c not in "0123456789abcdef" for c in expected)):
            raise ValueError("Evaluator materials require absolute paths and lowercase SHA-256: " + name)
        actual_path = Path(path).resolve()
        if name == "reference_annotations" and actual_path != Path(gold_path).resolve():
            raise ValueError("--gold differs from candidate-bound reference_annotations path")
        if not actual_path.is_file() or digest(actual_path) != expected:
            raise ValueError("Candidate-bound evaluator material changed: " + name)
        verified[name] = reference(actual_path)
    return verified


def _load_candidate(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    prepared, manifest = manifest_path.parent, read(manifest_path)
    if (manifest.get("candidate_version") != "v4.8-main-candidate-1"
            or manifest.get("protocol_version") != "4.8"
            or manifest.get("scope") != "offline_main_input_candidate_not_execution_registration"
            or manifest.get("roster") != list(ROSTER)
            or manifest.get("planned_case_count") != 4 or manifest.get("expected_sector_count") != 44
            or any(manifest.get(key) is not False for key in ("main_authorized", "main_frozen", "human_review_completed"))):
        raise ValueError("Expected the fixed unapproved v4.8 main candidate, not a pilot or execution approval")
    required = {"market_input.json", "public_numeric_registry.json", "runtime.json", "prompt_contract.json",
                "system_instruction.txt", "remaining_requirements.json"}
    required.update("packets/" + source + ".json" for source in SOURCES)
    required.update(f"schemas/{arm}_stage{stage}.json" for arm in ("R1", "R4") for stage in range(1, 5))
    required.update(f"previews/{case['case_id']}/stage{stage}_payload.json" for case in ROSTER for stage in range(1, 5))
    if set(manifest.get("files", {})) != required:
        raise ValueError("Main candidate file inventory differs from the specified public input set")
    for relative, expected in manifest["files"].items():
        if digest(_below(prepared, relative)) != expected:
            raise ValueError("Candidate input changed: " + relative)
    market, registry = read(prepared / "market_input.json"), read(prepared / "public_numeric_registry.json")
    if registry.get("source", {}).get("sha256") != digest(prepared / "market_input.json"):
        raise ValueError("Public registry points to another market version")
    packets = {source: read(prepared / "packets" / (source + ".json")) for source in SOURCES}
    for source, packet in packets.items():
        if packet.get("source_id") != source or packet.get("split") != "main":
            raise ValueError("Wrong main packet identity or split")
    return manifest, market, registry, packets


def _load_main_gold(path):
    selected = {}
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        source = value.get("source_id")
        if source in SOURCES:
            if source in selected or value.get("split") != "main":
                raise ValueError("Duplicate or non-main source annotation")
            selected[source] = value
    if set(selected) != set(SOURCES):
        raise ValueError("Both main source annotations are required offline")
    return selected


def build_report(manifest_path, run_root, gold_path, *, workspace_root=ROOT, synthetic=False):
    """Read captured main artifacts without running, approving, or repairing them."""
    manifest_path, run_root, gold_path = map(lambda p: Path(p).resolve(), (manifest_path, run_root, gold_path))
    manifest, market, registry, packets = _load_candidate(manifest_path)
    evaluator_materials = verify_evaluator_material_refs(manifest.get("evaluator_material_refs"), gold_path)
    snapshot_path = run_root / "manifest_snapshot.json"
    if not snapshot_path.is_file() or read(snapshot_path) != manifest:
        raise ValueError("Run candidate manifest snapshot differs from the supplied main candidate")
    expected_cases = {case["case_id"] for case in ROSTER}
    requests = []
    for request in run_root.rglob("request.json"):
        if request.parent.name.endswith("_generation"):
            parts = request.relative_to(run_root).parts
            if (len(parts) != 4 or parts[0] not in expected_cases or parts[1] not in ENDPOINTS
                    or parts[2] != "http_0001_generation"):
                raise ValueError("Unregistered main generation request; cannot omit extra sources, endpoints or calls")
            requests.append(request)
    golds = _load_main_gold(gold_path)
    summary_path = run_root / "summary.json"
    summary = read(summary_path) if summary_path.is_file() else None
    if summary is not None and summary.get("planned_cases") != list(ROSTER):
        raise ValueError("Main run summary roster differs from the fixed four cases")
    primary, auxiliary, materials, issues, case_records = [], [], [], [], []
    snapshots = {}
    for name in EXECUTION_SNAPSHOTS:
        path = run_root / name
        snapshots[name] = reference(path) if path.is_file() else None
        if requests and not path.is_file():
            issues.append({"kind": "main_execution_snapshot_missing", "filename": name})
    totals = {"core_generation_calls": sum(p.relative_to(run_root).parts[1] not in ("C1", "C2") for p in requests),
              "auxiliary_generation_calls": sum(p.relative_to(run_root).parts[1] in ("C1", "C2") for p in requests),
              "main_model_calls": len(requests)}
    if summary is None:
        issues.append({"kind": "main_run_summary_missing"})
    else:
        for key, actual in totals.items():
            if summary.get(key) != actual:
                issues.append({"kind": "main_summary_request_count_disagrees", "field": key,
                               "reported": summary.get(key), "captured": actual})
        if requests and (summary.get("main_frozen") is not True or summary.get("human_review_completed") is not True):
            issues.append({"kind": "main_generation_without_recorded_pre_execution_gate_state",
                           "main_frozen_as_recorded": summary.get("main_frozen"),
                           "human_source_review_as_recorded": summary.get("human_review_completed")})
    for case in ROSTER:
        folder = run_root / case["case_id"]
        case_summary_path = folder / "case_summary.json"
        case_summary = read(case_summary_path) if case_summary_path.is_file() else {}
        case_manifest_path = folder / "case_manifest.json"
        case_manifest = read(case_manifest_path) if case_manifest_path.is_file() else {}
        for obj in (case_summary, case_manifest):
            if obj and any(obj.get(key) != case[key] for key in ("case_id", "source_id", "arm", "split")):
                raise ValueError("Main case metadata disagrees with the prescribed roster")
        if case_manifest.get("packet"):
            _validate_ref(case_manifest["packet"], manifest_path.parent / "packets" / (case["source_id"] + ".json"), workspace_root)
        count = sum((folder / endpoint / "http_0001_generation/request.json").is_file() for endpoint in ENDPOINTS)
        declared = case_summary.get("core_calls_attempted", 0) + case_summary.get("auxiliary_calls_attempted", 0)
        if declared > count:
            raise ValueError("Main case summary claims requests absent from the preserved artifacts")
        if case_summary and declared != count:
            issues.append({"case_id": case["case_id"], "kind": "summary_attempt_count_lags_preserved_requests",
                           "summary_attempt_count": declared, "captured_request_count": count})
        if case_summary and case_summary.get("main_model_calls") != count:
            issues.append({"case_id": case["case_id"], "kind": "case_main_call_count_disagrees",
                           "reported": case_summary.get("main_model_calls"), "captured": count})
        if folder.exists() and not case_summary:
            issues.append({"case_id": case["case_id"], "kind": "case_summary_missing_or_interrupted"})
        case_records.append({**case, "case_summary_ref": reference(case_summary_path) if case_summary else None,
                             "case_summary": case_summary or None, "captured_generation_request_count": count,
                             "system_integrity_incident": case_summary.get("system_integrity_incident")})
        endpoint_materials = []
        for endpoint in ENDPOINTS:
            raw, metadata, material = _load_endpoint(case, endpoint, folder, case_summary, workspace_root)
            metadata.update(workflow_generation_attempted=count > 0,
                            workflow_status=case_summary.get("status", "no_case_summary" if folder.exists() else "not_started"),
                            workflow_termination_reason=case_summary.get("error", case_summary.get("status")))
            material.update(case_id=case["case_id"], source_id=case["source_id"], arm=case["arm"])
            endpoint_materials.append(material)
            for diagnostic in material["capture_diagnostics"]:
                issues.append({"case_id": case["case_id"], "endpoint": endpoint, **diagnostic})
            if endpoint == "C0":
                primary.append(evaluate_case(raw, packets[case["source_id"]], golds[case["source_id"]], market, registry, metadata))
            elif endpoint in ("C1", "C2") and (material["record_ref"] or material["attempted"]):
                auxiliary.append(evaluate_case(raw, packets[case["source_id"]], golds[case["source_id"]], market, registry, metadata))
        if case_summary.get("primary_record"):
            _validate_ref(case_summary["primary_record"], folder / "C0/record.json", workspace_root)
        if case_summary.get("auxiliary_terminal_record"):
            terminals = [x for x in endpoint_materials if x["endpoint"] in ("C1", "C2") and x["record_ref"]]
            if not terminals:
                raise ValueError("Auxiliary terminal claimed without a main auxiliary record")
            _validate_ref(case_summary["auxiliary_terminal_record"], folder / terminals[-1]["endpoint"] / "record.json", workspace_root)
        materials.extend(endpoint_materials)
    if verify_evaluator_material_refs(manifest["evaluator_material_refs"], gold_path) != evaluator_materials:
        raise ValueError("Candidate-bound evaluator materials changed during analysis")
    now = datetime.now(timezone.utc).isoformat()
    dependencies = ("evaluate_sector_v48_main_artifacts.py", "evaluate_sector_v48_artifacts.py", "evaluate_sector_v48.py",
                    "sector_engine.py", "sector_response_schema.py")
    provenance = {"prepared_manifest": reference(manifest_path), "manifest_role": "unapproved_main_input_candidate",
                  "run_manifest_snapshot": reference(snapshot_path),
                  "run_summary": reference(summary_path) if summary_path.is_file() else None,
                  "execution_snapshot_refs": snapshots, "candidate_files": manifest["files"],
                  "gold_annotations": reference(gold_path), "gold_access_role": "offline_evaluator_only",
                   "evaluator_material_refs": evaluator_materials,
                  "evaluator_software": [reference(Path(__file__).with_name(name)) for name in dependencies],
                  "verification_scope": "Candidate bytes, endpoint references and request counts checked; gate/authorization source judgments are not independently certified by this loader."}
    accounting = {"observed_main_generation_calls": len(requests),
                  "observed_core_generation_calls": totals["core_generation_calls"],
                  "observed_auxiliary_generation_calls": totals["auxiliary_generation_calls"],
                  "summary_main_model_calls_as_recorded": (summary or {}).get("main_model_calls"),
                  "count_scope": "Durable generation request envelopes, including attempts failing before provider inference; not a count of successful model answers."}
    report = {"artifact_version": VERSION, "created_at_utc": now, "scope": "main_only_offline_analysis",
              "data_origin": "synthetic_fixture_not_empirical" if synthetic else "captured_artifacts",
              "model_calls_by_this_evaluation": 0, **accounting,
               "evaluation_materials_verified": True,
              "provenance": provenance, "primary_C0_bundle": evaluate_bundle(primary, list(SOURCES)),
              "primary_C0_cases": primary, "auxiliary_endpoint_cases": auxiliary,
              "case_execution_records": case_records, "artifact_issues": issues,
              "system_integrity_incidents_present": any(x["system_integrity_incident"] is True for x in case_records)
                  or bool(summary and summary.get("system_integrity_incident")),
              "pre_execution_human_source_review_as_recorded": (summary or {}).get("human_review_completed"),
              "pre_execution_freeze_as_recorded": (summary or {}).get("main_frozen"),
              "execution_gate_verified_by_this_loader": False,
              "independent_human_review_completed": False, "semantic_review_completed": False,
              "strategic_preservation_verdict": None,
              "limits": ["The candidate manifest alone never authorizes a main execution. Gate snapshots are retained for a separate integrity audit.",
                         "Any pre-execution human source review is distinct from the new unfilled response-semantic worksheet.",
                         "All four prescribed C0 cases and 44 sector rows remain in accounting, including missing or invalid outputs.",
                         "C1/C2 are separate auxiliary observations and never overwrite C0 or become independent cases.",
                         "Source labels, arithmetic and resolving IDs do not certify source-to-reason-to-action preservation.",
                         "These are retrospective public-view cases with mixed dates, not private institution strategies or independently held-out institutions."]}
    worksheet = {"artifact_version": VERSION, "created_at_utc": now,
                 "artifact_kind": "unfilled_main_evaluator_only_semantic_review_worksheet",
                 "data_origin": report["data_origin"], "provenance": provenance,
                 "review_status": "not_started", "reviewer_id": None, "reviewer_role": None,
                 "independence_from_generation": None, "independent_human_review_completed": False,
                 "primary_C0_reviews": [], "auxiliary_reviews": [], "workflow_trace_materials": materials,
                 "instructions": report["limits"] + ["Record literal source passages, response locations and reasoning for each human judgment. No null field means success.",
                   "Compare the source, the model interpretation, its rationale and actual raw weights; keep numerical fact tuples and candidate lineage explicit."]}
    for name, values in (("primary_C0_reviews", primary), ("auxiliary_reviews", auxiliary)):
        for result in values:
            worksheet[name].append({"case_id": result["case_id"], "source_id": result["source_id"], "arm": result["arm"],
                                    "endpoint": result["endpoint"], "response_sha256": result["response_sha256"],
                                    "execution": result["execution"], "source_material_context": result["source_material_context"],
                                    **result["review_preparation"]})
    return report, worksheet


def write_report(manifest_path, run_root, gold_path, output, *, workspace_root=ROOT, synthetic=False):
    output = Path(output).resolve()
    protected = (Path(manifest_path).resolve().parent, Path(run_root).resolve())
    if any(output.is_relative_to(p) or p.is_relative_to(output) for p in protected):
        raise ValueError("Main evaluator output must be separate from candidate and online directories")
    if output.exists():
        raise FileExistsError("Preserve prior research output; use a new offline directory")
    report, worksheet = build_report(manifest_path, run_root, gold_path, workspace_root=workspace_root, synthetic=synthetic)
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (("evaluation_report.json", report), ("semantic_review_worksheet.json", worksheet)):
        with (output / name).open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    receipt = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "model_calls_by_this_evaluation": 0,
               "observed_main_generation_calls": report["observed_main_generation_calls"], "data_origin": report["data_origin"],
               "independent_human_review_completed": False, "main_execution_authorized_by_this_tool": False,
               "files": [reference(output / name) for name in ("evaluation_report.json", "semantic_review_worksheet.json")]}
    with (output / "receipt.json").open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "run-root", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--gold", default=str(ROOT / "data/sector_documents/evaluator_only/reference_annotations.jsonl"))
    parser.add_argument("--synthetic", action="store_true", help="Mark fabricated fixtures; not an empirical run")
    args = parser.parse_args(argv)
    print(json.dumps(write_report(args.manifest, args.run_root, args.gold, args.output, synthetic=args.synthetic), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
