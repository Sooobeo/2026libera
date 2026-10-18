"""Read-only candidate-specific v4.8 main preparation audit.

No model, network, subprocess, approval, freeze or source-review operation is
available. A PASS concerns a still-unapproved candidate's recorded inputs and
previews, not empirical results, human identity or permission to execute.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

from sector_v48_contract import build_system, stage_payload
from sector_response_schema import response_schema
from sector_engine import SECTOR_CODES

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("fidelity_q3_2026", "ubs_july_2026")
ARMS = ("R1", "R4")
SHARED = ("market_input.json", "public_numeric_registry.json", "runtime.json", "prompt_contract.json")
SOFTWARE = ("run_sector_v48_main.py", "sector_v48_main_gate.py", "sector_v48_main_transport.py",
            "sector_v48_main_awake.py", "sector_v48_contract.py", "sector_response_schema.py", "sector_engine.py",
            "compact_sector_prompt.py", "local_sector_single_case.py", "remote_sector_runtime.py",
            "benchmark_sector_latency.py", "probe_ollama_runtime.py", "run_sector_workflow.py")
EVALUATORS = ("evaluate_sector_v48_main_artifacts.py", "render_v48_main_review_packet.py",
              "evaluate_sector_v48_artifacts.py", "evaluate_sector_v48.py", "render_v48_review_packet.py",
              "sector_engine.py", "sector_response_schema.py", "audit_v48_main_round1.py", "audit_v48_main_round2.py")
MATERIALS = {"reference_annotations", "source_verification", "design_handoff", "evaluation_protocol",
             "review_template", "source_comparison"}


def roster():
    return [{"case_id": source + "__" + arm, "source_id": source, "arm": arm, "split": "main"}
            for source in SOURCES for arm in ARMS]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reference(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": digest(path)}


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("Nonfinite JSON number: " + value)
    def number(value):
        result = float(value)
        if not math.isfinite(result):
            invalid(value)
        return result
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=pairs,
                      parse_constant=invalid, parse_float=number)


def require(condition, message):
    if not condition:
        raise ValueError(message)


class Audit:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.rows = []
        self.seen = {}

    def check(self, name, function):
        try:
            value = function()
            self.rows.append({"id": name, "passed": True})
            return value
        except Exception as exc:
            self.rows.append({"id": name, "passed": False, "error_type": type(exc).__name__, "error": str(exc)})
            return None

    def file(self, path, expected=None):
        path = Path(path).resolve()
        current = digest(path)
        require(expected is None or current == expected, "Changed input: " + str(path))
        require(path not in self.seen or self.seen[path] == current, "Changed during audit: " + str(path))
        self.seen[path] = current
        return path

    def ref(self, value):
        require(isinstance(value, dict) and isinstance(value.get("path"), str)
                and isinstance(value.get("sha256"), str)
                and re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is not None, "Invalid path/SHA reference")
        path = Path(value["path"])
        if not path.is_absolute():
            path = self.root / path
        return self.file(path, value["sha256"])

    def json(self, path):
        return read(self.file(path))

    def stable(self):
        require(all(digest(path) == expected for path, expected in self.seen.items()), "Inputs changed during audit")


def audit(manifest_path, *, workspace_root=ROOT, synthetic=False):
    checker = Audit(workspace_root)
    manifest_path = Path(manifest_path).resolve()
    folder = manifest_path.parent
    manifest = checker.json(manifest_path)
    expected_roster = roster()
    names = set(SHARED) | {"system_instruction.txt", "remaining_requirements.json"}
    names |= {"packets/" + source + ".json" for source in SOURCES}
    names |= {f"schemas/{arm}_stage{stage}.json" for arm in ARMS for stage in range(1, 5)}
    names |= {f"previews/{case['case_id']}/stage{stage}_payload.json" for case in expected_roster for stage in range(1, 5)}

    def states():
        require(manifest.get("candidate_version") == "v4.8-main-candidate-1" and manifest.get("protocol_version") == "4.8"
                and manifest.get("scope") == "offline_main_input_candidate_not_execution_registration", "Candidate scope differs")
        require(all(manifest.get(key) is False for key in ("main_authorized", "main_frozen", "human_review_completed"))
                and manifest.get("human_review_status") == "pending", "Candidate must remain unapproved and human-pending")
        require(all(type(manifest.get(key)) is int and manifest[key] == 0
                    for key in ("model_calls_by_preparation", "main_model_calls", "actual_main_responses")), "Preparation counters differ")
        require(manifest.get("roster") == expected_roster and manifest.get("planned_case_count") == 4
                and manifest.get("expected_sector_count") == 44 and manifest.get("planned_core_calls_if_later_authorized") == 16
                and manifest.get("maximum_auxiliary_calls_if_later_authorized") == 8, "Fixed main case policy differs")
    checker.check("unapproved_four_case_state", states)

    def public_inventory():
        hashes = manifest.get("files")
        require(isinstance(hashes, dict) and set(hashes) == names and len(names) == 32, "Expected exactly 32 public files")
        for name in sorted(names):
            checker.ref({"path": str(folder / name), "sha256": hashes[name]})
        require({p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
                == names | {"manifest.json", "preparation_receipt.json"}, "Unexpected or missing candidate artifact")
    checker.check("exact_public_file_inventory", public_inventory)

    def receipt():
        value = checker.json(folder / "preparation_receipt.json")
        require(value.get("status") == "offline_candidate_created_not_main_ready"
                and value.get("candidate_version") == manifest.get("candidate_version")
                and type(value.get("model_calls")) is int and value["model_calls"] == 0
                and all(value.get(key) is False for key in ("main_authorized", "main_frozen", "human_review_completed")), "Preparation receipt state differs")
        require(value.get("inputs") == manifest.get("input_provenance"), "Preparation receipt input inventory differs")
        paths = [checker.ref(item) for item in value["inputs"]]
        require(len(paths) == len(set(paths)), "Duplicate input reference")
        outputs = [checker.ref(item) for item in value.get("outputs", [])]
        require(len(outputs) == 33 and set(outputs) == {(folder / name).resolve() for name in names | {"manifest.json"}},
                "Preparation receipt must bind all 33 outputs")
        require(checker.ref(value.get("builder")) == checker.root / "research/prepare_sector_v48_main_candidate.py",
                "Unexpected preparation builder")
    checker.check("preparation_receipt_inputs_and_outputs", receipt)

    def pilot_and_shared():
        prior = manifest["prior_pilot"]
        pilot_path = checker.ref(prior["manifest"])
        pilot = checker.json(pilot_path)
        registration_path = checker.ref(prior["registration"])
        evaluation_path = checker.ref(prior["evaluation"])
        summary_path = checker.ref(prior["run_summary"])
        registration = checker.json(registration_path); evaluation = checker.json(evaluation_path)
        summary = checker.json(summary_path)
        require(checker.ref(registration["manifest"]) == pilot_path
                and checker.ref(evaluation["provenance"]["prepared_manifest"]) == pilot_path
                and checker.ref(evaluation["provenance"]["run_summary"]) == summary_path,
                "Prior registration/evaluation refer to another pilot")
        require(evaluation.get("system_integrity_incidents_present") is False
                and evaluation.get("primary_C0_bundle", {}).get("planned_case_count") == 4
                and evaluation.get("primary_C0_bundle", {}).get("expected_sector_count") == 44,
                "Prior evaluation has an incident or another denominator")
        require(summary.get("status") == "all_planned_cases_accounted" and summary.get("main_model_calls") == 0,
                "Prior pilot not fully accounted")
        reviews = prior.get("postpilot_reviews", [])
        require(len(reviews) == 3, "Three post-pilot reviews required")
        paths = []
        for number, item in enumerate(reviews, 1):
            path = checker.ref(item); paths.append(path); review = checker.json(path)
            require(type(review.get("round")) is int and review["round"] == number and review.get("status") == "PASS",
                    "Prior pilot reviews must PASS in order")
            if number == 1:
                run_root = Path(review["run_root"])
                if not run_root.is_absolute():
                    run_root = checker.root / run_root
                require(checker.ref(review["manifest"]) == pilot_path
                        and checker.ref(review["registration"]) == registration_path
                        and run_root.resolve() == summary_path.parent, "Round1 audited another pilot")
            else:
                require(checker.ref(review["provenance"]["manifest"]) == pilot_path
                        and checker.ref(review["provenance"]["evaluation"]) == evaluation_path,
                        "Later pilot review used another evaluation")
                if number == 3 or "run_summary" in review["provenance"]:
                    require(checker.ref(review["provenance"]["run_summary"]) == summary_path,
                            "Later pilot review refers to another run summary")
        require(len(set(paths)) == 3 and prior.get("model_success_required") is False, "Prior model-success gate or duplicate reviews")
        for name in SHARED:
            original = checker.ref({"path": str(pilot_path.parent / name), "sha256": pilot["input_hashes"][name]})
            require((folder / name).read_bytes() == original.read_bytes(), "Shared input differs from reviewed pilot: " + name)
        registry = checker.json(folder / "public_numeric_registry.json")
        require(registry.get("source", {}).get("sha256") == digest(folder / "market_input.json"), "Registry market binding differs")
    checker.check("pilot_lineage_and_shared_four_bytes", pilot_and_shared)

    def evaluation_and_sources():
        refs = manifest.get("evaluator_material_refs")
        require(isinstance(refs, dict) and set(refs) == MATERIALS, "Six offline material references required")
        paths = {key: checker.ref(value) for key, value in refs.items()}
        require(all(Path(value["path"]).is_absolute() for value in refs.values()), "Offline refs must use absolute paths")
        verification = checker.json(paths["source_verification"])
        pinned = verification["artifact_sha256"]
        require(verification.get("all_mechanical_checks_passed") is True
                and pinned.get("evaluator_only/reference_annotations.jsonl") == refs["reference_annotations"]["sha256"],
                "Annotation bytes are not pinned to original source verification")
        docs = paths["source_verification"].parent
        source_manifest = checker.json(checker.ref({"path": str(docs / "source_manifest.json"), "sha256": pinned["source_manifest.json"]}))
        originals = manifest.get("original_documents", [])
        require(len(originals) == 2 and {row["source_id"] for row in originals} == set(SOURCES), "Two originals required")
        for source in SOURCES:
            relative = "packets/main/" + source + ".json"
            original_packet = checker.ref({"path": str(docs / relative), "sha256": pinned[relative]})
            require((folder / "packets" / (source + ".json")).read_bytes() == original_packet.read_bytes(), "Main packet bytes differ")
            packet = checker.json(original_packet)
            rows = [row for row in source_manifest["sources"] if row.get("source_id") == source]
            require(len(rows) == 1, "Source manifest identity is ambiguous")
            row = rows[0]; original = next(item for item in originals if item["source_id"] == source)
            require(checker.ref(original["original_pdf"]) == checker.ref(row["cache"])
                    and original["known_source_issues"] == row.get("known_source_issues", []), "Original PDF or known issues differ")
            require(packet.get("source_id") == source and packet.get("split") == row.get("split") == "main"
                    and packet.get("dates") == row.get("dates") and packet.get("source_url") == row.get("url")
                    and packet.get("numeric_target_weights_published_in_selected_section") is False
                    and [item.get("sector_code") for item in packet.get("sectors", [])] == list(SECTOR_CODES), "Packet scope/metadata differs")
        handoff = checker.json(paths["design_handoff"])
        prior = checker.json(checker.ref(manifest["prior_pilot"]["manifest"]))
        require(sum(checker.ref(item) == paths["design_handoff"] for item in prior["design_references"]) == 1,
                "Evaluation handoff is not pinned by the original pilot")
        for key in ("evaluation_protocol", "review_template", "source_comparison"):
            matches = [item for item in handoff.get("delivered_artifacts", [])
                       if (checker.root / item["path"]).resolve() == paths[key]]
            require(len(matches) == 1 and matches[0]["sha256"] == refs[key]["sha256"], "Criterion differs from frozen handoff")
    checker.check("two_source_and_six_evaluation_material_lineage", evaluation_and_sources)

    def technical_reviews():
        technical = manifest["technical_review"]
        require(technical.get("candidate_bound") is False and technical.get("main_authorization_created") is False,
                "Technical receipt must not authorize this candidate")
        value = checker.json(checker.ref(technical["receipt"]))
        require(value.get("artifact_kind") == "v4.8_main_technical_three_review_receipt" and value.get("status") == "PASS"
                and value.get("candidate_bound") is False and value.get("independent_human_review_completed") is False
                and all(type(value.get(key)) is int and value[key] == 0 for key in ("model_calls", "main_model_calls")), "Technical receipt scope differs")
        for key, expected_names in (("software_hashes", SOFTWARE), ("evaluator_software_hashes", EVALUATORS)):
            hashes = technical.get(key)
            require(isinstance(hashes, dict) and set(hashes) == set(expected_names) and hashes == value.get(key), "Technical inventory differs")
            for name, expected in hashes.items():
                checker.ref({"path": str(checker.root / "research" / name), "sha256": expected})
        require(technical.get("reviews") == value.get("reviews") and len(value["reviews"]) == 3, "Technical review refs differ")
        paths = []
        for number, item in enumerate(value["reviews"], 1):
            path = checker.ref(item); paths.append(path); review = checker.json(path)
            require(type(review.get("round")) is int and review["round"] == number and review.get("status") == "PASS"
                    and all(review.get(key) == technical[key] for key in ("software_hashes", "evaluator_software_hashes")), "Technical reviews do not bind current code")
        require(len(set(paths)) == 3, "Technical reviews are not separate records")
    checker.check("technical_thirteen_and_nine_with_three_reviews", technical_reviews)

    def previews():
        market = checker.json(folder / "market_input.json"); registry = checker.json(folder / "public_numeric_registry.json")
        contract = checker.json(folder / "prompt_contract.json")
        require((folder / "system_instruction.txt").read_text(encoding="utf-8") == build_system(contract), "System instruction differs")
        common = {}; preview_checks = []
        for case in expected_roster:
            packet = checker.json(folder / "packets" / (case["source_id"] + ".json"))
            for stage in range(1, 5):
                payload = checker.json(folder / f"previews/{case['case_id']}/stage{stage}_payload.json")
                require(payload == stage_payload(stage, case["arm"], packet, market, registry), "Authored payload differs")
                onset = stage == (1 if case["arm"] == "R1" else 4)
                require(("institution_document" in payload) == onset, "Assigned source appears at wrong stage")
                visible = case["arm"] == "R1" or stage == 4
                require(checker.json(folder / f"schemas/{case['arm']}_stage{stage}.json") == response_schema(stage, visible), "Stage schema differs")
                invariant = copy.deepcopy(payload); invariant.pop("institution_document", None); invariant.pop("response_schema", None)
                require(stage not in common or common[stage] == invariant, "Non-treatment conditions differ")
                common[stage] = invariant
            preview_checks.append({"case_id": case["case_id"], "onset_stage": 1 if case["arm"] == "R1" else 4,
                                   "authored_payloads_checked": 4, "future_assistant_or_calculator_history": "not_created"})
        require(manifest.get("preview_checks") == preview_checks, "Saved preview audit inventory differs")
        remaining = checker.json(folder / "remaining_requirements.json")
        require(remaining == manifest.get("remaining_requirements") and remaining.get("main_registration_or_freeze_available") is False,
                "Remaining human/authorization requirements differ")
    checker.check("sixteen_previews_eight_schemas_source_onset_and_common_conditions", previews)

    def input_coverage():
        refs = manifest.get("input_provenance", [])
        inputs = {checker.ref(item) for item in refs}
        consulted = {path for path in checker.seen if not path.is_relative_to(folder)}
        require(consulted <= inputs, "Consulted upstream source/code/review missing from preparation provenance")
    checker.check("consulted_input_provenance_coverage", input_coverage)
    checker.check("all_read_bytes_stable", checker.stable)
    technical = manifest.get("technical_review", {})
    if not isinstance(technical, dict):
        technical = {}
    return {"round": 1, "status": "PASS" if all(row["passed"] for row in checker.rows) else "FAIL",
            "artifact_kind": "v4.8_main_candidate_round1_audit", "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "data_origin": "synthetic_fixture_not_empirical" if synthetic else "actual_preparation_candidate",
            "candidate_manifest": reference(manifest_path), "candidate_bound": True,
            "software_hashes": technical.get("software_hashes", {}), "evaluator_software_hashes": technical.get("evaluator_software_hashes", {}),
            "reviewer": {"reviewer_id": "v48_main_candidate_round1", "reviewer_role": "deterministic_program",
                         "name_or_model_identity": "audit_v48_main_candidate_round1.py"},
            "authorship_disclosure": "Audit author also authored the preparer; independent AI and human review remain distinct.",
            "checks": checker.rows, "check_count": len(checker.rows), "pass_count": sum(row["passed"] for row in checker.rows),
            "auditor": reference(__file__), "model_calls": 0, "main_model_calls": 0, "api_calls": 0,
            "independent_human_review_completed": False, "main_authorized": False, "main_frozen": False,
            "scope": "Candidate byte/provenance/task validation while human source review and execution authorization remain pending.",
            "topic": "Public judgments -> source-grounded interpretation and rationale -> actual proposed allocation. No strategy success or optimal weights are asserted.",
            "limits": ["Hashes and recorded roles are not external timestamps or identity authentication.",
                       "Preparation contains no generated responses; future semantic findings and actual main measurements remain unavailable.",
                       "This audit supplies one technical review record and cannot itself authorize or freeze execution."]}


def validate_output(manifest_path, output, *, workspace_root=ROOT):
    """Keep new review output away from preserved candidate, pilot and source trees."""
    manifest_path, output = Path(manifest_path).resolve(), Path(output).resolve()
    manifest = read(manifest_path)
    protected = {manifest_path.parent}
    refs = [manifest.get("prior_pilot", {}).get(key) for key in ("manifest", "registration", "run_summary")]
    refs.append(manifest.get("evaluator_material_refs", {}).get("source_verification"))
    refs.extend(item.get("original_pdf") for item in manifest.get("original_documents", []))
    for item in refs:
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            path = Path(item["path"])
            if not path.is_absolute():
                path = Path(workspace_root) / path
            protected.add(path.resolve().parent)
    require(not any(output.is_relative_to(folder) for folder in protected),
            "Audit output must remain outside preserved candidate, pilot and source directories")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--synthetic", action="store_true")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    validate_output(args.manifest, output)
    report = audit(args.manifest, synthetic=args.synthetic)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": report["status"], "output": str(output), "model_calls": 0}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
