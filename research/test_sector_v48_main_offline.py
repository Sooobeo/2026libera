"""Main-specific synthetic artifact tests. No actual run, model, or network."""
import copy
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import evaluate_sector_v48_artifacts as pilot
import evaluate_sector_v48_main_artifacts as main_loader
from evaluate_sector_v48_main_artifacts import (ROSTER, SOURCES, EXECUTION_SNAPSHOTS, EVALUATOR_MATERIAL_KEYS,
                                               build_report, write_report)
from render_v48_main_review_packet import render_packet, write_packet
from test_evaluate_sector_v48 import fixture


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class MainFixture:
    """Explicit synthetic main data, without repointing pilot module globals."""
    def __init__(self, root):
        self.root = root
        self.prepared, self.run = root / "candidate", root / "synthetic_main_run"
        self.run.mkdir()
        self.values = {source: fixture(source) for source in SOURCES}
        for source, value in self.values.items():
            value[1].update(split="main", title="Synthetic main source: " + source)
            value[2].update(split="main", review_status={"human_source_validation": "fixture_not_a_human_judgment"})
        market, registry = copy.deepcopy(self.values[SOURCES[0]][3:5])
        save(self.prepared / "market_input.json", market)
        registry["source"] = {"sha256": pilot.digest(self.prepared / "market_input.json")}
        save(self.prepared / "public_numeric_registry.json", registry)
        save(self.prepared / "runtime.json", {"model": "synthetic_no_model_calls"})
        save(self.prepared / "prompt_contract.json", {"fixture_only": True})
        save(self.prepared / "remaining_requirements.json", {"fixture_only": True})
        (self.prepared / "system_instruction.txt").write_text("Synthetic fixture; not sendable", encoding="utf-8")
        for source in SOURCES:
            save(self.prepared / "packets" / (source + ".json"), self.values[source][1])
        for arm in ("R1", "R4"):
            for stage in range(1, 5):
                save(self.prepared / f"schemas/{arm}_stage{stage}.json", {"fixture_only": True})
        for case in ROSTER:
            for stage in range(1, 5):
                save(self.prepared / f"previews/{case['case_id']}/stage{stage}_payload.json", {"fixture_only": True})
        files = sorted(p for p in self.prepared.rglob("*") if p.is_file())
        self.manifest = {"candidate_version": "v4.8-main-candidate-1", "protocol_version": "4.8",
            "scope": "offline_main_input_candidate_not_execution_registration", "main_authorized": False,
            "main_frozen": False, "human_review_completed": False, "main_model_calls": 0,
            "roster": list(ROSTER), "planned_case_count": 4, "expected_sector_count": 44,
            "files": {p.relative_to(self.prepared).as_posix(): pilot.digest(p) for p in files}}
        self.manifest_path = self.prepared / "manifest.json"
        self.pin_manifest()
        self.gold = root / "evaluator_only_gold.jsonl"
        self.gold.write_text("\n".join(json.dumps(value[2]) for value in self.values.values()) + "\n", encoding="utf-8")
        materials = {"reference_annotations": pilot.reference(self.gold)}
        for name in EVALUATOR_MATERIAL_KEYS:
            if name == "reference_annotations":
                continue
            path = root / "offline_criteria" / (name + ".json")
            save(path, {"synthetic_fixture_only": True, "criterion": name})
            materials[name] = pilot.reference(path)
        self.manifest["evaluator_material_refs"] = materials
        self.pin_manifest()
        for name in EXECUTION_SNAPSHOTS:
            save(self.run / name, {"synthetic_fixture_only": True, "not_actual_approval": True})
        self.summary()

    def pin_manifest(self):
        save(self.manifest_path, self.manifest)
        save(self.run / "manifest_snapshot.json", self.manifest)

    def endpoint(self, case, endpoint="C0", *, total=1, completed=True, raw=None, record_exists=True):
        folder = self.run / case["case_id"] / endpoint
        values = self.values[case["source_id"]]
        proposal = copy.deepcopy(values[0])
        proposal["weights"][0]["weight"] = total
        stage = int(endpoint[-1]) if endpoint.startswith("stage") else 4
        visible = case["arm"] == "R1" or stage == 4
        if not visible:
            proposal.update(source_id=None, interpretations=[])
        content = json.dumps(proposal) if raw is None else raw
        save(folder / "http_0001_generation/request.json", {"body": {"fixture_only": True}})
        if completed:
            save(folder / "http_0001_generation/response.json", {"message": {"content": content}, "done_reason": "stop"})
        else:
            save(folder / "http_0001_generation/assembled_text.json", {"content": content, "complete": False})
        ids = values[5]["visible_evidence_ids"] if visible else ["M:vol:10"]
        save(folder / "visible_evidence_before_generation.json", {"ids": ids, "calculator_facts": []})
        record = {"endpoint": endpoint, "stage": stage, "institution_visible": visible,
            "raw_response_text": content, "parsed_response": proposal if raw is None else None,
            "response_complete": completed, "transport_status": "completed" if completed else "hard_deadline",
            "transport_result": {"supervisor": {"elapsed_seconds": 3.25}},
            "visible_evidence_ids_before_generation": ids, "visible_calculator_facts_before_generation": [],
            "request_body_sha256": pilot.value_digest({"fixture_only": True}),
            "feedback": {"facts": [{"fact_id": "C:" + endpoint + ":sum", "value": total}]}}
        if record_exists:
            save(folder / "record.json", record)
        return folder, record

    def case_summary(self, case, endpoints):
        folder = self.run / case["case_id"]
        entries = [{"endpoint": endpoint, "generation_attempted": True,
                    "record": pilot.reference(folder / endpoint / "record.json")} for endpoint in endpoints]
        summary = {**case, "status": "synthetic_fixture", "endpoints": entries,
            "core_calls_attempted": sum(x not in ("C1", "C2") for x in endpoints),
            "auxiliary_calls_attempted": sum(x in ("C1", "C2") for x in endpoints), "main_model_calls": len(endpoints),
            "system_integrity_incident": False,
            "primary_record": pilot.reference(folder / "C0/record.json") if "C0" in endpoints else None}
        save(folder / "case_summary.json", summary)
        save(folder / "case_manifest.json", {**case, "packet": pilot.reference(self.prepared / "packets" / (case["source_id"] + ".json"))})
        self.summary()

    def summary(self):
        requests = list(self.run.glob("*/*/http_0001_generation/request.json"))
        data = {"planned_cases": list(ROSTER), "status": "synthetic_fixture_not_empirical",
            "core_generation_calls": sum(p.relative_to(self.run).parts[1] not in ("C1", "C2") for p in requests),
            "auxiliary_generation_calls": sum(p.relative_to(self.run).parts[1] in ("C1", "C2") for p in requests),
            "main_model_calls": len(requests), "main_frozen": True, "human_review_completed": True}
        save(self.run / "summary.json", data)
        return data

    def load(self):
        return build_report(self.manifest_path, self.run, self.gold, workspace_root=self.root, synthetic=True)


class MainOfflineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = MainFixture(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_four_main_cases_and_44_rows_even_without_any_C0(self):
        report, worksheet = self.f.load()
        self.assertEqual(report["scope"], "main_only_offline_analysis")
        self.assertEqual(report["primary_C0_bundle"]["expected_sector_count"], 44)
        self.assertEqual([r["case_id"] for r in worksheet["primary_C0_reviews"]], [c["case_id"] for c in ROSTER])
        self.assertEqual(report["observed_main_generation_calls"], 0)
        self.assertIsNone(report["strategic_preservation_verdict"])

    def test_main_calls_are_observed_not_inherited_candidate_zero_or_evaluator_zero(self):
        self.f.endpoint(ROSTER[0], "stage1")
        self.f.endpoint(ROSTER[0], "C0", total=.975)
        self.f.endpoint(ROSTER[0], "C1", total=1)
        self.f.case_summary(ROSTER[0], ["stage1", "C0", "C1"])
        report, worksheet = self.f.load()
        self.assertEqual(report["observed_main_generation_calls"], 3)
        self.assertEqual(report["model_calls_by_this_evaluation"], 0)
        self.assertEqual(self.f.manifest["main_model_calls"], 0)
        self.assertNotIn("main_model_calls_by_this_evaluation", report)
        self.assertFalse(report["primary_C0_cases"][0]["execution"]["valid_raw_allocation"])
        self.assertTrue(report["auxiliary_endpoint_cases"][0]["execution"]["valid_raw_allocation"])
        self.assertEqual(report["primary_C0_cases"][0]["execution"]["elapsed_seconds"], 3.25)
        self.assertEqual(len(worksheet["auxiliary_reviews"]), 1)
        self.assertTrue(report["pre_execution_human_source_review_as_recorded"])
        self.assertFalse(worksheet["independent_human_review_completed"])
        self.assertFalse(report["execution_gate_verified_by_this_loader"])

    def test_early_main_failure_preserves_workflow_attempt_without_C0_attempt(self):
        self.f.endpoint(ROSTER[1], "stage1", completed=False, raw='{"partial":')
        self.f.case_summary(ROSTER[1], ["stage1"])
        report, worksheet = self.f.load()
        self.assertEqual(report["primary_C0_bundle"]["attempted_case_count"], 1)
        self.assertEqual(report["primary_C0_bundle"]["C0_attempted_case_count"], 0)
        self.assertEqual(report["observed_main_generation_calls"], 1)
        self.assertTrue(any(x["raw_response_text"] == '{"partial":' for x in worksheet["workflow_trace_materials"]))

    def test_orphan_capture_never_becomes_completed_C0(self):
        self.f.endpoint(ROSTER[0], record_exists=False)
        self.f.summary()
        report, worksheet = self.f.load()
        self.assertEqual(report["observed_main_generation_calls"], 1)
        self.assertEqual(report["primary_C0_bundle"]["completed_response_count"], 0)
        self.assertEqual(report["primary_C0_bundle"]["exact_label_correct_count"], 0)
        self.assertTrue(worksheet["primary_C0_reviews"][0]["literal_fields_for_manual_claim_review"])

    def test_gate_snapshots_missing_are_issues_without_erasing_model_text(self):
        self.f.endpoint(ROSTER[0])
        self.f.case_summary(ROSTER[0], ["C0"])
        (self.f.run / EXECUTION_SNAPSHOTS[0]).unlink()
        report, worksheet = self.f.load()
        self.assertIn("main_execution_snapshot_missing", [x["kind"] for x in report["artifact_issues"]])
        self.assertEqual(report["observed_main_generation_calls"], 1)
        self.assertTrue(worksheet["primary_C0_reviews"][0]["literal_fields_for_manual_claim_review"])

    def test_wrong_reported_main_zero_is_not_accepted_as_observed_zero(self):
        self.f.endpoint(ROSTER[0])
        self.f.case_summary(ROSTER[0], ["C0"])
        summary = self.f.summary();summary["main_model_calls"] = 0
        save(self.f.run / "summary.json", summary)
        report, _ = self.f.load()
        self.assertEqual(report["observed_main_generation_calls"], 1)
        self.assertTrue(any(x.get("field") == "main_model_calls" for x in report["artifact_issues"]))

    def test_candidate_cannot_be_silently_rewritten_into_an_approval(self):
        self.f.manifest["main_authorized"] = True
        self.f.pin_manifest()
        with self.assertRaisesRegex(ValueError, "unapproved"):
            self.f.load()

    def test_pilot_request_cannot_enter_main_case_accounting(self):
        save(self.f.run / "fidelity_q2_2026__R1/C0/http_0001_generation/request.json", {"body": {}})
        with self.assertRaisesRegex(ValueError, "Unregistered main"):
            self.f.load()

    def test_main_candidate_packet_or_gold_cannot_have_pilot_split(self):
        path = self.f.prepared / "packets" / (SOURCES[0] + ".json")
        packet = pilot.read(path);packet["split"] = "pilot";save(path, packet)
        self.f.manifest["files"][path.relative_to(self.f.prepared).as_posix()] = pilot.digest(path)
        self.f.pin_manifest()
        with self.assertRaisesRegex(ValueError, "main packet"):
            self.f.load()

    def test_unbound_gold_path_is_rejected_even_for_identical_bytes(self):
        alternate = self.f.root / "alternate_gold.jsonl"
        alternate.write_bytes(self.f.gold.read_bytes())
        with self.assertRaisesRegex(ValueError, "--gold differs"):
            build_report(self.f.manifest_path, self.f.run, alternate, workspace_root=self.f.root, synthetic=True)

    def test_changed_gold_or_criteria_rejected_before_scoring_and_raw_preserved(self):
        folder, _ = self.f.endpoint(ROSTER[0])
        before = (folder / "record.json").read_bytes()
        self.f.gold.write_text(self.f.gold.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "reference_annotations"):
            self.f.load()
        self.assertEqual((folder / "record.json").read_bytes(), before)
        self.f.manifest["evaluator_material_refs"]["reference_annotations"] = pilot.reference(self.f.gold)
        self.f.pin_manifest()
        criteria = Path(self.f.manifest["evaluator_material_refs"]["evaluation_protocol"]["path"])
        save(criteria, {"changed_after_binding": True})
        with self.assertRaisesRegex(ValueError, "evaluation_protocol"):
            self.f.load()

    def test_evaluator_material_inventory_and_required_hash_cannot_be_missing(self):
        self.f.manifest["evaluator_material_refs"]["source_comparison"]["sha256"] = None
        self.f.pin_manifest()
        with self.assertRaisesRegex(ValueError, "lowercase SHA-256"):
            self.f.load()
        self.f.manifest.pop("evaluator_material_refs")
        self.f.pin_manifest()
        with self.assertRaisesRegex(ValueError, "six candidate-bound"):
            self.f.load()

    def test_evaluator_material_change_during_analysis_is_rejected(self):
        original = main_loader._load_endpoint
        criteria = Path(self.f.manifest["evaluator_material_refs"]["evaluation_protocol"]["path"])
        changed = False
        def change_after_initial_verification(*args, **kwargs):
            nonlocal changed
            result = original(*args, **kwargs)
            if not changed:
                save(criteria, {"changed_while_analysis_was_running": True})
                changed = True
            return result
        with patch.object(main_loader, "_load_endpoint", side_effect=change_after_initial_verification):
            with self.assertRaisesRegex(ValueError, "evaluation_protocol"):
                self.f.load()

    def test_extra_gold_file_in_online_candidate_inventory_is_rejected(self):
        save(self.f.prepared / "hidden_gold.json", {"fixture_only": True})
        self.f.manifest["files"]["hidden_gold.json"] = pilot.digest(self.f.prepared / "hidden_gold.json")
        self.f.pin_manifest()
        with self.assertRaisesRegex(ValueError, "file inventory"):
            self.f.load()

    def test_pilot_globals_unchanged_after_main_analysis(self):
        before = (pilot.SOURCES, pilot.ROSTER, pilot.VERSION)
        self.f.load()
        self.assertEqual((pilot.SOURCES, pilot.ROSTER, pilot.VERSION), before)
        self.assertNotEqual(pilot.SOURCES, SOURCES)

    def test_output_never_written_into_online_or_candidate_and_never_overwrites(self):
        for output in (self.f.run / "analysis", self.f.prepared / "analysis"):
            with self.assertRaisesRegex(ValueError, "separate"):
                write_report(self.f.manifest_path, self.f.run, self.f.gold, output, synthetic=True)
        output = self.f.root / "offline_report"
        receipt = write_report(self.f.manifest_path, self.f.run, self.f.gold, output, workspace_root=self.f.root, synthetic=True)
        self.assertEqual(receipt["data_origin"], "synthetic_fixture_not_empirical")
        self.assertFalse(receipt["main_execution_authorized_by_this_tool"])
        with self.assertRaises(FileExistsError):
            write_report(self.f.manifest_path, self.f.run, self.f.gold, output, synthetic=True)


class Inspector(HTMLParser):
    def __init__(self):
        super().__init__();self.ids=[];self.scripts=0
    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:self.ids.append(values["id"])
        if tag == "script":self.scripts += 1


class MainRenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = MainFixture(Path(self.tmp.name))
        self.f.endpoint(ROSTER[0], total=.975)
        self.f.endpoint(ROSTER[0], "C1")
        self.f.case_summary(ROSTER[0], ["C0", "C1"])
        self.report, self.worksheet = self.f.load()
        self.paths = {"report_path": self.f.root / "evaluation_report.json",
                      "worksheet_path": self.f.root / "semantic_review_worksheet.json",
                      "output_path": self.f.root / "preview.html"}

    def tearDown(self):
        self.tmp.cleanup()

    def render(self):
        return render_packet(self.report, self.worksheet, **self.paths)

    def test_synthetic_marker_calls_and_strict_label_meaning_remain_explicit(self):
        html = self.render()
        self.assertIn("합성 자료 검증용 · 실제 본실험 결과 아님", html)
        self.assertIn("평가기의 호출이 0", html)
        self.assertIn("출처 ID 포함 등급 진단", html)
        self.assertIn("/ 44개 산업행", html)
        self.assertIn("97.5%", html)
        self.assertIn("독립 사람 의미 검토: 미작성", html)
        self.assertLess(html.index('id="primary"'), html.index('id="auxiliary"'))
        parser=Inspector();parser.feed(html)
        for case in ROSTER:self.assertIn(case["case_id"] + "-C0", parser.ids)
        self.assertIn(ROSTER[0]["case_id"] + "-C1", parser.ids)

    def test_untrusted_rationale_is_literal_and_human_fields_remain_null(self):
        row = self.worksheet["primary_C0_reviews"][0]["sector_reviews"][0]
        row["allocation_rationale_literal"] = '<script>alert("x")</script>'
        html = self.render();parser=Inspector();parser.feed(html)
        self.assertEqual(parser.scripts, 0)
        self.assertIn("&lt;script&gt;", html)
        self.assertIsNone(row["action_consistency"])

    def test_heading_adapter_never_rewrites_literal_model_or_source_text(self):
        row = self.worksheet["primary_C0_reviews"][0]["sector_reviews"][0]
        literal = '인용 원문: 등급 문자열 진단: 그대로 보존'
        row["allocation_rationale_literal"] = literal
        row["interpretation_reason_literal"] = literal
        row["source_passages"][0]["text"] = literal
        html = self.render()
        self.assertEqual(html.count(literal), 3)
        self.assertIn('<p class="note">출처 ID 포함 등급 진단: ', html)
        self.assertIn('v48_source_comparison_20261018_v2.html', html)

    def test_pilot_or_dropped_main_case_or_completed_judgment_is_rejected(self):
        original = copy.deepcopy(self.worksheet)
        self.report["scope"] = "pilot_only_offline_analysis"
        with self.assertRaisesRegex(ValueError, "main-only"):self.render()
        self.report["scope"] = "main_only_offline_analysis"
        self.worksheet["primary_C0_reviews"].pop()
        with self.assertRaisesRegex(ValueError, "four"):self.render()
        self.worksheet = original
        self.worksheet["primary_C0_reviews"][0]["sector_reviews"][0]["claim_support"] = "pass"
        with self.assertRaisesRegex(ValueError, "semantic judgments"):self.render()

    def test_write_is_new_offline_only_and_receipt_does_not_authorize(self):
        save(self.paths["report_path"], self.report);save(self.paths["worksheet_path"], self.worksheet)
        with self.assertRaisesRegex(ValueError, "outside"):
            write_packet(self.paths["report_path"], self.paths["worksheet_path"], self.f.run / "review.html")
        receipt = write_packet(**self.paths)
        self.assertEqual(receipt["observed_main_generation_calls"], 2)
        self.assertEqual(receipt["model_calls_by_this_render"], 0)
        self.assertFalse(receipt["main_execution_authorized_by_this_tool"])
        with self.assertRaises(FileExistsError):write_packet(**self.paths)

    def test_renderer_rechecks_candidate_bound_materials_without_new_scores(self):
        self.assertTrue(self.report["evaluation_materials_verified"])
        materials = self.report["provenance"]["evaluator_material_refs"]
        save(Path(materials["review_template"]["path"]), {"changed_after_analysis": True})
        with self.assertRaisesRegex(ValueError, "review_template"):
            self.render()


if __name__ == "__main__":
    unittest.main(verbosity=2)
