"""Synthetic lifecycle plus short real OS request verification; zero model calls."""
import ctypes
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

import run_sector_v48_guarded_pilot as wrapper
import sector_v48_main_awake as awake

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/evidence/v48_guarded_repeat_20261019/round1"


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, "-B", "-X", "utf8", "-m", "unittest",
               "test_run_sector_v48_guarded_pilot", "test_sector_v48_main_awake", "-v"]
    result = subprocess.run(command, cwd=ROOT / "research", capture_output=True)
    (OUT / "tests.stdout.bin").write_bytes(result.stdout)
    (OUT / "tests.stderr.bin").write_bytes(result.stderr)
    wrapper.save_new(OUT / "tests_invocation.json", {"at_utc": wrapper.now(), "argv": command,
        "exit_code": result.returncode, "kind": "18 synthetic tests; no power or model API in unittest"})

    class PowerStatus(ctypes.Structure):
        _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                    ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                    ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
    state = PowerStatus()
    power_ok = ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(state))
    power = {"api_success": bool(power_ok), **{name: getattr(state, name) for name, _ in state._fields_}}
    wrapper.save_new(OUT / "power_status.json", power)
    token = awake.acquire()
    try:
        wrapper.save_new(OUT / "actual_acquire.json", token)
        query = subprocess.run(["powercfg", "/requests"], capture_output=True)
        (OUT / "powercfg_requests.stdout.bin").write_bytes(query.stdout)
        (OUT / "powercfg_requests.stderr.bin").write_bytes(query.stderr)
        wrapper.save_new(OUT / "powercfg_query.json", {"at_utc": wrapper.now(), "exit_code": query.returncode,
            "scope": "Read-only current request listing while this process owns the request."})
    finally:
        released = awake.release(token)
        wrapper.save_new(OUT / "actual_release.json", released)
    manifest_path = ROOT / "data/sector_protocol/v48_pilot_r2_20261018/manifest.json"
    manifest = wrapper.read(manifest_path)
    frozen = {name: wrapper.ref(ROOT / "research" / name)["sha256"] == sha
              for name, sha in manifest["software_hashes"].items()}
    checks = [
        {"check": "18 synthetic lifecycle cases", "pass": result.returncode == 0},
        {"check": "Actual OS request accepted", "pass": token["status"] == "active"},
        {"check": "Actual OS request released", "pass": released["status"] == "released"},
        {"check": "Original pilot code unchanged", "pass": all(frozen.values()), "details": frozen},
        {"check": "No permanent power configuration change", "pass": not token["permanent_power_configuration_changed"]},
        {"check": "Research contract unchanged", "pass": True,
         "basis": "Wrapper invokes the frozen four-case coordinator once; no model/body/feedback/selection edits."},
    ]
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "round": 1,
        "status": "PASS" if all(x["pass"] for x in checks) else "FAIL",
        "reviewer_role": "author_AI_with_deterministic_and_OS_checks",
        "reviewed_software": {name: wrapper.ref(ROOT / "research" / name)["sha256"] for name in wrapper.SOFTWARE},
        "checks": checks, "model_calls": 0, "main_model_calls": 0,
        "scope": "Operational wrapper validation; not independent human review or proof of no future suspend.",
        "topic_alignment": "Same public judgment -> interpretation/reason -> raw allocation observations. Sleep handling is operational support, not a paper-derived strategic threshold.",
        "limits": "The short OS check verifies accepted/released state. It is not a full-duration sleep test and cannot prevent user-initiated sleep or lid closure.",
        "power_status": power,
        "evidence": [wrapper.ref(path) for path in OUT.iterdir() if path.is_file()]}
    wrapper.save_new(OUT / "review.json", report)
    print(json.dumps({"status": report["status"], "power": power, "output": str(OUT / "review.json")}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
