"""Synthetic orchestration and main-thread ownership tests; no model requests."""
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_sector_completion as coordinator
import sector_completion_awake as awake


class Ownership:
    def __init__(self):
        self.pulses = []

    def pulse(self, **kwargs):
        self.pulses.append(kwargs)


class SequenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="completion-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / "raw"
        self.reports = Path(self.temp.name) / "reports"
        self.run.mkdir()
        (self.reports / "events").mkdir(parents=True)
        self.owner = Ownership()
        self.calls, self.final_builds = [], []
        self.failures = {}
        self.bad_review = set()
        self.case_rows = [{"case_id": c, "messages": ["D0", c], "assigned_packet": {"case": c}}
                          for c in coordinator.CASES]
        self.declaration = {"review_gate": {"path": "synthetic", "sha256": "0" * 64},
                            "runtime": {"deadline_seconds": 4500}, "origin": "synthetic-no-network",
                            "server_log": "synthetic"}
        for target, replacement in [
            ("runtime.load_bundle", lambda: ({"response_schema": {}, "prompt_contract": {}}, self.case_rows)),
            ("runtime.request_body", lambda runtime, messages, schema: {"messages": messages}),
            ("runtime.prior_draft_refs", self.draft_refs),
            ("runtime.contract.build_final_messages", self.build_final),
            ("gate.validate_gate", lambda *a, **kw: {})]:
            context = patch("run_sector_completion." + target, replacement)
            context.start()
            self.addCleanup(context.stop)

    def draft_refs(self, run, case):
        return {"response": coordinator.ref(run / (case + "__D0") / "response.json")}

    def build_final(self, **kwargs):
        self.final_builds.append(kwargs)
        return {"ready": True, "messages": ["F0", kwargs["raw_draft"]]}

    def transport(self, *, spec, target, server_log, tick):
        target.mkdir()
        self.calls.append(spec)
        tick()
        pair = (spec["case_id"], spec["stage"])
        status, incident, eligible = self.failures.get(pair, ("completed", False, True))
        response = {"message": {"content": "synthetic-raw:" + ":".join(pair)}}
        coordinator.write_json(target / "response.json", response)
        result = {"status": status, "system_integrity_incident": incident,
                  "continuation_eligible": eligible, "generation_requests_attempted": 1,
                  "arithmetic_valid": False, "citation_visibility_valid": False,
                  "response": response, "response_artifact": coordinator.ref(target / "response.json")}
        coordinator.write_json(target / "transport_result.json", result)
        return result

    def reviewer(self, spec, folder, result):
        review = {"instrument_integrity_pass": (spec["case_id"], spec["stage"]) not in self.bad_review}
        coordinator.write_json(folder / "stage_review.json", review)
        return review

    def run_sequence(self):
        return coordinator.sequence(self.declaration, self.run, self.reports, self.owner,
                                    transport=self.transport, reviewer=self.reviewer,
                                    finalizer=lambda p: {"status": "unavailable", "generation_calls": 0},
                                    review_waiter=lambda **kw: {"status": "external_review_completed", "negative_findings_allowed": True})

    def test_three_cases_six_stages_keep_raw_errors_and_only_own_new_draft(self):
        result = self.run_sequence()
        self.assertEqual(result["status"], "attempt_sequence_finished")
        self.assertEqual(result["generation_requests_attempted"], 6)
        self.assertEqual(result["campaign_generation_requests_attempted"], 11)
        self.assertEqual([(s["case_id"], s["stage"]) for s in self.calls],
                         [(c, s) for c in coordinator.CASES for s in ("D0", "F0")])
        self.assertEqual(len(list((self.reports / "allocation_math").glob("*.json"))), 6)
        self.assertEqual(len(self.final_builds), 3)
        for case, built, spec in zip(coordinator.CASES, self.final_builds, self.calls[1::2]):
            self.assertEqual(built["raw_draft"], "synthetic-raw:" + case + ":D0")
            self.assertEqual(spec["raw_draft"], built["raw_draft"])
            self.assertEqual(spec["body"]["messages"], ["F0", built["raw_draft"]])
        events = [coordinator.read(p) for p in (self.reports / "events").glob("*.json")]
        retried = [e for e in events if e.get("overall_stage_attempt") == 2]
        self.assertEqual(retried, [])
        retried_cells = [e for e in events if e.get("overall_cell_attempt") == 2]
        self.assertEqual(retried_cells, [])

    def test_model_structure_failure_skips_own_final_but_runs_remaining_cases(self):
        self.failures[(coordinator.CASES[0], "D0")] = ("model_structure_failure", False, False)
        result = self.run_sequence()
        self.assertEqual(len(self.calls), 5)
        self.assertEqual(result["status"], "attempt_sequence_finished")
        self.assertEqual(len(result["cases"][0]["stages"]), 1)
        self.assertEqual(len(result["cases"]), 3)

    def test_system_interruption_halts_and_retains_two_missing_cases(self):
        self.failures[(coordinator.CASES[0], "D0")] = ("hard_deadline", True, False)
        result = self.run_sequence()
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(all(not c["stages"] for c in result["cases"][1:]))
        self.assertEqual(result["campaign_generation_requests_attempted"], 6)

    def test_instrument_failure_halts_even_with_completed_transport(self):
        self.bad_review.add((coordinator.CASES[0], "D0"))
        result = self.run_sequence()
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(len(self.calls), 1)

    def test_cancel_before_first_stage_issues_no_request(self):
        (self.run / "CANCEL").touch()
        result = self.run_sequence()
        self.assertEqual(result["generation_requests_attempted"], 0)
        self.assertEqual(len(result["cases"]), 3)

    def test_changed_case_inventory_fails_before_request(self):
        self.case_rows.reverse()
        with self.assertRaises(ValueError):
            self.run_sequence()
        self.assertFalse(self.calls)

    def test_reusing_stage_directory_fails_without_second_request(self):
        (self.run / (coordinator.CASES[0] + "__D0")).mkdir()
        with self.assertRaises(FileExistsError):
            self.run_sequence()
        self.assertFalse(self.calls)


class FakeAPI:
    def __init__(self):
        self.flags, self.ac = [], 1

    def state(self, flags):
        self.flags.append(flags)
        return awake.FLAGS if len(self.flags) > 1 else awake.CLEAR

    def power(self):
        return {"ac_line_status": self.ac}


class OwnershipTests(unittest.TestCase):
    def test_same_thread_acquire_pulse_and_release_are_explicit(self):
        api, events = FakeAPI(), []
        owner = awake.CoordinatorAwake(lambda kind, **kw: events.append((kind, kw)), api=api)
        owner.acquire()
        owner.pulse(force=True, require_ac=True)
        result = owner.release()
        self.assertEqual(api.flags, [awake.FLAGS, awake.FLAGS, awake.CLEAR])
        self.assertEqual(result["status"], "released")
        self.assertFalse(owner.active)
        self.assertEqual(len(events), 2)

    def test_missing_ac_refuses_acquisition_without_api_request(self):
        api = FakeAPI()
        api.ac = 0
        owner = awake.CoordinatorAwake(lambda *a, **k: None, api=api)
        with self.assertRaises(RuntimeError):
            owner.acquire()
        self.assertEqual(api.flags, [])
        self.assertEqual(owner.release()["status"], "no_request_acquired")

    def test_cross_thread_cannot_clear_owner_request(self):
        api = FakeAPI()
        owner = awake.CoordinatorAwake(lambda *a, **k: None, api=api)
        owner.acquire()
        errors = []
        def attempt():
            try:
                owner.release()
            except RuntimeError as exc:
                errors.append(exc)
        worker = threading.Thread(target=attempt)
        worker.start()
        worker.join()
        self.assertEqual(len(errors), 1)
        self.assertTrue(owner.active)
        self.assertEqual(owner.release()["status"], "released")

    def test_ac_loss_at_boundary_requires_stop_and_still_allows_cleanup(self):
        api = FakeAPI()
        owner = awake.CoordinatorAwake(lambda *a, **k: None, api=api)
        owner.acquire()
        api.ac = 0
        with self.assertRaises(RuntimeError):
            owner.pulse(force=True, require_ac=True)
        self.assertEqual(owner.release()["status"], "released")


class CoordinatorCleanupTests(unittest.TestCase):
    def test_acquisition_exception_is_accounted_and_cleanup_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            run, reports = base / "raw", base / "reports"
            runtime_path, gate_path, log = base / "runtime.json", base / "gate.json", base / "service.log"
            coordinator.write_json(runtime_path, {"backend_evidence": [{"path": "synthetic", "sha256": "0" * 64}]})
            log.touch()
            gate_obj = {k: {"path": "synthetic", "sha256": "0" * 64} for k in coordinator.gate.BOUND}
            gate_obj.update(freeze_ref={}, run_directory=str(run), output_root=str(reports), purpose="pilot_completion",
                            case_order=list(coordinator.CASES), max_generation_requests=6,
                            historical_generation_requests=5, campaign_max_generation_requests=11,
                            automatic_retries=0, main_allowed=False, old_outputs_observed=True,
                            explicit_retry_slots=[], historical_explicit_retry_slots=["fidelity_q2_2026__L__D0"],
                            analysis_role="primary_exploratory", excluded_new_main_execution=True, main_model_calls=0)
            coordinator.write_json(gate_path, gate_obj)
            validated = {"run_directory": str(run), "output_root": str(reports),
                         "runtime_ref": coordinator.ref(runtime_path), "gate_ref": coordinator.ref(gate_path)}
            released = []
            class RefuseAcquisition:
                def __init__(self, emit):
                    pass
                def acquire(self):
                    raise RuntimeError("synthetic AC unavailable before generation")
                def release(self):
                    released.append(True)
                    return {"status": "no_request_acquired"}
            args = SimpleNamespace(run_dir=run, output_root=reports, runtime=runtime_path,
                                   review_gate=gate_path, origin="synthetic-no-network", server_log=log)
            with patch.object(coordinator, "locations", return_value=(run, reports)), \
                 patch.object(coordinator.gate, "validate_gate", return_value=validated), \
                 patch.object(coordinator.runtime.prepare, "read", return_value=({"origin": args.origin}, {})):
                result = coordinator.execute(args, awake_factory=RefuseAcquisition)
            self.assertEqual(released, [True])
            self.assertEqual(result["status"], "stopped_semantic_review_pending")
            self.assertEqual(result["generation_requests_attempted"], 0)
            self.assertEqual(len(coordinator.read(run / "campaign_summary.json")["cases"]), 3)
            self.assertTrue((reports / "coordinator_awake_release.json").exists())
            self.assertEqual(result["errors"][0]["type"], "RuntimeError")

    def test_existing_workspace_output_is_never_reused(self):
        with self.assertRaises(FileExistsError):
            coordinator.locations(coordinator.ROOT / "research", coordinator.ROOT / "tmp/unused-test-output")



class CompletionScopeAndHistoryTests(unittest.TestCase):
    def valid_scope(self):
        return {"purpose": "pilot_completion", "case_order": list(coordinator.CASES),
                "max_generation_requests": 6, "historical_generation_requests": 5,
                "campaign_max_generation_requests": 11, "automatic_retries": 0,
                "main_model_calls": 0, "main_allowed": False, "old_outputs_observed": True,
                "analysis_role": "primary_exploratory", "excluded_new_main_execution": True,
                "explicit_retry_slots": [], "historical_explicit_retry_slots": ["fidelity_q2_2026__L__D0"]}

    def history(self):
        refs = {k: {"path": "tmp/completion-test-" + k + ".json", "sha256": "a" * 64}
                for k in coordinator.gate.BOUND}
        old_gate = {k: refs[k] for k in ("historical_gate_ref", "historical_terminal_ref", "historical_summary_ref",
                                       "prepared_manifest_ref", "finalizer_acceptance_ref")}
        old_gate["freeze_ref"] = {"path": "tmp/completion-test-old-freeze.json", "sha256": "b" * 64}
        summary = {"purpose": "pilot_continuation", "status": "stopped",
                   "case_order": list(coordinator.gate.inherited.CASES),
                   "generation_requests_attempted": 2, "historical_generation_requests": 3,
                   "campaign_generation_requests_attempted": 5, "automatic_retries": 0, "main_model_calls": 0,
                   "cases": [{"case_id": c, "stages": []} for c in coordinator.gate.inherited.CASES]}
        summary["cases"][0].update(status="stopped_for_integrity_or_cancellation", stages=[
            {"stage": s, "status": "completed", "generation_requests_attempted": 1} for s in ("D0", "F0")])
        terminal = {"purpose": "pilot_continuation", "status": "stopped_semantic_review_pending",
                    "awake_release": {"status": "released"}, "summary_ref": refs["prior_continuation_summary_ref"],
                    "declaration_ref": refs["prior_continuation_declaration_ref"],
                    "generation_requests_attempted": 2, "automatic_retries": 0, "main_model_calls": 0}
        declaration = {"purpose": "pilot_continuation", "review_gate": refs["prior_continuation_gate_ref"],
                       "freeze_ref": old_gate["freeze_ref"]}
        objects = {"prior_continuation_gate_ref": old_gate, "prior_continuation_terminal_ref": terminal,
                   "prior_continuation_summary_ref": summary, "prior_continuation_declaration_ref": declaration}
        return refs, objects

    def test_exact_three_first_attempts_primary_exploratory_scope(self):
        coordinator.gate.scope(self.valid_scope())

    def test_completed_fidelity_or_new_main_cannot_enter_scope(self):
        for invalid in ("fidelity_q2_2026__E", "fidelity_q2_2026__L", "fidelity_q3_2026__E"):
            value = self.valid_scope()
            value["case_order"][0] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                coordinator.gate.scope(value)

    def test_scope_rejects_wrong_count_bool_retry_and_main(self):
        for key, bad in (("max_generation_requests", 8), ("historical_generation_requests", 3),
                         ("main_model_calls", False), ("automatic_retries", True),
                         ("explicit_retry_slots", ["ubs_june_2026__E__D0"]),
                         ("main_allowed", True), ("excluded_new_main_execution", False),
                         ("analysis_role", "confirmatory")):
            value = self.valid_scope()
            value[key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                coordinator.gate.scope(value)

    def test_history_preserves_completed_L_despite_old_generic_stopped_row_label(self):
        refs, objects = self.history()
        self.assertIs(coordinator.gate.validate_history(objects, refs), objects["prior_continuation_terminal_ref"])

    def test_history_rejects_missing_L_final_or_already_attempted_UBS(self):
        for target in ("missing_final", "prior_UBS"):
            refs, objects = self.history()
            rows = objects["prior_continuation_summary_ref"]["cases"]
            if target == "missing_final":
                rows[0]["stages"].pop()
            else:
                rows[1]["stages"].append({"stage": "D0", "status": "completed", "generation_requests_attempted": 1})
            with self.subTest(target=target), self.assertRaises(ValueError):
                coordinator.gate.validate_history(objects, refs)

    def test_history_rejects_cross_segment_ref_cleanup_or_count(self):
        for target in ("reference", "release", "total", "bool_stage"):
            refs, objects = self.history()
            if target == "reference":
                objects["prior_continuation_terminal_ref"]["summary_ref"] = {"path": "tmp/other.json", "sha256": "a" * 64}
            elif target == "release":
                objects["prior_continuation_terminal_ref"]["awake_release"]["status"] = "release_not_confirmed"
            elif target == "total":
                objects["prior_continuation_summary_ref"]["campaign_generation_requests_attempted"] = 4
            else:
                objects["prior_continuation_summary_ref"]["cases"][0]["stages"][0]["generation_requests_attempted"] = True
            with self.subTest(target=target), self.assertRaises(ValueError):
                coordinator.gate.validate_history(objects, refs)

    def test_gate_requires_new_approved_receipt_before_any_other_work(self):
        with patch.object(coordinator.gate.paths, "read", return_value=({"receipt_version": "sector_continuation_gate_1"}, {"path": "tmp/x", "sha256": "a"*64})):
            with self.assertRaisesRegex(ValueError, "New prospective completion gate"):
                coordinator.gate.validate_gate("tmp/x")

    def test_duplicate_review_and_missing_current_code_coverage_rejected(self):
        import datetime
        when = datetime.datetime(2026, 10, 26, tzinfo=datetime.timezone.utc)
        reviews = [{"path": "tmp/review" + str(i) + ".json", "sha256": str(i) * 64} for i in (1, 2, 3)]
        review = {"status": "PASS", "completed_at_utc": "2026-10-25T00:00:00+00:00",
                  "review_axes": {a: {"pass": True, "reason": "synthetic observed evidence"}
                                  for a in ("errors", "consistency", "paper_topic")}}
        with patch.object(coordinator.gate, "checked", return_value=review), \
             patch.object(coordinator.gate, "verify_nested_refs", return_value=[]):
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                coordinator.gate.validate_reviews([reviews[0]] * 3, when)
            with self.assertRaisesRegex(ValueError, "current completion"):
                coordinator.gate.validate_reviews(reviews, when)


class CompletionPreservationTests(unittest.TestCase):
    def test_stop_after_complete_pair_preserves_cell_completion_and_unattempted_denominator(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            for stage in ("D0", "F0"):
                d = run / (coordinator.CASES[0] + "__" + stage)
                d.mkdir()
                coordinator.write_json(d / "transport_result.json", {"status": "completed",
                    "generation_requests_attempted": 1, "continuation_eligible": True})
            with patch.object(coordinator.runtime.prior, "call_accounting", return_value={"generation_requests_attempted": 1}):
                result = coordinator.recover_summary(run, {"type": "RuntimeError", "message": "AC unavailable"})
            self.assertEqual(result["status"], "stopped")
            self.assertEqual(result["cases"][0]["status"], "two_stages_completed_semantic_review_pending")
            self.assertEqual(result["generation_requests_attempted"], 2)
            self.assertEqual(result["campaign_generation_requests_attempted"], 7)
            self.assertTrue(all(row["stages"] == [] for row in result["cases"][1:]))

    def test_summary_budget_rejects_seventh_completion_request(self):
        with self.assertRaises(RuntimeError):
            coordinator.make_summary([{"stages": [{"generation_requests_attempted": 1}] * 7}], stopped=False)

    def test_awake_expiry_is_six_fixed_stage_and_review_ceilings_plus_cleanup(self):
        import datetime
        before = awake.now()
        owner = awake.CoordinatorAwake(lambda *a, **k: None, api=FakeAPI())
        seconds = (owner.expires - before).total_seconds()
        self.assertGreaterEqual(seconds, 39600)
        self.assertLess(seconds, 39601)

    def test_worker_render_token_generation_and_cleanup_AST_unchanged(self):
        import ast
        research = Path(__file__).resolve().parent
        old = ast.parse((research / "sector_continuation_runtime.py").read_text(encoding="utf-8"))
        new = ast.parse((research / "sector_completion_runtime.py").read_text(encoding="utf-8"))
        oldf = {n.name: ast.dump(n, include_attributes=False) for n in old.body if isinstance(n, ast.FunctionDef)}
        newf = {n.name: ast.dump(n, include_attributes=False) for n in new.body if isinstance(n, ast.FunctionDef)}
        for name in ("artifact_ref", "expected_stage_directory", "validate_worker_location", "prior_draft_refs",
                     "validate_prior_draft", "value_sha", "check_token_capacity", "worker", "supervise", "run_transport", "main"):
            with self.subTest(function=name):
                self.assertEqual(newf[name], oldf[name])

    def test_exact_token_reserve_boundary_and_overflow_without_generation(self):
        import hashlib
        from sector_v491_tokenizer import GGUF_SHA256, LIBRARY_HASHES
        rt = coordinator.runtime
        receipt = {"token_count": 57344, "rendered_utf8_sha256": hashlib.sha256(b"synthetic").hexdigest(),
                   "model_digest": rt.base.DIGEST, "template_sha256": rt.base.TEMPLATE,
                   "method": "exact_installed_libllama_vocab_only", "add_special": True, "parse_special": True,
                   "generation_calls": 0, "gguf_sha256": GGUF_SHA256, "library_hashes": LIBRARY_HASHES}
        runtime = {"options": {"num_predict": 8192, "num_ctx": 65536}}
        self.assertEqual(rt.check_token_capacity(receipt, "synthetic", runtime)["total_required_tokens"], 65536)
        receipt["token_count"] += 1
        with self.assertRaises(rt.CapacityFailure):
            rt.check_token_capacity(receipt, "synthetic", runtime)
        receipt["token_count"] = True
        with self.assertRaises(ValueError):
            rt.check_token_capacity(receipt, "synthetic", runtime)


class ExternalReviewBarrierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="completion-ack-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / "ubs_june_2026__E__D0"
        self.folder.mkdir()
        self.spec = {"case_id": "ubs_june_2026__E", "stage": "D0"}
        self.math_path = self.root / "math.json"
        for name in ("worker_spec.json", "transport_result.json", "stage_review.json"):
            coordinator.write_json(self.folder / name, self.spec if name == "worker_spec.json" else {"synthetic": name})
        coordinator.write_json(self.math_path, {"status": "available", "raw_sum": "1.02"})
        semantic = self.root / "semantic.json"
        coordinator.write_json(semantic, {"review_status": "completed", **self.spec,
            "transport_ref": coordinator.ref(self.folder / "transport_result.json"),
            "findings": [{"status": "contradicted", "reason": "retained synthetic negative outcome"}]})
        self.ack = {"schema_version": "sector_completion_stage_external_review_ack_1", "status": "completed",
            **self.spec, "model_calls": 0, "raw_model_content_modified": False,
            "worker_spec_ref": coordinator.ref(self.folder / "worker_spec.json"),
            "transport_ref": coordinator.ref(self.folder / "transport_result.json"),
            "stage_review_ref": coordinator.ref(self.folder / "stage_review.json"),
            "allocation_math_ref": coordinator.ref(self.math_path), "semantic_review_ref": coordinator.ref(semantic),
            "review_axes": {a: {"reviewed": True, "reason": "Negative findings recorded and preserved"}
                            for a in ("errors", "consistency", "paper_topic")}}
        self.owner = Ownership()
        self.cancel = self.root / "CANCEL"

    def validate(self):
        return coordinator.validate_external_review_ack(self.ack, spec=self.spec, folder=self.folder, math_path=self.math_path)

    def test_valid_negative_findings_ack_permits_progress_without_success_score(self):
        self.assertFalse(self.validate()["outcome_success_required"])
        coordinator.write_json(self.folder / "external_review_ack.json", self.ack)
        result = coordinator.wait_for_external_review(spec=self.spec, folder=self.folder, math_path=self.math_path,
            ownership=self.owner, cancel=self.cancel, timeout_seconds=0)
        self.assertEqual(result["status"], "external_review_completed")
        self.assertEqual(result["acknowledgement_ref"], coordinator.ref(self.folder / "external_review_ack.json"))

    def test_missing_ack_times_out_without_model_or_retry(self):
        with self.assertRaises(TimeoutError):
            coordinator.wait_for_external_review(spec=self.spec, folder=self.folder, math_path=self.math_path,
                ownership=self.owner, cancel=self.cancel, timeout_seconds=0)
        self.assertEqual(len(self.owner.pulses), 1)

    def test_rebound_but_changed_worker_spec_is_rejected(self):
        spec_path = self.folder / "worker_spec.json"
        spec_path.write_text(json.dumps({**self.spec, "changed": True}), encoding="utf-8")
        self.ack["worker_spec_ref"] = coordinator.ref(spec_path)
        with self.assertRaisesRegex(ValueError, "Preserved worker specification"):
            self.validate()

    def test_stale_math_hash_is_rejected(self):
        self.math_path.write_text('{"changed":true}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "bytes changed"):
            self.validate()

    def test_wrong_case_unreviewed_axis_or_semantic_stage_is_rejected(self):
        import copy
        original = copy.deepcopy(self.ack)
        for kind in ("case", "axis", "semantic"):
            self.ack = copy.deepcopy(original)
            if kind == "case":
                self.ack["case_id"] = "fidelity_q2_2026__E"
            elif kind == "axis":
                self.ack["review_axes"]["paper_topic"]["reviewed"] = False
            else:
                semantic = Path(self.ack["semantic_review_ref"]["path"])
                record = coordinator.read(semantic)
                record["stage"] = "F0"
                semantic.write_text(json.dumps(record), encoding="utf-8")
                self.ack["semantic_review_ref"] = coordinator.ref(semantic)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.validate()

    def test_malformed_existing_ack_fails_closed(self):
        (self.folder / "external_review_ack.json").write_text("{", encoding="utf-8")
        with self.assertRaises(ValueError):
            coordinator.wait_for_external_review(spec=self.spec, folder=self.folder, math_path=self.math_path,
                ownership=self.owner, cancel=self.cancel, timeout_seconds=0)

    def test_cancel_during_wait_honored_before_ack(self):
        coordinator.write_json(self.folder / "external_review_ack.json", self.ack)
        self.cancel.touch()
        with self.assertRaises(coordinator.runtime.remote.Cancelled):
            coordinator.wait_for_external_review(spec=self.spec, folder=self.folder, math_path=self.math_path,
                ownership=self.owner, cancel=self.cancel, timeout_seconds=0)

    def test_wait_timeout_cannot_exceed_frozen_operational_ceiling(self):
        with self.assertRaises(ValueError):
            coordinator.wait_for_external_review(spec=self.spec, folder=self.folder, math_path=self.math_path,
                ownership=self.owner, cancel=self.cancel, timeout_seconds=1801)


class SequenceReviewBarrierTests(unittest.TestCase):
    setUp = SequenceTests.setUp
    draft_refs = SequenceTests.draft_refs
    build_final = SequenceTests.build_final
    transport = SequenceTests.transport
    reviewer = SequenceTests.reviewer
    # Reuse fixture helpers without counting the existing orchestration tests twice.
    def test_no_next_generation_without_valid_ack(self):
        def no_ack(**kwargs):
            return coordinator.wait_for_external_review(**kwargs, timeout_seconds=0)
        with self.assertRaises(TimeoutError):
            coordinator.sequence(self.declaration, self.run, self.reports, self.owner,
                transport=self.transport, reviewer=self.reviewer, finalizer=lambda p: {"status": "available"},
                review_waiter=no_ack)
        self.assertEqual([(s["case_id"], s["stage"]) for s in self.calls], [(coordinator.CASES[0], "D0")])
        self.assertEqual(self.final_builds, [])

    def test_final_F0_also_requires_external_review(self):
        seen = []
        def reviewed(**kwargs):
            seen.append((kwargs["spec"]["case_id"], kwargs["spec"]["stage"], len(self.calls)))
            return {"status": "external_review_completed"}
        result = coordinator.sequence(self.declaration, self.run, self.reports, self.owner,
            transport=self.transport, reviewer=self.reviewer, finalizer=lambda p: {"status": "available"},
            review_waiter=reviewed)
        self.assertEqual(len(seen), 6)
        self.assertEqual(seen[-1], (coordinator.CASES[-1], "F0", 6))
        self.assertEqual([n for _, _, n in seen], list(range(1, 7)))
        self.assertEqual(result["status"], "attempt_sequence_finished")


if __name__ == "__main__":
    unittest.main()
