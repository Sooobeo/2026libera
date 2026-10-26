"""Synthetic completed-stage guard checks; real authority delegates are mocked explicitly."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_sector_last_final import scoped

SPEC = importlib.util.spec_from_file_location("last_semantic_test_target", Path(__file__).with_name("prepare_stage_semantic_audit.py"))
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class LastSemantic(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reports = self.root / "research/last_final_20261026"; self.reports.mkdir(parents=True)
        self.run = self.root / "data/local_sector_runtime/v494_last_final_20261026"
        self.oldrun = self.root / "data/local_sector_runtime/v494_remaining_20261026"
        self.case = audit.CASES[0]
        self.runtime, self.origin = {"options": {"temperature": 0}}, "http://127.0.0.1:11435"
        self.patch(audit, "ROOT", self.root); self.patch(audit, "REPORT_ROOT", self.reports)
        for name in ("prepare_stage_semantic_audit.py", "runtime_adapter.py", "parser.py"):
            (self.reports / name).write_text("# synthetic pinned source\n")
        self.patch(audit, "__file__", str(self.reports / "prepare_stage_semantic_audit.py"))
        self.patch(audit, "PARSER_PATH", self.reports / "parser.py")
        self.patch(audit, "RUBRIC_REF", self.write(self.root / "rubric.json", {}))
        self.initial = {"common_context": {"evidence_id": "CTX:task"},
            "common_market": {"sector_codes": list(audit.CODES), "baseline_weights": dict.fromkeys(audit.CODES, .1)},
            "public_numeric_fact_index": {"columns": ["fact_id", "value"], "rows": [["M:a:10", .1]]},
            "institution_document": None}
        self.messages = [{"role": "system", "content": "fixed"}, {"role": "user", "content": json.dumps(self.initial)}]
        prepared = self.write(self.root / "prepared.json", self.messages)
        aggregate = self.write(self.root / "aggregate.json", {"public_source_packets": {}})
        manifest = self.write(self.root / "manifest.json", {"prepared_cases": [{"case_id": self.case, "stage": "D0", **prepared}],
            "inputs": {"public_aggregate_never_sent": aggregate}})
        self.freeze_ref = self.write(self.root / "freeze.json", {"synthetic": "freeze"})
        self.gate_ref = self.write(self.root / "gate.json", {"freeze_ref": self.freeze_ref})
        self.prior = self.stage(self.oldrun, "D0")
        draft_refs = {role: self.ref(self.prior / filename) for role, filename in audit.DRAFT_FILES.items()}
        extras = {role: self.write(self.root / "external_evidence" / (role + ".json"), {"synthetic_role": role})
            for role in audit.adapter.EXTRA_ROLES}
        self.declaration = {**scoped(), "run_directory": str(self.run), "origin": self.origin,
            "runtime": self.runtime, "review_gate": self.gate_ref, "freeze_ref": self.freeze_ref,
            "prepared_manifest_ref": manifest, "external_draft_refs": draft_refs, "external_draft_evidence_refs": extras}
        self.write(self.run / "campaign_declaration.json", self.declaration)
        self.folder = self.stage(self.run, "F0")
        self.gate_validator = self.patch(audit.adapter, "validate_gate", lambda *a, **kw: {})
        self.external_validator = self.patch(audit.adapter, "validated_external_draft", lambda *a, **kw: {})
        self.prior_validator = self.patch(audit.adapter, "validate_prior_draft", lambda *a, **kw: {})
        self.patch(audit.adapter, "verify_nested_refs", lambda obj: [])
        self.worker_validator = self.patch(audit, "validate_worker_spec", self.worker_result)

    def patch(self, obj, name, result):
        context = patch.object(obj, name, side_effect=result) if callable(result) else patch.object(obj, name, result)
        value = context.start(); self.addCleanup(context.stop); return value

    def ref(self, p):
        return {"path": p.relative_to(self.root).as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}

    def write(self, p, obj):
        p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(obj)); return self.ref(p)

    def read(self, p):
        return json.loads(p.read_text())

    def raw(self):
        return json.dumps({"source_id": None, "sectors": [{"sector_code": code, "weight": .08,
            "source_label": None, "source_stance": "not_available", "source_evidence_ids": [],
            "source_reading": "No source", "decision_reason": "Given market evidence", "decision_evidence_ids": ["M:a:10"]}
            for code in audit.CODES]})

    def stage(self, run, stage, *, status="completed", integrity=True, raw=None):
        folder = run / (self.case + "__" + stage)
        response = {"done": True, "done_reason": "stop", "message": {"content": self.raw() if raw is None else raw}}
        response_ref = self.write(folder / "http_0001_generation/response.json", response)
        messages = copy.deepcopy(self.messages)
        spec = {"case_id": self.case, "stage": stage, "run_directory": str(run), "origin": self.origin,
            "runtime": self.runtime, "review_gate": self.gate_ref, "body": {"messages": messages}}
        if stage == "F0":
            draft = self.read(self.prior / "http_0001_generation/response.json")["message"]["content"]
            messages.extend([{"role": "assistant", "content": draft}, {"role": "user", "content": json.dumps({
                "institution_document": None, "actual_draft_calculator_feedback": {"evidence_id": "DRAFT:sum", "sum": .88}})}])
            spec.update(raw_draft=draft, draft_artifacts=copy.deepcopy(self.declaration["external_draft_refs"]))
        sr = self.write(folder / "worker_spec.json", spec)
        worker = {"status": status, "generation_requests_attempted": 1, "continuation_eligible": status == "completed", "system_integrity_incident": False}
        self.write(folder / "worker_summary.json", worker)
        sup = {"status": "worker_exited", "worker_exit_code": 0 if status == "completed" else 1, "generation_requests_attempted": 1, "worker": worker}
        self.write(folder / "supervisor_result.json", sup)
        tr = self.write(folder / "transport_result.json", {**worker, "response": response, "response_artifact": response_ref, "supervisor": sup})
        cr = self.write(folder / "response_contract_validation.json", {"continuation_eligible": status == "completed"})
        self.write(folder / "stage_review.json", {"case_id": self.case, "stage": stage, "instrument_integrity_pass": integrity,
            "checks": {"exact_response": True}, "input_refs": [sr, tr, response_ref, cr]})
        return folder

    def change(self, filename, mutate):
        p = self.folder / filename; obj = self.read(p); mutate(obj); updated = self.write(p, obj)
        review = self.read(self.folder / "stage_review.json")
        review["input_refs"] = [updated if audit.workspace_path(r["path"]) == p else r for r in review["input_refs"]]
        self.write(self.folder / "stage_review.json", review)

    def worker_result(self, spec):
        initial, final = [audit.strict(spec["body"]["messages"][i]["content"]) for i in (1, 3)]
        return {"status": "validated", "case_id": self.case, "stage": "F0", "expected_source_packet": None,
            "visible_evidence_ids": sorted(audit.visible_ids(initial) | audit.visible_ids(final))}

    def test_source_free_external_D0_raw_errors_preserved_and_pending(self):
        result = audit.prepare(self.folder)
        self.assertEqual(result["own_D0_origin"], "fixed_previous_remaining_segment")
        self.assertEqual(result["own_D0_stage_directory"], self.prior.relative_to(self.root).as_posix())
        self.assertIsNone(result["source_packet"])
        self.assertEqual(result["source_fidelity_applicability"], "not_applicable_no_source_supplied")
        self.assertEqual(result["raw_sum_exact_decimal"], "0.88")
        self.assertEqual(len(result["sector_rows"]), 11)
        self.assertEqual(result["coverage"]["semantic_rows_read"], 0)
        self.assertFalse(result["normalization"])
        self.gate_validator.assert_called_once(); self.external_validator.assert_called_once(); self.prior_validator.assert_called_once()
        self.assertFalse((self.run / (self.case + "__D0")).exists())

    def test_partial_and_bad_instrument_never_read_responses_or_authority(self):
        for kwargs in ({"status": "case_timeout"}, {"integrity": False}):
            self.stage(self.run, "F0", **kwargs)
            (self.folder / "http_0001_generation/response.json").unlink()
            with patch.object(audit, "read_bound", side_effect=AssertionError("must not read responses")):
                self.assertEqual(audit.prepare(self.folder)["status"], "unavailable_for_completed_output_review")
        self.gate_validator.assert_not_called(); self.external_validator.assert_not_called()

    def test_missing_review_precedes_response_and_authority(self):
        (self.folder / "stage_review.json").unlink()
        (self.folder / "http_0001_generation/response.json").unlink()
        with self.assertRaises(FileNotFoundError): audit.prepare(self.folder)
        self.gate_validator.assert_not_called()

    def test_stale_current_response_and_foreign_stage_ref_refused(self):
        (self.folder / "http_0001_generation/response.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "hash mismatch"): audit.prepare(self.folder)
        self.stage(self.run, "F0")
        review = self.read(self.folder / "stage_review.json")
        review["input_refs"].append({"path": "foreign/response.json", "sha256": "0"*64})
        self.write(self.folder / "stage_review.json", review)
        with self.assertRaisesRegex(ValueError, "Foreign stage"): audit.prepare(self.folder)

    def test_stale_external_evidence_and_old_ACK_backfill_rejected(self):
        p = self.root / self.declaration["external_draft_evidence_refs"]["semantic_review"]["path"]
        before = p.read_bytes(); p.write_text("{}")
        with self.assertRaisesRegex(ValueError, "hash mismatch"): audit.prepare(self.folder)
        p.write_bytes(before); self.write(self.prior / "external_review_ack.json", {})
        with self.assertRaisesRegex(ValueError, "ACK absence"): audit.prepare(self.folder)

    def test_bound_current_gate_and_validator_rejections_propagate(self):
        self.gate_validator.side_effect = ValueError("authority rejected")
        with self.assertRaisesRegex(ValueError, "authority rejected"): audit.prepare(self.folder)
        self.gate_validator.side_effect = lambda *a, **kw: {}
        self.worker_validator.side_effect = ValueError("worker rejected")
        with self.assertRaisesRegex(ValueError, "worker rejected"): audit.prepare(self.folder)
        self.worker_validator.side_effect = self.worker_result
        self.change("worker_spec.json", lambda s: s.update(review_gate={"path": "other.json", "sha256": "0"*64}))
        with self.assertRaisesRegex(ValueError, "binding differs"): audit.prepare(self.folder)

    def test_own_history_and_old_D0_same_bytes_wrong_path_rejected(self):
        self.change("worker_spec.json", lambda s: s.update(raw_draft="changed"))
        with self.assertRaisesRegex(ValueError, "exact actual own D0"): audit.prepare(self.folder)
        self.stage(self.run, "F0")
        other = self.root / "other.json"; other.write_bytes((self.prior / "http_0001_generation/response.json").read_bytes())
        self.change("worker_spec.json", lambda s: s["draft_artifacts"].update(response=self.ref(other)))
        with self.assertRaisesRegex(ValueError, "Unexpected bound path"): audit.prepare(self.folder)

    def test_source_packet_cannot_appear_in_source_free_control(self):
        def alter(spec):
            obj = json.loads(spec["body"]["messages"][3]["content"]); obj["institution_document"] = {"source_id": "unwanted"}
            spec["body"]["messages"][3]["content"] = json.dumps(obj)
        self.change("worker_spec.json", alter)
        with self.assertRaisesRegex(ValueError, "Source visibility"): audit.prepare(self.folder)

    def test_only_final_slot_and_typed_scope(self):
        self.change("worker_spec.json", lambda s: s.update(stage="D0"))
        with self.assertRaisesRegex(ValueError, "identity mismatch"): audit.prepare(self.folder)
        self.declaration["max_generation_requests"] = True
        self.write(self.run / "campaign_declaration.json", self.declaration)
        with self.assertRaisesRegex(ValueError, "scope differs"): audit.prepare(self.folder)

    def test_malformed_completed_model_text_retained_without_score(self):
        self.stage(self.run, "F0", status="model_structure_failure", raw="{not JSON")
        result = audit.prepare(self.folder)
        self.assertEqual(result["raw_final_or_draft_text"], "{not JSON")
        self.assertIsNotNone(result["output_json_parse_error"])
        self.assertFalse(result["coverage"]["semantic_scores_generated"])

    def test_exclusive_output_and_source_tree_unmodified(self):
        before = {str(p): p.read_bytes() for tree in (self.run, self.oldrun) for p in tree.rglob("*") if p.is_file()}
        out = self.reports / "bundle.json"; audit.write_new(self.folder, out)
        self.assertEqual(before, {str(p): p.read_bytes() for tree in (self.run, self.oldrun) for p in tree.rglob("*") if p.is_file()})
        with self.assertRaisesRegex(ValueError, "exclusive"): audit.write_new(self.folder, out)
        with self.assertRaisesRegex(ValueError, "exclusive"): audit.write_new(self.folder, self.run / "bundle.json")


if __name__ == "__main__": unittest.main(verbosity=2)
