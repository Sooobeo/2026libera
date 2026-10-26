"""Temporary same-thread wakefulness with explicit remaining-stage battery policy."""
from datetime import timedelta
import os
import threading
from sector_continuation_awake import CoordinatorAwake as ReviewedCoordinatorAwake, FLAGS, CLEAR, NativeAPI, now

MAX_OPERATIONAL_SECONDS = 5 * (4500 + 1800) + 1800
POWER_POLICY = {
    "version": "battery_aware_stage_boundary_1",
    "stage_start_minimum_battery_percent": 70,
    "in_stage_stop_at_or_below_battery_percent": 20,
    "allow_ac_online_without_battery": True,
    "allow_sufficient_battery_without_ac": True,
    "unknown_ac_rejected": True,
    "on_battery_unknown_or_critical_or_saver_rejected": True,
    "critical_or_saver_rejected_on_ac": True,
    "unknown_battery_rejected_except_ac_no_battery": True,
    "poll_interval_seconds": 60,
    "permanent_power_settings_changed": False,
}


def check_power(power, *, stage_start):
    ac, flags, percent, saver = (power.get(k) for k in
        ("ac_line_status", "battery_flag", "battery_percent", "battery_saver"))
    if type(ac) is not int or ac not in (0, 1):
        raise RuntimeError("Power status unknown: AC must be known online or offline")
    if type(saver) is not int or saver != 0:
        raise RuntimeError("Battery saver active or unknown; no continued intensive work")
    if type(flags) is not int or not 0 <= flags <= 255 or flags == 255:
        raise RuntimeError("Battery flags unknown")
    if flags & 4:
        raise RuntimeError("Critical battery flag; stop owned work")
    if flags & 128:
        if ac != 1 or flags != 128:
            raise RuntimeError("No-system-battery status requires known AC")
        return {"status": "allowed_known_AC_without_system_battery", "stage_start": stage_start}
    if type(percent) is not int or not 0 <= percent <= 100:
        raise RuntimeError("Battery percentage unknown")
    if ac == 1:
        return {"status": "allowed_known_AC", "stage_start": stage_start}
    if stage_start and percent < POWER_POLICY["stage_start_minimum_battery_percent"]:
        raise RuntimeError("Battery below fixed70percent stage-start allowance")
    if percent <= POWER_POLICY["in_stage_stop_at_or_below_battery_percent"]:
        raise RuntimeError("Battery at or below fixed20percent operating stop threshold")
    return {"status": "allowed_sufficient_battery", "stage_start": stage_start}


class CoordinatorAwake(ReviewedCoordinatorAwake):
    def __init__(self, emit, *, api=None):
        super().__init__(emit, api=api)
        self.expires = now() + timedelta(seconds=MAX_OPERATIONAL_SECONDS)
        self.last_ac = None

    def observed_power(self, *, stage_start):
        power = self.api.power()
        ac = power.get("ac_line_status")
        if self.last_ac is not None and ac != self.last_ac:
            self.emit("coordinator_power_transition", previous_ac_line_status=self.last_ac,
                      power_status=power, permanent_power_settings_changed=False)
        self.last_ac = ac
        try:
            decision = check_power(power, stage_start=stage_start)
        except BaseException as error:
            self.emit("coordinator_power_rejected", power_status=power, stage_start=stage_start,
                      error_type=type(error).__name__, error=str(error), permanent_power_settings_changed=False)
            raise
        return power, decision

    def acquire(self):
        self.check_thread()
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("Acquire only from coordinator main thread")
        power, decision = self.observed_power(stage_start=True)
        previous = self.api.state(FLAGS)
        self.active = True
        self.emit("coordinator_awake_acquired", helper_process_created=False, coordinator_pid=os.getpid(),
                  owner_thread_id=self.owner_thread, flags=FLAGS, previous_state=previous,
                  hard_expiry_utc=self.expires.isoformat(), power_status=power, power_decision=decision,
                  power_policy=POWER_POLICY, permanent_power_settings_changed=False,
                  limits="Manual sleep/lid remains effective; no uninterrupted execution guarantee.")

    def pulse(self, *, force=False, stage_start=False):
        self.check_thread()
        if not self.active or now() >= self.expires:
            raise RuntimeError("Coordinator awake ownership inactive or fixed operational expiry reached")
        if force or stage_start or now() >= self.next_heartbeat:
            power, decision = self.observed_power(stage_start=stage_start)
            previous = self.api.state(FLAGS)
            self.emit("coordinator_awake_heartbeat", coordinator_pid=os.getpid(), owner_thread_id=self.owner_thread,
                      renewal_previous_state=previous, power_status=power, power_decision=decision,
                      permanent_power_settings_changed=False)
            self.next_heartbeat = now() + timedelta(seconds=POWER_POLICY["poll_interval_seconds"])
