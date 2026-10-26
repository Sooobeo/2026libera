"""Offline masked remaining tests with synthetic text only; no service or model calls.

This layer mocks only new adapter validator boundaries. Frozen module globals
remain untouched; the exact external history and packaging logic are exercised.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_remaining_masked_review as masked
from test_build_campaign_masked_review import MaskFixture
from test_build_completion_masked_review import CompletionMaskFixture
from test_finalize_sector_campaign import digest_tree, read_json, ref, write_json


class RemainingMaskFixture(MaskFixture):
    def __init__(self, base):
        super().__init__(base, "pilot_continuation")
        self.purpose = "pilot_completion_resume"
        self.cases = masked.remaining.CASES
        self.f.cases, self.f.purpose = self.cases, self.purpose
        self.old = CompletionMaskFixture(base / "old_completion")
        old_folder = self.old.stage(self.cases[0], "D0")
        self.old.finish()
        draft = read_json(old_folder / "http_0001_generation/response.json")["message"]["content"]
        final_payload = {"stage": "F0", "task": "Review actual own draft using the supplied evidence.",
            "actual_draft_calculator_feedback": {"raw_sum": 1, "budget_residual": 0},
            "institution_document": self.packet("ubs_june_2026")}
        self.saved_messages = self.expected[self.cases[0]] + [{"role": "assistant", "content": draft},
                               {"role": "user", "content": json.dumps(final_payload)}]
        external = {role: ref(old_folder / filename) for role, filename in (
            ("response", "http_0001_generation/response.json"), ("worker_spec", "worker_spec.json"),
            ("worker_summary", "worker_summary.json"), ("supervisor_result", "supervisor_result.json"),
            ("transport_result", "transport_result.json"))}
        construction = write_json(self.old.run / (self.cases[0] + "__final_construction.json"),
                                  {"ready": True, "messages": self.saved_messages})
        scope = {"purpose": self.purpose, "case_order": list(self.cases), "stage_order": list(masked.remaining.STAGE_ORDER),
                 "max_generation_requests": 5, "historical_generation_requests": 6, "campaign_max_generation_requests": 11,
                 "automatic_retries": 0, "post_final_calls": 0, "main_model_calls": 0, "main_allowed": False,
                 "old_outputs_observed": True, "historical_first_attempt_results_unchanged": True,
                 "explicit_retry_slots": [], "historical_explicit_retry_slots": ["fidelity_q2_2026__L__D0"],
                 "analysis_role": "primary_exploratory", "excluded_new_main_execution": True}
        extra = {"prior_continuation_summary_ref": write_json(base / "prior_archived/raw/campaign_summary.json", {"synthetic": True}),
                 "prior_continuation_terminal_ref": write_json(base / "prior_archived/reports/terminal_receipt.json", {"synthetic": True}),
                 "prior_completion_summary_ref": ref(self.old.run / "campaign_summary.json"),
                 "prior_completion_terminal_ref": ref(self.old.terminal),
                 "prior_completion_declaration_ref": ref(self.old.run / "campaign_declaration.json"),
                 "external_draft_refs": external, "external_draft_evidence_refs": {"final_construction": construction}}
        for value in (self.f.common, self.f.protocol, self.f.freeze, self.f.gate, self.f.declaration):
            value.update(scope)
        for value in (self.f.extra, self.f.freeze, self.f.gate, self.f.declaration):
            value.update(extra)
        self.f.sync()
        self.finish()

    def stage(self, case, stage, **kwargs):
        if case != self.cases[0]:
            return super().stage(case, stage, **kwargs)
        if stage != "F0":
            raise ValueError("Synthetic remaining fixture also forbids repeated E D0")
        record = self.f.raw.make_stage(case, stage, **kwargs)
        folder = self.run / (case + "__F0")
        spec = read_json(folder / "worker_spec.json")
        spec.update(runtime=copy.deepcopy(self.f.runtime), review_gate=self.f.declaration["review_gate"],
                    raw_draft=self.saved_messages[2]["content"], draft_artifacts=self.f.declaration["external_draft_refs"])
        spec["body"]["messages"] = copy.deepcopy(self.saved_messages)
        write_json(folder / "worker_spec.json", spec)
        if record["status"] == "completed":
            self.f.raw.refresh_review(folder)
        self.records.setdefault(case, []).append(record)
        return folder

    def full(self):
        self.stage(self.cases[0], "F0", first="0.7", second="0.5")
        for case in self.cases[1:]:
            self.stage(case, "D0")
            self.stage(case, "F0", first="0.7", second="0.5")
        self.finish("attempt_sequence_finished")

    def finish(self, status="stopped"):
        super().finish(status)
        if self.purpose == "pilot_completion_resume":
            summary = read_json(self.run / "campaign_summary.json")
            summary["stage_order"] = list(masked.remaining.STAGE_ORDER)
            summary["campaign_generation_requests_attempted"] = 6 + summary["generation_requests_attempted"]
            write_json(self.run / "campaign_summary.json", summary)
            terminal = read_json(self.terminal)
            terminal["summary_ref"] = ref(self.run / "campaign_summary.json")
            write_json(self.terminal, terminal)

    def build(self):
        return masked.build(self.run, self.terminal, self.output, self.mapping)

    def accounting(self, run, terminal):
        if Path(run) != self.run or Path(terminal) != self.terminal:
            raise ValueError("Synthetic accounting received wrong run")
        summary = read_json(self.run / "campaign_summary.json")
        return {"purpose": "primary_exploratory_remaining_dataset", "case_order": list(masked.campaign.PILOT),
                "segment_case_order": list(self.cases), "segment_planned_final_allocations": 3,
                "segment_planned_stage_slots": 5, "remaining_generation_requests": summary["generation_requests_attempted"],
                "all_generation_requests_including_interrupted_attempt": 6 + summary["generation_requests_attempted"],
                "input_refs": [ref(p) for tree in (self.run, self.old.run) for p in tree.rglob("*.json")],
                "final_total_units": 10000, "synthetic_private_historical_findings": "Prior negative audit; not for judge."}


class RemainingMaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="completion-masked-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.f = RemainingMaskFixture(self.base)
        for name in ("validate_run", "validate_stage", "validate_external_stage"):
            context = patch.object(masked, name)
            setattr(self, name, context.start())
            self.addCleanup(context.stop)
        context = patch.object(masked, "remaining_accounting", side_effect=self.f.accounting)
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
        self.assertEqual([r["case_id"] for r in private["mapping"]], list(masked.remaining.CASES))
        self.assertEqual(private["actual_generation_requests"], 5)
        self.assertEqual(private["accounting_and_derived_diagnostics_private_only"]["all_generation_requests_including_interrupted_attempt"], 11)
        for case in self.f.cases:
            folder, item = self.f.item(case)
            for stage, filename in (("D0", "prior.txt"), ("F0", "final.txt")):
                source_run = self.f.old.run if case == self.f.cases[0] and stage == "D0" else self.f.run
                raw = read_json(source_run / (case + "__" + stage) / "http_0001_generation/response.json")["message"]["content"]
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
            with self.assertRaisesRegex(ValueError, "terminal_remaining"):
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
        with self.assertRaisesRegex(ValueError, "remaining_scope_mismatch"):
            self.f.build()
        self.accounting.assert_not_called()

    def test_missing_finals_stay_missing_and_three_planned_items_remain(self):
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
        with self.assertRaisesRegex(ValueError, "external_own_D0_history"):
            self.f.build()

    def test_wrong_assigned_source_is_rejected(self):
        self.f.full()
        path = self.f.run / (self.f.cases[0] + "__F0") / "worker_spec.json"
        spec = read_json(path)
        payload = json.loads(spec["body"]["messages"][3]["content"])
        payload["institution_document"]["source_id"] = "unassigned_source"
        spec["body"]["messages"][3]["content"] = json.dumps(payload)
        write_json(path, spec)
        with self.assertRaisesRegex(ValueError, "external_own_D0_history|unassigned"):
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

    def test_validated_accounting_must_be_three_of_fixed_five_and_six_plus_new(self):
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
        self.f.finish()
        self.validate_external_stage.side_effect = ValueError("Synthetic stage rejection")
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
        helper_refs = [ref(Path(module.__file__)) for module in (masked.original, masked.completion, masked.campaign, masked.remaining, masked.previous)]
        self.f.build()
        self.assertEqual(before, (masked.original.CASES, masked.original.EVALUATION, masked.original.validate_stage_spec))
        self.assertEqual(helper_refs, [ref(Path(module.__file__)) for module in (masked.original, masked.completion, masked.campaign, masked.remaining, masked.previous)])
        self.assertEqual(read_json(self.f.output / "rubric.json"),
                         masked.original.review_rubric(read_json(masked.original.EVALUATION)))

    def test_mutation_after_accounting_is_detected_before_output_creation(self):
        self.f.full()
        original = masked.inspect_stage
        changed = []
        def inspect(*args, **kwargs):
            result = original(*args, **kwargs)
            if not changed:
                path = self.f.old.run / (self.f.cases[0] + "__D0") / "worker_summary.json"
                content = read_json(path)
                content["changed"] = True
                write_json(path, content)
                changed.append(True)
            return result
        with patch.object(masked, "inspect_stage", side_effect=inspect):
            with self.assertRaises(ValueError):
                self.f.build()
        self.assertFalse(self.f.output.exists())


    def test_prior_completion_raw_and_report_trees_are_protected(self):
        for target in (self.f.old.run / "judge", self.f.old.f.reports / "judge"):
            with self.assertRaises(ValueError):
                masked.build(self.f.run, self.f.terminal, target, self.f.mapping)
        with self.assertRaises(ValueError):
            masked.build(self.f.run, self.f.terminal, self.f.output, self.f.old.run / "private")

    def test_prior_completion_D0_text_mutation_cannot_be_packaged(self):
        self.f.full()
        response_path = self.f.old.run / (self.f.cases[0] + "__D0") / "http_0001_generation/response.json"
        response = read_json(response_path)
        response["message"]["content"] += " changed"
        write_json(response_path, response)
        with self.assertRaises(ValueError):
            self.f.build()
        self.assertFalse(self.f.output.exists())

    def test_judge_order_is_shuffled_independently_of_private_mapping(self):
        from types import SimpleNamespace
        self.f.full()
        ids = ["a" * 32, "b" * 32, "c" * 32]
        class ReverseRandom:
            def shuffle(self, items):
                items.reverse()
        with patch.object(masked.uuid, "uuid4", side_effect=[SimpleNamespace(hex=i) for i in ids]), \
             patch.object(masked.secrets, "SystemRandom", return_value=ReverseRandom()):
            self.f.build()
        self.assertEqual(read_json(self.f.output / "index.json")["items"], ids[::-1])
        self.assertEqual([row["item_id"] for row in read_json(self.f.mapping / "private_mapping.json")["mapping"]], ids)

    def test_completed_external_D0_is_old_validator_and_not_new_attempt(self):
        self.f.full()
        before = digest_tree(self.f.old.run)
        self.f.build()
        self.assertEqual(before, digest_tree(self.f.old.run))
        self.validate_external_stage.assert_called_once()
        old_spec, old_folder = self.validate_external_stage.call_args.args
        self.assertEqual((old_spec["case_id"], old_spec["stage"]), (self.f.cases[0], "D0"))
        self.assertEqual(old_folder.parent, self.f.old.run)
        self.assertEqual(self.validate_stage.call_count, 5)
        self.assertFalse((self.f.run / (self.f.cases[0] + "__D0")).exists())
        private = read_json(self.f.mapping / "private_mapping.json")
        self.assertEqual((private["actual_generation_requests"], private["planned_stage_slots"]), (5, 5))


if __name__ == "__main__":
    unittest.main()
