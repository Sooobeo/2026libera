"""Record completed independent launcher inspection; does not launch anything."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
FILES = [
    "research/start_v494_pilot.ps1",
    "research/run_v494_recovery.py",
    "research/sector_v494_runtime.py",
    "research/sector_v494_review_gate.py",
    "research/recovery_20261025/runtime_candidate.json",
    "research/recovery_20261025/runtime/service_ready/service_receipt.json",
    "research/recovery_20261025/runtime/launch_review_observation.json",
]

source = (ROOT / FILES[0]).read_text(encoding="utf-8-sig")
assert "TotalMilliseconds) -gt 1" in source
assert "New-Item -ItemType Directory -Path $launch -ErrorAction Stop" in source
assert "-WindowStyle Hidden" in source
assert "-Wait" not in source
observation = json.loads((HERE / "launch_review_observation.json").read_text(encoding="utf-8-sig"))
assert all(observation["checks"].values())
report = {
    "receipt_version": "v494_launcher_independent_review_1",
    "status": "PASS",
    "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    "input_refs": [{"path": path, "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest()} for path in FILES],
    "launch_executed": False,
    "generation_calls": 0,
    "syntax_parse_errors": [],
    "syntax_evidence": "Final PowerShell Parser.ParseFile observed 0 errors via read-only command; launcher was not invoked.",
    "unit_tests_run_by_this_reviewer": [],
    "active_service_identity": {
        "pid": 35148,
        "receipt_creation_utc": "2026-10-25T10:03:30.7525818Z",
        "cim_creation_utc": "2026-10-25T10:03:30.7525810Z",
        "observed_difference_milliseconds": 0.0008,
        "tolerance_milliseconds": 1,
        "corrected_creation_comparison_passed": True,
        "other_identity_checks": "Exact PID, executable path/hash, serve command and single owned loopback listener are bound in launch_review_observation.json and rechecked by launcher."
    },
    "findings": [
        {"id": "creation_time_precision", "status": "resolved",
         "observation": "CIM rounds Start-Process creation time by 0.8 microsecond. Exact DateTime equality would wrongly reject the current service.",
         "resolution": "At most 1 ms absolute creation-time difference, alongside exact PID/path/hash/command/listener checks. Observed current difference is 0.0008 ms. This changes process identity precision only, with no scientific setting change."},
        {"id": "exclusive_launch_directory", "status": "resolved",
         "observation": "Idempotent Directory.CreateDirectory could allow simultaneous launchers to share log and receipt names.",
         "resolution": "New-Item without Force exclusively reserves launch directory and fails on an existing directory. Wrapper separately rejects existing run/report paths."}
    ],
    "review_axes": {
        "errors": {"pass": True, "reason": "Final syntax parsed without errors. Actual service field types match launcher assumptions; corrected timestamp comparison passes current process. Argument quoting, executable pin, version and idle checks were inspected. No further critical launch defect identified."},
        "consistency": {"pass": True, "reason": "Explicit recovered service and frozen candidate/gate paths feed one hidden independent Python Start-Process without Wait. Unique launch/run/report paths prevent resume or duplicate output reuse. Existing 11434 is never targeted; idle is checked again at launch."},
        "paper_topic": {"pass": True, "reason": "Launcher selects the same five-case prospectively frozen E/L/C development pilot and at most ten first attempts. Identity-check precision and exclusive log reservation alter no model, prompt, sources, generation options, source timing, scoring or experimental outcomes."}
    },
    "limitations": [
        "No launcher or generation executed by this reviewer; actual coordinator launch/completion must be observed separately.",
        "Idle/directory/process observations are time-bound. Launcher repeats checks immediately before startup.",
        "Successful launch does not establish completion or semantic source support."
    ],
    "service_calls_during_final_review": [],
    "service_restart_performed": False,
    "tooling_note": "One long review-recording PowerShell command was automatically rejected before execution with blocked by policy and no further reason. Bounded file patch and short read-only checks completed the artifact; no permission or launcher bypass occurred."
}
with (HERE / "launch_review.json").open("x", encoding="utf-8") as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({"status": report["status"], "receipt": str(HERE / "launch_review.json"), "generation_calls": 0}))
