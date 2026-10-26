"""Independent exact-arithmetic tests for the derived allocation finalizer.

These tests contain synthetic JSON only. They do not read experiment responses,
run a model, change frozen inputs, or turn derived weights into raw observations.
"""

import json
import sys
import unittest
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import finalize_sector_allocation as finalizer


CODES = ("10", "15", "20", "25", "30", "35", "40", "45", "50", "55", "60")
UNITS = 10000


def raw_vector(tokens, order=None):
    """Write numeric tokens verbatim, avoiding a float or Decimal JSON encoder."""
    if len(tokens) != len(CODES):
        raise ValueError("Synthetic vector must have eleven entries")
    by_code = dict(zip(CODES, tokens))
    order = CODES if order is None else order
    return '{"sectors":[' + ",".join(
        '{"sector_code":' + json.dumps(code) + ',"weight":' + by_code[code] + "}"
        for code in order
    ) + "]}"


def rational(value):
    return Fraction(int(value["numerator"]), int(value["denominator"]))


def with_constraints(raw, constraints):
    return raw[:-1] + ',"submitted_constraints":' + json.dumps(constraints) + "}"


class FinalizeAllocationTests(unittest.TestCase):
    def check_final(self, tokens, order=None):
        raw = raw_vector(tokens, order)
        result = finalizer.finalize_content(raw)
        self.assertEqual(result["status"], "finalized", result)
        json.dumps(result, allow_nan=False)
        rows = result["rows"]
        self.assertEqual(tuple(row["sector_code"] for row in rows), CODES)
        self.assertEqual(len(rows), len(CODES))
        source = [Fraction(Decimal(token)) for token in tokens]
        total = sum(source, Fraction())
        self.assertEqual(Fraction(Decimal(result["raw_sum_exact_decimal"])), total)
        self.assertEqual(result["final_total_units"], UNITS)
        self.assertEqual(result["final_total_percent"], "100.00")
        self.assertEqual(sum(row["final_units"] for row in rows), UNITS)
        self.assertEqual(sum((rational(row["normalized_weight_exact"]) for row in rows), Fraction()), 1)
        self.assertEqual(sum((Fraction(Decimal(row["final_weight_decimal"])) for row in rows), Fraction()), 1)
        self.assertEqual(sum((Decimal(row["final_percent"]) for row in rows), Decimal()), Decimal("100.00"))
        self.assertEqual(sum((rational(row["normalization_delta_exact"]) for row in rows), Fraction()), 1 - total)
        self.assertEqual(sum((rational(row["rounding_delta_exact"]) for row in rows), Fraction()), 0)
        for code, original, row in zip(CODES, source, rows):
            with self.subTest(code=code):
                normalized = original / total
                units = row["final_units"]
                self.assertIs(type(units), int)
                self.assertGreaterEqual(units, 0)
                self.assertLessEqual(units, UNITS)
                self.assertEqual(Fraction(Decimal(row["raw_weight_exact_decimal"])), original)
                self.assertEqual(rational(row["normalized_weight_exact"]), normalized)
                self.assertEqual(Fraction(Decimal(row["final_weight_decimal"])), Fraction(units, UNITS))
                self.assertEqual(Fraction(Decimal(row["final_percent"])), Fraction(units, 100))
                self.assertRegex(row["final_percent"], r"^\d+\.\d{2}$")
                self.assertEqual(rational(row["normalization_delta_exact"]), normalized - original)
                self.assertEqual(rational(row["rounding_delta_exact"]), Fraction(units, UNITS) - normalized)
                quota = normalized * UNITS
                floor = quota.numerator // quota.denominator
                self.assertIn(units, {floor, floor + 1})
                self.assertLess(abs(Fraction(units) - quota), 1)
                if original == 0:
                    self.assertEqual(units, 0)
        return result

    def assert_unavailable(self, raw):
        result = finalizer.finalize_content(raw)
        self.assertEqual(result["status"], "unavailable", result)
        json.dumps(result, allow_nan=False)
        self.assertIsInstance(result["reasons"], list)
        self.assertTrue(result["reasons"])
        self.assertFalse(result.get("rows"), "Unassessable input must not receive a fabricated portfolio")
        return result

    def test_official_sector_order_is_explicit(self):
        self.assertEqual(tuple(finalizer.CODES), CODES)

    def test_point92_vector_scales_and_distributes_exact_remainder(self):
        result = self.check_final(["0.08"] * 10 + ["0.12"])
        self.assertEqual(Decimal(result["raw_sum_exact_decimal"]), Decimal("0.92"))
        self.assertEqual([r["final_units"] for r in result["rows"]], [870] * 6 + [869] * 4 + [1304])

    def test_eleven_equal_weights_use_official_order_for_exact_tie(self):
        result = self.check_final(["0.09"] * 11)
        self.assertEqual([r["final_units"] for r in result["rows"]], [910] + [909] * 10)
        self.assertTrue(all(rational(r["normalized_weight_exact"]) == Fraction(1, 11) for r in result["rows"]))

    def test_three_equal_weights_retain_nonterminating_exact_rationals(self):
        result = self.check_final(["1"] * 3 + ["0"] * 8)
        self.assertEqual([r["final_units"] for r in result["rows"]], [3334, 3333, 3333] + [0] * 8)
        self.assertEqual(rational(result["rows"][0]["normalized_weight_exact"]), Fraction(1, 3))

    def test_near_tie_beyond_default_decimal_precision_is_not_a_tie(self):
        slightly_larger = "1." + "0" * 39 + "1"
        result = self.check_final(["1", slightly_larger, "1"] + ["0"] * 8)
        self.assertEqual([r["final_units"] for r in result["rows"]], [3333, 3334, 3333] + [0] * 8)

    def test_permutation_does_not_change_sector_mapping_or_tie_result(self):
        tokens = ["0.08"] * 10 + ["0.12"]
        normal = self.check_final(tokens)
        reversed_rows = self.check_final(tokens, tuple(reversed(CODES)))
        mixed_rows = self.check_final(tokens, CODES[4:] + CODES[:4])
        self.assertEqual(normal["rows"], reversed_rows["rows"])
        self.assertEqual(normal["rows"], mixed_rows["rows"])

    def test_positive_rescaling_preserves_normalized_and_display_vectors(self):
        left = self.check_final(["0.08"] * 10 + ["0.12"])
        right = self.check_final(["8"] * 10 + ["12"])
        for a, b in zip(left["rows"], right["rows"]):
            self.assertEqual(a["normalized_weight_exact"], b["normalized_weight_exact"])
            self.assertEqual(a["final_units"], b["final_units"])
        self.assertNotEqual(left["raw_sum_exact_decimal"], right["raw_sum_exact_decimal"])

    def test_already_unit_sum_on_basis_point_grid_is_identity(self):
        result = self.check_final(["0.10"] * 10 + ["0"])
        self.assertEqual([r["final_units"] for r in result["rows"]], [1000] * 10 + [0])
        for row in result["rows"]:
            self.assertEqual(rational(row["normalization_delta_exact"]), 0)
            self.assertEqual(rational(row["rounding_delta_exact"]), 0)

    def test_single_positive_component_and_signed_zero(self):
        result = self.check_final(["1.7", "-0.0"] + ["0"] * 9)
        self.assertEqual([r["final_units"] for r in result["rows"]], [10000] + [0] * 10)

    def test_zero_preservation_and_small_positive_rounding_to_zero(self):
        result = self.check_final(["0.00005", "0.00005", "0.9999"] + ["0"] * 8)
        self.assertEqual([r["final_units"] for r in result["rows"]], [1, 0, 9999] + [0] * 8)
        self.assertGreater(rational(result["rows"][1]["normalized_weight_exact"]), 0)

    def test_finite_tiny_decimal_does_not_underflow_before_normalization(self):
        result = self.check_final(["1e-400", "2e-400"] + ["0"] * 9)
        self.assertEqual([r["final_units"] for r in result["rows"]], [3333, 6667] + [0] * 9)
        self.assertEqual(Fraction(Decimal(result["raw_sum_exact_decimal"])), Fraction(3, 10**400))

    def test_finite_large_decimal_does_not_overflow_to_infinity(self):
        result = self.check_final(["1e400", "2e400"] + ["0"] * 9)
        self.assertEqual([r["final_units"] for r in result["rows"]], [3333, 6667] + [0] * 9)

    def test_display_finalization_is_idempotent(self):
        first = self.check_final(["0.08"] * 10 + ["0.12"])
        second = self.check_final([r["final_weight_decimal"] for r in first["rows"]])
        self.assertEqual([r["final_units"] for r in first["rows"]], [r["final_units"] for r in second["rows"]])
        self.assertTrue(all(rational(r["normalization_delta_exact"]) == 0 for r in second["rows"]))

    def test_largest_remainders_are_selected_not_just_first_sectors(self):
        result = self.check_final(["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"])
        quotas = [rational(r["normalized_weight_exact"]) * UNITS for r in result["rows"]]
        floors = [q.numerator // q.denominator for q in quotas]
        remaining = UNITS - sum(floors)
        ranked = sorted(range(11), key=lambda i: (-(quotas[i] - floors[i]), i))
        winners = set(ranked[:remaining])
        self.assertEqual([r["final_units"] for r in result["rows"]], [f + (i in winners) for i, f in enumerate(floors)])

    def test_negative_weight_including_underflow_sized_negative_is_unavailable(self):
        for negative in ("-0.1", "-1e-400"):
            with self.subTest(negative=negative):
                self.assert_unavailable(raw_vector([negative, "1"] + ["0"] * 9))

    def test_nonfinite_json_constants_are_unavailable(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(token=token):
                self.assert_unavailable(raw_vector([token] + ["0.1"] * 10))

    def test_boolean_and_string_weights_are_not_coerced(self):
        for token in ("true", "false", '"0.1"', "null"):
            with self.subTest(token=token):
                self.assert_unavailable(raw_vector([token] + ["0.1"] * 10))

    def test_all_zero_vector_has_no_arbitrary_fallback(self):
        self.assert_unavailable(raw_vector(["0"] * 11))

    def test_missing_sector_or_missing_weight_is_unavailable(self):
        parsed = json.loads(raw_vector(["0.1"] * 11))
        parsed["sectors"].pop()
        self.assert_unavailable(json.dumps(parsed))
        parsed = json.loads(raw_vector(["0.1"] * 11))
        del parsed["sectors"][0]["weight"]
        self.assert_unavailable(json.dumps(parsed))

    def test_duplicate_unknown_or_noncanonical_sector_code_is_unavailable(self):
        for code in ("15", "99", 10, "010"):
            with self.subTest(code=code):
                parsed = json.loads(raw_vector(["0.1"] * 11))
                parsed["sectors"][0]["sector_code"] = code
                self.assert_unavailable(json.dumps(parsed))

    def test_extra_row_is_not_silently_dropped(self):
        parsed = json.loads(raw_vector(["0.1"] * 11))
        parsed["sectors"].append({"sector_code": "99", "weight": 0})
        self.assert_unavailable(json.dumps(parsed))

    def test_duplicate_json_object_keys_are_not_last_value_wins(self):
        valid = raw_vector(["0.1"] * 11)
        duplicate_top = valid[:-1] + ',"sectors":' + valid[len('{"sectors":'):-1] + "}"
        self.assert_unavailable(duplicate_top)
        self.assert_unavailable(valid.replace('"weight":0.1', '"weight":0.1,"weight":0.2', 1))

    def test_malformed_or_partial_input_is_not_salvaged(self):
        valid = raw_vector(["0.1"] * 11)
        for raw in ("", "not JSON", "[]", "null", "{}", '{"sectors":{}}', valid[:-2]):
            with self.subTest(raw=raw[:40]):
                self.assert_unavailable(raw)
        parsed = json.loads(valid)
        parsed["sectors"][0] = None
        self.assert_unavailable(json.dumps(parsed))

    def test_scaling_can_newly_violate_submitted_bound_without_clipping(self):
        constraint = {"constraint_id": "cap", "sector_code": "10", "kind": "sector_max_weight",
                      "bound": 0.3, "evidence_ids": ["synthetic:cap"]}
        result = finalizer.finalize_content(with_constraints(raw_vector(["0.2"] + ["0.03"] * 10), [constraint]))
        self.assertEqual(result["status"], "finalized")
        self.assertEqual(result["rows"][0]["final_units"], 4000)
        record = result["submitted_constraint_diagnostics"]["records"][0]
        self.assertTrue(record["raw_satisfied"])
        self.assertFalse(record["normalized_satisfied"])
        self.assertFalse(record["final_satisfied"])
        json.dumps(result, allow_nan=False)

    def test_rounding_can_newly_violate_submitted_bound_without_second_repair(self):
        constraint = {"constraint_id": "cap", "sector_code": "10", "kind": "sector_max_weight",
                      "bound": 0.33335, "evidence_ids": ["synthetic:cap"]}
        raw = raw_vector(["0.33335", "0.33335", "0.33330"] + ["0"] * 8)
        result = finalizer.finalize_content(with_constraints(raw, [constraint]))
        self.assertEqual(result["status"], "finalized")
        record = result["submitted_constraint_diagnostics"]["records"][0]
        self.assertTrue(record["raw_satisfied"])
        self.assertTrue(record["normalized_satisfied"])
        self.assertFalse(record["final_satisfied"])
        self.assertEqual(result["rows"][0]["final_units"], 3334)

    def test_malformed_constraint_ids_remain_serializable_and_unassessable(self):
        for identifier in (1, {"unexpected": 1}, [1], "", None):
            with self.subTest(identifier=identifier):
                constraint = {"constraint_id": identifier, "sector_code": "10", "kind": "sector_max_weight",
                              "bound": 0.2, "evidence_ids": ["synthetic:cap"]}
                result = finalizer.finalize_content(with_constraints(raw_vector(["0.1"] * 10 + ["0"]), [constraint]))
                self.assertEqual(result["status"], "finalized")
                json.dumps(result, allow_nan=False)
                self.assertEqual(result["submitted_constraint_diagnostics"]["unassessable_count"], 1)

    def test_duplicate_constraint_ids_are_not_silently_combined(self):
        constraint = {"constraint_id": "duplicate", "sector_code": "10", "kind": "sector_max_weight",
                      "bound": 0.2, "evidence_ids": ["synthetic:cap"]}
        result = finalizer.finalize_content(with_constraints(raw_vector(["0.1"] * 10 + ["0"]), [constraint, constraint]))
        self.assertEqual(result["status"], "finalized")
        self.assertGreaterEqual(result["submitted_constraint_diagnostics"]["unassessable_count"], 1)
        json.dumps(result, allow_nan=False)

    def test_invalid_constraint_bounds_are_unassessable_not_portfolio_constraints(self):
        for bound in (-0.1, 1.1, True, "0.2", None):
            with self.subTest(bound=bound):
                constraint = {"constraint_id": "cap", "sector_code": "10", "kind": "sector_max_weight",
                              "bound": bound, "evidence_ids": ["synthetic:cap"]}
                result = finalizer.finalize_content(with_constraints(raw_vector(["0.1"] * 10 + ["0"]), [constraint]))
                self.assertEqual(result["status"], "finalized")
                self.assertEqual(result["submitted_constraint_diagnostics"]["unassessable_count"], 1)
                json.dumps(result, allow_nan=False)

    def test_malformed_constraint_container_does_not_invent_validated_constraints(self):
        result = finalizer.finalize_content(with_constraints(raw_vector(["0.1"] * 10 + ["0"]), {"unexpected": 1}))
        self.assertEqual(result["status"], "finalized")
        self.assertEqual(result["submitted_constraint_diagnostics"]["status"], "unassessable")
        json.dumps(result, allow_nan=False)

    def test_bounded_resource_guard_rejects_huge_compact_numeric_tokens(self):
        # Root confirmed guards are installed before Fraction conversion. These
        # compact tokens must never construct the corresponding giant integers.
        for token in ("1e1000000000", "1e-1000000000", "1" * 513):
            with self.subTest(token=token[:30]):
                result = self.assert_unavailable(raw_vector([token] + ["0"] * 10))
                self.assertTrue(any("resource_limit" in str(reason) for reason in result["reasons"]))

    def test_huge_constraint_number_is_bounded_and_result_stays_serializable(self):
        constraint = {"constraint_id": "cap", "sector_code": "10", "kind": "sector_max_weight",
                      "bound": "HUGE_TOKEN", "evidence_ids": ["synthetic:cap"]}
        raw = with_constraints(raw_vector(["0.1"] * 10 + ["0"]), [constraint]).replace('"HUGE_TOKEN"', "1e1000000000")
        result = finalizer.finalize_content(raw)
        self.assertEqual(result["status"], "finalized")
        self.assertEqual(result["submitted_constraint_diagnostics"]["unassessable_count"], 1)
        json.dumps(result, allow_nan=False)

    def test_exponent_beyond_decimal_platform_limit_is_reported_not_raised(self):
        self.assert_unavailable(raw_vector(["1e999999999999999999999999999999"] + ["0"] * 10))


if __name__ == "__main__":
    unittest.main()
