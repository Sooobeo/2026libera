"""Completeness/hash checks for human attestations; never certifies identity.

The existing pre-output protocol requires two independently authored reviews.
No code here fills their answers, adjudicates their meaning or manufactures a
review. Blank forms and AI/offline code reviews do not pass this gate.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import prepare_sector_v491 as prepare
import remote_sector_runtime as remote
from sector_engine import SECTOR_CODES

FORM_REFS = [
    {"path": "research/v491_human_review_pack_20261019_R1.json", "sha256": "ea6bd366adf09da0f79c9811fb760dc4b33b9b4a1618ac13435aecb20915f411"},
    {"path": "research/v491_human_review_pack_20261019_R2.json", "sha256": "4b6d6f4d584dad86e3cd299a74c6a04c85df017c870a219061d5b2daaf74fa00"},
]


def require(condition, message):
    if not condition:
        raise ValueError("Human pre-output review gate: " + message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def timestamp(value):
    require(nonempty(value), "UTC timestamp is missing")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.utcoffset() is not None and result.utcoffset().total_seconds() == 0,
            "timestamps must explicitly use UTC")
    require(result <= datetime.now(timezone.utc), "future review timestamp is invalid")
    return result


def validate_human_gate(path, expected_sha=None, split="pilot"):
    require(split == "pilot", "this runtime only supports the pilot split")
    gate, ref = prepare.read(path, expected_sha)
    require(gate.get("receipt_version") == "v491_human_preoutput_gate_1"
            and gate.get("pack_id") == "v491_preoutput_review_20261019"
            and gate.get("status") == "completed_for_approved_splits", "completed human receipt is required")
    require(gate.get("blank_form_refs") == FORM_REFS, "reviewer form versions differ")
    forms = [prepare.read(item["path"], item["sha256"])[0] for item in FORM_REFS]
    require(gate.get("input_refs") == forms[0]["input_refs"] == forms[1]["input_refs"], "input registry differs")
    for item in gate["input_refs"]:
        require(remote.sha(prepare.workspace_path(item["path"])) == item["sha256"], "reviewed source changed: " + item["path"])
    reviewers = gate.get("reviewers")
    require(isinstance(reviewers, list) and len(reviewers) == 2
            and [r.get("reviewer_slot") for r in reviewers] == ["R1", "R2"], "two distinct reviewer slots required")
    names, answers, completed, exported = [], [], [], []
    for reviewer, form, form_ref in zip(reviewers, forms, FORM_REFS):
        name = reviewer.get("reviewer_name")
        require(nonempty(name), "reviewer name is missing")
        names.append(name.strip().casefold())
        completed.append(timestamp(reviewer.get("completed_at_utc")))
        for attestation in ("independent_work", "no_model_outputs_seen", "original_pdf_read"):
            require(reviewer.get(attestation) is True, "human attestation missing: " + attestation)
        require(nonempty(reviewer.get("submission_sha256")) and len(reviewer["submission_sha256"]) == 64,
                "exact original submission hash is required")
        submission, _ = prepare.read(reviewer["submission_path"], reviewer["submission_sha256"])
        exported.append(timestamp(submission.get("exported_at_utc")))
        require(completed[-1] <= exported[-1], "submission export predates completion")
        require(submission.get("pack_id") == gate["pack_id"] and submission.get("reviewer_slot") == reviewer["reviewer_slot"]
                and submission.get("blank_form_ref") == form_ref and submission.get("input_refs") == gate["input_refs"],
                "submission belongs to another reviewer/form/input version")
        result = submission.get("answers")
        require(isinstance(result, dict), "original answers must be retained")
        require(set(result) == {field["key"] for field in form["form_fields"]}, "original answer fields differ from form")
        require(result.get("meta.review_scope") in (split, "both"), "reviewer's selected scope does not cover this split")
        for field in form["form_fields"]:
            key = field["key"]
            if not key.startswith(("meta.", "common.", "macro.", "source." + split + ".", "comparison." + split + ".")):
                continue
            value = result.get(key)
            if "options" in field:
                require(any(type(value) is type(option[0]) and value == option[0] for option in field["options"]),
                        "missing/invalid selected answer: " + key)
            else:
                require(nonempty(value), "missing text answer: " + key)
        for attestation in ("independent_work", "no_model_outputs_seen", "original_pdf_read"):
            require(result.get("meta." + attestation) is True, "original attestation is not affirmative")
        require(result.get("meta.reviewer_name") == name and result.get("meta.completed_at_utc") == reviewer["completed_at_utc"],
                "gate reviewer identity/timestamp differs from original answers")
        answers.append(result)
    require(len(set(names)) == 2, "two independently named human reviewers are required")
    coordinator = gate.get("coordinator", {})
    require(nonempty(coordinator.get("name")), "coordinator name is missing")
    adjudicated_at = timestamp(coordinator.get("reviewed_at_utc"))
    require(all(t <= adjudicated_at for t in exported), "reconciliation predates original submissions")
    selected = gate.get("splits", {}).get(split, {})
    require(selected.get("status") == "reviewed_before_outputs" and type(selected.get("source_review_rows_reviewed")) is int
            and selected.get("source_review_rows_reviewed") == 22,
            "22 source-sector reviews must be reconciled before outputs")
    for field in ("reviewer_fields_complete", "common_context_reviewed", "evaluation_rubric_reviewed",
                  "gate_approved_by_human", "gate_recorded_before_research_outputs"):
        require(selected.get(field) is True, "human coordinator approval is missing: " + field)
    require(selected.get("material_input_or_rubric_change_required") is False, "material revision remains pending")
    require(nonempty(selected.get("gate_rationale")), "gate rationale is missing")
    require(all(isinstance(selected.get(field), list) for field in ("source_and_context_disagreements", "unresolved_findings")),
            "disagreement and unresolved records must be preserved")
    rows = selected.get("source_comparison_rows")
    require(isinstance(rows, list) and [row.get("sector_code") for row in rows] == list(SECTOR_CODES),
            "exactly 11 ordered sector comparisons required")
    choices = {"substantive_difference_supported", "similarity_supported", "different_scales_not_directly_comparable",
               "insufficient_evidence", "uncertain"}
    for row in rows:
        prefix = "comparison." + split + "." + row["sector_code"] + ".decision"
        require(row.get("r1_decision") == answers[0][prefix] and row.get("r2_decision") == answers[1][prefix],
                "reconciliation must preserve both original decisions")
        require(row.get("reconciled_decision") in choices and nonempty(row.get("evidence_and_reason"))
                and type(row.get("disagreement_preserved")) is bool, "comparison decision/reason is incomplete")
        if row["r1_decision"] != row["r2_decision"]:
            require(row["disagreement_preserved"] is True, "reviewer disagreement must be preserved")
    return {"status": "human_attestation_completeness_and_hashes_passed", "split": split,
            "gate_ref": ref, "reviewer_names": [r["reviewer_name"] for r in reviewers],
            "reviewed_at_utc": coordinator["reviewed_at_utc"],
            "scope": "File identity, completeness and explicit human attestations only; software cannot certify human identity or semantic accuracy."}
