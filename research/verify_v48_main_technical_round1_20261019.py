"""Run final main-path synthetic checks and bind their exact code inventories.

No production candidate, authorization, human judgment or model run is created.
Tests use mocked generation / ephemeral fake HTTP and temporary fixture records.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import sector_v48_main_gate as gate

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/evidence/v48_main_integration_20261019/round1"
MODULES = (
    "test_run_sector_v48_main", "test_sector_v48_main_transport",
    "test_sector_v48_main_gate", "test_sector_v48_main_awake",
    "test_sector_v48_main_offline", "test_audit_v48_main_round1",
    "test_audit_v48_main_round2", "test_prepare_sector_v48_main_candidate",
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ref(path):
    return {"path": str(Path(path).resolve()), "sha256": sha(path)}


def save(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def inventories():
    return {"software_hashes": {name: sha(ROOT / "research" / name) for name in gate.SOFTWARE},
            "evaluator_software_hashes": {name: sha(ROOT / "research" / name) for name in gate.EVALUATOR_SOFTWARE}}


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    before = inventories()
    command = [sys.executable, "-B", "-X", "utf8", "-m", "unittest", "-v", *MODULES]
    result = subprocess.run(command, cwd=ROOT / "research", capture_output=True)
    (OUT / "tests.stdout.bin").write_bytes(result.stdout)
    (OUT / "tests.stderr.bin").write_bytes(result.stderr)
    save(OUT / "invocation.json", {"created_at_utc": datetime.now(timezone.utc).isoformat(),
        "argv": command, "exit_code": result.returncode, "model_calls": 0,
        "fixture_scope": "Mocked/fake-HTTP tests, no production study records or Windows power calls."})
    independent = [sys.executable, "-B", "-X", "utf8", "research/audit_v48_main_round2.py", "--self-test"]
    second = subprocess.run(independent, cwd=ROOT, capture_output=True)
    (OUT / "numeric_selftest.stdout.bin").write_bytes(second.stdout)
    (OUT / "numeric_selftest.stderr.bin").write_bytes(second.stderr)
    save(OUT / "numeric_selftest_invocation.json", {"argv": independent, "exit_code": second.returncode,
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "model_calls": 0})
    after = inventories()
    frozen_path = ROOT / "data/sector_protocol/v48_pilot_r2_20261018/manifest.json"
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    guard_review_path = ROOT / "research/evidence/v48_guarded_repeat_20261019/round1/review.json"
    guard_review = json.loads(guard_review_path.read_text(encoding="utf-8"))
    checks = [
        {"id": "synthetic_suite_passed", "pass": result.returncode == 0},
        {"id": "independent_numeric_selftests_passed", "pass": second.returncode == 0},
        {"id": "code_stable_during_tests", "pass": before == after},
        {"id": "complete_inventory", "pass": len(gate.SOFTWARE) == 13 and len(gate.EVALUATOR_SOFTWARE) == 9},
        {"id": "frozen_pilot_software_unchanged", "pass": all(sha(ROOT / "research" / name) == value for name, value in frozen["software_hashes"].items())},
        {"id": "active_guard_software_unchanged", "pass": all(sha(ROOT / "research" / name) == value for name, value in guard_review["reviewed_software"].items())},
    ]
    report = {"round": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all(row["pass"] for row in checks) else "FAIL", **after,
        "inventory_counts": {"online_entries": 13, "evaluation_entries": 9,
                             "unique_files": len(set(gate.SOFTWARE) | set(gate.EVALUATOR_SOFTWARE))},
        "reviewer": {"reviewer_id": "/root", "name_or_model_identity": "Codex coordinating AI reviewer",
                     "reviewer_role": "assistant_self_review"},
        "scope": "Execute contributed functional/failure-path tests against final code; does not validate investment judgment or authorize a main run.",
        "checks": checks, "candidate_bound": False, "model_calls": 0, "main_model_calls": 0,
        "independent_human_review_completed": False,
        "authorship_disclosure": "Tests and implementation are authored by collaborating AI agents; this is not an independent human audit.",
        "topic_alignment": "Public evidence -> stated rationale -> unchanged raw allocation remains the primary observation; arithmetic, source-label checks and citation resolution do not become strategic success.",
        "evidence": [ref(path) for path in OUT.iterdir() if path.is_file()],
        "test_software": [ref(ROOT / "research" / (name + ".py")) for name in MODULES],
        "auditor": ref(__file__)}
    save(OUT / "review.json", report)
    print(json.dumps({"status": report["status"], "review": str(OUT / "review.json"),
                      "suite_exit": result.returncode, "numeric_exit": second.returncode}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
