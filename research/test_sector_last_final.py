"""Synthetic last-final boundaries; no service, power, model or real output reads."""
import ast
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_sector_last_final as c
from last_final_20261026 import runtime_adapter as r
import sector_remaining_awake as old_awake


def scoped():
    return {"purpose": "pilot_last_final", "case_order": list(r.CASES), "stage_order": list(r.STAGE_ORDER),
        "max_generation_requests": 1, "historical_generation_requests": 10, "campaign_max_generation_requests": 11,
        "automatic_retries": 0, "post_final_calls": 0, "main_model_calls": 0, "main_allowed": False,
        "old_outputs_observed": True, "historical_first_attempt_results_unchanged": True,
        "analysis_role": "primary_exploratory", "excluded_new_main_execution": True,
        "explicit_retry_slots": [], "historical_explicit_retry_slots": ["fidelity_q2_2026__L__D0"],
        "power_policy": copy.deepcopy(r.POWER_POLICY)}


class ScopeAndRuntime(unittest.TestCase):
    def test_exact_scope_and_typed_accounting(self):
        r.scope(scoped())
        for key, bad in (("max_generation_requests", True), ("historical_generation_requests", 6),
                         ("main_allowed", True), ("purpose", "pilot_completion_resume"),
                         ("stage_order", [r.CASES[0] + "__D0"]), ("explicit_retry_slots", [r.STAGE_ORDER[0]])):
            with self.subTest(key=key), self.assertRaises(ValueError):
                r.scope({**scoped(), key: bad})

    def test_summary_cumulative_and_missing_denominator(self):
        row = {"case_id": r.CASES[0], "stages": [{"stage": "F0", "status": "completed", "generation_requests_attempted": 1}]}
        result = c.make_summary([row], stopped=False)
        self.assertEqual((result["campaign_generation_requests_attempted"], result["original_planned_final_cells"]), (11, 5))
        for bad in (True, 2, -1):
            row["stages"][0]["generation_requests_attempted"] = bad
            with self.assertRaises(ValueError):
                c.make_summary([row], stopped=False)
        empty = c.make_summary([{"case_id": r.CASES[0], "stages": []}], stopped=True)
        self.assertEqual(empty["campaign_generation_requests_attempted"], 10)

    def test_worker_supervisor_transport_AST_unchanged(self):
        original = ast.parse(Path(r.old.__file__).read_text(encoding="utf-8-sig"))
        current = ast.parse(Path(r.__file__).read_text(encoding="utf-8-sig"))
        for name in ("worker", "supervise", "run_transport"):
            left = next(x for x in original.body if isinstance(x, ast.FunctionDef) and x.name == name)
            right = next(x for x in current.body if isinstance(x, ast.FunctionDef) and x.name == name)
            self.assertEqual(ast.dump(left, include_attributes=False), ast.dump(right, include_attributes=False))
        self.assertIs(r.check_token_capacity, r.old.check_token_capacity)
        self.assertIs(r.request_body, r.old.request_body)
        self.assertIs(r.validate_runtime, r.old.validate_runtime)

    def test_external_draft_exact_text_identity_history_and_typed_runtime(self):
        refs = {k: {"path": str(r.ROOT / "synthetic" / k), "sha256": "a" * 64} for k in r.DRAFT_ARTIFACTS}
        old_runtime = {"backend_evidence": [{"path": "old"}], "scientific": 1.0}
        new_runtime = {"backend_evidence": [{"path": "new"}], "scientific": 1.0}
        carried = {"raw_draft": "exact saved draft", "draft_artifacts": refs,
                   "old_spec": {"runtime": old_runtime}, "final": {"messages": ["fixed", "history"]}}
        spec = {"review_gate": {}, "draft_artifacts": refs, "raw_draft": carried["raw_draft"],
                "runtime": new_runtime, "body": {"messages": carried["final"]["messages"]}}
        with patch.object(r, "checked", return_value={"external_draft_evidence_refs": {}}), patch.object(r, "validated_external_draft", return_value=carried):
            self.assertTrue(r.validate_prior_draft(spec)["old_missing_ACK_retained"])
            mutations = [lambda x: x.update(raw_draft="changed"),
                         lambda x: x["draft_artifacts"]["response"].update(sha256="b" * 64),
                         lambda x: x["runtime"].update(scientific=1),
                         lambda x: x["body"].update(messages=["truncated"])]
            for mutate in mutations:
                changed = copy.deepcopy(spec); mutate(changed)
                with self.assertRaises(ValueError):
                    r.validate_prior_draft(changed)

    def test_spec_rejects_D0_and_other_case_before_service_read(self):
        with patch.object(r, "validate_runtime"), patch.object(r, "validate_gate"), patch.object(r.prepare, "read") as reader:
            for case, stage in ((r.CASES[0], "D0"), ("ubs_june_2026__L", "F0")):
                with self.assertRaises(ValueError):
                    r.validate_spec({"runtime": {}, "review_gate": {"path": "x", "sha256": "a" * 64},
                                     "run_directory": "x", "case_id": case, "stage": stage})
            reader.assert_not_called()

    def test_review_uniqueness_current_code_coverage_and_chronology(self):
        refs = [{"path": str(r.ROOT / "synthetic" / (str(i) + ".json")), "sha256": str(i) * 64} for i in range(1, 4)]
        review = {"status": "PASS", "completed_at_utc": "2026-10-26T00:00:00Z",
            "review_axes": {k: {"pass": True, "reason": "checked"} for k in ("errors", "consistency", "paper_topic")}}
        code = [{"path": str(r.ROOT / name), "sha256": "a" * 64} for name in r.NEW_REVIEW_CODE]
        with patch.object(r, "checked", return_value=review), patch.object(r, "verify_nested_refs", return_value=code):
            r.validate_reviews(refs, r.timestamp("2026-10-26T01:00:00Z"))
            duplicate = copy.deepcopy(refs); duplicate[2]["sha256"] = duplicate[0]["sha256"]
            with self.assertRaises(ValueError):
                r.validate_reviews(duplicate, r.timestamp("2026-10-26T01:00:00Z"))
            with self.assertRaises(ValueError):
                r.validate_reviews(refs, r.timestamp("2026-10-25T01:00:00Z"))
        with patch.object(r, "checked", return_value=review), patch.object(r, "verify_nested_refs", return_value=[]):
            with self.assertRaises(ValueError):
                r.validate_reviews(refs, r.timestamp("2026-10-26T01:00:00Z"))


class FakeOwner:
    def __init__(self):
        self.pulses = []
    def pulse(self, **kw):
        self.pulses.append(kw)


class Sequence(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run, self.reports = Path(self.temp.name) / "raw", Path(self.temp.name) / "reports"
        self.run.mkdir(); (self.reports / "events").mkdir(parents=True)
        self.owner, self.calls, self.order = FakeOwner(), [], []
        self.declaration = {"review_gate": {"path": "fake", "sha256": "a" * 64},
            "runtime": {"deadline_seconds": 4500}, "origin": "no-network", "server_log": "fake"}
        for name, value in (("validate_gate", {}), ("validated_external_draft", {
                "raw_draft": "untouched external C D0", "draft_artifacts": {"response": "same-ref"},
                "final": {"messages": ["exact", "source-free", "history"]}}),
                ("load_bundle", ({"response_schema": {}}, []))):
            context = patch.object(r, name, return_value=value); context.start(); self.addCleanup(context.stop)
        context = patch.object(r, "request_body", side_effect=lambda runtime, messages, schema: {"messages": messages})
        context.start(); self.addCleanup(context.stop)
        self.status, self.incident, self.eligible = "completed", False, True

    def transport(self, *, spec, target, **kw):
        target.mkdir()
        self.calls.append(spec); self.order.append("transport")
        c.write_json(target / "worker_spec.json", spec)
        result = {"status": self.status, "system_integrity_incident": self.incident,
            "continuation_eligible": self.eligible, "generation_requests_attempted": 1,
            "arithmetic_valid": False, "citation_visibility_valid": False}
        c.write_json(target / "transport_result.json", result)
        return result

    def review(self, spec, folder, result):
        self.order.append("review")
        c.write_json(folder / "stage_review.json", {"instrument_integrity_pass": True})
        return {"instrument_integrity_pass": True}

    def finalize(self, folder):
        self.order.append("math")
        return {"status": "unavailable"}

    def acknowledge(self, **kwargs):
        self.order.append("full_semantic_ACK")
        self.assertTrue(kwargs["math_path"].is_file())
        return {"status": "external_review_completed"}

    def run_sequence(self, waiter=None):
        return c.sequence(self.declaration, self.run, self.reports, self.owner,
            transport=self.transport, reviewer=self.review, finalizer=self.finalize,
            review_waiter=waiter or self.acknowledge)

    def test_only_C_final_once_and_review_before_terminal(self):
        result = self.run_sequence()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual((self.calls[0]["case_id"], self.calls[0]["stage"]), (r.CASES[0], "F0"))
        self.assertEqual(self.calls[0]["raw_draft"], "untouched external C D0")
        self.assertEqual(self.order, ["transport", "review", "math", "full_semantic_ACK"])
        self.assertEqual(result["campaign_generation_requests_attempted"], 11)
        self.assertEqual(result["status"], "attempt_sequence_finished")
        self.assertFalse((self.run / (r.CASES[0] + "__D0")).exists())

    def test_missing_ACK_stops_without_second_request(self):
        def timeout(**kwargs):
            raise TimeoutError("synthetic")
        with self.assertRaises(TimeoutError):
            self.run_sequence(timeout)
        self.assertEqual(len(self.calls), 1)

    def test_prior_cancel_is_not_reused_new_cancel_prevents_request(self):
        (self.run / "CANCEL").touch()
        result = self.run_sequence()
        self.assertEqual(result["generation_requests_attempted"], 0)
        self.assertEqual(self.calls, [])

    def test_model_negative_outcome_retained_without_retry(self):
        self.status, self.eligible = "model_structure_failure", False
        result = self.run_sequence()
        self.assertEqual(result["cases"][0]["stages"][0]["status"], self.status)
        self.assertEqual(result["status"], "attempt_sequence_finished")
        self.assertEqual(len(self.calls), 1)

    def test_integrity_failure_retained_as_stop(self):
        self.status, self.incident, self.eligible = "cleanup_not_confirmed", True, False
        result = self.run_sequence()
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(len(self.calls), 1)

    def test_existing_stage_directory_refuses_reuse(self):
        (self.run / r.STAGE_ORDER[0]).mkdir()
        with self.assertRaises(FileExistsError):
            self.run_sequence()
        self.assertEqual(self.calls, [])

    def test_recovery_keeps_completed_transport_after_ACK_cancel(self):
        self.run_sequence()
        with patch.object(r.prior, "call_accounting", return_value={"generation_requests_attempted": 1}):
            result = c.recover_summary(self.run, {"type": "Cancelled"})
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["cases"][0]["stages"][0]["status"], "completed")
        self.assertTrue(result["cases"][0]["global_stop_does_not_erase_completed_transports"])


class Acknowledgement(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.spec = {"case_id": r.CASES[0], "stage": "F0"}
        for name, value in (("worker_spec.json", self.spec), ("transport_result.json", {}),
                            ("stage_review.json", {}), ("math.json", {})):
            c.write_json(self.folder / name, value)
        semantic = {"case_id": r.CASES[0], "stage": "F0", "review_status": "completed",
                    "transport_ref": c.ref(self.folder / "transport_result.json"), "negative_findings": True}
        c.write_json(self.folder / "semantic.json", semantic)
        self.ack = {"schema_version": "sector_last_final_stage_external_review_ack_1", "status": "completed",
            "case_id": r.CASES[0], "stage": "F0", "model_calls": 0, "raw_model_content_modified": False,
            "review_axes": {k: {"reviewed": True, "reason": "negative outcomes checked"} for k in ("errors", "consistency", "paper_topic")},
            **{key: c.ref(self.folder / name) for key, name in (("worker_spec_ref", "worker_spec.json"),
               ("transport_ref", "transport_result.json"), ("stage_review_ref", "stage_review.json"),
               ("allocation_math_ref", "math.json"), ("semantic_review_ref", "semantic.json"))}}
    def test_valid_negative_review_ACK_and_no_old_schema_acceptance(self):
        result = c.validate_external_review_ack(self.ack, spec=self.spec, folder=self.folder, math_path=self.folder / "math.json")
        self.assertFalse(result["outcome_success_required"])
        with self.assertRaises(ValueError):
            c.validate_external_review_ack({**self.ack, "schema_version": "sector_remaining_stage_external_review_ack_1"},
                spec=self.spec, folder=self.folder, math_path=self.folder / "math.json")
    def test_wrong_stage_or_stale_artifact_ACK_rejected(self):
        with self.assertRaises(ValueError):
            c.validate_external_review_ack(self.ack, spec={**self.spec, "stage": "D0"}, folder=self.folder, math_path=self.folder / "math.json")
        (self.folder / "transport_result.json").write_text('{"changed":true}')
        with self.assertRaises(ValueError):
            c.validate_external_review_ack(self.ack, spec=self.spec, folder=self.folder, math_path=self.folder / "math.json")
    def test_missing_review_timeout_and_cancellation(self):
        owner = FakeOwner()
        with self.assertRaises(TimeoutError):
            c.wait_for_external_review(spec=self.spec, folder=self.folder, math_path=self.folder / "math.json",
                ownership=owner, cancel=self.folder / "CANCEL", timeout_seconds=0)
        (self.folder / "CANCEL").touch()
        with self.assertRaises(r.remote.Cancelled):
            c.wait_for_external_review(spec=self.spec, folder=self.folder, math_path=self.folder / "math.json",
                ownership=owner, cancel=self.folder / "CANCEL", timeout_seconds=0)


class Awake(unittest.TestCase):
    def test_single_thread_battery_policy_and_release_with8100second_expiry(self):
        states = []
        api = SimpleNamespace(state=lambda flags: states.append(flags) or 0x80000000,
            power=lambda: {"ac_line_status": 0, "battery_percent": 80, "battery_flag": 1, "battery_saver": 0})
        before = datetime.now(timezone.utc)
        owner = c.CoordinatorAwake(lambda *a, **kw: None, api=api)
        self.assertTrue(8099 <= (owner.expires - before).total_seconds() <= 8101)
        owner.acquire(); owner.pulse(force=True, stage_start=True)
        self.assertEqual(owner.release()["status"], "released")
        self.assertEqual(states, [0x80000003, 0x80000003, 0x80000000])
    def test_low_start_battery_refuses_before_request(self):
        api = SimpleNamespace(state=lambda flags: self.fail("No state request expected"),
            power=lambda: {"ac_line_status": 0, "battery_percent": 69, "battery_flag": 1, "battery_saver": 0})
        owner = c.CoordinatorAwake(lambda *a, **kw: None, api=api)
        with self.assertRaises(RuntimeError):
            owner.acquire()
        self.assertEqual(owner.release()["status"], "no_request_acquired")


class FinallyCleanup(unittest.TestCase):
    def test_coordinator_exception_clears_owner_and_preserves_terminal_zero_calls(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); run, reports = root / "raw", root / "reports"
            selected = {"backend_evidence": [{"path": str(root / "service_receipt.json"), "sha256": "a" * 64}]}
            c.write_json(root / "runtime.json", selected)
            (root / "server.stdout.log").write_text("")
            obj = {**scoped(), **{k: {"path": "fake", "sha256": "b" * 64} for k in r.BOUND},
                **{k: {} for k in r.EXTERNAL_GROUPS}, "freeze_ref": {"path": "fake", "sha256": "c" * 64},
                "run_directory": str(run), "output_root": str(reports)}
            c.write_json(root / "gate.json", obj)
            validated = {"run_directory": str(run), "output_root": str(reports),
                "runtime_ref": c.ref(root / "runtime.json"), "gate_ref": c.ref(root / "gate.json")}
            lifecycle = []
            class Owner:
                def __init__(self, emit): pass
                def acquire(self): lifecycle.append("acquire")
                def release(self):
                    lifecycle.append("release")
                    return {"status": "released"}
            args = SimpleNamespace(runtime=root / "runtime.json", run_dir=run, output_root=reports,
                review_gate=root / "gate.json", origin="http://127.0.0.1:11435", server_log=root / "server.stdout.log")
            with patch.object(c, "ROOT", root), patch.object(r, "validate_gate", return_value=validated), \
                 patch.object(r.prepare, "read", return_value=({"origin": args.origin}, {})), \
                 patch.object(c, "sequence", side_effect=RuntimeError("synthetic failure")):
                result = c.execute(args, awake_factory=Owner)
            self.assertEqual(lifecycle, ["acquire", "release"])
            self.assertEqual(result["generation_requests_attempted"], 0)
            self.assertEqual(result["status"], "stopped_semantic_review_pending")
            self.assertTrue((reports / "terminal_receipt.json").is_file())
            self.assertEqual(c.read(run / "campaign_summary.json")["campaign_generation_requests_attempted"], 10)


if __name__ == "__main__":
    unittest.main()
