"""Independent round 2: exact-token binding, retained history, and human gate.

No network, model generation, output semantic scoring, or fabricated humans.
The constructed draft below is clearly synthetic instrument-test data only.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import sector_v491_contract as contract
import sector_v491_runtime as runtime
from sector_v491_human_gate import validate_human_gate
from sector_v491_tokenizer import sha_file

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--round1", required=True, type=Path)
    parser.add_argument("--output", default=ROOT / "research/v491_runtime_round2_token_review_20261019.json", type=Path)
    args = parser.parse_args()
    prior = json.loads(args.round1.read_text(encoding="utf-8-sig"))
    checks = []
    def check(name, ok, finding):
        checks.append({"check": name, "passed": bool(ok), "finding": finding})
    def rejected(name, callback, finding):
        try:
            callback()
        except (ValueError, RuntimeError, FileNotFoundError):
            check(name, True, finding)
        else:
            check(name, False, "Mutation unexpectedly accepted")

    # The caller provides round 1; chronological binding is retained regardless
    # of that receipt's field naming. Root verifies its status when ordering rounds.
    check("round1_receipt_present", isinstance(prior, dict) and bool(prior), "Bound prior independent implementation/test receipt")
    bundle, cases = runtime.load_bundle()
    check("only_four_pilot_cases", tuple(c["case_id"] for c in cases) == runtime.CASES and len(cases) == 4,
          "Main D0 is absent from the pilot coordinator inventory")
    late = [c for c in cases if c["arm"] == "L"]
    check("late_drafts_same_input_separate_cases", late[0]["messages"] == late[1]["messages"] and late[0]["case_id"] != late[1]["case_id"],
          "Two independent draft attempts remain required despite identical L messages")
    for c in cases:
        payload = contract.strict_json(c["messages"][1]["content"])
        check(c["case_id"] + ":visibility", ("institution_document" in payload) == (c["arm"] == "E"),
              "Source first-exposure timing is the only intended D0 source-information difference")
        check(c["case_id"] + ":common_context", payload["common_context"] == bundle["common_context"],
              "Common operating situation and macro facts retained at D0")
        obj = {"source_id": c["source_id"] if c["arm"] == "E" else None,
               "sectors": [{"sector_code": code, "source_label": None,
                    "source_reading": "Synthetic instrument fixture only", "source_evidence_ids": [],
                    "source_stance": "undetermined" if c["arm"] == "E" else "not_available",
                    "weight": 0.1, "decision_reason": "Synthetic instrument fixture only", "decision_evidence_ids": []}
                           for code in contract.SECTOR_CODES],
               "context_assessment": {"market_and_mandate_reading": "Synthetic instrument fixture only",
                    "allocation_implication": "Synthetic instrument fixture only", "evidence_ids": [],
                    "limitations": "Not a model output or human review"},
               "alternatives": "Synthetic instrument fixture only", "risk_discussion": "Synthetic instrument fixture only",
               "unresolved": [], "submitted_constraints": []}
        raw = "\r\n " + json.dumps(obj, ensure_ascii=False) + "\t"
        final = contract.build_final_messages(draft_messages=c["messages"], raw_draft=raw,
                 assigned_packet=c["assigned_packet"], prompt_contract=bundle["prompt_contract"],
                 response_schema=bundle["response_schema"])
        check(c["case_id"] + ":actual_own_history", final["ready"] and final["messages"][:2] == c["messages"]
              and final["messages"][2] == {"role": "assistant", "content": raw},
              "Original two-message D0 and verbatim own raw response, including outer CR/LF/tab, are retained")
        f0 = contract.strict_json(final["messages"][3]["content"])
        check(c["case_id"] + ":fresh_source_and_unrepaired_feedback", f0["institution_document"] == c["assigned_packet"]
              and final["draft_feedback"]["allocation"]["valid"] is False
              and abs(final["draft_feedback"]["allocation"]["raw_sum"] - 1.1) < 1e-12
              and final["draft_feedback"]["repaired"] is False,
              "Synthetic 1.1 budget error continues as measured error; fresh source is appended and no normalization occurs")

    base = ROOT / "research/evidence/v491_tokenizer_20261019/d0_capacity"
    capacity_runtime = {"options": {"num_ctx": 65536, "num_predict": 8192}}
    example = None
    for p in sorted(base.rglob("token_count.json")):
        receipt = json.loads(p.read_text(encoding="utf-8"))
        rendered = (p.parent / "rendered_prompt.txt").read_bytes().decode("utf-8")
        checked = runtime.check_token_capacity(receipt, rendered, capacity_runtime)
        check(p.parent.name + ":exact_bound", checked["total_required_tokens"] == receipt["token_count"] + 8192,
              "Observed actual rendered string is hash-bound to exact native count, plus full output allowance; format-inclusive rerender is separately recorded in token review r2")
        example = receipt, rendered
    receipt, rendered = example
    mutations = [{"token_count": False}, {"token_count": 0}, {"token_count": -1}, {"token_count": "10"},
                 {"rendered_utf8_sha256": "0" * 64}, {"model_digest": "0" * 64},
                 {"template_sha256": "0" * 64}, {"method": "bytes_div_four"},
                 {"add_special": False}, {"parse_special": False}, {"generation_calls": 1},
                 {"gguf_sha256": "0" * 64}, {"library_hashes": {"wrong": "0" * 64}}]
    for i, mutation in enumerate(mutations):
        rejected("receipt_mutation_" + str(i + 1),
                 lambda m=mutation: runtime.check_token_capacity(receipt | m, rendered, capacity_runtime),
                 "Reject changed count/renderer/model/template/native tokenizer provenance: " + str(mutation))
    rejected("one_token_insufficient_context", lambda: runtime.check_token_capacity(receipt, rendered,
             {"options": {"num_ctx": receipt["token_count"] + 8191, "num_predict": 8192}}),
             "The request stops before generation instead of truncating retained history")
    rejected("actual_blank_human_gate", lambda: validate_human_gate("research/v491_human_review_pack_20261019_gate_blank.json"),
             "Prepared forms and software/AI reviews are insufficient; actual independent human attestations required")

    source = (ROOT / "research/sector_v491_runtime.py").read_text(encoding="utf-8")
    check("worker_orders_render_count_generation", source.index('prior.render_call(session') < source.index('count = count_rendered_tokens') < source.index('response = remote.stream_call'),
          "Source inspection: actual body rendered, exact full-history token count checked, then one generation; there is no retry branch")
    check("awake_release_in_finally", 'finally:\n        session.stop_monitor()\n        if awake_token is not None:' in source,
          "Worker holds temporary awake request and releases it on normal/exception paths; abrupt process kill skips finally, and the supervisor treats a missing completed record as a global stop")
    check("json_type_exact_runtime_and_body", 'base.canonical(runtime) != base.canonical(expected)' in source
          and 'base.canonical(spec["body"]) != base.canonical(request_body' in source,
          "Independent review found Python False==0 / float==integer comparison weakness; canonical JSON comparison now preserves JSON type distinctions")
    check("preoutput_gate_all_entrypoints", source.count("validate_human_gate(") >= 3,
          "Manual source review: prepare, run, worker/supervisor spec validation require the same hash-bound human gate")
    report = {"round": 2, "reviewer": "independent tokenizer/runtime reviewer agent", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if all(c["passed"] for c in checks) else "issues_found", "checks": checks,
        "check_count": len(checks), "failed_checks": [c["check"] for c in checks if not c["passed"]],
        "model_generation_calls": 0, "human_reviews_fabricated": 0,
        "prior_round1": {"path": args.round1.resolve().relative_to(ROOT).as_posix(), "sha256": sha_file(args.round1)},
        "reviewed_files": [{"path": "research/" + p, "sha256": sha_file(ROOT / "research" / p)} for p in
                           ["sector_v491_runtime.py", "sector_v491_human_gate.py", "sector_v491_tokenizer.py", "test_sector_v491_runtime.py", "verify_v491_runtime_token_round2.py"]],
        "limits": ["Offline correctness/guard review is not proof of successful formal pilot or main runtime.",
            "Actual F0 capacity is only decided after an actual D0; no universal unseen-response bound is claimed.",
            "Human identity and interpretation accuracy cannot be certified by this completeness validator.",
            "Renderer whitespace policy is unchanged: HTTP history verbatim, only documented outer JSON whitespace trimming in actual renderer.",
            "D0 context and native token correctness do not establish semantic quality, 12-month performance, or significance."]}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "check_count": report["check_count"], "failed_checks": report["failed_checks"]}))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
