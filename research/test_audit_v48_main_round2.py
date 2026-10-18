"""Synthetic main-only accounting/tamper tests; no model, OS power or HTTP call."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import audit_v48_main_round2 as audit
from sector_v48_contract import evaluate_proposal
from sector_response_schema import validate_response
from test_sector_v48_main_offline import MainFixture, save


class AuditFixture(MainFixture):
    def __init__(self, root):
        super().__init__(root)
        self.market = audit.read(self.prepared / "market_input.json")
        self.market.update(sector_codes=list(audit.CODES), covariance_unit="daily_decimal_return_squared",
            lookback_return_dates=["2026-01-01", "2026-03-31"],
            covariance=[[.0001 if i == j else 0 for j in range(11)] for i in range(11)])
        save(self.prepared / "market_input.json", self.market)
        self.registry = audit.read(self.prepared / "public_numeric_registry.json")
        self.registry["source"]["sha256"] = audit.ref(self.prepared / "market_input.json")["sha256"]
        save(self.prepared / "public_numeric_registry.json", self.registry)
        self.manifest["files"].update({name: audit.ref(self.prepared / name)["sha256"]
            for name in ("market_input.json", "public_numeric_registry.json")})
        self.pin_manifest()
        self.case_endpoints = {}

    def populate(self, case, *, total=1, repair=False, bad_contract=False):
        ids, facts, previous = ["M:vol:10"], [], None
        endpoints = list(audit.CORE) + (["C1"] if repair else [])
        for endpoint in endpoints:
            stage = int(endpoint[-1]) if endpoint.startswith("stage") else 4
            visible = case["arm"] == "R1" or stage == 4
            if visible:
                ids = sorted(set(ids) | set(self.values[case["source_id"]][2]["evidence_index"]))
            proposal = copy.deepcopy(self.values[case["source_id"]][0])
            if not visible:
                proposal.update(source_id=None, interpretations=[])
                for row in proposal["weights"]:
                    row["evidence_ids"] = ["M:vol:10"]
            if stage < 3:
                proposal["weights"] = []
            elif endpoint == "C0":
                proposal["weights"][0]["weight"] = total
                if bad_contract:
                    proposal.pop("alternatives")
            raw = json.dumps(proposal)
            folder, record = self.endpoint(case, endpoint, raw=raw)
            feedback = evaluate_proposal(proposal, stage, self.market, ids, endpoint, previous)
            record.update(parsed_response=proposal, feedback=feedback,
                schema_validation=validate_response(raw, stage, case["source_id"] if visible else None, visible),
                visible_evidence_ids_before_generation=list(ids),
                visible_calculator_facts_before_generation=copy.deepcopy(facts))
            if bad_contract and endpoint == "C0":
                record["transport_status"] = "model_contract_failure"
            save(folder / "record.json", record)
            save(folder / "visible_evidence_before_generation.json", {"ids": ids, "calculator_facts": facts})
            facts.extend(copy.deepcopy(feedback["facts"]))
            ids = sorted(set(ids) | {f["fact_id"] for f in feedback["facts"]})
            previous = copy.deepcopy(proposal["weights"])
        self.case_endpoints[case["case_id"]] = endpoints
        self.case_summary(case, endpoints)

    def report(self):
        report, worksheet = self.load()
        path = self.root / "synthetic_evaluation.json"
        save(path, report)
        return path, report

    def audit(self):
        path, _ = self.report()
        return audit.build_audit(self.manifest_path, self.run, path)

    def refresh(self, case):
        self.case_summary(case, self.case_endpoints[case["case_id"]])


class MainRound2Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="libera_main_round2_synthetic_")
        self.addCleanup(temp.cleanup)
        self.f = AuditFixture(Path(temp.name))

    def passed(self, report):
        self.assertEqual(report["status"], "PASS", [c["id"] for c in report["checks"] if not c["passed"]])

    def failed(self, report, fragment):
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any(fragment in c["id"] and not c["passed"] for c in report["checks"]))

    def test_all_unreached_preserve_four_44_and_no_strategy_verdict(self):
        report = self.f.audit()
        self.passed(report)
        self.assertEqual(report["expected_sector_count"], 44)
        self.assertEqual(report["observed_main_generation_calls"], 0)
        self.assertFalse(report["execution_gate_certified_by_this_audit"])

    def test_invalid_C0_and_valid_aux_are_separate_and_not_zero_main_calls(self):
        self.f.populate(audit.ROSTER[0], total=1.035, repair=True)
        report = self.f.audit()
        self.passed(report)
        self.assertEqual(report["observed_main_generation_calls"], 5)
        self.assertEqual(report["main_model_calls_by_audit"], 0)
        self.assertEqual(report["case_numerics"][0]["decimal_raw_sum"], "1.035")
        self.assertEqual(report["model_arithmetic_outcome"]["valid_C0_count"], 0)

    def test_four_valid_raw_C0_and_covariance_pairs(self):
        for case in audit.ROSTER:
            self.f.populate(case)
        report = self.f.audit()
        self.passed(report)
        self.assertEqual(report["model_arithmetic_outcome"]["valid_C0_count"], 4)
        self.assertEqual(report["observed_main_generation_calls"], 16)

    def test_unrelated_bad_contract_does_not_erase_valid_vector(self):
        self.f.populate(audit.ROSTER[0], bad_contract=True)
        report = self.f.audit()
        self.passed(report)
        self.assertTrue(report["case_numerics"][0]["C0_valid_raw_allocation"])
        self.assertFalse(report["case_numerics"][0]["C0_schema_valid"])

    def test_main_count_candidate_zero_cannot_replace_observed_requests(self):
        self.f.populate(audit.ROSTER[0])
        path, report = self.f.report()
        report["observed_main_generation_calls"] = 0
        save(path, report)
        self.failed(audit.build_audit(self.f.manifest_path, self.f.run, path), "main_evaluation_observed_total")

    def test_frozen_evaluator_material_tamper_is_detected_offline(self):
        path, report = self.f.report()
        material = Path(self.f.manifest["evaluator_material_refs"]["review_template"]["path"])
        save(material, {"changed_after_candidate": True})
        self.failed(audit.build_audit(self.f.manifest_path, self.f.run, path), "evaluator_material_frozen_bytes:review_template")

    def test_evaluation_cannot_substitute_material_provenance(self):
        path, report = self.f.report()
        report["provenance"]["evaluator_material_refs"]["review_template"]["sha256"] = "1" * 64
        save(path, report)
        self.failed(audit.build_audit(self.f.manifest_path, self.f.run, path), "evaluation_uses_prebound_evaluator_materials")

    def test_fact_numeric_tamper_detected_despite_untouched_raw_sum(self):
        case = audit.ROSTER[0]
        self.f.populate(case, total=1.035)
        path = self.f.run / case["case_id"] / "C0/record.json"
        record = audit.read(path)
        next(f for f in record["feedback"]["facts"] if f["fact_id"] == "C:C0:sum")["value"] = 1
        save(path, record)
        self.f.refresh(case)
        self.failed(self.f.audit(), "fact_value")

    def test_duplicate_aux_or_aux_substitution_rejected(self):
        self.f.populate(audit.ROSTER[0], total=1.035, repair=True)
        path, report = self.f.report()
        report["auxiliary_endpoint_cases"].append(copy.deepcopy(report["auxiliary_endpoint_cases"][0]))
        save(path, report)
        self.failed(audit.build_audit(self.f.manifest_path, self.f.run, path), "auxiliary_exact_unique_inventory")

    def test_candidate_execution_flags_cannot_be_forged_as_permission(self):
        self.f.manifest["main_authorized"] = True
        self.f.pin_manifest()
        with self.assertRaises(ValueError):
            self.f.report()

    def test_pilot_globals_and_auditor_are_unchanged(self):
        import audit_v48_pilot_round2 as pilot
        self.assertEqual(pilot.SOURCES, ("fidelity_q2_2026", "ubs_june_2026"))
        self.assertEqual(audit.SOURCES, ("fidelity_q3_2026", "ubs_july_2026"))
        self.assertEqual(audit.ref(Path(pilot.__file__))["sha256"], "a82630dfac7344f9b77cdaa018e741d0c833bb4c75375fb386c9814035d816a2")


if __name__ == "__main__":
    unittest.main(verbosity=2)
