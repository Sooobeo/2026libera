"""Adversarial offline tests: denominator, lineage, visibility and semantic limits."""
import copy
import json
import unittest

from evaluate_sector_v48 import SECTOR_CODES, evaluate_case, evaluate_bundle, verify_claim


def fixture(source="source_A", arm="R1"):
    gold = {"source_id": source, "rating_vocabulary": ["Neutral"], "sector_ratings": {}, "evidence_index": {}}
    packet = {"source_id": source, "split": "pilot", "evidence_passages": []}
    response = {"source_id": source, "interpretations": [], "weights": [], "alternatives": "Alternative remains a choice.",
                "risk_discussion": "Historical variability is uncertain.", "unresolved": [], "submitted_constraints": []}
    for index, code in enumerate(SECTOR_CODES):
        eid = source + ":" + code
        gold["sector_ratings"][code] = {"rating": "Neutral", "evidence_ids": [eid], "reason_evidence_ids": []}
        gold["evidence_index"][eid] = {"source_id": source, "sector_codes": [code], "claims": ["rating"]}
        packet["evidence_passages"].append({"evidence_id": eid, "text": code + " is Neutral."})
        response["interpretations"].append({"sector_code": code, "rating": "Neutral", "reason": "Source has no separate reason.", "evidence_ids": [eid]})
        response["weights"].append({"sector_code": code, "weight": 1 if index == 0 else 0,
                                    "rationale": "A literal model rationale, not verified.", "evidence_ids": [eid]})
    market = {"baseline_id": "baseline", "baseline_weights": {code: 1 if i == 0 else 0 for i, code in enumerate(SECTOR_CODES)}}
    registry = {"version": "registry-v1", "rows": [{"fact_id": "M:vol:10", "sector_code": "10", "metric": "daily_volatility",
                                                    "value": 0.125, "unit": "daily_decimal_return", "period": ["2026-01-01", "2026-03-31"]}]}
    metadata = {"case_id": source + "__" + arm, "source_id": source, "arm": arm, "endpoint": "C0",
                "attempted": True, "transport_completed": True, "attempt_status": "completed_response",
                "visible_evidence_ids": list(gold["evidence_index"]) + ["M:vol:10"], "current_candidate_id": "stage4"}
    return response, packet, gold, market, registry, metadata


def assessed(source="source_A", arm="R1", mutation=None, metadata_mutation=None):
    response, packet, gold, market, registry, metadata = fixture(source, arm)
    if mutation:
        mutation(response)
    if metadata_mutation:
        metadata_mutation(metadata)
    return evaluate_case(json.dumps(response), packet, gold, market, registry, metadata)


def claim_fixture():
    registry = fixture()[4]
    claim = {"literal_claim_text": "Energy daily volatility is 0.125.", "response_field_and_span": "/risk_discussion:0-39",
             "normalized_claim_tuple": {"subject": "10", "predicate_or_metric": "daily_volatility", "value_or_relation": "0.125",
                                        "unit": "daily_decimal_return", "period_or_as_of": ["2026-01-01", "2026-03-31"],
                                        "source_or_fact_id": "M:vol:10", "data_version": "registry-v1"}}
    return claim, registry


class CaseEvaluationTests(unittest.TestCase):
    def test_correct_labels_do_not_certify_strategy(self):
        result = assessed()
        self.assertEqual(result["source_fact_preservation"]["exact_label_correct_count"], 11)
        self.assertTrue(result["execution"]["valid_raw_allocation"])
        review = result["review_preparation"]
        self.assertFalse(review["independent_human_review_completed"])
        self.assertFalse(review["automatic_semantic_certification"])
        self.assertIsNone(review["strategic_preservation_verdict"])
        self.assertEqual(review["semantic_assessed_sector_count"], 0)
        for row in review["sector_reviews"]:
            self.assertIsNone(row["source_to_action_assessment_status"])
            self.assertIsNone(row["literal_stance"])

    def test_invalid_vector_retains_rationale_and_labels(self):
        result = assessed(mutation=lambda r: r["weights"][0].update(weight=0.975))
        self.assertFalse(result["execution"]["valid_raw_allocation"])
        self.assertEqual(result["source_fact_preservation"]["exact_label_correct_count"], 11)
        self.assertEqual(len(result["review_preparation"]["sector_reviews"]), 11)
        self.assertIn("literal model rationale", result["review_preparation"]["sector_reviews"][0]["allocation_rationale_literal"])
        self.assertIsNone(result["valid_portfolio_risk"])

    def test_duplicate_label_no_credit_and_duplicate_text_retained(self):
        result = assessed(mutation=lambda r: r["interpretations"].append(copy.deepcopy(r["interpretations"][0])))
        self.assertEqual(result["source_fact_preservation"]["exact_label_correct_count"], 10)
        self.assertEqual(result["source_fact_preservation"]["expected_sector_count"], 11)
        self.assertEqual(len(result["review_preparation"]["sector_reviews"][0]["interpretation_occurrences"]), 2)

    def test_bad_contract_does_not_destroy_valid_raw_vector(self):
        result = assessed(mutation=lambda r: r.pop("alternatives"))
        self.assertFalse(result["execution"]["contract_valid"])
        self.assertTrue(result["execution"]["valid_raw_allocation"])
        self.assertEqual(result["execution"]["outcome_category"], "model_response_contract_failure")

    def test_timeout_complete_looking_json_not_valid_endpoint(self):
        result = assessed(metadata_mutation=lambda m: m.update(transport_completed=False, attempt_status="timed_out"))
        self.assertFalse(result["execution"]["valid_raw_allocation"])
        self.assertEqual(result["execution"]["outcome_category"], "execution_or_infrastructure_failure")
        self.assertTrue(result["execution"]["human_readable_text_present"])
        self.assertEqual(result["source_fact_preservation"]["exact_label_correct_count"], 0)
        self.assertEqual(result["source_fact_preservation"]["observed_exact_labels_in_readable_material"], 11)

    def test_unparsed_readable_text_stays_available(self):
        _, packet, gold, market, registry, metadata = fixture()
        result = evaluate_case("Energy should be underweight because ...", packet, gold, market, registry, metadata)
        self.assertEqual(result["source_fact_preservation"]["exact_label_correct_count"], 0)
        fragments = result["review_preparation"]["literal_fields_for_manual_claim_review"]
        self.assertEqual(fragments[0]["literal_text"], "Energy should be underweight because ...")
        self.assertFalse(result["execution"]["valid_raw_allocation"])

    def test_duplicate_json_keys_and_nonfinite_are_distinct(self):
        _, packet, gold, market, registry, metadata = fixture()
        for text, expected in (("{\"source_id\":1,\"source_id\":2}", "duplicate_keys"), ("{\"weight\":NaN}", "nonfinite_number"), ("{\"weight\":1e400}", "nonfinite_number")):
            result = evaluate_case(text, packet, gold, market, registry, metadata)
            self.assertEqual(result["execution"]["parse_status"], expected)

    def test_boolean_weight_is_not_numeric(self):
        result = assessed(mutation=lambda r: r["weights"][0].update(weight=True))
        self.assertFalse(result["execution"]["arithmetic_valid"])
        self.assertIsNone(result["review_preparation"]["sector_reviews"][0]["raw_active_weight_decimal"])

    def test_public_numeric_citation_does_not_break_document_citation(self):
        result = assessed(mutation=lambda r: r["interpretations"][0]["evidence_ids"].append("M:vol:10"))
        citations = result["review_preparation"]["sector_reviews"][0]["interpretation_citations"]
        self.assertTrue(citations["syntax_valid"])
        self.assertEqual([x["kind"] for x in citations["entries"]], ["document", "public_numeric"])
        self.assertTrue(all(x["visible"] for x in citations["entries"]))
        self.assertIsNone(citations["semantic_entailment"])

    def test_visibility_not_inferred_from_quoted_ids(self):
        result = assessed(metadata_mutation=lambda m: m.update(visible_evidence_ids=[]))
        citation = result["review_preparation"]["sector_reviews"][0]["interpretation_citations"]["entries"][0]
        self.assertFalse(citation["visible"])
        self.assertIsNone(citation["entails_claim"])

    def test_wrong_source_identity_zero_label_credit(self):
        result = assessed(mutation=lambda r: r.update(source_id="other_source"))
        self.assertEqual(result["source_fact_preservation"]["exact_label_correct_count"], 0)
        self.assertTrue(result["execution"]["valid_raw_allocation"])

    def test_no_mutation_of_evidence_or_response(self):
        values = fixture()
        original = copy.deepcopy(values)
        evaluate_case(json.dumps(values[0]), *values[1:])
        self.assertEqual(values, original)


class BundleEvaluationTests(unittest.TestCase):
    def test_workflow_attempted_without_C0_is_not_wholly_unattempted(self):
        _, packet, gold, market, registry, metadata = fixture()
        metadata.update(attempted=False, transport_completed=False, workflow_generation_attempted=True,
                        workflow_status="failed_stage2", workflow_termination_reason="timed_out")
        case = evaluate_case(None, packet, gold, market, registry, metadata)
        result = evaluate_bundle([case], ["source_A", "source_B"])
        self.assertEqual(result["attempted_case_count"], 1)
        self.assertEqual(result["C0_attempted_case_count"], 0)
        self.assertEqual(result["case_accounting"][0]["workflow_status"], "failed_stage2")
        self.assertEqual(result["expected_sector_count"], 44)

    def test_all_absent_fixed_denominator(self):
        result = evaluate_bundle([], ["source_A", "source_B"])
        self.assertEqual(result["planned_case_count"], 4)
        self.assertEqual(result["expected_sector_count"], 44)
        self.assertEqual(result["exact_label_accuracy"], 0)
        self.assertIsNone(result["between_source_distance_difference_R4_minus_R1"])
        self.assertTrue(all(row["half_L1_distance"] is None for row in result["between_source_pairs"]))

    def test_one_case_earns_eleven_of_fortyfour(self):
        result = evaluate_bundle([assessed()], ["source_A", "source_B"])
        self.assertEqual(result["exact_label_accuracy"], 0.25)
        self.assertEqual(result["by_arm"]["R1"]["expected_sector_count"], 22)
        self.assertEqual(result["valid_raw_allocation_count"], 1)

    def test_pair_requires_both_valid(self):
        cases = [assessed(source, arm) for source in ("source_A", "source_B") for arm in ("R1", "R4")]
        cases[-1] = assessed("source_B", "R4", mutation=lambda r: r["weights"][0].update(weight=0.975))
        result = evaluate_bundle(cases, ["source_A", "source_B"])
        self.assertEqual(result["eligible_between_source_pair_count"], 1)
        self.assertEqual(result["eligible_within_source_pair_count"], 1)
        self.assertEqual(result["between_source_pairs"][0]["half_L1_distance"], 0)
        self.assertIsNone(result["between_source_pairs"][1]["half_L1_distance"])
        self.assertIsNone(result["between_source_distance_difference_R4_minus_R1"])

    def test_all_four_valid_distances_are_descriptive(self):
        cases = [assessed(source, arm) for source in ("source_A", "source_B") for arm in ("R1", "R4")]
        def move(response):
            response["weights"][0]["weight"] = 0
            response["weights"][1]["weight"] = 1
        cases[-1] = assessed("source_B", "R4", mutation=move)
        result = evaluate_bundle(cases, ["source_A", "source_B"])
        self.assertEqual(result["between_source_distance_difference_R4_minus_R1"], 1)
        self.assertEqual(result["exact_label_accuracy"], 1)
        self.assertIsNone(result["strategic_preservation_verdict"])

    def test_duplicates_and_repairs_not_silently_pooled(self):
        one = assessed()
        with self.assertRaises(ValueError):
            evaluate_bundle([one, one], ["source_A", "source_B"])
        one["endpoint"] = "C1"
        with self.assertRaises(ValueError):
            evaluate_bundle([one], ["source_A", "source_B"])


class NumericClaimTests(unittest.TestCase):
    def check(self, claim, registry, **kwargs):
        return verify_claim(claim, registry, visible_fact_ids=["M:vol:10"], **kwargs)

    def test_complete_tuple_matches(self):
        claim, registry = claim_fixture()
        self.assertEqual(self.check(claim, registry)["assessment_status"], "supported")

    def test_actual_calculator_fact_provenance_and_nontemporal_algebra(self):
        from sector_v48_contract import evaluate_proposal
        response, _, _, market, _, metadata = fixture()
        result = evaluate_proposal(response, 4, market, metadata["visible_evidence_ids"], "C0")
        fact = next(row for row in result["facts"] if row["fact_id"] == "C:C0:sum")
        claim = {"literal_claim_text": "The prior C0 sum was 1.", "response_field_and_span": "/unresolved/0",
                 "candidate_id": "C0", "period_scope": "candidate_local_no_calendar_period",
                 "normalized_claim_tuple": {"subject": fact["subject"], "predicate_or_metric": fact["metric"],
                                            "value_or_relation": "1", "unit": fact["unit"], "period_or_as_of": None,
                                            "source_or_fact_id": fact["fact_id"], "data_version": fact["data_version"]}}
        checked = verify_claim(claim, {}, result["facts"], visible_fact_ids=[fact["fact_id"]], current_candidate_id="C1")
        self.assertEqual(checked["assessment_status"], "supported")
        claim["applies_to_current_candidate"] = True
        checked = verify_claim(claim, {}, result["facts"], visible_fact_ids=[fact["fact_id"]], current_candidate_id="C1")
        self.assertEqual(checked["assessment_status"], "contradicted")

    def test_nonsector_public_subject_uses_exact_input_pointer(self):
        claim, registry = claim_fixture()
        registry["rows"][0].update(sector_code=None, source_json_pointer="/baseline_volatility")
        claim["normalized_claim_tuple"]["subject"] = "/baseline_volatility"
        self.assertEqual(self.check(claim, registry)["assessment_status"], "supported")

    def test_same_value_wrong_entity_unit_metric_period_version(self):
        for field, wrong in (("subject", "15"), ("unit", "percent"), ("predicate_or_metric", "annual_volatility"),
                             ("period_or_as_of", ["2025-01-01", "2025-03-31"]), ("data_version", "other")):
            claim, registry = claim_fixture()
            claim["normalized_claim_tuple"][field] = wrong
            checked = self.check(claim, registry)
            self.assertEqual(checked["assessment_status"], "contradicted")
            self.assertIn(field, checked["tuple_mismatches"])
            self.assertEqual(checked["numeric_discrepancy_raw"], "0.000")

    def test_no_favorable_rounding_without_reference_policy(self):
        claim, registry = claim_fixture()
        claim["normalized_claim_tuple"]["value_or_relation"] = "0.13"
        claim["precision_policy"] = {"kind": "decimal_places", "places": 2, "rounding": "HALF_UP"}
        self.assertEqual(self.check(claim, registry)["assessment_status"], "contradicted")
        registry["rows"][0]["precision_policy"] = claim["precision_policy"]
        self.assertEqual(self.check(claim, registry)["assessment_status"], "supported")

    def test_future_and_invisible_facts_not_evidence(self):
        claim, registry = claim_fixture()
        claim["normalized_claim_tuple"]["source_or_fact_id"] = "C:C1:sum"
        self.assertEqual(self.check(claim, registry)["reason"], "unknown_fact_id")
        claim, registry = claim_fixture()
        checked = verify_claim(claim, registry, visible_fact_ids=[])
        self.assertEqual(checked["reason"], "fact_not_visible_before_response")

    def test_prior_candidate_not_current_verification(self):
        claim, registry = claim_fixture()
        fact = copy.deepcopy(registry["rows"][0])
        fact.update(fact_id="C:C0:sum", metric="weight_sum", subject="portfolio", candidate_id="C0", value=0.975, data_version="calc-v1")
        claim["normalized_claim_tuple"].update(subject="portfolio", predicate_or_metric="weight_sum", value_or_relation="0.975",
                                               source_or_fact_id="C:C0:sum", data_version="calc-v1")
        claim["applies_to_current_candidate"] = True
        checked = verify_claim(claim, {}, [fact], visible_fact_ids=["C:C0:sum"], current_candidate_id="C1")
        self.assertEqual(checked["reason"], "earlier_candidate_is_not_current_verification")

    def test_missing_literal_or_tuple_remains_unassessed(self):
        claim, registry = claim_fixture()
        claim.pop("literal_claim_text")
        self.assertEqual(self.check(claim, registry)["assessment_status"], "not_assessable")
        claim, registry = claim_fixture()
        claim["normalized_claim_tuple"].pop("unit")
        self.assertEqual(self.check(claim, registry)["assessment_status"], "not_assessable")

    def test_self_derived_claim_requires_captured_current_formula(self):
        claim = {"literal_claim_text": "My proposed sum is 0.975, pending verification.", "response_field_and_span": "/unresolved/0",
                 "provenance_type": "model_derived_pending", "candidate_id": "C0", "formula": "sum(raw_weights)",
                 "identified_as_model_derived_pending": True,
                 "normalized_claim_tuple": {"subject": "portfolio", "predicate_or_metric": "weight_sum", "value_or_relation": "0.975",
                                            "unit": "decimal_weight", "period_or_as_of": "current_proposal", "source_or_fact_id": None,
                                            "data_version": "captured-response-sha"}}
        fact = {"fact_id": "EVAL:C0:sum", "subject": "portfolio", "metric": "weight_sum", "value": "0.975", "unit": "decimal_weight",
                "period": "current_proposal", "data_version": "captured-response-sha", "candidate_id": "C0",
                "formula": "sum(raw_weights)", "evaluator_only": True}
        result = verify_claim(claim, {}, [fact], current_candidate_id="C0")
        self.assertEqual(result["assessment_status"], "supported")
        result = verify_claim(claim, {}, [fact], current_candidate_id="C1")
        self.assertEqual(result["assessment_status"], "not_assessable")


if __name__ == "__main__":
    unittest.main(verbosity=2)
