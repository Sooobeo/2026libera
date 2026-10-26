"""Synthetic completion bundle tests; no model/service calls or real responses.

Only the inherited full offline worker validator is substituted with a local
fixture validator. Gate/code/receipt/source/history/hash guards here run normally;
the production validator remains mandatory and its rejection is tested.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("completion_audit", Path(__file__).with_name("prepare_stage_semantic_audit.py"))
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class CompletionBundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run = self.root / "data/local_sector_runtime/completion"
        self.run.mkdir(parents=True)
        self.reports = self.root / "research/completion_20261026"
        self.reports.mkdir(parents=True)
        for name, value in (("ROOT", self.root), ("REPORT_ROOT", self.reports)):
            p = patch.object(audit, name, value); p.start(); self.addCleanup(p.stop)
        rubric = self.write(self.root / "rubric.json", {"fixture": "rubric"})
        p = patch.object(audit, "RUBRIC_REF", rubric); p.start(); self.addCleanup(p.stop)
        p = patch.object(audit, "validate_worker_spec", side_effect=self.worker_validation)
        self.validator = p.start(); self.addCleanup(p.stop)
        self.packet = {"source_id": "ubs_june_2026", "rating_vocabulary": ["Neutral"], "evidence_table": {
            "columns": ["evidence_id", "source_page", "text"], "rows": [
                ["ubs_june_2026:p3:sector:" + code, 3, "Sector receives Neutral. Balanced."] for code in audit.CODES]}}
        self.runtime = {"options": {"temperature": 0}}
        self.origin = "http://127.0.0.1:11435"
        self.messages = {}
        prepared = []
        for case in audit.CASES:
            initial = {"common_context": {"evidence_id": "CTX:task"},
                "common_market": {"sector_codes": list(audit.CODES), "baseline_weights": dict.fromkeys(audit.CODES, .1)},
                "public_numeric_fact_index": {"columns": ["fact_id", "value"], "rows": [["M:a:10", .1]]},
                "institution_document": self.packet if case.endswith("__E") else None}
            messages = [{"role": "system", "content": "fixed"}, {"role": "user", "content": json.dumps(initial)}]
            self.messages[case] = messages
            ref = self.write(self.root / (case + "_prepared.json"), messages)
            prepared.append({"case_id": case, "stage": "D0", **ref})
        aggregate = self.write(self.root / "aggregate.json", {"public_source_packets": {"ubs_june_2026": self.packet}})
        self.manifest = self.write(self.root / "manifest.json", {"prepared_cases": prepared,
            "inputs": {"public_aggregate_never_sent": aggregate}})
        self.scope = {"purpose": "pilot_completion", "case_order": list(audit.CASES),
            "max_generation_requests": 6, "historical_generation_requests": 5, "campaign_max_generation_requests": 11,
            "automatic_retries": 0, "main_model_calls": 0, "main_allowed": False, "old_outputs_observed": True,
            "analysis_role": "primary_exploratory", "excluded_new_main_execution": True,
            "explicit_retry_slots": [], "historical_explicit_retry_slots": ["fidelity_q2_2026__L__D0"],
            "run_directory": str(self.run), "runtime_ref": self.write(self.root / "runtime.json", self.runtime),
            "protocol_ref": self.write(self.root / "protocol.json", {"fixture": "protocol"}),
            "prepared_manifest_ref": self.manifest}
        code_refs = []
        for name in sorted(audit.CODE_PATHS):
            path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("# synthetic pinned code\n")
            code_refs.append(self.ref(path))
        self.frozen = {**self.scope, "freeze_version": "sector_completion_freeze_1",
                       "status": "frozen_for_pilot_completion_only", "code_refs": code_refs}
        self.freeze_ref = self.write(self.root / "freeze.json", self.frozen)
        self.gate = {**self.scope, "receipt_version": "sector_completion_gate_1",
                     "status": "approved_for_completion_before_generation", "freeze_ref": self.freeze_ref}
        self.gate_ref = self.write(self.root / "gate.json", self.gate)
        self.declaration = {**self.scope, "review_gate": self.gate_ref, "freeze_ref": self.freeze_ref,
                            "runtime": self.runtime, "origin": self.origin}
        self.write(self.run / "campaign_declaration.json", self.declaration)
        self.case = audit.CASES[1]

    def ref(self, path):
        return {"path": path.relative_to(self.root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(json.dumps(value).encode())
        return self.ref(path)

    def read(self, path):
        return json.loads(path.read_text())

    def worker_validation(self, spec):
        messages = spec["body"]["messages"]
        initial, final = audit.strict(messages[1]["content"]), audit.strict(messages[-1]["content"])
        return {"status": "validated", "case_id": spec["case_id"], "stage": spec["stage"],
                "expected_source_packet": final.get("institution_document"),
                "visible_evidence_ids": sorted(audit.visible_ids(initial) | audit.visible_ids(final))}

    def output(self):
        return {"source_id": None, "sectors": [{"sector_code": code, "weight": .08,
                "source_label": None, "source_stance": "not_available", "source_reading": "No source available.",
                "source_evidence_ids": [], "decision_reason": "Use supplied market facts.", "decision_evidence_ids": ["M:a:10"]}
                for code in audit.CODES]}

    def stage(self, stage="D0", raw=None, status="completed", integrity=True, prior=None, case=None):
        case = case or self.case
        folder = self.run / (case + "__" + stage)
        raw = json.dumps(self.output()) if raw is None else raw
        response = {"done": True, "done_reason": "stop", "message": {"content": raw}}
        response_ref = self.write(folder / "http_0001_generation/response.json", response)
        messages = copy.deepcopy(self.messages[case])
        spec = {"case_id": case, "stage": stage, "run_directory": str(self.run), "body": {"messages": messages},
                "runtime": self.runtime, "origin": self.origin, "review_gate": self.gate_ref}
        if stage == "F0":
            draft = self.read(prior / "http_0001_generation/response.json")["message"]["content"]
            final = {"institution_document": None if case.endswith("__C") else self.packet,
                     "actual_draft_calculator_feedback": {"evidence_id": "DRAFT:sum", "sum": .88}}
            messages.extend([{"role": "assistant", "content": draft}, {"role": "user", "content": json.dumps(final)}])
            spec.update(raw_draft=draft, draft_artifacts={key: self.ref(prior / filename) for key, filename in audit.DRAFT_FILES.items()})
        spec_ref = self.write(folder / "worker_spec.json", spec)
        worker = {"status": status, "generation_requests_attempted": 1, "continuation_eligible": status == "completed",
                  "system_integrity_incident": False}
        self.write(folder / "worker_summary.json", worker)
        supervisor = {"status": "worker_exited", "worker_exit_code": 0 if status == "completed" else 1,
                      "generation_requests_attempted": 1, "worker": worker}
        self.write(folder / "supervisor_result.json", supervisor)
        transport = {**worker, "response_artifact": response_ref, "response": response, "supervisor": supervisor}
        transport_ref = self.write(folder / "transport_result.json", transport)
        validation_ref = self.write(folder / "response_contract_validation.json", {"continuation_eligible": status == "completed"})
        self.write(folder / "stage_review.json", {"case_id": case, "stage": stage, "instrument_integrity_pass": integrity,
            "checks": {"response_exactly_bound": True}, "input_refs": [spec_ref, transport_ref, response_ref, validation_ref]})
        return folder

    def change(self, folder, filename, mutate):
        value = self.read(folder / filename); mutate(value)
        ref = self.write(folder / filename, value)
        review = self.read(folder / "stage_review.json")
        review["input_refs"] = [ref if audit.workspace_path(r["path"]) == folder / filename else r for r in review["input_refs"]]
        self.write(folder / "stage_review.json", review)

    def test_raw_budget_error_retained_without_normalization_or_score(self):
        result = audit.prepare(self.stage())
        self.assertEqual(result["raw_sum_exact_decimal"], "0.88")
        self.assertFalse(result["normalization"])
        self.assertEqual(result["coverage"]["semantic_rows_read"], 0)
        self.assertEqual(result["external_allocation_math"], "separate_derived_artifact_not_applied_here")
        self.assertEqual(len(result["sector_rows"]), 11)

    def test_L_D0_and_C_both_stages_source_fidelity_NA(self):
        for case in (audit.CASES[1], audit.CASES[2]):
            draft = self.stage(case=case)
            self.assertEqual(audit.prepare(draft)["source_fidelity_applicability"], "not_applicable_no_source_supplied")
            if case.endswith("__C"):
                final = audit.prepare(self.stage("F0", prior=draft, case=case))
                self.assertEqual(final["source_fidelity_applicability"], "not_applicable_no_source_supplied")

    def test_E_D0_and_L_F0_actual_assigned_UBS_packet(self):
        self.assertEqual(audit.prepare(self.stage(case=audit.CASES[0]))["source_packet"], self.packet)
        draft = self.stage()
        result = audit.prepare(self.stage("F0", prior=draft))
        self.assertEqual(result["source_packet"], self.packet)
        self.assertIsNotNone(result["own_prior_text"])
        self.assertTrue(all(row["own_D0_raw_delta_exact_decimal"] == "0.00" for row in result["sector_rows"]))

    def test_failed_and_bad_instrument_never_read_response(self):
        for kwargs in ({"status": "case_timeout"}, {"integrity": False}):
            folder = self.stage(**kwargs)
            (folder / "http_0001_generation/response.json").unlink()
            self.assertEqual(audit.prepare(folder)["semantic_review_status"], "not_assessed")
        self.validator.assert_not_called()

    def test_missing_stage_review_fails_before_response(self):
        folder = self.stage(); (folder / "stage_review.json").unlink()
        (folder / "http_0001_generation/response.json").unlink()
        with self.assertRaises(FileNotFoundError): audit.prepare(folder)

    def test_malformed_normally_finished_model_text_remains_observation(self):
        result = audit.prepare(self.stage(raw="not JSON", status="model_structure_failure"))
        self.assertEqual(result["raw_final_or_draft_text"], "not JSON")
        self.assertIsNotNone(result["output_json_parse_error"])
        self.assertIsNone(result["raw_sum_exact_decimal"])

    def test_duplicate_nonfinite_and_overflow_raw_diagnostics(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":1e400}'):
            result = audit.prepare(self.stage(raw=raw, status="model_structure_failure"))
            self.assertIsNotNone(result["output_json_parse_error"])
            json.dumps(result, allow_nan=False)

    def test_extreme_negative_exponent_keeps_raw_and_parse_diagnostic(self):
        raw = '{"x":1e-999999999999999999999999999999}'
        result = audit.prepare(self.stage(raw=raw, status="model_structure_failure"))
        self.assertEqual(result["raw_final_or_draft_text"], raw)
        self.assertIsNotNone(result["output_json_parse_error"])
        json.dumps(result, allow_nan=False)

    def test_boolean_weight_not_numeric_negative_weight_not_repaired(self):
        value = self.output(); value["sectors"][0]["weight"] = True
        self.assertIsNotNone(audit.prepare(self.stage(raw=json.dumps(value)))["raw_vector_diagnostic_error"])
        value["sectors"][0]["weight"] = -.08
        result = audit.prepare(self.stage(raw=json.dumps(value)))
        self.assertEqual(result["raw_sum_exact_decimal"], "0.72")
        self.assertEqual(result["sector_rows"][0]["raw_weight_exact_decimal"], "-0.08")

    def test_citation_membership_never_entailment_score(self):
        value = self.output(); value["sectors"][0]["decision_evidence_ids"].append("invented")
        result = audit.prepare(self.stage(raw=json.dumps(value)))
        self.assertEqual(result["unavailable_id_occurrences"][0]["id"], "invented")
        self.assertEqual(result["sector_rows"][0]["semantic_category"], "pending_actual_AI_reading")

    def test_foreign_review_reference_is_not_opened(self):
        folder = self.stage(); review = self.read(folder / "stage_review.json")
        review["input_refs"].append({"path": "active_other_stage/response.json", "sha256": "0" * 64})
        self.write(folder / "stage_review.json", review)
        with self.assertRaisesRegex(ValueError, "Foreign stage review"): audit.prepare(folder)

    def test_completed_contract_eligibility_must_agree(self):
        folder = self.stage()
        self.change(folder, "response_contract_validation.json", lambda value: value.update(continuation_eligible=False))
        with self.assertRaisesRegex(ValueError, "contract eligibility differs"): audit.prepare(folder)

    def test_response_byte_change_rejected(self):
        folder = self.stage(); (folder / "http_0001_generation/response.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "hash mismatch"): audit.prepare(folder)

    def test_required_stage_binding_and_check_values(self):
        folder = self.stage(); review = self.read(folder / "stage_review.json")
        review["input_refs"].pop(); self.write(folder / "stage_review.json", review)
        with self.assertRaisesRegex(ValueError, "binding missing"): audit.prepare(folder)
        folder = self.stage(); review = self.read(folder / "stage_review.json"); review["checks"] = {"x": 1}
        self.write(folder / "stage_review.json", review)
        with self.assertRaisesRegex(ValueError, "passing checks"): audit.prepare(folder)

    def test_worker_mismatch_and_bool_attempt_rejected(self):
        folder = self.stage()
        self.change(folder, "transport_result.json", lambda t: t.update(generation_requests_attempted=True))
        with self.assertRaisesRegex(ValueError, "integer generation"): audit.prepare(folder)
        folder = self.stage(); self.change(folder, "transport_result.json", lambda t: t.update(continuation_eligible=False))
        with self.assertRaisesRegex(ValueError, "outcome mismatch"): audit.prepare(folder)

    def test_extra_generation_directory_rejected(self):
        folder = self.stage(); (folder / "http_0002_generation").mkdir()
        with self.assertRaisesRegex(ValueError, "Unexpected generation"): audit.prepare(folder)

    def test_changed_frozen_code_rejected(self):
        folder = self.stage(); (self.root / "research/sector_completion_runtime.py").write_text("# changed")
        with self.assertRaisesRegex(ValueError, "Frozen code changed"): audit.prepare(folder)

    def test_gate_hash_or_scope_change_rejected(self):
        folder = self.stage(); gate = self.read(self.root / "gate.json"); gate["max_generation_requests"] = 10
        self.write(self.root / "gate.json", gate)
        with self.assertRaisesRegex(ValueError, "hash mismatch"): audit.prepare(folder)

    def test_no_Fidelity_or_wrong_stage_completion_slot(self):
        folder = self.stage(); self.change(folder, "worker_spec.json", lambda s: s.update(case_id="fidelity_q2_2026__L"))
        with self.assertRaisesRegex(ValueError, "identity mismatch"): audit.prepare(folder)

    def test_changed_worker_runtime_rejected(self):
        folder = self.stage(); self.change(folder, "worker_spec.json", lambda s: s.update(runtime={"temperature": 1}))
        with self.assertRaisesRegex(ValueError, "runtime differs"): audit.prepare(folder)

    def test_actual_worker_validator_rejection_propagates(self):
        folder = self.stage(); self.validator.side_effect = ValueError("exact body differs")
        with self.assertRaisesRegex(ValueError, "exact body differs"): audit.prepare(folder)

    def test_F0_own_D0_must_be_completed_and_instrument_bound(self):
        draft = self.stage(integrity=False); final = self.stage("F0", prior=draft)
        with self.assertRaisesRegex(ValueError, "Own D0 instrument guard"): audit.prepare(final)

    def test_F0_requires_all_five_D0_artifacts(self):
        draft = self.stage(); final = self.stage("F0", prior=draft)
        self.change(final, "worker_spec.json", lambda s: s["draft_artifacts"].pop("worker_summary"))
        with self.assertRaisesRegex(ValueError, "five own D0"): audit.prepare(final)

    def test_other_run_or_case_D0_substitution_rejected(self):
        draft = self.stage(); final = self.stage("F0", prior=draft)
        wrong = self.root / "other/response.json"; wrong.parent.mkdir(); wrong.write_bytes((draft / "http_0001_generation/response.json").read_bytes())
        self.change(final, "worker_spec.json", lambda s: s["draft_artifacts"].update(response=self.ref(wrong)))
        with self.assertRaisesRegex(ValueError, "Unexpected bound path"): audit.prepare(final)

    def test_changed_raw_D0_in_messages_rejected(self):
        draft = self.stage(); final = self.stage("F0", prior=draft)
        self.change(final, "worker_spec.json", lambda s: s["body"]["messages"][2].update(content="different"))
        with self.assertRaisesRegex(ValueError, "exact actual own D0"): audit.prepare(final)

    def test_changed_visible_source_or_initial_common_context_rejected(self):
        draft = self.stage(); final = self.stage("F0", prior=draft)
        def mutate(s):
            payload = json.loads(s["body"]["messages"][3]["content"])
            payload["institution_document"]["evidence_table"]["rows"][0][2] = "Different meaning."
            s["body"]["messages"][3]["content"] = json.dumps(payload)
        self.change(final, "worker_spec.json", mutate)
        with self.assertRaisesRegex(ValueError, "frozen packet"): audit.prepare(final)
        folder = self.stage(); self.change(folder, "worker_spec.json", lambda s: s["body"]["messages"][0].update(content="changed"))
        with self.assertRaisesRegex(ValueError, "frozen prepared input"): audit.prepare(folder)

    def test_bound_change_during_preparation_rejected(self):
        folder = self.stage()
        def mutate(spec):
            value = self.worker_validation(spec)
            (self.root / "research/sector_completion_gate.py").write_text("# changed during reading")
            return value
        self.validator.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "changed during preparation"): audit.prepare(folder)

    def test_exclusive_output_and_report_namespace(self):
        folder = self.stage(); output = self.reports / "bundle.json"
        audit.write_new(folder, output); before = output.read_bytes()
        with self.assertRaisesRegex(ValueError, "exclusive"): audit.write_new(folder, output)
        self.assertEqual(output.read_bytes(), before)
        with self.assertRaisesRegex(ValueError, "exclusive"): audit.write_new(folder, self.root / "outside_report.json")


if __name__ == "__main__":
    unittest.main()
