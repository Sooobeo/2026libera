"""Synthetic stage fixtures only; no generation/service calls or old global patches."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import prepare_main_stage_semantic_audit as audit
from test_build_campaign_masked_review import MaskFixture
from test_finalize_sector_campaign import digest_tree, read_json, ref, write_json


class MainStageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="main-stage-audit-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.f = MaskFixture(self.base, "main")
        self.case = self.f.cases[0]
        rubric_path = self.base / "rubric.json"
        rubric_path.write_bytes((audit.ROOT / audit.RUBRIC["path"]).read_bytes())
        for name, value in (("ROOT", self.base), ("RUBRIC", ref(rubric_path))):
            context = patch.object(audit, name, value)
            context.start()
            self.addCleanup(context.stop)
        context = patch.object(audit, "validate_main_spec")
        self.validate = context.start()
        self.addCleanup(context.stop)

    def changed_spec(self, directory, edit):
        path = directory / "worker_spec.json"
        spec = read_json(path)
        edit(spec)
        write_json(path, spec)
        self.f.f.raw.refresh_review(directory)

    def rewrite_response(self, directory, raw, status="model_structure_failure"):
        response_path = directory / "http_0001_generation/response.json"
        response = read_json(response_path)
        response["message"]["content"] = raw
        response_ref = write_json(response_path, response)
        transport_path = directory / "transport_result.json"
        transport = read_json(transport_path)
        transport.update(response=response, response_artifact=response_ref, status=status)
        write_json(transport_path, transport)
        self.f.f.raw.refresh_review(directory)

    def test_complete_raw_evidence_bundle_is_pending_and_read_only(self):
        directory = self.f.stage(self.case, "D0", first="0.7", second="0.5")
        before = digest_tree(self.f.run)
        result = audit.prepare(directory)
        self.assertEqual(before, digest_tree(self.f.run))
        self.assertEqual(result["semantic_review_status"], "pending_actual_AI_reading")
        self.assertEqual(result["coverage"]["semantic_rows_read"], 0)
        self.assertFalse(result["normalization_performed"])
        self.assertEqual(result["actual_current_payload"]["institution_document"]["source_id"], "fidelity_q3_2026")
        self.assertEqual(result["raw_response_text"], read_json(directory / "http_0001_generation/response.json")["message"]["content"])
        self.assertNotIn("sector_rows", result)
        self.validate.assert_called_once()

    def test_noncomplete_guard_does_not_open_worker_or_saved_response(self):
        directory = self.f.stage(self.case, "D0")
        transport_path = directory / "transport_result.json"
        transport = read_json(transport_path)
        transport["status"] = "case_timeout"
        write_json(transport_path, transport)
        (directory / "worker_spec.json").unlink()
        (directory / "http_0001_generation/response.json").unlink()
        result = audit.prepare(directory)
        self.assertEqual(result["status"], "unavailable_for_completed_output_review")
        self.assertNotIn("raw_response_text", result)
        self.validate.assert_not_called()

    def test_instrument_failure_does_not_extract_saved_text(self):
        directory = self.f.stage(self.case, "D0")
        review_path = directory / "stage_review.json"
        review = read_json(review_path)
        review["instrument_integrity_pass"] = False
        write_json(review_path, review)
        (directory / "worker_spec.json").unlink()
        result = audit.prepare(directory)
        self.assertEqual(result["semantic_review_status"], "not_assessed")
        self.validate.assert_not_called()

    def test_missing_durable_review_refuses_stage(self):
        directory = self.f.stage(self.case, "D0")
        (directory / "stage_review.json").unlink()
        with self.assertRaises(FileNotFoundError):
            audit.prepare(directory)
        self.validate.assert_not_called()

    def test_structure_failure_preserves_malformed_text(self):
        directory = self.f.stage(self.case, "D0")
        self.rewrite_response(directory, "not a JSON submission")
        result = audit.prepare(directory)
        self.assertEqual(result["raw_response_text"], "not a JSON submission")
        self.assertIsNotNone(result["output_parse_diagnostic"])
        self.assertEqual(result["semantic_review_status"], "pending_actual_AI_reading")

    def test_large_finite_literal_remains_exact_raw_and_serializable(self):
        directory = self.f.stage(self.case, "D0")
        self.rewrite_response(directory, '{"unexpected":1e400}')
        result = audit.prepare(directory)
        self.assertEqual(result["raw_response_text"], '{"unexpected":1e400}')
        self.assertIn("binary-float range", result["output_parse_diagnostic"])
        json.dumps(result, allow_nan=False)

    def test_own_actual_D0_and_feedback_are_retained(self):
        draft = self.f.stage(self.case, "D0")
        final = self.f.stage(self.case, "F0")
        result = audit.prepare(final)
        self.assertEqual(result["own_prior_raw_text"], read_json(draft / "http_0001_generation/response.json")["message"]["content"])
        self.assertIn("actual_draft_calculator_feedback", result["actual_current_payload"])

    def test_cross_run_response_ref_is_rejected(self):
        directory = self.f.stage(self.case, "D0")
        response_path = directory / "http_0001_generation/response.json"
        other_ref = write_json(self.base / "another_run/response.json", read_json(response_path))
        transport_path = directory / "transport_result.json"
        transport = read_json(transport_path)
        transport["response_artifact"] = other_ref
        write_json(transport_path, transport)
        self.f.f.raw.refresh_review(directory)
        with self.assertRaisesRegex(ValueError, "another run, case or role"):
            audit.prepare(directory)

    def test_cross_case_worker_identity_is_rejected(self):
        directory = self.f.stage(self.case, "D0")
        self.changed_spec(directory, lambda spec: spec.update(case_id=self.f.cases[1]))
        with self.assertRaisesRegex(ValueError, "Stage review identity mismatch"):
            audit.prepare(directory)
        review_path = directory / "stage_review.json"
        review = read_json(review_path)
        review["case_id"] = self.case
        write_json(review_path, review)
        with self.assertRaisesRegex(ValueError, "case/stage/run"):
            audit.prepare(directory)

    def test_wrong_final_source_identity_is_rejected(self):
        self.f.stage(self.case, "D0")
        final = self.f.stage(self.case, "F0")
        def edit(spec):
            payload = json.loads(spec["body"]["messages"][3]["content"])
            payload["institution_document"]["source_id"] = "ubs_july_2026"
            spec["body"]["messages"][3]["content"] = json.dumps(payload)
        self.changed_spec(final, edit)
        with self.assertRaisesRegex(ValueError, "source identity/timing"):
            audit.prepare(final)

    def test_prior_response_from_other_case_is_rejected(self):
        self.f.stage(self.case, "D0")
        final = self.f.stage(self.case, "F0")
        other = self.f.stage(self.f.cases[1], "D0")
        self.changed_spec(final, lambda spec: spec["draft_artifacts"].update(response=ref(other / "http_0001_generation/response.json")))
        with self.assertRaisesRegex(ValueError, "another run, case or role"):
            audit.prepare(final)

    def test_candidate_authority_is_rejected_before_runtime_validation(self):
        self.f.f.gate.update(status="CANDIDATE_ONLY_NOT_MAIN_READY_NOT_APPROVED", main_allowed=False)
        self.f.f.sync()
        directory = self.f.stage(self.case, "D0")
        with self.assertRaisesRegex(ValueError, "Candidate or continuation authority"):
            audit.prepare(directory)
        self.validate.assert_not_called()

    def test_runtime_validation_failure_cannot_be_bypassed(self):
        directory = self.f.stage(self.case, "D0")
        self.validate.side_effect = ValueError("Synthetic stale full main gate")
        with self.assertRaisesRegex(ValueError, "stale full main gate"):
            audit.prepare(directory)

    def test_math_sidecar_is_bound_read_only_without_certification(self):
        directory = self.f.stage(self.case, "D0")
        refs = [ref(directory / name) for name in ("worker_spec.json", "transport_result.json", "http_0001_generation/response.json")]
        sidecar = self.base / "derived_math.json"
        write_json(sidecar, {"case_id": self.case, "stage": "D0", "status": "finalized", "input_refs": refs, "final_total_units": 10000})
        before = sidecar.read_bytes()
        result = audit.prepare(directory, sidecar)
        self.assertEqual(sidecar.read_bytes(), before)
        self.assertEqual(result["observed_math_sidecar"]["final_total_units"], 10000)
        self.assertIn("math not recomputed", result["math_sidecar_scope"])
        self.assertFalse(result["normalization_performed"])

    def test_other_case_math_sidecar_refused(self):
        directory = self.f.stage(self.case, "D0")
        sidecar = self.base / "derived_math.json"
        write_json(sidecar, {"case_id": self.f.cases[1], "stage": "D0", "input_refs": []})
        with self.assertRaisesRegex(ValueError, "another case or stage"):
            audit.prepare(directory, sidecar)

    def test_source_free_L_and_C_have_no_invented_source(self):
        for case in (self.f.cases[1], self.f.cases[-1]):
            result = audit.prepare(self.f.stage(case, "D0"))
            self.assertNotIn("institution_document", result["actual_current_payload"])

    def test_original_helper_bytes_and_global_root_unchanged(self):
        original_root = audit._pure.ROOT
        audit.prepare(self.f.stage(self.case, "D0"))
        self.assertEqual(audit._pure.ROOT, original_root)
        self.assertEqual(hashlib.sha256(audit.PURE_HELPER.read_bytes()).hexdigest(), audit.PURE_HELPER_SHA)


if __name__ == "__main__":
    unittest.main()
