"""Create a new, immutable pre-generation reference record; no model calls."""
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research/v44_conditions_reference_20261018.json"
HTML = ROOT / "research/v44_conditions_reference_20261018.html"
MANIFEST = ROOT / "research/evidence/v44_primary_sources_20261018/manifest.json"

SOURCES = {
    "finvector_paper": {"url": "https://arxiv.org/pdf/2610.08882", "kind": "author_preprint", "locator": "section 4.1, Table 3; section 10 and Table 8",
        "verified": "Qwen3.5-4B 기본 모델을 별도로 평가한다. 네 조건의 seed 3407, greedy, thinking 비활성화, batch 8, 새 출력 700, MLX 0.32.2 및 MLX-LM 0.31.3을 명시한다. 명시적 JSON schema 조건을 비교한다.",
        "limits": "penalty 값은 보고하지 않는다. 공개 예제는 비공개 평가기와 다르다. 원문 base revision은 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a이며 Ollama manifest와 동일한 가중치 변환임을 증명하지 않았다."},
    "finvector_example": {"url": "https://github.com/alinakhay/FinVector-Market-4B/blob/main/examples/inference_mlx.py", "kind": "author_public_code", "locator": "saved snapshot lines 20, 32-38",
        "verified": "예제 자체가 벤치마크 prompt가 아니라고 명시한다. enable_thinking=False와 generate(..., max_tokens=700)를 쓰며 별도 sampler 또는 logits processor를 전달하지 않는다.",
        "limits": "이 예제에서 비공개 평가기의 모든 생성 조건을 역추론할 수 없다."},
    "mlx_lm": {"url": "https://github.com/ml-explore/mlx-lm/blob/v0.31.3/mlx_lm/generate.py", "kind": "official_versioned_code", "locator": "saved snapshot lines 307-313, 386, 409-416; generate/stream_generate",
        "verified": "기본 sampler는 argmax이며 logits_processors 기본값은 None이다. processor가 제공될 때만 logits를 가공한다.",
        "limits": "Ollama와의 수치·토큰 단위 동등성이나 FinVector 비공개 실행기의 penalty 설정을 증명하지 않는다."},
    "portbench": {"url": "https://arxiv.org/html/2605.27887v6#S3.SS1", "kind": "author_preprint_versioned", "locator": "section 3.1",
        "verified": "temperature 0 및 최대 출력 8192를 보고한다. 기본 thinking은 켜져 있고 대상 목록에 Qwen3.5-4B가 없다.",
        "limits": "8192를 이번 소형 모델·산업 배분 과제에 옮기는 적용이지 동일 실험 재현이나 최적 출력 길이의 증거가 아니다."},
    "qwen_card": {"url": "https://huggingface.co/Qwen/Qwen3.5-4B", "kind": "official_model_card", "locator": "Instruct mode; Best Practices",
        "verified": "API/template 매개변수로 thinking을 끄는 방식을 제공한다. 일반 non-thinking 권고는 T=0.7, top_p=0.8, top_k=20, presence=1.5, repetition=1.0이다.",
        "limits": "FinVector greedy 조건과 다르다. reasoning 권고도 페이지 두 위치에서 서로 다르므로 단일 최적값으로 취급하지 않는다. 이번 T0·무벌점 조건을 제작사의 일반 최적 권고라고 부르지 않는다."},
    "ollama_chat": {"url": "https://docs.ollama.com/api/chat", "kind": "official_documentation", "locator": "format, think, keep_alive request fields",
        "verified": "format=json과 think=false를 지원하며 keep_alive=0은 모델 해제를 요청한다.",
        "limits": "API의 JSON 형식 제어는 논문의 prompt schema만 제공한 통제와 같다고 가정할 수 없다."},
    "ollama_modelfile": {"url": "https://docs.ollama.com/modelfile#valid-parameters-and-values", "kind": "official_documentation", "locator": "repeat_penalty, seed, num_ctx, num_predict",
        "verified": "repeat_penalty=1은 벌점을 끄는 값이며 문맥·출력·seed의 API 의미를 문서화한다.",
        "limits": "구현 매개변수의 뜻을 뒷받침하며 금융 실험 최적값을 보고하지 않는다."},
    "ollama_versioned_source": {"url": "https://github.com/ollama/ollama/tree/v0.35.1", "kind": "official_versioned_code", "locator": "saved api/types.go 160-170; routes.go 2899-2923,2956-2957; prompt.go 35-74; llama_server.go 284,423,1660-1670",
        "verified": "truncate·shift·debug render 필드, 무잘림 전달·렌더만 반환하는 분기, 요청 temperature·penalty·seed 전달을 확인했다.",
        "limits": "API 소스 확인은 설치 바이너리의 모든 내부 수치 경로를 독립 재현한 것이 아니다. 삭제된 옛 sample/samplers.go를 현재 엔진 근거로 쓰지 않는다."},
}

CONDITIONS = [
    {"field": "model", "value": "qwen3.5:4b-q4_K_M", "level": "paper_model_family_plus_engineering_quantization", "sources": ["finvector_paper"],
     "reason": "금융 과제에서 기본 4B 평가 선례가 있다. Q4_K_M와 설치 digest는 실행 관측으로 고정한다.", "not_supported": "FinVector adapter 사용·원논문 점수 재현·같은 HF revision의 무손실 변환 주장"},
    {"field": "think", "value": False, "level": "direct_financial_paper_precedent_api_adaptation", "sources": ["finvector_paper", "qwen_card", "ollama_chat"],
     "reason": "별도 thinking 출력을 끈다.", "not_supported": "추론 능력 부재 또는 내부 사고 과정의 관측"},
    {"field": "format_and_prompt", "value": "format=json plus explicit response fields", "level": "paper_prompt_control_plus_api_implementation", "sources": ["finvector_paper", "finvector_example", "ollama_chat"],
     "reason": "모든 조건에 동일한 출력 필드와 JSON 제어를 사용한다.", "not_supported": "JSON 유효성이 문서 해석·전략 타당성을 보장한다는 주장"},
    {"field": "temperature", "value": 0, "level": "paper_greedy_backend_adaptation", "sources": ["finvector_paper", "mlx_lm", "portbench"],
     "reason": "greedy를 지향하는 통제다. T0는 PortBench에도 직접 보고된다.", "not_supported": "서로 다른 엔진·GPU에서 출력이 완전히 같다는 보장"},
    {"field": "seed", "value": 3407, "level": "direct_financial_paper_value", "sources": ["finvector_paper"],
     "reason": "평가 seed를 직접 가져온다.", "not_supported": "greedy·GPU 실행의 완전한 결정성 보장"},
    {"field": "num_predict", "value": 8192, "level": "paper_value_transferred_to_different_model_and_task", "sources": ["portbench"],
     "reason": "네 단계 출력의 연구 상한으로 적용한다.", "not_supported": "FinVector의 700-token 조건 준수·8192 충분성 또는 최적성"},
    {"field": "repeat_penalty_presence_penalty_frequency_penalty", "value": [1.0, 0.0, 0.0], "level": "public_implementation_translation_not_paper_reported", "sources": ["finvector_example", "mlx_lm", "ollama_modelfile", "ollama_versioned_source"],
     "reason": "공개 최소 예제의 무가공 argmax 경로를 무벌점 요청으로 옮기는 구현 선택이다.", "not_supported": "FinVector 벤치마크에 이 세 값이 보고되었다는 주장"},
    {"field": "top_p_top_k_min_p", "value": [0.95, 20, 0.0], "level": "observed_defaults_and_explicit_engineering_control", "sources": ["ollama_versioned_source"],
     "reason": "관측한 모델 top_p/top_k를 기록하고 min_p는 중립값으로 명시한다. 전체 요청·기본값을 저장한다.", "not_supported": "금융 논문에서 선택한 최적값 또는 모든 엔진에서 항상 무효라는 주장"},
    {"field": "num_ctx", "value": 65536, "level": "engineering_capacity_candidate", "sources": ["ollama_modelfile", "ollama_versioned_source"],
     "reason": "기존 실측 후보를 유지하고 매 단계 실제 렌더링된 전체 이력과 상한을 점검한다.", "not_supported": "논문 최적 문맥·네 단계 전체의 수용성 검증 완료"},
    {"field": "num_thread_num_batch_serial_requests", "value": [2, 512, 1], "level": "measured_environment_and_engineering_control", "sources": [],
     "reason": "노트북 기술 진단과 같은 운영 조건으로 단일 요청씩 진행한다.", "not_supported": "FinVector 평가 batch=8과 num_batch=512의 동일성"},
    {"field": "truncate_shift_debug_preflight", "value": {"truncate": False, "shift": False, "debug_render_before_each_generation": True}, "level": "official_versioned_api_history_preservation_control", "sources": ["ollama_versioned_source"],
     "reason": "원문과 명시적 이전 응답을 삭제하지 않고 보존하는 사전 점검이다. 초과·누락은 기록하고 중단한다.", "not_supported": "모든 긴 문맥의 의미적 기억이 유지된다는 주장"},
    {"field": "request_timeout_seconds_keep_alive", "value": [900, 0], "level": "prior_runtime_engineering_limit_and_resource_control", "sources": ["ollama_chat"],
     "reason": "900초는 사전에 고정한 운영 제한이며 keep_alive=0은 해제 제어다. 120초 진단 상한을 연구 제한으로 전용하지 않는다.", "not_supported": "논문 최적 시간 제한 또는 시간 초과의 금융 의미 실패 해석"},
    {"field": "engine_and_backend", "value": "Ollama 0.35.1 / Windows / Vulkan Intel Arc 140V", "level": "observed_runtime_pin_not_paper_replication", "sources": ["ollama_versioned_source"],
     "reason": "digest·버전·템플릿·바이너리·실제 배치 근거를 실행기에서 고정한다.", "not_supported": "MLX/Apple Metal과 동일한 수치 결과·전용 VRAM 16GB·양자화 성능 보장"},
]


def main():
    if OUTPUT.exists() or HTML.exists():
        raise FileExistsError("Reference file must remain immutable after preparation; write a new revision instead")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    records = manifest["records"]
    for record in records:
        if hashlib.sha256((ROOT / record["path"]).read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("Primary source snapshot changed: " + record["path"])
    local = ROOT / "research/local_sector_latency_20261018.json"
    value = {
        "schema_version": "libera_v44_conditions_reference_1.0", "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "primary_sources_verified_before_generation; recommendation_for_one_pilot_case; not_main_readiness_approval",
        "freeze_policy": "Hash this complete file before generation. Do not update it after any pilot response; subsequent findings belong in new audit files.",
        "all_numbers_reported_by_papers": False,
        "critical_interpretation": "핵심 연구 조건은 논문 선례를 쓰되 구현·자원 수치는 근거 수준을 별도로 공개한다. 모든 수치가 논문에 직접 보고됐다는 주장은 허용되지 않는다.",
        "recommended_request": {"model": "qwen3.5:4b-q4_K_M", "think": False, "format": "json", "keep_alive": 0, "truncate": False, "shift": False,
            "options": {"temperature": 0, "seed": 3407, "num_predict": 8192, "num_ctx": 65536,
                        "num_thread": 2, "num_batch": 512, "repeat_penalty": 1.0, "presence_penalty": 0.0,
                        "frequency_penalty": 0.0, "top_p": 0.95, "top_k": 20, "min_p": 0.0}},
        "recommended_execution": {"engine": "0.35.1", "model_digest": "d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04",
            "request_timeout_seconds": 900, "serial_requests": 1, "authorized_pilot_cases": 1, "stages_per_case": 4,
            "count_basis": "One case and four stages follow the authorized LIBERA pilot design, not a paper-derived statistical sample-size calculation.",
            "automatic_retry": False, "main_frozen": False},
        "conditions": CONDITIONS, "sources": SOURCES, "primary_code_snapshot_manifest": {"path": MANIFEST.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest()},
        "primary_code_sources": records,
        "local_measurement_reference": {"path": local.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(local.read_bytes()).hexdigest(),
            "scope": "Engineering observations only; 32-token first-stage probes do not establish four-stage or 8192-token feasibility."},
        "falsifiable_checks": [
            "Before every generation, verify actual engine/model/template pins and saved request settings; mismatch stops the case.",
            "Save the rendered prompt and verify complete source passages and visible history in order; no silent truncation or context shift.",
            "Record every terminal reason, actual tokens, timing, failed/partial output and resource samples; length/timeout does not establish semantic failure.",
            "Check raw JSON/schema, eleven allowed sector IDs, references and exact allocation sum residual without repairing the response.",
            "One completed case tests feasibility only; it cannot estimate R1/R4 effects, institutional population effects, or future return/risk performance.",
            "Post-run self-verification does not authorize generation retries or post-outcome changes to the frozen response/evaluation record."],
        "no_new_model_calls": True, "existing_plan_paper_config_modified": False,
        "verification_notes": ["Primary paper, author example, versioned MLX code, official model card and Ollama API/code were checked independently.",
            "Web extraction line offsets differed from live raw downloads. Local source SHA and local snapshot line numbers are authoritative for implementation locators.",
            "The exact bundled llama.cpp greedy/sampler path was not independently re-derived here; T0 and neutral penalties are an explicitly limited backend adaptation, not proof of complete decoding equivalence."]}
    OUTPUT.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    e = html.escape
    rows = []
    for item in CONDITIONS:
        links = " · ".join(f'<a href="{e(SOURCES[s]["url"])}">{e(s)}</a>' for s in item["sources"]) or "로컬 운영 기록"
        rows.append("<tr>" + "".join(f"<td>{x}</td>" for x in [e(item["field"]),e(json.dumps(item["value"], ensure_ascii=False)),e(item["level"]),e(item["reason"]),e(item["not_supported"]),links]) + "</tr>")
    content = f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>v4.4 실행 조건의 원문 근거</title><style>body{{max-width:1200px;margin:32px auto;padding:0 20px;font-family:system-ui;line-height:1.7;color:#17283a}}h1{{font-size:1.7rem}}table{{border-collapse:collapse;width:100%;font-size:.86rem}}th,td{{border:1px solid #d5dce5;padding:9px;vertical-align:top;text-align:left}}th{{background:#edf3f7}}.scroll{{overflow:auto}}.notice{{padding:14px;background:#edf5f8;border-left:5px solid #27637a}}code{{overflow-wrap:anywhere}}</style><h1>v4.4 실행 조건의 원문 근거</h1><p class="notice">핵심 연구 조건의 논문 선례와 구현·자원 수치를 구분했다. 모든 숫자가 논문 보고값이라는 주장은 할 수 없다. 이번 기록은 한 사례의 네 단계 예비 실행에 앞선 근거이며 본과제 준비 완료 판정이 아니다.</p><p>FinVector는 기본 Qwen3.5-4B를 명시적 JSON·greedy·thinking 비활성화로 평가했다. 해당 평가의 출력 상한은 700이다. 이번 8192는 PortBench의 다른 모델·과제에서 옮긴 값이다. 무벌점 값은 저자 공개 최소 예제와 MLX 기본 동작을 옮긴 구현 선택이며 비공개 벤치마크의 보고값이 아니다. Qwen 일반 권장값과도 구분한다.</p><div class="scroll"><table><tr><th>조건</th><th>권고값</th><th>근거 수준</th><th>적용 이유</th><th>뒷받침하지 못하는 주장</th><th>원문</th></tr>{''.join(rows)}</table></div><p>실제 출력·입력 보존·수치 형식·종료 사유를 예비에서 확인해야 한다. 한 사례로 절차의 비교 효과나 기관 전체의 행동을 추정하지 않는다. 원문 인용은 공개 1차 자료만 사용했고 구현 소스 여섯 개의 내용 해시를 보존했다.</p><p><a href="v44_conditions_reference_20261018.json">고정할 JSON·출처·검증 범위</a> · <a href="evidence/v44_primary_sources_20261018/manifest.json">공식 소스 파일 해시</a></p></html>'''
    HTML.write_text(content, encoding="utf-8")
    print(json.dumps({"json": OUTPUT.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(), "html": HTML.relative_to(ROOT).as_posix(), "model_calls": 0}))


if __name__ == "__main__":
    main()
