"""Preserve precise parameter-source locators without rewriting the v4.8 basis."""
import json
from pathlib import Path
from bs4 import BeautifulSoup
from pypdf import PdfReader
from build_v48_reference_basis import ROOT, download, metadata, reference, utc

OUT = ROOT / "research/v48_parameter_reference_addendum_20261018.json"


def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    pb_abs = download("portbench_abs_latest.html", "https://arxiv.org/abs/2605.27887")
    pb_full = download("portbench_2605_27887v6.html", "https://arxiv.org/html/2605.27887v6")
    fv_abs = download("finvector_abs_latest.html", "https://arxiv.org/abs/2610.08882")
    fv_pdf = reference("research/evidence/v45_structured_output_20261018/finvector_2610_08882.pdf", url="https://arxiv.org/pdf/2610.08882v1", kind="reused_primary_snapshot")
    assert fv_pdf["sha256"] == "a7551b10caddb0d9f94a215f29fad4771f5cd2addae56ea43d706f7c5c1c1dfa"
    pb_meta, fv_meta = metadata(pb_abs), metadata(fv_abs)
    assert pb_meta["latest_version_observed"] == 6
    assert fv_meta["latest_version_observed"] == 1
    pb_soup = BeautifulSoup((ROOT / pb_full["path"]).read_bytes(), "html.parser")
    pb_text = pb_soup.get_text(" ", strip=True)
    reader = PdfReader(ROOT / fv_pdf["path"])
    page4 = " ".join(reader.pages[3].extract_text().split())
    checks = [
        {"id": "PortBench_latest_v6_2026_10_09", "passed": "9 Oct 2026" in pb_meta["dateline_original"]},
        {"id": "FinVector_latest_v1_2026_10_06", "passed": "6 Oct 2026" in fv_meta["dateline_original"]},
        {"id": "PortBench_T5_60day", "passed": "60-day lookback window" in pb_text and "T5 (Maximum-Sharpe allocation)" in pb_text},
        {"id": "PortBench_C4_F9_annualization", "passed": "252" in pb_text and "Annualized estimated volatility" in pb_text and "C.4" in pb_text and "F.9" in pb_text},
        {"id": "PortBench_Eq8_similarity", "passed": "(8)" in pb_text and "reference similarity" in pb_text},
        {"id": "PortBench_8192", "passed": "8192" in pb_text and "thinking mode enabled by default" in pb_text},
        {"id": "FinVector_eval_seed_not_only_training_seed", "passed": "4.1 Four frozen arms" in page4 and "seed 3407, greedy decoding, disabled thinking, batch size 8" in page4},
        {"id": "FinVector_700_cap_and_MLX_engine", "passed": "700-new-token ceiling" in page4 and "MLX 0.32.2" in page4 and "MLX-LM 0.31.3" in page4},
        {"id": "FinVector_PDF_historical_hash_unchanged", "passed": True},
    ]
    if not all(x["passed"] for x in checks):
        raise AssertionError(checks)
    payload = {
        "schema_version": "libera_v48_parameter_reference_addendum_1.0", "created_at_utc": utc(),
        "scope": "Two inherited parameter sources rechecked for precise provenance and current versions. Supplements, does not rewrite, v48_reference_basis_20261018.json.",
        "primary_sources": [{**pb_abs, "source_id": "portbench_abs_latest"}, {**pb_full, "source_id": "portbench_fulltext_v6"}, {**fv_abs, "source_id": "finvector_abs_latest"}, {**fv_pdf, "source_id": "finvector_pdf_v1"}],
        "metadata": {"portbench": pb_meta, "finvector": fv_meta},
        "checked_parameters": [
            {"parameter": "lookback", "value": 60, "unit": "daily return lookback observations in LIBERA", "paper_locator": "PortBench v6 Appendix C.1, T5 maximum-Sharpe allocation", "paper_url": "https://arxiv.org/html/2605.27887v6", "direct_support_ko": "T5는 60-day lookback에서 연율화 평균과 공분산을 추정한다.", "application_class": "paper_value_transferred_to_new_task", "limit_ko": "원 다자산 최대-Sharpe 과제와 LIBERA 11개 산업 ETF 자료의 목적은 다르다. 60개 수익률을 확보하는 날짜 선택은 자료·구현 규칙이며 최적 창 길이 또는 기관 고유 위험선호를 뜻하지 않는다."},
            {"parameter": "annualization", "value": 252, "paper_locator": "PortBench v6 Appendix C.4 execution/return accounting and classical strategies; Appendix F.9 decisions/covariance estimates", "paper_url": "https://arxiv.org/html/2605.27887v6", "direct_support_ko": "일간 수익률 변동성에 sqrt(252), 공분산 기반 추정 변동성에 sqrt(252*w' Sigma w)를 사용한다.", "application_class": "direct_formula_with_task_adaptation", "limit_ko": "부적합 비중을 정상 포트폴리오로 정규화하는 근거가 아니며, 미래 손실확률이나 수익률 예측을 입증하지 않는다. 원 연구의 미투자 현금 처리는 가져오지 않는다."},
            {"parameter": "allocation_distance", "formula_LIBERA": "d(w,v)=0.5*sum_i(abs(w_i-v_i))", "paper_formula": "s_acc=1-0.5*sum_i(abs(w_i-w*_p,i))", "paper_locator": "PortBench v6 Appendix C.2 Equation (8)", "paper_url": "https://arxiv.org/html/2605.27887v6", "direct_support_ko": "원식은 정규화된 long-only 배분과 계산 참조 사이의 유사성이다.", "application_class": "distance_component_adapted_to_two_model_proposals", "limit_ko": "LIBERA에서는 두 유효 제안 간 거리로만 사용한다. 비교 제안 v를 정답 비중으로 간주하지 않으며 1-distance를 기관 전략 정확도로 부르지 않는다."},
            {"parameter": "max_output_tokens", "value": 8192, "paper_locator": "PortBench v6 Section 3.1", "paper_url": "https://arxiv.org/html/2605.27887v6", "application_class": "paper_value_transferred_to_different_model_and_task", "limit_ko": "원 연구는 thinking 기본 활성화이며 현재 4B가 평가 모델 목록에 없다. FinVector의 700-token 평가와 구분하고 현재 과제에 대한 최적·충분 상한이라고 주장하지 않는다."},
            {"parameter": "seed", "value": 3407, "paper_locator": "FinVector-Market-4B v1 Section 4.1, PDF page 4, paragraph immediately after Table 3", "paper_url": "https://arxiv.org/pdf/2610.08882v1", "direct_support_ko": "네 평가 조건에 공통 seed 3407을 명시한다. 학습 seed만에서 추론한 값이 아니다.", "application_class": "reported_paper_value_with_backend_adaptation", "limit_ko": "3407이라는 숫자는 직접 논문 선례이고 Ollama의 seed 요청 필드에 적용하는 것은 backend 변형이다. MLX와 Ollama의 난수·토큰·출력 동등성이나 최적값의 근거가 아니다. 순수 무근거 공학 수치로 분류하지 않는다."},
            {"parameter": "greedy_and_thinking", "values": {"greedy": True, "thinking": False}, "paper_locator": "FinVector-Market-4B v1 Section 4.1, PDF page 4", "paper_url": "https://arxiv.org/pdf/2610.08882v1", "application_class": "paper_condition_with_Ollama_T0_translation", "limit_ko": "원 평가 MLX 0.32.2/MLX-LM 0.31.3, batch8, max700과 현재 런타임은 다르다. JSON schema를 프롬프트에 넣은 조건이 Ollama constrained decoding과 동일하지 않다. 미보고 repetition/presence/frequency penalty를 논문 평가 설정으로 단정하지 않는다."},
        ],
        "engineering_parameters_not_established_by_these_papers": ["Q4_K_M quantization", "65536 context tokens", "900-second per-call deadline", "num_thread=2", "num_batch=512", "1e-6 sum tolerance", "exact Ollama engine/template/binary pins"],
        "checks": checks, "all_passed": True,
        "memo_reference": reference("research/v48_reference_basis_20261018.json"),
        "historical_snapshot_manifest": reference("research/evidence/v45_structured_output_20261018/manifest.json"),
        "model_calls": 0, "prior_files_modified": False,
    }
    with OUT.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"output": reference(OUT.relative_to(ROOT)), "checks": len(checks), "all_passed": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
