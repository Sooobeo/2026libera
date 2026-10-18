"""Render saved installation/diagnostic records; never contact a model or network.

python research/build_runtime_report.py --install-dir data/sector_runtime/install_...
    --diagnostic-dir data/sector_runtime/health_... --diagnostic-dir data/sector_runtime/stage1_...

This report distinguishes installed artifacts, one-request technical diagnostics,
and the not-yet-established suitability of a full experimental workflow. Missing
measurements remain null. It does not alter plans, paper drafts, or runtime settings.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import math
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATE = "20261017"
TARGET = "qwen3.6:35b"
GIB = 1024 ** 3
STATUS_KO = {
    "installed": "설치 완료 기록 있음", "installation_failed": "설치 실패 기록 있음",
    "installation_in_progress_or_unfinalized": "설치 진행 / 미종결 · 완료 기록 없음",
    "installation_not_observed": "설치 기록 미확인", "installation_record_unreadable": "설치 기록 읽기 오류",
    "installation_records_conflict": "설치 완료·실패 기록이 함께 있음 · 확인 필요",
    "completed_generation": "응답 생성 완료", "output_limit_reached": "출력 한도 도달",
    "timeout": "시간 제한 종료", "cancelled": "취소됨", "request_error": "요청 오류",
    "http_error": "HTTP 오류", "incomplete_stream": "응답 스트림 미완료",
    "dry_run": "입력 작성만 수행", "diagnostic_in_progress_or_unfinalized": "진행 / 미종결 · 요약 기록 없음",
    "diagnostic_not_observed": "진단 기록 미확인", "diagnostic_record_unreadable": "진단 기록 읽기 오류",
    "diagnostic_failed_recorded": "진단 실패 기록 있음",
}


def num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def at(value, *keys):
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def unwrap(value):
    return value.get("value") if isinstance(value, dict) and "value" in value else value


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


class Records:
    def __init__(self):
        self.sources = {}
        self.issues = []

    def read(self, path: Path, lines=False):
        key = rel(path)
        if not path.is_file():
            self.sources[key] = {"exists": False, "status": "not_present_at_report_time"}
            return None
        raw = path.read_bytes()
        self.sources[key] = {"exists": True, "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                             "modified_at_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()}
        try:
            text = raw.decode("utf-8-sig")
            if not lines:
                value = json.loads(text)
            else:
                value = []
                for index, line in enumerate(text.splitlines(), 1):
                    if not line.strip():
                        continue
                    try:
                        value.append(json.loads(line))
                    except (ValueError, TypeError):
                        self.issues.append({"path": key, "line": index, "issue": "unreadable_JSONL_row_possibly_in_flight"})
            self.sources[key]["status"] = "read"
            return value
        except (ValueError, UnicodeError) as exc:
            self.sources[key]["status"] = "unreadable"
            self.issues.append({"path": key, "issue": type(exc).__name__, "message": str(exc)})
            return None


def model_fields(record):
    if not isinstance(record, dict):
        return None
    return {"name": record.get("name", record.get("model")), "digest": record.get("digest"),
            "size_bytes": record.get("size"), "parameter_size": at(record, "details", "parameter_size"),
            "quantization": at(record, "details", "quantization_level"),
            "format": at(record, "details", "format"), "family": at(record, "details", "family"),
            "advertised_context_length": at(record, "details", "context_length")}


def installation(folder: Path, records: Records):
    before = records.read(folder / "before.json")
    result = records.read(folder / "result.json")
    failure = records.read(folder / "failure.json")
    events = records.read(folder / "pull_events.jsonl", lines=True)
    show = records.read(folder / "model_show.json")
    if isinstance(result, dict) and result.get("status") == "installed" and failure is not None:
        state = "installation_records_conflict"
    elif isinstance(result, dict) and result.get("status") == "installed":
        state = "installed"
    elif failure is not None or any(isinstance(x, dict) and x.get("error") for x in (events or [])):
        state = "installation_failed"
    elif records.sources[rel(folder / "result.json")].get("status") == "unreadable":
        state = "installation_record_unreadable"
    elif before is not None or events is not None:
        state = "installation_in_progress_or_unfinalized"
    else:
        state = "installation_not_observed"
    model = model_fields(at(result, "model"))
    if model is not None and model["quantization"] is None:
        model["quantization"] = at(show, "details", "quantization_level")
    before_models = at(before, "models", "models")
    last = events[-1] if events else None
    return {"directory": rel(folder), "status": state, "target_model": TARGET, "model": model,
            "engine_version": at(result, "engine", "version") or at(before, "version", "version"),
            "engine_version_observation_phase": "installation_result" if at(result, "engine", "version") else "before_attempt",
            "install_elapsed_seconds": at(result, "elapsed_seconds") if at(result, "elapsed_seconds") is not None else at(failure, "elapsed_seconds"),
            "recorded_inference_calls": at(result, "inference_calls") if at(result, "inference_calls") is not None else at(failure, "inference_calls"),
            "failure": failure,
            "template_sha256": at(result, "template_sha256"),
            "installed_before_this_attempt": any(x.get("name") == TARGET for x in before_models) if isinstance(before_models, list) else None,
            "last_pull_event": last, "pull_event_count": len(events) if events is not None else None,
            "elapsed_source": rel(folder / "result.json") if result is not None else None,
            "installation_does_not_establish_experiment_suitability": True}


def memory_values(snapshot):
    return {"observed_at_utc": at(snapshot, "observed_at_utc"),
            "total_physical_bytes": at(snapshot, "global_memory_status_ex", "total_physical_bytes"),
            "available_physical_bytes": at(snapshot, "global_memory_status_ex", "available_physical_bytes"),
            "committed_bytes": at(snapshot, "system_performance_info", "committed_bytes"),
            "commit_limit_bytes": at(snapshot, "system_performance_info", "commit_limit_bytes")}


def ps_models(record):
    value = unwrap(record)
    models = value.get("models") if isinstance(value, dict) else None
    if not isinstance(models, list):
        return None
    keys = ("name", "model", "digest", "size", "size_vram", "context_length", "processor", "backend", "gpu", "offload", "expires_at", "details")
    return [{k: m[k] for k in keys if k in m} for m in models if isinstance(m, dict)]


def diagnostic(folder: Path, records: Records):
    manifest = records.read(folder / "diagnostic_manifest.json")
    request = records.read(folder / "request.json")
    summary = records.read(folder / "summary.json")
    before = records.read(folder / "before.json")
    after = records.read(folder / "after.json")
    samples = records.read(folder / "resource_samples.jsonl", lines=True)
    failure = records.read(folder / "failure.json")
    monitor_error = records.read(folder / "monitor_error.json")
    if isinstance(summary, dict):
        status = summary.get("status", "diagnostic_record_unreadable")
    elif failure is not None:
        status = "diagnostic_failed_recorded"
    elif records.sources[rel(folder / "summary.json")].get("status") == "unreadable":
        status = "diagnostic_record_unreadable"
    elif manifest is not None or before is not None or samples is not None:
        status = "diagnostic_in_progress_or_unfinalized"
    else:
        status = "diagnostic_not_observed"
    tags = unwrap(at(before, "tags"))
    models = tags.get("models") if isinstance(tags, dict) else None
    name = at(request, "model")
    model = next((model_fields(m) for m in models if m.get("name") == name), None) if isinstance(models, list) else None
    show = unwrap(at(before, "show"))
    # Read measured resource samples separately from the provider's timing summary.
    free, commit, limits = [], [], []
    ps = []
    def ps_signature(models):
        return json.dumps([{k: v for k, v in m.items() if k != "expires_at"} for m in models], sort_keys=True)
    def collect_ps(record, source, elapsed=None):
        value = ps_models(record)
        if value is not None:
            entry = {"source": source, "elapsed_seconds": elapsed, "models": value}
            signature = ps_signature(value)
            if not ps or ps_signature(ps[-1]["models"]) != signature:
                ps.append(entry)
    collect_ps(at(before, "ps"), rel(folder / "before.json"))
    for i, row in enumerate(samples or [], 1):
        if not isinstance(row, dict):
            continue
        mem = memory_values(row.get("memory"))
        for key, dest in (("available_physical_bytes", free), ("committed_bytes", commit), ("commit_limit_bytes", limits)):
            if num(mem[key]) is not None:
                dest.append(mem[key])
        collect_ps(row.get("ollama_ps"), f"{rel(folder / 'resource_samples.jsonl')}:{i}", row.get("elapsed_seconds"))
    collect_ps(at(after, "ps"), rel(folder / "after.json"))
    provider = at(summary, "provider_metrics")
    if not isinstance(provider, dict):
        provider = None
    mode = at(manifest, "mode")
    return {"directory": rel(folder), "status": status, "mode": mode,
            "scope": "technical_health_check_not_experiment" if mode == "health" else "single_stage1_load_check_not_full_pilot_or_main" if mode == "stage1" else "unclassified_saved_diagnostic",
            "requested_model": name, "model": model,
            "engine_version": at(unwrap(at(before, "version")), "version"),
            "show_quantization": at(show, "details", "quantization_level"),
            "requested_context_tokens": at(request, "options", "num_ctx"),
            "requested_output_cap": at(request, "options", "num_predict"),
            "thinking": at(request, "think"), "temperature": at(request, "options", "temperature"),
            "model_requests_attempted": at(summary, "model_requests_attempted"),
            "experiment_calls_counted": at(summary, "experiment_calls_counted"),
            "client_wall_seconds": at(summary, "client_inference_wall_seconds"),
            "first_stream_chunk_seconds": at(summary, "first_stream_chunk_seconds"),
            "first_thinking_chunk_seconds": at(summary, "first_thinking_chunk_seconds"),
            "first_answer_chunk_seconds": at(summary, "first_answer_chunk_seconds"),
            "provider_metrics": provider, "provider_metrics_source": rel(folder / "summary.json"),
            "memory": {"before": memory_values(at(before, "memory")), "after": memory_values(at(after, "memory")),
                       "sample_count": len(samples) if samples is not None else None,
                       "sampled_minimum_available_physical_bytes": min(free) if free else None,
                       "sampled_maximum_committed_bytes": max(commit) if commit else None,
                       "sampled_commit_limit_bytes_observed": sorted(set(limits)) if limits else None,
                       "reported_summary_resources": at(summary, "resources"),
                       "sample_source": rel(folder / "resource_samples.jsonl")},
            "actual_ps_observations": ps, "error": at(summary, "error") or failure,
            "monitor_error": monitor_error,
            "completion_caution": "Completed generation is not a validated finance answer, complete four-stage pilot, throughput guarantee, or experiment suitability decision."}


def esc(value):
    return html.escape(str(value))


def fmt(value, unit="", digits=2):
    if value is None:
        return "미확인"
    return (f"{value:,.{digits}f}" if num(value) is not None else esc(value)) + unit


def gib(value):
    return fmt(value / GIB if num(value) is not None else None, " GiB")


def row(label, value):
    return f"<tr><th>{esc(label)}</th><td>{value}</td></tr>"


def make_html(report, html_path):
    install = report["installation"]
    local = report["hardware"]["local"]
    remote = report["hardware"]["remote_user_report"]
    local_mem = at(local, "computer", "TotalPhysicalMemory")
    remote_mem = at(remote, "reported", "total_physical_memory_bytes")
    model = install.get("model") or {}
    interruption = report.get("interruption_record")
    interruption_html = ""
    if isinstance(interruption, dict):
        observed = interruption.get("observations", {})
        state = lambda value: "존재" if value is True else "없음" if value is False else "미확인"
        connection = "응답 가능" if interruption.get("localhost_11434_accepts_connection") is True else "접속 불가" if interruption.get("localhost_11434_accepts_connection") is False else "미확인"
        interruption_html = (f"<p class='note'>별도 중단 관측({esc(interruption.get('recorded_at_utc', '시각 미확인'))}, "
                             f"{esc(interruption.get('installation_directory', '시도 미확인'))}): "
                             f"Ollama 실행 파일 {state(at(observed, 'ollama_executable', 'exists'))}, "
                             f"당시 API {connection}. 이후 상태를 대신하지 않는 역사 기록입니다. "
                             f"원인 기록: {esc(interruption.get('cause', '미확인'))}</p>")
    tables = []
    for d in report["diagnostics"]:
        p = d.get("provider_metrics") or {}
        m = d["memory"]
        label = "짧은 기능 진단" if d["mode"] == "health" else "단계 1 부하 진단" if d["mode"] == "stage1" else "진단"
        text = row("상태", esc(STATUS_KO.get(d["status"], d["status"])))
        text += row("설정", f"{fmt(d['requested_model'])} · context {fmt(d['requested_context_tokens'], digits=0)} · 출력 상한 {fmt(d['requested_output_cap'], digits=0)}")
        text += row("엔진 / 실제 모델", f"{fmt(d['engine_version'])} / {fmt(at(d, 'model', 'quantization') or d['show_quantization'])}<br><code>{fmt(at(d, 'model', 'digest'))}</code>")
        text += row("제공자 시간(초)", "로드 " + fmt(p.get("load_duration_seconds")) + " · 프롬프트 처리 " + fmt(p.get("prompt_eval_duration_seconds")) + " · 생성 " + fmt(p.get("eval_duration_seconds")) + " · 전체 " + fmt(p.get("total_duration_seconds")))
        text += row("클라이언트 시간", fmt(d["client_wall_seconds"], "초") + " · 첫 thinking " + fmt(d["first_thinking_chunk_seconds"], "초") + " · 첫 답변 " + fmt(d["first_answer_chunk_seconds"], "초"))
        text += row("제공자 출력 속도", fmt(p.get("generation_tokens_per_second"), " token/s") + " · 출력 수 " + fmt(p.get("eval_count"), digits=0) + " · 종료 사유 " + fmt(p.get("done_reason")))
        text += row("프롬프트 속도", fmt(p.get("prompt_reported_tokens_per_second"), " token/s") + " · 캐시 제외 " + fmt(p.get("uncached_prompt_tokens_per_second"), " token/s"))
        text += row("가용 RAM", "전 " + gib(at(m, "before", "available_physical_bytes")) + " · 표본 최소 " + gib(m["sampled_minimum_available_physical_bytes"]) + " · 후 " + gib(at(m, "after", "available_physical_bytes")))
        text += row("시스템 commit", "전 " + gib(at(m, "before", "committed_bytes")) + " · 표본 최대 " + gib(m["sampled_maximum_committed_bytes"]) + " · 후 " + gib(at(m, "after", "committed_bytes")) + " · 표본 수 " + fmt(m["sample_count"], digits=0))
        text += row("commit 한도", "전 " + gib(at(m, "before", "commit_limit_bytes")) + " · 후 " + gib(at(m, "after", "commit_limit_bytes")))
        actual = []
        for obs in d["actual_ps_observations"]:
            source = esc(obs["source"])
            if not obs["models"]:
                actual.append(f"<li><code>{source}</code>: 상주 모델 없음</li>")
            for mm in obs["models"]:
                description = f"{fmt(mm.get('name', mm.get('model')))} · context {fmt(mm.get('context_length'), digits=0)} · size_vram {gib(mm.get('size_vram'))}"
                backend = {key: mm[key] for key in ("processor", "backend", "gpu", "offload") if key in mm}
                description += " · backend " + (esc(json.dumps(backend, ensure_ascii=False)) if backend else "명시 필드 없음")
                actual.append(f"<li><code>{source}</code>: {description}</li>")
        ps_html = "<details><summary>실제 /api/ps 관측</summary><ul>" + "".join(actual) + "</ul></details>" if actual else "<p>/api/ps 관측 미확인</p>"
        error = f"<p class='note'>오류 기록: {esc(json.dumps(d['error'], ensure_ascii=False))}</p>" if d["error"] else ""
        tables.append(f"<section><h2>{label}</h2><p class='source'>{esc(d['directory'])}</p><table>{text}</table>{error}{ps_html}</section>")
    json_href = os.path.relpath(ROOT / report["assessment_path"], html_path.parent).replace("\\", "/")
    return """<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LIBERA 로컬 모델 설치·실행 진단</title><style>
body{max-width:960px;margin:36px auto;padding:0 22px;font:16px/1.75 system-ui,sans-serif;color:#1f303b;background:#fff}h1{font-size:28px;line-height:1.4}h2{font-size:21px;margin:30px 0 12px}.notice{padding:16px 20px;background:#eef4f6;border-left:4px solid #236574}.note,.source{font-size:13px;color:#52636d}.source,code{overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border-bottom:1px solid #d9e2e7;padding:10px 12px;text-align:left;vertical-align:top}th{width:24%;background:#f7f9fa}details{margin:12px 0}li{margin:7px 0}a{color:#176477}footer{margin-top:30px;border-top:1px solid #d9e2e7;padding-top:16px;font-size:13px}@media(max-width:600px){body{padding:0 14px}th,td{padding:8px}h1{font-size:24px}}@media print{body{margin:0;max-width:none}details{display:block}}
</style><h1>로컬 모델 설치·실행 진단</h1>""" + f"""
<p class="note">기록 읽은 시각: {esc(report['generated_at_utc'])}</p>
<p class="notice"><strong>학술제의 AI 실험 결과가 아닙니다.</strong> 설치와 개별 요청의 기술 진단을 기록합니다. 설치 완료, 응답 생성 완료, 전체 실험에 대한 적합성은 서로 다른 판단입니다. 이 보고서는 자동 적합 판정을 내리지 않습니다.</p>
<section><h2>설치 기록</h2><table>
{row('상태', esc(STATUS_KO.get(install['status'], install['status'])))}
{row('모델 / 양자화', fmt(model.get('name') or install['target_model']) + ' / ' + fmt(model.get('quantization')))}
{row('모델 크기 / 관측 엔진', gib(model.get('size_bytes')) + ' / Ollama ' + fmt(install['engine_version']) + (' (시도 전 관측)' if install['engine_version_observation_phase'] == 'before_attempt' else ' (완료 기록)'))}
{row('모델 digest', '<code>' + fmt(model.get('digest')) + '</code>')}
{row('설치 시도 소요', fmt(install['install_elapsed_seconds'], '초'))}
</table><p class="source">{esc(install['directory'])}</p>
{('<p class="note">실패 기록: ' + esc(json.dumps(install['failure'], ensure_ascii=False)) + '</p>') if install['failure'] else ''}
{('<p class="note">최근 다운로드 이벤트: ' + esc(json.dumps(install['last_pull_event'], ensure_ascii=False)) + '</p>') if install['status'] != 'installed' and install['last_pull_event'] else ''}{interruption_html}</section>
<section><h2>하드웨어 관측의 범위</h2><table>
{row('로컬 PC 관측값', fmt(at(local, 'processor', 'Name')) + ' · 물리 RAM ' + gib(local_mem))}
{row('디스플레이 이름', fmt(at(local, 'graphics', 'Name')))}
{row('RDP 세션 사용자 제공값', '메모리 ' + gib(remote_mem) + ' · ' + fmt(at(remote, 'reported', 'model')))}
{row('물리 서버 GPU / RAM', '미확인 · RDP 게스트의 값으로 물리 서버 성능을 판단하지 않음')}
</table><p class="note">로컬 inventory 관측시각: {fmt(at(local, 'captured_at_utc'))}. 디스플레이 이름만으로 실제 추론 backend를 확정하지 않습니다. 공유 GPU 메모리를 시스템 RAM에 별도로 더하지 않습니다. 원격 수치는 사용자가 붙여 넣은 RDP 출력이며 물리 서버의 직접 측정이 아닙니다.</p></section>
{''.join(tables) if tables else '<section><h2>실행 진단</h2><p>선택된 진단 기록이 없습니다. 응답 속도와 메모리 부하는 미측정입니다.</p></section>'}
<p class="note">health의 256토큰 상한은 짧은 기술 점검입니다. 8,192토큰 상한의 stage1도 단일 단계 진단이며, 네 단계의 예비·본실험을 완료한 것이 아닙니다. 종료 기록이 없는 속도는 미확인으로 둡니다. 출력 속도에는 제공자가 집계한 thinking이 포함될 수 있으며 최종 답변만의 속도가 아닙니다. 프롬프트 속도는 캐시 영향을 받을 수 있습니다. 메모리 최소·최대는 수집한 표본의 값이며 정확한 순간 최솟값·최댓값은 아닙니다. /api/ps 상주는 요청 실행 중이라는 증거와 다릅니다.</p>
<footer><a href="{esc(json_href)}">측정값·출처·해시 JSON</a> · <a href="https://ollama.com/library/qwen3.6:35b">Ollama 모델 페이지</a> · <a href="https://huggingface.co/Qwen/Qwen3.6-35B-A3B">Qwen 공식 모델 카드</a><p>보고서 생성기는 저장 파일만 읽습니다. 모델 다운로드·추론·원격 변경을 수행하지 않았습니다.</p></footer></html>"""


def build(install_dir, diagnostic_dirs, inventory, remote, output_json, output_html, interruption=None):
    records = Records()
    report = {"schema_version": "runtime_record_assessment_1.0", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "descriptive_records_only_no_experiment_suitability_verdict",
              "report_generator_inference_calls": 0, "network_requests_by_report_generator": 0,
              "assessment_path": rel(output_json), "html_path": rel(output_html),
              "installation": installation(install_dir, records),
              "diagnostics": [diagnostic(p, records) for p in diagnostic_dirs],
              "hardware": {"local": records.read(inventory), "remote_user_report": records.read(remote)},
              "hardware_sources": {"local": rel(inventory), "remote_user_report": rel(remote)},
              "experiment_suitability": {"status": "not_automatically_assessed", "full_pilot_established_by_this_report": False},
              "interpretation_limits": ["Installation completion is distinct from runtime/experiment suitability.",
                 "Health and stage1 runs are technical diagnostics, never full pilot/main experimental results.",
                 "No terminal metrics means null, not zero; a missing summary does not prove a process is still running.",
                 "Sample extrema are not exact peaks. Provider generation counts are not final-answer-only counts.",
                 "RDP guest specifications do not establish physical-host GPU or RAM; adapter names do not establish the actual inference backend."],
              "official_references": ["https://ollama.com/library/qwen3.6:35b", "https://huggingface.co/Qwen/Qwen3.6-35B-A3B"]}
    report["interruption_record"] = records.read(interruption) if interruption else None
    report["interruption_record_source"] = rel(interruption) if interruption else None
    report["interruption_matches_selected_installation"] = (at(report["interruption_record"], "installation_directory") == rel(install_dir)) if report["interruption_record"] else None
    report["sources"] = records.sources
    report["read_issues"] = records.issues
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    output_html.write_text(make_html(report, output_html), encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-dir", type=Path, required=True)
    parser.add_argument("--diagnostic-dir", type=Path, action="append", default=[])
    parser.add_argument("--inventory", type=Path, default=ROOT / f"data/sector_runtime/hardware_inventory_{DATE}.json")
    parser.add_argument("--remote-report", type=Path, default=ROOT / f"data/sector_runtime/remote_hardware_user_report_{DATE}.json")
    parser.add_argument("--interruption-report", type=Path, default=ROOT / f"data/sector_runtime/runtime_interruption_{DATE}.json")
    parser.add_argument("--output-json", type=Path, default=ROOT / f"data/sector_runtime/runtime_assessment_{DATE}.json")
    parser.add_argument("--output-html", type=Path, default=ROOT / f"research/audits/runtime_{DATE}.html")
    args = parser.parse_args(argv)
    report = build(args.install_dir, args.diagnostic_dir, args.inventory, args.remote_report, args.output_json, args.output_html, args.interruption_report)
    print(json.dumps({"installation_status": report["installation"]["status"], "diagnostics": len(report["diagnostics"]),
                      "read_issues": len(report["read_issues"]), "html": rel(args.output_html),
                      "assessment": rel(args.output_json), "inference_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
