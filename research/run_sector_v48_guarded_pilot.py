"""One explicitly registered repeat of the unchanged four-case development pilot.

Only operating change: a thread-scoped Windows idle-sleep request. Model inputs,
fixed case order, C0/auxiliary rules and original runner bytes remain unchanged.
Manual sleep/lid closing cannot be prevented. Prior observations remain separate.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import run_sector_v48 as pilot
import sector_v48_main_awake as awake

ROOT = Path(__file__).resolve().parents[1]
SOFTWARE = ("run_sector_v48_guarded_pilot.py", "sector_v48_main_awake.py")


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def resolve(path):
    path = Path(path)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def ref(path):
    path = resolve(path)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def checked(item):
    path = resolve(item["path"])
    if ref(path)["sha256"] != item["sha256"]:
        raise ValueError("Changed registered artifact: " + str(path))
    return path


def save_new(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def verify_operation(args):
    manifest, registration = resolve(args.manifest), resolve(args.registration)
    pilot.verify_manifest(manifest)
    reg = pilot.verify_registration(registration, manifest)
    operation_path = checked(reg["operating_addendum"])
    operation = read(operation_path)
    if (operation["kind"] != "one_explicit_sleep_disrupted_pilot_repeat"
            or operation["main_authorized"] is not False
            or operation["automatic_retries"] != 0
            or operation["repeat_bundle_limit"] != 1
            or operation["roster"] != list(pilot.ROSTER)
            or checked(operation["manifest"]) != manifest
            or resolve(operation["new_run_root"]) != resolve(args.output)
            or resolve(operation["guard_record_root"]) != resolve(args.guard_output)):
        raise ValueError("Operating addendum does not authorize this fixed pilot repeat")
    prior = checked(operation["prior_run_summary"])
    if read(prior)["status"] == "running" or prior.parent == resolve(args.output):
        raise ValueError("Prior pilot must be terminal and retained separately")
    if read(prior).get("main_model_calls") != 0:
        raise ValueError("Expected pilot-only predecessor")
    expected = {name: ref(ROOT / "research" / name)["sha256"] for name in SOFTWARE}
    if operation["operating_software_hashes"] != expected:
        raise ValueError("Operating wrapper or awake helper changed")
    reviews = [read(checked(item)) for item in operation["operating_reviews"]]
    if len(reviews) != 3 or [x["round"] for x in reviews] != [1, 2, 3]:
        raise ValueError("Three ordered operating reviews required")
    if any(x["status"] != "PASS" or x["reviewed_software"] != expected for x in reviews):
        raise ValueError("All operating reviews must cover these exact code bytes")
    prior_reviews = [read(checked(item)) for item in operation["prior_run_reviews"]]
    if len(prior_reviews) != 3 or [x["round"] for x in prior_reviews] != [1, 2, 3]:
        raise ValueError("Preserve three preceding-run reviews, including failures")
    for item in operation["environment_evidence"]:
        checked(item)
    target, guard = resolve(args.output), resolve(args.guard_output)
    if target.exists() or guard.exists() or target == guard or guard.is_relative_to(target) or target.is_relative_to(guard):
        raise ValueError("Use new separate run and operating-record folders")
    for protected in (prior.parent, manifest.parent):
        if any(output.is_relative_to(protected) or protected.is_relative_to(output) for output in (target, guard)):
            raise ValueError("Preserve original pilot and prepared input directories")
    return operation_path, operation


def run(args):
    operation_path, operation = verify_operation(args)
    guard = resolve(args.guard_output)
    guard.mkdir(parents=True, exist_ok=False)
    save_new(guard / "invocation.json", {"at_utc": now(), "operation": ref(operation_path),
        "registration": ref(args.registration), "run_root": str(resolve(args.output)),
        "model_calls_by_wrapper": 0, "main_model_calls": 0})
    token = awake.acquire()
    if token.get("status") != "active":
        save_new(guard / "acquire.json", {"at_utc": now(), "request": token})
        save_new(guard / "summary.json", {"at_utc": now(), "status": "not_started_awake_request_failed",
            "model_calls_by_wrapper": 0, "main_model_calls": 0, "permanent_power_settings_changed": False})
        raise RuntimeError("Windows idle-sleep protection was not acquired; pilot not started")
    result, error = None, None
    try:
        save_new(guard / "acquire.json", {"at_utc": now(), "request": token})
        # No monkeypatching, history rewriting, per-case selection or automatic retry.
        result = pilot.run(args)
        return result
    except BaseException as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        released = awake.release(token)
        save_new(guard / "release.json", {"at_utc": now(), "request": released})
        save_new(guard / "summary.json", {"at_utc": now(), "status": ("awake_restoration_failed" if released.get("status") != "released" else "pilot_returned" if error is None else "pilot_raised"),
            "pilot_exit_code": result, "error": error, "awake_release": released,
            "operation": ref(operation_path), "model_calls_by_wrapper": 0, "main_model_calls": 0,
            "permanent_power_settings_changed": False,
            "limits": "Idle-sleep request only; user-initiated sleep/lid closing and power loss remain possible. No claim of empirical success."})
        if released.get("status") != "released" and error is None:
            raise RuntimeError("Pilot ended but awake-state restoration was not confirmed; inspect operating record")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "registration", "output", "guard-output", "server-log"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
