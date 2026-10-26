"""Offline fixture tests; no runtime imports or model/service requests."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("audit_bundle", Path(__file__).with_name("prepare_stage_semantic_audit.py"))
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patch = patch.object(audit, "ROOT", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.tmp.cleanup)
        self.run = self.root / "run"
        self.run.mkdir()
        self.case = audit.CASES[0]
        self.initial = {"common_context": {"evidence_id": "CTX:task"},
                        "common_market": {"sector_codes": list(audit.CODES), "baseline_weights": dict.fromkeys(audit.CODES, .1)},
                        "public_numeric_fact_index": {"columns": ["fact_id", "value"], "rows": [["M:a:10", .1]]},
                        "institution_document": None}
        self.messages = [{"role": "system", "content": "fixed"}, {"role": "user", "content": json.dumps(self.initial)}]
        prepared = self.write(self.root / "prepared.json", self.messages)
        self.packet = {"source_id": "fidelity_q2_2026", "rating_vocabulary": ["Neutral"], "evidence_table": {
            "columns": ["evidence_id", "source_page", "text"], "rows": [
                ["fidelity_q2_2026:p3:sector:" + code, 3, "Sector receives Neutral. Balanced."] for code in audit.CODES]}}
        aggregate_ref = self.write(self.root / "aggregate.json", {"public_source_packets": {"fidelity_q2_2026": self.packet}})
        manifest = self.write(self.root / "manifest.json", {"prepared_cases": [{"case_id": self.case, "stage": "D0", **prepared}],
            "inputs": {"public_aggregate_never_sent": aggregate_ref}})
        self.write(self.run / "campaign_declaration.json", {"purpose": "pilot_continuation", "case_order": list(audit.CASES), "prepared_manifest_ref": manifest})
        rubric = self.write(self.root / "rubric.json", {"fixture": "rubric"})
        self.rubric_patch = patch.object(audit, "RUBRIC_REF", rubric)
        self.rubric_patch.start()
        self.addCleanup(self.rubric_patch.stop)

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(value).encode()
        path.write_bytes(raw)
        return {"path": path.relative_to(self.root).as_posix(), "sha256": hashlib.sha256(raw).hexdigest()}

    def output(self):
        return {"source_id": None, "sectors": [{"sector_code": code, "weight": .1 if i < 10 else 0,
                "source_label": None, "source_stance": "not_available", "source_reading": "No source available.",
                "source_evidence_ids": [], "decision_reason": "Use supplied market facts.", "decision_evidence_ids": ["M:a:10"]}
                for i, code in enumerate(audit.CODES)]}

    def stage(self, stage="D0", raw=None, status="completed", integrity=True, prior=None):
        directory = self.run / (self.case + "__" + stage)
        raw = json.dumps(self.output()) if raw is None else raw
        response = {"done": True, "done_reason": "stop", "message": {"content": raw}}
        response_ref = self.write(directory / "http_0001_generation" / "response.json", response)
        messages = self.messages.copy()
        spec = {"case_id": self.case, "stage": stage, "run_directory": str(self.run), "body": {"messages": messages}}
        if stage == "F0":
            prior_response = json.loads((prior / "http_0001_generation" / "response.json").read_text())
            prior_text = prior_response["message"]["content"]
            prior_ref = self.ref(prior / "http_0001_generation" / "response.json")
            final = {"institution_document": self.packet, "actual_draft_calculator_feedback": {"sum": 1}}
            messages.extend([{"role": "assistant", "content": prior_text}, {"role": "user", "content": json.dumps(final)}])
            spec.update(raw_draft=prior_text, draft_artifacts={"response": prior_ref})
        spec_ref = self.write(directory / "worker_spec.json", spec)
        transport_ref = self.write(directory / "transport_result.json", {"status": status, "generation_requests_attempted": 1,
            "response_artifact": response_ref, "response": response})
        self.write(directory / "stage_review.json", {"case_id": self.case, "stage": stage, "instrument_integrity_pass": integrity,
            "input_refs": [spec_ref, transport_ref, response_ref]})
        return directory

    def ref(self, path):
        return {"path": path.relative_to(self.root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def test_source_free_completed_has_pending_semantics_and_exact_sum(self):
        result = audit.prepare(self.stage())
        self.assertEqual(result["raw_sum_exact_decimal"], "1.0")
        self.assertEqual(result["coverage"]["semantic_rows_read"], 0)
        self.assertEqual(len(result["sector_rows"]), 11)
        self.assertTrue(all(r["source_free_field_check"] for r in result["sector_rows"]))
        self.assertEqual(result["unavailable_id_occurrences"], [])
        self.assertEqual(result["source_fidelity_applicability"], "not_applicable_no_source_supplied")

    def test_failed_stage_does_not_open_response(self):
        directory = self.stage(status="case_timeout")
        (directory / "http_0001_generation" / "response.json").unlink()
        self.assertEqual(audit.prepare(directory)["semantic_review_status"], "not_assessed")

    def test_bad_instrument_does_not_open_response(self):
        directory = self.stage(integrity=False)
        (directory / "http_0001_generation" / "response.json").unlink()
        self.assertEqual(audit.prepare(directory)["semantic_review_status"], "not_assessed")

    def test_missing_review_never_accepts_stage(self):
        directory = self.stage()
        (directory / "stage_review.json").unlink()
        with self.assertRaises(FileNotFoundError):
            audit.prepare(directory)

    def test_completed_malformed_output_preserved_for_manual_review(self):
        result = audit.prepare(self.stage(raw="not JSON", status="model_structure_failure"))
        self.assertEqual(result["raw_final_or_draft_text"], "not JSON")
        self.assertIsNotNone(result["output_json_parse_error"])
        self.assertIsNone(result["raw_sum_exact_decimal"])
        self.assertEqual(result["coverage"]["structural_sector_rows_prepared"], 0)

    def test_overflowing_finite_literal_retains_serializable_raw_bundle(self):
        raw = json.dumps(self.output())[:-1] + ', "unexpected_numeric_claim": 1e400}'
        result = audit.prepare(self.stage(raw=raw, status="model_structure_failure"))
        self.assertEqual(result["raw_final_or_draft_text"], raw)
        self.assertIn("finite binary-float range", result["output_json_parse_error"])
        self.assertEqual(result["semantic_review_status"], "pending_actual_AI_reading")
        self.assertIsNone(result["raw_sum_exact_decimal"])
        json.dumps(result, allow_nan=False)

    def test_missing_vector_does_not_invent_weights(self):
        output = self.output()
        output["sectors"].pop()
        result = audit.prepare(self.stage(raw=json.dumps(output), status="model_structure_failure"))
        self.assertIsNone(result["raw_sum_exact_decimal"])
        self.assertEqual(len(result["sector_rows"]), 10)

    def test_hash_mismatch_refused(self):
        directory = self.stage()
        path = directory / "http_0001_generation" / "response.json"
        path.write_text('{}')
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            audit.prepare(directory)

    def test_own_raw_draft_and_new_source_are_retained(self):
        draft = self.stage()
        result = audit.prepare(self.stage(stage="F0", prior=draft))
        self.assertEqual(result["own_prior_text"], result["raw_final_or_draft_text"])
        self.assertTrue(all(r["own_D0_raw_delta_exact_decimal"] in {"0", "0.0"} for r in result["sector_rows"]))
        self.assertTrue(all(r["explicit_published_label"] == "Neutral" for r in result["sector_rows"]))
        self.assertEqual(result["source_fidelity_applicability"], "applicable")

    def test_other_run_prior_ref_refused(self):
        draft = self.stage()
        final = self.stage(stage="F0", prior=draft)
        spec_path = final / "worker_spec.json"
        spec = json.loads(spec_path.read_text())
        wrong = self.root / "other_run" / "D0" / "http_0001_generation" / "response.json"
        wrong.parent.mkdir(parents=True)
        wrong.write_bytes((draft / "http_0001_generation" / "response.json").read_bytes())
        spec["draft_artifacts"]["response"] = self.ref(wrong)
        spec_ref = self.write(spec_path, spec)
        review = json.loads((final / "stage_review.json").read_text())
        review["input_refs"][0] = spec_ref
        self.write(final / "stage_review.json", review)
        with self.assertRaisesRegex(ValueError, "Unexpected bound path"):
            audit.prepare(final)

    def test_id_visibility_is_not_support(self):
        output = self.output()
        output["sectors"][0]["decision_evidence_ids"].append("invented")
        result = audit.prepare(self.stage(raw=json.dumps(output)))
        self.assertEqual(result["unavailable_id_occurrences"], [{"id": "invented", "output_pointer": "/sectors/0/decision_evidence_ids/1"}])
        self.assertEqual(result["sector_rows"][0]["semantic_category"], "pending_actual_AI_reading")

    def test_changed_final_source_packet_refused(self):
        draft = self.stage()
        final = self.stage(stage="F0", prior=draft)
        spec_path = final / "worker_spec.json"
        spec = json.loads(spec_path.read_text())
        payload = json.loads(spec["body"]["messages"][3]["content"])
        payload["institution_document"]["evidence_table"]["rows"][0][2] = "Changed institutional meaning."
        spec["body"]["messages"][3]["content"] = json.dumps(payload)
        spec_ref = self.write(spec_path, spec)
        review = json.loads((final / "stage_review.json").read_text())
        review["input_refs"][0] = spec_ref
        self.write(final / "stage_review.json", review)
        with self.assertRaisesRegex(ValueError, "differs from frozen packet"):
            audit.prepare(final)

    def test_strict_parser_rejects_duplicates_and_nonfinite(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}'):
            with self.assertRaises(ValueError):
                audit.strict(raw)

    def test_boolean_weight_rejected_and_negative_raw_retained(self):
        output = self.output()
        output["sectors"][0]["weight"] = True
        self.assertIsNotNone(audit.prepare(self.stage(raw=json.dumps(output)))["raw_vector_diagnostic_error"])
        output["sectors"][0]["weight"] = -.1
        self.assertEqual(audit.decimal_vector(audit.strict(json.dumps(output), exact=True))["10"], audit.Decimal("-.1"))

    def test_precision_preserved_beyond_default_decimal_context(self):
        left = audit.Decimal("0.123456789012345678901234567890123456789")
        right = audit.Decimal("0.000000000000000000000000000000000000001")
        self.assertEqual(str(audit.decimal_sum([left, right])), "0.123456789012345678901234567890123456790")

    def test_rating_is_explicit_not_inferred(self):
        self.assertIsNone(audit.explicit_rating("An attractive outlook.", ["Attractive", "Neutral"]))
        self.assertEqual(audit.explicit_rating("Utilities receives Attractive. Resilience.", ["Attractive", "Neutral"]), "Attractive")


if __name__ == "__main__":
    unittest.main()
