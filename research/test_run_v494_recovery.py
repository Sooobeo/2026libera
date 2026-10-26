"""Synthetic tests only: no real launch, HTTP, semantic scoring or shutdown."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_v494_recovery as runner
import build_v494_masked_review as bundle
import test_v492_masked_review as inherited_mask_tests


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="v494_wrapper_test_")
        self.root = Path(self.temp.name).resolve()
        self.root_patch = patch.object(runner, "ROOT", self.root)
        self.root_patch.start()
        (self.root / "research").mkdir()
        for name in ("sector_v494_runtime.py", "run_v494_recovery.py", "analyze_v492_pilot.py", "build_v494_masked_review.py"):
            (self.root / "research" / name).write_text("nonexecutable synthetic fixture", encoding="utf-8")
        for name in ("runtime.json", "gate.json"):
            runner.write_json(self.root / name, {"synthetic": True})
        (self.root / "server.log").write_text("synthetic", encoding="utf-8")
        self.args = argparse.Namespace(runtime=self.root / "runtime.json", review_gate=self.root / "gate.json",
                                       server_log=self.root / "server.log", run_dir=self.root / "run",
                                       output_root=self.root / "reports", origin="http://127.0.0.1:11436")
        self.calls = []

    def tearDown(self):
        self.root_patch.stop()
        self.temp.cleanup()

    def declaration(self, run):
        run.mkdir()
        runner.write_json(run / "pilot_declaration.json", {
            "purpose": "pilot_only", "case_order": list(runner.CASES), "max_generation_requests": 10,
            "main_model_calls": 0, "automatic_retries": 0, "AI_preoutput_review_completed": True,
            "review_mode": "AI_delegated_by_user", "frozen_for_pilot": True})

    def summary(self, run):
        value = {"status": "pilot_attempt_sequence_finished", "generation_requests_attempted": 0,
                 "main_model_calls": 0, "automatic_retries": 0, "post_final_calls": 0,
                 "cases": [{"case_id": c, "stages": [], "status": "not_attempted_after_stop"} for c in runner.CASES]}
        runner.write_json(run / "pilot_summary.json", value)
        return value

    def fake_runtime(self, fail=False, preparation_fail=False):
        test = self
        class FakeRuntime:
            def prepare_pilot(self, runtime, run, origin, server, gate):
                test.calls.append("prepare")
                if preparation_fail:
                    raise ValueError("synthetic rejected preflight")
                test.declaration(run)
            def run_pilot(self, run):
                test.calls.append("run")
                if fail:
                    folder = run / (runner.CASES[0] + "__D0")
                    generation = folder / "http_0001_generation"
                    generation.mkdir(parents=True)
                    runner.write_json(generation / "request.json", {"fixture": "attempted"})
                    runner.write_json(generation / "response.json", {"message": {"content": "partial preserved raw text"}})
                    raise RuntimeError("synthetic failure after first envelope")
                return test.summary(run)
        return FakeRuntime()

    def analyzer(self, run):
        self.calls.append("analysis")
        self.assertTrue((run / "pilot_summary.json").exists())
        return {"final_coverage": {"planned": 5}, "semantic_review": "not performed"}

    def masked(self, run, judge, private):
        self.calls.append("masked")
        judge.mkdir()
        private.mkdir()
        runner.write_json(judge / "COMPLETE.json", {"scoring_performed": False})
        return {"judge_bundle": str(judge), "private_mapping": str(private), "model_calls": 0}

    def execute(self, **kwargs):
        return runner.execute(self.args, runtime_module=kwargs.get("runtime", self.fake_runtime()),
                              analyzer=kwargs.get("analyzer", self.analyzer), masked_builder=self.masked)

    def test_clean_sequence_packages_without_semantic_or_cleanup_claim(self):
        result = self.execute()
        self.assertEqual(self.calls, ["prepare", "run", "analysis", "masked"])
        self.assertEqual(result["status"], "completed_semantic_review_pending")
        self.assertFalse(result["semantic_review"]["performed_by_wrapper"])
        self.assertFalse(result["service_cleanup"]["service_stop_attempted"])
        self.assertEqual(len(list((self.args.output_root / "events").glob("*.json"))), 6)

    def test_exception_recovers_accounting_without_binding_or_repairing_raw_response(self):
        result = self.execute(runtime=self.fake_runtime(fail=True))
        self.assertEqual(result["status"], "completed_with_errors_attention_required")
        summary = runner.read(self.args.run_dir / "pilot_summary.json")
        self.assertEqual(summary["status"], "stopped")
        self.assertEqual(summary["generation_requests_attempted"], 1)
        self.assertEqual(len(summary["cases"]), 5)
        stage = summary["cases"][0]["stages"][0]
        self.assertEqual(stage["status"], "coordinator_exception_recovered")
        self.assertFalse(stage["continuation_eligible"])
        folder = self.args.run_dir / (runner.CASES[0] + "__D0")
        receipt = runner.read(folder / "transport_result.json")
        self.assertIsNone(receipt["response_artifact"])
        self.assertIsNone(receipt["response"])
        self.assertEqual(runner.read(folder / "http_0001_generation/response.json")["message"]["content"], "partial preserved raw text")
        self.assertEqual(self.calls, ["prepare", "run", "analysis", "masked"])

    def test_existing_transport_and_terminal_never_overwritten(self):
        self.declaration(self.args.run_dir)
        folder = self.args.run_dir / (runner.CASES[0] + "__D0")
        generation = folder / "http_0001_generation"
        generation.mkdir(parents=True)
        runner.write_json(generation / "request.json", {})
        receipt = {"status": "completed", "generation_requests_attempted": 1, "continuation_eligible": True}
        runner.write_json(folder / "transport_result.json", receipt)
        original = (folder / "transport_result.json").read_bytes()
        result = runner.recover_terminal_summary(self.args.run_dir, {"type": "fixture"})
        self.assertTrue(result["created"])
        self.assertEqual((folder / "transport_result.json").read_bytes(), original)
        summary_bytes = (self.args.run_dir / "pilot_summary.json").read_bytes()
        self.assertFalse(runner.recover_terminal_summary(self.args.run_dir, {"type": "second"})["created"])
        self.assertEqual((self.args.run_dir / "pilot_summary.json").read_bytes(), summary_bytes)

    def test_failed_processor_does_not_suppress_other_processor(self):
        def broken(run):
            self.calls.append("analysis")
            raise PermissionError("synthetic filesystem failure")
        result = self.execute(analyzer=broken)
        self.assertIn("masked", self.calls)
        self.assertEqual(result["errors"][0]["step"], "analysis")
        self.assertTrue((self.args.output_root / "terminal_receipt.json").exists())

    def test_preparation_failure_has_no_fabricated_terminal_pilot(self):
        result = self.execute(runtime=self.fake_runtime(preparation_fail=True))
        self.assertEqual(self.calls, ["prepare"])
        self.assertIsNone(result["summary_ref"])
        self.assertFalse(self.args.run_dir.exists())

    def test_existing_run_refused_before_any_calls(self):
        self.args.run_dir.mkdir()
        with self.assertRaises(FileExistsError):
            self.execute()
        self.assertEqual(self.calls, [])
        self.assertFalse(self.args.output_root.exists())

    def test_second_launch_refused_no_resume(self):
        self.execute()
        calls = list(self.calls)
        with self.assertRaises(FileExistsError):
            self.execute()
        self.assertEqual(self.calls, calls)

    def test_events_and_output_names_are_immutable(self):
        self.args.output_root.mkdir()
        (self.args.output_root / "events").mkdir()
        a = runner.event(self.args.output_root, "same")
        b = runner.event(self.args.output_root, "same")
        self.assertNotEqual(a["path"], b["path"])
        with self.assertRaises(FileExistsError):
            runner.write_json(a["path"], {})

    def test_changed_processor_source_is_not_executed(self):
        fake = self.fake_runtime()
        original_run = fake.run_pilot
        def changed(run):
            result = original_run(run)
            (self.root / "research/analyze_v492_pilot.py").write_text("changed", encoding="utf-8")
            return result
        fake.run_pilot = changed
        result = self.execute(runtime=fake)
        self.assertNotIn("analysis", self.calls)
        self.assertIn("masked", self.calls)
        self.assertEqual(result["errors"][0]["step"], "analysis")


class AdaptedMaskedTests(inherited_mask_tests.MaskedBundleTests):
    """Reuse the established synthetic preservation/masking failure cases."""
    def setUp(self):
        self.subject_patch = patch.object(inherited_mask_tests, "bundle", bundle)
        self.subject_patch.start()
        super().setUp()

    def tearDown(self):
        super().tearDown()
        self.subject_patch.stop()

    def test_actual_common_system_and_final_instruction_are_available_without_arm_metadata(self):
        self.make_run()
        self.build()
        _, item = self.item_for(bundle.CASES[0])
        evidence = item["supplied_final_evidence"]
        self.assertEqual(evidence["common_system_instruction"], self.drafts[bundle.CASES[0]][0]["content"])
        self.assertEqual(evidence["final_instruction"], "shared fixture task")


if __name__ == "__main__":
    unittest.main()
