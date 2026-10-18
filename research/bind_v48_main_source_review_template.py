"""Bind a blank v2 source-review worksheet to an already prepared main candidate.

Offline metadata/byte checks only. This tool creates no candidate, judgment,
reviewer identity, review time, execution gate, freeze or authorization. It never
reads reference annotations or model responses. Actual source review remains a
separate human task; uncertainty and non-comparability are legitimate findings.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "research/evaluator_only/v48_main_source_review_template_20261018_v2.json"
SOURCES = ("fidelity_q3_2026", "ubs_july_2026")
CODES = ("10", "15", "20", "25", "30", "35", "40", "45", "50", "55", "60")
RELATIONSHIPS = {"substantive_difference_supported", "similarity_supported",
                 "different_scales_not_directly_comparable", "insufficient_evidence", "uncertain"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def reference(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def read(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError("Nonfinite JSON value: " + value)
    return json.loads(data.decode("utf-8-sig"), object_pairs_hook=pairs,
                      parse_constant=nonfinite)


class Inputs:
    def __init__(self, root):
        self.root, self.refs = Path(root).resolve(), {}

    def path(self, value):
        path = Path(value)
        return (path if path.is_absolute() else self.root / path).resolve()

    def file(self, path, expected=None):
        path = self.path(path)
        data = path.read_bytes()
        found = hashlib.sha256(data).hexdigest()
        if expected is not None:
            require(sha(expected) and found == expected, "Input hash mismatch: " + str(path))
        prior = self.refs.get(str(path))
        require(prior is None or prior["sha256"] == found, "Input changed between reads: " + str(path))
        self.refs[str(path)] = {"path": str(path), "sha256": found}
        return data

    def bound(self, item):
        require(isinstance(item, dict) and isinstance(item.get("path"), str)
                and bool(item["path"].strip()) and sha(item.get("sha256")), "Required file reference missing")
        self.file(item["path"], item["sha256"])
        return self.refs[str(self.path(item["path"]))]

    def stable(self):
        for item in self.refs.values():
            require(reference(item["path"]) == item, "Input changed while binding: " + item["path"])


def candidate_files():
    names = {"market_input.json", "public_numeric_registry.json", "runtime.json", "prompt_contract.json",
             "system_instruction.txt", "remaining_requirements.json"}
    names.update("packets/" + source + ".json" for source in SOURCES)
    names.update(f"schemas/{arm}_stage{stage}.json" for arm in ("R1", "R4") for stage in range(1, 5))
    names.update(f"previews/{source}__{arm}/stage{stage}_payload.json"
                 for source in SOURCES for arm in ("R1", "R4") for stage in range(1, 5))
    return names


def validate_blank(template):
    require(template.get("review_version") == "v4.8-main-source-review-1"
            and template.get("artifact_kind") == "blank_pre_execution_source_review_template_not_review_or_authorization",
            "Blank v2 source-review template required")
    require(template.get("review_status") == "not_started" and template.get("completed_at_utc") is None
            and template.get("independent_human_review_completed") is False
            and template.get("candidate_manifest") == {"path": None, "sha256": None}
            and bool(template.get("pending")), "Template must remain unreviewed and unbound")
    reviewer = template.get("reviewer")
    require(isinstance(reviewer, dict) and reviewer and all(v is None for v in reviewer.values()),
            "Do not bind or erase a recorded reviewer identity")
    require(template.get("human_judgments_created") == 0 and template.get("model_calls_by_template_creation") == 0,
            "Template records must contain no generated judgments or calls")
    require(set(template.get("allowed_relationships", [])) == RELATIONSHIPS,
            "Preserve uncertainty, insufficient evidence and non-comparability choices")
    materials = template.get("source_materials", [])
    require(len(materials) == 2 and [m.get("source_id") for m in materials] == list(SOURCES),
            "Exactly the two main sources are required")
    for material in materials:
        require(material.get("packet") == {"path": None, "sha256": None}
                and material.get("review_status") == "not_started" and material.get("review_notes") is None,
                "Source material review must be unfilled")
        require(all(d.get("disposition") is None and d.get("reason") is None
                    for d in material.get("known_source_issue_dispositions", [])), "Source issue findings must be unfilled")
    rows = template.get("source_difference_inventory", [])
    require(len(rows) == 11 and [r.get("sector_code") for r in rows] == list(CODES), "Exactly 11 ordered industries required")
    for row in rows:
        require(row.get("split") == "main" and row.get("source_A_id") == SOURCES[0]
                and row.get("source_B_id") == SOURCES[1] and row.get("review_status") == "not_started"
                and row.get("independent_human_review_completed") is False, "Comparison row is not a blank main row")
        for key in ("created_before_main_responses", "rating_definition_scope", "period_and_universe_scope",
                    "relationship", "decision_relevance_reason", "reviewer_id", "reviewer_role"):
            require(row.get(key) is None, "Do not bind or erase an existing comparison finding: " + key)
        require(row.get("comparability_limits") == [], "Comparison findings must remain blank")
        for side in ("A", "B"):
            prefix = "source_" + side
            require(all(row.get(prefix + suffix) is None for suffix in
                        ("_literal_judgment", "_researcher_paraphrase", "_missing_material_reason"))
                    and row.get(prefix + "_evidence_records") == []
                    and row.get(prefix + "_paraphrase_review") == {"status": None, "reason": None},
                    "Original, paraphrase and paraphrase-review fields must remain blank")


def build_binding(manifest_path, template_path=TEMPLATE, *, workspace_root=ROOT):
    """Return the still-blank bound worksheet and input snapshot; write nothing."""
    inputs = Inputs(workspace_root)
    manifest_path, template_path = inputs.path(manifest_path), inputs.path(template_path)
    candidate = read(inputs.file(manifest_path))
    template = read(inputs.file(template_path))
    validate_blank(template)
    require(candidate.get("candidate_version") == "v4.8-main-candidate-1"
            and candidate.get("scope") == "offline_main_input_candidate_not_execution_registration",
            "An already prepared, non-executable main candidate is required")
    require(all(candidate.get(k) is False for k in ("main_authorized", "main_frozen", "human_review_completed")),
            "Candidate must not claim authorization, freeze or human completion")
    require(all(type(candidate.get(k)) is int and candidate[k] == 0
                for k in ("main_model_calls", "actual_main_responses")), "Candidate must retain zero preparation main responses/calls")
    expected_roster = [{"case_id": source + "__" + arm, "source_id": source, "arm": arm, "split": "main"}
                       for source in SOURCES for arm in ("R1", "R4")]
    require(candidate.get("roster") == expected_roster and candidate.get("expected_sector_count") == 44,
            "Fixed main four-case / 44-industry denominator required")
    require(isinstance(candidate.get("files"), dict) and set(candidate["files"]) == candidate_files(),
            "Exact 32 candidate input files required")
    for name, expected in candidate["files"].items():
        require(sha(expected), "Required candidate SHA-256 missing: " + name)
        inputs.file(manifest_path.parent / name, expected)
    reviews = candidate.get("prior_pilot", {}).get("postpilot_reviews", [])
    require(isinstance(reviews, list) and len(reviews) == 3, "Candidate must record three prior pilot reviews")
    for number, item in enumerate(reviews, 1):
        review = read(inputs.file(inputs.bound(item)["path"]))
        require(type(review.get("round")) is int and review["round"] == number and review.get("status") == "PASS",
                "Recorded prior pilot reviews must be ordered PASS rounds 1, 2 and 3")
    originals = candidate.get("original_documents", [])
    require(len(originals) == 2 and {o.get("source_id") for o in originals} == set(SOURCES),
            "Two candidate original documents required")
    result = copy.deepcopy(template)
    result["candidate_manifest"] = copy.deepcopy(inputs.refs[str(manifest_path)])
    result["candidate_status"] = "bound_to_candidate_bytes; independent_human_source_review_not_started"
    for material in result["source_materials"]:
        source = material["source_id"]
        original = next(o for o in originals if o["source_id"] == source)
        candidate_pdf = inputs.bound(original.get("original_pdf"))
        template_pdf = inputs.bound(material.get("original_pdf"))
        require(candidate_pdf == template_pdf, "Template and candidate refer to different original PDF bytes or paths")
        require([d["issue"] for d in material["known_source_issue_dispositions"]] == original.get("known_source_issues"),
                "Known original source limits differ; do not silently rewrite review scope")
        packet_path = manifest_path.parent / "packets" / (source + ".json")
        packet = read(inputs.file(packet_path))
        require(packet.get("source_id") == source and packet.get("split") == "main"
                and packet.get("dates") == material.get("recorded_dates_for_review_not_new_judgment")
                and packet.get("source_url") == material.get("source_url"),
                "Source identity, recorded dates or URL differ from the blank worksheet")
        material["original_pdf"] = copy.deepcopy(original["original_pdf"])
        material["packet"] = copy.deepcopy(inputs.refs[str(packet_path.resolve())])
    inputs.stable()
    return result, inputs, candidate


def bind(manifest_path, output_dir, template_path=TEMPLATE, *, workspace_root=ROOT):
    result, inputs, candidate = build_binding(manifest_path, template_path, workspace_root=workspace_root)
    manifest_path, output = inputs.path(manifest_path), inputs.path(output_dir)
    require(not output.exists(), "Use a new output directory; preserve existing worksheet and receipt")
    protected = {manifest_path.parent, inputs.root / "data/sector_documents",
                 inputs.root / "data/sector_protocol/v48_design_20261018"}
    for original in candidate["original_documents"]:
        protected.add(inputs.path(original["original_pdf"]["path"]).parent)
    for key in ("manifest", "registration", "run_summary"):
        item = candidate.get("prior_pilot", {}).get(key)
        require(isinstance(item, dict) and isinstance(item.get("path"), str) and sha(item.get("sha256")),
                "Protected prior pilot reference missing: " + key)
        protected.add(inputs.path(item["path"]).parent)
    for folder in protected:
        folder = folder.resolve()
        require(not output.is_relative_to(folder) and not folder.is_relative_to(output),
                "Binding output overlaps a preserved candidate/pilot/source input directory")
    inputs.stable()
    output.mkdir(parents=True, exist_ok=False)
    worksheet_path = output / "source_review_pending.json"
    with worksheet_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    inputs.stable()
    receipt = {"artifact_kind": "v4.8_main_blank_source_review_binding_receipt",
        "status": "references_bound_source_review_pending", "assembled_at_utc": datetime.now(timezone.utc).isoformat(),
        "timestamp_scope": "Artifact assembly only; human reviewer and completion times remain null.",
        "inputs": list(inputs.refs.values()), "output": reference(worksheet_path), "binder": reference(__file__),
        "input_file_count": len(candidate["files"]), "source_count": 2, "comparison_row_count": 11,
        "model_calls": 0, "human_judgments_created": 0, "independent_human_review_completed": False,
        "main_candidate_created": False, "main_gate_created": False, "main_authorization_created": False,
        "scope": "Recorded metadata and byte consistency only. Prior review PASS is checked as a record, not an independent repeat of those audits. No source-meaning verdict, identity authentication or guarantee of absent main responses is made.",
        "topic_alignment": "Preserves a blank review of original judgment, researcher paraphrase, definitions, dates, comparability and limits before source-to-reason-to-allocation interpretation."}
    with (output / "binding_receipt.json").open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--template", default=TEMPLATE, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(bind(args.manifest, args.output_dir, args.template), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
