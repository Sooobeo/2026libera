"""Compare saved laptop/server engineering probes without running any model.

All paths are explicit inputs. Synthetic and optional real-input observations
stay separate from each other and from the research pilot/main. Missing results
are unknown, not zero or failure. This script never modifies raw/study files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from build_remote_sector_report import (
    ROOT, Reader, esc, extreme, gib, is_number, obj, read_latency, read_real_input,
    relative, request_settings, shown, table, unique,
)

EXPECTED_ENGINE = "0.35.1"
EXPECTED_DIGESTS = {
    "qwen3.5:4b-q4_K_M": "d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04",
    "qwen3:1.7b": "8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7",
}


def value_hash(value):
    if value is None:
        return None
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def normalized_parameters(value):
    """Ignore distinct-key line order, preserving repeated values (e.g. stops)."""
    if not isinstance(value, str):
        return None
    output = {}
    for line in value.splitlines():
        if not line.strip():
            continue
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            return None
        key, raw = parts
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = raw
        if type(parsed) is float and parsed.is_integer():
            parsed = int(parsed)
        output.setdefault(key, []).append(parsed)
    return output


def read_probe_details(reader, folder, model):
    """Use saved HTTP requests for conditions; specs alone are not execution."""
    calls = sorted(folder.glob("http_*/request.json"))
    requests = []
    for path in calls:
        request = obj(reader.read(path)); body = obj(request.get("body"))
        requests.append({"path": relative(path, reader.root), "body_sha256": value_hash(body) if body else None,
                         "messages_sha256": value_hash(body.get("messages")),
                         "options_sha256": value_hash(body.get("options")),
                         "settings": request_settings(body)})
    observation = reader.read(folder / "model_observation.json")
    if not isinstance(observation, dict):
        observation = reader.read(folder.parent / "model_observation_before_request.json")
    observation = obj(observation)
    show = obj(observation.get("show")); selected = obj(observation.get("selected_model"))
    template = show.get("template")
    template_hash = hashlib.sha256(template.encode("utf-8")).hexdigest() if isinstance(template, str) else None
    pins = {"model": selected.get("name"), "digest": selected.get("digest"),
            "engine": obj(observation.get("version")).get("version"),
            "quantization": obj(show.get("details")).get("quantization_level"),
            "template_sha256": template_hash,
            "reported_template_sha256": observation.get("template_sha256"),
            "template_hash_consistent": template_hash == observation["template_sha256"] if template_hash and observation.get("template_sha256") else None,
            "inherited_parameters": show.get("parameters"),
            "inherited_parameters_sha256": value_hash(show.get("parameters")),
            "inherited_parameters_normalized": normalized_parameters(show.get("parameters")),
            "inherited_parameters_normalized_sha256": value_hash(normalized_parameters(show.get("parameters")))}
    pins["approved_digest_match"] = matches(selected.get("digest"), EXPECTED_DIGESTS.get(model))
    pins["approved_engine_match"] = matches(pins["engine"], EXPECTED_ENGINE)
    pins["requested_model_matches_observed"] = matches(model, selected.get("name"))
    rows = reader.lines(folder / "monitor.jsonl")
    windows = [obj(row.get("memory")) for row in rows
               if obj(row.get("memory")).get("platform") == "win32" or
               obj(row.get("memory")).get("source") == "windows_existing_read_only_memory_collector"]
    processes = [p for memory in windows for p in memory.get("ollama_process_memory", []) if isinstance(p, dict)]
    performance = [obj(memory.get("system_performance_info")) for memory in windows]
    global_memory = [obj(memory.get("global_memory_status_ex")) for memory in windows]
    residency = []
    for row in rows:
        api = obj(row.get("ollama_ps"))
        if api.get("status") == "ok":
            residency.extend(m for m in obj(api.get("value")).get("models", [])
                             if isinstance(m, dict) and m.get("name") == model)
    cleanup = reader.read(folder / "unload_and_residency.json")
    if not isinstance(cleanup, dict):
        cleanup = reader.read(folder.parent / "unload_and_residency_after.json")
    cleanup = obj(cleanup)
    ps = cleanup.get("ps", [])
    explicit_idle = (obj(cleanup.get("unload")).get("status") == "ok" and
                     obj(obj(cleanup.get("unload")).get("value")).get("done") is True and
                     any(obj(p).get("status") == "ok" and obj(obj(p).get("value")).get("models") == [] for p in ps)) if cleanup else None
    return {"requests": requests, "pins": pins,
            "windows_memory": {
                "sample_count": len(windows),
                "working_set_sum_sampled_max_bytes": extreme([m.get("working_set_sum_bytes") for m in windows]),
                "system_available_physical_sampled_min_bytes": extreme([m.get("available_physical_bytes") for m in windows], min),
                "system_total_physical_bytes_observed": unique([m.get("total_physical_bytes") for m in global_memory]),
                "system_committed_sampled_max_bytes": extreme([m.get("committed_bytes") for m in performance]),
                "system_commit_limit_bytes_observed": unique([m.get("commit_limit_bytes") for m in performance]),
                "observed_process_names": unique([p.get("name") for p in processes]),
                "process_memory_sources": unique([p.get("memory_info_source") for p in processes]),
                "missing_working_set_samples": sum(not is_number(m.get("working_set_sum_bytes")) for m in windows),
                "interpretation": "Named process working sets may double-count shared pages; system available RAM and commit have distinct scopes. No cgroup or dedicated VRAM capacity is inferred."},
            "placement": {"model_residency_samples": len(residency),
                          "reported_vram_bytes": unique([m.get("size_vram") for m in residency]),
                          "reported_resident_bytes": unique([m.get("size") for m in residency]),
                          "reported_context_lengths": unique([m.get("context_length") for m in residency]),
                          "physical_gpu_capacity_inferred": False},
            "cleanup": cleanup, "completed_unload_and_empty_ps_observed": explicit_idle}


def load_environment(reader, environment, synthetic_paths, real_paths):
    runs = []
    for run in read_latency(reader, synthetic_paths):
        if isinstance(run.get("reported_summary"), dict) and any(
                run["reported_summary"].get(key) != 0 for key in ("pilot_model_calls", "main_model_calls")):
            raise ValueError("Synthetic engineering summaries must explicitly declare zero research calls")
        run.update(environment=environment, input_kind="synthetic")
        path = reader.root / run["summary_path"]
        for probe in run["probes"]:
            probe["saved_details"] = read_probe_details(reader, path.parent / probe["probe_id"], probe["model"])
        runs.append(run)
    for run in read_real_input(reader, real_paths):
        run.update(environment=environment, input_kind="real_input")
        path = reader.root / run["summary_path"]
        run["saved_details"] = read_probe_details(reader, path.parent / "compact_probe", obj(run.get("reported_summary")).get("model"))
        runs.append(run)
    return runs


def flatten(runs):
    rows = []
    for run in runs:
        if run["input_kind"] == "synthetic":
            for probe in run["probes"]:
                rows.append({**probe, "environment": run["environment"], "input_kind": "synthetic",
                             "summary_path": run["summary_path"]})
        else:
            if not isinstance(run.get("reported_summary"), dict):
                continue
            summary = obj(run.get("reported_summary"))
            rows.append({**run, "probe_id": summary.get("case_input"), "model": summary.get("model"),
                         "threads": obj(run.get("request_settings")).get("num_thread"),
                         "elapsed_seconds": obj(summary.get("supervisor")).get("elapsed_seconds"),
                         "deadline_seconds": obj(run.get("supervisor_result")).get("deadline_seconds", obj(summary.get("supervisor")).get("deadline_seconds")),
                         "deadline_source": "saved supervisor_result.deadline_seconds; summary display text does not override execution values",
                         "script_wall_seconds": summary.get("script_wall_seconds")})
    return rows


def matches(a, b):
    return None if a is None or b is None else a == b


def compare(rows):
    comparisons = []
    local = [r for r in rows if r["environment"] == "local_windows"]
    remote = [r for r in rows if r["environment"] == "remote_ct"]
    for left in local:
        for right in remote:
            if (left["input_kind"], left["model"], left["probe_id"]) != (right["input_kind"], right["model"], right["probe_id"]):
                continue
            lp, rp = left["saved_details"]["pins"], right["saved_details"]["pins"]
            lr, rr = left["saved_details"]["requests"], right["saved_details"]["requests"]
            lr, rr = lr[0] if len(lr) == 1 else {}, rr[0] if len(rr) == 1 else {}
            checks = {key: matches(lp.get(key), rp.get(key)) for key in
                      ("model", "digest", "engine", "quantization", "template_sha256", "inherited_parameters_normalized_sha256")}
            checks.update({key: matches(lr.get(key), rr.get(key)) for key in
                           ("body_sha256", "messages_sha256", "options_sha256")})
            comparisons.append({"model": left["model"], "probe_id": left["probe_id"], "input_kind": left["input_kind"],
                                "local_summary_path": left["summary_path"], "remote_summary_path": right["summary_path"],
                                "saved_request_and_pin_checks": checks,
                                "all_saved_controls_match": all(v is True for v in checks.values()),
                                "control_scope": "Saved HTTP request and model/engine pins only; supervisor deadlines are compared separately.",
                                "raw_inherited_parameter_text_match": matches(lp.get("inherited_parameters_sha256"), rp.get("inherited_parameters_sha256")),
                                "supervisor_deadlines": {"local_seconds": left.get("deadline_seconds"), "remote_seconds": right.get("deadline_seconds"),
                                                         "match": matches(left.get("deadline_seconds"), right.get("deadline_seconds"))},
                                "both_approved_pins_observed": all(p.get(k) is True for p in (lp, rp)
                                                                    for k in ("approved_digest_match", "approved_engine_match", "template_hash_consistent", "requested_model_matches_observed")),
                                "causal_speedup_or_statistical_ranking_established": False,
                                "limits": "OS, hardware, GPU placement, process/OS cache and single-run timing differ. Matching saved settings does not isolate a hardware or model-size effect. No speed ratio is inferred from censored runs."})
    return comparisons


def build(local_synthetic, remote_synthetic, local_real=None, remote_real=None, hardware_path=None, root=ROOT,
          correction_paths=None, audit_paths=None, backend_log_paths=None,
          final_runtime_path=None, startup_record_path=None, startup_helper_path=None):
    reader = Reader(root)
    runs = load_environment(reader, "local_windows", local_synthetic, local_real or [])
    runs += load_environment(reader, "remote_ct", remote_synthetic, remote_real or [])
    rows = flatten(runs)
    hardware = reader.read(hardware_path) if hardware_path else None
    final_runtime = reader.read(final_runtime_path) if final_runtime_path else None
    startup_record = reader.read(startup_record_path) if startup_record_path else None
    if startup_helper_path:
        reader.record(startup_helper_path)
    corrections = []
    for path in correction_paths or []:
        correction = reader.read(path)
        if not isinstance(correction, dict):
            continue
        original = correction.get("original_summary")
        record = reader.record(root / original) if isinstance(original, str) else {}
        matched = record.get("exists") is True and record.get("sha256") == correction.get("original_summary_sha256")
        if not matched:
            reader.warnings.append("Correction original summary hash mismatch: " + relative(path, root))
        corrections.append({"path": relative(path, root), "original_summary_hash_matches": matched, "record": correction})
    reviews = []
    for path in audit_paths or []:
        review = reader.read(path)
        if isinstance(review, dict):
            reviews.append({"path": relative(path, root), "status": review.get("status"), "scope": review.get("scope"),
                            "checks_passed": review.get("checks_passed", sum(c.get("status") == "pass" for c in review.get("checks", []))),
                            "reported_limits": review.get("limits", review.get("limitations", [])),
                            "human_semantic_review": False})
    backend = []
    for path in backend_log_paths or []:
        record = reader.record(path)
        extracted = []
        if record["exists"]:
            for number, line in enumerate(path.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1):
                if 'msg="inference compute"' in line or re.search(r"offloaded \d+/\d+ layers to GPU", line) or "Vulkan0 KV buffer size" in line:
                    extracted.append({"line": number, "text": line})
        backend.append({"path": relative(path, root), "exists": record["exists"], "sha256": record["sha256"],
                        "excerpts": extracted, "scope": "Immutable log snapshot; backend-reported device/layer placement, not dedicated VRAM capacity or an isolated causal speedup."})
    reader.record(Path(__file__))
    reader.record(Path(__file__).with_name("build_remote_sector_report.py"))
    return {"schema_version": "local_remote_engineering_comparison_1.0",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "builder": "research/build_local_latency_report.py",
            "scope": "Saved engineering observations only; no inference, evaluation, installation or study mutation by this builder.",
            "builder_model_calls": 0, "pilot_model_calls": 0, "main_model_calls": 0,
            "research_count_scope": "All linked probes are engineering calls, excluded from the existing research pilot/main; zero is not a claim about all historical project attempts.",
            "hardware": {"path": relative(hardware_path, root) if hardware_path else None, "record": hardware,
                         "capacity_caveat": "Arc 140V display name '(16GB)' and AdapterRAM do not establish dedicated VRAM capacity; actual Ollama placement is reported separately."},
            "runs": runs, "observations": rows, "comparisons": compare(rows),
            "additive_metadata_corrections": corrections, "independent_machine_reviews": reviews,
            "immutable_backend_evidence": backend,
            "local_service_snapshot": {
                "final_runtime_path": relative(final_runtime_path, root) if final_runtime_path else None,
                "final_runtime_record": final_runtime,
                "startup_record_path": relative(startup_record_path, root) if startup_record_path else None,
                "startup_record": startup_record,
                "startup_helper_path": relative(startup_helper_path, root) if startup_helper_path else None,
                "scope": "Saved installation/residency and service-start observations, not a live query or proof that this process performed earlier benchmarks."},
            "local_observed_probes": sum(r["environment"] == "local_windows" and bool(r["saved_details"]["requests"]) for r in rows),
            "local_observed_generation_request_envelopes": sum(len(r["saved_details"]["requests"]) for r in rows if r["environment"] == "local_windows"),
            "local_observed_real_input_probes": sum(r["environment"] == "local_windows" and r["input_kind"] == "real_input" and bool(r["saved_details"]["requests"]) for r in rows),
            "research_suitability_certified": False, "latency_solution_certified": False,
            "source_files": list(reader.sources.values()), "warnings": reader.warnings}


def render(value, directory, root=ROOT):
    def link(path, title):
        if not path:
            return "미연결"
        return '<a href="' + esc(os.path.relpath(root / path, directory).replace("\\", "/")) + '">' + esc(title) + '</a>'

    labels = {"local_windows": "노트북 Windows", "remote_ct": "서버 CT", "synthetic": "짧은 합성", "real_input": "실제 첫 단계"}
    timing_rows, controls, memory, pin_rows = [], [], [], []
    for row in value["observations"]:
        calls = row.get("calls", []); call = calls[0] if len(calls) == 1 else {}; metrics = obj(call.get("metrics"))
        details = row["saved_details"]; pin = details["pins"]
        requested = details["requests"][0]["settings"] if len(details["requests"]) == 1 else {}
        name = labels[row["environment"]] + " / " + labels[row["input_kind"]] + " / " + str(row["probe_id"])
        timing_rows.append([esc(name), shown(row.get("model")), shown(row.get("status")),
                            shown(row.get("deadline_seconds")), shown(row.get("elapsed_seconds"), 3), shown(metrics.get("wall_seconds"), 3),
                            shown(metrics.get("ttft_any_generated_seconds"), 3) + " / " + shown(metrics.get("ttft_content_seconds"), 3),
                            shown(metrics.get("load_duration_seconds"), 3), shown(metrics.get("prompt_eval_duration_seconds"), 3),
                            shown(metrics.get("eval_duration_seconds"), 3), shown(metrics.get("total_duration_seconds"), 3),
                            shown(metrics.get("prompt_eval_count")) + " / " + shown(metrics.get("eval_count")),
                            shown(metrics.get("prompt_eval_tokens_per_second")) + " / " + shown(metrics.get("eval_tokens_per_second")),
                            shown(call.get("raw_stream_bytes"))])
        controls.append([esc(name), shown(requested.get("num_thread")), shown(requested.get("num_ctx")), shown(requested.get("num_predict")),
                         shown(requested.get("temperature")) + " / " + shown(requested.get("think")),
                         " / ".join(shown(requested.get(k)) for k in ("repeat_penalty", "presence_penalty", "frequency_penalty")),
                         shown(requested.get("seed")), shown(details["completed_unload_and_empty_ps_observed"])])
        wm, remote = details["windows_memory"], obj(row.get("resources"))
        memory.append([esc(name), shown(wm["sample_count"] if row["environment"] == "local_windows" else remote.get("sample_count")),
                       gib(wm["working_set_sum_sampled_max_bytes"]) if row["environment"] == "local_windows" else "해당 없음",
                       gib(remote.get("runtime_rss_sum_sampled_max_bytes")) if row["environment"] == "remote_ct" else "해당 없음",
                       gib(remote.get("cgroup_memory_current_sampled_max_bytes")) if row["environment"] == "remote_ct" else "해당 없음",
                       gib(wm["system_available_physical_sampled_min_bytes"] if row["environment"] == "local_windows" else remote.get("proc_available_sampled_min_bytes")),
                       gib(wm["system_committed_sampled_max_bytes"]) if row["environment"] == "local_windows" else "해당 없음",
                       ", ".join(shown(x) for x in details["placement"]["reported_vram_bytes"]) or "미관측",
                       ", ".join(shown(x) for x in details["placement"]["reported_context_lengths"]) or "미관측"])
        pin_rows.append([esc(name), shown(pin["engine"]), shown(pin["quantization"]),
                         shown(pin["approved_digest_match"]) + " / " + shown(pin["approved_engine_match"]), '<code>' + shown(pin["digest"]) + '</code>',
                         '<code>' + shown(pin["template_sha256"]) + '</code>'])
    comparison_rows = [[shown(c["model"]) + " / " + esc(str(c["probe_id"])), labels[c["input_kind"]], shown(c["all_saved_controls_match"]),
                        shown(c["supervisor_deadlines"]["local_seconds"]) + " / " + shown(c["supervisor_deadlines"]["remote_seconds"]),
                        esc(json.dumps(c["saved_request_and_pin_checks"], ensure_ascii=False))] for c in value["comparisons"]]
    hardware = obj(value["hardware"]["record"])
    hardware_text = (shown(obj(hardware.get("cpu")).get("Name")) + ", RAM " + gib(hardware.get("ram_bytes")) +
                     ", 표시 장치 " + shown(obj(hardware.get("display_controller")).get("Name"))) if hardware else "노트북 하드웨어 원본 미연결"
    evidence = " · ".join(link(r["summary_path"], labels[r["environment"]] + " " + labels[r["input_kind"]] + " 원본") for r in value["runs"])
    timings = table(["관측", "모델", "상태", "감시 제한 초", "감시 경과 초", "HTTP 경과 초", "첫 생성/내용 초", "적재 초", "입력 처리 초", "생성 초", "엔진 전체 초", "입력/출력 토큰", "입력/생성 tok/s", "수신 bytes"], timing_rows) if timing_rows else "<p>연결된 호출 원본이 없다. 설치·실행·실패를 추정하지 않는다.</p>"
    correction_html = "".join("<p>" + link(c["path"], "원본을 보존한 메타데이터 정정") + " · 원본 SHA 일치 " + shown(c["original_summary_hash_matches"]) +
                              ": 요약의 설명 문구와 별개로 실제 supervisor 제한값은 " + shown(c["record"].get("actual_deadline_seconds")) + "초다.</p>" for c in value["additive_metadata_corrections"])
    review_html = "<p>" + " · ".join(link(r["path"], "독립 코드 검토 " + str(r["checks_passed"]) + "개 통과") for r in value["independent_machine_reviews"]) + "</p>" if value["independent_machine_reviews"] else ""
    host_limit_html = ""
    if any("host was not isolated" in str(limit).lower() for review in value["independent_machine_reviews"] for limit in review["reported_limits"]):
        host_limit_html = "<p>4B 원본 감사에는 실제 입력 실행 중 같은 노트북에서 보고서 도구의 --help와 모니터링도 동작했다고 기록되어 있다. 다른 작업을 차단한 전용 성능 시험이 아니므로 이번 시간은 그 운영 상황의 단회 관측으로 읽는다.</p>"
    backend_html = "".join("<p>" + link(b["path"], "고정한 실행 로그") + "</p><ul>" + "".join("<li>" + str(e["line"]) + "행: <code>" + esc(e["text"]) + "</code></li>" for e in b["excerpts"]) + "</ul>" for b in value["immutable_backend_evidence"])
    service = value["local_service_snapshot"]; final_state = obj(service["final_runtime_record"]); startup = obj(service["startup_record"])
    service_html = ""
    if final_state or startup:
        residency = obj(final_state.get("/api/ps")).get("models")
        empty = residency == [] if isinstance(residency, list) else None
        service_html = ("<h2>별도로 보존한 마지막 서비스 상태</h2><p>기록된 API 버전 " + shown(obj(final_state.get("/api/version")).get("version")) +
                        ", 모델 상주 없음 관측 " + shown(empty) + ". 별도 시작 기록 PID " + shown(startup.get("pid")) +
                        ", loopback 리스너 소유 확인 " + shown(startup.get("listener_owner_verified")) + ". " +
                        link(service["final_runtime_path"], "설치·상주 확인 원본") + " · " + link(service["startup_record_path"], "서비스 시작 기록") +
                        " · " + link(service["startup_helper_path"], "재시작 도구") +
                        ". 저장 시점의 관측이며 실시간 상태나 앞선 성능 시험을 이 PID가 수행했다는 주장이 아니다.</p>")
    return f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>노트북·서버 성능 관측 비교</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1200px;margin:35px auto;padding:0 20px;line-height:1.7;color:#17283a;background:#fafbfc}}h1{{font-size:1.8rem}}h2{{font-size:1.2rem;margin-top:2rem}}.notice{{border-left:5px solid #27637a;padding:12px 16px;background:#edf5f8}}.scroll{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:.88rem;background:#fff}}th,td{{padding:8px;border:1px solid #dbe2e9;text-align:left;vertical-align:top}}th{{background:#edf1f5}}code{{overflow-wrap:anywhere}}a{{color:#145b88}}footer{{color:#59697a;font-size:.8rem}}</style>
<h1>노트북·서버의 실행 시간 관측</h1><p class="notice">설치 후 수행한 별도 기술 점검을 비교하는 보고서다. 요청 파일을 확인한 노트북 점검은 {value['local_observed_probes']}개이며 그중 실제 입력은 {value['local_observed_real_input_probes']}개다. 이는 연결된 증거 수로, 프로젝트 전체 실행 횟수가 아니다. 여기의 요청은 연구 예비·본과제 응답 수에 포함하지 않으며 금융 판단의 정확성을 채점하지 않았다.</p>
<h2>실제로 받은 응답과 시간</h2>{timings}{correction_html}<p>감시 시간은 자식 프로세스 수명, HTTP 시간은 요청 관측, 엔진 전체 시간은 서버 보고값이다. 첫 생성 출력은 ttft_any_generated_seconds, 첫 내용은 ttft_content_seconds 원필드를 사용한다. hard deadline은 그 시점까지 완료하지 못한 관측이며 완료시간으로 바꾸지 않는다. 종료 응답이 없어 토큰이나 처리시간을 받지 못하면 0이 아닌 미확인으로 둔다. 짧은 합성 JSON의 성공은 긴 기관 문서·네 단계 실험 수행을 보장하지 않는다. 실제 입력의 출력 상한 도달은 32-token 공학 상한에서 응답이 잘렸다는 뜻이며 요구 JSON의 완결성·금융 판단 정확성을 검증하지 않았다.</p>
<h2>비교 조건과 모델 확인</h2>{table(['관측','요청 스레드','문맥 상한','출력 상한','T / thinking','repeat / presence / frequency','seed','해제 완료·빈 ps 확인'], controls)}
{table(['대응 관측','입력 종류','저장 요청·모델핀 일치','감시 제한: 노트북/서버 초','입력·옵션·핀별 비교'], comparison_rows) if comparison_rows else '<p>같은 모델·입력·probe ID의 노트북/서버 쌍이 아직 없다.</p>'}
<p>모델 manifest·엔진·양자화·템플릿·기본값과 실제 요청의 메시지·옵션·전체 본문 해시를 비교한다. 기본값 문자열의 원시 해시는 보존하되 서로 다른 키의 줄 순서는 설정 차이로 보지 않으며, 같은 키의 반복값(예: stop)은 순서와 값을 보존한다. prompt.txt 파일의 OS별 개행과 실제 보낸 입력도 구분한다. 누락된 근거는 일치로 처리하지 않는다. 감시 제한시간은 요청·모델핀과 별도로 비교한다. 같은 요청이라도 OS·하드웨어·GPU 배치·프로세스 및 OS 캐시가 다르고 각 설정은 단회 관측이므로 일반적인 성능 배율이나 원인별 효과를 주장하지 않는다. 스레드는 요청값이며 실제 사용 스레드 수와 같다고 가정하지 않는다. 32-token 출력, 문맥·벌점·스레드 설정은 공학 점검 조건이며 논문 실험의 전체 재현이 아니다.</p>
{table(['관측','엔진','양자화','승인 digest / 엔진 일치','실제 모델 digest','관측 템플릿 SHA256'], pin_rows)}
<h2>메모리와 배치</h2><p>{hardware_text}. {link(value['hardware']['path'], '하드웨어 원본')}. 표시 이름의 16GB나 AdapterRAM을 전용 VRAM 용량으로 해석하지 않는다.</p>
{table(['관측','표본 수','Windows working set 최대','Linux RSS 합 최대','cgroup 사용 표본 최대','시스템 가용 RAM 최소','Windows 시스템 commit 최대','API 보고 VRAM bytes','API 보고 문맥'], memory)}
<p>Windows working set과 Linux RSS는 관측한 이름의 프로세스 합이며 공유 페이지를 중복 셀 수 있다. cgroup은 다른 작업·캐시를 포함하며 Windows 값과 직접 동일시하지 않는다. 시스템 commit은 resident RAM이 아니고, 서로 다른 범위의 수치를 더하지 않는다. 메모리 누락은 0 사용량이 아니다. Ollama 보고 VRAM은 실행 배치 관측이며 물리 GPU의 전용 용량을 측정한 값이 아니다.</p>
{backend_html}
{service_html}
<h2>해석 범위</h2><p>실제 입력 점검이 연결되어 있어도 한 단계·짧은 출력 상한의 기술 진단이다. 중복 정리 입력만 전송했다면 원형 대비 속도 향상을 측정한 것이 아니며, 필드 복원 일치가 동일한 모델 행동을 뜻하지 않는다. 이 보고서는 속도 문제 해결·모델 추천·본실험 적합성을 자동 승인하지 않고 기존 연구 모델과 평가 조건을 변경하지 않는다.</p>{host_limit_html}
<h2>근거 파일</h2><p>{evidence or '원본 미연결'}</p>{review_html}<p>독립 코드는 저장 기록의 일관성을 검토하며 사람의 금융 의미 검토를 대신하지 않는다. 각 원본 경로·해시·세부 관측은 {link(value.get('report_json_path'), '전체 관측 JSON')}에 보존했다.</p>
{('<p>읽기 경고: '+esc(json.dumps(value['warnings'],ensure_ascii=False))+'</p>') if value['warnings'] else ''}
<footer>{esc(value['generated_at_utc'])} · 읽기 전용 생성 · 이 생성기의 모델 호출 0</footer></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("local-latency", "remote-latency", "local-real-input", "remote-real-input"):
        parser.add_argument("--" + name + "-json", type=Path, action="append", default=[])
    parser.add_argument("--hardware-json", type=Path)
    parser.add_argument("--correction-json", type=Path, action="append", default=[])
    parser.add_argument("--audit-json", type=Path, action="append", default=[])
    parser.add_argument("--backend-log", type=Path, action="append", default=[], help="Immutable server-log snapshots only")
    parser.add_argument("--final-runtime-json", type=Path)
    parser.add_argument("--startup-record-json", type=Path)
    parser.add_argument("--startup-helper", type=Path)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research")
    parser.add_argument("--output-stem", default="local_sector_latency_20261018")
    args = parser.parse_args()
    if Path(args.output_stem).name != args.output_stem or args.output_stem in (".", ".."):
        raise ValueError("Output stem must be a filename component")
    inputs = args.local_latency_json + args.remote_latency_json + args.local_real_input_json + args.remote_real_input_json
    destination = args.output_dir.resolve()
    for path in inputs:
        if destination == path.resolve().parent or path.resolve().parent in destination.parents:
            raise ValueError("Report output must not be inside a raw artifact directory")
    value = build(args.local_latency_json, args.remote_latency_json, args.local_real_input_json,
                  args.remote_real_input_json, args.hardware_json, correction_paths=args.correction_json,
                  audit_paths=args.audit_json, backend_log_paths=args.backend_log,
                  final_runtime_path=args.final_runtime_json, startup_record_path=args.startup_record_json,
                  startup_helper_path=args.startup_helper)
    for record in value["source_files"]:
        path = ROOT / record["path"]
        if path.is_file() != record["exists"] or (record["exists"] and hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]):
            raise RuntimeError("Source changed while reading; rerun after retrieval completes: " + record["path"])
    destination.mkdir(parents=True, exist_ok=True)
    html_path, json_path = (destination / (args.output_stem + ext) for ext in (".html", ".json"))
    if any(path.resolve() in (html_path.resolve(), json_path.resolve()) for path in inputs + ([args.hardware_json] if args.hardware_json else [])):
        raise ValueError("Refusing to overwrite an input file")
    value.update(report_html_path=relative(html_path), report_json_path=relative(json_path))
    html_path.write_text(render(value, destination), encoding="utf-8")
    json_path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"html": relative(html_path), "json": relative(json_path),
                      "local_observed_probes": value["local_observed_probes"],
                      "paired_comparisons": len(value["comparisons"]), "warnings": value["warnings"],
                      "builder_model_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
