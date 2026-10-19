"""Synthetic, offline tests; no real model output is read."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import analyze_v492_pilot as a


def value(weights=None, source=None):
    weights = weights or {c: (1 if c == "10" else 0) for c in a.CODES}
    return {"source_id": source, "sectors": [
        {"sector_code": c, "weight": weights[c], "source_label": None,
         "source_reading": "No institution supplied", "source_evidence_ids": [],
         "source_stance": "not_available", "decision_reason": "Synthetic fixture",
         "decision_evidence_ids": ["common_fact"]} for c in a.CODES],
        "alternatives": "Synthetic alternative", "risk_discussion": "Synthetic risk",
        "unresolved": [], "submitted_constraints": [],
        "context_assessment": {"market_and_mandate_reading": "Synthetic context",
          "allocation_implication": "Synthetic implication", "evidence_ids": ["common_fact"],
          "limitations": "Synthetic limitation"}}


def encode(v):
    return json.dumps(v, ensure_ascii=False, allow_nan=False)


def references():
    return [{"reference_id": name, "weights": {c: (1 if c == "10" else 0) for c in a.CODES}}
            for name in ("equal_weight", "long_only_minimum_variance", "existing_market_benchmark")]


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encode(obj), encoding="utf-8")


def completed_fixture(root, cases_attempted=5):
    rows = []
    for index, case in enumerate(a.CASES):
        stages = []
        if index < cases_attempted:
            for stage in a.STAGES:
                target = root / (case + "__" + stage)
                source = None if case.endswith("__C") or (case.endswith("__L") and stage == "D0") else case.rsplit("__", 1)[0]
                response = {"done": True, "done_reason": "stop", "message": {"content": encode(value(source=source))}}
                response_path = target / "http_0001_generation/response.json"
                write(response_path, response)
                transport = {"status": "completed", "system_integrity_incident": False,
                             "generation_requests_attempted": 1,
                             "response": response, "response_artifact": {"path": str(response_path.resolve()),
                             "sha256": a.sha_bytes(response_path.read_bytes())}}
                write(target / "transport_result.json", transport)
                payload = {"common_context": {"fact_id": "common_fact"}, "public_numeric_fact_index": {}}
                if source:
                    payload["institution_document"] = {"source_id": source, "evidence_id": "source_fact"}
                write(target / "worker_spec.json", {"case_id": case, "stage": stage,
                    "body": {"messages": [{"role": "user", "content": encode(payload)}]}})
                stages.append({"stage": stage, "status": "completed", "generation_requests_attempted": 1,
                               "continuation_eligible": True})
        rows.append({"case_id": case, "status": "synthetic", "stages": stages})
    summary = {"status": "pilot_attempt_sequence_finished", "cases": rows,
               "generation_requests_attempted": cases_attempted * 2,
               "main_model_calls": 0, "automatic_retries": 0, "post_final_calls": 0}
    write(root / "pilot_summary.json", summary)
    return summary


class ArithmeticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = a.read_json(a.ROOT / a.SCHEMA)[0]

    def metrics(self, v):
        return a.parse_output(encode(v), self.schema)["vector"]

    def test_concentrated_vectors_have_exact_distance_one(self):
        left = self.metrics(value())
        right = self.metrics(value({c: int(c == "15") for c in a.CODES}))
        result = a.compare(left, right, "left", "right")
        self.assertEqual(result["distance"], 1)
        self.assertEqual(result["raw_difference_exact_decimal"]["10"], "1")
        self.assertEqual(result["raw_difference_exact_decimal"]["15"], "-1")

    def test_exact_decimal_differences_not_binary_roundoff(self):
        first, second = value(), value()
        first["sectors"][0]["weight"], first["sectors"][1]["weight"] = .3, .7
        second["sectors"][0]["weight"], second["sectors"][1]["weight"] = .1, .9
        result = a.compare(self.metrics(first), self.metrics(second), "F0", "D0")
        self.assertEqual(result["distance_exact_decimal"], "0.2")
        self.assertEqual(result["raw_difference_exact_decimal"]["10"], "0.2")

    def test_bad_budget_retained_not_normalized(self):
        invalid = value(); invalid["sectors"][0]["weight"] = .8
        met = self.metrics(invalid)
        self.assertEqual(met["raw_weights"]["10"], .8)
        self.assertEqual(met["raw_sum_exact_decimal"], "0.8")
        result = a.compare(met, self.metrics(value()), "invalid", "valid")
        self.assertIsNone(result["distance"])
        self.assertEqual(result["raw_difference_exact_decimal"]["10"], "-0.2")
        self.assertFalse(met["normalized_or_repaired"])

    def test_missing_duplicate_unknown_boolean_negative(self):
        broken = []
        v = value(); v["sectors"].pop(); broken.append(v)
        v = value(); v["sectors"][1]["sector_code"] = "10"; broken.append(v)
        v = value(); v["sectors"][1]["sector_code"] = "999"; broken.append(v)
        v = value(); v["sectors"][0]["weight"] = True; broken.append(v)
        v = value(); v["sectors"][0]["weight"] = 1.1; v["sectors"][1]["weight"] = -.1; broken.append(v)
        for case in broken:
            with self.subTest(case=case):
                self.assertFalse(self.metrics(case)["distance_eligible"])

    def test_entire_json_required_no_code_fence_or_partial_extraction(self):
        for raw in (encode(value())[:-1], "```json\n" + encode(value()) + "\n```",
                    encode(value()) + encode(value()), '[{"sectors":[]}]', '{"x":1,"x":2}'):
            result = a.parse_output(raw, self.schema)
            self.assertFalse(result["parseable"])
            self.assertFalse(result["vector"]["distance_eligible"])

    def test_nonfinite_numbers_rejected(self):
        for raw in (encode(value()).replace('"weight": 1', '"weight": NaN', 1),
                    encode(value()).replace('"weight": 1', '"weight": 1e400', 1)):
            self.assertFalse(a.parse_output(raw, self.schema)["parseable"])

    def test_explanatory_schema_failure_does_not_censor_vector(self):
        v = value(); del v["risk_discussion"]
        result = a.parse_output(encode(v), self.schema)
        self.assertTrue(result["parseable"])
        self.assertFalse(result["schema_valid"])
        self.assertTrue(result["vector"]["distance_eligible"])

    def test_tolerance_is_not_normalization_or_exact_unit_sum(self):
        v = value(); v["sectors"][0]["weight"] = 1.0000005
        metrics = self.metrics(v)
        self.assertTrue(metrics["distance_eligible"])
        self.assertFalse(metrics["valid_raw_allocation"])
        result = a.compare(metrics, self.metrics(value()), "raw", "unit")
        self.assertEqual(result["distance_exact_decimal"], "0.00000025")
        self.assertIn("approximation", result["interpretation"])

    def test_citations_cannot_authorize_themselves_from_assistant_text(self):
        spec = {"body": {"messages": [
            {"role": "user", "content": encode({"common_context": {"fact_id": "common_fact"}})},
            {"role": "assistant", "content": encode({"fact_id": "fabricated"})},
            {"role": "user", "content": encode({"actual_draft_calculator_feedback": {}})}]}}
        ids, sources = a.stage_evidence(spec)
        self.assertEqual(ids, {"common_fact"})
        self.assertEqual(sources, [])
        v = value(); v["sectors"][0]["decision_evidence_ids"] = ["fabricated"]
        self.assertEqual(a.citation_diagnostics(encode(v), ids)["unavailable_citations"][0]["id"], "fabricated")

    def test_lossless_table_evidence_ids(self):
        ids = a.declared_evidence_ids({"columns": ["fact_id", "value"], "rows": [["table_fact", 2]]})
        self.assertEqual(ids, {"table_fact"})

    def test_completion_marker_gate_before_opening_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(a, "read_json", side_effect=AssertionError("must not open any file")):
                with self.assertRaisesRegex(ValueError, "pilot_summary.json absent"):
                    a.analyze(tmp)

    def test_all_five_and_ten_denominators_with_missing_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            completed_fixture(Path(tmp), cases_attempted=1)
            result = a.analyze(tmp)
            self.assertEqual(result["denominators"]["planned_final_sector_rows"], 55)
            self.assertEqual(result["final_coverage"]["planned"], 5)
            self.assertEqual(result["final_coverage"]["not_attempted"], 4)
            self.assertEqual(result["all_stage_coverage"]["attempted"], 2)
            self.assertIsNone(result["shared_control_comparisons"][0]["distance"])
            self.assertEqual(result["eligible_within_source_pairs"], 0)

    def test_five_valid_finals_source_independent_shared_C(self):
        with tempfile.TemporaryDirectory() as tmp:
            completed_fixture(Path(tmp))
            result = a.analyze(tmp)
            self.assertEqual(result["final_coverage"]["valid_raw_allocation"], 5)
            self.assertEqual(len(result["shared_control_comparisons"]), 4)
            self.assertEqual(result["difference_of_distances"]["value"], 0)
            control = [r for r in result["stage_records"] if r["case_id"].endswith("__C")]
            self.assertEqual(len(control), 2)
            self.assertTrue(all(r["C_source_free_input"] for r in control))
            self.assertTrue(all(r["source_fidelity_applicability"] == "not_applicable" for r in control))
            self.assertEqual(result["denominators"]["shared_C_count"], 1)
            late_draft = next(r for r in result["stage_records"] if r["case_id"] == a.CASES[1] and r["stage"] == "D0")
            self.assertFalse(late_draft["source_conditioned"])
            self.assertEqual(late_draft["source_fidelity_applicability"], "not_applicable")

    def test_length_stop_valid_full_json_is_separate_from_schema_and_distance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); completed_fixture(root, 1)
            target = root / (a.CASES[0] + "__F0")
            path = target / "http_0001_generation/response.json"
            response = a.read_json(path)[0]; response["done_reason"] = "length"
            v = value(); del v["risk_discussion"]
            response["message"]["content"] = encode(v); write(path, response)
            tr = a.read_json(target / "transport_result.json")[0]
            tr.update(response=response, status="output_limit_reached")
            tr["response_artifact"]["sha256"] = a.sha_bytes(path.read_bytes()); write(target / "transport_result.json", tr)
            result = a.analyze(root)
            final = result["stage_records"][1]
            self.assertTrue(final["readable_partial"])
            self.assertFalse(final["schema_valid"])
            self.assertTrue(final["vector"]["distance_eligible"])
            self.assertEqual(final["done_reason"], "length")

    def test_response_hash_mismatch_is_not_silently_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); completed_fixture(root, 1)
            target = root / (a.CASES[0] + "__F0")
            path = target / "http_0001_generation/response.json"
            path.write_bytes(path.read_bytes() + b" ")
            final = a.analyze(root)["stage_records"][1]
            self.assertFalse(final["response_artifact_bound"])
            self.assertFalse(final["vector"]["distance_eligible"])
            self.assertIn("binding_failed", final["artifact_issue"])

    def test_spec_identity_mismatch_does_not_keep_an_eligible_vector(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); completed_fixture(root, 1)
            path = root / (a.CASES[0] + "__F0") / "worker_spec.json"
            spec = a.read_json(path)[0]; spec["case_id"] = a.CASES[2]; write(path, spec)
            final = a.analyze(root)["stage_records"][1]
            self.assertTrue(final["response_artifact_bound"])
            self.assertFalse(final["vector"]["distance_eligible"])
            self.assertIn("case_stage_mismatch", final["artifact_issue"])

    def test_institution_in_C_input_is_integrity_issue_not_zero_fidelity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); completed_fixture(root)
            path = root / (a.CASES[-1] + "__F0") / "worker_spec.json"
            spec = a.read_json(path)[0]
            payload = json.loads(spec["body"]["messages"][0]["content"])
            payload["institution_document"] = {"source_id": "fidelity_q2_2026"}
            spec["body"]["messages"][0]["content"] = encode(payload); write(path, spec)
            final = a.analyze(root)["stage_records"][-1]
            self.assertFalse(final["C_source_free_input"])
            self.assertFalse(final["vector"]["distance_eligible"])
            self.assertEqual(final["source_fidelity_applicability"], "not_applicable")

    def test_duplicate_case_and_attempt_boolean_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); summary = completed_fixture(root, 1)
            original = copy.deepcopy(summary)
            summary["cases"][-1]["case_id"] = summary["cases"][0]["case_id"]
            write(root / "pilot_summary.json", summary)
            with self.assertRaisesRegex(ValueError, "five_planned"):
                a.analyze(root)
            original["cases"][0]["stages"][0]["generation_requests_attempted"] = True
            write(root / "pilot_summary.json", original)
            with self.assertRaisesRegex(ValueError, "zero_or_one"):
                a.analyze(root)

    def test_zero_call_capacity_failure_is_not_erased(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); summary = completed_fixture(root, 0)
            summary["cases"][0]["stages"] = [{"stage": "D0", "status": "context_capacity_failure",
                "generation_requests_attempted": 0, "continuation_eligible": False}]
            write(root / "pilot_summary.json", summary)
            write(root / (a.CASES[0] + "__D0") / "transport_result.json",
                  {"status": "context_capacity_failure", "generation_requests_attempted": 0,
                   "system_integrity_incident": True, "response": None})
            report = a.analyze(root)
            self.assertEqual(report["all_stage_coverage"]["attempted"], 0)
            self.assertEqual(report["all_stage_coverage"]["infrastructure_failure"], 1)
            self.assertTrue(report["stage_records"][0]["system_integrity_incident"])

    def test_expected_timeout_partial_text_is_not_repaired_or_called_corrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); summary = completed_fixture(root, 0)
            summary["generation_requests_attempted"] = 1
            summary["cases"][0]["stages"] = [{"stage": "D0", "status": "case_timeout",
                "generation_requests_attempted": 1, "continuation_eligible": False}]
            write(root / "pilot_summary.json", summary)
            target = root / (a.CASES[0] + "__D0")
            write(target / "transport_result.json", {"status": "case_timeout", "generation_requests_attempted": 1,
                "system_integrity_incident": False, "response": None, "response_artifact": None})
            write(target / "http_0001_generation/assembled_text.json", {"content": encode(value())[:-1]})
            report = a.analyze(root); first = report["stage_records"][0]
            self.assertTrue(first["readable_partial"])
            self.assertFalse(first["artifact_integrity_failure"])
            self.assertFalse(first["parseable"])
            self.assertFalse(first["vector"]["distance_eligible"])


if __name__ == "__main__":
    unittest.main()
