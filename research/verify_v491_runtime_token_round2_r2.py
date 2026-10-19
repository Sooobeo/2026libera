"""Limited independent recheck of the F0 saved-D0 provenance revision.

Retains the earlier 46-check review. Only affected tests and structural guards
are repeated; no server requests, real research outputs or human attestations.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import unittest

import sector_v491_runtime as runtime
from sector_v491_tokenizer import sha_file
from test_sector_v491_runtime import RuntimeTests

ROOT = Path(__file__).resolve().parent.parent
NAMES = [
    "test_final_cannot_be_started_with_only_caller_supplied_draft",
    "test_final_prior_response_hash_mismatch_denied",
    "test_final_prior_response_other_case_denied",
    "test_final_self_consistent_changed_draft_cannot_replace_saved_response",
    "test_final_requires_saved_completion_and_continuation",
    "test_final_saved_response_requires_pinned_model_and_normal_stop",
    "test_final_saved_draft_spec_must_name_same_case",
    "test_draft_cannot_accept_prior_draft_reference",
    "test_worker_location_must_match_same_run_case_and_stage",
    "test_final_request_must_retain_exact_own_history",
    "test_oversize_actual_final_prevents_generation_and_is_capacity_failure",
    "test_four_separate_cases_eight_calls_no_final_repair",
    "test_raw_sum_failure_and_bad_citations_do_not_censor_final",
]


def functions(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.name: ast.dump(n, include_attributes=False) for n in tree.body if isinstance(n, ast.FunctionDef)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--round1", required=True, type=Path)
    args = parser.parse_args()
    prior = json.loads(args.round1.read_text(encoding="utf-8"))
    if prior.get("status") != "PASS" or any(t.get("returncode") != 0 for t in prior["tests"]):
        raise RuntimeError("The completed updated round1 test receipt is required")
    original = ROOT / "research/v491_runtime_round2_token_review_20261019.json"
    history = ROOT / "research/artifacts/v491_runtime_review_history_20261019/r1"
    old_source = history / "sector_v491_runtime.py"
    if not old_source.is_file():
        # Snapshot directory uses the original path name if its creator preserves folders.
        matches = list(history.rglob("sector_v491_runtime.py"))
        if len(matches) != 1:
            raise RuntimeError("Exact prior runtime snapshot required")
        old_source = matches[0]
    original_review = json.loads(original.read_text(encoding="utf-8"))
    old_refs = {r["path"]: r["sha256"] for r in original_review["reviewed_files"]}
    if sha_file(old_source) != old_refs["research/sector_v491_runtime.py"]:
        raise RuntimeError("Prior code snapshot does not match the original round2")
    previous, current = functions(old_source), functions(ROOT / "research/sector_v491_runtime.py")
    checks = []
    for name in ["candidate_runtime", "validate_runtime", "load_bundle", "request_body", "check_token_capacity"]:
        checks.append({"check": name + "_unchanged_AST", "passed": previous[name] == current[name],
                       "finding": "Previous review of CPU/options/source inventory/exact capacity remains applicable; runtime version advances explicitly"})
    for name in ["sector_v491_human_gate.py", "sector_v491_tokenizer.py"]:
        checks.append({"check": name + "_unchanged_bytes", "passed": sha_file(ROOT / "research" / name) == old_refs["research/" + name],
                       "finding": "Previously reviewed native tokenizer and genuine-human completeness gate remain byte-identical"})
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.TestSuite(RuntimeTests(name) for name in NAMES))
    checks.append({"check": "affected_provenance_and_integration_tests", "passed": result.wasSuccessful() and result.testsRun == len(NAMES),
                   "finding": "Direct F0 cannot bypass saved own-D0 provenance; same-case/schema/error-preservation/capacity and full4case8call synthetic path remain valid"})
    checks.append({"check": "five_prior_artifacts_bound", "passed": set(runtime.DRAFT_ARTIFACTS) == {"response", "worker_spec", "worker_summary", "supervisor_result", "transport_result"},
                   "finding": "Actual D0 response bytes, source/case/runtime spec, worker completion, supervisor completion and final cleanup/continuation records must agree"})
    source = (ROOT / "research/sector_v491_runtime.py").read_text(encoding="utf-8")
    checks.append({"check": "provenance_precedes_F0_build", "passed": source.index('provenance = validate_prior_draft(spec)') < source.index('final = contract.build_final_messages(draft_messages=messages'),
                   "finding": "The raw draft is bound to saved same-run/case completion before F0 is constructed or sent"})
    report = {"round": 2, "revision": "r2", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if all(c["passed"] for c in checks) else "issues_found",
        "scope": "Limited independent recheck after F0 saved-D0 provenance fix; earlier unaffected review retained",
        "previous_round2": {"path": original.relative_to(ROOT).as_posix(), "sha256": sha_file(original)},
        "prior_round1_r2": {"path": args.round1.resolve().relative_to(ROOT).as_posix(), "sha256": sha_file(args.round1)},
        "history_manifest": {"path": (history / "snapshot_manifest.json").relative_to(ROOT).as_posix(), "sha256": sha_file(history / "snapshot_manifest.json")},
        "checks": checks, "check_count": len(checks), "failed_checks": [c["check"] for c in checks if not c["passed"]],
        "tests_run": result.testsRun, "test_names": NAMES, "test_log": stream.getvalue(),
        "model_generation_calls": 0, "real_human_reviews_performed": 0,
        "reviewed_files": [{"path": "research/" + name, "sha256": sha_file(ROOT / "research" / name)} for name in
            ["sector_v491_runtime.py", "sector_v491_human_gate.py", "sector_v491_tokenizer.py", "test_sector_v491_runtime.py", "verify_v491_runtime_token_round2_r2.py"]],
        "limits": ["Hash-bound internal records prevent accidental cross-case substitution; they do not authenticate an operator who deliberately fabricates every file.",
            "Synthetic in-memory/file fixtures are instrument tests, not actual model responses or human review attestations.",
            "Actual F0 capacity and complete pilot performance remain unmeasured until real D0 outputs exist after the human gate."]}
    target = ROOT / "research/v491_runtime_round2_token_review_20261019_r2.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(checks), "tests": result.testsRun, "failed": report["failed_checks"]}))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
