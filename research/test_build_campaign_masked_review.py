"""Synthetic offline campaigns; real accounting validator, no service/model calls.

Only this new adapter's runtime approval boundary is mocked for synthetic
settings. No frozen builder, finalizer or runtime module global is patched.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_campaign_masked_review as masked
from test_finalize_sector_campaign import Fixture, digest_tree, read_json, ref, write_json


class MaskFixture:
    def __init__(self, base, purpose="pilot_continuation"):
        self.f = Fixture(base, purpose)
        self.purpose, self.base = purpose, base
        self.run, self.cases = self.f.run, self.f.cases
        self.output, self.mapping = base / "judge", base / "private"
        self.records = {}
        self.expected = {}
        prepared = []
        for case in masked.campaign.PILOT if purpose == "pilot_continuation" else masked.campaign.MAIN:
            source, arm = case.rsplit("__", 1)
            payload = {"stage": "D0", "task": "Allocate the common hypothetical sleeve.",
                       "common_context": {"horizon": "12 months"}, "common_market": {"cutoff_exclusive": "2026-07-17"},
                       "public_numeric_fact_index": {"meaning": "Only supplied metrics"}, "response_schema": {"type": "object"}}
            if arm == "E":
                payload["institution_document"] = self.packet(source)
            messages = [{"role": "system", "content": "Use supplied evidence and preserve exact raw choices."},
                        {"role": "user", "content": json.dumps(payload)}]
            self.expected[case] = messages
            prepared.append({"case_id": case, "stage": "D0", **write_json(self.f.inputs / (case + "_prepared.json"), messages)})
        manifest_ref = write_json(self.f.inputs / "prepared_manifest.json", {"prepared_cases": prepared})
        for value in (self.f.extra, self.f.declaration, self.f.gate, self.f.freeze):
            value["prepared_manifest_ref"] = manifest_ref
        self.f.sync()
        self.finish()

    @staticmethod
    def packet(source):
        return {"source_id": source, "issuer": "Synthetic issuer", "rating_vocabulary": ["Neutral"],
                "evidence_table": {"columns": ["evidence_id", "source_page", "text"],
                                   "rows": [[source + ":p1:sector:10", 1, "Energy receives Neutral. Balanced evidence."]]}}

    def stage(self, case, stage, **kwargs):
        record = self.f.stage(case, stage, **kwargs)
        directory = self.run / (case + "__" + stage)
        spec_path = directory / "worker_spec.json"
        spec = read_json(spec_path)
        spec["body"]["messages"] = copy.deepcopy(self.expected[case])
        if stage == "F0":
            own = read_json(self.run / (case + "__D0") / "http_0001_generation/response.json")["message"]["content"]
            final = {"stage": "F0", "task": "Review actual own draft using the supplied evidence.",
                     "actual_draft_calculator_feedback": {"raw_sum": 1, "budget_residual": 0}}
            if not case.endswith("__C"):
                final["institution_document"] = self.packet(case.rsplit("__", 1)[0])
            spec["body"]["messages"] += [{"role": "assistant", "content": own}, {"role": "user", "content": json.dumps(final)}]
        write_json(spec_path, spec)
        if record["status"] == "completed":
            self.f.raw.refresh_review(directory)
        self.records.setdefault(case, []).append(record)
        return directory

    def finish(self, status="stopped"):
        summary = self.f.summary(self.records, status=status)
        summary.update(purpose=self.purpose, at_utc="2026-10-26T01:00:00+00:00")
        write_json(self.run / "campaign_summary.json", summary)
        self.terminal = self.f.reports / "terminal_receipt.json"
        write_json(self.terminal, {"purpose": self.purpose,
            "status": "completed_semantic_review_pending" if status == "attempt_sequence_finished" else "stopped_semantic_review_pending",
            "at_utc": "2026-10-26T01:00:01+00:00", "run_directory": str(self.run), "output_root": str(self.f.reports),
            "summary_ref": ref(self.run / "campaign_summary.json"), "declaration_ref": ref(self.run / "campaign_declaration.json"),
            "generation_requests_attempted": summary["generation_requests_attempted"],
            "automatic_retries": 0, "main_model_calls": summary["main_model_calls"]})

    def full(self):
        for case in self.cases:
            self.stage(case, "D0")
            self.stage(case, "F0", first="0.7", second="0.5")  # A measured raw-budget error, not filtered.
        self.finish("attempt_sequence_finished")

    def build(self):
        return masked.build(self.run, self.terminal, self.output, self.mapping, purpose=self.purpose)

    def item(self, case):
        private = read_json(self.mapping / "private_mapping.json")
        opaque = next(row["item_id"] for row in private["mapping"] if row["case_id"] == case)
        return self.output / opaque, read_json(self.output / opaque / "item.json")


class MaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="masked-campaign-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        for name in ("validate_run", "validate_stage"):
            context = patch.object(masked, name)
            context.start()
            self.addCleanup(context.stop)

    def test_continuation_four_finals_preserve_errors_text_evidence_and_raw(self):
        f = MaskFixture(self.base)
        f.full()
        before = digest_tree(f.run)
        result = f.build()
        self.assertEqual((result["items"], result["model_generation_calls"], result["service_calls"]), (4, 0, 0))
        index = read_json(f.output / "index.json")
        self.assertEqual((index["planned_final_submissions"], index["planned_final_sector_rows"]), (4, 44))
        self.assertEqual(before, digest_tree(f.run))
        for case in f.cases:
            folder, item = f.item(case)
            raw = read_json(f.run / (case + "__F0") / "http_0001_generation/response.json")["message"]["content"]
            own = read_json(f.run / (case + "__D0") / "http_0001_generation/response.json")["message"]["content"]
            self.assertEqual((folder / "final.txt").read_text(), raw)
            self.assertEqual((folder / "prior.txt").read_text(), own)
            self.assertTrue(item["final_submission"]["normal_generation_completed"])
            self.assertNotIn("stage", item["supplied_final_evidence"])
            self.assertIsNone(item["supplied_final_evidence"]["institution_document"] if case.endswith("__C") else None)
            judge = json.dumps(item)
            for hidden in ("case_id", "run_directory", "source_refs", "endpoint_amendment", "derived_comparisons", "final_total_units", str(f.run), case):
                self.assertNotIn(hidden, judge)
        private = read_json(f.mapping / "private_mapping.json")
        self.assertEqual(private["actual_generation_requests"], 8)
        self.assertIn("accounting_and_derived_diagnostics_private_only", private)
        self.assertTrue((f.output / "COMPLETE.json").exists())

    def test_main_five_items_and_ten_slots_never_select_pilot(self):
        f = MaskFixture(self.base, "main")
        f.full()
        f.build()
        private = read_json(f.mapping / "private_mapping.json")
        self.assertEqual(private["planned_stage_slots"], 10)
        self.assertEqual([row["case_id"] for row in private["mapping"]], list(masked.campaign.MAIN))
        self.assertEqual(read_json(f.output / "index.json")["planned_final_sector_rows"], 55)
        self.assertNotIn("historical", json.dumps(read_json(f.output / "index.json")))

    def test_no_terminal_receipt_blocks_before_any_model_text_or_accounting(self):
        f = MaskFixture(self.base)
        f.terminal.unlink()
        with patch.object(masked, "campaign_accounting") as accounting, patch.object(masked, "inspect_stage") as inspect:
            with self.assertRaisesRegex(ValueError, "Both terminal"):
                f.build()
            accounting.assert_not_called()
            inspect.assert_not_called()
        self.assertFalse(f.output.exists())

    def test_live_summary_blocks_even_if_a_receipt_is_present(self):
        f = MaskFixture(self.base)
        summary = read_json(f.run / "campaign_summary.json")
        summary["status"] = "running"
        write_json(f.run / "campaign_summary.json", summary)
        with patch.object(masked, "campaign_accounting") as accounting:
            with self.assertRaisesRegex(ValueError, "terminal attempt sequence"):
                f.build()
            accounting.assert_not_called()

    def test_terminal_must_bind_exact_summary(self):
        f = MaskFixture(self.base)
        summary = read_json(f.run / "campaign_summary.json")
        summary["note"] = "changed after terminal"
        write_json(f.run / "campaign_summary.json", summary)
        with self.assertRaisesRegex(ValueError, "exact declaration and summary"):
            f.build()

    def test_explicit_wrong_purpose_rejected(self):
        f = MaskFixture(self.base)
        with self.assertRaisesRegex(ValueError, "purpose differs"):
            masked.build(f.run, f.terminal, f.output, f.mapping, purpose="main")

    def test_missing_finals_keep_full_denominator_without_draft_substitution(self):
        f = MaskFixture(self.base)
        f.stage(f.cases[0], "D0")
        f.finish()
        f.build()
        folder, item = f.item(f.cases[0])
        self.assertIsNone(item["final_submission"]["text_file"])
        self.assertTrue((folder / "prior.txt").exists())
        self.assertFalse((folder / "final.txt").exists())
        self.assertIsNone(item["supplied_final_evidence"])
        self.assertEqual(len(read_json(f.output / "index.json")["items"]), 4)

    def test_partial_final_is_explicit_diagnostic_and_exact_prefix(self):
        f = MaskFixture(self.base)
        case = f.cases[0]
        f.stage(case, "D0")
        final = f.stage(case, "F0", status="case_timeout")
        events = final / "http_0001_generation/events.jsonl"
        events.write_text(json.dumps({"event": {"message": {"content": '{"unfinished": '}}}) + "\n", encoding="utf-8")
        f.finish()
        f.build()
        folder, item = f.item(case)
        self.assertEqual((folder / "final.txt").read_text(), '{"unfinished": ')
        self.assertTrue(item["final_submission"]["partial_or_unbound_diagnostic_only"])
        self.assertFalse(item["final_submission"]["normal_generation_completed"])
        self.assertEqual(item["final_submission"]["status"], "case_timeout")
        self.assertIsNotNone(item["supplied_final_evidence"])

    def test_unrequested_final_payload_not_presented_as_supplied_evidence(self):
        f = MaskFixture(self.base)
        case = f.cases[0]
        f.stage(case, "D0")
        f.stage(case, "F0", status="preflight_failed", attempts=0)
        f.finish()
        f.build()
        _, item = f.item(case)
        self.assertIsNone(item["supplied_final_evidence"])
        self.assertIsNone(item["final_submission"]["text_file"])

    def test_wrong_own_draft_is_rejected_by_real_campaign_validator(self):
        f = MaskFixture(self.base)
        f.full()
        path = f.run / (f.cases[0] + "__F0") / "worker_spec.json"
        spec = read_json(path)
        spec["raw_draft"] = "not own output"
        write_json(path, spec)
        f.f.raw.refresh_review(path.parent)
        with self.assertRaisesRegex(ValueError, "F0_new_D0_history"):
            f.build()
        self.assertFalse(f.output.exists())

    def test_extra_generation_is_rejected(self):
        f = MaskFixture(self.base)
        f.full()
        (f.run / (f.cases[0] + "__F0") / "http_0002_generation").mkdir()
        with self.assertRaises(ValueError):
            f.build()

    def test_summary_and_terminal_cannot_jointly_hide_an_attempt(self):
        f = MaskFixture(self.base)
        f.full()
        summary_path = f.run / "campaign_summary.json"
        summary = read_json(summary_path)
        summary["generation_requests_attempted"] -= 1
        write_json(summary_path, summary)
        terminal = read_json(f.terminal)
        terminal["generation_requests_attempted"] -= 1
        terminal["summary_ref"] = ref(summary_path)
        write_json(f.terminal, terminal)
        with self.assertRaisesRegex(ValueError, "campaign_attempt_accounting"):
            f.build()

    def test_wrong_final_source_is_not_injected_as_judge_evidence(self):
        f = MaskFixture(self.base)
        f.full()
        path = f.run / (f.cases[0] + "__F0") / "worker_spec.json"
        spec = read_json(path)
        payload = json.loads(spec["body"]["messages"][3]["content"])
        payload["institution_document"]["source_id"] = "unassigned_source"
        spec["body"]["messages"][3]["content"] = json.dumps(payload)
        write_json(path, spec)
        f.f.raw.refresh_review(path.parent)
        with self.assertRaisesRegex(ValueError, "unassigned"):
            f.build()

    def test_prepared_input_hash_change_fails(self):
        f = MaskFixture(self.base)
        f.full()
        (f.f.inputs / (f.cases[0] + "_prepared.json")).write_text("[]")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            f.build()

    def test_rubric_dimensions_are_the_existing_raw_semantic_rubric(self):
        f = MaskFixture(self.base)
        f.build()
        expected = masked.original.review_rubric(read_json(masked.original.EVALUATION))
        self.assertEqual(read_json(f.output / "rubric.json"), expected)
        self.assertTrue(expected["no_composite_score"])
        self.assertNotIn("primary_final_allocation", json.dumps(expected))

    def test_paths_are_exclusive_and_judge_private_trees_disjoint(self):
        f = MaskFixture(self.base)
        for output, mapping in ((f.run / "judge", f.mapping), (f.output, f.output / "private"), (f.f.reports / "judge", f.mapping)):
            with self.assertRaises(ValueError):
                masked.build(f.run, f.terminal, output, mapping, purpose=f.purpose)
        f.output.mkdir()
        with self.assertRaises(FileExistsError):
            f.build()

    def test_accounting_artifact_mutation_during_packaging_is_detected(self):
        f = MaskFixture(self.base)
        f.full()
        original_inspect = masked.inspect_stage
        changed = []
        def inspect(*args):
            result = original_inspect(*args)
            if not changed:
                path = f.run / (f.cases[0] + "__D0") / "worker_summary.json"
                record = read_json(path)
                record["altered"] = True
                write_json(path, record)
                changed.append(True)
            return result
        with patch.object(masked, "inspect_stage", side_effect=inspect):
            with self.assertRaises(ValueError):
                f.build()
        self.assertFalse(f.output.exists())

    def test_frozen_helper_globals_are_not_changed(self):
        before = (masked.original.CASES, masked.original.EVALUATION, masked.original.validate_stage_spec)
        f = MaskFixture(self.base, "main")
        f.full()
        f.build()
        self.assertEqual(before, (masked.original.CASES, masked.original.EVALUATION, masked.original.validate_stage_spec))


class RuntimeDispatchTests(unittest.TestCase):
    def test_explicit_runtime_module_names_and_rejection(self):
        self.assertEqual(masked.RUNTIMES, {"pilot_continuation": "sector_continuation_runtime", "main": "sector_main_runtime"})
        with self.assertRaises(ValueError):
            masked.runtime_module("pilot")

    def test_run_and_stage_validation_call_explicit_selected_runtime(self):
        from unittest.mock import Mock
        fake = Mock()
        declaration = {"runtime": {"synthetic": True}, "review_gate": {"path": "gate.json", "sha256": "a" * 64}}
        with patch.object(masked, "runtime_module", return_value=fake) as selected:
            masked.validate_run(declaration, Path("synthetic"), "main")
            masked.validate_stage({"stage": "D0"}, Path("synthetic-stage"), "pilot_continuation")
            self.assertEqual([c.args[0] for c in selected.call_args_list], ["main", "pilot_continuation"])
            fake.validate_runtime.assert_called_once_with(declaration["runtime"])
            fake.validate_gate.assert_called_once()
            fake.validate_spec.assert_called_once_with({"stage": "D0"})
            fake.validate_worker_location.assert_called_once()


if __name__ == "__main__":
    unittest.main()
