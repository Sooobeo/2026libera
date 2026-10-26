"""Synthetic three-segment accounting; no live outputs or service/model calls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import finalize_sector_completion as completion
from test_finalize_sector_campaign import Fixture, SyntheticRun, digest_tree, read_json, ref, write_json


class CompletionFixture:
    def stage(self, case, stage, **kwargs):
        record = Fixture.stage(self, case, stage, **kwargs)
        folder = self.run / (case + "__" + stage)
        if not (folder / "stage_review.json").exists():
            write_json(folder / "stage_review.json", {"case_id": case, "stage": stage, "synthetic": True})
        math_ref = write_json(self.reports / "allocation_math" / (folder.name + ".json"),
                              completion.math.finalize_stage(folder))
        semantic_ref = write_json(self.reports / "semantic" / (folder.name + ".json"), {
            "review_status": "completed", "case_id": case, "stage": stage,
            "transport_ref": ref(folder / "transport_result.json"),
            "findings": ["Synthetic negative source finding; no quality threshold."]})
        write_json(folder / "external_review_ack.json", {
            "schema_version": "sector_completion_stage_external_review_ack_1", "status": "completed",
            "case_id": case, "stage": stage, "model_calls": 0, "raw_model_content_modified": False,
            "worker_spec_ref": ref(folder / "worker_spec.json"), "transport_ref": ref(folder / "transport_result.json"),
            "stage_review_ref": ref(folder / "stage_review.json"), "allocation_math_ref": math_ref,
            "semantic_review_ref": semantic_ref,
            "review_axes": {axis: {"reviewed": True, "reason": "Adverse finding retained."}
                            for axis in ("errors", "consistency", "paper_topic")}})
        return record

    def __init__(self, base):
        self.base = base
        self.prior = Fixture(base / "prior")
        old_terminal = write_json(self.prior.inputs / "historical_terminal_ref.json", {
            "status": "stopped_semantic_review_pending", "at_utc": "2026-10-25T23:00:00+00:00",
            "run_directory": str(self.prior.historical.run), "generation_requests_attempted": 3,
            "summary_ref": ref(self.prior.historical.run / "pilot_summary.json")})
        for value in (self.prior.extra, self.prior.freeze, self.prior.gate, self.prior.declaration):
            value["historical_terminal_ref"] = old_terminal
        self.prior.sync()
        prior_records = {self.prior.cases[0]: [self.prior.stage(self.prior.cases[0], "D0"),
                                             self.prior.stage(self.prior.cases[0], "F0", first="0.7", second="0.5")]}
        self.prior.summary(prior_records)
        prior_summary = read_json(self.prior.run / "campaign_summary.json")
        prior_summary.update(purpose="pilot_continuation", at_utc="2026-10-26T00:00:05+00:00")
        prior_summary_ref = write_json(self.prior.run / "campaign_summary.json", prior_summary)
        prior_terminal = write_json(self.prior.reports / "terminal_receipt.json", {
            "status": "stopped_semantic_review_pending", "at_utc": "2026-10-26T00:00:06+00:00",
            "purpose": "pilot_continuation", "run_directory": str(self.prior.run),
            "output_root": str(self.prior.reports), "generation_requests_attempted": 2,
            "summary_ref": prior_summary_ref, "declaration_ref": ref(self.prior.run / "campaign_declaration.json")})
        self.run, self.reports, self.inputs = base / "completion_raw", base / "completion_reports", base / "completion_inputs"
        self.raw = SyntheticRun(self.run)
        self.cases = completion.CASES
        self.runtime = copy.deepcopy(self.prior.runtime)
        self.common = {"purpose": "pilot_completion", "case_order": list(self.cases),
                       "max_generation_requests": 6, "historical_generation_requests": 5,
                       "campaign_max_generation_requests": 11, "automatic_retries": 0,
                       "main_allowed": False, "old_outputs_observed": True,
                       "historical_first_attempt_results_unchanged": True, "explicit_retry_slots": [],
                       "historical_explicit_retry_slots": [completion.campaign.PILOT[1] + "__D0"],
                       "analysis_role": "primary_exploratory", "excluded_new_main_execution": True}
        self.extra = {key: self.prior.declaration[key] for key in (
            "historical_gate_ref", "historical_terminal_ref", "historical_summary_ref",
            "prepared_manifest_ref", "finalizer_acceptance_ref")}
        self.extra.update(prior_continuation_gate_ref=self.prior.declaration["review_gate"],
                          prior_continuation_terminal_ref=prior_terminal,
                          prior_continuation_summary_ref=prior_summary_ref,
                          prior_continuation_declaration_ref=ref(self.prior.run / "campaign_declaration.json"),
                          completion_finalizer_review_ref=write_json(self.inputs / "adapter_review.json", {"synthetic": True}))
        self.protocol = {**copy.deepcopy(self.common), "status": "approved_design_for_prospective_completion_freeze",
                         "recorded_at_utc": "2026-10-26T00:00:10+00:00", "raw_diagnostics_required": True,
                         "primary_final_allocation_endpoint": "F0_derived_integer_allocation",
                         "exact_math_policy_ref": self.extra["finalizer_acceptance_ref"]}
        location = {"run_directory": str(self.run), "output_root": str(self.reports)}
        self.freeze = {**copy.deepcopy(self.common), **self.extra, **location,
                       "status": "frozen_for_pilot_completion_only", "recorded_at_utc": "2026-10-26T00:00:11+00:00",
                       "code_refs": [ref(Path(m.__file__)) for m in (completion, completion.math, completion.campaign)]}
        self.gate = {**copy.deepcopy(self.common), **self.extra, **location,
                     "status": "approved_for_completion_before_generation", "recorded_at_utc": "2026-10-26T00:00:12+00:00"}
        self.declaration = {**copy.deepcopy(self.common), **self.extra, **location, "runtime": self.runtime,
                            "created_at_utc": "2026-10-26T00:00:13+00:00"}
        self.sync()
        write_json(self.run / "execution_started.json", {"at_utc": "2026-10-26T00:00:14+00:00"})
        self.summary({})

    sync = Fixture.sync

    def summary(self, records, status="stopped"):
        attempts = sum(s["generation_requests_attempted"] for rows in records.values() for s in rows)
        summary = {**copy.deepcopy(self.common), "status": status, "at_utc": "2026-10-26T00:00:15+00:00",
                   "cases": [{"case_id": c, "stages": records.get(c, [])} for c in self.cases],
                   "generation_requests_attempted": attempts, "campaign_generation_requests_attempted": 5 + attempts,
                   "post_final_calls": 0, "main_model_calls": 0, "original_planned_final_cells": 5,
                   "segment_planned_final_cells": 3}
        sr = write_json(self.run / "campaign_summary.json", summary)
        self.terminal = self.reports / "terminal_receipt.json"
        write_json(self.terminal, {"purpose": "pilot_completion", "at_utc": "2026-10-26T00:00:16+00:00",
                                 "status": "completed_semantic_review_pending" if status == "attempt_sequence_finished" else "stopped_semantic_review_pending",
                                 "run_directory": str(self.run), "output_root": str(self.reports),
                                 "summary_ref": sr, "declaration_ref": ref(self.run / "campaign_declaration.json"),
                                 "generation_requests_attempted": attempts, "automatic_retries": 0, "main_model_calls": 0})
        return summary

    def refresh_terminal(self):
        terminal = read_json(self.terminal)
        terminal.update(summary_ref=ref(self.run / "campaign_summary.json"),
                        declaration_ref=ref(self.run / "campaign_declaration.json"))
        write_json(self.terminal, terminal)

    def full(self):
        records = {case: [self.stage(case, "D0"), self.stage(case, "F0", first="0.8", second="0.4")]
                   for case in self.cases}
        self.summary(records, "attempt_sequence_finished")
        return records


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="completion-finalizer-test-")
        self.addCleanup(self.temp.cleanup)
        self.f = CompletionFixture(Path(self.temp.name).resolve())
        for name in ("validate_run", "validate_stage"):
            context = patch.object(completion, name)
            setattr(self, name, context.start())
            self.addCleanup(context.stop)
        self.real_ack_validator = completion.validate_acknowledgement
        context = patch.object(completion, "validate_acknowledgement", return_value={
            "status": "external_review_completed", "outcome_success_required": False, "model_calls": 0})
        self.validate_acknowledgement = context.start()
        self.addCleanup(context.stop)

    def test_full_three_segments_keep_five_cells_eleven_attempts_and_raw_bytes(self):
        self.f.full()
        before = digest_tree(self.f.base)
        result = completion.finalize_completion(self.f.run)
        self.assertEqual(before, digest_tree(self.f.base))
        self.assertEqual((result["planned_final_allocations"], result["logical_stage_slots"],
                          result["finalized_finals"], result["all_generation_requests_including_interrupted_attempt"]), (5, 10, 5, 11))
        self.assertEqual(len(result["stage_records"]), 10)
        self.assertEqual([result[k] for k in ("original_generation_requests", "prior_continuation_generation_requests", "completion_generation_requests")], [3, 2, 6])
        failed = result["all_attempt_ledger"][2]
        self.assertEqual((failed["case_id"], failed["observed_transport_status"]), (completion.campaign.PILOT[1], "hard_deadline"))
        self.assertEqual(result["all_attempt_ledger"][3]["logical_slot_attempt"], 2)
        self.assertEqual(result["all_attempt_ledger"][4]["logical_slot_attempt"], 1)
        self.assertTrue(all(r["final_total_units"] == 10000 for r in result["stage_records"]))
        self.assertFalse(result["historical_failed_attempt_erased"])
        self.assertEqual(result["semantic_review_status"], "not_performed_by_finalizer")
        self.assertEqual(self.validate_stage.call_count, 6)
        json.dumps(result, allow_nan=False)

    def test_missing_new_finals_keep_full_denominator_and_null_pairs(self):
        result = completion.finalize_completion(self.f.run)
        self.assertEqual((result["finalized_finals"], result["all_generation_requests_including_interrupted_attempt"]), (2, 5))
        self.assertEqual(len(result["completion_stage_records"]), 6)
        self.assertTrue(all(p["status"] == "unavailable" and p["total_variation_exact"] is None
                            for p in result["derived_comparisons"]["shared_control"]))
        self.assertFalse(result["missing_finals_replaced"])

    def test_model_structure_failure_and_zero_request_preflight_are_preserved(self):
        records = {self.f.cases[0]: [self.f.stage(self.f.cases[0], "D0", status="model_structure_failure")],
                   self.f.cases[1]: [self.f.stage(self.f.cases[1], "D0", status="preflight_failed", attempts=0)]}
        self.f.summary(records)
        result = completion.finalize_completion(self.f.run)
        self.assertEqual(result["all_generation_requests_including_interrupted_attempt"], 6)
        self.assertEqual(result["completion_stage_records"][0]["observed_transport_status"], "model_structure_failure")
        self.assertEqual(result["completion_stage_records"][2]["generation_requests_attempted"], 0)

    def test_live_summary_is_rejected_before_any_math_or_history(self):
        summary = read_json(self.f.run / "campaign_summary.json")
        summary["status"] = "running"
        write_json(self.f.run / "campaign_summary.json", summary)
        with patch.object(completion.math, "finalize_stage") as stage, patch.object(completion.math, "finalize_run") as history:
            with self.assertRaisesRegex(ValueError, "terminal_completion"):
                completion.finalize_completion(self.f.run)
            stage.assert_not_called()
            history.assert_not_called()

    def test_missing_terminal_is_rejected_before_history(self):
        self.f.terminal.unlink()
        with patch.object(completion.math, "finalize_run") as history:
            with self.assertRaises(FileNotFoundError):
                completion.finalize_completion(self.f.run)
            history.assert_not_called()

    def test_candidate_authority_is_rejected(self):
        self.f.protocol["status"] = "candidate_for_root_review_not_execution_approval"
        self.f.sync()
        self.f.refresh_terminal()
        with self.assertRaisesRegex(ValueError, "approved_amended_endpoint"):
            completion.finalize_completion(self.f.run)

    def test_fidelity_rerun_or_new_main_scope_is_rejected(self):
        for field, value in (("case_order", list(completion.campaign.PILOT[1:])), ("main_allowed", True),
                             ("excluded_new_main_execution", False), ("historical_generation_requests", 3)):
            declaration = read_json(self.f.run / "campaign_declaration.json")
            original = copy.deepcopy(declaration)
            declaration[field] = value
            write_json(self.f.run / "campaign_declaration.json", declaration)
            with self.assertRaisesRegex(ValueError, "completion_scope_mismatch"):
                completion.finalize_completion(self.f.run)
            write_json(self.f.run / "campaign_declaration.json", original)

    def test_terminal_cross_run_binding_rejected(self):
        terminal = read_json(self.f.terminal)
        terminal["run_directory"] = str(self.f.prior.run)
        write_json(self.f.terminal, terminal)
        with self.assertRaisesRegex(ValueError, "terminal_binding"):
            completion.finalize_completion(self.f.run)

    def test_hidden_request_directory_is_rejected(self):
        (self.f.run / "fidelity_q2_2026__E__D0").mkdir()
        with self.assertRaisesRegex(ValueError, "unaccounted_completion_stage"):
            completion.finalize_completion(self.f.run)

    def test_summary_cannot_hide_request(self):
        self.f.full()
        summary = read_json(self.f.run / "campaign_summary.json")
        summary["cases"][0]["stages"][0]["generation_requests_attempted"] = 0
        write_json(self.f.run / "campaign_summary.json", summary)
        self.f.refresh_terminal()
        with self.assertRaisesRegex(ValueError, "summary_stage_accounting"):
            completion.finalize_completion(self.f.run)

    def test_cumulative_total_cannot_drop_historical_failure(self):
        summary = read_json(self.f.run / "campaign_summary.json")
        summary["campaign_generation_requests_attempted"] = 4
        write_json(self.f.run / "campaign_summary.json", summary)
        self.f.refresh_terminal()
        with self.assertRaisesRegex(ValueError, "summary_total_mismatch"):
            completion.finalize_completion(self.f.run)

    def test_raw_sum_errors_are_finalized_without_becoming_semantic_success(self):
        records = {self.f.cases[0]: [self.f.stage(self.f.cases[0], "D0", first="0.7", second="0.5"),
                                    self.f.stage(self.f.cases[0], "F0", first="0.7", second="0.5")]}
        self.f.summary(records)
        result = completion.finalize_completion(self.f.run)
        row = result["completion_stage_records"][1]
        self.assertEqual(row["status"], "finalized")
        self.assertEqual(row["final_total_units"], 10000)
        self.assertTrue(result["raw_diagnostics_required"])
        self.assertEqual(result["semantic_review_status"], "not_performed_by_finalizer")

    def test_cross_case_prior_D0_cannot_be_substituted(self):
        self.f.full()
        folder = self.f.run / (self.f.cases[0] + "__F0")
        spec = read_json(folder / "worker_spec.json")
        spec["draft_artifacts"]["response"] = ref(self.f.run / (self.f.cases[1] + "__D0") / "http_0001_generation/response.json")
        write_json(folder / "worker_spec.json", spec)
        self.f.raw.refresh_review(folder)
        with self.assertRaisesRegex(ValueError, "own_new_D0_binding"):
            completion.finalize_completion(self.f.run)

    def test_runtime_validation_errors_propagate(self):
        self.validate_run.side_effect = ValueError("synthetic stale gate")
        with self.assertRaisesRegex(ValueError, "synthetic stale gate"):
            completion.finalize_completion(self.f.run)

    def test_stage_validation_errors_propagate(self):
        self.f.summary({self.f.cases[0]: [self.f.stage(self.f.cases[0], "D0")]})
        self.validate_stage.side_effect = ValueError("synthetic wrong source")
        with self.assertRaisesRegex(ValueError, "synthetic wrong source"):
            completion.finalize_completion(self.f.run)

    def test_post_final_extra_request_is_rejected(self):
        summary = read_json(self.f.run / "campaign_summary.json")
        summary["post_final_calls"] = 1
        write_json(self.f.run / "campaign_summary.json", summary)
        self.f.refresh_terminal()
        with self.assertRaisesRegex(ValueError, "post_final_calls"):
            completion.finalize_completion(self.f.run)

    def test_math_policy_and_original_diagnostics_cannot_silently_change(self):
        self.f.protocol["raw_diagnostics_required"] = False
        self.f.sync()
        self.f.refresh_terminal()
        with self.assertRaisesRegex(ValueError, "approved_amended_endpoint"):
            completion.finalize_completion(self.f.run)

    def test_finalizer_source_must_be_frozen(self):
        self.f.freeze["code_refs"] = self.f.freeze["code_refs"][1:]
        self.f.sync()
        self.f.refresh_terminal()
        with self.assertRaisesRegex(ValueError, "all_three_finalizer"):
            completion.finalize_completion(self.f.run)

    def test_last_missing_ack_after_stop_is_preserved_without_future_authorization(self):
        self.f.summary({self.f.cases[0]: [self.f.stage(self.f.cases[0], "D0")]})
        (self.f.run / (self.f.cases[0] + "__D0") / "external_review_ack.json").unlink()
        result = completion.finalize_completion(self.f.run)
        self.assertEqual(result["external_review_acknowledgements"][0]["status"], "unavailable_or_invalid")
        self.assertEqual(result["all_generation_requests_including_interrupted_attempt"], 6)

    def test_progression_without_prior_ack_is_rejected(self):
        self.f.full()
        (self.f.run / (self.f.cases[0] + "__D0") / "external_review_ack.json").unlink()
        with self.assertRaisesRegex(ValueError, "progression_without_valid_external_review"):
            completion.finalize_completion(self.f.run)

    def test_normal_completion_requires_last_ack_too(self):
        self.f.full()
        (self.f.run / (self.f.cases[-1] + "__F0") / "external_review_ack.json").unlink()
        with self.assertRaisesRegex(ValueError, "progression_without_valid_external_review"):
            completion.finalize_completion(self.f.run)

    def test_ack_math_cannot_claim_a_different_finalization(self):
        self.f.full()
        folder = self.f.run / (self.f.cases[0] + "__D0")
        ack = read_json(folder / "external_review_ack.json")
        math_path = Path(ack["allocation_math_ref"]["path"])
        sidecar = read_json(math_path)
        sidecar["final_total_units"] = 9999
        ack["allocation_math_ref"] = write_json(math_path, sidecar)
        write_json(folder / "external_review_ack.json", ack)
        with self.assertRaisesRegex(ValueError, "progression_without_valid_external_review"):
            completion.finalize_completion(self.f.run)

    def test_ack_validator_failure_cannot_authorize_progression(self):
        self.f.full()
        self.validate_acknowledgement.side_effect = ValueError("Synthetic stale semantic reference")
        with self.assertRaisesRegex(ValueError, "progression_without_valid_external_review"):
            completion.finalize_completion(self.f.run)

    def test_actual_pure_ack_validator_accepts_adverse_findings(self):
        self.f.summary({self.f.cases[0]: [self.f.stage(self.f.cases[0], "D0", first="0.7", second="0.5")]})
        self.validate_acknowledgement.side_effect = self.real_ack_validator
        result = completion.finalize_completion(self.f.run)
        acknowledgement = result["external_review_acknowledgements"][0]
        self.assertEqual(acknowledgement["status"], "external_review_completed")
        self.assertFalse(acknowledgement["outcome_success_required"])
        self.assertEqual(result["completion_stage_records"][0]["final_total_units"], 10000)


if __name__ == "__main__":
    unittest.main()
