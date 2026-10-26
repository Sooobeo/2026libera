"""Adversarial offline recovery checks. All responses/review fixtures are synthetic.

No real model requests, semantic accuracy claims, or production freeze writes.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import prepare_sector_v494 as preparation
import sector_v492_runtime as historical
import sector_v494_runtime as runtime
import sector_v494_review_gate as gate
import test_sector_v492_runtime as original_tests


class PreparedFixture:
    def prepare_fixture(self):
        (runtime.ROOT / "tmp").mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="v494_recovery_test_", dir=runtime.ROOT / "tmp")
        self.addCleanup(temporary.cleanup)
        self.prepared_root = Path(temporary.name)
        self.old_bundle, self.old_cases = historical.load_bundle()
        prompt = copy.deepcopy(self.old_bundle["prompt_contract"])
        prompt["protocol_version"] = "4.9.4"
        candidate = self.prepared_root / "synthetic_candidate.json"
        candidate.write_text(json.dumps({"prompt_contract": prompt}), encoding="utf-8")
        p = patch.object(preparation, "PROMPT_CANDIDATE", candidate)
        p.start(); self.addCleanup(p.stop)
        self.prepared_dir = self.prepared_root / "prepared_design"
        self.prepared_manifest = preparation.prepare(self.prepared_dir)
        p = patch.object(runtime, "MANIFEST", self.prepared_dir / "prepared/preparation_manifest.json")
        p.start(); self.addCleanup(p.stop)
        p = patch.object(original_tests, "runtime", runtime)
        p.start(); self.addCleanup(p.stop)


class V494RuntimeTests(PreparedFixture, original_tests.RuntimeTests):
    """Reuse every v492 adversarial runtime test against the new runtime module."""
    def setUp(self):
        self.prepare_fixture()
        super().setUp()

    def transport(self, calls, **kwargs):
        inherited_transport = super().transport(calls, **kwargs)
        def persisted_transport(**parameters):
            result = inherited_transport(**parameters)
            if result.get("response") is None:
                target = runtime.expected_stage_directory(parameters["spec"])
                target.mkdir()
                runtime.remote.save(target / "worker_spec.json", parameters["spec"])
                runtime.remote.save(target / "transport_result.json", result)
            return result
        return persisted_transport

    def persist_completed_stage(self, spec, raw):
        result = super().persist_completed_stage(spec, raw)
        target = runtime.expected_stage_directory(spec)
        checked = runtime.validate_spec(spec)
        validation = runtime.contract.validate_response(raw, response_schema=spec["body"]["format"],
            visible_evidence_ids=checked["visible_evidence_ids"], expected_source_packet=checked["expected_source_packet"])
        runtime.remote.save(target / "response_contract_validation.json", validation)
        return result

    def persisted_with_validation(self, spec, raw):
        result = self.persist_completed_stage(spec, raw)
        target = runtime.expected_stage_directory(spec)
        validation = runtime.remote.read(target / "response_contract_validation.json")
        continuation = validation["continuation_eligible"]
        result.update(status="completed" if continuation else "model_structure_failure", continuation_eligible=continuation)
        worker = result["supervisor"]["worker"]
        worker.update(status=result["status"], continuation_eligible=continuation)
        for name, value in (("worker_summary.json", worker), ("supervisor_result.json", result["supervisor"]), ("transport_result.json", result)):
            (target / name).write_text(json.dumps(value), encoding="utf-8")
        return result

    def test_preparation_retains_common_evidence_schema_and_source_timing(self):
        loaded, cases = runtime.load_bundle()
        self.assertEqual(loaded["response_schema"], self.old_bundle["response_schema"])
        self.assertEqual([c["case_id"] for c in cases], list(historical.CASES))
        for old, new in zip(self.old_cases, cases):
            before = json.loads(old["messages"][1]["content"])
            after = json.loads(new["messages"][1]["content"])
            for key in ("common_context", "common_market", "public_numeric_fact_index", "response_schema", "institution_document"):
                self.assertEqual(before.get(key), after.get(key), (new["case_id"], key))
        self.assertEqual(cases[1]["messages"], cases[3]["messages"])
        self.assertEqual(cases[1]["messages"], cases[4]["messages"])

    def test_preparation_refuses_overwrite_and_preserves_historical_bytes(self):
        paths = [historical.MANIFEST, runtime.ROOT / "research/sector_v492_runtime.py",
                 runtime.ROOT / "research/sector_v492_contract.py",
                 runtime.ROOT / "research/v492_pilot_freeze_20261019.json"]
        before = {str(p): runtime.remote.sha(p) for p in paths}
        with self.assertRaises(FileExistsError):
            preparation.prepare(self.prepared_dir)
        self.assertEqual(before, {str(p): runtime.remote.sha(p) for p in paths})

    def test_tampered_prepared_message_denied_even_with_rehashed_manifest(self):
        manifest_path = runtime.MANIFEST
        manifest = runtime.remote.read(manifest_path)
        item = manifest["prepared_cases"][1]
        path = preparation.paths.workspace_path(item["path"])
        messages = runtime.remote.read(path)
        payload = json.loads(messages[1]["content"])
        payload["institution_document"] = self.old_cases[1]["assigned_packet"]
        messages[1]["content"] = json.dumps(payload)
        path.write_text(json.dumps(messages), encoding="utf-8")
        item["sha256"] = runtime.remote.sha(path)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "reconstructed public inputs"):
            runtime.load_bundle()

    def test_tampered_completed_response_stops_before_next_model_stage(self):
        target = self.declaration()
        calls = []
        original = self.transport(calls)
        def tampering_transport(**kwargs):
            result = original(**kwargs)
            response_path = Path(result["response_artifact"]["path"])
            response_path.write_bytes(response_path.read_bytes() + b" ")
            return result
        summary = runtime.run_pilot(target, transport=tampering_transport)
        self.assertEqual(len(calls), 1)
        self.assertEqual(summary["status"], "stopped")
        self.assertEqual(len(summary["cases"]), 5)

    def test_each_stage_records_error_integrity_and_topic_review(self):
        from review_sector_v494_stage import review_and_record
        spec = self.spec()
        raw = original_tests.response_for(spec, broken_sum=True, invented_citation=True)
        result = self.persist_completed_stage(spec, raw)
        review = review_and_record(spec, runtime.expected_stage_directory(spec), result)
        self.assertTrue(review["instrument_integrity_pass"])
        for axis in ("errors", "consistency", "paper_topic"):
            self.assertIn(axis, review["review_axes"])
            self.assertTrue(review["review_axes"][axis]["reason"].strip())
        self.assertFalse(review.get("semantic_support_verified", False))

    def test_model_vector_failure_is_retained_without_integrity_halt(self):
        from review_sector_v494_stage import review_and_record
        spec = self.spec()
        obj = json.loads(original_tests.response_for(spec))
        obj["sectors"][1]["sector_code"] = obj["sectors"][0]["sector_code"]
        result = self.persisted_with_validation(spec, json.dumps(obj))
        self.assertEqual(result["status"], "model_structure_failure")
        review = review_and_record(spec, runtime.expected_stage_directory(spec), result)
        self.assertTrue(review["instrument_integrity_pass"])
        self.assertFalse(review["diagnostics"]["arithmetic_valid"])

    def test_schema_failure_with_numeric_vector_is_not_instrument_failure(self):
        from review_sector_v494_stage import review_and_record
        spec = self.spec()
        obj = json.loads(original_tests.response_for(spec))
        del obj["context_assessment"]
        result = self.persisted_with_validation(spec, json.dumps(obj))
        self.assertEqual(result["status"], "model_structure_failure")
        review = review_and_record(spec, runtime.expected_stage_directory(spec), result)
        self.assertTrue(review["instrument_integrity_pass"])

    def test_budget_tolerance_boundary_preserves_frozen_float_policy(self):
        from review_sector_v494_stage import review_and_record
        spec = self.spec()
        obj = json.loads(original_tests.response_for(spec))
        for row in obj["sectors"]:
            row["weight"] = 0
        obj["sectors"][0]["weight"] = 0.999999
        result = self.persisted_with_validation(spec, json.dumps(obj))
        review = review_and_record(spec, runtime.expected_stage_directory(spec), result)
        self.assertTrue(review["instrument_integrity_pass"])
        self.assertEqual(review["diagnostics"]["raw_sum_decimal"], "0.999999")
        self.assertFalse(review["diagnostics"]["arithmetic_valid"])

    def test_duplicate_json_keys_do_not_become_a_valid_allocation(self):
        from review_sector_v494_stage import review_and_record
        spec = self.spec()
        obj = json.loads(original_tests.response_for(spec))
        raw = '{"source_id": "duplicate", ' + json.dumps(obj)[1:]
        result = self.persisted_with_validation(spec, raw)
        review = review_and_record(spec, runtime.expected_stage_directory(spec), result)
        self.assertTrue(review["instrument_integrity_pass"])
        self.assertNotEqual(review["diagnostics"].get("arithmetic_valid"), True)

    def test_valid_stage_directory_name_in_other_run_is_rejected(self):
        from review_sector_v494_stage import review_and_record
        spec = self.spec()
        result = self.persist_completed_stage(spec, original_tests.response_for(spec))
        target = runtime.expected_stage_directory(spec)
        original_run = self.root / "different_run"
        original_run.mkdir()
        moved = original_run / target.name
        target.rename(moved)
        result["response_artifact"] = runtime.artifact_ref(moved / "http_0001_generation/response.json")
        (moved / "transport_result.json").write_text(json.dumps(result), encoding="utf-8")
        review = review_and_record(spec, moved, result)
        self.assertFalse(review["instrument_integrity_pass"])


class V494GateTests(PreparedFixture, unittest.TestCase):
    def setUp(self):
        self.prepare_fixture()
        original_tests.RuntimeTests.setUp(self)
        self.code = self.root / "synthetic_code.py"
        self.code.write_text("# SYNTHETIC TEST ONLY\n", encoding="utf-8")
        p = patch.object(gate, "REQUIRED_CODE_PATHS", {self.code.relative_to(runtime.ROOT).as_posix()})
        p.start(); self.addCleanup(p.stop)
        # The runtime fixture mocks its imported gate; these tests call the real
        # new gate directly. The genuine historical gate is read and verified.
        self.instruction = {"exact_text": "다 진행해봐.\n배분,인용 오류 점검 및 새 파일럿 검증하는건 한 단계 할 때마다 오류,정합성, 소논문 주제와의 연결성이 너무 멀어지지 않는지 다 확인하면서 진행해",
                            "timestamp_kind": "recorded_after_user_message", "recorded_at_utc": "2026-10-25T00:00:00Z",
                            "scope": "SYNTHETIC UNIT TEST ONLY"}
        self.prompt_ref = self.ref(self.prepared_dir / "prompt_contract.json")
        self.objects = {
            "input_protocol_ref": {"protocol_version": "4.9.1"},
            "evaluation_protocol_ref": {"protocol_version": "4.9.2"},
            "source_review_ref": {"status": "completed_ai_preoutput_source_review"},
            "method_review_ref": {"status": "PASS", "synthetic": True},
            "runtime_ref": self.config,
            "prepared_manifest_ref": self.prepared_manifest,
        }
        self.reviews = [self.save("review_" + str(i) + ".json", {
            "status": "PASS", "completed_at_utc": "2026-10-25T00:01:00Z", "input_refs": [],
            "review_axes": {axis: {"pass": True, "reason": "SYNTHETIC TEST ONLY"} for axis in ("errors", "consistency", "paper_topic")}}) for i in range(3)]
        self.freeze = {"freeze_version": "v494_development_freeze_1", "protocol_version": "4.9.4",
            "status": "frozen_for_pilot_only", "main_allowed": False, "user_instruction": self.instruction,
            "case_order": gate.CASE_ORDER, "controls": gate.CONTROLS, "code_refs": [self.ref(self.code)],
            "stage_review_refs": self.reviews, "recorded_at_utc": "2026-10-25T00:02:00Z"}
        self.receipt = {"receipt_version": "v494_development_gate_1", "status": "approved_for_pilot_before_generation",
            "review_mode": "AI_delegated_by_user", "main_allowed": False, "pilot_cases": gate.CASE_ORDER,
            "old_outputs_observed": True, "new_run_research_calls_before_freeze": 0,
            "user_instruction": self.instruction, "recorded_at_utc": "2026-10-25T00:03:00Z",
            "stage_review_refs": self.reviews,
            "historical_gate_ref": self.ref(runtime.ROOT / "research/v492_ai_review_gate_20261019.json")}

    def ref(self, path):
        return {"path": Path(path).relative_to(runtime.ROOT).as_posix(), "sha256": runtime.remote.sha(path)}

    def save(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return self.ref(path)

    def write(self):
        refs = {name: self.save(name + ".json", value) for name, value in self.objects.items()}
        refs["prompt_contract_ref"] = self.prompt_ref
        self.freeze.update(refs); self.receipt.update(refs)
        self.receipt["freeze_ref"] = self.save("new_freeze.json", self.freeze)
        self.save("new_gate.json", self.receipt)
        return self.root / "new_gate.json"

    def test_explicit_development_gate_passes_without_claiming_human_review(self):
        result = gate.validate_review_gate(self.write(), runtime=self.config)
        self.assertTrue(result["old_outputs_observed"])
        self.assertFalse(result["independent_human_review_completed"])

    def test_changed_code_or_prompt_after_freeze_denied(self):
        for target in (self.code, self.prepared_dir / "prompt_contract.json"):
            path = self.write(); original = target.read_bytes()
            target.write_bytes(original + b" ")
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "artifact changed"):
                gate.validate_review_gate(path)
            target.write_bytes(original)

    def test_runtime_controls_and_engine_cannot_change(self):
        original = copy.deepcopy(self.config)
        for key, value in (("temperature", 0.4), ("num_gpu", False), ("num_predict", 1024)):
            self.config["options"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                gate.validate_review_gate(self.write(), runtime=self.config)
            self.config.clear(); self.config.update(copy.deepcopy(original))
        self.config["engine_version"] = "unreviewed"
        with self.assertRaises(ValueError):
            gate.validate_review_gate(self.write(), runtime=self.config)

    def test_new_call_count_requires_integer_zero(self):
        for value in (False, 0.0, 1):
            self.receipt["new_run_research_calls_before_freeze"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                gate.validate_review_gate(self.write())

    def test_missing_topic_axis_or_postfreeze_review_denied(self):
        path = self.write()
        review_path = preparation.paths.workspace_path(self.reviews[0]["path"])
        original = runtime.remote.read(review_path)
        for change in ("missing_axis", "late_review"):
            changed = copy.deepcopy(original)
            if change == "missing_axis":
                del changed["review_axes"]["paper_topic"]
            else:
                changed["completed_at_utc"] = "2026-10-25T00:04:00Z"
            review_path.write_text(json.dumps(changed), encoding="utf-8")
            self.reviews[0].update(self.ref(review_path))
            with self.subTest(change=change), self.assertRaises(ValueError):
                gate.validate_review_gate(self.write())


if __name__ == "__main__":
    unittest.main()
