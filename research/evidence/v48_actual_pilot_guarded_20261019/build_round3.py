"""Terminal guarded-pilot accounting/topic review; PASS is not readiness."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / "data/local_sector_runtime/pilot_v48_guarded_20261019"
PREP = ROOT / "data/sector_protocol/v48_pilot_r2_20261018"
EVAL = ROOT / "research/evaluator_only/v48_pilot_guarded_20261019/evaluation_report.json"
AUTHOR = ROOT / "research/evaluator_only/v48_guarded_pilot_author_review_20261019.json"
ENV = ROOT / "research/evidence/v48_guarded_operating_investigation_20261019/final_xpath/environmental_deviation_v2.json"
OUT = Path(__file__).with_name("round3.json")
CODES = ["10", "15", "20", "25", "30", "35", "40", "45", "50", "55", "60"]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve(value):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def ref(path):
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path)}


def matches(value, path):
    return resolve(value["path"]) == path.resolve() and value["sha256"] == sha(path)


def pointer(value, locator):
    for part in locator[1:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def main():
    if OUT.exists():
        raise FileExistsError("Preserve the review; use another version")
    report, summary, author, env = map(read, (EVAL, RUN / "summary.json", AUTHOR, ENV))
    round1_path, round2_path = OUT.with_name("round1.json"), OUT.with_name("round2.json")
    round1, round2 = read(round1_path), read(round2_path)
    worksheet_path = EVAL.with_name("semantic_review_worksheet.json")
    worksheet = read(worksheet_path)
    html_path = EVAL.with_name("review_with_label_scope.html")
    html = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    bundle = report["primary_C0_bundle"]
    checks = []

    def check(identifier, passed, evidence=None):
        checks.append({"id": identifier, "passed": bool(passed), "evidence": evidence})

    planned = [x["case_id"] for x in summary["planned_cases"]]
    check("fixed_four_case_identity_order", len(planned) == 4 and planned == [x["case_id"] for x in report["primary_C0_cases"]])
    check("planned_44_sector_slots", bundle["planned_case_count"] == 4 and bundle["expected_sector_count"] == 44)
    check("two_workflows_two_C0_requests", bundle["attempted_case_count"] == bundle["C0_attempted_case_count"] == 2)
    check("one_completed_no_valid_C0", bundle["completed_response_count"] == 1 and bundle["valid_raw_allocation_count"] == 0)
    check("eight_core_two_auxiliary_requests", summary["core_generation_calls"] == 8 and summary["auxiliary_generation_calls"] == 2)
    requests = list(RUN.glob("*/**/http_0001_generation/request.json"))
    check("durable_request_count_ten", len(requests) == 10, "Durable request envelopes include an attempt that failed before a model answer.")
    check("no_retry_or_main_call", summary["automatic_retries"] == 0 and summary["main_model_calls"] == 0)
    check("no_main_freeze_or_human_review", summary["main_frozen"] is False and summary["human_review_completed"] is False)
    check("runtime_failure_preserved", summary["status"] == "stopped_system_integrity_incident" and report["system_integrity_incidents_present"] is True and round1["status"] == "FAIL")
    check("recorded_round1_failure_not_overridden", round1["check_count"] == 724 and round1["pass_count"] == 722 and round1["environmental_companion_does_not_override_contract_fail"] is True)
    check("round2_arithmetic_scope_pass_same_report", round2["status"] == "PASS" and matches(round2["provenance"]["evaluation"], EVAL))
    check("all_reviews_same_manifest", matches(round1["manifest"], PREP / "manifest.json") and matches(round2["provenance"]["manifest"], PREP / "manifest.json"))
    check("author_same_terminal_provenance", all(matches(author["provenance"][key], path) for key, path in
          (("manifest", PREP / "manifest.json"), ("evaluation", EVAL), ("run_summary", RUN / "summary.json"))))
    inventory = round1["artifact_inventory"]
    check("round1_inventory_exact_current_run", {resolve(item["path"]) for item in inventory} == {p.resolve() for p in RUN.rglob("*") if p.is_file()})
    check("round1_inventory_current_bytes", all(matches(item, resolve(item["path"])) for item in inventory))
    check("all_comparison_pairs_unavailable_not_zero", all(row["eligible"] is False and row["half_L1_distance"] is None
          for kind in ("within_source_pairs", "between_source_pairs") for row in bundle[kind])
          and bundle["between_source_distance_difference_R4_minus_R1"] is None)
    check("no_automatic_semantic_verdict", bundle["semantic_assessed_sector_count"] == 0
          and report["strategic_preservation_verdict"] is None and report["independent_human_review_completed"] is False)
    check("evaluator_did_not_generate", report["model_calls_by_this_evaluation"] == report["main_model_calls_by_this_evaluation"] == 0)
    check("input_diagnostic_count_not_runtime_success", report["artifact_issues"] == [] and report["system_integrity_incidents_present"] is True,
          "An empty loader input-issue list does not cancel the recorded system incident.")

    all_rows = []
    for case in report["primary_C0_cases"]:
        case_id, ex = case["case_id"], case["execution"]
        rows = case["review_preparation"]["sector_reviews"]
        check(case_id + ":eleven_rows", [r["sector_code"] for r in rows] == CODES)
        for row in rows:
            check(case_id + ":" + row["sector_code"] + ":human_pending",
                  all(row.get(key) is None for key in ("literal_stance", "claim_support", "action_consistency", "source_to_action_assessment_status", "reviewer_id"))
                  and row["independent_human_review_completed"] is False)
            matching = next(r for r in author["all_44_C0_sector_reviews"] if r["case_id"] == case_id and r["sector_code"] == row["sector_code"])
            all_rows.append({"case_id": case_id, "endpoint": "C0", "sector_code": row["sector_code"],
                             "C0_material_status": matching["C0_material_status"], "author_review_status": matching["author_review_status"],
                             "completed_response_available": ex["transport_completed"], "valid_full_raw_allocation": ex["valid_raw_allocation"],
                             "independent_human_judgment": None, "strategic_preservation_verdict": None})
    check("author_all44_no_selective_denominator", len(author["all_44_C0_sector_reviews"]) == 44 and len({(r["case_id"], r["sector_code"]) for r in author["all_44_C0_sector_reviews"]}) == 44)
    check("author11_read33_unassessed", sum(r["author_review_status"] == "completed_literal_read_against_supplied_packet_and_registry" for r in all_rows) == 11
          and sum(r["author_review_status"] == "not_assessed_no_C0_text" for r in all_rows) == 33)
    first, failed = report["primary_C0_cases"][:2]
    check("complete_invalid_explanations_preserved", first["execution"]["raw_sum"] == 1.035 and all(r["allocation_rationale_literal"] for r in first["review_preparation"]["sector_reviews"]))
    check("joint_ID_label_diagnostic_not_all_wrong_strings", first["source_fact_preservation"]["exact_label_correct_count"] == 0 and first["source_fact_preservation"]["source_identity_matches"] is False
          and all(r["source_literal_rating"] == r["model_literal_rating"] for r in first["review_preparation"]["sector_reviews"]),
          "11 literal rating strings match in the completed C0, but source_id is null. Registered joint ID+label diagnostic0/11 is not a claim that all label strings are wrong, and neither statistic is strategy preservation.")
    check("R4_no_answer_is_infrastructure_category", failed["execution"]["attempt_status"] == "attempted_no_response" and failed["execution"]["outcome_category"] == "execution_or_infrastructure_failure" and not failed["execution"]["human_readable_text_present"])
    check("UBS_never_started_not_model_failures", summary["cases_not_started"] == ["ubs_june_2026__R1", "ubs_june_2026__R4"] and all(not c["execution"]["attempted"] and c["execution"]["outcome_category"] == "not_attempted" for c in report["primary_C0_cases"][2:]))
    aux = report["auxiliary_endpoint_cases"]
    check("auxiliary_exact_C1_C2_separate", [(x["case_id"], x["endpoint"]) for x in aux] == [(planned[0], "C1"), (planned[0], "C2")])
    check("C1_complete_invalid_0995", aux[0]["execution"]["transport_completed"] and aux[0]["execution"]["raw_sum"] == 0.995 and not aux[0]["execution"]["valid_raw_allocation"])
    check("C2_partial_never_complete_vector_credit", not aux[1]["execution"]["transport_completed"] and aux[1]["execution"]["human_readable_text_present"]
          and aux[1]["execution"]["raw_sum"] is None and not aux[1]["execution"]["valid_raw_allocation"])
    check("aux_terminal_is_C2_not_best_candidate", summary["cases"][0]["auxiliary_terminal_record"]["path"].endswith("/C2/record.json") and summary["cases"][0]["primary_never_replaced"] is True)
    for group, completed in (("paper_observations", True), ("completed_auxiliary_observations", True), ("partial_auxiliary_observations", False)):
        for item in author[group]:
            path = resolve(item["response_artifact"]["path"]); record = read(path)
            check(group + ":" + item["id"] + ":literal_current_run", path == RUN / item["case_id"] / item["endpoint"] / "record.json"
                  and matches(item["response_artifact"], path) and record["response_complete"] is completed
                  and item["model_quote"] in pointer(record, item["response_locator"]))
            check(group + ":" + item["id"] + ":not_human_score", item["independent_human_judgment"] is None and item["automatic_semantic_score"] is None)
    check("primary_examples_only_completed_C0", len(author["paper_observations"]) == 8 and all(x["endpoint"] == "C0" for x in author["paper_observations"]))
    check("author_no_ready_or_semantic_pass", author["main_experiment_readiness"] is False and author["main_candidate_created_by_this_review"] is False and author["strategic_preservation_verdict"] is None and author["independent_human_review_completed"] is False)
    check("worksheet_provenance_and_null_state", worksheet["provenance"] == report["provenance"] and worksheet["independent_human_review_completed"] is False)
    check("HTML_primary44_aux22", len(html.select("#primary article.sector")) == 44 and len(html.select("#auxiliary article.sector")) == 22)
    check("HTML_labels_explicit_ID_scope", "출처 ID 포함 등급 일치 보조 진단:" in html.get_text() and "모든 등급 문구가 틀렸다는 뜻" in html.get_text())
    check("environment_same_run_summary", matches(env["run_summary"], RUN / "summary.json") and matches(round1["environmental_deviation"], ENV))
    check("guard_lifecycle_not_health_proof", env["guard"]["active_before_first_case"] is True and env["guard"]["released_after_summary_same_thread"] is True)
    check("screen_off_events_not_called_sleep", len(env["screen_off_windows"]) == 5 and all(w["exit_xml_data"]["SleepEntered"] == "false" and w["exit_xml_data"]["SleepDurationInUs"] == "0" for w in env["screen_off_windows"]))
    server_path = resolve(env["server_log"]["path"])
    check("device_loss_literal_preserved", matches(env["server_log"], server_path) and b"ggml_vulkan: device lost on Vulkan0" in server_path.read_bytes())
    check("frozen_pilot_software_unchanged", all(sha(ROOT / "research" / name) == expected for name, expected in read(PREP / "manifest.json")["software_hashes"].items()))
    document = {
        "review_version": "v48_guarded_actual_pilot_round3_accounting_topic_1", "round": 3,
        "status": "PASS" if all(c["passed"] for c in checks) else "FAIL",
        "status_meaning": "PASS only means this record/accounting/literal/topic review meets its contract. The runtime integrity audit failed. It is not pilot readiness, model success, independent human review or main execution authorization.",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reviewer_role": "author_AI_implementation_participant_not_independent_human",
        "authorship_conflict": "This reviewer authored the offline evaluator and renderer and the terminal author review. Runtime auditor also authored transport; arithmetic audit is separately implemented. These are AI implementation/cross-reviews, not independent human source/semantic judgments.",
        "independent_human_review_completed": False,
        "provenance": {"manifest": ref(PREP / "manifest.json"), "evaluation": ref(EVAL), "run_summary": ref(RUN / "summary.json"),
                       "round1": ref(round1_path), "round2": ref(round2_path), "environment": ref(ENV),
                       "author_review": ref(AUTHOR), "semantic_review_worksheet": ref(worksheet_path), "review_html": ref(html_path),
                       "label_scope_clarification": ref(OUT.with_name("review_label_scope_clarification.json")),
                       "independent_agent_narrative_crosscheck": ref(OUT.with_name("round2_narrative_crosscheck.json")),
                       "review_receipt_generator": ref(Path(__file__))},
        "check_count": len(checks), "pass_count": sum(c["passed"] for c in checks), "checks": checks,
        "observed_accounting": {"planned_cases": 4, "planned_sector_slots": 44, "workflow_generation_attempted_cases": 2,
                                "core_generation_calls": 8, "auxiliary_generation_calls": 2, "C0_attempted_cases": 2,
                                "completed_C0_cases": 1, "valid_completed_C0_cases": 0, "partial_C0_cases": 0,
                                "C0_requested_no_response_cases": 1, "whole_cases_not_started": 2,
                                "completed_C1_cases": 1, "valid_completed_C1_cases": 0, "partial_C2_cases": 1,
                                "author_AI_read_C0_rows": 11, "C0_rows_no_text_unassessed": 33, "independent_human_assessed_sector_slots": 0},
        "all_44_C0_sector_availability": all_rows,
        "pilot_readiness": "FAIL_SYSTEM_INTEGRITY_INCIDENT_AND_INCOMPLETE_MEASUREMENT",
        "main_experiment_readiness": False, "main_candidate_creation_allowed_by_this_review": False,
        "topic_connection_review": author["topic_connection"],
        "environmental_interpretation": {"source": ref(ENV), "readiness_failed": True,
                                         "screen_off_not_equated_to_sleep": True,
                                         "recorded_incident": "Vulkan0 device loss and llama-server APPCRASH; later LiveKernelEvent141 records are reporting-time evidence, not precise fault-onset timestamps.",
                                         "root_cause_confirmed": False, "model_inability_inferred": False,
                                         "uninterrupted_GPU_health_inferred_from_awake_request": False,
                                         "exact_active_compute_time_inferred": False, "configured_deadline_substituted_for_actual_elapsed": False},
        "operational_recommendation_scope": "Keep this failed repeat distinct from the original failed run. Resolve the captured environment incident and validate any changed operating setup before a newly registered measurement. Do not manufacture a candidate or declare main readiness from arithmetic/narrative review PASS.",
        "strategic_preservation_verdict": None, "model_calls_by_this_review": 0, "main_model_calls_by_this_review": 0,
        "frozen_online_files_modified": False, "human_judgments_filled": False,
    }
    with OUT.open("x", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"output": ref(OUT), "status": document["status"], "checks": len(checks),
                      "pass_count": document["pass_count"], "pilot_readiness": document["pilot_readiness"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
