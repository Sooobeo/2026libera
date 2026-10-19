"""Temporary synthetic AI-review fixtures only; no real review is claimed."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sector_v492_review_gate as gate


class ReviewGateTests(unittest.TestCase):
    def setUp(self):
        (gate.paths.ROOT / "tmp").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="v492_review_gate_synthetic_", dir=gate.paths.ROOT / "tmp")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.code = self.root / "synthetic_code.py"
        self.code.write_text("# SYNTHETIC FIXTURE ONLY\n", encoding="utf-8")
        self.code_rel = self.code.relative_to(gate.paths.ROOT).as_posix()
        code_patch = patch.object(gate, "REQUIRED_CODE_PATHS", {self.code_rel})
        code_patch.start()
        self.addCleanup(code_patch.stop)
        self.instruction = {"exact_text": "걍 다 너한테 맞길게 평가규칙 저거 아님",
                            "timestamp_kind": "recorded_after_user_message", "recorded_at_utc": "2026-10-18T00:00:00Z",
                            "scope": "SYNTHETIC UNIT TEST ONLY; not an actual authorization record."}
        self.runtime = {"protocol_version": "4.9.2", "backend": "cpu", "pilot_order": gate.CASE_ORDER,
                        "options": {"num_thread": 8, "num_ctx": 65536, "num_predict": 8192, "num_gpu": 0},
                        "deadline_seconds": 4500, "pilot_max_generation_requests": 10, "main_allowed": False}
        self.source = {"protocol_version": "4.9.2", "review_mode": "AI_delegated_by_user",
            "status": "completed_ai_preoutput_source_review", "independent_human_review_completed": False,
            "reviewed_before_research_outputs": True, "research_generation_calls_observed": 0,
            "material_changes_required": False, "completed_at_utc": "2026-10-18T00:01:00Z",
            "input_refs": [self.ref(self.code)], "pilot_source_reviews": [], "pilot_source_comparisons": [], "unresolved": []}
        for sid in ("fidelity_q2_2026", "ubs_june_2026"):
            for code in gate.SECTOR_CODES:
                self.source["pilot_source_reviews"].append({"source_id": sid, "sector_code": code,
                    "original_rating": "SYNTHETIC", "interpretation": "SYNTHETIC UNIT TEST ONLY",
                    "source_packet_evidence_id": sid + ":sector:" + code,
                    "original_evidence": {"page": 1, "evidence_id": sid + ":sector:" + code,
                        "rating_visual_locator": "SYNTHETIC", "rationale_paraphrase": "SYNTHETIC"},
                    "paraphrase_assessment": {"status": "SYNTHETIC", "reason": "SYNTHETIC"}})
        for code in gate.SECTOR_CODES:
            self.source["pilot_source_comparisons"].append({"sector_code": code, "decision": "uncertain",
                "evidence_and_reason": "SYNTHETIC UNIT TEST ONLY", "scope_limit": "No actual source review performed"})
        prompt_ref = self.save("prompt.json", {"protocol_version": "4.9.2", "F0_instruction": "SYNTHETIC conditional final instruction"})
        prepared = []
        for index, case_id in enumerate(gate.CASE_ORDER):
            item = self.save("draft_" + str(index) + ".json", {"synthetic": True})
            prepared.append({"case_id": case_id, **item})
        self.objects = {"input_protocol_ref": {"protocol_version": "4.9.1"},
                        "evaluation_protocol_ref": {"protocol_version": "4.9.2"},
                        "source_review_ref": self.source, "method_review_ref": {"status": "PASS", "synthetic": True},
                        "runtime_ref": self.runtime,
                        "prepared_manifest_ref": {"protocol_version": "4.9.2", "model_calls": 0,
                            "prepared_cases": prepared, "inputs": {"prompt_contract": prompt_ref}}}
        self.refs = {"prompt_contract_ref": prompt_ref}
        self.freeze = {"freeze_version": "v492_pilot_preoutput_freeze_1", "protocol_version": "4.9.2",
            "status": "frozen_for_pilot_only", "purpose": "pilot_only", "user_instruction": self.instruction,
            "case_order": gate.CASE_ORDER, "controls": gate.CONTROLS, "code_refs": [self.ref(self.code)],
            "recorded_at_utc": "2026-10-18T00:02:00Z"}
        self.receipt = {"receipt_version": "v492_ai_preoutput_gate_1", "status": "approved_for_pilot_before_generation",
            "review_mode": "AI_delegated_by_user", "main_allowed": False, "pilot_cases": gate.CASE_ORDER,
            "user_instruction": self.instruction, "recorded_at_utc": "2026-10-18T00:03:00Z",
            "review": {"reviewer": "Codex", "source_meaning_checked": True, "topic_alignment_checked": True,
                       "limitations": ["SYNTHETIC FIXTURE ONLY; no actual review performed"],
                       "completed_at_utc": "2026-10-18T00:01:30Z"}}

    def ref(self, path):
        return {"path": Path(path).relative_to(gate.paths.ROOT).as_posix(), "sha256": gate.remote.sha(path)}

    def save(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return self.ref(path)

    def write(self):
        for name, value in self.objects.items():
            self.refs[name] = self.save(name + ".json", value)
        self.freeze.update(self.refs)
        self.receipt.update(self.refs)
        self.receipt["freeze_ref"] = self.save("freeze.json", self.freeze)
        self.save("gate.json", self.receipt)
        return self.root / "gate.json"

    def test_synthetic_complete_AI_review_requires_no_human_signatures(self):
        result = gate.validate_review_gate(self.write(), runtime=self.runtime)
        self.assertFalse(result["independent_human_review_completed"])
        self.assertEqual(result["status"], "delegated_AI_review_and_preoutput_freeze_verified")

    def test_missing_source_review_row_denies(self):
        self.source["pilot_source_reviews"].pop()
        with self.assertRaisesRegex(ValueError, "22 source-sector"):
            gate.validate_review_gate(self.write())

    def test_source_review_without_original_locator_denies(self):
        self.source["pilot_source_reviews"][0]["original_evidence"]["rating_visual_locator"] = ""
        with self.assertRaisesRegex(ValueError, "original locator"):
            gate.validate_review_gate(self.write())

    def test_fake_human_completion_claim_denies(self):
        self.source["independent_human_review_completed"] = True
        with self.assertRaisesRegex(ValueError, "completed AI source review"):
            gate.validate_review_gate(self.write())

    def test_pending_material_revision_denies(self):
        self.source["material_changes_required"] = True
        with self.assertRaisesRegex(ValueError, "material revision"):
            gate.validate_review_gate(self.write())

    def test_source_review_after_freeze_denies(self):
        self.source["completed_at_utc"] = "2026-10-18T00:02:30Z"
        with self.assertRaisesRegex(ValueError, "source review must precede freeze"):
            gate.validate_review_gate(self.write())

    def test_changed_evaluation_after_freeze_denies(self):
        path = self.write()
        evaluation = gate.paths.workspace_path(self.refs["evaluation_protocol_ref"]["path"])
        evaluation.write_bytes(evaluation.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "artifact changed"):
            gate.validate_review_gate(path)

    def test_changed_code_after_freeze_denies(self):
        path = self.write()
        self.code.write_bytes(self.code.read_bytes() + b"# changed\n")
        with self.assertRaisesRegex(ValueError, "artifact changed"):
            gate.validate_review_gate(path)

    def test_original_user_instruction_provenance_required(self):
        self.instruction["timestamp_kind"] = "invented_exact_message_arrival_time"
        with self.assertRaisesRegex(ValueError, "honest record-time provenance"):
            gate.validate_review_gate(self.write())

    def test_main_cannot_be_enabled(self):
        self.receipt["main_allowed"] = True
        with self.assertRaisesRegex(ValueError, "five pilot cases only"):
            gate.validate_review_gate(self.write())

    def test_control_case_cannot_be_removed(self):
        self.receipt["pilot_cases"] = gate.CASE_ORDER[:-1]
        with self.assertRaisesRegex(ValueError, "five pilot cases only"):
            gate.validate_review_gate(self.write())

    def test_frozen_runtime_must_match_controls(self):
        self.runtime["options"]["num_predict"] = 32
        with self.assertRaisesRegex(ValueError, "runtime does not implement"):
            gate.validate_review_gate(self.write())

    def test_worker_requires_coordinator_declaration_after_freeze(self):
        path = self.write()
        result = gate.validate_review_gate(path, runtime=self.runtime)
        run = self.root / "run"
        run.mkdir()
        declaration = {"review_gate": result["gate_ref"], "case_order": gate.CASE_ORDER,
                       "runtime": self.runtime, "created_at_utc": "2026-10-18T00:04:00Z"}
        (run / "pilot_declaration.json").write_text(json.dumps(declaration), encoding="utf-8")
        (run / "execution_started.json").write_text('{"at_utc":"2026-10-18T00:05:00Z"}', encoding="utf-8")
        gate.validate_review_gate(path, runtime=self.runtime, run_directory=run)
        (run / "execution_started.json").write_text('{"at_utc":"2026-10-18T00:01:00Z"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must precede coordinator execution"):
            gate.validate_review_gate(path, runtime=self.runtime, run_directory=run)


if __name__ == "__main__":
    unittest.main()
