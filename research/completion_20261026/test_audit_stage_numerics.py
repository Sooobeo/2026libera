"""Offline numeric and artifact-binding tests; all response text is synthetic.

Guard re-execution is mocked only in the bundle adapter unit tests. Its frozen
implementation is separately reviewed/tested; this suite does not claim a live
stage integration test.
"""
import copy
from decimal import Decimal
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).with_name("audit_stage_numerics.py")
SPEC = importlib.util.spec_from_file_location("numeric_audit_under_test", SOURCE)
n = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(n)


def raw(weights=None, codes=None):
    weights = weights or ["1"] * 11
    codes = codes or n.CODES
    return '{"sectors":[' + ','.join('{"sector_code":"' + c + '","weight":' + str(w) + '}'
                                     for c, w in zip(codes, weights)) + ']}'


def market():
    # Deliberately distinctive ordered rows and one nonzero off-diagonal.
    cov = [[Decimal("0.0001") if i == j else Decimal(0) for j in range(11)] for i in range(11)]
    cov[0][1] = cov[1][0] = Decimal("0.00005")
    corr = [[Decimal(1) if i == j else Decimal(0) for j in range(11)] for i in range(11)]
    corr[0][1] = corr[1][0] = Decimal("0.5")
    return {"sector_codes": list(n.CODES), "sector_names": ["sector " + c for c in n.CODES],
            "tickers": ["ETF" + c for c in n.CODES],
            "daily_mean_return": [Decimal(i + 1) / 1000 for i in range(11)],
            "daily_volatility": [Decimal("0.01")] * 11,
            "annualized_volatility_diagnostic": [Decimal("0.02")] * 11,
            "lookback_compound_return": [Decimal(i + 1) / 100 for i in range(11)],
            "benchmark_reported_weights_percent": [Decimal(19)] + [Decimal("8.1")] * 10,
            "baseline_weights": {c: Decimal("0.19") if c == "10" else Decimal("0.081") for c in n.CODES},
            "covariance": cov, "correlation": corr, "annualization_trading_days": Decimal(4),
            "return_observations": Decimal(60), "lookback_return_dates": ["start", "end"],
            "covariance_ddof": Decimal(1), "units": "daily_decimal_return",
            "covariance_unit": "daily_decimal_return_squared", "cutoff_exclusive": "after_end"}


def index():
    return {"matrix_reference_table": {"shared": {"sector_order": list(n.CODES)}},
            "fact_tables": [{"shared": {"metric": "mean", "unit": "daily_decimal_return", "period": "lookback"},
                             "columns": ["fact_id", "sector_code", "common_market_json_pointer"],
                             "rows": [["mean:" + c, c, "/daily_mean_return/" + str(i)] for i, c in enumerate(n.CODES)]},
                            {"shared": {"metric": "benchmark", "unit": "decimal_weight", "period": "snapshot"},
                             "columns": ["fact_id", "sector_code", "common_market_json_pointer"],
                             "rows": [["benchmark:10", "10", "/baseline_weights/10"]]}]}


def sidecar():
    # Analytic equal-11 fixture: exactly one residual unit, first canonical code.
    rows = []
    for i, c in enumerate(n.CODES):
        units = 910 if i == 0 else 909
        rows.append({"sector_code": c, "final_units": units, "raw_weight_exact_decimal": "1",
                     "normalized_weight_exact": n.ratio(Fraction(1, 11)),
                     "normalization_delta_exact": n.ratio(Fraction(-10, 11)),
                     "rounding_delta_exact": n.ratio(Fraction(units, 10000) - Fraction(1, 11))})
    return {"status": "finalized", "rows": rows, "raw_sum_exact_decimal": "11",
            "normalization_multiplier_exact": n.ratio(Fraction(1, 11)), "normalization_applied": True,
            "final_total_units": 10000}


class ArithmeticTests(unittest.TestCase):
    def test_equal_eleven_canonical_tie_is_input_order_independent(self):
        result = n.independent_allocation(raw(codes=list(reversed(n.CODES))))
        self.assertEqual(result["independent_total_units"], 10000)
        self.assertEqual(result["remainder_recipients"], ["10"])
        self.assertEqual([r["independent_units"] for r in result["rows"]], [910] + [909] * 10)

    def test_material_092_sum_is_normalization_not_rounding(self):
        result = n.independent_allocation(raw(["0.02", "0.02", "0.10", "0.09", "0.04", "0.09", "0.12", "0.38", "0.03", "0.02", "0.01"]))
        self.assertEqual(n.unratio(result["raw_sum"]), Fraction(92, 100))
        self.assertFalse(result["raw_budget_within_1e_6"])
        self.assertEqual(n.unratio(result["normalization_multiplier"]), Fraction(25, 23))
        self.assertEqual([r["independent_units"] for r in result["rows"]], [218, 217, 1087, 978, 435, 978, 1304, 4131, 326, 217, 109])

    def test_exact_budget_preserved_with_rounding(self):
        result = n.independent_allocation(raw(["0.33333"] * 3 + ["0.00001"] + ["0"] * 7))
        self.assertEqual(n.unratio(result["raw_sum"]), 1)
        self.assertFalse(result["normalization_applied"])
        self.assertEqual([r["independent_units"] for r in result["rows"]], [3334, 3333, 3333] + [0] * 8)

    def test_numeric_policy_rejects_malformed_vectors_but_retains_diagnostics(self):
        cases = [raw(["-1"] + ["1"] * 10), raw(["0"] * 11), raw(["true"] + ["1"] * 10),
                 raw(["NaN"] + ["1"] * 10), raw(["1e513"] + ["1"] * 10),
                 raw(["\"0.1\""] + ["1"] * 10), raw(codes=["10"] * 11),
                 '{"sectors":[]}', '{"sectors":[],"sectors":[]}']
        for value in cases:
            with self.subTest(value=value[:70]):
                self.assertEqual(n.independent_allocation(value)["status"], "unavailable")
        negative = n.independent_allocation(cases[0])
        self.assertEqual(negative["raw_negative_codes"], ["10"])
        self.assertEqual(n.unratio(negative["raw_sum"]), 9)

    def test_above_one_is_retained_raw_constraint_not_scaling_veto(self):
        result = n.independent_allocation(raw(["2"] + ["0"] * 10))
        self.assertEqual(result["status"], "mathematically_scalable_vector")
        self.assertEqual(result["raw_above_one_codes"], ["10"])
        self.assertEqual(result["rows"][0]["independent_units"], 10000)

    def test_overflow_and_nonfinite_strict_document_rejected(self):
        for value in ('{"x":1e400}', '{"x":NaN}', '{"x":1,"x":2}'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                n.strict(value)

    def test_sidecar_full_numeric_identity_and_mismatch(self):
        independent = n.independent_allocation(raw())
        self.assertTrue(n.compare_sidecar(independent, sidecar(), "completed")["matches"])
        for field, value in (("final_units", 909), ("raw_weight_exact_decimal", "1.01"),
                             ("normalized_weight_exact", n.ratio(Fraction(1, 10))),
                             ("rounding_delta_exact", n.ratio(0))):
            changed = sidecar()
            changed["rows"][0][field] = value
            with self.subTest(field=field):
                self.assertFalse(n.compare_sidecar(independent, changed, "completed")["matches"])
        changed = sidecar()
        changed["normalization_multiplier_exact"] = n.ratio(1)
        self.assertFalse(n.compare_sidecar(independent, changed, "completed")["matches"])

    def test_structure_failure_keeps_mathematical_scalability_separate(self):
        result = n.compare_sidecar(n.independent_allocation(raw()), {"status": "unavailable"}, "model_structure_failure")
        self.assertTrue(result["matches"])
        self.assertFalse(result["accepted_endpoint_expected_available"])

    def test_derived_sum_can_exceed_individual_input_digit_or_exponent_cap(self):
        value = Fraction(9 * 10 ** 512)
        independent = n.independent_allocation(raw(["9e512"] * 11))
        self.assertEqual(independent["status"], "mathematically_scalable_vector")
        expected = sidecar()
        expected["raw_sum_exact_decimal"] = str(11 * value.numerator)
        expected["normalization_multiplier_exact"] = n.ratio(1 / (11 * value))
        for row in expected["rows"]:
            row["raw_weight_exact_decimal"] = str(value.numerator)
            row["normalization_delta_exact"] = n.ratio(Fraction(1, 11) - value)
        self.assertTrue(n.compare_sidecar(independent, expected, "completed")["matches"])

    def test_malformed_sidecar_is_comparison_failure_not_fabricated_match(self):
        result = n.compare_sidecar(n.independent_allocation(raw()), {"status": "finalized", "rows": None}, "completed")
        self.assertFalse(result["matches"])
        self.assertIn("malformed_sidecar_numeric_fields", result)


class MarketTests(unittest.TestCase):
    def test_visible_facts_units_and_exact_covariance_recomputations(self):
        result = n.market_facts(market(), index())
        self.assertEqual(result["numeric_fact_table"][0]["percent_equivalent"], "0.1")
        self.assertEqual(Decimal(result["sector_internal_checks"][0]["daily_sd_minus_visible_approx"]), 0)
        self.assertEqual(Decimal(result["sector_internal_checks"][0]["annual_sd_minus_visible_approx"]), 0)
        self.assertEqual(Decimal(result["matrix_internal_checks"][1]["correlation_recomputed_approx"]), Decimal("0.5"))
        self.assertEqual(n.unratio(result["covariance_symmetry_max_abs"]), 0)
        self.assertIn("no 60 by 11", result["unrecomputed"][0])

    def test_swapping_order_with_arrays_and_pointers_preserves_sector_facts(self):
        m, ix = market(), index()
        permutation = list(reversed(range(11)))
        for key, value in list(m.items()):
            if isinstance(value, list) and len(value) == 11:
                m[key] = [[value[i][j] for j in permutation] for i in permutation] if key in ("covariance", "correlation") else [value[i] for i in permutation]
        ix["matrix_reference_table"]["shared"]["sector_order"] = m["sector_codes"]
        for row in ix["fact_tables"][0]["rows"]:
            row[2] = "/daily_mean_return/" + str(m["sector_codes"].index(row[1]))
        result = n.market_facts(m, ix)
        self.assertEqual(n.unratio(result["numeric_fact_table"][0]["visible_exact"]), Fraction(1, 1000))
        self.assertEqual(result["sector_internal_checks"][0]["sector_code"], "60")

    def test_wrong_array_sector_pointer_rejected(self):
        ix = index()
        ix["fact_tables"][0]["rows"][0][2] = "/daily_mean_return/1"
        with self.assertRaisesRegex(ValueError, "wrong array sector"):
            n.market_facts(market(), ix)

    def test_wrong_code_keyed_baseline_pointer_rejected(self):
        ix = index()
        ix["fact_tables"][1]["rows"][0][2] = "/baseline_weights/15"
        with self.assertRaisesRegex(ValueError, "wrong baseline sector"):
            n.market_facts(market(), ix)

    def test_mismatched_matrix_order_and_dimensions_rejected(self):
        ix = index()
        ix["matrix_reference_table"]["shared"]["sector_order"] = list(reversed(n.CODES))
        with self.assertRaisesRegex(ValueError, "sector order differs"):
            n.market_facts(market(), ix)
        m = market()
        m["covariance"][0].pop()
        with self.assertRaisesRegex(ValueError, "Eleven by eleven"):
            n.market_arrays(m)

    def test_full_quadratic_includes_both_offdiagonal_terms(self):
        weights = {c: Fraction(1, 2) if c in ("10", "15") else Fraction() for c in n.CODES}
        result = n.portfolio_diagnostics(weights, market(), "synthetic")
        self.assertEqual(n.unratio(result["daily_quadratic_variance_exact"]), Fraction(3, 40000))
        self.assertEqual(n.unratio(result["weighted_visible_daily_mean_exact"]), Fraction(3, 2000))
        self.assertEqual(Decimal(result["annualized_sd_approx"]), n.square_root(Fraction(3, 10000)))
        self.assertIsNone(result["compounded_portfolio_return"])

    def test_raw_vs_derived_changes_and_benchmark_directions_can_reverse(self):
        prior = n.independent_allocation(raw(["0.2"] + ["0.08"] * 10))
        current = n.independent_allocation(raw(["0.21"] + ["0.1"] * 10))
        result = n.allocation_comparisons(current, prior, market())
        energy = result["sector_rows"][0]
        self.assertEqual(energy["own_D0_to_current"]["raw_change_direction"], "above")
        self.assertEqual(energy["own_D0_to_current"]["derived_change_direction"], "below")
        self.assertTrue(energy["benchmark_relations"]["supplied_serialized_baseline"]["direction_changed_by_external_math"])
        self.assertEqual(n.unratio(result["portfolio_diagnostics"][0]["weight_sum_exact"]), Fraction(121, 100))

    def test_reported_vs_normalized_benchmark_are_distinct(self):
        m = market()
        m["benchmark_reported_weights_percent"] = [Decimal("9")] * 11
        current = n.independent_allocation(raw(["0.0905"] + ["0.09095"] * 10))
        result = n.allocation_comparisons(current, None, m)
        relation = result["sector_rows"][0]["benchmark_relations"]
        self.assertEqual(relation["reported_benchmark_percent_div100"]["raw_direction"], "above")
        self.assertEqual(relation["exact_reported_sum_normalization"]["raw_direction"], "below")


class BundleAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.patch_root = patch.object(n, "ROOT", self.root)
        self.patch_root.start()
        self.case = n.CASES[0]
        self.run = self.root / "raw_run"
        self.directory = self.run / (self.case + "__D0")
        self.directory.mkdir(parents=True)
        self.reports = self.root / "reports"
        (self.reports / "allocation_math").mkdir(parents=True)
        self.bundle_path = self.reports / "bundle.json"
        self.math_path = self.reports / "allocation_math" / (self.case + "__D0.json")
        self.declaration_ref = self.write(self.run / "campaign_declaration.json", {"output_root": str(self.reports)})
        payload = {"common_market": market(), "public_numeric_fact_index": index()}
        # Preserve decimal JSON numbers, as the real prepared body does.
        content = json.dumps(payload, default=float)
        self.spec_ref = self.write(self.directory / "worker_spec.json", {"case_id": self.case, "stage": "D0", "body": {"messages": [{}, {"content": content}]}})
        self.response_ref = self.write(self.directory / "response.json", {"message": {"content": raw()}})
        self.transport_ref = self.write(self.directory / "transport_result.json", {"status": "completed", "response_artifact": self.response_ref})
        self.review_ref = self.write(self.directory / "stage_review.json", {"case_id": self.case, "stage": "D0"})
        self.math = sidecar()
        self.math.update(case_id=self.case, stage="D0", observed_transport_status="completed",
                         input_refs=[self.spec_ref, self.transport_ref, self.response_ref, self.review_ref])
        self.write(self.math_path, self.math)
        self.bundle = {"version": "completion_semantic_bundle_1", "purpose": "pilot_completion", "status": "prepared_for_semantic_reading",
                       "case_id": self.case, "stage": "D0", "observed_transport_status": "completed",
                       "raw_final_or_draft_text": raw(), "raw_response_content_sha256": hashlib.sha256(raw().encode()).hexdigest(),
                       "own_prior_text": None, "refs": [self.declaration_ref, self.spec_ref, self.transport_ref, self.response_ref, self.review_ref]}
        self.write(self.bundle_path, self.bundle)
        self.guard = patch.object(n, "rebuild_guarded_bundle", side_effect=lambda directory: copy.deepcopy(self.bundle))
        self.mock_guard = self.guard.start()

    def tearDown(self):
        self.guard.stop()
        self.patch_root.stop()
        self.tmp.cleanup()

    def write(self, path, value):
        data = (json.dumps(value) + "\n").encode()
        path.write_bytes(data)
        return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}

    def test_bound_numeric_report_without_prose_score(self):
        result = n.audit_bundle(self.bundle_path, self.math_path)
        self.assertTrue(result["accepted_sidecar_comparison"]["matches"])
        self.assertEqual(result["semantic_claims_graded"], 0)
        self.assertEqual(result["model_calls"], 0)
        self.assertIsNone(result["accepted_own_D0_sidecar_comparison"])

    def test_noncomplete_header_rejected_before_guard_or_model_text_use(self):
        self.bundle["observed_transport_status"] = "running"
        self.write(self.bundle_path, self.bundle)
        with self.assertRaisesRegex(ValueError, "Completed guarded"):
            n.audit_bundle(self.bundle_path, self.math_path)
        self.mock_guard.assert_not_called()

    def test_regenerated_guard_and_bundle_disagreement_rejected(self):
        changed = copy.deepcopy(self.bundle)
        changed["raw_final_or_draft_text"] = raw(["2"] * 11)
        self.write(self.bundle_path, changed)
        with self.assertRaisesRegex(ValueError, "freshly guarded"):
            n.audit_bundle(self.bundle_path, self.math_path)

    def test_stale_bound_artifact_rejected(self):
        self.write(self.directory / "stage_review.json", {"case_id": "foreign", "stage": "D0"})
        with self.assertRaisesRegex(ValueError, "reference changed"):
            n.audit_bundle(self.bundle_path, self.math_path)

    def test_crosscase_math_rejected(self):
        self.math["case_id"] = n.CASES[1]
        self.write(self.math_path, self.math)
        with self.assertRaisesRegex(ValueError, "case/stage/transport"):
            n.audit_bundle(self.bundle_path, self.math_path)

    def test_crossrun_math_path_rejected(self):
        foreign = self.root / "other_math.json"
        self.write(foreign, self.math)
        with self.assertRaisesRegex(ValueError, "declared report path"):
            n.audit_bundle(self.bundle_path, foreign)

    def test_math_must_bind_current_response_and_stage_review(self):
        self.math["input_refs"] = [self.spec_ref, self.transport_ref]
        self.write(self.math_path, self.math)
        with self.assertRaisesRegex(ValueError, "omits current stage"):
            n.audit_bundle(self.bundle_path, self.math_path)

    def test_raw_digest_rejected(self):
        self.bundle["raw_response_content_sha256"] = "0" * 64
        self.write(self.bundle_path, self.bundle)
        with self.assertRaisesRegex(ValueError, "Raw text digest"):
            n.audit_bundle(self.bundle_path, self.math_path)

    def configure_final(self):
        prior_spec = json.loads((self.directory / "worker_spec.json").read_text())
        final_dir = self.run / (self.case + "__F0")
        final_dir.mkdir()
        final_spec = {**prior_spec, "stage": "F0"}
        spec_ref = self.write(final_dir / "worker_spec.json", final_spec)
        response_ref = self.write(final_dir / "response.json", {"message": {"content": raw()}})
        transport_ref = self.write(final_dir / "transport_result.json", {"status": "completed", "response_artifact": response_ref})
        review_ref = self.write(final_dir / "stage_review.json", {"case_id": self.case, "stage": "F0"})
        final_math = {**sidecar(), "case_id": self.case, "stage": "F0", "observed_transport_status": "completed",
                      "input_refs": [spec_ref, transport_ref, response_ref, review_ref]}
        final_math_path = self.reports / "allocation_math" / (self.case + "__F0.json")
        self.write(final_math_path, final_math)
        self.bundle.update(stage="F0", own_prior_text=raw(), refs=self.bundle["refs"] + [spec_ref, transport_ref, response_ref, review_ref])
        self.write(self.bundle_path, self.bundle)
        return final_math_path

    def test_f0_own_d0_sidecar_and_deltas_are_separately_checked(self):
        final_math = self.configure_final()
        result = n.audit_bundle(self.bundle_path, final_math)
        self.assertTrue(result["accepted_own_D0_sidecar_comparison"]["matches"])
        self.assertTrue(result["accepted_sidecar_comparison"]["matches"])
        self.assertTrue(all(row["own_D0_to_current"]["raw_change_direction"] == "equal"
                            and row["own_D0_to_current"]["derived_change_direction"] == "equal"
                            for row in result["raw_and_derived_relations"]["sector_rows"]))

    def test_f0_prior_numeric_mismatch_retained_without_repairing_or_rejecting_current(self):
        final_math = self.configure_final()
        self.math["rows"][0]["final_units"] = 909
        self.write(self.math_path, self.math)
        result = n.audit_bundle(self.bundle_path, final_math)
        self.assertFalse(result["accepted_own_D0_sidecar_comparison"]["matches"])
        self.assertTrue(result["accepted_sidecar_comparison"]["matches"])

    def test_f0_prior_sidecar_must_bind_own_prior_spec(self):
        final_math = self.configure_final()
        self.math["input_refs"] = [self.transport_ref, self.response_ref, self.review_ref]
        self.write(self.math_path, self.math)
        with self.assertRaisesRegex(ValueError, "omits current stage"):
            n.audit_bundle(self.bundle_path, final_math)


if __name__ == "__main__":
    unittest.main(verbosity=2)
