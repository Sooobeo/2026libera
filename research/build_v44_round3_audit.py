"""Offline semantic-audit closure for the predetermined, interrupted v4.4 case.

Reads immutable artifacts; never contacts a model or repairs a response.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_REL = "data/local_sector_runtime/single_case_v44_20261018"
RUN = ROOT / RUN_REL
RUBRIC = "research/evaluator_only/fidelity_q2_r1_prerun_reference_20261018.json"
OUT = ROOT / "research/v44_single_case_round3_20261018.json"
HTML = OUT.with_suffix(".html")


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fingerprint(path: Path):
    raw = path.read_bytes()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def main():
    summary = read(RUN / "summary.json")
    rubric = read(ROOT / RUBRIC)
    assert fingerprint(ROOT / RUBRIC)["sha256"] == "8022c19d7b5e9654139996d88cac230cb12d29b30fcf7e817850203c02c35f38"
    assert summary["status"] == "hard_deadline"
    assert summary["completed_workflow_stages"] == summary["completed_cases"] == 0
    body = read(RUN / "stage1_transport/authoritative_body.json")
    transmitted = json.loads(body["messages"][1]["content"])
    original_messages = read(RUN / "fidelity_q2_2026__R1/stage1_request.json")
    original = json.loads(original_messages[1]["content"])
    packet = read(ROOT / "data/sector_documents/packets/pilot/fidelity_q2_2026.json")
    supervisor = read(RUN / "stage1_transport/supervisor_result.json")
    cleanup = read(RUN / "stage1_transport/unload_and_residency.json")
    raw_path = RUN / "stage1_transport/http_0001_generation/raw_stream.bin"
    raw = raw_path.read_bytes()
    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    content = "".join(event.get("message", {}).get("content", "") for event in events)
    thinking = "".join(event.get("message", {}).get("thinking", "") for event in events)
    try:
        json.loads(content)
        parse_error = None
    except json.JSONDecodeError as error:
        parse_error = {"type": type(error).__name__, "message": str(error), "position": error.pos}
    expected = ["source_id", "interpretations", "weights", "alternatives", "risk_discussion", "unresolved", "submitted_constraints"]
    key_occurrences = {key: len(re.findall(r'"' + re.escape(key) + r'"\s*:', content)) for key in expected}
    # Parse only individual complete values. Never close, complete or score the
    # interrupted JSON document as if it were a submitted response.
    decoder = json.JSONDecoder()
    comparisons = []
    incomplete_fields = []
    for key, value in {"stage": original["stage"], "task": original["task"], **original["common_market"]}.items():
        match = re.search(r'"' + re.escape(key) + r'"\s*:\s*', content)
        if not match:
            continue
        try:
            observed, end = decoder.raw_decode(content, match.end())
        except json.JSONDecodeError:
            incomplete_fields.append(key)
            continue
        comparisons.append({"field": key, "exact_original_value": observed == value, "start_char": match.start(), "end_char": end})
    comparisons.sort(key=lambda row: row["start_char"])
    assert len(comparisons) == 17 and all(row["exact_original_value"] for row in comparisons)
    assert incomplete_fields == ["lookback_compound_return"]
    evidence_names = [RUBRIC, "research/build_v44_round3_audit.py"]
    evidence_names.extend(rubric["evidence_files"])
    evidence_names.extend(f"{RUN_REL}/{name}" for name in [
        "summary.json", "runtime.json", "invocation.json", "run_failure.json", "manifest_snapshot.json",
        "fidelity_q2_2026__R1/failure.json", "fidelity_q2_2026__R1/stage1_request.json",
        "stage1_transport/authoritative_body.bin", "stage1_transport/authoritative_body.json",
        "stage1_transport/projection_validation.json", "stage1_transport/supervisor_result.json",
        "stage1_transport/unload_and_residency.json", "stage1_transport/pin_before_generation.json",
        "stage1_transport/render_only/validation.json", "stage1_transport/render_only/rendered_prompt.txt",
        "stage1_transport/http_0001_generation/raw_stream.bin", "stage1_transport/http_0001_generation/events.jsonl",
        "stage1_transport/http_0001_generation/request.json",
    ])
    evidence = {name: fingerprint(ROOT / name) for name in dict.fromkeys(evidence_names)}
    reference_matches = all(evidence[name]["sha256"] == item["sha256"] for name, item in rubric["evidence_files"].items())
    checks = []

    def check(identifier, condition, meaning):
        assert condition, identifier
        checks.append({"id": identifier, "status": "pass", "meaning": meaning})

    check("pre_run_reference_unchanged", reference_matches, "All original sources and offline rubric dependencies match their pre-run hashes.")
    check("terminal_failed_case_retained", summary["cases_with_generation_attempt"] == 1 and summary["automatic_retries"] == 0, "One attempted case is retained; no replacement or retry is counted.")
    check("no_completed_response", summary["http_streams_completed"] == 0 and summary["completed_workflow_stages"] == 0 and not list(RUN.rglob("*_record.json")), "No completed workflow record exists.")
    check("later_stages_unstarted", summary["generation_stages_not_started"] == [2, 3, 4], "Stages 2–4 are unobserved, not three independently failed semantic answers.")
    check("correct_visible_source", transmitted["institution_document"] == original["institution_document"] == packet, "The actual request included the unchanged Fidelity Q2 public packet with 12 passages; hidden annotations are not used as required model input.")
    check("actual_stream_integrity", len(events) == 6191 and len(raw) == 818079, "All nonempty raw stream lines parse as transport events; this is not a generated token count.")
    check("no_terminal_event", all(event.get("done") is False for event in events), "No terminal done:true event exists in the generation stream.")
    check("correct_stream_model", all(event.get("model") == "qwen3.5:4b-q4_K_M" for event in events), "All observed response events name the requested model.")
    check("partial_not_submitted_json", parse_error is not None and len(content) == 7681 and not thinking, "A partial content stream exists, but it is not a complete JSON answer.")
    check("required_keys_prefix_diagnostic_only", all(value == 0 for value in key_occurrences.values()), "The seven requested keys are absent in the available prefix. This does not manufacture an answer or a semantic score.")
    check("subset_input_repetition_verified", len(comparisons) == 17 and all(row["exact_original_value"] for row in comparisons), "Seventeen complete field values match the actual original input; an additional list is unfinished. No whole-input-copy claim is made.")
    check("no_research_completion_or_freeze", summary["main_model_calls"] == 0 and summary["main_freeze"] is False and summary["human_semantic_pass"] is False, "Main remains unrun and unfrozen, with no semantic approval.")
    check("cleanup_observed", cleanup["status"] == "no_resident_models_observed" and cleanup["unload"]["value"]["done_reason"] == "unload" and all(item["value"]["models"] == [] for item in cleanup["ps"]), "Cleanup reports successful unload and an empty resident-model list at that observation.")
    check("raw_artifacts_unchanged_during_review", all(fingerprint(ROOT / name) == item for name, item in evidence.items()), "All referenced files remain byte-identical during this read-only audit.")

    report = {
        "schema_version": "v44_single_case_semantic_audit_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reviewer": "independent_assistant_round3",
        "audit_status": "completed",
        "case_status": "incomplete_hard_deadline",
        "semantic_evaluation_status": "not_evaluable_no_completed_response",
        "research_task_pass": False,
        "human_semantic_approval": False,
        "main_ready": False,
        "case_id": summary["case_id"],
        "pre_run_rubric": {"path": RUBRIC, **evidence[RUBRIC]},
        "summary": summary,
        "timing": {"whole_script_wall_seconds": summary["wall_seconds"], "supervised_child_elapsed_seconds": supervisor["elapsed_seconds"], "supervised_deadline_seconds": supervisor["deadline_seconds"], "scope_note": "Child setup, metadata, renderer and generation share the deadline. Cleanup and process overhead are outside it; wall times are not output throughput."},
        "partial_stream": {
            "raw_bytes": len(raw), "parseable_transport_events": len(events), "transport_event_count_is_not_token_count": True,
            "done_true_events": sum(event.get("done") is True for event in events),
            "content_characters": len(content), "thinking_characters": len(thinking),
            "first_recorded_event_utc": events[0].get("created_at"), "last_recorded_event_utc": events[-1].get("created_at"),
            "complete_json": False, "parse_error": parse_error,
            "required_response_keys_prefix_occurrences": key_occurrences,
            "prefix_occurrences_are_not_submission_detection": True,
            "input_repetition": {"scope": "individually completed field values only", "matching_fields": comparisons, "matching_complete_field_count": len(comparisons), "incomplete_fields": incomplete_fields, "whole_input_reproduction_claimed": False},
            "prefix_excerpt": content[:240], "suffix_excerpt": content[-180:],
            "final_eval_count": None, "final_prompt_eval_count": None, "quality_inference": "none"
        },
        "evaluation": {
            "eligible_completed_claims": 0, "claim_assessments": [],
            "category_counts": {key: None for key in ["supported", "contradicted", "not_stated", "uncertain"]},
            "absence_rule": "Missing or incomplete output is unobserved/not submitted. It is not a not_stated or contradicted source claim.",
            "dimensions": [{"id": row["id"], "status": "not_evaluable_no_completed_response", "pre_run_rule": row["rule"], "reference": row["reference"]} for row in rubric["audit_dimensions"]],
            "source_rating_accuracy": None, "citation_entailment_score": None, "portfolio_weights": None,
            "benchmark_tilts": None, "portfolio_risk": None, "strategy_quality": None, "composite_score": None,
            "stage1_weight_rule": "Stages 1 and 2 may legitimately leave weights empty. The present failure is absence of a completed interpretation/response, not absence of an early allocation.",
            "input_values_not_model_decisions": True,
            "no_exact_weight_gold_or_invented_risk_cap": True
        },
        "topic_connection": {
            "intended_construct": "Whether an institution-document interpretation is preserved through an evidence-linked industry allocation workflow.",
            "observed_result": "One attempted first-stage generation did not deliver a completed interpretation within its deadline. No portfolio or four-stage trajectory is observed.",
            "not_identified": ["institution-specific strategy quality", "source-label fidelity of a completed answer", "R1 versus R4 effect", "cross-institution similarity or convergence", "portfolio performance"],
            "source_error_vs_decision": "Neither an institutional factual error nor an independent allocation choice can be assigned from this unfinished input-repeating prefix.",
            "next_revision_limit": "Input repetition motivates reviewing task adherence, but this one incomplete run does not establish its cause or validate a prompt, model, or runtime remedy. Any revision must be separately recorded before another run."
        },
        "scope_limits": [
            "Audit checks passing means the audit is evidence-consistent, not that the research task passed.",
            "Offline reference annotations and the original PDF are evaluator-only; full-PDF facts absent from the visible packet are not missing model requirements.",
            "No completed response was repaired, rescored as a synthetic portfolio, or replaced by its input benchmark.",
            "This review makes no claim of human validation, future risk prediction, financial strategy failure, or successful four-stage execution.",
            "Earlier 32-output-token engineering diagnostics are different tasks and do not validate an 8192-token research answer."
        ],
        "checks": checks, "check_count": len(checks), "evidence_files": evidence,
        "mutations": {"model_calls": 0, "raw_result_edits": 0, "runtime_edits": 0, "plan_or_paper_edits": 0},
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    esc = html.escape
    raw_link = f"../{RUN_REL}/stage1_transport/http_0001_generation/raw_stream.bin"
    html_text = f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>단일 사례 3차 감사 — 미완료·평가 불가</title>
<style>body{{font-family:system-ui,sans-serif;line-height:1.65;color:#172434;background:#f3f6f8;margin:0}}main{{max-width:900px;margin:28px auto;padding:30px;background:white;border-radius:12px}}h1{{font-size:1.75rem}}h2{{font-size:1.2rem;margin-top:28px}}.status{{border-left:5px solid #a35a17;padding:12px 18px;background:#fff6e9}}table{{border-collapse:collapse;width:100%;font-size:.95rem}}th,td{{border-bottom:1px solid #dce3e8;text-align:left;vertical-align:top;padding:9px}}code,pre{{font-family:ui-monospace,monospace;font-size:.83rem}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f8;padding:14px}}a{{color:#145c91}}.small{{font-size:.88rem;color:#4b5b68}}</style></head><body><main>
<p class="small">2026-10-18 · Fidelity Q2 2026 · R1 · 사전 지정 1사례 · 독립 3차 검토</p>
<h1>감사는 완료됐지만, 사례가 끝나지 않아 의미 평가는 불가능합니다</h1>
<p class="status">첫 단계가 제한시간에 종료됐습니다. 완료된 답변·단계·사례는 모두 0개이고, 2–4단계는 시작되지 않았습니다. 본실험 호출은 0회이며 동결·사람의 의미 검증 승인도 없습니다.</p>
<table><thead><tr><th>관찰</th><th>원본에서 확인한 내용</th></tr></thead><tbody>
<tr><td>시간</td><td>전체 {summary['wall_seconds']:.3f}초; 감독 대상 프로세스 {supervisor['elapsed_seconds']:.3f}초 / 설정 제한 {supervisor['deadline_seconds']}초. 정리 작업과 운영체제 오버헤드 때문에 범위가 다릅니다.</td></tr>
<tr><td>생성 도중의 출력</td><td>{len(raw):,}바이트, 정상 파싱된 스트림 이벤트 {len(events):,}개, 내용 {len(content):,}자. 이벤트 수는 토큰 수가 아닙니다. 완료 이벤트는 0개이며 전체 내용은 미완성 JSON입니다.</td></tr>
<tr><td>입력 반복</td><td>완료된 개별 필드 17개의 값이 실제 입력과 일치했습니다. 업무 설명과 시장 행렬 등 일부 입력을 재출력한 관찰이며, 입력 전체 복사나 완성된 기관 해석을 뜻하지 않습니다.</td></tr>
<tr><td>응답 형식</td><td>요구된 7개 응답 키는 현재 접두 부분에 없습니다. 문자열 검사는 보조 관찰일 뿐이며, 완료된 제출물이 없다는 판정은 종료 상태와 응답 기록 부재에 근거합니다.</td></tr>
<tr><td>종료 후 상태</td><td>모델 해제 응답과 빈 상주 모델 목록이 기록됐습니다. 재시도·대체 사례는 없고 시도한 사례는 그대로 남깁니다.</td></tr>
</tbody></table>
<h2>어떤 것을 평가할 수 없나</h2>
<p>기관의 산업별 등급·이유·인용 근거, 기준 비중 대비 배분, 위험 해석과 전략의 논리 연결을 평가할 완성 답변이 없습니다. 따라서 <strong>supported / contradicted / not_stated / uncertain</strong>에 배정할 완료 주장도 없고, 정확도·비중·위험·전략 점수는 모두 미산출입니다. 응답 부재를 출처와 모순되는 주장이나 0점짜리 전략으로 바꾸지 않았습니다.</p>
<p>첫 두 단계에서는 비중이 비어 있어도 허용됩니다. 이번에 관측된 문제는 초기 비중의 부재 자체가 아니라, 첫 단계 해석을 마치지 못했다는 점입니다. 입력에 포함된 기준 비중과 공분산을 모델의 투자 제안으로 간주하지 않습니다.</p>
<h2>소논문 논점과의 연결</h2>
<p>본 연구가 보려는 것은 기관 문서의 판단이 산업 배분 과정에 어떻게 보존되는가입니다. 이번 시도는 그 비교에 필요한 해석·배분 경로를 만들지 못했습니다. 기관별 전략의 차이, R1과 R4의 효과, 전략의 수렴이나 성과는 이 사례로 판단할 수 없습니다. 입력 반복은 후속 업무 수행 방식 검토의 단서지만, 원인이나 개선책의 효과가 입증된 것은 아닙니다.</p>
<p class="small">사전 근거표와 원문 PDF의 해시를 다시 대조했습니다. 사전 기준의 8개 의미 평가 차원은 유지했고, 완성 응답이 없으므로 적용 결과는 모두 평가 불가입니다. 기관의 관점과 모델의 독립적 배분 선택을 혼동하거나 정확 비중 정답·임의 위험 상한을 만들지 않았습니다. 감사 확인 {len(checks)}개 통과는 실험 성공이나 사람 검증 통과를 의미하지 않습니다.</p>
<h2>짧은 원본 관찰</h2><pre>{esc(content[:240])}</pre>
<p class="small">위 내용은 완성 답변이 아닌 스트림 접두 부분입니다. 원본을 닫힌 JSON으로 고치거나 보충하지 않았습니다.</p>
<p><a href="{OUT.name}">전체 감사 JSON·검사·해시</a> · <a href="../{RUN_REL}/summary.json">실행 종료 요약</a> · <a href="{raw_link}">보존된 부분 스트림</a> · <a href="evaluator_only/fidelity_q2_r1_prerun_reference_20261018.json">실행 전 평가자 전용 근거표</a></p>
<p class="small">기관 원문: <a href="https://www.fidelity.com/bin-public/600_Fidelity_Com_English/documents/learning-center/Quarterly-Sector-And-Investment-Research-Update-Second-Quarter-2026.pdf">Fidelity Q2 2026 보고서</a>, 산업 판단 p.3 및 해석 범위 p.2. 원문 전체와 평가자 정답은 모델에 추가로 제공하지 않았습니다. 이번 감사에서는 모델 호출·원본 수정·런타임 수정·소논문 수정이 모두 0회입니다.</p>
</main></body></html>'''
    HTML.write_text(html_text, encoding="utf-8")
    assert all(fingerprint(ROOT / name) == item for name, item in evidence.items())
    print(json.dumps({"json": str(OUT.relative_to(ROOT)), **fingerprint(OUT), "html": str(HTML.relative_to(ROOT)), "checks": len(checks), "semantic_evaluation": report["semantic_evaluation_status"]}))


if __name__ == "__main__":
    main()
