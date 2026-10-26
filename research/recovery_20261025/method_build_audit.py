"""Offline audit of historical v4.9.2 outputs and minimal v4.9.4 prompt proposal.

Writes only method_* files in this directory. Never calls a model or repairs an
output. Selected semantic examples are unmasked retrospective method diagnosis,
not the protocol's separate masked output-by-output semantic coding.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "research"))
import sector_v492_contract as contract


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8-sig"))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def ref(relative):
    return {"path": relative, "sha256": sha((ROOT / relative).read_bytes())}


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


PROMPT = "data/sector_protocol/v492_design_20261019/prompt_contract.json"
PROTOCOL = "research/v492_evaluation_protocol_20261019_r2.json"
MANUSCRIPT = "paper/v493_manuscript_20261019.json"
RUN = "data/local_sector_runtime/v492_pilot_20261019"
original = read(PROMPT)
candidate = copy.deepcopy(original)
candidate.update(protocol_version="4.9.4", status="prospective_development_candidate_not_frozen_or_generated")
old_budget = "Choose long-only weights summing to one; raw numbers will be checked, never silently corrected."
new_budget = (
    "Each weight is a decimal fraction of the full allocation. Choose nonnegative weights "
    "whose eleven submitted values sum to one (100%); raw numbers will be checked, never silently corrected."
)
assert original["system"].count(old_budget) == 1
candidate["system"] = original["system"].replace(old_budget, new_budget)
source_field_clarification = (
    " When an institution packet is visible, source_label means the sector's published rating "
    "in that packet's rating_vocabulary, not its issuer or title. Copy evidence IDs exactly as supplied."
)
candidate["system"] += source_field_clarification
old_draft_absence = (
    "If no institution packet is supplied, use source_id=null, source_label=null, "
    "source_stance=not_available, and empty source_evidence_ids. Explicitly say "
    "institutional evidence is unavailable; do not guess it."
)
new_draft_absence = (
    "If no institution packet is supplied: use source_id=null, source_label=null, "
    "source_stance=not_available, and empty source_evidence_ids; explicitly say "
    "institutional evidence is unavailable; do not guess it."
)
assert original["D0_instruction"].count(old_draft_absence) == 1
candidate["D0_instruction"] = original["D0_instruction"].replace(old_draft_absence, new_draft_absence)
old_absence = (
    "If no institution packet is supplied, institutional evidence remains unavailable. "
    "Use source_id=null, source_label=null, source_stance=not_available, and empty source_evidence_ids "
    "for every sector. Do not guess a source, issuer, rating or institutional rationale. "
    "Explain the allocation from the common evidence and actual draft feedback without attributing it to an institution."
)
new_conditional = (
    "If an institution packet is supplied in this final message: use its exact source_id; "
    "give each sector's published source_label, source_reading and source_evidence_ids from that packet, "
    "and state your own adoption, qualification, departure or uncertainty in source_stance. "
    "If no institution packet is supplied in this final message: institutional evidence remains unavailable; "
    "use source_id=null and, for every sector, source_label=null, source_stance=not_available and empty "
    "source_evidence_ids; do not guess a source, issuer, rating or institutional rationale; explain "
    "the allocation from common evidence and actual draft feedback without institutional attribution."
)
assert original["F0_instruction"].count(old_absence) == 1
candidate["F0_instruction"] = original["F0_instruction"].replace(old_absence, new_conditional)
budget_feedback_clarification = (
    " The feedback's raw_budget_residual equals sum(D0 weights)-1. A budget correction requires the "
    "net change across all eleven weights to offset that residual; verify the sum of the eleven "
    "numbers actually submitted as F0 before claiming the budget is satisfied."
)
candidate["F0_instruction"] += budget_feedback_clarification
candidate["amendment_scope"] = {
    "basis": "Development after inspecting v4.9.2 pilot outputs; not a prespecified replication or replacement of those outputs.",
    "parent_prompt": ref(PROMPT),
    "changed_model_input_fields": ["system", "D0_instruction", "F0_instruction"],
    "D0_instruction_change": "Only delimit the no-packet branch; no evidence block changes.",
    "schema_and_supplied_evidence_unchanged": True,
    "calculator_feedback_unchanged": True,
    "post_output_semantic_correction_feedback_added": False,
    "no_target_weights_or_normalization": True,
}
save("method_prompt_candidate.json", candidate)

paths = {PROMPT, PROTOCOL, MANUSCRIPT, "research/sector_v492_contract.py",
         "research/sector_v491_contract.py", "research/sector_engine.py",
         "research/v492_runtime_candidate_20261019.json"}
stages = []
case_checks = []
parsed_outputs = {}
payloads = {}
construction_by_case = {}
for construction_path in sorted((ROOT / RUN).glob("*__final_construction.json")):
    relative = construction_path.relative_to(ROOT).as_posix()
    paths.add(relative)
    stored = read(relative)
    case = construction_path.name.removesuffix("__final_construction.json")
    construction_by_case[case] = stored
    d0 = json.loads(stored["messages"][1]["content"])
    f0 = json.loads(stored["messages"][3]["content"])
    payloads[case] = d0
    rebuilt = contract.build_final_messages(
        draft_messages=stored["messages"][:2], raw_draft=stored["messages"][2]["content"],
        assigned_packet=f0.get("institution_document"), prompt_contract=original,
        response_schema=d0["response_schema"],
    )
    draft = json.loads(stored["messages"][2]["content"])
    exact_draft_sum = sum((Decimal(str(s["weight"])) for s in draft["sectors"]), Decimal(0))
    stage_entries = []
    for stage in ["D0", "F0"]:
        prefix = f"{RUN}/{case}__{stage}"
        response_path = prefix + "/http_0001_generation/response.json"
        if not (ROOT / response_path).exists():
            continue
        validation_path = prefix + "/response_contract_validation.json"
        if not (ROOT / validation_path).exists():
            continue
        for filename in ["http_0001_generation/response.json", "response_contract_validation.json",
                         "authoritative_body.json", "worker_summary.json", "submission_calculation.json"]:
            if (ROOT / prefix / filename).exists():
                paths.add(prefix + "/" + filename)
        response = read(response_path)
        raw = response["message"]["content"]
        parsed = json.loads(raw)
        recorded = read(validation_path)
        visible = contract.prior._public_common(d0["common_market"], d0["public_numeric_fact_index"], d0["common_context"])
        packet = d0.get("institution_document")
        if stage == "F0":
            visible = set(stored["visible_evidence_ids_for_final"])
            packet = f0.get("institution_document")
        elif packet:
            visible.update(contract.evidence_ids(packet))
        recomputed = contract.validate_response(raw, response_schema=d0["response_schema"],
                                               visible_evidence_ids=visible, expected_source_packet=packet)
        exact_sum = sum((Decimal(str(s["weight"])) for s in parsed["sectors"]), Decimal(0))
        row = {
            "case_id": case, "stage": stage, "raw_response": ref(response_path),
            "raw_content_sha256": sha(raw.encode("utf-8")),
            "recorded_validation": ref(validation_path),
            "raw_content_matches_recorded_parsed": parsed == recorded["parsed"],
            "validation_recomputation_matches": recomputed == recorded,
            "raw_weight_sum_decimal": str(exact_sum),
            "raw_budget_residual_decimal": str(exact_sum - Decimal(1)),
            "schema_valid": recorded["schema_valid"],
            "complete_vector": recorded["complete_vector"],
            "arithmetic_valid": recorded["arithmetic"]["valid"],
            "source_id": parsed["source_id"],
            "expected_source_id": packet["source_id"] if packet else None,
            "visibility_errors": recorded["visibility_errors"],
            "source_label_diagnostics": recorded["source_label_diagnostics"],
            "continuation_eligible": recorded["continuation_eligible"],
            "contract_valid_is_not_arithmetic_or_semantic_success": True,
        }
        stages.append(row)
        stage_entries.append(row)
        parsed_outputs[(case, stage)] = parsed
    checks = {
        "case_id": case,
        "stored_final_construction": ref(relative),
        "reconstructed_final_messages_identical": rebuilt["messages"] == stored["messages"],
        "reconstructed_draft_feedback_identical": rebuilt["draft_feedback"] == stored["draft_feedback"],
        "feedback_sum_matches_decimal_recomputation": math.isclose(stored["draft_feedback"]["allocation"]["raw_sum"], float(exact_draft_sum), abs_tol=1e-12),
        "feedback_residual_matches_decimal_recomputation": math.isclose(stored["draft_feedback"]["allocation"]["raw_budget_residual"], float(exact_draft_sum-1), abs_tol=1e-12),
        "D0_institution_visible": "institution_document" in d0,
        "F0_institution_visible": "institution_document" in f0,
        "F0_feedback_is_own_D0_only": json.loads(stored["messages"][2]["content"]) == draft,
    }
    for stage in ["D0", "F0"]:
        body_path = f"{RUN}/{case}__{stage}/authoritative_body.json"
        if (ROOT / body_path).exists():
            body = read(body_path)
            checks[stage + "_sent_messages_match_construction"] = body["messages"] == stored["messages"][:2 if stage == "D0" else 4]
    if (case, "F0") in parsed_outputs:
        final = parsed_outputs[(case, "F0")]
        draft_weights = {s["sector_code"]: Decimal(str(s["weight"])) for s in draft["sectors"]}
        deltas = {s["sector_code"]: Decimal(str(s["weight"])) - draft_weights[s["sector_code"]] for s in final["sectors"]}
        checks["raw_component_deltas_decimal"] = {k: str(v) for k,v in deltas.items()}
        checks["raw_net_delta_decimal"] = str(sum(deltas.values(), Decimal(0)))
        checks["all_weights_unchanged"] = all(v == 0 for v in deltas.values())
        checks["valid_portfolio_distance_eligible"] = False
        checks["distance_exclusion_reason"] = "Both own D0 and F0 violate raw budget; report raw deltas only, never normalized distances."
    case_checks.append(checks)

e_case = "fidelity_q2_2026__E"
l_case = "fidelity_q2_2026__L"
e_final = parsed_outputs[(e_case, "F0")]
l_final = parsed_outputs[(l_case, "F0")]
market = payloads[l_case]["common_market"]
assert payloads[e_case]["common_market"] == market


def example(case, stage, pointer, quote, anchors, explanation, uncertainty="No causal mechanism inferred; this is a directly observed output-field diagnosis."):
    return {
        "output_artifact": ref(f"{RUN}/{case}__{stage}/http_0001_generation/response.json"),
        "output_field": pointer, "short_exact_quote": quote,
        "visible_evidence_anchors": anchors,
        "category": "unsupported_or_contradictory_link", "reason": explanation,
        "uncertainty": uncertainty, "reviewer": "Codex method_audit agent; unvalidated AI assistance",
    }


examples = [
    example(e_case,"F0","/sectors/10/decision_reason","completing the sum to 1.0",
            [{"evidence_id":"C:D0:sum","value":0.85}, {"locator":"F0 /sectors/*/weight","exact_decimal_sum":"0.850"}],
            "All eleven weights are unchanged from own D0 and sum to 0.85; no budget correction occurred."),
    example(e_case,"F0","/source_id and /sectors/*/source_reading","Not available",
            [{"locator":"F0 payload /institution_document/source_id","value":"fidelity_q2_2026"}],
            "Fidelity packet is present in both sent D0 and F0. Null source identity and unavailable fields contradict supplied evidence and Fidelity claims in decision_reason.",
            "The previous F0 no-source instruction is grammatically ambiguous. Prompt ambiguity is plausible, not an established causal explanation of the model output."),
    example(l_case,"F0","/sectors/*/source_label","Fidelity Investments / Denise Chisholm",
            [{"locator":"F0 payload /institution_document/rating_vocabulary","value":["Underweight","Neutral","Overweight"]}],
            "All eleven source_label fields contain issuer text instead of source-specific published rating. The schema gives no field description, and source_label is not explicitly defined in original instructions."),
    example(e_case,"D0","/sectors/8/decision_evidence_ids","correlation",
            [{"evidence_id":"M:correlation","locator":"D0 /public_numeric_fact_index/matrix_reference_table"}],
            "The cited bare ID is not visible; the actual matrix ID is M:correlation. This is a citation identifier error, not evidence that the supplied correlation matrix is absent."),
    example(l_case,"F0","/sectors/0/decision_reason","historical underperformance (-4.3% annualized)",
            [{"evidence_id":"M:lookback_compound_return:10","value":market["lookback_compound_return"][0],"unit":"decimal_return_over_window","period":market["lookback_return_dates"]}],
            "Visible Energy return is positive 4.2877% over the lookback window. The claim reverses sign and calls an unannualized window return annualized."),
    example(l_case,"F0","/sectors/6/decision_reason","exceptional historical performance (149.9% annualized)",
            [{"evidence_id":"M:lookback_compound_return:40","value":market["lookback_compound_return"][6],"unit":"decimal_return_over_window","period":market["lookback_return_dates"]}],
            "Visible Financials return is 8.20596% over the lookback window, not 149.9% annualized. A valid evidence ID does not validate the associated number, subject or period."),
    example(l_case,"F0","/sectors/10/source_stance and decision_reason","a cautious 'Overweight' stance",
            [{"evidence_id":"fidelity_q2_2026:p3:sector:60","text":"Real Estate receives Overweight. Valuation dispersion offers favorable risk-return."},
             {"evidence_id":"M:baseline_weights:60","value":market["baseline_weights"]["60"]},
             {"locator":"F0 /sectors/10/weight","value":0.015}],
            "Final 0.015 is below the supplied comparator 0.018018018, and the text says it is below baseline but calls this adoption of Overweight. This is an internal explanation/weight inconsistency; no numeric weight is required solely by the source rating.",
            "Fidelity's broad-market universe is not exactly the task comparator. Do not invent a universal rating-to-weight rule; the diagnosis concerns the model's own explicit baseline/adoption claims."),
    example(l_case,"F0","/risk_discussion","The final allocation is long-only and sums to 1.0.",
            [{"locator":"F0 /sectors/*/weight","exact_decimal_sum":"1.023"}],
            "The long-only claim is supported, but the sum claim is false. Raw net change from own D0 is zero despite changes in all eleven sectors."),
]
for ex in examples:
    raw = read(ex["output_artifact"]["path"])["message"]["content"]
    assert ex["short_exact_quote"] in raw, ex["short_exact_quote"]

audit = {
    "audit_version":"method_v492_to_v494_20261025_1",
    "review_date_Asia_Seoul":"2026-10-25",
    "reviewer":"Codex method_audit subagent; external to Qwen generation but not an independent human/statistical rater",
    "scope":"Read-only historical method diagnosis plus an unfrozen prospective prompt candidate. No model calls, historical edits, normalization, clipping, retry or repaired response.",
    "semantic_review_limit":"Selected unmasked retrospective examples diagnose methods. This is not the protocol's masked complete output-by-output semantic evaluation or a winning-arm comparison.",
    "research_question_preserved":"How supplied institution-specific public evidence connects to the model's stated source interpretation, decision rationale and observable allocation, with E/L timing and a source-free C trajectory.",
    "historical_stage_checks":stages,
    "historical_feedback_and_message_checks":case_checks,
    "selected_semantic_examples":examples,
    "causal_diagnosis":{
        "budget_failure":"Actual submitted weights fail the budget, while exact sent feedback correctly reports own D0 sum and residual. No calculator arithmetic bug found in these completed cases.",
        "budget_limits":"This does not identify why the model failed, or establish that proposed wording will fix it. Invalid-vector risk and active-weight feedback are null by existing design; absence of those fields is not a wrong sum.",
        "source_fields":"Original F0 absence condition is followed by standalone null-field imperatives. A clearer explicit branch is warranted, but the single E failure cannot prove causation. Undefined source_label field meaning plausibly contributes to issuer/title substitutions across visible-source drafts and finals.",
        "citations":"E D0 contains unknown ID correlation; completed E/L finals have no unknown IDs. Valid IDs coexist with incorrect numerical claims and contradictory attribution.",
        "contract_flag_limit":"L F0 contract_valid=true despite invalid sum and all labels outside vocabulary because the flag checks structural completeness plus citation visibility. Report dimensions separately; do not reinterpret contract_valid as success.",
    },
    "prospective_prompt":ref("research/recovery_20261025/method_prompt_candidate.json"),
    "exact_text_amendments":[
        {"field":"system","operation":"replace","old":old_budget,"new":new_budget,"reason":"Clarify existing full-budget decimal-weight requirement; no new economic constraint."},
        {"field":"system","operation":"append","new":source_field_clarification,"reason":"Define ambiguous rating field and preserve exact visible citation IDs without supplying source-specific answers."},
        {"field":"D0_instruction","operation":"replace","old":old_draft_absence,"new":new_draft_absence,"reason":"Keep unavailable-evidence declaration inside the no-packet condition; no source timing or evidence-block changes."},
        {"field":"F0_instruction","operation":"replace","old":old_absence,"new":new_conditional,"reason":"Keep source-present and source-absent instructions explicitly conditional across all arms."},
        {"field":"F0_instruction","operation":"append","new":budget_feedback_clarification,"reason":"Explain already supplied residual and aggregate correction; no target weights or altered calculator feedback."},
    ],
    "not_recommended": [
        "Do not normalize, clip, replace invalid vectors, retry until success, add hidden source truth or give per-sector target weights.",
        "Do not add output-specific citation/label corrections to F0; that would introduce semantic coaching beyond the existing arithmetic intervention.",
        "Do not change source documents, numeric market data, common context, response schema, source timing, number of turns, model, generation settings or completed historical evidence in this prompt amendment.",
        "Do not change tables to a different input representation merely because some claims have wrong units; that is a separate intervention with broader confounds.",
        "Do not treat schema/transport validity, arithmetic validity and semantic fidelity as interchangeable or require semantically successful output to enter main.",
    ],
    "confounds_and_disclosure": [
        "The new prompt is informed by old pilot outcomes; preserve and label those outcomes as development, freeze a new version before generation and do not pool versions as identical replications.",
        "Wording, instruction length and exposure change. Any improvement cannot be attributed solely to correcting an ambiguous branch or to evidence timing.",
        "E/L compare history, timing and exposure together; C lacks source content. None isolates a pure psychological mechanism or pure semantic information effect.",
        "One run per five cells does not establish reproducibility, significance, population causality or equivalence. Eleven sector rows are not eleven independent experimental units.",
        "An arithmetic-valid vector may still have unsupported reasoning. An arithmetic-invalid vector may preserve source meaning but is ineligible for valid-portfolio distance.",
    ],
    "stagewise_checks": [
        {"step":"historical diagnosis","errors":"Raw sums, exact citations and declared labels independently checked against actual sent payloads.","consistency":"Verbatim raw outputs, construction and recalculated feedback compared; all failures retained.","topic":"Keep explanation-to-weight contradictions as relevant evidence-chain outcomes, not just an optimization task."},
        {"step":"prospective prompt amendment","errors":"Explicit present/absent branches; exact rating field and aggregate weight identity.","consistency":"One common prompt across E/L/C; no hidden references, new targets or semantic feedback.","topic":"Repairs interpretation of the existing task without introducing an institution-specific ideal portfolio."},
        {"step":"pre-output freeze","errors":"Verify rendered messages, tokens, no truncation, model/backend pins and exact schema.","consistency":"Bind input/code/prompt/evaluation hashes and all planned five cells before any generation.","topic":"Declare same evidence-to-allocation question and no successful-output threshold."},
        {"step":"new pilot generation","errors":"Check transport, preserved raw stream, parseability and finite complete vector before dependent F0.","consistency":"One D0 and one conditional F0 per planned cell; no retry or post-final repair. Output citation/label/sum failures remain results.","topic":"Continue recording source reading, stated choice and actual weight, rather than replacing failures with a preferred allocation."},
        {"step":"postpilot review and main decision","errors":"Evaluate arithmetic, source fidelity, numeric fidelity and evidence-choice links separately with coverage and missingness.","consistency":"Keep infrastructure incidents separate; preregister/freeze subsequent amendments before held-out main; ordinary output errors are not infrastructure failures.","topic":"Readiness concerns interpretable and auditable execution. Invalid vectors can make allocation contrasts unobserved without invalidating the research as a failure-diagnostic study."},
    ],
    "main_readiness_interpretation":{
        "allowed_basis":"Correct inputs, preserved E/L/C boundaries, frozen review/code/runtime, faithful request/output capture, declared missingness and no retries.",
        "not_required":"Zero arithmetic errors, perfect citations, a desired institutional contrast or a favored semantic verdict.",
        "if_no_valid_pairs":"Primary allocation contrast remains unobserved; report source-reading and feasibility/failure diagnostics and do not claim the allocation question was answered.",
        "if_runtime_changed":"Do not call it an exact historical replication. Either restore pinned environment or explicitly version/freeze and qualify a new runtime before generation.",
    },
    "evidence_refs":[ref(p) for p in sorted(paths)],
    "offline_check_results":{
        "every_recomputed_validation_matches_record":all(s["validation_recomputation_matches"] for s in stages),
        "every_raw_response_matches_recorded_parsed":all(s["raw_content_matches_recorded_parsed"] for s in stages),
        "every_reconstructed_message_and_feedback_matches":all(c["reconstructed_final_messages_identical"] and c["reconstructed_draft_feedback_identical"] for c in case_checks),
        "all_feedback_sums_and_residuals_correct":all(c["feedback_sum_matches_decimal_recomputation"] and c["feedback_residual_matches_decimal_recomputation"] for c in case_checks),
        "all_sent_messages_match_construction":all(v for c in case_checks for k,v in c.items() if k.endswith("_sent_messages_match_construction")),
        "candidate_D0_only_no_packet_branch_delimiters_changed":candidate["D0_instruction"] == original["D0_instruction"].replace(old_draft_absence,new_draft_absence),
        "candidate_has_no_experiment_specific_target_weights":True,
        "selected_exact_quotes_verified_in_raw_output":True,
        "historical_artifacts_written":0,
        "model_calls":0,
    },
}
assert all(audit["offline_check_results"][k] for k in audit["offline_check_results"] if k not in {"historical_artifacts_written","model_calls"})
save("method_audit.json", audit)
print(json.dumps({"audit":str(OUT/"method_audit.json"),"prompt":str(OUT/"method_prompt_candidate.json"),"completed_stage_checks":len(stages),"construction_checks":len(case_checks),"all_checks_passed":True}))
