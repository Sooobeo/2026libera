"""Create a new blank source-review worksheet, never a completed gate/approval."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "research/evaluator_only/v48_main_source_review_template_20261018_v2.json"
RECEIPT = ROOT / "research/evidence/v48_main_gate_validation_20261018/blank_source_template_receipt_v2.json"
SOURCES = ("fidelity_q3_2026", "ubs_july_2026")
SECTORS = ("10", "15", "20", "25", "30", "35", "40", "45", "50", "55", "60")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def reference(path):
    return {"path": str(Path(path).resolve()), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}


def build(root=ROOT):
    old = read(root / "research/v48_review_template_20261018.json")
    manifest = read(root / "data/sector_documents/source_manifest.json")
    result = {
        "review_version": "v4.8-main-source-review-1",
        "artifact_kind": "blank_pre_execution_source_review_template_not_review_or_authorization",
        "review_status": "not_started", "completed_at_utc": None,
        "independent_human_review_completed": False,
        "candidate_manifest": {"path": None, "sha256": None},
        "candidate_status": "placeholder; no actual main candidate was created by this tool",
        "reviewer": {"reviewer_id": None, "reviewer_role": None, "name_or_model_identity": None,
                     "independence_from_response_generation": None, "source_familiarity_or_qualification": None},
        "pending": ["독립 사람 검토자가 원문·연구자 의역·정의·시점·비교가능성·해석 한계를 확인해야 합니다."],
        "instructions_ko": [
            "이 빈 서식을 보존하고 새 파일로 복사하여 작성하세요. 현재 값은 사람 판정이나 본실험 승인이 아닙니다.",
            "본실험 후보가 생성된 뒤 candidate_manifest와 각 packet의 실제 경로·SHA-256을 연결하세요. 원본 PDF 참조는 아래처럼 고정되어 있습니다.",
            "검토자의 실제 이름 또는 식별자, 역할, 독립성 선언, 검토 완료 시점을 직접 기록하세요. 역할 선언을 신원 인증이라고 해석하지 않습니다.",
            "산업별로 PDF의 실제 원문과 연구자 의역을 구분하여 적고, 원문의 페이지·표·행 위치 및 파일 해시를 남기세요.",
            "두 기관의 등급 척도와 기준일·대상 시장이 같은지 먼저 확인하세요. 등급 문구를 임의의 투자비중이나 기관의 실제 보유량으로 바꾸지 마세요.",
            "비교불가·불확실·자료부족도 정당한 완료 판단입니다. 긍정적인 차이 또는 보존 결론을 강제하지 않습니다.",
            "알려진 한계는 원문 그대로 보존하고 resolved, accepted_limitation, not_assessable 중 하나와 구체적인 이유를 기록하세요. 6/31/26을 임의로 6/30으로 고치지 마세요.",
            "모든 11개 산업과 양쪽 자료를 검토한 뒤 실제 완료된 항목만 completed로 바꾸세요. 미검토 항목을 pending에서 지운다고 검토가 완료되지는 않습니다.",
            "사전 원문검토는 향후 생성될 모델 응답의 의미 검토와 별개입니다. 이 파일은 본실험 실행 승인서가 아닙니다.",
        ],
        "allowed_relationships": old["allowed_states"]["inventory_relationship"],
        "source_materials": [], "source_difference_inventory": [],
        "model_calls_by_template_creation": 0, "human_judgments_created": 0,
    }
    for sid in SOURCES:
        source = next(s for s in manifest["sources"] if s["source_id"] == sid)
        pdf = root / source["cache"]["path"]
        if reference(pdf)["sha256"] != source["cache"]["sha256"]:
            raise ValueError("Pinned source PDF changed")
        result["source_materials"].append({"source_id": sid,
            "original_pdf": {key: source["cache"][key] for key in ("path", "sha256")},
            "packet": {"path": None, "sha256": None}, "review_status": "not_started", "review_notes": None,
            "source_url": source["url"], "recorded_dates_for_review_not_new_judgment": source["dates"],
            "known_source_issue_dispositions": [{"issue": issue, "disposition": None, "reason": None}
                for issue in source["known_source_issues"]]})
    for sector in SECTORS:
        row = copy.deepcopy(old["row_templates"]["source_difference_inventory"])
        row.update(inventory_id="main-source-" + sector, split="main", sector_code=sector,
                   source_A_id=SOURCES[0], source_B_id=SOURCES[1])
        row.update(source_A_researcher_paraphrase=None, source_B_researcher_paraphrase=None,
                   source_A_paraphrase_review={"status": None, "reason": None},
                   source_B_paraphrase_review={"status": None, "reason": None},
                   source_A_missing_material_reason=None, source_B_missing_material_reason=None)
        row["questions_ko"] = ["양쪽 PDF의 실제 원문은 무엇이며 어느 페이지·행에 있는가?",
            "연구자 의역이 원문의 범위·단서·불확실성을 바꾸었는가?",
            "등급의 정의와 시점·산업범위가 직접 비교 가능한가?",
            "이 차이 또는 공통점이 판단 이유와 산업 비중 선택의 연결을 해석하는 데 무엇을 알려 주는가?",
            "자료에서 알 수 없는 비공개 목적·제약·위험선호·실제보유와 미해결 한계는 무엇인가?"]
        result["source_difference_inventory"].append(row)
    return result


def main():
    if DESTINATION.exists() or RECEIPT.exists():
        raise FileExistsError("Preserve existing worksheet and receipt")
    inputs = [reference(ROOT / "research/v48_review_template_20261018.json"),
              reference(ROOT / "data/sector_documents/source_manifest.json")]
    result = build()
    rows = result["source_difference_inventory"]
    checks = {
        "exact_11_main_sectors": len(rows) == 11 and {r["sector_code"] for r in rows} == set(SECTORS),
        "both_source_materials_present": [r["source_id"] for r in result["source_materials"]] == list(SOURCES),
        "all_judgments_unfilled": all(r[k] is None for r in rows for k in
            ("source_A_literal_judgment", "source_B_literal_judgment", "relationship", "reviewer_id", "reviewer_role")),
        "all_paraphrase_checks_unfilled": all(r["source_" + side + "_paraphrase_review"] == {"status": None, "reason": None} for r in rows for side in ("A", "B")),
        "all_rows_not_started": all(r["review_status"] == "not_started" and r["independent_human_review_completed"] is False for r in rows),
        "candidate_binding_placeholder": result["candidate_manifest"] == {"path": None, "sha256": None},
        "known_issue_findings_unfilled": all(d["disposition"] is None and d["reason"] is None
            for s in result["source_materials"] for d in s["known_source_issue_dispositions"]),
        "independent_human_completion_false": result["independent_human_review_completed"] is False,
        "no_review_approval_or_calls_created": result["human_judgments_created"] == 0 and result["model_calls_by_template_creation"] == 0,
    }
    if not all(checks.values()):
        raise AssertionError(checks)
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    with DESTINATION.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    for item in inputs:
        if reference(item["path"]) != item:
            raise ValueError("Input changed while creating blank template")
    receipt = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "status": "blank_template_checks_passed",
        "checks": checks, "author_role": "assistant_self_review", "independent_human_review_completed": False,
        "inputs": inputs, "generator": reference(__file__), "output": reference(DESTINATION),
        "model_calls": 0, "main_approval_created": False,
        "topic_alignment": "Pre-source review distinguishes public judgment, paraphrase, definitions, dates and limits before examining future source-to-reason-to-action preservation."}
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    with RECEIPT.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(DESTINATION), "receipt": str(RECEIPT), "check_count": len(checks)}))


if __name__ == "__main__":
    main()
