"""Offline artifact-loader tests with synthetic model responses only."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from evaluate_sector_v48_artifacts import (ROSTER, SOURCES, build_report, write_report, digest, value_digest,
                                         _elapsed_material)
from test_evaluate_sector_v48 import fixture


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class ArtifactLoaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.prepared = self.root / "prepared"
        self.run = self.root / "run"
        self.run.mkdir()
        self.values = {source: fixture(source) for source in SOURCES}
        market, registry = copy.deepcopy(self.values[SOURCES[0]][3:5])
        save(self.prepared / "market_input.json", market)
        registry["source"] = {"sha256": digest(self.prepared / "market_input.json")}
        save(self.prepared / "public_numeric_registry.json", registry)
        save(self.prepared / "runtime.json", {"model": "synthetic-test-no-call"})
        save(self.prepared / "prompt_contract.json", {"test_only": True})
        for source in SOURCES:
            save(self.prepared / "packets" / (source + ".json"), self.values[source][1])
        self.manifest_path = self.prepared / "manifest.json"
        files = sorted(path for path in self.prepared.rglob("*.json"))
        self.manifest = {"protocol_version": "4.8", "scope": "all_four_fixed_pilot_cases_only",
                         "roster": list(ROSTER), "main_authorized": False,
                         "input_hashes": {path.relative_to(self.prepared).as_posix(): digest(path) for path in files},
                         "software_hashes": {"fixture": "no-execution-attestation"}}
        save(self.manifest_path, self.manifest)
        save(self.run / "manifest_snapshot.json", self.manifest)
        self.gold = self.root / "offline_gold.jsonl"
        annotations = [copy.deepcopy(self.values[source][2]) for source in SOURCES]
        for annotation in annotations:
            annotation["split"] = "pilot"
            annotation["review_status"] = {"human_source_validation": "pending"}
        self.gold.write_text("\n".join(json.dumps(value) for value in annotations) + "\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def ref(self, path):
        return {"path": path.relative_to(self.root).as_posix(), "sha256": digest(path)}

    def endpoint(self, case, endpoint="C0", *, total=1, status="completed", raw=None, completed=True, record_exists=True):
        folder = self.run / case["case_id"] / endpoint
        values = self.values[case["source_id"]]
        proposal = copy.deepcopy(values[0])
        proposal["weights"][0]["weight"] = total
        stage = int(endpoint[-1]) if endpoint.startswith("stage") else 4
        visible = case["arm"] == "R1" or stage == 4
        if not visible:
            proposal["source_id"] = None
            proposal["interpretations"] = []
        text = json.dumps(proposal) if raw is None else raw
        save(folder / "http_0001_generation/request.json", {"body": {"test_only": True}})
        if completed:
            save(folder / "http_0001_generation/response.json", {"message": {"content": text}, "done_reason": "stop"})
        else:
            save(folder / "http_0001_generation/assembled_text.json", {"content": text, "complete": False})
        visible_ids = values[5]["visible_evidence_ids"] if visible else ["M:vol:10"]
        visibility = {"ids": visible_ids, "calculator_facts": []}
        save(folder / "visible_evidence_before_generation.json", visibility)
        record = {"endpoint": endpoint, "stage": stage, "institution_visible": visible,
                  "raw_response_text": text, "response_complete": completed,
                  "parsed_response": proposal if raw is None else None,
                  "transport_status": status, "transport_result": {"wall_seconds": 1.25},
                  "visible_evidence_ids_before_generation": visible_ids,
                  "visible_calculator_facts_before_generation": [], "recorded_at_utc": "2026-10-18T01:00:00Z",
                  "request_body_sha256": value_digest({"test_only": True}),
                  "feedback": {"facts": [{"fact_id": "C:" + endpoint + ":sum", "value": total}]}}
        if record_exists:
            save(folder / "record.json", record)
        return folder, record

    def case_summary(self, case, endpoints, *, status="completed_core", incident=False, attempted_count=None):
        folder = self.run / case["case_id"]
        entries = []
        for endpoint in endpoints:
            path = folder / endpoint / "record.json"
            record = json.loads(path.read_text(encoding="utf-8"))
            entries.append({"endpoint": endpoint, "status": record["transport_status"],
                            "generation_attempted": True, "record": self.ref(path)})
        summary = {**case, "status": status, "endpoints": entries,
                   "core_calls_attempted": sum(e not in ("C1", "C2") for e in endpoints) if attempted_count is None else attempted_count,
                   "auxiliary_calls_attempted": sum(e in ("C1", "C2") for e in endpoints),
                   "system_integrity_incident": incident,
                   "primary_record": self.ref(folder / "C0/record.json") if "C0" in endpoints else None,
                   "auxiliary_terminal_record": self.ref(folder / endpoints[-1] / "record.json") if endpoints and endpoints[-1] in ("C1", "C2") else None}
        save(folder / "case_summary.json", summary)
        save(folder / "case_manifest.json", {**case, "packet": self.ref(self.prepared / "packets" / (case["source_id"] + ".json"))})

    def load(self):
        return build_report(self.manifest_path, self.run, self.gold, workspace_root=self.root)

    def test_all_absent_keeps_four_cases_and_fortyfour_rows(self):
        report, worksheet = self.load()
        bundle = report["primary_C0_bundle"]
        self.assertEqual(bundle["planned_case_count"], 4)
        self.assertEqual(bundle["expected_sector_count"], 44)
        self.assertEqual(bundle["C0_attempted_case_count"], 0)
        self.assertEqual(len(worksheet["primary_C0_reviews"]), 4)
        self.assertFalse(worksheet["independent_human_review_completed"])

    def test_early_failure_counts_workflow_not_C0_and_preserves_trace(self):
        case = ROSTER[1]
        self.endpoint(case, "stage1", status="hard_deadline", raw='{"unfinished":', completed=False)
        self.case_summary(case, ["stage1"], status="stopped_hard_deadline")
        report, worksheet = self.load()
        self.assertEqual(report["primary_C0_bundle"]["attempted_case_count"], 1)
        self.assertEqual(report["primary_C0_bundle"]["C0_attempted_case_count"], 0)
        trace = next(item for item in worksheet["workflow_trace_materials"] if item["case_id"] == case["case_id"] and item["endpoint"] == "stage1")
        self.assertEqual(trace["raw_response_text"], '{"unfinished":')
        self.assertIsNone(trace["automatic_semantic_assessment"])

    def test_valid_repair_never_replaces_invalid_C0(self):
        case = ROSTER[0]
        self.endpoint(case, "C0", total=0.975)
        self.endpoint(case, "C1", total=1)
        self.case_summary(case, ["C0", "C1"], status="completed_core_and_auxiliary_policy")
        report, worksheet = self.load()
        self.assertEqual(report["primary_C0_bundle"]["valid_raw_allocation_count"], 0)
        self.assertEqual(report["primary_C0_cases"][0]["execution"]["raw_sum"], 0.975)
        self.assertEqual(report["auxiliary_endpoint_cases"][0]["execution"]["raw_sum"], 1)
        self.assertEqual(len(worksheet["auxiliary_reviews"]), 1)
        row = worksheet["primary_C0_reviews"][0]["sector_reviews"][0]
        self.assertIsNotNone(row["allocation_rationale_literal"])
        self.assertIsNone(row["source_to_action_assessment_status"])
        self.assertIsNone(report["strategic_preservation_verdict"])

    def test_current_feedback_does_not_become_pre_generation_evidence(self):
        case = ROSTER[0]
        folder, record = self.endpoint(case)
        # A model citing its yet-to-be-computed C0 fact cannot use post-response feedback.
        proposal = json.loads(record["raw_response_text"])
        proposal["weights"][0]["evidence_ids"] = ["C:C0:sum"]
        self.endpoint(case, raw=json.dumps(proposal))
        self.case_summary(case, ["C0"])
        report, _ = self.load()
        cite = report["primary_C0_cases"][0]["review_preparation"]["sector_reviews"][0]["allocation_citations"]["entries"][0]
        self.assertFalse(cite["visible"])
        self.assertEqual(cite["kind"], "unknown")

    def test_actual_nested_supervisor_time_takes_precedence_and_retains_scope(self):
        case = ROSTER[0]
        folder, record = self.endpoint(case)
        record["transport_result"] = {
            "wall_seconds": 1.25,
            "supervisor": {"elapsed_seconds": 572.0204213000252,
                           "deadline_scope": "Child setup, metadata, rendering and generation; cleanup excluded.",
                           "worker": {"elapsed_seconds": 570.1340267000196}}}
        save(folder / "record.json", record)
        self.case_summary(case, ["C0"])
        report, worksheet = self.load()
        self.assertEqual(report["primary_C0_cases"][0]["execution"]["elapsed_seconds"], 572.0204213000252)
        material = next(row for row in worksheet["workflow_trace_materials"]
                        if row["case_id"] == case["case_id"] and row["endpoint"] == "C0")
        timing = material["timing_provenance"]
        self.assertEqual(timing["selected_record_field"], "transport_result.supervisor.elapsed_seconds")
        self.assertIn("cleanup excluded", timing["scope"])
        self.assertEqual(timing["observed_duration_fields"]["transport_result.supervisor.worker.elapsed_seconds"],
                         570.1340267000196)

    def test_worker_duration_fallback_has_its_own_narrower_scope(self):
        timing = _elapsed_material({"transport_result": {"supervisor": {"worker": {"elapsed_seconds": 570.1}},
                                                        "wall_seconds": 1.25}})
        self.assertEqual(timing["elapsed_seconds"], 570.1)
        self.assertEqual(timing["selected_record_field"], "transport_result.supervisor.worker.elapsed_seconds")
        self.assertIn("excludes supervisor setup", timing["scope"])

    def test_missing_duration_is_not_zero_or_provider_duration_and_legacy_is_labelled(self):
        absent = _elapsed_material({"transport_result": {"response": {"total_duration": 5000000000}}})
        self.assertIsNone(absent["elapsed_seconds"])
        self.assertIsNone(absent["selected_record_field"])
        legacy = _elapsed_material({"transport_result": {"wall_seconds": 1.25}})
        self.assertEqual(legacy["elapsed_seconds"], 1.25)
        self.assertIn("legacy", legacy["scope"])

    def test_invalid_preferred_duration_is_not_hidden_by_fallback(self):
        for value in (-1, True, "572.0"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Invalid recorded elapsed"):
                _elapsed_material({"transport_result": {"supervisor": {"elapsed_seconds": value}, "wall_seconds": 1.25}})

    def test_complete_capture_without_record_stays_unconfirmed_endpoint(self):
        self.endpoint(ROSTER[0], record_exists=False)
        report, worksheet = self.load()
        result = report["primary_C0_cases"][0]
        self.assertTrue(result["execution"]["attempted"])
        self.assertFalse(result["execution"]["transport_completed"])
        self.assertEqual(result["source_fact_preservation"]["exact_label_correct_count"], 0)
        self.assertEqual(result["source_fact_preservation"]["observed_exact_labels_in_readable_material"], 11)
        self.assertTrue(worksheet["primary_C0_reviews"][0]["literal_fields_for_manual_claim_review"])

    def test_partial_response_envelope_keeps_cancelled_record_without_credit(self):
        case = ROSTER[0]
        folder, _ = self.endpoint(case, completed=False, raw='{"unfinished":', status="cancelled")
        (folder / "http_0001_generation/response.json").write_text('{"message":', encoding="utf-8")
        self.case_summary(case, ["C0"], status="stopped_cancelled")
        report, worksheet = self.load()
        result = report["primary_C0_cases"][0]
        self.assertFalse(result["execution"]["transport_completed"])
        self.assertEqual(result["source_fact_preservation"]["exact_label_correct_count"], 0)
        self.assertEqual(report["artifact_issues"][0]["kind"], "malformed_or_partial_response_envelope")
        material = next(row for row in worksheet["workflow_trace_materials"] if row["case_id"] == case["case_id"] and row["endpoint"] == "C0")
        self.assertEqual(material["raw_response_text"], '{"unfinished":')
        self.assertIsNotNone(material["response_ref"])

    def test_bad_envelope_claiming_completion_remains_an_integrity_error(self):
        case = ROSTER[0]
        folder, _ = self.endpoint(case)
        (folder / "http_0001_generation/response.json").write_text('{"message":', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "claims completion"):
            self.load()

    def test_unrecorded_partial_envelopes_fall_back_to_flushed_events(self):
        folder, _ = self.endpoint(ROSTER[0], record_exists=False, completed=False)
        generation = folder / "http_0001_generation"
        (generation / "response.json").write_text('{"message":', encoding="utf-8")
        (generation / "assembled_text.json").write_text('{"content":', encoding="utf-8")
        (generation / "events.jsonl").write_text(json.dumps({"event": {"message": {"content": "literal retained fragment"}}}) + '\n{"partial":', encoding="utf-8")
        report, worksheet = self.load()
        material = next(row for row in worksheet["workflow_trace_materials"] if row["case_id"] == ROSTER[0]["case_id"] and row["endpoint"] == "C0")
        self.assertEqual(material["raw_response_text"], "literal retained fragment")
        self.assertEqual(len(material["capture_diagnostics"]), 3)
        self.assertFalse(report["primary_C0_cases"][0]["execution"]["transport_completed"])

    def test_completed_response_and_later_cleanup_incident_both_retained(self):
        case = ROSTER[0]
        self.endpoint(case, status="cleanup_not_confirmed")
        self.case_summary(case, ["C0"], status="stopped_cleanup_not_confirmed", incident=True)
        report, _ = self.load()
        self.assertTrue(report["primary_C0_cases"][0]["execution"]["transport_completed"])
        self.assertTrue(report["system_integrity_incidents_present"])

    def test_raw_record_response_disagreement_is_not_silently_scored(self):
        case = ROSTER[0]
        folder, record = self.endpoint(case)
        record["raw_response_text"] = "modified after capture"
        save(folder / "record.json", record)
        self.case_summary(case, ["C0"])
        with self.assertRaisesRegex(ValueError, "raw text differs"):
            self.load()

    def test_record_hash_change_detected(self):
        case = ROSTER[0]
        folder, record = self.endpoint(case)
        self.case_summary(case, ["C0"])
        record["recorded_at_utc"] = "changed"
        save(folder / "record.json", record)
        with self.assertRaisesRegex(ValueError, "hash does not match"):
            self.load()

    def test_prepared_input_change_detected(self):
        save(self.prepared / "market_input.json", {"changed": True})
        with self.assertRaisesRegex(ValueError, "Prepared input changed"):
            self.load()

    def test_manifest_snapshot_and_roster_must_match(self):
        altered = copy.deepcopy(self.manifest)
        altered["roster"] = altered["roster"][:-1]
        save(self.run / "manifest_snapshot.json", altered)
        with self.assertRaisesRegex(ValueError, "snapshot differs"):
            self.load()

    def test_visibility_record_mismatch_detected(self):
        case = ROSTER[0]
        folder, _ = self.endpoint(case)
        save(folder / "visible_evidence_before_generation.json", {"ids": ["invented_future"], "calculator_facts": []})
        with self.assertRaisesRegex(ValueError, "pre-generation visibility"):
            self.load()

    def test_generation_request_body_change_detected(self):
        folder, _ = self.endpoint(ROSTER[0])
        save(folder / "http_0001_generation/request.json", {"body": {"changed_prompt": True}})
        with self.assertRaisesRegex(ValueError, "request hash differs"):
            self.load()

    def test_extra_generation_call_is_not_silently_omitted(self):
        save(self.run / ROSTER[0]["case_id"] / "C3/http_0001_generation/request.json", {"body": {}})
        with self.assertRaisesRegex(ValueError, "Unregistered generation"):
            self.load()

    def test_output_is_new_offline_location_and_hash_receipt(self):
        for output in (self.run / "evaluation", self.prepared / "evaluation"):
            with self.assertRaisesRegex(ValueError, "outside online/prepared"):
                write_report(self.manifest_path, self.run, self.gold, output, workspace_root=self.root)
        output = self.root / "evaluator_only" / "run1"
        receipt = write_report(self.manifest_path, self.run, self.gold, output, workspace_root=self.root)
        self.assertEqual(receipt["model_calls"], 0)
        self.assertEqual(receipt["files"][0]["sha256"], digest(output / "evaluation_report.json"))
        with self.assertRaises(FileExistsError):
            write_report(self.manifest_path, self.run, self.gold, output, workspace_root=self.root)

    def test_summary_cannot_claim_missing_requests(self):
        case = ROSTER[0]
        self.endpoint(case)
        self.case_summary(case, ["C0"], attempted_count=2)
        with self.assertRaisesRegex(ValueError, "requests absent"):
            self.load()

    def test_stale_summary_count_retains_actual_attempt_accounting(self):
        case = ROSTER[0]
        self.endpoint(case, "stage1")
        self.case_summary(case, ["stage1"], attempted_count=0, status="running")
        report, _ = self.load()
        self.assertEqual(report["primary_C0_bundle"]["attempted_case_count"], 1)
        self.assertEqual(report["artifact_issues"][0]["kind"], "summary_attempt_count_lags_preserved_requests")


if __name__ == "__main__":
    unittest.main(verbosity=2)
