"""Synthetic candidate auditor tests; no actual candidate/report or model calls."""
import json
from pathlib import Path
import unittest

import audit_v48_main_candidate_round1 as candidate_audit
import test_prepare_sector_v48_main_candidate as fixtures


class CandidateAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = fixtures.MainCandidateTests(methodName="test_candidate_has_four_cases_44_sectors_and_no_execution_or_freeze")
        cls.fixture.setUp()
        third_path = cls.fixture.audits[2]
        third = candidate_audit.read(third_path)
        third["provenance"]["run_summary"] = candidate_audit.reference(cls.fixture.run / "summary.json")
        cls.fixture.write(third_path, third)
        cls.fixture.prepare()
        cls.folder = cls.fixture.output
        cls.original = {path: path.read_bytes() for path in cls.folder.rglob("*") if path.is_file()}

    @classmethod
    def tearDownClass(cls):
        cls.fixture.doCleanups()

    def setUp(self):
        for path, data in self.original.items():
            path.write_bytes(data)

    def write(self, path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def report(self):
        return candidate_audit.audit(self.folder / "manifest.json", workspace_root=self.fixture.real, synthetic=True)

    def refresh_manifest_receipt(self, change=None):
        path = self.folder / "manifest.json"
        manifest = candidate_audit.read(path)
        if change:
            change(manifest)
        for name in manifest["files"]:
            manifest["files"][name] = candidate_audit.digest(self.folder / name)
        self.write(path, manifest)
        receipt_path = self.folder / "preparation_receipt.json"
        receipt = candidate_audit.read(receipt_path)
        receipt["outputs"] = [candidate_audit.reference(self.folder / name)
                              for name in sorted(set(manifest["files"]) | {"manifest.json"})]
        self.write(receipt_path, receipt)

    def assert_failed(self, report, name):
        self.assertEqual(report["status"], "FAIL")
        self.assertIn(name, {row["id"] for row in report["checks"] if not row["passed"]})
        self.assertEqual(report["main_model_calls"], 0)
        self.assertFalse(report["independent_human_review_completed"])

    def test_valid_synthetic_candidate_has_gate_compatible_review_fields(self):
        report = self.report()
        self.assertEqual(report["status"], "PASS", report["checks"])
        self.assertEqual(report["round"], 1)
        self.assertEqual(report["data_origin"], "synthetic_fixture_not_empirical")
        self.assertEqual(report["candidate_manifest"], candidate_audit.reference(self.folder / "manifest.json"))
        self.assertEqual(len(report["software_hashes"]), 13)
        self.assertEqual(len(report["evaluator_software_hashes"]), 9)
        self.assertEqual((report["model_calls"], report["main_model_calls"], report["api_calls"]), (0, 0, 0))
        self.assertFalse(report["main_authorized"]); self.assertFalse(report["main_frozen"])
        self.assertFalse(report["independent_human_review_completed"])

    def test_pre_R4_document_rejected_even_after_candidate_hashes_are_refreshed(self):
        path = self.folder / "previews/fidelity_q3_2026__R4/stage1_payload.json"
        payload = candidate_audit.read(path)
        payload["institution_document"] = {"source_id": "fidelity_q3_2026", "synthetic": True}
        self.write(path, payload); self.refresh_manifest_receipt()
        self.assert_failed(self.report(), "sixteen_previews_eight_schemas_source_onset_and_common_conditions")

    def test_common_baseline_name_is_allowed_with_no_assigned_document(self):
        path = self.folder / "previews/fidelity_q3_2026__R4/stage1_payload.json"
        payload = candidate_audit.read(path)
        self.assertIn("fidelity_q3_2026", payload["common_market"]["synthetic_common_baseline_provenance"])
        self.assertNotIn("institution_document", payload)
        self.assertEqual(self.report()["status"], "PASS")

    def test_shared_runtime_cannot_drift_from_original_pilot(self):
        path = self.folder / "runtime.json"; value = candidate_audit.read(path)
        value["synthetic_changed_condition"] = True
        self.write(path, value); self.refresh_manifest_receipt()
        self.assert_failed(self.report(), "pilot_lineage_and_shared_four_bytes")

    def test_main_packet_cannot_drift_from_pinned_original(self):
        path = self.folder / "packets/ubs_july_2026.json"; value = candidate_audit.read(path)
        value["title"] = "Synthetic altered packet"
        self.write(path, value); self.refresh_manifest_receipt()
        self.assert_failed(self.report(), "two_source_and_six_evaluation_material_lineage")

    def test_changed_gold_is_detected_without_parsing_it(self):
        path = self.fixture.gold; before = path.read_bytes()
        self.addCleanup(path.write_bytes, before)
        path.write_bytes(before + b"\n")
        self.assert_failed(self.report(), "two_source_and_six_evaluation_material_lineage")

    def test_missing_receipt_output_is_not_accepted(self):
        path = self.folder / "preparation_receipt.json"; value = candidate_audit.read(path)
        value["outputs"].pop()
        self.write(path, value)
        self.assert_failed(self.report(), "preparation_receipt_inputs_and_outputs")

    def test_technical_maps_cannot_be_substituted(self):
        self.refresh_manifest_receipt(lambda value: value["technical_review"]["software_hashes"].update(
            {"run_sector_v48_main.py": "0" * 64}))
        self.assert_failed(self.report(), "technical_thirteen_and_nine_with_three_reviews")

    def test_preparation_cannot_assert_main_approval(self):
        self.refresh_manifest_receipt(lambda value: value.update(main_authorized=True, main_model_calls=1))
        self.assert_failed(self.report(), "unapproved_four_case_state")

    def test_extra_request_artifact_is_rejected_without_network(self):
        path = self.folder / "request.json"
        self.addCleanup(path.unlink)
        self.write(path, {"synthetic_not_an_actual_request": True})
        self.assert_failed(self.report(), "exact_public_file_inventory")

    def test_other_evaluation_cannot_substitute_for_bound_pilot_review(self):
        path = self.fixture.audits[2]; before = path.read_bytes()
        self.addCleanup(path.write_bytes, before)
        review = candidate_audit.read(path)
        review["provenance"]["evaluation"] = candidate_audit.reference(self.fixture.registration_path)
        self.write(path, review)
        self.refresh_manifest_receipt(lambda value: value["prior_pilot"]["postpilot_reviews"].__setitem__(2, candidate_audit.reference(path)))
        self.assert_failed(self.report(), "pilot_lineage_and_shared_four_bytes")

    def test_new_audit_output_cannot_append_to_preserved_artifact_trees(self):
        for folder in (self.folder, self.fixture.run, self.fixture.pilot, self.fixture.docs):
            with self.assertRaisesRegex(ValueError, "outside preserved"):
                candidate_audit.validate_output(self.folder / "manifest.json", folder / "new_audit.json",
                                                workspace_root=self.fixture.real)
        separate = self.fixture.root.parent / (self.fixture.root.name + "_uncreated_review") / "audit.json"
        candidate_audit.validate_output(self.folder / "manifest.json", separate, workspace_root=self.fixture.real)

    def test_round3_cannot_point_to_another_run_summary(self):
        path = self.fixture.audits[2]; before = path.read_bytes()
        self.addCleanup(path.write_bytes, before)
        review = candidate_audit.read(path)
        review["provenance"]["run_summary"] = candidate_audit.reference(self.fixture.registration_path)
        self.write(path, review)
        self.refresh_manifest_receipt(lambda value: value["prior_pilot"]["postpilot_reviews"].__setitem__(2, candidate_audit.reference(path)))
        self.assert_failed(self.report(), "pilot_lineage_and_shared_four_bytes")


if __name__ == "__main__":
    unittest.main()
