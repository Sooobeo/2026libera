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
import run_sector_main as coordinator
import sector_main_awake as awake


class Ownership:
    def __init__(self):
        self.pulses = []

    def pulse(self, **kwargs):
        self.pulses.append(kwargs)


class SequenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="continuation-synthetic-")
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
            context = patch("run_sector_main." + target, replacement)
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
                                    finalizer=lambda p: {"status": "unavailable", "generation_calls": 0})

    def test_five_cases_ten_stages_keep_raw_errors_and_only_own_new_draft(self):
        result = self.run_sequence()
        self.assertEqual(result["status"], "attempt_sequence_finished")
        self.assertEqual(result["generation_requests_attempted"], 10)
        self.assertEqual(result["main_model_calls"], 10)
        self.assertEqual([(s["case_id"], s["stage"]) for s in self.calls],
                         [(c, s) for c in coordinator.CASES for s in ("D0", "F0")])
        self.assertEqual(len(list((self.reports / "allocation_math").glob("*.json"))), 10)
        self.assertEqual(len(self.final_builds), 5)
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
        self.assertEqual(len(self.calls), 9)
        self.assertEqual(result["status"], "attempt_sequence_finished")
        self.assertEqual(len(result["cases"][0]["stages"]), 1)
        self.assertEqual(len(result["cases"]), 5)

    def test_system_interruption_halts_and_retains_four_missing_cases(self):
        self.failures[(coordinator.CASES[0], "D0")] = ("hard_deadline", True, False)
        result = self.run_sequence()
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(all(not c["stages"] for c in result["cases"][1:]))
        self.assertEqual(result["main_model_calls"], 1)

    def test_instrument_failure_halts_even_with_completed_transport(self):
        self.bad_review.add((coordinator.CASES[0], "D0"))
        result = self.run_sequence()
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(len(self.calls), 1)

    def test_cancel_before_first_stage_issues_no_request(self):
        (self.run / "CANCEL").touch()
        result = self.run_sequence()
        self.assertEqual(result["generation_requests_attempted"], 0)
        self.assertEqual(len(result["cases"]), 5)

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
        owner = awake.MainCoordinatorAwake(lambda kind, **kw: events.append((kind, kw)), api=api)
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
        owner = awake.MainCoordinatorAwake(lambda *a, **k: None, api=api)
        with self.assertRaises(RuntimeError):
            owner.acquire()
        self.assertEqual(api.flags, [])
        self.assertEqual(owner.release()["status"], "no_request_acquired")

    def test_cross_thread_cannot_clear_owner_request(self):
        api = FakeAPI()
        owner = awake.MainCoordinatorAwake(lambda *a, **k: None, api=api)
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
        owner = awake.MainCoordinatorAwake(lambda *a, **k: None, api=api)
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
            runtime_path, gate_path, log = base / "runtime.json", base / "gate.json", base / "server.stderr.log"
            coordinator.write_json(runtime_path, {"backend_evidence": [{"path": str(base / "service_receipt.json"), "sha256": "0" * 64}]})
            log.touch()
            gate_obj = {k: {"path": "synthetic", "sha256": "0" * 64} for k in coordinator.gate.BOUND}
            gate_obj.update(freeze_ref={}, run_directory=str(run), output_root=str(reports), purpose="main",
                            case_order=list(coordinator.CASES), max_generation_requests=10,
                            historical_generation_requests=3, campaign_max_generation_requests=11,
                            automatic_retries=0, main_allowed=True, old_outputs_observed=True,
                            explicit_retry_slots=[coordinator.CASES[0] + "__D0"])
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
                 patch.object(coordinator.runtime.prepare, "read", return_value=({"origin": args.origin}, {})), \
                 patch.object(coordinator.runtime.prepare, "workspace_path", side_effect=lambda p: Path(p).resolve()):
                result = coordinator.execute(args, awake_factory=RefuseAcquisition)
            self.assertEqual(released, [True])
            self.assertEqual(result["status"], "stopped_semantic_review_pending")
            self.assertEqual(result["generation_requests_attempted"], 0)
            self.assertEqual(len(coordinator.read(run / "campaign_summary.json")["cases"]), 5)
            self.assertTrue((reports / "coordinator_awake_release.json").exists())
            self.assertEqual(result["errors"][0]["type"], "RuntimeError")

    def test_existing_workspace_output_is_never_reused(self):
        with self.assertRaises(FileExistsError):
            coordinator.locations(coordinator.ROOT / "research", coordinator.ROOT / "tmp/unused-test-output")


class MainInputAndRuntimeTests(unittest.TestCase):
    def test_real_offline_main_inputs_reconstruct_without_model_calls(self):
        loaded, cases = coordinator.runtime.load_bundle()
        self.assertEqual([c["case_id"] for c in cases], list(coordinator.CASES))
        self.assertEqual(cases[1]["messages"], cases[3]["messages"])
        self.assertEqual(cases[1]["messages"], cases[4]["messages"])
        self.assertEqual(loaded["preparation_manifest"]["model_calls"], 0)
        self.assertIsNone(cases[4]["assigned_packet"])

    def test_new_main_runtime_keeps_scientific_request_exact(self):
        instrument = coordinator.read(coordinator.ROOT / "research/continuation_20261026/runtime_candidate.json")
        selected = coordinator.runtime.candidate_runtime(instrument)
        coordinator.runtime.validate_runtime(selected)
        self.assertEqual(selected["runtime_version"], "sector_main_runtime_1")
        self.assertEqual(selected["main_order"], list(coordinator.CASES))
        self.assertFalse(selected["main_allowed"])
        self.assertNotIn("pilot_order", selected)
        loaded, cases = coordinator.runtime.load_bundle()
        body = coordinator.runtime.request_body(selected, cases[0]["messages"], loaded["response_schema"])
        old = coordinator.runtime.original.request_body(instrument, cases[0]["messages"], loaded["response_schema"])
        self.assertEqual(coordinator.runtime.base.canonical(body), coordinator.runtime.base.canonical(old))

    def test_scientific_seed_change_fails_closed(self):
        instrument = coordinator.read(coordinator.ROOT / "research/continuation_20261026/runtime_candidate.json")
        selected = coordinator.runtime.candidate_runtime(instrument)
        selected["options"]["seed"] += 1
        with self.assertRaises(ValueError):
            coordinator.runtime.validate_runtime(selected)

    def test_main_awake_uses_ten_stage_operational_expiry(self):
        from datetime import datetime, timezone
        start = datetime.now(timezone.utc)
        owner = awake.MainCoordinatorAwake(lambda *a, **k: None, api=FakeAPI())
        seconds = (owner.expires - start).total_seconds()
        self.assertGreaterEqual(seconds, 10 * 4500 + 1800)
        self.assertLess(seconds, 10 * 4500 + 1801)


class MainOperatingGateTests(unittest.TestCase):
    def setUp(self):
        self.terminal_ref = {"path": "terminal.json", "sha256": "1" * 64}
        self.summary_ref = {"path": "summary.json", "sha256": "2" * 64}
        self.summary = {"purpose": "pilot_continuation", "status": "attempt_sequence_finished",
            "case_order": list(coordinator.gate.continuation.CASES), "generation_requests_attempted": 4,
            "main_model_calls": 0, "automatic_retries": 0, "post_final_calls": 0,
            "cases": [{"case_id": c, "stages": [{"stage": "D0", "status": "model_structure_failure",
                "generation_requests_attempted": 1}]} for c in coordinator.gate.continuation.CASES]}
        self.terminal = {"purpose": "pilot_continuation", "status": "completed_semantic_review_pending",
            "errors": [], "awake_release": {"status": "released"}, "at_utc": "2026-10-26T01:00:00Z",
            "generation_requests_attempted": 4}
        self.review = {"status": "PASS_FOR_PROSPECTIVE_MAIN_FREEZE", "coverage_reviewed": True,
            "all_attempted_stages_reviewed": True, "reviewed_case_order": list(coordinator.gate.continuation.CASES),
            "operating_feasibility": {"pass": True, "reason": "Synthetic reviewed operational evidence; not a measured live claim."}, "unresolved_system_integrity_incidents": [],
            "ordinary_model_errors_are_outcomes": True, "main_generation_calls_before_review": 0,
            "continuation_terminal_ref": self.terminal_ref, "continuation_summary_ref": self.summary_ref,
            "completed_at_utc": "2026-10-26T01:01:00Z"}

    def validate(self):
        return coordinator.gate.validate_operating_review(self.review, self.terminal, self.summary,
                                                         self.terminal_ref, self.summary_ref)

    def test_ordinary_structure_failures_do_not_require_four_valid_finals(self):
        self.validate()

    def test_raw_arithmetic_citation_semantic_errors_are_not_an_operational_veto(self):
        for case in self.summary["cases"]:
            case["stages"] = [{"stage": stage, "status": "completed", "generation_requests_attempted": 1,
                               "arithmetic_valid": False, "citation_valid": False, "semantic_failure": True}
                              for stage in ("D0", "F0")]
        self.summary["generation_requests_attempted"] = 8
        self.terminal["generation_requests_attempted"] = 8
        self.validate()

    def test_unresolved_infrastructure_incident_blocks_main(self):
        self.review["unresolved_system_integrity_incidents"] = ["hard_deadline"]
        with self.assertRaises(ValueError):
            self.validate()

    def test_global_stop_or_unattempted_independent_cell_blocks_main(self):
        self.summary["status"] = "stopped"
        self.summary["cases"][-1]["stages"] = []
        with self.assertRaises(ValueError):
            self.validate()

    def test_missing_f0_after_completed_d0_blocks_coverage_claim(self):
        self.summary["cases"][0]["stages"][0]["status"] = "completed"
        with self.assertRaises(ValueError):
            self.validate()

    def test_release_not_verified_blocks_main(self):
        self.terminal["awake_release"]["status"] = "release_not_confirmed"
        with self.assertRaises(ValueError):
            self.validate()

    def test_review_must_bind_real_terminal_and_follow_its_timestamp(self):
        self.review["completed_at_utc"] = "2026-10-26T00:59:00Z"
        with self.assertRaises(ValueError):
            self.validate()

    def test_main_candidate_and_continuation_scope_cannot_authorize_main(self):
        candidate = coordinator.read(coordinator.ROOT / "research/continuation_20261026/main_protocol_candidate.json")
        with self.assertRaises(ValueError):
            coordinator.gate.scope(candidate)
        with self.assertRaises(ValueError):
            coordinator.gate.scope({"purpose": "pilot_continuation", "case_order": list(coordinator.CASES),
                                    "max_generation_requests": 10, "automatic_retries": 0, "main_allowed": True})

    def test_actual_frozen_continuation_gate_is_rejected_as_main_authority(self):
        with self.assertRaisesRegex(ValueError, "Separate approved prospective main gate required"):
            coordinator.gate.validate_gate(coordinator.ROOT / "research/continuation_20261026/review_gate.json")


class MainReviewCoverageTests(unittest.TestCase):
    def setUp(self):
        self.frozen_at = coordinator.gate.timestamp("2026-10-26T01:02:00Z")
        self.refs = [{"path": "research/synthetic_review_" + str(i) + ".json", "sha256": str(i) * 64}
                     for i in (1, 2, 3)]
        self.sources = [coordinator.ref(coordinator.ROOT / name)
                        for name in sorted(coordinator.gate.MAIN_REVIEW_CODE)]
        self.reviews = {}
        for i, reference in enumerate(self.refs):
            self.reviews[reference["path"]] = {
                "status": "PASS", "completed_at_utc": "2026-10-26T01:01:00Z",
                "nested": {"reviewed_source_refs": self.sources if i == 0 else []},
                "review_axes": {a: {"pass": True, "reason": "Synthetic review coverage only."}
                                for a in ("errors", "consistency", "paper_topic")}}
        self.real_checked = coordinator.gate.checked
        context = patch.object(coordinator.gate, "checked", side_effect=self.checked)
        context.start()
        self.addCleanup(context.stop)

    def checked(self, reference, *, json_object=True):
        if json_object and reference["path"] in self.reviews:
            return self.reviews[reference["path"]]
        return self.real_checked(reference, json_object=json_object)

    def test_distinct_reviews_cover_exact_current_main_sources(self):
        coordinator.gate.validate_reviews(self.refs, self.frozen_at)

    def test_duplicate_review_reference_cannot_supply_three_reviews(self):
        with self.assertRaisesRegex(ValueError, "distinct paths and contents"):
            coordinator.gate.validate_reviews([self.refs[0]] * 3, self.frozen_at)

    def test_same_review_content_at_another_path_is_not_independent(self):
        self.refs[1]["sha256"] = self.refs[0]["sha256"]
        with self.assertRaisesRegex(ValueError, "distinct paths and contents"):
            coordinator.gate.validate_reviews(self.refs, self.frozen_at)

    def test_unrelated_reviews_cannot_authorize_main_scope(self):
        self.reviews[self.refs[0]["path"]]["nested"]["reviewed_source_refs"] = [
            coordinator.ref(coordinator.ROOT / "research/sector_continuation_gate.py")]
        with self.assertRaisesRegex(ValueError, "all four current modules and their tests"):
            coordinator.gate.validate_reviews(self.refs, self.frozen_at)

    def test_missing_test_source_coverage_is_rejected(self):
        self.reviews[self.refs[0]["path"]]["nested"]["reviewed_source_refs"] = [
            r for r in self.sources if Path(r["path"]).name != "test_sector_main.py"]
        with self.assertRaisesRegex(ValueError, "all four current modules and their tests"):
            coordinator.gate.validate_reviews(self.refs, self.frozen_at)

    def test_stale_nested_code_hash_is_rejected(self):
        self.sources[0]["sha256"] = "f" * 64
        with self.assertRaises(ValueError):
            coordinator.gate.validate_reviews(self.refs, self.frozen_at)

    def test_future_freeze_builder_must_be_in_main_code_inventory(self):
        self.assertIn("research/freeze_sector_main.py", coordinator.gate.REQUIRED_CODE)


if __name__ == "__main__":
    unittest.main()
