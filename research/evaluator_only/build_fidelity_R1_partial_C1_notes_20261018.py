"""Preserve manually selected partial C1 quotes, never reconstruct its JSON."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "data/local_sector_runtime/pilot_v48_20261018/fidelity_q2_2026__R1"
OUT = ROOT / "research/evaluator_only/v48_fidelity_R1_partial_C1_observations_20261018.json"


def ref(path):
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    if OUT.exists():
        raise FileExistsError("Preserve previous partial-response observations")
    path = BASE / "C1/record.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    c0_path = BASE / "C0/record.json"
    c0 = json.loads(c0_path.read_text(encoding="utf-8"))
    raw = record["raw_response_text"]
    assert record["response_complete"] is False and record["transport_status"] == "hard_deadline"
    assert record["parsed_response"] is None and record["feedback"] is None

    def quote(literal):
        start = raw.index(literal)
        return {"model_quote": literal, "response_artifact": ref(path), "response_locator": "/raw_response_text",
                "unicode_codepoint_span": [start, start + len(literal)]}

    tail = '"sector_code": "45",\n      "weight": 0.380,\n      "rationale": "Overweight relative to baseline (0.380). R'
    assert raw.endswith(tail)
    unchanged_rationales = [row["rationale"] in raw for row in c0["parsed_response"]["weights"][:7]]
    assert all(unchanged_rationales)
    observations = [
        {"id": "partial_C1_contains_changed_IT_number_but_no_full_allocation", **quote(tail),
         "evidence_refs": [{**ref(c0_path), "locator": "/parsed_response/weights/7"}],
         "author_assessment": "마지막 잘린 IT 행에는 0.380이라는 원비중이 읽힌다. 완료 C0의 IT 비중 0.420과는 다르지만 이유 문장은 중간에 끊겼다. 이는 수정을 시도한 조각을 보존하는 관측이며 수정 완료를 뜻하지 않는다.",
         "limits": "전체 벡터·합계·위험값을 재구성하거나 결측 산업을 0으로 대체하지 않는다. 이 조각을 완결 C1이나 유효 원배분으로 인정하지 않고 C0를 대체하지 않는다."},
        {"id": "partial_C1_preserves_energy_reason_fragment", **quote(c0["parsed_response"]["weights"][0]["rationale"]),
         "evidence_refs": [{**ref(c0_path), "locator": "/parsed_response/weights/0/rationale"},
                           ref(ROOT / "research/evaluator_only/v48_fidelity_R1_C0_author_observations_20261018.json")],
         "author_assessment": "부분 C1에서도 Energy의 잘못된 음수 평균수익률과 자본지출 이유를 포함한 C0 문장이 그대로 읽힌다. 해당 문장에 관한 기존 출처·수치 대조를 연결하되 C1 전체의 전략 보존 판정을 만들지 않는다.",
         "limits": "표시된 문장 바깥의 이후 정정·미해결 설명이 있었을 것이라고 추정하지 않는다. 존재하지 않는 완결 설명을 보완하지 않는다."},
        {"id": "timeout_and_missing_structure_are_separate_from_primary_content", **quote('"source_id": null'),
         "evidence_refs": [{**ref(path), "locator": "/response_complete"},
                           {**ref(path), "locator": "/schema_validation"},
                           {**ref(path), "locator": "/transport_result"}],
         "author_assessment": "hard_deadline으로 종료된 읽을 수 있는 응답 조각이며 구조 검사에는 invalid_or_ambiguous_JSON이 남아 있다. 완료 응답의 원문 보존·형식·배분 조건과 부분 텍스트의 읽을 수 있음은 구분한다.",
         "limits": "완료 C0의 산술 오류를 지우지 않는다. 미완료 C1의 등급·원비중을 정상 완료 크레딧으로 올리지 않으며 시스템 무결성 사건의 유무도 모델의 투자판단 성공 판정으로 사용하지 않는다."}
    ]
    output = {"artifact_kind": "author_AI_auxiliary_partial_response_observations_not_primary_or_completed_C1",
              "case_id": "fidelity_q2_2026__R1", "endpoint": "C1", "response_complete": False,
              "transport_status": record["transport_status"], "recorded_at_utc": record["recorded_at_utc"],
              "reviewer_role": "author_AI_implementation_participant_not_independent_human",
              "independent_human_review_completed": False, "independent_human_judgment": None,
              "paper_observations": [], "auxiliary_partial_observations": observations,
              "earliest_seven_rationales_identical_to_C0_in_readable_text": unchanged_rationales,
              "full_C1_weights_reconstructed": False, "valid_allocation_credit": False,
              "C0_replaced": False, "C2_reviewed": False, "strategic_preservation_verdict": None,
              "provenance": {"created_at_utc": datetime.now(timezone.utc).isoformat(),
                             "files": [ref(path), ref(c0_path), ref(Path(__file__))]},
              "model_calls_by_review": 0, "online_artifacts_changed": False}
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": ref(OUT), "partial_observations": len(observations), "complete_C1_credit": False}))


if __name__ == "__main__":
    main()
