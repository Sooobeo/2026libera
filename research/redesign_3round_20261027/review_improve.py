"""Sequential, recorded design review improvements. No model experiment runs."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
PLAN = ROOT / "plan"
SOURCE = PLAN / "LIBERA_실험설정_v6.0_20261027.json"
FINAL_HTML = PLAN / "LIBERA_최종실험설계_쉬운설명_v6.3_20261027.html"


def save_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def version_path(number: int) -> Path:
    return PLAN / f"LIBERA_실험설정_v6.{number}_20261027.json"


def write_round(number: int, previous_path: Path, spec: dict, findings: list[dict], changes: list[str]) -> None:
    spec["protocol_version"] = f"6.{number}-design"
    spec["status"] = "prospective_reviewed_design_not_executed"
    spec["execution_enabled"] = False
    spec["review_cycles_completed"] = number
    spec.setdefault("revision_history", []).append({
        "round": number,
        "input": str(previous_path.relative_to(ROOT)),
        "input_sha256": hashlib.sha256(previous_path.read_bytes()).hexdigest(),
        "changes": changes,
    })
    output_path = version_path(number)
    save_json(output_path, spec)
    save_json(WORK / f"review_round{number}.json", {
        "round": number,
        "review_type": "independent_AI_review_plus_primary_agent_revision_not_human_source_audit",
        "criteria": ["실험 정합성", "논리성", "제목과 원초록의 검증력", "완결성"],
        "input": str(previous_path.relative_to(ROOT)),
        "input_sha256": hashlib.sha256(previous_path.read_bytes()).hexdigest(),
        "findings": findings,
        "applied_changes": changes,
        "output": str(output_path.relative_to(ROOT)),
        "output_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "new_experimental_model_calls": 0,
    })
    print(json.dumps({"round": number, "output": str(output_path), "changes": len(changes)}, ensure_ascii=False))


def round_one() -> None:
    spec = deepcopy(load_json(SOURCE))
    spec["data_contract"]["classification_threshold_basis"] = "0925의 연구 설정. LLM 출력 전에 분모와 제외 규칙을 고정"
    spec["task_definition"] = {
        "construct": "같은 시장에서 펀드별 보유상태로 정한 위험예산과 허용 정보가 요구하는 산업배분 차이",
        "research_objective_not_actual_fund_private_objective": "기존 주식 부문의 분산을 넘지 않으며 주어진 기대수익을 최대화하는 동일 연구 과제",
        "holdings_role": "기본 모형에서 h는 위험상한 h.T@Sigma@h와 변경분 계산에 사용. 보유 구성 자체를 보존하는 최적화는 아님",
        "do_not_infer": ["기관 전략 전체 복제", "실제 펀드의 비공개 목적함수", "동일 모델 공유 자체의 독립 인과효과", "실제 미래 수익"],
        "reallocation_scope": "분류 가능한 주식 부문만 재배분; 전체 펀드 자산배분이나 전체 펀드 위험최적화가 아님",
        "holdings_sensitivity": "보유 구성 보존 또는 turnover 제한을 추가할 때는 연구상 별도 민감도 조건으로 표시하고 실제 펀드 규칙으로 귀속하지 않음",
    }
    spec["workflow"]["stage_contracts"] = [
        {"stage": 1, "name": "계획", "required": ["기본 운용조건과 위험예산", "제공된 근거 ID와 값·시점", "채택·보류 근거", "산업별 검토 계획"],
         "weights_required": False, "forbidden": ["미제공 전망 추정", "의무 제약 창작", "최적비중 조회"]},
        {"stage": 2, "name": "배분안 구성", "required": ["12산업 최초 원비중", "h 대비 변경분", "변경을 지지한 근거 ID", "수익과 위험의 상충"], "weights_required": True},
        {"stage": 3, "name": "점검과 수정", "required": ["최종 12산업 원비중", "계산검사 결과", "전 단계 오류의 유지·교정", "실제 증감과 일치하는 설명"], "weights_required": True},
    ]
    spec["workflow"]["output"] = "stage_contracts에 따라 계획은 근거와 조건을, 구성과 점검은 12산업 비중을 제출"
    spec["workflow"]["propagation_log"] = ["최초 오류 단계", "근거 ID", "누락·오독·계산·설명 모순 구분", "후속 단계에서 유지 또는 교정", "관련 비중 변화"]
    spec["pre_model_identification_audit"] = {
        "compute_before_any_main_model_output": ["네 펀드 h와 위험상한", "full 및 available 기준배분", "기준 펀드 간 거리 분포", "필요한 차이0 또는 불확실한 쌍의 비율"],
        "no_outcome_selection": "기준 차이가 큰 사례만 골라 AI를 실행하지 않으며 모든 사전 생성 사례와 식별 불가 비율을 보존",
        "H1_primary_arm": "C-context/FULL; 모든 기관별 허용정보를 준 상태에서 필요한 차이가 유지되는지 검사",
        "R0_role": "정보 부족 대조와 G_available 진단; R0에서 필요한 기준 차이가 없으면 과잉수렴 부재가 아니라 식별 기회 부족",
    }
    spec["retrieval"]["corpus_contract_required"] = {
        "B": "사전 고정한 문서 양식의 가상 펀드별 전망과 관련 설명; 문서 종류·개수·필드·길이와 실제문서의 보조 역할을 명시",
        "A_C": "해당 펀드 공식 원문의 적격 업무 절; 날짜와 펀드 필터",
        "gold_unit": "근거 ID별 값·단위·날짜·관측 정밀도 묶음",
        "diagnostics": ["검색과 FULL의 동일 입력 비율", "gold recall@4", "단위·정밀도 동시 회수율", "문서 길이·순서 분포"],
        "no_artificial_advantage": "검색이 어렵도록 결과를 본 뒤 불필요한 문서를 추가하거나 FULL을 불리하게 자르지 않음",
    }
    spec["evaluation"]["primary_mitigation_endpoints"] = ["pair_response_error_full", "full_regret"]
    spec["evaluation"]["pair_response_error_full"] = "0.5*L1((wi-wj)-(wstar_full_i-wstar_full_j))"
    spec["evaluation"]["H1_rule"] = "FULL의 G_available(=G_full)>0와 available/full regret>0를 함께 검사. R0와 R1의 available G는 정보집합 진단. 공통성 자체의 원인은 단정하지 않음"
    spec["evaluation"]["improvement_rule"] = "쌍별 기준 반응오차와 full regret이 같은 정책에서 함께 감소해야 공동 개선. signed G 감소만으로 승자 판정 금지. |G| 증가·실패 악화는 별도 경고와 권고 보류 기준"
    spec["analysis"]["confirmatory_tests"] = [
        {"id": "H1", "contrast": "FULL versus its allowed-information reference", "endpoints": ["G_available positive", "R_available positive"],
         "combination": "IUT: max of one-sided positive-direction component p values"},
        {"id": "H2", "contrast": "R1 minus R0", "endpoints": ["pair_response_error_full decreases", "full_regret decreases"],
         "combination": "IUT: max of one-sided decrease-direction component p values"},
        *[{"id": f"H3_{a}_{b}", "contrast": f"{a} versus {b}", "endpoints": ["pair_response_error_full", "full_regret"],
           "combination": "two directional IUTs; p=min(1,2*min(p_both_a_better,p_both_b_better)); label winner only when both improve in that direction"}
          for a, b in [("R1", "R2"), ("R1", "R3"), ("R2", "R3")]],
    ]
    spec["analysis"]["test"] = "시나리오 단위 평균. H1 각 성분은 단일표본 단측검정, 정책 차이는 대응 단측검정. 시점의 양방향 선택은 2배 보정. 영분산·표본 부족은 p를 강제로 만들지 않음"
    spec["analysis"]["multiplicity"] = {"method": "Holm on joint claims", "family_size": 5, "alpha": 0.05}
    spec["analysis"]["confirmatory_family_change_from_original"] = "H1, RAG 공동개선, 시점 세 쌍의 공동개선이라는 다섯 주장에 맞춰 결합검정과 Holm 적용"
    spec["analysis"]["signed_G_role"] = "수축과 과도한 차이를 해석하는 방향 지표. 감소 자체가 개선이라는 주검정으로 쓰지 않음"
    spec["analysis"]["additional"] += ["R0/R1 G_available diagnostics", "FULL versus R1 error and regret", "stage-level error propagation"]
    spec["reference_solver"]["distance_uncertainty"] = "산업별 근접최적해 폭만 보지 않고 쌍별 Dstar와 G의 가능한 범위를 보수적으로 계산. G 부호가 해 선택에 따라 바뀌면 수렴 판정 유보"
    findings = [
        {"criterion": "제목과 원초록의 검증력", "problem": "R0는 기관별 추가정보가 없고 h는 위험상한으로만 반영돼 H1 식별 기회가 작을 수 있음", "fix": "기관별 정보가 모두 있는 FULL을 H1의 주 검사로 지정하고 원래 수리과제의 의미를 명시"},
        {"criterion": "논리성", "problem": "G 감소가0을 넘어 과도하게 달라지는 것도 개선으로 보일 수 있음", "fix": "배분 차이 벡터의 오차와 모형상 손실의 공동 개선으로 검정"},
        {"criterion": "실험 정합성", "problem": "세 단계 모두 비중 제출이면 계획·구성·검토 역할이 사라짐", "fix": "단계별 산출물과 오류 전달 기록 구체화"},
        {"criterion": "완결성", "problem": "코퍼스·gold 단위 및 해의 거리 불확실성 처리 부족", "fix": "검색 코퍼스 계약과 입력 동일성 진단, 기준거리 범위 검사 추가"},
    ]
    write_round(1, SOURCE, spec, findings, [
        "원초록의 전략적 이질성을 수리 과제의 관측 가능한 차이로 명확히 정의",
        "FULL에서 충분한 정보를 줘도 필요한 차이를 잃는지 H1 검사",
        "G 감소 대신 방향·크기를 포함한 쌍별 반응오차와 손실의 공동 개선 검사",
        "다섯 주장별 IUT 및 Holm 구조로 변경",
        "계획·최초배분·점검 산출물과 오류 전달 기록 구분",
        "검색 자료와 기준거리의 식별 가능성 점검 추가",
    ])


def round_two() -> None:
    previous = version_path(1)
    spec = deepcopy(load_json(previous))
    spec["data_contract"]["return_definition"] = "French12 value-weighted monthly total returns, percentage divided by100. Do not mix the existing auxiliary excess-return series or subtract risk-free returns silently."
    spec["data_contract"]["holdings_accounting"] = {
        "eligible_equity": "공식 보유표의 양의 평가액 보통주·상장 REIT·보통주 ADR·외국 보통주. 동일 발행인·동일 경제권리 중복 및 통화를 감사",
        "fixed_outside_scope": "현금·채권·우선주·펀드지분·파생상품·매핑 불가 주식 및 그 밖의 자산과 부채를 원래 항목대로 보존",
        "coverage": "V_FF12_mapped_eligible_equity / V_all_eligible_equity; SIC 누락 주식도 분모에 유지",
        "h": "각 FF12 산업의 매핑 주식 평가액 / 전체 매핑 주식 평가액",
        "q_NAV": "전체 매핑 주식 평가액 / 동일 보유표의 공식 순자산 NAV; 산업의 NAV 대비 노출은 q_NAV*w",
        "source_constraint_denominator": "각 규칙의 원문 분모 D_j를 별도 보존. NAV를 총자산·순자산+차입 등과 바꾸지 않음",
        "reconciliation": "보유표 가치·현금·기타자산·부채를 NAV에 대조하고 평가일·통화·분모 불일치를 해결. 주식 비중 q를 임의로0~1에 자르지 않음",
        "SIC_source_priority": ["해당 시점 공식 공시의 발행인 SIC", "동일 발행인 식별자를 연결한 SEC 공식 자료", "사전 지정 공식 보완자료"],
        "unresolved_policy": "누락 SIC와 지분 중복을 기록. 분류율90% 미달, 불완전 보유표, 분모 불일치 또는 부적격 h이면 네 펀드 본실험 시작을 보류. AI 결과를 보고 펀드·날짜를 대체하지 않음",
        "risk_scope": "h.T@Sigma@h는 재배분하는 주식 부문의 FF12 대리 위험. 고정자산·해외·환율과의 공분산을 포함한 전체 펀드 위험이 아님",
    }
    spec["data_contract"]["constraint_translation"] = [
        {"class": 1, "rule": "FF12 비중만으로 정확히 계산 가능한 명시 규칙", "handling": "수리 제약으로 사용하고 근거·분모·계수를 저장"},
        {"class": 2, "rule": "고정 보유분과 원문 분모를 합치면 정확히 계산 가능한 규칙", "handling": "각 D_j로 q_Dj*w와 고정 분자를 결합. 산업 바구니별 소속·계수가 확인될 때만 검사"},
        {"class": 3, "rule": "blue-chip·발행인·유동성·통화 등 FF12로 판정 불가한 규칙", "handling": "의미 해석과 수치검증 불가를 기록. 원문을 잘 읽었다는 이유로 실제 준수 판정 금지"},
    ]
    spec["data_contract"]["starting_holdings_gate"] = "B의 모든 h는 사전 명시된 수리 제약을 만족해야 한다. 불일치는 예외·분모·시점·매핑부터 감사하며 위험상한 확대나 비중 수선으로 해결하지 않는다. 해결 전 요청하지 않는다."
    spec["retrieval"]["B_fixed_corpus"] = {
        "per_fund_scenario_documents": [
            {"id": "forecast_memo", "content": "가상임을 표시한 현재 펀드 전망. 12개 산업별 x값·단위·기준일과 r 및 Omega 규칙, 근거 ID"},
            {"id": "method_note", "content": "관측 오차와 정밀도의 뜻 및 공통 y와의 관계. 전망 수치의 새 복사본을 만들지 않음"},
            {"id": "fund_facts", "content": "감사된 h·의무 과제·적용 제약의 원문 근거. 의무 조건은 검색과 무관하게 모든 군이 이미 받음"},
        ],
        "current_forecast_count": 1,
        "no_invented_distractors": True,
        "number_placement": "forecast_memo에12행을 고정 산업순서로 둔다. 단위·날짜·관측정밀도를 숫자와 함께 유지하고 청크 경계가 행을 자르지 않음",
        "large_atomic_block": "필수 표가400모델토큰을 넘으면 머리글·정밀도를 반복한 산업행 블록으로 분할. 길이·중복 gold를 기록하며 개발 후 규칙 고정",
        "gold_units": "12개 산업 관측 각각 및 그 해석에 필요한 단위·날짜·정밀도. 동일 사실 중복은 회수율 분모에서 한 번만 계산",
        "query_stays_fixed": True,
        "FULL": "같은 세 문서의 적격 원문 전체. 모델 입력에 실제·가상 문서의 역할을 명시",
        "nonidentification": "R1 검색 결과가 FULL과 실질적으로 같은 경우 검색 대 전체원문 차이는 식별되지 않음. 시점 비교와 근거 없음 비교는 유지",
    }
    spec["modules"]["A"]["tools"] = ["합계·분산·검사 가능한 제약 계산기", "문서 사실과 출처 추적"]
    spec["modules"]["C"]["tools"] = list(spec["modules"]["A"]["tools"])
    for key in ["A", "C"]:
        spec["modules"][key]["forbidden"] = ["정성 전망을 xi·r로 임의 변환", "B의 사후분포 도구로 실제 전망의 수치 정답 생성", "최적비중 오차나 후회손실의 실제기관 정답 주장"]
        spec["modules"][key]["evaluation"] = ["사실·단위·날짜·귀속", "검사 가능한 명시 제약", "설명과 원비중 일치", "실패 전파와 공동오류", "검색 회수와 비용"]
    spec["modules"]["C"]["new_document_rule"] = "추가 전망은 A의2026-03-31 상한 이후 처음 공개되고 C의2026-06-30 상한 안에 공개된 문서. 계속 유효한 기존 의무 규칙은 기본정보로 유지하되 새 전망 회수 성과로 세지 않음"
    spec["workflow"]["tools_by_module"] = {"B": ["posterior(exposed_evidence_ids)", "check_portfolio(raw_weights,exposed_evidence_ids)"],
                                                   "A_C": list(spec["modules"]["A"]["tools"])}
    spec["execution_policy"] = {
        "all_attempts_primary": True,
        "effective_allocation": "w_policy = final_raw_w if finite complete vector passes all prespecified allocation constraints, otherwise h",
        "fallback_meaning": "제안이 실행 불가능하면 거래하지 않고 기존 보유를 유지. 원응답 정규화·수선·최적해 대체가 아님",
        "fallback_feasible_before_model": True,
        "stages": {
            "planning_schema_failure": "원응답과 오류를 보존하고 해당 궤적은 중단해 h 유지",
            "stage2_schema_or_incomplete_vector_failure": "보존 후 해당 궤적 중단해 h 유지",
            "stage2_complete_vector_math_failure": "원비중과 실제 계산 피드백을 그대로3단계에 전달; 원래 허용된 최종 점검에서만 수정 기회",
            "final_failure": "원응답 보존, 실패로 계상, h 유지; 최종 뒤 추가 수정 호출 없음",
            "source_or_explanation_error": "비중이 기계적 제약을 만족하면 원비중은 보존하되 별도 사실·설명 오류로 기록. 투자판단의 경제적 진실을 자동 통과시키지 않음",
        },
        "report_separately": ["모델 최종 원비중", "유효 여부와 실패 유형", "h 유지 여부", "정책 실행 비중", "유효 원출력에 조건부인 진단"],
        "H1_attribution": "FULL의 전체 업무정책 수축·손실과 유효 원출력 진단을 분리. fallback에서 생긴 수축을 모델이 제안한 전략 수축으로 부르지 않음",
        "failure_recommendation_rule": "공동 개선 검정과 별도로 관측 원출력 실패율·h유지율이 비교군보다 높아진 정책은 권고 보류. 비유의성으로 실패율 동등성을 선언하지 않음",
    }
    spec["evaluation"]["allocation_for_primary_metrics"] = "모든 시나리오·펀드·두 반복의 w_policy. 원출력 무효 답도 h 유지로 전체 정책 평가에 포함"
    spec["evaluation"]["invalid_policy"] = "무효 원응답을 성공으로 바꾸지 않으며 raw 지표는 NA. 사전 정의된 h 유지 정책의 지표를 별도 계산하고 전체 시도에서 평가"
    spec["analysis"]["matched_validity"] = "H1 H2 H3의 전체 정책 분석은 네 펀드와 두 반복의 모든 사전 시나리오를 포함. 유효 원출력만의 하위 분석을 주효과로 대체하지 않음"
    spec["analysis"]["valid_only_estimand"] = "별도 진단만. 유효 원출력에 조건부인 결과이며 전체 정책 또는 모든 모델 시도에 대한 효과가 아님"
    spec["analysis"]["H1_attribution"] = "주검정은 FULL 업무정책 전체의 기준 대비 수축과 손실. 유효 원출력 쌍과 fallback이 개입한 쌍의 비중·수축·손실 기여를 함께 보여 주고 직접 모델 판단의 증거와 구분"
    spec["reference_solver"]["near_optimal_component_width_max_for_distance_metrics"] = None
    spec["reference_solver"]["nonunique_policy"] = "산업별1%p는 원설계 진단값으로만 기록. 사례를 조용히 삭제하지 않고 근접최적집합의 거리 범위를 보존하며 주결론에는 보수적 경계를 사용"
    spec["reference_solver"]["uncertainty_bounds"] = {
        "representative": "각펀드 full/available의 동일한 대표해 v를 모든 정책에 재사용",
        "coordinate_ranges": "mu.T@w>=f_primal-epsilon의 근접최적집합에서 각좌표 l,u. epsilon과 검증된 primal-dual gap을 기록",
        "eta": "eta_i=0.5*sum_k(max(v_ik-l_ik,u_ik-v_ik)); any admissible reference is within eta_i in TV",
        "Dstar_interval": "[max(0,Dstar_point-eta_i-eta_j),min(1,Dstar_point+eta_i+eta_j)]",
        "G_interval": "Dstar_interval minus observed policy distance D",
        "E_interval": "[max(0,Epoint-eta_i-eta_j),min(2,Epoint+eta_i+eta_j)]",
        "A_interval": "A=|G|; lower is distance of G interval from zero, upper is max absolute endpoint",
        "policy_difference_upper": "U(E_A)-L(E_B) and U(A_A)-L(A_B) upper-bound the true A-minus-B difference. Use these conservative scenario differences in decrease tests",
        "regret_difference": "same full objective gives R_A-R_B=mu_full.T@(w_B-w_A); independently verify without subtracting two approximate fstar values",
        "absolute_regret_bounds": "use independently verified primal feasible objective and dual bound to bound absolute regret; do not call float noise positive loss",
        "H1_test_inputs": "scenario averages of lower G and lower absolute regret; positive inference must survive reference uncertainty",
        "failure": "solver/coordinate-range failure is evaluator failure, not model failure; resolve before first main request. Post-output evaluator defect requires declared global reanalysis, never replacing unfavorable scenarios",
    }
    spec["reference_solver"]["distance_uncertainty"] = "uncertainty_bounds에 따라 G뿐 아니라 E와 |G| 및 정책 차이의 가능한 범위를 평가. 승자가 경계에 따라 바뀌면 확증 판정 유보"
    spec["evaluation"]["A_full"] = "mean over scenario-replicate-pairs of |G_full|; never abs(mean signed G)"
    spec["evaluation"]["H1_rule"] = "FULL 전체 업무정책의 lower G_available와 lower R_available가 양수인지 결합검정. 유효 원출력과 fallback 기여를 분리하여 원출력 없는 정책수축을 모델 전략으로 해석하지 않음"
    spec["evaluation"]["improvement_rule"] = "R0의 양의 수축, E_full 감소, R_full 감소, mean|G_full| 감소를 모두 H2 결합검정에 포함. 기준 불확실성 경계와 전체 시도 정책으로 판정"
    spec["analysis"]["confirmatory_tests"] = [
        {"id": "H1", "contrast": "FULL policy versus full/available reference", "components": ["lower G_available > 0", "lower R_available > 0"], "p": "max of component one-sided p values", "label": "충분한 정보 아래 공통 AI 업무정책의 수축과 손실"},
        {"id": "H2", "contrast": "R1 policy minus R0 policy", "components": ["R0 lower G_full > 0", "upper delta E_full < 0", "exact delta R_full < 0", "upper delta mean|G_full| < 0"], "p": "max of component one-sided p values", "label": "추가정보 제공을 포함한 RAG 정책의 과잉수렴 완화"},
        *[{"id": f"H3_{a}_{b}", "contrast": f"{a} policy versus {b} policy", "components_per_direction": ["comparison baseline lower G_full > 0", "upper delta E_full < 0", "exact delta R_full < 0", "upper delta mean|G_full| < 0"],
           "p": "directional IUT p=max(components); two-direction claim p=min(1,2*min(p_a_better,p_b_better))", "label": "시점 정책의 완화 우위"} for a, b in [("R1", "R2"), ("R1", "R3"), ("R2", "R3")]],
    ]
    spec["analysis"]["non_testable_policy"] = {
        "reasons": ["식별 가능한 기준 차이가 없음", "검증된 기준 경계를 계산 못함", "영분산 등으로 표본검정 불가", "예정 시나리오 또는 r층 누락", "미완료 실행으로 계획 표본 불충족"],
        "Holm": "not_testable 표시와 함께 구현상 p=1을 넣어 최초 다섯 claim family 유지. 검사 가능한 주장만 남겨 보정 수를 줄이지 않음",
        "incomplete_main": "원래 목표60시나리오와 세r층 및 두반복 완결 전 확증 분석으로 종료하지 않음. 자원 문제로 미완료이면 기술 결과만 보고",
        "reduced_N": "본실험 시작 전 개발자료·자원 근거로만 개정하고 민감도·비용·분석을 재동결. 결과의 유의성을 보고 증원·감축 금지",
    }
    spec["analysis"]["aggregation_order"] = "각 scenario×replicate에서 네펀드의 E,G,|G|,regret을 먼저 계산해 집계한 후 두 반복 평균. mean|G|는 절댓값 후 집계"
    spec["runtime_and_failure_contract"] = {
        "model_selection": "개발자료의 전체 이력 수용·구조화/도구 지원·시간·자원으로 선택. RAG 승리나 수렴 방향으로 선택하지 않음",
        "freeze_fields": ["실제 model snapshot/hash", "양자화와 chat template", "모듈별 도구 schema", "tokenizer/context", "temperature and supported seed or unsupported marker", "output cap", "two tool roundtrips per stage", "request timeout", "engine and API revision"],
        "infra_retries": {"eligible": ["429", "5xx", "connection timeout before any content response"], "max_retries": 2, "same_request_bytes": True, "client_auto_retry": False, "backoff_seconds": [2, 4], "respect_retry_after": True},
        "non_retry_failures": ["output truncation", "JSON/schema error", "weight/constraint failure", "refusal", "tool limit failure", "citation or semantic error"],
        "partial_stream": "내용이 일부 도착한 응답은 보존하고 incomplete 출력으로 계상; 유리한 재생성으로 교체하지 않음",
        "version_drift": "다른 반환모델·template·도구 버전이면 실행 중단. 이미 완료한 비교와 새 버전을 혼합하지 않고 재개 가능한 동일 snapshot 여부부터 확인",
        "balanced_order": "시나리오 안에서 펀드·조건·반복의 순서를 고정 seed로 균형화. 각 궤적 내부1→2→3 의존은 유지",
        "actual_calls": "각 시도·재시도·tool call·잘림과 elapsed usage를 기록. 논리 슬롯과 실제 요청 수를 구분",
    }
    spec["analysis"]["sample_precision_plan"] = {
        "target": "원안60개의 독립 생성 시나리오, r별20, 두반복 유지",
        "pilot_report": "개발12상황의 시나리오 대응차이 분산과 원출력 유효율, 참조 경계 폭, 토큰·지연으로 여러 효과크기의 검출가능성과 CI폭·비용을 계산",
        "no_guarantee": "파일럿 효과 방향은 목표 효과나 모델 선택 기준이 아님. 60이라는 숫자만으로 검정력을 보장하지 않음",
        "replanning": "새 결합검정·보정계열에 맞게 민감도를 갱신한 뒤 본실험 전에 N과 실행환경을 동결",
    }
    findings = [
        {"criterion": "완결성", "problem": "유효 원출력만 남기는 주분석은 실패가 많은 정책을 유리하게 만들 수 있음", "fix": "유효하면 원비중, 무효면 h 유지라는 전체 시도 정책과 raw 실패 진단 분리"},
        {"criterion": "논리성", "problem": "기준해 폭과 |G| 경고만으로 완화 판정이 닫히지 않음", "fix": "G E |G|와 정책 차이의 보수적 범위, 네 성분 결합검정, 검정불능 p=1 규칙"},
        {"criterion": "실험 정합성", "problem": "90% 분모·주식범위·제약·부적격 h와 A/C 도구가 미정", "fix": "보유 회계식과 제약3분류, B 전용 사후분포와 A/C 실제문서 도구 분리"},
        {"criterion": "제목과 원초록의 검증력", "problem": "오류 탈락·새문서 중복·불완전 실행이 주제를 검증한 것처럼 보일 위험", "fix": "계획 표본 전체정책·진짜 신규 전망 분할·미완료시 확증 유보·세부 실행 계약"},
    ]
    write_round(2, previous, spec, findings, [
        "실행 불가 시 기존 보유 유지 정책으로 전체 시도를 주분석에 포함하고 원출력과 구분",
        "기준배분의 불확실성을 G E |G| 및 정책 차이까지 전파",
        "과잉수렴 완화에 필요한 네 조건을 결합검정으로 닫음",
        "검정불능·입력/평가기 오류·실행 미완료의 처리 확정",
        "보유 분류율과 h q 분모, 공식 제약의 검사 가능 범위 명시",
        "B 코퍼스3문서 구조와 A/C의 실제문서 도구·시간분할 확정",
        "원설계의 인프라 재시도와 실행버전·도구 계약 복원",
        "파일럿 기반 표본 정밀도·시간·비용 점검과 사전 동결 규칙 추가",
    ])


def round_three() -> None:
    previous = version_path(2)
    spec = deepcopy(load_json(previous))
    spec["evaluation"]["primary_mitigation_endpoints"] = {
        "prerequisite": "비교 기준 정책의 양의 G_full",
        "comparison_endpoints": ["쌍별 반응오차 E_full", "모형상 기대수익 손실 R_full", "절댓값 후 집계한 mean|G_full|"],
        "claim_rule": "prerequisite와 세 개선 방향을 모두 성분으로 넣는 IUT; 최종 Holm 보정과 실패율 권고 보류 규칙도 적용",
    }
    spec["reference_solver"]["near_optimal_set"] = "각 검증된 primal feasible 목적값 f_primal에 대해 mu.T@w>=f_primal-epsilon. epsilon=1e-9와 별도 primal-dual gap을 기록하고 uncertainty_bounds에만 따라 거리 범위 계산"
    spec["reference_solver"]["canonical_definition"] = "near_optimal_set 및 uncertainty_bounds가 유일한 실행 정의. 대표해 fstar 단독 허용치나 산업별1%p로 다른 제외 규칙을 만들지 않음"
    spec["reference_solver"]["uncertainty_bounds"]["E_interval"] = "[max(0,Epoint-eta_i-eta_j),Epoint+eta_i+eta_j]; do not cap at2 when raw sum has a disclosed engineering residual"
    spec["execution_policy"]["scope"] = "B 주분석의 수리 제약을 만족하는 h에 적용. A C에서는 검사 가능한 조건과 수치검증 불가 조건을 분리하며 h유지가 전체펀드 규정 준수의 증명은 아님"
    spec["counterfactual_contract"] = {
        "role": "원초록의 개별 정보 변화에 대한 반응 평가",
        "scenarios": 60, "seed": 3001, "arms": ["R1", "R3", "C-context"], "replicates": 2,
        "target_assignment": "각 r층20시나리오 안에서 F01 F02 F03 F04를 각5번 배정; 총60시나리오에서 각펀드15번. 순서는 seed로 고정",
        "hold_fixed": ["theta", "y", "h", "Sigma", "m0", "V0", "Omega0", "r and Omegai", "모든 의무 제약", "다른 펀드 x", "문서 양식과 날짜·단위", "모델과 도구 및 근거 최초 제공 단계"],
        "change": "선택한 한 펀드의 epsilon_i만 동일 분포 N(0,Omegai)에서 독립 재추출해 xi_b=theta+epsilon_i_b 생성",
        "logical_identifiers": "모델이 보는 문서·근거의 논리 ID와 형식은 유지하고 값만 바꿈. 새 버전 해시는 평가·보관 manifest에 기록",
        "reference_and_retrieval": "새 xi로 정답표·full/available 기준·원문을 다시 만들고 동일 BM25로 실제 재검색. 매 시점 비교 안에서는 새 패킷을 R1 R3에 일치시킴",
        "matched_execution": "원래 x의 기존 본실험 궤적을 재사용하고 교체 x는 독립 초기상태부터 실행. 같은 모델 반복끼리 짝지어 변화량을 비교",
        "measurement": "0.5*L1((w_policy_b-w_policy_a)-(wstar_b-wstar_a)); raw 유효진단과 fallback 변화도 별도",
        "retrieval_interpretation": "회수 근거가 같으면 제공 정보 변화에 대한 반응. 회수 집합·정밀도가 달라지면 검색을 포함한 전체 경로 반응으로 구분",
        "zero_reference_change": "기준 변화가0인 짝도 보존; 모델 변화가 클수록 좋은 것으로 판정하지 않음",
        "no_outcome_selection": True,
    }
    spec["negative_control_contract"] = {
        "role": "같은 판단 조건에서 식별자만 바뀌어 불필요한 차이가 생기는지 진단",
        "scenarios": 8, "seed": 4001, "arms": ["R1", "R3", "C-context"], "replicates": 2,
        "precision_assignment": "0.5 1 2 순서로 여덟 상황에 순환 배정; 네 라벨 안에서는 항상 같은 r",
        "profile_selection": "감사된 네 펀드 보유상태를 사전 순환해 여덟개의 기초 프로필을 만들되 각 상황에서는 한 프로필을 네 가상 라벨에 똑같이 복제",
        "copy_identically": ["h and risk cap", "연구목표와 의무 수리 제약", "Sigma m0 V0 Omega0", "y x r Omegai", "문서값·날짜·단위·길이·순서", "FULL 집합", "검색 결과와 근거 텍스트", "도구 정책과 sampler"],
        "only_difference": "비식별 가상 라벨; 라벨 정규화 뒤 모든 모델 입력과 도구 접근목록 해시가 같아야 함",
        "virtual_labels": ["N01", "N02", "N03", "N04"],
        "forbidden": "가상 복제조건에 실제 펀드별 fund_facts나 보유·목표를 다시 주입하지 않음",
        "oracle_identity": "동일 입력의 같은 canonical 기준해를 복제하므로 Dstar_point=0, Gpoint=-D<=0. 근접최적집합 범위도 함께 기록",
        "interpretation": "관측 D는 라벨 또는 생성 변동의 크기. 비중이 달랐다는 사실만으로 경제적 오류를 선언하지 않고 손실과 기준 불확실성을 확인",
    }
    spec["runtime_and_failure_contract"]["terminal_statuses"] = {
        "model_output_failure": "실제 요청 후 형식·계산·한도 등의 실패로 궤적 종료; h 유지로 전체 정책에 포함",
        "operational_failure": "허용된 동일 요청 재시도까지 소진한 인프라 장애; h 유지로 전체 정책에 포함하며 모델 의미·수치 실패와 별도 계상",
        "not_attempted": "아직 요청하지 않은 슬롯; h로 채우지 않으며 계획 표본 완료 전 확증결론 유보",
        "protocol_violation": "잘못된 모델·입력·버전으로 호출한 기록은 보존하되 예정된 처리의 결과로 합산하지 않음. 해당 동결 조건의 슬롯은 미완료로 남기고 실행 중단·정정 이력 기록",
        "parent_failure": "앞 단계의 최종 실패로 후속 요청을 생략한 궤적은 종료된 한 업무 실패이며 별도 미실행 표본으로 중복 계상하지 않음",
    }
    spec["analysis"]["completion_unit"] = "scenario×fund×arm×replicate의 업무 궤적. 최종 원응답 또는 사전 정의된 실패·h 유지의 terminal status가 있으면 완료. 모든 단계가 호출돼야만 완료인 것은 아님"
    spec["analysis"]["non_testable_policy"]["incomplete_main"] = "모든 예정 업무 궤적에 terminal status가 있어야 확증 분석. 미요청·프로토콜 위반 슬롯을 h로 채워 완료 처리하지 않음. 원안60시나리오와 세r층·두반복을 완결"
    spec["analysis"]["H1_H2_relationship"] = "H1은 FULL의 충분정보 업무정책 수축, H2는 R0 대비 R1의 총 근거제공 정책효과다. 두 통과를 같은 실패경로의 교정 증거로 자동 연결하지 않음"
    spec["analysis"]["FULL_R1_bridge_diagnostic"] = {
        "prespecified_secondary": True,
        "check": "수치 근거·정밀도·의무조건이 같아 full/available 기준이 같은지와 실제 입력의 길이·순서·내용 차이를 확인",
        "same_information_different_presentation": "R1 FULL의 반응오차·손실·실패 차이를 기술적으로 보고해 검색을 통한 자료 정리의 가능성을 논의",
        "different_information": "정보 접근과 문맥 구성이 함께 달라진 총효과로 해석",
        "identical_inputs": "검색 대 전체원문 처치가 비식별임을 표시. 독립 생성 차이를 검색 효과로 주장하지 않음",
        "not_identified": "추가 조정검정 없이 H2가 FULL의 잔여 모델 오류를 직접 치료했다는 확증 주장 금지",
    }
    spec["result_interpretation"] = [
        {"when": "H1 통과, H2 통과", "say": "충분한 정보를 준 공통 AI 업무에서도 수축·손실이 관측됐고, 별도로 R0 대비 R1의 정보제공 정책은 완화 조건을 충족", "not_say": "RAG가 H1의 동일한 내부 원인을 치료함 또는 모델 공유 자체가 원인임"},
        {"when": "H1 통과, H2 미통과", "say": "충분정보 업무정책의 문제는 확인됐으나 사전 지정 RAG 정책의 완화는 확인하지 못함"},
        {"when": "H1 미통과, H2 통과", "say": "정보가 부족한 R0 대비 RAG 정책의 수축·손실 완화가 확인됨. 충분정보하 모델의 잔여 수축은 확인하지 못함"},
        {"when": "두 주장 미통과", "say": "이번 과제에서 문제 또는 완화의 확증 근거를 확보하지 못함. 효과 없음·동등성으로 단정하지 않음"},
        {"when": "오차·손실만 감소하거나 거리만 증가", "say": "품질 개선 또는 배분 차이 변화의 보조 결과. 네 성분 완화 판정을 대신하지 않음"},
        {"when": "H3의 특정 쌍 통과", "say": "검정한 두 시점 정책 안에서의 완화 우위. 비교하지 않은 R0 우위나 보편적 최적 시점으로 확대하지 않음"},
        {"when": "fallback이 수축·손실 대부분에 기여", "say": "제안 실패 후 보유를 유지하는 전체 업무정책의 결과. 모델이 직접 유사한 비중을 제시한 것과 구분"},
        {"when": "식별 기회·검정 가능성·실행 완결 부족", "say": "이유와 분모를 공개하고 해당 주장 판정 유보"},
    ]
    spec["recommendation_rule"] = "사전 지정 해당 비교의 완화 결합검정과 최종 보정을 통과하고 관측 실패·h유지율이 비교군보다 높지 않을 때 그 비교 범위에서만 권고. 실패율의 통계적 동등성이나 모든 정책 중 최선으로 확대하지 않음"
    spec["source_to_design_crosswalk"] = [
        {"abstract_element": "공통 AI와 전략적 이질성·판단품질", "design": "FULL H1, 전체정책과 원출력 진단, E G regret 제약 실패"},
        {"abstract_element": "실제4펀드·12산업·기존보유 대비 변경", "design": "감사된 h와 q, FF12, 원비중과 w-h"},
        {"abstract_element": "공통 시장과 펀드별 추가 전망·수리 기준", "design": "B의 y xi 정규 생성, full/available 분산상한 최적화"},
        {"abstract_element": "계획·배분구성·점검의 검색 근거 배치", "design": "세 stage contract, 실제 BM25와 동일 패킷의 R1 R2 R3 재생"},
        {"abstract_element": "추가근거 없음과 전체적격 원문 대조", "design": "R0 및 FULL, H2와 FULL R1 보조 연결"},
        {"abstract_element": "개별 정보변화 반응", "design": "x교체 계약과 원래 예산1080단계"},
        {"abstract_element": "실제문서 정확성·공동오류·새문서 검색", "design": "A 실제문서, 보류한 C의 신규 전망과 실제 재검색"},
        {"abstract_element": "검색·실행 비용과 설계 원칙", "design": "호출·토큰·시간·실패·근거 전달 기록과 비교별 제한된 권고"},
    ]
    spec["design_vs_execution"] = {
        "design_review": "정합성·논리성·원주제 검증력·완결성에 대해 검토 뒤 개선을 세 차례 수행",
        "implementation_pending": ["실제4펀드 공식 원문과 전체 보유 추출", "SIC 매핑·분류율·제약 사람 감사", "B 생성기와 기준평가기 구현·검산", "검색 색인·로그·정보경계", "세단계 실행기와 파일럿", "모델·문맥·예산·표본의 실행 전 동결"],
        "unknown_until_run": ["과잉수렴 존재", "RAG 완화 여부", "좋은 제공 시점", "실패율", "실제 토큰·시간·비용"],
        "no_new_experimental_model_calls": 0,
    }
    findings = [
        {"criterion": "실험 정합성", "problem": "v6.1의두지표 필드와 v6.2의네성분 검정, 근접최적집합 정의가 중복", "fix": "유일한 평가 계약으로 통일"},
        {"criterion": "논리성", "problem": "H1과H2를 같은 오류의 교정으로 연결하거나 시점 쌍 우위를 전체 최적으로 확대할 위험", "fix": "결과별 허용 결론·금지 결론과 FULL R1 보조진단을 사전 규정"},
        {"criterion": "제목과 원초록의 검증력", "problem": "정보교체·동일정보 대조는 예산만 있고 생성 계약이 미완성", "fix": "무엇을 고정·교체·복제하는지와 oracle·검색 재실행을 확정"},
        {"criterion": "완결성", "problem": "재시도 소진, 앞단계 실패와 미요청 슬롯의 경계가 모호", "fix": "완료 단위를 업무 궤적으로 정의하고 terminal status별 집계 확정"},
    ]
    write_round(3, previous, spec, findings, [
        "지표·근접최적집합·검정 계약의 잔존 이중정의 해소",
        "개별 전망 교체와 완전 동일정보 음성대조의 구체 실행 계약 완성",
        "인프라 실패·모델 실패·미실행·프로토콜 오류의 구분과 완료 단위 확정",
        "H1 H2 H3별 결과 해석과 제한된 권고 규칙 확정",
        "원초록의 모든 실험 요소에 대한 대응표 작성",
        "처음 읽는 사람을 위한 bullet 설명과 설계 완료·실행 전 상태 분리",
    ])
    render_novice(spec)


def render_novice(spec: dict) -> None:
    outline = [
        ("무엇을 알아보는 실험인가", [
            "같은 AI를 쓰는 서로 다른 펀드가, 각자의 조건상 달라야 할 투자판단까지 비슷하게 만드는지 확인한다.",
            "펀드별 자료를 실제로 검색해 제공하는 RAG를 어느 업무 단계부터 쓰면 필요한 차이와 판단 품질이 함께 좋아지는지 비교한다.",
            "비슷한 답이 항상 나쁜 것은 아니다. 정보와 제약상 달라야 하는 경우에만 그 차이를 보존했는지 묻는다.",
        ]),
        ("누구의 어떤 자산을 대상으로 하나", [
            "미국 액티브 주식형 펀드4개인 Fidelity Contrafund FCNTX, Vanguard PRIMECAP VPMCX, Dodge & Cox Stock DODGX, T. Rowe Price Blue Chip Growth TRBCX를 사용한다.",
            "공식 전체 보유자료를12개 산업으로 분류하고, 분류 가능한 주식 부문만 재배분한다. 현금·채권·분류하지 못한 자산 등은 원래 상태로 남긴다.",
            "원초록의12개 산업은 French12 분류다. 기존 Fidelity·UBS 공개전망 실험의11개 산업과 섞지 않는다.",
        ]),
        ("실제 자료와 가상 자료를 어떻게 쓰나", [
            "실제 공시에서 펀드의 보유상태와 확인 가능한 운용조건을 얻는다. 공개자료와 보유자료의 시점·분모·분류율을 먼저 감사한다.",
            "통제실험에서는 모두가 보는 시장 전망과 펀드마다 다른 추가 전망을 숫자 생성기로 만든다. 추가 전망은 가상 자료라고 분명히 표시한다.",
            "서로 다른 정보를 주었을 때 어느 정도 다른 판단이 필요한지 계산하려고 가상 전망을 사용한다. 이를 실제 운용사의 비공개 전망으로 주장하지 않는다.",
        ]),
        ("무엇을 기준으로 잘했는지 판단하나", [
            "현재 주식 부문의 위험수준을 넘지 않으면서, 주어진 정보상 기대수익을 가장 크게 하는 기준배분을 별도 계산기로 구한다.",
            "각 펀드의 기준배분이 다르면 필요한 차이가 있는 것이다. 모델의 배분과 이 차이의 크기·방향, 기대수익 손실을 비교한다.",
            "기본 모형에서는 기존 보유상태가 위험예산과 변경분의 기준이다. 실제 펀드 전략 전체나 미래 수익의 정답을 복원하는 실험은 아니다.",
            "전체 허용정보를 다 쓴 기준과 AI가 실제로 받은 정보만 쓴 기준을 모두 계산해 정보 부족과 정보 활용 실패를 구분한다.",
        ]),
        ("모든 조건에서 같게 주는 것은 무엇인가", [
            "기본 운용목표, 현재 보유비중, 반드시 지킬 수리 제약, 공통 시장자료와 같은 계산도구는 처음부터 모두에게 준다.",
            "비중은 음수가 될 수 없고 합계가100%여야 한다. 위험예산도 지켜야 한다. 연구자가 실제 원문에 없는 펀드별 목표나 제약을 만들지 않는다.",
            "같은 모델·기본 지침·출력 형식·세 단계 업무를 유지한다. 추가 전망자료가 어느 단계부터 들어오는지가 주요 차이다.",
        ]),
        ("AI는 어떤 순서로 일하나", [
            "1단계 계획: 받은 자료의 뜻과 운용조건을 확인하고 어떤 근거로 판단할지 정리한다. 이 단계에서는 최종 비중을 요구하지 않는다.",
            "2단계 배분안 구성:12개 산업의 최초 비중과 현재 보유 대비 변경분, 그 근거를 제출한다.",
            "3단계 점검과 수정: 실제 계산 피드백과 근거를 대조하고 최종 비중을 확정한다. 어느 오류가 남거나 고쳐졌는지도 기록한다.",
        ]),
        ("다섯 조건을 어떻게 비교하나", [
            "R0: 추가 전망자료를 주지 않는다. 기본 운용조건과 공통 시장자료는 모두 받는다.",
            "R1: 계획 단계부터 검색한 추가자료를 준다.",
            "R2: 최초 배분안을 만드는 단계부터 같은 검색자료를 준다.",
            "R3: 최종 점검 단계부터 같은 검색자료를 준다.",
            "FULL: 전체 적격 원문을 계획 단계부터 준다.",
            "검색은 실제로 실행하고, R1·R2·R3에는 같은 검색결과를 사용한다. 한 번 받은 자료는 이후에도 유지한다.",
            "이 비교는 자료의 최초 도입과 이후 유지가 결합된 업무정책 비교다. 누적 노출을 제거한 순수 시간효과로 해석하지 않는다.",
        ]),
        ("RAG에서 실제로 검색하는 것은 무엇인가", [
            "통제실험의 검색 대상은 펀드별 가상 전망문서, 해석 방법 문서, 감사된 펀드 조건 문서다. 검색 점수·문단·원문 위치와 자료의 길이를 저장한다.",
            "자기 펀드와 공통 문서만 검색할 수 있다. 다른 펀드의 추가 전망이나 평가용 정답 비중은 접근할 수 없다.",
            "검색한 자료가 전체 원문과 같아지면 그 사실을 공개한다. 그 사례에서 검색이 전체 원문보다 우수하다고 주장하지 않는다.",
        ]),
        ("무엇을 개선 또는 완화라고 부르나", [
            "먼저 비교 기준에서 필요한 차이보다 실제 차이가 작은지 확인한다.",
            "그다음 필요한 차이의 방향·크기를 얼마나 잘 따라갔는지, 기준 대비 기대수익 손실이 줄었는지, 차이가 너무 작거나 너무 큰 정도가 함께 줄었는지 본다.",
            "이 조건을 모두 만족해야 과잉수렴 완화로 판정한다. 단순히 배분을 서로 다르게 만든 것만으로 성공이라고 하지 않는다.",
            "예를 들어 두 펀드의 올바른 배분을 서로 바꿔 주면 펀드 간 거리 자체는 같아도 각자에게 틀린 답이다. 새 평가에는 이 오류도 잡는 지표가 포함된다.",
            "검정은60개 시장상황을 단위로 하고, 다섯 주장에 대한 다중비교를 보정한다. 펀드 쌍이나 두 반복을 별도 독립 시장표본으로 세지 않는다.",
        ]),
        ("AI가 실행할 수 없는 답을 내면 어떻게 하나", [
            "최종 비중의 합계가 틀리거나 수리 제약을 어기면 원응답은 실패로 남긴다. 연구자가 정규화해서 성공한 답으로 바꾸지 않는다.",
            "전체 업무정책의 결과는 거래하지 않고 기존 보유를 유지한 것으로 계산한다. 이 안전장치가 만든 결과와 AI가 직접 제안한 결과를 따로 보여 준다.",
            "인프라 장애는 정해진 횟수의 같은 요청 재시도 뒤 운영 실패로 기록한다. 아예 요청하지 않은 실험을 보유 유지로 채워 완료 처리하지 않는다.",
        ]),
        ("자료를 실제로 사용했는지도 확인하나", [
            "같은 시장·보유·제약을 유지한 채 한 펀드의 추가 전망만 바꾸고 판단이 적절히 반응하는지 본다. 나머지 조건은 그대로 둔다.",
            "반대로 보유·목표·전망·문서·도구를 모두 같게 복제하고 이름표만 바꾸는 대조도 둔다. 차이가 필요하지 않은데 인위적 차이를 만들지는 않는지 확인한다.",
            "문서 내용의 정확성, 근거의 잘못된 귀속, 설명과 실제 증감의 모순, 여러 출력에 남은 같은 오류도 기록한다.",
        ]),
        ("가상 실험 뒤 실제 문서는 어떻게 확인하나", [
            "A에서는 네 실제 펀드의 공식 문서를 사용해 사실·제약 해석·설명과 비중의 일치를 확인한다.",
            "C에서는 개발에 쓰지 않은 다음 기간의 새 전망문서를 색인하고 실제 검색부터 다시 한다. 기존 규칙을 다시 찾은 것을 새 전망 검증으로 세지 않는다.",
            "실제 문서의 정성적 전망을 임의의 숫자로 바꾸지 않는다. A·C에는 가상 통제실험의 정답 비중이나 기대수익 손실 평가를 그대로 적용하지 않는다.",
        ]),
        ("어떤 결과가 나오면 무엇을 말할 수 있나", [
            "FULL에서도 필요한 차이와 품질을 잃으면 충분한 정보 아래의 공통 AI 업무정책 문제를 확인한 것이다. 제안 실패 후 보유 유지에서 생긴 부분은 따로 설명한다.",
            "R1이 R0보다 완화 조건을 통과하면, 정보가 부족했던 업무에 펀드 자료를 연결하는 RAG 정책의 효과를 확인한 것이다.",
            "두 결과가 모두 나와도 RAG가 FULL에서 발견한 동일 내부 원인을 고쳤다고 자동 결론 내리지 않는다. FULL과 R1의 실제 정보·문맥 차이도 함께 확인한다.",
            "시점의 우위는 실제로 검정한 비교 안에서만 말한다. 초기 제공이 언제나 최선이라고 미리 정하지 않는다.",
            "유의한 차이를 찾지 못하거나 기준 차이가 불확실하면 판정을 유보한다. 효과 없음이나 모든 정책이 같다고 단정하지 않는다.",
        ]),
        ("얼마나 실행하고 현재 어디까지 준비됐나", [
            "기본 목표는 독립적으로 생성한60개 시장상황, 네 펀드, 다섯 조건, 두 번의 실행이다. 공통 모델로 총2400개의 세 단계 업무를 수행한다.",
            "개발 파일럿·전망교체·동일정보 대조·실제문서 적용까지 원계획은9816개의 업무 단계다. 도구 왕복과 재시도 때문에 실제 모델 요청은 더 많을 수 있다.",
            "먼저 개발자료15단계, 네 펀드60단계, 전체 개발 파일럿 순으로 수행 가능성과 비용을 확인한다. 같은 버전의 완료 궤적만 재사용하고 실패·폐기 시도도 비용에 포함한다.",
            "본실험 전에 자료·검색·평가·모델·표본·비용 계획을 고정한다. 결과를 보고 표본이나 조건을 바꾸지 않는다.",
            "현재는 설계의 세 차례 검토와 개선을 완료했다. 실제4펀드 자료 구축, 새 검색·평가기·실행기와 파일럿은 다음 실행 전 작업이다. 새 본실험 결과는 아직 없다.",
        ]),
    ]
    esc = html.escape
    css = '''body{font-family:"Malgun Gothic",Arial,sans-serif;line-height:1.8;color:#18232c;background:#f5f6f7;margin:0;word-break:keep-all;overflow-wrap:anywhere}main{max-width:980px;margin:30px auto;background:#fff;padding:42px 50px}h1{font-size:28px;line-height:1.45;color:#000;margin:0 0 12px}.subtitle{font-size:17px}.meta{font-size:13px;color:#53606b}.outline{list-style:disc;padding-left:24px}.outline>li{margin:25px 0}.outline>li>b{font-size:19px;color:#000}.outline ul{padding-left:22px;margin-top:8px}.outline ul li{margin:8px 0}details{margin-top:28px;border-top:1px solid #d9d9d9;padding-top:16px}summary{font-weight:700;cursor:pointer}a{color:#19588a}code{font-size:12px;overflow-wrap:anywhere}.technical{font-size:14px}@media(max-width:700px){main{padding:24px 18px;margin:0}h1{font-size:24px}.outline>li>b{font-size:18px}}@media print{body{background:#fff}main{margin:0;padding:0;max-width:none}.outline>li>b{break-after:avoid}li{orphans:2;widows:2}}'''
    doc = f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LIBERA 최종 실험 설계 쉬운 설명</title><style>{css}</style></head><body><main>'
    doc += f'<p class="meta">2026년10월27일 · v6.3 · 검토와 개선3회 완료 · 실험 실행 전 설계</p><h1>{esc(spec["title"])}</h1><p class="subtitle">{esc(spec["subtitle"])}</p>'
    doc += '<ul class="outline"><li><b>세 차례 검토에서 무엇을 고쳤나</b><ul>'
    doc += '<li>1차: 제목과 실제 검사가 연결되도록 FULL의 충분정보 검사를 보강하고, 단순 거리 대신 필요한 차이의 방향·크기와 판단 손실을 함께 평가하도록 고쳤다.</li>'
    doc += '<li>2차: 실패한 답안을 제외하지 않는 전체 업무정책 평가, 기준배분 불확실성, 보유자료·실제문서·운영 실패 처리 계약을 완성했다.</li>'
    doc += '<li>3차: 전망교체와 동일정보 대조, 결론과 권고의 범위, 지표의 중복 정의를 정리하고 원초록의 모든 요소를 대응시켰다.</li></ul></li>'
    for heading, bullets in outline:
        doc += '<li><b>' + esc(heading) + '</b><ul>' + ''.join('<li>' + esc(b) + '</li>' for b in bullets) + '</ul></li>'
    doc += '</ul><details><summary>실행자용 수식과 판정 규칙</summary><ul class="technical">'
    technical = [
        "D=½||wi−wj||₁, Gfull=D*full−D, Gavailable=D*available−D. 양의 G는 기준보다 가까운 수축이다.",
        "Efull=½||(wi−wj)−(w*i−w*j)||₁는 필요한 차이의 방향과 크기를 함께 본다. A=mean|Gfull|는 쌍별 절댓값을 먼저 취한다.",
        "Rfull=μfullᵀ(w*full−w). 같은 기준의 정책 차이는 μfullᵀ(wB−wA)로 직접 검산한다.",
        "H1은 FULL 정책의 G와 R의 보수적 하한이 양수인지 검사한다. H2/H3의 방향별 완화는 비교 기준의 양의G와 E R A의 감소를 모두 요구한다.",
        "결합 p는 성분 단측p의 최댓값이다. 시점의 두 방향 선택은2배 보정하고, 사전 지정 다섯 주장에 Holm 보정을 적용한다. 검정불능은p=1을 유지한다.",
        "기준배분의 근접최적집합 좌표 범위로 전체 거리 오차를 보수적으로 계산한다. 이 불확실성 안에서 결론이 바뀌면 확증 판정을 유보한다.",
        "전체 정책은 최종 원비중이 유효하면 그대로, 무효면 h 유지다. 실패율과 원출력 조건부 진단을 별도로 보고한다.",
    ]
    doc += ''.join('<li>' + esc(t) + '</li>' for t in technical)
    doc += '</ul></details><details><summary>기존 자료와 최종 설정 파일</summary><ul class="technical">'
    doc += '<li><a href="' + esc(version_path(3).as_uri(), quote=True) + '">최종 실험 설정 JSON</a></li>'
    for source in spec["lineage"]:
        p = Path(source["path"])
        absolute = p if p.is_absolute() else ROOT / p
        doc += '<li><a href="' + esc(absolute.as_uri(), quote=True) + '">' + esc(source["path"]) + '</a> — ' + esc(source["role"]) + '</li>'
    doc += '</ul></details></main></body></html>'
    FINAL_HTML.write_text(doc, encoding="utf-8")
    save_json(WORK / "novice_outline.json", [{"topic": heading, "bullets": bullets} for heading, bullets in outline])
    reviews = [load_json(WORK / f"review_round{n}.json") for n in [1, 2, 3]]
    save_json(WORK / "review_history.json", {"cycles": reviews, "original_abstract_crosswalk": spec["source_to_design_crosswalk"], "execution_state": spec["design_vs_execution"]})
    history = f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LIBERA 실험 설계 검토와 개선 기록</title><style>{css}</style></head><body><main><h1>LIBERA 실험 설계 검토와 개선 기록</h1><p class="meta">2026년10월27일 · 원제목과 원초록 유지 · 순차 검토와 개선3회</p><ul class="outline">'
    for review in reviews:
        history += f'<li><b>{review["round"]}차 검토와 개선</b><ul>'
        for finding in review["findings"]:
            history += '<li><b>' + esc(finding["criterion"]) + '</b><ul><li>검토: ' + esc(finding["problem"]) + '</li><li>개선: ' + esc(finding["fix"]) + '</li></ul></li>'
        history += '</ul></li>'
    history += '<li><b>원초록과 최종 설계의 대응</b><ul>'
    for item in spec["source_to_design_crosswalk"]:
        history += '<li>' + esc(item["abstract_element"]) + ' → ' + esc(item["design"]) + '</li>'
    history += '</ul></li><li><b>설계 완료와 실행 준비의 구분</b><ul><li>세 번의 검토는 설계의 정합성과 해석 규칙을 개선한 것이며 독립적인 사람의 원문 감사나 본실험 실행이 아니다.</li>'
    for item in spec["design_vs_execution"]["implementation_pending"]:
        history += '<li>실행 전 작업: ' + esc(item) + '</li>'
    history += '</ul></li></ul></main></body></html>'
    (WORK / "review_history.html").write_text(history, encoding="utf-8")
    print(json.dumps({"explanation": str(FINAL_HTML), "topics": len(outline)}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, choices=[1, 2, 3], required=True)
    args = parser.parse_args()
    if args.round == 1:
        round_one()
    elif args.round == 2:
        round_two()
    else:
        round_three()


if __name__ == "__main__":
    main()
