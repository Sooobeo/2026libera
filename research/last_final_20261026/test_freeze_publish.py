"""Tempfile-only freezer/publisher tests: no historical output or service reads."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import unittest
from unittest.mock import patch

import freeze_sector_last_final as f
import publish_last_final_review_ack as p
import run_sector_last_final as c
from test_sector_last_final import scoped


class Publisher(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run, self.reports, self.semantic = (self.root / n for n in ("raw", "reports", "semantic"))
        self.stage = self.run / c.STAGE_ORDER[0]
        self.stage.mkdir(parents=True); self.semantic.mkdir()
        (self.reports / "allocation_math").mkdir(parents=True)
        self.spec = {"case_id": c.CASES[0], "stage": "F0"}
        for name, obj in (("worker_spec.json", self.spec), ("transport_result.json", {}), ("stage_review.json", {})):
            c.write_json(self.stage / name, obj)
        c.write_json(self.reports / "allocation_math" / (self.stage.name + ".json"), {})
        self.review = self.semantic / "full_review.json"
        c.write_json(self.review, {"case_id": c.CASES[0], "stage": "F0", "review_status": "completed",
            "transport_ref": c.ref(self.stage / "transport_result.json"), "negative_findings": ["raw sum differs"],
            "review_axes": {k: {"reviewed": True, "reason": "actual audit completed"} for k in ("errors", "consistency", "paper_topic")}})
        for name, value in (("RUN", self.run), ("REPORTS", self.reports), ("SEMANTIC", self.semantic)):
            context = patch.object(p, name, value); context.start(); self.addCleanup(context.stop)

    def test_real_ACK_validation_atomic_exclusive_and_negative_findings(self):
        result = p.publish(self.stage, self.review)
        self.assertEqual(result["status"], "published")
        self.assertEqual(c.read(self.stage / "external_review_ack.json")["schema_version"], "sector_last_final_stage_external_review_ack_1")
        self.assertEqual(list(self.semantic.glob(".ack_*")), [])
        with self.assertRaises(FileExistsError): p.publish(self.stage, self.review)

    def test_wrong_slot_and_external_review_tree_rejected(self):
        other = self.run / (c.CASES[0] + "__D0"); other.mkdir()
        c.write_json(other / "worker_spec.json", {"case_id": c.CASES[0], "stage": "D0"})
        with self.assertRaises(ValueError): p.publish(other, self.review)
        with self.assertRaises(ValueError): p.publish(self.stage, self.root / "outside.json")
        self.assertFalse((self.stage / "external_review_ack.json").exists())

    def test_incomplete_or_stale_review_cannot_publish(self):
        item = c.read(self.review); item["review_status"] = "pending"
        self.review.write_text(json.dumps(item))
        with self.assertRaises(ValueError): p.publish(self.stage, self.review)
        item["review_status"] = "completed"; self.review.write_text(json.dumps(item))
        (self.stage / "transport_result.json").write_text('{"changed":true}')
        with self.assertRaises(ValueError): p.publish(self.stage, self.review)
        self.assertFalse((self.stage / "external_review_ack.json").exists())


class Freezer(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.folder = self.root / "new"; self.folder.mkdir()
        self.run, self.reports = self.root / "raw", self.folder / "reports"
        for name, value in (("ROOT", self.root), ("FOLDER", self.folder), ("RUN", self.run), ("REPORTS", self.reports),
                            ("SUPPORT_CODE", {"support.py"})):
            self.patch(f, name, value)
        for name in ("old.py", "new.py", "support.py"):
            (self.root / name).write_text("# synthetic\n")
        c.write_json(self.root / "prior_freeze.json", {"code_refs": [self.ref(self.root / "old.py")]})
        for name in f.REVIEW_NAMES:
            c.write_json(self.folder / name, {"status": "PASS", "name": name})
        c.write_json(self.folder / "runtime_candidate.json", {"backend_evidence": [{"new": True}], "option": 1.0})
        (self.root / "CANCEL").write_text("preserved plaintext cancellation")
        c.write_json(self.root / "accepted_math.json", {"status": "PASS"})
        self.protocol = {**scoped(), "status": "approved_design_for_prospective_last_final_freeze",
            "runtime_ref": self.ref(self.folder / "runtime_candidate.json"),
            "last_finalizer_review_ref": self.ref(self.folder / "last_finalizer_review.json"),
            "prior_remaining_cancel_ref": self.ref(self.root / "CANCEL"),
            "finalizer_acceptance_ref": self.ref(self.root / "accepted_math.json"),
            "exact_math_policy_ref": self.ref(self.root / "accepted_math.json"),
            "external_draft_refs": {}, "external_draft_evidence_refs": {}}
        self.save_protocol()
        self.patch(f.validation, "BOUND", ("runtime_ref", "protocol_ref", "last_finalizer_review_ref", "prior_remaining_cancel_ref", "finalizer_acceptance_ref"))
        self.patch(f.validation, "REQUIRED_CODE", {"new.py"})
        self.patch(f.validation, "checked", self.checked)
        self.patch(f.validation, "same_ref", lambda a,b: a == b)
        self.patch(f.validation, "verify_nested_refs", lambda obj: [])
        self.patch(f.validation, "validate_history", lambda obj: (None,None,None,{"freeze_ref": self.ref(self.root / "prior_freeze.json")}))
        self.patch(f.validation, "validated_external_draft", lambda obj: {"old_spec": {"runtime": {"backend_evidence": [{"old": True}], "option": 1.0}}})
        self.patch(f.validation, "validate_runtime", lambda obj: None)
        self.patch(f.validation, "validate_reviews", lambda refs, at: None)
        self.patch(f.validation, "validate_gate", lambda path: {"status": "synthetic_gate_verified", "model_calls": 0})

    def patch(self, obj, name, value):
        context = patch.object(obj, name, value); context.start(); self.addCleanup(context.stop)

    def ref(self, path):
        return {"path": Path(path).relative_to(self.root).as_posix(), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}

    def checked(self, ref, json_object=True):
        path = self.root / ref["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != ref["sha256"]: raise ValueError("stale synthetic ref")
        return c.read(path) if json_object else path

    def save_protocol(self):
        (self.folder / "protocol_and_review.json").write_text(json.dumps(self.protocol))

    def test_plaintext_cancel_old_code_and_all_new_refs_are_bound(self):
        result = f.freeze(); self.assertEqual(result["status"], "synthetic_gate_verified")
        frozen = c.read(self.folder / "freeze.json"); gate = c.read(self.folder / "review_gate.json")
        self.assertEqual(frozen["max_generation_requests"], 1)
        self.assertEqual({r["path"] for r in frozen["code_refs"]}, {"old.py", "new.py", "support.py"})
        self.assertEqual(frozen["prior_remaining_cancel_ref"], self.protocol["prior_remaining_cancel_ref"])
        self.assertEqual(gate["freeze_ref"], self.ref(self.folder / "freeze.json"))
        self.assertEqual(len(frozen["review_refs"]), 5)
        with self.assertRaises(FileExistsError): f.freeze()

    def test_mutated_historical_source_refuses_before_freeze_write(self):
        (self.root / "old.py").write_text("# changed\n")
        with self.assertRaises(ValueError): f.freeze()
        self.assertFalse((self.folder / "freeze.json").exists())

    def test_typed_scientific_option_change_refuses_before_write(self):
        (self.folder / "runtime_candidate.json").write_text('{"backend_evidence":[{"new":true}],"option":1}')
        self.protocol["runtime_ref"] = self.ref(self.folder / "runtime_candidate.json"); self.save_protocol()
        with self.assertRaises(ValueError): f.freeze()
        self.assertFalse((self.folder / "freeze.json").exists())

    def test_missing_review_existing_run_and_candidate_protocol_refused(self):
        (self.folder / f.REVIEW_NAMES[-1]).unlink()
        with self.assertRaises(FileNotFoundError): f.freeze()
        self.run.mkdir()
        with self.assertRaises(FileExistsError): f.freeze()
        self.run.rmdir(); self.protocol["status"] = "candidate"; self.save_protocol()
        with self.assertRaises(ValueError): f.freeze()
        self.assertFalse((self.folder / "freeze.json").exists())


if __name__ == "__main__":
    unittest.main()
