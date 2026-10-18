"""Temporary Windows execution-state request for an active experiment process.

Importing this module has no OS side effect. The owning runner calls acquire()
and release() in one thread and always releases in finally. No power plan is
changed. The API return records acceptance, not proof that sleep never occurred.

Primary references (accessed 2026-10-18 UTC):
https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate
https://learn.microsoft.com/en-us/windows/win32/power/about-power-management

ES_SYSTEM_REQUIRED with ES_CONTINUOUS requests working state during active work.
CPU/disk activity alone need not reset the idle timer. Modern Standby makes a
bounded lifecycle important. User sleep/lid/power actions cannot be overridden;
this helper does not guarantee uninterrupted inference or a wall-time deadline.
"""
from __future__ import annotations

from datetime import datetime, timezone
import sys
import threading

VERSION = "v48-temporary-windows-awake-1"
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
FLAGS = ES_CONTINUOUS | ES_SYSTEM_REQUIRED


def _now():
    return datetime.now(timezone.utc).isoformat()


def _set_thread_execution_state(flags):
    # Loaded only by an explicit call, never at import or by the synthetic tests.
    import ctypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    function = kernel.SetThreadExecutionState
    function.argtypes = [ctypes.c_uint32]
    function.restype = ctypes.c_uint32
    return int(function(flags))


def acquire():
    """Request temporary system wakefulness; return a serializable receipt token."""
    token = {"version": VERSION, "status": "not_requested", "at_utc": _now(),
             "owner_thread_id": threading.get_native_id(), "flags": FLAGS,
             "previous_state": None, "released": False, "platform": sys.platform,
             "permanent_power_configuration_changed": False,
             "scope": "Thread execution-state request during an active operation; not proof of uninterrupted operation.",
             "limits": "Does not prevent explicit user sleep/lid/power actions or guarantee deadline enforcement during suspend."}
    if sys.platform != "win32":
        token["status"] = "unsupported_platform"
        return token
    try:
        previous = _set_thread_execution_state(FLAGS)
        if type(previous) is not int or not 0 <= previous <= 0xFFFFFFFF:
            raise ValueError("Unexpected execution-state return type or range")
        token["previous_state"] = previous
        token["status"] = "active" if previous else "request_failed"
        if not previous:
            token["error"] = "SetThreadExecutionState returned NULL; no active request confirmed."
    except Exception as exc:
        token.update(status="request_failed", error_type=type(exc).__name__, error=str(exc))
    return token


def release(token):
    """Restore the recorded prior state from the same thread; never hide failure.

    In a fresh runner the prior state is ES_CONTINUOUS, so this clears our system
    requirement. If that thread already had a requirement, preserve it. This is
    an execution-state restoration only, not a permanent power setting change.
    """
    result = {"version": VERSION, "status": "not_released", "at_utc": _now(),
              "owner_thread_id": threading.get_native_id(), "restore_flags": None,
              "permanent_power_configuration_changed": False}
    if not isinstance(token, dict) or token.get("version") != VERSION:
        return result | {"status": "invalid_token"}
    if token.get("released") is True:
        return result | {"status": "already_released"}
    if token.get("status") != "active":
        return result | {"status": "no_active_request"}
    if token.get("owner_thread_id") != result["owner_thread_id"]:
        return result | {"status": "wrong_thread", "error": "Release must run on the acquiring thread."}
    prior = token.get("previous_state")
    if type(prior) is not int or not 0 < prior <= 0xFFFFFFFF or sys.platform != "win32":
        return result | {"status": "invalid_token_or_platform"}
    result["restore_flags"] = prior | ES_CONTINUOUS
    try:
        previous = _set_thread_execution_state(result["restore_flags"])
        if type(previous) is not int or not 0 <= previous <= 0xFFFFFFFF:
            raise ValueError("Unexpected execution-state return type or range")
        result["api_previous_state"] = previous
        result["status"] = "released" if previous else "release_failed"
        if previous:
            token["released"] = True
        else:
            result["error"] = "SetThreadExecutionState returned NULL; restoration not confirmed."
    except Exception as exc:
        result.update(status="release_failed", error_type=type(exc).__name__, error=str(exc))
    return result
