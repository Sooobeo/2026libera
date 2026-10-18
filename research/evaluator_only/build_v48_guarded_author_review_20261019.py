"""Bind bounded author-AI observations to the terminal guarded pilot, all 44 slots."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "data/local_sector_runtime/pilot_v48_guarded_20261019"
PREP = ROOT / "data/sector_protocol/v48_pilot_r2_20261018"
EVAL = ROOT / "research/evaluator_only/v48_pilot_guarded_20261019/evaluation_report.json"
C0_NOTES = Path(__file__).with_name("v48_guarded_fidelity_R1_C0_author_observations_20261019.json")
C1_NOTES = Path(__file__).with_name("v48_guarded_fidelity_R1_C1_author_observations_20261019.json")
OUT = Path(__file__).with_name("v48_guarded_pilot_author_review_20261019.json")
CODES = ["10", "15", "20", "25", "30", "35", "40", "45", "50", "55", "60"]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path, locator=None):
    result = {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path)}
    if locator is not None:
        result["locator"] = locator
    return result


def pointer(value, locator):
    for part in locator[1:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def validate_observation(item, complete):
    path = ROOT / item["response_artifact"]["path"]
    assert sha(path) == item["response_artifact"]["sha256"]
    record = read(path)
    assert record["response_complete"] is complete
    assert item["model_quote"] in pointer(record, item["response_locator"])
    assert path == RUN / item["case_id"] / item["endpoint"] / "record.json"
    for evidence in item["evidence_refs"]:
        evidence_path = ROOT / evidence["path"]
        assert sha(evidence_path) == evidence["sha256"]
        pointer(read(evidence_path), evidence["locator"])


def main():
    if OUT.exists():
        raise FileExistsError("Preserve prior author reviews")
    report, summary, c0_note, c1_note = map(read, (EVAL, RUN / "summary.json", C0_NOTES, C1_NOTES))
    assert sha(EVAL) == "431ee2a7bac73111eabdeaec0183a1005539a57ffb69dfdc2ff6682c50d94270"
    assert sha(RUN / "summary.json") == "951d865500e3263082343972085eccba5afe9f2358de15d377dfbe66c1003464"
    assert summary["status"] == "stopped_system_integrity_incident"
    assert summary["core_generation_calls"] == 8 and summary["auxiliary_generation_calls"] == 2
    assert report["primary_C0_bundle"]["expected_sector_count"] == 44
    provider_log = RUN / "fidelity_q2_2026__R4/C0/server_log_after_snapshot.bin"
    assert sha(provider_log) == "9c3d41f6832513b51f7ad025c2fcb1fa6ab843a53abba5507534c773ca91351b"
    provider_log_text = provider_log.read_bytes().decode("utf-8", errors="replace")
    assert "ggml_vulkan: device lost on Vulkan0" in provider_log_text and "ggml_vulkan: getFenceStatus" in provider_log_text
    checked_inputs = [EVAL, RUN / "summary.json", PREP / "manifest.json", C0_NOTES, C1_NOTES, provider_log, Path(__file__)]
    snapshots = {path: sha(path) for path in checked_inputs}
    primary_observations = deepcopy(c0_note["paper_observations"])
    completed_auxiliary = deepcopy(c1_note["auxiliary_observations"])
    for item in primary_observations + completed_auxiliary:
        validate_observation(item, True)

    rows = []
    completed_rows = {row["sector_code"]: row for row in c0_note["sector_details"]}
    for case in report["primary_C0_cases"]:
        case_id = case["case_id"]
        record_path = RUN / case_id / "C0/record.json"
        ex = case["execution"]
        if case_id == "fidelity_q2_2026__R1":
            assert ex["transport_completed"] and ex["raw_sum"] == 1.035 and not ex["valid_raw_allocation"]
            for code in CODES:
                row = deepcopy(completed_rows[code])
                row.update({"C0_material_status": "completed_C0_invalid_full_vector", "response_artifact": ref(record_path),
                            "independent_human_review_completed": False, "strategic_preservation_verdict": None})
                rows.append(row)
        else:
            assert ex["human_readable_text_present"] is False
            status = "C0_request_failed_no_response" if ex["attempted"] else "workflow_not_started_after_system_incident"
            for code in CODES:
                rows.append({"case_id": case_id, "endpoint": "C0", "sector_code": code,
                             "C0_material_status": status, "response_artifact": ref(record_path) if record_path.is_file() else None,
                             "author_review_status": "not_assessed_no_C0_text", "interpretation_quote": None,
                             "rationale_quote": None, "raw_weight": None, "author_note": None,
                             "reason_unassessed": "No C0 response was captured; earlier stage or another case is not substituted.",
                             "independent_human_review_completed": False, "independent_human_judgment": None,
                             "automatic_semantic_score": None, "strategic_preservation_verdict": None})
    assert len(rows) == len({(r["case_id"], r["sector_code"]) for r in rows}) == 44

    partial_path = RUN / "fidelity_q2_2026__R1/C2/record.json"
    partial = read(partial_path)
    assert partial["response_complete"] is False and partial["transport_status"] == "hard_deadline"
    assert partial["parsed_response"] is None
    raw = partial["raw_response_text"]
    literal = "This weight is restored from the previous revision (0.380) to maintain the intended aggressive stance on Information Technology, as the previous reduction was an arithmetic correction that inadvertently altered the strategic intent relative to the Fidelity rating."
    coordinate = '"sector_code": "45",\n      "weight": 0.420'
    assert literal in raw and coordinate in raw
    partial_observation = {
        "id": "guarded_C2_partial_IT_restoration_explanation", "case_id": "fidelity_q2_2026__R1", "endpoint": "C2",
        "claim_or_action": "미완료 텍스트에서 IT0.420 표기와 이전 산술 수정이 의도를 바꿨다는 모델의 설명이 읽힌다.",
        "model_quote": literal, "response_locator": "/raw_response_text", "response_artifact": ref(partial_path),
        "literal_coordinate_excerpt": coordinate,
        "quote_character_span": [raw.index(literal), raw.index(literal) + len(literal)],
        "evidence_summary": "완료 C1의 IT값은0.380이다. C2 부분텍스트에는 IT0.420이 보이고 aggressive stance를 유지하려고 이전 수정을 되돌린다고 적는다. 텍스트는 다음 산업 행 중간에서 끝나며 완전한 JSON·11개 최종 벡터·합계는 확보되지 않았다.",
        "evidence_refs": [ref(RUN / "fidelity_q2_2026__R1/C1/record.json", "/parsed_response/weights/7"),
                          ref(partial_path, "/raw_response_text"), ref(partial_path, "/response_complete"),
                          ref(partial_path, "/parsed_response"), ref(partial_path, "/transport_status"),
                          ref(PREP / "packets/fidelity_q2_2026.json", "/evidence_passages/8")],
        "author_assessment": "산술 조정과 선택 이유의 관계에 대한 모델의 설명이 남아 있다는 부분 관측이다. 모델이 주장하는 strategic intent는 기관의 비공개 의도를 확인한 사실이나 작성자의 인과 설명으로 승격하지 않는다.",
        "limits": "부분 텍스트의 한 좌표를 완성된 배분으로 세지 않는다. 나머지 값을 채워 합계·위험·전략 복구 성공을 계산하지 않으며, C0나 완료 C1을 대체하지 않는다.",
        "independent_human_judgment": None, "automatic_semantic_score": None,
        "transport_completed": False, "completed_response_credit": False,
    }
    validate_observation(partial_observation, False)
    r4_path = RUN / "fidelity_q2_2026__R4/C0/record.json"
    r4 = read(r4_path)
    assert r4["raw_response_text"] is None and r4["response_complete"] is False
    assert r4["transport_result"]["system_integrity_incident"] is True

    result = {
        "artifact_kind": "terminal_guarded_pilot_author_source_reason_action_review",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reviewer_role": "author_AI_implementation_participant_not_independent_human", "reviewer_id": "v48_offline_evaluator",
        "authorship_disclosure": "This author-AI implemented the offline evaluator/renderer and prepared this review. Separate runtime and arithmetic audits do not turn this into independent human source or semantic judgment.",
        "independent_human_review_completed": False,
        "provenance": {"manifest": ref(PREP / "manifest.json"), "evaluation": ref(EVAL), "run_summary": ref(RUN / "summary.json"),
                       "source_C0_interim_review": ref(C0_NOTES), "source_C1_interim_review": ref(C1_NOTES),
                       "C2_record": ref(partial_path), "R4_no_response_record": ref(r4_path),
                       "R4_provider_log": ref(provider_log), "review_generator": ref(Path(__file__))},
        "review_scope": "All44 planned C0 slots are retained. Eleven rows from the only completed C0 were literally reviewed against supplied researcher paraphrases and the public numeric registry;33 have no C0 text and are unassessed. Completed C1 and incomplete C2 observations are auxiliary and separate. No original-PDF independent human review is claimed.",
        "review_summary": {"planned_C0_cases": 4, "planned_C0_sector_slots": 44, "workflow_generation_attempted_cases": 2,
                           "C0_attempted_cases": 2, "completed_C0_cases": 1, "valid_completed_C0_cases": 0,
                           "completed_C0_rows_read_by_author_AI": 11, "C0_rows_unassessed_no_text": 33,
                           "independent_human_assessed_sector_slots": 0, "core_generation_calls": 8, "auxiliary_generation_calls": 2},
        "all_44_C0_sector_reviews": rows,
        "paper_observations": primary_observations,
        "completed_auxiliary_observations": completed_auxiliary,
        "partial_auxiliary_observations": [partial_observation],
        "source_note_manual_numeric_comparisons": deepcopy(c0_note["manual_numerical_claim_comparisons"]),
        "C0_trace_details": deepcopy(c0_note["trace_details"]),
        "C1_descriptive_arithmetic": deepcopy(c1_note["descriptive_arithmetic"]),
        "C2_capture": {"record": ref(partial_path), "response_complete": False, "parseable_full_response": False,
                       "raw_character_count": len(raw), "raw_terminal_excerpt": raw[-200:],
                       "complete_vector_inferred": False, "raw_sum": None, "valid_portfolio_risk": None,
                       "elapsed_seconds_as_recorded": partial["transport_result"]["supervisor"]["elapsed_seconds"]},
        "environmental_scope": {"run_status": summary["status"], "R4_C0_record": ref(r4_path),
                                "R4_recorded_transport_error": r4["transport_result"]["supervisor"]["worker"]["error"],
                                "R4_provider_log": ref(provider_log),
                                "provider_log_literal": "ggml_vulkan: device lost on Vulkan0",
                                "provider_log_locator": "lines20813-20814; device lost and getFenceStatus",
                                "limits": "The endpoint record captures a connection/stream failure, while the separately preserved server snapshot contains Vulkan device-loss diagnostics. These establish a runtime incident, not its ultimate hardware, driver or sleep-related cause. The full operating investigation is separate; no infrastructure failure is recoded as a model strategy verdict."},
        "topic_connection": ["Readable reasons and actual coordinates can be contrasted even when a complete portfolio violates its budget, without calling that portfolio valid.",
                             "The completed C0 contains both supported source-reason-direction links and unsupported additional reasons/numeric claims. Representative examples do not form an overall strategy score.",
                             "C1 changes one weight but its completion claim disagrees with the actual sum. C2 supplies only a partial explanation. Stated correction and actual correction are distinct objects for organizational review.",
                             "No valid completed C0 pair exists. R1/R4 effects, cross-source convergence, harmful homogenization and population effects remain unmeasured.",
                             "Public dated outlooks and researcher summaries do not identify private institutional mandates, customer risk preferences or unique optimal allocations. Mixed document/market vintages are not a contemporaneous backtest.",
                             "Source review, actual-weight reconciliation and explicit responsibilities are operational proposals, not measured benefits; review time, organizational productivity, investor losses and net benefit were not measured."],
        "pilot_readiness": "FAIL_SYSTEM_INTEGRITY_INCIDENT_AND_INCOMPLETE_MEASUREMENT",
        "main_experiment_readiness": False, "main_candidate_created_by_this_review": False,
        "strategic_preservation_verdict": None, "automatic_semantic_score": None,
        "model_calls_by_this_review": 0, "main_model_calls_by_this_review": 0, "online_artifacts_changed": False,
    }
    assert all(sha(path) == expected for path, expected in snapshots.items())
    with OUT.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"path": OUT.relative_to(ROOT).as_posix(), "sha256": sha(OUT),
                      "planned_rows": 44, "author_read_rows": 11, "unassessed_rows": 33,
                      "primary_observations": 8, "completed_auxiliary_observations": 3, "partial_auxiliary_observations": 1}))


if __name__ == "__main__":
    main()
