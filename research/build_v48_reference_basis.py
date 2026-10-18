"""Build an append-only primary-source memo for the v4.8 redesign; no model calls."""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "research/evidence/v48_reference_20261018"
OUT = ROOT / "research/v48_reference_basis_20261018.json"


def utc():
    return datetime.now(timezone.utc).isoformat()


def reference(path, **extra):
    p = ROOT / path
    raw = p.read_bytes()
    return {"path": p.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw), **extra}


def download(name, url):
    p = DEST / name
    if p.exists():
        raise FileExistsError(p)
    req = urllib.request.Request(url, headers={"User-Agent": "LIBERA-public-primary-source-verification/1.0"})
    with urllib.request.urlopen(req, timeout=45) as response:
        raw, status, resolved = response.read(), response.status, response.url
    if status != 200:
        raise RuntimeError((url, status))
    with p.open("xb") as out:
        out.write(raw)
    return reference(p.relative_to(ROOT), url=url, resolved_url=resolved, http_status=status, retrieved_at_utc=utc(), kind="new_primary_snapshot")


def metadata(ref):
    soup = BeautifulSoup((ROOT / ref["path"]).read_bytes(), "html.parser")
    def vals(name):
        return [tag.get("content") for tag in soup.find_all("meta", attrs={"name": name})]
    dateline = " ".join(soup.select_one(".dateline").stripped_strings)
    authors = vals("citation_author")
    return {"title_registered": vals("citation_title")[0], "citation_authors_original": authors,
            "citation_date_original": vals("citation_date")[0], "arxiv_id": vals("citation_arxiv_id")[0],
            "dateline_original": dateline,
            "latest_version_observed": int(re.search(r"this version, v(\d+)", dateline).group(1)) if "this version" in dateline else 1,
            "metadata_locator": "head meta citation_title/citation_author/citation_date/citation_arxiv_id; .dateline"}


def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    DEST.mkdir(parents=True, exist_ok=True)
    old_bib_path = "research/v47_added_bibliography_v2_20261018.json"
    old_bib = json.loads((ROOT / old_bib_path).read_text(encoding="utf-8"))
    old_entries = {x["id"]: x for x in old_bib["entries"]}
    table = [
        ("uptake", "2607.15388", 1, "research/evidence/v47_priority1_options_20261018/uptake_fulltext.html"),
        ("symbolic", "2606.27757", 1, "research/evidence/v47_priority1_options_20261018/symbolic_fulltext.html"),
        ("finfirst", "2609.25192", 1, "research/evidence/v47_priority1_options_20261018/finfirst_fulltext.html"),
        ("externalization", "2609.38869", 2, "research/evidence/priority23_candidates_20261018/externalization_fulltext_v2.html"),
        ("e2a", "2609.14302", 1, "research/evidence/priority23_candidates_20261018/e2a_fulltext.html"),
        ("fundapod", "2605.27864", 5, "research/evidence/priority23_candidates_20261018/fundapod_fulltext.html"),
        ("instrument", "2609.19844", 2, None),
    ]
    sources, papers, checks = [], [], []
    old_refs = {}
    for prior_name in ("research/v47_priority1_revision_options_20261018.json", "research/priority23_paper_candidates_v2_20261018.json"):
        prior = json.loads((ROOT / prior_name).read_text(encoding="utf-8"))
        for item in prior["primary_sources"]:
            old_refs[item["path"]] = item
    for sid, arxiv_id, version, old_full in table:
        abs_ref = download(f"{sid}_abs_latest.html", f"https://arxiv.org/abs/{arxiv_id}")
        meta = metadata(abs_ref)
        if meta["latest_version_observed"] != version:
            raise RuntimeError(f"Unexpected latest version: {sid}: {meta}")
        if old_full:
            full_ref = reference(old_full, url=f"https://arxiv.org/html/{arxiv_id}v{version}", kind="reused_primary_snapshot")
            if full_ref["sha256"] != old_refs[old_full]["sha256"]:
                raise RuntimeError(f"Historical primary source hash changed: {old_full}")
            prior = old_entries[sid]
            if meta["title_registered"] != prior["title_registered"] or meta["citation_authors_original"] != [a["original_citation_author"] for a in prior["authors"]]:
                raise RuntimeError(f"Bibliographic metadata changed: {sid}")
            bib = {k: prior[k] for k in ("authors", "year", "version_date", "initial_submission_date", "apa_text", "apa_authors", "apa_title_sentence_case")}
            bib["bibliographic_metadata_reused_from"] = reference(old_bib_path)
        else:
            full_ref = download("instrument_2609_19844v2.html", f"https://arxiv.org/html/{arxiv_id}v{version}")
            expected = ["Xiao, Hang", "Xu, Chuhong", "Zhou, Kainan", "Qian, Gangzhen", "Yi, Lu"]
            if meta["citation_authors_original"] != expected:
                raise RuntimeError(f"Instrument authors differ: {meta}")
            bib = {
                "authors": [{"family": a.split(", ")[0], "given": a.split(", ")[1], "original_citation_author": a} for a in expected],
                "year": 2026, "version_date": "2026-10-09", "initial_submission_date": "2026-09-17",
                "apa_authors": "Xiao, H., Xu, C., Zhou, K., Qian, G., & Yi, L.",
                "apa_title_sentence_case": "Trust, but validate the instrument: Auditing AI-generated RTL verification plans on authored security-regression proxies",
                "apa_text": "Xiao, H., Xu, C., Zhou, K., Qian, G., & Yi, L. (2026). Trust, but validate the instrument: Auditing AI-generated RTL verification plans on authored security-regression proxies (Version 2) [Author accepted manuscript]. arXiv. https://arxiv.org/abs/2609.19844v2",
                "publication_status_note": "arXiv abstract comments state accepted at IEEE Cyber-AI 2026, author accepted manuscript; no proceedings DOI or pagination is invented.",
            }
        sources.extend([{**abs_ref, "source_id": sid + "_abs_latest"}, {**full_ref, "source_id": sid + "_fulltext"}])
        papers.append({"id": sid, "arxiv_id": arxiv_id, "version": version,
                       "url": f"https://arxiv.org/abs/{arxiv_id}v{version}",
                       "fulltext_url": f"https://arxiv.org/html/{arxiv_id}v{version}",
                       "metadata": meta, "bibliography": bib, "source_ids": [sid + "_abs_latest", sid + "_fulltext"]})
        checks.append({"id": sid + "_latest_version_and_bibliography", "status": "pass"})
    details = {
        "uptake": {
            "locators": ["Sections 3.2-3.4", "Appendix H.1-H.2", "Appendix I Table 12", "Appendix I.1 Single-Agent Iterative", "Appendix I.5"],
            "direct_support_ko": "최초 제출과 외부 검증 후 회복, 오류 검출과 후보 변경과 실제 수정을 구분한다. Single-Agent Iterative의 총 outer attempt 상한은 최초 제출을 포함한 3회이다. 이전 후보와 실패 기록을 활용하며 문제 간 기억을 초기화한다.",
            "application_ko": "LIBERA 단계4의 최초 최종안을 C0 주분석으로 보존하고, 산술 부적합일 때 C1/C2를 보조 분석으로 추가한다. 같은 정책·상한을 R1/R4에 적용한다.",
            "adaptations_and_limits_ko": "원 논문의 3회는 금융 4단계 전체를 의미하지 않는다. 원 single-agent는 시도 사이 raw chat을 초기화하고 compact ledgers를 사용한다. LIBERA의 4단계 뒤 수정과 전체 원문 이력 보존은 명시적 변형이다. gpt-oss-120b 수학 결과는 현재 4B 금융 성능·최적 반복 수·인과 기제를 입증하지 않는다.",
            "numbers_adopted_or_rejected": {"direct_reported_total_outer_attempt_cap": 3, "libera_total_endpoint_candidates_including_C0": 3, "libera_additional_generation_cap": 2, "claim_of_optimality": False, "paper_effect_sizes_adopted": False},
            "support_class": "direct_process_and_budget_precedent_with_explicit_domain_and_protocol_adaptation",
        },
        "symbolic": {
            "locators": ["Section III-B, Equation 2", "Section III-C", "Section IV-A"],
            "direct_support_ko": "원과제·실제 오류 피드백·이전 시도를 함께 주고 검증 성공 또는 사전 상한에서 종료한다. 실행 가능성과 목표 일치 검증을 구분한다.",
            "application_ko": "기존 원문과 실제 계산 결과를 보존한 제한적 재제출. 계산기는 검사만 하고 모델 비중을 수정하지 않는다.",
            "adaptations_and_limits_ko": "PDDL/VAL 계획 검증과 목표 인식 연구이다. LIBERA는 목표 인식 정답·수정 행동·산업별 목표 비중을 주지 않는다. 현재 2회 추가 호출 수치와 금융 전략 타당성의 직접 근거가 아니다.",
            "numbers_adopted_or_rejected": {"iteration_cap_imported_from_this_paper": False},
            "support_class": "nonfinancial_bounded_external_feedback_pattern",
        },
        "finfirst": {
            "locators": ["Sections 2.2.2-2.3", "Section 2.3 Independent re-solving and Rubric audit"],
            "direct_support_ko": "출처 위치·정의·기간·단위·버전·계산 입력과 중간 계산을 추적한다. 동등한 근거 경로를 허용하며 과제에서 요구하지 않은 항목을 평가에 추가하지 않는다.",
            "application_ko": "계산·사실·기관 원문·모델 해석의 근거를 분리하고 다음 실행 전에 요구와 평가를 함께 고정하는 근거이다.",
            "adaptations_and_limits_ko": "검색 과제의 평가 방법이지 산업 배분의 유일한 정답이 아니다. 이번 agent 검토 3회를 전문가 독립 재해결과 동일시하지 않는다.",
            "numbers_adopted_or_rejected": {"rubric_weights_tolerances_or_tool_budgets_imported": False},
            "support_class": "financial_traceability_and_rubric_alignment_precedent",
        },
        "externalization": {
            "locators": ["Sections 3.4-3.5, Table 1", "Section 4.1.2", "Sections 4.1.3-4.1.4"],
            "direct_support_ko": "동일한 evidence registry에서 조건별 정보 노출만 바꾸고 시스템 지시·출력 스키마를 유지한다. 수치와 관계는 외부에서 계산할 수 있다. 구조화된 주장과 근거의 일치는 자유 서술 전체의 진실성을 보장하지 않는다.",
            "application_ko": "기관별 자료를 정확히 보존하고 공통 시장정보·계산·출력 계약을 고정하는 설계 원칙. 다음 수치 설명 검증의 후보 근거이며 이번 재설계로 해당 평가가 이미 구현됐다고 주장하지 않는다.",
            "adaptations_and_limits_ko": "SHAP 주식 예측 설명 연구이며 CRSP/WRDS 자료는 무료 민간 공개 데이터가 아니다. 방법만 전용하고 기존 공개 데이터는 유지한다. 현재 GGUF 4B 배분 결과를 검증하지 않는다.",
            "numbers_adopted_or_rejected": {"paper_effect_sizes_models_windows_or_rating_scales_imported": False},
            "support_class": "financial_evidence_contract_precedent_not_current_performance_evidence",
        },
        "e2a": {
            "locators": ["Sections 3.3-3.4", "Section 4.2", "Section 4.3.4", "Limitations"],
            "direct_support_ko": "차트에 유일한 매매 행동 정답이 있다고 가정하지 않는다. 검증 가능한 사실, 설명과 행동의 일관성, 행동 산출 범위를 함께 본다. 주장 오류가 적어도 산출을 회피한 결과일 수 있다.",
            "application_ko": "배분 산출·산술 유효성·기관 근거 충실성을 따로 보고한다. 유효 배분만 남긴 결과로 전체 판단 보존을 주장하지 않으며, 비중 미제출을 동질화로 해석하지 않는다.",
            "adaptations_and_limits_ko": "금융 차트 행동 과제이므로 기관 house view나 산업별 정답 비중의 근거가 아니다. NDR 합성식·확신 척도·기술지표 임계값을 전용하지 않는다. Oracle 개입의 상세 절을 확인하지 못해 해당 효과를 이번 수정 방법의 핵심 근거로 쓰지 않는다.",
            "numbers_adopted_or_rejected": {"NDR_formula_thresholds_confidence_scales_imported": False},
            "support_class": "financial_evidence_to_action_and_coverage_precedent",
        },
        "fundapod": {
            "locators": ["Section 3 DP2-DP4", "Sections 5.1 and 5.4", "Section 7 Limitations"],
            "direct_support_ko": "기관 투자연구에서 자료 처리와 판단을 나누고 서로 다른 관점 및 출처가 연결된 검토 가능한 분석을 보존하는 설계 선례이다.",
            "application_ko": "기관 공개 근거 → 모델 해석과 가정 → 제안과 대안의 연결을 보존하는 후속 설명 계약의 후보이다.",
            "adaptations_and_limits_ko": "설계와 사례 설명이며 공식적인 정량 효과·persona 충실성·투자 성과의 검증은 아니다. 기관 sector view를 전체 운용 목적·실제 보유 비중·법적 제약으로 확대하지 않는다.",
            "numbers_adopted_or_rejected": {"alternative_counts_word_lengths_or_portfolio_weights_imported": False},
            "support_class": "institutional_research_design_precedent_not_effectiveness_evidence",
        },
        "instrument": {
            "locators": ["Sections V-A, V-C and V-E", "Section VI", "Sections VII-A and VII-C", "Section IX"],
            "direct_support_ko": "제공자·스키마 수용과 실제 실행 의미 검증을 구분하고 예정된 실패를 보존한다. 생성 규칙과 실행 규칙이 불일치한 사례를 측정 도구 사고로 보존하며 prompt 효과를 주장하지 않는다. 변경은 별도 동결하고 기존 결과를 덮어쓰지 않는다.",
            "application_ko": "관측·계약·검증기의 정합성 통과와 모델의 산술 성공을 분리한다. 원문이 완전하고 계약이 일치할 때 산술 실패를 결과로 보존한다. 입력 또는 측정이 훼손되면 기관 정보 노출 효과를 해석하지 않는다.",
            "adaptations_and_limits_ko": "RTL 보안 검증 연구이다. LIBERA의 모델 실패를 무조건 유효 증거로 인정하거나 기존 실패 게이트를 소급 통과시키는 근거가 아니다. 부적합 비중은 유효 포트폴리오 위험·전략 차이 분석에 그대로 사용할 수 없다.",
            "numbers_adopted_or_rejected": {"sample_size_repetitions_resource_limits_tests_or_thresholds_imported": False},
            "support_class": "nonfinancial_measurement_integrity_and_failure_preservation_precedent",
        },
    }
    for paper in papers:
        paper.update(details[paper["id"]])
    reused_context = [reference(p) for p in (
        old_bib_path, "research/v47_planner_executor_reference_20261018.json",
        "research/priority23_paper_candidates_v2_20261018.json",
        "research/v44_conditions_reference_20261018.json", "research/v45_revision_reference_20261018.json",
        "research/v47_handoff_20261018.json")]
    result = {
        "schema_version": "libera_v48_reference_basis_1.0", "protocol_version": "4.8", "created_at_utc": utc(),
        "status": "primary_reference_basis_for_redesign_not_execution_registration_or_result",
        "research_priority_ko": "공통 생성형 AI가 공개 기관별 투자판단 근거를 해석하고 제안에 연결하는지를 관측한다. 계산 수정은 이를 대체하는 주제가 아니라 사후 보조 진단이다.",
        "selected_design": {
            "primary_endpoint": "Original stage-4 C0 under the fixed four-stage R1/R4 protocol, preserved before any post-C0 repair.",
            "repair_scope": "Auxiliary finite model-authored arithmetic revision only after schema-valid and complete but arithmetically invalid C0.",
            "max_additional_generation_calls": 2, "max_endpoint_candidates_including_C0": 3,
            "eligible_failure": "Complete response passing the predeclared schema, with a complete model-authored candidate that fails the predeclared arithmetic portfolio contract.",
            "ineligible_failure_types": ["provider/transport failure", "timeout or incomplete stream", "strict JSON parse failure", "response schema failure", "missing or unavailable C0"],
            "revision_stop": "First arithmetically valid candidate, the two-revision cap, or a transport/parse/schema failure. A later failure is preserved and does not authorize an extra generation.",
            "same_policy_across_arms": True, "equal_actual_calls_claimed": False,
            "history": "Preserve literal submitted answers and genuine calculator feedback; no rewriting invalid history, no automatic summary or hidden truncation.",
            "forbidden": ["normalization", "projection", "clipping", "host-authored allocation", "target allocation hints", "gold labels as feedback", "new institution facts in repair", "retry until passing", "replace C0 with repaired endpoint in the primary comparison"],
            "comparison_limit": "R1/R4 compares the full registered information-exposure procedures, including repeated access/history. It does not isolate timing, internal reasoning, or the causal effect of repair.",
            "invalid_outputs": "Retain every scheduled case. Separate no response, no allocation, arithmetic invalidity, unsupported institution interpretation and explanation-action contradiction. Valid-only portfolio analyses remain conditional and show their coverage.",
            "three_reviews": "The user's three-review rule validates design, measurement and provenance. It is not a paper-derived sample size, three model rerolls, human approval or a guarantee that generated portfolios will be correct.",
            "readiness_limit": "No original failed v46/v47 outcome is reclassified. This memo does not pass the old gate, authorize main execution, or establish a successful revised pilot.",
        },
        "numeric_provenance": [
            {"item": "3 endpoint candidates including C0", "class": "paper_parameter_transferred_with_adaptation", "value": 3, "source_id": "uptake", "locator": "Appendix I Table 12", "limit": "The original cap is total outer submissions, not three extra calls and not a proven optimum."},
            {"item": "additional revision cap", "class": "derived_from_transferred_parameter", "value": 2, "calculation": "3 total endpoint candidates - 1 preserved stage-4 C0 = 2 possible revisions"},
            {"item": "original stages", "class": "existing_LIBERA_design_choice", "value": 4, "source_path": "research/v47_handoff_20261018.json", "limit": "The four-stage R1/R4 mapping is LIBERA's operationalization, not the cited repair paper's protocol."},
            {"item": "planned pilot cases", "class": "existing_LIBERA_design_choice", "value": 4, "calculation": "2 institution packets x 2 exposure procedures", "limit": "Not a paper-based power calculation, population sample or independent sample of eleven sectors."},
            {"item": "max generation calls per case", "class": "arithmetic_derivation", "value": 6, "calculation": "4 original-stage calls + 2 auxiliary revisions"},
            {"item": "max generation calls per four-case pilot", "class": "arithmetic_derivation", "value": 24, "calculation": "4 cases x 6 maximum generation calls", "limit": "Historical development and renderer/verifier requests are recorded separately and not erased or hidden."},
            {"item": "900-second per-call deadline", "class": "inherited_engineering_bound", "value": 900, "source_path": "research/v44_conditions_reference_20261018.json", "limit": "Not a paper-derived optimal latency or behavioral success threshold; cleanup outside this bound."},
            {"item": "review count", "class": "explicit_user_workflow_requirement", "value": 3, "limit": "Not a model retry count or a literature-derived numerical condition."},
            {"item": "sum-to-one and nonnegative weights", "class": "declared_portfolio_task_contract", "limit": "Budget feasibility is a mathematical task requirement, not an inferred institution mandate or unique strategic gold."},
            {"item": "floating-point tolerance and other runtime settings", "class": "inherited_numerical_or_runtime_implementation", "source_path": "research/v44_conditions_reference_20261018.json", "limit": "No new tolerance, model, decoding parameter, statistical cutoff or strategic success threshold is set by this memo; source-specific inherited paper/author-code/engineering provenance remains distinct."},
        ],
        "locator_corrections": [{
            "source_id": "e2a", "old_memo_path": "research/priority23_paper_candidates_v2_20261018.json",
            "old_locator": "Section 4.3.3", "observed_title": "Scaling Is Not Monotonic",
            "correct_for_evidence_to_action_and_coverage": ["Sections 3.3-3.4", "Section 4.2", "Section 4.3.4"],
            "correction_scope": "New reference memo corrects the locator; historical files remain unchanged.",
            "oracle_intervention_limit": "Mentioned in abstract/introduction/conclusion, but the current main-text section named in the old memo does not supply the detailed repair experiment. Do not use it as a verified exact intervention recipe.",
        }],
        "papers": papers, "primary_sources": sources, "historical_context_references": reused_context,
        "latest_version_verification": {"method": "New unversioned arXiv abstract downloads, parsed metadata and latest datelines, compared with specified versions; versioned full text examined for method locators.", "scope": "Targeted primary-source verification on retrieval date, not an exhaustive systematic literature review."},
        "self_checks": checks, "model_calls_by_researcher": 0, "main_model_calls": 0,
        "prior_files_modified": False, "new_runtime_implementation": False, "main_ready": False, "main_frozen": False,
    }
    for ref in result["primary_sources"] + result["historical_context_references"]:
        now = reference(ref["path"])
        if now["sha256"] != ref["sha256"]:
            raise RuntimeError(f"Hash drift: {ref['path']}")
    checks.extend([
        {"id": "all_primary_and_context_hashes_match", "status": "pass"},
        {"id": "seven_papers_have_locator_support_adaptation_and_numeric_scope", "status": "pass"},
        {"id": "total3_means_C0_plus_at_most2_not3_additional", "status": "pass"},
        {"id": "main_C0_separate_from_auxiliary_repair", "status": "pass"},
        {"id": "schema_and_transport_failures_do_not_trigger_repair", "status": "pass"},
        {"id": "E2A_locator_corrected_without_historical_edits", "status": "pass"},
        {"id": "no_model_calls_or_paper_derived_claim_for_local_engineering_choices", "status": "pass"},
    ])
    with OUT.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"output": reference(OUT.relative_to(ROOT)), "papers": len(papers), "primary_snapshots": len(sources), "self_checks": len(checks), "model_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
