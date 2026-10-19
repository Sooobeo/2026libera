"""Package the token-only audit as a small, lossless reviewable artifact."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from sector_v491_tokenizer import sha_file

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "research/evidence/v491_tokenizer_20261019"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", default="r2", choices=["r2"])
    parser.parse_args()
    summary = json.loads((SOURCE / "d0_capacity_with_format/summary.json").read_text(encoding="utf-8"))
    tests = json.loads((SOURCE / "tests_r3_result.json").read_text(encoding="utf-8"))
    if summary["status"] != "pass" or tests["returncode"] != 0:
        raise RuntimeError("Review prerequisites failed")
    r1 = json.loads((SOURCE / "d0_capacity/summary.json").read_text(encoding="utf-8"))
    prior_cases = {case["case_id"]: case for case in r1["cases"]}
    comparisons = [{"case_id": case["case_id"],
        "same_rendered_bytes": case["rendered_utf8_sha256"] == prior_cases[case["case_id"]]["rendered_utf8_sha256"],
        "same_token_count": case["token_count"] == prior_cases[case["case_id"]]["token_count"]}
        for case in summary["cases"]]
    # This comparison is empirical; no assumption that output-schema settings
    # cannot influence the renderer is used to certify the final request.
    if len(comparisons) != 8 or not all(c["same_rendered_bytes"] and c["same_token_count"] for c in comparisons):
        raise RuntimeError("Structured-format rendering changed; review the new exact counts before finalizing")
    file_rows = [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha_file(p),
                  "bytes": p.stat().st_size} for p in sorted(SOURCE.rglob("*")) if p.is_file()]
    archive = ROOT / "research/artifacts/v491_tokenizer_evidence_20261019_r2.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for row in file_rows:
            output.write(ROOT / row["path"], row["path"])
    with zipfile.ZipFile(archive) as check:
        assert check.testzip() is None
        assert len(check.namelist()) == len(file_rows)
        assert all(hashlib.sha256(check.read(row["path"])).hexdigest() == row["sha256"] for row in file_rows)
    sources = [
        ("include_llama.h", "include/llama.h", "Exact model-params ABI, vocabulary-only loading and tokenizer C API"),
        ("src_llama.cpp", "src/llama.cpp", "Vocabulary-only mode returns before tensor loading; no backend initialization required"),
        ("tools_server_server-context.cpp", "tools/server/server-context.cpp", "Completion handler tokenizes input with add_special=true and parse_special=true"),
        ("tools_server_server-common.cpp", "tools/server/server-common.cpp", "Text path delegates to native common_tokenize")]
    report = {
        "review": "v4.9.1 exact tokenizer and D0 context capacity",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "pass_for_exact_D0_sizing_and_dynamic_stage_guard_only",
        "generation_calls": 0, "render_only_calls": 8,
        "historical_render_only_calls_without_format": 8,
        "review_history": "Original r1 counts remain preserved. r2 repeats all 8 exact render-only requests with the API format schema included, and is the current capacity receipt.",
        "historical_code_snapshot_manifest": {"path": "research/evidence/v491_tokenizer_20261019/review_history_r1/snapshot_manifest.json",
            "sha256": sha_file(SOURCE / "review_history_r1/snapshot_manifest.json")},
        "native_backend": "installed Ollama 0.35.1 libllama.dll; llama.cpp commit 6f767fe96; GGUF vocabulary-only, no tensors/context/backend load",
        "actual_D0_cases": [{k: c[k] for k in ["case_id", "token_count", "required_tokens", "fits_with_output_reserve", "rendered_utf8_sha256", "token_ids_sha256", "structured_format_schema_sha256"]}
                            for c in summary["cases"]],
        "format_and_thread_revision_render_comparison": comparisons,
        "exact_D0_token_range": summary["exact_D0_token_range"],
        "selected_engineering_capacity_for_this_check": 65536,
        "renderer_request_cpu_threads": summary["renderer_request_cpu_threads"],
        "paper_derived_output_allowance": 8192,
        "parameter_scope": "65536 is inherited engineering capacity, not a paper-derived optimal value. 8192 is a transferred PortBench allowance, not proof of task sufficiency.",
        "ordered_reviews": [
            {"round": 1, "scope": "All 8 unchanged prepared D0 inputs, actual render-only preservation and exact native count", "status": "pass", "case_count": 8},
            {"round": 2, "scope": "Pinned source ABI / native binary / GGUF and independent count against 5 archived actual provider counters", "status": "pass", "crosschecks": summary["archived_counter_crosschecks"]},
            {"round": 3, "scope": "Native integration and fail-closed malformed input / changed binary / changed model checks", "status": "pass", "test_count": 12,
             "test_receipt": "research/evidence/v491_tokenizer_20261019/tests_r3_result.json"}],
        "F0_universal_capacity_proven": False,
        "full_two_stage_memory_or_latency_proven": False,
        "required_F0_guard": summary["F0_policy"],
        "limits": summary["limitations"] + [
            "An 8192-token generated response can retokenize differently; calculator feedback may echo unbounded constraint/citation fields. Adding 8192 to D0 cannot certify every future F0.",
            "A failed actual F0 capacity check must be an execution failure in the denominator, with no truncation, retry, repair or convenient case replacement.",
            "Native tokenizer pins the GGUF/library bytes; live manifest and chat-template pins remain runtime checks.",
            "CPU isolation is a diagnostic response to observed prior Vulkan device-lost failures; it does not establish faster response or guarantee stability.",
            "No formal pilot or main generation was performed by this audit; prior source-blinded human gates remain required."],
        "sources": [{"url": "https://raw.githubusercontent.com/ggml-org/llama.cpp/6f767fe96/" + remote,
                     "local_path": "research/evidence/v491_tokenizer_20261019/" + local,
                     "sha256": sha_file(SOURCE / local), "supports": claim} for local, remote, claim in sources],
        "code": [{"path": "research/" + p, "sha256": sha_file(ROOT / "research" / p)}
                 for p in ["sector_v491_tokenizer.py", "test_sector_v491_tokenizer.py", "v491_token_capacity_audit.py", "v491_token_review_finalize.py", "v491_token_restore_review_history.py"]],
        "evidence_archive": {"path": archive.relative_to(ROOT).as_posix(), "sha256": sha_file(archive), "file_count": len(file_rows), "all_archived_member_hashes_verified": True},
        "evidence_files": file_rows}
    path = ROOT / "research/v491_token_review_20261019_r2.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"path": path.relative_to(ROOT).as_posix(), "sha256": sha_file(path), "archive": report["evidence_archive"]}))


if __name__ == "__main__":
    main()
