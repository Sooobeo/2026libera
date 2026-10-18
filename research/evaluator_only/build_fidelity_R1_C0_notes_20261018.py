"""Record manually authored observations of the first completed C0 only.

No live workflow changes; no inference calls; no whole-pilot verdict. Reuses
literal source references from the preserved stage3 note only after checking
that the quoted C0 fields actually match. Human judgment fields stay null.
"""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASE = "fidelity_q2_2026__R1"
CASE_ROOT = ROOT / "data/local_sector_runtime/pilot_v48_20261018" / CASE
PREPARED = ROOT / "data/sector_protocol/v48_pilot_r2_20261018"
OUT = ROOT / "research/evaluator_only/v48_fidelity_R1_C0_author_observations_20261018.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def ref(path, locator=None):
    result = {"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    if locator is not None:
        result["locator"] = locator
    return result


def main():
    if OUT.exists():
        raise FileExistsError("Preserve existing observations")
    record_path = CASE_ROOT / "C0/record.json"
    prior_path = CASE_ROOT / "stage3/record.json"
    note_path = ROOT / "research/evaluator_only/v48_stage3_trace_notes_20261018.json"
    registry_path = PREPARED / "public_numeric_registry.json"
    packet_path = PREPARED / "packets/fidelity_q2_2026.json"
    record, prior, early, registry, packet = map(read, (record_path, prior_path, note_path, registry_path, packet_path))
    assert record["response_complete"] is True and record["transport_status"] == "completed"
    response_capture = CASE_ROOT / "C0/http_0001_generation/response.json"
    envelope = read(response_capture)
    assert envelope["done_reason"] == "stop" and envelope["message"]["content"] == record["raw_response_text"]
    current, previous = record["parsed_response"], prior["parsed_response"]
    identical = {key: current[key] == previous[key] for key in ("source_id", "interpretations", "weights", "alternatives", "unresolved", "submitted_constraints")}
    assert all(identical.values())
    literal = json.loads(record["raw_response_text"], parse_float=Decimal)
    total = sum((row["weight"] for row in literal["weights"]), Decimal(0))
    assert total == Decimal("1.035") and record["feedback"]["valid_portfolio_risk"] is None
    previous_sum = next((i, f) for i, f in enumerate(record["visible_calculator_facts_before_generation"])
                        if f["fact_id"] == "C:stage3:sum")
    assert previous_sum[1]["value"] == 1.035
    registry_rows = {f["fact_id"]: (i, f) for i, f in enumerate(registry["rows"])}
    passages = {p["evidence_id"]: (i, p) for i, p in enumerate(packet["evidence_passages"])}

    def numerical(name, code):
        i, fact = registry_rows["M:" + name + ":" + code]
        return {**ref(registry_path, f"/rows/{i}"), "fact_literal": fact}

    def source(code):
        identifier = "fidelity_q2_2026:p2:scope" if code == "scope" else "fidelity_q2_2026:p3:sector:" + code
        i, passage = passages[identifier]
        return {**ref(packet_path, f"/evidence_passages/{i}"), "passage_literal": passage}

    def observation(identifier, claim, quote, locator, evidence_summary, evidence_refs, assessment, limits):
        assert quote in record["raw_response_text"] or quote in json.dumps(current, ensure_ascii=False)
        return {"id": identifier, "case_id": CASE, "endpoint": "C0", "claim_or_action": claim,
                "model_quote": quote, "response_locator": locator, "response_artifact": ref(record_path),
                "evidence_summary": evidence_summary, "evidence_refs": evidence_refs,
                "author_assessment": assessment, "limits": limits,
                "independent_human_judgment": None, "automatic_semantic_score": None}

    observations = [
        observation("C0_claimed_correction_without_changed_weights",
            "합계를 고쳤다고 설명했지만 실제 제출된 11개 비중은 변하지 않았다.",
            "The previous proposal had a sum of 1.035, which was corrected to 1.000 by reducing the overweight in IT and RE and slightly increasing the underweight sectors to absorb the excess weight, maintaining alignment with the Fidelity ratings while satisfying the full-investment constraint.",
            "/parsed_response/risk_discussion",
            "C0 생성 전에 C:stage3:sum=1.035가 노출되었다. 단계3과 C0 weights 배열은 동일하며 십진 합계는 모두 1.035다. C0 계산기 결과도 invalid_raw_proposal이며 위험값은 없다.",
            [ref(prior_path, "/parsed_response/weights"), ref(record_path, "/parsed_response/weights"),
             ref(record_path, "/visible_calculator_facts_before_generation/" + str(previous_sum[0])),
             ref(record_path, "/feedback/allocation")],
            "이 한 응답에서는 재검토·수정의 서술과 실제 행동이 일치하지 않는다. 근거를 받고 수정했다고 말하는 것과 실행 가능한 배분을 제출하는 것은 구분된다.",
            "한 사례의 관측이다. 의도적 기만, 내부 인지기제, 전체 모델 또는 R1/R4 효과를 추론하지 않는다. C1/C2에서 바뀌더라도 이 최초 C0를 덮어쓰지 않는다."),
        observation("C0_energy_source_reason_transfer", "Energy 축소 이유에 다른 산업의 자본지출 이유가 섞인다.",
            current["weights"][0]["rationale"], "/parsed_response/weights/0/rationale",
            "Energy의 제공 문장은 unfavorable risk-return indicators이며 capital spending은 Materials15에 제시되어 있다. Energy 원비중 0.025는 기준 0.030030보다 작다.",
            [source("10"), source("15"), numerical("baseline_weights", "10")],
            "축소 방향 자체는 해당 전망과 연결되지만 그 선택을 뒷받침하는 이유 일부는 산업별 출처와 어긋난다. 등급 보존만으로 이유 보존을 확인할 수 없다.",
            "이는 제공 패킷의 근거 대조다. 원본 PDF 전체에 Energy 자본지출 논의가 전혀 없다는 주장이 아니며, 패킷 의역의 독립 사람 검토가 남아 있다."),
        observation("C0_consumer_mean_sign_mismatch", "경기소비재 확대의 근거로 실제와 반대 부호의 평균수익률을 든다.",
            current["weights"][3]["rationale"], "/parsed_response/weights/3/rationale",
            "경기소비재25 일평균은 -0.0002551436565인데 응답은 +0.00085라고 한다. 필수소비재30 실제 값 +0.0008473073에 가깝다. 30의 응답도 -0.00026을 인용하지만 실제는 양수다.",
            [numerical("daily_mean_return", "25"), numerical("daily_mean_return", "30"),
             ref(record_path, "/parsed_response/weights/4/rationale")],
            "확대·축소를 뒷받침하는 시장 근거의 대상과 부호가 틀렸다. 실제 다른 산업 수치와 대응하는 패턴은 관찰되지만 내부 교환 과정을 입증한 것은 아니다.",
            "과거 평균은 미래 기대수익의 정답도 아니다. 임의 반올림 문턱이나 전체 수치 정확도 점수를 새로 만들지 않는다."),
        observation("C0_IT_risk_value_not_supported_by_its_visible_ID", "IT의 높은 원비중을 잘못된 연율 위험값으로 설명한다.",
            current["weights"][7]["rationale"], "/parsed_response/weights/7/rationale",
            "M:annualized_volatility_diagnostic:45의 실제 값은 0.3368510791(연율 수익률 표준편차), 응답 값은 0.2122다. IT의 상대적 최상위 변동성 순위와 전망의 favorable post-decline valuations는 각각 지지되지만 위험 수치 자체는 다르다.",
            [numerical("annualized_volatility_diagnostic", "45"), source("45")],
            "올바른 출처 ID와 전망 이유를 함께 적더라도 같은 문장 속 위험 수치의 충실성까지 보장하지 않는다.",
            "IT 42%의 최적성이나 기관의 실제 위험선호를 판단하지 않는다. 서술 통계 오류 수정이 이전 단계에 주입된 적이 없으므로 특정 숫자 정정 피드백을 무시했다고 서술하지 않는다."),
        observation("C0_industrial_reason_to_direction_supported", "산업재의 가치평가 이유와 기준보다 큰 원비중은 연결된다.",
            current["weights"][2]["rationale"], "/parsed_response/weights/2/rationale",
            "제공 문장은 Industrials receives Overweight 및 favorable forward-looking valuation evidence다. 원비중 0.105는 공통 기준 0.0880880881보다 크다.",
            [source("20"), numerical("baseline_weights", "20"), ref(record_path, "/parsed_response/weights/2/weight")],
            "이 산업에서는 공개 전망의 이유→확대 서술→기준보다 높은 좌표가 서로 연결되는 부분을 관찰할 수 있다.",
            "선정 문서에 정답 목표비중이 없으므로 10.5%의 크기·최적성은 평가하지 않는다. 전체 합계는 부적합하므로 이 관측을 유효 포트폴리오 성과로 부르지 않는다."),
        observation("C0_alternatives_described_but_not_verified", "두 대안이 서술되지만 변화 단위와 위험 비교는 확정되지 않았다.",
            current["alternatives"], "/parsed_response/alternatives",
            "5%·2.5%가 상대 변화인지 퍼센트포인트인지 명확하지 않고 대안 전체 벡터가 없다. RE는 자신의 배분 이유에서 low volatility, 대안에서는 high-volatility로 표현된다. unresolved/1은 대안이 hypothetical and not yet verified라고 명시한다.",
            [ref(record_path, "/parsed_response/weights/10/rationale"),
             ref(record_path, "/parsed_response/unresolved/1"), numerical("annualized_volatility_diagnostic", "60")],
            "실제 대안 방향이 제시되었다는 점과, 그 대안이 수치상 실행 가능하거나 위험·기대수익을 개선한다고 확인되지는 않았다는 점을 함께 보존한다.",
            "단위를 임의 선택하여 포트폴리오를 재구성·정규화하지 않는다. 모델 자체의 미검증 단서를 삭제하거나 검증 완료를 주장했다고 과장하지 않는다."),
        observation("C0_source_identity_separate_from_copied_labels", "11개 등급 표기는 유지되지만 source_id는 null이다.",
            current["unresolved"][3], "/parsed_response/unresolved/3",
            "interpretations에는 Fidelity 이름, 11개 해당 등급과 evidence_id가 적혀 있다. source_id는 null이며 구조 검사는 valid_structure이나 출처 식별 일치는 false다.",
            [ref(record_path, "/parsed_response/interpretations"), ref(record_path, "/parsed_response/source_id"),
             ref(record_path, "/schema_validation/source_identity_matches_visible_metadata")],
            "출처 ID를 포함하는 엄격한 등급 진단과 눈에 읽히는 등급 문자열은 구분해야 한다. 0/11이라는 엄격 점수가 모든 등급 문자가 틀렸다는 뜻으로 제시되면 안 된다.",
            "사전 평가 규칙을 바꾸거나 점수를 보정하지 않는다. 등급 문자열의 보존만으로 의미·이유·실행 보존 판정을 내리지 않는다."),
        observation("C0_public_view_not_private_mandate", "명시적 제약이 없다는 말과 기관의 실제 제약을 식별했다는 주장을 구별한다.",
            current["unresolved"][2], "/parsed_response/unresolved/2",
            "submitted_constraints는 빈 배열이다. 제공 범위 문장은 투자자의 목표·위험허용도에 따라 포트폴리오가 달라지고 전략가 견해가 회사 전체를 대표할 필요가 없다고 밝힌다.",
            [ref(record_path, "/parsed_response/submitted_constraints"), source("scope")],
            "이 출력에서 새로운 정량 기관 제약이나 위험회피 계수가 명시됐다고 볼 근거는 없다. 모델의 성장·회복·평균회귀 해석은 공개 문서의 이유와 구별해 읽어야 한다.",
            "빈 제약 배열은 실제 기관에 제약이 없다는 증거가 아니다. 공개 산업전망 과제를 비공개 기관 전략·목적 복원으로 확대하지 않는다."),
    ]
    data = {"artifact_kind": "author_AI_completed_single_C0_observations_before_whole_pilot_completion",
            "reviewer_role": "author_AI_implementation_participant_not_independent_human",
            "independent_human_review_completed": False, "independent_human_judgment": None,
            "whole_pilot_review_status": "pending_remaining_fixed_cases", "strategic_preservation_verdict": None,
            "paper_observations": observations, "auxiliary_observations": [],
            "trace_details": {"stage3_to_C0_literal_equalities": identical, "C0_decimal_raw_sum": str(total),
                "prior_sum_visible_before_C0": previous_sum[1], "C0_raw_allocation": record["feedback"]["allocation"],
                "C0_valid_portfolio_risk": record["feedback"]["valid_portfolio_risk"],
                "stage3_observations_ref": ref(note_path), "automatic_semantic_score": None},
            "provenance": {"created_at_utc": datetime.now(timezone.utc).isoformat(),
                "manifest": ref(PREPARED / "manifest.json"),
                "evaluation": None, "run_summary": None,
                "pending_provenance_reason": "Whole-pilot offline report and final run summary do not exist in completed form at this interim author observation.",
                "files": [ref(p) for p in (record_path, prior_path, response_capture, packet_path, registry_path, note_path, Path(__file__))]},
            "model_calls_by_this_review": 0, "online_artifacts_changed": False,
            "review_scope": "Only this completed C0 is observed. Other cases and C1/C2 are unreviewed; no R1/R4 or between-source conclusion."}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": ref(OUT), "observations": len(observations), "whole_pilot_verdict": None, "model_calls": 0}))


if __name__ == "__main__":
    main()
