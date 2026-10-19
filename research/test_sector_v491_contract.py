"""Adversarial offline contract checks; no actual model generation."""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import sector_v491_contract as contract


def object_schema(fields):
    return {"type": "object", "properties": fields, "required": list(fields), "additionalProperties": False}


def fixture_schema():
    text = {"type": "string", "minLength": 1}
    ids = {"type": "array", "items": text}
    row = object_schema({
        "sector_code": {"type": "string", "enum": list(contract.SECTOR_CODES)},
        "source_label": {"type": ["string", "null"]}, "source_reading": text,
        "source_evidence_ids": ids,
        "source_stance": {"type": "string", "enum": ["adopt", "qualify", "depart", "undetermined", "not_available"]},
        "weight": {"type": "number"}, "decision_reason": text, "decision_evidence_ids": ids})
    constraint = object_schema({"constraint_id": text, "sector_code": {"enum": list(contract.SECTOR_CODES)},
                                "kind": {"enum": ["sector_min_weight", "sector_max_weight"]},
                                "bound": {"type": "number"}, "evidence_ids": ids})
    return object_schema({
        "source_id": {"type": ["string", "null"]},
        "sectors": {"type": "array", "items": row, "minItems": 11, "maxItems": 11},
        "context_assessment": object_schema({"market_and_mandate_reading": text,
                                              "allocation_implication": text, "evidence_ids": ids,
                                              "limitations": text}),
        "alternatives": text, "risk_discussion": text, "unresolved": ids,
        "submitted_constraints": {"type": "array", "items": constraint}})


def fixture_packet(source="source_a"):
    return {"source_id": source, "rating_vocabulary": ["Neutral", "Overweight", "Underweight"],
            "evidence_table": {"shared": {"source_id": source},
                               "columns": ["evidence_id", "text"],
                               "rows": [[source + ":sector:" + c, "Synthetic public Neutral judgment."]
                                        for c in contract.SECTOR_CODES]}}


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.schema = fixture_schema()
        self.packet = fixture_packet()
        self.other = fixture_packet("source_b")
        self.market = {"sector_codes": list(contract.SECTOR_CODES),
                       "baseline_id": "synthetic_common_comparator",
                       "baseline_weights": {c: 1 / 11 for c in contract.SECTOR_CODES},
                       "covariance": [[0.0001 if i == j else 0 for j in range(11)] for i in range(11)],
                       "covariance_unit": "daily_decimal_return_squared",
                       "lookback_return_dates": ["2026-04-21", "2026-07-16"]}
        self.index = {"fact_tables": [{"shared": {"unit": "decimal_weight"},
                                      "columns": ["fact_id", "common_market_json_pointer"],
                                      "rows": [["M:baseline:" + c, "/baseline_weights/" + c]
                                               for c in contract.SECTOR_CODES]}]}
        self.context = {"protocol_version": "4.9.1", "operating_brief": {
            "evidence_items": [{"evidence_id": "B:task", "statement": "Synthetic new-money allocation."}]},
            "market_context": {"facts": [{"evidence_id": "X:inflation", "value": 2.5, "unit": "percent",
                                            "publication_date": "2026-07-14"}]}}
        self.prompt = {"system": "Synthetic fixed public-data research task.",
                       "D0_instruction": "Prepare a provisional allocation.",
                       "F0_instruction": "Review the actual draft and assigned source; return first final."}
        self.visible = contract.evidence_ids(self.context) | contract.evidence_ids(self.index)

    def response(self, source=True):
        return {"source_id": self.packet["source_id"] if source else None,
                "sectors": [{"sector_code": c, "source_label": "Neutral" if source else None,
                             "source_reading": "Synthetic public meaning." if source else "No institution evidence supplied.",
                             "source_evidence_ids": [self.packet["source_id"] + ":sector:" + c] if source else [],
                             "source_stance": "adopt" if source else "not_available", "weight": 1 / 11,
                             "decision_reason": "Synthetic illustrative choice, not an empirical finding.",
                             "decision_evidence_ids": ["M:baseline:" + c, "X:inflation"]}
                            for c in contract.SECTOR_CODES],
                "context_assessment": {"market_and_mandate_reading": "Synthetic task assessment.",
                                        "allocation_implication": "Synthetic implication.",
                                        "evidence_ids": ["B:task", "X:inflation"],
                                        "limitations": "Synthetic fixture only."},
                "alternatives": "Synthetic alternative.", "risk_discussion": "Historical variability is not future loss.",
                "unresolved": [], "submitted_constraints": []}

    def messages(self, arm="E", packet=None):
        return contract.build_draft_messages(arm=arm, assigned_packet=packet or self.packet,
                                              common_market=self.market, public_numeric_fact_index=self.index,
                                              common_context=self.context, prompt_contract=self.prompt,
                                              response_schema=self.schema)

    def check_response(self, obj, source=True):
        return contract.validate_response(contract.canonical_json(obj), response_schema=self.schema,
                                          expected_source_packet=self.packet if source else None,
                                          visible_evidence_ids=self.visible | (contract.evidence_ids(self.packet) if source else set()))

    def final(self, arm="E", obj=None):
        return contract.build_final_messages(draft_messages=self.messages(arm),
                                              raw_draft=contract.canonical_json(obj or self.response(arm == "E")),
                                              assigned_packet=self.packet, prompt_contract=self.prompt,
                                              response_schema=self.schema)

    def test_common_context_exactly_equal_across_all_four_cases(self):
        inputs = [json.loads(self.messages(arm, packet)[1]["content"])
                  for arm in ("E", "L") for packet in (self.packet, self.other)]
        for key in ("common_context", "common_market", "public_numeric_fact_index", "response_schema", "task"):
            self.assertTrue(all(x[key] == inputs[0][key] for x in inputs))

    def test_real_compact_source_bundle_all_sources_and_fully_shared_tables(self):
        path = Path(__file__).resolve().parents[1] / "data/sector_protocol/v49_design_20261019/public_compact_candidate.json"
        candidate = json.loads(path.read_text(encoding="utf-8"))
        late_messages = []
        for source_id in candidate["public_source_packets"]:
            for arm in ("E", "L"):
                messages = contract.build_draft_messages(
                    arm=arm, **contract.select_public_inputs(candidate, source_id),
                    common_context=self.context, prompt_contract=self.prompt, response_schema=self.schema)
                self.assertEqual(len(messages), 2)
                if arm == "L":
                    late_messages.append(messages)
        self.assertEqual(len(late_messages), 4)
        self.assertTrue(all(messages == late_messages[0] for messages in late_messages))

    def real_v491_inputs(self):
        root = Path(__file__).resolve().parents[1]
        def read(relative):
            return json.loads((root / relative).read_text(encoding="utf-8"))
        candidate = read("data/sector_protocol/v491_design_20261019/public_compact_candidate.json")
        context = read("data/sector_context/v491_20261019/common_context.json")
        prompt = read("data/sector_protocol/v491_design_20261019/prompt_contract.json")
        schema = read("data/sector_protocol/v491_design_20261019/response_schema.json")
        return candidate, context, prompt, schema

    def test_real_v491_macro_fact_table_and_common_brief_are_visible_in_all_cases(self):
        candidate, context, prompt, schema = self.real_v491_inputs()
        ids = contract.evidence_ids(context)
        self.assertIn("CTX:horizon", ids)
        self.assertIn("MACRO_FED_TARGET_20260617", ids)
        self.assertIn("CTX:liquidity_and_ESG", ids)
        self.assertEqual(len(ids), 17)
        self.assertEqual(context, candidate["common_context"])
        common_hashes = []
        for source_id in candidate["public_source_packets"]:
            for arm in ("E", "L"):
                messages = contract.build_draft_messages(arm=arm,
                    **contract.select_public_inputs(candidate, source_id), common_context=context,
                    prompt_contract=prompt, response_schema=schema)
                payload = contract.strict_json(messages[1]["content"])
                common_hashes.append(hashlib.sha256(contract.canonical_json(payload["common_context"]).encode("utf-8")).hexdigest())
                self.assertEqual(contract.evidence_ids(payload["common_context"]), ids)
                self.assertEqual(payload["common_context"]["operating_brief"]["existing_sector_holdings"], None)
        self.assertEqual(len(set(common_hashes)), 1)

    def test_real_v491_F0_with_explicitly_synthetic_raw_draft_preserves_error(self):
        candidate, context, prompt, schema = self.real_v491_inputs()
        # This in-memory response is a test fixture, not a model or source result.
        # No synthetic response or final request is saved by the preparation CLI.
        for source_id in candidate["public_source_packets"]:
            selected = contract.select_public_inputs(candidate, source_id)
            packet = selected["assigned_packet"]
            source_evidence = sorted(contract.evidence_ids(packet))
            for arm in ("E", "L"):
                obj = self.response(arm == "E")
                obj["source_id"] = source_id if arm == "E" else None
                obj["context_assessment"] = {
                    "market_and_mandate_reading": "SYNTHETIC TEST FIXTURE ONLY: read common task.",
                    "allocation_implication": "SYNTHETIC TEST FIXTURE ONLY: deliberately invalid sum.",
                    "evidence_ids": ["CTX:task", "MACRO_FED_TARGET_20260617"],
                    "limitations": "SYNTHETIC TEST FIXTURE ONLY; no economic inference or model output."}
                for row in obj["sectors"]:
                    row["weight"] = 0.1
                    row["decision_evidence_ids"] = ["M:baseline_weights:" + row["sector_code"]]
                    row["source_reading"] = "SYNTHETIC TEST FIXTURE ONLY; not a source interpretation."
                    row["decision_reason"] = "SYNTHETIC TEST FIXTURE ONLY; deliberate raw sum failure."
                    row["source_label"] = packet["rating_vocabulary"][0] if arm == "E" else None
                    row["source_evidence_ids"] = [source_evidence[0]] if arm == "E" else []
                raw = "\n" + json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
                messages = contract.build_draft_messages(arm=arm, **selected, common_context=context,
                                                          prompt_contract=prompt, response_schema=schema)
                result = contract.build_final_messages(draft_messages=messages, raw_draft=raw,
                                                        assigned_packet=packet, prompt_contract=prompt,
                                                        response_schema=schema)
                self.assertTrue(result["ready"])
                self.assertTrue(result["draft_validation"]["schema_valid"])
                self.assertTrue(result["draft_validation"]["visibility_valid"])
                self.assertFalse(result["draft_feedback"]["allocation"]["valid"])
                self.assertAlmostEqual(result["draft_feedback"]["allocation"]["raw_sum"], 1.1)
                self.assertEqual(result["messages"][2]["content"], raw)
                self.assertEqual(result["messages"][:2], messages)
                self.assertFalse(result["draft_feedback"]["repaired"])
                self.assertEqual(result["model_calls"], 0)

    def test_real_v491_preparer_writes_only_eight_D0_requests_and_external_manifest(self):
        import prepare_sector_v491 as preparer
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="v491_contract_test_", dir=root / "tmp") as directory:
            manifest = preparer.prepare(output_dir=directory)
            self.assertEqual(manifest["counts"], {"pilot_D0": 4, "main_D0": 4, "prepared_D0": 8, "prepared_F0": 0})
            self.assertTrue(all(manifest["checks"].values()))
            self.assertEqual(manifest["model_calls"], 0)
            self.assertEqual(len(list(Path(directory).rglob("*.json"))), 9)
            for case in manifest["prepared_cases"]:
                raw = (root / case["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), case["sha256"])
                messages = json.loads(raw)
                self.assertEqual([m["role"] for m in messages], ["system", "user"])
                payload = json.loads(messages[1]["content"])
                self.assertNotIn("case_id", payload)
                self.assertNotIn("arm", payload)
                self.assertEqual(payload["stage"], "D0")

    def test_l_draft_excludes_source_identity_and_assignment_metadata(self):
        a, b = self.messages("L"), self.messages("L", self.other)
        self.assertEqual(a, b)
        serialized = contract.canonical_json(a)
        for forbidden in ("source_a", "source_b", "institution_document", "case_id", '"arm"'):
            self.assertNotIn(forbidden, serialized)

    def test_select_allowlist_excludes_other_packets_and_evaluator_metadata(self):
        bundle = {"common_market": self.market, "public_numeric_fact_index": self.index,
                  "public_source_packets": {"source_a": self.packet, "source_b": self.other},
                  "evaluator_only": {"secret": "do not send"}}
        selected = contract.select_public_inputs(bundle, "source_a")
        self.assertEqual(set(selected), {"common_market", "public_numeric_fact_index", "assigned_packet"})
        self.assertNotIn("source_b", contract.canonical_json(selected))
        self.assertNotIn("secret", contract.canonical_json(selected))

    def test_common_input_rejects_aggregate_injection(self):
        self.context["market_context"]["public_source_packets"] = {"source_b": self.other}
        with self.assertRaises(ValueError):
            self.messages("L")

    def test_market_fact_pointer_must_resolve(self):
        self.index["fact_tables"][0]["rows"][0][1] = "/missing"
        with self.assertRaises(ValueError):
            self.messages()

    def test_duplicate_market_fact_id_rejected(self):
        self.index["fact_tables"][0]["rows"][1][0] = self.index["fact_tables"][0]["rows"][0][0]
        with self.assertRaises(ValueError):
            self.messages()

    def test_source_passage_cannot_impersonate_another_source(self):
        self.packet["evidence_table"]["shared"]["source_id"] = "source_b"
        with self.assertRaises(ValueError):
            self.messages()

    def test_source_vocabulary_and_common_instructions_required(self):
        self.packet["rating_vocabulary"] = []
        with self.assertRaises(ValueError):
            self.messages()
        self.packet = fixture_packet()
        self.prompt["system"] = " "
        with self.assertRaises(ValueError):
            self.messages()

    def test_valid_schema_context_and_weights(self):
        result = self.check_response(self.response())
        for key in ("parse_valid", "schema_valid", "complete_vector", "structural_valid", "visibility_valid", "contract_valid", "continuation_eligible"):
            self.assertTrue(result[key], key)
        self.assertTrue(result["arithmetic"]["valid"])

    def test_duplicate_sector_blocks_continuation(self):
        obj = self.response()
        obj["sectors"][1]["sector_code"] = obj["sectors"][0]["sector_code"]
        result = self.check_response(obj)
        self.assertTrue(result["schema_valid"])
        self.assertFalse(result["complete_vector"])
        self.assertFalse(result["continuation_eligible"])
        self.assertFalse(self.final(obj=obj)["ready"])

    def test_schema_missing_context_blocks_continuation(self):
        obj = self.response()
        del obj["context_assessment"]
        self.assertFalse(self.check_response(obj)["schema_valid"])
        self.assertFalse(self.final(obj=obj)["ready"])

    def test_bool_weight_rejected(self):
        obj = self.response()
        obj["sectors"][0]["weight"] = True
        self.assertFalse(self.check_response(obj)["schema_valid"])

    def test_nonfinite_duplicate_key_and_fenced_json_rejected(self):
        raw = contract.canonical_json(self.response())
        for invalid in (raw.replace('"weight":0.09090909090909091', '"weight":NaN', 1),
                        raw.replace('"weight":0.09090909090909091', '"weight":1e400', 1),
                        '{"x":1,"x":2}', "```json\n" + raw + "\n```"):
            result = contract.validate_response(invalid, response_schema=self.schema,
                                                 visible_evidence_ids=self.visible)
            self.assertFalse(result["parse_valid"])

    def test_wrong_source_is_recorded_without_censoring_final(self):
        obj = self.response()
        obj["source_id"] = "source_b"
        result = self.check_response(obj)
        self.assertFalse(result["visibility_valid"])
        self.assertTrue(result["continuation_eligible"])
        self.assertTrue(self.final(obj=obj)["ready"])

    def test_wrong_label_is_outcome_not_structural_gate(self):
        obj = self.response()
        obj["sectors"][0]["source_label"] = "Attractive"
        result = self.check_response(obj)
        self.assertTrue(result["continuation_eligible"])
        self.assertEqual(result["source_label_diagnostics"][0]["kind"], "outside_source_vocabulary")

    def test_same_vocabulary_wrong_meaning_requires_review(self):
        obj = self.response()
        obj["sectors"][0]["source_label"] = "Overweight"
        result = self.check_response(obj)
        self.assertTrue(result["contract_valid"])
        self.assertEqual(result["source_label_diagnostics"], [])
        self.assertIn("independent_review", result["semantic_support"])

    def test_hidden_source_or_future_calculator_citation_is_logged(self):
        for hidden in ("source_b:sector:10", "C:F0:sum", "unpublished:gold"):
            obj = self.response()
            obj["context_assessment"]["evidence_ids"].append(hidden)
            result = self.check_response(obj)
            self.assertFalse(result["visibility_valid"])
            self.assertTrue(result["continuation_eligible"])

    def test_source_citation_cannot_use_market_fact_as_source(self):
        obj = self.response()
        obj["sectors"][0]["source_evidence_ids"] = ["M:baseline:10"]
        result = self.check_response(obj)
        self.assertFalse(result["visibility_valid"])
        self.assertEqual(result["visibility_errors"][0]["kind"], "not_assigned_source_evidence")

    def test_l_source_attribution_is_not_available(self):
        obj = self.response(False)
        obj["sectors"][0]["source_label"] = "Neutral"
        self.assertFalse(self.check_response(obj, False)["visibility_valid"])
        self.assertTrue(self.check_response(self.response(False), False)["visibility_valid"])

    def test_sum_failure_preserved_and_final_still_available(self):
        obj = self.response()
        for row in obj["sectors"]:
            row["weight"] = 0.1
        before = copy.deepcopy(obj)
        result = self.final(obj=obj)
        self.assertTrue(result["ready"])
        self.assertFalse(result["draft_feedback"]["allocation"]["valid"])
        self.assertAlmostEqual(result["draft_feedback"]["allocation"]["raw_sum"], 1.1)
        self.assertAlmostEqual(result["draft_feedback"]["allocation"]["raw_budget_residual"], 0.1)
        self.assertIsNone(result["draft_feedback"]["valid_portfolio_historical_risk"])
        self.assertFalse(result["draft_feedback"]["repaired"])
        self.assertEqual(obj, before)
        self.assertEqual(json.loads(result["messages"][2]["content"]), before)

    def test_negative_raw_weight_preserved(self):
        obj = self.response()
        obj["sectors"][0]["weight"] = -0.1
        result = self.final(obj=obj)
        self.assertTrue(result["ready"])
        self.assertEqual(result["draft_feedback"]["allocation"]["negative_weight_codes"], ["10"])
        self.assertEqual(json.loads(result["messages"][2]["content"])["sectors"][0]["weight"], -0.1)

    def test_final_preserves_exact_messages_and_draft_whitespace(self):
        messages = self.messages()
        raw = "\n " + json.dumps(self.response(), indent=3) + " \n"
        result = contract.build_final_messages(draft_messages=messages, raw_draft=raw,
                                               assigned_packet=self.packet, prompt_contract=self.prompt,
                                               response_schema=self.schema)
        self.assertEqual(result["messages"][:2], messages)
        self.assertEqual(result["messages"][2], {"role": "assistant", "content": raw})
        self.assertEqual(len(result["messages"]), 4)
        self.assertEqual(result["model_calls"], 0)

    def test_final_source_refresh_bytes_and_position_identical_across_arms(self):
        e = json.loads(self.final("E")["messages"][-1]["content"])
        l = json.loads(self.final("L")["messages"][-1]["content"])
        self.assertEqual(list(e), list(l))
        self.assertEqual(list(e), ["stage", "task", "actual_draft_calculator_feedback", "institution_document"])
        self.assertEqual(contract.canonical_json(e["institution_document"]), contract.canonical_json(l["institution_document"]))
        self.assertEqual(e["task"], l["task"])

    def test_final_refuses_source_switch_for_early_arm(self):
        with self.assertRaises(ValueError):
            contract.build_final_messages(draft_messages=self.messages(), raw_draft=contract.canonical_json(self.response()),
                                           assigned_packet=self.other, prompt_contract=self.prompt,
                                           response_schema=self.schema)

    def test_final_cannot_accept_fabricated_feedback_input(self):
        messages = self.messages()
        payload = json.loads(messages[1]["content"])
        payload["actual_draft_calculator_feedback"] = {"valid": True}
        messages[1]["content"] = contract.canonical_json(payload)
        with self.assertRaises(ValueError):
            contract.build_final_messages(draft_messages=messages, raw_draft=contract.canonical_json(self.response()),
                                           assigned_packet=self.packet, prompt_contract=self.prompt,
                                           response_schema=self.schema)

    def test_calculator_ids_exist_only_after_actual_draft_calculation(self):
        result = self.final("L")
        self.assertNotIn("C:D0:sum", contract.canonical_json(self.messages("L")))
        self.assertIn("C:D0:sum", result["visible_evidence_ids_for_final"])
        self.assertNotIn("C:F0:sum", result["visible_evidence_ids_for_final"])
        final_obj = self.response()
        final_obj["context_assessment"]["evidence_ids"].append("C:D0:sum")
        validation = contract.validate_response(contract.canonical_json(final_obj), response_schema=self.schema,
                                                 expected_source_packet=self.packet,
                                                 visible_evidence_ids=result["visible_evidence_ids_for_final"])
        self.assertTrue(validation["visibility_valid"])

    def test_actual_feedback_binds_raw_vector_and_market_hash(self):
        first = self.final()["draft_feedback"]
        obj = self.response()
        obj["sectors"][0]["weight"] += 0.01
        second = self.final(obj=obj)["draft_feedback"]
        self.assertNotEqual(first["lineage"]["submitted_vector_sha256"], second["lineage"]["submitted_vector_sha256"])
        self.assertEqual(first["lineage"]["market_values_sha256"], second["lineage"]["market_values_sha256"])
        self.assertFalse(first["gold_access"])

    def test_no_post_final_repair_endpoint(self):
        with self.assertRaises(ValueError):
            contract.evaluate_submission(self.response(), market=self.market,
                                          visible_evidence_ids=self.visible, endpoint_id="F1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
