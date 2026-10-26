"""Synthetic last-slot accounting; no model/service calls or live output reads."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import finalize_sector_last_final as last
from test_finalize_sector_remaining import RemainingFixture
from test_finalize_sector_campaign import Fixture, SyntheticRun, digest_tree, read_json, ref, write_json


class LastFixture:
    sync = Fixture.sync

    def __init__(self, base):
        self.base = base
        self.previous = RemainingFixture(base / "history")
        p = self.previous
        e, l, c = p.cases
        records = {e: [p.stage(e, "F0")], l: [p.stage(l, "D0"), p.stage(l, "F0")], c: [p.stage(c, "D0")]}
        p.summary(records)
        folder = p.run / (c + "__D0")
        ack = read_json(folder / "external_review_ack.json")
        (folder / "external_review_ack.json").unlink()
        sem_path = Path(ack["semantic_review_ref"]["path"])
        sem = read_json(sem_path)
        sem.update(completed_at_utc="2026-10-26T00:00:27+00:00", review_axes={
            axis: {"reviewed": True, "reason": "Negative findings retained after terminal."}
            for axis in ("errors", "consistency", "paper_topic")})
        sem_ref = write_json(sem_path, sem)
        old_spec = read_json(folder / "worker_spec.json")
        raw = read_json(folder / "http_0001_generation/response.json")["message"]["content"]
        self.run, self.reports, self.inputs = base / "last_raw", base / "last_reports", base / "last_inputs"
        self.raw = SyntheticRun(self.run)
        self.runtime = copy.deepcopy(p.runtime)
        self.common = {**copy.deepcopy(p.common), "purpose": last.PURPOSE, "case_order": list(last.CASES),
                       "stage_order": list(last.STAGE_ORDER), "max_generation_requests": 1, "historical_generation_requests": 10}
        self.extra = {k: p.declaration[k] for k in last.previous.BOUND}
        self.extra.update(prior_remaining_gate_ref=p.declaration["review_gate"],
            prior_remaining_terminal_ref=ref(p.terminal), prior_remaining_summary_ref=ref(p.run / "campaign_summary.json"),
            prior_remaining_declaration_ref=ref(p.run / "campaign_declaration.json"),
            prior_remaining_cancel_ref=write_json(p.run / "CANCEL", {"synthetic": True}),
            prior_pause_checkpoint_ref=write_json(self.inputs / "pause.json", {"synthetic": True}),
            resumption_design_ref=write_json(self.inputs / "resumption_design.json", {"synthetic": True}),
            last_finalizer_review_ref=write_json(self.inputs / "review.json", {"synthetic": True}))
        draft = {role: ref(folder / name) for role, name in (
            ("response", "http_0001_generation/response.json"), ("worker_spec", "worker_spec.json"),
            ("worker_summary", "worker_summary.json"), ("supervisor_result", "supervisor_result.json"),
            ("transport_result", "transport_result.json"))}
        self.final = {"ready": True, "messages": old_spec["body"]["messages"] + [
            {"role": "assistant", "content": raw}, {"role": "user", "content": "Synthetic source-free feedback"}]}
        evidence = {"stage_review": ack["stage_review_ref"], "allocation_math": ack["allocation_math_ref"],
            "semantic_review": sem_ref, "semantic_validation": write_json(self.inputs / "semantic_validation.json", {"status": "PASS"}),
            "root_review": write_json(self.inputs / "root_review.json", {"review_status": "completed"}),
            "terminal": self.extra["prior_remaining_terminal_ref"], "summary": self.extra["prior_remaining_summary_ref"],
            "declaration": self.extra["prior_remaining_declaration_ref"],
            "final_construction": write_json(self.inputs / "prepared_final_construction.json", self.final)}
        self.operating = {"external_draft_refs": draft, "external_draft_evidence_refs": evidence,
                          "power_policy": {"version": "synthetic-bound-policy"}}
        self.protocol = {**copy.deepcopy(self.common), **copy.deepcopy(self.operating),
            "status": "approved_design_for_prospective_last_final_freeze", "recorded_at_utc": "2026-10-26T00:00:30+00:00",
            "raw_diagnostics_required": True, "primary_final_allocation_endpoint": "F0_derived_integer_allocation",
            "exact_math_policy_ref": self.extra["finalizer_acceptance_ref"]}
        location = {"run_directory": str(self.run), "output_root": str(self.reports)}
        self.freeze = {**copy.deepcopy(self.common), **self.extra, **copy.deepcopy(self.operating), **location,
            "status": "frozen_for_pilot_last_final_only", "recorded_at_utc": "2026-10-26T00:00:31+00:00",
            "code_refs": [ref(Path(m.__file__)) for m in (last, last.previous, last.math, last.campaign, last.completion)]}
        self.gate = {**copy.deepcopy(self.common), **self.extra, **copy.deepcopy(self.operating), **location,
            "status": "approved_for_last_final_before_generation", "recorded_at_utc": "2026-10-26T00:00:32+00:00"}
        self.declaration = {**copy.deepcopy(self.common), **self.extra, **copy.deepcopy(self.operating), **location,
            "runtime": self.runtime, "created_at_utc": "2026-10-26T00:00:33+00:00"}
        self.sync()
        write_json(self.run / "execution_started.json", {"at_utc": "2026-10-26T00:00:34+00:00"})
        self.summary([])

    def stage(self, **kwargs):
        record = self.raw.make_stage(last.CASE, "F0", **kwargs)
        folder = self.run / last.STAGE_ORDER[0]
        spec = read_json(folder / "worker_spec.json")
        spec.update(runtime=self.runtime, review_gate=self.declaration["review_gate"],
                    raw_draft=self.final["messages"][2]["content"], draft_artifacts=self.operating["external_draft_refs"])
        spec["body"]["messages"] = self.final["messages"]
        write_json(folder / "worker_spec.json", spec)
        if record["status"] == "completed":
            self.raw.refresh_review(folder)
        if not (folder / "stage_review.json").exists():
            write_json(folder / "stage_review.json", {"case_id": last.CASE, "stage": "F0"})
        mr = write_json(self.reports / "allocation_math" / (folder.name + ".json"), last.math.finalize_stage(folder))
        sem = write_json(self.reports / "semantic/final.json", {"review_status": "completed", "case_id": last.CASE,
            "stage": "F0", "transport_ref": ref(folder / "transport_result.json"), "findings": ["Adverse synthetic finding"]})
        write_json(folder / "external_review_ack.json", {"worker_spec_ref": ref(folder / "worker_spec.json"),
            "transport_ref": ref(folder / "transport_result.json"), "stage_review_ref": ref(folder / "stage_review.json"),
            "allocation_math_ref": mr, "semantic_review_ref": sem})
        return record

    def summary(self, records, status="stopped"):
        attempts = sum(r["generation_requests_attempted"] for r in records)
        self.summary_value = {**copy.deepcopy(self.common), "status": status, "at_utc": "2026-10-26T00:00:35+00:00",
            "cases": [{"case_id": last.CASE, "stages": records}], "generation_requests_attempted": attempts,
            "campaign_generation_requests_attempted": 10 + attempts, "original_planned_final_cells": 5,
            "segment_planned_final_cells": 1}
        sr = write_json(self.run / "campaign_summary.json", self.summary_value)
        self.terminal = self.reports / "terminal_receipt.json"
        write_json(self.terminal, {"purpose": last.PURPOSE, "at_utc": "2026-10-26T00:00:36+00:00",
            "status": "completed_semantic_review_pending" if status == "attempt_sequence_finished" else "stopped_semantic_review_pending",
            "run_directory": str(self.run), "output_root": str(self.reports), "summary_ref": sr,
            "declaration_ref": ref(self.run / "campaign_declaration.json"), "generation_requests_attempted": attempts,
            "automatic_retries": 0, "main_model_calls": 0})

    def refresh(self):
        self.sync()
        self.summary(self.summary_value["cases"][0]["stages"], self.summary_value["status"])


class LastFinalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="last-final-test-")
        self.addCleanup(self.temp.cleanup)
        self.f = LastFixture(Path(self.temp.name).resolve())
        for module in (last, last.previous, last.completion):
            for name in ("validate_run", "validate_stage"):
                ctx = patch.object(module, name)
                ctx.start(); self.addCleanup(ctx.stop)
            ctx = patch.object(module, "validate_acknowledgement", return_value={"status": "external_review_completed", "outcome_success_required": False})
            ctx.start(); self.addCleanup(ctx.stop)

    def result(self):
        return last.finalize_last_final(self.f.run)

    def test_plaintext_cancel_is_hash_bound_without_json_requirement(self):
        path = self.f.previous.run / "CANCEL"
        path.write_text("User requested pause.\n", encoding="utf-8")
        for value in (self.f.freeze, self.f.gate, self.f.declaration):
            value["prior_remaining_cancel_ref"] = ref(path)
        self.f.refresh()
        self.assertEqual(self.result()["last_final_generation_requests"], 0)

    def test_full_last_final_preserves_all_previous_bytes_and_eleven_attempts(self):
        self.f.summary([self.f.stage(first="0.8", second="0.4")], "attempt_sequence_finished")
        before = digest_tree(self.f.base)
        r = self.result()
        self.assertEqual(before, digest_tree(self.f.base))
        self.assertEqual([r[k] for k in ("planned_final_allocations", "planned_final_sector_rows", "logical_stage_slots", "finalized_finals", "all_generation_requests_including_interrupted_attempt")], [5, 55, 10, 5, 11])
        self.assertEqual(r["all_attempt_ledger"][-1]["segment"], "last_final")
        self.assertEqual(sum(x["case_id"] == last.CASE and x["stage"] == "D0" for x in r["all_attempt_ledger"]), 1)
        self.assertEqual(r["prior_remaining_derived_report"]["external_review_acknowledgements"][-1]["status"], "unavailable_or_invalid")
        self.assertFalse(r["external_review_reconciliation"]["old_ACK_created"])
        self.assertEqual(r["stage_records"][-2]["run_directory"], str(self.f.previous.run))
        self.assertEqual(r["stage_records"][-1]["run_directory"], str(self.f.run))
        self.assertEqual(r["derived_comparisons"]["own_D0_F0"][-1]["status"], "computed")

    def test_zero_new_requests_retains_full_planned_denominators(self):
        r = self.result()
        self.assertEqual((r["all_generation_requests_including_interrupted_attempt"], r["finalized_finals"]), (10, 4))
        self.assertEqual(r["stage_records"][-1]["reasons"], ["not_attempted"])

    def test_negative_model_weight_is_outcome_not_gate(self):
        self.f.summary([self.f.stage(first="-0.1", second="1.1")], "attempt_sequence_finished")
        r = self.result()
        self.assertEqual((r["finalized_finals"], len(r["all_attempt_ledger"])), (4, 11))
        self.assertEqual(r["external_review_acknowledgements"][0]["status"], "external_review_completed")

    def test_structure_failure_remains_unavailable_without_retry(self):
        self.f.summary([self.f.stage(status="model_structure_failure")], "attempt_sequence_finished")
        r = self.result()
        self.assertEqual((r["last_final_generation_requests"], r["finalized_finals"]), (1, 4))

    def test_no_terminal_means_no_historical_read(self):
        self.f.terminal.unlink()
        with patch.object(last, "historical_dataset") as old, self.assertRaises(OSError): self.result()
        old.assert_not_called()

    def test_running_summary_rejected(self):
        self.f.summary([], "running")
        with self.assertRaisesRegex(ValueError, "terminal_last_final"): self.result()

    def test_wrong_scope_and_second_request_rejected(self):
        for key, value in (("purpose", "main"), ("max_generation_requests", 2), ("historical_generation_requests", 9), ("stage_order", [last.CASE + "__D0"]), ("automatic_retries", True)):
            with self.subTest(key=key), self.assertRaises(ValueError): last.scope({**self.f.declaration, key: value})

    def test_candidate_rejected(self):
        self.f.protocol["status"] = "candidate"; self.f.refresh()
        with self.assertRaisesRegex(ValueError, "approved_last_final"): self.result()

    def test_omitted_frozen_previous_finalizer_rejected(self):
        self.f.freeze["code_refs"] = self.f.freeze["code_refs"][:1]; self.f.refresh()
        with self.assertRaisesRegex(ValueError, "five_finalizer_sources"): self.result()

    def test_old_ACK_must_not_be_backfilled(self):
        write_json(self.f.previous.run / (last.CASE + "__D0/external_review_ack.json"), {"status": "invented"})
        with self.assertRaisesRegex(ValueError, "backfilled"): self.result()

    def test_repeated_new_D0_directory_rejected(self):
        (self.f.run / (last.CASE + "__D0")).mkdir()
        with self.assertRaisesRegex(ValueError, "unaccounted_last_final"): self.result()

    def test_final_raw_history_cannot_be_substituted(self):
        self.f.summary([self.f.stage()])
        folder = self.f.run / last.STAGE_ORDER[0]
        spec = read_json(folder / "worker_spec.json"); spec["raw_draft"] += "changed"
        write_json(folder / "worker_spec.json", spec); self.f.raw.refresh_review(folder)
        with self.assertRaisesRegex(ValueError, "exact_external_own_D0"): self.result()

    def test_late_semantic_review_must_bind_current_control_transport(self):
        ev = self.f.operating["external_draft_evidence_refs"]
        p = Path(ev["semantic_review"]["path"]); sem = read_json(p); sem["transport_ref"] = ev["stage_review"]
        nr = write_json(p, sem)
        for value in (self.f.protocol, self.f.freeze, self.f.gate, self.f.declaration): value["external_draft_evidence_refs"]["semantic_review"] = nr
        self.f.refresh()
        with self.assertRaisesRegex(ValueError, "control_D0_semantic"): self.result()

    def test_review_time_must_preserve_after_terminal_chronology(self):
        ev = self.f.operating["external_draft_evidence_refs"]
        p = Path(ev["semantic_review"]["path"]); sem = read_json(p); sem["completed_at_utc"] = "2026-10-26T00:00:01+00:00"
        nr = write_json(p, sem)
        for value in (self.f.protocol, self.f.freeze, self.f.gate, self.f.declaration): value["external_draft_evidence_refs"]["semantic_review"] = nr
        self.f.refresh()
        with self.assertRaisesRegex(ValueError, "after_terminal_review"): self.result()

    def test_normal_finish_requires_current_ACK(self):
        self.f.summary([self.f.stage()], "attempt_sequence_finished")
        (self.f.run / (last.STAGE_ORDER[0] + "/external_review_ack.json")).unlink()
        with self.assertRaisesRegex(ValueError, "normal_last_final_finish"): self.result()

    def test_stopped_current_ACK_gap_is_retained(self):
        self.f.summary([self.f.stage()])
        (self.f.run / (last.STAGE_ORDER[0] + "/external_review_ack.json")).unlink()
        r = self.result()
        self.assertEqual(r["external_review_acknowledgements"][0]["status"], "unavailable_or_invalid")
        self.assertEqual(r["all_generation_requests_including_interrupted_attempt"], 11)

    def test_normal_finish_cannot_skip_only_stage(self):
        self.f.summary([], "attempt_sequence_finished")
        with self.assertRaisesRegex(ValueError, "missing_final_requires"): self.result()

    def test_summary_cumulative_count_cannot_hide_last_request(self):
        self.f.summary([self.f.stage()])
        s = read_json(self.f.run / "campaign_summary.json"); s["campaign_generation_requests_attempted"] = 10
        write_json(self.f.run / "campaign_summary.json", s)
        t = read_json(self.f.terminal); t["summary_ref"] = ref(self.f.run / "campaign_summary.json"); write_json(self.f.terminal, t)
        with self.assertRaisesRegex(ValueError, "summary_count_mismatch"): self.result()


if __name__ == "__main__":
    unittest.main(verbosity=2)
