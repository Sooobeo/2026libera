"""Temporary same-main-thread wakefulness, with no detached helper process."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
import os
import sys
import threading

FLAGS = 0x80000003
CLEAR = 0x80000000


def now():
    return datetime.now(timezone.utc)


class PowerStatus(ctypes.Structure):
    _fields_ = [("ACLineStatus", wintypes.BYTE), ("BatteryFlag", wintypes.BYTE),
                ("BatteryLifePercent", wintypes.BYTE), ("SystemStatusFlag", wintypes.BYTE),
                ("BatteryLifeTime", wintypes.DWORD), ("BatteryFullLifeTime", wintypes.DWORD)]


class NativeAPI:
    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("This continuation requires the reviewed Windows CPU environment")
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.SetThreadExecutionState.argtypes = [wintypes.DWORD]
        self.api.SetThreadExecutionState.restype = wintypes.DWORD
        self.api.GetSystemPowerStatus.argtypes = [ctypes.POINTER(PowerStatus)]
        self.api.GetSystemPowerStatus.restype = wintypes.BOOL

    def state(self, flags):
        result = int(self.api.SetThreadExecutionState(flags))
        if result == 0:
            raise ctypes.WinError(ctypes.get_last_error())
        return result

    def power(self):
        value = PowerStatus()
        if not self.api.GetSystemPowerStatus(ctypes.byref(value)):
            raise ctypes.WinError(ctypes.get_last_error())
        return {"at_utc": now().isoformat(), "ac_line_status": value.ACLineStatus,
                "battery_flag": value.BatteryFlag,
                "battery_percent": None if value.BatteryLifePercent == 255 else value.BatteryLifePercent,
                "battery_saver": value.SystemStatusFlag}


class CoordinatorAwake:
    def __init__(self, emit, *, api=None):
        self.api = api or NativeAPI()
        self.emit = emit
        self.owner_thread = threading.get_native_id()
        self.active = False
        self.expires = now() + timedelta(seconds=8 * 4500 + 1800)
        self.next_heartbeat = now()

    def check_thread(self):
        if threading.get_native_id() != self.owner_thread:
            raise RuntimeError("Coordinator wake ownership must stay on the acquiring main thread")

    def acquire(self):
        self.check_thread()
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("Acquire only from coordinator main thread")
        power = self.api.power()
        if power["ac_line_status"] != 1:
            raise RuntimeError("Observed AC power is required before this continuation starts")
        previous = self.api.state(FLAGS)
        self.active = True
        self.emit("coordinator_awake_acquired", helper_process_created=False, coordinator_pid=os.getpid(),
                  owner_thread_id=self.owner_thread, flags=FLAGS, previous_state=previous,
                  hard_expiry_utc=self.expires.isoformat(), power_status=power,
                  permanent_power_settings_changed=False,
                  limits="Manual sleep/lid actions remain effective. No uninterrupted execution guarantee.")

    def pulse(self, *, force=False, require_ac=False):
        self.check_thread()
        if not self.active or now() >= self.expires:
            raise RuntimeError("Coordinator awake ownership inactive or fixed total operational expiry reached")
        if force or now() >= self.next_heartbeat:
            power = self.api.power()
            previous = self.api.state(FLAGS)
            self.emit("coordinator_awake_heartbeat", coordinator_pid=os.getpid(), owner_thread_id=self.owner_thread,
                      renewal_previous_state=previous, power_status=power,
                      permanent_power_settings_changed=False)
            self.next_heartbeat = now() + timedelta(seconds=60)
            if require_ac and power["ac_line_status"] != 1:
                raise RuntimeError("AC unavailable before stage; no new generation started")

    def release(self):
        self.check_thread()
        result = {"coordinator_pid": os.getpid(), "owner_thread_id": self.owner_thread,
                  "clear_flags": CLEAR, "permanent_power_settings_changed": False,
                  "status": "no_request_acquired"}
        if self.active:
            try:
                result.update(api_previous_state=self.api.state(CLEAR), status="released")
                self.active = False
            except BaseException as exc:
                result.update(status="release_not_confirmed", error_type=type(exc).__name__, error=str(exc))
        return result
