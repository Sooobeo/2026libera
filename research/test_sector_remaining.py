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
import run_sector_remaining as coordinator
import sector_remaining_awake as awake


class Ownership:
    def __init__(self):
        self.pulses = []

    def pulse(self, **kwargs):
        self.pulses.append(kwargs)


class SequenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="remaining-synthetic-")
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
            ("gate.validate_gate", lambda *a, **kw: {}),
            ("gate.validated_external_draft", lambda value: {"raw_draft": "external-unchanged-D0",
                "draft_artifacts": {"response": {"path": "synthetic-old-response", "sha256": "e" * 64}},
                "final": {"messages": ["F0", "external-unchanged-D0"]}})]:
            context = patch("run_sector_remaining." + target, replacement)
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

    def test_exact_five_stages_carry_external_D0_and_keep_new_case_histories(self):
        result = self.run_sequence()
        self.assertEqual(result["status"], "attempt_sequence_finished")
        self.assertEqual(result["generation_requests_attempted"], 5)
        self.assertEqual(result["campaign_generation_requests_attempted"], 11)
        self.assertEqual([s["case_id"] + "__" + s["stage"] for s in self.calls], list(coordinator.STAGE_ORDER))
        self.assertEqual(len(list((self.reports / "allocation_math").glob("*.json"))), 5)
        self.assertEqual(len(self.final_builds), 2)
        self.assertEqual(self.calls[0]["raw_draft"], "external-unchanged-D0")
        self.assertEqual(self.calls[0]["body"]["messages"], ["F0", "external-unchanged-D0"])
        self.assertFalse((self.run / (coordinator.CASES[0] + "__D0")).exists())
        self.assertFalse((self.run / (coordinator.CASES[0] + "__final_construction.json")).exists())
        for case, built, spec in zip(coordinator.CASES[1:], self.final_builds, self.calls[2::2]):
            self.assertEqual(built["raw_draft"], "synthetic-raw:" + case + ":D0")
            self.assertEqual(spec["raw_draft"], built["raw_draft"])
            self.assertEqual(spec["body"]["messages"], ["F0", built["raw_draft"]])
        starts = [coordinator.read(p) for p in (self.reports / "events").glob("*.json")]
        self.assertTrue(all(e.get("overall_stage_attempt", 1) == 1 for e in starts))
        self.assertEqual(sum(p.get("stage_start") is True for p in self.owner.pulses), 5)

    def test_model_structure_failure_skips_own_final_but_runs_remaining_cases(self):
        self.failures[(coordinator.CASES[1], "D0")] = ("model_structure_failure", False, False)
        result = self.run_sequence()
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(result["status"], "attempt_sequence_finished")
        self.assertEqual(len(result["cases"][1]["stages"]), 1)
        self.assertEqual(len(result["cases"]), 3)

    def test_system_interruption_halts_and_retains_two_missing_cases(self):
        self.failures[(coordinator.CASES[0], "F0")] = ("hard_deadline", True, False)
        result = self.run_sequence()
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(all(not c["stages"] for c in result["cases"][1:]))
        self.assertEqual(result["campaign_generation_requests_attempted"], 7)

    def test_instrument_failure_halts_even_with_completed_transport(self):
        self.bad_review.add((coordinator.CASES[0], "F0"))
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
        (self.run / (coordinator.CASES[0] + "__F0")).mkdir()
        with self.assertRaises(FileExistsError):
            self.run_sequence()
        self.assertFalse(self.calls)


class FakeAPI:
    def __init__(self):
        self.flags, self.ac, self.percent, self.battery_flags, self.saver = [], 1, 100, 1, 0

    def state(self, flags):
        self.flags.append(flags)
        return awake.FLAGS if len(self.flags) > 1 else awake.CLEAR

    def power(self):
        return {"ac_line_status": self.ac, "battery_percent": self.percent,
                "battery_flag": self.battery_flags, "battery_saver": self.saver}


class OwnershipTests(unittest.TestCase):
    def test_same_thread_acquire_pulse_and_release_are_explicit(self):
        api, events = FakeAPI(), []
        owner = awake.CoordinatorAwake(lambda kind, **kw: events.append((kind, kw)), api=api)
        owner.acquire()
        owner.pulse(force=True, stage_start=True)
        result = owner.release()
        self.assertEqual(api.flags, [awake.FLAGS, awake.FLAGS, awake.CLEAR])
        self.assertEqual(result["status"], "released")
        self.assertFalse(owner.active)
        self.assertEqual(len(events), 2)

    def test_insufficient_battery_refuses_acquisition_without_api_request(self):
        api = FakeAPI()
        api.ac, api.percent = 0, 69
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

    def test_insufficient_battery_at_boundary_stops_and_allows_cleanup(self):
        api = FakeAPI()
        owner = awake.CoordinatorAwake(lambda *a, **k: None, api=api)
        owner.acquire()
        api.ac, api.percent = 0, 69
        with self.assertRaises(RuntimeError):
            owner.pulse(force=True, stage_start=True)
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
            gate_obj.update(freeze_ref={}, run_directory=str(run), output_root=str(reports), purpose="pilot_completion_resume",
                            case_order=list(coordinator.CASES), stage_order=list(coordinator.STAGE_ORDER),
                            power_policy=awake.POWER_POLICY, external_draft_refs={}, external_draft_evidence_refs={}, max_generation_requests=5,
                            historical_generation_requests=6, campaign_max_generation_requests=11,
                            automatic_retries=0, post_final_calls=0, main_allowed=False, old_outputs_observed=True,
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



class CompletionPreservationTests(unittest.TestCase):
    def test_stop_after_external_E_final_preserves_cell_completion_and_unattempted_denominator(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            for stage in ("F0",):
                d = run / (coordinator.CASES[0] + "__" + stage)
                d.mkdir()
                coordinator.write_json(d / "transport_result.json", {"status": "completed",
                    "generation_requests_attempted": 1, "continuation_eligible": True})
            with patch.object(coordinator.runtime.prior, "call_accounting", return_value={"generation_requests_attempted": 1}):
                result = coordinator.recover_summary(run, {"type": "RuntimeError", "message": "AC unavailable"})
            self.assertEqual(result["status"], "stopped")
            self.assertEqual(result["cases"][0]["status"], "remaining_stages_completed_semantic_review_pending")
            self.assertEqual(result["generation_requests_attempted"], 1)
            self.assertEqual(result["campaign_generation_requests_attempted"], 7)
            self.assertTrue(all(row["stages"] == [] for row in result["cases"][1:]))

    def test_summary_budget_rejects_sixth_remaining_request(self):
        with self.assertRaises(RuntimeError):
            coordinator.make_summary([{"stages": [{"generation_requests_attempted": 1}] * 6}], stopped=False)

    def test_awake_expiry_is_five_fixed_stage_and_review_ceilings_plus_cleanup(self):
        import datetime
        before = awake.now()
        owner = awake.CoordinatorAwake(lambda *a, **k: None, api=FakeAPI())
        seconds = (owner.expires - before).total_seconds()
        self.assertGreaterEqual(seconds, 33300)
        self.assertLess(seconds, 33301)

    def test_worker_render_token_generation_and_cleanup_AST_unchanged(self):
        import ast
        research = Path(__file__).resolve().parent
        old = ast.parse((research / "sector_completion_runtime.py").read_text(encoding="utf-8"))
        new = ast.parse((research / "sector_remaining_runtime.py").read_text(encoding="utf-8"))
        oldf = {n.name: ast.dump(n, include_attributes=False) for n in old.body if isinstance(n, ast.FunctionDef)}
        newf = {n.name: ast.dump(n, include_attributes=False) for n in new.body if isinstance(n, ast.FunctionDef)}
        for name in ("artifact_ref", "expected_stage_directory", "validate_worker_location", "prior_draft_refs",
                     "value_sha", "check_token_capacity", "worker", "supervise", "run_transport", "main"):
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
        self.temp = tempfile.TemporaryDirectory(prefix="remaining-ack-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / "ubs_june_2026__E__F0"
        self.folder.mkdir()
        self.spec = {"case_id": "ubs_june_2026__E", "stage": "F0"}
        self.math_path = self.root / "math.json"
        for name in ("worker_spec.json", "transport_result.json", "stage_review.json"):
            coordinator.write_json(self.folder / name, self.spec if name == "worker_spec.json" else {"synthetic": name})
        coordinator.write_json(self.math_path, {"status": "available", "raw_sum": "1.02"})
        semantic = self.root / "semantic.json"
        coordinator.write_json(semantic, {"review_status": "completed", **self.spec,
            "transport_ref": coordinator.ref(self.folder / "transport_result.json"),
            "findings": [{"status": "contradicted", "reason": "retained synthetic negative outcome"}]})
        self.ack = {"schema_version": "sector_remaining_stage_external_review_ack_1", "status": "completed",
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
                record["stage"] = "D0"
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
        self.assertEqual([(s["case_id"], s["stage"]) for s in self.calls], [(coordinator.CASES[0], "F0")])
        self.assertEqual(self.final_builds, [])

    def test_final_F0_also_requires_external_review(self):
        seen = []
        def reviewed(**kwargs):
            seen.append((kwargs["spec"]["case_id"], kwargs["spec"]["stage"], len(self.calls)))
            return {"status": "external_review_completed"}
        result = coordinator.sequence(self.declaration, self.run, self.reports, self.owner,
            transport=self.transport, reviewer=self.reviewer, finalizer=lambda p: {"status": "available"},
            review_waiter=reviewed)
        self.assertEqual(len(seen), 5)
        self.assertEqual(seen[-1], (coordinator.CASES[-1], "F0", 5))
        self.assertEqual([n for _, _, n in seen], list(range(1, 6)))
        self.assertEqual(result["status"], "attempt_sequence_finished")


class BatteryPolicyTests(unittest.TestCase):
    def power(self, ac=0, percent=70, flags=1, saver=0):
        return {"ac_line_status": ac, "battery_percent": percent, "battery_flag": flags, "battery_saver": saver}

    def test_stage_start_70_boundary_and_running_20_boundary(self):
        self.assertEqual(awake.check_power(self.power(), stage_start=True)["status"], "allowed_sufficient_battery")
        with self.assertRaises(RuntimeError):
            awake.check_power(self.power(percent=69), stage_start=True)
        awake.check_power(self.power(percent=21), stage_start=False)
        with self.assertRaises(RuntimeError):
            awake.check_power(self.power(percent=20), stage_start=False)

    def test_unknown_critical_saver_or_invalid_types_reject_on_either_power(self):
        for ac in (0, 1):
            for change in ({"ac_line_status": 255}, {"ac_line_status": True}, {"battery_percent": 255},
                           {"battery_flag": 255}, {"battery_flag": 4}, {"battery_flag": 12},
                           {"battery_saver": 1}, {"battery_saver": 255}, {"battery_percent": True}):
                with self.subTest(ac=ac, change=change), self.assertRaises(RuntimeError):
                    awake.check_power({**self.power(ac=ac), **change}, stage_start=False)

    def test_no_system_battery_is_only_allowed_on_known_AC(self):
        awake.check_power(self.power(ac=1, percent=255, flags=128), stage_start=True)
        for ac, flags in ((0, 128), (255, 128), (1, 129), (1, 132)):
            with self.subTest(ac=ac, flags=flags), self.assertRaises(RuntimeError):
                awake.check_power(self.power(ac=ac, percent=255, flags=flags), stage_start=False)

    def test_AC_transition_with_full_battery_is_recorded_and_continues(self):
        api, events = FakeAPI(), []
        owner = awake.CoordinatorAwake(lambda kind, **kw: events.append((kind, kw)), api=api)
        owner.acquire()
        api.ac = 0
        owner.pulse(force=True, stage_start=True)
        self.assertTrue(owner.active)
        transitions = [data for kind, data in events if kind == "coordinator_power_transition"]
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0]["power_status"]["battery_percent"], 100)
        self.assertEqual(owner.release()["status"], "released")

    def test_in_stage_low_battery_aborts_but_release_clears_same_thread(self):
        api = FakeAPI()
        owner = awake.CoordinatorAwake(lambda *a, **kw: None, api=api)
        owner.acquire()
        api.ac, api.percent = 0, 20
        try:
            with self.assertRaises(RuntimeError):
                owner.pulse(force=True)
        finally:
            self.assertEqual(owner.release()["status"], "released")
        self.assertEqual(api.flags[-1], awake.CLEAR)


class RemainingScopeTests(unittest.TestCase):
    def scope(self):
        return {"purpose": "pilot_completion_resume", "case_order": list(coordinator.CASES),
                "stage_order": list(coordinator.STAGE_ORDER), "power_policy": awake.POWER_POLICY,
                "max_generation_requests": 5, "historical_generation_requests": 6,
                "campaign_max_generation_requests": 11, "automatic_retries": 0, "post_final_calls": 0,
                "main_model_calls": 0, "main_allowed": False, "old_outputs_observed": True,
                "analysis_role": "primary_exploratory", "excluded_new_main_execution": True,
                "explicit_retry_slots": [], "historical_explicit_retry_slots": ["fidelity_q2_2026__L__D0"]}

    def test_five_exact_unattempted_stages_with_six_history(self):
        coordinator.gate.scope(self.scope())

    def test_reexecution_wrong_counts_boolean_main_retry_and_power_changes_rejected(self):
        import copy
        for key, value in (("stage_order", ["ubs_june_2026__E__D0"] + list(coordinator.STAGE_ORDER)),
                           ("purpose", "pilot_completion"), ("historical_generation_requests", 5),
                           ("max_generation_requests", 6), ("automatic_retries", False),
                           ("main_allowed", True), ("power_policy", {}),
                           ("explicit_retry_slots", ["ubs_june_2026__E__D0"])):
            obj = copy.deepcopy(self.scope())
            obj[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                coordinator.gate.scope(obj)

    def test_duplicate_reviews_and_missing_current_source_coverage_reject(self):
        from datetime import datetime, timezone
        reviews = [{"path": "tmp/review" + str(i), "sha256": str(i) * 64} for i in (1, 2, 3)]
        value = {"status": "PASS", "completed_at_utc": "2026-10-25T00:00:00+00:00",
                 "review_axes": {a: {"pass": True, "reason": "synthetic"} for a in ("errors", "consistency", "paper_topic")}}
        with patch.object(coordinator.gate, "checked", return_value=value), \
             patch.object(coordinator.gate, "verify_nested_refs", return_value=[]):
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                coordinator.gate.validate_reviews([reviews[0]] * 3, datetime.now(timezone.utc))
            with self.assertRaisesRegex(ValueError, "current"):
                coordinator.gate.validate_reviews(reviews, datetime.now(timezone.utc))

    def test_history_retains_exact_one_previous_UBS_D0_and_no_later_stages(self):
        refs = {key: {"path": "tmp/" + key + ".json", "sha256": "a" * 64} for key in coordinator.gate.BOUND}
        old = {key: refs[key] for key in coordinator.gate.previous.BOUND}
        old["freeze_ref"] = {"path": "tmp/prior-freeze.json", "sha256": "b" * 64}
        summary = {"purpose": "pilot_completion", "status": "stopped", "case_order": list(coordinator.CASES),
            "generation_requests_attempted": 1, "automatic_retries": 0, "main_model_calls": 0,
            "historical_generation_requests": 5, "campaign_generation_requests_attempted": 6,
            "cases": [{"case_id": c, "stages": []} for c in coordinator.CASES]}
        summary["cases"][0]["stages"] = [{"stage": "D0", "status": "completed", "generation_requests_attempted": 1}]
        terminal = {"purpose": "pilot_completion", "status": "stopped_semantic_review_pending",
            "awake_release": {"status": "released"}, "summary_ref": refs["prior_completion_summary_ref"],
            "declaration_ref": refs["prior_completion_declaration_ref"],
            "generation_requests_attempted": 1, "automatic_retries": 0, "main_model_calls": 0}
        decl = {"purpose": "pilot_completion", "review_gate": refs["prior_completion_gate_ref"], "freeze_ref": old["freeze_ref"]}
        objs = {"prior_completion_gate_ref": old, "prior_completion_summary_ref": summary,
                "prior_completion_terminal_ref": terminal, "prior_completion_declaration_ref": decl}
        with patch.object(coordinator.gate.previous, "validate_history") as inherited:
            self.assertIs(coordinator.gate.validate_history(objs, refs), terminal)
            inherited.assert_called_once_with(objs, refs)
            summary["cases"][1]["stages"] = [{"stage": "D0", "status": "completed", "generation_requests_attempted": 1}]
            with self.assertRaises(ValueError):
                coordinator.gate.validate_history(objs, refs)


class ExternalDraftBoundaryTests(unittest.TestCase):
    def setUp(self):
        import copy
        self.old_runtime = {"options": {"temperature": 0.0, "num_thread": 8},
                            "backend_evidence": [{"path": "old", "sha256": "a" * 64}]}
        self.runtime = copy.deepcopy(self.old_runtime)
        self.runtime["backend_evidence"][0] = {"path": "new", "sha256": "b" * 64}
        self.refs = {key: {"path": "tmp/old-" + key + ".json", "sha256": "c" * 64}
                     for key in coordinator.runtime.DRAFT_ARTIFACTS}
        self.carried = {"raw_draft": "exact unchanged JSON string", "draft_artifacts": self.refs,
                        "old_spec": {"runtime": self.old_runtime, "run_directory": "oldrun", "review_gate": {}},
                        "final": {"messages": ["same", "saved", "messages"]}}
        self.pinned = {"external_draft_evidence_refs": {"semantic_review": {"path": "synthetic", "sha256": "d" * 64}}}
        self.spec = {"case_id": coordinator.CASES[0], "stage": "F0", "runtime": self.runtime,
                     "review_gate": {"path": "synthetic", "sha256": "a" * 64}, "draft_artifacts": copy.deepcopy(self.refs),
                     "raw_draft": self.carried["raw_draft"], "body": {"messages": self.carried["final"]["messages"]}}
        for target, replacement in (("prepare.read", lambda *a: (self.pinned, {})),
                                    ("gate.scope", lambda value: None),
                                    ("gate.validated_external_draft", lambda value: self.carried)):
            context = patch("sector_remaining_runtime." + target, replacement)
            context.start()
            self.addCleanup(context.stop)

    def test_exact_external_draft_and_owned_backend_difference_allowed(self):
        result = coordinator.runtime.validate_prior_draft(self.spec)
        self.assertEqual(result["status"], "explicit_external_completed_D0_artifacts_bound")
        self.assertFalse(result["raw_draft_copied_to_new_D0_stage"])

    def test_external_changed_ref_raw_messages_or_scientific_type_reject(self):
        import copy
        saved = copy.deepcopy(self.spec)
        for kind in ("raw", "reference", "history", "threads", "float_type"):
            self.spec = copy.deepcopy(saved)
            if kind == "raw": self.spec["raw_draft"] += " "
            elif kind == "reference": self.spec["draft_artifacts"]["response"]["sha256"] = "0" * 64
            elif kind == "history": self.spec["body"]["messages"].append("audit must never enter model")
            elif kind == "threads": self.spec["runtime"]["options"]["num_thread"] = 7
            else: self.spec["runtime"]["options"]["temperature"] = 0
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                coordinator.runtime.validate_prior_draft(self.spec)

    def test_other_cases_do_not_use_external_draft_exception(self):
        self.spec["case_id"] = coordinator.CASES[1]
        self.spec["run_directory"] = "data/local_sector_runtime/v494_remaining_20261026"
        with self.assertRaisesRegex(ValueError, "same run/case"):
            coordinator.runtime.validate_prior_draft(self.spec)


class PublisherIntegrationTests(unittest.TestCase):
    def test_completed_F0_publishes_once_and_E_D0_is_rejected(self):
        import publish_remaining_review_ack as publisher
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run, reports, semantic = root / "raw", root / "reports", root / "semantic"
            run.mkdir(); (reports / "allocation_math").mkdir(parents=True); semantic.mkdir()
            case = coordinator.CASES[0]
            stage = run / (case + "__F0"); stage.mkdir()
            spec = {"case_id": case, "stage": "F0"}
            coordinator.write_json(stage / "worker_spec.json", spec)
            for name in ("transport_result.json", "stage_review.json"):
                coordinator.write_json(stage / name, {"synthetic": name})
            coordinator.write_json(reports / "allocation_math" / (stage.name + ".json"), {"status": "available"})
            review_path = semantic / "full.json"
            review = {"review_status": "completed", **spec, "transport_ref": coordinator.ref(stage / "transport_result.json"),
                "review_axes": {a: {"reviewed": True, "reason": "Negative findings retained"}
                                for a in ("errors", "consistency", "paper_topic")}}
            coordinator.write_json(review_path, review)
            with patch.object(publisher, "RUN", run), patch.object(publisher, "REPORTS", reports), \
                 patch.object(publisher, "SEMANTIC", semantic):
                result = publisher.publish(stage, review_path)
                self.assertEqual(result["status"], "published")
                self.assertEqual(coordinator.read(stage / "external_review_ack.json")["schema_version"],
                                 "sector_remaining_stage_external_review_ack_1")
                with self.assertRaises(FileExistsError): publisher.publish(stage, review_path)
                disallowed = run / (case + "__D0"); disallowed.mkdir()
                coordinator.write_json(disallowed / "worker_spec.json", {"case_id": case, "stage": "D0"})
                with self.assertRaises(ValueError): publisher.publish(disallowed, review_path)
            self.assertEqual(list(semantic.glob(".ack_*.tmp")), [])


class RuntimeStageScopeTests(unittest.TestCase):
    def test_external_E_D0_cannot_be_generated_in_new_namespace(self):
        spec = {"runtime": {"backend_evidence": [{"path": "synthetic", "sha256": "a" * 64}]},
                "review_gate": {"path": "synthetic", "sha256": "b" * 64},
                "run_directory": str(coordinator.ROOT / "data/local_sector_runtime/v494_remaining_20261026"),
                "case_id": coordinator.CASES[0], "stage": "D0", "origin": "http://127.0.0.1:11435"}
        spec["cancel_path"] = str(Path(spec["run_directory"]) / "CANCEL")
        rt = coordinator.runtime
        with patch.object(rt, "validate_runtime"), patch.object(rt, "validate_gate"), \
             patch.object(rt.prepare, "read", return_value=({"origin": spec["origin"]}, {})), \
             patch.object(rt, "load_bundle") as bundle:
            with self.assertRaisesRegex(ValueError, "five declared remaining"):
                rt.validate_spec(spec)
            bundle.assert_not_called()

    def test_ack_rejects_repeated_E_D0_before_reading_artifacts(self):
        with self.assertRaisesRegex(ValueError, "five remaining"):
            coordinator.validate_external_review_ack({}, spec={"case_id": coordinator.CASES[0], "stage": "D0"},
                folder=Path("synthetic"), math_path=Path("synthetic"))


if __name__ == "__main__":
    unittest.main()
