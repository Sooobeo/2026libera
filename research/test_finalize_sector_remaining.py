"""Synthetic four-segment finalizer tests; no model or service calls.

Runtime/gate and acknowledgement delegates are mocked at their public boundary;
artifact, terminal, historical accounting, exact history and math checks are real.
The remaining runtime suite separately tests its own gate and ACK contracts.
"""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import finalize_sector_remaining as remaining
from test_finalize_sector_completion import CompletionFixture
from test_finalize_sector_campaign import Fixture, SyntheticRun, digest_tree, read_json, ref, write_json


class RemainingFixture:
    sync = Fixture.sync

    def __init__(self, base):
        self.base = base
        self.previous = CompletionFixture(base / "history")
        old_record = self.previous.stage(remaining.CASES[0], "D0", first="0.6", second="0.35")
        self.previous.summary({remaining.CASES[0]: [old_record]})
        old_folder = self.previous.run / (remaining.CASES[0] + "__D0")
        old_spec = read_json(old_folder / "worker_spec.json")
        draft = read_json(old_folder / "http_0001_generation/response.json")["message"]["content"]
        final = {"ready": True, "messages": old_spec["body"]["messages"] + [
            {"role": "assistant", "content": draft}, {"role": "user", "content": "Preserved synthetic F0 feedback"}]}
        final_ref = write_json(self.previous.run / (remaining.CASES[0] + "__final_construction.json"), final)
        self.run, self.reports, self.inputs = base / "remaining_raw", base / "remaining_reports", base / "remaining_inputs"
        self.raw, self.cases = SyntheticRun(self.run), remaining.CASES
        self.runtime = copy.deepcopy(self.previous.runtime)
        self.common = {**copy.deepcopy(self.previous.common), "purpose": remaining.PURPOSE,
                       "stage_order": list(remaining.STAGE_ORDER), "max_generation_requests": 5,
                       "historical_generation_requests": 6, "main_model_calls": 0, "post_final_calls": 0}
        self.extra = {k: self.previous.declaration[k] for k in remaining.completion.BOUND}
        self.extra.update(prior_completion_gate_ref=self.previous.declaration["review_gate"],
                          prior_completion_terminal_ref=ref(self.previous.terminal),
                          prior_completion_summary_ref=ref(self.previous.run / "campaign_summary.json"),
                          prior_completion_declaration_ref=ref(self.previous.run / "campaign_declaration.json"),
                          remaining_finalizer_review_ref=write_json(self.inputs / "review.json", {"synthetic": True}))
        external = {role: ref(old_folder / name) for role, name in (
            ("response", "http_0001_generation/response.json"), ("worker_spec", "worker_spec.json"),
            ("worker_summary", "worker_summary.json"), ("supervisor_result", "supervisor_result.json"),
            ("transport_result", "transport_result.json"))}
        old_ack = read_json(old_folder / "external_review_ack.json")
        evidence = {key: old_ack[key + "_ref"] for key in ("stage_review", "allocation_math", "semantic_review")}
        evidence.update(external_review_ack=ref(old_folder / "external_review_ack.json"),
                        terminal=self.extra["prior_completion_terminal_ref"], summary=self.extra["prior_completion_summary_ref"],
                        declaration=self.extra["prior_completion_declaration_ref"], final_construction=final_ref)
        self.operating = {"external_draft_refs": external, "external_draft_evidence_refs": evidence,
                          "power_policy": {"version": "synthetic-bound-policy"}}
        self.protocol = {**copy.deepcopy(self.common), **copy.deepcopy(self.operating),
                         "status": "approved_design_for_prospective_remaining_freeze", "recorded_at_utc": "2026-10-26T00:00:20+00:00",
                         "raw_diagnostics_required": True, "primary_final_allocation_endpoint": "F0_derived_integer_allocation",
                         "exact_math_policy_ref": self.extra["finalizer_acceptance_ref"]}
        location = {"run_directory": str(self.run), "output_root": str(self.reports)}
        self.freeze = {**copy.deepcopy(self.common), **self.extra, **copy.deepcopy(self.operating), **location,
                       "status": "frozen_for_pilot_remaining_only", "recorded_at_utc": "2026-10-26T00:00:21+00:00",
                       "code_refs": [ref(Path(m.__file__)) for m in (remaining, remaining.math, remaining.campaign, remaining.completion)]}
        self.gate = {**copy.deepcopy(self.common), **self.extra, **copy.deepcopy(self.operating), **location,
                     "status": "approved_for_remaining_before_generation", "recorded_at_utc": "2026-10-26T00:00:22+00:00"}
        self.declaration = {**copy.deepcopy(self.common), **self.extra, **copy.deepcopy(self.operating), **location,
                            "runtime": self.runtime, "created_at_utc": "2026-10-26T00:00:23+00:00"}
        self.sync()
        write_json(self.run / "execution_started.json", {"at_utc": "2026-10-26T00:00:24+00:00"})
        self.summary({})

    def stage(self, case, stage, **kwargs):
        if case == remaining.CASES[0] and stage == "F0":
            record = self.raw.make_stage(case, stage, **kwargs)
            folder = self.run / (case + "__" + stage)
            spec = read_json(folder / "worker_spec.json")
            final = read_json(Path(self.operating["external_draft_evidence_refs"]["final_construction"]["path"]))
            spec.update(runtime=self.runtime, review_gate=self.declaration["review_gate"],
                        raw_draft=final["messages"][2]["content"], draft_artifacts=self.operating["external_draft_refs"])
            spec["body"]["messages"] = final["messages"]
            write_json(folder / "worker_spec.json", spec)
            if record["status"] == "completed":
                self.raw.refresh_review(folder)
        else:
            record = Fixture.stage(self, case, stage, **kwargs)
            folder = self.run / (case + "__" + stage)
        if not (folder / "stage_review.json").exists():
            write_json(folder / "stage_review.json", {"case_id": case, "stage": stage})
        mr = write_json(self.reports / "allocation_math" / (folder.name + ".json"), remaining.math.finalize_stage(folder))
        sem = write_json(self.reports / "semantic" / (folder.name + ".json"), {
            "review_status": "completed", "case_id": case, "stage": stage,
            "transport_ref": ref(folder / "transport_result.json"), "findings": ["Negative synthetic finding retained."]})
        write_json(folder / "external_review_ack.json", {"schema_version": "sector_remaining_stage_external_review_ack_1",
            "status": "completed", "case_id": case, "stage": stage, "model_calls": 0, "raw_model_content_modified": False,
            "worker_spec_ref": ref(folder / "worker_spec.json"), "transport_ref": ref(folder / "transport_result.json"),
            "stage_review_ref": ref(folder / "stage_review.json"), "allocation_math_ref": mr, "semantic_review_ref": sem,
            "review_axes": {axis: {"reviewed": True, "reason": "Adverse observations retained."} for axis in ("errors", "consistency", "paper_topic")}})
        return record

    def summary(self, records, status="stopped"):
        attempts = sum(s["generation_requests_attempted"] for stages in records.values() for s in stages)
        value = {**copy.deepcopy(self.common), "status": status, "at_utc": "2026-10-26T00:00:25+00:00",
                 "cases": [{"case_id": c, "stages": records.get(c, [])} for c in self.cases],
                 "generation_requests_attempted": attempts, "campaign_generation_requests_attempted": 6 + attempts,
                 "original_planned_final_cells": 5, "segment_planned_final_cells": 3}
        sr = write_json(self.run / "campaign_summary.json", value)
        self.terminal = self.reports / "terminal_receipt.json"
        write_json(self.terminal, {"purpose": remaining.PURPOSE, "at_utc": "2026-10-26T00:00:26+00:00",
            "status": "completed_semantic_review_pending" if status == "attempt_sequence_finished" else "stopped_semantic_review_pending",
            "run_directory": str(self.run), "output_root": str(self.reports), "summary_ref": sr,
            "declaration_ref": ref(self.run / "campaign_declaration.json"), "generation_requests_attempted": attempts,
            "automatic_retries": 0, "main_model_calls": 0})
        return value

    def refresh_terminal(self):
        terminal = read_json(self.terminal)
        terminal.update(summary_ref=ref(self.run / "campaign_summary.json"), declaration_ref=ref(self.run / "campaign_declaration.json"))
        write_json(self.terminal, terminal)

    def full(self):
        records = {self.cases[0]: [self.stage(self.cases[0], "F0", first="0.8", second="0.4")]}
        for case in self.cases[1:]:
            records[case] = [self.stage(case, "D0"), self.stage(case, "F0")]
        self.summary(records, "attempt_sequence_finished")
        return records


class RemainingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="remaining-finalizer-test-")
        self.addCleanup(self.temp.cleanup)
        self.f = RemainingFixture(Path(self.temp.name).resolve())
        for module in (remaining, remaining.completion):
            for name in ("validate_run", "validate_stage"):
                context = patch.object(module, name)
                context.start()
                self.addCleanup(context.stop)
            context = patch.object(module, "validate_acknowledgement", return_value={
                "status": "external_review_completed", "outcome_success_required": False, "model_calls": 0})
            mocked = context.start()
            if module is remaining:
                self.ack_validator = mocked
            self.addCleanup(context.stop)

    def result(self):
        return remaining.finalize_remaining(self.f.run)

    def test_full_five_remaining_slots_preserve_all_four_segments_and_bytes(self):
        self.f.full()
        before = digest_tree(self.f.base)
        result = self.result()
        self.assertEqual(before, digest_tree(self.f.base))
        self.assertEqual([result[k] for k in ("planned_final_allocations", "logical_stage_slots", "finalized_finals",
                         "remaining_generation_requests", "all_generation_requests_including_interrupted_attempt")], [5, 10, 5, 5, 11])
        self.assertEqual([result[k] for k in ("original_generation_requests", "prior_continuation_generation_requests", "completion_generation_requests")], [3, 2, 1])
        ledger = result["all_attempt_ledger"]
        self.assertEqual(ledger[2]["observed_transport_status"], "hard_deadline")
        self.assertEqual(ledger[3]["logical_slot_attempt"], 2)
        self.assertEqual(sum(r["case_id"] == self.f.cases[0] and r["stage"] == "D0" for r in ledger), 1)
        pair = result["derived_comparisons"]["own_D0_F0"][2]
        self.assertEqual(pair["status"], "computed")
        carried = result["stage_records"][4]
        self.assertEqual(carried["run_directory"], str(self.f.previous.run))
        self.assertEqual(result["stage_records"][5]["run_directory"], str(self.f.run))

    def test_zero_new_attempts_keep_carried_D0_and_full_denominators(self):
        result = self.result()
        self.assertEqual((result["finalized_finals"], result["all_generation_requests_including_interrupted_attempt"]), (2, 6))
        self.assertEqual(len(result["remaining_stage_records"]), 5)
        self.assertEqual(len(result["stage_records"]), 10)
        self.assertEqual(result["planned_final_sector_rows"], 55)
        self.assertEqual(result["derived_comparisons"]["own_D0_F0"][2]["status"], "unavailable")

    def test_no_completed_output_quality_threshold(self):
        c = self.f.cases[0]
        self.f.summary({c: [self.f.stage(c, "F0", first="-0.1", second="1.1")]})
        result = self.result()
        self.assertEqual(result["remaining_stage_records"][0]["status"], "unavailable")
        self.assertEqual(result["all_generation_requests_including_interrupted_attempt"], 7)
        self.assertEqual(result["external_review_acknowledgements"][0]["status"], "external_review_completed")

    def test_structure_failure_skips_own_F0_but_allows_next_independent_case(self):
        e, l, c = self.f.cases
        records = {e: [self.f.stage(e, "F0")], l: [self.f.stage(l, "D0", status="model_structure_failure")],
                   c: [self.f.stage(c, "D0"), self.f.stage(c, "F0")]}
        self.f.summary(records, "attempt_sequence_finished")
        result = self.result()
        self.assertEqual(result["remaining_generation_requests"], 4)
        self.assertEqual(result["finalized_finals"], 4)
        self.assertEqual(result["remaining_stage_records"][2]["reasons"], ["not_attempted"])

    def test_terminal_required_before_historical_or_stage_traversal(self):
        self.f.terminal.unlink()
        with patch.object(remaining, "historical_dataset") as historical, self.assertRaises(OSError):
            self.result()
        historical.assert_not_called()

    def test_active_summary_rejected(self):
        value = read_json(self.f.run / "campaign_summary.json")
        value["status"] = "running"
        write_json(self.f.run / "campaign_summary.json", value)
        self.f.refresh_terminal()
        with self.assertRaisesRegex(ValueError, "terminal_remaining"):
            self.result()

    def test_wrong_scope_or_stage_order_rejected(self):
        for key, value in (("purpose", "main"), ("historical_generation_requests", 5), ("max_generation_requests", 6),
                           ("main_model_calls", 1), ("stage_order", list(reversed(remaining.STAGE_ORDER)))):
            altered = {**self.f.declaration, key: value}
            with self.subTest(key=key), self.assertRaises(ValueError):
                remaining.scope(altered)

    def test_candidate_cannot_act_as_approved_protocol(self):
        self.f.protocol["status"] = "candidate"
        self.f.sync()
        self.f.refresh_terminal()
        with self.assertRaisesRegex(ValueError, "approved_remaining_protocol"):
            self.result()

    def test_frozen_source_coverage_required(self):
        self.f.freeze["code_refs"] = [r for r in self.f.freeze["code_refs"] if Path(r["path"]).name != "finalize_sector_completion.py"]
        self.f.sync()
        self.f.refresh_terminal()
        with self.assertRaisesRegex(ValueError, "historical_finalizer_sources"):
            self.result()

    def test_operating_policy_must_equal_protocol_and_authority(self):
        self.f.protocol["power_policy"] = {"version": "changed"}
        self.f.sync()
        self.f.refresh_terminal()
        with self.assertRaisesRegex(ValueError, "protocol_operating_binding"):
            self.result()

    def test_wrong_external_role_path_rejected_even_with_no_new_generation(self):
        wrong = write_json(self.f.inputs / "wrong_response.json", read_json(Path(self.f.operating["external_draft_refs"]["response"]["path"])))
        for target in (self.f.protocol, self.f.freeze, self.f.gate, self.f.declaration):
            target["external_draft_refs"]["response"] = wrong
        self.f.sync()
        self.f.refresh_terminal()
        with self.assertRaisesRegex(ValueError, "fixed_old_UBS_E_D0"):
            self.result()

    def test_external_saved_final_history_substitution_rejected(self):
        reference = self.f.operating["external_draft_evidence_refs"]["final_construction"]
        final = read_json(Path(reference["path"]))
        final["messages"][2]["content"] += " changed"
        new_ref = write_json(Path(reference["path"]), final)
        for target in (self.f.protocol, self.f.freeze, self.f.gate, self.f.declaration):
            target["external_draft_evidence_refs"]["final_construction"] = new_ref
        self.f.sync()
        self.f.refresh_terminal()
        with self.assertRaisesRegex(ValueError, "lost_exact_history"):
            self.result()

    def test_new_F0_cannot_replace_actual_external_assistant_text(self):
        case = self.f.cases[0]
        record = self.f.stage(case, "F0")
        path = self.f.run / (case + "__F0") / "worker_spec.json"
        spec = read_json(path)
        spec["raw_draft"] += "changed"
        write_json(path, spec)
        self.f.raw.refresh_review(path.parent)
        self.f.summary({case: [record]})
        with self.assertRaisesRegex(ValueError, "external_own_D0_history"):
            self.result()

    def test_new_UBS_E_D0_directory_is_never_a_second_request(self):
        (self.f.run / (self.f.cases[0] + "__D0")).mkdir()
        with self.assertRaisesRegex(ValueError, "unaccounted_remaining"):
            self.result()

    def test_completed_D0_missing_F0_cannot_skip_to_later_case(self):
        e, l, c = self.f.cases
        records = {e: [self.f.stage(e, "F0")], l: [self.f.stage(l, "D0")], c: [self.f.stage(c, "D0")]}
        self.f.summary(records)
        with self.assertRaisesRegex(ValueError, "completed_D0_missing_F0"):
            self.result()

    def test_normal_finish_requires_all_independent_slots(self):
        self.f.summary({}, "attempt_sequence_finished")
        with self.assertRaisesRegex(ValueError, "skipped_independent"):
            self.result()

    def test_last_stopped_ACK_gap_retained_without_fabricated_success(self):
        case = self.f.cases[0]
        self.f.summary({case: [self.f.stage(case, "F0")]})
        (self.f.run / (case + "__F0") / "external_review_ack.json").unlink()
        result = self.result()
        self.assertEqual(result["external_review_acknowledgements"][0]["status"], "unavailable_or_invalid")
        self.assertEqual(result["all_generation_requests_including_interrupted_attempt"], 7)

    def test_missing_earlier_ACK_cannot_hide_progression(self):
        e, l, _ = self.f.cases
        self.f.summary({e: [self.f.stage(e, "F0")], l: [self.f.stage(l, "D0")]})
        (self.f.run / (e + "__F0") / "external_review_ack.json").unlink()
        with self.assertRaisesRegex(ValueError, "progression_without_valid"):
            self.result()

    def test_normal_finish_cannot_have_last_missing_ACK(self):
        self.f.full()
        (self.f.run / remaining.STAGE_ORDER[-1] / "external_review_ack.json").unlink()
        with self.assertRaisesRegex(ValueError, "progression_without_valid"):
            self.result()

    def test_wrong_cumulative_count_rejected(self):
        value = read_json(self.f.run / "campaign_summary.json")
        value["campaign_generation_requests_attempted"] = 7
        write_json(self.f.run / "campaign_summary.json", value)
        self.f.refresh_terminal()
        with self.assertRaisesRegex(ValueError, "summary_total_mismatch"):
            self.result()

    def test_extend_ledger_rejects_historical_D0_duplicate(self):
        previous = {"all_attempt_ledger": [{"case_id": self.f.cases[0], "stage": "D0"}] * 6}
        row = {"case_id": self.f.cases[0], "stage": "D0", "generation_requests_attempted": 1}
        with self.assertRaisesRegex(ValueError, "repeats_historical_or_unplanned"):
            remaining.extend_ledger(previous, [row])


if __name__ == "__main__":
    unittest.main(verbosity=2)
