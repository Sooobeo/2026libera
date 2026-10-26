"""Remaining wrapper boundary tests using synthetic bundles and a mocked guard.

Arithmetic is the unchanged reviewed implementation with its separate29 tests.
These tests do not claim live remaining-stage or real-runtime integration.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


n = load(Path(__file__).with_name("audit_stage_numerics.py"), "remaining_numeric_under_test")
fixtures = load(ROOT / "research/completion_20261026/test_audit_stage_numerics.py", "accepted_numeric_fixtures")


class RemainingNumericTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="remaining-numeric-test-", dir=ROOT / "data")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.run, self.reports = self.base / "current", self.base / "reports"
        self.run.mkdir()
        self.reports.mkdir()
        self.declaration = {"run_directory": str(self.run), "output_root": str(self.reports)}
        self.declaration_ref = self.write(self.run / "campaign_declaration.json", self.declaration)
        self.bundle_path = self.reports / "bundle.json"
        self.current = self.make_stage(self.run, self.reports, "ubs_june_2026__L", "D0")
        self.bundle = self.make_bundle(self.current)
        self.write(self.bundle_path, self.bundle)
        self.guard = patch.object(n, "rebuild_guarded_bundle", side_effect=lambda _: copy.deepcopy(self.bundle)).start()
        self.addCleanup(patch.stopall)

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(value) + "\n").encode()
        path.write_bytes(data)
        return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}

    def make_stage(self, run, reports, case, stage):
        folder = run / (case + "__" + stage)
        folder.mkdir(parents=True)
        content = json.dumps({"common_market": fixtures.market(), "public_numeric_fact_index": fixtures.index()}, default=float)
        spec = self.write(folder / "worker_spec.json", {"case_id": case, "stage": stage, "body": {"messages": [{}, {"content": content}]}})
        response = self.write(folder / "response.json", {"message": {"content": fixtures.raw()}})
        transport = self.write(folder / "transport_result.json", {"status": "completed", "response_artifact": response})
        review = self.write(folder / "stage_review.json", {"case_id": case, "stage": stage})
        math = {**fixtures.sidecar(), "case_id": case, "stage": stage, "observed_transport_status": "completed",
                "input_refs": [spec, response, transport, review]}
        math_path = reports / "allocation_math" / (folder.name + ".json")
        self.write(math_path, math)
        return {"folder": folder, "case": case, "stage": stage, "refs": [spec, response, transport, review],
                "math": math, "math_path": math_path}

    def make_bundle(self, item):
        raw = fixtures.raw()
        return {"version": "remaining_semantic_bundle_1", "purpose": "pilot_completion_resume",
                "status": "prepared_for_semantic_reading", "observed_transport_status": "completed",
                "case_id": item["case"], "stage": item["stage"], "refs": [self.declaration_ref] + item["refs"],
                "raw_final_or_draft_text": raw, "raw_response_content_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                "own_prior_text": None, "own_D0_stage_directory": None, "own_D0_declaration_ref": None, "own_D0_origin": None}

    def configure_final(self, external):
        case = "ubs_june_2026__E" if external else "common_market_only__C"
        self.current = self.make_stage(self.run, self.reports, case, "F0")
        old_run = self.base / "previous_completion" if external else self.run
        old_reports = self.base / "previous_reports" if external else self.reports
        old_declaration = {"run_directory": str(old_run), "output_root": str(old_reports)}
        old_ref = self.write(old_run / "campaign_declaration.json", old_declaration) if external else self.declaration_ref
        self.prior = self.make_stage(old_run, old_reports, case, "D0")
        self.bundle = self.make_bundle(self.current)
        self.bundle.update(own_prior_text=fixtures.raw(), own_D0_stage_directory=str(self.prior["folder"]),
                           own_D0_declaration_ref=old_ref,
                           own_D0_origin="fixed_previous_completion_segment" if external else "same_remaining_run")
        self.bundle["refs"] += [old_ref] + self.prior["refs"]
        self.write(self.bundle_path, self.bundle)

    def result(self):
        return n.audit_bundle(self.bundle_path, self.current["math_path"])

    def test_completed_D0_wrapper_uses_pure_numbers_without_prose_grade(self):
        result = self.result()
        self.assertTrue(result["accepted_sidecar_comparison"]["matches"])
        self.assertEqual(result["semantic_claims_graded"], 0)
        self.assertEqual(result["model_calls"], 0)
        self.assertIsNone(result["independent_own_D0_allocation"])

    def test_live_header_rejected_before_guard(self):
        self.bundle["observed_transport_status"] = "running"
        self.write(self.bundle_path, self.bundle)
        with self.assertRaisesRegex(ValueError, "Completed remaining"):
            self.result()
        self.guard.assert_not_called()

    def test_old_completion_purpose_is_not_current_authority(self):
        self.bundle["purpose"] = "pilot_completion"
        self.write(self.bundle_path, self.bundle)
        with self.assertRaisesRegex(ValueError, "Completed remaining"):
            self.result()

    def test_new_UBS_E_D0_slot_rejected(self):
        self.bundle["case_id"] = "ubs_june_2026__E"
        self.write(self.bundle_path, self.bundle)
        with self.assertRaisesRegex(ValueError, "Completed remaining"):
            self.result()

    def test_modified_bundle_fails_fresh_guard_equality(self):
        altered = {**self.bundle, "raw_final_or_draft_text": "changed"}
        self.write(self.bundle_path, altered)
        with self.assertRaisesRegex(ValueError, "freshly guarded"):
            self.result()

    def test_external_D0_uses_original_declaration_math_and_exact_zero_delta(self):
        self.configure_final(True)
        result = self.result()
        self.assertEqual(result["own_D0_origin"], "fixed_previous_completion_segment")
        self.assertTrue(result["accepted_own_D0_sidecar_comparison"]["matches"])
        self.assertTrue(all(r["own_D0_to_current"]["raw_change_direction"] == "equal"
                            and r["own_D0_to_current"]["derived_change_direction"] == "equal"
                            for r in result["raw_and_derived_relations"]["sector_rows"]))

    def test_same_run_D0_uses_new_own_history(self):
        self.configure_final(False)
        result = self.result()
        self.assertEqual(result["own_D0_origin"], "same_remaining_run")
        self.assertTrue(result["accepted_own_D0_sidecar_comparison"]["matches"])

    def test_crosscase_prior_directory_rejected(self):
        self.configure_final(True)
        self.bundle["own_D0_stage_directory"] = str(self.prior["folder"].parent / "ubs_june_2026__L__D0")
        self.write(self.bundle_path, self.bundle)
        with self.assertRaisesRegex(ValueError, "Own D0 stage identity"):
            self.result()

    def test_prior_declaration_cannot_point_at_current_run(self):
        self.configure_final(True)
        self.bundle["own_D0_declaration_ref"] = self.declaration_ref
        self.write(self.bundle_path, self.bundle)
        with self.assertRaisesRegex(ValueError, "Wrong artifact role"):
            self.result()

    def test_external_history_must_not_be_labelled_same_run(self):
        self.configure_final(True)
        self.bundle["own_D0_origin"] = "same_remaining_run"
        self.write(self.bundle_path, self.bundle)
        with self.assertRaisesRegex(ValueError, "provenance differs"):
            self.result()

    def test_prior_numerical_mismatch_remains_reported(self):
        self.configure_final(True)
        self.prior["math"]["rows"][0]["final_units"] = 909
        self.write(self.prior["math_path"], self.prior["math"])
        result = self.result()
        self.assertFalse(result["accepted_own_D0_sidecar_comparison"]["matches"])
        self.assertTrue(result["accepted_sidecar_comparison"]["matches"])

    def test_missing_external_sidecar_is_not_invented(self):
        self.configure_final(True)
        self.prior["math_path"].unlink()
        with self.assertRaises(OSError):
            self.result()


if __name__ == "__main__":
    unittest.main(verbosity=2)
