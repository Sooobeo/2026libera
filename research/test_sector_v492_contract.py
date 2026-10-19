"""Offline adversarial tests for source-free C; no real model responses/calls."""
from __future__ import annotations

import copy
import json
import unittest

import sector_v492_contract as contract
import test_sector_v491_contract as prior_fixtures


class Contract492Tests(unittest.TestCase):
    def setUp(self):
        fixture = prior_fixtures.ContractTests()
        fixture.setUp()
        self.fixture = fixture
        self.schema = fixture.schema
        self.packet = fixture.packet
        self.other = fixture.other
        self.market = fixture.market
        self.index = fixture.index
        self.context = fixture.context
        self.visible = fixture.visible
        self.prompt = {
            "system": "Synthetic fixed public-data research task.",
            "D0_instruction": "Prepare a provisional allocation.",
            "F0_instruction": "Review your actual draft and feedback. If an institutional document is supplied, interpret it; otherwise state that no institutional document was supplied.",
        }

    def draft(self, arm="C", packet=None):
        return contract.build_draft_messages(
            arm=arm, assigned_packet=None if arm == "C" else (packet or self.packet),
            common_market=self.market, public_numeric_fact_index=self.index,
            common_context=self.context, prompt_contract=self.prompt,
            response_schema=self.schema,
        )

    def final(self, arm="C", obj=None, raw=None):
        if obj is None:
            obj = self.fixture.response(arm == "E")
        if raw is None:
            raw = contract.canonical_json(obj)
        return contract.build_final_messages(
            draft_messages=self.draft(arm), raw_draft=raw,
            assigned_packet=None if arm == "C" else self.packet,
            prompt_contract=self.prompt, response_schema=self.schema,
        )

    def test_C_D0_is_byte_identical_to_both_source_L_D0(self):
        c = contract.canonical_json(self.draft("C"))
        self.assertEqual(c, contract.canonical_json(self.draft("L")))
        self.assertEqual(c, contract.canonical_json(self.draft("L", self.other)))
        self.assertNotIn("source_a", c)
        self.assertNotIn("source_b", c)
        self.assertNotIn("institution_document", c)

    def test_C_cannot_receive_packet_and_E_L_require_one(self):
        arguments = dict(common_market=self.market, public_numeric_fact_index=self.index,
                         common_context=self.context, prompt_contract=self.prompt,
                         response_schema=self.schema)
        with self.assertRaises(ValueError):
            contract.build_draft_messages(arm="C", assigned_packet=self.packet, **arguments)
        for arm in ("E", "L"):
            with self.assertRaises(ValueError):
                contract.build_draft_messages(arm=arm, assigned_packet=None, **arguments)

    def test_C_has_same_four_message_two_turn_structure_and_no_source(self):
        result = self.final()
        self.assertTrue(result["ready"])
        self.assertEqual([m["role"] for m in result["messages"]],
                         ["system", "user", "assistant", "user"])
        self.assertIsNone(result["source_packet_sha256"])
        self.assertEqual(result["model_calls"], 0)
        for i in (1, 3):
            self.assertNotIn("institution_document", json.loads(result["messages"][i]["content"]))
        self.assertTrue(set(result["visible_evidence_ids_for_final"]).isdisjoint(
            contract.evidence_ids(self.packet)))

    def test_same_conditional_F0_task_and_feedback_shape_all_arms(self):
        payloads = [json.loads(self.final(arm)["messages"][3]["content"]) for arm in ("E", "L", "C")]
        self.assertTrue(all(p["task"] == self.prompt["F0_instruction"] for p in payloads))
        self.assertEqual(set(payloads[0]), set(payloads[1]))
        self.assertEqual(set(payloads[0]) - {"institution_document"}, set(payloads[2]))
        self.assertTrue(all(p["actual_draft_calculator_feedback"]["lineage"]["contract_version"]
                            == contract.CONTRACT_VERSION for p in payloads))

    def test_all_five_D0_common_inputs_and_schema_equal(self):
        messages = [self.draft(arm, packet) for packet in (self.packet, self.other)
                    for arm in ("E", "L")] + [self.draft("C")]
        payloads = [json.loads(m[1]["content"]) for m in messages]
        for key in ("task", "common_context", "common_market", "public_numeric_fact_index", "response_schema"):
            self.assertTrue(all(contract.canonical_json(p[key]) == contract.canonical_json(payloads[0][key])
                                for p in payloads))
        self.assertTrue(all(m[0] == messages[0][0] for m in messages))

    def test_C_preserves_entire_own_raw_D0_whitespace_and_invalid_sum(self):
        obj = self.fixture.response(False)
        for row in obj["sectors"]:
            row["weight"] = 0.1
        raw = "\r\n " + json.dumps(obj, indent=2) + " \r\n"
        original = self.draft("C")
        result = self.final(raw=raw)
        self.assertTrue(result["ready"])
        self.assertEqual(result["messages"][:2], original)
        self.assertEqual(result["messages"][2]["content"], raw)
        self.assertFalse(result["draft_feedback"]["allocation"]["valid"])
        self.assertAlmostEqual(result["draft_feedback"]["allocation"]["raw_sum"], 1.1)
        self.assertFalse(result["draft_feedback"]["repaired"])

    def test_C_hallucinated_source_is_measured_not_censored_or_supplied_as_fact(self):
        obj = self.fixture.response(True)
        result = self.final(obj=obj)
        self.assertTrue(result["ready"])
        self.assertFalse(result["draft_validation"]["visibility_valid"])
        self.assertEqual(result["messages"][2]["content"], contract.canonical_json(obj))
        payload = json.loads(result["messages"][3]["content"])
        self.assertNotIn("institution_document", payload)
        self.assertTrue(all(not i.startswith("source_a:") for i in result["visible_evidence_ids_for_final"]))

    def test_C_malformed_draft_stops_without_constructing_F0(self):
        for raw in ("not JSON", "{}", contract.canonical_json({**self.fixture.response(False), "sectors": []})):
            result = self.final(raw=raw)
            self.assertFalse(result["ready"])
            self.assertIsNone(result["messages"])
            self.assertEqual(result["model_calls"], 0)

    def test_C_final_cannot_discard_an_early_source_packet(self):
        with self.assertRaisesRegex(ValueError, "cannot remove"):
            contract.build_final_messages(draft_messages=self.draft("E"),
                raw_draft=contract.canonical_json(self.fixture.response(True)),
                assigned_packet=None, prompt_contract=self.prompt, response_schema=self.schema)

    def test_C_rejects_even_null_institution_key_in_D0(self):
        messages = self.draft()
        payload = json.loads(messages[1]["content"])
        payload["institution_document"] = None
        messages[1]["content"] = contract.canonical_json(payload)
        with self.assertRaises(ValueError):
            contract.build_final_messages(draft_messages=messages,
                raw_draft=contract.canonical_json(self.fixture.response(False)),
                assigned_packet=None, prompt_contract=self.prompt, response_schema=self.schema)

    def test_E_final_cannot_switch_source(self):
        with self.assertRaisesRegex(ValueError, "differs"):
            contract.build_final_messages(draft_messages=self.draft("E"),
                raw_draft=contract.canonical_json(self.fixture.response(True)),
                assigned_packet=self.other, prompt_contract=self.prompt, response_schema=self.schema)

    def test_same_source_packet_repeated_E_L_final(self):
        for arm in ("E", "L"):
            result = self.final(arm)
            payload = json.loads(result["messages"][3]["content"])
            self.assertEqual(payload["institution_document"], self.packet)
            self.assertTrue(contract.evidence_ids(self.packet).issubset(result["visible_evidence_ids_for_final"]))
            self.assertIsNotNone(result["source_packet_sha256"])

    def test_schema_json_types_and_extra_message_keys_not_silently_accepted(self):
        messages = self.draft()
        altered_schema = copy.deepcopy(self.schema)
        altered_schema["properties"]["sectors"]["minItems"] = 11.0
        with self.assertRaises(ValueError):
            contract.build_final_messages(draft_messages=messages,
                raw_draft=contract.canonical_json(self.fixture.response(False)),
                assigned_packet=None, prompt_contract=self.prompt, response_schema=altered_schema)
        messages[1]["hidden"] = "foreign metadata"
        with self.assertRaises(ValueError):
            contract.build_final_messages(draft_messages=messages,
                raw_draft=contract.canonical_json(self.fixture.response(False)),
                assigned_packet=None, prompt_contract=self.prompt, response_schema=self.schema)

    def test_control_selection_does_not_read_source_corpus(self):
        common_only = {"common_market": self.market, "public_numeric_fact_index": self.index}
        chosen = contract.select_public_inputs(common_only, None)
        self.assertIsNone(chosen["assigned_packet"])
        chosen["common_market"]["baseline_id"] = "mutated copy"
        self.assertNotEqual(chosen["common_market"], common_only["common_market"])

    def test_C_response_has_no_source_expectation_and_semantics_unvalidated(self):
        result = contract.validate_response(contract.canonical_json(self.fixture.response(False)),
            response_schema=self.schema, expected_source_packet=None, visible_evidence_ids=self.visible)
        self.assertTrue(result["contract_valid"])
        self.assertEqual(result["semantic_support"], "unvalidated_AI_assisted_review_not_automatically_certified")

    def test_real_frozen_common_inputs_C_equal_all_four_L_and_no_institution_evidence(self):
        candidate, context, _, schema = self.fixture.real_v491_inputs()
        chosen = contract.select_public_inputs(candidate, None)
        control = contract.build_draft_messages(arm="C", **chosen, common_context=context,
            prompt_contract=self.prompt, response_schema=schema)
        for source_id in candidate["public_source_packets"]:
            late = contract.build_draft_messages(arm="L",
                **contract.select_public_inputs(candidate, source_id), common_context=context,
                prompt_contract=self.prompt, response_schema=schema)
            self.assertEqual(control, late)
            self.assertNotIn(source_id, contract.canonical_json(control))
        self.assertTrue(contract.evidence_ids(json.loads(control[1]["content"])).isdisjoint(
            set().union(*(contract.evidence_ids(p) for p in candidate["public_source_packets"].values()))))


if __name__ == "__main__":
    unittest.main()
