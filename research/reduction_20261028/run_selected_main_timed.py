"""Run the frozen main campaign once, with independent process timing.

Operational wrapper only: no model calls, experiment changes, or retries.
"""
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "data/v64_20261028/main_only_results/direct_main_config.json"
EXPECTED_CONFIG_SHA256 = "e868b80e67afae04b5f261b4d8efbf6b7d8219d5da8cd56acfb3325adaff01b0"
RUN_ID = "b713cc4533c2f5b18e165f51592ca8f89223977fd1e15aee202adff8bbca6b54"
OUT = CONFIG.parent
PHASE_DIR = OUT / "phases" / RUN_ID / "B-main"
KST = timezone(timedelta(hours=9))


def stamp():
    value = datetime.now(timezone.utc)
    return {"utc": value.isoformat(), "kst": value.astimezone(KST).isoformat()}


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".writing")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    deadline = time.monotonic() + 30
    while True:
        try:
            temporary.replace(path)
            return
        except OSError as exc:
            if os.name != "nt" or getattr(exc, "winerror", None) not in (5, 32, 33) or time.monotonic() >= deadline:
                raise
            time.sleep(0.05)


def main():
    if hashlib.sha256(CONFIG.read_bytes()).hexdigest() != EXPECTED_CONFIG_SHA256:
        raise RuntimeError("Frozen configuration changed; no campaign was dispatched.")
    session = OUT / "execution" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    session.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, "-u", "-m", "research.v63.campaign", str(CONFIG), "--phase", "B-main"]
    receipt = {
        "schema": "libera_timed_main_process_v1", "status": "starting",
        "run_id": RUN_ID, "command": command, "config_sha256": EXPECTED_CONFIG_SHA256,
        "planned_trajectories": 160, "planned_stage_slots": 480,
        "started_at": stamp(), "timing_clock": "time.perf_counter_ns",
        "timing_scope": "Campaign child launch through process exit, including preflight and analysis; excludes document review and server verification.",
        "automatic_retry": False, "phase_directory": str(PHASE_DIR),
        "stdout_path": str(session / "campaign.stdout.log"),
        "stderr_path": str(session / "campaign.stderr.log"),
    }
    receipt_path = session / "process_receipt.json"
    save(receipt_path, receipt)
    save(OUT / "active_execution.json", {"run_id": RUN_ID, "receipt_path": str(receipt_path), "phase_directory": str(PHASE_DIR)})
    started_ns = time.perf_counter_ns()
    try:
        with (session / "campaign.stdout.log").open("wb") as stdout, (session / "campaign.stderr.log").open("wb") as stderr:
            child = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
            receipt.update(status="running", campaign_pid=child.pid)
            save(receipt_path, receipt)
            code = child.wait()
        receipt.update(exit_code=code, elapsed_seconds=(time.perf_counter_ns() - started_ns) / 1e9, finished_at=stamp())
        analysis = json.loads((PHASE_DIR / "analysis.json").read_text(encoding="utf-8-sig")) if (PHASE_DIR / "analysis.json").exists() else {}
        measurements = json.loads((PHASE_DIR / "measurements.json").read_text(encoding="utf-8-sig")) if (PHASE_DIR / "measurements.json").exists() else {}
        receipt.update(analysis_status=analysis.get("status"), terminal_trajectories=measurements.get("terminal_trajectories"))
        complete = code == 0 and analysis.get("status") == "completed_descriptive_analysis" and measurements.get("terminal_trajectories") == 160
        receipt["status"] = "completed" if complete else "stopped_incomplete"
        save(receipt_path, receipt)
        return code if code else (0 if complete else 2)
    except Exception as exc:
        receipt.update(status="supervisor_error", error=repr(exc), observed_at=stamp(), elapsed_seconds=(time.perf_counter_ns() - started_ns) / 1e9)
        save(receipt_path, receipt)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
