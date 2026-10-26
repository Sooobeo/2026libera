"""Build a prospective LIBERA redesign from retained local source material.

No source file is modified and no retrieval or model experiment is executed.
Run with the managed Codex Python runtime, from the repository root.
"""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
PLAN = ROOT / "plan"
VERSION = "6.0-design"
JSON_OUT = PLAN / "LIBERA_실험설정_v6.0_20261027.json"
HTML_OUT = PLAN / "LIBERA_원설계복원_실험재설계_v6.0_20261027.html"
TITLE = "공통 GenAI는 기관투자자의 전략적 이질성을 축소하는가?"
SUBTITLE = "-액티브 주식형 펀드의 자산배분 프로세스 내 Workflow RAG 배치와 완화효과를 중심으로-"


def file_record(path: Path, role: str) -> dict:
    return {
        "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "role": role,
        "exists": path.is_file(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
    }


sources = [
    file_record(Path("C:/Users/Insun/Downloads/greengreen (1).pdf"), "원제목과 원초록 전체 2쪽 기준"),
    file_record(PLAN / "LIBERA_실험설계서0925.html", "A B C 구조와 4펀드 12산업 3단계 5조건 원설계"),
    file_record(PLAN / "문규리 제안서 상세_최종.html", "공통 GenAI와 부정적 동질화의 원래 연구 논리"),
    file_record(PLAN / "LIBERA_실험설정_20261017.json", "후속 축소 및 서로 다른 데이터 계열의 구분"),
    file_record(PLAN / "LIBERA_실험설정_v4.9.1_20261019.json", "직접 제공 E L 실험의 경계와 오류 보존"),
    file_record(ROOT / "data/documentary/source_inventory.json", "실제 4펀드의 신원과 공식 자료 후보"),
    file_record(ROOT / "data/french/manifest.json", "FF12 수익률 및 SIC 원본과 취득 해시"),
    file_record(ROOT / "data/institutional_recent/summary.json", "기존 24시장창 72가상위임의 정량 보조자료"),
    file_record(ROOT / "research/prepare_institutional_benchmark.py", "거리 반응오차 및 수치 검산 코드 재사용 후보"),
    file_record(ROOT / "data/sector_documents/corpus_card.json", "별도 GICS11 공개 전망 자료의 범위"),
    file_record(ROOT / "paper/LIBERA_소논문_원초록반영_v5.4_20261026.docx", "기존 원고와 완료자료 보존 대상"),
]
inventory = json.loads((ROOT / "data/documentary/source_inventory.json").read_text(encoding="utf-8"))
recent = json.loads((ROOT / "data/institutional_recent/summary.json").read_text(encoding="utf-8"))

funds = [
    {"fund_id": "F01", "ticker": "FCNTX", "name": "Fidelity Contrafund", "series": "S000006037"},
    {"fund_id": "F02", "ticker": "VPMCX", "name": "Vanguard PRIMECAP", "series": "S000002568"},
    {"fund_id": "F03", "ticker": "DODGX", "name": "Dodge & Cox Stock", "series": "S000011202"},
    {"fund_id": "F04", "ticker": "TRBCX", "name": "T. Rowe Price Blue Chip Growth", "series": "S000002069"},
]
arms = [
    {"id": "R0", "onset": None, "evidence": "no_additional_outlook"},
    {"id": "R1", "onset": 1, "evidence": "frozen_retrieved_packet"},
    {"id": "R2", "onset": 2, "evidence": "frozen_retrieved_packet"},
    {"id": "R3", "onset": 3, "evidence": "frozen_retrieved_packet"},
    {"id": "C-context", "alias": "FULL", "onset": 1, "evidence": "all_eligible_original_text"},
]
# Reader-facing Korean strings are kept separately from machine arm definitions.
arm_rows = [
    ["R0", "추가 근거 없음", "추가 근거 없음", "추가 근거 없음", "추가정보 부재 대조"],
    ["R1", "검색 근거 최초 제공", "같은 근거 유지", "같은 근거 유지", "계획부터 도입"],
    ["R2", "추가 근거 없음", "검색 근거 최초 제공", "같은 근거 유지", "배분 구성부터 도입"],
    ["R3", "추가 근거 없음", "추가 근거 없음", "검색 근거 최초 제공", "점검부터 도입"],
    ["C-context", "전체 적격 원문", "같은 원문 유지", "같은 원문 유지", "정보 접근 대조 FULL"],
]
for arm, row in zip(arms, arm_rows):
    arm["stage_view"] = row[1:4]

budget = [
    {"block": "B 본실험", "factors": [60, 4, 5, 2, 3], "purpose": "주 통제실험"},
    {"block": "개별 전망 x 교체", "factors": [60, 1, 3, 2, 3], "purpose": "R1 R3 C-context 정보반응"},
    {"block": "B 개발 파일럿", "factors": [12, 4, 5, 1, 3], "purpose": "본분석 제외"},
    {"block": "동일정보 음성대조", "factors": [8, 4, 3, 2, 3], "purpose": "R1 R3 C-context 인위적 차이 점검"},
    {"block": "A C 실제문서 적용", "factors": [2, 4, 5, 2, 3], "purpose": "현실자료 및 새 문서 검색 확인"},
]
for row in budget:
    count = 1
    for value in row["factors"]:
        count *= value
    row["logical_stages"] = count
total_stages = sum(row["logical_stages"] for row in budget)

spec = {
    "protocol_version": VERSION,
    "as_of_date": "2026-10-27",
    "status": "prospective_redesign_not_frozen_not_executed",
    "execution_enabled": False,
    "title": TITLE,
    "subtitle": SUBTITLE,
    "user_constraints": [
        "제목과 원초록의 연구 목적을 기준으로 본문과 실험을 맞춘다.",
        "기존 실험 설계와 준비된 데이터에서 출발한다.",
        "기존 원고 원응답 실행기록 수치와 과거 분석 역할을 덮어쓰지 않는다.",
    ],
    "design_basis": "0925 A B C 원설계 복원과 완료된 직접제공 실험의 실패 반영",
    "lineage": sources,
    "research_questions": [
        "RQ1 공통 LLM 사용 조건에서 기준상 필요한 펀드 간 차이가 줄며 판단 손실 또는 제약 위반을 동반하는가?",
        "RQ2 실제 검색한 펀드별 근거 제공이 필요한 차이와 판단 품질을 함께 개선하는가?",
        "RQ3 계획 배분안 구성 점검 중 근거의 도입 및 유지 정책에 따라 효과가 어떻게 달라지는가?",
    ],
    "modules": {
        "B": {"role": "primary_controlled_experiment", "funds": 4, "taxonomy": "French12", "industries": 12,
              "base_holdings": "실제 공시에서 구성할 h이며 현재 미구축",
              "additional_outlook": "가상임을 명시한 정규 생성 x이며 실제 펀드의 내부 전망이 아님",
              "oracle": "posterior_expected_return_max_under_holdings_variance_cap"},
        "A": {"role": "actual_document_application", "holdings_as_of": "2025-12-31", "publication_cutoff": "2026-03-31",
              "exact_weight_gold": False, "outcomes": ["source_facts", "applicable_constraints", "evidence_to_decision", "allocation_changes"]},
        "C": {"role": "held_out_document_retrieval", "holdings_as_of": "2026-03-31", "publication_cutoff": "2026-06-30",
              "rebuild_index_and_rerun_retrieval": True, "tuning_on_C_forbidden": True, "exact_weight_gold": False},
    },
    "data_contract": {
        "funds": funds,
        "development_holdings_as_of": "2025-09-30",
        "development_publication_cutoff": "2025-12-31",
        "numeric_reference_period": ["2016-01", "2025-12"],
        "numeric_observations": 120,
        "returns": "기존 French12 월간자료를 소수 수익률 단위로 통일",
        "taxonomy_boundary": "FF12 본실험과 GICS11 기존 공개전망 실험을 결합하지 않음",
        "holdings": "complete holdings; issuer SIC mapping; classifiable equity sleeve h; sleeve share q; fixed and unclassified assets retained",
        "classification_coverage_threshold": 0.90,
        "classification_threshold_basis": "0925の研究設定。LLM出力を見る前に分母と除外規則を固定",
        "constraint_policy": "공식 원문의 분모 예외 적용조건을 유지. 12산업 배분에서 평가 불가능한 규칙은 의미검사로 분리하며 숨은 산업상한을 만들지 않음",
        "vintage": "cached revised French data; retrospective controlled task, not authenticated historical-vintage trading replay",
    },
    "scenario_generator": {
        "status": "required_not_implemented_in_this_redesign",
        "historical_mean": "m0", "historical_covariance": "Sigma from 120 months with Ledoit-Wolf",
        "prior_covariance": "V0=Sigma/12", "common_error_covariance": "Omega0=V0",
        "private_error_covariance": "Omegai=V0/r", "precision_levels": [0.5, 1.0, 2.0],
        "generation": ["theta~N(m0,V0)", "y=theta+epsilon0", "xi=theta+epsiloni", "errors conditionally independent given theta"],
        "full_posterior": "Vi=(inv(V0)+inv(Omega0)+inv(Omegai))^-1; mui=Vi@(inv(V0)@m0+inv(Omega0)@y+inv(Omegai)@xi)",
        "visible_information_posterior": "Use only delivered observations and their disclosed precision. Partial x requires selection-matrix Gaussian update; missing precision cannot be filled from hidden metadata.",
        "atomic_document_fields": ["signal values", "industry codes", "unit", "date", "precision or covariance rule", "evidence IDs"],
        "rnd": {"algorithm": "PCG64 SeedSequence", "development": 1001, "main": 2001, "x_replacement": 3001,
                "negative_control": 4001, "execution_order": 5001, "human_audit": 6001, "bootstrap": 7001},
        "return_display_decimals": 10, "covariance_significant_digits": 12,
        "score_from_roundtripped_displayed_values": True,
        "no_future_theta_in_reference_or_tools": True,
    },
    "workflow": {
        "stages": ["계획", "배분안 구성", "점검과 수정"], "arms": arms,
        "common_to_every_arm_from_stage1": ["fund objective", "mandatory constraints", "holdings h", "risk cap h.T@Sigma@h",
                                           "common signal y", "Sigma", "m0", "V0", "Omega0", "industry universe", "same tools and output schema"],
        "treatment": "additional private-outlook evidence availability, onset and retention; never withhold mandatory mandates from R0",
        "estimand": "workflow adoption-and-retention policy, including cumulative exposure and self-generated history; not pure token-position or isolated timing effect",
        "independent_initial_state": True, "full_own_history_retained": True,
        "tools": ["posterior(exposed_evidence_ids)", "check_portfolio(raw_weights,exposed_evidence_ids)"],
        "tool_roundtrips_per_stage_max": 2,
        "calculator_cannot_return": ["reference weights", "optimal trades", "hidden xi", "theta", "other fund information", "semantic answer key"],
        "max_output_tokens_candidate_from_original": 2048,
        "output": ["12 unique industry rows", "raw weights", "changes from h", "evidence IDs", "short decision rationale", "declared revisions"],
        "direction_statement_check": "declarations of increase or decrease against h and previous valid submission; distinguish invalid predecessor",
        "post_final_repair": False, "automatic_normalization": False,
    },
    "retrieval": {
        "status": "required_not_executed",
        "engine_from_original": "BM25Okapi", "package_from_original": "rank-bm25==0.2.2",
        "k1": 1.5, "b": 0.75, "epsilon": 0.25,
        "chunk_max_tokens": 400, "chunk_overlap_tokens": 50, "top_k": 4,
        "tokenizer": "lowercase English letter-number tokens; chunk token counts use frozen model tokenizer",
        "query": "investment outlook expected return forecast uncertainty risk portfolio industry + fixed French12 industry names",
        "scope": "common corpus plus own fund eligible corpus; source-date and fund filters applied before ranking",
        "forbidden_corpus": ["theta", "reference allocation", "evaluator annotations", "other funds private outlook", "held-out documents before C"],
        "ties": "document ID then paragraph order", "dedup": "source hash and merged overlapping evidence",
        "preserve_atomic_numeric_rows_units_footnotes": True,
        "timing_comparison": "Run actual retrieval once per fund-scenario; freeze returned text order hashes scores and length; replay identical bytes to R1 R2 R3",
        "records": ["query", "corpus manifest", "eligible IDs", "scores", "ranked chunk IDs", "text hashes", "gold recall@4", "final packet token count"],
        "full_context": "all prespecified eligible original text; never silently truncate; flag identity with retrieved packet",
        "C_policy": "index unseen eligible documents and rerun the same retrieval policy; do not reuse old packets",
    },
    "reference_solver": {
        "status": "new_evaluator_required; old gamma-QP is not equivalent",
        "objective": "maximize mui.T@w", "constraints": ["w>=0", "sum(w)=1", "w.T@Sigma@w<=h.T@Sigma@h", "applicable prespecified explicit constraints"],
        "candidate": "CVXPY + Clarabel SOCP from 0925; runtime installation and lock pending",
        "independent_crosscheck": "separate constrained solve and feasibility/objective residual checks; do not reuse old quadratic KKT certificate as proof",
        "solver_gap_tolerance": 1e-9, "solver_feasibility_tolerance": 1e-9, "solver_max_iterations": 500,
        "output_sum_and_lower_tolerance": 1e-6,
        "risk_residual_tolerance": "max(1e-10,1e-6*h.T@Sigma@h)",
        "near_optimal_set": "mui.T@w>=fstar-1e-9; min/max each component",
        "near_optimal_component_width_max_for_distance_metrics": 0.01,
        "nonunique_policy": "keep value regret and failure counts; withhold allocation distance/G when near-optimal set is too wide; report exclusions",
        "references": ["full allowed fund information", "actually delivered information"],
        "meaning": "conditional solution to declared research task, not the fund manager's hidden optimum or future realized return",
    },
    "evaluation": {
        "D": "0.5*L1(wi-wj)", "D_star": "0.5*L1(wstar_i-wstar_j)", "G_full": "D_star_full-D",
        "G_available": "D_star_available-D",
        "information_set_distance_component": "G_full-G_available=D_star_full-D_star_available; signed, not necessarily positive",
        "full_regret": "mui_full.T@(wstar_full-w)",
        "available_regret": "mui_available.T@(wstar_available-w)",
        "individual_reference_error": "0.5*L1(w-wstar)",
        "pair_response_error": "0.5*L1((wi-wj)-(wstar_i-wstar_j))",
        "individual_information_response_error": "0.5*L1((wb-wa)-(wstar_b-wstar_a))",
        "always_report": ["raw budget residual", "risk and constraint failures", "transport/schema failures", "source errors and shared errors", "retrieval recall", "calls tokens latency"],
        "invalid_policy": "preserve every attempt; invalid allocation has no primary distance/regret; no normalization, zero-filling or favorable censoring",
        "improvement_rule": "positive G is brought toward zero while absolute G, reference error and information response do not contradict recovery; full regret jointly improves; observed constraint/failure rates do not worsen",
        "no_inferiority_equivalence_from_nonsignificance": True,
        "R0_interpretation": "full regret includes absent additional information; available regret separates implementation error from information loss",
        "H1_rule": "test R0 G_available against zero; positive corrected evidence plus observed available-information loss or constraint problems is interpreted as avoidable convergence under the common model. G_full alone cannot establish it.",
        "identifiability": "report D_star_available=0 or numerically unresolved pairs as having no identified positive contraction opportunity; do not select cases by model outcomes",
        "oracle_diagnostic": "using available oracle as model output must yield G_available=0 and R_available=0 even if G_full and R_full are positive",
    },
    "analysis": {
        "main_scenarios": 60, "precision_strata": 3, "scenarios_per_stratum": 20, "funds": 4, "replicates": 2,
        "sample_size_role": "0925 original planning target retained; not a measured power guarantee; revise before main only if resource feasibility requires",
        "independent_unit": "generated scenario, conditional on fixed calibrated market and fund profiles",
        "six_fund_pairs_not_independent": True, "replicates_not_independent_market_samples": True,
        "aggregate": "compute metrics per replicate first, then scenario averages; do not average weights before nonlinear metrics",
        "confirmatory_family_change_from_original": "RAG vs R0 promoted from auxiliary to primary because mitigation is in title and abstract",
        "confirmatory_tests": ["R0 mean G_available against zero, positive estimate required", "R1-R0 G_full", "R1-R0 full regret",
                               "R1-R2 G_full", "R1-R2 full regret", "R1-R3 G_full", "R1-R3 full regret", "R2-R3 G_full", "R2-R3 full regret"],
        "test": "scenario-level two-sided paired t for contrasts; one-sample two-sided t for R0 G_available; report degenerate variance without forcing a t result",
        "mitigation_estimand": "R1-R0 is total information-provision workflow effect, not retrieval-engine superiority or sharedness causation",
        "multiplicity": {"method": "Holm", "family_size": 9, "alpha": 0.05},
        "bootstrap": {"resamples": 10000, "unit": "whole scenario", "stratify_by": "r", "interval": "individual 95% percentile, not simultaneous"},
        "matched_validity": "for each comparison and replicate require all four funds valid in both arms; use same scenario mask for G and regret; report co-valid masks and every failure separately",
        "valid_only_estimand": "conditional on joint success, not an unconditional treatment effect over all attempted outputs",
        "additional": ["R0 full versus available benchmark decomposition", "R2/R3 vs R0", "C-context contrasts", "pair response error", "x replacement", "negative controls", "actual-document A C", "resource costs"],
        "shared_model_claim_boundary": "common-model workflow evaluated against task-specific reference; independent causal effect of sharing a model versus heterogeneous models is not identified",
    },
    "workload": {"original_blocks": budget, "logical_stages_total": total_stages,
                 "model_responses_before_infrastructure_retries": [total_stages, total_stages * 3],
                 "pilot_staging": [
                     {"step": "offline", "model_calls": 0, "task": "data integrity, generator, posterior, oracle, retrieval and visibility checks"},
                     {"step": "technical smoke", "logical_stages": 15, "task": "one development scenario one fund five arms; subset of pilot, not additional sample"},
                     {"step": "paired feasibility", "logical_stages": 60, "task": "same development scenario all four funds five arms; same-hash completed technical-smoke trajectories may be reused"},
                     {"step": "development pilot", "logical_stages": 720, "task": "12 development scenarios; same-version and same-hash earlier completed trajectories may be reused, all excluded from main"}],
                 "pilot_accounting": "720 planned logical slots is not a lifetime call ceiling; every failed, abandoned or superseded attempt counts separately. A changed model/protocol/input cannot reuse old trajectories as the new pilot.",
                 "execution_rule": "do not auto-launch 9816 stages; measure full-history token and latency on prospective development inputs before selecting frozen main runtime and budget"},
    "current_readiness": {
        "source_inventory_exists": True,
        "source_inventory_raw_documents_saved": inventory.get("raw_documents_saved"),
        "source_inventory_frozen_gold_ready": inventory.get("frozen_gold_ready"),
        "french_raw_cached": True,
        "fund_holdings_and_mapping_complete": False,
        "signal_generator_complete": False,
        "variance_cap_oracle_complete": False,
        "actual_BM25_index_and_run_complete": False,
        "three_stage_five_arm_runner_complete": False,
        "new_model_runs": 0,
        "recent_auxiliary_cases": recent["cases"],
        "recent_auxiliary_AI_calls_recorded": recent["AI_calls"],
    },
    "reuse": [
        {"asset": "data/french", "use": "본실험 FF12 시장자료 보정과 SIC 분류의 출발점", "not_use": "과거 시점의 미개정 공표값으로 단정하지 않음"},
        {"asset": "data/documentary/source_inventory.json", "use": "4펀드 식별자와 공식 원문 수집 경로", "not_use": "이미 구축된 완전 코퍼스나 확정 gold로 취급하지 않음"},
        {"asset": "data/institutional_recent", "use": "별도 72개 명시 목적 통제과제와 평가 함수 검산", "not_use": "실제4펀드 또는 0925 분산상한 본실험으로 대체하지 않음"},
        {"asset": "research/prepare_institutional_benchmark.py", "use": "TV pair response error failure preservation and testing patterns", "not_use": "gamma quadratic optimum or KKT certificate as new risk-cap optimum"},
        {"asset": "data/sector_documents and data/sector_market", "use": "기존 GICS11 공개전망 예비진단과 사실·단위 오류 재현", "not_use": "FF12와 변환 없이 혼합하지 않음"},
        {"asset": "v5 completed E L C responses", "use": "합계 오류 수치오독 설명 모순 정규화 반전의 회귀 사례", "not_use": "새 본실험 표본이나 RAG 성과로 합산하지 않음"},
    ],
    "build_order": [
        "Freeze four funds, complete official source bytes, dates, identifiers and eligibility audit",
        "Construct complete holdings, SIC-to-FF12 map, h, q, fixed assets, and applicable constraints",
        "Construct 120-month FF12 calibration, independent signal generator, document templates and gold facts",
        "Implement posterior and variance-cap oracle with independent verification and near-optimal-set checks",
        "Build actual BM25 corpus, fixed retrieval logs, FULL set and exposed-information guards",
        "Implement three-stage five-arm runner using raw portfolios and common calculator feedback",
        "Run staged development-only feasibility and freeze model, tokenizer, context, tools, hashes and budget",
        "Freeze generation/retrieval/analysis code, seeds, model, sample plan and execution rules using development-only evidence",
        "Mechanically generate main scenarios, oracle and retrieval packets without model outcomes; freeze input manifest hashes before the first main model request",
        "Execute main, counterfactual and negative controls, then A and held-out C; report all failures",
    ],
    "human_review": {"fund_eligibility_and_constraints": "two independent humans for all funds",
                     "actual_facts": "per fund random 10%, minimum20 fields or all if fewer; preserve units dates locators and pre-adjudication agreement",
                     "generated_B_facts": "automatic exhaustive roundtrip verification",
                     "AI_review_not_human_substitute": True},
    "main_freeze_requirements": {
        "method_freeze_after_development": ["complete source corpus and eligibility dates", "holdings coverage and constraint audit", "verified generator and risk-cap oracle",
                                            "development retrieval logs and packet validation", "no hidden-information leakage", "three-stage full-history fit without truncation",
                                            "fixed model and sampler", "pilot tokens latency and executable budget", "fixed code seeds sample plan analysis and failure policy"],
        "input_manifest_freeze_before_first_main_request": ["mechanically generated main inputs", "reference-only numerical validation", "actual main retrieval logs and packet hashes", "balanced execution order", "model-visible and evaluator-only separation"],
    },
    "not_performed_by_this_redesign": ["fund data download", "new signal corpus generation", "BM25 retrieval", "oracle calculation", "model invocation", "manuscript rewrite"],
}
changes = [
    ["원초록과 0925", "4개 실제 펀드와 FF12 12산업", "복원", "GICS11 자료와 결합하지 않음"],
    ["원초록과 0925", "계획 배분안 구성 점검과 수정", "복원", "모든 조건에서 같은 세 단계와 도구"],
    ["0925 §6", "실제 BM25 검색과 5조건", "복원", "검색 후 동일 패킷을 R1 R2 R3에 재생"],
    ["0925 §7", "사후전망 기대수익 최대화와 보유 분산 상한", "복원", "gamma 목적함수와 구분하고 새 평가기 검증"],
    ["0925 §8 및 기존 코드", "G 손실 정보반응 제약위반", "유지 보강", "기존 쌍별 반응오차를 함께 보고"],
    ["0925 전체 및 제공정보 기준", "R0 G에 정보 부재 기여 포함", "기준 보강", "H1은 Gavailable로 검정하고 Gfull과의 차이는 정보집합 효과로 분리"],
    ["0925 §11", "R0 비교가 보조분석", "수정", "완화효과를 직접 검정하도록 R1 대 R0를 주분석으로 승격"],
    ["0925 §11", "시점 6개 검정 Holm", "수정", "기준 G 및 R1 R0를 포함한 9개 검정 단일 Holm 계열"],
    ["0925 §10", "60상황 2반복 및 전체9816단계", "계획 목표 유지", "15→60→720 개발 단계로 실행 가능성부터 확인"],
    ["완료 E L C 실험", "원합계 오류와 정규화 방향 반전", "실험기 반영", "일차 결과에 자동 정규화 금지 원비중 제약과 증감 검사"],
]


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def table(headers: list[str], rows: list[list]) -> str:
    return '<div class="tablewrap"><table><thead><tr>' + ''.join(f'<th>{esc(v)}</th>' for v in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{esc(v)}</td>' for v in row) + '</tr>' for row in rows) + '</tbody></table></div>'


sections = []
sections.append(("원초록과 기존 설계를 기준으로 한 복원", '''
<p>제목과 원초록의 연구 목적을 유지하고, 2026년 9월 25일 실험설계서의 A 실제자료 적용, B 통제실험, C 새 문서 검색 검증을 복원한다. 원초록의 12산업은 French12로 정의돼 있다. 현재 완료된 Fidelity·UBS의 GICS11 직접 제공 실험은 별도 자료로 보존하고 새 본실험에 합산하지 않는다.</p>
<p>핵심 질문은 공통 LLM 사용 조건에서 펀드별로 필요한 차이가 줄어드는가, 그 차이가 판단 손실 또는 제약 위반과 함께 나타나는가, 실제 검색 근거의 도입·유지 정책이 차이와 품질을 함께 개선하는가이다. 같은 모델을 공유한 사실 자체의 인과효과나 금융시장 전체의 동조는 이 설계의 식별 대상이 아니다.</p>
''' + table(["기존 근거", "요소", "처리", "재설계 내용"], changes)))
sections.append(("준비된 데이터와 아직 구축할 데이터", table(["자산", "현재 확인 상태", "재사용과 경계"], [
    ["네 펀드 신원과 공식 자료 후보", "source_inventory.json 있음. raw_documents_saved=false, frozen_gold_ready=false", "FCNTX VPMCX DODGX TRBCX 유지. 공식 원문 저장과 전체 보유표 추출 필요"],
    ["French 수익률과 SIC", "12산업 월간·일간 및 분류 원본 ZIP과 해시 있음", "12산업 시장 보정과 보유 매핑에 사용. 새 기준배분은 별도 계산"],
    ["24시장창 72가상 위임", "수리 검증 완료 기록, AI 실행0. 중첩창이며 gamma=1 3 5", "검산용 보조과제. 실제 펀드나 분산상한 과제의 대체물이 아님"],
    ["GICS11 공개 전망", "Fidelity UBS 원문과 요약 입력, 시장자료, 완료 출력 보존", "오독·합계·설명 모순을 검사하는 개발 사례. FF12 결과와 합산 금지"],
    ["실제 보유 h와 q 고정자산", "미구축", "전체 보유자료와 SIC 매핑·분류율 확인 후 구성"],
    ["검색 및 새 통제실험", "BM25 색인·검색 로그, y x 생성기, 분산상한 평가기와 3단계 실행기 미구축", "이번 설계 완료와 실제 실험 완료를 구분"],
]) + '<p>본문·데이터·소프트웨어의 기존 파일을 덮어쓰지 않는다. 준비 상태는 새 설계의 실행 가능성을 확인하기 위한 목록이며, 아직 효과가 관측됐다는 뜻이 아니다.</p>'))
sections.append(("펀드와 통제 과제", table(["익명 ID", "펀드", "대표 클래스"], [[f["fund_id"], f["name"], f["ticker"]] for f in funds]) + '''
<p>개발은 2025년 9월 말 보유와 2025년 말까지의 공시, A는 2025년 말 보유와 2026년 3월 말까지의 공시, C는 2026년 3월 말 보유와 2026년 6월 말까지의 공시로 분리한다. 보고 기준일과 공개일을 별도 기록한다. 전체 보유표에서 발행사 SIC를 French12에 연결해 주식 부문 h를 구성하고, 그 부문의 펀드 전체 비중 q와 분류 불가·기타 고정자산을 보존한다. 원설계의 주식 분류율90%는 자료 품질에 관한 연구 설정이며 분모와 적용 규칙을 입력 구축 전에 고정한다.</p>
<p>B에서는 실제 보유상태와 2016–2025년 120개월 French12 수익률의 위험척도를 사용한다. 펀드별 추가 전망 x는 생성기가 만든 가상 관측이며 실제 운용사의 내부 전망으로 표시하지 않는다. 기본 운용목표·필수 제약·h·위험상한은 R0를 포함한 모든 조건이 처음부터 받는다. 전망의 등급에서 위험회피계수나 숨은 목표비중을 만들지 않는다.</p>
<p>A와 C는 실제 문서의 사실·적용 가능한 제약·선택 이유와 비중의 연결을 평가한다. 실제 문서의 정성 전망에서 유일한 정답 비중을 만들거나 B의 가상 전망을 실제 기관의 사실로 옮기지 않는다.</p>'''))
sections.append(("시나리오와 수리 기준배분", '''
<p>원설계의 정규 생성기를 복원한다. m₀는 역사적 월간 평균, Σ는 Ledoit–Wolf 공분산, V₀=Σ/12, Ω₀=V₀, Ωᵢ=V₀/r이며 r은0.5 1 2이다. 각 시나리오의 θ와 공통 전망 y를 생성하고, 같은 θ에 조건부 독립인 펀드별 xᵢ를 생성한다. 실제 시장 예측의 정답이나 관측된 기관별 믿음으로 부르지 않는다.</p>
<p class="equation">Vᵢ = (V₀⁻¹ + Ω₀⁻¹ + Ωᵢ⁻¹)⁻¹<br>μᵢ* = Vᵢ(V₀⁻¹m₀ + Ω₀⁻¹y + Ωᵢ⁻¹xᵢ)</p>
<p>생성기는 값·단위·날짜·정밀도·근거 ID를 가진 고정 문서 양식과 평가표를 함께 만든다. 평가자는 표시된 값을 다시 읽어 계산하며 숨겨진 θ나 다른 펀드의 x를 기준에 넣지 않는다. 개발1001, 본실험2001, 전망교체3001, 음성대조4001, 순서5001, 감사6001, bootstrap7001의 난수 흐름을 분리한다.</p>
<p class="equation">wᵢ* = arg max μᵢ*ᵀw<br>w ≥ 0, 1ᵀw = 1, wᵀΣw ≤ hᵢᵀΣhᵢ, 사전 명시된 적용 가능 제약</p>
<p>이 기준은 기존 보유 주식 부문의 분산을 넘지 않는 범위에서 기대수익을 최대화하는 명시 과제의 해다. 기존 gamma 이차효용 최적해와 다른 문제이므로 CVXPY와 Clarabel 후보 평가기를 새로 구현하고 독립 계산으로 검증한다. 거의 최적인 집합의 비중 폭이1%p를 넘으면 그 사례의 기준거리와 G를 유보하고 목적값 손실은 유지한다.</p>
<p>전체 허용정보 기준 Rfull과 실제 제공정보 기준 Ravailable을 나란히 계산한다. R0의 Rfull에는 추가정보 부재가 포함된다. 일부 관측만 회수했다면 보이는 관측과 정밀도만으로 조건부 계산한다. 미제공 정밀도를 평가자 메타데이터에서 보충하지 않는다.</p>'''))
sections.append(("실제 검색과 세 단계 다섯 조건", table(["조건", "계획", "배분안 구성", "점검과 수정", "역할"], arm_rows) + '''
<p>BM25Okapi, k₁=1.5, b=0.75, ε=0.25, 최대400토큰 문단과50토큰 겹침, top4 및 중립 고정 질의를 원설계에서 유지한다. 펀드와 공개일 필터는 검색 전에 적용한다. 숫자 행·단위·각주·관측 정밀도는 함께 보존한다. 검색 대상은 공통 문서와 자기 펀드의 적격 원문이며 정답·θ·다른 펀드 사적정보는 제외한다.</p>
<p>각 펀드·시나리오에서 실제 검색을 한 번 실행하고 결과 텍스트·순서·점수·길이·해시를 고정한다. R1 R2 R3에는 이 동일한 패킷을 처음 제공하는 단계만 바꾸고 이후에도 유지한다. C에서는 보류한 새 문서를 색인하고 검색부터 다시 수행한다. 전체 적격 원문이 검색 패킷과 같으면 그 사실을 보고하고 검색의 우위를 주장하지 않는다.</p>
<p>전 조건은 같은 모델·기본 지침·세 단계·출력 형식·계산도구를 사용하고 독립 초기 상태에서 시작한다. 자신의 전체 단계 이력을 보존한다. 비교 대상은 최초 도입과 그 이후 유지가 결합된 업무정책이다. 초기 조건의 누적 노출과 수정 기회까지 통제한 순수 시점 효과로 부르지 않는다.</p>
<p>도구는 이미 노출된 근거로 사후평균을 계산하는 posterior와 원비중을 검사하는 check_portfolio이다. 최적비중·숨은 전망·평가자 판정은 반환하지 않는다. 단계당 도구 왕복 최대2회, 출력2048토큰은 원설계의 운영 후보값이며 전체 이력으로 검증한 뒤 본실험 전에 고정한다.</p>'''))
sections.append(("평가와 완화 판정", table(["항목", "계산", "판정상 역할"], [
    ["과잉수렴 G", "Gfull=D*full−D, Gavailable=D*available−D, D=½||wi−wj||₁", "전체 정보와 제공 정보의 기준을 분리. H1은 제공정보 대비 피할 수 있는 수축을 검사"],
    ["기대수익 손실", "Rfull=μ*ᵀ(w*−w), Ravailable 별도", "B의 명시 목적에 따른 손실. 실제 수익이나 gamma 효용손실과 혼합하지 않음"],
    ["필요한 방향의 보존", "개별 기준거리와 ½||(wi−wj)−(w*i−w*j)||₁", "비중을 서로 바꿔도 거리가 같은 문제를 포착"],
    ["개별 정보반응", "x만 교체한 짝의 배분 변화와 기준 변화의 차이", "그럴듯한 설명 대신 실제 선택 반응 검사"],
    ["제약과 출력 실패", "원비중 합계·비음수·위험상한·명시 제약·파싱", "전체 시도 분모. 정상화로 성공으로 바꾸지 않음"],
    ["근거 및 공유 오류", "값 단위 날짜 원문 위치와 실제 증감 대조", "제공된 근거의 정확성과 선택 설명을 구분"],
    ["검색과 비용", "recall@4·토큰·호출·지연", "검색 실패와 회수 후 활용 실패 분리"],
]) + '''<p>R0가 자신이 받은 정보에 완벽히 합리적으로 반응해도 숨은 x 때문에 Gfull과 Rfull은 양수가 될 수 있다. 따라서 H1은 Gavailable을 사용하고 Ravailable 및 제약을 함께 본다. Gfull−Gavailable=D*full−D*available로 정보집합에 따른 기준거리 변화도 보고한다. 제공정보 기준의 필요한 차이가0이거나 수치적으로 해소되지 않은 쌍에는 양의 수축 기회가 식별되지 않았다고 표시한다. 평가자용 available 최적해를 출력으로 넣으면 Gavailable과 Ravailable이0이어야 한다는 검산을 요구한다.</p>
<p>RAG 정책의 완화효과는 양의 Gfull이0에 가까워지고 기준거리·정보반응이 회복되며 Rfull도 함께 개선될 때 채택한다. 음의 G를 더 크게 만들거나 차이만 늘린 결과는 성공이 아니다. 관측된 제약 위반·실패율이 악화한 정책은 권고하지 않는다. 유의하지 않음을 품질 비악화나 동등성의 증거로 쓰지 않는다.</p>
<p>최종 원비중을 외부 정규화하지 않는다. 합계 오류가 있으면 일차 배분거리와 손실은 계산 불가로 남기고 실패를 보고한다. 주 비교별로 두 조건의 네 펀드가 모두 유효한 동일 시나리오·반복을 사용하고 G와 손실에 같은 마스크를 적용한다. 이는 공동 성공에 조건부인 품질 비교이므로 전체 실패율과 함께 제시한다.</p>'''))
sections.append(("표본과 분석 계획", '''
<p>원설계의 B 본실험60상황은 r별20상황, 네 펀드, 다섯 조건, 두 반복으로 유지한다. 펀드6쌍이나 두 모델 반복을 독립 시장표본으로 세지 않는다. 지표는 반복별로 먼저 계산한 뒤 시나리오 안에서 집계한다. 고정된 시장 보정값·네 펀드에 조건부인 생성 시나리오가 독립 단위다.</p>
<p>원설계에서 보조였던 R0 비교를 승격한다. R0의 평균Gavailable에 대한0 비교, R1 대 R0의 Gfull과 Rfull, R1 R2 R3 사이 세 쌍의 Gfull과 Rfull을 합한9개 검정을 단일 Holm 계열 α=0.05로 사전 지정한다. 차이는 시나리오 대응 비교이며, R0의 Gavailable은 단일표본 검정이다. R0의 Gavailable은 보정된 양의 증거가 있고 관측 Ravailable 또는 제약 문제가 함께 뒷받침될 때 제공정보 대비 과잉수렴으로 해석한다. R1 대 R0는 추가정보 제공을 포함한 정책 총효과이며 검색엔진 자체의 우월성은 아니다. 95% 개별 구간은 r층 내 시나리오 전체를10000회 복원추출한다. 실제 검색 근거 제공의 완화효과를 제목에서 묻기 때문에 추가한 분석 변경이다.</p>
<p>R2 R3와 R0의 추가 비교, C-context, 정보반응, 동일정보 대조, A C와 비용은 보조분석으로 둔다. x 교체는 시나리오별 사전 배정한 한 펀드에서 R1 R3 C-context를 비교하고, 같은 정보·보유·목표를 네 익명 ID에 복제한 음성대조로 불필요한 차이의 생성을 확인한다. 유효 시나리오가 적거나 실패 구성의 차이가 크면 그 제한을 수치로 보고하고 확증 결론을 유보한다.</p>'''))
sections.append(("실행 규모와 단계별 준비", table(["블록", "산식", "업무 단계 수"], [[r["block"], " × ".join(map(str, r["factors"])), r["logical_stages"]] for r in budget] + [["합계", "도구 왕복과 인프라 재시도 전", total_stages]]) + '''
<p>9816은 원설계의 계획 합계이며 실행 지시가 아니다. 단계당 도구 왕복을 모두 사용하면 모델 응답은29448회까지 증가할 수 있다. 기존 CPU4B 환경의 긴 지연을 그대로 적용해 전체 본실험을 예약하지 않는다. 새 입력과 전체 이력으로 토큰·지연·유효성부터 실측한다.</p>
<ol><li>모델 호출 없이 보유자료·생성기·평가기·검색·정보경계를 검증한다.</li><li>개발 한 시나리오 한 펀드의 다섯 조건15단계로 형식과 도구·문맥 수행 가능성을 확인한다.</li><li>같은 개발 시나리오 네 펀드60단계로 필요한 차이와 조건 짝의 관측 가능성을 확인한다.</li><li>개발12상황720단계를 계획한다. 같은 모델·프로토콜·입력 해시로 완료한 앞 단계 궤적만 재사용할 수 있다. 실패·폐기·이전 버전 시도는 모두 별도 계상한다. 720은 계획 슬롯 수이며 누적 실제 호출 상한이 아니다.</li><li>개발 결과로 코드·생성규칙·검색정책·seed·모델·문맥·예산·표본·분석을 먼저 동결한다. 그 규칙으로 본실험 입력을 기계 생성하고 검색한 뒤 첫 모델 요청 전에 입력 manifest와 패킷 해시를 추가 동결한다.</li><li>본실험 결과를 보지 않은 상태에서 실행환경과 규모를 확정한다. 자원이 부족하면 표본계획과 분석 민감도를 먼저 개정하며 유의성이 나올 때까지 늘리지 않는다.</li></ol>
<p>이 개발 과정은 RAG가 이기는 모델이나 설정을 고르는 과정이 아니다. FULL에서도 자료 읽기·제약 처리·구조화 출력이 가능한지와 비용을 확인한다. 실제 API 또는 서버 모델의 사용 가능성과 비용은 새로 확인해야 하며 과거 문서의 단가를 현재 단가로 쓰지 않는다.</p>'''))
sections.append(("구축 순서와 논문 연결", '<ol>' + ''.join(f'<li>{esc(v)}</li>' for v in [
    "4펀드 공식 원문과 전체 보유표를 저장하고 공개일·식별자·적격성을 대조한다.",
    "h와q 및 고정자산, FF12 매핑과 적용 제약을 구성한다.",
    "120개월 시장자료 보정, y와x 생성, 수리 기준배분과 사실 정답표를 구축한다.",
    "실제 검색 로그와 고정 패킷, FULL 원문집합, 근거 접근 경계를 구현한다.",
    "세 단계 실행기와 계산기·원비중 및 증감 검사를 연결하고 개발 파일럿을 수행한다.",
    "개발 검증 뒤 방법과 실행규칙을 먼저 동결하고 본실험 자료를 기계 생성한 뒤 첫 요청 전에 입력 manifest를 동결한다.",
    "B 결과로 과잉수렴과 완화효과에 답하고 A C로 실제 문서 적용과 새 검색을 확인한다.",
]) + '</ol><p>논문은 문제 제기 → 원설계와 자료 → 기존 직접 제공 실험에서 확인한 설계상 문제 → 새 B 통제실험 → A C 적용 → 효과와 한계의 순서로 연결한다. 새 실험 결과가 나오기 전에는 과잉수렴이나 완화효과의 방향을 미리 서술하지 않는다. 이번 변경은 설계서와 설정 파일을 추가하며 기존 v5.4 원고와 데이터의 내용은 보존한다.</p>'))

source_rows = []
for s in sources:
    path = Path(s["path"])
    absolute = path if path.is_absolute() else ROOT / path
    href = absolute.as_uri()
    source_rows.append(f'<li><a href="{esc(href)}">{esc(s["path"])}</a> — {esc(s["role"])}</li>')

css = '''
body{font-family:"Malgun Gothic",Arial,sans-serif;line-height:1.75;color:#17212a;margin:0;background:#f4f5f6;word-break:keep-all;overflow-wrap:anywhere}
main{max-width:1050px;margin:32px auto;padding:42px 48px;background:white}
h1{font-size:29px;line-height:1.4;margin:0 0 12px;color:#000}h2{font-size:21px;color:#000;margin:36px 0 12px}
.subtitle{font-size:17px;margin:0 0 22px}.meta{font-size:13px;color:#56606a}.lead{font-size:17px}
p{margin:12px 0}.tablewrap{overflow:auto;margin:20px 0}table{border-collapse:collapse;width:100%;font-size:13px;min-width:660px}
th,td{border:1px solid #d9d9d9;padding:11px 12px;text-align:left;vertical-align:top}th{background:#e9edf1;color:#000}
tr:nth-child(even) td{background:#fafbfc}li{margin:8px 0}a{color:#19588a;overflow-wrap:anywhere}
.equation{font-family:"Cambria Math",Cambria,serif;font-size:18px;line-height:1.8;margin:22px 0;overflow-wrap:anywhere}
@media(max-width:700px){main{margin:0;padding:24px 18px}h1{font-size:24px}.subtitle{font-size:15px}}
@media print{body{background:white}main{margin:0;padding:0;max-width:none}h2{break-after:avoid}tr{break-inside:avoid}.tablewrap{overflow:visible}table{min-width:0;font-size:10px}}
'''
document = '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LIBERA 원설계 복원 실험재설계</title><style>' + css + '</style></head><body><main>'
document += f'<p class="meta">LIBERA 실험재설계 v6.0 · 2026년10월27일 · 본실험 전 설계안</p><h1>{esc(TITLE)}</h1><p class="subtitle">{esc(SUBTITLE)}</p>'
document += '<p class="lead">원초록과 기존 실험설계를 기준으로, 실제4펀드·12산업의 필요한 배분 차이와 판단 품질을 함께 검증하는 Workflow RAG 본실험을 복원한다.</p>'
for number, (heading, body) in enumerate(sections, 1):
    document += f'<section><h2>{number} {esc(heading)}</h2>{body}</section>'
document += '<section><h2>10 근거 파일</h2><p>설정 JSON의 lineage에는 아래 파일의 SHA256을 기록했다. 원설계의 설정과 현재 준비된 실물 데이터를 구분해 사용했다.</p><ul>' + ''.join(source_rows) + '</ul></section></main></body></html>'

WORK.mkdir(parents=True, exist_ok=True)
PLAN.mkdir(parents=True, exist_ok=True)
JSON_OUT.write_text(json.dumps(spec, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
HTML_OUT.write_text(document, encoding="utf-8")
(WORK / "source_inventory.json").write_text(json.dumps({"sources": sources, "changes": changes}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

checks = {
    "schema_version": VERSION,
    "all_lineage_sources_exist": all(s["exists"] for s in sources),
    "title_preserved": spec["title"] == TITLE and spec["subtitle"] == SUBTITLE,
    "primary_industries": spec["modules"]["B"]["industries"],
    "arms": [a["id"] for a in arms],
    "old_budget_recomputed": total_stages,
    "maximum_model_responses_recomputed": total_stages * 3,
    "main_not_executed": not spec["execution_enabled"] and spec["current_readiness"]["new_model_runs"] == 0,
    "outputs": [str(JSON_OUT), str(HTML_OUT)],
}
# Verify the outputs from disk, rather than only their in-memory objects.
loaded = json.loads(JSON_OUT.read_text(encoding="utf-8"))
assert loaded["analysis"]["multiplicity"]["family_size"] == len(loaded["analysis"]["confirmatory_tests"]) == 9
assert checks["all_lineage_sources_exist"] and total_stages == 9816
assert all(len(arm["stage_view"]) == 3 for arm in loaded["workflow"]["arms"])
assert len(loaded["data_contract"]["funds"]) == 4
assert not loaded["execution_enabled"]
(WORK / "build_receipt.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(checks, ensure_ascii=False, indent=2))
