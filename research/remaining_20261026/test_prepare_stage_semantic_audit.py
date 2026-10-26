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

SPEC = importlib.util.spec_from_file_location("remaining_audit", Path(__file__).with_name("prepare_stage_semantic_audit.py"))
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class RemainingBundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run = self.root / "data/local_sector_runtime/v494_remaining_20261026"
        self.run.mkdir(parents=True)
        self.reports = self.root / "research/remaining_20261026"
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
        self.scope = {"purpose": "pilot_completion_resume", "case_order": list(audit.CASES),
            "stage_order": list(audit.STAGE_ORDER), "power_policy": {"fixture_battery_guard": True},
            "max_generation_requests": 5, "historical_generation_requests": 6, "campaign_max_generation_requests": 11,
            "automatic_retries": 0, "main_model_calls": 0, "main_allowed": False, "old_outputs_observed": True,
            "analysis_role": "primary_exploratory", "excluded_new_main_execution": True,
            "explicit_retry_slots": [], "historical_explicit_retry_slots": ["fidelity_q2_2026__L__D0"],
            "run_directory": str(self.run), "runtime_ref": self.write(self.root / "runtime.json", self.runtime),
            "protocol_ref": self.write(self.root / "protocol.json", {"fixture": "protocol"}),
            "prepared_manifest_ref": self.manifest}
        self.make_external()
        code_refs = []
        for name in sorted(audit.CODE_PATHS):
            path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("# synthetic pinned code\n")
            code_refs.append(self.ref(path))
        self.frozen = {**self.scope, "freeze_version": "sector_remaining_freeze_1",
                       "status": "frozen_for_pilot_remaining_only", "code_refs": code_refs}
        self.freeze_ref = self.write(self.root / "freeze.json", self.frozen)
        self.gate = {**self.scope, "receipt_version": "sector_remaining_gate_1",
                     "status": "approved_for_remaining_before_generation", "freeze_ref": self.freeze_ref}
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

    def make_external(self):
        self.oldrun = self.root / "data/local_sector_runtime/v494_completion_20261026"
        self.oldreports = self.root / "research/completion_20261026/run_reports"
        self.oldsemantic = self.oldreports.parent / "semantic/review.json"
        old_gate = self.write(self.root / "old_gate.json", {"fixture": "old approved gate"})
        new_run = self.run
        self.run, self.gate_ref = self.oldrun, old_gate
        self.external_dir = self.stage(case=audit.EXTERNAL_CASE)
        self.run = new_run
        old_decl = self.write(self.oldrun / "campaign_declaration.json", {"purpose": "pilot_completion",
            "run_directory": str(self.oldrun), "output_root": str(self.oldreports), "review_gate": old_gate})
        old_summary = self.write(self.oldrun / "campaign_summary.json", {"purpose": "pilot_completion", "status": "stopped",
            "case_order": list(audit.CASES), "generation_requests_attempted": 1,
            "cases": [{"case_id": case, "stages": [{"stage": "D0", "status": "completed", "generation_requests_attempted": 1}]
                      if case == audit.EXTERNAL_CASE else []} for case in audit.CASES]})
        old_terminal = self.write(self.oldreports / "terminal_receipt.json", {"purpose": "pilot_completion",
            "status": "stopped_semantic_review_pending", "generation_requests_attempted": 1,
            "summary_ref": old_summary, "declaration_ref": old_decl})
        draft_refs = {key: self.ref(self.external_dir / name) for key, name in audit.DRAFT_FILES.items()}
        old_math = self.write(self.oldreports / "allocation_math" / (audit.EXTERNAL_CASE + "__D0.json"),
            {"case_id": audit.EXTERNAL_CASE, "stage": "D0", "observed_transport_status": "completed",
             "status": "finalized", "raw_sum_exact_decimal": "0.88"})
        axes = {a: {"reviewed": True, "reason": "Adverse arithmetic and source findings retained"}
                for a in ("errors", "consistency", "paper_topic")}
        semantic_ref = self.write(self.oldsemantic, {"review_status": "completed", "case_id": audit.EXTERNAL_CASE,
            "stage": "D0", "transport_ref": draft_refs["transport_result"], "review_axes": axes,
            "findings": [{"status": "contradicted", "reason": "Invalid raw budget retained"}]})
        stage_review = self.ref(self.external_dir / "stage_review.json")
        ack = self.write(self.external_dir / "external_review_ack.json", {
            "schema_version": "sector_completion_stage_external_review_ack_1", "status": "completed",
            "case_id": audit.EXTERNAL_CASE, "stage": "D0", "raw_model_content_modified": False, "model_calls": 0,
            "worker_spec_ref": draft_refs["worker_spec"], "transport_ref": draft_refs["transport_result"],
            "stage_review_ref": stage_review, "allocation_math_ref": old_math,
            "semantic_review_ref": semantic_ref, "review_axes": axes})
        raw = self.read(self.external_dir / "http_0001_generation/response.json")["message"]["content"]
        messages = copy.deepcopy(self.messages[audit.EXTERNAL_CASE])
        messages.extend([{"role": "assistant", "content": raw}, {"role": "user", "content": json.dumps({
            "institution_document": self.packet, "actual_draft_calculator_feedback": {"evidence_id": "DRAFT:sum", "sum": .88}})}])
        final_ref = self.write(self.oldrun / (audit.EXTERNAL_CASE + "__final_construction.json"), {"ready": True, "messages": messages})
        self.scope.update(prior_completion_gate_ref=old_gate, prior_completion_terminal_ref=old_terminal,
            prior_completion_summary_ref=old_summary, prior_completion_declaration_ref=old_decl,
            external_draft_refs=draft_refs, external_draft_evidence_refs={"stage_review": stage_review,
                "allocation_math": old_math, "semantic_review": semantic_ref, "external_review_ack": ack,
                "terminal": old_terminal, "summary": old_summary, "declaration": old_decl, "final_construction": final_ref})

    def sync_authority(self, folder=None):
        self.frozen.update(self.scope)
        self.freeze_ref = self.write(self.root / "freeze.json", self.frozen)
        self.gate.update(self.scope); self.gate["freeze_ref"] = self.freeze_ref
        self.gate_ref = self.write(self.root / "gate.json", self.gate)
        self.declaration.update(self.scope)
        self.declaration.update(review_gate=self.gate_ref, freeze_ref=self.freeze_ref)
        self.write(self.run / "campaign_declaration.json", self.declaration)
        if folder:
            self.change(folder, "worker_spec.json", lambda spec: spec.update(review_gate=self.gate_ref,
                draft_artifacts=copy.deepcopy(self.scope["external_draft_refs"])))

    def external_change(self, role, mutate, folder):
        reference = self.scope["external_draft_evidence_refs"][role]
        path = self.root / reference["path"]
        value = self.read(path); mutate(value)
        reference = self.write(path, value)
        self.scope["external_draft_evidence_refs"][role] = reference
        field = {"terminal": "prior_completion_terminal_ref", "summary": "prior_completion_summary_ref",
                 "declaration": "prior_completion_declaration_ref"}.get(role)
        if field: self.scope[field] = reference
        self.sync_authority(folder)

    def external_final(self):
        return self.stage("F0", prior=self.external_dir, case=audit.EXTERNAL_CASE)

    def test_fixed_reviewed_external_D0_is_retained_without_new_D0(self):
        result = audit.prepare(self.external_final())
        self.assertEqual(result["purpose"], "pilot_completion_resume")
        self.assertEqual(result["version"], "remaining_semantic_bundle_1")
        self.assertEqual(result["own_D0_origin"], "fixed_previous_completion_segment")
        self.assertEqual(result["own_D0_stage_directory"], self.external_dir.relative_to(self.root).as_posix())
        self.assertEqual(result["own_prior_text"], result["raw_final_or_draft_text"])
        self.assertEqual(result["raw_sum_exact_decimal"], "0.88")
        self.assertFalse((self.run / (audit.EXTERNAL_CASE + "__D0")).exists())
        self.assertFalse(result["normalization"])

    def test_L_and_C_use_only_same_run_D0_with_source_timing(self):
        for case in audit.CASES[1:]:
            draft = self.stage(case=case)
            self.assertEqual(audit.prepare(draft)["source_fidelity_applicability"], "not_applicable_no_source_supplied")
            result = audit.prepare(self.stage("F0", prior=draft, case=case))
            self.assertEqual(result["own_D0_origin"], "same_remaining_run")
            self.assertEqual(result["source_packet"], None if case.endswith("__C") else self.packet)

    def test_previously_completed_E_D0_is_not_a_remaining_slot(self):
        folder = self.stage(case=audit.EXTERNAL_CASE)
        with self.assertRaisesRegex(ValueError, "identity mismatch"): audit.prepare(folder)

    def test_failed_current_F0_never_opens_current_or_external_response(self):
        folder = self.stage("F0", prior=self.external_dir, case=audit.EXTERNAL_CASE, status="case_timeout")
        (folder / "http_0001_generation/response.json").unlink()
        (self.external_dir / "http_0001_generation/response.json").unlink()
        result = audit.prepare(folder)
        self.assertEqual(result["semantic_review_status"], "not_assessed")
        self.validator.assert_not_called()

    def test_bad_current_instrument_guard_does_not_open_response(self):
        folder = self.stage(integrity=False)
        (folder / "http_0001_generation/response.json").unlink()
        self.assertEqual(audit.prepare(folder)["semantic_review_status"], "not_assessed")

    def test_external_draft_hash_change_rejected(self):
        folder = self.external_final()
        (self.external_dir / "http_0001_generation/response.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "hash mismatch"): audit.prepare(folder)

    def test_other_old_run_same_bytes_cannot_replace_fixed_external_D0(self):
        folder = self.external_final()
        wrong = self.root / "other/response.json"; wrong.parent.mkdir()
        wrong.write_bytes((self.external_dir / "http_0001_generation/response.json").read_bytes())
        self.scope["external_draft_refs"]["response"] = self.ref(wrong)
        self.sync_authority(folder)
        with self.assertRaisesRegex(ValueError, "External draft path differs"): audit.prepare(folder)

    def test_incomplete_external_D0_rejected_before_response_read(self):
        folder = self.external_final()
        path = self.external_dir / "transport_result.json"
        value = self.read(path); value["status"] = "case_timeout"
        self.scope["external_draft_refs"]["transport_result"] = self.write(path, value)
        self.sync_authority(folder)
        (self.external_dir / "http_0001_generation/response.json").unlink()
        with self.assertRaisesRegex(ValueError, "normally completed"): audit.prepare(folder)

    def test_pending_external_semantic_review_rejected(self):
        folder = self.external_final()
        self.external_change("semantic_review", lambda r: r.update(review_status="pending"), folder)
        with self.assertRaisesRegex(ValueError, "semantic review must be complete"): audit.prepare(folder)

    def test_external_ACK_must_bind_exact_review_and_math(self):
        folder = self.external_final()
        self.external_change("external_review_ack", lambda r: r.update(allocation_math_ref={"path": "other.json", "sha256": "0"*64}), folder)
        with self.assertRaisesRegex(ValueError, "ACK binding differs"): audit.prepare(folder)

    def test_external_review_axis_completed_not_correctness_required(self):
        result = audit.prepare(self.external_final())
        self.assertEqual(result["semantic_review_status"], "pending_actual_AI_reading")
        self.assertEqual(self.read(self.oldsemantic)["findings"][0]["status"], "contradicted")
        folder = self.external_final()
        self.external_change("semantic_review", lambda r: r["review_axes"]["errors"].update(reviewed=False), folder)
        self.external_change("external_review_ack", lambda r: r.update(semantic_review_ref=self.scope["external_draft_evidence_refs"]["semantic_review"]), folder)
        with self.assertRaisesRegex(ValueError, "review axes must be complete"): audit.prepare(folder)

    def test_saved_final_construction_must_equal_actual_F0_history(self):
        folder = self.external_final()
        self.external_change("final_construction", lambda r: r["messages"][2].update(content="substituted draft"), folder)
        with self.assertRaisesRegex(ValueError, "saved final construction"): audit.prepare(folder)

    def test_prior_terminal_count_and_full_remaining_inventory_are_bound(self):
        folder = self.external_final()
        self.external_change("terminal", lambda r: r.update(generation_requests_attempted=True), folder)
        with self.assertRaisesRegex(ValueError, "one historical completion request"): audit.prepare(folder)

    def test_exact_external_groups_required(self):
        folder = self.external_final()
        self.scope["external_draft_evidence_refs"].pop("final_construction")
        self.sync_authority(folder)
        with self.assertRaisesRegex(ValueError, "five artifacts and eight"): audit.prepare(folder)

    def test_L_F0_cannot_substitute_external_E_D0(self):
        draft = self.stage(); folder = self.stage("F0", prior=draft)
        self.change(folder, "worker_spec.json", lambda s: s.update(draft_artifacts=self.scope["external_draft_refs"]))
        with self.assertRaisesRegex(ValueError, "Unexpected bound path"): audit.prepare(folder)

    def test_stage_order_and_integer_accounting_cannot_expand(self):
        for key, value in (("stage_order", [audit.EXTERNAL_CASE + "__D0", *audit.STAGE_ORDER]),
                           ("max_generation_requests", 6), ("historical_generation_requests", True)):
            original = copy.deepcopy(self.declaration)
            self.declaration[key] = value
            self.write(self.run / "campaign_declaration.json", self.declaration)
            folder = self.stage()
            with self.assertRaises(ValueError): audit.prepare(folder)
            self.declaration = original
            self.write(self.run / "campaign_declaration.json", original)

    def test_current_code_runtime_and_validator_changes_are_not_ignored(self):
        folder = self.stage()
        self.validator.side_effect = ValueError("wrong frozen body")
        with self.assertRaisesRegex(ValueError, "wrong frozen body"): audit.prepare(folder)
        self.validator.side_effect = self.worker_validation
        (self.root / "research/sector_remaining_runtime.py").write_text("# changed")
        with self.assertRaisesRegex(ValueError, "Frozen code changed"): audit.prepare(folder)

    def test_nonfatal_raw_numeric_citation_errors_and_exclusive_output(self):
        value = self.output(); value["sectors"][0]["decision_evidence_ids"].append("unknown")
        folder = self.stage(raw=json.dumps(value)); output = self.reports / "bundle.json"
        result = audit.write_new(folder, output)
        self.assertEqual(result["raw_sum_exact_decimal"], "0.88")
        self.assertEqual(result["unavailable_id_occurrences"][0]["id"], "unknown")
        before = output.read_bytes()
        with self.assertRaisesRegex(ValueError, "exclusive"): audit.write_new(folder, output)
        self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
