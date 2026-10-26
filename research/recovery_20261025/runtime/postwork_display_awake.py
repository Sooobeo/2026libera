"""One bounded postprocessing awake request; no persistent power changes."""
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

from temporary_display_awake import Windows, FLAGS, ES_CONTINUOUS

HERE = Path(__file__).resolve().parent
FOLDER = HERE / "postwork_awake_01"
VERSION = "postwork_display_awake_1"


def now():
    return datetime.now(timezone.utc)


def ref(path):
    raw = path.read_bytes()
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest()}


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n"); stream.flush(); os.fsync(stream.fileno())


def main():
    config_path = FOLDER / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    launched = datetime.fromisoformat(config["launched_at_utc"])
    expiry = datetime.fromisoformat(config["hard_expiry_utc"])
    if (config["version"] != VERSION or config["flags"] != FLAGS
            or Path(config["code_ref"]["path"]).resolve() != Path(__file__).resolve()
            or config["code_ref"]["sha256"] != ref(Path(__file__))["sha256"]
            or Path(config["native_api_ref"]["path"]).resolve() != (HERE / "temporary_display_awake.py").resolve()
            or config["native_api_ref"]["sha256"] != ref(HERE / "temporary_display_awake.py")["sha256"]
            or Path(config["python"]).resolve() != Path(sys.executable).resolve()
            or expiry != launched + timedelta(minutes=30) or expiry <= now()
            or launched > now() + timedelta(seconds=5)
            or (FOLDER / "STOP").exists()):
        raise ValueError("Postwork helper ownership/code/expiry configuration mismatch")
    api = Windows()
    active, reason, next_heartbeat = False, "exception", now()
    try:
        previous = api.state(FLAGS)
        active = True
        write(FOLDER / "acquire.json", {"version": VERSION, "status": "active",
            "at_utc": now().isoformat(), "helper_pid": os.getpid(),
            "owner_thread_id": threading.get_native_id(), "flags": FLAGS,
            "previous_state": previous, "hard_expiry_utc": expiry.isoformat(),
            "code_ref": ref(Path(__file__)), "config_ref": ref(config_path),
            "power_status": api.power(), "scope": config["scope"],
            "persistent_power_settings_changed": False, "model_calls": 0})
        while True:
            if (FOLDER / "STOP").exists():
                reason = "explicit_postwork_stop"; break
            if now() >= expiry:
                reason = "absolute_30minute_expiry"; break
            if now() >= next_heartbeat:
                previous = api.state(FLAGS)
                with (FOLDER / "heartbeat.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"at_utc": now().isoformat(), "helper_pid": os.getpid(),
                        "owner_thread_id": threading.get_native_id(), "renewal_previous_state": previous,
                        "power_status": api.power()}) + "\n")
                    stream.flush()
                next_heartbeat = now() + timedelta(seconds=60)
            time.sleep(2)
    except BaseException as exc:
        write(FOLDER / "failure.json", {"at_utc": now().isoformat(), "error": repr(exc), "acquired": active})
        raise
    finally:
        receipt = {"version": VERSION, "at_utc": now().isoformat(), "helper_pid": os.getpid(),
            "owner_thread_id": threading.get_native_id(), "reason": reason, "acquired": active,
            "clear_flags": ES_CONTINUOUS, "power_status": api.power(),
            "persistent_power_settings_changed": False, "model_calls": 0}
        try:
            if active:
                receipt["api_previous_state"] = api.state(ES_CONTINUOUS)
                receipt["status"] = "released"
            else:
                receipt["status"] = "no_request_acquired"
        except BaseException as exc:
            receipt.update(status="release_not_confirmed", error=repr(exc))
        write(FOLDER / "release.json", receipt)


if __name__ == "__main__":
    main()
