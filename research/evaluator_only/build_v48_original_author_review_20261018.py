"""Write an author-AI literal review, preserving the failed original pilot.

The eleven sector assessments below are individually authored after reading
the captured C0, supplied passages, and fact registry. No regex extracts or
scores natural-language claims; no original-source human judgment is filled.
"""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "data/local_sector_runtime/pilot_v48_20261018"
PREP = ROOT / "data/sector_protocol/v48_pilot_r2_20261018"
OUT = Path(__file__).with_name("v48_original_pilot_author_review_20261018.json")
CASE = "fidelity_q2_2026__R1"
CODES = ["10", "15", "20", "25", "30", "35", "40", "45", "50", "55", "60"]

# Hand-transcribed claims, not a language-extraction/scoring algorithm.
VOL_CLAIMS = ["0.1551", "0.1944", "0.1972", "0.1834", "0.1664", "0.1327", "0.1534", "0.2122", "0.1789", "0.1669", "0.1327"]
MEAN_CLAIMS = {"10": "-0.00030", "20": "0.00071", "25": "0.00085", "30": "-0.00026", "35": "0.00170", "40": "0.00135", "45": "0.00255", "50": "-0.00079"}
ASSESSMENTS = {
    "10": "해석문은 패킷의 불리한 위험·수익 지표라는 이유를 유지하고 원비중 0.025도 기준보다 작다. 그러나 배분 이유의 자본지출 부담은 제공 패킷에서 Materials의 이유다. Energy의 인용 변동성 0.1551은 해당 ID 값 0.24627687526240125와 다르고, 음수 평균수익률 주장과 달리 실제 Energy 일평균은 양수다. 평균회귀·구조적 역풍은 모델의 추가 가설이며 확인된 기관 목적이 아니다.",
    "15": "해석문과 배분 이유에 자본지출 부담이 남아 있으며 원비중 0.015는 기준보다 작다. 이는 공개 이유와 축소 방향이 연결되는 관측이다. 연율 변동성의 문자 수치는 0.1944, 등록 값은 0.19436460180258697이다. 적절한 축소 규모가 1.5%라는 정답이나 성장 가능성 감소라는 추가 해석의 실증적 타당성은 문서에서 얻지 못한다.",
    "20": "전망의 유리한 미래 가치평가 이유가 해석문·배분 이유에 모두 남고, 원비중 0.105는 기준보다 높다. 일평균 수익률의 양수 부호도 공통자료와 맞는다. 따라서 이유→확대 설명→기준보다 큰 좌표의 연결을 관찰할 수 있다. 과거 평균이 미래 성장을 보장하거나 10.5%가 최적이라는 결론은 아니다.",
    "25": "해석문은 미래 가치평가에 따른 유리한 위험·수익이라는 이유를 유지한다. 배분 이유는 그 구체적 설명을 등급 동의로 줄이고, 과거 평균이 양수 0.00085라는 추가 근거로 확대를 정당화한다. 실제 경기소비재 일평균은 -0.0002551436565336444이며 연율 변동성도 0.18553788110332176으로 인용한 0.1834와 다르다. 확대 방향이 원문 등급과 같다는 사실과 시장 근거의 불일치는 함께 기록해야 한다.",
    "30": "가치함정 우려와 약한 기초여건이라는 패킷 이유는 해석과 배분 설명에 남고 원비중은 기준보다 작다. 그러나 배분 근거로 든 음수 일평균 -0.00026과 달리 실제 필수소비재 평균은 +0.0008473073009094685다. 경기소비재 응답의 +0.00085와 반대쪽 값에 가까운 패턴은 보이지만 모델 내부에서 값을 교환한 과정까지 입증하지 않는다.",
    "35": "균형 잡힌 위험·수익이라는 Neutral 이유는 해석문에 남는다. 원비중 0.095는 기준 0.0890890890890891보다 크지만 사전 정의된 근접 문턱이 없으므로 이 차이만으로 Neutral의 의미 보존·훼손을 점수화하지 않는다. 최저 변동성이 0.1327이라는 설명은 틀리다. Health Care 등록 값은 0.18338371693726102이고 최저값은 Financials 0.132724604028941이다.",
    "40": "상대 가치평가가 하방을 지지한다는 패킷 이유와 기준보다 높은 원비중 0.130은 연결된다. 그러나 변동성 인용값 0.1534는 해당 산업 실제 값 0.132724604028941과 다르며 Communication Services 값에 가깝다. 가치회복을 포착한다는 표현은 모델의 추가 투자 해석으로 구별하며 비공개 기관 목적이라고 보지 않는다.",
    "45": "기초여건·하락 후 가치평가라는 패킷 이유가 해석문과 배분 이유에 남고 원비중 0.420은 기준보다 크다. IT의 최상위 변동성과 양수 평균수익률이라는 순위·부호는 공통자료와 맞지만 변동성 0.2122라는 인용은 실제 0.33685107914419216과 다르다. growth at a reasonable price와 42% 규모의 정당성은 별도 가설이며 공개 전망만으로 확인되지 않는다.",
    "50": "기술 관련 구성요소가 방어적 구성요소보다 낫다는 제공 문구가 해석과 배분 설명에 이어지고 원비중 0.010은 기준보다 작다. 과거 평균의 음수 부호는 자료와 맞는다. 변동성 0.1789는 실제 0.15339610421634242와 다르다. 산업 내부의 상대적 전망을 산업 전체의 큰 축소로 연결하는 규모 선택은 문서의 정답으로 확인되지 않는다.",
    "55": "불리한 가치평가라는 패킷 이유가 해석문과 배분 설명에 남고 원비중 0.015는 기준보다 작다. 변동성 0.1669는 해당 산업의 실제 0.17893057942789112와 다르다. 축소 방향의 연결과 위험 수치의 잘못된 인용을 분리한다.",
    "60": "가치평가 분산에 따른 유리한 위험·수익이라는 패킷 이유가 해석·배분 설명에 남으며 원비중 0.075는 기준보다 크다. 인용 변동성 0.1327은 실제 0.16693062035900388과 다르고, 배분 이유에서는 low volatility지만 대안에서는 high-volatility로 부른다. 7.5%가 공개 기관의 목표비중이거나 위험·수익 개선을 달성했다고 해석하지 않는다.",
}

def read(p):
    return json.loads(p.read_text(encoding="utf-8"))

def ref(p, locator=None):
    result = {"path": str(p.relative_to(ROOT)).replace("\\", "/"), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
    if locator is not None:
        result["locator"] = locator
    return result

def pointer(obj, path):
    for key in path.lstrip("/").split("/"):
        key = key.replace("~1", "/").replace("~0", "~")
        obj = obj[int(key)] if isinstance(obj, list) else obj[key]
    return obj

def main():
    if OUT.exists():
        raise FileExistsError("Do not overwrite an existing author review")
    report_path = ROOT / "research/evaluator_only/v48_pilot_20261018/evaluation_report.json"
    report = read(report_path)
    registry_path = PREP / "public_numeric_registry.json"
    registry = read(registry_path)
    facts = {r["fact_id"]: (i, r) for i, r in enumerate(registry["rows"])}
    record_path = RUN / CASE / "C0/record.json"
    record = read(record_path)
    parsed = record["parsed_response"]
    stage3_path = RUN / CASE / "stage3/record.json"
    stage3 = read(stage3_path)
    packet_path = PREP / "packets/fidelity_q2_2026.json"
    packet = read(packet_path)
    source_passages = {p["evidence_id"]: (i, p) for i, p in enumerate(packet["evidence_passages"])}
    rows = []
    for case in report["primary_C0_cases"]:
        for i, sector in enumerate(case["review_preparation"]["sector_reviews"]):
            code = sector["sector_code"]
            row = {"case_id": case["case_id"], "endpoint": "C0", "sector_code": code,
                   "response_complete": case["execution"]["transport_completed"],
                   "valid_raw_allocation": case["execution"]["valid_raw_allocation"],
                   "independent_human_judgment": None, "automatic_semantic_score": None,
                   "strategic_preservation_verdict": None}
            if case["case_id"] != CASE:
                row.update(author_review_status="not_assessed_no_completed_C0",
                           material_availability="partial_C0_preserved_separately" if case["execution"]["attempted"] else "C0_not_reached",
                           author_assessment="완료된 C0가 없어 이 산업의 최종 해석·배분 연결을 평가하지 않았다. 부분문장이나 앞 단계 결과를 완성된 최종 응답으로 대신하지 않는다.",
                           limits="이 미관측은 전략 실패나 거리 0이 아니다. 원 실행의 환경 중단 기록을 함께 읽어야 한다.")
                candidate_path = RUN / case["case_id"] / "C0/record.json"
                row["response_artifact"] = ref(candidate_path) if candidate_path.exists() else None
                rows.append(row)
                continue
            interpretation, allocation = parsed["interpretations"][i], parsed["weights"][i]
            assert interpretation["sector_code"] == allocation["sector_code"] == code
            idx, passage = source_passages[f"fidelity_q2_2026:p3:sector:{code}"]
            baseline = facts[f"M:baseline_weights:{code}"][1]
            manual_claims = []
            for metric, claim in [("annualized_volatility_diagnostic", VOL_CLAIMS[i])] + ([("daily_mean_return", MEAN_CLAIMS[code])] if code in MEAN_CLAIMS else []):
                fact_id = f"M:{metric}:{code}"
                fidx, fact = facts[fact_id]
                literal = f"{fact_id} = {claim}"
                assert literal in allocation["rationale"]
                manual_claims.append({"transcription_method": "individually_read_and_hand_transcribed_not_regex_extraction", "literal_claim_text": literal,
                                      "response_field_and_span": {"json_pointer": f"/parsed_response/weights/{i}/rationale", "substring": literal},
                                      "claimed_fact_id": fact_id, "claimed_value_literal": claim,
                                      "reference_fact_literal": fact, "reference_artifact": ref(registry_path, f"/rows/{fidx}"),
                                      "value_minus_reference_decimal": str(Decimal(claim) - Decimal(str(fact["value"]))),
                                      "reference_period_not_explicitly_repeated_in_model_sentence": True,
                                      "new_rounding_tolerance_or_accuracy_score_applied": False,
                                      "scope": "Literal value/subject comparison only. Rounded display differences are retained without treating every difference as a substantive error or setting a new score threshold."})
            row.update(author_review_status="literal_source_reason_action_read_by_author_AI",
                       material_availability="complete_C0_invalid_budget_with_readable_reasons",
                       response_artifact=ref(record_path),
                       source_passage_literal=passage,
                       source_artifact=ref(packet_path, f"/evidence_passages/{idx}"),
                       interpretation_literal=interpretation,
                       interpretation_locator=f"/parsed_response/interpretations/{i}",
                       allocation_rationale_literal=allocation["rationale"],
                       allocation_rationale_locator=f"/parsed_response/weights/{i}/rationale",
                       raw_weight=allocation["weight"], baseline_fact=baseline,
                       raw_active_weight_decimal=str(Decimal(str(allocation["weight"]))-Decimal(str(baseline["value"]))),
                       baseline_reference=ref(registry_path, f"/rows/{facts[baseline['fact_id']][0]}"),
                       hand_transcribed_numeric_claims=manual_claims,
                       author_assessment=ASSESSMENTS[code],
                       limits="제공 패킷은 연구자 의역이다. 원본 PDF에 대한 독립 사람 검토는 미완료이고 공개 문서에 정답 목표비중은 없다. 전체 원비중 합계 1.035이므로 개별 좌표 관측을 실행 가능한 포트폴리오 성과·전체 전략 보존 판정으로 확대하지 않는다.")
            rows.append(row)
    assert len(rows) == 44 and sum(r["author_review_status"] == "literal_source_reason_action_read_by_author_AI" for r in rows) == 11

    previous_notes_path = ROOT / "research/evaluator_only/v48_fidelity_R1_C0_author_observations_20261018.json"
    observations = read(previous_notes_path)["paper_observations"]
    validations = []
    for ob in observations:
        p = ROOT / ob["response_artifact"]["path"]
        assert ref(p)["sha256"] == ob["response_artifact"]["sha256"]
        actual_record = read(p)
        assert actual_record["response_complete"] is True
        assert ob["model_quote"] in pointer(actual_record, ob["response_locator"])
        for evidence in ob["evidence_refs"]:
            p = ROOT / evidence["path"]
            assert ref(p)["sha256"] == evidence["sha256"]
            pointer(read(p), evidence["locator"])
        validations.append({"observation_id": ob["id"], "quote_and_all_evidence_hashes_locators_valid": True})
    assert 4 <= len(observations) <= 8

    partial_path = RUN / "fidelity_q2_2026__R4/C0/record.json"
    partial = read(partial_path)
    assert partial["response_complete"] is False and partial["parsed_response"] is None
    partial_quotes = [
        ("Departed from baseline (0.0300) to reflect Fidelity's Underweight rating. Halved the baseline weight to approximate a -10% tilt relative to the common market, acknowledging unfavorable risk-return indicators.",
         "Energy의 부분 배분 설명은 원문 UW·불리한 위험수익 이유와 연결되지만, 기준의 절반이라는 말과 -10% 변화라는 말은 서로 다른 크기를 뜻한다. 실제 부분 좌표는 약 0.015015이며 공통 기준 약 0.030030의 절반이다.",
         "완료되지 않은 JSON의 한 좌표 관측이다. 전체 합계·실행 가능성·최종 수정 성공이나 R1/R4 효과는 평가하지 않는다."),
        ("Overweight relative to baseline (0.0881) to reflect Fidelity's Overweight rating. Increased weight by 50% to approximate a +50% tilt, supported by favorable forward-looking valuations.",
         "산업재의 부분 설명은 가치평가 이유와 확대 방향을 연결한다. 읽히는 부분 원비중 0.132132132132132는 공통 기준 0.08808808808808809의 약 1.5배다.",
         "부분 응답이므로 완성된 포트폴리오 의미 보존 판정이나 정량 주결과에 포함하지 않는다.")]
    partial_observations = []
    for quote, assessment, limits in partial_quotes:
        start = partial["raw_response_text"].index(quote)
        partial_observations.append({"case_id": "fidelity_q2_2026__R4", "endpoint": "C0", "response_complete": False,
                                     "response_artifact": ref(partial_path), "response_locator": "/raw_response_text",
                                     "raw_text_codepoint_span": [start, start+len(quote)], "model_quote": quote,
                                     "author_assessment": assessment, "limits": limits,
                                     "independent_human_judgment": None, "automatic_semantic_score": None,
                                     "included_in_paper_completed_observation_table": False})
    assert parsed["weights"] == stage3["parsed_response"]["weights"]
    assert sum(Decimal(str(w["weight"])) for w in parsed["weights"]) == Decimal("1.035")
    partial_c1_path = ROOT / "research/evaluator_only/v48_fidelity_R1_partial_C1_observations_20261018.json"
    result = {
        "artifact_kind": "actual_original_interrupted_pilot_author_AI_literal_review",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reviewer_role": "author_AI_implementation_participant_not_independent_human",
        "authorship_conflict": "Same agent authored the evaluator and these qualitative notes; runtime and arithmetic audits are separate AI checks. This is not independent human adjudication.",
        "independent_human_review_completed": False, "independent_human_judgment": None,
        "provenance": {"manifest": ref(PREP / "manifest.json"), "evaluation": ref(report_path), "run_summary": ref(RUN / "summary.json"),
                       "environment": ref(ROOT / "research/evidence/v48_pilot_timing_investigation_20261018/postpilot_environmental_deviation.json"),
                       "round3_accounting": ref(ROOT / "research/evidence/v48_actual_pilot_20261018/round3.json"),
                       "earlier_completed_case_notes": ref(previous_notes_path), "generator": ref(Path(__file__).resolve())},
        "review_scope": "One completed, invalid Fidelity R1 C0 is read against supplied researcher-paraphrased source passages and the visible common market registry. All 44 planned slots are retained. Partial material is explicitly separate; two UBS cases have no C0.",
        "all_44_C0_sector_reviews": rows,
        "author_review_coverage": {"planned_sector_slots": 44, "completed_C0_sector_rows_literally_read": 11, "remaining_sector_slots_without_completed_C0": 33, "independent_human_assessed_sector_slots": 0},
        "paper_observations": observations,
        "paper_observation_evidence_validation": validations,
        "paper_observation_selection_scope": "Eight representative observations of the sole completed C0; the full eleven-row review above prevents selective examples from replacing coverage. No aggregate success/failure score is inferred, and the 33 unobserved rows are not counted as unsupported strategies.",
        "partial_C0_observations": partial_observations,
        "auxiliary_partial_review": {"artifact": ref(partial_c1_path), "observations": read(partial_c1_path)["auxiliary_partial_observations"], "completed_C1": False, "C0_replaced": False, "full_sum_or_success_inferred": False},
        "earlier_trace_note_refs": [ref(ROOT / "research/evaluator_only/v48_preliminary_trace_notes_20261018.json"), ref(ROOT / "research/evaluator_only/v48_stage3_trace_notes_20261018.json")],
        "aggregate_interpretation": [
            "The source rating strings and several source-specific reasons occur in the sole completed response; some raw coordinate directions follow those reasons. This supports bounded trace observations, not a whole-strategy preservation verdict.",
            "Additional market explanations contain wrong signs or sector-specific numbers, and the claimed budget correction did not change the eleven submitted weights. Source-to-reason-to-action checks therefore add information beyond rating-string or arithmetic-only diagnostics.",
            "No valid completed pair exists. R1/R4 convergence, between-institution differences, causal effects, return performance and general model ability remain unestimated.",
            "Power-state interruptions and the terminal system-integrity incident are operational deviations. Missing responses are not model strategic failures. A later separately registered repeat must retain and identify this original run.",
            "Public strategist outlooks are not private firm mandates. The packet's original-source accuracy, grade definitions and cross-source comparability need independent human review. Fidelity Apr17 is the official landing-page update date, not a verified PDF publication date.",
            "Suggested source checking and stated-versus-actual revision checks connect to organizational use of AI, but no measured productivity gain, labor impact, loss prevention or net benefit follows from this pilot."
        ],
        "strategic_preservation_verdict": None,
        "pilot_readiness": "FAIL_ENVIRONMENTAL_DEVIATION_AND_INCOMPLETE_MEASUREMENT",
        "model_calls_by_this_review": 0, "main_model_calls_by_this_review": 0,
        "online_artifacts_changed": False, "semantic_numeric_score_created": False,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": ref(OUT), "rows": len(rows), "completed_rows_read": 11, "paper_observations": len(observations), "all_observation_quotes_and_evidence_validated": True}, ensure_ascii=False))

if __name__ == "__main__":
    main()
