"""Render a main-only, unfilled Korean review packet without executing a run.

Shared pure HTML fragments preserve literal source/reason/action columns. The
pilot renderer and its globals remain unchanged. Synthetic artifacts force an
explicit fixture banner; a zero-call evaluator is not a zero-call main run.
"""
from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path

from evaluate_sector_v48_main_artifacts import ROSTER, ROOT, verify_evaluator_material_refs
from evaluate_sector_v48_artifacts import read, reference, digest
from render_v48_review_packet import CSS, SECTOR_NAMES, text, local_link, _case_block, _material_index


def _validate(report, worksheet):
    if (report.get("scope") != "main_only_offline_analysis"
            or worksheet.get("artifact_kind") != "unfilled_main_evaluator_only_semantic_review_worksheet"):
        raise ValueError("Expected a main-only report and a distinct main worksheet")
    if report.get("provenance") != worksheet.get("provenance") or report.get("data_origin") != worksheet.get("data_origin"):
        raise ValueError("Main report and worksheet provenance differ")
    if report.get("evaluation_materials_verified") is not True:
        raise ValueError("Main review requires candidate-bound evaluator material verification")
    provenance = report["provenance"]
    materials = verify_evaluator_material_refs(provenance.get("evaluator_material_refs"),
                                               provenance["gold_annotations"]["path"])
    candidate_ref = provenance["prepared_manifest"]
    candidate_path = Path(candidate_ref["path"])
    if digest(candidate_path) != candidate_ref["sha256"]:
        raise ValueError("Candidate manifest changed since main evaluation")
    candidate_materials = verify_evaluator_material_refs(read(candidate_path).get("evaluator_material_refs"),
                                                         provenance["gold_annotations"]["path"])
    if materials != candidate_materials:
        raise ValueError("Report evaluator material references differ from the bound candidate")
    if report.get("independent_human_review_completed") is not False or worksheet.get("independent_human_review_completed") is not False:
        raise ValueError("This renderer is for unfilled response review, not completed human judgments")
    primary, auxiliary = worksheet.get("primary_C0_reviews", []), worksheet.get("auxiliary_reviews", [])
    expected = {case["case_id"] for case in ROSTER}
    if len(primary) != 4 or {x.get("case_id") for x in primary} != expected or any(x.get("endpoint") != "C0" for x in primary):
        raise ValueError("All four prescribed main C0 cases must remain represented")
    keys = [(x.get("case_id"), x.get("endpoint")) for x in auxiliary]
    if len(keys) != len(set(keys)) or any(c not in expected or e not in ("C1", "C2") for c, e in keys):
        raise ValueError("Main auxiliary endpoints must be unique and separate from C0")
    bundle = report["primary_C0_bundle"]
    if bundle.get("planned_case_count") != 4 or bundle.get("expected_sector_count") != 44:
        raise ValueError("The fixed main denominator is four cases and 44 sector rows")
    for review in primary + auxiliary:
        rows = review.get("sector_reviews", [])
        if len(rows) != 11 or {x["sector_code"] for x in rows} != set(SECTOR_NAMES):
            raise ValueError("Every reviewed main endpoint requires 11 preserved sector rows")
        if any(row.get(key) is not None for row in rows for key in
               ("literal_stance", "claim_support", "action_consistency", "source_to_action_assessment_status")):
            raise ValueError("This unfilled rendering cannot silently present completed semantic judgments")
    return primary, auxiliary


def _main_case(review, materials, output_path):
    # A presentation-only adapter for the shared fragment's older heading.
    # The pure evaluator requires source identity as well as literal labels.
    # No field value, judgment or scoring behavior is transformed here.
    fragment = _case_block(review, materials, output_path)
    return fragment.replace('<p class="note">등급 문자열 진단: ',
                            '<p class="note">출처 ID 포함 등급 진단: ')


def render_packet(report, worksheet, *, report_path, worksheet_path, output_path, synthetic=False):
    primary, auxiliary = _validate(report, worksheet)
    bundle, materials = report["primary_C0_bundle"], _material_index(worksheet)
    synthetic = synthetic or report.get("data_origin") == "synthetic_fixture_not_empirical"
    title = "LIBERA v4.8 · 본실험 응답 검토지"
    html = '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + title + '</title><style>' + CSS + '</style></head><body><main>'
    html += '<header><div class="eyebrow">LIBERA · MAIN ARTIFACT REVIEW · OFFLINE</div><h1>공개 판단은 설명과 실제 산업 비중에 연결되는가?</h1>'
    if synthetic:
        html += '<div class="callout synthetic"><strong>합성 자료 검증용 · 실제 본실험 결과 아님</strong><p>아래 요청 수·응답·비중은 시험 fixture에 기록된 값입니다. 실제 본실험 수행이나 연구 결과로 인용하지 않습니다.</p></div>'
    html += '<div class="callout"><strong>생성 후 응답의 독립 사람 의미 검토: 미작성</strong><p>입력 원문에 관한 사전 검토와 새 응답의 의미 검토는 서로 다른 절차입니다. 이 도구는 실행을 승인하거나 사람 판정을 만들지 않습니다. 출처 판단 → 해석 → 선택 이유 → 원비중을 대조할 자료를 제공합니다.</p></div>'
    html += '<div class="links">' + local_link(report_path, "본실험 오프라인 보고서", output_path) + ' ' + local_link(worksheet_path, "미작성 응답 검토지", output_path)
    html += ' ' + local_link(ROOT / "research/evaluator_only/v48_source_comparison_20261018_v2.html", "원문과 연구자 의역 비교", output_path) + '</div>'
    html += '<nav><a href="#accounting">전체 분모와 요청 기록</a><a href="#primary">C0 주결과</a><a href="#auxiliary">C1/C2 보조</a><a href="#trace">앞 단계</a></nav></header>'
    html += '<section><h2>연구질문에 연결하여 읽는 순서</h2><p>출처의 이유를 모델이 어떻게 해석했는지, 채택·유보·이탈을 설명한 이유가 실제 선택에 반영됐는지 확인합니다. 정당한 근거가 있는 이탈은 허용됩니다. 출처의 등급 표기나 합계만으로 전략 보존을 판정하지 않습니다.</p>'
    html += '<p>자료는 Fidelity Q3와 UBS July의 공개 전망입니다. 기관의 비공개 목표·위험선호·실제 보유 비중을 복원한 것으로 확대하지 않습니다. 두 등급 척도를 자동 등치하거나 Neutral을 정확한 기준비중으로 강제하지 않습니다. 연구자 의역은 원문 PDF에 대한 독립 검토와 구분합니다. 서로 다른 기준일과 Fidelity Q3의 잘못 인쇄된 날짜도 그대로 검토해야 합니다.</p></section>'
    html += '<section id="accounting"><h2>전체 네 사례와 44개 산업행</h2><div class="metrics">'
    counts = (("계획 사례", bundle["planned_case_count"]), ("업무 흐름 시도", bundle["attempted_case_count"]),
              ("C0 요청 사례", bundle["C0_attempted_case_count"]), ("완료 C0", bundle["completed_response_count"]),
              ("유효 C0 원배분", bundle["valid_raw_allocation_count"]),
              ("기록된 본실험 생성 요청", report["observed_main_generation_calls"]),
              ("이 평가기의 모델 호출", report["model_calls_by_this_evaluation"]))
    for label, value in counts:
        html += '<div class="metric"><small>' + label + '</small><strong>' + text(value) + '</strong></div>'
    html += '</div><p>기록된 요청은 핵심 단계 ' + text(report["observed_core_generation_calls"]) + '회, 보조 수정 ' + text(report["observed_auxiliary_generation_calls"]) + '회입니다. 이는 저장된 생성 요청 봉투의 수이며 성공 응답 수가 아닙니다. 평가기의 호출이 0이라는 사실을 본실험 요청이 0이라는 뜻으로 사용하지 않습니다.</p>'
    html += '<p>출처 ID 포함 등급 진단: ' + text(bundle["exact_label_correct_count"]) + ' / 44개 산업행. 해당 출처 ID와 등급 표기 및 완료 응답 조건을 함께 요구합니다. ID가 없으면 등급 문구가 같아도 이 엄격 진단은 0일 수 있습니다. 분모를 줄이거나 이를 의미·전략 점수로 바꾸지 않습니다.</p>'
    html += '<p>거리 계산 가능 쌍: 같은 문서의 R1/R4 ' + text(bundle["eligible_within_source_pair_count"]) + '/2, 같은 절차의 두 문서 ' + text(bundle["eligible_between_source_pair_count"]) + '/2. 무효·미완료 배분은 임의 정규화하지 않으며 미관측 거리를 0으로 바꾸지 않습니다.</p>'
    if report.get("artifact_issues") or report.get("system_integrity_incidents_present"):
        html += '<div class="not-observed">기록·실행 무결성 문제가 남아 있습니다. 아래 문장을 읽을 수 있다는 사실과 실행계약이 검증됐다는 판단은 구분해야 합니다.<pre>' + escape(json.dumps(report.get("artifact_issues", []), ensure_ascii=False, indent=2)) + '</pre></div>'
    html += '<details><summary>실행계약과 사전 사람 검토의 기록 · 이 도구가 새 승인하지 않음</summary><p>사전 원문 검토 상태(실행 요약의 기록): ' + text(report.get("pre_execution_human_source_review_as_recorded")) + '; 동결 상태(기록): ' + text(report.get("pre_execution_freeze_as_recorded")) + '.</p><p>후보 입력 manifest의 미승인 상태와 별도의 실행계약 snapshot은 다릅니다. 아래 참조가 있다는 것만으로 서명·사람 판단의 진실성을 자동 인증하지 않습니다.</p>'
    for name, item in report["provenance"].get("execution_snapshot_refs", {}).items():
        html += '<p>' + local_link((item or {}).get("path"), name, output_path) + '</p>'
    html += '</details></section><section id="primary"><h2>C0 · 최초 최종안</h2><p>모든 예정 사례를 표시합니다. 부적합 배분도 설명과 원문을 보존하며, 이후 수정 후보로 C0를 교체하지 않습니다.</p>'
    for review in primary:
        html += _main_case(review, materials, output_path)
    html += '</section><section id="auxiliary"><h2>C1/C2 · 별도 보조 수정</h2><p>추가 계산 기회를 가진 수정 응답입니다. C0와 합치거나 독립 사례로 세지 않습니다.</p>'
    if not auxiliary:
        html += '<p class="not-observed">기록된 보조 수정 응답이 없습니다. 미시도와 수정 실패는 구분합니다.</p>'
    for review in auxiliary:
        html += _main_case(review, materials, output_path)
    html += '</section><section id="trace"><h2>단계1–3의 과정 기록</h2><p>중간 단계는 최종 C0나 새로운 독립 표본이 아닙니다. R4에는 4단계에 기관 문서가 처음 제공됩니다.</p>'
    for material in worksheet.get("workflow_trace_materials", []):
        if material["endpoint"] not in ("stage1", "stage2", "stage3") or not (material.get("record_ref") or material.get("attempted")):
            continue
        html += '<details><summary>' + text(material["case_id"]) + ' · ' + text(material["endpoint"]) + '</summary><p>' + local_link((material.get("record_ref") or {}).get("path"), "원기록", output_path) + '</p><pre>' + text(material.get("raw_response_text"), "남은 응답 없음") + '</pre></details>'
    html += '</section><footer>이 HTML 생성은 본실험 승인·실행이나 독립 사람 의미 검토 완료가 아닙니다. 실제 자료와 합성 시험 자료를 구분하고, 원문·수치 주장·후보 계보·판정 이유를 함께 기록하십시오.</footer></main></body></html>'
    return html


def write_packet(report_path, worksheet_path, output_path, *, synthetic=False):
    report_path, worksheet_path, output_path = map(lambda x: Path(x).resolve(), (report_path, worksheet_path, output_path))
    if output_path.exists():
        raise FileExistsError("Preserve prior main review output")
    report, worksheet = read(report_path), read(worksheet_path)
    for name in ("prepared_manifest", "run_manifest_snapshot"):
        parent = Path(report["provenance"][name]["path"]).resolve().parent
        if output_path.is_relative_to(parent):
            raise ValueError("Main review HTML must be outside candidate and online directories")
    html = render_packet(report, worksheet, report_path=report_path, worksheet_path=worksheet_path,
                         output_path=output_path, synthetic=synthetic)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as handle:
        handle.write(html)
    return {"output": reference(output_path), "model_calls_by_this_render": 0,
            "observed_main_generation_calls": report["observed_main_generation_calls"],
            "human_judgments_created": 0, "main_execution_authorized_by_this_tool": False,
            "inputs": [reference(report_path), reference(worksheet_path)]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("report", "worksheet", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--synthetic", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(write_packet(args.report, args.worksheet, args.output, synthetic=args.synthetic), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
