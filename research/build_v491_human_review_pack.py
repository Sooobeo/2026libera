"""Build blank, output-blind human review materials without any model calls."""
from __future__ import annotations

import copy
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "research/v491_human_review_pack_20261019"
PACK_ID = "v491_preoutput_review_20261019"
SECTORS = ["10", "15", "20", "25", "30", "35", "40", "45", "50", "55", "60"]
KOREAN = ["에너지", "소재", "산업재", "경기소비재", "필수소비재", "건강관리", "금융", "정보기술", "커뮤니케이션 서비스", "유틸리티", "부동산"]
OPTIONS = {
    "checked": [("confirmed", "원문과 일치 확인"), ("issue_found", "불일치·문제 발견"), ("uncertain", "확인 곤란·판단 유보")],
    "comparison": [("substantive_difference_supported", "실질적인 판단 차이가 근거로 확인됨"), ("similarity_supported", "유사한 판단이 근거로 확인됨"), ("different_scales_not_directly_comparable", "척도·범위 차이로 직접 비교 곤란"), ("insufficient_evidence", "근거 부족"), ("uncertain", "불확실")],
    "boolean": [(True, "예"), (False, "아니요")],
    "scope": [("pilot", "우선 개발용 문서(pilot)만 검토"), ("main", "본실험 문서(main) 검토"), ("both", "개발용·본실험 모두 검토")],
}


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def ref(path):
    p = ROOT / path
    return {"path": path, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def save(path, obj):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def build_base():
    template_path = "research/v491_human_review_template_20261019.json"
    protocol_path = "research/v491_evaluation_protocol_20261019.json"
    context_path = "data/sector_context/v491_20261019/common_context.json"
    candidate_path = "data/sector_protocol/v491_design_20261019/public_compact_candidate.json"
    manifest_path = "data/sector_documents/source_manifest.json"
    template, protocol, context, candidate, manifest = [read(p) for p in [template_path, protocol_path, context_path, candidate_path, manifest_path]]
    fields = []

    def field(key, label, section, kind="text", options=None):
        item = {"key": key, "label": label, "section": section, "kind": kind}
        if options:
            item["options"] = OPTIONS[options]
        fields.append(item)
        return key

    for key, label, kind, opt in [
        ("reviewer_name", "검토자 이름 또는 연구팀 내 식별자", "text", None),
        ("reviewer_background", "원문을 해석할 수 있는 배경·역할 (경제·금융·영어 등)", "text", None),
        ("review_scope", "이번 제출에서 완료한 검토 범위 (우선 pilot만 작성해도 됩니다)", "select", "scope"),
        ("completed_at_utc", "선택한 범위의 작성 완료 시각 (UTC ISO 8601; 예: 2026-10-20T09:00:00Z)", "text", None),
        ("independent_work", "다른 검토자의 답안을 읽거나 상의하기 전에 따로 작성했습니까?", "select", "boolean"),
        ("no_model_outputs_seen", "이번 검토 범위에 해당하는 v4.9.1 실험 또는 연구입력 진단의 AI 출력을 보지 않았습니까?", "select", "boolean"),
        ("conflicts_or_prior_exposure", "기존 실험·AI 답변 또는 다른 검토자 의견을 본 이력이 있다면 범위와 시점을 적으세요. 없으면 '없음'.", "text", None),
        ("original_pdf_read", "아래의 해시로 지정된 원문 PDF와 공통 근거를 직접 대조했습니까?", "select", "boolean"),
    ]:
        field("meta." + key, label, "meta", kind, opt)
    for key, label in [
        ("task_vs_institution", "가상 신규 자금 과제와 기관의 실제 목적·보유분을 구분했는지, 정량 위험·목표 비중을 임의로 만들지 않았는지 검토하세요."),
        ("date_horizon", "판단일·12개월 과제와 각 보고서의 날짜·기간 차이를 검토하세요. 6/31/26 날짜 오기와 사후 자료수집 한계도 기록하세요."),
        ("benchmark_market", "비교 기준은 기존 보유분·정답이 아님을 확인하고, 산업 ETF 수익률·공분산·단위·기간·계산 계보의 문제를 기록하세요."),
        ("rubric_scope", "평가 규칙의 근거→해석→선택 연결이 적절한지, 어휘나 비중 차이를 자동 성공으로 삼지 않는지 검토하세요. 모호하면 수정 제안을 적으세요."),
    ]:
        field("common." + key + ".status", label + " (판정)", "common", "select", "checked")
        field("common." + key + ".evidence", "위 판정의 근거·위치·남은 문제 (없음도 명시)", "common")
    ft = context["market_context"]["fact_table"]
    macros = [{**ft["shared"], **dict(zip(ft["columns"], r))} for r in ft["rows"]]
    for m in macros:
        prefix = "macro." + m["evidence_id"]
        field(prefix + ".status", "원문 수치·단위·관측기간·발표일·판본 확인", "macro", "select", "checked")
        field(prefix + ".evidence", "직접 확인한 원문 위치·판정 근거·불확실성", "macro")
    sources = []
    source_inputs = []
    for m in manifest["sources"]:
        sid, split = m["source_id"], m["split"]
        pp = f"data/sector_documents/packets/{split}/{sid}.json"
        packet = read(pp)
        assert ref(m["cache"]["path"])["sha256"] == m["cache"]["sha256"]
        source_inputs.extend([ref(pp), ref(m["cache"]["path"])])
        rows = []
        for code in SECTORS:
            passages = [e for e in packet["evidence_passages"] if e["evidence_id"].endswith(":sector:" + code)]
            assert len(passages) == 1
            prefix = f"source.{split}.{sid}.{code}"
            rows.append({"sector_code": code, "sector_name_ko": KOREAN[SECTORS.index(code)], "passages": passages, "answer_prefix": prefix})
            field(prefix + ".original_meaning", "원문을 확인한 뒤 평가어·이유·범위를 짧게 확인하세요. 아래 요약과 같으면 '해당 의미 확인, p.__'처럼 적어도 됩니다. 원문 이유가 없으면 명시하세요.", "source:" + sid)
            field(prefix + ".paraphrase_status", "아래 연구자 요약이 원문 의미를 보존했습니까?", "source:" + sid, "select", "checked")
            field(prefix + ".evidence_and_issues", "원문 페이지·문장 위치 및 판정 근거. 이유를 새로 만들거나 목표 비중으로 번역하지 마세요.", "source:" + sid)
        sources.append({"source_id": sid, "split": split, "packet": packet, "original": m, "sector_review_rows": rows})
    comparisons = copy.deepcopy(template["source_comparison"])
    for split, obj in comparisons.items():
        for row in obj["rows"]:
            prefix = f"comparison.{split}.{row['sector_code']}"
            row["answer_prefix"] = prefix
            field(prefix + ".decision", "기관 간 의미 비교", "comparison:" + split, "select", "comparison")
            field(prefix + ".reason_and_scope", "공통점·차이·비교 곤란의 구체적 이유와 범위. 서로 다른 단어만으로 실질 차이를 단정하지 마세요.", "comparison:" + split)
            field(prefix + ".source_locations", "두 원문 각각의 페이지·문장 위치와 근거 ID", "comparison:" + split)
    refs = [ref(p) for p in [template_path, protocol_path, context_path, candidate_path, manifest_path]] + source_inputs
    return {
        "pack_id": PACK_ID,
        "protocol_version": "4.9.1",
        "phase": "pre_output_source_and_context_review",
        "visibility": "evaluator_only_never_model_input",
        "status": "blank_human_form_not_completed_review",
        "human_review_completed": False,
        "model_outputs_included": False,
        "input_refs": refs,
        "source_documents": sources,
        "source_comparison": comparisons,
        "common_context": context,
        "macro_review_facts": macros,
        "common_market": candidate["common_market"],
        "public_numeric_fact_index": candidate["public_numeric_fact_index"],
        "evaluation_protocol": protocol,
        "form_fields": fields,
        "answers": {f["key"]: None for f in fields},
        "completion_policy": {
            "reviewers": "Two distinct human readers complete their own forms before any corresponding v4.9.1 research outputs are viewed. This is quality control, not extra statistical samples.",
            "independence": "R1 and R2 receive only their own blank form and the same source material. The coordinator retains submitted originals and hashes before sharing disagreement items.",
            "uncertainty": "Do not force agreement. Preserve issue_found, uncertain, insufficient_evidence and different_scales_not_directly_comparable, with evidence.",
            "pilot_gate": "The pre-output review gate applies to pilot as well as main. Content-neutral runtime diagnostics may precede it; research-output diagnostics must not be shown to reviewers.",
            "reconciliation": "After both forms are saved, compare all source and context findings and all 11 contrasts per split. Preserve both originals, disagreements, reconciliation rationale and unresolved items. Material input/rubric changes require a new version and renewed relevant review before generation.",
            "approval": "Saving or exporting this form never marks human review complete. A coordinator must verify named human attestations, all relevant answers and evidence, preserve unresolved findings, and create the split gate receipt.",
            "no_fabricated_targets": "No gold sector weights, rating-to-weight conversion, utility coefficient or forced disagreement may be invented.",
            "topic_connection": "Assess whether differing public organizational judgments survive as supported interpretations and allocation reasons. Different words or weights alone do not establish fidelity or harmful homogenization.",
        },
    }


def escaped(value):
    return html.escape(str(value), quote=True)


def field_html(field):
    key = escaped(field["key"])
    if field["kind"] == "select":
        body = '<select data-key="' + key + '"><option value="">미작성</option>'
        for value, label in field["options"]:
            body += '<option value="' + escaped(json.dumps(value, ensure_ascii=False)) + '">' + escaped(label) + '</option>'
        body += '</select>'
    else:
        body = f'<textarea data-key="{key}" rows="3" spellcheck="false"></textarea>'
    return '<label>' + escaped(field["label"]) + body + '</label>'


def render(pack, json_ref):
    by_prefix = lambda p: ''.join(field_html(f) for f in pack["form_fields"] if f["key"].startswith(p))
    parts = [f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LIBERA 독립 검토 {pack['reviewer_slot']}</title>
<style>body{{font:16px/1.65 system-ui,sans-serif;color:#182435;background:#f4f6f9;margin:0}}main{{max-width:1060px;margin:auto;padding:36px 24px}}h1,h2,h3{{line-height:1.35}}h1{{font-size:30px}}h2{{margin-top:42px}}section,article,details{{background:white;border:1px solid #d9e1eb;border-radius:10px;padding:20px;margin:18px 0}}label{{display:block;margin:18px 0;font-weight:600}}textarea,select,input{{display:block;box-sizing:border-box;width:100%;font:15px/1.5 system-ui;margin-top:6px;padding:10px;border:1px solid #9aaec4;border-radius:5px;background:#fff;color:#162e49}}textarea{{resize:vertical;min-height:85px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.5 ui-monospace,monospace;background:#f1f5fa;padding:12px}}a{{color:#1758a4}}summary{{cursor:pointer;font-weight:700}}.note{{border-left:5px solid #426da3;background:#edf3fc;padding:14px 18px}}.warn{{border-color:#b47720;background:#fff7e8}}.tools{{position:sticky;top:0;background:#182e49;color:white;padding:12px 16px;z-index:1;display:flex;align-items:center;gap:12px;flex-wrap:wrap}}button{{font:inherit;padding:8px 13px;cursor:pointer}}.tools input{{width:240px;background:white;margin:0}}.id{{font:13px ui-monospace,monospace;overflow-wrap:anywhere}}.source{{border-left:3px solid #a7c0df;padding-left:14px}}@media print{{.tools{{display:none}}body{{background:white}}main{{padding:0}}details{{break-inside:avoid}}textarea{{border:1px solid #999}}}}@media(max-width:650px){{main{{padding:18px 12px}}section,article,details{{padding:14px}}h1{{font-size:25px}}}}</style>
<main><p>LIBERA · v4.9.1 · 사람 검토 사전 자료 · {pack['reviewer_slot']}</p><h1>기관별 판단이 무엇인지 먼저 확인하기</h1>
<p>이 자료는 <strong>{pack['reviewer_slot']} 한 사람의 독립 작성본</strong>입니다. AI 결과를 평가하기 전에 원문이 실제로 무엇을 말하는지, 두 기관의 판단을 비교할 수 있는지 확정합니다. 모든 답란은 비어 있습니다. 자동 저장은 없으므로 작업 중에도 JSON 저장을 누르세요. 저장한 파일은 같은 검토자 페이지에서 불러올 수 있습니다.</p>
<div class="note"><strong>지금은 pilot 검토부터 하면 됩니다.</strong> 작성자 8칸 + 공통 검토 8칸 + 거시 7개×2칸 + 개발 문서 22행×3칸 + 개발 기관 비교 11행×3칸 = 129답란입니다. 본실험(main)의 22행·비교 11행, 즉 99답란은 pilot 실행 전에는 비워 두어도 됩니다. 제공된 수치나 문장을 모두 다시 옮길 필요 없이 원문 대조 결과와 위치를 짧게 적으세요. 본실험 전에는 main 부분을 별도 완료·잠금합니다.</div>
<nav><a href="#review-meta">작성자</a> · <a href="#review-common">공통 상황</a> · <a href="#fidelity_q2_2026">개발 Fidelity</a> · <a href="#ubs_june_2026">개발 UBS</a> · <a href="#compare-pilot">개발 기관 비교</a> · <a href="#fidelity_q3_2026">본실험 Fidelity</a> · <a href="#ubs_july_2026">본실험 UBS</a> · <a href="#compare-main">본실험 기관 비교</a></nav>
<div class="note warn">다른 검토자의 답안과 v4.9.1 연구입력에 대한 AI 답변을 보지 않은 상태에서 작성하세요. 이 페이지의 영문 요약은 연구자가 만든 자료이며 원문 자체가 아닙니다. 링크된 원문 PDF를 직접 대조해야 합니다. 기존 출력이나 타인의 의견을 본 이력은 숨기지 않고 기록합니다.</div>
<div class="tools"><button type="button" id="export">작성 내용 JSON 저장</button><label style="margin:0">내 답안 불러오기 <input id="import" type="file" accept="application/json,.json"></label><span id="progress" aria-live="polite"></span></div>
<section><h2>검토 순서와 연구 목적</h2><ol><li>공통 업무·시장 사실과 원문 PDF의 날짜, 범위, 평가어 정의를 확인합니다.</li><li>4개 문서의 11개 산업을 빠짐없이 읽고 요약의 충실성·근거·불확실성을 기록합니다.</li><li>개발용 문서끼리 11개, 본실험 문서끼리 11개 비교를 작성합니다. 단어 차이를 판단 차이로 강제 환산하지 않습니다.</li><li>작성본을 저장해 조정자에게 전달합니다. 두 원본을 먼저 잠근 뒤 의견 차이를 논의합니다.</li></ol><p>논문의 질문은 공통 AI가 조직별 공개 판단을 근거 있는 배분 제안에 어떻게 전달하는가입니다. 원문의 차이를 사전에 확인해야 나중에 비중이 같거나 다르다는 결과를 올바르게 해석할 수 있습니다. 평가어를 정답 비중으로 바꾸지 않고, 근거가 있으면 기관 전망에서 벗어난 배분도 평가할 수 있게 합니다. 두 명 검토는 현지 품질관리 절차이며 논문이 정한 최적 인원이나 통계 표본 수가 아닙니다.</p><p>예비실험과 본실험 모두 해당 출력을 보기 전 이 관문을 거칩니다. 서로 다른 척도 때문에 직접 비교하기 어렵거나 근거가 부족하다는 결론도 허용합니다. 차이가 없다는 이유로 문서나 산업을 결과에 맞춰 교체하지 않습니다.</p></section>
<h2 id="review-meta">1. 독립성·작성자 기록</h2>{by_prefix('meta.')}
<h2 id="review-common">2. 공통 업무와 시장 맥락</h2><p>미국 11개 산업에 신규 자금을 배분하는 가상 과제입니다. 기준일은 2026-07-17, 판단기간은 12개월이며 기존 산업 보유분은 없습니다. S&amp;P 산업 비중은 비교 기준입니다. 공개 전망에서 알 수 없는 기관의 목표수익률·위험회피계수·목표 비중을 만들지 않습니다. 오래된 개발 보고서에도 같은 7월 상황을 주므로 당시 운용의 실시간 재현으로 해석하지 않습니다.</p>
<details><summary>실제 공통 업무 지시 원문</summary><pre>{escaped(json.dumps(pack['common_context']['operating_brief'],ensure_ascii=False,indent=2))}</pre></details>
<details><summary>실제 산업별 시장수치·계산 계보 (공통 입력과 동일)</summary><pre>{escaped(json.dumps({'common_market':pack['common_market'],'public_numeric_fact_index':pack['public_numeric_fact_index']},ensure_ascii=False,indent=2))}</pre></details>{by_prefix('common.')}
<h3>7개 거시 사실의 원문 대조</h3>''']
    for fact in pack["macro_review_facts"]:
        parts.append('<article><h3>' + escaped(fact['label']) + '</h3><p class="id">' + escaped(fact['evidence_id']) + '</p><p><a target="_blank" rel="noopener" href="' + escaped(fact['source_url']) + '">공식 발표 원문</a></p><pre>' + escaped(json.dumps(fact, ensure_ascii=False, indent=2)) + '</pre>' + by_prefix('macro.' + fact['evidence_id'] + '.') + '</article>')
    parts.append('<h2>3. 문서별 11개 산업 읽기</h2><p>PDF 파일을 직접 여는 링크와 공개 URL을 함께 제공합니다. 공개 URL은 나중에 내용이 바뀔 수 있으므로 아래 SHA-256으로 지정된 저장본이 비교 기준입니다. 페이지 번호는 기존 패킷의 source_page 표기를 따르며 원문 페이지와 맞는지도 검토합니다.</p>')
    for src in pack['source_documents']:
        original, packet, sid = src['original'], src['packet'], src['source_id']
        parts.append(f'<section id="{escaped(sid)}"><h3>{escaped(packet["title"])} · {escaped(src["split"])}</h3><p><a href="../{escaped(original["cache"]["path"])}" target="_blank">해시 고정 원문 PDF</a> · <a href="{escaped(packet["source_url"])}" target="_blank" rel="noopener">공개 URL</a></p><p class="id">SHA-256: {original["cache"]["sha256"]}</p><p>원문 확인 페이지: {escaped(json.dumps(original["source_pages"],ensure_ascii=False))}</p><details><summary>날짜·원문 범위·이미 알려진 문제</summary><pre>{escaped(json.dumps({"dates":packet["dates"],"known_source_issues":original["known_source_issues"],"rating_vocabulary":packet["rating_vocabulary"],"scope_passages":[e for e in packet["evidence_passages"] if ":sector:" not in e["evidence_id"]]},ensure_ascii=False,indent=2))}</pre></details>')
        for row in src['sector_review_rows']:
            parts.append('<details class="source-row"><summary>' + row['sector_code'] + ' · ' + row['sector_name_ko'] + '</summary>')
            for e in row['passages']:
                parts.append('<p class="source">연구자 요약 (원문과 직접 대조): ' + escaped(e['text']) + '</p><p class="id">' + escaped(e['evidence_id']) + ' · 원문 p.' + str(e['source_page']) + '</p>')
            parts.append(by_prefix(row['answer_prefix'] + '.') + '</details>')
        parts.append('</section>')
    parts.append('<h2>4. 기관 간 의미 비교</h2><p>먼저 같은 산업에서 두 원문이 말하는 대상과 평가척도가 같은지 확인합니다. Overweight와 Attractive는 다른 어휘와 정의이므로 자동 등치하지 않습니다. 같은 비중이 합리적일 수 있고 다른 비중에 근거가 없을 수 있습니다. 여기서는 모델의 비중을 예측하지 않습니다.</p>')
    for split, obj in pack['source_comparison'].items():
        parts.append('<section id="compare-' + split + '"><h3>' + ('개발용 문서 비교' if split == 'pilot' else '본실험 문서 비교') + '</h3>')
        for row in obj['rows']:
            parts.append('<details class="comparison-row"><summary>' + row['sector_code'] + ' · ' + KOREAN[SECTORS.index(row['sector_code'])] + '</summary>')
            for src in row['sources']:
                parts.append('<p><strong>' + escaped(src['source_id']) + '</strong> · 원문 평가어: ' + escaped(', '.join(src['rating_vocabulary'])) + '</p>')
                for e in src['passages']:
                    parts.append('<p class="source">연구자 요약: ' + escaped(e['text']) + '</p><p class="id">' + escaped(e['evidence_id']) + ' · p.' + str(e['source_page']) + '</p>')
            parts.append(by_prefix(row['answer_prefix'] + '.') + '</details>')
        parts.append('</section>')
    parts.append('<h2>5. 조정과 다음 단계</h2><p>두 검토자가 따로 작성한 원본 JSON을 조정자가 먼저 보존하고 각각 SHA-256을 기록합니다. 그 뒤 모든 산업의 의견 차이와 공통사실 문제를 비교합니다. 조정본에는 두 판단, 근거, 합의 또는 미해결 사유를 남기고 원본을 덮어쓰지 않습니다. 불확실성·직접 비교 불가능은 유효한 판단입니다. 사실 오류가 발견되어 입력이나 평가 규칙이 바뀌면 새 판본으로 검토한 뒤 동결합니다.</p><p>출력 이후에는 조건·실행 순서를 가린 결과를 같은 두 사람이 따로 검토합니다. 실제 설명으로 조건이 추측될 수 있다는 한계는 남습니다. E/L 차이·기관 간 차이와 근거 충실성을 구분하고, 실패·누락을 0거리나 기준 배분으로 채우지 않습니다. 이 작성본 저장만으로 본실험이 승인되거나 검토가 완료되지 않습니다.</p><details><summary>기존 평가 프로토콜 전문</summary><pre>' + escaped(json.dumps(pack['evaluation_protocol'],ensure_ascii=False,indent=2)) + '</pre></details>')
    script_data = {'pack_id': PACK_ID, 'reviewer_slot': pack['reviewer_slot'], 'blank_form_ref': json_ref, 'fields': pack['form_fields'], 'input_refs': pack['input_refs']}
    parts.append('<script id="pack-data" type="application/json">' + json.dumps(script_data, ensure_ascii=False).replace('</', '<\\/') + '</script>')
    parts.append('''<script>
const pack=JSON.parse(document.getElementById('pack-data').textContent);
const fields=Array.from(document.querySelectorAll('[data-key]'));
const fieldMeta=new Map(pack.fields.map(f=>[f.key,f]));
function currentAnswers(){return Object.fromEntries(fields.map(el=>[el.dataset.key,el.value===''?null:(el.tagName==='SELECT'?JSON.parse(el.value):el.value)]));}
function updateProgress(){const a=currentAnswers();document.getElementById('progress').textContent=Object.values(a).filter(v=>v!==null&&v!=='').length+' / '+fields.length+'개 답란 작성 · 검토 완료는 별도 확인';}
function exportPayload(){return {pack_id:pack.pack_id,reviewer_slot:pack.reviewer_slot,blank_form_ref:pack.blank_form_ref,input_refs:pack.input_refs,exported_at_utc:new Date().toISOString(),status:'human_submission_requires_coordinator_check',human_review_completed:false,answers:currentAnswers()};}
function applyAnswers(data){
 if(data.pack_id!==pack.pack_id||data.reviewer_slot!==pack.reviewer_slot||JSON.stringify(data.blank_form_ref)!==JSON.stringify(pack.blank_form_ref))throw Error('이 검토자·판본의 저장 파일이 아닙니다.');
 if(!data.answers||Array.isArray(data.answers)||typeof data.answers!=='object')throw Error('답안 형식이 올바르지 않습니다.');
 if(Object.keys(data.answers).length!==fields.length||!fields.every(el=>Object.hasOwn(data.answers,el.dataset.key)))throw Error('답안 항목이 이 판본과 다릅니다.');
 for(const el of fields){const v=data.answers[el.dataset.key],f=fieldMeta.get(el.dataset.key);if(v!==null&&(f.kind==='select'?!f.options.some(o=>o[0]===v):typeof v!=='string'))throw Error('허용되지 않은 답안 형식: '+el.dataset.key);}
 for(const el of fields){const v=data.answers[el.dataset.key];el.value=v===null?'':(el.tagName==='SELECT'?JSON.stringify(v):v);}updateProgress();
}
document.getElementById('export').addEventListener('click',()=>{const data=exportPayload();const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)+'\\n'],{type:'application/json;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=pack.pack_id+'_'+pack.reviewer_slot+'_answers_'+new Date().toISOString().replaceAll(':','-')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
document.getElementById('import').addEventListener('change',async event=>{try{const f=event.target.files[0];if(!f)return;applyAnswers(JSON.parse(await f.text()));}catch(e){alert(e.message);}finally{event.target.value='';}});
fields.forEach(el=>el.addEventListener('input',updateProgress));updateProgress();
</script></main></html>''')
    return ''.join(parts)


def main():
    base = build_base()
    outputs = []
    for slot in ['R1', 'R2']:
        pack = copy.deepcopy(base)
        pack['reviewer_slot'] = slot
        jp, hp = f'{PREFIX}_{slot}.json', f'{PREFIX}_{slot}.html'
        save(jp, pack)
        (ROOT / hp).write_text(render(pack, ref(jp)), encoding='utf-8', newline='\n')
        outputs.extend([ref(jp), ref(hp)])
    gate = {
        'receipt_version': 'v491_human_preoutput_gate_1',
        'pack_id': PACK_ID,
        'status': 'pending_human_completion',
        'visibility': 'evaluator_only_never_model_input',
        'blank_form_refs': [r for r in outputs if r['path'].endswith('.json')],
        'input_refs': base['input_refs'],
        'reviewers': [{'reviewer_slot':s,'reviewer_name':None,'submission_path':None,'submission_sha256':None,'completed_at_utc':None,'independent_work':None,'no_model_outputs_seen':None,'original_pdf_read':None} for s in ['R1','R2']],
        'coordinator': {'name':None,'reviewed_at_utc':None,'authenticity_note':'Machine checks can validate completeness and file identity, not certify that a human performed a review.'},
        'splits': {split:{'status':'pending','reviewer_fields_complete':None,'source_review_rows_reviewed':None,'common_context_reviewed':None,'evaluation_rubric_reviewed':None,'source_comparison_rows':[{'sector_code':c,'r1_decision':None,'r2_decision':None,'reconciled_decision':None,'evidence_and_reason':None,'disagreement_preserved':None} for c in SECTORS],'source_and_context_disagreements':None,'unresolved_findings':None,'material_input_or_rubric_change_required':None,'gate_approved_by_human':None,'gate_rationale':None,'gate_recorded_before_research_outputs':None} for split in ['pilot','main']},
        'completion_rules': [
            'Preserve two separate named human submissions and exact hashes before reconciliation; no AI-filled human answers.',
            'First complete pilot: metadata/common/macro + pilot source and 11 pilot comparison fields only (129 fields). Main-only fields may remain null before pilot; main must be completed and separately gated before main outputs. Uncertainty is permitted with evidence.',
            'Populate every comparison row with R1/R2 originals and the reconciled finding; retain disagreements and unresolved items.',
            'Confirmed material factual/representation/rubric errors require a new version and renewed review before the affected split can run.',
            'Coordinator records split approval and rationale before any corresponding research output; an export alone is not approval.',
            'Preserve the lack of substantive source distinction when found; do not force a difference or replace documents based on outputs.',
            'Never supply this receipt, either reviewer form, source comparison or evaluation rubric to the model.'
        ]
    }
    gate['completed_receipt_contract'] = {
        'status': 'completed_for_approved_splits',
        'reviewer_scope_rule': 'Each submitted meta.review_scope must be the approved split or both. Each split may reference an original saved copy; preserve pilot originals when later completing main.',
        'approved_split_status': 'reviewed_before_outputs',
        'required_true_split_fields': ['reviewer_fields_complete','common_context_reviewed','evaluation_rubric_reviewed','gate_approved_by_human','gate_recorded_before_research_outputs'],
        'source_review_rows_reviewed': 22,
        'required_false_split_fields': ['material_input_or_rubric_change_required'],
        'required_list_split_fields': ['source_and_context_disagreements','unresolved_findings'],
        'comparison_decisions_allowed': [o[0] for o in OPTIONS['comparison']],
        'approval_does_not_require': ['substantive_difference_supported in any row','unanimity','a numeric target allocation','successful model outputs'],
    }
    gate_path = f'{PREFIX}_gate_blank.json'
    save(gate_path, gate)
    outputs.append(ref(gate_path))
    save(f'{PREFIX}_manifest.json', {'pack_id':PACK_ID,'status':'blank_human_materials_ready_no_human_review_completed','model_calls':0,'human_review_completed':False,'counts':{'reviewers':2,'source_documents_per_reviewer':4,'source_sector_rows_per_reviewer':44,'source_comparison_rows_per_reviewer':22,'macro_facts_per_reviewer':7,'answer_fields_per_reviewer':len(base['form_fields']),'required_fields_for_pilot':129,'additional_fields_for_main':99},'output_refs':outputs,'prior_input_refs':base['input_refs'],'generator_ref':ref('research/build_v491_human_review_pack.py')})
    print(json.dumps({'outputs':len(outputs),'fields_per_reviewer':len(base['form_fields']),'source_rows':44,'comparison_rows':22,'human_review_completed':False}))


if __name__ == '__main__':
    main()
