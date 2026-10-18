"""Read-only v4.8 pilot artifact evaluation and evaluator-only review worksheets.

No model, HTTP, online-runner import or semantic judge is used. The command
requires a new output directory outside prepared inputs and online run artifacts.
It preserves C0 as the primary endpoint, and writes each C1/C2 separately.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from evaluate_sector_v48 import evaluate_case, evaluate_bundle

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("fidelity_q2_2026", "ubs_june_2026")
ROSTER = tuple({"case_id": source + "__" + arm, "source_id": source, "arm": arm, "split": "pilot"}
               for source in SOURCES for arm in ("R1", "R4"))
ENDPOINTS = ("stage1", "stage2", "stage3", "C0", "C1", "C2")
VERSION = "v4.8-offline-artifacts-1"


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key in artifact: " + str(path))
            result[key] = value
        return result
    def invalid(_):
        raise ValueError("Nonfinite JSON value in artifact: " + str(path))
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=pairs, parse_constant=invalid)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def value_digest(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def reference(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": digest(path)}


def _below(base, relative):
    base = Path(base).resolve()
    target = (base / relative).resolve()
    if not target.is_relative_to(base):
        raise ValueError("Artifact path escapes its declared directory")
    return target


def _validate_ref(ref, actual, workspace_root):
    if not isinstance(ref, dict) or ref.get("sha256") != digest(actual):
        raise ValueError("Recorded artifact hash does not match: " + str(actual))
    recorded_path = Path(ref.get("path", ""))
    if not recorded_path.is_absolute():
        recorded_path = Path(workspace_root) / recorded_path
    if recorded_path.resolve() != Path(actual).resolve():
        raise ValueError("Recorded artifact location does not match: " + str(actual))


def _load_prepared(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    prepared = manifest_path.parent
    manifest = read(manifest_path)
    if (manifest.get("protocol_version") != "4.8"
            or manifest.get("scope") != "all_four_fixed_pilot_cases_only"
            or manifest.get("roster") != list(ROSTER)
            or manifest.get("main_authorized") is not False):
        raise ValueError("Only the fixed v4.8 four-case pilot manifest is accepted")
    hashes = manifest.get("input_hashes", {})
    required = {"market_input.json", "public_numeric_registry.json", "runtime.json", "prompt_contract.json"}
    required.update("packets/" + source + ".json" for source in SOURCES)
    if not required.issubset(hashes):
        raise ValueError("Prepared input inventory is incomplete")
    for relative, expected in hashes.items():
        path = _below(prepared, relative)
        if digest(path) != expected:
            raise ValueError("Prepared input changed: " + relative)
    market = read(prepared / "market_input.json")
    registry = read(prepared / "public_numeric_registry.json")
    if registry.get("source", {}).get("sha256") != digest(prepared / "market_input.json"):
        raise ValueError("Public registry points to a different market version")
    packets = {source: read(prepared / "packets" / (source + ".json")) for source in SOURCES}
    for source, packet in packets.items():
        if packet.get("source_id") != source or packet.get("split") != "pilot":
            raise ValueError("Wrong prepared source packet")
    return manifest, market, registry, packets


def _load_gold(path):
    # This path is consumed only by the offline evaluator, never the runner.
    selected = {}
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        source = value.get("source_id")
        if source in SOURCES:
            if source in selected or value.get("split") != "pilot":
                raise ValueError("Duplicate or non-pilot source annotation")
            selected[source] = value
    if set(selected) != set(SOURCES):
        raise ValueError("Both pilot source annotations are required")
    return selected


def _raw_material(folder, record):
    """Use exact stored text. Event concatenation recovers fragments, not C0."""
    response_path = folder / "http_0001_generation/response.json"
    response, diagnostics = None, []
    if response_path.is_file():
        try:
            response = read(response_path)
            if not isinstance(response, dict) or not isinstance(response.get("message", {}), dict):
                raise ValueError("Malformed response envelope type")
        except (ValueError, TypeError, UnicodeError) as exc:
            response = None
            diagnostics.append({"kind": "malformed_or_partial_response_envelope",
                                "path": str(response_path), "error_type": type(exc).__name__,
                                "sha256": digest(response_path)})
    if record is not None:
        raw = record.get("raw_response_text")
        if response is not None and raw != response.get("message", {}).get("content", ""):
            raise ValueError("Record raw text differs from response capture: " + str(folder))
        if record.get("response_complete") is True and (
                response is None or response.get("done_reason") != "stop"):
            raise ValueError("Record claims completion without the completed response capture")
        return raw, response, "record.raw_response_text", diagnostics
    if response is not None:
        return response.get("message", {}).get("content", ""), response, "response_capture_without_endpoint_record", diagnostics
    assembled = folder / "http_0001_generation/assembled_text.json"
    if assembled.is_file():
        try:
            value = read(assembled)
            if not isinstance(value, dict):
                raise ValueError("Malformed assembled text type")
            return value.get("content"), None, "assembled_partial_text_without_endpoint_record", diagnostics
        except (ValueError, TypeError, UnicodeError) as exc:
            diagnostics.append({"kind": "malformed_or_partial_assembled_text", "path": str(assembled),
                                "error_type": type(exc).__name__, "sha256": digest(assembled)})
    events = folder / "http_0001_generation/events.jsonl"
    if events.is_file():
        fragments = []
        for index, raw_line in enumerate(events.read_bytes().splitlines()):
            try:
                line = raw_line.decode("utf-8")
                event = json.loads(line)["event"]
                part = event.get("message", {}).get("content", "")
                if not isinstance(part, str):
                    break
                fragments.append(part)
            except (ValueError, KeyError, TypeError, UnicodeError):
                diagnostics.append({"kind": "partial_or_invalid_event_line", "path": str(events), "line_number": index + 1})
                break
        return "".join(fragments) or None, None, "concatenated_stored_event_fragments_without_endpoint_record", diagnostics
    return None, None, "no_response_material", diagnostics


def _elapsed_material(record):
    """Select a recorded duration; never substitute provider token timings.

    The current runner records supervisor elapsed time including child setup,
    metadata and rendering. Worker time has a narrower scope. The legacy
    top-level wall_seconds field is retained only as a documented fallback.
    None means unobserved, not a zero-duration endpoint.
    """
    transport = (record or {}).get("transport_result") or {}
    supervisor = transport.get("supervisor") or {}
    worker = supervisor.get("worker") or {}
    candidates = (
        (supervisor.get("elapsed_seconds"), "transport_result.supervisor.elapsed_seconds",
         supervisor.get("deadline_scope") or "supervisor_recorded_elapsed; cleanup and OS scheduling overhead may be excluded"),
        (worker.get("elapsed_seconds"), "transport_result.supervisor.worker.elapsed_seconds",
         "worker_recorded_elapsed; excludes supervisor setup and post-worker cleanup"),
        (transport.get("wall_seconds"), "transport_result.wall_seconds",
         "legacy top-level wall_seconds; producer did not record a more specific scope"),
    )
    for value, location, scope in candidates:
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("Invalid recorded elapsed time at " + location)
        return {"elapsed_seconds": value, "selected_record_field": location,
                "scope": scope, "observed_duration_fields": {
                    key: observed for observed, key, _ in candidates if observed is not None}}
    return {"elapsed_seconds": None, "selected_record_field": None,
            "scope": "unobserved; not inferred from timestamps or provider counters", "observed_duration_fields": {}}


def _load_endpoint(case, endpoint, case_root, summary, workspace_root):
    folder = case_root / endpoint
    record_path = folder / "record.json"
    record = read(record_path) if record_path.is_file() else None
    listed = [entry for entry in summary.get("endpoints", []) if entry.get("endpoint") == endpoint]
    if len(listed) > 1:
        raise ValueError("Duplicate endpoint in case summary")
    if listed and listed[0].get("record"):
        _validate_ref(listed[0]["record"], record_path, workspace_root)
    if record is not None:
        expected_stage = int(endpoint[-1]) if endpoint.startswith("stage") else 4
        if record.get("endpoint") != endpoint or record.get("stage") != expected_stage:
            raise ValueError("Endpoint/stage identity mismatch")
        visible = case["arm"] == "R1" or expected_stage == 4
        if record.get("institution_visible") is not visible:
            raise ValueError("Source exposure flag does not match the declared arm")
    raw, response, raw_origin, capture_diagnostics = _raw_material(folder, record)
    request_path = folder / "http_0001_generation/request.json"
    attempted = request_path.is_file()
    if attempted and record is not None:
        request = read(request_path)
        if record.get("request_body_sha256") != value_digest(request.get("body")):
            raise ValueError("Recorded request hash differs from captured generation body")
    if listed and listed[0].get("generation_attempted") is not attempted:
        raise ValueError("Recorded generation attempt disagrees with request artifact")
    if record is not None and record.get("response_complete") is True and not attempted:
        raise ValueError("Completed response has no generation request capture")
    visibility_path = folder / "visible_evidence_before_generation.json"
    captured_visibility = read(visibility_path) if visibility_path.is_file() else None
    if record is not None and captured_visibility is not None:
        if (record.get("visible_evidence_ids_before_generation") != captured_visibility.get("ids")
                or record.get("visible_calculator_facts_before_generation") != captured_visibility.get("calculator_facts")):
            raise ValueError("Record disagrees with captured pre-generation visibility")
    visible_ids = record.get("visible_evidence_ids_before_generation") if record else (captured_visibility or {}).get("ids")
    visible_facts = record.get("visible_calculator_facts_before_generation", []) if record else (captured_visibility or {}).get("calculator_facts", [])
    # A fully captured response remains completed even if a later cleanup fails.
    # The independent instrument incident is retained for readiness decisions.
    completed = bool(record and record.get("response_complete") is True and response and response.get("done_reason") == "stop")
    status = record.get("transport_status") if record else ("endpoint_record_missing" if folder.is_dir() else "endpoint_not_reached")
    if completed:
        attempt_status = "completed_response"
    elif not attempted:
        attempt_status = "not_attempted"
    elif status in ("case_timeout", "hard_deadline"):
        attempt_status = "timed_out"
    elif status == "cancelled":
        attempt_status = "interrupted"
    elif raw:
        attempt_status = "partial_response"
    else:
        attempt_status = "attempted_no_response"
    timing = _elapsed_material(record)
    metadata = {**case, "endpoint": endpoint, "current_candidate_id": endpoint,
                "attempted": attempted, "transport_completed": completed,
                "attempt_status": attempt_status, "transport_status": status,
                "termination_reason": status,
                "visible_evidence_ids": visible_ids,
                "calculator_facts": visible_facts,
                "elapsed_seconds": timing["elapsed_seconds"]}
    material = {"endpoint": endpoint, "stage": int(endpoint[-1]) if endpoint.startswith("stage") else 4,
                "record_ref": reference(record_path) if record_path.is_file() else None,
                "request_ref": reference(request_path) if request_path.is_file() else None,
                "response_ref": reference(folder / "http_0001_generation/response.json") if (folder / "http_0001_generation/response.json").is_file() else None,
                "visibility_ref": reference(visibility_path) if visibility_path.is_file() else None,
                "raw_text_origin": raw_origin, "recorded_at_utc": (record or {}).get("recorded_at_utc"),
                "timing_provenance": timing,
                "capture_diagnostics": capture_diagnostics,
                "attempted": attempted, "completed": completed, "transport_status": status,
                "raw_response_text": raw,
                "parsed_response_as_captured": (record or {}).get("parsed_response"),
                "feedback_as_recorded": (record or {}).get("feedback"),
                "visible_evidence_ids_before_generation": visible_ids,
                "visible_calculator_facts_before_generation": visible_facts,
                "automatic_semantic_assessment": None}
    return raw, metadata, material


def build_report(manifest_path, run_root, gold_path, *, workspace_root=ROOT):
    """Return an offline report and an unfilled reviewer worksheet; no writes."""
    manifest_path, run_root, gold_path = map(lambda p: Path(p).resolve(), (manifest_path, run_root, gold_path))
    if not run_root.is_dir():
        raise ValueError("Run artifact directory does not exist")
    manifest, market, registry, packets = _load_prepared(manifest_path)
    snapshot_path = run_root / "manifest_snapshot.json"
    if not snapshot_path.is_file() or read(snapshot_path) != manifest:
        raise ValueError("Run manifest snapshot differs from the supplied prepared manifest")
    expected_cases = {case["case_id"] for case in ROSTER}
    for request_path in run_root.rglob("request.json"):
        if request_path.parent.name.endswith("_generation"):
            parts = request_path.relative_to(run_root).parts
            if (len(parts) != 4 or parts[0] not in expected_cases or parts[1] not in ENDPOINTS
                    or parts[2] != "http_0001_generation"):
                raise ValueError("Unregistered generation request; cannot silently omit extra cases or calls")
    golds = _load_gold(gold_path)
    run_summary_path = run_root / "summary.json"
    run_summary = read(run_summary_path) if run_summary_path.is_file() else None
    if run_summary is not None and run_summary.get("planned_cases") != list(ROSTER):
        raise ValueError("Run summary roster differs from the fixed pilot")
    primary, auxiliary, materials, issues, summaries = [], [], [], [], []
    for case in ROSTER:
        folder = run_root / case["case_id"]
        summary_path = folder / "case_summary.json"
        summary = read(summary_path) if summary_path.is_file() else {}
        case_manifest_path = folder / "case_manifest.json"
        case_manifest = read(case_manifest_path) if case_manifest_path.is_file() else {}
        for obj in (summary, case_manifest):
            if obj and any(obj.get(key) != case[key] for key in ("case_id", "source_id", "arm", "split")):
                raise ValueError("Case metadata does not match the prespecified roster")
        if case_manifest.get("packet"):
            _validate_ref(case_manifest["packet"], manifest_path.parent / "packets" / (case["source_id"] + ".json"), workspace_root)
        request_count = sum((folder / endpoint / "http_0001_generation/request.json").is_file() for endpoint in ENDPOINTS)
        declared_count = summary.get("core_calls_attempted", 0) + summary.get("auxiliary_calls_attempted", 0)
        if declared_count > request_count:
            raise ValueError("Summary claims generation requests absent from the preserved artifacts")
        if summary and declared_count != request_count:
            issues.append({"case_id": case["case_id"], "kind": "summary_attempt_count_lags_preserved_requests",
                           "summary_attempt_count": declared_count, "captured_request_count": request_count})
        if folder.exists() and not summary:
            issues.append({"case_id": case["case_id"], "kind": "case_summary_missing_or_interrupted"})
        summaries.append({**case, "case_summary_ref": reference(summary_path) if summary else None,
                          "case_summary": summary or None, "captured_generation_request_count": request_count,
                          "system_integrity_incident": summary.get("system_integrity_incident"),
                          "source_inventory_human_review": "pending_not_inferred_from_this_loader"})
        endpoint_materials = []
        for endpoint in ENDPOINTS:
            raw, metadata, material = _load_endpoint(case, endpoint, folder, summary, workspace_root)
            metadata.update(workflow_generation_attempted=request_count > 0,
                            workflow_status=summary.get("status", "no_case_summary" if folder.exists() else "not_started"),
                            workflow_termination_reason=summary.get("error", summary.get("status")))
            material["case_id"] = case["case_id"]
            material["source_id"] = case["source_id"]
            material["arm"] = case["arm"]
            endpoint_materials.append(material)
            for diagnostic in material["capture_diagnostics"]:
                issues.append({"case_id": case["case_id"], "endpoint": endpoint, **diagnostic})
            if endpoint == "C0":
                primary.append(evaluate_case(raw, packets[case["source_id"]], golds[case["source_id"]], market, registry, metadata))
            elif endpoint in ("C1", "C2") and (material["record_ref"] or material["attempted"]):
                auxiliary.append(evaluate_case(raw, packets[case["source_id"]], golds[case["source_id"]], market, registry, metadata))
        if summary.get("primary_record"):
            _validate_ref(summary["primary_record"], folder / "C0/record.json", workspace_root)
        if summary.get("auxiliary_terminal_record"):
            terminals = [item for item in endpoint_materials if item["endpoint"] in ("C1", "C2") and item["record_ref"]]
            if not terminals:
                raise ValueError("Auxiliary terminal claimed without an auxiliary record")
            _validate_ref(summary["auxiliary_terminal_record"], folder / terminals[-1]["endpoint"] / "record.json", workspace_root)
        materials.extend(endpoint_materials)
    primary_bundle = evaluate_bundle(primary, list(SOURCES))
    now = datetime.now(timezone.utc).isoformat()
    provenance = {"prepared_manifest": reference(manifest_path), "run_manifest_snapshot": reference(snapshot_path),
                  "gold_annotations": reference(gold_path), "gold_access_role": "offline_evaluator_only",
                  "run_summary": reference(run_summary_path) if run_summary_path.is_file() else None,
                  "input_hashes_as_registered": manifest["input_hashes"],
                  "runtime_software_hashes_as_registered": manifest.get("software_hashes"),
                  "evaluator_software": [reference(Path(__file__)), reference(Path(__file__).with_name("evaluate_sector_v48.py"))],
                  "verification_scope": "Prepared inputs and recorded artifacts checked. Current runtime software need not equal old recorded bytes for read-only analysis; no retrospective execution attestation is claimed."}
    report = {"artifact_version": VERSION, "created_at_utc": now, "scope": "pilot_only_offline_analysis",
              "model_calls_by_this_evaluation": 0, "main_model_calls_by_this_evaluation": 0,
              "provenance": provenance, "primary_C0_bundle": primary_bundle,
              "primary_C0_cases": primary, "auxiliary_endpoint_cases": auxiliary,
              "auxiliary_policy": "Each attempted C1/C2 is separate. Terminal selection remains the frozen runner stop rule; never choose the best response or replace C0.",
              "case_execution_records": summaries, "artifact_issues": issues,
              "system_integrity_incidents_present": any(item["system_integrity_incident"] is True for item in summaries),
              "semantic_review_completed": False, "independent_human_review_completed": False,
              "strategic_preservation_verdict": None,
              "research_connection": "Inspect source judgment, interpretation, claimed adoption/departure, rationale and raw action under R1/R4. Arithmetic and label checks are supporting diagnostics; neither settles strategic preservation or harmful convergence.",
              "limits": ["Pilot development exposure prevents independent confirmation claims.",
                         "Missing or invalid C0 remains in the full four-case and 44-sector accounting.",
                         "Readable partial material can be reviewed, but does not receive completed-C0 factual credit.",
                         "A completed response can coexist with later infrastructure failure; readiness must review the retained incident.",
                         "No weighted composite, NLP claim extraction, investment-quality gold or automatic semantic verdict is produced."]}
    worksheet = {"artifact_version": VERSION, "created_at_utc": now,
                 "artifact_kind": "unfilled_evaluator_only_semantic_review_worksheet",
                 "review_status": "not_started", "reviewer_id": None, "reviewer_role": None,
                 "independence_from_generation": None, "independent_human_review_completed": False,
                 "protocol_path": "research/v48_evaluation_protocol_20261018.json",
                 "provenance": provenance, "primary_C0_reviews": [], "auxiliary_reviews": [],
                 "workflow_trace_materials": materials,
                 "instructions": ["Review C0 first. Earlier stages describe the path, not additional independent cases.",
                                  "Keep literal source/model statements separate from reviewer support or action-consistency judgments.",
                                  "Record exact source passage and response location for every judgment; copied ratings or resolving IDs are insufficient.",
                                  "A justified departure can preserve an evidence-aware decision process; do not force favorable source ratings into fixed numeric weights.",
                                  "Record uncertainty, missingness and noncomparability explicitly. No null field is a favorable verdict.",
                                  "Review each actual C1/C2 separately. Their extra computation cannot erase C0 outcomes.",
                                  "Verify numeric claims through manually transcribed full tuples and captured candidate lineage; no automatic free-text certification is supplied.",
                                  "Independent source review remains pending; assistant checks are not human approval."]}
    for key, cases in (("primary_C0_reviews", primary), ("auxiliary_reviews", auxiliary)):
        for result in cases:
            worksheet[key].append({"case_id": result["case_id"], "source_id": result["source_id"], "arm": result["arm"],
                                   "endpoint": result["endpoint"], "response_sha256": result["response_sha256"],
                                   "execution": result["execution"], "source_material_context": result["source_material_context"],
                                   **result["review_preparation"]})
    return report, worksheet


def write_report(manifest_path, run_root, gold_path, output, *, workspace_root=ROOT):
    output = Path(output).resolve()
    protected = (Path(manifest_path).resolve().parent, Path(run_root).resolve())
    if any(output.is_relative_to(path) for path in protected):
        raise ValueError("Evaluator-only gold/review output must be outside online/prepared directories")
    if output.exists():
        raise FileExistsError("Use a new versioned output directory; existing analysis is preserved")
    report, worksheet = build_report(manifest_path, run_root, gold_path, workspace_root=workspace_root)
    output.mkdir(parents=True, exist_ok=False)
    for filename, value in (("evaluation_report.json", report), ("semantic_review_worksheet.json", worksheet)):
        (output / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    receipt = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "model_calls": 0,
               "files": [reference(output / name) for name in ("evaluation_report.json", "semantic_review_worksheet.json")],
               "primary_planned_cases": 4, "primary_expected_sector_rows": 44,
               "independent_human_review_completed": False}
    (output / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--gold", default=str(ROOT / "data/sector_documents/evaluator_only/reference_annotations.jsonl"))
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    receipt = write_report(args.manifest, args.run_root, args.gold, args.output)
    print(json.dumps({"output": str(Path(args.output).resolve()), "model_calls": 0,
                      "receipt_sha256": digest(Path(args.output) / "receipt.json")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
