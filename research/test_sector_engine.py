"""Meaningful synthetic tests of denominator, visibility and semantic boundaries.

Fixtures are not institutional observations or experiment results.
Run: python -m unittest discover -s research -p test_sector_engine.py -v
"""
import copy
import json
import unittest

from sector_engine import (
    SECTOR_CODES, SECTORS, MODEL_TOOL_FUNCTIONS, allocation_distance,
    calculate_portfolio, paired_workflow_distances, parse_response,
    score_bundle, score_response, score_text, validate_gold, validate_weights,
)


def fixture(source="fidelity_test", labels=None):
    vocabulary = labels or ["Overweight", "Neutral", "Underweight"]
    gold = {"source_id": source, "rating_vocabulary": vocabulary,
            "sector_ratings": {}, "evidence_index": {}}
    response = {"source_id": source, "interpretations": [], "weights": []}
    for i, code in enumerate(SECTOR_CODES):
        eid = f"{source}:{code}"
        label = vocabulary[i % len(vocabulary)]
        gold["sector_ratings"][code] = {"rating": label, "evidence_ids": [eid]}
        gold["evidence_index"][eid] = {"source_id": source, "sector_codes": [code],
                                      "claims": ["rating", "reason", "constraint"]}
        response["interpretations"].append({"sector_code": code, "rating": label,
            "evidence_ids": [eid], "reason": "Synthetic fixture rationale."})
        response["weights"].append({"sector_code": code, "weight": 1 / len(SECTORS),
            "rationale": "Synthetic fixture rationale.", "evidence_ids": [eid]})
    return gold, response


def public_market():
    return {"baseline_id": "synthetic_equal_weight", "baseline_weights": {
        code: 1 / len(SECTORS) for code in SECTOR_CODES},
        "sector_codes": list(SECTOR_CODES),
        "covariance": [[0.01 if i == j else 0 for j in range(11)] for i in range(11)],
        "covariance_unit": "monthly_decimal_return_squared"}


class SectorEngineTests(unittest.TestCase):
    def test_complete_extraction_is_11_and_two_sources_are_22(self):
        g1, r1 = fixture()
        g2, r2 = fixture("ubs_test", ["Attractive", "Neutral", "Unattractive"])
        result = score_bundle([r1, r2], [g1, g2])
        self.assertEqual(result["primary_rating"], {"correct": 22, "expected": 22, "accuracy": 1})
        self.assertIsNone(result["composite_score"])

    def test_missing_response_stays_in_full_denominator(self):
        g1, r1 = fixture()
        g2, _ = fixture("ubs_test", ["Attractive", "Neutral", "Unattractive"])
        result = score_bundle([r1], [g1, g2])
        self.assertEqual(result["primary_rating"]["correct"], 11)
        self.assertEqual(result["primary_rating"]["expected"], 22)
        self.assertEqual(result["sources"][1]["source_response_status"], "missing")

    def test_duplicate_source_is_not_cherry_picked(self):
        gold, response = fixture()
        scored = score_bundle([response, response], [gold])
        self.assertEqual(scored["primary_rating"]["correct"], 0)
        self.assertEqual(scored["sources"][0]["source_response_status"], "duplicate")

    def test_missing_duplicate_unknown_sector_have_separate_records(self):
        gold, response = fixture()
        response["interpretations"].pop()
        response["interpretations"].append(copy.deepcopy(response["interpretations"][0]))
        response["interpretations"].append({"sector_code": "999", "rating": "Neutral"})
        scored = score_response(response, gold)
        self.assertEqual(scored["primary_rating"]["correct"], 9)
        self.assertEqual(scored["primary_rating"]["expected"], 11)
        self.assertEqual(scored["interpretation_structure"]["duplicates"], ["10"])
        self.assertEqual(scored["interpretation_structure"]["missing"], ["60"])
        self.assertEqual(scored["interpretation_structure"]["unknown"], ["999"])

    def test_unknown_labels_not_aliased_between_sources(self):
        gold, response = fixture("ubs_test", ["Attractive", "Neutral", "Unattractive"])
        response["interpretations"][0]["rating"] = "Overweight"
        scored = score_response(response, gold, public_market())
        self.assertEqual(scored["primary_rating"]["correct"], 10)
        self.assertFalse(scored["rating_records"][0]["label_valid_for_source"])
        self.assertEqual(scored["source_tilt_diagnostics"], [])

    def test_fidelity_direction_is_benchmark_relative_continuous_only(self):
        gold, response = fixture()
        gold["allocation_semantics"] = {"kind": "benchmark_relative_tilt",
            "baseline_id": "synthetic_equal_weight",
            "label_directions": {"Overweight": 1, "Underweight": -1, "Neutral": 0}}
        response["weights"][0]["weight"] += 0.02
        response["weights"][1]["weight"] -= 0.02
        scored = score_response(response, gold, public_market())
        self.assertAlmostEqual(scored["source_tilt_diagnostics"][0]["signed_tilt"], 0.02)
        self.assertNotIn("pass", scored["source_tilt_diagnostics"][0])
        other = public_market(); other["baseline_id"] = "different_baseline"
        self.assertEqual(score_response(response, gold, other)["source_tilt_diagnostics"], [])

    def test_wrong_sector_or_unknown_citations_do_not_prove_grounding(self):
        gold, response = fixture()
        response["interpretations"][0]["evidence_ids"] = ["missing_id"]
        response["interpretations"][1]["evidence_ids"] = ["fidelity_test:10"]
        score = score_response(response, gold)
        self.assertEqual(score["primary_rating"]["correct"], 11)
        self.assertEqual(score["evidence"]["rating_citation_valid_count"], 9)
        self.assertIn("requires_independent_review", score["evidence"]["semantic_reason_support"])

    def test_scope_evidence_is_allowed_but_not_a_rating_or_reason_citation(self):
        gold, response = fixture()
        gold["evidence_index"]["scope"] = {"source_id": gold["source_id"],
            "sector_codes": list(SECTOR_CODES), "claims": ["scope", "rating_semantics"]}
        validate_gold(gold)
        response["interpretations"][0]["evidence_ids"] = ["scope"]
        score = score_response(response, gold)
        self.assertEqual(score["primary_rating"]["correct"], 11)
        self.assertFalse(score["rating_records"][0]["rating_citation_valid"])
        self.assertFalse(score["rating_records"][0]["reason_citation_valid"])

    def test_unstated_source_reasons_are_not_missing_model_errors(self):
        gold, response = fixture("ubs_test", ["Attractive", "Neutral", "Unattractive"])
        for code in SECTOR_CODES[:6]:
            gold["sector_ratings"][code]["reason_evidence_ids"] = []
            gold["evidence_index"][f"ubs_test:{code}"]["claims"] = ["rating"]
        for row in response["interpretations"][:6]:
            row["reason"] = "The selected source does not state a separate reason."
            row["reason_evidence_ids"] = []
        score = score_response(response, gold)
        self.assertEqual(score["primary_rating"]["correct"], 11)
        self.assertEqual(score["evidence"]["reason_citation_expected"], 5)
        self.assertEqual(score["evidence"]["reason_citation_valid_count"], 5)
        self.assertEqual(len(score["evidence"]["reason_not_stated_sector_codes"]), 6)
        self.assertIsNone(score["rating_records"][0]["reason_citation_valid"])

    def test_source_identity_mismatch_invalidates_labels_and_evidence(self):
        gold, response = fixture()
        response["source_id"] = "other"
        score = score_response(response, gold)
        self.assertEqual(score["primary_rating"]["correct"], 0)
        self.assertEqual(score["evidence"]["rating_citation_valid_count"], 0)
        self.assertTrue(score["allocation"]["valid"])

    def test_weight_validation_does_not_repair_or_drop_missing_zero(self):
        _, response = fixture()
        original = copy.deepcopy(response["weights"])
        response["weights"][0]["weight"] = -0.01
        out = calculate_portfolio(response["weights"])
        self.assertFalse(out["allocation"]["valid"])
        self.assertFalse(out["repaired"])
        self.assertEqual(response["weights"][0]["weight"], -0.01)
        missing = original[:-1]
        self.assertEqual(validate_weights(missing)["missing_codes"], ["60"])

    def test_boolean_nan_infinity_overflow_and_duplicate_weights(self):
        for value in [True, float("nan"), float("inf"), 10 ** 400, "0.1"]:
            _, response = fixture(); response["weights"][0]["weight"] = value
            self.assertFalse(validate_weights(response["weights"])["valid"])
        _, response = fixture()
        response["weights"].append(copy.deepcopy(response["weights"][0]))
        self.assertEqual(validate_weights(response["weights"])["duplicate_codes"], ["10"])

    def test_engineering_sum_tolerance_retains_signed_raw_residual(self):
        _, response = fixture()
        response["weights"][0]["weight"] += 5e-7
        result = validate_weights(response["weights"])
        self.assertTrue(result["valid"])
        self.assertGreater(result["raw_budget_residual"], 0)
        self.assertFalse(result["normalized_or_repaired"])
        response["weights"][0]["weight"] += 1e-4
        self.assertFalse(validate_weights(response["weights"])["valid"])

    def test_hidden_constraint_is_not_checked_or_enforced_early(self):
        gold, response = fixture()
        constraint = {"constraint_id": "hidden_cap", "kind": "sector_max_weight",
            "sector_code": "10", "bound": 0.05, "evidence_ids": ["fidelity_test:10"]}
        early = calculate_portfolio(response["weights"], submitted_constraints=[constraint],
                                    visible_evidence_ids=[])
        self.assertFalse(early["ok"])
        self.assertEqual(early["submitted_constraint_checks"]["checks"], [])
        late = calculate_portfolio(response["weights"], submitted_constraints=[constraint],
                                   visible_evidence_ids=["fidelity_test:10"])
        self.assertTrue(late["ok"])
        self.assertGreater(late["submitted_constraint_checks"]["checks"][0]["violation"], 0)
        self.assertFalse(late["repaired"])
        gold["constraints"] = [constraint]
        offline = score_response(response, gold)
        self.assertGreater(offline["document_constraint_checks"]["checks"][0]["violation"], 0)
        self.assertNotIn("score_response", MODEL_TOOL_FUNCTIONS)

    def test_tools_do_not_read_or_mutate_gold_or_market(self):
        _, response = fixture()
        market = public_market(); before = copy.deepcopy((response, market))
        out = calculate_portfolio(response["weights"], market)
        self.assertEqual((response, market), before)
        self.assertFalse(out["gold_access"])
        self.assertAlmostEqual(out["market_diagnostics"]["risk"]["raw_variance"], 0.01 / 11)
        self.assertEqual(out["market_diagnostics"]["baseline"]["raw_half_L1_distance"], 0)

    def test_bad_covariance_shape_units_or_negative_eigenvalue_rejected(self):
        _, response = fixture()
        for change in ["shape", "unit", "negative", "asymmetric", "boolean"]:
            market = public_market()
            if change == "shape": market["covariance"].pop()
            if change == "unit": market.pop("covariance_unit")
            if change == "negative": market["covariance"][0][0] = -1
            if change == "asymmetric": market["covariance"][0][1] = 1
            if change == "boolean": market["covariance"][0][0] = True
            self.assertFalse(calculate_portfolio(response["weights"], market)["ok"])

    def test_gold_setup_cannot_reduce_denominator_or_cross_source_scope(self):
        gold, _ = fixture(); del gold["sector_ratings"]["60"]
        with self.assertRaises(ValueError): validate_gold(gold)
        gold, _ = fixture(); gold["evidence_index"]["fidelity_test:10"]["source_id"] = "other"
        with self.assertRaises(ValueError): validate_gold(gold)

    def test_strict_parse_duplicate_json_keys_and_failure_denominator(self):
        gold, _ = fixture()
        for raw in ['{"source_id":"a","source_id":"b"}', '{"x":NaN}', '[1,2]',
                    "[" * 2000 + "]" * 2000, 'not JSON']:
            self.assertFalse(parse_response(raw)["ok"])
            score = score_text(raw, gold)
            self.assertEqual(score["primary_rating"]["correct"], 0)
            self.assertEqual(score["primary_rating"]["expected"], 11)

    def test_four_valid_rule_and_missing_distance_not_zero(self):
        _, a = fixture("a"); _, b = fixture("b")
        responses = {"a": {"R1": copy.deepcopy(a), "R4": copy.deepcopy(a)},
                     "b": {"R1": copy.deepcopy(b), "R4": copy.deepcopy(b)}}
        result = paired_workflow_distances(responses, ("a", "b"))
        self.assertTrue(result["four_valid_allocations"])
        self.assertEqual(result["between_source_distance_R4_minus_R1"], 0)
        responses["b"]["R4"]["weights"].pop()
        result = paired_workflow_distances(responses, ("a", "b"))
        self.assertFalse(result["four_valid_allocations"])
        self.assertIsNone(result["between_source_distance_R4_minus_R1"])
        self.assertTrue(result["within_source"]["a"]["evaluable"])
        self.assertFalse(allocation_distance([], a["weights"])["evaluable"])

    def test_reports_are_strict_json_and_synthetic_inputs_unchanged(self):
        gold, response = fixture()
        before = copy.deepcopy((gold, response))
        report = score_response(response, gold, public_market())
        json.dumps(report, allow_nan=False)
        self.assertEqual(before, (gold, response))


if __name__ == "__main__":
    unittest.main()
