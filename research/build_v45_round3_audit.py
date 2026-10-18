"""Offline source/logic audit; never imports or calls a model runner.

The report is deliberately blocked until the run has a terminal summary and the
reviewer has populated MANUAL_REVIEW from completed, unchanged response records.
Partial streams cannot become claims or repaired portfolios in this report.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_REL = "data/local_sector_runtime/single_case_v45_20261018"
RUN = ROOT / RUN_REL
CASE = "fidelity_q2_2026__R1"
RUBRIC_REL = "research/evaluator_only/fidelity_q2_r1_prerun_reference_20261018.json"
RUBRIC_SHA = "8022c19d7b5e9654139996d88cac230cb12d29b30fcf7e817850203c02c35f38"
REG_REL = "data/sector_protocol/v45_single_case_registration_20261018.json"
REG_SHA = "8cf54a9aaaad2ad89e595174a6bfda85b0a307b99f932ca1e0ae5274081b34da"
OUT = ROOT / "research/v45_single_case_round3_20261018.json"
CATEGORIES = {"supported", "contradicted", "not_stated", "uncertain"}

# Filled only after reading completed records and a terminal run summary.
# Each factual claim has a literal output excerpt/JSON pointer and separate
# visible-packet and original-source status. Exact allocation choices are not
# labeled right/wrong against nonexistent institution target weights.
MANUAL_REVIEW = None


def claim(stage, location, excerpt, status, original_status, source_locations,
          reason, kind="source_reason", cited_evidence_ids=None):
    return {"stage": stage, "json_pointer": location, "excerpt": excerpt,
            "claim_kind": kind, "visible_evidence_status": status,
            "original_source_status": original_status,
            "source_locations": source_locations, "reason_for_category": reason,
            "cited_evidence_ids": cited_evidence_ids or []}


# Reviewed from completed records only, while later stages were still running.
# This is a provisional chronological record, not the final case conclusion.
STAGE12_REVIEW_DRAFT = {
    "status": "completed_stage_review_only_final_case_pending",
    "completed_stages_reviewed": [1, 2],
    "interpretation_reasons": "All eleven original labels and their eleven same-sector reason paraphrases agree with the visible packet in both completed stages. The original PDF p3 agrees at that stated level; labels and reasons do not establish allocation correctness.",
    "claim_assessments": [
        claim(1, "/weights/3/rationale", "Aligns with Fidelity Overweight rating", "contradicted", "not_applicable_market_or_decision",
              ["stage1 weights sector25=0.09", "market.baseline_weights.25=0.09309309309309309", "Fidelity PDFp2 scope and p3 Consumer Discretionary row"],
              "소비재 선택재 비중은 제공된 기준보다 낮습니다. 확대 의견을 따랐다는 자기설명과 숫자의 관계가 맞지 않습니다. 비중을 낮게 선택한 것 자체를 정답 위반으로 판정한 것은 아닙니다.", "derived_arithmetic", ["fidelity_q2_2026:p3:sector:25"]),
        claim(1, "/weights/6/rationale", "Aligns with Fidelity Overweight rating", "contradicted", "not_applicable_market_or_decision",
              ["stage1 weights sector40=0.11", "market.baseline_weights.40=0.11811811811811812", "Fidelity PDFp2 scope and p3 Financials row"],
              "금융 비중은 제공된 기준보다 낮지만 원문 확대 의견과 정렬됐다고 설명합니다. 기준 대비 차이를 인정하고 별도 판단 근거를 설명하는 방식은 가능했으나 이 구절에는 그 구분이 없습니다.", "derived_arithmetic", ["fidelity_q2_2026:p3:sector:40"]),
        claim(1, "/weights/7/rationale", "Aligns with Fidelity Overweight rating", "contradicted", "not_applicable_market_or_decision",
              ["stage1 weights sector45=0.37", "market.baseline_weights.45=0.38038038038038036", "Fidelity PDFp2 scope and p3 Information Technology row"],
              "정보기술은 절대 비중이 가장 크지만 기준 비중보다 낮습니다. 절대 비중의 순위와 기준 대비 확대는 서로 다르므로 이 설명은 제출값과 맞지 않습니다.", "derived_arithmetic", ["fidelity_q2_2026:p3:sector:45"]),
        claim(1, "/risk_discussion", "IT at 0.0113 daily", "contradicted", "not_applicable_market_or_decision",
              ["market.sector_codes[7]=45", "market.daily_volatility[7]=0.021219623435220682"],
              "입력의 정보기술 일별 변동성은 0.021219623435220682입니다. 제시한 0.0113은 해당 섹터 값이 아니며 일반적인 반올림으로 일치하지 않습니다.", "historical_market_fact"),
        claim(1, "/risk_discussion", "Utilities at 0.0084", "contradicted", "not_applicable_market_or_decision",
              ["market.sector_codes[9]=55", "market.daily_volatility[9]=0.011271567026449757"],
              "입력의 유틸리티 일별 변동성은 0.011271567026449757입니다. 0.0084는 해당 섹터 수치가 아닙니다. 다른 행의 반올림과 유사하더라도 오류 원인은 단정하지 않습니다.", "historical_market_fact"),
        claim(1, "/risk_discussion", "identifies Information Technology (45) and Industrials (20) as primary growth drivers", "not_stated", "not_stated",
              ["Fidelity PDFp3 title, introductory paragraph and Information Technology/Industrials rows", "packet p3 sector45 and sector20"],
              "원문과 패킷은 유리한 기초여건·가치평가와 확대 의견을 제시합니다. 두 섹터를 주요 성장 동력으로 지정했다는 서열·성장 역할은 선택된 근거에 명시되지 않았습니다. 현실에서 거짓이라는 판정은 아닙니다."),
        claim(1, "/alternatives", "reducing exposure to Energy (10) and Materials (15) due to capital spending concerns", "not_stated", "not_stated",
              ["Fidelity PDFp3 Energy and Materials comments", "packet p3 sector10 and sector15"],
              "자본지출 부담은 소재에 제시된 이유입니다. 에너지에도 같은 이유를 붙이는 부분은 출처가 뒷받침하지 않습니다. 소재에 관한 부분은 원문과 부합하므로 결합 문장 전체를 두 섹터 모두의 오류로 세지 않습니다."),
        claim(1, "/risk_discussion", "do not guarantee future performance", "supported", "supported",
              ["market.interpretation and asof_scope", "Fidelity PDFp2/p3 past-performance qualification"],
              "과거 변동성 수치가 미래 성과를 보장하지 않는다는 범위 제한은 자료와 맞습니다. 같은 문장에 포함된 잘못된 섹터 수치는 별도 주장으로 검토했습니다.", "forecast_or_risk_claim"),
        claim(2, "/risk_discussion", "a daily volatility of 0.0113", "contradicted", "not_applicable_market_or_decision",
              ["stage2 risk_discussion refers to Information Technology45", "market.daily_volatility[7]=0.021219623435220682"],
              "정보기술의 잘못된 일별 변동성이 2단계에서도 반복됩니다. 모델에 주어진 원자료는 0.021219623435220682입니다.", "historical_market_fact"),
        claim(2, "/alternatives", "the sector with the strongest fundamental support", "not_stated", "not_stated",
              ["Fidelity PDFp3 scorecard and IT comment", "packet p3 sector45"],
              "정보기술의 강한 기초여건은 제시되지만 전체 섹터 중 가장 강하다는 비교 서열은 해당 근거에 없습니다. 대안을 제안하는 행위와 그 비교 전제의 근거 여부를 분리합니다."),
        claim(2, "/risk_discussion", "historical volatility is a diagnostic tool rather than a guarantee of future risk", "supported", "supported",
              ["market.interpretation", "SYSTEM final sentence", "Fidelity PDFp2/p3 historical-performance qualification"],
              "과거 변동성 진단을 미래 위험 보장으로 해석하지 않는다는 제한은 자료의 범위와 부합합니다.", "forecast_or_risk_claim"),
    ],
    "decision_and_task_observations": [
        {"stage": 1, "observation": "The response actually extracts all11 source labels/reasons and proposes a sector allocation. It is no longer the v4.4 input-shaped echo. This does not make its numeric facts or allocation valid."},
        {"stage": 1, "observation": "The proposed weights sum exactly to0.965. The calculator records residual-0.035 and withholds portfolio diagnostics. This is a budget violation, not a source-rating error."},
        {"stage": 2, "observation": "The request contains stage1 calculator feedback with raw_sum0.965 and valid=false. Stage2 repeats exactly the same weights, so the disclosed budget error remains. It may still be revised at later stages; no final conclusion yet."},
        {"stage": 2, "observation": "The alternative differs concretely: IT0.40 instead of0.37 and RealEstate0.07 instead of0.085. If all other weights were held fixed the sum would be0.980, but the prose does not give a complete alternative vector, so this conditional calculation is not a measured alternative portfolio."},
        {"stage": 2, "observation": "The text describes a growth-versus-diversification tradeoff. Valuation dispersion is not itself a measured diversification benefit; no covariance-based comparison or complete alternative risk calculation is supplied."},
        {"stage": "1 and2", "observation": "Communication Services rationale says it avoids sectors where technology components outperform defensive ones. The source distinguishes the two components and gives aggregate Underweight; the proposed general exclusion rule lacks a clear source-to-decision explanation. The underweight choice itself is not automatically wrong."},
        {"stage": "1 and2", "observation": "unresolved=[] and submitted_constraints=[]. No numerical risk cap, hidden client objective or gamma is invented. Future uncertainty is acknowledged in risk_discussion, but the unresolved budget issue and retrospective/source-universe limitations are not explicitly addressed."},
        {"stage": "1 and2", "observation": "Each allocation row cites the same-sector source passage. Valid citation identity does not establish that the passage supports the chosen numerical magnitude or every added causal statement."},
    ],
}

STAGE3_REVIEW_DRAFT = {
    "status": "completed_stage_review_only_final_case_pending",
    "completed_stages_reviewed": [3],
    "claim_assessments": [
        claim(3, "/risk_discussion", "a daily volatility of 0.0113", "contradicted", "not_applicable_market_or_decision",
              ["stage3 risk_discussion refers to Information Technology45", "market.daily_volatility[7]=0.021219623435220682"],
              "3단계에서도 정보기술 일별 변동성을 0.0113으로 기재했습니다. 입력은 0.021219623435220682이며, 앞 단계의 오류가 지속됩니다.", "historical_market_fact"),
        claim(3, "/alternatives", "the sector with the strongest fundamental support", "not_stated", "not_stated",
              ["Fidelity PDFp3 scorecard and IT comment", "packet p3 sector45"],
              "강한 정보기술 기초여건은 근거에 있지만 전체 섹터 중 가장 강하다는 서열은 제시되지 않았습니다. 비교 전제의 근거 문제이며 대안을 제안했다는 사실과 구분합니다."),
        claim(3, "/risk_discussion", "historical volatility is a diagnostic tool rather than a guarantee of future risk", "supported", "supported",
              ["market.interpretation", "SYSTEM final sentence", "Fidelity PDFp2/p3 historical-performance qualification"],
              "미래 위험을 보장하지 않는 과거 진단으로 한정한 설명은 근거와 일치합니다. 특정 섹터 수치의 불일치는 별도입니다.", "forecast_or_risk_claim"),
    ],
    "decision_and_task_observations": [
        {"stage": 3, "observation": "The entire submitted proposal equals stage2 by parsed JSON values, including weights, alternatives, reasons, risk discussion and empty unresolved/constraints arrays."},
        {"stage": 3, "observation": "A concrete provisional allocation is submitted, but the repeated raw sum remains0.965 despite prior visible calculator feedback. Budget reconsideration is not observed in the stage3 values; final stage4 is still pending."},
    ],
}

MANUAL_REVIEW = {
    "status": "completed",
    "completed_stages_reviewed": [1, 2, 3, 4],
    "assessment": "material_factual_and_decision_consistency_errors_observed",
    "workflow_completed": True,
    "final_allocation_constraint_satisfied": False,
    "overall_semantic_approval": False,
    "approval_basis": "No new score threshold: the final response explicitly contradicts its raw sum and prior calculator feedback, misstates supplied market numbers, and misdescribes three benchmark-relative directions.",
    "headline_ko": "4단계는 완주했지만, 최종 배분과 핵심 설명은 검증을 통과하지 못했습니다",
    "conclusion_ko": "네 번의 응답은 모두 끝났고 원래 산업 등급은 최종 11/11개가 맞았습니다. 그러나 최종 비중 합계는 96.5%로 전액 배분 조건을 어겼고, 모델은 오히려 합계 조건을 충족했다고 잘못 설명했습니다. 잘못된 위험 수치와 일부 비중 방향 설명도 남았습니다.",
    "reader_findings": [
        {"title_ko": "원래 등급과 기본 이유는 보존됐습니다.", "detail_ko": "모든 단계에서 11개 등급·동일 산업의 근거 ID가 유지됐고, 해석란의 이유는 보인 패킷을 따랐습니다. 이는 출처 추출의 성공이며 배분·전략 설명의 정확성을 보장하지 않습니다."},
        {"title_ko": "완전투자 위반을 세 번의 피드백 뒤에도 고치지 않았습니다.", "detail_ko": "네 단계의 비중은 모두 같고 합계는 0.965입니다. 2·3·4단계 입력에는 직전 계산기의 valid=false와 잔차 −0.035가 있었지만 최종 답변은 처음부터 합계 1 조건을 충족했다고 썼습니다. 남은 3.5%를 임의로 현금으로 넣거나 전체 비중을 보정하지 않았습니다."},
        {"title_ko": "‘비중 확대에 부합한다’는 설명과 원안이 다릅니다.", "detail_ko": "최종 소비재 선택재 9%, 금융 11%, 정보기술 37%는 제공된 공통 기준의 약 9.3093%, 11.8118%, 38.0380%보다 낮습니다. 모델은 이 세 비중이 원문 확대 의견과 일치한다고 설명했습니다. 다른 판단을 선택하는 것은 허용되지만, 그런 이탈을 인정하거나 설명하지 않았습니다."},
        {"title_ko": "시장 수치를 잘못 읽은 오류가 반복됐습니다.", "detail_ko": "정보기술의 입력 일별 변동성은 0.0212196234인데 모든 단계에서 0.0113으로 썼습니다. 1단계의 유틸리티 0.0084도 입력 0.0112715670과 다릅니다. 과거 변동성이 미래를 보장하지 않는다는 제한 설명은 맞지만 숫자 자체는 틀렸습니다."},
        {"title_ko": "대안은 있었지만 비교의 근거는 불완전했습니다.", "detail_ko": "2–4단계는 정보기술을 40%로, 부동산을 7%로 바꾸는 대안을 제시했습니다. 전체 대안 벡터나 위험 계산은 없고 ‘가장 강한 기초여건’이라는 비교 서열, 가치평가 분산에서 분산투자 효과로 넘어가는 설명은 제시된 근거가 충분하지 않습니다. 수치 대안의 존재와 타당한 비교를 구분했습니다."},
        {"title_ko": "기관의 숨은 목적이나 숫자 상한을 만들지는 않았습니다.", "detail_ko": "추가 제약은 비어 있고 위험회피계수·고객별 위험 한도를 새로 제시하지 않았습니다. 다만 unresolved도 계속 비어 있어 이미 지적된 예산 위반과 과거 문서·후행 시장자료의 한계가 해결되지 않은 채 남았습니다."},
    ],
    "topic_connection_ko": "이 사례에서는 기관 문서의 등급을 정확히 옮기는 일과 그 판단을 일관된 산업 배분으로 연결하는 일이 구별됐습니다. 소논문에는 ‘등급 추출은 정확했지만, 원안 제약과 수치·설명 연결의 오류가 계산 피드백 뒤에도 남은 탐색 사례’로 제시할 수 있습니다. 반복 개발한 Fidelity R1 한 사례이므로 기관 간 차이, R1/R4 효과, 전략 수렴, 일반적인 모델 능력이나 미래 수익률에 대한 결론으로 확대할 수는 없습니다.",
    "claim_assessments": STAGE12_REVIEW_DRAFT["claim_assessments"] + STAGE3_REVIEW_DRAFT["claim_assessments"] + [
        claim(4, "/weights/3/rationale", "Aligns with Fidelity Overweight", "contradicted", "not_applicable_market_or_decision",
              ["final weights sector25=0.09", "market.baseline_weights.25=0.09309309309309309", "Fidelity PDFp2 scope and p3 sector25"],
              "소비재 선택재 원안은 공통 기준보다 낮으므로 ‘확대 의견에 부합’한다는 자기설명과 불일치합니다. 임의로 0.965를 나누어 보정하지 않았습니다.", "derived_arithmetic", ["fidelity_q2_2026:p3:sector:25"]),
        claim(4, "/weights/6/rationale", "Aligns with Fidelity Overweight", "contradicted", "not_applicable_market_or_decision",
              ["final weights sector40=0.11", "market.baseline_weights.40=0.11811811811811812", "Fidelity PDFp2 scope and p3 sector40"],
              "금융 원안은 공통 기준보다 낮습니다. 원문 등급은 올바르게 옮겼지만 그 등급과 제출 비중이 일치한다는 설명은 맞지 않습니다.", "derived_arithmetic", ["fidelity_q2_2026:p3:sector:40"]),
        claim(4, "/weights/7/rationale", "Aligns with Fidelity Overweight", "contradicted", "not_applicable_market_or_decision",
              ["final weights sector45=0.37", "market.baseline_weights.45=0.38038038038038036", "Fidelity PDFp2 scope and p3 sector45"],
              "정보기술은 원안 중 절대 비중이 가장 크지만 공통 기준보다 낮습니다. 절대 비중 순위와 기준 대비 확대를 구분해야 합니다.", "derived_arithmetic", ["fidelity_q2_2026:p3:sector:45"]),
        claim(4, "/risk_discussion", "a daily volatility of 0.0113", "contradicted", "not_applicable_market_or_decision",
              ["market.sector_codes[7]=45", "market.daily_volatility[7]=0.021219623435220682"],
              "정보기술 일별 변동성 오류가 최종 답변에도 남았습니다. 이는 배분 취향의 차이가 아니라 입력 수치의 불일치입니다.", "historical_market_fact"),
        claim(4, "/risk_discussion", "the initial allocation already satisfied the sum-to-one constraint", "contradicted", "not_applicable_market_or_decision",
              ["all four raw weight arrays sum exactly0.965", "stage1-3 calculator feedback raw_sum0.965 valid=false", "stage4 request previous calculator_feedback"],
              "첫 원안부터 최종까지 합계는 0.965이고 이전 계산 피드백 세 번 모두 위반을 알렸습니다. 합계 1을 충족했다는 최종 사실 진술은 제출값·실제로 보인 피드백과 직접 모순됩니다.", "derived_arithmetic"),
        claim(4, "/risk_discussion", "No departures from source preferences were made", "contradicted", "not_applicable_market_or_decision",
              ["Fidelity PDFp2 hypothetical benchmark-relative tilt definition", "final raw weights and common benchmark sector25/40/45", "final risk_discussion full last sentence"],
              "공통 기준에 비추어 확대 의견인 세 산업의 원안 비중이 낮은데도 이탈이 없었다고 합니다. 또한 예산 합계 충족 여부는 기관 선호 보존을 논리적으로 증명하지 않습니다. 이 평가는 원문이 정확한 수치 비중을 제시했다는 가정에 의존하지 않습니다.", "derived_arithmetic"),
        claim(4, "/alternatives", "the sector with the strongest fundamental support", "not_stated", "not_stated",
              ["Fidelity PDFp3 scorecard and IT comment", "packet p3 sector45"],
              "정보기술에 강한 기초여건이 있다는 근거는 있지만 전체 섹터 중 가장 강하다는 서열은 선택된 원문·패킷에 명시되지 않았습니다."),
        claim(4, "/risk_discussion", "historical volatility is a diagnostic tool rather than a guarantee of future risk", "supported", "supported",
              ["market.interpretation", "SYSTEM final sentence", "Fidelity PDFp2/p3 historical-performance qualification"],
              "미래 위험을 보장하지 않는다는 범위 제한은 올바르게 남아 있습니다. 이 장점이 잘못된 수치·합계 진술을 상쇄하는 점수로 사용되지는 않습니다.", "forecast_or_risk_claim"),
        claim(4, "/risk_discussion", "the S&P 500 sector reference serves as a neutral benchmark rather than a target", "supported", "not_applicable_market_or_decision",
              ["SYSTEM common benchmark comparison-point instruction", "market.baseline_derivation", "market.interpretation"],
              "공통 기준을 기관의 보유 비중이나 유일한 정답으로 취급하지 않는다는 설명은 실험 자료의 역할과 맞습니다. 실제 방향을 설명하는 과정의 오류와 구분했습니다.", "source_scope"),
    ],
    "decision_and_task_observations": STAGE12_REVIEW_DRAFT["decision_and_task_observations"] + STAGE3_REVIEW_DRAFT["decision_and_task_observations"] + [
        {"stage": 4, "observation": "The same eleven numerical weights persist through all four stages. Stage4 changes wording and adds an incorrect assertion that the original sum satisfied the budget, rather than repairing the disclosed raw budget error."},
        {"stage": 4, "observation": "There is no independently supplied institutional exact-weight target. Large RealEstate relative exposure is recorded descriptively; it is not rejected by an invented cap or declared optimal vector."},
        {"stage": 4, "observation": "HealthCare Neutral is not interpreted as mandatory exact benchmark equality. Its small nonzero active weight is not treated as a semantic violation."},
        {"stage": 4, "observation": "No forecast probability of loss or guaranteed future return is produced. The repeated wrong daily-volatility value is a historical data error, separate from future-performance prediction."},
    ],
    "stage_task_assessment": [
        {"stage": 1, "status": "partly_performed", "basis": "Source interpretation and a concrete proposal are supplied; historical uncertainty is acknowledged but unresolved=[] omits the exposed temporal/universe limitations, and numbers/tilt explanations contain material errors."},
        {"stage": 2, "status": "partly_performed", "basis": "A distinct numeric alternative and qualitative tradeoff are offered, but it is not a complete alternative vector or supported quantitative risk comparison; the prior budget error persists."},
        {"stage": 3, "status": "partly_performed", "basis": "A provisional allocation with citations is submitted. It is unchanged from stage2 and retains the visibly reported budget violation."},
        {"stage": 4, "status": "partly_performed_with_material_contradictions", "basis": "A final response and correct original labels are supplied, but the final allocation is infeasible under the task budget and its reconsideration explanation contradicts the prior arithmetic feedback. This is not a composite strategy score."},
    ],
    "institution_scope_review": "The response calls these Fidelity research/ratings but does not explicitly assert a legally binding firm-wide mandate, a private client objective, numerical risk tolerance or undisclosed sector cap. The public strategist scope is not fully restated, so no broader institutional-policy inference is warranted.",
    "temporal_universe_review": "The response does not falsely date the whole case as a contemporaneous trading replay, but it also omits the source March31 view versus later market-window/June30 comparator and top3000-versus-sector-ETF limitations. These are completeness limits, not fabricated factual contradictions.",
    "source_reason_review": "All four stages repeat the eleven researcher-paraphrased reason sentences from the visible packet. The original p3 supports their broad meaning. Financials original wording is conditional (may limit downside); the response must not be read as a loss guarantee, and its global risk text expressly denies a future guarantee.",
    "citation_review": "Each source interpretation and weight rationale supplies the corresponding same-sector p3 evidence ID. This demonstrates location/scope matching, not entailment of chosen numeric weights, superlatives or extra causal explanations. The primary source has no exact target-weight table for this task.",
}


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fingerprint(path: Path):
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def pointer(value, path):
    """Resolve a JSON pointer for exact audit-to-output anchoring."""
    for token in path.strip("/").split("/") if path else []:
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def source_labels(proposal, rubric):
    rows = proposal.get("interpretations", []) if isinstance(proposal, dict) else []
    rows = rows if isinstance(rows, list) else []
    counts = Counter(row.get("sector_code") for row in rows if isinstance(row, dict)
                     and isinstance(row.get("sector_code"), str))
    source_matches = isinstance(proposal, dict) and proposal.get("source_id") == "fidelity_q2_2026"
    comparisons = []
    for ref in rubric["sector_reference"]:
        code = ref["sector_code"]
        row = next((item for item in rows if isinstance(item, dict) and item.get("sector_code") == code), {})
        label = row.get("rating")
        correct = bool(source_matches and counts[code] == 1 and isinstance(label, str)
                       and label.strip() == ref["original_strategist_view"])
        comparisons.append({"sector_code": code, "sector_name": ref["sector_name"],
            "original_label": ref["original_strategist_view"], "submitted_label": label,
            "row_count": counts[code], "correct_original_label": correct,
            "original_pdf_page": 3, "original_location": ref["original_location"]})
    return {"correct": sum(row["correct_original_label"] for row in comparisons),
            "expected": 11, "rows": comparisons,
            "scope": "Original-label extraction only; not semantic rationale or strategic quality."}


def decimal_weights(raw_text, market):
    value = json.loads(raw_text, parse_float=Decimal, parse_int=Decimal)
    rows = value.get("weights")
    if not isinstance(rows, list) or not rows:
        return {"status": "not_submitted", "raw_sum": None, "rows": []}
    codes = [row.get("sector_code") for row in rows if isinstance(row, dict)]
    numerical = all(isinstance(row, dict) and isinstance(row.get("weight"), Decimal)
                    and row["weight"].is_finite() for row in rows)
    unique = len(codes) == len(set(codes)) and set(codes) == set(market["sector_codes"])
    result = {"status": "observed_raw", "numeric": numerical, "all_codes_once": unique,
              "raw_sum": str(sum((row["weight"] for row in rows), Decimal(0))) if numerical else None,
              "rows": [], "no_normalization": True,
              "scope": "Exact submitted decimal sum and raw coordinate differences from the supplied baseline. If the budget is invalid these are not valid fully-invested portfolio comparisons. No target-weight gold or cash imputation."}
    if numerical:
        result["signed_sum_residual"] = str(sum((row["weight"] for row in rows), Decimal(0)) - 1)
        for row in rows:
            code = row["sector_code"]
            baseline = market["baseline_weights"].get(code)
            result["rows"].append({"sector_code": code, "weight": str(row["weight"]),
                "active_weight": str(row["weight"] - Decimal(str(baseline))) if baseline is not None and unique else None})
    return result


def collect():
    if not (RUN / "summary.json").is_file():
        raise RuntimeError("Run has no terminal summary. No final semantic report is permitted.")
    summary = read(RUN / "summary.json")
    if summary["status"] in ("not_started", "attempted", "running", "started"):
        raise RuntimeError("Run is not terminal.")
    assert fingerprint(ROOT / RUBRIC_REL)["sha256"] == RUBRIC_SHA
    assert fingerprint(ROOT / REG_REL)["sha256"] == REG_SHA
    rubric = read(ROOT / RUBRIC_REL)
    packet_path = ROOT / "data/sector_protocol/v45_single_case_20261018/model_packet.json"
    market_path = ROOT / "data/sector_protocol/v45_single_case_20261018/market_input.json"
    packet, market = read(packet_path), read(market_path)
    names = [RUBRIC_REL, REG_REL, "research/build_v45_round3_audit.py",
             "research/v45_preflight_implementation_review_20261018.json",
             "research/evaluator_only/v45_structured_prerun_review_20261018.json",
             "research/v45_revision_reference_20261018.json",
             str(packet_path.relative_to(ROOT)).replace("\\", "/"),
             str(market_path.relative_to(ROOT)).replace("\\", "/")]
    names += list(rubric["evidence_files"])
    for relative in ["summary.json", "invocation.json", "runtime.json", "manifest_snapshot.json", "run_failure.json"]:
        if (RUN / relative).is_file(): names.append(f"{RUN_REL}/{relative}")
    stages, proposals = [], {}
    for stage in range(1, 5):
        folder = RUN / f"stage{stage}_transport"
        record = RUN / CASE / f"stage{stage}_record.json"
        stage_row = {"stage": stage, "completed_record_present": record.is_file(),
                     "generation_request_present": (folder / "http_0001_generation/request.json").is_file(),
                     "source_label_extraction": None, "allocation": None}
        if record.is_file():
            response_path = RUN / CASE / f"stage{stage}_response.json"
            response = read(response_path)
            assert response.get("done_reason") == "stop"
            raw = response["message"]["content"]
            proposal = json.loads(raw)
            recorded = read(record)
            assert proposal == recorded["raw_proposal"]
            proposals[stage] = proposal
            stage_row.update(status="completed_response_available",
                response_path=str(response_path.relative_to(ROOT)).replace("\\", "/"),
                response_sha256=fingerprint(response_path)["sha256"],
                source_label_extraction=source_labels(proposal, rubric),
                allocation=decimal_weights(raw, market),
                calculator_result=recorded["calculator_result"],
                raw_content_characters=len(raw))
            for p in [record, response_path, RUN / CASE / f"stage{stage}_request.json"]:
                names.append(str(p.relative_to(ROOT)).replace("\\", "/"))
        else:
            stage_row["status"] = "attempted_without_completed_response" if stage_row["generation_request_present"] else "not_started"
        for name in ["logical_messages.json", "grounded_messages.json", "response_schema.json", "authoritative_body.json",
                     "response_contract_validation.json", "projection_validation.json", "supervisor_result.json",
                     "unload_and_residency.json", "http_0001_generation/request.json", "http_0001_generation/response.json",
                     "http_0001_generation/raw_stream.bin", "http_0001_generation/events.jsonl", "render_only/validation.json"]:
            p = folder / name
            if p.is_file(): names.append(str(p.relative_to(ROOT)).replace("\\", "/"))
        stages.append(stage_row)
    evidence = {name: fingerprint(ROOT / name) for name in dict.fromkeys(names)}
    for name, expected in rubric["evidence_files"].items():
        assert evidence[name]["sha256"] == expected["sha256"], name
    assert len(proposals) == summary["completed_workflow_stages"]
    return summary, rubric, packet, market, stages, proposals, evidence


def main():
    summary, rubric, packet, market, stages, proposals, evidence = collect()
    if not MANUAL_REVIEW or MANUAL_REVIEW.get("status") != "completed":
        raise RuntimeError("Independent source/logic review is unfinished. No final report was written.")
    manual = MANUAL_REVIEW
    assert set(manual["completed_stages_reviewed"]) == set(proposals)
    claims = manual["claim_assessments"]
    for claim in claims:
        stage = claim["stage"]
        assert stage in proposals
        original_text = pointer(proposals[stage], claim["json_pointer"])
        assert isinstance(original_text, str) and claim["excerpt"] in original_text
        assert claim["visible_evidence_status"] in CATEGORIES
        assert claim["original_source_status"] in CATEGORIES | {"not_applicable_market_or_decision"}
        assert claim["reason_for_category"] and claim["source_locations"]
        row = stages[stage - 1]
        claim["response_path"] = row["response_path"]
        claim["response_sha256"] = row["response_sha256"]
        claim["human_review_required"] = True
    final_labels = source_labels(proposals.get(4), rubric)
    counts = Counter(claim["visible_evidence_status"] for claim in claims)
    checks = []

    def check(identifier, condition, meaning):
        assert condition, identifier
        checks.append({"id": identifier, "status": "pass", "meaning": meaning})

    check("terminal_four_stage_records", summary["status"] == "completed_four_stages" and len(proposals) == 4,
          "Four completed unchanged proposals exist; this is workflow completion, not financial approval.")
    check("registered_case_and_references", fingerprint(ROOT / REG_REL)["sha256"] == REG_SHA and fingerprint(ROOT / RUBRIC_REL)["sha256"] == RUBRIC_SHA,
          "The same source/case and pre-run semantic rubric were retained.")
    check("all_original_labels_preserved", all(row["source_label_extraction"]["correct"] == 11 for row in stages),
          "All four stages reproduce all eleven original labels; stages are not independent samples.")
    check("unchanged_numeric_weights", all(proposals[n]["weights"][i]["weight"] == proposals[1]["weights"][i]["weight"]
                                         for n in range(2, 5) for i in range(11)),
          "Numerical weights persist through the four-stage sequence without model correction.")
    check("same_budget_error_all_stages", all(Decimal(row["allocation"]["raw_sum"]) == Decimal("0.965")
                                              and row["calculator_result"]["allocation"]["valid"] is False for row in stages),
          "The submitted sum is exactly0.965 at every stage and the original calculator marks it invalid.")
    for n in range(2, 5):
        messages = read(RUN / CASE / f"stage{n}_request.json")
        feedback = json.loads(messages[-2]["content"])["calculator_feedback"]
        check(f"prior_error_visible_stage{n}", feedback == stages[n - 2]["calculator_result"] and feedback["allocation"]["valid"] is False,
              "The next stage receives the literal preceding invalid-allocation calculator result.")
    check("stage2_and3_proposals_identical", proposals[2] == proposals[3],
          "Equality concerns the parsed complete response values, not a claim about hidden reasoning.")
    check("final_false_sum_assertion_anchored", "the initial allocation already satisfied the sum-to-one constraint" in proposals[4]["risk_discussion"],
          "The contradictory final budget assertion is present verbatim in the captured response.")
    check("market_numbers_anchored", market["sector_codes"][7] == "45" and market["daily_volatility"][7] == 0.021219623435220682
          and market["sector_codes"][9] == "55" and market["daily_volatility"][9] == 0.011271567026449757,
          "The reviewed daily volatility values use the packet's declared sector order.")
    check("atomic_claims_anchored", len(claims) == 23,
          "Every selected factual excerpt was checked against its original JSON pointer; compound claims were separated.")
    check("original_source_bytes_unchanged", all(fingerprint(ROOT / name) == item for name, item in evidence.items()),
          "Referenced raw results, packet, source files and audit dependencies remain byte-identical.")
    check("no_main_retry_or_human_approval", summary["main_model_calls"] == 0 and summary["automatic_retries"] == 0
          and summary["human_semantic_pass"] is False and summary["main_freeze"] is False,
          "This reviewed pilot does not authorize or imply main-study or human approval.")
    report = {
        "schema_version": "v45_single_case_semantic_audit_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reviewer": "independent_assistant_round3", "audit_status": "completed",
        "case_id": CASE, "protocol_version": "4.5", "run_summary": summary,
        "stages": stages, "source_label_primary_fixed_denominator": final_labels,
        "semantic_review": manual,
        "category_counts": {key: counts.get(key, 0) for key in sorted(CATEGORIES)} if claims else {key: None for key in sorted(CATEGORIES)},
        "category_count_scope": "Audited atomic factual excerpts, not a source-sector score or a measure of overall strategy quality.",
        "existing_audit_dimensions": rubric["audit_dimensions"],
        "denominator_reconciliation": "Final-label extraction retains the registered11 denominator, including an attempted case without a final answer. Semantic claims require actual completed responses; missing output is not a contradicted or not_stated claim. Four sequential stages are not four independent cases.",
        "decisions_have_no_exact_weight_gold": True,
        "main_model_calls": 0, "main_frozen": False, "human_semantic_approval": False,
        "mutations": {"model_calls": 0, "raw_edits": 0, "runtime_changes": 0, "automatic_answer_revision": 0},
        "evidence_files": evidence,
        "checks": checks, "check_count": len(checks),
        "limits": [
            "This is a reused exploratory Fidelity R1 case, not an independent confirmatory sample.",
            "Schema enforcement controls keys, types, array lengths and public code vocabulary; their compliance alone is not model reasoning performance.",
            "Original source labels, citation correctness, factual entailment, allocation choice and portfolio arithmetic are distinct dimensions.",
            "No unique institution numeric weights, mandatory risk cap, private mandate or general firm preference is imputed.",
            "The case does not estimate R1/R4 effects, institutional convergence, causal benefits of schema versus prompt guidance or future investment performance.",
            "Assistant self-reviews do not constitute independent human adjudication.",
        ],
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    esc = html.escape
    rows = "".join(f"<tr><td>{s['stage']}</td><td>{esc(s['status'])}</td><td>"
                   + (f"{s['source_label_extraction']['correct']}/11" if s['source_label_extraction'] else "미관측")
                   + "</td><td>" + esc(str((s.get('allocation') or {}).get('raw_sum') or "미제출")) + "</td></tr>" for s in stages)
    findings = "".join(f"<li><strong>{esc(item['title_ko'])}</strong> {esc(item['detail_ko'])}</li>" for item in manual["reader_findings"])
    claim_rows = "".join(f"<tr><td>{c['stage']}단계 · <code>{esc(c['json_pointer'])}</code></td><td>{esc(c['excerpt'])}</td><td>{esc(c['visible_evidence_status'])}</td><td>{esc(c['reason_for_category'])}</td></tr>" for c in claims)
    text = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>v4.5 단일 사례 3차 원문·논리 감사</title><style>
body{{font-family:system-ui,sans-serif;background:#f3f6f8;color:#172434;line-height:1.65;margin:0}}main{{max-width:1100px;padding:30px;margin:24px auto;background:white;border-radius:12px}}h1{{font-size:1.8rem}}h2{{font-size:1.2rem;margin-top:28px}}table{{width:100%;border-collapse:collapse}}td,th{{padding:9px;text-align:left;vertical-align:top;border-bottom:1px solid #dce3e8}}.status{{padding:15px;background:#eef4fa;border-left:5px solid #35719e}}.small{{font-size:.88rem;color:#4b5b68}}code{{overflow-wrap:anywhere}}a{{color:#145c91}}li{{margin:10px 0}}.claims{{font-size:.88rem}}
</style></head><body><main><p class="small">2026-10-18 · Fidelity Q2 2026 · R1 · 독립 3차 자체 검토</p><h1>{esc(manual['headline_ko'])}</h1>
<p class="status">{esc(manual['conclusion_ko'])}</p><table><thead><tr><th>단계</th><th>원본 상태</th><th>원래 등급 추출</th><th>제출 비중 합계</th></tr></thead><tbody>{rows}</tbody></table>
<p class="small">최종 4단계 추출 지표는 고정 분모 {final_labels['correct']}/11입니다. 등급 정확도는 근거 해석·전략 품질과 다릅니다. 4단계 미제출이면 추출값은 0/11이지만, 없는 주장을 의미상 틀렸다고 채점하지 않습니다.</p>
<h2>원문과 논리의 주요 확인 사항</h2><ul>{findings}</ul>
<h2>소논문에서 말할 수 있는 범위</h2><p>{esc(manual['topic_connection_ko'])}</p>
<p>정확 비중 정답이나 임의 위험 상한을 만들지 않았습니다. 산업별 비중은 제안한 판단이며, 원래 기관 등급·사실 전제·상충 관계의 설명을 따로 검토했습니다. 본실험은 0회·미동결이며 사람의 의미 검증 승인은 없습니다.</p>
<details><summary>완성 답변의 주요 주장 {len(claims)}개와 근거 펼치기</summary><table class="claims"><thead><tr><th>원본 위치</th><th>검토한 구절</th><th>보인 근거와 관계</th><th>판정 이유</th></tr></thead><tbody>{claim_rows}</tbody></table></details>
<p class="small">supported / contradicted / not_stated / uncertain은 개별 사실 주장의 근거 관계입니다. 제안 비중 자체의 정답 여부나 종합 전략 점수가 아닙니다. 원문 PDF와 실제 보인 패킷의 범위 차이는 JSON에서 따로 기록합니다.</p>
<p><a href="{OUT.name}">전체 감사 JSON·원본 해시·단계별 검토</a> · <a href="../{RUN_REL}/summary.json">실행 종료 요약</a> · <a href="evaluator_only/fidelity_q2_r1_prerun_reference_20261018.json">실행 전 평가자 전용 근거표</a></p>
<p class="small">세 차례 자체 검토는 사람의 독립 검증을 대신하지 않습니다. 실패한 이전 v4.4 시도는 그대로 보존합니다.</p></main></body></html>'''
    OUT.with_suffix(".html").write_text(text, encoding="utf-8")
    assert all(fingerprint(ROOT / path) == item for path, item in evidence.items())
    print(json.dumps({"json": str(OUT.relative_to(ROOT)), **fingerprint(OUT), "html": str(OUT.with_suffix('.html').relative_to(ROOT)), "model_calls": 0}))


if __name__ == "__main__":
    main()
