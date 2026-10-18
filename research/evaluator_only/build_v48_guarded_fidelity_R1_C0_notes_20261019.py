"""Record manually read source/reason/action observations for one completed C0.

This is an offline author-AI note, not automatic semantic scoring or a human
review. It never reads an unfinished case or writes into the live run.
"""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
PREP = ROOT / "data/sector_protocol/v48_pilot_r2_20261018"
RUN = ROOT / "data/local_sector_runtime/pilot_v48_guarded_20261019"
CASE = "fidelity_q2_2026__R1"
C0 = RUN / CASE / "C0/record.json"
STAGE3 = RUN / CASE / "stage3/record.json"
PACKET = PREP / "packets/fidelity_q2_2026.json"
REGISTRY = PREP / "public_numeric_registry.json"
CONTRACT = PREP / "prompt_contract.json"
OUT = Path(__file__).with_name("v48_guarded_fidelity_R1_C0_author_observations_20261019.json")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path, locator=None, **extra):
    value = {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path), **extra}
    if locator is not None:
        value["locator"] = locator
    return value


def pointer(value, locator):
    for part in locator[1:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def main():
    if OUT.exists():
        raise FileExistsError("Preserve observations; use a new version")
    captured = [C0, STAGE3, PACKET, REGISTRY, CONTRACT,
                RUN / CASE / "C0/http_0001_generation/response.json",
                RUN / CASE / "C0/http_0001_generation/request.json",
                PREP / "manifest.json", Path(__file__)]
    hashes = {path: digest(path) for path in captured}
    assert hashes[C0] == "0c650b3a2eb08406bf884007a49e033731f30dad9f7373a70083aa0708ec2f36"
    assert hashes[STAGE3] == "e7c7a40e4a06b7d622e8e1ff00b96b83cb71b32b0bb30f9dfc0663d6bfcfccb6"
    record, prior, packet, registry = map(read, (C0, STAGE3, PACKET, REGISTRY))
    parsed = record["parsed_response"]
    assert record["response_complete"] is True and record["transport_status"] == "completed"
    assert record["schema_validation"]["valid"] is True
    assert read(captured[5])["message"]["content"] == record["raw_response_text"]
    assert json.loads(record["raw_response_text"]) == parsed
    weights = parsed["weights"]
    assert len(weights) == 11 and weights == prior["parsed_response"]["weights"]
    total = sum(Decimal(str(row["weight"])) for row in weights)
    assert total == Decimal("1.035")
    assert record["feedback"]["allocation"]["valid"] is False
    assert all(value == 0 for value in record["feedback"]["raw_weight_deltas"].values())
    facts = {row["fact_id"]: (index, row) for index, row in enumerate(registry["rows"])}

    def passage(index):
        return ref(PACKET, f"/evidence_passages/{index}", passage_literal=packet["evidence_passages"][index])

    def fact(identifier):
        index, row = facts[identifier]
        return ref(REGISTRY, f"/rows/{index}", fact_literal=row)

    def response(locator):
        return ref(C0, locator)

    observations = []

    def observe(identifier, locator, claim, evidence, refs, assessment, limits):
        quote = pointer(record, locator)
        assert isinstance(quote, str) and quote
        observations.append({
            "id": identifier, "case_id": CASE, "endpoint": "C0",
            "claim_or_action": claim, "model_quote": quote,
            "response_locator": locator, "response_artifact": ref(C0),
            "evidence_summary": evidence, "evidence_refs": refs,
            "author_assessment": assessment, "limits": limits,
            "independent_human_judgment": None, "automatic_semantic_score": None,
        })

    observe("guarded_C0_correction_claim_vs_unchanged_raw_vector", "/parsed_response/risk_discussion",
            "합계를 수정했다고 서술하지만 새 실행의 이전 11개 원비중을 그대로 제출했다.",
            "새 stage3와 C0의 weights 배열은 수치·이유·근거 ID까지 같다. Decimal로 더한 C0 합계는 1.035이며 모든 이전 대비 delta는 0이다. C0 전에 보였던 C:stage3:sum도 1.035이다.",
            [response("/parsed_response/weights"), ref(STAGE3, "/parsed_response/weights"),
             response("/feedback/raw_weight_deltas"), response("/visible_calculator_facts_before_generation/0"),
             response("/feedback/allocation")],
            "수정했다는 설명과 실제 선택의 변화가 어긋난다. 이는 설명의 확인과 제출 벡터의 확인을 구분해야 하는 사례 관측이다.",
            "이 한 응답의 산술·문장 대조이며 전체 모델의 전략 능력이나 다른 절차와의 차이를 판정하지 않는다. 정규화하거나 보조안으로 C0를 바꾸지 않는다.")
    observe("guarded_C0_energy_added_reason_and_wrong_return_sign", "/parsed_response/weights/0/rationale",
            "Energy의 축소 방향에는 제공 전망을 사용하지만 근거에 없는 이유와 반대 부호의 시장 수치를 덧붙였다.",
            "Energy 제공 문장은 unfavorable risk-return indicators다. 자본지출 부담은 같은 패킷의 Materials 문장에 있다. Energy의 일평균 수익률 ID 실제 값은 +0.000818731323068254인데 응답은 -0.00030이라고 적는다. 원비중0.025는 기준0.03003003003003003보다 작다.",
            [passage(1), passage(2), fact("M:daily_mean_return:10"), fact("M:baseline_weights:10"), response("/parsed_response/weights/0/weight")],
            "출처의 축소 판단과 실제 축소 방향은 함께 보이지만, Energy 제공 근거에 없는 자본지출 이유가 추가되고 같은 표현은 Materials 패킷에 제시되어 있다. 해당 ID의 수익률 부호도 다르다.",
            "모델 내부에서 산업 간 전이가 일어났다고 단정하지 않는다. 평균회귀·구조적 역풍은 이 응답이 추가한 추론이며 원문이 확정한 전망이나 미래 기대수익으로 취급하지 않는다.")
    observe("guarded_C0_industrials_supported_reason_and_direction", "/parsed_response/weights/2/rationale",
            "산업재의 가치평가 이유와 기준보다 큰 원비중이 연결된다.",
            "제공 문장은 Industrials receives Overweight 및 favorable forward-looking valuation evidence다. C0는 같은 이유를 말하며 원비중0.105를 제출했다. 공통 기준은0.08808808808808809이고 공개 일평균 수익률도 양수0.000705407660168093이다.",
            [passage(3), fact("M:baseline_weights:20"), fact("M:daily_mean_return:20"), response("/parsed_response/weights/2/weight")],
            "이 산업에서는 제공 이유→확대 서술→기준보다 큰 실제 좌표의 연결을 관찰할 수 있다. 관측 가능한 지지 부분을 실패 원인과 함께 남긴다.",
            "10.5%가 기관의 정답이나 최적 비중이라는 뜻이 아니다. 전체 합계는 부적합하므로 유효 포트폴리오 성과로 부르지 않는다. 근접한 통계 인용에 새 반올림 문턱이나 종합점수를 부여하지 않는다.")
    observe("guarded_C0_IT_supported_view_wrong_volatility_value", "/parsed_response/weights/7/rationale",
            "IT의 전망 이유와 확대 방향은 연결되지만 인용한 연율 변동성 값은 해당 ID와 다르다.",
            "IT 제공 이유는 fundamentals and post-decline valuations다. 원비중0.42는 기준0.38038038038038036보다 크다. M:annualized_volatility_diagnostic:45 값은0.33685107914419216인데 응답은0.2122를 적는다. 이 ID는 2026-04-21~07-16의 annual_decimal_return 단위 표준편차다. 등록된 11개 값 가운데 IT가 가장 크다는 순위는 맞는다.",
            [passage(8), fact("M:baseline_weights:45"), fact("M:annualized_volatility_diagnostic:45"), response("/parsed_response/weights/7/weight")],
            "전망 이유와 확대 선택의 부분적 연결, 시장 수치의 불일치를 분리해 읽어야 한다. 유효한 ID를 적는 것만으로 수치나 전략의 충실성이 보장되지는 않는다.",
            "IT42%의 최적성·기관 위험선호를 추정하지 않는다. 잘못된 숫자가 나온 내부 원인을 단정하거나 수치 오류를 전체 의미 실패로 확장하지 않는다.")
    observe("guarded_C0_health_neutral_and_risk_rank", "/parsed_response/weights/5/rationale",
            "Neutral을 유지했다고 설명하지만 그 이유로 든 최저 변동성 주장은 자료와 다르다.",
            "Health Care 제공 이유는 balanced risk-return이고 원비중0.095, 기준0.0890890890890891이다. 해당 연율 변동성은0.18338371693726102이며 응답값0.1327과 다르다. 등록된 최저 연율 변동성은 Financials의0.132724604028941이다.",
            [passage(6), fact("M:baseline_weights:35"), fact("M:annualized_volatility_diagnostic:35"), fact("M:annualized_volatility_diagnostic:40"), response("/parsed_response/weights/5/weight")],
            "Neutral 표기와 설명은 읽을 수 있으나 최저 위험이라는 보조 근거는 지지되지 않는다. 가까운 비중이라는 표현의 수용 여부는 정성 검토에 남긴다.",
            "Neutral을 기준 비중과 정확히 같아야 한다는 규칙으로 바꾸지 않는다. 임의의 허용 편차나 숫자 유사성을 사용해 전략 성공을 채점하지 않는다.")
    observe("guarded_C0_alternatives_not_verified", "/parsed_response/alternatives",
            "대안의 변화 방향을 제시하지만 변화 단위와 위험·수익 비교는 확정되지 않았다.",
            "5%·2.5%가 상대 변화인지 퍼센트포인트인지 명확하지 않고 대안 전체 벡터가 없다. RE는 자신의 배분 이유에서는 low volatility, 대안에서는 high-volatility로 적혀 있다. unresolved/1은 대안이 hypothetical and not yet verified라고 명시한다.",
            [response("/parsed_response/weights/10/rationale"), response("/parsed_response/unresolved/1"), ref(CONTRACT, "/common_instructions/8")],
            "대안을 서술했다는 점과 실제 실행 가능성·위험·기대수익 비교가 검증되지는 않았다는 점을 함께 보존한다.",
            "단위를 임의 선택해 벡터를 재구성하거나 정규화하지 않는다. 모델 스스로 적은 미검증 단서를 삭제하지 않으며 대안 효과를 확정한 것으로 과장하지 않는다.")
    observe("guarded_C0_identity_separate_from_literal_labels", "/parsed_response/unresolved/3",
            "제공된 11개 등급 문자열은 옮겼지만 source_id는 null이다.",
            "11개 interpretations에서 제공 등급 문구와 Fidelity 근거 ID가 읽힌다. source_id는 null이며 구조검사는 valid_structure이지만 source_identity_matches_visible_metadata는 false다.",
            [response("/parsed_response/interpretations"), response("/parsed_response/source_id"), response("/schema_validation/source_identity_matches_visible_metadata"), *[passage(i) for i in range(1, 12)]],
            "출처 ID 포함 엄격 진단과 읽을 수 있는 등급 문구 보존을 구분해야 한다. 아직 bundle 평가가 없는 이 기록에서 최종 점수를 생성하지 않는다.",
            "등급 문구를 옮긴 사실은 이유의 충실성이나 실제 전략 보존을 인증하지 않는다. 기존 평가 규칙을 바꾸거나 누락 ID를 복구하지 않는다.")
    observe("guarded_C0_public_view_and_constraints_scope", "/parsed_response/unresolved/2",
            "기관별 구체 제약을 식별하지 못한 상태와 실험의 공통 실행 규칙을 구분해야 한다.",
            "submitted_constraints는 빈 배열이다. 제공 범위 문장은 전략가 판단이 회사 전체를 대표할 필요가 없고 투자자의 목표·위험허용도에 따라 선택이 달라진다고 밝힌다. 별도의 공통 과제에는 원비중·완전투자 확인 등 실행 규칙이 있다.",
            [response("/parsed_response/submitted_constraints"), passage(0), ref(CONTRACT, "/common_instructions/1"), ref(CONTRACT, "/common_instructions/9")],
            "이 출력에서 특정 기관의 정량 위험회피 계수나 비공개 제약이 밝혀졌다고 볼 근거는 없다. 공통 실행 규칙까지 없다는 뜻으로 읽어서도 안 된다.",
            "빈 제약 배열은 실제 기관에 제약이 없다는 증거가 아니다. 공개 산업전망의 반영 과제를 비공개 운용목적·고객 위험선호의 복원으로 확대하지 않는다.")

    # These author-written summaries follow a literal reading of all 11 rows.
    # They are not generated by matching source labels or numerical directions.
    notes = {
        "10": "불리한 위험수익 전망과 축소 방향은 연결된다. 자본지출 이유는 Energy 제공 문장에 없고 일평균 수익률 인용은 실제 부호와 반대다.",
        "15": "자본지출 부담이라는 제공 이유를 재사용하며 기준보다 작은 비중을 제출한다. 가까운 미래 성장 잠재력의 저하는 모델이 덧붙인 추론이다.",
        "20": "유리한 선행 가치평가 이유와 기준 초과 비중이 연결된다. 성장 포착은 모델의 추가 목적 표현이며 최적비중으로 판정하지 않는다.",
        "25": "제공 확대 등급과 원비중 방향은 연결되지만 이유 문장에서 일평균 수익률을 양수0.00085라고 적는다. 등록된 해당 값은 음수 -0.0002551436565336444이다.",
        "30": "가치함정·약한 펀더멘털 이유와 축소 방향은 연결된다. 일평균 수익률을 음수 -0.00026이라 적지만 등록값은 양수0.0008473073009094685이다.",
        "35": "균형 잡힌 위험수익의 Neutral 해석을 유지하지만 최저 변동성이라는 보조 이유는 등록자료와 다르다. 가까움의 허용 한계를 임의로 정하지 않는다.",
        "40": "상대 가치평가의 하방 지지 이유와 확대 방향은 연결된다. 연율 변동성0.1534는 해당 등록값0.132724604028941과 다르며 가치회복 포착은 모델의 추론이다.",
        "45": "펀더멘털·하락 후 가치평가와 확대 방향은 연결된다. 최상위 변동성 순위는 맞지만 그 값0.2122는 해당 등록값과 다르다.",
        "50": "기술 관련 요소와 방어적 요소의 차이를 제공 이유로 사용하고 축소한다. 등록 일평균 수익률은 음수이지만 연율 변동성 인용0.1789는 해당 값0.15339610421634242와 다르다.",
        "55": "불리한 가치평가와 축소 방향은 연결된다. 연율 변동성 인용0.1669는 해당 값0.17893057942789112와 다르다.",
        "60": "가치평가 분산과 확대 방향은 연결된다. 연율 변동성 인용0.1327는 해당 값0.16693062035900388과 다르며 대안에서의 높은 위험 분류와도 설명 차이가 있다.",
    }
    labels = ["Underweight", "Underweight", "Overweight", "Overweight", "Underweight", "Neutral",
              "Overweight", "Overweight", "Underweight", "Underweight", "Overweight"]
    rows = []
    for index, weight in enumerate(weights):
        code = weight["sector_code"]
        assert parsed["interpretations"][index]["sector_code"] == code
        assert parsed["interpretations"][index]["rating"] == labels[index]
        baseline = facts["M:baseline_weights:" + code][1]["value"]
        rows.append({"case_id": CASE, "endpoint": "C0", "sector_code": code,
                     "author_review_status": "completed_literal_read_against_supplied_packet_and_registry",
                     "source_passage": passage(index + 1),
                     "interpretation_quote": parsed["interpretations"][index]["reason"],
                     "interpretation_ref": response(f"/parsed_response/interpretations/{index}/reason"),
                     "rationale_quote": weight["rationale"], "rationale_ref": response(f"/parsed_response/weights/{index}/rationale"),
                     "raw_weight": weight["weight"], "weight_ref": response(f"/parsed_response/weights/{index}/weight"),
                     "baseline_fact": fact("M:baseline_weights:" + code),
                     "raw_coordinate_difference_decimal": str(Decimal(str(weight["weight"])) - Decimal(str(baseline))),
                     "coordinate_scope": "Descriptive coordinate of an invalid full vector; not a valid portfolio, stance threshold or score.",
                     "author_note": notes[code], "independent_human_judgment": None, "automatic_semantic_score": None})

    # Manually transcribed numerical claims: exact value/ID comparisons only.
    # No NLP extraction, inferred precision cutoff or behavioral score is used.
    manual_claims = [(0, "M:daily_mean_return:10", "-0.00030"),
                     (3, "M:daily_mean_return:25", "0.00085"),
                     (4, "M:daily_mean_return:30", "-0.00026"),
                     (5, "M:annualized_volatility_diagnostic:35", "0.1327"),
                     (7, "M:annualized_volatility_diagnostic:45", "0.2122")]
    numeric = []
    for index, identifier, value in manual_claims:
        literal = f"{identifier} = {value}"
        assert literal in weights[index]["rationale"]
        registered = facts[identifier][1]
        numeric.append({"manual_claim_literal": literal, "response_ref": response(f"/parsed_response/weights/{index}/rationale"),
                        "registered_fact": fact(identifier), "stated_value_decimal": value,
                        "difference_decimal": str(Decimal(value) - Decimal(str(registered["value"]))),
                        "same_sign": (Decimal(value) > 0) == (Decimal(str(registered["value"])) > 0),
                        "period_unit_scope": "The displayed registry tuple supplies the documented fact unit/period; it does not fill missing model wording.",
                        "numeric_score": None, "precision_threshold_added": False})
    # Verify every quotation, evidence locator and immutable input again.
    for item in observations:
        assert pointer(record, item["response_locator"]) == item["model_quote"]
        for evidence in item["evidence_refs"]:
            path = ROOT / evidence["path"]
            assert digest(path) == evidence["sha256"]
            pointer(read(path), evidence["locator"])
    assert all(digest(path) == expected for path, expected in hashes.items())
    result = {
        "artifact_kind": "interim_guarded_repeat_single_C0_author_observations_not_bundle_evaluation",
        "reviewer_role": "assistant_self_review", "reviewer_id": "v48_offline_evaluator",
        "independent_human_review_completed": False, "case_id": CASE, "endpoint": "C0",
        "review_scope": "Only the completed first Fidelity Q2/R1 C0 in the new guarded run. All 11 rows were literally read against supplied researcher-paraphrase passages and the public numeric registry. Original PDFs were not independently re-reviewed here. Other cases and C1/C2 remain unreviewed in this note.",
        "provenance": {"created_at_utc": datetime.now(timezone.utc).isoformat(), "manifest": ref(PREP / "manifest.json"),
                       "evaluation": None, "run_summary": None,
                       "pending_provenance_reason": "The four-case repeat is still running; final bundle evaluation and final run-summary binding belong to a later separate author review.",
                       "run_root": RUN.relative_to(ROOT).as_posix(), "files": [ref(path) for path in captured]},
        "paper_observations": observations, "sector_details": rows, "manual_numerical_claim_comparisons": numeric,
        "trace_details": {"C0_decimal_raw_sum": str(total), "previous_decimal_raw_sum": str(sum(Decimal(str(x["weight"])) for x in prior["parsed_response"]["weights"])),
                          "stage3_to_C0_literal_equalities": {key: parsed[key] == prior["parsed_response"][key] for key in parsed},
                          "raw_allocation_as_recorded": record["feedback"]["allocation"], "valid_portfolio_risk": record["feedback"]["valid_portfolio_risk"],
                          "all_previous_weight_deltas_zero": True,
                          "visible_prior_sum_fact": record["visible_calculator_facts_before_generation"][0],
                          "comparison_with_original_run": "Not used to pool results or certify repeatability; every observation above is bound to this new record."},
        "aggregate_limits": ["No R1/R4 or between-source comparison yet; no four-case semantic verdict.",
                             "No private institutional objective, risk preference or unique target weight is identified by these public passages.",
                             "No strategic success/failure score, rounding threshold, repaired weights or hidden-model causal mechanism is added.",
                             "Representative observations do not replace later fixed-four/44-slot accounting or independent human review.",
                             "Document and market dates differ; this is a retrospective document-conditioned case, not a contemporaneous decision backtest."],
        "model_calls_by_this_review": 0, "online_artifacts_changed": False, "automatic_semantic_score": None,
    }
    with OUT.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"path": OUT.relative_to(ROOT).as_posix(), "sha256": digest(OUT),
                      "completed_C0_cases_reviewed": 1, "sector_rows_read": 11, "observations": len(observations),
                      "raw_sum": str(total), "human_review_completed": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
