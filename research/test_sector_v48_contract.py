"""Offline engineering fixtures; no model calls or experimental observations."""
from __future__ import annotations

import copy
import json
import math
import unittest

from sector_engine import SECTOR_CODES
from sector_response_schema import validate_response
from sector_v48_contract import (build_system, complete_vector, evaluate_proposal,
                                 repair_eligible, stage_payload)


def market_fixture():
    return {"sector_codes": list(SECTOR_CODES), "baseline_id": "common_test_baseline",
            "baseline_weights": {code: (1.0 if i == 0 else 0.0) for i, code in enumerate(SECTOR_CODES)},
            "covariance": [[0.0001 if i == j else 0.0 for j in range(11)] for i in range(11)],
            "covariance_unit": "daily_decimal_return_squared",
            "lookback_return_dates": ["2026-01-01", "2026-01-31"]}


def registry_fixture():
    return {"rows": [{"fact_id": "M:baseline_weights:10", "sector_code": "10",
                      "metric": "normalized_baseline_weight", "unit": "decimal_weight",
                      "period": ["2026-01-01"], "source_json_pointer": "/baseline_weights/10",
                      "value": 1.0}]}


def proposal_fixture(total=1.0, source_visible=True):
    return {"source_id": "institution_fixture" if source_visible else None,
            "interpretations": ([{"sector_code": code, "rating": "fixture_label",
                                    "evidence_ids": ["visible_document_id"], "reason": "fixture reason"}
                                   for code in SECTOR_CODES] if source_visible else []),
            "weights": [{"sector_code": code, "weight": total if i == 0 else 0.0,
                         "rationale": "fixture choice", "evidence_ids": []}
                        for i, code in enumerate(SECTOR_CODES)],
            "alternatives": "fixture alternative", "risk_discussion": "historical variability only",
            "unresolved": [], "submitted_constraints": []}


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.market = market_fixture()
        self.registry = registry_fixture()
        self.packet = {"source_id": "UNSEEN_INSTITUTION_SENTINEL", "private_fixture": "DO_NOT_EXPOSE_EARLY"}

    def calc(self, response, stage=4, endpoint_id="C0", previous=None):
        return evaluate_proposal(response, stage, self.market, [], endpoint_id, previous)

    def test_r4_visibility_and_complete_structural_schema(self):
        for stage in (1, 2, 3):
            payload = stage_payload(stage, "R4", self.packet, self.market, self.registry)
            text = json.dumps(payload)
            self.assertNotIn("UNSEEN_INSTITUTION_SENTINEL", text)
            self.assertNotIn("DO_NOT_EXPOSE_EARLY", text)
            self.assertNotIn("institution_document", payload)
            self.assertEqual(payload["response_schema"]["properties"]["interpretations"]["maxItems"], 0)
        final = stage_payload(4, "R4", self.packet, self.market, self.registry)
        self.assertEqual(final["institution_document"], self.packet)
        self.assertEqual(final["response_schema"]["properties"]["interpretations"]["minItems"], 11)

    def test_source_packet_occurs_only_at_assigned_onset(self):
        for arm in ("R1", "R4"):
            present = [stage for stage in range(1, 5)
                       if "institution_document" in stage_payload(stage, arm, self.packet, self.market, self.registry)]
            self.assertEqual(present, [1] if arm == "R1" else [4])

    def test_common_market_and_index_only_stage1(self):
        first = stage_payload(1, "R4", self.packet, self.market, self.registry)
        self.assertNotIn("value", first["public_numeric_fact_index"]["columns"])
        self.assertEqual(first["public_numeric_fact_index"]["rows"][0][0], "M:baseline_weights:10")
        for stage in (2, 3, 4):
            next_stage = stage_payload(stage, "R4", self.packet, self.market, self.registry)
            self.assertNotIn("common_market", next_stage)
            self.assertNotIn("public_numeric_fact_index", next_stage)

    def test_fact_registry_must_match_supplied_market(self):
        for corruption in ("value", "id", "duplicate", "pointer"):
            registry = copy.deepcopy(self.registry)
            row = registry["rows"][0]
            if corruption == "value": row["value"] = 0.5
            elif corruption == "id": row["fact_id"] = "hidden:evaluator"
            elif corruption == "duplicate": registry["rows"].append(copy.deepcopy(row))
            else: row["source_json_pointer"] = "/missing"
            with self.subTest(corruption=corruption), self.assertRaises(ValueError):
                stage_payload(1, "R4", self.packet, self.market, registry)

    def test_matrix_reference_ids_are_visible_without_duplicate_values(self):
        self.registry["matrix_fact_references"] = [{"fact_id": "M:covariance",
            "source_json_pointer": "/covariance", "unit": "daily_decimal_return_squared",
            "sector_order": list(SECTOR_CODES)}]
        payload = stage_payload(1, "R4", self.packet, self.market, self.registry)
        refs = payload["public_numeric_fact_index"]["matrix_references"]
        self.assertEqual(refs[0]["fact_id"], "M:covariance")
        self.assertEqual(refs[0]["sector_order"], list(SECTOR_CODES))
        self.assertNotIn("value", refs[0])
        self.registry["matrix_fact_references"][0]["sector_order"].reverse()
        with self.assertRaises(ValueError):
            stage_payload(1, "R4", self.packet, self.market, self.registry)

    def test_payload_and_calculator_do_not_mutate_supplied_objects(self):
        proposal = proposal_fixture(0.965)
        originals = copy.deepcopy((self.market, self.registry, self.packet, proposal))
        payload = stage_payload(1, "R1", self.packet, self.market, self.registry)
        payload["common_market"]["baseline_weights"]["10"] = 0.5
        payload["institution_document"]["source_id"] = "changed_copy"
        self.calc(proposal)
        self.assertEqual((self.market, self.registry, self.packet, proposal), originals)

    def test_system_preserves_topic_and_permitted_departure(self):
        system = build_system({"common_instructions": ["PRESPECIFIED_INSTRUCTION_SENTINEL"]})
        self.assertIn("published judgments", system)
        self.assertIn("reasoned departure", system)
        self.assertIn("C0", system)
        self.assertIn("PRESPECIFIED_INSTRUCTION_SENTINEL", system)
        with self.assertRaises(ValueError): build_system({})

    def test_early_empty_weights_are_not_a_zero_budget_portfolio(self):
        for stage in (1, 2):
            p = proposal_fixture(source_visible=False)
            p["weights"] = []
            result = self.calc(p, stage, "stage" + str(stage))
            self.assertEqual(result["status"], "not_yet_proposed")
            self.assertIsNone(result["calculator_result"])
            self.assertIsNone(result["allocation"]["raw_sum"])
            self.assertIsNone(result["valid_portfolio_risk"])
            self.assertEqual(result["facts"], [])

    def test_stage3_empty_is_invalid_without_imputation(self):
        p = proposal_fixture(source_visible=False)
        p["weights"] = []
        result = self.calc(p, 3, "stage3")
        self.assertEqual(result["status"], "invalid_raw_proposal")
        self.assertIsNone(result["allocation"]["raw_sum"])
        self.assertFalse(result["repair_eligibility"]["eligible"])

    def test_schema_requires_zero_or_eleven_early_and_eleven_late(self):
        for stage in (1, 2, 3, 4):
            for count in (0, 1, 10, 11):
                p = proposal_fixture(source_visible=False)
                p["weights"] = p["weights"][:count]
                check = validate_response(json.dumps(p), stage, None, institution_visible=False)
                self.assertEqual(check["valid"], count == 11 or (stage < 3 and count == 0))

    def test_complete_invalid_sum_is_raw_and_has_no_valid_portfolio_risk(self):
        p = proposal_fixture(0.965)
        result = self.calc(p)
        self.assertEqual(result["allocation"]["raw_sum"], 0.965)
        self.assertAlmostEqual(result["allocation"]["raw_budget_residual"], -0.035)
        self.assertTrue(complete_vector(p["weights"])["complete"])
        self.assertTrue(result["repair_eligibility"]["eligible"])
        self.assertIsNone(result["valid_portfolio_risk"])
        self.assertIsNone(result["calculator_result"]["market_diagnostics"]["risk"])
        self.assertAlmostEqual(result["raw_algebra"]["active_weights"]["10"], -0.035)
        self.assertFalse(any(f["interpretation_scope"] == "valid_portfolio_historical_diagnostic" for f in result["facts"]))
        self.assertFalse(result["repaired"])
        self.assertEqual(p["weights"][0]["weight"], 0.965)

    def test_valid_portfolio_risk_and_fact_units(self):
        result = self.calc(proposal_fixture())
        self.assertTrue(result["allocation"]["valid"])
        self.assertAlmostEqual(result["valid_portfolio_risk"]["volatility"], 0.01)
        fact = next(f for f in result["facts"] if f["fact_id"] == "C:C0:volatility")
        self.assertEqual(fact["unit"], "daily_decimal_return")
        self.assertEqual(fact["period"], self.market["lookback_return_dates"])
        self.assertFalse(result["repair_eligibility"]["eligible"])

    def test_negative_and_above_one_are_eligible_even_when_sum_is_one(self):
        p = proposal_fixture(1.1)
        p["weights"][1]["weight"] = -0.1
        result = self.calc(p)
        self.assertAlmostEqual(result["allocation"]["raw_sum"], 1.0)
        self.assertFalse(result["allocation"]["valid"])
        self.assertEqual(result["allocation"]["negative_weight_codes"], ["15"])
        self.assertEqual(result["allocation"]["above_one_weight_codes"], ["10"])
        self.assertTrue(result["repair_eligibility"]["eligible"])
        self.assertIsNone(result["valid_portfolio_risk"])

    def test_bool_missing_duplicate_unknown_and_nonfinite_not_repairable(self):
        for corruption in ("bool", "missing", "duplicate", "unknown", "nan", "infinity"):
            p = proposal_fixture(0.9)
            if corruption == "bool": p["weights"][0]["weight"] = True
            elif corruption == "missing": p["weights"].pop()
            elif corruption == "duplicate": p["weights"][-1]["sector_code"] = "10"
            elif corruption == "unknown": p["weights"][-1]["sector_code"] = "99"
            elif corruption == "nan": p["weights"][0]["weight"] = math.nan
            else: p["weights"][0]["weight"] = math.inf
            with self.subTest(corruption=corruption):
                self.assertFalse(complete_vector(p["weights"])["complete"])
                self.assertFalse(repair_eligible(p)["eligible"])
                result = self.calc(p)
                self.assertFalse(result["allocation"]["valid"])
                self.assertIsNone(result["valid_portfolio_risk"])

    def test_incomplete_response_structure_is_not_repairable(self):
        p = proposal_fixture(0.9)
        del p["alternatives"]
        self.assertFalse(repair_eligible(p)["eligible"])
        self.assertEqual(repair_eligible(p)["reason"], "invalid_response_structure")

    def test_aggregate_overflow_cannot_be_valid(self):
        p = proposal_fixture()
        for row in p["weights"]: row["weight"] = 1e308
        result = self.calc(p)
        self.assertTrue(complete_vector(p["weights"])["complete"])
        self.assertFalse(result["allocation"]["valid"])
        self.assertIsNone(result["allocation"]["raw_sum"])
        self.assertIsNone(result["valid_portfolio_risk"])
        self.assertTrue(result["repair_eligibility"]["eligible"])
        json.dumps(result, allow_nan=False)

    def test_fact_ids_and_hashes_track_actual_candidate(self):
        first = proposal_fixture(0.965)
        revised = proposal_fixture(0.975)
        a = self.calc(first)
        b = self.calc(revised, endpoint_id="C1", previous=first["weights"])
        self.assertTrue(all(f["fact_id"].startswith("C:C0:") for f in a["facts"]))
        self.assertTrue(all(f["fact_id"].startswith("C:C1:") for f in b["facts"]))
        self.assertNotEqual(a["lineage"]["submitted_vector_sha256"], b["lineage"]["submitted_vector_sha256"])
        self.assertEqual(a["lineage"]["market_values_sha256"], b["lineage"]["market_values_sha256"])
        self.assertEqual(b["lineage"]["previous_submitted_vector_sha256"], a["lineage"]["submitted_vector_sha256"])
        for fact in b["facts"]:
            self.assertEqual(fact["candidate_id"], "C1")
            self.assertEqual(fact["data_version"], b["lineage"]["submitted_vector_sha256"])
            self.assertEqual(fact["market_data_version"], b["lineage"]["market_values_sha256"])
            self.assertEqual(fact["subject"], fact["sector_code"] or "portfolio")
        self.assertAlmostEqual(b["raw_weight_deltas"]["10"], 0.01)
        self.assertEqual(sum(delta != 0 for delta in b["raw_weight_deltas"].values()), 1)

    def test_changed_market_changes_lineage_and_algebra(self):
        p = proposal_fixture()
        original = self.calc(p)
        self.market["baseline_weights"]["10"] = 0.8
        self.market["baseline_weights"]["15"] = 0.2
        changed = self.calc(p)
        self.assertNotEqual(original["lineage"]["market_values_sha256"], changed["lineage"]["market_values_sha256"])
        self.assertAlmostEqual(changed["raw_algebra"]["active_weights"]["10"], 0.2)

    def test_endpoint_cannot_include_hidden_case_identity_or_future_stage(self):
        for endpoint in ("fidelity_q2_2026:C0", "stage4", "C3", "stage1"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                self.calc(proposal_fixture(), endpoint_id=endpoint)
        with self.assertRaises(ValueError):
            self.calc(proposal_fixture(source_visible=False), stage=1, endpoint_id="C0")

    def test_unavailable_constraint_evidence_cannot_expand_visibility(self):
        p = proposal_fixture()
        p["submitted_constraints"] = [{"constraint_id": "invented", "sector_code": "10",
                                        "kind": "sector_max_weight", "bound": 0.1,
                                        "evidence_ids": ["hidden_evidence"]}]
        result = self.calc(p)
        self.assertFalse(result["calculator_result"]["submitted_constraint_checks"]["valid_request"])
        self.assertFalse(result["repair_eligibility"]["eligible"])
        self.assertFalse(result["gold_access"])

    def test_invalid_visible_ids_and_stage_are_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_proposal(proposal_fixture(), 4, self.market, ["same", "same"], "C0")
        for stage in (True, 0, 5, 1.0):
            with self.subTest(stage=stage), self.assertRaises(ValueError):
                stage_payload(stage, "R4", self.packet, self.market, self.registry)


if __name__ == "__main__":
    unittest.main()
