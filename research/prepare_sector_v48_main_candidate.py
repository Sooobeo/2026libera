"""Prepare a NON-EXECUTABLE v4.8 main-input candidate after three pilot audits.

Offline file packaging only. No transport, HTTP, process, registration, freeze,
or inference command is provided. Stage previews contain only authored payloads;
no future model response or calculator history is invented. A three-review
technical receipt binds implemented code; human source review and candidate-bound
main freeze/authorization remain separate and pending.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from sector_engine import SECTOR_CODES
from sector_response_schema import response_schema
from sector_v48_contract import build_system, stage_payload

ROOT = Path(__file__).resolve().parents[1]
VERSION = "v4.8-main-candidate-1"
MAIN_SOURCES = ("fidelity_q3_2026", "ubs_july_2026")
PILOT_SOURCES = ("fidelity_q2_2026", "ubs_june_2026")
ARMS = ("R1", "R4")
SHARED_INPUTS = ("market_input.json", "public_numeric_registry.json", "runtime.json", "prompt_contract.json")
PILOT_SOFTWARE = ("run_sector_v48.py", "sector_v48_transport.py", "sector_v48_contract.py",
                  "sector_response_schema.py", "sector_engine.py", "compact_sector_prompt.py",
                  "local_sector_single_case.py", "remote_sector_runtime.py", "benchmark_sector_latency.py",
                  "probe_ollama_runtime.py", "run_sector_workflow.py")
MAIN_SOFTWARE = ("run_sector_v48_main.py", "sector_v48_main_gate.py", "sector_v48_main_transport.py",
                 "sector_v48_main_awake.py", "sector_v48_contract.py", "sector_response_schema.py",
                 "sector_engine.py", "compact_sector_prompt.py", "local_sector_single_case.py",
                 "remote_sector_runtime.py", "benchmark_sector_latency.py", "probe_ollama_runtime.py",
                 "run_sector_workflow.py")
MAIN_EVALUATOR_SOFTWARE = ("evaluate_sector_v48_main_artifacts.py", "render_v48_main_review_packet.py",
                          "evaluate_sector_v48_artifacts.py", "evaluate_sector_v48.py", "render_v48_review_packet.py",
                          "sector_engine.py", "sector_response_schema.py", "audit_v48_main_round1.py",
                          "audit_v48_main_round2.py")
EVALUATOR_CRITERIA = {
    "evaluation_protocol": "research/v48_evaluation_protocol_20261018.json",
    "review_template": "research/v48_review_template_20261018.json",
    "source_comparison": "research/evaluator_only/v48_source_comparison_20261018.json",
}


def roster(sources, split):
    return [{"case_id": source + "__" + arm, "source_id": source, "arm": arm, "split": split}
            for source in sources for arm in ARMS]


def read(path):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("Duplicate JSON key: " + key)
            value[key] = item
        return value
    def invalid(value):
        raise ValueError("Nonfinite JSON value: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=pairs, parse_constant=invalid)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve(path, root):
    value = Path(path)
    return value.resolve() if value.is_absolute() else (Path(root) / value).resolve()


def below(folder, relative):
    folder = Path(folder).resolve()
    target = (folder / relative).resolve()
    if not target.is_relative_to(folder):
        raise ValueError("Path escapes declared input root: " + str(relative))
    return target


def ref(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": digest(path)}


class Inputs:
    """Keep the exact bytes consulted and recheck before any candidate is written."""
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.refs = {}

    def record(self, path, expected=None):
        path = Path(path).resolve()
        current = ref(path)
        if expected is not None and current["sha256"] != expected:
            raise ValueError("Input hash mismatch: " + str(path))
        if str(path) in self.refs and self.refs[str(path)] != current:
            raise ValueError("Input changed during preparation: " + str(path))
        self.refs[str(path)] = current
        return path

    def reference(self, value, expected_path=None):
        if not isinstance(value, dict) or not isinstance(value.get("path"), str) or not isinstance(value.get("sha256"), str):
            raise ValueError("A path and SHA-256 reference are required")
        path = resolve(value["path"], self.root)
        if expected_path is not None and path != Path(expected_path).resolve():
            raise ValueError("Reference points to another artifact: " + str(path))
        return self.record(path, value["sha256"])

    def json(self, path, expected=None):
        return read(self.record(path, expected))

    def stable(self):
        for value in self.refs.values():
            if digest(value["path"]) != value["sha256"]:
                raise ValueError("Input changed during preparation: " + value["path"])


def verify_upstream(inputs, manifest_path, registration_path, evaluation_path, audit_paths):
    """Bind all three PASS reviews to one completed pilot, allowing model failures."""
    manifest_path, registration_path, evaluation_path = map(Path, (manifest_path, registration_path, evaluation_path))
    manifest = inputs.json(manifest_path)
    registration = inputs.json(registration_path)
    evaluation = inputs.json(evaluation_path)
    expected_roster = roster(PILOT_SOURCES, "pilot")
    if (manifest.get("protocol_version") != "4.8" or manifest.get("scope") != "all_four_fixed_pilot_cases_only"
            or manifest.get("roster") != expected_roster or manifest.get("main_authorized") is not False
            or manifest.get("main_frozen") is not False):
        raise ValueError("Expected the fixed v4.8 pilot manifest")
    expected_names = set(SHARED_INPUTS) | {"packets/" + source + ".json" for source in PILOT_SOURCES}
    expected_names |= {f"schemas/{arm}_stage{stage}.json" for arm in ARMS for stage in range(1, 5)}
    if set(manifest.get("input_hashes", {})) != expected_names or set(manifest.get("software_hashes", {})) != set(PILOT_SOFTWARE):
        raise ValueError("Incomplete registered pilot input/software inventory")
    for name, sha in manifest["input_hashes"].items():
        inputs.record(below(manifest_path.parent, name), sha)
    for name, sha in manifest["software_hashes"].items():
        inputs.record(below(inputs.root / "research", name), sha)
    if not manifest.get("design_references"):
        raise ValueError("Pilot design references missing")
    for value in manifest["design_references"]:
        inputs.reference(value)
    inputs.reference(registration.get("manifest"), manifest_path)
    if (registration.get("protocol_version") != "4.8" or registration.get("roster") != expected_roster
            or registration.get("main_authorized") is not False or len(registration.get("reviews", [])) != 3):
        raise ValueError("Pilot registration does not match the fixed roster")
    for number, value in enumerate(registration["reviews"], 1):
        reviewed = read(inputs.reference(value))
        if reviewed.get("round") != number or reviewed.get("status") != "PASS" or reviewed.get("manifest_sha256") != digest(manifest_path):
            raise ValueError("Pilot implementation review is not bound to this manifest")
    provenance = evaluation.get("provenance", {})
    inputs.reference(provenance.get("prepared_manifest"), manifest_path)
    summary_path = inputs.reference(provenance.get("run_summary"))
    run_root = summary_path.parent
    if summary_path.name != "summary.json":
        raise ValueError("Unexpected pilot summary location")
    snapshot_path = inputs.reference(provenance.get("run_manifest_snapshot"), run_root / "manifest_snapshot.json")
    if read(snapshot_path) != manifest or inputs.json(run_root / "registration_snapshot.json") != registration:
        raise ValueError("Pilot snapshots differ from reviewed inputs")
    summary = read(summary_path)
    if (summary.get("status") != "all_planned_cases_accounted" or summary.get("planned_cases") != expected_roster
            or summary.get("main_model_calls") != 0 or summary.get("main_frozen") is not False
            or summary.get("human_review_completed") is not False):
        raise ValueError("Pilot accounting is incomplete or reporting states differ")
    bundle = evaluation.get("primary_C0_bundle", {})
    if (evaluation.get("scope") != "pilot_only_offline_analysis" or not isinstance(evaluation.get("artifact_issues"), list)
            or evaluation.get("system_integrity_incidents_present") is not False
            or evaluation.get("main_model_calls_by_this_evaluation") != 0
            or bundle.get("planned_case_count") != 4 or bundle.get("expected_sector_count") != 44):
        raise ValueError("Pilot evaluation is unresolved or has another denominator")
    if len(audit_paths) != 3:
        raise ValueError("Exactly three post-pilot audit files are required")
    audits = [inputs.json(path) for path in audit_paths]
    for number, audit in enumerate(audits, 1):
        if audit.get("round") != number or audit.get("status") != "PASS":
            raise ValueError("Ordered post-pilot rounds 1, 2, 3 must all PASS")
    first = audits[0]
    inputs.reference(first.get("manifest"), manifest_path)
    inputs.reference(first.get("registration"), registration_path)
    if resolve(first.get("run_root", ""), inputs.root) != run_root:
        raise ValueError("Round 1 audited another run")
    inventory = first.get("artifact_inventory", [])
    captured = set()
    for value in inventory:
        path = inputs.reference(value)
        if not path.is_relative_to(run_root) or path in captured:
            raise ValueError("Invalid or duplicate round-1 run inventory path")
        captured.add(path)
    if captured != {p.resolve() for p in run_root.rglob("*") if p.is_file()}:
        raise ValueError("Round-1 inventory does not match all current pilot artifacts")
    for audit in audits[1:]:
        provenance = audit.get("provenance", {})
        inputs.reference(provenance.get("manifest"), manifest_path)
        inputs.reference(provenance.get("evaluation"), evaluation_path)
        if "run_summary" in provenance:
            inputs.reference(provenance["run_summary"], summary_path)
    return manifest, summary, run_root, evaluation


def main_packets(inputs, documents):
    """Validate packaged main inputs and pinned original PDFs, without reading gold."""
    documents = Path(documents).resolve()
    verification = inputs.json(documents / "verification.json")
    manifest_hash = verification.get("artifact_sha256", {}).get("source_manifest.json")
    if not isinstance(manifest_hash, str):
        raise ValueError("Original document manifest hash is missing")
    source_manifest = inputs.json(documents / "source_manifest.json", manifest_hash)
    if verification.get("all_mechanical_checks_passed") is not True:
        raise ValueError("Document packaging has not passed its recorded checks")
    selected = [item for item in source_manifest.get("sources", []) if item.get("source_id") in MAIN_SOURCES]
    if len(selected) != 2 or {item["source_id"] for item in selected} != set(MAIN_SOURCES):
        raise ValueError("Exactly two pinned main sources are required")
    packets, originals = {}, []
    for source in MAIN_SOURCES:
        relative = "packets/main/" + source + ".json"
        expected = verification.get("artifact_sha256", {}).get(relative)
        if not isinstance(expected, str):
            raise ValueError("Main packet hash is missing")
        packet = inputs.json(documents / relative, expected)
        item = next(item for item in selected if item["source_id"] == source)
        if (packet.get("source_id") != source or packet.get("split") != "main" or item.get("split") != "main"
                or [row.get("sector_code") for row in packet.get("sectors", [])] != list(SECTOR_CODES)
                or packet.get("numeric_target_weights_published_in_selected_section") is not False
                or packet.get("dates") != item.get("dates") or packet.get("source_url") != item.get("url")):
            raise ValueError("Main source identity, scope or original metadata mismatch")
        if not packet.get("evidence_passages") or any(
                row.get("source_id") != source or not row.get("evidence_id", "").startswith(source + ":")
                for row in packet["evidence_passages"]):
            raise ValueError("Main packet evidence source mismatch")
        original = inputs.reference(item.get("cache"))
        originals.append({"source_id": source, "original_pdf": ref(original),
                          "recorded_human_review_status": item.get("human_review_status", "unknown"),
                          "known_source_issues": item.get("known_source_issues", [])})
        packets[source] = packet
    return packets, originals


def preview_payloads(packets, market, registry):
    previews, checks = {}, []
    common = {}
    for case in roster(MAIN_SOURCES, "main"):
        history = []
        for stage in range(1, 5):
            payload = stage_payload(stage, case["arm"], packets[case["source_id"]], market, registry)
            visible = case["arm"] == "R1" or stage == 4
            onset = stage == (1 if case["arm"] == "R1" else 4)
            if ("institution_document" in payload) != onset or payload["response_schema"] != response_schema(stage, visible):
                raise ValueError("Source onset or stage schema differs from frozen v4.8")
            history.append(payload)
            if case["arm"] == "R4" and stage < 4 and any("institution_document" in item for item in history):
                raise ValueError("Assigned institution appears before R4 stage 4")
            invariant = copy.deepcopy(payload)
            invariant.pop("institution_document", None)
            invariant.pop("response_schema", None)  # Visibility is the declared treatment-dependent schema difference.
            if stage in common and invariant != common[stage]:
                raise ValueError("Non-treatment stage conditions differ across cases")
            common[stage] = invariant
            name = f"previews/{case['case_id']}/stage{stage}_payload.json"
            previews[name] = encoded(payload)
        checks.append({"case_id": case["case_id"], "onset_stage": 1 if case["arm"] == "R1" else 4,
                       "authored_payloads_checked": 4, "future_assistant_or_calculator_history": "not_created"})
    return previews, checks


def evaluator_materials(inputs, documents, prior):
    """Pin offline criteria bytes without parsing annotations or exposing them online."""
    verification_path = Path(documents) / "verification.json"
    verification = inputs.json(verification_path)
    expected = verification.get("artifact_sha256", {}).get("evaluator_only/reference_annotations.jsonl")
    if (not isinstance(expected, str) or len(expected) != 64
            or any(char not in "0123456789abcdef" for char in expected)):
        raise ValueError("Pinned reference annotation SHA-256 is required")
    gold = inputs.record(Path(documents) / "evaluator_only/reference_annotations.jsonl", expected)
    handoff_path = inputs.root / "research/v48_handoff_20261018.json"
    matches = [item for item in prior.get("design_references", [])
               if isinstance(item, dict) and isinstance(item.get("path"), str)
               and resolve(item["path"], inputs.root) == handoff_path]
    if len(matches) != 1:
        raise ValueError("Pilot-pinned v4.8 design handoff is required for evaluation criteria")
    handoff = inputs.json(inputs.reference(matches[0], handoff_path))
    delivered = handoff.get("delivered_artifacts", [])
    result = {"reference_annotations": ref(gold), "source_verification": ref(verification_path),
              "design_handoff": ref(handoff_path)}
    for key, relative in EVALUATOR_CRITERIA.items():
        path = inputs.root / relative
        matches = [item for item in delivered if isinstance(item, dict) and isinstance(item.get("path"), str)
                   and resolve(item["path"], inputs.root) == path]
        if len(matches) != 1:
            raise ValueError("Design handoff does not pin evaluation material: " + key)
        result[key] = ref(inputs.reference(matches[0], path))
    return result


def verify_technical_receipt(inputs, path):
    """Bind three technical reviews without treating them as main approval."""
    path = Path(path).resolve()
    receipt = inputs.json(path)
    if (receipt.get('artifact_kind') != 'v4.8_main_technical_three_review_receipt'
            or receipt.get('status') != 'PASS' or receipt.get('candidate_bound') is not False
            or receipt.get('independent_human_review_completed') is not False
            or any(type(receipt.get(k)) is not int or receipt[k] != 0 for k in ('model_calls', 'main_model_calls'))):
        raise ValueError('Completed non-authorizing main technical review receipt required')
    for key, names in (('software_hashes', MAIN_SOFTWARE), ('evaluator_software_hashes', MAIN_EVALUATOR_SOFTWARE)):
        hashes = receipt.get(key)
        if not isinstance(hashes, dict) or set(hashes) != set(names):
            raise ValueError('Technical review software inventory mismatch: ' + key)
        for name, expected in hashes.items():
            if (not isinstance(expected, str) or len(expected) != 64
                    or any(char not in '0123456789abcdef' for char in expected)):
                raise ValueError('Technical review requires a lowercase SHA-256: ' + name)
            inputs.record(inputs.root / 'research' / name, expected)
    reviews = receipt.get('reviews')
    if not isinstance(reviews, list) or len(reviews) != 3:
        raise ValueError('Exactly three main technical reviews required')
    seen = set()
    for number, item in enumerate(reviews, 1):
        review_path = inputs.reference(item)
        if review_path in seen:
            raise ValueError('Technical review rounds must be separate records')
        seen.add(review_path); review = inputs.json(review_path)
        if (type(review.get('round')) is not int or review['round'] != number or review.get('status') != 'PASS'
                or any(review.get(key) != receipt[key] for key in ('software_hashes', 'evaluator_software_hashes'))):
            raise ValueError('Technical reviews must PASS in order and bind identical code inventories')
    return receipt


def prepare(pilot_manifest, pilot_registration, evaluation, audits, output, *, technical_review_receipt, workspace_root=ROOT, documents=None):
    inputs = Inputs(workspace_root)
    manifest_path = Path(pilot_manifest).resolve()
    output = Path(output).resolve()
    documents = Path(documents or inputs.root / "data/sector_documents").resolve()
    if output.exists():
        raise FileExistsError("Candidate output must be a new directory")
    prior, summary, run_root, prior_evaluation = verify_upstream(inputs, manifest_path, pilot_registration, evaluation, audits)
    technical = verify_technical_receipt(inputs, technical_review_receipt)
    protected = (manifest_path.parent, run_root, documents)
    if any(output.is_relative_to(folder) or folder.is_relative_to(output) for folder in protected):
        raise ValueError("Candidate must be separate from pilot and original document directories")
    packets, originals = main_packets(inputs, documents)
    evaluation_material_refs = evaluator_materials(inputs, documents, prior)
    shared = {name: read(manifest_path.parent / name) for name in SHARED_INPUTS}
    registry, market = shared["public_numeric_registry.json"], shared["market_input.json"]
    if registry.get("source", {}).get("sha256") != digest(manifest_path.parent / "market_input.json"):
        raise ValueError("Public numerical registry points to another market input")
    files = {name: (manifest_path.parent / name).read_bytes() for name in SHARED_INPUTS}
    for source in MAIN_SOURCES:
        files["packets/" + source + ".json"] = (documents / "packets/main" / (source + ".json")).read_bytes()
    for arm in ARMS:
        for stage in range(1, 5):
            files[f"schemas/{arm}_stage{stage}.json"] = encoded(response_schema(stage, arm == "R1" or stage == 4))
    previews, preview_checks = preview_payloads(packets, market, registry)
    files.update(previews)
    files["system_instruction.txt"] = build_system(shared["prompt_contract.json"]).encode("utf-8")
    requirements = {
        "status": "technical_code_reviewed_candidate_source_review_and_execution_gate_pending", "main_runner_implemented": True,
        "main_artifact_evaluator_implemented": True, "main_independent_audit_adapters_implemented": [1, 2],
        "main_registration_or_freeze_available": False,
        "required_followup": [
            "Finish independent human pre-generation source meaning review with reviewer, exact evidence, unresolved limits and date; this is distinct from later semantic assessment of model responses.",
            "Bind the already technically reviewed main coordinator, gate, transport and temporary awake helper to this candidate and exact future run root; no main run is authorized here.",
            "Bind the technically reviewed main artifact loader, renderer and independent round1/round2 auditors. Complete three separate candidate-bound technical/contract/topic review records before execution, and three post-run review rounds on actual outputs later.",
            "Bind a full executable and evaluator software inventory, original source versions, reviewed inputs and criteria before any main response; this candidate has no executable registration.",
            "Verify complete actual history and feedback, source onset, first C0, separate eligible C1/C2, no hidden evaluator inputs, raw failure preservation and full 4-case/44-sector accounting.",
            "Keep instrument validity separate from model outcomes; no valid-allocation minimum, strategic target weights, label-equivalence mapping or favorable-result gate is introduced.",
            "Record any changes justified by pilot findings as a new version before main; do not tune to main annotations. Obtain main execution authorization separately from this non-executable preparation.",
        ],
        "preview_limit": "Each file is only that stage's authored task payload, not a complete conversation or sendable API request. Later actual assistant outputs and calculator feedback are unknown and deliberately absent.",
        "source_boundary": "Shared market/baseline provenance may name Fidelity Q3 for every case. That common, declared provenance is not assignment of the case-specific institution document; check authored institution_document placement and invariant common input, not a substring blacklist.",
        "evaluation_material_boundary": "The candidate pins annotation, protocol, blank review template and source-comparison metadata before main. These files are evaluator-only, absent from the 32 online input files and all prompts. The online gate validates reference metadata only; offline evaluation must verify exact referenced bytes and the supplied annotation path before scoring.",
        "topic": "Public source judgment -> interpretation and reasons -> actual proposed weights; labels and arithmetic remain supporting diagnostics.",
        "limits": ["Same two institutions and similar documents are not independent held-out institution replication.",
                   "Mixed publication/view dates and current-vintage adjusted prices form retrospective reasoning cases, not a historical tradable information set.",
                   "Fidelity Q3's printed 6/31/26 is retained unresolved; no invented normalized date.",
                   "No source annotations, independent human conclusions, responses, strategy score or actual main result are manufactured."],
    }
    files["remaining_requirements.json"] = encoded(requirements)
    inputs.record(Path(__file__))
    candidate = {"candidate_version": VERSION, "protocol_version": "4.8",
        "scope": "offline_main_input_candidate_not_execution_registration", "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "main_authorized": False, "main_frozen": False, "human_review_completed": False,
        "human_review_status": "pending", "main_runner_implemented": True, "main_artifact_evaluator_implemented": True,
        "main_independent_audit_adapters_implemented": [1, 2],
        "technical_review": {"receipt": ref(technical_review_receipt), "candidate_bound": False,
            "software_hashes": technical["software_hashes"], "evaluator_software_hashes": technical["evaluator_software_hashes"],
            "reviews": technical["reviews"], "main_authorization_created": False},
        "evaluator_material_refs": evaluation_material_refs,
        "roster": roster(MAIN_SOURCES, "main"), "planned_case_count": 4, "expected_sector_count": 44,
        "planned_core_calls_if_later_authorized": 16, "maximum_auxiliary_calls_if_later_authorized": 8,
        "model_calls_by_preparation": 0, "main_model_calls": 0, "actual_main_responses": 0,
        "prior_pilot": {"manifest": ref(manifest_path), "registration": ref(pilot_registration), "evaluation": ref(evaluation),
                        "run_summary": ref(run_root / "summary.json"), "postpilot_reviews": [ref(p) for p in audits],
                        "accounting_status": summary["status"], "model_success_required": False,
                        "retained_evaluation_artifact_issues": prior_evaluation["artifact_issues"],
                        "issue_policy": "Captured partial-output diagnostics remain visible; three PASS audits and absence of a system-integrity incident gate preparation, not absence of model errors or all capture diagnostics."},
        "input_provenance": sorted(inputs.refs.values(), key=lambda value: value["path"]),
        "original_documents": originals, "preview_checks": preview_checks,
        "inherited_pilot_software_hashes_for_traceability_only": prior["software_hashes"],
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
        "remaining_requirements": requirements,
        "authorization_boundary": "This artifact neither freezes nor authorizes main execution. It has no model/API/runner entrypoint."}
    files["manifest.json"] = encoded(candidate)
    inputs.stable()
    output.mkdir(parents=True, exist_ok=False)
    for name, data in sorted(files.items()):
        target = below(output, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(data)
    receipt = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "candidate_version": VERSION,
               "status": "offline_candidate_created_not_main_ready", "model_calls": 0, "main_authorized": False,
               "main_frozen": False, "human_review_completed": False, "builder": ref(__file__),
               "inputs": candidate["input_provenance"], "outputs": [ref(output / name) for name in sorted(files)]}
    with (output / "preparation_receipt.json").open("xb") as handle:
        handle.write(encoded(receipt))
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("pilot-manifest", "pilot-registration", "evaluation", "technical-review-receipt", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--audit", action="append", required=True, type=Path)
    args = parser.parse_args(argv)
    result = prepare(args.pilot_manifest, args.pilot_registration, args.evaluation, args.audit, args.output, technical_review_receipt=args.technical_review_receipt)
    print(json.dumps({"status": result["status"], "output": str(args.output.resolve()), "model_calls": 0,
                      "main_authorized": False, "main_frozen": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
