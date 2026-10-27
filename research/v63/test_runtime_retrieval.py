"""Synthetic engineering tests only: no model inference or real fund findings."""
from __future__ import annotations
from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np

from research.v63 import retrieval as r, runtime as rt

TEST_COUNTER = r.TokenCounter("synthetic whitespace counter; NOT MODEL TOKENIZER", lambda x: len(x.split()), False)


def corpus():
    return r.b_documents("F01", "ENGINEERING_ONLY", [0.01 + i * 0.001 for i in range(12)], 1.0,
                         "2025-12-31", "SYNTHETIC TEST BASELINE; no real fund holdings.")


def packet():
    docs = corpus()
    ids = [e for d in docs for u in d.units for e in u.evidence_ids]
    return r.retrieve(docs, "F01", "2026-03-31", "B", TEST_COUNTER, engineering=True, gold_ids=ids)


def baseline():
    b = {k: [] for k in rt.BASE_FIELDS}
    b.update(fund_id="F01", h=[1 / 12] * 12, module="B", objective="SYNTHETIC TEST ONLY")
    return b


def final(stage, weights=None):
    if stage == 1:
        output = {"baseline_conditions": {"objective_summary":"test","budget_and_long_only":"long only, sum 1","risk_cap":1,"mandatory_rule_ids":[],"limitations":"test"}, "evidence": [], "adopted_and_withheld": [], "industry_plan": [{"industry":code,"direction":"hold","reason":"test"} for code in r.INDUSTRIES]}
    elif stage == 2:
        output = {"weights": weights or [1 / 12] * 12, "change_from_h": [0] * 12, "evidence": [], "tradeoffs": "test"}
    else:
        output = {"weights": weights or [1 / 12] * 12, "calculator_check": {"performed":False,"valid":None,"note":"test"}, "previous_errors": [], "direction_explanation": "test", "evidence": []}
    return {"kind": "final", "output": output}


def response(payload, digest="TEST_ONLY"):
    return {"content": json.dumps(payload), "model_sha256": digest, "finish_reason": "stop", "usage": {"test": True}}


def check_weights(w):
    return {"valid": len(w) == 12 and abs(sum(w) - 1) < 1e-8 and min(w) >= 0, "sum": sum(w), "budget_residual": sum(w) - 1,
            "variance": 0, "risk_cap": 1, "constraint_violations": []}


class RetrievalTests(unittest.TestCase):
    def test_no_production_proxy_tokenizer(self):
        with self.assertRaisesRegex(ValueError, "exact model tokenizer"):
            r.retrieve(corpus(), "F01", "2026-03-31", "B", TEST_COUNTER)

    def test_filters_before_ranking_and_never_other_fund(self):
        docs = corpus()
        extras = r.b_documents("F02", "ENGINEERING_ONLY", [999] * 12, 1, "2025-12-31", "hidden other-fund")
        extras += r.b_documents("F01", "FUTURE", [999] * 12, 1, "2026-07-01", "future")
        extras += r.b_documents("F01", "HELD_OUT", [999] * 12, 1, "2026-03-31", "held out", period="C")
        found = r.retrieve(docs + extras, "F01", "2026-03-31", "B", TEST_COUNTER, engineering=True)
        original = packet()
        self.assertEqual(found["all_chunk_scores"], original["all_chunk_scores"])
        self.assertNotIn("999", found["packet"]["text"])

    def test_atomic_rows_keep_header_precision(self):
        d = r.Document("atomic", "F01", "2025-12-31", "B", "forecast_memo", "unit decimal date 2025-12-31 precision r=1",
                       tuple(r.AtomicUnit(("row%d " % i) + "value " * 125, (str(i),)) for i in range(12)))
        chunks = r.chunk_document(d, TEST_COUNTER)
        self.assertGreater(len(chunks), 1)
        self.assertEqual({j for c in chunks for j in c["unit_indices"]}, set(range(12)))
        for chunk in chunks:
            self.assertLessEqual(chunk["tokens"], 400)
            self.assertIn("precision r=1", chunk["text"])
            for i in chunk["unit_indices"]:
                self.assertIn(d.units[i].text, chunk["text"])

    def test_oversized_atomic_fails_without_truncation(self):
        d = r.Document("big", "F01", "2025-12-31", "B", "official_text", "header", (r.AtomicUnit("x " * 401),))
        with self.assertRaisesRegex(ValueError, "Atomic unit"):
            r.chunk_document(d, TEST_COUNTER)

    def test_retention_and_no_gold_to_model(self):
        p = packet()
        self.assertIn("gold_recall_at_4", p["diagnostics_evaluator_only"])
        self.assertEqual(p["diagnostics_evaluator_only"]["gold_recall_at_4"], 1)
        self.assertTrue(p["diagnostics_evaluator_only"]["same_atomic_content_as_full"])
        for arm, onset in rt.ARMS.items():
            for stage in (1, 2, 3):
                view = rt.evidence_for_stage(p, arm, stage)
                self.assertEqual(set(view), {"text", "sha256", "tokens", "exposed_evidence_ids"})
                if onset is None or stage < onset:
                    self.assertEqual(view["text"], "")
                elif arm != "C-context":
                    self.assertEqual(view, p["packet"])

    def test_c_new_publication_window(self):
        docs = [r.Document(str(i), "F01", date, "C", "official_text", "forecast", (r.AtomicUnit("risk return"),))
                for i, date in enumerate(["2026-03-31", "2026-04-01", "2026-07-01"])]
        selected = r.eligible_documents(docs, "F01", "2026-06-30", "C")
        self.assertEqual([x.publication_date for x in selected], ["2026-04-01"])

    def test_mandatory_baseline_evidence_not_withheld_from_r0(self):
        b = baseline()
        b["mandatory_constraints"] = [{"rule": "documented mandatory constraint", "evidence_id": "MANDATE-1"}]
        self.assertEqual(rt.disclosed_baseline_ids(b), {"MANDATE-1"})


class RuntimeTests(unittest.TestCase):
    def test_unknown_recovery_is_nonterminal_without_holdings_fallback(self):
        from research.v63.recovery import RecoveryInterruption
        trace,state=self.run_fake([RecoveryInterruption('Unknown dispatch')])
        self.assertEqual(trace['status'],'recovery_interrupted')
        self.assertIsNone(trace['effective_weights']);self.assertFalse(trace['fallback'])
        self.assertEqual(trace['actual_model_calls'],0)
        self.assertEqual(trace['new_model_requests_this_execution'],0)
        self.assertTrue(trace['calls'][0]['uncertain_prior_dispatch'])
        self.assertEqual([s['status'] for s in trace['stages']],['recovery_interrupted','not_attempted','not_attempted'])
        self.assertEqual(len(state['requests']),1)

    def run_fake(self, responses, arm="R1", tool=None):
        state = {"requests": []}
        def client(raw):
            state["requests"].append(json.loads(raw))
            item = responses[len(state["requests"]) - 1]
            if isinstance(item, Exception): raise item
            return item
        with tempfile.TemporaryDirectory() as d:
            trace = rt.run_trajectory(baseline(), packet(), arm, client,
                        tool or (lambda name, args, exposed: {"error": "synthetic"}), check_weights,
                        {"model": "synthetic", "model_sha256": "TEST_ONLY", "context_tokens": 100000, "output_tokens": 2048},
                        output_dir=Path(d) / "run", count_rendered_request=lambda req: len(json.dumps(req).split()), engineering=True)
            self.assertTrue((Path(d) / "run/trace.json").is_file())
        return trace, state

    def test_three_stages_full_history_no_fabricated_calls(self):
        trace, state = self.run_fake([response(final(i)) for i in (1, 2, 3)])
        self.assertEqual(trace["status"], "completed")
        self.assertEqual(trace["actual_model_calls"], 3)
        self.assertFalse(trace["fallback"])
        self.assertGreater(len(state["requests"][2]["messages"]), len(state["requests"][1]["messages"]))

    def test_evidence_is_injected_once_at_onset_with_all_prior_outputs_retained(self):
        for arm,onset in rt.ARMS.items():
            trace,state=self.run_fake([response(final(i)) for i in (1,2,3)],arm=arm)
            self.assertEqual([s['stage'] for s in trace['stages'] if s['evidence_injected_this_stage']],[] if onset is None else [onset])
            last=state['requests'][-1]['messages']
            self.assertEqual(sum(m['role']=='assistant' for m in last),2)
            if onset is not None:
                text=packet()['full' if arm=='C-context' else 'packet']['text']
                self.assertEqual(sum(m['content'].count(text) for m in last),1)

    def test_compact_schema_rejects_repeated_full_fact_in_decision_list(self):
        item=final(1)
        item['output']['adopted_and_withheld']=[{'evidence_id':'E','decision':'adopted','reason':'test','value':123}]
        trace,_=self.run_fake([response(item)])
        self.assertEqual(trace['status'],'model_output_failure')

    def test_replayed_response_preserves_original_time_without_new_request(self):
        item=response(final(1));item.update(replayed=True,source_elapsed_seconds=25.,new_generation_requests=0,transport_generation_requests=1)
        trace,_=self.run_fake([item,response(final(2)),response(final(3))])
        self.assertEqual(trace['calls'][0]['elapsed_seconds'],25.)
        self.assertEqual(trace['actual_model_calls'],3);self.assertEqual(trace['new_model_requests_this_execution'],2)

    def test_stage2_math_failure_goes_to_final_without_normalizing(self):
        invalid = [0.2] * 12
        trace, _ = self.run_fake([response(final(1)), response(final(2, invalid)), response(final(3))])
        self.assertEqual(trace["stages"][1]["raw_output"]["weights"], invalid)
        self.assertFalse(trace["stages"][1]["raw_weight_check"]["valid"])
        self.assertEqual(trace["status"], "completed")

    def test_final_failure_preserves_raw_and_holdings(self):
        invalid = [0.2] * 12
        trace, _ = self.run_fake([response(final(1)), response(final(2)), response(final(3, invalid))])
        self.assertEqual(trace["status"], "model_output_failure")
        self.assertEqual(trace["actual_model_calls"], 3)
        self.assertEqual(trace["stages"][2]["raw_output"]["weights"], invalid)
        self.assertEqual(trace["effective_weights"], baseline()["h"])

    def test_schema_error_stops_and_does_not_retry(self):
        trace, _ = self.run_fake([response({"kind": "final", "output": {}})])
        self.assertEqual(trace["status"], "model_output_failure")
        self.assertEqual(trace["actual_model_calls"], 1)
        self.assertEqual([s["status"] for s in trace["stages"]], ["model_output_failure", "parent_failure", "parent_failure"])

    def test_version_drift_is_not_fallback_result(self):
        trace, _ = self.run_fake([response(final(1), "WRONG_MODEL")])
        self.assertEqual(trace["status"], "protocol_violation")
        self.assertIsNone(trace["effective_weights"])

    def test_hidden_tool_id_never_passed_to_calculator(self):
        calls = []
        request = {"kind": "tools", "calls": [{"name": "posterior", "arguments": {"exposed_evidence_ids": ["hidden_id"]}}]}
        trace, _ = self.run_fake([response(request)] + [response(final(i)) for i in (1, 2, 3)],
                                 tool=lambda *args: calls.append(args))
        self.assertEqual(calls, [])
        self.assertEqual(trace["stages"][0]["tools"][0]["result"]["error"], "unavailable_tool_or_evidence")

    def test_oracle_tool_result_is_protocol_violation(self):
        request = {"kind": "tools", "calls": [{"name": "posterior", "arguments": {"exposed_evidence_ids": []}}]}
        trace, _ = self.run_fake([response(request)], tool=lambda *args: {"reference_weights": [1 / 12] * 12})
        self.assertEqual(trace["status"], "protocol_violation")
        self.assertIsNone(trace["effective_weights"])

    def test_tool_roundtrip_limit(self):
        req = response({"kind": "tools", "calls": [{"name": "posterior", "arguments": {"exposed_evidence_ids": []}}]})
        trace, _ = self.run_fake([req, req, req])
        self.assertEqual(trace["status"], "model_output_failure")
        self.assertEqual(trace["actual_model_calls"], 3)
        self.assertEqual(len(trace["stages"][0]["tools"]), 2)

    def test_partial_response_kept_not_retried(self):
        trace, _ = self.run_fake([rt.InfraFailure("partial", partial_content="{bad")])
        self.assertEqual(trace["status"], "model_output_failure")
        self.assertEqual(trace["actual_model_calls"], 1)
        self.assertEqual(trace["calls"][0]["partial_content"], "{bad")

    def test_exact_retry_bytes_and_backoff(self):
        requests, sleeps, events = [], [], []
        def client(raw):
            requests.append(raw)
            if len(requests) < 3: raise rt.InfraFailure("429", retry_after=3)
            return {"content": "ok"}
        rt.call_with_retries(client, b'unchanged', events, sleep=sleeps.append)
        self.assertEqual(requests, [b'unchanged'] * 3)
        self.assertEqual(sleeps, [3, 4])

    def test_schedule_counts_balancing_and_unattempted(self):
        schedule = rt.planned_schedule()
        self.assertEqual(schedule, rt.planned_schedule())
        self.assertEqual(len(schedule), 3272)
        self.assertEqual(sum(x["logical_stages"] for x in schedule), 9816)
        counts = Counter(x["block"] for x in schedule)
        self.assertEqual(counts, {"B-development": 240, "B-main": 2400, "x-replacement": 360, "negative-control": 192, "actual-documents": 80})
        self.assertTrue(all(x["status"] == "not_attempted" and x["effective_weights"] is None for x in schedule))
        self.assertEqual(Counter(x["fund_id"] for x in schedule if x["block"] == "x-replacement"), {"F01": 90, "F02": 90, "F03": 90, "F04": 90})

    def test_schedule_matches_numeric_counterfactual_assignments(self):
        from research.v63 import numerics
        cal = {"m0": np.zeros(12), "V0": np.eye(12) * .001, "Omega0": np.eye(12) * .001}
        scenarios, hidden = numerics.generate_scenarios(cal, block="main")
        replacements = numerics.replacement_signals(cal, scenarios, hidden)
        schedule = rt.planned_schedule()
        found = {(s["scenario"], s["fund_id"]) for s in schedule if s["block"] == "x-replacement"}
        self.assertEqual(found, {(s["scenario_id"], s["fund_id"]) for s in replacements})
        for r_level in (.5, 1, 2):
            ids = {s["scenario_id"] for s in scenarios if s["r"] == r_level}
            self.assertEqual(Counter(f for sid, f in found if sid in ids), {"F01": 5, "F02": 5, "F03": 5, "F04": 5})

    def test_missing_gate_cannot_run_real(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "Unmet v6.3"):
                rt.run_trajectory(baseline(), packet(), "R1", None, None, check_weights, {}, output_dir=d,
                                  count_rendered_request=lambda x: 1)

    def test_bad_nested_tools_are_model_schema_failure(self):
        for calls in ([1], [{"name": "posterior", "arguments": []}]):
            trace, _ = self.run_fake([response({"kind": "tools", "calls": calls})])
            self.assertEqual(trace["status"], "model_output_failure")
            self.assertEqual(trace["experimental_model_calls"], 0)

    def test_supported_seed_requires_seed(self):
        self.assertIn("supported_seed_value_missing", rt.gate_errors({"seed_support": "supported"}))

    def test_ac_no_synthetic_posterior_fields(self):
        b = {k: v for k, v in baseline().items() if k in rt.AC_BASE_FIELDS}
        b["module"] = "A"
        remaining = [response(final(i)) for i in (1, 2, 3)]
        with tempfile.TemporaryDirectory() as d:
            trace = rt.run_trajectory(b, packet(), "R0", lambda raw: remaining.pop(0), None, check_weights,
                        {"model": "synthetic", "model_sha256": "TEST_ONLY", "context_tokens": 100000},
                        output_dir=Path(d) / "run", count_rendered_request=lambda x: 10, engineering=True)
        self.assertEqual(trace["status"], "completed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
