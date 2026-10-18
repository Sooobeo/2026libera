"""Build a separate author-AI stage3 trace note from completed stored artifacts.

Manual observations below are review notes, not an automatic semantic scorer.
No C0 files, network endpoint, model, or online artifact are read or changed.
"""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASE = "fidelity_q2_2026__R1"
RUN = ROOT / "data/local_sector_runtime/pilot_v48_20261018" / CASE
PREPARED = ROOT / "data/sector_protocol/v48_pilot_r2_20261018"
OUTPUT = ROOT / "research/evaluator_only/v48_stage3_trace_notes_20261018.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def ref(path):
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    if OUTPUT.exists():
        raise FileExistsError("Preserve existing observations; choose a new version")
    records = {stage: read(RUN / stage / "record.json") for stage in ("stage1", "stage2", "stage3")}
    record = records["stage3"]
    assert record["response_complete"] is True and record["transport_status"] == "completed"
    parsed = record["parsed_response"]
    market_path = PREPARED / "market_input.json"
    registry_path = PREPARED / "public_numeric_registry.json"
    packet_path = PREPARED / "packets/fidelity_q2_2026.json"
    market, registry, packet = map(read, (market_path, registry_path, packet_path))
    rows = {row["sector_code"]: (i, row) for i, row in enumerate(parsed["weights"])}
    facts = {row["fact_id"]: (i, row) for i, row in enumerate(registry["rows"])}
    passages = {row["evidence_id"]: (i, row) for i, row in enumerate(packet["evidence_passages"])}

    def quote(code):
        i, row = rows[code]
        return {"response_locator": f"/parsed_response/weights/{i}/rationale", "model_quote": row["rationale"],
                "raw_weight": row["weight"], "listed_evidence_ids": row["evidence_ids"]}

    def source(code):
        i, passage = passages["fidelity_q2_2026:p3:sector:" + code]
        return {**ref(packet_path), "locator": f"/evidence_passages/{i}", **passage}

    def fact(name, code):
        i, row = facts["M:" + name + ":" + code]
        return {**ref(registry_path), "locator": f"/rows/{i}", **row}

    literal = json.loads(record["raw_response_text"], parse_float=Decimal)
    total = sum((row["weight"] for row in literal["weights"]), Decimal(0))
    assert total == Decimal("1.035")
    feedback = record["feedback"]
    assert feedback["allocation"]["valid"] is False and feedback["valid_portfolio_risk"] is None
    observations = [
        {"id": "stage3_budget_claim_disagrees_with_literal_weights",
         "response_locator": "/parsed_response/risk_discussion", "model_quote": parsed["risk_discussion"],
         "decimal_raw_sum": str(total), "decimal_signed_budget_residual": str(total - Decimal(1)),
         "feedback_locator": "/feedback/allocation", "feedback_as_recorded": feedback["allocation"],
         "author_assessment": "원비중의 정확한 십진 합계는 1.035(103.5%)인데 설명은 합계 1.000이라고 한다. 전체 벡터의 예산 제약은 실패했다. 계산기는 원비중을 그대로 보존하고 포트폴리오 위험을 산출하지 않았다.",
         "topic_connection": "판단을 말로 설명하는 능력과 실행 가능한 배분을 제출하는 능력을 구별한다. 설명은 별도 검토할 수 있으나 정상 배분쌍의 거리·위험 성과로 바꾸어 해석하지 않는다."},
        {"id": "energy_capital_spending_reason_migrates_from_materials", **quote("10"),
         "source_evidence": [source("10"), source("15")],
         "author_assessment": "Energy의 이유에 capital spending concerns를 넣었지만 제공된 해당 근거는 Materials 문장에 있다. Energy 제공 문장은 unfavorable risk-return indicators까지만 명시한다. 이는 제공 패킷 안의 산업 간 근거 이동 관측이며, 원본 PDF 전체에 Energy 관련 자본지출 논의가 절대 없다는 주장으로 확대하지 않는다.",
         "topic_connection": "원문 등급을 유지해도 다른 산업의 이유가 배분 근거로 섞일 수 있으므로 출처→이유→행동 연결을 직접 검토해야 한다."},
        {"id": "energy_and_IT_numeric_misstatements_persist_into_actions",
         "model_claims": [quote("10"), quote("45")],
         "numeric_evidence": [fact("annualized_volatility_diagnostic", "10"), fact("daily_mean_return", "10"),
                              fact("annualized_volatility_diagnostic", "45")],
         "author_assessment": "Energy 연율 변동성은 약 0.24628인데 0.1551이라고 하고, 일평균 수익률은 양수 0.0008187인데 -0.00030이라고 한다. IT 연율 변동성은 약 0.33685인데 0.2122라고 한다. 초기 위험 설명의 잘못된 수치가 단계3 배분 이유에도 나타난다. 보이는 M 식별자를 적었다는 사실만으로 값·단위·대상이 뒷받침되지는 않는다.",
         "limits": "초기 계산기는 weights=[]에 대해 포트폴리오 사실을 제공하지 않았다. 서술 통계 오류 수정이 주입된 적이 없으므로 이를 피드백 무시나 특정 인지기제의 인과증거로 부르지 않는다."},
        {"id": "consumer_sector_mean_signs_crossed",
         "model_claims": [quote("25"), quote("30")],
         "numeric_evidence": [fact("daily_mean_return", "25"), fact("daily_mean_return", "30")],
         "author_assessment": "경기소비재25는 실제 음수 -0.0002551인데 양수 0.00085를 근거로 비중 확대를 설명한다. 필수소비재30은 실제 양수 0.0008473인데 음수 -0.00026을 근거로 축소를 설명한다. 표기 수치가 서로 다른 산업의 실제 값과 반올림 수준에서 대응하지만 내부적으로 값을 교환했다는 생성 기제까지 입증하는 것은 아니다.",
         "topic_connection": "출처의 확대·축소 방향을 따르더라도 공통 자료를 잘못 인용해 그 선택을 정당화할 수 있다. 방향 일치와 근거 충실성은 별도다."},
        {"id": "healthcare_lowest_volatility_claim_uses_other_sector_value", **quote("35"),
         "numeric_evidence": [fact("annualized_volatility_diagnostic", "35"), fact("annualized_volatility_diagnostic", "40")],
         "author_assessment": "건강관리35의 실제 연율 변동성은 약 0.18338이다. 제시한 최저 0.1327은 금융40의 값 약 0.13272에 가깝고, 실제 최저 산업도 금융40이다. 제공 대상·단위·기간에 맞는 사실인지 확인해야 한다.",
         "limits": "Neutral이 수치상 정확히 기준비중이라는 정답을 만들지 않는다. 0.095가 기준 0.089089에 가깝다는 말의 허용범위는 사전 기준이 없으므로 이 기록에서 새 문턱을 정하지 않는다."},
        {"id": "industrial_source_reason_and_raw_direction_have_support", **quote("20"),
         "source_evidence": [source("20")], "numeric_evidence": [fact("baseline_weights", "20")],
         "author_assessment": "산업재의 favorable forward-looking valuations라는 이유는 제공된 원문 요약과 연결되며 원비중 0.105도 공통 기준 0.088088보다 높다. 이 좌표에서 공개 전망→확대 이유→확대 방향의 연결은 읽을 수 있다. 원문의 정량 목표비중은 없으므로 10.5%라는 크기의 정답성이나 최적성까지 지지하는 것은 아니다.",
         "limits": "전체 합계가 103.5%인 부적합 벡터의 한 좌표를 읽은 것이다. 유효 포트폴리오 또는 기관의 실제 보유자산을 관측한 것으로 취급하지 않는다."},
        {"id": "actual_alternatives_now_present_but_ambiguous_and_unverified",
         "response_locator": "/parsed_response/alternatives", "model_quote": parsed["alternatives"],
         "qualifier_locator": "/parsed_response/unresolved/1", "model_qualifier": parsed["unresolved"][1],
         "other_literal_claim": quote("60"),
         "author_assessment": "단계2의 선언만 있던 대안과 달리 단계3에는 두 조정 방향이 제시된다. 그러나 5%·2.5%가 비중의 상대 변화인지 퍼센트포인트인지 불명확하고 전체 대안 벡터도 없다. RE를 배분 이유에서는 low volatility, 대안에서는 high-volatility라고 부른다. 저자는 대안이 미검증이라는 응답 자체의 단서도 함께 보존한다.",
         "limits": "해석을 임의로 확정해 대안 포트폴리오를 구성하거나 위험·기대수익 개선을 인증하지 않는다. 제공된 과거 평균이 미래 기대수익을 확정하지도 않는다."},
        {"id": "source_identity_and_unstated_mandate_boundary",
         "source_id_literal": parsed["source_id"], "submitted_constraints_literal": parsed["submitted_constraints"],
         "unresolved_literal": parsed["unresolved"],
         "author_assessment": "Fidelity 이름과 11개 등급을 적으면서도 source_id는 null이고 기관 판단이 pending이라고 쓴다. 출처 식별과 문자 등급의 일치를 구분해 표시해야 한다. submitted_constraints는 빈 배열이므로 명시적인 새 기관 제약이나 정량 위험회피 계수를 꾸며 넣었다고 판정할 근거는 없다. mean reversion·growth at a reasonable price·value recovery는 모델이 덧붙인 해석 또는 목적 표현이며 실제 기관의 비공개 운용목적으로 승격하지 않는다.",
         "topic_connection": "공개 전망을 해석하는 과제와 기관의 전체 목적·제약을 복원하는 과제를 구별한다."},
    ]
    note = {"artifact_kind": "author_AI_preliminary_stage3_trace_review_not_primary_result",
            "case_id": CASE, "endpoint": "stage3", "recorded_at_utc": record["recorded_at_utc"],
            "reviewer_role": "author_AI_implementation_participant_not_independent_human",
            "independent_human_review_completed": False, "independent_human_judgment": None,
            "C0_reviewed": False, "primary_semantic_verdict": None, "numeric_composite_score": None,
            "observations": observations,
            "stage2_to_stage3_interpretations_identical": records["stage2"]["parsed_response"]["interpretations"] == parsed["interpretations"],
            "visible_calculator_facts_before_stage3": record["visible_calculator_facts_before_generation"],
            "feedback_status_after_stage3": feedback["status"],
            "feedback_can_become_visible_only_in_later_generation": True,
            "limits": ["Only this completed early-stage response is reviewed; no C0, repair or R1/R4 result is judged.",
                       "Source passages are researcher paraphrases with original labels; original-PDF validation and independent human review remain pending.",
                       "No human-judgment field is filled by this author-AI record; no new tolerance, scoring threshold or optimal institution weights are introduced.",
                       "These observations are not fed back to the live model. Online prompts, feedback and data remain frozen."],
            "model_calls_by_this_review": 0,
            "provenance": {"created_at_utc": datetime.now(timezone.utc).isoformat(),
                           "files": [ref(RUN / stage / "record.json") for stage in records] +
                                    [ref(path) for path in (packet_path, registry_path, market_path,
                                      ROOT / "research/evaluator_only/v48_preliminary_trace_notes_20261018.json", Path(__file__))]}}
    OUTPUT.write_text(json.dumps(note, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": ref(OUTPUT), "observations": len(observations), "C0_reviewed": False, "model_calls": 0}))


if __name__ == "__main__":
    main()
