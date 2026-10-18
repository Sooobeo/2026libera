"""Render evaluator-only Korean HTML; no inference, grading or model calls.

The packet places literal evidence beside captured reasoning and raw choices.
Unfilled human judgments remain unfilled; all C0 views precede auxiliary C1/C2.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
from html import escape
import json
import os
from pathlib import Path
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SECTOR_NAMES = {"10": "에너지", "15": "소재", "20": "산업재", "25": "경기소비재", "30": "필수소비재",
                "35": "헬스케어", "40": "금융", "45": "정보기술", "50": "커뮤니케이션 서비스", "55": "유틸리티", "60": "부동산"}
CSS = """
:root{--ink:#18212c;--muted:#586574;--line:#d9e0e6;--accent:#175b67;--paper:#fff;--bg:#f4f6f8}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.8 "Malgun Gothic","Apple SD Gothic Neo",sans-serif;word-break:keep-all;overflow-wrap:anywhere}
main{margin:28px auto 70px;padding:40px 42px;background:var(--paper);max-width:1440px}h1{font-size:30px;line-height:1.4;letter-spacing:-.03em}h2{font-size:24px;margin:36px 0 14px}h3{font-size:20px;margin:25px 0 12px}h4{font-size:16px;margin:0 0 10px}p{margin:8px 0 14px}a{color:var(--accent);text-underline-offset:3px}.eyebrow{font-size:12px;letter-spacing:.1em;font-weight:700;color:var(--accent)}.meta,.note{font-size:13px;color:var(--muted)}.callout{padding:16px 20px;background:#f2f7f8;border-left:4px solid var(--accent);margin:20px 0}.synthetic{background:#fff5dd;border-color:#a26c16}.pending{color:#7a531d}.tag{display:inline-block;padding:1px 8px;border:1px solid #bac9cf;font-size:12px;margin:0 8px 5px 0;color:#32515a}nav{display:flex;flex-wrap:wrap;gap:10px 18px;margin:24px 0}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid var(--line);padding:10px 12px;vertical-align:top;text-align:left}th{background:#eaf0f3}.case{border-top:2px solid var(--line);margin-top:30px;padding-top:12px}.sector{border:1px solid var(--line);margin:18px 0}.sector-title{padding:10px 14px;background:#f1f5f6;font-weight:700}.grid{display:grid;grid-template-columns:1fr 1fr 1.15fr}.cell{padding:14px;border-right:1px solid var(--line);min-width:0}.cell:last-child{border:0}.judgment{border-top:1px solid var(--line);padding:10px 14px;background:#fafbfc;font-size:13px}.literal{white-space:pre-wrap;word-break:normal;overflow-wrap:anywhere}.locator{font:12px/1.6 Consolas,monospace;color:var(--muted);margin-top:7px}code,pre{font:12px/1.7 Consolas,"Malgun Gothic",monospace}code{background:#f1f4f6;padding:1px 4px}pre{white-space:pre-wrap;word-break:break-word;background:#f5f7f9;padding:16px;max-height:600px;overflow:auto}.metrics{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}.metric{padding:10px 15px;background:#f4f7f8;border:1px solid var(--line)}.metric strong{display:block;font-size:20px}.metric small{color:var(--muted)}details{margin:14px 0}summary{cursor:pointer;color:var(--accent);font-weight:700}ul,ol{padding-left:24px}footer{margin-top:40px;padding-top:20px;border-top:1px solid var(--line);font-size:13px;color:var(--muted)}.links{display:flex;gap:10px;flex-wrap:wrap}section{scroll-margin-top:20px}.not-observed{padding:14px;background:#faf8f2;border-left:3px solid #a1884e}
@media(max-width:900px){main{padding:24px 18px;margin:0}.grid{grid-template-columns:1fr}.cell{border-right:0;border-bottom:1px solid var(--line)}h1{font-size:25px}.metric strong{font-size:18px}}
@media print{@page{size:A4;margin:14mm}body{background:#fff;font-size:9pt}main{margin:0;padding:0;max-width:none}nav,.screen-only{display:none}h1{font-size:21pt}h2{font-size:16pt}.grid{grid-template-columns:1fr 1fr 1.15fr}.sector{break-inside:avoid}.case{break-before:page}pre{max-height:none}a{color:inherit}.locator{font-size:7pt}}
"""


def text(value, missing="미기록"):
    return escape(missing if value is None else str(value))


def local_link(path, label, output_path):
    if not path:
        return text(label) + " <span class=note>(파일 없음)</span>"
    target = Path(path)
    if not target.is_absolute():
        target = ROOT / target
    target = target.resolve()
    try:
        relative = Path(os.path.relpath(target, Path(output_path).resolve().parent)).as_posix()
        url = quote(relative, safe="/:")
    except ValueError:
        url = target.as_uri()
    return '<a href="' + escape(url, quote=True) + '">' + escape(label) + '</a>'


def source_link(url, label):
    if not isinstance(url, str) or urlsplit(url).scheme not in ("https", "http"):
        return escape(label) + " <span class=note>(공식 링크 미기록)</span>"
    return '<a href="' + escape(url, quote=True) + '" target="_blank" rel="noopener noreferrer">' + escape(label) + '</a>'


def weight(value):
    if value is None:
        return "미기록·계산 불가"
    try:
        decimal = Decimal(str(value))
        if not decimal.is_finite():
            raise InvalidOperation
        percent = format(decimal * 100, "f")
        if "." in percent:
            percent = percent.rstrip("0").rstrip(".")
        return '<code>' + text(value) + '</code> <span class="note">(' + escape(percent) + '%)</span>'
    except (InvalidOperation, ValueError):
        return text(value)


def pending(value):
    return '<span class="pending">독립 사람 검토 전 · 미판정</span>' if value is None else '<span class="pending">기록된 판정: ' + text(value) + '</span>'


def literal(value, location=None):
    content = '<div class="literal">' + text(value, "내용 없음 · 누락 또는 해당 단계 미도달") + '</div>'
    if location:
        content += '<div class="locator">' + text(location) + '</div>'
    return content


def _material_index(worksheet):
    return {(item["case_id"], item["endpoint"]): item for item in worksheet.get("workflow_trace_materials", [])}


def _row_block(row, record_ref, output_path):
    code = row["sector_code"]
    passages = row.get("source_passages", [])
    source_html = '<p>출처 등급: <strong>' + text(row.get("source_literal_rating")) + '</strong></p>'
    for passage in passages:
        source_html += literal(passage.get("text"), passage.get("evidence_id"))
        if passage.get("source_page") is not None:
            source_html += '<div class="note">출처 ' + text(passage["source_page"]) + '쪽</div>'
    if not passages:
        source_html += '<p class="note">행에 연결된 발췌문 없음. 출처 전체 맥락을 확인해야 합니다.</p>'
    source_html += '<p class="note">별도 이유 제공: ' + ("있음" if row.get("source_separate_reason_available") is True else "없음 또는 별도 미기록") + '</p>'
    interpretation = '<p>AI가 적은 등급: <strong>' + text(row.get("model_literal_rating")) + '</strong></p>'
    irows = row.get("interpretation_occurrences", [])
    wrows = row.get("weight_occurrences", [])
    if len(irows) == 1:
        interpretation += literal(row.get("interpretation_reason_literal"), f"/interpretations/{irows[0][0]}/reason")
    elif irows:
        interpretation += '<p class="note">중복 행 · 하나를 임의 선택하지 않았습니다.</p>'
        for index, item in irows:
            interpretation += literal(item.get("reason"), f"/interpretations/{index}/reason")
    else:
        interpretation += literal(None)
    interpretation += '<p class="note">등급 문자열 진단: ' + ("일치" if row.get("exact_label_correct") is True else "완료된 해당 응답에서 일치 확인 안 됨") + ' · 전략 보존 판정과 별개</p>'
    allocation = '<p>원비중: ' + weight(row.get("raw_weight")) + '</p>'
    allocation += '<p class="note">공통 기준비중: ' + weight(row.get("raw_baseline_weight")) + '<br>원비중 − 기준비중: <code>' + text(row.get("raw_active_weight_decimal"), "계산 불가") + '</code></p>'
    if len(wrows) == 1:
        allocation += literal(row.get("allocation_rationale_literal"), f"/weights/{wrows[0][0]}/rationale")
    elif wrows:
        allocation += '<p class="note">중복 비중 행 · 유효한 단일 비중으로 해석하지 않습니다.</p>'
        for index, item in wrows:
            allocation += literal(item.get("rationale"), f"/weights/{index}/rationale")
    else:
        allocation += literal(None)
    allocation += '<p class="note">이 행의 숫자는 모델의 선택입니다. 출처가 제시한 정답 비중이 아닙니다.</p>'
    citations = {"interpretation_citations": row.get("interpretation_citations"), "allocation_citations": row.get("allocation_citations")}
    block = '<article class="sector"><div class="sector-title">' + text(code) + ' · ' + text(SECTOR_NAMES.get(code, code)) + '</div>'
    block += '<div class="grid"><div class="cell"><h4>① 출처가 말한 판단과 이유</h4>' + source_html + '</div>'
    block += '<div class="cell"><h4>② AI가 해석한 내용</h4>' + interpretation + '</div>'
    block += '<div class="cell"><h4>③ 실제 선택과 선택 이유</h4>' + allocation + '</div></div>'
    block += '<div class="judgment">판단 채택·유보·이탈의 실제 의미: ' + pending(row.get("literal_stance")) + '<br>근거가 설명을 지지하는가: ' + pending(row.get("claim_support"))
    block += '<br>설명한 방향과 실제 비중이 맞는가: ' + pending(row.get("action_consistency")) + '<br>출처 판단 → 선택 연결: ' + pending(row.get("source_to_action_assessment_status"))
    block += '<details><summary>인용 ID 확인 기록 · 의미의 참/거짓 판정 아님</summary><pre>' + escape(json.dumps(citations, ensure_ascii=False, indent=2)) + '</pre></details>'
    if record_ref:
        block += local_link(record_ref.get("path"), "이 응답의 원기록", output_path)
    return block + '</div></article>'


def _case_block(review, materials, output_path):
    identifier, endpoint = review["case_id"], review["endpoint"]
    key = identifier + "-" + endpoint
    execution = review["execution"]
    context = review.get("source_material_context", {})
    material = materials.get((identifier, endpoint), {})
    valid = execution.get("valid_raw_allocation") is True
    content = '<article class="case" id="' + escape(key, quote=True) + '"><h3>' + text(identifier) + ' · ' + text(endpoint) + '</h3>'
    content += '<p><span class="tag">' + ("주결과 · 최초 최종안" if endpoint == "C0" else "보조 결과 · 사후 산술 수정") + '</span><span class="tag">' + text(review["arm"]) + '</span></p>'
    content += '<p>' + source_link(context.get("source_url"), context.get("title") or review["source_id"]) + '<br><span class="note">' + text(context.get("issuer")) + '</span></p>'
    content += '<div class="metrics"><div class="metric"><small>원비중 합계</small><strong>' + weight(execution.get("raw_sum")) + '</strong></div>'
    content += '<div class="metric"><small>합계 − 1</small><strong>' + text(execution.get("signed_budget_residual"), "계산 불가") + '</strong></div>'
    content += '<div class="metric"><small>배분 유효성</small><strong>' + ("유효한 원배분" if valid else "유효 배분 미확인") + '</strong></div></div>'
    content += '<p class="note">완료 응답: ' + ("있음" if execution.get("transport_completed") else "없음") + ' · 형식: ' + text(execution.get("contract_status")) + ' · 실행 상태: ' + text(execution.get("transport_status")) + '</p>'
    if not valid:
        content += '<p class="not-observed">이 응답은 유효한 포트폴리오 거리·위험 비교에 넣지 않습니다. 남아 있는 출처 해석과 선택 이유는 아래에서 별도로 검토합니다. 실패가 기관 판단 보존을 자동으로 부정하거나 입증하지는 않습니다.</p>'
    record_ref = material.get("record_ref")
    content += '<div class="links">' + local_link((record_ref or {}).get("path"), "원응답·요청·검증 기록", output_path)
    content += ' ' + local_link((material.get("request_ref") or {}).get("path"), "실제 요청", output_path) + '</div>'
    content += '<details><summary>출처 전체 맥락·기간·등급 정의 확인</summary><p class="note">공개 리서치의 견해입니다. 실제 보유비중, 법적 제약이나 비공개 투자 목적과 같다고 가정하지 않습니다.</p>'
    content += '<pre>' + escape(json.dumps({key: context.get(key) for key in ("dates", "task_scope", "rating_vocabulary")}, ensure_ascii=False, indent=2)) + '</pre>'
    for passage in context.get("evidence_passages") or []:
        content += literal(passage.get("text"), passage.get("evidence_id"))
    content += '</details>'
    for row in review.get("sector_reviews", []):
        content += _row_block(row, record_ref, output_path)
    cross = [item for item in review.get("literal_fields_for_manual_claim_review", []) if item.get("sector_code") is None]
    if cross:
        content += '<details open><summary>대안·위험·미해결 사항 · 수치 주장 사람이 확인할 원문</summary>'
        for item in cross:
            content += literal(item.get("literal_text"), item.get("response_field_and_span"))
        content += '<p class="note">수치를 검토할 때 대상·지표·값·단위·기간·출처 ID·자료 버전과 해당 후보의 계보를 함께 적습니다. 같은 숫자만 발견했다고 근거가 확인된 것은 아닙니다.</p></details>'
    return content + '</article>'


def render_packet(report, worksheet, *, report_path, worksheet_path, output_path, synthetic=False):
    if report.get("scope") != "pilot_only_offline_analysis" or worksheet.get("artifact_kind") != "unfilled_evaluator_only_semantic_review_worksheet":
        raise ValueError("Expected the v4.8 pilot report and unfilled offline worksheet")
    if report.get("provenance") != worksheet.get("provenance"):
        raise ValueError("Report and worksheet provenance differ")
    primary = worksheet.get("primary_C0_reviews", [])
    auxiliary = worksheet.get("auxiliary_reviews", [])
    if any(item.get("endpoint") != "C0" for item in primary) or any(item.get("endpoint") not in ("C1", "C2") for item in auxiliary):
        raise ValueError("Primary and auxiliary endpoint collections must remain separate")
    bundle = report["primary_C0_bundle"]
    materials = _material_index(worksheet)
    title = "LIBERA v4.8 · 기관 판단과 AI 선택 연결 검토지"
    html = '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + title + '</title><style>' + CSS + '</style></head><body><main>'
    html += '<header><div class="eyebrow">LIBERA 2026 · OFFLINE REVIEW · V4.8</div><h1>기관의 판단은 AI의 설명과 산업 비중에 남았는가?</h1><p>출처 → AI 해석 → 선택 이유 → 실제 원비중을 나란히 읽는 사람 검토 자료</p>'
    if synthetic:
        html += '<div class="callout synthetic"><strong>합성 데이터 화면 점검용 · 실제 모델·실험 결과 아님</strong><p>아래 값과 문장은 렌더러 검증을 위한 시험 자료입니다. 연구 결과로 인용하지 않습니다.</p></div>'
    html += '<div class="callout"><strong>독립 사람 검토 전 · 전략 보존 결론 미판정</strong><p>프로그램은 실행·형식·산술·정확한 등급 문자열을 확인합니다. 근거의 의미와 의사결정의 연결은 아래 원문을 보고 별도로 판단해야 합니다. 세 차례 AI 자체 검증은 독립 사람 검토를 대신하지 않습니다.</p></div>'
    html += '<nav><a href="#reading">검토 순서</a><a href="#accounting">전체 사례와 실패 분모</a><a href="#primary">C0 주결과</a><a href="#auxiliary">C1/C2 보조 결과</a><a href="#trace">앞 단계 원문</a></nav>'
    html += '<div class="links">' + local_link(report_path, "평가 보고서 JSON", output_path) + ' ' + local_link(worksheet_path, "사람 검토지 JSON", output_path)
    html += ' ' + local_link(ROOT / "paper/LIBERA_텀페이퍼_초안_v4.8_20261018.html", "소논문 연구질문", output_path) + ' ' + local_link(ROOT / "research/evaluator_only/v48_source_comparison_20261018.json", "출처 비교 목록 · 사람 판정 전", output_path) + '</div></header>'
    html += '<section id="reading"><h2>논문과 연결하여 읽는 순서</h2><ol><li>출처가 어떤 판단과 이유를 말했는지, 두 문서의 견해가 실제로 비교 가능한지 확인합니다. Fidelity의 Overweight와 UBS의 Attractive를 같은 등급으로 바꾸지 않습니다.</li><li>AI가 그 판단을 정확히 이해했는지, 제공되지 않은 기관의 목적·위험성향·제약을 꾸며 내지 않았는지 확인합니다.</li><li>판단을 채택·유보하거나 다르게 선택한 이유를 읽고, 설명한 방향이 실제 원비중과 공통 기준비중의 차이에 반영되는지 확인합니다. 정당한 근거가 있는 이탈은 허용됩니다.</li><li>같은 출처의 R1과 R4를 비교합니다. 최초 자료 제공 위치와 이후 활용 기회가 함께 달라진 비교이며, 기억이나 앵커링만 따로 측정한 효과가 아닙니다.</li><li>출처 사이 배분이 비슷해졌다면 문서의 실제 유사성·차이와 이유를 함께 봅니다. 비슷한 비중만으로 유해한 획일화를 결론 내리지 않습니다.</li></ol><p class="note">사람 검토지에는 검토자·역할·독립성, 정확한 응답 위치, 출처와 판정 이유를 기입합니다. 이 HTML에는 사람이 완료한 판정을 새로 만들어 넣지 않습니다.</p></section>'
    html += '<section id="accounting"><h2>전체 사례와 실패 분모</h2><div class="metrics">'
    for label, value in (("계획 사례", bundle["planned_case_count"]), ("workflow 시도 사례", bundle["attempted_case_count"]), ("C0 시도 사례", bundle["C0_attempted_case_count"]), ("완료 C0 응답", bundle["completed_response_count"]), ("유효 C0 배분", bundle["valid_raw_allocation_count"])):
        html += '<div class="metric"><small>' + label + '</small><strong>' + text(value) + '</strong></div>'
    html += '</div><p>정확한 등급 문자열 보조 진단: ' + text(bundle["exact_label_correct_count"]) + ' / ' + text(bundle["expected_sector_count"]) + '개 산업행. 누락·중복·미완료 C0 때문에 분모를 줄이지 않습니다. 이 수치는 전략의 질이나 근거–행동 연결 점수가 아닙니다.</p>'
    html += '<div class="table-wrap"><table><thead><tr><th>사례</th><th>실행 결과</th><th>C0 유효 원배분</th><th>원문·의미 검토</th></tr></thead><tbody>'
    for row in bundle["case_accounting"]:
        html += '<tr><td><a href="#' + text(row["case_id"] + "-C0") + '">' + text(row["case_id"]) + '</a></td><td>' + text(row["outcome_category"]) + '<br><span class="note">' + text(row.get("workflow_status")) + '</span></td><td>' + ("있음" if row["valid_raw_allocation"] else "미확인") + '</td><td>독립 사람 검토 전</td></tr>'
    html += '</tbody></table></div><p>거리 비교 가능 쌍: 같은 출처 R1/R4 ' + text(bundle["eligible_within_source_pair_count"]) + ' / 2쌍, 같은 조건의 두 출처 ' + text(bundle["eligible_between_source_pair_count"]) + ' / 2쌍. 관측되지 않은 거리를 0으로 대체하지 않습니다.</p>'
    if report.get("system_integrity_incidents_present"):
        html += '<p class="not-observed">실행 환경·기록 무결성 사건이 보고되었습니다. 완성된 응답이 남아 있어도 실험 준비 완료 여부는 해당 사건을 별도로 검토해야 합니다.</p>'
    html += '</section><section id="primary"><h2>C0 · 최초 최종안이 주결과입니다</h2><p>네 단계 업무를 거친 첫 최종응답입니다. 사후 수정이 성공하더라도 아래 C0 기록을 바꾸지 않습니다.</p>'
    for review in primary:
        html += _case_block(review, materials, output_path)
    html += '</section><section id="auxiliary"><h2>C1/C2 · 별도로 읽는 사후 산술 수정</h2><p>동일한 수정 자격·중단 규칙에 따른 보조 진단입니다. 수정 후보를 새 독립 사례로 세거나 주결과와 섞지 않습니다.</p>'
    if not auxiliary:
        html += '<p class="not-observed">기록된 사후 수정 응답이 없습니다. 수정 미시도는 수정 실패와 별개입니다.</p>'
    for review in auxiliary:
        html += _case_block(review, materials, output_path)
    html += '</section><section id="trace"><h2>앞 단계 원문 · 판단이 바뀐 경로 확인</h2><p class="note">stage1–3은 C0 이전 과정입니다. 새로운 독립 표본이나 최종안으로 세지 않습니다. R4의 앞 단계에는 기관 문서가 아직 제공되지 않았습니다.</p>'
    for item in worksheet.get("workflow_trace_materials", []):
        if item["endpoint"] not in ("stage1", "stage2", "stage3") or not (item.get("record_ref") or item.get("attempted")):
            continue
        html += '<details><summary>' + text(item["case_id"]) + ' · ' + text(item["endpoint"]) + ' · ' + text(item.get("transport_status")) + '</summary><p class="note">기록 시각: ' + text(item.get("recorded_at_utc")) + '</p>'
        html += local_link((item.get("record_ref") or {}).get("path"), "이 단계 원기록", output_path)
        html += '<pre>' + text(item.get("raw_response_text"), "응답 텍스트 없음") + '</pre></details>'
    html += '</section><footer>독립 사람의 출처·의미 검토와 본실험은 이 렌더링으로 완료되지 않습니다. 해석 가능한 원문, 평가 불가능한 항목과 그 이유를 함께 남기십시오. 생성 시각: ' + text(report.get("created_at_utc")) + '</footer></main></body></html>'
    return html


def write_packet(report_path, worksheet_path, output_path, *, synthetic=False):
    report_path, worksheet_path, output_path = map(Path, (report_path, worksheet_path, output_path))
    if output_path.exists():
        raise FileExistsError("Use a new HTML output path; prior review packets are preserved")
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    worksheet = json.loads(worksheet_path.read_text(encoding="utf-8-sig"))
    html = render_packet(report, worksheet, report_path=report_path, worksheet_path=worksheet_path,
                         output_path=output_path, synthetic=synthetic)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path.resolve()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--worksheet", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--synthetic", action="store_true", help="Clearly mark a synthetic layout test; never use it as an empirical result")
    args = parser.parse_args(argv)
    output = write_packet(args.report, args.worksheet, args.output, synthetic=args.synthetic)
    print(json.dumps({"output": str(output), "model_calls": 0, "human_judgments_created": 0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
