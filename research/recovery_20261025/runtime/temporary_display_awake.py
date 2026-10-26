"""Bounded, coordinator-owned display/system request; no persistent power change.

Runs on one live thread. Stops on exact coordinator-handle exit, terminal receipt,
STOP marker or absolute expiry. No input simulation, away mode or model calls.
"""
from __future__ import annotations
import argparse
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
ES_CONTINUOUS = 0x80000000
FLAGS = ES_CONTINUOUS | 0x1 | 0x2
WAIT_OBJECT_0, WAIT_TIMEOUT = 0, 258
VERSION = "v494_coordinator_temporary_display_awake_1"


def now():
    return datetime.now(timezone.utc)


def ref(path):
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, obj):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(obj, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n"); stream.flush(); os.fsync(stream.fileno())


class PowerStatus(C.Structure):
    _fields_ = [("ACLineStatus", C.c_ubyte), ("BatteryFlag", C.c_ubyte),
                ("BatteryLifePercent", C.c_ubyte), ("SystemStatusFlag", C.c_ubyte),
                ("BatteryLifeTime", W.DWORD), ("BatteryFullLifeTime", W.DWORD)]


class Windows:
    def __init__(self):
        if os.name != "nt":
            raise RuntimeError("Windows is required")
        self.api = C.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "OpenProcess": ([W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            "GetProcessTimes": ([W.HANDLE, C.POINTER(W.FILETIME), C.POINTER(W.FILETIME), C.POINTER(W.FILETIME), C.POINTER(W.FILETIME)], W.BOOL),
            "QueryFullProcessImageNameW": ([W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)], W.BOOL),
            "WaitForSingleObject": ([W.HANDLE, W.DWORD], W.DWORD),
            "CloseHandle": ([W.HANDLE], W.BOOL),
            "SetThreadExecutionState": ([W.DWORD], W.DWORD),
            "GetSystemPowerStatus": ([C.POINTER(PowerStatus)], W.BOOL),
        }
        for name, (args, result) in signatures.items():
            getattr(self.api, name).argtypes = args
            getattr(self.api, name).restype = result

    def open(self, pid):
        handle = self.api.OpenProcess(0x00100000 | 0x1000, False, pid)
        if not handle:
            raise C.WinError(C.get_last_error())
        return handle

    def identity(self, handle, pid):
        times = [W.FILETIME() for _ in range(4)]
        if not self.api.GetProcessTimes(handle, *[C.byref(t) for t in times]):
            raise C.WinError(C.get_last_error())
        ticks = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        size = W.DWORD(32768); name = C.create_unicode_buffer(size.value)
        if not self.api.QueryFullProcessImageNameW(handle, 0, name, C.byref(size)):
            raise C.WinError(C.get_last_error())
        created = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=ticks // 10)
        return {"pid": pid, "executable": name.value, "creation_filetime_100ns": ticks,
                "creation_utc": created.isoformat()}

    def power(self):
        status = PowerStatus()
        if not self.api.GetSystemPowerStatus(C.byref(status)):
            return {"status": "unavailable", "winerror": C.get_last_error()}
        return {"status": "observed", "at_utc": now().isoformat(),
                "ac_line_status": status.ACLineStatus,
                "ac_interpretation": {0: "offline", 1: "online", 255: "unknown"}.get(status.ACLineStatus, "unrecognized"),
                "battery_flag": status.BatteryFlag,
                "battery_percent": None if status.BatteryLifePercent == 255 else status.BatteryLifePercent,
                "battery_saver": status.SystemStatusFlag,
                "battery_lifetime_seconds": None if status.BatteryLifeTime == 0xffffffff else status.BatteryLifeTime,
                "battery_full_lifetime_seconds": None if status.BatteryFullLifeTime == 0xffffffff else status.BatteryFullLifeTime}

    def state(self, flags):
        previous = int(self.api.SetThreadExecutionState(flags))
        if previous == 0:
            raise C.WinError(C.get_last_error())
        return previous


def live_stage(run):
    stages = [p for p in run.iterdir() if p.is_dir() and p.name.endswith(("__D0", "__F0"))]
    active = [p.name for p in stages if not (p / "transport_result.json").exists()]
    return {"active_stage_directories": sorted(active), "existing_stage_count": len(stages)}


def inspect(launch_path):
    def trace(message):
        print(now().isoformat() + " inspect " + message, file=sys.stderr, flush=True)
    trace("read_launch")
    launch = read(launch_path)
    if launch.get("coordinator_pid") != 35216 or launch.get("origin") != "http://127.0.0.1:11435":
        raise ValueError("Only the current explicitly assigned coordinator is allowed")
    trace("initialize_native_api")
    api = Windows(); handle = api.open(launch["coordinator_pid"])
    try:
        trace("check_handle_and_identity")
        if api.api.WaitForSingleObject(handle, 0) != WAIT_TIMEOUT:
            raise RuntimeError("Coordinator is not active")
        identity = api.identity(handle, launch["coordinator_pid"])
        trace("compare_receipt_identity")
        if Path(identity["executable"]).resolve() != Path(launch["python"]).resolve():
            raise ValueError("Coordinator executable differs from launch receipt")
        created = datetime.fromisoformat(identity["creation_utc"])
        launched = datetime.fromisoformat(launch["launched_at_utc"].replace("Z", "+00:00"))
        if abs((created - launched).total_seconds()) > 10:
            raise ValueError("Coordinator creation is inconsistent with launch receipt")
        expected_script = (ROOT / "research/run_v494_recovery.py").resolve()
        if not any(Path(arg).resolve() == expected_script for arg in launch["arguments"]
                   if isinstance(arg, str) and arg.endswith(".py")):
            raise ValueError("Coordinator script differs from reviewed launch")
        trace("read_power_status")
        power_status = api.power()
        trace("record_inspection")
        return {"version": VERSION, "recorded_at_utc": now().isoformat(),
                "launch_ref": ref(launch_path), "coordinator_identity": identity,
                "hard_expiry_utc": (launched + timedelta(hours=13)).isoformat(),
                "power_status": power_status, "stage": live_stage(Path(launch["run_directory"])),
                "requested_flags": FLAGS, "generation_calls": 0, "power_state_changed": False}
    finally:
        api.api.CloseHandle(handle)


def run(config_path):
    config = read(config_path); folder = config_path.parent
    if folder != HERE / "temporary_awake_01":
        raise ValueError("Only dedicated new temporary helper folder is allowed")
    identity = config["coordinator_identity"]
    launch_path = Path(config["launch_ref"]["path"])
    if ref(launch_path) != config["launch_ref"] or config.get("requested_flags") != FLAGS:
        raise ValueError("Launch receipt or requested flags changed")
    launch = read(launch_path)
    terminal = Path(launch["report_directory"]) / "terminal_receipt.json"
    expiry = datetime.fromisoformat(config["hard_expiry_utc"])
    launched = datetime.fromisoformat(launch["launched_at_utc"].replace("Z", "+00:00"))
    if (config.get("version") != VERSION or identity["pid"] != launch["coordinator_pid"]
            or expiry != launched + timedelta(hours=13)):
        raise ValueError("Bound coordinator identity or fixed hard expiry changed")
    if expiry <= now() or terminal.exists():
        raise RuntimeError("Coordinator already terminal or helper expiry reached")
    api = Windows(); handle = api.open(identity["pid"])
    acquired, previous, reason = False, None, "exception"
    started = now(); next_heartbeat = started
    code_ref = ref(Path(__file__))
    try:
        if api.identity(handle, identity["pid"]) != identity or api.api.WaitForSingleObject(handle, 0) != WAIT_TIMEOUT:
            raise ValueError("Exact coordinator PID/creation/executable identity differs")
        previous = api.state(FLAGS); acquired = True
        write(folder / "acquire.json", {"version": VERSION, "status": "active",
            "at_utc": now().isoformat(), "helper_pid": os.getpid(), "owner_thread_id": threading.get_native_id(),
            "flags": FLAGS, "previous_state": previous, "code_ref": code_ref, "config_ref": ref(config_path),
            "coordinator_identity": identity, "hard_expiry_utc": expiry.isoformat(),
            "operational_amendment_stage": live_stage(Path(launch["run_directory"])),
            "power_status": api.power(), "persistent_power_settings_changed": False,
            "frozen_runtime_changed": False, "generation_calls": 0,
            "scope": "Temporary display/system request on this live thread; not evidence of guaranteed continuity. Manual sleep/lid/power actions are respected."})
        while True:
            if terminal.exists():
                reason = "coordinator_terminal_receipt"; break
            if now() >= expiry:
                reason = "absolute_hard_expiry"; break
            if (folder / "STOP").exists():
                reason = "explicit_helper_stop_marker"; break
            status = api.api.WaitForSingleObject(handle, 2000)
            if status == WAIT_OBJECT_0:
                reason = "bound_coordinator_exited"; break
            if status != WAIT_TIMEOUT:
                raise C.WinError(C.get_last_error())
            if now() >= next_heartbeat:
                renewal_previous = api.state(FLAGS)
                with (folder / "heartbeat.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"at_utc": now().isoformat(), "helper_pid": os.getpid(),
                        "owner_thread_id": threading.get_native_id(), "renewal_previous_state": renewal_previous,
                        "coordinator_handle_active": True, "power_status": api.power()}) + "\n")
                    stream.flush()
                next_heartbeat = now() + timedelta(seconds=60)
    except BaseException as exc:
        write(folder / "failure.json", {"at_utc": now().isoformat(), "error": repr(exc), "acquired": acquired})
        raise
    finally:
        release = {"version": VERSION, "at_utc": now().isoformat(), "reason": reason,
                   "helper_pid": os.getpid(), "owner_thread_id": threading.get_native_id(),
                   "coordinator_identity": identity, "acquired": acquired,
                   "clear_flags": ES_CONTINUOUS, "persistent_power_settings_changed": False,
                   "generation_calls": 0, "power_status": api.power()}
        try:
            if acquired:
                release["api_previous_state"] = api.state(ES_CONTINUOUS)
                release["status"] = "released"
            else:
                release["status"] = "no_request_acquired"
        except BaseException as exc:
            release.update(status="release_not_confirmed", error=repr(exc))
        finally:
            api.api.CloseHandle(handle)
            write(folder / "release.json", release)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("inspect", "run", "bootstrap"))
    parser.add_argument("path", type=Path)
    arguments = parser.parse_args()
    if arguments.mode == "inspect":
        print(json.dumps(inspect(arguments.path), ensure_ascii=False))
    elif arguments.mode == "bootstrap":
        # Exactly one explicit launcher owns this new config name. Inspection
        # verifies the live PID/executable/creation against the launch receipt
        # before any execution-state request, then run binds the exact FILETIME.
        config_path = HERE / "temporary_awake_01/config.json"
        configuration = inspect(arguments.path)
        write(config_path, configuration)
        run(config_path)
    else:
        run(arguments.path)
