"""Read-only final operating analysis of the stopped guarded pilot, no API calls."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
RUN = ROOT / "data/local_sector_runtime/pilot_v48_guarded_20261019"
GUARD = ROOT / "data/local_sector_runtime/pilot_v48_guarded_20261019_operating"
CONSULTED = {}


def ref(path):
    path = path.resolve()
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    assert path not in CONSULTED or CONSULTED[path] == sha
    CONSULTED[path] = sha
    return {"path": str(path), "sha256": sha}


def read(path):
    ref(path)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def lines(path):
    ref(path)
    result, partial = [], False
    for line in path.read_bytes().splitlines():
        try:
            result.append(json.loads(line))
        except (ValueError, UnicodeError):
            partial = True
            break
    return result, partial


def xml_fields(row):
    return {d.attrib.get("Name", str(i)): d.text for i, d in enumerate(ET.fromstring(row["xml"]).findall(
        ".//{http://schemas.microsoft.com/win/2004/08/events/event}Data"))}


def sample_description(samples, start, end):
    inside = [x for x in samples if start <= instant(x["at_utc"]) <= end]
    gaps = [{"previous_at_utc": a["at_utc"], "next_at_utc": b["at_utc"],
             "utc_gap_seconds": (instant(b["at_utc"]) - instant(a["at_utc"])).total_seconds(),
             "recorded_elapsed_gap_seconds": b["elapsed_seconds"] - a["elapsed_seconds"]}
            for a, b in zip(samples, samples[1:]) if instant(b["at_utc"]) >= start and instant(a["at_utc"]) <= end]
    return {"sample_count_inside": len(inside),
            "first_inside_utc": inside[0]["at_utc"] if inside else None,
            "last_inside_utc": inside[-1]["at_utc"] if inside else None,
            "largest_adjacent_gap_intersecting_window": max(gaps, key=lambda x: x["utc_gap_seconds"]) if gaps else None}


summary = read(RUN / "summary.json")
acquire, release, invocation = (read(GUARD / name) for name in ("acquire.json", "release.json", "invocation.json"))
start, end = instant(invocation["at_utc"]), instant(summary["finished_at_utc"])
events = sorted(read(HERE / "windows_system_events.json"), key=lambda x: x["at_utc"])
application = sorted(read(HERE / "windows_relevant_application_events.json"), key=lambda x: x["at_utc"])
query = read(HERE / "event_query.json")
samples, endpoints = [], []
for supervisor_path in sorted(RUN.glob("*/*/supervisor_result.json")):
    folder = supervisor_path.parent
    supervisor = read(supervisor_path)
    monitor_rows, partial_monitor = lines(folder / "monitor.jsonl")
    event_path = folder / "http_0001_generation/events.jsonl"
    event_rows, partial_events = lines(event_path)
    generation = [{"at_utc": r["event"]["created_at"], "elapsed_seconds": r["elapsed_seconds"]}
                  for r in event_rows if r.get("event", {}).get("created_at")]
    monitors = [{"at_utc": r["memory"]["observed_at_utc"], "elapsed_seconds": r["elapsed_seconds"]}
                for r in monitor_rows if r.get("memory", {}).get("observed_at_utc")]
    values = {"case_id": folder.parent.name, "endpoint": folder.name,
              "generation_events": generation, "monitor_samples": monitors,
              "partial_generation_jsonl_tail": partial_events, "partial_monitor_jsonl_tail": partial_monitor}
    samples.append(values)
    endpoints.append({"case_id": folder.parent.name, "endpoint": folder.name,
                      "supervisor": ref(supervisor_path), "status": supervisor["status"],
                      "elapsed_seconds": supervisor["elapsed_seconds"], "configured_deadline_seconds": supervisor["deadline_seconds"],
                      "elapsed_minus_configured_seconds": supervisor["elapsed_seconds"] - supervisor["deadline_seconds"],
                      "worker_status": supervisor.get("worker", {}).get("status"),
                      "cleanup": ref(folder / "unload_and_residency.json"),
                      "cleanup_status": read(folder / "unload_and_residency.json")["status"],
                      "generation_events": ref(event_path), "raw_stream": ref(event_path.with_name("raw_stream.bin")),
                      "monitor": ref(folder / "monitor.jsonl"),
                      "generation_event_count_is_not_token_count": True,
                      "generated_timestamped_events": len(generation), "monitor_samples": len(monitors)})

windows = []
for entering in (r for r in events if r["id"] == 506 and r["within_pilot_interval"]):
    exit_rows = [r for r in events if r["id"] == 507 and instant(entering["at_utc"]) < instant(r["at_utc"]) <= end]
    leaving = exit_rows[0] if exit_rows else None
    a, b = instant(entering["at_utc"]), instant(leaving["at_utc"]) if leaving else end
    observations = []
    for item in samples:
        gen, mon = item["generation_events"], item["monitor_samples"]
        if not any(a <= instant(r["at_utc"]) <= b for r in gen + mon):
            continue
        observations.append({"case_id": item["case_id"], "endpoint": item["endpoint"],
                             "generation": sample_description(gen, a, b), "monitor": sample_description(mon, a, b)})
    windows.append({"entry_record_id": entering["record_id"], "entry_at_utc": entering["at_utc"],
                    "exit_record_id": leaving["record_id"] if leaving else None,
                    "exit_at_utc": leaving["at_utc"] if leaving else None,
                    "exit_xml_data": xml_fields(leaving) if leaving else None,
                    "right_censored_at_pilot_end": leaving is None, "observations": observations})

failed = RUN / "fidelity_q2_2026__R4/C0"
log_path = failed / "server_log_after_snapshot.bin"
log_bytes = log_path.read_bytes()
delta = read(failed / "server_log_delta.json")
assert hashlib.sha256(log_bytes).hexdigest() == delta["sha256"] and len(log_bytes) == delta["after_bytes"]
delta_bytes = log_bytes[delta["prior_bytes"]:]
selected = [line for line in delta_bytes.decode("utf-8", errors="replace").splitlines()
            if "device lost" in line or "getFenceStatus" in line or "progress = 0.92" in line]
assert any("device lost on Vulkan0" in line for line in selected)
crashes = [{"at_utc": r["at_utc"], "id": r["id"], "provider": r["provider"], "record_id": r["record_id"],
            "within_pilot_interval": r["within_pilot_interval"],
            "minimal_event_fields": {k: v for k, v in xml_fields(r).items() if k in
                {"AppName", "AppVersion", "ModuleName", "ModuleVersion", "ExceptionCode", "EventName", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"}}}
           for r in application]
assert acquire["request"]["status"] == "active" and release["request"]["status"] == "released"
assert acquire["request"]["owner_thread_id"] == release["request"]["owner_thread_id"]
assert instant(acquire["at_utc"]) <= instant(summary["cases"][0]["started_at_utc"]) < end <= instant(release["at_utc"])
assert len(windows) == 5 and all(w["exit_xml_data"]["SleepEntered"] == "false"
    and w["exit_xml_data"]["SleepDurationInUs"] == "0" for w in windows)
assert sum(p.name == "request.json" for p in RUN.glob("*/*/http_0001_generation/request.json")) == 10

sources = [
 {"url": "https://docs.ollama.com/gpu", "section": "Vulkan GPU Support / GPU Selection",
  "supported_context": "The current official page says Vulkan is enabled by default when its backend is installed. It documents OLLAMA_VULKAN=0 or GGML_VK_VISIBLE_DEVICES=-1 to disable Vulkan. These options were not applied in this investigation."},
 {"url": "https://docs.vulkan.org/spec/latest/chapters/devsandqueues.html", "section": "Lost Device",
  "supported_context": "Device loss is implementation dependent. Possible reasons include execution timeouts, power management, resource management and implementation or application errors. A device-lost message alone does not identify one cause or prove physical hardware damage."},
 {"url": "https://learn.microsoft.com/en-us/windows-hardware/drivers/display/timeout-detection-and-recovery", "section": "Overview / Timeout detection",
  "supported_context": "Microsoft describes 0x141 as an engine timeout in its TDR documentation. The two recorded LiveKernelEvent141 reports support a nearby GPU-timeout event, but their reporting timestamps after pilot termination do not prove the precise fault onset or root cause."},
 {"url": "https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/prepare-software-for-modern-standby", "section": "Modern Standby phases",
  "supported_context": "Display-off begins preparation for Modern Standby. An outstanding power request can keep the system in a preparatory phase indefinitely on AC, while battery behavior differs. A display-off entry marker alone does not prove suspended computation."},
 {"url": "https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/modern-standby-sleepstudy", "section": "Screen Off and Sleep states",
  "supported_context": "The overall screen-off session includes distinct preparation and low-power states. This report therefore uses the captured SleepEntered, residency and duration fields together with stream and monitor records."}
]
for source in sources:
    source["accessed_date_utc"] = "2026-10-18"
    source["evidence_type"] = "Official primary page read; concise paraphrase, not a full archived page"

report = {
 "created_at_utc": datetime.now(timezone.utc).isoformat(), "status": "OPERATING_INTEGRITY_FAILURE",
 "run_root": str(RUN.resolve()), "run_summary": ref(RUN / "summary.json"), "server_log": ref(log_path),
 "pilot_interval": {"start_utc": start.isoformat(), "end_utc": end.isoformat(), "postwork_awake_is_separate": True},
 "model_calls_by_investigation": 0, "main_model_calls": 0, "power_settings_changed": False,
 "model_restarted": False, "frozen_code_changed": False,
 "event_query": ref(HERE / "event_query.json"), "system_events": ref(HERE / "windows_system_events.json"),
 "relevant_application_events": ref(HERE / "windows_relevant_application_events.json"),
 "unsuccessful_initial_query": ref(HERE.parent / "final/event_query.json"),
 "guard": {"acquire": ref(GUARD / "acquire.json"), "release": ref(GUARD / "release.json"),
           "invocation": ref(GUARD / "invocation.json"), "active_before_first_case": True,
           "released_after_summary_same_thread": True, "permanent_power_settings_changed": False,
           "scope": "Recorded temporary request lifecycle, not proof of continuous CPU/GPU operation or GPU health."},
 "screen_off_windows": windows,
 "sleep_observation": "All five completed in-pilot 506/507 sessions report SleepEntered=false, SleepDurationInUs=0, and zero DRIPS residency. No open screen-off session remains in this captured interval. This does not rule out short scheduling/device pauses outside the meaning of these OS counters.",
 "power_source_changes": [{"at_utc": r["at_utc"], "record_id": r["record_id"], "AcOnline": xml_fields(r).get("AcOnline")}
                          for r in events if r["id"] == 105 and r["within_pilot_interval"]],
 "power_source_interpretation": "AC was disconnected at 23:08:38.0127342Z and reconnected at 23:22:33.4816348Z. This is an observed environmental change, not evidence establishing it caused device loss.",
 "display_4101_count_in_captured_query": sum(r["id"] == 4101 for r in events),
 "device_and_crash_events": crashes, "server_log_delta": ref(failed / "server_log_delta.json"),
 "selected_server_delta_lines": selected,
 "failed_generation_result": ref(failed / "http_0001_generation/result.json"),
 "failed_endpoint_cleanup": ref(failed / "unload_and_residency.json"),
 "incident_summary": {
   "confirmed_proximate_failure": "During FQ2 R4 C0 prompt processing, the captured backend log reports Vulkan0 device lost and getFenceStatus failure after reporting 0.92 prompt progress. The provider request returned HTTP500/connection-reset error with no generated content observed, and the runner stopped on an instrument incident.",
   "os_corroboration": "An in-pilot llama-server.exe APPCRASH was recorded at 23:23:14.5359121Z, with APPCRASH WER at 23:23:22.1084299Z. Two LiveKernelEvent141 reports at 23:23:44.0759608Z and 23:23:57.8100412Z were recorded after termination and are retained as delayed adjacent evidence.",
   "qualified_inference": "The backend device-loss message and nearby OS engine-timeout reports are consistent with a GPU/backend execution failure. Their association is observational. No kernel dump was read; neither the exact timeout onset nor the causal chain was established.",
   "root_cause": "Undetermined: workload/driver/backend/resource/power interactions are possible; neither AC transition, sleep, physical GPU fault nor a particular software bug is proven as the cause.",
   "readiness": "FAIL: retain system-integrity failure; no main candidate or main freeze can be advanced from this run."},
 "endpoint_timings_and_cleanup": endpoints,
 "deadline_interpretation": "The configured per-call watchdog is 900 seconds. FQ2 R1 C2 ended with hard_deadline at 900.0403510000033 recorded supervisor seconds, including polling/termination overhead. Other recorded supervisors ended below 900 seconds. This is a measured wall-time observation, not an exactly enforced 900.000-second bound or active-compute duration.",
 "case_failure_separation": [
   {"case_id": "fidelity_q2_2026__R1", "classification": "C0 arithmetic failure with bounded auxiliary repair; C2 time budget exhausted", "system_integrity_incident": False, "raw_primary_preserved": True, "semantic_verdict": None},
   {"case_id": "fidelity_q2_2026__R4", "classification": "Backend/OS-correlated instrument failure before C0 content", "system_integrity_incident": True, "semantic_verdict": None},
   {"case_id": "ubs_june_2026__R1", "classification": "Scheduled but not started after global instrument stop", "model_inability_inferred": False},
   {"case_id": "ubs_june_2026__R4", "classification": "Scheduled but not started after global instrument stop", "model_inability_inferred": False}],
 "request_accounting": {"core": 8, "auxiliary": 2, "total_durable_generation_envelopes": 10,
                        "planned_cases": 4, "planned_sectors": 44, "main": 0, "automatic_retries": 0},
 "official_sources": sources,
 "limits": ["No causal hardware/driver diagnosis, kernel-dump analysis, stress test or additional generation was performed.",
            "Post-termination WER timestamps are reporting times and are not substituted for precise GPU-fault onset.",
            "No Display4101 was found in this targeted query; absence of that event does not negate the retained device-loss/APPCRASH/141 evidence.",
            "Generation JSONL events are transport chunks, not independently counted tokens. Monitor observations are sampled, not continuous GPU telemetry.",
            "The earlier empty FilterHashtable query is preserved but not used as absence evidence; raw UTC XPath recovered known events.",
            "No result is discarded or relabeled as a semantic/model-strategy success. The four-case denominator and raw C0 remain unchanged.",
            "Postwork awake lease began only after the pilot guard released and is outside this model-run operating interval."]}
report["read_artifact_inventory"] = [{"path": str(p), "sha256": sha} for p, sha in sorted(CONSULTED.items())]
assert all(hashlib.sha256(p.read_bytes()).hexdigest() == sha for p, sha in CONSULTED.items())
report["all_consulted_artifacts_stable"] = True
target = HERE / "environmental_deviation_v2.json"
with target.open("x", encoding="utf-8") as handle:
    json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
    handle.write("\n")
print(json.dumps({"report": ref(target), "status": report["status"], "completed_screenoff_windows": len(windows),
                  "all_sleep_entered_false": True, "generation_requests": 10, "main_model_calls": 0}))
