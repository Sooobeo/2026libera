"""Freeze the audited recovery/development pilot before any new research output."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import prepare_sector_v494 as preparation
import sector_v494_runtime as runtime
import sector_v494_review_gate as gate_rules

ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / "research/recovery_20261025"
INSTRUCTION = "다 진행해봐.\n배분,인용 오류 점검 및 새 파일럿 검증하는건 한 단계 할 때마다 오류,정합성, 소논문 주제와의 연결성이 너무 멀어지지 않는지 다 확인하면서 진행해"


def now():
    return datetime.now(timezone.utc).isoformat()


def ref(path):
    p = Path(path)
    p = p if p.is_absolute() else ROOT / p
    return {"path": p.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def read(path):
    p = Path(path)
    return json.loads((p if p.is_absolute() else ROOT / p).read_text(encoding="utf-8-sig"))


def save(path, value):
    p = Path(path)
    p = p if p.is_absolute() else ROOT / p
    with p.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def make_candidate():
    handoff = read(RECOVERY / "runtime/handoff.json")
    old = read("research/v492_runtime_candidate_20261019.json")
    evidence = [dict(ref(RECOVERY / "runtime/service_ready/service_receipt.json"), role="cpu_service"), *old["backend_evidence"][1:]]
    candidate = runtime.candidate_runtime(backend="cpu", num_ctx=65536, num_thread=8,
        tokenizer_config=handoff["tokenizer_config"], backend_evidence=evidence)
    runtime.validate_runtime(candidate)
    save(RECOVERY / "runtime_candidate.json", candidate)
    return candidate


def freeze():
    names = {"runtime": RECOVERY / "runtime_candidate.json", "freeze": RECOVERY / "pilot_freeze.json",
             "gate": RECOVERY / "review_gate.json"}
    if names["freeze"].exists() or names["gate"].exists():
        raise FileExistsError("This freeze already exists; preserve it")
    candidate = read(names["runtime"])
    runtime.validate_runtime(candidate)
    loaded, cases = runtime.load_bundle()
    assert [c["case_id"] for c in cases] == gate_rules.CASE_ORDER
    reviews = [RECOVERY / n for n in ("stage01_interruption_review.json", "stage02_method_preparation_review.json", "stage03_implementation_review.json")]
    for path in reviews:
        review = read(path)
        assert review["status"] == "PASS"
        assert all(review["review_axes"][axis]["pass"] is True for axis in ("errors", "consistency", "paper_topic"))
        for item in review.get("input_refs", []):
            assert ref(item["path"])["sha256"] == item["sha256"], item["path"]
    instruction = {"exact_text": INSTRUCTION, "timestamp_kind": "recorded_after_user_message", "recorded_at_utc": now(),
                   "scope": "Recovery, post-output prompt clarification and one new pilot with stepwise error, consistency and paper-topic checks. No automatic success-driven retries or unreviewed main execution."}
    refs = {
        "input_protocol_ref": ref("plan/LIBERA_실험설정_v4.9.1_20261019.json"),
        "evaluation_protocol_ref": ref("research/v492_evaluation_protocol_20261019_r2.json"),
        "source_review_ref": ref("research/v492_source_review_20261019.json"),
        "method_review_ref": ref(reviews[1]),
        "prompt_contract_ref": ref(preparation.DESIGN / "prompt_contract.json"),
        "prepared_manifest_ref": ref(preparation.MANIFEST), "runtime_ref": ref(names["runtime"]),
    }
    extra = {"research/freeze_sector_v494.py", "research/analyze_v492_pilot.py",
             "research/build_v492_masked_review.py", "research/recovery_20261025/method_build_audit.py",
             "research/recovery_20261025/runtime/start_isolated_cpu.ps1",
             "research/recovery_20261025/runtime/stop_isolated_cpu.ps1"}
    frozen = {"freeze_version": "v494_development_freeze_1", "protocol_version": "4.9.4",
              "status": "frozen_for_pilot_only", "purpose": "pilot_only", "recorded_at_utc": now(),
              "user_instruction": instruction, **refs,
              "case_order": gate_rules.CASE_ORDER, "controls": gate_rules.CONTROLS,
              "code_refs": [ref(p) for p in sorted(gate_rules.REQUIRED_CODE_PATHS | extra)],
              "stage_review_refs": [ref(p) for p in reviews], "main_allowed": False,
              "old_outputs_observed": True, "new_run_research_calls_before_freeze": 0,
              "development_disclosure": "Old failures informed clarification. This run is not pooled with the old run as identical replications. All outcomes retained; no success threshold selects cases.",
              "step_review_policy": "Each completed attempt gets exact artifact/arithmetic/citation/timing checks before the next stage. Interpretation of source support is separately recorded by AI; deterministic checks cannot certify semantic success."}
    save(names["freeze"], frozen)
    gate = {"receipt_version": "v494_development_gate_1", "status": "approved_for_pilot_before_generation",
            "review_mode": "AI_delegated_by_user", "recorded_at_utc": now(), "user_instruction": instruction,
            **refs, "freeze_ref": ref(names["freeze"]), "historical_gate_ref": ref("research/v492_ai_review_gate_20261019.json"),
            "stage_review_refs": frozen["stage_review_refs"], "pilot_cases": gate_rules.CASE_ORDER,
            "main_allowed": False, "old_outputs_observed": True, "new_run_research_calls_before_freeze": 0,
            "independent_human_review_completed": False}
    save(names["gate"], gate)
    result = gate_rules.validate_review_gate(names["gate"], runtime=candidate)
    save(RECOVERY / "freeze_validation.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["candidate", "freeze"])
    args = parser.parse_args()
    result = make_candidate() if args.command == "candidate" else freeze()
    print(json.dumps({"status": result.get("status", "candidate_created"), "model_calls": 0}))
