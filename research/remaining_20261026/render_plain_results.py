"""Render accepted terminal exploratory results as a standalone Korean HTML.

No model/service calls, no raw-response reads, no allocation recalculation.
Only accepted 10,000-unit vectors are displayed. Root generates actual reports
only after terminal finalization and the stagewise audits are complete.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
from html import escape
import json
import os
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = Path(__file__).resolve().parent
CASES = ("fidelity_q2_2026__E", "fidelity_q2_2026__L", "ubs_june_2026__E", "ubs_june_2026__L", "common_market_only__C")
CODES = ("10", "15", "20", "25", "30", "35", "40", "45", "50", "55", "60")
SECTORS = ("에너지", "소재", "산업재", "경기소비재", "필수소비재", "헬스케어", "금융", "정보기술", "커뮤니케이션 서비스", "유틸리티", "부동산")
LABELS = {
    CASES[0]: "Fidelity · 처음부터", CASES[1]: "Fidelity · 초안 뒤",
    CASES[2]: "UBS · 처음부터", CASES[3]: "UBS · 초안 뒤", CASES[4]: "기관자료 없음",
}
TITLE = "공통 생성형 AI의 기관별 공개 투자판단 반영"
SUBTITLE = "자료 제공 여부와 시점에 따른 산업배분 사례연구"


def require(value, message):
    if not value:
        raise ValueError(message)


def unique_object(items):
    out = {}
    for key, value in items:
        require(key not in out, "Duplicate JSON field: " + key)
        out[key] = value
    return out


def load(path):
    data = Path(path).read_bytes()
    def reject(value):
        raise ValueError("Nonfinite JSON value: " + value)
    return json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique_object, parse_constant=reject), data


def workspace_path(value):
    path = Path(value)
    path = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    require(path.is_relative_to(ROOT), "Workspace-contained file required")
    return path


def text(value, name):
    require(isinstance(value, str) and len(value) <= 20000, "Plain text required: " + name)
    return value


def notes_validated(notes):
    require(isinstance(notes, dict) and notes.get("schema_version") == "plain_results_notes_1", "Plain notes schema required")
    require(set(notes) <= {"schema_version", "title", "observations", "caveats", "related_files"}, "Unexpected notes fields")
    text(notes.get("title", TITLE), "title")
    for key in ("observations", "caveats", "related_files"):
        require(isinstance(notes.get(key), list) and len(notes[key]) <= 50, "Small notes list required: " + key)
    for row in notes["observations"]:
        require(isinstance(row, dict) and set(row) == {"title", "text"}, "Observation needs title/text only")
        text(row["title"], "observation title"); text(row["text"], "observation text")
    for item in notes["caveats"]:
        text(item, "caveat")
    for item in notes["related_files"]:
        require(isinstance(item, dict) and set(item) == {"label", "path"}, "Related file needs label/path only")
        text(item["label"], "link label")
        raw = text(item["path"], "link path")
        require(raw and not Path(raw).is_absolute() and ":" not in raw and not raw.startswith(("/", "\\")),
                "Links must be workspace-relative file paths, never web or script URLs")
        workspace_path(raw)
    return notes


def raw_total_percent(value):
    require(isinstance(value, str) and 0 < len(value) <= 2048, "Exact raw sum string required")
    amount = Decimal(value)
    require(amount.is_finite() and amount > 0 and abs(amount.adjusted()) <= 2048, "Finite positive raw sum required")
    with localcontext() as context:
        context.prec = 4096
        result = format(amount * 100, "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    return result + "%"


def percent_units(units):
    return str(units // 100) + "." + str(units % 100).zfill(2) + "%"


def validate_results(result):
    require(isinstance(result, dict) and result.get("version") == "sector_remaining_finalizer_1"
            and result.get("purpose") == "primary_exploratory_remaining_dataset"
            and result.get("analysis_role") == "primary_exploratory"
            and result.get("case_order") == list(CASES), "Accepted remaining exploratory result schema required")
    for key, value in (("planned_final_allocations", 5), ("planned_final_sector_rows", 55), ("logical_stage_slots", 10),
                       ("generation_calls", 0), ("service_calls", 0), ("main_model_calls", 0)):
        require(type(result.get(key)) is int and result[key] == value, "Wrong result scope: " + key)
    require(result.get("primary_final_allocation_endpoint") == "F0_derived_integer_allocation"
            and result.get("raw_diagnostics_required") is True, "Raw and derived endpoints must remain distinct")
    attempts = result.get("all_generation_requests_including_interrupted_attempt")
    require(type(attempts) is int and 6 <= attempts <= 11, "Six historical plus at most five new attempts required")
    records = result.get("stage_records")
    require(isinstance(records, list) and len(records) == 10, "All ten logical stage slots required")
    lookup, units = {}, {}
    for record in records:
        key = (record.get("case_id"), record.get("stage"))
        require(key[0] in CASES and key[1] in ("D0", "F0") and key not in lookup, "Exact unique case/stage required")
        require(record.get("status") in ("finalized", "unavailable"), "Unknown derived result status")
        lookup[key] = record
        if record["status"] != "finalized":
            continue
        require(record.get("version") == "sector_allocation_finalizer_1", "Accepted allocation version required")
        policy = record.get("policy", {})
        require(policy.get("normalization") == "positive_sum_proportional_scaling"
                and policy.get("rounding") == "largest_remainder_to_10000_integer_units", "Accepted exact allocation policy required")
        require(type(record.get("final_total_units")) is int and record["final_total_units"] == 10000, "10000 accepted units required")
        rows = record.get("rows")
        require(isinstance(rows, list) and len(rows) == 11, "Eleven accepted allocation rows required")
        vector = {}
        for row in rows:
            code, count = row.get("sector_code"), row.get("final_units")
            require(code in CODES and code not in vector and type(count) is int and 0 <= count <= 10000,
                    "Canonical sector and bounded integer units required")
            vector[code] = count
        require(set(vector) == set(CODES) and sum(vector.values()) == 10000, "Accepted final allocation does not sum to10000")
        raw_total_percent(record.get("raw_sum_exact_decimal"))
        units[key] = vector
    require(set(lookup) == {(case, stage) for case in CASES for stage in ("D0", "F0")}, "Missing logical stage slot")
    require(result.get("finalized_finals") == sum((case, "F0") in units for case in CASES), "Final availability count differs")
    validate_comparisons(result.get("derived_comparisons"), units)
    return lookup, units


def comparison_pairs():
    return {
        "within_source": [(CASES[0] + ":F0", CASES[1] + ":F0"), (CASES[2] + ":F0", CASES[3] + ":F0")],
        "between_source": [(CASES[0] + ":F0", CASES[2] + ":F0"), (CASES[1] + ":F0", CASES[3] + ":F0")],
        "shared_control": [(case + ":F0", CASES[4] + ":F0") for case in CASES[:4]],
        "own_D0_F0": [(case + ":F0", case + ":D0") for case in CASES],
    }


def validate_comparisons(groups, units):
    pairs = comparison_pairs()
    require(isinstance(groups, dict) and set(groups) == set(pairs), "All declared comparison groups required")
    for name, expected in pairs.items():
        require(isinstance(groups[name], list) and len(groups[name]) == len(expected), "Comparison denominator differs")
        for row, (left, right) in zip(groups[name], expected):
            require(row.get("left") == left and row.get("right") == right, "Comparison identity differs")
            lkey, rkey = tuple(left.rsplit(":", 1)), tuple(right.rsplit(":", 1))
            available = lkey in units and rkey in units
            if not available:
                require(row.get("status") == "unavailable", "Missing allocation cannot yield a comparison")
                continue
            require(row.get("status") == "computed", "Available comparison must retain computed result")
            delta = {code: units[lkey][code] - units[rkey][code] for code in CODES}
            require(row.get("final_unit_differences") == delta, "Derived difference does not match accepted integer vectors")
            ratio = row.get("total_variation_exact", {})
            for key in ("numerator", "denominator"):
                require(isinstance(ratio.get(key), str) and len(ratio[key]) <= 64, "Small exact TV ratio required")
            observed = Fraction(int(ratio["numerator"]), int(ratio["denominator"]))
            require(observed == Fraction(sum(abs(v) for v in delta.values()), 20000), "TV differs from accepted vectors")


def label(identity):
    case, stage = identity.rsplit(":", 1)
    return LABELS[case] + (" · 초안" if stage == "D0" else " · 최종")


def comparison_table(rows):
    content = []
    for row in rows:
        if row["status"] == "computed":
            ratio = row["total_variation_exact"]
            amount = Fraction(int(ratio["numerator"]), int(ratio["denominator"])) * 10000
            require(amount.denominator == 1, "TV display must retain exact0.01percent units")
            value = percent_units(amount.numerator)
        else:
            value = "산출 불가"
        content.append("<tr><td>" + escape(label(row["left"])) + "</td><td>" + escape(label(row["right"]))
                       + "</td><td class='number'>" + value + "</td></tr>")
    return "<div class='table-scroll'><table><thead><tr><th>배분 A</th><th>배분 B</th><th>다시 옮겨야 할 비중</th></tr></thead><tbody>" + "".join(content) + "</tbody></table></div>"


CSS = """
:root{color-scheme:light;--ink:#15283b;--muted:#526579;--line:#dce4ec;--blue:#1555a3;--paper:#fff;--soft:#f2f6fa}
*{box-sizing:border-box}body{margin:0;background:#eaf0f5;color:var(--ink);font-family:system-ui,-apple-system,'Malgun Gothic',sans-serif;line-height:1.7}
main{max-width:1180px;margin:32px auto;background:var(--paper);border:1px solid var(--line);border-radius:18px;padding:48px;box-shadow:0 8px 32px #15283b0a}
header{border-bottom:2px solid var(--ink);padding-bottom:26px}.eyebrow{color:var(--blue);font-weight:750;font-size:.86rem;letter-spacing:.03em}h1{font-size:2rem;line-height:1.35;margin:10px 0}h2{font-size:1.32rem;margin:38px 0 12px}h3{font-size:1.05rem;margin:24px 0 8px}.subtitle{font-size:1.15rem;margin:0;color:var(--muted)}p{margin:10px 0}.intro{max-width:850px}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:24px 0}.stat{background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:16px}.stat strong{display:block;font-size:1.4rem}.stat span{font-size:.88rem;color:var(--muted)}.note{background:#edf5ff;border-left:4px solid var(--blue);padding:14px 18px;margin:18px 0}.caution{background:#fff7e9;border-left-color:#a76b1b}.table-scroll{overflow-x:auto;margin:16px 0}table{width:100%;border-collapse:collapse;font-size:.9rem}th,td{border-bottom:1px solid var(--line);padding:10px 12px;text-align:left;vertical-align:top}th{background:var(--soft);font-weight:700}td.number,th.number{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}tfoot{font-weight:750;background:var(--soft)}caption{text-align:left;color:var(--muted);font-size:.85rem;padding-bottom:8px}.raw-error{color:#9c431c;font-weight:650}.missing{color:var(--muted)}.observation{border-top:1px solid var(--line);padding:6px 0 12px}.observation p{white-space:pre-wrap}.small{color:var(--muted);font-size:.85rem}.condition{white-space:nowrap}ol,ul{padding-left:24px}li{margin:8px 0}a{color:var(--blue);overflow-wrap:anywhere}details{border:1px solid var(--line);padding:14px 18px;border-radius:8px;margin-top:20px}summary{font-weight:700;cursor:pointer}footer{border-top:1px solid var(--line);margin-top:36px;padding-top:18px;overflow-wrap:anywhere}
@media(max-width:760px){main{margin:0;border-radius:0;border:0;padding:24px 18px}h1{font-size:1.55rem}.stats{grid-template-columns:1fr}.stat{padding:12px}table{min-width:620px}}
@media print{body{background:white}main{max-width:none;border:0;box-shadow:none;margin:0;padding:12mm}h2,h3{break-after:avoid}tr,.note,.stat{break-inside:avoid}.table-scroll{overflow:visible}table{font-size:8.5pt}a{color:inherit}details{display:block}summary{display:none}}
"""


def render_html(result, notes, *, related_links=None, provenance=None):
    notes_validated(notes)
    lookup, units = validate_results(result)
    total_rows = []
    for case in CASES:
        cells = ["<td class='condition'>" + escape(LABELS[case]) + "</td>"]
        for stage in ("D0", "F0"):
            record = lookup[(case, stage)]
            if (case, stage) in units:
                raw = raw_total_percent(record["raw_sum_exact_decimal"])
                warning = " raw-error" if Decimal(record["raw_sum_exact_decimal"]) != 1 else ""
                cells += ["<td class='number" + warning + "'>" + escape(raw) + "</td>",
                          "<td class='number'>" + percent_units(sum(units[(case, stage)].values())) + "</td>"]
            else:
                cells += ["<td class='number missing'>산출 불가</td>"] * 2
        total_rows.append("<tr>" + "".join(cells) + "</tr>")
    allocations = []
    for code, sector in zip(CODES, SECTORS):
        cells = ["<th scope='row'>" + sector + "</th>"]
        for case in CASES:
            vector = units.get((case, "F0"))
            cells.append("<td class='number' data-case='" + case + "' data-units='" + str(vector[code]) + "'>"
                         + percent_units(vector[code]) + "</td>" if vector is not None else "<td class='number missing'>—</td>")
        allocations.append("<tr>" + "".join(cells) + "</tr>")
    totals = [percent_units(sum(units[(c, "F0")].values())) if (c, "F0") in units else "산출 불가" for c in CASES]
    notes_html = "".join("<article class='observation'><h3>" + escape(row["title"]) + "</h3><p>" + escape(row["text"]) + "</p></article>" for row in notes["observations"])
    if not notes_html:
        notes_html = "<p class='small'>추가 관찰 요약이 제공되지 않았습니다. 아래의 배분 수치는 설명·인용의 정확성을 대신 평가하지 않습니다.</p>"
    extra_caveats = "".join("<li>" + escape(item) + "</li>" for item in notes["caveats"])
    links = "".join("<li><a href='" + escape(url, quote=True) + "'>" + escape(name) + "</a></li>" for name, url in (related_links or []))
    provenance_html = "".join("<p class='small'>" + escape(key) + ": " + escape(value) + "</p>" for key, value in (provenance or {}).items())
    groups = result["derived_comparisons"]
    condition_rows = "".join("<tr><td class='condition'>" + escape(LABELS[case]) + "</td><td>" + source + "</td><td>" + timing + "</td></tr>" for case, source, timing in (
        (CASES[0], "Fidelity 공개 문서", "초안 전부터 제공하고 최종 답변에서도 사용"),
        (CASES[1], "Fidelity 공개 문서", "공통 자료로 초안을 쓴 뒤, 최종 답변 전에 추가"),
        (CASES[2], "UBS 공개 문서", "초안 전부터 제공하고 최종 답변에서도 사용"),
        (CASES[3], "UBS 공개 문서", "공통 자료로 초안을 쓴 뒤, 최종 답변 전에 추가"),
        (CASES[4], "기관 자료 없음", "초안과 최종 답변 모두 공통 자료만 사용")))
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(notes.get('title', TITLE))}</title><style>{CSS}</style></head>
<body><main><header><div class="eyebrow">5조건 · 11업종 · 탐색적 주된 분석</div><h1>{escape(notes.get('title', TITLE))}</h1><p class="subtitle">{SUBTITLE}</p></header>
<section class="intro"><h2>무엇을 비교했나요?</h2><p>같은 AI에 같은 공통 시장자료를 주고, 기관의 공개 자료를 <strong>처음부터 주는 경우</strong>, <strong>초안 뒤에 주는 경우</strong>, <strong>주지 않는 경우</strong>를 비교했습니다. AI는 11개 업종의 배분 초안(D0)을 작성한 뒤, 자신의 초안과 계산 피드백을 검토해 최종 답변(F0)을 냈습니다.</p><p>여기서 ‘기관’은 <strong>그 기관의 공개 문서를 제공한 조건</strong>을 뜻합니다. 실제 기관의 투자 결정이나 정답 비중을 뜻하지 않습니다.</p></section>
<div class="stats"><div class="stat"><strong>{result['finalized_finals']} / 5조건</strong><span>보정된 최종 배분을 산출할 수 있는 조건</span></div><div class="stat"><strong>11개 업종</strong><span>모든 조건에서 같은 배분 대상</span></div><div class="stat"><strong>{result['all_generation_requests_including_interrupted_attempt']}회 요청</strong><span>중단된 시도를 포함한 전체 실행 기록</span></div></div>
<div class="table-scroll"><table><caption>‘처음부터’와 ‘초안 뒤’는 기관자료의 제공 방식을 뜻합니다.</caption><thead><tr><th>조건</th><th>기관자료</th><th>자료를 제공한 시점</th></tr></thead><tbody>{condition_rows}</tbody></table></div>
<div class="note caution">이 결과는 다섯 사례의 <strong>탐색적 분석</strong>입니다. 투자 수익을 검증한 실험이나 인과효과 추정이 아닙니다. ‘초안 뒤’ 조건은 시점 외에 대화 이력·초안·자료 노출도 달라져, 순수한 타이밍 효과라고 단정할 수 없습니다.</div>
<section><h2>관찰 요약</h2>{notes_html}</section>
<section><h2>원시 배분과 100% 보정은 구분해서 읽습니다</h2><p><strong>원시합</strong>은 AI가 실제 제출한 11개 비중을 더한 값입니다. <strong>보정합</strong>은 그 비중을 후처리해 합계 100%로 만든 값입니다. 원시 결과를 덮어쓰지 않고 둘 다 남겼습니다.</p><div class="table-scroll"><table id="budget-totals"><caption>D0는 초안, F0는 최종 답변입니다. 산출 불가는 0%가 아닙니다.</caption><thead><tr><th>조건</th><th class="number">초안 원시합</th><th class="number">초안 보정합</th><th class="number">최종 원시합</th><th class="number">최종 보정합</th></tr></thead><tbody>{''.join(total_rows)}</tbody></table></div>
<div class="note"><strong>보정 방법</strong><ol><li>각 원시 비중을 원시 총합으로 나누는 <strong>비례 정규화</strong>를 적용합니다. 예를 들어 원시합이 95%라면 각 비중을 0.95로 나눕니다. 95%나 88%와 같은 원시합 부족을 단순한 반올림 오류라고 부르지 않습니다.</li><li>정규화된 비중을 전체 10,000단위로 바꿉니다. 한 단위는 0.01%입니다. 각 값을 내린 뒤, 남은 단위를 소수 잔여가 큰 업종부터 배분합니다. 잔여가 같으면 미리 고정한 업종 코드 순서를 따릅니다.</li><li>아래 최종표는 이 절차를 거친 <strong>정수 단위 배분</strong>만 사용합니다. 보고서가 원시값을 다시 보정하거나 누락 업종을 채우지 않습니다.</li></ol></div><p class="small">보정은 상대적인 비중을 바탕으로 사용 가능한 배분표를 만드는 계산입니다. AI의 원시 계산 오류를 없던 것으로 만들거나, 설명·인용의 정확성을 고쳐 주는 절차가 아닙니다. 보정 후에는 원시값과 다른 증감 방향이 나타날 수도 있습니다.</p></section>
<section><h2>업종별 최종 배분</h2><p>각 열은 F0 최종 답변을 보정한 배분입니다. 값은 전체 자금 대비 비중이며, 산출 가능한 열의 합계는 정확히 100.00%입니다.</p><div class="table-scroll"><table id="final-allocations"><thead><tr><th>업종</th>{''.join('<th class="number">'+escape(LABELS[c])+'</th>' for c in CASES)}</tr></thead><tbody>{''.join(allocations)}</tbody><tfoot><tr><th>합계</th>{''.join('<td class="number">'+v+'</td>' for v in totals)}</tr></tfoot></table></div></section>
<section><h2>배분이 얼마나 달랐나요?</h2><p><strong>‘전체 자금 중 다시 옮겨야 할 비중’</strong>은 한 배분을 다른 배분과 같게 만들기 위해 업종 사이에 재배분해야 할 최소 비중입니다. 두 정수 배분 사이의 총변동거리(TV)에 100을 곱했습니다. 0%면 두 배분이 같습니다. 이 값은 수익률·설명 정확도·기관자료 반영 성공률이 아닙니다.</p>
<h3>같은 기관자료: 처음부터 제공 vs 초안 뒤 제공</h3><p class="small">서로 다른 두 조건의 <strong>최종(F0) 대 최종(F0)</strong> 배분을 비교합니다.</p>{comparison_table(groups['within_source'])}
<h3>같은 조건 안에서: 초안에서 최종 답변으로</h3><p class="small">각 조건의 <strong>자기 최종(F0) 대 자기 초안(D0)</strong> 보정 배분을 비교합니다. 위의 조건 간 비교와는 다른 질문입니다.</p>{comparison_table(groups['own_D0_F0'])}
<details><summary>기관 간 비교와 기관자료 없는 조건과의 비교</summary><h3>제공 방식이 같은 두 기관자료 조건</h3>{comparison_table(groups['between_source'])}<h3>기관자료 없는 조건과의 차이</h3>{comparison_table(groups['shared_control'])}</details></section>
<section><h2>해석할 때 함께 볼 점</h2><ul><li>기관 간 비중 차이가 크거나 작다는 사실만으로 기관자료 반영의 성공·실패를 판정할 수 없습니다. 실제 설명, 인용 문장, 수치·단위·시점에 대한 감사 결과를 함께 읽어야 합니다.</li><li>다섯 조건은 반복 실험의 평균이 아닙니다. 운영 중단과 재개가 있었고, 일부 결과를 본 뒤 현재 조건을 주된 탐색적 분석으로 삼는 결정과 100% 배분 후처리가 추가되었습니다.</li><li>공개 문서와 제공된 시장자료 안에서 나타난 사례 차이입니다. 실제 기관의 포트폴리오, 미래 성과, 투자 권고 또는 일반적인 인과효과로 확대하지 않습니다.</li>{extra_caveats}</ul></section>
<footer><h2>근거 파일</h2><p class="small">이 HTML은 외부 화면 자원 없이 열립니다. 아래 근거 링크는 함께 보관된 파일을 가리킵니다.</p><ul>{links}</ul>{provenance_html}</footer>
</main></body></html>"""


def generate(results_path, notes_path, output):
    results_path, notes_path, output = map(workspace_path, (results_path, notes_path, output))
    require(output.is_relative_to(REPORT_ROOT) and output.suffix.lower() == ".html", "New HTML must be inside remaining report tree")
    require(output not in (results_path, notes_path), "Inputs cannot be output")
    if output.exists():
        raise FileExistsError("Report already exists; choose a new name")
    result, result_bytes = load(results_path)
    notes, note_bytes = load(notes_path)
    notes_validated(notes)
    references = [("통합 배분 결과(JSON)", results_path), ("관찰 요약·주의점(JSON)", notes_path)]
    for item in notes["related_files"]:
        target = workspace_path(item["path"])
        require(target.is_file(), "Related file does not exist: " + item["path"])
        references.append((item["label"], target))
    links = [(name, quote(os.path.relpath(target, output.parent).replace("\\", "/"), safe="/")) for name, target in references]
    provenance = {"생성 시각(KST)": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds"),
        "통합 결과 SHA256": hashlib.sha256(result_bytes).hexdigest(),
        "관찰 메모 SHA256": hashlib.sha256(note_bytes).hexdigest(),
        "보고서 생성기 SHA256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    encoded = render_html(result, notes, related_links=links, provenance=provenance).encode("utf-8")
    require(results_path.read_bytes() == result_bytes and notes_path.read_bytes() == note_bytes, "Input changed during report rendering")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as handle:
        handle.write(encoded)
    return {"status": "created", "output": str(output), "sha256": hashlib.sha256(encoded).hexdigest(),
            "model_calls": 0, "service_calls": 0, "raw_files_read": 0, "inputs_modified": False}


def self_test():
    """One tiny synthetic dataset; validate displayed units, TV and escaping."""
    import re
    from tempfile import TemporaryDirectory
    records, units = [], {}
    for case in CASES:
        for stage in ("D0", "F0"):
            vector = dict(zip(CODES, [910] + [909] * 10))
            if case == CASES[0] and stage == "F0":
                vector[CODES[0]] += 100
                vector[CODES[1]] -= 100
            units[(case, stage)] = vector
            records.append({"case_id": case, "stage": stage, "status": "finalized", "version": "sector_allocation_finalizer_1",
                "policy": {"normalization": "positive_sum_proportional_scaling", "rounding": "largest_remainder_to_10000_integer_units"},
                "raw_sum_exact_decimal": "0.95" if stage == "D0" else "0.88", "final_total_units": 10000,
                "rows": [{"sector_code": code, "final_units": value} for code, value in vector.items()]})
    groups = {}
    for name, pairs in comparison_pairs().items():
        groups[name] = []
        for left, right in pairs:
            lv, rv = units[tuple(left.rsplit(":", 1))], units[tuple(right.rsplit(":", 1))]
            delta = {code: lv[code] - rv[code] for code in CODES}
            distance = Fraction(sum(abs(value) for value in delta.values()), 20000)
            groups[name].append({"left": left, "right": right, "status": "computed",
                "total_variation_exact": {"numerator": str(distance.numerator), "denominator": str(distance.denominator)},
                "final_unit_differences": delta})
    result = {"version": "sector_remaining_finalizer_1", "purpose": "primary_exploratory_remaining_dataset", "analysis_role": "primary_exploratory",
              "case_order": list(CASES), "planned_final_allocations": 5, "planned_final_sector_rows": 55, "logical_stage_slots": 10,
              "generation_calls": 0, "service_calls": 0, "main_model_calls": 0, "all_generation_requests_including_interrupted_attempt": 11,
              "primary_final_allocation_endpoint": "F0_derived_integer_allocation", "raw_diagnostics_required": True,
              "stage_records": records, "derived_comparisons": groups, "finalized_finals": 5}
    notes = {"schema_version": "plain_results_notes_1", "observations": [{"title": "<script>alert(1)</script>", "text": "합성 & 검증"}],
             "caveats": [], "related_files": []}
    html = render_html(result, notes)
    displayed = re.findall(r"data-case='([^']+)' data-units='([0-9]+)'", html)
    assert len(displayed) == 55 and all(sum(int(n) for c, n in displayed if c == case) == 10000 for case in CASES)
    assert "95%" in html and "88%" in html and "100.00%" in html
    assert "1.00%" in comparison_table(groups["within_source"])
    assert "<script>" not in html and "&lt;script&gt;" in html and "합성 &amp; 검증" in html
    bad = {**notes, "related_files": [{"label": "x", "path": "javascript:alert(1)"}]}
    try:
        notes_validated(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("Unsafe link accepted")
    with TemporaryDirectory(prefix="plain-results-synthetic-", dir=REPORT_ROOT) as folder:
        base = Path(folder)
        rp, np, out = base / "result.json", base / "notes.json", base / "report.html"
        rp.write_text(json.dumps(result), encoding="utf-8"); np.write_text(json.dumps(notes), encoding="utf-8")
        generate(rp, np, out)
        before = out.read_bytes()
        try:
            generate(rp, np, out)
        except FileExistsError:
            pass
        else:
            raise AssertionError("Existing report overwritten")
        assert out.read_bytes() == before
    return {"status": "PASS", "synthetic_fixtures": 1, "displayed_final_cells": len(displayed),
            "five_column_sums_units": [10000] * 5, "escaping_verified": True,
            "unsafe_link_rejected": True, "exclusive_output_verified": True, "nonzero_TV_percent_verified": True,
            "actual_results_read": False, "model_calls": 0, "service_calls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path)
    parser.add_argument("--notes", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result = self_test()
    else:
        if not all((args.results, args.notes, args.output)):
            parser.error("--results --notes --output are required; actual generation is root-only after terminal finalization")
        result = generate(args.results, args.notes, args.output)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
