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
import run_sector_continuation as coordinator
import sector_continuation_awake as awake


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
            context = patch("run_sector_continuation." + target, replacement)
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

    def test_four_cases_eight_stages_keep_raw_errors_and_only_own_new_draft(self):
        result = self.run_sequence()
        self.assertEqual(result["status"], "attempt_sequence_finished")
        self.assertEqual(result["generation_requests_attempted"], 8)
        self.assertEqual(result["campaign_generation_requests_attempted"], 11)
        self.assertEqual([(s["case_id"], s["stage"]) for s in self.calls],
                         [(c, s) for c in coordinator.CASES for s in ("D0", "F0")])
        self.assertEqual(len(list((self.reports / "allocation_math").glob("*.json"))), 8)
        self.assertEqual(len(self.final_builds), 4)
        for case, built, spec in zip(coordinator.CASES, self.final_builds, self.calls[1::2]):
            self.assertEqual(built["raw_draft"], "synthetic-raw:" + case + ":D0")
            self.assertEqual(spec["raw_draft"], built["raw_draft"])
            self.assertEqual(spec["body"]["messages"], ["F0", built["raw_draft"]])
        events = [coordinator.read(p) for p in (self.reports / "events").glob("*.json")]
        retried = [e for e in events if e.get("overall_stage_attempt") == 2]
        self.assertEqual([(e["case_id"], e["stage"]) for e in retried], [(coordinator.CASES[0], "D0")])
        retried_cells = [e for e in events if e.get("overall_cell_attempt") == 2]
        self.assertEqual({e["stage"] for e in retried_cells}, {"D0", "F0"})

    def test_model_structure_failure_skips_own_final_but_runs_remaining_cases(self):
        self.failures[(coordinator.CASES[0], "D0")] = ("model_structure_failure", False, False)
        result = self.run_sequence()
        self.assertEqual(len(self.calls), 7)
        self.assertEqual(result["status"], "attempt_sequence_finished")
        self.assertEqual(len(result["cases"][0]["stages"]), 1)
        self.assertEqual(len(result["cases"]), 4)

    def test_system_interruption_halts_and_retains_three_missing_cases(self):
        self.failures[(coordinator.CASES[0], "D0")] = ("hard_deadline", True, False)
        result = self.run_sequence()
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(all(not c["stages"] for c in result["cases"][1:]))
        self.assertEqual(result["campaign_generation_requests_attempted"], 4)

    def test_instrument_failure_halts_even_with_completed_transport(self):
        self.bad_review.add((coordinator.CASES[0], "D0"))
        result = self.run_sequence()
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(len(self.calls), 1)

    def test_cancel_before_first_stage_issues_no_request(self):
        (self.run / "CANCEL").touch()
        result = self.run_sequence()
        self.assertEqual(result["generation_requests_attempted"], 0)
        self.assertEqual(len(result["cases"]), 4)

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
            gate_obj.update(freeze_ref={}, run_directory=str(run), output_root=str(reports), purpose="pilot_continuation",
                            case_order=list(coordinator.CASES), max_generation_requests=8,
                            historical_generation_requests=3, campaign_max_generation_requests=11,
                            automatic_retries=0, main_allowed=False, old_outputs_observed=True,
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
                 patch.object(coordinator.runtime.prepare, "read", return_value=({"origin": args.origin}, {})):
                result = coordinator.execute(args, awake_factory=RefuseAcquisition)
            self.assertEqual(released, [True])
            self.assertEqual(result["status"], "stopped_semantic_review_pending")
            self.assertEqual(result["generation_requests_attempted"], 0)
            self.assertEqual(len(coordinator.read(run / "campaign_summary.json")["cases"]), 4)
            self.assertTrue((reports / "coordinator_awake_release.json").exists())
            self.assertEqual(result["errors"][0]["type"], "RuntimeError")

    def test_existing_workspace_output_is_never_reused(self):
        with self.assertRaises(FileExistsError):
            coordinator.locations(coordinator.ROOT / "research", coordinator.ROOT / "tmp/unused-test-output")


if __name__ == "__main__":
    unittest.main()
