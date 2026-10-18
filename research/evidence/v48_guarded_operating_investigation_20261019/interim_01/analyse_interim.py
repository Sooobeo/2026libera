"""Reproduce an interim read-only operating comparison from captured prefixes."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def reference(path):
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def rows(path):
    result, partial = [], False
    for index, line in enumerate(path.read_bytes().splitlines()):
        try:
            result.append(json.loads(line.decode("utf-8")))
        except (ValueError, UnicodeError):
            partial = True
            break
    return result, partial


def xml_data(value):
    return {row.attrib.get("Name"): row.text for row in ET.fromstring(value).findall(
        ".//{http://schemas.microsoft.com/win/2004/08/events/event}Data")}


def describe_samples(samples, start, end):
    inside = [row for row in samples if start <= instant(row["at_utc"]) <= end]
    overlaps = [(left, right) for left, right in zip(samples, samples[1:])
                if instant(right["at_utc"]) >= start and instant(left["at_utc"]) <= end]
    gaps = [{"previous_at_utc": left["at_utc"], "next_at_utc": right["at_utc"],
             "utc_gap_seconds": (instant(right["at_utc"]) - instant(left["at_utc"])).total_seconds(),
             "recorded_elapsed_gap_seconds": right["elapsed_seconds"] - left["elapsed_seconds"]}
            for left, right in overlaps]
    return {"observed_samples_inside": len(inside), "first_inside": inside[0] if inside else None,
            "last_inside": inside[-1] if inside else None,
            "largest_adjacent_gap_intersecting_window": max(gaps, key=lambda x: x["utc_gap_seconds"]) if gaps else None,
            "no_gap_threshold_or_active_cpu_duration_inferred": True}


query = read(HERE / "event_query.json")
events = read(HERE / "windows_system_events.json")
for event in events:
    event["decoded_event_data"] = xml_data(event["xml"])
windows = []
for entering in (row for row in events if row["event_id"] == 506):
    later = [row for row in events if row["event_id"] == 507
             and instant(row["time_created_utc"]) > instant(entering["time_created_utc"])]
    leaving = later[0] if later else None
    start = instant(entering["time_created_utc"])
    end = instant(leaving["time_created_utc"] if leaving else query["query_started_at_utc"])
    observations = []
    for path in sorted((HERE / "captured_run_prefix").rglob("events.jsonl")):
        if path.parent.name != "http_0001_generation":
            continue
        values, partial = rows(path)
        samples = [{"at_utc": row["event"]["created_at"], "elapsed_seconds": row["elapsed_seconds"],
                    "has_content": bool(row["event"].get("message", {}).get("content")),
                    "done": row["event"].get("done")}
                   for row in values if row.get("event", {}).get("created_at")]
        if not samples or instant(samples[-1]["at_utc"]) < start or instant(samples[0]["at_utc"]) > end:
            continue
        observed = describe_samples(samples, start, end)
        monitor_path = path.parents[1] / "monitor.jsonl"
        monitor, monitor_partial = rows(monitor_path)
        monitors = [{"at_utc": row["memory"]["observed_at_utc"], "elapsed_seconds": row["elapsed_seconds"]}
                    for row in monitor if row.get("memory", {}).get("observed_at_utc")]
        observed.update({"endpoint": path.parents[1].name, "case_id": path.parents[2].name,
                         "generation_events_ref": reference(path), "raw_wire_ref": reference(path.with_name("raw_stream.bin")),
                         "captured_event_tail_incomplete": partial, "monitor_tail_incomplete": monitor_partial,
                         "monitor_ref": reference(monitor_path), "monitor_window": describe_samples(monitors, start, end),
                         "captured_generation_first": samples[0], "captured_generation_last": samples[-1],
                         "generation_event_count_is_not_a_token_count": True})
        supervisor = path.parents[1] / "supervisor_result.json"
        if supervisor.is_file():
            value = read(supervisor)
            observed["captured_terminal_supervisor"] = {"ref": reference(supervisor), "status": value.get("status"),
                "elapsed_seconds": value.get("elapsed_seconds"), "configured_deadline_seconds": value.get("deadline_seconds"),
                "worker_status": value.get("worker", {}).get("status"),
                "worker_system_integrity_incident": value.get("worker", {}).get("system_integrity_incident")}
        observations.append(observed)
    windows.append({"entry_record_id": entering["record_id"], "entry_utc": entering["time_created_utc"],
                    "entry_xml_data": entering["decoded_event_data"],
                    "exit_record_id": leaving["record_id"] if leaving else None,
                    "exit_utc": leaving["time_created_utc"] if leaving else None,
                    "exit_xml_data": leaving["decoded_event_data"] if leaving else None,
                    "window_end_for_comparison_utc": end.isoformat(), "right_censored_at_os_query": leaving is None,
                    "observations": observations})

first = windows[0]
assert first["exit_xml_data"]["SleepEntered"] == "false"
assert first["exit_xml_data"]["SleepDurationInUs"] == "0"
assert first["exit_xml_data"]["DripsResidencyInUs"] == "0"
assert first["exit_xml_data"]["PowerStateAc"] == "true"
assert any(item["observed_samples_inside"] > 0 and item["monitor_window"]["observed_samples_inside"] > 0
           for item in first["observations"])

guard_refs = []
for name in ("acquire.json", "invocation.json"):
    source = ROOT / "data/local_sector_runtime/pilot_v48_guarded_20261019_operating" / name
    target = HERE / ("guard_" + name)
    with target.open("xb") as handle:
        handle.write(source.read_bytes())
    guard_refs.append({"source": str(source), "capture": reference(target)})

report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "status": "INTERIM_OBSERVATION_NOT_FINAL_AUDIT",
          "run_root": str(ROOT / "data/local_sector_runtime/pilot_v48_guarded_20261019"),
          "model_calls_by_investigation": 0, "power_settings_changed": False, "run_or_guard_changed": False,
          "event_capture": reference(HERE / "windows_system_events.json"), "query": reference(HERE / "event_query.json"),
          "stream_capture_inventory": reference(HERE / "stream_capture_inventory.json"), "guard_captures": guard_refs,
          "windows": windows,
          "first_complete_window_conclusion": "The exit XML directly reports SleepEntered=false, SleepDurationInUs=0 and zero DRIPS residency while on AC. Generation and monitor observations inside the same window show continuing recorded activity. The 506/507 pair therefore does not establish a suspended inference or an instrument failure in this completed stage.",
          "second_window_conclusion": "No matching 507 was captured by the event-query cutoff. Observed samples within the censored window are reported, but final Sleep/Screen Off accounting and final instrument verdict remain pending.",
          "official_sources": [
              {"url": "https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/prepare-software-for-modern-standby",
               "accessed_date_utc": "2026-10-18", "page_updated": "2021-12-22",
               "supported_context": "Modern Standby begins with display-off. Software passes through preparation phases before desktop suspension. Outstanding power requests can retain the No-CS phase on AC power until cleared; this explains why a display-off session can retain active work."},
              {"url": "https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/modern-standby-sleepstudy",
               "accessed_date_utc": "2026-10-18", "page_updated": "2022-06-21",
               "supported_context": "The overall session is a screen-off to screen-on interval. Modern SleepStudy distinguishes Screen Off preparation from the long-term low-power Sleep state. A session-level marker alone therefore does not quantify suspended application time."}],
          "limits": ["This is a running-prefix observation and cannot substitute for the terminal pilot audit.",
                     "No continuity, ideal throughput or zero scheduling pauses is certified. No arbitrary event-gap cutoff is introduced.",
                     "Elapsed wall time is not active CPU time, and a Modern Standby duration is not automatically lost inference time.",
                     "No model outcome, source interpretation, arithmetic value or case denominator is changed by this operating investigation."]}
with (HERE / "interim_analysis.json").open("x", encoding="utf-8") as handle:
    handle.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"report": reference(HERE / "interim_analysis.json"), "windows": [
    {"entry": window["entry_utc"], "exit": window["exit_utc"], "endpoints": [
        {"endpoint": item["endpoint"], "samples_inside": item["observed_samples_inside"],
         "largest_gap": item["largest_adjacent_gap_intersecting_window"],
         "monitor_samples_inside": item["monitor_window"]["observed_samples_inside"]}
        for item in window["observations"]]} for window in windows]}, ensure_ascii=False))
