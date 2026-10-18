"""Append local engineering observations without changing the v4.3 study.

Default: write review copies under research/local_engineering_addendum_preview.
Only an explicit --apply replaces the three current dated documents. This script
never runs a model, changes a runtime, or regenerates the historical remote report.
Run the original v4.3 builder first, then this additive builder when refreshing.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import math
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
REPORT = "research/local_sector_latency_20261018.json"
KEY = "local_engineering_addendum"
FILES = {
    "plan": "plan/LIBERA_실험계획_20261018.html",
    "paper": "paper/LIBERA_텀페이퍼_초안_20261018.html",
    "config": "plan/LIBERA_실험설정_20261018.json",
}
MARKERS = ("LOCAL_ENGINEERING_REMOTE_SCOPE", "LOCAL_ENGINEERING_APPENDIX")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def shown(value, digits=None) -> str:
    if value is None:
        return "미관측"
    if digits is not None and type(value) in (int, float) and math.isfinite(value):
        return f"{value:.{digits}f}"
    return esc(value)


def json_read(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def validate_report(report, root: Path) -> list[dict]:
    if report.get("schema_version") != "local_remote_engineering_comparison_1.0":
        raise ValueError("Unsupported local engineering report schema")
    for key in ("builder_model_calls", "pilot_model_calls", "main_model_calls"):
        if type(report.get(key)) is not int or report[key] != 0:
            raise ValueError(f"Engineering-only zero required: {key}")
    for key in ("research_suitability_certified", "latency_solution_certified"):
        if report.get(key) is not False:
            raise ValueError(f"The report must not certify the research: {key}")
    if not isinstance(report.get("source_files"), list) or not report["source_files"]:
        raise ValueError("Report source hashes are required")
    for source in report["source_files"]:
        path = (root / source["path"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("Report evidence must remain in the workspace")
        if path.is_file() != source["exists"]:
            raise ValueError(f"Evidence existence changed; regenerate report: {path}")
        if source["exists"] and digest(path.read_bytes()) != source["sha256"]:
            raise ValueError(f"Evidence changed; regenerate report: {path}")
    rows = report.get("observations")
    if not isinstance(rows, list):
        raise ValueError("Report observations must be an array")
    return [r for r in rows if r.get("environment") == "local_windows"]


def validate_study(config):
    if config.get("protocol_version") != "4.3":
        raise ValueError("This addendum is scoped to the existing v4.3 documents")
    main = config["observed_execution"]["main"]
    if main.get("frozen") is not False or main.get("status") != "not_run":
        raise ValueError("This addendum requires the observed main to remain unrun/unfrozen")
    for key in ("completed_cases", "completed_calls"):
        if type(main.get(key)) is not int or main[key] != 0:
            raise ValueError("Do not publish the zero-main addendum over new research results")
    if config["results"].get("main_execution_ready") is not False:
        raise ValueError("The addendum must not replace an existing readiness decision")


def marker(name, content):
    return f"<!-- {name}:BEGIN -->\n{content}\n<!-- {name}:END -->"


def strip_own_blocks(document):
    for name in MARKERS:
        begin, end = f"<!-- {name}:BEGIN -->", f"<!-- {name}:END -->"
        if document.count(begin) != document.count(end) or document.count(begin) > 1:
            raise ValueError("Malformed or duplicate generated addendum markers")
        document = re.sub(re.escape(begin) + r".*?" + re.escape(end), "", document, flags=re.S)
    return document


def appendix_position(document):
    """Use the styled article, otherwise the footer/end inside the sole main."""
    articles = list(re.finditer(r'</article\s*>', document, flags=re.I))
    if len(articles) == 1:
        return articles[0].start()
    mains = list(re.finditer(r'<main\b[^>]*>', document, flags=re.I))
    ends = list(re.finditer(r'</main\s*>', document, flags=re.I))
    if len(mains) != 1 or len(ends) != 1 or mains[0].end() >= ends[0].start():
        raise ValueError("A unique styled article or main is required for the appendix")
    footers = list(re.finditer(r'<footer\b[^>]*>', document[mains[0].end():ends[0].start()], flags=re.I))
    return mains[0].end() + footers[0].start() if footers else ends[0].start()


def appendix_html(rows, report_path, report_sha, config, report_html_path=None):
    timing, controls = [], []
    labels = {"synthetic": "짧은 합성 입력", "real_input": "실제 첫 단계 입력"}
    for row in rows:
        details = row.get("saved_details", {})
        requests = details.get("requests", [])
        settings = requests[0].get("settings", {}) if len(requests) == 1 else {}
        calls = row.get("calls", [])
        call = calls[0] if len(calls) == 1 else {}
        metrics = call.get("metrics", {})
        name = f"{row.get('model')} / {labels.get(row.get('input_kind'), row.get('input_kind'))} / {row.get('probe_id')}"
        values = [esc(name), shown(row.get("status")), shown(row.get("elapsed_seconds"), 3),
                  shown(metrics.get("wall_seconds"), 3), shown(metrics.get("ttft_content_seconds"), 3),
                  shown(metrics.get("prompt_eval_count")), shown(metrics.get("eval_count")),
                  shown(call.get("raw_stream_bytes"))]
        timing.append("<tr>" + "".join(f"<td>{v}</td>" for v in values) + "</tr>")
        pin = details.get("pins", {})
        values = [esc(name), shown(settings.get("num_thread")), shown(settings.get("num_ctx")),
                  shown(settings.get("num_predict")), shown(settings.get("temperature")),
                  shown(settings.get("think")), " / ".join(shown(settings.get(k)) for k in
                  ("repeat_penalty", "presence_penalty", "frequency_penalty")),
                  shown(settings.get("seed")), shown(pin.get("engine")), shown(pin.get("quantization"))]
        controls.append("<tr>" + "".join(f"<td>{v}</td>" for v in values) + "</tr>")
    def table(heads, body):
        return "<div style=\"overflow-x:auto\"><table><thead><tr>" + "".join(f"<th>{esc(h)}</th>" for h in heads) + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>"
    times = table(["로컬 관측", "상태", "감시 경과 초", "HTTP 경과 초", "첫 내용 초", "입력 토큰", "출력 토큰", "수신 bytes"], timing)
    options = table(["로컬 관측", "요청 스레드", "문맥", "출력 상한", "T", "thinking", "repeat/presence/frequency", "seed", "엔진", "양자화"], controls)
    link = "../" + report_path
    readable_link = (f'<a href="{esc("../" + report_html_path)}">읽기용 진단 보고서</a> · '
                     if report_html_path else "")
    model = config["model"]
    return f'''<section id="local-engineering-20261018"><h2>부록. 노트북 실행 진단 — 연구 실험과 별도인 관측</h2>
<p>아래는 원격 실행 이후 노트북에서 수행한 기술 점검이다. {readable_link}<a href="{esc(link)}">관측 JSON</a>의 저장된 요청·응답만 표시하며, 원격 실행의 과거 결과를 덮어쓰지 않는다. JSON SHA256: <code>{esc(report_sha)}</code>.</p>
{times}
<p>감시 경과 시간은 자식 프로세스 수명이고 HTTP 경과 시간은 요청 관측이다. 제한시간 종료는 완료시간이 아니다. 종료 응답이 없으면 토큰 수·처리속도·첫 응답 시간은 0이 아닌 미관측이다. 출력 상한에 도달한 기술 진단은 금융 답변의 정확성이나 요구 JSON의 완결성을 채점한 결과가 아니다.</p>
{options}
<p>스레드 수는 요청값이다. 문맥·32-token 출력 상한·벌점·seed·시간 제한은 이 기술 점검의 구현 조건이며, 논문에 근거해 확정한 연구 실험 조건이라고 부르지 않는다. 특히 벌점 없는 설정을 사용한 진단은 기존 v4.3의 상속 기본값과 구분한다. 모델·입력·옵션의 대응 여부는 연결 보고서에 남기며, 한 번씩의 관측과 다른 OS·CPU·메모리·배치·캐시만으로 일반적인 속도 배율이나 원인별 효과를 추정하지 않는다.</p>
<p>실제 입력 점검은 Fidelity Q2의 R1 첫 단계 한 번이며 출력 상한은 짧게 제한했다. 중복 필드를 정확히 복원할 수 있는 표현으로 줄였지만 네 단계·R1/R4 전체와 8,192-token 연구 출력 상한을 검증한 것이 아니다. 원형 입력을 함께 실행한 비교가 아니므로 압축 자체의 속도 효과도 확인하지 않았다. 데이터 값의 보존은 동일한 모델 행동을 보장하지 않는다.</p>
<p><strong>연구 프로토콜은 v4.3이며 {esc(model['ollama_tag'])}, 출력 상한 {esc(model['max_output_tokens'])}, 문맥 {esc(model['context_tokens'])} 후보를 그대로 보존한다.</strong> 로컬 진단을 연구 예비·본과제 완료 수에 합산하지 않는다. 본과제 완료 0건·미동결·실행 적합성 미확정이며, 압축 표현이나 1.7B 모델을 본과제에 자동 채택하지 않았다. 연구 조건을 바꾸려면 변경 근거와 버전을 먼저 남기고 필요한 전체 예비검증을 거쳐 본과제 전에 동결한다.</p>
<p>이 진단의 의미는 논문의 기관 문서 해석·산업 배분 비교를 실제로 수행할 실행 환경을 찾는 데 있다. 짧은 응답의 속도는 기관 판단 보존, 산업 비중의 타당성 또는 R1/R4 효과의 증거가 아니다. 독립 사람의 원문·의미 검토 상태도 이 부록으로 바뀌지 않는다.</p>
<p>노트북용 <a href="../research/start_local_sector_ollama.ps1">Ollama GPU 서비스 시작 도구</a>는 서비스 시작을 위한 별도 도구이며 연구 실험을 실행하지 않는다. 앞 절에 남긴 원격 CT 명령을 노트북 명령으로 사용하지 않는다. 도구가 존재한다는 사실만으로 새 서비스 시작 경로의 검증 완료를 선언하지 않는다.</p></section>'''


def build_documents(root: Path, report_path: Path):
    root, report_path = root.resolve(), report_path.resolve()
    if not report_path.is_relative_to(root):
        raise ValueError("The report must be inside the workspace")
    report_bytes = report_path.read_bytes()
    report = json.loads(report_bytes.decode("utf-8-sig"))
    rows = validate_report(report, root)
    paths = {key: root / value for key, value in FILES.items()}
    config = json_read(paths["config"])
    validate_study(config)
    clean_config = copy.deepcopy(config)
    clean_config.pop(KEY, None)
    html_report = root / report.get("report_html_path", report_path.with_suffix(".html").relative_to(root).as_posix())
    if not html_report.resolve().is_relative_to(root):
        raise ValueError("The readable report must remain inside the workspace")
    record = {"report_path": report_path.relative_to(root).as_posix(), "report_sha256": digest(report_bytes),
              "report_html_path": html_report.relative_to(root).as_posix() if html_report.is_file() else None,
              "report_html_sha256": digest(html_report.read_bytes()) if html_report.is_file() else None,
              "scope": "local_engineering_observations_only; historical remote execution preserved",
              "builder": "research/build_local_engineering_addendum.py", "builder_sha256": digest(Path(__file__).read_bytes()),
              "generated_at_utc": report.get("generated_at_utc"), "observations": copy.deepcopy(rows),
              "pilot_model_calls_added": 0, "main_model_calls_added": 0,
              "research_protocol_changed": False, "main_frozen": False, "main_execution_ready": False,
              "compact_prompt_adopted_for_research": False, "model_selected_from_latency_alone": False,
              "source_report_warnings": report.get("warnings", []),
              "historical_observed_execution_scope": "Unchanged remote CT record; local observations are stored in this separate appendix."}
    new_config = copy.deepcopy(clean_config)
    new_config[KEY] = record
    appendix = marker(MARKERS[1], appendix_html(rows, record["report_path"], record["report_sha256"], clean_config, record["report_html_path"]))
    note = marker(MARKERS[0], '<aside id="remote-runtime-historical-scope"><p><strong>다음 절은 이전 원격 서버의 v4.3 실행 기록이다.</strong> 당시 관측과 연구 카운트를 보존했다. 이후 노트북 기술 점검은 <a href="#local-engineering-20261018">별도 부록</a>에서 확인하며, 이 과거 기록의 상태를 현재 노트북의 실행 상태로 일반화하지 않는다.</p></aside>')
    outputs = {"config": json.dumps(new_config, ensure_ascii=False, indent=2, allow_nan=False) + "\n"}
    for key in ("plan", "paper"):
        original = paths[key].read_text(encoding="utf-8")
        clean = strip_own_blocks(original)
        anchors = list(re.finditer(r'<section\b[^>]*\bid=["\']runtime-v43["\'][^>]*>', clean))
        if len(anchors) != 1:
            raise ValueError(f"Expected exactly one historical runtime section: {key}")
        additions = [(appendix_position(clean), appendix), (anchors[0].start(), note)]
        document = clean
        # Insert from the end so original byte positions remain valid.
        for position, text in sorted(additions, key=lambda item: item[0], reverse=True):
            document = document[:position] + text + document[position:]
        if strip_own_blocks(document) != clean:
            raise AssertionError("Non-addendum HTML changed")
        outputs[key] = document
    if {k: v for k, v in new_config.items() if k != KEY} != clean_config:
        raise AssertionError("Research config changed")
    return outputs, record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-json", type=Path, default=ROOT / REPORT)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="Explicitly append to current plan/paper/config")
    group.add_argument("--output-dir", type=Path, default=ROOT / "research/local_engineering_addendum_preview")
    args = parser.parse_args(argv)
    outputs, record = build_documents(ROOT, args.report_json)
    destination = ROOT if args.apply else args.output_dir.resolve()
    # Validate and build all outputs before the first write; source evidence is untouched.
    if not args.apply and any((destination / FILES[k]).resolve() == (ROOT / FILES[k]).resolve() for k in FILES):
        raise ValueError("Use --apply explicitly to update current study documents")
    for key, content in outputs.items():
        target = destination / FILES[key]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    print(json.dumps({"applied": args.apply, "destination": str(destination), "report_sha256": record["report_sha256"],
                      "local_observation_rows": len(record["observations"]), "research_conditions_changed": False,
                      "research_calls_added": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
