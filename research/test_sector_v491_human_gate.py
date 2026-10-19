"""Ephemeral synthetic fixtures only; this test suite performs no human review."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

import prepare_sector_v491 as prepare
import sector_v491_human_gate as gate
import remote_sector_runtime as remote


class HumanGateTests(unittest.TestCase):
    def setUp(self):
        (prepare.ROOT / "tmp").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="v491_gate_synthetic_test_", dir=prepare.ROOT / "tmp")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.receipt = remote.read(prepare.ROOT / "research/v491_human_review_pack_20261019_gate_blank.json")
        self.receipt["status"] = "completed_for_approved_splits"
        self.submissions = []
        for index, form_ref in enumerate(gate.FORM_REFS):
            form = remote.read(prepare.ROOT / form_ref["path"])
            answers = {}
            for field in form["form_fields"]:
                if field["key"].startswith(("source.main.", "comparison.main.")):
                    answers[field["key"]] = None
                elif "options" in field:
                    answers[field["key"]] = field["options"][0][0]
                else:
                    answers[field["key"]] = "SYNTHETIC UNIT TEST ONLY; no human review took place."
            name = "SYNTHETIC UNIT TEST REVIEWER " + str(index + 1)
            answers.update({"meta.reviewer_name": name, "meta.completed_at_utc": "2026-10-18T00:00:00Z",
                            "meta.review_scope": "pilot", "meta.independent_work": True,
                            "meta.no_model_outputs_seen": True, "meta.original_pdf_read": True})
            submission = {"pack_id": form["pack_id"], "reviewer_slot": "R" + str(index + 1),
                          "blank_form_ref": form_ref, "input_refs": form["input_refs"],
                          "exported_at_utc": "2026-10-18T00:01:00Z", "answers": answers}
            self.submissions.append(submission)
            self.receipt["reviewers"][index].update(reviewer_name=name, completed_at_utc=answers["meta.completed_at_utc"],
                independent_work=True, no_model_outputs_seen=True, original_pdf_read=True)
        self.receipt["coordinator"].update(name="SYNTHETIC UNIT TEST COORDINATOR", reviewed_at_utc="2026-10-18T00:02:00Z")
        selected = self.receipt["splits"]["pilot"]
        selected.update(status="reviewed_before_outputs", reviewer_fields_complete=True, source_review_rows_reviewed=22,
            common_context_reviewed=True, evaluation_rubric_reviewed=True, source_and_context_disagreements=[],
            unresolved_findings=[], material_input_or_rubric_change_required=False, gate_approved_by_human=True,
            gate_rationale="SYNTHETIC UNIT TEST ONLY; this is not an actual human gate.", gate_recorded_before_research_outputs=True)
        for row in selected["source_comparison_rows"]:
            decision = self.submissions[0]["answers"]["comparison.pilot." + row["sector_code"] + ".decision"]
            row.update(r1_decision=decision, r2_decision=decision, reconciled_decision=decision,
                       evidence_and_reason="SYNTHETIC UNIT TEST ONLY.", disagreement_preserved=False)

    def write(self):
        for i, submission in enumerate(self.submissions):
            path = self.root / ("synthetic_R" + str(i + 1) + ".json")
            path.write_text(json.dumps(submission), encoding="utf-8")
            self.receipt["reviewers"][i].update(submission_path=str(path), submission_sha256=remote.sha(path))
        path = self.root / "synthetic_gate.json"
        path.write_text(json.dumps(self.receipt), encoding="utf-8")
        return path

    def test_synthetic_complete_pilot_fixture_allows_main_answers_to_remain_blank(self):
        result = gate.validate_human_gate(self.write())
        self.assertEqual(result["status"], "human_attestation_completeness_and_hashes_passed")
        self.assertIn("cannot certify human identity", result["scope"])

    def test_required_answer_missing_denies(self):
        self.submissions[0]["answers"]["common.task_vs_institution.evidence"] = None
        with self.assertRaisesRegex(ValueError, "missing text answer"):
            gate.validate_human_gate(self.write())

    def test_scope_main_cannot_authorize_pilot(self):
        self.submissions[0]["answers"]["meta.review_scope"] = "main"
        with self.assertRaisesRegex(ValueError, "scope does not cover"):
            gate.validate_human_gate(self.write())

    def test_changed_original_decision_cannot_be_hidden_in_reconciliation(self):
        self.receipt["splits"]["pilot"]["source_comparison_rows"][0]["r1_decision"] = "uncertain"
        with self.assertRaisesRegex(ValueError, "preserve both original decisions"):
            gate.validate_human_gate(self.write())

    def test_disagreement_must_remain_recorded(self):
        self.submissions[0]["answers"]["comparison.pilot.10.decision"] = "uncertain"
        self.receipt["splits"]["pilot"]["source_comparison_rows"][0]["r1_decision"] = "uncertain"
        with self.assertRaisesRegex(ValueError, "disagreement must be preserved"):
            gate.validate_human_gate(self.write())

    def test_null_submission_sha_cannot_disable_hash_verification(self):
        path = self.write()
        self.receipt["reviewers"][0]["submission_sha256"] = None
        path.write_text(json.dumps(self.receipt), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "submission hash is required"):
            gate.validate_human_gate(path)

    def test_nonindependent_review_denies(self):
        self.submissions[0]["answers"]["meta.independent_work"] = False
        with self.assertRaisesRegex(ValueError, "attestation is not affirmative"):
            gate.validate_human_gate(self.write())

    def test_pending_material_revision_denies(self):
        self.receipt["splits"]["pilot"]["material_input_or_rubric_change_required"] = True
        with self.assertRaisesRegex(ValueError, "material revision remains pending"):
            gate.validate_human_gate(self.write())

    def test_unknown_extra_answers_denied(self):
        self.submissions[0]["answers"]["unexpected.model_output"] = "not allowed"
        with self.assertRaisesRegex(ValueError, "answer fields differ"):
            gate.validate_human_gate(self.write())

    def test_reconciliation_cannot_predate_export(self):
        self.receipt["coordinator"]["reviewed_at_utc"] = "2026-10-18T00:00:30Z"
        with self.assertRaisesRegex(ValueError, "reconciliation predates"):
            gate.validate_human_gate(self.write())

    def test_same_named_reviewer_cannot_fill_both_slots(self):
        same_name = self.receipt["reviewers"][0]["reviewer_name"]
        self.receipt["reviewers"][1]["reviewer_name"] = same_name
        self.submissions[1]["answers"]["meta.reviewer_name"] = same_name
        with self.assertRaisesRegex(ValueError, "two independently named"):
            gate.validate_human_gate(self.write())

    def test_future_review_timestamp_denied(self):
        self.receipt["reviewers"][0]["completed_at_utc"] = "2100-01-01T00:00:00Z"
        self.submissions[0]["answers"]["meta.completed_at_utc"] = "2100-01-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "future review timestamp"):
            gate.validate_human_gate(self.write())

    def test_changed_input_hash_denied(self):
        self.receipt["input_refs"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "input registry differs"):
            gate.validate_human_gate(self.write())

    def test_submission_bytes_changed_after_hash_denied(self):
        receipt_path = self.write()
        submission = Path(self.receipt["reviewers"][0]["submission_path"])
        submission.write_bytes(submission.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "input hash differs"):
            gate.validate_human_gate(receipt_path)


if __name__ == "__main__":
    unittest.main()
