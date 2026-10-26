"""Offline synthetic packaging tests; only new adapter boundaries are mocked.

Frozen completion authority/accounting already has separate tests. These tests
exercise the masked layer with a synthetic accounting result and exact raw files.
No old module global, frozen source, actual response or service is changed/read.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_completion_masked_review as masked
from test_build_campaign_masked_review import MaskFixture
from test_finalize_sector_campaign import digest_tree, read_json, ref, write_json


class CompletionMaskFixture(MaskFixture):
    def __init__(self, base):
        super().__init__(base, "pilot_continuation")
        self.purpose = "pilot_completion"
        self.cases = masked.completion.CASES
        self.f.cases, self.f.purpose = self.cases, self.purpose
        scope = {"purpose": self.purpose, "case_order": list(self.cases), "max_generation_requests": 6,
                 "historical_generation_requests": 5, "campaign_max_generation_requests": 11,
                 "automatic_retries": 0, "main_model_calls": 0, "main_allowed": False,
                 "old_outputs_observed": True, "historical_first_attempt_results_unchanged": True,
                 "explicit_retry_slots": [], "historical_explicit_retry_slots": ["fidelity_q2_2026__L__D0"],
                 "analysis_role": "primary_exploratory", "excluded_new_main_execution": True}
        extra = {"prior_continuation_summary_ref": write_json(base / "prior_archived/raw/campaign_summary.json", {"synthetic": True}),
                 "prior_continuation_terminal_ref": write_json(base / "prior_archived/reports/terminal_receipt.json", {"synthetic": True})}
        for value in (self.f.common, self.f.protocol, self.f.freeze, self.f.gate, self.f.declaration):
            value.update(scope)
        for value in (self.f.extra, self.f.freeze, self.f.gate, self.f.declaration):
            value.update(extra)
        self.f.sync()
        self.finish()

    def build(self):
        return masked.build(self.run, self.terminal, self.output, self.mapping)

    def accounting(self, run, terminal):
        if Path(run) != self.run or Path(terminal) != self.terminal:
            raise ValueError("Synthetic accounting received wrong run")
        summary = read_json(self.run / "campaign_summary.json")
        return {"purpose": "primary_exploratory_completion_dataset", "case_order": list(masked.campaign.PILOT),
                "segment_case_order": list(self.cases), "segment_planned_final_allocations": 3,
                "segment_planned_stage_slots": 6, "completion_generation_requests": summary["generation_requests_attempted"],
                "all_generation_requests_including_interrupted_attempt": 5 + summary["generation_requests_attempted"],
                "input_refs": [ref(p) for p in self.run.rglob("*.json")],
                "final_total_units": 10000, "synthetic_private_historical_findings": "Prior negative audit; not for judge."}


class CompletionMaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="completion-masked-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.f = CompletionMaskFixture(self.base)
        for name in ("validate_run", "validate_stage"):
            context = patch.object(masked, name)
            setattr(self, name, context.start())
            self.addCleanup(context.stop)
        context = patch.object(masked, "completion_accounting", side_effect=self.f.accounting)
        self.accounting = context.start()
        self.addCleanup(context.stop)

    def test_only_three_new_finals_keep_exact_raw_and_own_history(self):
        self.f.full()
        before = digest_tree(self.f.run)
        result = self.f.build()
        self.assertEqual((result["items"], result["model_generation_calls"], result["service_calls"]), (3, 0, 0))
        self.assertEqual(before, digest_tree(self.f.run))
        index = read_json(self.f.output / "index.json")
        self.assertEqual((index["planned_final_submissions"], index["planned_final_sector_rows"]), (3, 33))
        self.assertEqual(len(set(index["items"])), 3)
        self.assertTrue(all(len(i) == 32 and all(c in "0123456789abcdef" for c in i) for i in index["items"]))
        private = read_json(self.f.mapping / "private_mapping.json")
        self.assertEqual([r["case_id"] for r in private["mapping"]], list(masked.completion.CASES))
        self.assertEqual(private["actual_generation_requests"], 6)
        self.assertEqual(private["accounting_and_derived_diagnostics_private_only"]["all_generation_requests_including_interrupted_attempt"], 11)
        for case in self.f.cases:
            folder, item = self.f.item(case)
            for stage, filename in (("D0", "prior.txt"), ("F0", "final.txt")):
                raw = read_json(self.f.run / (case + "__" + stage) / "http_0001_generation/response.json")["message"]["content"]
                self.assertEqual((folder / filename).read_text(), raw)
            self.assertTrue(item["final_submission"]["normal_generation_completed"])
        self.assertTrue((self.f.output / "COMPLETE.json").exists())

    def test_judge_copies_hide_case_paths_hypothesis_audits_and_derived_math(self):
        self.f.full()
        self.f.build()
        for path in self.f.output.rglob("*.json"):
            content = path.read_text()
            for secret in ("case_id", "run_directory", "selection_role", "analysis_role", "primary_exploratory",
                           "endpoint_amendment", "derived_comparisons", "final_total_units", "prior negative audit",
                           "synthetic_private_historical_findings", str(self.f.run), *self.f.cases):
                self.assertNotIn(secret.lower(), content.lower())
        _, control = self.f.item(self.f.cases[-1])
        self.assertIsNone(control["supplied_final_evidence"]["institution_document"])
        for case in self.f.cases[:2]:
            _, item = self.f.item(case)
            self.assertEqual(item["supplied_final_evidence"]["institution_document"]["source_id"], "ubs_june_2026")
            self.assertNotIn("stage", item["supplied_final_evidence"])

    def test_missing_terminal_stops_before_accounting_or_text(self):
        self.f.terminal.unlink()
        with patch.object(masked, "inspect_stage") as inspect:
            with self.assertRaises(FileNotFoundError):
                self.f.build()
            inspect.assert_not_called()
            self.accounting.assert_not_called()
        self.assertFalse(self.f.output.exists())

    def test_live_summary_stops_before_accounting_or_text(self):
        summary = read_json(self.f.run / "campaign_summary.json")
        summary["status"] = "running"
        write_json(self.f.run / "campaign_summary.json", summary)
        with patch.object(masked, "inspect_stage") as inspect:
            with self.assertRaisesRegex(ValueError, "terminal_completion"):
                self.f.build()
            inspect.assert_not_called()
            self.accounting.assert_not_called()

    def test_terminal_must_bind_exact_current_summary(self):
        summary = read_json(self.f.run / "campaign_summary.json")
        summary["extra"] = "changed after terminal"
        write_json(self.f.run / "campaign_summary.json", summary)
        with self.assertRaisesRegex(ValueError, "terminal_binding"):
            self.f.build()

    def test_fidelity_or_main_scope_cannot_enter_new_bundle(self):
        declaration = read_json(self.f.run / "campaign_declaration.json")
        declaration["case_order"] = list(masked.campaign.MAIN)
        write_json(self.f.run / "campaign_declaration.json", declaration)
        with self.assertRaisesRegex(ValueError, "completion_scope_mismatch"):
            self.f.build()
        self.accounting.assert_not_called()

    def test_missing_finals_stay_missing_and_three_planned_items_remain(self):
        self.f.stage(self.f.cases[0], "D0")
        self.f.finish()
        self.f.build()
        folder, item = self.f.item(self.f.cases[0])
        self.assertIsNone(item["final_submission"]["text_file"])
        self.assertIsNone(item["supplied_final_evidence"])
        self.assertTrue((folder / "prior.txt").exists())
        self.assertFalse((folder / "final.txt").exists())
        self.assertEqual(len(read_json(self.f.output / "index.json")["items"]), 3)

    def test_partial_final_is_exact_prefix_and_diagnostic_only(self):
        case = self.f.cases[0]
        self.f.stage(case, "D0")
        folder = self.f.stage(case, "F0", status="case_timeout")
        (folder / "http_0001_generation/events.jsonl").write_text(
            json.dumps({"event": {"message": {"content": '{"unfinished": '}}}) + "\n", encoding="utf-8")
        self.f.finish()
        self.f.build()
        judge, item = self.f.item(case)
        self.assertEqual((judge / "final.txt").read_text(), '{"unfinished": ')
        self.assertTrue(item["final_submission"]["partial_or_unbound_diagnostic_only"])
        self.assertFalse(item["final_submission"]["normal_generation_completed"])
        self.assertIsNotNone(item["supplied_final_evidence"])

    def test_unattempted_final_payload_is_not_presented_as_supplied(self):
        case = self.f.cases[0]
        self.f.stage(case, "D0")
        self.f.stage(case, "F0", status="preflight_failed", attempts=0)
        self.f.finish()
        self.f.build()
        _, item = self.f.item(case)
        self.assertIsNone(item["supplied_final_evidence"])
        self.assertIsNone(item["final_submission"]["text_file"])

    def test_substituted_own_draft_is_rejected(self):
        self.f.full()
        path = self.f.run / (self.f.cases[0] + "__F0") / "worker_spec.json"
        spec = read_json(path)
        spec["raw_draft"] = "substituted draft"
        write_json(path, spec)
        with self.assertRaisesRegex(ValueError, "own_new_D0_binding"):
            self.f.build()

    def test_wrong_assigned_source_is_rejected(self):
        self.f.full()
        path = self.f.run / (self.f.cases[0] + "__F0") / "worker_spec.json"
        spec = read_json(path)
        payload = json.loads(spec["body"]["messages"][3]["content"])
        payload["institution_document"]["source_id"] = "unassigned_source"
        spec["body"]["messages"][3]["content"] = json.dumps(payload)
        write_json(path, spec)
        with self.assertRaisesRegex(ValueError, "unassigned"):
            self.f.build()

    def test_changed_prepared_input_hash_is_rejected(self):
        self.f.full()
        (self.f.f.inputs / (self.f.cases[0] + "_prepared.json")).write_text("[]")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.f.build()

    def test_extra_generation_evidence_is_rejected(self):
        self.f.full()
        (self.f.run / (self.f.cases[0] + "__F0") / "http_0002_generation").mkdir()
        with self.assertRaisesRegex(ValueError, "Extra or undeclared"):
            self.f.build()

    def test_summary_and_terminal_cannot_hide_request(self):
        self.f.full()
        summary_path = self.f.run / "campaign_summary.json"
        summary = read_json(summary_path)
        summary["generation_requests_attempted"] -= 1
        write_json(summary_path, summary)
        terminal = read_json(self.f.terminal)
        terminal["generation_requests_attempted"] -= 1
        terminal["summary_ref"] = ref(summary_path)
        write_json(self.f.terminal, terminal)
        with self.assertRaisesRegex(ValueError, "All planned stage accounting"):
            self.f.build()

    def test_validated_accounting_failure_cannot_be_bypassed(self):
        self.accounting.side_effect = ValueError("Synthetic frozen accounting violation")
        with self.assertRaisesRegex(ValueError, "frozen accounting violation"):
            self.f.build()
        self.assertFalse(self.f.output.exists())

    def test_validated_accounting_must_be_three_of_fixed_five_and_five_plus_new(self):
        real = self.f.accounting
        def wrong(run, terminal):
            value = real(run, terminal)
            value["all_generation_requests_including_interrupted_attempt"] = 4
            return value
        self.accounting.side_effect = wrong
        with self.assertRaisesRegex(ValueError, "Validated campaign accounting differs"):
            self.f.build()

    def test_runtime_and_stage_validation_errors_propagate(self):
        self.validate_run.side_effect = ValueError("Synthetic gate rejection")
        with self.assertRaisesRegex(ValueError, "gate rejection"):
            self.f.build()
        self.validate_run.side_effect = None
        self.f.stage(self.f.cases[0], "D0")
        self.f.finish()
        self.validate_stage.side_effect = ValueError("Synthetic stage rejection")
        with self.assertRaisesRegex(ValueError, "stage rejection"):
            self.f.build()

    def test_all_raw_and_historical_trees_are_protected(self):
        historical = self.f.f.historical.run
        prior = self.base / "prior_archived/raw"
        for output, mapping in ((self.f.run / "judge", self.f.mapping), (historical / "judge", self.f.mapping),
                                (self.f.output, prior / "private"), (self.f.f.reports / "judge", self.f.mapping),
                                (self.f.output, self.f.output / "mapping")):
            with self.assertRaises(ValueError):
                masked.build(self.f.run, self.f.terminal, output, mapping)
        self.f.output.mkdir()
        with self.assertRaises(FileExistsError):
            self.f.build()

    def test_original_rubric_and_old_module_globals_unchanged(self):
        before = (masked.original.CASES, masked.original.EVALUATION, masked.original.validate_stage_spec)
        helper_refs = [ref(Path(module.__file__)) for module in (masked.original, masked.completion, masked.campaign)]
        self.f.build()
        self.assertEqual(before, (masked.original.CASES, masked.original.EVALUATION, masked.original.validate_stage_spec))
        self.assertEqual(helper_refs, [ref(Path(module.__file__)) for module in (masked.original, masked.completion, masked.campaign)])
        self.assertEqual(read_json(self.f.output / "rubric.json"),
                         masked.original.review_rubric(read_json(masked.original.EVALUATION)))

    def test_mutation_after_accounting_is_detected_before_output_creation(self):
        self.f.full()
        original = masked.inspect_stage
        changed = []
        def inspect(*args):
            result = original(*args)
            if not changed:
                path = self.f.run / (self.f.cases[0] + "__D0") / "worker_summary.json"
                content = read_json(path)
                content["changed"] = True
                write_json(path, content)
                changed.append(True)
            return result
        with patch.object(masked, "inspect_stage", side_effect=inspect):
            with self.assertRaises(ValueError):
                self.f.build()
        self.assertFalse(self.f.output.exists())


if __name__ == "__main__":
    unittest.main()
