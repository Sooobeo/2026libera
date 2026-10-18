"""Author-AI offline accounting/topic review of the original, interrupted pilot.

This is an evidence-specific review receipt, not a scorer or readiness gate.
It does not call a model, alter inputs, or fill independent human judgments.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / "data/local_sector_runtime/pilot_v48_20261018"
OUT = Path(__file__).parent / "round3.json"
EVALUATION = ROOT / "research/evaluator_only/v48_pilot_20261018/evaluation_report.json"

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def ref(path):
    return {"path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

def main():
    if OUT.exists():
        raise FileExistsError("Preserve the previous receipt; use a new version.")
    report = read(EVALUATION)
    summary = read(RUN / "summary.json")
    bundle = report["primary_C0_bundle"]
    env_path = ROOT / "research/evidence/v48_pilot_timing_investigation_20261018/postpilot_environmental_deviation.json"
    env = read(env_path)
    round1 = ROOT / "research/evidence/v48_actual_pilot_20261018/round1_with_environment.json"
    round2 = ROOT / "research/evidence/v48_actual_pilot_20261018/round2_actual.json"
    worksheet_path = EVALUATION.with_name("semantic_review_worksheet.json")
    codes = ["10", "15", "20", "25", "30", "35", "40", "45", "50", "55", "60"]
    planned = [x["case_id"] for x in summary["planned_cases"]]
    checks = []
    def check(key, condition, detail=None):
        checks.append({"id": key, "passed": bool(condition), "evidence": detail})
    check("planned_four_case_identity_order_retained", planned == [c["case_id"] for c in report["primary_C0_cases"]] and len(planned) == 4)
    check("fixed_44_sector_denominator", bundle["expected_sector_count"] == 44)
    check("workflow_vs_C0_attempts_distinct", bundle["attempted_case_count"] == 3 and bundle["C0_attempted_case_count"] == 2)
    check("one_completed_no_valid_C0", bundle["completed_response_count"] == 1 and bundle["valid_raw_allocation_count"] == 0)
    check("recorded_generation_count_10_core_1_aux", summary["core_generation_calls"] == 10 and summary["auxiliary_generation_calls"] == 1)
    generation_requests = sorted(RUN.glob("*/**/http_0001_generation/request.json"))
    check("durable_request_count_matches_summary", len(generation_requests) == 11)
    check("no_main_calls_or_freeze", summary["main_model_calls"] == 0 and summary["main_frozen"] is False)
    check("no_automatic_retries", summary["automatic_retries"] == 0)
    check("environmental_failure_retained", summary["status"] == "stopped_system_integrity_incident" and read(round1)["status"] == "FAIL" and env["environmental_deviation"]["present"] is True)
    check("missing_or_invalid_pairs_never_zero", all(p["eligible"] is False and p["half_L1_distance"] is None for k in ("within_source_pairs", "between_source_pairs") for p in bundle[k]) and bundle["between_source_distance_difference_R4_minus_R1"] is None)
    check("human_semantics_not_certified", report["independent_human_review_completed"] is False and bundle["semantic_assessed_sector_count"] == 0 and bundle["strategic_preservation_verdict"] is None)
    check("no_evaluation_model_calls", report["model_calls_by_this_evaluation"] == 0)
    check("numeric_round2_same_evaluation", read(round2)["provenance"]["evaluation"]["sha256"] == ref(EVALUATION)["sha256"])
    rows = []
    for case in report["primary_C0_cases"]:
        ex = case["execution"]
        sectors = case["review_preparation"]["sector_reviews"]
        check(case["case_id"] + ":eleven_explicit_slots", [r["sector_code"] for r in sectors] == codes)
        record_path = RUN / case["case_id"] / "C0/record.json"
        availability = "completed_response_invalid_allocation" if ex["transport_completed"] else "partial_C0_response_not_complete" if ex["attempted"] else "C0_not_reached"
        for row in sectors:
            check(case["case_id"] + ":" + row["sector_code"] + ":human_judgments_pending", all(row.get(k) is None for k in ("literal_stance", "claim_support", "action_consistency", "source_to_action_assessment_status", "reviewer_id")) and row["independent_human_review_completed"] is False)
            rows.append({"case_id": case["case_id"], "endpoint": "C0", "sector_code": row["sector_code"],
                         "C0_material_status": availability,
                         "response_artifact": ref(record_path) if record_path.exists() else None,
                         "completed_interpretation_available": bool(ex["transport_completed"] and row["interpretation_occurrences"]),
                         "completed_weight_rationale_available": bool(ex["transport_completed"] and row["weight_occurrences"]),
                         "full_raw_allocation_valid": ex["valid_raw_allocation"],
                         "author_semantic_assessment_in_this_accounting_receipt": "not_assessed",
                         "independent_human_judgment": None,
                         "strategic_preservation_verdict": None})
    first = report["primary_C0_cases"][0]
    check("invalid_complete_response_explanation_retained", first["execution"]["raw_sum"] == 1.035 and all(r["allocation_rationale_literal"] for r in first["review_preparation"]["sector_reviews"]))
    check("source_identity_label_diagnostic_not_meaning_score", first["source_fact_preservation"]["source_identity_matches"] is False and first["source_fact_preservation"]["exact_label_correct_count"] == 0 and all(r["source_literal_rating"] == r["model_literal_rating"] for r in first["review_preparation"]["sector_reviews"]), "The completed case has 11 matching rating strings but null source_id; the registered joint ID+label diagnostic is 0/11. Neither number establishes strategic preservation.")
    aux = report["auxiliary_endpoint_cases"]
    check("partial_C1_separate_no_C0_replacement", len(aux) == 1 and aux[0]["endpoint"] == "C1" and aux[0]["execution"]["transport_completed"] is False and aux[0]["execution"]["raw_sum"] is None)
    check("no_C2_observed", not any(RUN.glob("*/C2/record.json")))
    document = {
        "review_version": "v48_actual_original_pilot_round3_accounting_topic_1",
        "round": 3, "status": "PASS" if all(c["passed"] for c in checks) else "FAIL",
        "status_meaning": "Only the accounting and bounded-topic review contract below. This is NOT pilot readiness, model success, independent human review or authorization to execute main.",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reviewer_role": "author_AI_implementation_participant_not_independent_human",
        "authorship_conflict": "This reviewer implemented the evaluator and prepared its report; separate runtime and arithmetic audits are linked. Three AI checks do not replace an independent human source/semantic review.",
        "independent_human_review_completed": False,
        "provenance": {"manifest": ref(ROOT / "data/sector_protocol/v48_pilot_r2_20261018/manifest.json"), "evaluation": ref(EVALUATION), "run_summary": ref(RUN / "summary.json"), "round1": ref(round1), "round2": ref(round2), "environment": ref(env_path), "semantic_review_worksheet": ref(worksheet_path), "review_receipt_generator": ref(Path(__file__).resolve())},
        "check_count": len(checks), "pass_count": sum(c["passed"] for c in checks), "checks": checks,
        "observed_accounting": {"planned_cases": 4, "planned_sector_slots": 44, "workflow_generation_attempted_cases": 3, "core_generation_calls": 10, "auxiliary_generation_calls": 1, "C0_attempted_cases": 2, "completed_C0_cases": 1, "valid_completed_C0_cases": 0, "partial_C0_cases": 1, "C0_not_reached_cases": 2, "completed_C1_cases": 0, "partial_C1_cases": 1, "C2_cases": 0, "independent_human_assessed_sector_slots": 0},
        "all_44_C0_sector_availability": rows,
        "pilot_readiness": "FAIL_ENVIRONMENTAL_DEVIATION_AND_INCOMPLETE_MEASUREMENT",
        "main_experiment_readiness": False,
        "topic_connection_review": [
            "The paper asks whether AI-generated investment reasoning preserves distinguishable public source judgments through interpretation and allocation. The saved source passage, literal interpretation, allocation rationale and raw choice permit a bounded trace review of one completed C0 even when its weights violate the budget.",
            "The complete Fidelity R1 C0 has an arithmetic failure (raw sum 1.035) and readable reasons. That failure does not erase the reasons, but neither readable reasons nor copied rating strings establish investment quality or strategy preservation.",
            "R1/R4 and between-source distances are unobserved because no jointly valid completed C0 pair exists. Missingness is not zero distance, convergence, strategic homogenization, or a causal effect of evidence timing.",
            "The actual objects are two dated public sector outlook documents, not reconstructed private institutional objectives, risk-tolerance coefficients, constraints, realized holdings or firm-wide strategies. Researcher-paraphrased passages still require original-source human review.",
            "The market packet and document snapshots have different dates; this is a retrospective common-input task, not a contemporaneous historical trading replay or test of subsequent profit.",
            "For the business/economics conference theme, source checking and reconciliation of stated revisions with actual allocation are proposed operational responses. This pilot has not measured organizational productivity, labor effects, investor losses, response costs or net benefit."
        ],
        "environmental_interpretation": {"source": ref(env_path), "deviation_present": True, "not_model_inability_by_itself": True, "not_uninterrupted_equal_900_second_exposure": True, "no_exact_active_compute_time_inferred": True, "no_deadline_clipping_or_posthoc_threshold": True, "original_failure_retained_if_separate_repeat_occurs": True},
        "semantic_followup_scope": "A separate author-AI literal source-to-reason-to-action review may cover the completed eleven rows and partial traces. All forty-four availability slots above remain; no later selective examples replace the denominator or independent human review.",
        "strategic_preservation_verdict": None,
        "model_calls_by_this_review": 0, "main_model_calls_by_this_review": 0,
        "frozen_online_files_modified": False, "human_judgments_filled": False,
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": ref(OUT), "status": document["status"], "checks": len(checks), "pass_count": document["pass_count"], "pilot_readiness": document["pilot_readiness"]}, ensure_ascii=False))

if __name__ == "__main__":
    main()
