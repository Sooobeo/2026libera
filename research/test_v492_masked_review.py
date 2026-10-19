"""Ephemeral synthetic outputs only; no live pilot responses are opened."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_v492_masked_review as bundle


class MaskedBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="v492_mask_test_only_")
        self.root = Path(self.temp.name)
        self.run = self.root / "synthetic_run"
        self.run.mkdir()
        self.judge, self.private = self.root / "judge", self.root / "private"
        self.manifest_path = bundle.ROOT / "data/sector_protocol/v492_design_20261019/prepared/preparation_manifest.json"
        self.manifest = bundle.read(self.manifest_path)
        self.drafts = {row["case_id"]: bundle.checked(row) for row in self.manifest["prepared_cases"]}
        self.packets = {case.rsplit("__", 1)[0]: bundle.read_content(messages[1])["institution_document"]
                        for case, messages in self.drafts.items() if case.endswith("__E")}
        self.gate = self.root / "test_only_gate.json"
        bundle.write_json(self.gate, {"evaluation_protocol_ref": bundle.ref(bundle.EVALUATION),
                                     "prepared_manifest_ref": bundle.ref(self.manifest_path)})
        bundle.write_json(self.run / "pilot_declaration.json", {"review_gate": bundle.ref(self.gate)})
        self.gate_patch = patch.object(bundle, "validate_run_gate")
        self.spec_patch = patch.object(bundle, "validate_stage_spec")
        self.gate_patch.start()
        self.spec_patch.start()

    def tearDown(self):
        self.gate_patch.stop()
        self.spec_patch.stop()
        self.temp.cleanup()

    def save(self, path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def make_run(self, modes=None):
        modes = modes or {}
        cases, total = [], 0
        for index, case in enumerate(bundle.CASES):
            draft_text = '  {"fixture": "prior %s", "raw_sum": 1.1}\r\n' % index
            stages = []
            for stage in ("D0", "F0"):
                mode = modes.get((case, stage), "complete")
                if mode == "not_attempted":
                    continue
                folder = self.run / (case + "__" + stage)
                folder.mkdir()
                messages = copy.deepcopy(self.drafts[case])
                if stage == "F0":
                    payload = {"stage": "F0", "task": "shared fixture task",
                               "actual_draft_calculator_feedback": {"raw_sum": 1.1, "fixture": True}}
                    if case != bundle.CASES[-1]:
                        payload["institution_document"] = self.packets[case.rsplit("__", 1)[0]]
                    messages += [{"role": "assistant", "content": draft_text},
                                 {"role": "user", "content": bundle.canonical(payload)}]
                bundle.write_json(folder / "worker_spec.json", {
                    "case_id": case, "stage": stage, "body": {"messages": messages}})
                if mode == "preflight_failure":
                    bundle.write_json(folder / "transport_result.json", {
                        "status": "capacity_failure", "generation_requests_attempted": 0,
                        "response_artifact": None, "response": None})
                    stages.append({"stage": stage, "status": "capacity_failure", "generation_requests_attempted": 0})
                    continue
                generation = folder / "http_0001_generation"
                generation.mkdir()
                text = draft_text if stage == "D0" else ' \n{"fixture_final": %s, "bad_sum": 1.1}\r\n' % index
                status = "completed" if mode == "complete" else "failed"
                transport = {"status": status, "generation_requests_attempted": 1, "response_artifact": None}
                if mode == "complete":
                    path = generation / "response.json"
                    transport["response"] = {"message": {"content": text}}
                    bundle.write_json(path, transport["response"])
                    transport["response_artifact"] = bundle.ref(path)
                elif mode == "partial":
                    bundle.write_json(generation / "assembled_text.json", {"content": ' {"unfinished": ', "complete": False})
                elif mode == "event_partial":
                    (generation / "events.jsonl").write_text(
                        json.dumps({"event": {"message": {"content": "α\r\n"}}}) + '\n{"truncated":', encoding="utf-8")
                elif mode != "empty_failure":
                    raise AssertionError(mode)
                bundle.write_json(folder / "transport_result.json", transport)
                stages.append({"stage": stage, "status": status, "generation_requests_attempted": 1})
                total += 1
            cases.append({"case_id": case, "status": "test_fixture", "stages": stages})
        bundle.write_json(self.run / "pilot_summary.json", {"status": "pilot_attempt_sequence_finished",
                         "cases": cases, "generation_requests_attempted": total,
                         "main_model_calls": 0, "automatic_retries": 0, "post_final_calls": 0})

    def build(self):
        return bundle.build(self.run, self.judge, self.private)

    def item_for(self, case):
        mapping = bundle.read(self.private / "private_mapping.json")
        item_id = next(row["item_id"] for row in mapping["mapping"] if row["case_id"] == case)
        return self.judge / item_id, bundle.read(self.judge / item_id / "item.json")

    def test_full_bundle_masks_metadata_preserves_exact_strings_and_dates(self):
        self.make_run()
        result = self.build()
        self.assertEqual(result["first_attempt_requests"], 10)
        index = bundle.read(self.judge / "index.json")
        self.assertEqual(len(index["items"]), 5)
        for path in self.judge.rglob("*.json"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(str(self.run), text)
            self.assertNotIn('"case_id"', text)
            self.assertNotIn('"arm"', text)
            self.assertNotIn('"C_rule"', text)
            for case in bundle.CASES:
                self.assertNotIn(case, text)
        for index, case in enumerate(bundle.CASES):
            folder, item = self.item_for(case)
            original = bundle.read(self.run / (case + "__F0") / "http_0001_generation/response.json")["message"]["content"]
            self.assertEqual((folder / "final.txt").read_bytes(), original.encode("utf-8"))
            expected_context = bundle.read_content(self.drafts[case][1])["common_context"]
            self.assertEqual(item["supplied_final_evidence"]["common_context"], expected_context)
        self.assertTrue((self.judge / "COMPLETE.json").exists())

    def test_no_source_item_keeps_no_hidden_institution(self):
        self.make_run()
        self.build()
        _, item = self.item_for(bundle.CASES[-1])
        self.assertIsNone(item["supplied_final_evidence"]["institution_document"])
        text = json.dumps(item)
        self.assertNotIn("fidelity_q2_2026", text)
        self.assertNotIn("ubs_june_2026", text)
        self.assertNotIn("ubs_july", text)

    def test_source_packet_and_actual_feedback_are_preserved(self):
        self.make_run()
        self.build()
        _, item = self.item_for(bundle.CASES[1])
        self.assertEqual(item["supplied_final_evidence"]["institution_document"], self.packets["fidelity_q2_2026"])
        self.assertEqual(item["supplied_final_evidence"]["actual_draft_calculator_feedback"]["raw_sum"], 1.1)

    def test_missing_partial_and_not_attempted_are_retained_without_replacement(self):
        self.make_run({(bundle.CASES[0], "F0"): "partial", (bundle.CASES[1], "F0"): "not_attempted",
                       (bundle.CASES[2], "D0"): "empty_failure", (bundle.CASES[2], "F0"): "not_attempted",
                       (bundle.CASES[4], "D0"): "not_attempted", (bundle.CASES[4], "F0"): "not_attempted"})
        self.build()
        folder, item = self.item_for(bundle.CASES[0])
        self.assertEqual((folder / "final.txt").read_bytes(), b' {"unfinished": ')
        _, missing = self.item_for(bundle.CASES[1])
        self.assertIsNone(missing["final_submission"]["text_file"])
        self.assertEqual(missing["own_prior_submission"]["text_file"], "prior.txt")
        self.assertIsNone(missing["supplied_final_evidence"])
        self.assertEqual(bundle.read(self.private / "private_mapping.json")["planned_stage_slots"], 10)

    def test_event_prefix_is_retained_without_repair(self):
        self.make_run({(bundle.CASES[0], "F0"): "event_partial"})
        self.build()
        folder, item = self.item_for(bundle.CASES[0])
        self.assertEqual((folder / "final.txt").read_bytes(), "α\r\n".encode())
        self.assertEqual(item["final_submission"]["text_state"], "recorded_event_prefix_partial")

    def test_preflight_failure_does_not_claim_evidence_was_delivered(self):
        self.make_run({(bundle.CASES[0], "F0"): "preflight_failure"})
        self.build()
        _, item = self.item_for(bundle.CASES[0])
        self.assertEqual(item["final_submission"]["status"], "capacity_failure")
        self.assertIsNone(item["supplied_final_evidence"])
        self.assertIsNone(item["final_submission"]["text_file"])

    def test_live_run_is_rejected_before_any_response_read(self):
        with patch.object(bundle, "extract_text", side_effect=AssertionError("must not read")):
            with self.assertRaisesRegex(ValueError, "Completed pilot_summary"):
                self.build()
        self.assertFalse(self.judge.exists())

    def test_private_mapping_cannot_be_nested_in_judge_bundle(self):
        with self.assertRaises(ValueError):
            bundle.build(self.run, self.judge, self.judge / "mapping")

    def test_changed_response_hash_rejected(self):
        self.make_run()
        path = self.run / (bundle.CASES[0] + "__F0") / "http_0001_generation/response.json"
        self.save(path, {"message": {"content": "changed"}})
        with self.assertRaisesRegex(ValueError, "transport receipt"):
            self.build()

    def test_no_source_final_injection_and_hidden_main_source_rejected(self):
        for case, source in ((bundle.CASES[-1], "fidelity_q2_2026"), (bundle.CASES[0], "fidelity_q3_2026")):
            messages = copy.deepcopy(self.drafts[case])
            messages += [{"role": "assistant", "content": "raw"}, {"role": "user", "content": bundle.canonical({
                "stage": "F0", "task": "task", "actual_draft_calculator_feedback": {},
                "institution_document": {"source_id": source}})}]
            with self.assertRaises(ValueError):
                bundle.visible_final_evidence({"case_id": case, "body": {"messages": messages}}, "raw", self.drafts[case])

    def test_own_draft_whitespace_replacement_rejected(self):
        messages = copy.deepcopy(self.drafts[bundle.CASES[-1]])
        messages += [{"role": "assistant", "content": "raw"}, {"role": "user", "content": "{}"}]
        with self.assertRaisesRegex(ValueError, "exact saved own"):
            bundle.visible_final_evidence({"case_id": bundle.CASES[-1], "body": {"messages": messages}}, " raw", self.drafts[bundle.CASES[-1]])

    def test_main_case_and_duplicate_attempt_are_rejected(self):
        self.make_run()
        path = self.run / "pilot_summary.json"
        summary = bundle.read(path)
        summary["cases"][0]["case_id"] = "fidelity_q3_2026__E"
        self.save(path, summary)
        with self.assertRaisesRegex(ValueError, "five declared"):
            self.build()

    def test_extra_generation_and_false_counts_rejected(self):
        self.make_run()
        folder = self.run / (bundle.CASES[0] + "__D0")
        (folder / "http_0002_generation").mkdir()
        with self.assertRaisesRegex(ValueError, "Extra or replacement"):
            self.build()

    def test_interrupted_unbound_response_retained_without_completion_claim(self):
        self.make_run()
        folder = self.run / (bundle.CASES[0] + "__F0")
        transport = bundle.read(folder / "transport_result.json")
        transport.update(status="failed", response_artifact=None)
        self.save(folder / "transport_result.json", transport)
        summary = bundle.read(self.run / "pilot_summary.json")
        summary["cases"][0]["stages"][1]["status"] = "failed"
        self.save(self.run / "pilot_summary.json", summary)
        self.build()
        _, item = self.item_for(bundle.CASES[0])
        self.assertEqual(item["final_submission"]["status"], "failed")
        self.assertEqual(item["final_submission"]["text_state"], "unbound_saved_response_content_after_interruption")
        self.assertFalse(item["final_submission"]["saved_response_is_bound"])

    def test_rubric_excludes_contrasts_source_comparison_answers_and_benchmarks(self):
        rubric = bundle.review_rubric(bundle.read(bundle.EVALUATION))
        self.assertIn("when_no_institution_supplied", rubric["dimensions"]["source_fidelity"])
        for key in ("descriptive_comparisons", "interpretation", "design", "source_review_ref", "computational_references_ref"):
            self.assertNotIn(key, rubric)


if __name__ == "__main__":
    unittest.main()
