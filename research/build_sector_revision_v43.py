"""Build dated v4.3 documents without changing v4.2 or executing a model.

Usage:
    python research/build_sector_revision_v43.py
    python research/build_sector_revision_v43.py --status-json PATH

Status is an explicit observational input, not a command to run anything. Counts
are attributed to that input; linked files are hashed, not semantically certified.
Optional top-level objects: installation, runtime, pilot, main, human_review.
Each may provide status, manifest_path, summary_path and notes. pilot/main may
provide completed_cases and completed_calls. runtime may provide model_tag,
digest, engine_version, context_tokens, thinking, temperature, max_output_tokens,
runtime_manifest_path, resource_summary. main may provide frozen and
freeze_manifest_path. Unknown quantities remain null. No network is used.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
OLD_DATE, NEW_DATE = "20261017", "20261018"
MODEL_TAG = "qwen3.5:4b-q4_K_M"
REMOTE_ROOT = "/root/libera_20261018"
REMOTE_RUNTIME = "data/sector_runtime/inventory_v43/runtime_pinned.json"
NAMES = {
    "plan": "plan/LIBERA_실험계획_{date}.html",
    "paper": "paper/LIBERA_텀페이퍼_초안_{date}.html",
    "config": "plan/LIBERA_실험설정_{date}.json",
}
FINVECTOR = "https://arxiv.org/pdf/2610.08882"
DATACENTRIC = "https://arxiv.org/html/2609.10113"
PORTBENCH = "https://arxiv.org/html/2605.27887v6"
FINVECTOR_EXAMPLE = "https://github.com/alinakhay/FinVector-Market-4B/blob/main/examples/inference_mlx.py"
MLX_GENERATE = "https://github.com/ml-explore/mlx-lm/blob/v0.31.3/mlx_lm/generate.py"
REVIEW = "research/small_model_review_20261018.html"
REGISTRY = "research/small_model_registry_20261018.json"
STATUS_LABELS = {
    "not_run": "미실행", "not_verified": "미검증", "unknown": "미확인",
    "pending": "대기", "running": "진행 중", "in_progress": "진행 중",
    "completed": "완료 기록 있음", "complete": "완료 기록 있음",
    "installed": "설치 기록 있음", "failed": "실패 기록 있음",
    "partial": "일부 완료", "interrupted": "중단 기록 있음",
    "ready": "준비 상태 보고됨", "pinned": "버전 고정 기록 있음",
    "not_frozen": "미동결", "frozen": "동결 기록 있음",
}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def source_record(path: Path, root: Path) -> dict[str, Any]:
    return {"path": relative(path, root), "exists": path.is_file(),
            "sha256": sha256(path) if path.is_file() else None}


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def count_text(value: Any) -> str:
    return "미확인" if value is None else str(value)


def label(value: Any) -> str:
    return STATUS_LABELS.get(str(value), str(value))


def normalize_status(raw: dict[str, Any] | None, root: Path) -> dict[str, Any]:
    absent = raw is None
    raw = raw or {}
    status: dict[str, Any] = {"input_supplied": not absent,
                            "count_provenance": "operator_status_input; not an independent re-evaluation",
                            "warnings": [], "evidence_files": []}
    for section in ("installation", "runtime", "pilot", "main", "human_review"):
        value = raw.get(section, {})
        if not isinstance(value, dict):
            raise ValueError(f"status.{section} must be an object")
        status[section] = copy.deepcopy(value)
        default = "not_run" if absent and section in ("pilot", "main") else "not_verified"
        status[section].setdefault("status", default)
    for split in ("pilot", "main"):
        for field in ("completed_cases", "completed_calls"):
            value = status[split].get(field, 0 if absent else None)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"status.{split}.{field} must be a nonnegative integer or null")
            status[split][field] = value
    status["main"].setdefault("frozen", False)
    if type(status["main"]["frozen"]) is not bool:
        raise ValueError("status.main.frozen must be boolean")
    status["notes"] = raw.get("notes", [])
    if not isinstance(status["notes"], list):
        raise ValueError("status.notes must be an array")

    for section in ("installation", "runtime", "pilot", "main", "human_review"):
        for key, value in status[section].items():
            if key.endswith("_path") and isinstance(value, str) and value:
                path = Path(value)
                if not path.is_absolute():
                    path = root / path
                record = source_record(path, root)
                record["status_field"] = f"{section}.{key}"
                status["evidence_files"].append(record)
                if not record["exists"]:
                    status["warnings"].append(f"Referenced evidence file not found: {section}.{key}: {value}")
    for split in ("pilot", "main"):
        if (status[split]["completed_calls"] or 0) > 0:
            records = [r for r in status["evidence_files"] if r["status_field"].startswith(split + ".")]
            if not any(r["exists"] for r in records):
                status["warnings"].append(f"{split} counts are reported but no corresponding evidence file was found")
    observed_tag = status["runtime"].get("model_tag")
    if observed_tag and observed_tag != MODEL_TAG:
        status["warnings"].append(f"Observed model differs from v4.3 candidate: {observed_tag}")
    for field, expected in {"temperature": 0, "thinking": False,
                            "max_output_tokens": 8192, "context_tokens": 65536}.items():
        if field in status["runtime"] and status["runtime"][field] != expected:
            status["warnings"].append(f"Observed runtime.{field} differs from v4.3 candidate; preserve both and resolve before main")
    for split in ("pilot", "main"):
        if status[split]["status"] == "not_run" and (status[split]["completed_calls"] or 0) > 0:
            raise ValueError(f"status.{split}: not_run conflicts with positive completed_calls")
    # A state label never supplies missing evidence of a run, installation or freeze.
    status["runtime_evidence_present"] = any(
        r["exists"] and r["status_field"].startswith("runtime.") for r in status["evidence_files"])
    status["freeze_evidence_present"] = any(
        r["exists"] and r["status_field"] == "main.freeze_manifest_path" for r in status["evidence_files"])
    if status["main"]["frozen"] and not status["freeze_evidence_present"]:
        status["warnings"].append("Main freeze was reported without an existing freeze manifest")
    return status


def observation_sentence(status: dict[str, Any]) -> str:
    p, m = status["pilot"], status["main"]
    return (f"설치: {label(status['installation']['status'])}. "
            f"예비 실행: {label(p['status'])}, 완료 사례 {count_text(p['completed_cases'])}건·"
            f"완료 응답 {count_text(p['completed_calls'])}건. "
            f"본과제: {label(m['status'])}, 완료 사례 {count_text(m['completed_cases'])}건·"
            f"완료 응답 {count_text(m['completed_calls'])}건. "
            f"독립 사람 검토: {label(status['human_review']['status'])}.")


def fragment(markup: str):
    return list(BeautifulSoup(markup, "html.parser").contents)


def append_html(element, markup: str) -> None:
    for node in fragment(markup):
        element.append(node)


def replace_html(element, markup: str) -> None:
    for node in fragment(markup):
        element.insert_before(node)
    element.decompose()


def model_method_html(status: dict[str, Any]) -> str:
    return f'''<h3 id="model-v43">4.6. 소형 모델을 사용하는 조건과 해석 범위</h3>
<p>v4.3의 선정 후보는 <strong>Qwen3.5-4B의 Q4_K_M 양자화본</strong>이며 정확한 Ollama 태그는 <code>{MODEL_TAG}</code>다. 현재 접근 가능한 CPU·메모리 자원을 고려한 실행 후보이며, 설치 여부와 전체 네 단계 수행 가능 여부는 아래 실제 기록으로 구분한다. 연구질문·기관 문서·11개 산업·R1/R4 비교는 유지한다. 이 연구는 소형 모델에 적용한 산업 배분 사례이며 PortBench의 모델·정밀도·환경을 그대로 재현한 실험이 아니다.</p>
<p>Hayrapetyan 등(2026)은 금융 평가에서 원본 Qwen3.5-4B를 직접 평가했고, Khaybullina(2026)는 같은 모델에 명시적 JSON 형식을 제공하고 thinking을 끈 금융 과제를 보고했다. 모델 선정과 thinking 비활성화·구조화 출력 설정의 근거는 이 연구들이다. 이 설정은 별도의 thinking 출력을 요구하지 않는다는 뜻이며 모델에 추론 능력이 없다는 뜻은 아니다. 금융 추가 학습 모델 FinVector-Market-4B를 설치한 것으로 부르지 않으며, 원 논문 점수를 이 Ollama 양자화본의 성능으로 옮기지 않는다. 구체적 차이는 <a href="../{REVIEW}">소형 모델 조사</a>와 <a href="../{REGISTRY}">공개 태그·digest 조회 기록</a>에 남겼다.</p>
<table><thead><tr><th>항목</th><th>v4.3 후보값</th><th>근거와 적용 범위</th></tr></thead><tbody>
<tr><td>출력 방식</td><td>thinking=false, 명시적 JSON</td><td>FinVector §4.1의 원본 모델 평가 선례. 모델 내부 thinking trace를 요구하지 않아도 해석·대안·근거·최종 비중은 응답 필드로 요구한다.</td></tr>
<tr><td>샘플링</td><td>temperature=0</td><td>FinVector의 greedy decoding을 Ollama에서 구현하는 후보이며, 동일 백엔드 재현은 아니다. PortBench §3.1도 T=0을 사용한다. 두 조건에 같은 값을 고정한다.</td></tr>
<tr><td>단계별 최대 출력</td><td>8,192 tokens</td><td>PortBench §3.1에서 가져와 다른 모델·과제로 옮긴 연구자 응용이다. FinVector의 700-token 상한을 따랐다는 주장이 아니며, 충분성은 예비 응답의 종료·완결성에서 확인한다.</td></tr>
<tr><td>전체 문맥 한도</td><td>65,536 tokens</td><td>네 단계 입력·명시적 응답·계산 피드백을 보존하기 위한 구현 후보다. 금융 논문이 정한 최적값이나 현재 서버의 수용 보장이 아니다. 실제 템플릿과 토큰화·메모리를 점검하고 무통보 잘림을 허용하지 않는다.</td></tr>
<tr><td>모델 식별</td><td>정확한 태그·digest·Q4_K_M·엔진</td><td>설치 후 실제 서비스의 응답으로 고정한다. 일반 태그와 별도 변형을 혼동하지 않으며 공개 manifest 조회만으로 설치 완료를 선언하지 않는다.</td></tr>
</tbody></table>
<p>FinVector의 출력 상한·batch·seed는 해당 과제의 조건이다. Data-Centric §5.1의 temperature 0과 32,768 tokens는 채점 모델의 설정이므로 Qwen 생성 조건으로 사용하지 않는다. 위 후보를 수정한다면 예비 기록과 함께 양 조건에 같은 변경을 적용하고, 본과제 전에 모델·입력·규칙과 함께 동결한다.</p>
<p>생성 요청에서 샘플링 관련 값 중 직접 지정하는 항목은 temperature=0이다. top_p·top_k·presence_penalty 등 나머지 모델 기본 설정은 설치 메타데이터와 실제 요청을 대조해 실행 기록에 따로 표시한다. 상속된 기본값을 금융 논문으로 선정한 값이라고 부르지 않으며, T=0에서 각 설정이 실제로 적용되는 방식과 효과는 엔진 구현에 의존한다. 엔진·양자화·기본 생성 설정이 다르므로 FinVector의 전체 생성 조건을 재현했다는 주장은 하지 않는다. 실행 중에는 이 설정을 바꾸지 않는다.</p>
<p><strong>본과제 동결 전 해결할 설정 문제가 남아 있다.</strong> FinVector 논문은 penalty 설정을 보고하지 않는다. 현재 모델에 상속된 presence_penalty=1.5를 논문 기반 수치라고 정당화할 수 없으므로, 모든 생성 조건을 논문에 근거해 확정한 상태라고 부르지 않는다. 미보고 기본값의 처리·근거 수준·한계를 명시하는 조건 개정 결정과 필요한 예비 재검증을 본과제 전에 완료해야 한다. 이 문제를 숨기거나 이미 기록된 예비실험의 조건을 사후 변경하지 않는다.</p>
<p>후속 검토 후보 중 <code>seed=3407</code>은 <a href="{FINVECTOR}">FinVector §4.1</a>에 직접 보고된 수치다. <code>repeat_penalty=1, presence_penalty=0, frequency_penalty=0</code>은 <a href="{FINVECTOR_EXAMPLE}">저자 공개 최소 예제</a>와 <a href="{MLX_GENERATE}">MLX-LM 0.31.3의 기본 argmax·logits_processors=None</a>을 벌점 없는 Ollama 설정으로 옮기는 구현 후보로만 검토한다. 공개 예제는 논문의 실제 비공개 평가 실행기가 아니므로 이 값들을 보고된 벤치마크 조건이라고 부르지 않는다. 후보를 현재 실행에 자동 적용하지 않았고, LIBERA에서 검증된 조건도 아니다.</p>
<p>소형 모델이 기본 산업 판단·인용·비중 형식을 수행하지 못하면 R1/R4 차이가 작다는 사실을 절차 효과의 부재로 해석할 수 없다. 양자화와 thinking 비활성화 설정의 영향도 이번 설정의 한계로 기록한다. R1/R4 차이가 크게 나오는 모델을 사후 선택하지 않으며 완결성·형식·근거 해석 가능성·실행 자원의 예비 점검과 연구 결과를 구분한다.</p>'''


def status_html(status: dict[str, Any], status_record: dict[str, Any] | None) -> str:
    p, m, r = status["pilot"], status["main"], status["runtime"]
    rows = [("설치", label(status["installation"]["status"])),
            ("서비스 버전 고정", label(r["status"])),
            ("예비 실행", f"{label(p['status'])} / 완료 사례 {count_text(p['completed_cases'])} / 완료 응답 {count_text(p['completed_calls'])}"),
            ("본과제", f"{label(m['status'])} / 완료 사례 {count_text(m['completed_cases'])} / 완료 응답 {count_text(m['completed_calls'])}"),
            ("본과제 동결", "동결 상태가 보고됨" if m["frozen"] else "미동결"),
            ("독립 사람 검토", label(status["human_review"]["status"]))]
    for key, title in [("model_tag", "실제 서비스 모델 태그"), ("digest", "실제 서비스 digest"),
                       ("diagnostic_completed_calls", "짧은 기술 진단 완료 응답 수 — 예비 사례에서 제외"),
                       ("engine_version", "실제 엔진 버전"), ("context_tokens", "보고된 문맥 한도"),
                       ("thinking", "보고된 thinking 설정"), ("temperature", "보고된 temperature"),
                       ("inherited_model_parameters", "메타데이터에 보고된 모델 기본 생성 설정"),
                       ("request_overrides", "실제 요청에서 지정한 생성 설정"),
                       ("max_output_tokens", "보고된 출력 상한"), ("resource_summary", "실행 자원 관측")]:
        value = r.get(key)
        if value is not None:
            rows.append((title, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list, bool)) else str(value)))
    table = "".join(f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in rows)
    records = status["evidence_files"]
    if status_record:
        records = [dict(status_record, status_field="status_input")] + records
    links = []
    for item in records:
        path = str(item["path"])
        shown = f"{item['status_field']}: {path}"
        if item["exists"] and not Path(path).is_absolute():
            links.append(f'<li><a href="../{esc(path)}">{esc(shown)}</a></li>')
        else:
            links.append(f"<li>{esc(shown)} — {'존재 확인' if item['exists'] else '파일 미확인'}</li>")
    notes = [str(x) for x in status["notes"]]
    for section in ("installation", "runtime", "pilot", "main", "human_review"):
        value = status[section].get("notes") or []
        notes.extend([str(value)] if isinstance(value, str) else [str(x) for x in value])
    note_html = "".join(f"<li>{esc(n)}</li>" for n in notes + status["warnings"])
    return f'''<section id="runtime-v43"><h2>v4.3 실행 기록과 남은 검증</h2>
<p>{'제공된 상태 JSON의 보고값을 표시한다. 연결 파일의 존재와 해시 확인은 응답 내용의 타당성 검증과 다르다.' if status['input_supplied'] else '실제 실행 상태 입력은 아직 없다. 이 개정본에 연결된 예비·본과제 AI 결과는 0건이며 설치와 실험 적합성은 미검증이다.'} 짧은 합성 입력 점검이나 단일 단계 진단은 네 단계 예비실험 완료로 세지 않는다.</p>
<table><thead><tr><th>구분</th><th>관측·보고 상태</th></tr></thead><tbody>{table}</tbody></table>
<p>설치 완료, 응답 생성 완료, 평가 유효성, 본과제 준비 완료는 별개다. 이 문서 생성기는 성공이나 실험 적합성을 자동 판정하지 않는다. 예비 응답에서 평가 기준을 보완할 수 있지만, 본 응답을 본 뒤 확인적 기준·임계값·제외 규칙을 바꾸지 않는다. 사후 추가 분석은 탐색적이라고 밝힌다.</p>
<p>실행기는 각 모델 요청 직전에 모델 digest·엔진 버전·템플릿 해시의 일치를 확인하도록 작성되어 있다. 다만 호출마다 조회한 메타데이터 전체를 별도 파일로 저장하지 않으므로, 모든 순간의 서비스 상태를 독립적으로 재검증할 수 있는 기록은 아니다. 보존 범위는 최초 inventory의 메타데이터·런타임 핀, 실제 요청·응답, 실행 코드 해시와 실행 결과다. 코드에 있는 확인 절차와 남겨진 관측 증거를 구분한다.</p>
{('<ul>' + ''.join(links) + '</ul>') if links else ''}
{('<ul>' + note_html + '</ul>') if note_html else ''}</section>'''


def add_references(soup: BeautifulSoup) -> None:
    section = soup.find(id="references")
    if section is None:
        raise ValueError("references section missing")
    ul = section.find("ul")
    if ul is None:
        ul = soup.new_tag("ul")
        section.append(ul)
    refs = [
        ("ref-hayrapetyan26", f'Hayrapetyan, Z., Kalmykov, A., Kokosinskii, D., Stanishevskii, D., &amp; Zmitrovich, D. (2026). <i>Data-centric post-training for financial reasoning: Mining, distillation, and verifiable learning</i> (Version 1) [Technical report]. arXiv. <a href="{DATACENTRIC}">원문 §5·Table 3</a>'),
        ("ref-khaybullina26", f'Khaybullina, A. (2026). <i>FinVector-Market-4B: A controlled study of LoRA adaptation for structured financial tasks</i> (Version 1) [Preprint]. arXiv. <a href="{FINVECTOR}">원문 §4.1·§6.4·§7.3·§10</a>'),
    ]
    for rid, text in refs:
        if not soup.find(id=rid):
            append_html(ul, f'<li id="{rid}">{text}</li>')
    if "references" in (ul.get("class") or []):
        entries = ul.find_all("li", recursive=False)
        for entry in entries:
            entry.extract()
        for entry in sorted(entries, key=lambda item: item.get_text().lower()):
            ul.append(entry)


def build_html(source: Path, kind: str, status: dict[str, Any], status_record: dict[str, Any] | None) -> str:
    soup = BeautifulSoup(source.read_text(encoding="utf-8"), "html.parser")
    for node in list(soup.find_all(string=True)):
        if node.parent.name in ("script", "style"):
            continue
        new = str(node).replace("v4.2", "v4.3").replace("VERSION 4.2", "VERSION 4.3")
        new = new.replace("2026년 10월 17일", "2026년 10월 18일").replace("2026-10-17", "2026-10-18")
        new = new.replace("사람 검토는 아직 완료되지 않았다", "사람 검토의 진행 상태와 근거는 아래 실행 기록에 별도로 표시한다")
        new = new.replace("자료의 원문 해석을 독립적으로 검토하는 절차가 남아 있다", "자료의 원문 해석에 대한 독립 검토의 진행 상태를 별도로 기록한다")
        new = new.replace("아직 관측 결과가 없으므로 어느 절차도 효과가 확인된 해결책으로 제시하지 않는다", "본과제 결과가 확정되기 전에는 어느 절차도 효과가 확인된 해결책으로 제시하지 않는다")
        if new != str(node):
            node.replace_with(new)
    # Update only the new paper/plan/config cross-links; historical audits stay historical.
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "LIBERA_" in href and OLD_DATE in href:
            anchor["href"] = href.replace(OLD_DATE, NEW_DATE)
        if "parameter_basis_v42.json" in href:
            anchor.string = "보존한 v4.2 수치·식·운영 결정의 근거표"
    design = soup.find(id="design")
    old_model = next((p for p in design.find_all("p") if "목표 모델은 PortBench" in p.get_text()), None)
    if old_model is None:
        raise ValueError("Expected v4.2 model paragraph missing; refuse silent partial rebuild")
    replace_html(old_model, model_method_html(status))
    for heading in design.find_all("h3"):
        if heading.get_text().startswith("4.5."):
            heading.string = "4.5. 독립 수치 보조 과제"
    workflow = next(p for p in design.find_all("p") if p.get_text().startswith("각 실행은"))
    extra = '''<p>여기서 유지하는 이력은 사용자가 볼 수 있는 모델 응답과 계산 피드백이다. 응답 필드에 해석·대안·배분 이유를 남기지만 모델 내부의 숨겨진 thinking을 관찰하거나 기억 메커니즘을 측정하는 것은 아니다. thinking 비활성화 설정에서도 네 단계의 명시적 판단 이력은 유지하며, 조건별 출력이 다르므로 실제 생성 이력까지 동일하다고 가정하지 않는다.</p>'''
    workflow.insert_after(BeautifulSoup(extra, "html.parser").p)
    evaluation = next(p for p in design.find_all("p") if p.get_text().startswith("유효성·원문 등급"))
    evaluation.string = ("유효성·원문 등급·인용 범위·비중 거리의 계산식과 실패 처리는 구현했다. 의미 검토 기준을 포함한 평가규칙은 예비 응답을 보고 보완할 수 있지만 본 응답을 보기 전에 입력·모델·규칙의 해시와 함께 동결한다(Nosek et al., 2018). 본 결과에 맞춘 확인적 기준·임계값·제외 규칙 변경은 허용하지 않으며, 추가 분석은 탐색적이라고 표시한다. JSON 실패·출력 상한 도달·문맥 부족을 자동 재질문이나 이력 삭제로 숨기지 않고 원문과 실패를 보존한다. 모델 변경이 필요하면 예비실험 변경으로 기록한다.")
    runtime_section = BeautifulSoup(status_html(status, status_record), "html.parser").section
    design.insert_after(runtime_section)
    nav = soup.find("nav")
    if nav:
        append_html(nav, '<a href="#runtime-v43">v4.3 실행 상태</a>')
    sentence = observation_sentence(status)
    for element in soup.select(".status"):
        element.clear()
        append_html(element, f'<strong>v4.3 · 본과제 결과와 예비 점검을 구분.</strong> {esc(sentence)}')
    if kind == "paper":
        abstract = soup.select_one(".abstract p")
        if abstract:
            abstract.string = abstract.get_text().replace(
                "자료·실행기·기계적 평가기를 준비했으나 실제 AI 응답과 독립 사람 검토 결과는 없다.",
                "자료·실행기·기계적 평가기를 준비하고 소형 모델의 실행 가능성을 별도로 점검한다. 실행 및 사람 검토 상태는 본문의 기록에 구분해 제시한다.")
        for p in soup.find(id="intro").find_all("p"):
            if "실제 모델 예비 실행과 기준 확정이 남아 있다" in p.get_text():
                p.string = p.get_text().replace("실제 모델 예비 실행과 기준 확정이 남아 있다", "모델 예비 점검·기준 동결·본 응답의 진행 상태를 별도로 기록한다")
        append_html(soup.find(id="limits"), '<p>소형 모델·Q4_K_M 양자화·thinking 비활성화 설정에 조건부인 사례다. 다른 논문에서 얻은 원본 모델의 금융 점수는 현재 서비스의 성능 측정치가 아니다. 낮은 기본 문서 해석 능력, 출력 형식 실패 또는 문맥·자원 제약 때문에 두 절차가 모두 실패하면 이를 기관 판단 보존이나 절차 효과의 부재로 단정할 수 없다. 명시적 응답 이력은 관찰할 수 있지만 숨겨진 사고 과정의 변화나 모델 전체의 일반 능력은 식별하지 않는다.</p>')
        conclusion = soup.find(id="conclusion").find_all("p")[-1]
        conclusion.string = (sentence + " 예비 점검은 실행·해석 가능성을 확인하기 위한 것이며 본과제 효과의 증거로 대체하지 않는다. 두 문서 사례의 결과를 전체 기관의 전략이나 시장 위험으로 일반화하지 않는다. 상경·경영학적 기여는 공통 기술을 쓰는 조직이 고유한 판단 근거를 최종 결정에 전달하도록 업무 절차와 검토 책임을 어떻게 구성할지 분석하는 데 있다.")
    else:
        callout = soup.select_one(".callout")
        if callout:
            callout.clear()
            append_html(callout, f'<strong>v4.3 · 소형 모델 적용과 예비 검증을 구분한다.</strong> {esc(sentence)} 본과제 효과와 실행 적합성은 설치 완료만으로 판단하지 않는다.')
        candidates = soup.find(id="candidates")
        replace_html(candidates, '''<section id="candidates"><h2>확정한 선택과 남은 검증</h2><p>자원 조건을 반영해 Qwen3.5-4B Q4_K_M을 우선 실행 후보로 선택했다. 기본 과제를 수행할 수 있는지 예비 점검하고, 실패하면 원인과 조건 변경을 기록한다. 모델의 다운로드 크기만으로 메모리 적합성을 판정하지 않으며, 두 절차의 차이가 큰지를 모델 선택 기준으로 삼지 않는다.</p><p>기관 문서·GICS 11개 산업·공통 기준 비중·R1/R4 비교·계산 지원은 유지한다. 예비 점검 뒤 독립 원문 검토, 의미 평가 지침, 실제 서비스 버전과 입력·규칙의 동결 상태를 확인한다. 사람 검토나 본과제 준비 완료를 설치 성공으로 대신하지 않는다.</p><p>이번 개정의 근거와 후보 비교는 <a href="../research/small_model_review_20261018.html">소형 모델 조사</a>에서 확인할 수 있다. 본과제 실행은 동결 조건을 충족한 뒤 진행한다.</p></section>''')
    appendix = soup.find(id="appendix")
    for p in appendix.find_all("p"):
        if "지금은 실제 예비 실행 전까지 준비했다" in p.get_text():
            p.string = p.get_text().replace("지금은 실제 예비 실행 전까지 준비했다.", "현재 진행 상태와 근거 파일은 v4.3 실행 기록에 표시한다.")
        if "이 파일은 결과를 꾸며 넣지 않은" in p.get_text():
            p.string = p.get_text().replace("이 파일은 결과를 꾸며 넣지 않은 문헌 검토 및 실험 전 소논문이다.", "이 파일은 문헌·실험설계와 확인된 실행 상태를 구분한 소논문 초안이다. 예비 결과만으로 본과제 결론을 작성하지 않는다.")
    pre = appendix.find("pre")
    if pre:
        pre.string = ("# 아래는 원격 CT 내부의 재현 순서이며 이 문서 생성기가 실행하지 않는다.\n"
                      f"cd {REMOTE_ROOT}\n"
                      ".venv/bin/python research/run_sector_workflow.py verify\n"
                      "# 정확한 모델 설치 후 서비스 메타데이터를 고정한다. 이 단계는 추론이 아니다.\n"
                      ".venv/bin/python research/remote_sector_runtime.py inventory --pin-runtime --run-id inventory_v43\n"
                      f".venv/bin/python research/run_sector_workflow.py preflight --runtime {REMOTE_RUNTIME}\n"
                      "# 단일 합성 입력·256-token 상한의 기술 진단이며 예비 사례 수에 넣지 않는다.\n"
                      f".venv/bin/python research/remote_sector_runtime.py diagnose --runtime {REMOTE_RUNTIME} --run-id diagnose_v43\n"
                      "# 동일한 핀으로 네 단계 실제 예비 사례를 실행한다.\n"
                      f".venv/bin/python research/remote_sector_runtime.py pilot --runtime {REMOTE_RUNTIME} --run-id pilot_v43\n"
                      "# 기존 run-id 디렉터리는 덮어쓰지 않는다. 재실행은 새 ID와 그 핀 경로를 기록한다.\n"
                      "# 실제 예비 응답과 독립 원문 검토 기록 후 평가규칙·입력·모델 동결.\n"
                      "# 본과제 명령은 동결 확인 후 사용하며, 본 응답으로 기준을 조정하지 않는다.")
    append_html(appendix, '<p>위 명령은 노트북에서 실행하는 명령이 아니라 원격 CT의 작업 디렉터리와 가상환경을 전제로 한다. 설치·가상환경 준비 및 각 명령의 성공 여부는 실제 상태 입력으로만 갱신한다. 진단 출력은 <code>data/sector_runtime/diagnose_v43</code>, 예비 출력은 <code>data/sector_runtime/pilot_v43</code>에 기록한다. 내려받은 증거 파일의 로컬 경로와 원격 실행 경로는 구분한다.</p>')
    append_html(appendix, f'<p><a href="../{REVIEW}">v4.3 모델·조건 근거</a> · <a href="../plan/LIBERA_실험설정_{NEW_DATE}.json">v4.3 설정과 상태 출처</a> · <a href="../{NAMES[kind].format(date=OLD_DATE)}">보존한 v4.2 문서</a>. 기존 v4.2의 독립 감사와 수치 근거표는 당시 설계에 관한 기록이며 이 개정의 감사 완료 표시가 아니다.</p>')
    add_references(soup)
    footer = soup.find("footer")
    if footer:
        footer.string = "LIBERA · 2026-10-18 · v4.3 · " + sentence + " 이전 버전 감사는 당시 파일에만 적용."
    return str(soup)


def build_config(old: dict[str, Any], status: dict[str, Any], provenance: dict[str, Any]) -> dict[str, Any]:
    cfg = copy.deepcopy(old)
    cfg.update(protocol_version="4.3", as_of_date="2026-10-18",
               previous_protocol="LIBERA_실험설정_20261017.json",
               status="small_model_application; observational_status_attached; no_automatic_suitability_claim")
    cfg["revision_provenance"] = provenance
    cfg["observed_execution"] = status
    cfg["workflow"]["history_semantics"] = "visible model responses and calculator feedback retained; not hidden thinking traces"
    cfg["workflow"]["internal_thinking_observed"] = False
    cfg["model"] = {
        "primary_target": "Qwen3.5-4B", "ollama_tag": MODEL_TAG,
        "quantization": "Q4_K_M", "temperature": 0, "max_output_tokens": 8192,
        "thinking": False, "context_tokens": 65536,
        "runtime_ready": False,
        "exact_served_revision": status["runtime"].get("digest"),
        "runtime_manifest_path": status["runtime"].get("runtime_manifest_path"),
        "candidate_not_observed_settings": not (status["runtime_evidence_present"] and all(
            key in status["runtime"] and status["runtime"][key] == expected
            for key, expected in {"model_tag": MODEL_TAG, "temperature": 0, "thinking": False,
                                  "max_output_tokens": 8192, "context_tokens": 65536}.items())),
        "settings_observation_scope": "Reported inventory/request settings from supplied status evidence; observed values do not certify execution suitability.",
        "runtime_readiness_policy": "Installation or pilot status is reported separately; this builder never certifies execution readiness.",
        "model_basis": [{"url": DATACENTRIC, "locator": "sections 5.1-5.3, Table 3", "scope": "exact base model evaluated in finance; target decoding not fully disclosed"},
                        {"url": FINVECTOR, "locator": "section 4.1, Table 3", "scope": "base Qwen3.5-4B; explicit JSON and disabled thinking; not the LoRA adapter"}],
        "parameter_basis": [
            {"parameter": "thinking", "value": False, "kind": "direct_financial_paper_precedent", "url": FINVECTOR, "locator": "section 4.1"},
            {"parameter": "temperature", "value": 0, "kind": "backend_adaptation", "url": FINVECTOR, "locator": "section 4.1 greedy decoding", "note": "Ollama implementation candidate; also T=0 in PortBench; not identical engine reproduction"},
            {"parameter": "max_output_tokens", "value": 8192, "kind": "paper_value_transferred_to_different_model_and_task", "url": PORTBENCH, "locator": "section 3.1", "note": "Not FinVector's 700-token condition; adequacy checked on pilot, before main"},
            {"parameter": "context_tokens", "value": 65536, "kind": "engineering_candidate_not_paper_constant", "note": "Preserve all four stages including visible responses and calculation feedback; verify actual tokenization and memory"}],
        "backend_settings": "Pin served digest, quantization, chat template, engine, context, sampling defaults and thinking implementation from actual runtime evidence.",
        "context_overflow": "fail and record; no silent truncation, history deletion or budget change",
        "limitations": ["financial base-model paper scores do not measure this quantized runtime", "small-model application, not PortBench replication", "basic task inability can obscure workflow differences", "no hidden-thinking or memory mechanism identification"],
        "future_decoding_candidates_not_applied": [
            {"values": {"seed": 3407}, "basis": "directly reported in FinVector section 4.1", "source": FINVECTOR,
             "validated_for_libera": False},
            {"values": {"repeat_penalty": 1, "presence_penalty": 0, "frequency_penalty": 0},
             "basis": "implementation translation of the author's minimal public example and MLX-LM 0.31.3 default argmax with logits_processors=None; NOT reported benchmark penalty values",
             "sources": [FINVECTOR_EXAMPLE, MLX_GENERATE], "validated_for_libera": False}],
        "future_candidate_scope": "Not applied to the v4.3 research pilot/main protocol; separate engineering probes may use these values without establishing research validity.",
        "review": "../" + REVIEW,
    }
    cfg["evaluation"]["post_outcome_additions"] = "Rubric refinements allowed on pilot only before main freeze; additions after main outcomes are exploratory, not revised confirmatory rules."
    cfg["evaluation"]["status"] = "mechanical_spec_implemented; see_observed_execution_for_reviews; freeze_after_pilot_before_main"
    cfg["main"]["status"] = status["main"]["status"]
    cfg["main"]["pending"] = ["check actual runtime pin and full four-stage pilot evidence", "independent semantic/source review", "freeze inputs, model and rubric before main responses", "main execution and offline evaluation"]
    cfg["main"]["blocking_design_decisions"] = [{
        "issue": "Inherited presence_penalty=1.5 is not a reported FinVector benchmark parameter; the paper does not report penalties.",
        "required_before_main_freeze": "Decide and document treatment of unreported model defaults, evidence strength and limitations; record any runtime/protocol revision and required pilot revalidation.",
        "current_pilot_settings_changed": False,
        "all_parameters_paper_reported_claim_permitted": False,
    }]
    cfg["main"]["runtime_policy"] = "candidate selected; actual readiness requires separate reviewed runtime and pilot evidence"
    p, m = status["pilot"], status["main"]
    total_calls = None if p["completed_calls"] is None or m["completed_calls"] is None else p["completed_calls"] + m["completed_calls"]
    total_cases = None if p["completed_cases"] is None or m["completed_cases"] is None else p["completed_cases"] + m["completed_cases"]
    observed_activity = (total_calls or 0) > 0 or any(
        isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
        for value in (p.get("attempted_calls_observed"), m.get("attempted_calls_observed"),
                      status["runtime"].get("diagnostic_completed_calls")))
    cfg["results"] = {
        "ai_runs": total_cases, "ai_completed_calls": total_calls,
        "pilot_completed_cases": p["completed_cases"], "pilot_completed_calls": p["completed_calls"],
        "main_completed_cases": m["completed_cases"], "main_completed_calls": m["completed_calls"],
        "pilot_attempted_calls_observed": p.get("attempted_calls_observed"),
        "diagnostic_completed_calls_excluded_from_experiment": status["runtime"].get("diagnostic_completed_calls"),
        "human_runs": status["human_review"].get("completed_reviews"),
        "count_unit": "ai_runs counts completed four-stage cases; calls counted separately; diagnostics excluded",
        "count_source": "observed_execution status input, or zero linked observations when no status supplied",
        "main_execution_ready": False, "readiness_assessment": "not_automatically_certified_by_document_builder",
        "material_preparation_complete": old["results"].get("material_preparation_complete"),
        "software_tests_only": False if observed_activity else True if not status["input_supplied"] else None,
        "main_effect_estimate": None,
    }
    cfg["sources"]["small_model_finance"] = DATACENTRIC
    cfg["sources"]["nonthinking_structured_finance"] = FINVECTOR
    return cfg


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status-json", type=Path)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--output-root", type=Path, default=ROOT)
    args = parser.parse_args()
    root, out = args.source_root.resolve(), args.output_root.resolve()
    sources = {key: root / template.format(date=OLD_DATE) for key, template in NAMES.items()}
    before = {key: sha256(path) for key, path in sources.items()}
    raw = read_json(args.status_json) if args.status_json else None
    status = normalize_status(raw, root)
    status_record = source_record(args.status_json, root) if args.status_json else None
    provenance = {"builder": "research/build_sector_revision_v43.py",
                  "source_version": "4.2", "source_files": {key: source_record(path, root) for key, path in sources.items()},
                  "model_review": source_record(root / REVIEW, root),
                  "registry_observation": source_record(root / REGISTRY, root),
                  "status_input": status_record, "network_or_model_execution": False,
                  "previous_audits_apply_to_previous_versions_only": True}
    config = build_config(read_json(sources["config"]), status, provenance)
    documents = {key: build_html(sources[key], key, status, status_record) for key in ("plan", "paper")}
    # Abort before any write if the preservation input changed during this build.
    if before != {key: sha256(path) for key, path in sources.items()}:
        raise RuntimeError("v4.2 source changed while building; rerun from a consistent snapshot")
    outputs = {key: out / template.format(date=NEW_DATE) for key, template in NAMES.items()}
    if any(path.resolve() in {p.resolve() for p in sources.values()} for path in outputs.values()):
        raise ValueError("Refusing to overwrite preserved source documents")
    for path in outputs.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    for key, document in documents.items():
        outputs[key].write_text(document, encoding="utf-8")
    outputs["config"].write_text(json.dumps(config, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"protocol_version": "4.3", "outputs": {k: str(v) for k, v in outputs.items()},
                      "source_hashes_unchanged": before == {k: sha256(p) for k, p in sources.items()},
                      "status_input_supplied": status["input_supplied"], "warnings": status["warnings"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
