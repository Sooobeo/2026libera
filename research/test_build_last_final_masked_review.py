"""Synthetic last-final packaging; authority is delegated, never monkeypatched in production."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_last_final_masked_review as masked
from test_build_campaign_masked_review import MaskFixture
from test_finalize_sector_campaign import digest_tree, read_json, ref, write_json


class BundleFixture(MaskFixture):
    def __init__(self, base):
        super().__init__(base)
        self.old = MaskFixture(base / "old")
        oldfolder = self.old.stage(masked.last.CASE, "D0")
        self.old.finish()
        self.cases = masked.last.CASES
        self.f.cases = self.cases
        self.records = {}
        self.final_messages = self.expected[masked.last.CASE] + [
            {"role": "assistant", "content": read_json(oldfolder / "http_0001_generation/response.json")["message"]["content"]},
            {"role": "user", "content": json.dumps({"stage": "F0", "task": "Review your own raw draft.",
                "actual_draft_calculator_feedback": {"raw_sum": 1, "budget_residual": 0}})}]
        scope = {"purpose": masked.last.PURPOSE, "case_order": list(self.cases), "stage_order": list(masked.last.STAGE_ORDER),
            "max_generation_requests": 1, "historical_generation_requests": 10, "campaign_max_generation_requests": 11,
            "automatic_retries": 0, "post_final_calls": 0, "main_model_calls": 0, "main_allowed": False,
            "old_outputs_observed": True, "historical_first_attempt_results_unchanged": True,
            "explicit_retry_slots": [], "historical_explicit_retry_slots": ["fidelity_q2_2026__L__D0"],
            "analysis_role": "primary_exploratory", "excluded_new_main_execution": True}
        extra = {"prior_remaining_summary_ref": ref(self.old.run / "campaign_summary.json"),
            "prior_remaining_terminal_ref": ref(self.old.terminal), "prior_remaining_declaration_ref": ref(self.old.run / "campaign_declaration.json"),
            "external_draft_refs": {role: ref(oldfolder / name) for role, name in (
                ("response", "http_0001_generation/response.json"), ("worker_spec", "worker_spec.json"),
                ("worker_summary", "worker_summary.json"), ("supervisor_result", "supervisor_result.json"), ("transport_result", "transport_result.json"))},
            "external_draft_evidence_refs": {"final_construction": write_json(base / "construction.json", {"ready": True, "messages": self.final_messages})}}
        for prefix in ("prior_continuation", "prior_completion"):
            extra[prefix + "_summary_ref"] = write_json(base / (prefix + "/raw/campaign_summary.json"), {})
            extra[prefix + "_terminal_ref"] = write_json(base / (prefix + "/reports/terminal_receipt.json"), {})
        for v in (self.f.common, self.f.protocol, self.f.freeze, self.f.gate, self.f.declaration): v.update(scope)
        for v in (self.f.extra, self.f.freeze, self.f.gate, self.f.declaration): v.update(extra)
        self.f.sync()
        self.finish()

    def finish(self, status="stopped"):
        super().finish(status)
        if hasattr(self, "old"):
            s = read_json(self.run / "campaign_summary.json")
            s.update(purpose=masked.last.PURPOSE, stage_order=list(masked.last.STAGE_ORDER))
            write_json(self.run / "campaign_summary.json", s)
            t = read_json(self.terminal); t.update(purpose=masked.last.PURPOSE, summary_ref=ref(self.run / "campaign_summary.json"))
            write_json(self.terminal, t)

    def final(self, **kwargs):
        record = self.f.raw.make_stage(masked.last.CASE, "F0", **kwargs)
        folder = self.run / masked.last.STAGE_ORDER[0]
        spec = read_json(folder / "worker_spec.json")
        spec.update(raw_draft=self.final_messages[2]["content"], draft_artifacts=self.f.declaration["external_draft_refs"])
        spec["body"]["messages"] = copy.deepcopy(self.final_messages)
        write_json(folder / "worker_spec.json", spec)
        self.records[masked.last.CASE] = [record]
        self.finish("attempt_sequence_finished" if record["status"] in ("completed", "model_structure_failure") else "stopped")
        return folder

    def accounting(self, run, terminal):
        if Path(run) != self.run or Path(terminal) != self.terminal: raise ValueError("wrong accounting input")
        n = read_json(self.run / "campaign_summary.json")["generation_requests_attempted"]
        return {"version": masked.last.VERSION, "purpose": "primary_exploratory_last_final_dataset",
            "case_order": list(masked.campaign.PILOT), "segment_case_order": list(self.cases),
            "segment_planned_final_allocations": 1, "segment_planned_stage_slots": 1,
            "planned_final_allocations": 5, "planned_final_sector_rows": 55, "logical_stage_slots": 10,
            "last_final_generation_requests": n, "all_generation_requests_including_interrupted_attempt": 10+n,
            "input_refs": [ref(p) for tree in (self.run, self.old.run) for p in tree.rglob("*.json")],
            "prior_unmasked_findings": "PRIVATE NEGATIVE REVIEW", "derived_units": [10000]}

    def build(self):
        return masked.build(self.run, self.terminal, self.output, self.mapping)


class LastMaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="last-mask-"); self.addCleanup(self.temp.cleanup)
        self.f = BundleFixture(Path(self.temp.name).resolve())
        for name in ("current_validator", "prior_validator"):
            p = patch.object(masked, name); p.start(); self.addCleanup(p.stop)
        p = patch.object(masked, "accounting", side_effect=self.f.accounting); self.accounting = p.start(); self.addCleanup(p.stop)

    def test_one_item_raw_own_history_and_private_math(self):
        folder = self.f.final(first="0.8", second="0.4")
        before = digest_tree(self.f.run), digest_tree(self.f.old.run)
        self.assertEqual(self.f.build()["items"], 1)
        self.assertEqual(before, (digest_tree(self.f.run), digest_tree(self.f.old.run)))
        out, item = self.f.item(masked.last.CASE)
        self.assertEqual((out/"prior.txt").read_text(), self.f.final_messages[2]["content"])
        self.assertEqual((out/"final.txt").read_text(), read_json(folder/"http_0001_generation/response.json")["message"]["content"])
        self.assertIsNone(item["supplied_final_evidence"]["institution_document"])
        judge = json.dumps(item)
        for private in (masked.last.CASE, "case_id", "derived_units", "PRIVATE NEGATIVE REVIEW", str(self.f.run), "after_terminal"):
            self.assertNotIn(private, judge)
        index = read_json(self.f.output/"index.json")
        self.assertEqual((index["planned_final_submissions"], index["planned_final_sector_rows"]), (1,11))
        private = read_json(self.f.mapping/"private_mapping.json")
        self.assertEqual(private["campaign_planned_final_submissions_private"],5)
        self.assertEqual(private["accounting_and_derived_diagnostics_private_only"]["all_generation_requests_including_interrupted_attempt"],11)

    def test_terminal_required_before_accounting_or_text(self):
        self.f.terminal.unlink()
        with self.assertRaises(OSError): self.f.build()
        self.accounting.assert_not_called(); self.assertFalse(self.f.output.exists())

    def test_running_rejected_before_accounting(self):
        self.f.finish("running")
        with self.assertRaisesRegex(ValueError,"terminal"): self.f.build()
        self.accounting.assert_not_called()

    def test_authority_error_propagates_before_writes(self):
        self.accounting.side_effect = ValueError("gate rejected")
        with self.assertRaisesRegex(ValueError,"gate rejected"): self.f.build()
        self.assertFalse(self.f.output.exists())

    def test_missing_final_not_replaced_by_own_draft(self):
        self.f.build(); folder,item=self.f.item(masked.last.CASE)
        self.assertIsNone(item["final_submission"]["text_file"])
        self.assertFalse((folder/"final.txt").exists()); self.assertTrue((folder/"prior.txt").exists())
        self.assertIsNone(item["supplied_final_evidence"])

    def test_model_structure_failure_raw_remains_reviewable(self):
        stage=self.f.final(status="model_structure_failure")
        response={"message":{"role":"assistant","content":"{broken JSON"},"done":True,"done_reason":"stop"}
        response_ref=write_json(stage/"http_0001_generation/response.json",response)
        transport=read_json(stage/"transport_result.json")
        transport.update(response=response,response_artifact=response_ref)
        write_json(stage/"transport_result.json",transport)
        self.f.build(); folder,item=self.f.item(masked.last.CASE)
        self.assertEqual((folder/"final.txt").read_text(),"{broken JSON")
        self.assertEqual(item["final_submission"]["status"],"model_structure_failure")

    def test_interrupted_unbound_raw_is_diagnostic_only(self):
        stage=self.f.final(status="hard_deadline")
        write_json(stage/"http_0001_generation/response.json",{"message":{"role":"assistant","content":"partial raw"}})
        self.f.build(); folder,item=self.f.item(masked.last.CASE)
        self.assertEqual((folder/"final.txt").read_text(),"partial raw")
        self.assertTrue(item["final_submission"]["partial_or_unbound_diagnostic_only"])
        self.assertFalse(item["final_submission"]["normal_generation_completed"])

    def test_unbound_response_cannot_claim_completed_transport(self):
        stage=self.f.final();p=stage/"http_0001_generation/response.json"
        response=read_json(p);response["message"]["content"]+="changed";write_json(p,response)
        with self.assertRaisesRegex(ValueError,"bound transport"):self.f.build()

    def test_old_and_new_validators_are_distinct(self):
        self.f.final()
        with patch.object(masked,"prior_validator") as old,patch.object(masked,"current_validator") as new:
            self.f.build()
            self.assertEqual(old.call_args.args[1],self.f.old.run/(masked.last.CASE+"__D0"))
            self.assertEqual(new.call_args.args[1],self.f.run/masked.last.STAGE_ORDER[0])

    def test_original_rubric_bytes_and_dimensions(self):
        self.f.build()
        self.assertEqual(read_json(self.f.output/"rubric.json"),masked.original.review_rubric(read_json(masked.original.EVALUATION)))

    def test_changed_prepared_bytes_rejected(self):
        row=read_json(Path(self.f.f.declaration["prepared_manifest_ref"]["path"]))["prepared_cases"][-1]
        Path(row["path"]).write_text("[]")
        with self.assertRaisesRegex(ValueError,"hash"): self.f.build()

    def test_wrong_raw_own_history_rejected(self):
        folder=self.f.final(); s=read_json(folder/"worker_spec.json");s["raw_draft"]+="changed";write_json(folder/"worker_spec.json",s)
        with self.assertRaisesRegex(ValueError,"own_D0"): self.f.build()

    def test_no_new_raw_or_private_tree_target(self):
        for target in (self.f.run/"judge",self.f.old.run/"judge",self.f.old.f.reports/"judge",self.f.f.reports/"judge"):
            with self.subTest(target=str(target)),self.assertRaises(ValueError):
                masked.build(self.f.run,self.f.terminal,target,self.f.mapping)

    def test_exclusive_output(self):
        self.f.build()
        with self.assertRaises(FileExistsError): self.f.build()

    def test_wrong_cumulative_accounting_rejected(self):
        value=self.f.accounting(self.f.run,self.f.terminal);value["all_generation_requests_including_interrupted_attempt"]=9
        self.accounting.side_effect=None;self.accounting.return_value=value
        with self.assertRaisesRegex(ValueError,"accounting"): self.f.build()


if __name__ == "__main__": unittest.main(verbosity=2)
