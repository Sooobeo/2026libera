"""Offline adversarial pilot coordinator checks; all transports are synthetic."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import sector_v492_runtime as runtime
import sector_v492_contract as contract


def response_for(spec, *, broken_sum=False, invented_citation=False):
    """Synthetic output for instrument checks, never a research response."""
    checked = runtime.validate_spec(spec)
    packet = checked["expected_source_packet"]
    evidence = sorted(contract.evidence_ids(packet)) if packet else []
    obj = {"source_id": packet["source_id"] if packet else None,
           "sectors": [{"sector_code": code, "source_label": packet["rating_vocabulary"][0] if packet else None,
                        "source_reading": "Synthetic fixture only.", "source_evidence_ids": evidence[:1],
                        "source_stance": "adopt" if packet else "not_available",
                        "weight": 0.1 if broken_sum else 1 / 11,
                        "decision_reason": "Synthetic fixture only.",
                        "decision_evidence_ids": ["invented:not-visible"] if invented_citation else ["CTX:task"]}
                       for code in contract.SECTOR_CODES],
           "context_assessment": {"market_and_mandate_reading": "Synthetic fixture only.",
                                  "allocation_implication": "Synthetic fixture only.",
                                  "evidence_ids": ["CTX:task"], "limitations": "Synthetic fixture only."},
           "alternatives": "Synthetic fixture only.", "risk_discussion": "Synthetic fixture only.",
           "unresolved": [], "submitted_constraints": []}
    return " \n" + json.dumps(obj, ensure_ascii=False) + "\t\r\n"


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        (runtime.ROOT / "tmp").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="v492_runtime_test_", dir=runtime.ROOT / "tmp")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = "http://127.0.0.1:11435"
        evidence = [
            ("cpu_service", {"status": "ready", "version": runtime.base.ENGINE,
                "require_request_num_gpu_zero": True, "origin": source,
                "child_environment": {"OLLAMA_VULKAN": "0", "OLLAMA_IGPU_ENABLE": "0"}}),
            ("smoke_spec", {"origin": source, "body": {"model": runtime.base.MODEL,
                "options": {"num_gpu": 0, "num_ctx": 65536, "num_thread": 8}}}),
            ("smoke_result", {"status": "completed", "response_model": runtime.base.MODEL,
                "assessment_scope": "not_graded_engineering_feasibility"})]
        refs = []
        for role, value in evidence:
            path = self.root / (role + ".json")
            path.write_text(json.dumps(value), encoding="utf-8")
            refs.append({"role": role, "path": str(path), "sha256": runtime.remote.sha(path)})
        self.config = runtime.candidate_runtime(backend="cpu", num_ctx=65536,
            tokenizer_config={"library_dir": "synthetic_not_loaded", "gguf_path": "synthetic_not_loaded"},
            backend_evidence=refs)
        self.config_path = self.root / "runtime.json"
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")
        self.log = self.root / "server.log"
        self.log.write_text("synthetic test only", encoding="utf-8")
        self.bundle, self.cases = runtime.load_bundle()
        self.gate_path = self.root / "synthetic_gate_fixture.json"
        self.gate_path.write_text('{"test_fixture_only":true}', encoding="utf-8")
        self.gate_ref = {"path": str(self.gate_path), "sha256": runtime.remote.sha(self.gate_path)}
        gate_mock = patch.object(runtime, "validate_review_gate", return_value={"gate_ref": self.gate_ref})
        self.gate_mock = gate_mock.start()
        self.addCleanup(gate_mock.stop)

    def declaration(self):
        target = self.root / "pilot"
        runtime.prepare_pilot(self.config_path, target, "http://127.0.0.1:11435", self.log, self.gate_path)
        return target

    def spec(self, case_index=0):
        case = self.cases[case_index]
        return {"origin": "http://127.0.0.1:11435", "runtime": self.config, "case_id": case["case_id"],
                "stage": "D0", "raw_draft": None, "deadline_seconds": 4500,
                "run_directory": str(self.root),
                "review_gate": self.gate_ref,
                "cancel_path": str(self.root / "CANCEL"),
                "body": runtime.request_body(self.config, case["messages"], self.bundle["response_schema"])}

    def transport(self, calls, *, broken_sum=False, invented_citation=False, fail_at=None, incident=False):
        def run(**kwargs):
            spec = kwargs["spec"]
            calls.append(copy.deepcopy(spec))
            if fail_at == len(calls):
                return {"status": "failed" if incident else "model_structure_failure", "response": None,
                        "system_integrity_incident": incident, "continuation_eligible": False,
                        "generation_requests_attempted": 1}
            content = response_for(spec, broken_sum=broken_sum, invented_citation=invented_citation)
            return self.persist_completed_stage(spec, content)
        return run

    def persist_completed_stage(self, spec, content):
        """Temporary synthetic transport files; no human/model output is asserted."""
        target = runtime.expected_stage_directory(spec)
        target.mkdir()
        (target / "http_0001_generation").mkdir()
        response = {"model": runtime.base.MODEL, "done": True, "done_reason": "stop", "message": {"content": content}}
        worker = {"status": "completed", "continuation_eligible": True, "system_integrity_incident": False,
                  "generation_requests_attempted": 1}
        supervisor = {"status": "worker_exited", "worker_exit_code": 0, "worker": worker,
                      "generation_requests_attempted": 1}
        for name, value in (("worker_spec.json", spec), ("worker_summary.json", worker),
                            ("supervisor_result.json", supervisor), ("http_0001_generation/response.json", response)):
            runtime.remote.save(target / name, value)
        result = {"status": "completed", "response": response, "supervisor": supervisor,
                  "system_integrity_incident": False, "continuation_eligible": True,
                  "generation_requests_attempted": 1,
                  "response_artifact": runtime.artifact_ref(target / "http_0001_generation/response.json")}
        runtime.remote.save(target / "transport_result.json", result)
        return result

    def final_spec(self):
        spec = self.spec()
        raw = response_for(spec)
        self.persist_completed_stage(spec, raw)
        final = contract.build_final_messages(draft_messages=self.cases[0]["messages"], raw_draft=raw,
            assigned_packet=self.cases[0]["assigned_packet"], prompt_contract=self.bundle["prompt_contract"],
            response_schema=self.bundle["response_schema"])
        spec.update(stage="F0", raw_draft=raw,
            draft_artifacts=runtime.prior_draft_refs(spec["run_directory"], spec["case_id"]),
            body=runtime.request_body(self.config, final["messages"], self.bundle["response_schema"]))
        return spec

    def test_fixed_options_cannot_drift(self):
        runtime.validate_runtime(self.config)
        for field, value in (("temperature", 0.5), ("num_predict", 700), ("num_thread", 4), ("num_gpu", 1),
                             ("temperature", False), ("num_predict", 8192.0)):
            altered = copy.deepcopy(self.config)
            altered["options"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                runtime.validate_runtime(altered)

    def test_body_boolean_zero_is_not_integer_zero(self):
        spec = self.spec()
        spec["body"]["options"]["num_gpu"] = False
        with self.assertRaisesRegex(ValueError, "API body differs"):
            runtime.validate_spec(spec)

    def test_declared_4500_second_ceiling_rejects_old_900(self):
        spec = self.spec()
        self.assertEqual(runtime.candidate_runtime(backend="cpu", num_ctx=65536,
            tokenizer_config=self.config["tokenizer_config"], backend_evidence=self.config["backend_evidence"])["deadline_seconds"], 4500)
        spec["deadline_seconds"] = 900
        with self.assertRaisesRegex(ValueError, "engineering ceiling is 4500"):
            runtime.validate_spec(spec)

    def test_supervisor_does_not_apply_legacy_900_second_cutoff(self):
        spec = self.spec()
        directory = runtime.expected_stage_directory(spec)
        directory.mkdir()
        path = directory / "worker_spec.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        process = MagicMock()
        process.poll.side_effect = [None, 0]
        process.returncode = 0
        with patch.object(runtime.subprocess, "Popen", return_value=process), \
             patch.object(runtime.time, "monotonic", side_effect=[0, 901, 902]), \
             patch.object(runtime.time, "sleep"):
            result = runtime.supervise(path)
        process.kill.assert_not_called()
        self.assertEqual(result["status"], "worker_exited")
        self.assertEqual(result["deadline_seconds"], 4500)

    def test_supervisor_stops_at_declared_4500_second_cutoff(self):
        spec = self.spec()
        directory = runtime.expected_stage_directory(spec)
        directory.mkdir()
        path = directory / "worker_spec.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        process = MagicMock()
        process.poll.return_value = None
        process.returncode = -1
        with patch.object(runtime.subprocess, "Popen", return_value=process), \
             patch.object(runtime.time, "monotonic", side_effect=[0, 4501, 4502]):
            result = runtime.supervise(path)
        process.kill.assert_called_once()
        self.assertEqual(result["status"], "hard_deadline")

    def test_backend_reference_hash_is_verified(self):
        changed = copy.deepcopy(self.config)
        changed["backend_evidence"][0]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            runtime.validate_runtime(changed)

    def test_main_case_denied(self):
        spec = self.spec()
        spec["case_id"] = "fidelity_q3_2026__E"
        with self.assertRaises(ValueError):
            runtime.validate_spec(spec)

    def test_worker_spec_cannot_bypass_review_gate(self):
        self.gate_mock.side_effect = ValueError("AI review and freeze pending")
        with self.assertRaisesRegex(ValueError, "AI review and freeze pending"):
            runtime.validate_spec(self.spec())

    def test_worker_requires_exact_review_gate_hash(self):
        spec = self.spec()
        spec["review_gate"]["sha256"] = None
        with self.assertRaisesRegex(ValueError, "pin an exact completed delegated-AI review gate hash"):
            runtime.validate_spec(spec)

    def test_pilot_preparation_cannot_bypass_review_gate(self):
        self.gate_mock.side_effect = ValueError("AI review and freeze pending")
        with self.assertRaisesRegex(ValueError, "AI review and freeze pending"):
            self.declaration()
        self.assertFalse((self.root / "pilot").exists())

    def test_pilot_run_rechecks_review_gate(self):
        target = self.declaration()
        self.gate_mock.side_effect = ValueError("AI receipt changed")
        calls = []
        with self.assertRaisesRegex(ValueError, "AI receipt changed"):
            runtime.run_pilot(target, transport=self.transport(calls))
        self.assertEqual(calls, [])

    def test_blank_AI_review_receipt_is_rejected(self):
        from sector_v492_review_gate import validate_review_gate
        with self.assertRaisesRegex(ValueError, "completed delegated-AI receipt"):
            validate_review_gate(self.gate_path)

    def test_late_source_injection_denied_before_transport(self):
        spec = self.spec(1)
        payload = json.loads(spec["body"]["messages"][1]["content"])
        payload["institution_document"] = self.cases[1]["assigned_packet"]
        spec["body"]["messages"][1]["content"] = json.dumps(payload)
        with self.assertRaises(ValueError):
            runtime.validate_spec(spec)

    def test_controller_metadata_cannot_enter_messages(self):
        spec = self.spec()
        spec["body"]["messages"][1]["content"] += "\ncase_id=controller_only"
        with self.assertRaises(ValueError):
            runtime.validate_spec(spec)

    def test_final_request_must_retain_exact_own_history(self):
        spec = self.final_spec()
        raw = spec["raw_draft"]
        runtime.validate_spec(spec)
        self.assertEqual(spec["body"]["messages"][2]["content"], raw)
        spec["body"]["messages"][2]["content"] = raw.strip()
        with self.assertRaises(ValueError):
            runtime.validate_spec(spec)

    def test_final_cannot_be_started_with_only_caller_supplied_draft(self):
        spec = self.final_spec()
        del spec["draft_artifacts"]
        with self.assertRaisesRegex(ValueError, "exact prior D0 artifact references"):
            runtime.validate_spec(spec)

    def test_final_prior_response_hash_mismatch_denied(self):
        spec = self.final_spec()
        spec["draft_artifacts"]["response"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "input hash differs"):
            runtime.validate_spec(spec)

    def test_final_prior_response_other_case_denied(self):
        spec = self.final_spec()
        original = Path(spec["draft_artifacts"]["response"]["path"])
        other = self.root / "ubs_june_2026__E__D0" / "http_0001_generation" / "response.json"
        other.parent.mkdir(parents=True)
        other.write_bytes(original.read_bytes())
        spec["draft_artifacts"]["response"] = runtime.artifact_ref(other)
        with self.assertRaisesRegex(ValueError, "same run/case D0 artifact"):
            runtime.validate_spec(spec)

    def test_final_self_consistent_changed_draft_cannot_replace_saved_response(self):
        spec = self.final_spec()
        spec["raw_draft"] = spec["raw_draft"].strip()
        final = contract.build_final_messages(draft_messages=self.cases[0]["messages"], raw_draft=spec["raw_draft"],
            assigned_packet=self.cases[0]["assigned_packet"], prompt_contract=self.bundle["prompt_contract"],
            response_schema=self.bundle["response_schema"])
        spec["body"] = runtime.request_body(self.config, final["messages"], self.bundle["response_schema"])
        with self.assertRaisesRegex(ValueError, "completed pinned D0 response content exactly"):
            runtime.validate_spec(spec)

    def test_final_requires_saved_completion_and_continuation(self):
        spec = self.final_spec()
        ref = spec["draft_artifacts"]["worker_summary"]
        path = Path(ref["path"])
        value = runtime.remote.read(path)
        value["continuation_eligible"] = False
        path.write_text(json.dumps(value), encoding="utf-8")
        spec["draft_artifacts"]["worker_summary"] = runtime.artifact_ref(path)
        with self.assertRaisesRegex(ValueError, "worker, supervisor and cleanup/continuation records must agree"):
            runtime.validate_spec(spec)

    def test_final_saved_response_requires_pinned_model_and_normal_stop(self):
        spec = self.final_spec()
        path = Path(spec["draft_artifacts"]["response"]["path"])
        original = runtime.remote.read(path)
        for change in ({"model": "unapproved"}, {"done_reason": "length"}, {"done": False}):
            path.write_text(json.dumps(original | change), encoding="utf-8")
            spec["draft_artifacts"]["response"] = runtime.artifact_ref(path)
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "completed pinned D0 response content exactly"):
                runtime.validate_spec(spec)

    def test_final_saved_draft_spec_must_name_same_case(self):
        spec = self.final_spec()
        path = Path(spec["draft_artifacts"]["worker_spec"]["path"])
        original = runtime.remote.read(path)
        original["case_id"] = runtime.CASES[2]
        path.write_text(json.dumps(original), encoding="utf-8")
        spec["draft_artifacts"]["worker_spec"] = runtime.artifact_ref(path)
        with self.assertRaisesRegex(ValueError, "execution identity or declared conditions differ"):
            runtime.validate_spec(spec)

    def test_draft_cannot_accept_prior_draft_reference(self):
        spec = self.spec()
        spec["draft_artifacts"] = None
        with self.assertRaisesRegex(ValueError, "Draft stage cannot contain"):
            runtime.validate_spec(spec)

    def test_worker_location_must_match_same_run_case_and_stage(self):
        with self.assertRaisesRegex(ValueError, "directory must belong to this run, case and stage"):
            runtime.validate_worker_location(self.spec(), self.root / "another_run")

    def token_receipt(self, text, count):
        from sector_v491_tokenizer import GGUF_SHA256, LIBRARY_HASHES
        return {"token_count": count, "rendered_utf8_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "model_digest": runtime.base.DIGEST, "template_sha256": runtime.base.TEMPLATE,
                "method": "exact_installed_libllama_vocab_only", "add_special": True,
                "parse_special": True, "generation_calls": 0,
                "gguf_sha256": GGUF_SHA256, "library_hashes": LIBRARY_HASHES}

    def test_oversize_actual_final_prevents_generation_and_is_capacity_failure(self):
        spec = self.final_spec()
        directory = runtime.expected_stage_directory(spec)
        directory.mkdir()
        spec_path = directory / "worker_spec.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")

        def render(session, body, expected_system):
            rendered = session.target / "render_only"
            rendered.mkdir()
            (rendered / "rendered_prompt.txt").write_text("oversize exact final", encoding="utf-8")

        with patch.object(runtime.prior, "render_call", side_effect=render), \
             patch.object(runtime.bench, "observe", return_value={}), \
             patch.object(runtime.base, "assert_pin"), \
             patch.object(runtime.bench.ProbeSession, "start_monitor"), \
             patch.object(runtime.awake, "acquire", return_value={"status": "active"}), \
             patch.object(runtime.awake, "release", return_value={"status": "released"}), \
             patch("sector_v491_tokenizer.count_rendered_tokens", return_value=self.token_receipt("oversize exact final", 65536)), \
             patch.object(runtime.remote, "stream_call") as generate:
            self.assertEqual(runtime.worker(spec_path), 1)
            generate.assert_not_called()
        result = runtime.remote.read(directory / "worker_summary.json")
        self.assertEqual(result["status"], "capacity_failure")
        self.assertEqual(result["generation_requests_attempted"], 0)

    def test_exact_capacity_includes_full_output_allowance(self):
        receipt = self.token_receipt("exact rendered", 65536 - 8192)
        self.assertEqual(runtime.check_token_capacity(receipt, "exact rendered", self.config)["total_required_tokens"], 65536)
        receipt["token_count"] += 1
        with self.assertRaises(ValueError):
            runtime.check_token_capacity(receipt, "exact rendered", self.config)

    def test_token_counter_rejects_estimates_or_other_prompt(self):
        good = self.token_receipt("exact rendered", 42)
        for patch_value in ({"token_count": True}, {"method": "utf8_bytes_div_four"},
                            {"rendered_utf8_sha256": "0" * 64}, {"model_digest": "0" * 64}):
            with self.subTest(value=patch_value), self.assertRaises(ValueError):
                runtime.check_token_capacity({**good, **patch_value}, "exact rendered", self.config)

    def test_five_separate_cases_ten_calls_no_final_repair(self):
        target = self.declaration()
        calls = []
        summary = runtime.run_pilot(target, transport=self.transport(calls))
        self.assertEqual(summary["generation_requests_attempted"], 10)
        self.assertEqual([s["stage"] for s in calls], ["D0", "F0"] * 5)
        self.assertEqual(summary["main_model_calls"], 0)
        self.assertEqual(summary["post_final_calls"], 0)
        self.assertEqual(calls[2]["body"]["messages"], calls[6]["body"]["messages"])
        self.assertEqual(calls[2]["body"]["messages"], calls[8]["body"]["messages"])
        self.assertNotEqual(calls[2]["case_id"], calls[6]["case_id"])
        self.assertEqual(calls[8]["case_id"], "common_market_only__C")
        self.assertNotIn("institution_document", json.loads(calls[9]["body"]["messages"][-1]["content"]))
        for draft, final in zip(calls[::2], calls[1::2]):
            self.assertEqual(final["body"]["messages"][:2], draft["body"]["messages"])
            self.assertEqual(final["body"]["messages"][2]["content"], final["raw_draft"])

    def test_raw_sum_failure_and_bad_citations_do_not_censor_final(self):
        target = self.declaration()
        calls = []
        summary = runtime.run_pilot(target, transport=self.transport(calls, broken_sum=True, invented_citation=True))
        self.assertEqual(summary["generation_requests_attempted"], 10)
        final = runtime.remote.read(target / (runtime.CASES[0] + "__final_construction.json"))
        self.assertFalse(final["draft_validation"]["arithmetic"]["valid"])
        self.assertFalse(final["draft_validation"]["visibility_valid"])
        self.assertTrue(final["ready"])
        self.assertNotIn("invented:not-visible", final["draft_feedback"].get("facts", []))

    def test_unreadable_draft_skips_only_its_final(self):
        target = self.declaration()
        calls = []
        result = runtime.run_pilot(target, transport=self.transport(calls, fail_at=1))
        self.assertEqual(result["generation_requests_attempted"], 9)
        self.assertEqual(len(result["cases"][0]["stages"]), 1)
        self.assertEqual(calls[1]["case_id"], runtime.CASES[1])

    def test_integrity_failure_stops_all_following_cases(self):
        target = self.declaration()
        calls = []
        result = runtime.run_pilot(target, transport=self.transport(calls, fail_at=1, incident=True))
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["status"], "stopped")
        self.assertTrue(all(c["status"] == "not_attempted_after_stop" for c in result["cases"][1:]))

    def test_second_execution_is_not_a_resume_or_retry(self):
        target = self.declaration()
        calls = []
        runtime.run_pilot(target, transport=self.transport(calls))
        with self.assertRaises(FileExistsError):
            runtime.run_pilot(target, transport=self.transport(calls))
        self.assertEqual(len(calls), 10)

    def test_preexisting_cancel_prevents_all_generation(self):
        target = self.declaration()
        (target / "CANCEL").touch()
        calls = []
        result = runtime.run_pilot(target, transport=self.transport(calls))
        self.assertEqual(calls, [])
        self.assertEqual(result["generation_requests_attempted"], 0)


if __name__ == "__main__":
    unittest.main()
