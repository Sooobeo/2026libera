"""Summarize retrieved v4.3 remote artifacts without executing or changing them.

Default input: data/remote_sector_20261018/data/sector_runtime/{inventory_v43,
diagnose_v43,pilot_v43}. Missing pilot artifacts mean not available locally,
not that a remote job was never started. Output JSON is an observational input
for build_sector_revision_v43.py. No network, model call or evaluator is used.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data/remote_sector_20261018/data/sector_runtime"
EXPECTED_MODEL = "qwen3.5:4b-q4_K_M"
EXPECTED_DIGEST = "d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04"
EXPECTED_ENGINE = "0.35.1"
PLANNED_CASES = [
    {"case_id": source + "__" + arm, "source_id": source, "arm": arm}
    for source in ("fidelity_q2_2026", "ubs_june_2026") for arm in ("R1", "R4")
]
FINVECTOR = "https://arxiv.org/pdf/2610.08882"
PORTBENCH = "https://arxiv.org/html/2605.27887v6#S3.SS1"
FINVECTOR_EXAMPLE = "https://github.com/alinakhay/FinVector-Market-4B/blob/main/examples/inference_mlx.py"
MLX_GENERATE = "https://github.com/ml-explore/mlx-lm/blob/v0.31.3/mlx_lm/generate.py"
FAILURES = {"failed", "timeout", "diagnostic_response_failed"}
LABELS = {
    "not_available": "로컬 증거 미수신", "not_verified": "미확인",
    "not_started": "미시작 기록", "not_run": "미실행",
    "pending": "대기", "in_progress_or_incomplete_artifacts": "진행 중 또는 증거 미완",
    "completed": "완료 기록", "installed": "설치 확인", "pinned": "식별 정보 고정",
    "failed": "실패 기록", "timeout": "시간 초과", "cancelled": "중단 기록",
    "interrupted": "중단 기록", "execution_interrupted": "실행 중단·후속 검토 필요",
    "user_requested_latency_revision": "사용자 요청에 따른 속도 개선 검토",
    "hard_deadline": "감시 프로세스 제한시간 종료", "output_limit_reached": "출력 상한 도달",
    "no_resident_models_observed": "모델 상주 없음 관측",
    "incomplete": "미완료", "diagnostic_response_failed": "진단 응답 기준 미충족",
    "needs_revision": "실패 원인 검토·수정 필요", "requires_review": "후속 검토 필요",
}


def is_number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def relative(path: Path, root: Path = ROOT) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


class Reader:
    """Keep missing/invalid values distinct and hash every consulted source."""

    def __init__(self, root: Path):
        self.root = root
        self.sources: dict[str, dict] = {}
        self.warnings: list[str] = []

    def record(self, path: Path) -> dict:
        key = relative(path, self.root)
        if key not in self.sources:
            exists = path.is_file()
            self.sources[key] = {"path": key, "exists": exists,
                                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if exists else None,
                                 "bytes": path.stat().st_size if exists else None}
        return self.sources[key]

    def read(self, path: Path) -> Any:
        if not self.record(path)["exists"]:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            self.warnings.append(f"Cannot parse {relative(path, self.root)}: {type(exc).__name__}")
            return None

    def lines(self, path: Path) -> list[dict]:
        if not self.record(path)["exists"]:
            return []
        rows = []
        for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("object required")
                rows.append(value)
            except ValueError:
                self.warnings.append(f"Unparsed line {number}: {relative(path, self.root)}")
        return rows


def obj(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def extreme(values: list[Any], operation=max) -> float | int | None:
    values = [v for v in values if is_number(v)]
    return operation(values) if values else None


def unique(values: list[Any]) -> list[Any]:
    return list(dict.fromkeys(v for v in values if isinstance(v, (str, int, float)) and not isinstance(v, bool)))


def parameter_dict(value: Any) -> dict:
    if not isinstance(value, str):
        return {}
    output = {}
    for line in value.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            try:
                output[parts[0]] = json.loads(parts[1])
            except ValueError:
                output[parts[0]] = parts[1]
    return output


def request_settings(body: dict) -> dict:
    return {**obj(body.get("options")), **{k: body[k] for k in ("model", "think", "format", "keep_alive") if k in body}}


def call_metrics(result: dict, response: dict) -> dict:
    metrics = dict(obj(result.get("metrics")))
    for field in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
        if is_number(response.get(field)):
            metrics[field + "_seconds"] = response[field] / 1e9
    for field in ("prompt_eval_count", "eval_count"):
        if is_number(response.get(field)):
            metrics[field] = response[field]
    for prefix in ("prompt_eval", "eval"):
        count, duration = metrics.get(prefix + "_count"), metrics.get(prefix + "_duration_seconds")
        metrics[prefix + "_tokens_per_second"] = count / duration if is_number(count) and is_number(duration) and duration > 0 else None
    return metrics


def read_calls(reader: Reader, directory: Path) -> list[dict]:
    calls = []
    for folder in sorted(directory.glob("http_*")):
        if not folder.is_dir():
            continue
        request = obj(reader.read(folder / "request.json"))
        response = obj(reader.read(folder / "response.json"))
        result = obj(reader.read(folder / "result.json"))
        raw_record = reader.record(folder / "raw_stream.bin")
        for name in ("events.jsonl", "assembled_text.json"):
            reader.record(folder / name)
        body = obj(request.get("body"))
        message = obj(response.get("message"))
        completed = result.get("status") == "completed" and response.get("done") is True
        if result.get("status") == "completed" and not completed:
            reader.warnings.append(f"Completed HTTP result has no saved terminal response: {relative(folder, reader.root)}")
        calls.append({"folder": folder.name, "kind": request.get("kind", result.get("kind")),
                      "status": result.get("status", "in_progress_or_incomplete_artifacts"),
                      "completed_response_observed": completed,
                      "request_path": relative(folder / "request.json", reader.root),
                      "response_path": relative(folder / "response.json", reader.root) if response else None,
                      "result_path": relative(folder / "result.json", reader.root) if result else None,
                      "started_at_utc": result.get("started_at_utc"),
                      "done_reason": response.get("done_reason"),
                      "raw_stream_bytes": raw_record["bytes"],
                      "first_content_observed": result["metrics"].get("ttft_content_seconds") is not None if isinstance(result.get("metrics"), dict) and "ttft_content_seconds" in result["metrics"] else None,
                      "request_content_utf8_bytes": sum(len(m["content"].encode("utf-8")) for m in body["messages"] if isinstance(m, dict) and isinstance(m.get("content"), str)) if isinstance(body.get("messages"), list) else None,
                      "request_settings": request_settings(body),
                      "nonempty_thinking_observed": bool(message.get("thinking")) if response else None,
                      "metrics": call_metrics(result, response),
                      "error_type": result.get("error_type"), "error": result.get("error")})
    return calls


def summarize_memory(reader: Reader, directory: Path, before: dict, after: dict, model: str = EXPECTED_MODEL) -> dict:
    rows = reader.lines(directory / "monitor.jsonl")
    memories = [obj(row.get("memory")) for row in rows]
    proc = [obj(row.get("proc_meminfo")) for row in memories]
    cg = [obj(row.get("cgroup")) for row in memories]
    pre, post = obj(before.get("memory")), obj(after.get("memory"))
    preproc, postproc = obj(pre.get("proc_meminfo")), obj(post.get("proc_meminfo"))
    precg, postcg = obj(pre.get("cgroup")), obj(post.get("cgroup"))

    def swap_used(value):
        total, free = value.get("SwapTotal_bytes"), value.get("SwapFree_bytes")
        return total - free if is_number(total) and is_number(free) else None

    residency = []
    for row in rows:
        api = obj(row.get("ollama_ps"))
        if api.get("status") == "ok":
            residency.extend(item for item in obj(api.get("value")).get("models", []) if isinstance(item, dict) and item.get("name") == model)
    return {
        "monitor_path": relative(directory / "monitor.jsonl", reader.root), "sample_count": len(rows),
        "proc_memory_total_bytes": preproc.get("MemTotal_bytes"),
        "proc_swap_total_bytes": preproc.get("SwapTotal_bytes"),
        "proc_available_sampled_min_bytes": extreme([v.get("MemAvailable_bytes") for v in proc], min),
        "runtime_rss_sum_sampled_max_bytes": extreme([v.get("rss_sum_bytes") for v in memories]),
        "cgroup_memory_current_sampled_max_bytes": extreme([v.get("memory.current") for v in cg]),
        "cgroup_memory_peak_before_bytes": precg.get("memory.peak"),
        "cgroup_memory_peak_after_bytes": postcg.get("memory.peak"),
        "cgroup_limits_before": {k: precg.get(k) for k in ("memory.max", "memory.swap.max")},
        "cgroup_memory_events_before": precg.get("memory.events"),
        "cgroup_memory_events_after": postcg.get("memory.events"),
        "proc_swap_used_before_bytes": swap_used(preproc),
        "proc_swap_used_after_bytes": swap_used(postproc),
        "proc_swap_used_sampled_max_bytes": extreme([swap_used(v) for v in proc]),
        "proc_committed_as_sampled_max_bytes": extreme([v.get("Committed_AS_bytes") for v in proc]),
        "proc_commit_limit_before_bytes": preproc.get("CommitLimit_bytes"),
        "observed_process_names": unique([p.get("name") for row in memories for p in row.get("processes", [])]),
        "resident_sample_count": len(residency),
        "resident_context_tokens": unique([v.get("context_length") for v in residency]),
        "resident_size_bytes": unique([v.get("size") for v in residency]),
        "resident_vram_bytes": unique([v.get("size_vram") for v in residency]),
        "scope": "Sampled container-visible /proc, visible cgroup and named runtime process RSS; not an isolated physical host measurement.",
        "limitations": ["RSS may double-count shared pages; cgroup includes cache and unrelated activity; do not add them.",
                        "memory.peak is an unreset cumulative high-water mark, not the maximum of interval samples.",
                        "Visible cgroup max does not establish effective ancestor/LXC limits; /proc may be virtualized.",
                        "Swap usage does not attribute paging or its speed effect to the model.",
                        "VRAM zero is a residency observation, not an inventory of physical server GPUs.",
                        "Allocated context does not prove that long inputs/history were preserved without truncation."]}


def read_run(reader: Reader, directory: Path) -> dict:
    summary = obj(reader.read(directory / "summary.json"))
    invocation = obj(reader.read(directory / "invocation.json"))
    before = obj(reader.read(directory / "inventory_before.json"))
    after = obj(reader.read(directory / "inventory_after.json"))
    calls = read_calls(reader, directory)
    return {"directory": relative(directory, reader.root), "directory_available": directory.is_dir(),
            "status": summary.get("status", "in_progress_or_incomplete_artifacts" if directory.is_dir() else "not_available"),
            "summary_path": relative(directory / "summary.json", reader.root) if summary else None,
            "invocation": invocation, "reported_summary": summary,
            "inventory_before": before, "inventory_after": after,
            "calls": calls, "observed_http_calls": len(calls),
            "observed_completed_http_responses": sum(c["completed_response_observed"] for c in calls),
            "resources": summarize_memory(reader, directory, before, after)}


def read_pilot(reader: Reader, directory: Path, run: dict) -> dict:
    destination = directory / "pilot"
    summary = obj(reader.read(destination / "summary.json")) or run["reported_summary"]
    planned = reader.read(destination / "planned_cases.json")
    rows = planned if isinstance(planned, list) and all(isinstance(x, dict) for x in planned) else PLANNED_CASES
    reported = {r.get("case_id"): r for r in summary.get("records", []) if isinstance(r, dict)}
    cases = []
    for row in rows:
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or Path(case_id).name != case_id or case_id in (".", ".."):
            reader.warnings.append("Invalid case_id in pilot roster; ignored")
            continue
        folder = destination / case_id
        record = reported.get(case_id, {})
        stages = []
        for stage in range(1, 5):
            paths = {kind: folder / f"stage{stage}_{kind}.json" for kind in ("request", "response", "record")}
            values = {kind: reader.read(path) for kind, path in paths.items()}
            response = obj(values["response"])
            observed = any(v is not None for v in values.values())
            stages.append({"stage": stage, "request_present": values["request"] is not None,
                           "response_present": values["response"] is not None,
                           "provider_done": response.get("done"), "done_reason": response.get("done_reason"),
                           "parsed_and_calculated_record_present": isinstance(values["record"], dict),
                           "state": "recorded" if isinstance(values["record"], dict) else "attempted" if observed else "not_observed",
                           "response_path": relative(paths["response"], reader.root) if values["response"] is not None else None})
        final = reader.read(folder / "final.json")
        failure = reader.read(folder / "failure.json")
        coordinator_failure = reader.read(destination / (case_id + "_coordinator_failure.json"))
        complete = isinstance(final, dict) and all(s["parsed_and_calculated_record_present"] for s in stages)
        if record.get("status") == "completed" and not complete:
            reader.warnings.append(f"Pilot case reported completed but full stage/final files unavailable: {case_id}")
        state = record.get("status") or ("completed" if complete else "failed" if failure or coordinator_failure else "in_progress_or_incomplete_artifacts" if folder.is_dir() else "not_available")
        cases.append({"case_id": case_id, "source_id": row.get("source_id"), "arm": row.get("arm"),
                      "status": state, "coordinator_status": record.get("status"),
                      "four_stage_artifact_complete": complete,
                      "attempted_stages_observed": sum(s["request_present"] for s in stages),
                      "completed_stage_records": sum(s["parsed_and_calculated_record_present"] for s in stages),
                      "final_present": isinstance(final, dict), "stages": stages,
                      "failure": failure, "coordinator_failure": coordinator_failure,
                      "http_call_folders": record.get("http_call_folders", []),
                      "model_calls_attempted_reported": record.get("model_calls_attempted")})
    scores_path = destination / "offline_scores.json"
    scores = reader.read(scores_path)
    dependencies = reader.read(destination / "dependencies.json")
    hashes = reader.read(destination / "input_hashes.json")
    available = directory.is_dir()
    reported_attempts = summary.get("pilot_model_calls")
    call_artifacts_complete = reported_attempts == run["observed_http_calls"] if is_number(reported_attempts) else None
    if available and call_artifacts_complete is False:
        reader.warnings.append("Pilot reported call count differs from available HTTP folders; total completed call count remains unknown")
    expected_case_ids = {c["case_id"] for c in cases}
    case_artifacts_complete = bool(reported) and set(reported) == expected_case_ids and not any(
        (c["coordinator_status"] == "completed") != c["four_stage_artifact_complete"] for c in cases)
    if available and not summary:
        reader.warnings.append("Pilot final summary not received; file observations are lower bounds, not completed totals")
    return {"status": summary.get("status", run["status"]), "directory_available": available,
            "summary_path": relative(destination / "summary.json", reader.root) if (destination / "summary.json").is_file() else run["summary_path"],
            "planned_cases": len(rows), "roster_basis": "saved_planned_cases" if isinstance(planned, list) else "protocol_expectation_only",
            "completed_cases": sum(c["four_stage_artifact_complete"] for c in cases) if available and case_artifacts_complete else None,
            "completed_calls": run["observed_completed_http_responses"] if available and call_artifacts_complete is True else None,
            "completed_case_artifacts_observed": sum(c["four_stage_artifact_complete"] for c in cases) if available else None,
            "completed_http_responses_observed": run["observed_completed_http_responses"] if available else None,
            "call_artifact_count_matches_reported_attempts": call_artifacts_complete if available else None,
            "attempted_http_calls_observed": run["observed_http_calls"] if available else None,
            "not_started_cases_reported": sum(c["coordinator_status"] == "not_started" for c in cases) if reported else None,
            "cases": cases, "dependencies": dependencies, "input_hashes": hashes,
            "offline_scores_path": relative(scores_path, reader.root) if isinstance(scores, dict) else None,
            "offline_scores": scores if isinstance(scores, dict) else None,
            "score_scope": "Descriptive only; a not-started roster row is not an observed model error. Citation IDs do not establish semantic support."}


def read_latency(reader: Reader, paths: list[Path]) -> list[dict]:
    """A separate engineering namespace; never alter research case/call counts."""
    output = []
    for path in paths:
        summary = reader.read(path)
        if not isinstance(summary, dict):
            output.append({"summary_path": relative(path, reader.root), "status": "not_available", "probes": []})
            continue
        invocation = obj(reader.read(path.parent / "invocation.json"))
        if summary.get("pilot_model_calls", 0) != 0 or summary.get("main_model_calls", 0) != 0:
            raise ValueError("Latency summary declares research calls; refusing to mix it into an engineering result")
        probes = []
        for row in summary.get("records", []):
            if not isinstance(row, dict):
                continue
            probe_id = row.get("probe_id")
            if not isinstance(probe_id, str) or Path(probe_id).name != probe_id or probe_id in (".", ".."):
                reader.warnings.append("Invalid latency probe_id; ignored")
                continue
            folder = path.parent / probe_id
            spec = obj(reader.read(folder / "worker_spec.json"))
            observation = obj(reader.read(folder / "model_observation.json"))
            worker = reader.read(folder / "worker_summary.json")
            supervisor = reader.read(folder / "supervisor_result.json")
            calls = read_calls(reader, folder)
            actual_settings = next((c["request_settings"] for c in calls if c["request_settings"]), None)
            probes.append({"probe_id": probe_id, "model": row.get("model"), "threads": row.get("threads"),
                           "status": row.get("status", "not_verified"),
                           "supervisor_status": row.get("supervisor_status", obj(supervisor).get("supervisor_status")),
                           "elapsed_seconds": row.get("elapsed_seconds", obj(supervisor).get("elapsed_seconds")),
                           "reported_metrics": row.get("provider_metrics"), "response_assessment": row.get("response_assessment"),
                           "request_settings": actual_settings or request_settings(obj(spec.get("body"))),
                           "settings_source": "saved_http_request" if actual_settings else "worker_spec_only",
                           "deadline_seconds": spec.get("deadline_seconds", invocation.get("deadline_seconds")),
                           "observed_model_digest": obj(observation.get("selected_model")).get("digest"),
                           "observed_engine": obj(observation.get("version")).get("version"),
                           "worker_summary": worker, "supervisor_result": supervisor, "calls": calls,
                           "resources": summarize_memory(reader, folder, {}, {}, str(row.get("model")))})
        output.append({"summary_path": relative(path, reader.root), "status": summary.get("status", "not_verified"),
                       "reported_summary": summary, "invocation": invocation, "probes": probes,
                       "scope": "Synthetic engineering latency only; neither pilot cases nor main responses.",
                       "comparison_limits": "One fixed-order attempt per configuration, differing models/tokenizers and persistent OS cache; no statistical speed ranking or four-stage feasibility conclusion."})
    return output


def read_real_input(reader: Reader, paths: list[Path]) -> list[dict]:
    """Read the bounded real-input engineering probe, never score its content."""
    output = []
    for path in paths:
        summary = reader.read(path)
        if not isinstance(summary, dict):
            output.append({"summary_path": relative(path, reader.root), "status": "not_available", "calls": []})
            continue
        if summary.get("scope") != "real_input_engineering_feasibility_only":
            raise ValueError("Unexpected real-input engineering scope")
        if summary.get("pilot_model_calls") != 0 or summary.get("main_model_calls") != 0:
            raise ValueError("Real-input probe must explicitly declare zero research calls")
        invocation = obj(reader.read(path.parent / "invocation.json"))
        validation = reader.read(path.parent / "roundtrip_and_sizes.json")
        observation = reader.read(path.parent / "model_observation_before_request.json")
        cleanup = reader.read(path.parent / "unload_and_residency_after.json")
        for filename in ("original_request_not_sent.json", "compact_request_to_send.json"):
            reader.record(path.parent / filename)
        folder = path.parent / "compact_probe"
        worker = reader.read(folder / "worker_summary.json")
        supervisor = reader.read(folder / "supervisor_result.json")
        spec = obj(reader.read(folder / "worker_spec.json"))
        calls = read_calls(reader, folder)
        actual_settings = next((c["request_settings"] for c in calls if c["request_settings"]), None)
        output.append({"summary_path": relative(path, reader.root), "status": summary.get("status", "not_verified"),
                       "scope": "Real first-stage input engineering feasibility only; no semantic scoring or research case completion.",
                       "reported_summary": summary, "invocation": invocation, "validation": validation,
                       "model_observation": observation, "cleanup": cleanup, "calls": calls,
                       "worker_summary": worker, "supervisor_result": supervisor,
                       "request_settings": actual_settings or request_settings(obj(spec.get("body"))),
                       "settings_source": "saved_http_request" if actual_settings else "worker_spec_only",
                       "resources": summarize_memory(reader, folder, {}, {}, str(summary.get("model"))),
                       "interpretation_limits": "Only the compact version was sent. Exact-value round-trip is not equal-model-behavior evidence; no original/compact latency ratio, four-stage feasibility, financial quality or speed-resolution claim."})
    return output


def read_engineering_reviews(reader: Reader, paths: list[Path], summaries: list[dict]) -> list[dict]:
    """Link saved independent machine reviews only to hash-matched summaries."""
    output = []
    for path in paths:
        review = reader.read(path)
        if not isinstance(review, dict):
            continue
        evidence = obj(review.get("evidence_files"))
        covered = []
        for summary in summaries:
            source_path = summary["summary_path"]
            recorded = reader.sources.get(source_path, {})
            if recorded.get("exists") and obj(evidence.get(source_path)).get("sha256") == recorded.get("sha256"):
                covered.append(source_path)
        output.append({"path": relative(path, reader.root), "status": review.get("status"),
                       "scope": review.get("scope"), "check_count": review.get("check_count"),
                       "reported_pass_count": sum(c.get("status") == "pass" for c in review.get("checks", []) if isinstance(c, dict)),
                       "summary_sha256_matches": covered, "human_semantic_review": False})
        if not covered:
            reader.warnings.append("Engineering review has no hash-matched supplied summary: " + relative(path, reader.root))
    return output


def read_hardware(reader: Reader, path: Path | None) -> dict:
    if path is None:
        return {"status": "not_available", "path": None, "reported_cpu_features": {}}
    value = reader.read(path)
    features = {}
    names = {"avx", "avx2", "fma", "sse4_1", "sse4_2"}

    def visit(item):
        if isinstance(item, dict):
            for key, child in item.items():
                normalized = str(key).lower().replace(".", "_")
                if normalized in names and type(child) is bool:
                    features[normalized] = child
                if "flags" in normalized and isinstance(child, (str, list)):
                    flags = child.split() if isinstance(child, str) else child
                    if all(isinstance(x, str) for x in flags):
                        for name in names:
                            features[name] = name in flags
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return {"status": "available" if isinstance(value, (dict, list)) else "not_available",
            "path": relative(path, reader.root) if value is not None else None,
            "raw_record": value, "reported_cpu_features": features,
            "scope": "Features exposed to the remote environment, not an independent physical-host inventory."}


def build_assessment(runtime_root: Path, repo_root: Path = ROOT, latency_paths: list[Path] | None = None,
                     hardware_path: Path | None = None, operator_cancel_reason: str | None = None,
                     real_input_paths: list[Path] | None = None, engineering_review_paths: list[Path] | None = None) -> dict:
    reader = Reader(repo_root)
    inventory = read_run(reader, runtime_root / "inventory_v43")
    diagnostic = read_run(reader, runtime_root / "diagnose_v43")
    pilot_run = read_run(reader, runtime_root / "pilot_v43")
    pilot = read_pilot(reader, runtime_root / "pilot_v43", pilot_run)
    cancel_path = runtime_root / "pilot_v43/CANCEL"
    cancel_record = reader.read(cancel_path)
    cancelled_calls = [c for c in pilot_run["calls"] if c["status"] == "cancelled"]
    cancelled_folders = {c["folder"] for c in cancelled_calls}
    interruption_observed = bool(cancelled_calls or pilot_run["status"] == "cancelled")
    for case in pilot["cases"]:
        interrupted = bool(set(case["http_call_folders"]) & cancelled_folders)
        case["execution_interruption_observed"] = interrupted
        if interrupted:
            case["display_status"] = "interrupted"
            case["interpretation"] = "Coordinator failed status follows cancellation; not an observed semantic or investment-judgment failure."
    cancellation = {"interruption_observed": interruption_observed,
                    "cancel_record_path": relative(cancel_path, repo_root) if cancel_record is not None else None,
                    "raw_cancel_record": cancel_record,
                    "operator_supplement": operator_cancel_reason,
                    "operator_supplement_scope": "Additional operator-provided context; does not override raw timeout/cancel status.",
                    "cancelled_http_folders": sorted(cancelled_folders),
                    "interpretation": "Cancellation is distinct from timeout. A response absent at cancellation does not establish semantic failure."}
    latency = read_latency(reader, latency_paths or [])
    real_input = read_real_input(reader, real_input_paths or [])
    engineering_reviews = read_engineering_reviews(reader, engineering_review_paths or [], latency + real_input)
    hardware = read_hardware(reader, hardware_path)
    pin_path = runtime_root / "inventory_v43/runtime_pinned.json"
    meta_path = runtime_root / "inventory_v43/model_metadata.json"
    pin, metadata = obj(reader.read(pin_path)), obj(reader.read(meta_path))
    show, selected = obj(metadata.get("show")), obj(metadata.get("selected_model"))
    diagnostics_detail = reader.read(runtime_root / "diagnose_v43/diagnosis.json")
    review_path = repo_root / "research/remote_diagnostic_review_20261018.json"
    independent_review = reader.read(review_path)
    defaults = parameter_dict(show.get("parameters"))
    metadata_consistent = bool(pin and metadata and selected.get("name") == pin.get("model") == EXPECTED_MODEL
                               and selected.get("digest") == pin.get("digest")
                               and obj(metadata.get("version")).get("version") == pin.get("engine_version")
                               and isinstance(show.get("template"), str)
                               and hashlib.sha256(show["template"].encode()).hexdigest() == pin.get("template_sha256"))
    approved_runtime_match = bool(metadata_consistent and pin.get("digest") == EXPECTED_DIGEST
                                  and pin.get("engine_version") == EXPECTED_ENGINE
                                  and obj(show.get("details")).get("quantization_level") == "Q4_K_M")
    failures = []
    for phase, run in (("inventory", inventory), ("diagnosis", diagnostic), ("pilot", pilot_run)):
        if run["status"] in FAILURES:
            failures.append({"phase": phase, "status": run["status"], "error": run["reported_summary"].get("error")})
        for call in run["calls"]:
            if call["status"] in FAILURES:
                failures.append({"phase": phase, "call": call["folder"], "status": call["status"], "error": call["error"]})
        if (run["reported_summary"].get("main_model_calls") or 0) != 0:
            raise ValueError("Unexpected nonzero main calls: this builder only supports the pilot-only snapshot")
    for case in pilot["cases"]:
        if case["status"] in FAILURES and not case["execution_interruption_observed"]:
            failures.append({"phase": "pilot", "case_id": case["case_id"], "status": case["status"], "failure": case["failure"]})
    if pin and metadata and not metadata_consistent:
        failures.append({"phase": "inventory", "status": "metadata_pin_mismatch"})
    elif pin and metadata and not approved_runtime_match:
        failures.append({"phase": "inventory", "status": "approved_runtime_mismatch"})
    settings = {"diagnosis": [c["request_settings"] for c in diagnostic["calls"]],
                "pilot": list({json.dumps(c["request_settings"], sort_keys=True): c["request_settings"] for c in pilot_run["calls"]}.values())}
    installation_status = "installed" if metadata_consistent else "failed" if inventory["status"] in FAILURES else "not_verified"
    runtime = {
        "status": "pinned" if approved_runtime_match else "not_verified", "model_tag": pin.get("model"),
        "digest": pin.get("digest"), "engine_version": pin.get("engine_version"),
        "template_sha256": pin.get("template_sha256"), "quantization": obj(show.get("details")).get("quantization_level"),
        "diagnostic_completed_calls": diagnostic["observed_completed_http_responses"] if diagnostic["directory_available"] else None,
        "context_tokens": pin.get("context_tokens"), "thinking": pin.get("thinking"),
        "temperature": pin.get("temperature"), "max_output_tokens": pin.get("max_output_tokens"),
        "runtime_manifest_path": relative(pin_path, repo_root) if pin else None,
        "model_metadata_path": relative(meta_path, repo_root) if metadata else None,
        "inherited_model_parameters": defaults,
        "request_overrides": settings,
        "resource_summary": {
            "observed_cpu": obj(inventory["inventory_before"].get("cpu")).get("model name"),
            "os_logical_cpus": inventory["inventory_before"].get("os_cpu_count"),
            "reported_cpu_features": hardware["reported_cpu_features"],
            "diagnosis": {k: diagnostic["resources"][k] for k in (
                "sample_count", "proc_memory_total_bytes", "proc_swap_total_bytes", "runtime_rss_sum_sampled_max_bytes",
                "cgroup_memory_current_sampled_max_bytes", "proc_available_sampled_min_bytes", "resident_vram_bytes")},
            "pilot": {k: pilot_run["resources"][k] for k in (
                "sample_count", "runtime_rss_sum_sampled_max_bytes", "cgroup_memory_current_sampled_max_bytes",
                "proc_available_sampled_min_bytes", "resident_vram_bytes")}},
        "notes": [f"짧은 기술 진단 상태: {LABELS.get(diagnostic['status'], diagnostic['status'])}. 로컬에서 확인한 완료 HTTP 응답: {diagnostic['observed_completed_http_responses'] if diagnostic['directory_available'] else '미확인'}건. 예비 사례 수에 포함하지 않는다.",
                  "모델 기본 temperature와 실제 요청 temperature를 구분한다. show.parameters의 기본값 중 요청하지 않은 항목은 명시적으로 덮어쓰지 않았다.",
                  "기본값의 실제 적용 순서·효과는 엔진에 의존하며 FinVector의 전체 decoding 조건을 재현했다는 주장이 아니다.",
                  "호출 직전 pin 검증은 코드에 구현되어 있지만 조회 메타데이터를 호출별로 별도 저장하지 않았다. 최초 inventory, 요청·응답과 코드 해시가 보존 범위다.",
                  "설치·짧은 JSON 생성 성공은 전체 네 단계 수행이나 금융 판단의 유효성을 보장하지 않는다."]}
    # Remove unavailable paths, so the document builder does not invent file links.
    runtime = {k: v for k, v in runtime.items() if not k.endswith("_path") or v is not None}
    output = {
        "schema_version": "1.0", "protocol_version": "4.3", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "builder": "research/build_remote_sector_report.py", "runtime_root": relative(runtime_root, repo_root),
        "scope": "Read-only summary of retrieved inventory, synthetic diagnosis and pilot artifacts. No inference, scoring or main experiment executed by builder.",
        "installation": {"status": installation_status, "notes": ["Exact tag/digest/engine/template consistency is checked from saved files; live service is not queried."]},
        "runtime": runtime,
        "diagnostics": {"status": diagnostic["status"], "completed_calls": diagnostic["observed_completed_http_responses"] if diagnostic["directory_available"] else None,
                        "detail": diagnostics_detail, "run": diagnostic,
                        "independent_machine_review_path": relative(review_path, repo_root) if isinstance(independent_review, dict) else None,
                        "independent_machine_review_status": obj(independent_review).get("status")},
        "pilot": {"status": "interrupted" if interruption_observed else pilot["status"] if pilot["directory_available"] else "not_verified",
                  "completed_cases": pilot["completed_cases"], "completed_calls": pilot["completed_calls"],
                  "attempted_calls_observed": pilot["attempted_http_calls_observed"],
                  "notes": ["미수신 파일은 원격 미실행·실패를 뜻하지 않는다. not_started는 실제 coordinator 기록에서만 구분한다.",
                            "완료 응답 수는 저장된 HTTP 종료 응답 수이며 올바른 JSON·정확한 판단 수가 아니다.",
                            "완료 사례는 네 단계 record와 final 파일을 모두 확인한 수이며 내용의 의미 검토 완료가 아니다."] +
                           (["CANCEL 및 호출 기록에 따른 실행 중단이다. 시간 초과와 구분하며, 응답 미완료를 금융 판단의 의미 실패로 판정하지 않는다."] if interruption_observed else []),
                  "details": pilot, "run": pilot_run, "cancellation": cancellation},
        "main": {"status": "not_run", "completed_cases": 0, "completed_calls": 0, "attempted_calls_observed": 0, "frozen": False,
                 "notes": ["이 실행 범위는 pilot 전용이다. 본과제 실행·평가규칙 동결을 이 보고서가 승인하지 않는다.",
                           "본과제 동결 전 설정 결정이 필요하다. FinVector는 penalty를 보고하지 않으므로 상속된 presence_penalty=1.5는 논문 기반 수치라고 정당화할 수 없다. 미보고 기본값의 처리·근거 수준·한계를 명시하고 필요한 조건 개정과 예비 재검증을 마쳐야 한다."],
                 "blocking_design_decisions": ["Resolve unreported inherited penalty defaults before main freeze; current pilot runtime is unchanged."],
                 "future_candidates_not_applied": [
                     {"values": {"seed": 3407}, "evidence_kind": "paper_reported", "source": FINVECTOR, "locator": "section 4.1", "validated_for_libera": False},
                     {"values": {"repeat_penalty": 1, "presence_penalty": 0, "frequency_penalty": 0},
                      "evidence_kind": "implementation_reference_not_reported_benchmark_conditions",
                      "sources": [FINVECTOR_EXAMPLE, MLX_GENERATE],
                      "reason": "Candidate translation of the public minimal example and MLX-LM 0.31.3 default argmax/logits_processors=None to neutral Ollama penalties; the actual benchmark runner is private.",
                      "validated_for_libera": False}],
                 "future_candidates_automatically_applied": False},
        "human_review": {"status": "pending", "completed_reviews": None,
                         "notes": ["자동·독립 코드 검토를 사람의 원문·의미 검토 완료로 세지 않는다."]},
        "assessment": {"status": "needs_revision" if failures else "execution_interrupted" if interruption_observed else "requires_review", "failure_records": failures,
                       "execution_readiness_certified": False, "model_recommendation": None,
                       "notes": ["실패 기록은 원인과 조건 수정의 검토 대상이며 자동으로 새 설정을 적용하지 않는다."]},
        "engineering_results": {"latency": latency, "real_input": real_input, "independent_machine_reviews": engineering_reviews,
                                "hardware": hardware,
                                "included_in_research_pilot_or_main_counts": False,
                                "research_runtime_automatically_changed": False,
                                "latency_problem_resolved": None, "research_suitability_established": False},
        "inventory": inventory, "metadata_pin_consistent": metadata_consistent,
        "approved_runtime_match": approved_runtime_match,
        "approved_runtime_reference": {"model": EXPECTED_MODEL, "digest": EXPECTED_DIGEST,
                                       "engine_version": EXPECTED_ENGINE, "quantization": "Q4_K_M",
                                       "basis": "The explicitly selected v4.3 runtime constants; not a new model recommendation."},
        "notes": ["예비·기술 진단의 결과이며 학술제 본실험 결과가 아니다.",
                  "FinVector는 thinking 비활성화·JSON·greedy의 선례다. 양자화·엔진·상속 기본값이 달라 전체 재현을 주장하지 않는다.",
                  "8192 출력 상한은 PortBench의 값을 다른 모델·과제로 옮긴 적용이며 65536 문맥은 구현 후보다.",
                  "실행 중 설정을 바꾸지 않고, 평가 기준 보완은 예비 단계에서만 한 뒤 본과제 전에 동결한다."],
        "sources": {"finvector": FINVECTOR, "portbench": PORTBENCH,
                    "finvector_public_minimal_example": FINVECTOR_EXAMPLE, "mlx_lm_0313_generate": MLX_GENERATE},
        "source_files": list(reader.sources.values()), "warnings": reader.warnings,
    }
    if latency:
        observations = []
        for run in latency:
            for probe in run["probes"]:
                call = probe["calls"][0] if probe["calls"] else {}
                metrics = obj(call.get("metrics"))
                observations.append(f"{probe['probe_id']}: {LABELS.get(probe['status'], probe['status'])}, "
                                    f"감시 {shown(probe['elapsed_seconds'], 3)}초, "
                                    f"HTTP {shown(metrics.get('wall_seconds'), 3)}초, "
                                    f"첫 내용 {shown(metrics.get('ttft_content_seconds'), 3)}초, "
                                    f"수신 {shown(call.get('raw_stream_bytes'))} bytes")
        output["notes"].append("별도 합성 속도 진단 관측: " + "; ".join(observations) +
                               ". 설정별 한 번의 공학 점검이며 예비·본과제 완료 수에 합산하지 않는다. 제한시간 종료는 완료시간이 아니며 모델·문맥·벌점 등 구성 차이로 일반적인 성능 배율을 계산하지 않는다.")
    for run in real_input:
        saved = obj(run.get("reported_summary")); call = run["calls"][0] if run["calls"] else {}
        output["notes"].append(f"실제 문서 첫 단계의 별도 기술 점검({saved.get('model', '미확인')}): "
                               f"{LABELS.get(run['status'], run['status'])}, "
                               f"감시 {shown(obj(saved.get('supervisor')).get('elapsed_seconds'), 3)}초, "
                               f"수신 {shown(call.get('raw_stream_bytes'))} bytes. "
                               "압축 입력만 보낸 32-token 상한의 단일 요청이며 원형 대비 속도 개선이나 네 단계 적합성을 입증하지 않는다. "
                               "현재 속도 문제의 해결과 작은 모델의 연구 과제 충족은 확인되지 않았다.")
    if inventory["summary_path"]:
        output["installation"]["manifest_path"] = inventory["summary_path"]
    if pilot["summary_path"]:
        output["pilot"]["summary_path"] = pilot["summary_path"]
    if pilot["offline_scores_path"]:
        output["pilot"]["offline_scores_path"] = pilot["offline_scores_path"]
    return output


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def shown(value: Any, digits: int = 2) -> str:
    if value is None:
        return "미확인"
    if type(value) is bool:
        return "예" if value else "아니요"
    if isinstance(value, float):
        return f"{value:,.{digits}f}"
    return esc(LABELS.get(str(value), str(value)))


def gib(value: Any) -> str:
    return f"{value / 2**30:.3f} GiB" if is_number(value) else "미확인"


def table(headers: list[str], rows: list[list[str]]) -> str:
    return "<div class='scroll'><table><thead><tr>" + "".join(f"<th>{esc(x)}</th>" for x in headers) + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{v}</td>" for v in row) + "</tr>" for row in rows) + "</tbody></table></div>"


def render_html(value: dict, output_dir: Path, repo_root: Path = ROOT) -> str:
    def link(path, title):
        if not path:
            return "미수신"
        source = Path(path)
        if not source.is_absolute():
            source = repo_root / source
        target = os.path.relpath(source, output_dir).replace("\\", "/")
        return f'<a href="{esc(target)}">{esc(title)}</a>'

    runtime, pilot = value["runtime"], value["pilot"]
    diagnostic = value["diagnostics"]
    engineering = value["engineering_results"]
    summary = table(["구분", "로컬 증거에서 확인한 상태"], [
        ["설치·핀", shown(value["installation"]["status"]) + " / " + shown(runtime["status"])],
        ["짧은 기술 진단", shown(diagnostic["status"]) + " · 완료 응답 " + shown(diagnostic["completed_calls"]) + "건"],
        ["네 단계 예비실험", shown(pilot["status"]) + " · 완료 사례 " + shown(pilot["completed_cases"]) + "건 / 완료 HTTP 응답 " + shown(pilot["completed_calls"]) + "건"],
        ["본과제·사람 의미 검토", "본과제 0건·미동결 / 사람 의미 검토 대기"],
        ["후속 상태", shown(value["assessment"]["status"]) + " · 적합성 자동 승인 없음"],
    ])
    before = value["inventory"]["inventory_before"]
    metadata = table(["항목", "관측값 또는 고정값"], [
        ["모델 / 양자화 / 엔진", " / ".join(shown(runtime.get(k)) for k in ("model_tag", "quantization", "engine_version"))],
        ["모델 digest", f"<code>{shown(runtime.get('digest'))}</code>"],
        ["CPU / OS 논리 CPU 수", shown(obj(before.get("cpu")).get("model name")) + " / " + shown(before.get("os_cpu_count"))],
        ["예비 고정 요청", f"T={shown(runtime.get('temperature'))}, thinking={esc(runtime.get('thinking'))}, 출력 {shown(runtime.get('max_output_tokens'))}, 문맥 {shown(runtime.get('context_tokens'))}"],
        ["메타데이터의 모델 기본값", "<code>" + esc(json.dumps(runtime["inherited_model_parameters"], ensure_ascii=False)) + "</code>"],
    ])
    timings = []
    for phase, run in (("기술 진단", diagnostic["run"]), ("예비", pilot["run"])):
        for call in run["calls"]:
            m = call["metrics"]
            timings.append([phase + " " + esc(call["folder"]), shown(call["status"]),
                            shown(m.get("prompt_eval_count")) + " / " + shown(m.get("eval_count")),
                            shown(m.get("ttft_content_seconds")), shown(m.get("load_duration_seconds")), shown(m.get("prompt_eval_duration_seconds")),
                            shown(m.get("eval_duration_seconds")), shown(m.get("wall_seconds")),
                            shown(m.get("prompt_eval_tokens_per_second")) + " / " + shown(m.get("eval_tokens_per_second"))])
    timings_html = table(["호출", "상태", "입력/출력 토큰", "첫 내용까지 초", "적재 초", "입력 처리 초", "생성 초", "전체 경과 초", "입력/생성 tok/s"], timings) if timings else "<p>호출 파일을 아직 받지 못했다.</p>"
    memories = []
    for phase, run in (("기술 진단", diagnostic["run"]), ("예비", pilot["run"])):
        m = run["resources"]
        memories.append([phase, shown(m["sample_count"]), gib(m["proc_memory_total_bytes"]),
                         gib(m["runtime_rss_sum_sampled_max_bytes"]), gib(m["cgroup_memory_current_sampled_max_bytes"]),
                         gib(m["proc_available_sampled_min_bytes"]),
                         gib(m["proc_swap_used_before_bytes"]) + " → " + gib(m["proc_swap_used_after_bytes"]),
                         esc(json.dumps(m["resident_vram_bytes"]))])
    memories_html = table(["범위", "표본 수", "/proc 전체 RAM", "모델 관련 RSS 최대", "cgroup 사용 표본 최대", "/proc 가용 최소", "swap 전→후", "보고 VRAM bytes"], memories)
    case_rows = [[esc(c["case_id"]), shown(c.get("display_status", c["status"])) + (" (실행기 기록: " + shown(c["coordinator_status"]) + ")" if c["execution_interruption_observed"] else ""), shown(c["attempted_stages_observed"]),
                  shown(c["completed_stage_records"]), shown(c["final_present"])] for c in pilot["details"]["cases"]]
    cases_html = table(["예비 사례", "상태", "요청 파일 단계 수", "계산까지 기록한 단계 수", "최종 파일"], case_rows)
    cancellation_html = ""
    cancellation = pilot["cancellation"]
    if cancellation["interruption_observed"]:
        call = next((c for c in pilot["run"]["calls"] if c["status"] == "cancelled"), {})
        cancellation_html = ("<p class='notice'>호출 결과가 cancelled로 기록된 실행 중단이다. 시간 초과(timeout)와 구분한다. "
                             "중단 호출 경과시간 " + shown(obj(call.get("metrics")).get("wall_seconds"), 3) + "초, 수신 원시 데이터 " + shown(call.get("raw_stream_bytes")) + " bytes. "
                             "첫 내용의 발생이 기록되지 않았다면 TTFT는 미관측이며 0초가 아니다. 완성된 응답이 없는 중단을 금융 판단의 의미 실패로 세지 않는다.</p>")
        if cancellation["raw_cancel_record"] is not None:
            cancellation_html += "<p>취소 요청 기록: <code>" + esc(json.dumps(cancellation["raw_cancel_record"], ensure_ascii=False)) + "</code> · " + link(cancellation["cancel_record_path"], "CANCEL 원본") + "</p>"
        if cancellation["operator_supplement"]:
            cancellation_html += "<p>운영자가 추가로 제공한 사유: " + shown(cancellation["operator_supplement"]) + ". 원시 호출의 종료 상태와 별도로 보존한다.</p>"
    latency_rows, latency_conditions = [], []
    for run in engineering["latency"]:
        for probe in run["probes"]:
            metrics = probe["calls"][0]["metrics"] if probe["calls"] else obj(probe["reported_metrics"])
            raw_bytes = probe["calls"][0]["raw_stream_bytes"] if probe["calls"] else None
            settings = probe["request_settings"]
            latency_rows.append([esc(probe["probe_id"]), shown(probe["model"]), shown(probe["threads"]),
                                 shown(probe["status"]), shown(probe["elapsed_seconds"], 3),
                                 shown(metrics.get("wall_seconds"), 3), shown(metrics.get("ttft_content_seconds"), 3),
                                 shown(metrics.get("prompt_eval_duration_seconds"), 3), shown(raw_bytes),
                                 shown(metrics.get("prompt_eval_count")) + " / " + shown(metrics.get("eval_count")),
                                 shown(metrics.get("prompt_eval_tokens_per_second")) + " / " + shown(metrics.get("eval_tokens_per_second"))])
            latency_conditions.append([esc(probe["probe_id"]), shown(settings.get("num_ctx")), shown(settings.get("num_predict")),
                                       " / ".join(shown(settings.get(k)) for k in ("repeat_penalty", "presence_penalty", "frequency_penalty")),
                                       shown(settings.get("seed"))])
    latency_html = table(["속도 진단", "모델", "요청 스레드", "종료 상태", "감시 경과 초", "HTTP 경과 초", "첫 내용까지 초", "입력 처리 초", "수신 bytes", "입력/출력 토큰", "입력/생성 tok/s"], latency_rows) if latency_rows else "<p>연결된 속도 비교 결과 파일은 아직 없다. 실행 여부나 성공을 추정하지 않는다.</p>"
    if engineering["latency"]:
        latency_html += table(["속도 진단", "문맥 상한", "출력 상한", "repeat / presence / frequency", "seed"], latency_conditions)
        latency_html += "<p>" + " · ".join(link(r["summary_path"], "속도 비교 원본") + " (합성 입력 " + shown(r.get("invocation", {}).get("prompt_utf8_bytes")) + " bytes)" for r in engineering["latency"]) + "</p>"
        latency_html += "<p>감시 경과시간에는 자식 실행기 관측 범위가 포함되어 HTTP 요청 시간과 다르다. 제한시간 종료는 그 시점까지 응답을 받지 못했다는 뜻이며 실제 완료시간이 아니다. 종료 응답이 없어 토큰·입력 처리시간을 받지 못한 칸은 0으로 채우지 않는다. 짧은 JSON 응답의 성공으로 금융 문서 해석 능력을 판단하지 않는다.</p>"
    real_rows = []
    for run in engineering["real_input"]:
        saved = obj(run.get("reported_summary")); supervised = obj(saved.get("supervisor"))
        sizes = obj(obj(run.get("validation")).get("sizes"))
        call = run["calls"][0] if run["calls"] else {}
        metrics = obj(call.get("metrics"))
        real_rows.append([shown(saved.get("model")), shown(saved.get("case_input")), shown(run["status"]),
                          shown(supervised.get("elapsed_seconds"), 3), shown(saved.get("script_wall_seconds"), 3),
                          shown(metrics.get("ttft_content_seconds"), 3), shown(call.get("raw_stream_bytes")),
                          shown(obj(sizes.get("original")).get("content_utf8_bytes")) + " → " + shown(obj(sizes.get("compact")).get("content_utf8_bytes")),
                          shown(saved.get("cleanup_status"))])
    real_html = table(["모델", "실제 입력", "종료 상태", "감시 경과 초", "정리 포함 전체 초", "첫 내용까지 초", "수신 bytes", "원형→압축 내용 bytes", "종료 후 정리"], real_rows) if real_rows else "<p>실제 문서 입력 진단 원본은 아직 연결되지 않았다. 원격 진행 상황이나 결과를 추정하지 않는다.</p>"
    if engineering["real_input"]:
        real_html += "<p>" + " · ".join(link(r["summary_path"], "실제 입력 진단 원본") for r in engineering["real_input"]) + "</p>"
        real_html += "<p>저장된 실제 입력 진단의 요청 설정: " + " · ".join(
            shown(obj(r.get("reported_summary")).get("model")) + " — " +
            ", ".join(esc(k) + "=" + shown(r.get("request_settings", {}).get(k))
                      for k in ("num_ctx", "num_predict", "num_thread", "temperature", "think", "repeat_penalty", "presence_penalty", "frequency_penalty", "seed"))
            for r in engineering["real_input"]) + ". 연구의 고정 예비 조건과 별도로 기록한다.</p>"
    review_links = []
    for review in engineering["independent_machine_reviews"]:
        matched = bool(review["summary_sha256_matches"])
        review_links.append(link(review["path"], "독립 코드 검토") + " · 보고된 통과 " + shown(review["reported_pass_count"]) + "/" + shown(review["check_count"]) + " · 현재 요약 해시 일치 " + shown(matched))
    engineering_reviews_html = "<p>" + "<br>".join(review_links) + "</p>" if review_links else ""
    hardware = engineering["hardware"]
    features = hardware["reported_cpu_features"]
    hardware_html = ""
    if features:
        hardware_html = "<p>별도 환경 기록에서 노출된 CPU 기능: " + ", ".join(esc(k) + "=" + ("지원" if v else "미지원") for k, v in sorted(features.items())) + ". " + link(hardware["path"], "환경 원본") + "</p>"
    score = pilot["details"]["offline_scores"]
    score_html = "<p>오프라인 점수 파일은 아직 연결되지 않았다.</p>"
    if isinstance(score, dict):
        rows = []
        interrupted_ids = {c["case_id"] for c in pilot["details"]["cases"] if c["execution_interruption_observed"]}
        for record in score.get("records", []):
            s = obj(record.get("score")); rating = obj(s.get("primary_rating"))
            interrupted = record.get("case_id") in interrupted_ids
            observed = record.get("status") != "not_started" and not interrupted
            rows.append([esc(record.get("case_id")), shown(record.get("status")),
                         shown(rating.get("correct")) + "/" + shown(rating.get("expected")) if observed else "중단: 완성된 응답의 의미 판단 미관측" if interrupted else "미시작: 모델 오류로 해석하지 않음",
                         shown(obj(s.get("allocation")).get("valid")) if observed else "해석 제외"])
        score_html = table(["사례", "평가기 기록", "원문 등급 일치", "비중 형식 유효"], rows)
        score_html += "<p>기술적인 사례별 점수다. 원본 평가기의 예정 사례 명부와 수치를 변경하지 않으며, 중단·미시작을 별도로 표시한다. 미완성 슬롯의 0을 관측된 의미 오답으로 해석하지 않는다. 인용 ID 일치가 이유의 타당성을 보증하지 않으며, 유일한 정답 비중·전략 우열·기관 전체에 대한 효과를 뜻하지 않는다.</p>"
    failures = value["assessment"]["failure_records"]
    failure_html = "<p>현재 읽은 파일에서 실패 기록이 없다는 사실만으로 전체 과제가 성공했다고 판정하지 않는다.</p>" if not failures else "<ul>" + "".join(f"<li>{esc(json.dumps(f, ensure_ascii=False))}</li>" for f in failures) + "</ul>"
    warnings = "<ul>" + "".join(f"<li>{esc(w)}</li>" for w in value["warnings"]) + "</ul>" if value["warnings"] else ""
    evidence = " · ".join([link(runtime.get("model_metadata_path"), "설치 메타데이터"), link(runtime.get("runtime_manifest_path"), "런타임 핀"),
                           link(diagnostic["run"].get("summary_path"), "기술 진단 요약"), link(pilot.get("summary_path"), "예비 요약"),
                           link(pilot.get("offline_scores_path"), "오프라인 점수"), link(diagnostic.get("independent_machine_review_path"), "독립 진단 코드 검토")])
    return f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LIBERA 원격 실행 관측 · 2026-10-18</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1100px;margin:40px auto;padding:0 20px;line-height:1.7;color:#162334;background:#fafbfc}}h1{{font-size:1.8rem}}h2{{font-size:1.2rem;margin-top:2rem}}p{{margin:.7rem 0}}.notice{{border-left:5px solid #27637a;padding:12px 18px;background:#edf5f8}}.scroll{{overflow:auto}}table{{border-collapse:collapse;width:100%;background:white;font-size:.9rem}}th,td{{padding:9px 11px;text-align:left;vertical-align:top;border:1px solid #dbe2e9}}th{{background:#edf1f5}}code{{overflow-wrap:anywhere}}a{{color:#145b88}}footer{{color:#536273;font-size:.8rem;margin-top:30px}}</style>
<h1>원격 소형 모델의 실행 관측</h1><p class="notice">이 보고서는 설치 확인·짧은 기술 진단·예비실험을 구분한다. 학술제 본실험 결과가 아니며, 실행 성공만으로 기관의 투자 판단을 올바르게 해석했다고 결론 내리지 않는다.</p>
{summary}<p>숫자는 받아온 파일에 한정된다. 미수신은 원격 미실행이나 실패를 뜻하지 않는다. 완료 HTTP 응답은 서버가 응답을 끝냈다는 뜻이며, 네 단계 완료·내용의 정확성과 다르다.</p>
<h2>모델과 설정</h2>{metadata}<p>기본 temperature는 실제 요청의 temperature로 덮어쓴다. 원시 요청에서 top_p·top_k·presence_penalty를 따로 지정하지 않았다면 메타데이터 기본값과 구분해 보고한다. 상속된 기본값을 금융 논문으로 선택한 수치라고 부르지 않는다. 실제 샘플링의 적용 순서와 효과는 엔진 구현에 의존한다. thinking 비활성화는 별도 사고 출력 요청을 끈 설정이며 추론 능력이 없다는 뜻이 아니다.</p>
<h2>실제로 걸린 시간</h2>{timings_html}<p>토큰 수와 처리속도는 Ollama 보고값이다. 진단은 256-token 상한의 짧은 합성 요청이며, 네 단계 예비 상한은 8192다. 짧은 진단 속도로 긴 문서의 완료시간이나 서버가 멈췄는지를 단정하지 않는다. 적재·입력 처리·생성 합과 벽시계 경과시간은 측정 범위가 다를 수 있다.</p>
<h2>메모리와 실행 위치</h2>{memories_html}{hardware_html}<p>RSS는 이름을 확인한 Ollama/llama-server 프로세스 합계이며 공유 페이지를 중복 셀 수 있다. cgroup에는 캐시와 다른 작업도 포함된다. 두 값을 더하거나 모두 모델 전용 RAM으로 읽지 않는다. memory.peak는 초기화하지 않은 누적 최대치이고, 위 표는 표본 최대치다. /proc RAM·swap과 상위 LXC 제한은 별개이며 visible memory.max가 max이면 상위 실효 한도는 확인되지 않는다. VRAM 0은 관측된 모델 배치 정보로, 물리 서버 GPU가 없다는 증거가 아니다.</p>
<h2>예비 사례와 평가</h2>{cancellation_html}{cases_html}<p>단계 기록은 응답을 파싱하고 계산 결과를 저장했다는 뜻이며 형식·전략의 타당성 통과 표시가 아니다. 별도의 사람 의미 검토는 대기 중이다.</p>{score_html}
<h2>별도 속도 진단: 짧은 합성 입력</h2>{latency_html}<p>이 표의 요청은 합성 입력을 쓴 기술 점검이며 4개 예비 사례·본과제 응답 수에 합산하지 않는다. 문맥·출력 상한·스레드·벌점 등의 비교 설정은 속도 점검용 공학적 선택이며 투자 실험의 논문 조건이 아니다. 설정별 한 번의 고정 순서 실행이고 모델·토크나이저·OS 캐시가 달라 통계적인 속도 순위나 네 단계 수행 가능성을 입증하지 않는다. 원래 예비실험과는 입력·문맥·벌점 등 전체 구성이 다르므로 모델 크기만의 속도 효과를 계산하지 않는다. 이 결과로 연구 런타임이나 본과제 조건을 자동 변경하지 않는다.</p>
<h2>별도 속도 진단: 실제 첫 단계 입력</h2>{real_html}<p>실제 기관 문서를 포함한 첫 단계 입력의 기술 점검이며 예비·본과제 사례 수에 합산하지 않는다. 중복 필드를 복원 가능한 형태로 정리한 입력만 전송하므로 원형 대비 속도 향상을 측정한 실험이 아니다. 필드값의 복원 일치도 같은 모델 행동을 보장하지 않는다. 32-token 출력 상한의 한 요청으로 네 단계 완주나 전략의 타당성을 평가할 수 없다. 종료 원본이 있더라도 속도 해결·작은 모델의 연구 적합성을 자동 승인하지 않는다.</p>{engineering_reviews_html}<p>독립 코드 검토는 저장 원본의 일관성 검사이며 사람의 금융 의미 검토가 아니다. GPU 메모리 보고값, 노출된 CPU 명령어, 입력 길이·처리시간은 각각 관측값이다. GPU 가속 부재나 벡터 명령어 미지원, 긴 입력 처리가 지연에 기여했을 가능성은 원인 후보이며 이 비교만으로 각 원인의 효과를 분리하거나 속도 문제가 해결됐다고 결론 내리지 않는다.</p>
<h2>한계와 후속 검토</h2>{failure_html}<p>각 요청 직전 digest·엔진·템플릿을 확인하는 코드가 있지만 조회 메타데이터 전체를 호출별로 저장하지 않았다. 최초 inventory, 실제 요청·응답, 코드·입력 해시를 근거로 하며 매 순간의 서비스 상태를 독립 재검증할 수 있다고 주장하지 않는다. 원격 예비실험 중 설정을 변경하지 않는다.</p>
<p><strong>본과제 동결 전 생성 설정의 근거를 해결해야 한다.</strong> FinVector 논문에는 penalty 값이 없으므로 상속된 presence_penalty=1.5를 논문 기반 수치라고 부를 수 없다. 후속 후보 seed=3407은 논문 §4.1에 직접 보고된 값이다. repeat_penalty=1·presence_penalty=0·frequency_penalty=0은 <a href="{FINVECTOR_EXAMPLE}">저자 공개 최소 예제</a>와 <a href="{MLX_GENERATE}">MLX-LM 0.31.3의 기본 argmax·logits_processors=None</a>에서 유추한 무벌점 구현 후보이며, 논문의 실제 벤치마크 보고값은 아니다. 미보고 기본값의 처리와 한계를 명시하는 조건 개정 결정을 기록하고 필요한 예비 재검증을 거친 뒤 본과제를 동결해야 한다. v4.3 예비·본과제 프로토콜에 자동 적용하지 않았으며, 별도 합성 속도 진단에서 사용해도 투자 과제에서 검증된 후보를 뜻하지 않는다.</p>
<p><a href="{FINVECTOR}">FinVector §4.1</a>은 thinking 비활성화·JSON·greedy의 선례다. 이 실행은 양자화·엔진·상속 기본값이 달라 전체 decoding 재현이 아니다. 8192는 <a href="{PORTBENCH}">PortBench §3.1</a> 값을 다른 모델·과제로 옮긴 적용이며, 65536 문맥은 구현 후보다. 문맥 할당 보고만으로 긴 문서나 이력 보존을 입증하지 않는다. 평가 규칙의 보완은 예비 이후 본과제 동결 전에 한다.</p>{warnings}
<h2>근거 파일</h2><p>{evidence}</p><p><a href="remote_sector_status_20261018.json">전체 관측 JSON·파일 해시·단계별 기록</a></p><footer>생성 {esc(value['generated_at_utc'])} · 읽기 전용 보고서 생성기 · 모델 호출 0 · 누락값은 미확인으로 보존</footer></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research")
    parser.add_argument("--latency-json", type=Path, action="append", default=[], help="Repeated synthetic engineering summary.json; kept separate from research counts")
    parser.add_argument("--real-input-json", type=Path, action="append", default=[], help="Repeated real-input engineering summary.json; never counted or scored as research cases")
    parser.add_argument("--engineering-audit-json", type=Path, action="append", default=[], help="Saved independent machine review; summary hashes must match before scope is linked")
    parser.add_argument("--hardware-json", type=Path, help="Retrieved remote CPU-feature record")
    parser.add_argument("--pilot-cancel-reason", choices=["user_requested_latency_revision"], help="Optional operator context; raw CANCEL and termination records remain primary")
    args = parser.parse_args()
    runtime_root, output_dir = args.runtime_root.resolve(), args.output_dir.resolve()
    if output_dir == runtime_root or runtime_root in output_dir.parents:
        raise ValueError("Report outputs must not be written inside the raw artifact tree")
    value = build_assessment(runtime_root, latency_paths=args.latency_json,
                             hardware_path=args.hardware_json, operator_cancel_reason=args.pilot_cancel_reason,
                             real_input_paths=args.real_input_json, engineering_review_paths=args.engineering_audit_json)
    # A retrieval still being copied must not produce a mixed-version report.
    for record in value["source_files"]:
        path = Path(record["path"])
        if not path.is_absolute():
            path = ROOT / path
        if path.is_file() != record["exists"] or (record["exists"] and hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]):
            raise RuntimeError("Source snapshot changed while reading; rerun after retrieval completes: " + record["path"])
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / "remote_sector_execution_20261018.html"
    json_path = output_dir / "remote_sector_status_20261018.json"
    value["report_html_path"] = relative(html_path)
    value["report_json_path"] = relative(json_path)
    value["runtime"]["report_path"] = relative(html_path)
    html_path.write_text(render_html(value, output_dir), encoding="utf-8")
    json_path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"html": relative(html_path), "status_json": relative(json_path),
                      "installation": value["installation"]["status"], "diagnosis": value["diagnostics"]["status"],
                      "pilot": value["pilot"]["status"], "pilot_completed_cases": value["pilot"]["completed_cases"],
                      "pilot_completed_calls": value["pilot"]["completed_calls"],
                      "assessment": value["assessment"]["status"], "warnings": value["warnings"], "model_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
