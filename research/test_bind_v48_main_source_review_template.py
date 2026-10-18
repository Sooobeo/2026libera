"""Temporary synthetic binding checks; no real candidate, judgment or model call."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import bind_v48_main_source_review_template as binder


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


class Fixture:
    def __init__(self, root):
        self.root, self.prepared = root, root / "synthetic_candidate"
        self.manifest_path, self.template_path = self.prepared / "manifest.json", root / "blank_v2.json"
        self.template = binder.read(binder.TEMPLATE.read_bytes())
        originals = []
        for material in self.template["source_materials"]:
            source = material["source_id"]
            pdf = root / "synthetic_originals" / (source + ".pdf")
            pdf.parent.mkdir(parents=True, exist_ok=True)
            pdf.write_bytes(b"Synthetic byte fixture; not an actual PDF source or judgment")
            material["original_pdf"] = binder.reference(pdf)
            originals.append({"source_id": source, "original_pdf": binder.reference(pdf),
                "known_source_issues": [x["issue"] for x in material["known_source_issue_dispositions"]]})
        for relative in binder.candidate_files():
            save(self.prepared / relative, {"synthetic_only": True})
        for material in self.template["source_materials"]:
            source = material["source_id"]
            save(self.prepared / "packets" / (source + ".json"), {"source_id": source, "split": "main",
                "dates": material["recorded_dates_for_review_not_new_judgment"], "source_url": material["source_url"]})
        prior = {}
        for key in ("manifest", "registration", "run_summary"):
            path = root / "synthetic_prior" / (key + ".json")
            save(path, {"synthetic_only": True})
            prior[key] = binder.reference(path)
        prior["postpilot_reviews"] = []
        for number in (1, 2, 3):
            path = root / "synthetic_prior" / ("round" + str(number) + ".json")
            save(path, {"round": number, "status": "PASS", "synthetic_only": True})
            prior["postpilot_reviews"].append(binder.reference(path))
        self.candidate = {"candidate_version": "v4.8-main-candidate-1",
            "scope": "offline_main_input_candidate_not_execution_registration",
            "main_authorized": False, "main_frozen": False, "human_review_completed": False,
            "main_model_calls": 0, "actual_main_responses": 0, "expected_sector_count": 44,
            "roster": [{"case_id": source + "__" + arm, "source_id": source, "arm": arm, "split": "main"}
                       for source in binder.SOURCES for arm in ("R1", "R4")],
            "files": {name: binder.reference(self.prepared / name)["sha256"] for name in binder.candidate_files()},
            "original_documents": originals, "prior_pilot": prior}
        self.pin()

    def pin(self):
        save(self.manifest_path, self.candidate)
        save(self.template_path, self.template)

    def build(self):
        return binder.build_binding(self.manifest_path, self.template_path, workspace_root=self.root)

    def bind(self, output=None):
        return binder.bind(self.manifest_path, output or self.root / "bound_pending",
                           self.template_path, workspace_root=self.root)


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.f = Fixture(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_only_refs_and_candidate_status_change_and_no_source_verdict(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        bound, inputs, candidate = self.f.build()
        expected = copy.deepcopy(self.f.template)
        expected["candidate_manifest"] = binder.reference(self.f.manifest_path)
        expected["candidate_status"] = "bound_to_candidate_bytes; independent_human_source_review_not_started"
        for material in expected["source_materials"]:
            material["packet"] = binder.reference(self.f.prepared / "packets" / (material["source_id"] + ".json"))
        self.assertEqual(bound, expected)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        self.assertIsNone(bound["completed_at_utc"])
        self.assertEqual(bound["source_materials"][0]["recorded_dates_for_review_not_new_judgment"]["sector_view_as_of_raw"], "6/31/26")
        self.assertIn("uncertain", bound["allowed_relationships"])
        self.assertIn("different_scales_not_directly_comparable", bound["allowed_relationships"])

    def test_writes_only_new_pending_worksheet_and_non_authorizing_receipt(self):
        result = self.f.bind()
        self.assertEqual(result["status"], "references_bound_source_review_pending")
        self.assertFalse(result["main_candidate_created"])
        self.assertFalse(result["main_gate_created"])
        self.assertFalse(result["main_authorization_created"])
        self.assertEqual(result["human_judgments_created"], 0)
        self.assertEqual(result["model_calls"], 0)
        output = self.root / "bound_pending"
        self.assertEqual({p.name for p in output.iterdir()}, {"source_review_pending.json", "binding_receipt.json"})
        first = {p: p.read_bytes() for p in output.iterdir()}
        with self.assertRaises(ValueError): self.f.bind()
        self.assertEqual(first, {p: p.read_bytes() for p in output.iterdir()})

    def test_filled_judgment_identity_or_review_time_is_never_erased(self):
        original = copy.deepcopy(self.f.template)
        for kind in ("judgment", "identity", "time", "paraphrase", "issue"):
            with self.subTest(kind=kind):
                self.f.template = copy.deepcopy(original)
                if kind == "judgment": self.f.template["source_difference_inventory"][0]["relationship"] = "uncertain"
                elif kind == "identity": self.f.template["reviewer"]["reviewer_id"] = "synthetic_reviewed"
                elif kind == "time": self.f.template["completed_at_utc"] = "2026-10-19T00:00:00Z"
                elif kind == "paraphrase": self.f.template["source_difference_inventory"][0]["source_A_researcher_paraphrase"] = "already filled"
                else: self.f.template["source_materials"][0]["known_source_issue_dispositions"][0]["disposition"] = "not_assessable"
                self.f.pin()
                with self.assertRaises(ValueError): self.f.bind()
                self.assertFalse((self.root / "bound_pending").exists())

    def test_missing_industry_and_source_order_rejected(self):
        self.f.template["source_difference_inventory"].pop()
        self.f.pin()
        with self.assertRaises(ValueError): self.f.build()

    def test_changed_packet_or_required_hash_rejected(self):
        name = "packets/" + binder.SOURCES[0] + ".json"
        path = self.f.prepared / name
        path.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError): self.f.build()
        self.f.candidate["files"][name] = None
        self.f.pin()
        with self.assertRaises(ValueError): self.f.build()

    def test_dates_url_and_known_limits_cannot_silently_change(self):
        self.f.template["source_materials"][0]["recorded_dates_for_review_not_new_judgment"]["sector_view_as_of_raw"] = "6/30/26"
        self.f.pin()
        with self.assertRaises(ValueError): self.f.build()

    def test_original_pdf_and_known_issue_mismatch_rejected(self):
        self.f.candidate["original_documents"][0]["known_source_issues"] = []
        self.f.pin()
        with self.assertRaises(ValueError): self.f.build()

    def test_prior_reviews_require_three_ordered_pass_records(self):
        path = Path(self.f.candidate["prior_pilot"]["postpilot_reviews"][0]["path"])
        save(path, {"round": 1, "status": "FAIL", "synthetic_only": True})
        self.f.candidate["prior_pilot"]["postpilot_reviews"][0] = binder.reference(path)
        self.f.pin()
        with self.assertRaises(ValueError): self.f.build()

    def test_preparation_flags_and_no_main_calls_must_remain_false_zero(self):
        self.f.candidate["main_authorized"] = True
        self.f.pin()
        with self.assertRaises(ValueError): self.f.build()
        self.f.candidate["main_authorized"] = False
        self.f.candidate["actual_main_responses"] = 1
        self.f.pin()
        with self.assertRaises(ValueError): self.f.build()

    def test_output_cannot_enter_candidate_original_or_prior_trees(self):
        for folder in (self.f.prepared, self.root / "synthetic_originals", self.root / "synthetic_prior"):
            with self.subTest(folder=folder):
                target = folder / "new_review"
                with self.assertRaises(ValueError): self.f.bind(target)
                self.assertFalse(target.exists())

    def test_extra_candidate_file_and_nonfinite_json_rejected(self):
        self.f.candidate["files"]["../escape.json"] = "1" * 64
        self.f.pin()
        with self.assertRaises(ValueError): self.f.build()
        with self.assertRaises(ValueError): binder.read(b'{"value":NaN}')
        with self.assertRaises(ValueError): binder.read(b'{"value":0,"value":1}')


if __name__ == "__main__":
    unittest.main(verbosity=2)
