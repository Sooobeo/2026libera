"""Read-only four-segment accounting for five fixed exploratory conditions.

Only five never-attempted remaining slots are allowed. The existing completed
UBS E D0 stays in its original run and is counted once, then linked to new F0.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import finalize_sector_allocation as math
import finalize_sector_campaign as campaign
import finalize_sector_completion as completion

VERSION = "sector_remaining_finalizer_1"
PURPOSE = "pilot_completion_resume"
CASES = tuple(campaign.PILOT[2:])
STAGE_ORDER = (CASES[0] + "__F0", CASES[1] + "__D0", CASES[1] + "__F0",
               CASES[2] + "__D0", CASES[2] + "__F0")
BOUND = (*completion.BOUND, "prior_completion_gate_ref", "prior_completion_terminal_ref",
         "prior_completion_summary_ref", "prior_completion_declaration_ref", "remaining_finalizer_review_ref")
EXTERNAL_GROUPS = ("external_draft_refs", "external_draft_evidence_refs")


def scope(value):
    expected = {"purpose": PURPOSE, "case_order": list(CASES), "stage_order": list(STAGE_ORDER),
                "max_generation_requests": 5, "historical_generation_requests": 6,
                "campaign_max_generation_requests": 11, "automatic_retries": 0,
                "main_model_calls": 0, "post_final_calls": 0,
                "main_allowed": False, "old_outputs_observed": True,
                "historical_first_attempt_results_unchanged": True, "explicit_retry_slots": [],
                "historical_explicit_retry_slots": [campaign.PILOT[1] + "__D0"],
                "analysis_role": "primary_exploratory", "excluded_new_main_execution": True}
    for key, wanted in expected.items():
        if type(value.get(key)) is not type(wanted) or value[key] != wanted:
            raise ValueError("remaining_scope_mismatch:" + key)


def validate_run(declaration, run):
    import sector_remaining_runtime as runtime
    runtime.validate_runtime(declaration["runtime"])
    return runtime.validate_gate(declaration["review_gate"]["path"], declaration["review_gate"]["sha256"],
                                 runtime=declaration["runtime"], run_directory=run)


def validate_stage(spec, directory):
    import sector_remaining_runtime as runtime
    runtime.validate_spec(spec)
    runtime.validate_worker_location(spec, directory)


def validate_acknowledgement(ack, *, spec, directory, math_path):
    from run_sector_remaining import validate_external_review_ack
    return validate_external_review_ack(ack, spec=spec, folder=directory, math_path=math_path)


def terminal_guard(run, terminal_receipt=None):
    """Read only terminal metadata before traversing any model artifacts."""
    declaration, dr = math.read_artifact(run / "campaign_declaration.json")
    scope(declaration)
    reports = Path(declaration["output_root"]).resolve()
    terminal_path = Path(terminal_receipt).resolve() if terminal_receipt else reports / "terminal_receipt.json"
    if (terminal_path != reports / "terminal_receipt.json" or run.is_relative_to(reports)
            or reports.is_relative_to(run)):
        raise ValueError("separate_declared_remaining_terminal_required")
    summary, sr = math.read_artifact(run / "campaign_summary.json")
    terminal, tr = math.read_artifact(terminal_path)
    if (summary.get("purpose") != PURPOSE or terminal.get("purpose") != PURPOSE
            or summary.get("status") not in {"stopped", "attempt_sequence_finished"}
            or terminal.get("status") not in {"stopped_semantic_review_pending", "completed_semantic_review_pending"}
            or (summary["status"] == "attempt_sequence_finished") != (terminal["status"] == "completed_semantic_review_pending")):
        raise ValueError("terminal_remaining_campaign_required")
    if (Path(declaration["run_directory"]).resolve() != run or Path(terminal["run_directory"]).resolve() != run
            or Path(terminal["output_root"]).resolve() != reports
            or not completion.same_ref(terminal.get("declaration_ref"), dr)
            or not completion.same_ref(terminal.get("summary_ref"), sr)):
        raise ValueError("remaining_terminal_binding_mismatch")
    if (summary.get("case_order") != list(CASES) or summary.get("stage_order") != list(STAGE_ORDER)
            or [r.get("case_id") for r in summary.get("cases", [])] != list(CASES)):
        raise ValueError("fixed_three_cases_and_five_remaining_slots_required")
    attempts = summary.get("generation_requests_attempted")
    if type(attempts) is not int or not 0 <= attempts <= 5:
        raise ValueError("remaining_request_count_invalid")
    for value in (summary, terminal):
        for key, wanted in (("generation_requests_attempted", attempts), ("automatic_retries", 0), ("main_model_calls", 0)):
            if type(value.get(key)) is not int or value[key] != wanted:
                raise ValueError("remaining_terminal_accounting_mismatch:" + key)
    if campaign.timestamp(terminal["at_utc"]) < campaign.timestamp(summary["at_utc"]):
        raise ValueError("terminal_predates_summary")
    return declaration, summary, [dr, sr, tr]


def authority(declaration, run, refs):
    freeze, fr = campaign.checked(declaration["freeze_ref"])
    protocol, pr = campaign.checked(declaration["protocol_ref"])
    runtime, rr = campaign.checked(declaration["runtime_ref"])
    gate, gr = campaign.checked(declaration["review_gate"])
    started, er = math.read_artifact(run / "execution_started.json")
    refs.extend([fr, pr, rr, gr, er])
    for value in (freeze, protocol, gate):
        scope(value)
    if (protocol.get("status") != "approved_design_for_prospective_remaining_freeze"
            or protocol.get("raw_diagnostics_required") is not True
            or protocol.get("primary_final_allocation_endpoint") != "F0_derived_integer_allocation"
            or not completion.same_ref(protocol.get("exact_math_policy_ref"), declaration.get("finalizer_acceptance_ref"))):
        raise ValueError("approved_remaining_protocol_required")
    if (freeze.get("status") != "frozen_for_pilot_remaining_only"
            or gate.get("status") != "approved_for_remaining_before_generation" or declaration.get("runtime") != runtime):
        raise ValueError("remaining_authority_status_mismatch")
    if not (campaign.timestamp(protocol["recorded_at_utc"]) <= campaign.timestamp(freeze["recorded_at_utc"])
            <= campaign.timestamp(gate["recorded_at_utc"]) <= campaign.timestamp(declaration["created_at_utc"])
            <= campaign.timestamp(started["at_utc"])):
        raise ValueError("prospective_remaining_chronology_required")
    for value in (freeze, gate):
        for key in ("protocol_ref", "runtime_ref", *BOUND, *EXTERNAL_GROUPS, "power_policy"):
            if value.get(key) != declaration.get(key):
                raise ValueError("remaining_reference_binding_mismatch:" + key)
        if (Path(value["run_directory"]).resolve() != run
                or Path(value["output_root"]).resolve() != Path(declaration["output_root"]).resolve()):
            raise ValueError("remaining_location_binding_mismatch")
    for key in (*EXTERNAL_GROUPS, "power_policy"):
        if protocol.get(key) != declaration.get(key):
            raise ValueError("remaining_protocol_operating_binding_mismatch:" + key)
    if gate.get("freeze_ref") != declaration.get("freeze_ref"):
        raise ValueError("remaining_freeze_binding_mismatch")
    for key in BOUND:
        _, reference = campaign.checked(declaration[key])
        refs.append(reference)
    code_refs = freeze.get("code_refs", [])
    if len({str(Path(r["path"]).resolve()) for r in code_refs}) != len(code_refs):
        raise ValueError("duplicate_frozen_code_reference")
    for module in (math, campaign, completion):
        path = Path(module.__file__).resolve()
        expected = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        if sum(completion.same_ref(r, expected) for r in code_refs) != 1:
            raise ValueError("historical_finalizer_sources_must_remain_frozen")
    own = {"path": str(Path(__file__).resolve()), "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if sum(completion.same_ref(r, own) for r in code_refs) != 1:
        raise ValueError("remaining_finalizer_source_must_be_frozen")
    refs.extend(code_refs)
    campaign.unchanged(refs)
    validate_run(declaration, run)
    return protocol


def historical_dataset(declaration, protocol, refs):
    old_summary, sr = campaign.checked(declaration["prior_completion_summary_ref"])
    old_terminal, tr = campaign.checked(declaration["prior_completion_terminal_ref"])
    old_declaration, dr = campaign.checked(declaration["prior_completion_declaration_ref"])
    old_run = Path(sr["path"]).resolve().parent
    if (Path(sr["path"]).name != "campaign_summary.json" or old_summary.get("status") != "stopped"
            or not completion.same_ref(old_terminal.get("summary_ref"), sr)
            or not completion.same_ref(old_terminal.get("declaration_ref"), dr)
            or not completion.same_ref(old_declaration.get("review_gate"), declaration["prior_completion_gate_ref"])
            or old_terminal.get("generation_requests_attempted") != 1
            or old_summary.get("generation_requests_attempted") != 1
            or old_summary.get("campaign_generation_requests_attempted") != 6
            or campaign.timestamp(old_terminal["at_utc"]) > campaign.timestamp(protocol["recorded_at_utc"])):
        raise ValueError("fixed_completed_D0_historical_segment_required")
    pattern = [[(s.get("stage"), s.get("status"), s.get("generation_requests_attempted"))
                for s in c.get("stages", [])] for c in old_summary.get("cases", [])]
    if pattern != [[("D0", "completed", 1)], [], []]:
        raise ValueError("only_old_UBS_E_D0_may_be_carried")
    for key in completion.BOUND:
        if old_declaration.get(key) != declaration.get(key):
            raise ValueError("earlier_historical_binding_changed:" + key)
    previous = completion.finalize_completion(old_run, tr["path"])
    if (previous["all_generation_requests_including_interrupted_attempt"] != 6
            or previous["completion_generation_requests"] != 1):
        raise ValueError("six_historical_attempts_required")
    retained = [dict(row) for row in previous["stage_records"]
                if row["case_id"] in campaign.PILOT[:2] or (row["case_id"] == CASES[0] and row["stage"] == "D0")]
    if len(retained) != 5:
        raise ValueError("exactly_five_carried_stage_records_required")
    # External D0 completion/audits are authority for handoff, not a quality gate.
    acknowledgement = previous["external_review_acknowledgements"]
    if len(acknowledgement) != 1 or acknowledgement[0].get("status") != "external_review_completed":
        raise ValueError("inherited_D0_completed_review_ack_required")
    verify_external_history(declaration, old_run, refs)
    refs.extend([sr, tr, dr, *previous["input_refs"]])
    return retained, previous


def verify_external_history(declaration, old_run, refs):
    folder = old_run / (CASES[0] + "__D0")
    names = {"response": "http_0001_generation/response.json", "worker_spec": "worker_spec.json",
             "worker_summary": "worker_summary.json", "supervisor_result": "supervisor_result.json",
             "transport_result": "transport_result.json"}
    if set(declaration.get("external_draft_refs", {})) != set(names):
        raise ValueError("exact_five_external_draft_roles_required")
    records = {}
    for key, filename in names.items():
        records[key], reference = campaign.checked(declaration["external_draft_refs"][key])
        if Path(reference["path"]).resolve() != folder / filename:
            raise ValueError("external_draft_not_the_fixed_old_UBS_E_D0")
        refs.append(reference)
    evidence = declaration.get("external_draft_evidence_refs", {})
    if set(evidence) != {"stage_review", "allocation_math", "semantic_review", "external_review_ack",
                        "terminal", "summary", "declaration", "final_construction"}:
        raise ValueError("exact_external_draft_evidence_roles_required")
    extra = {}
    for key, reference in evidence.items():
        extra[key], actual = campaign.checked(reference)
        refs.append(actual)
    for short, full in (("terminal", "prior_completion_terminal_ref"), ("summary", "prior_completion_summary_ref"),
                        ("declaration", "prior_completion_declaration_ref")):
        if not completion.same_ref(evidence[short], declaration[full]):
            raise ValueError("external_historical_metadata_binding_differs")
    ack = extra["external_review_ack"]
    if Path(evidence["external_review_ack"]["path"]).resolve() != folder / "external_review_ack.json":
        raise ValueError("external_review_ack_is_not_own_D0")
    for key in ("stage_review", "allocation_math", "semantic_review"):
        if not completion.same_ref(evidence[key], ack.get(key + "_ref")):
            raise ValueError("external_evidence_differs_from_completed_D0_ack")
    final, raw = extra["final_construction"], records["response"]["message"]["content"]
    if (Path(evidence["final_construction"]["path"]).resolve() != old_run / (CASES[0] + "__final_construction.json")
            or final.get("ready") is not True or not isinstance(final.get("messages"), list)
            or len(final["messages"]) != 4 or final["messages"][:2] != records["worker_spec"]["body"]["messages"]
            or final["messages"][2] != {"role": "assistant", "content": raw}):
        raise ValueError("saved_external_F0_construction_lost_exact_history")


def own_history(run, case, spec, declaration, refs):
    if case != CASES[0]:
        return completion.own_history(run, case, spec, refs)
    records = {}
    for key, reference in declaration["external_draft_refs"].items():
        records[key], actual = campaign.checked(reference)
        refs.append(actual)
    final, final_ref = campaign.checked(declaration["external_draft_evidence_refs"]["final_construction"])
    refs.append(final_ref)
    raw = records["response"]["message"]["content"]
    messages = spec.get("body", {}).get("messages")
    if (spec.get("draft_artifacts") != declaration["external_draft_refs"] or spec.get("raw_draft") != raw
            or final.get("ready") is not True or messages != final.get("messages")
            or not isinstance(messages, list) or len(messages) != 4
            or messages[:2] != records["worker_spec"]["body"]["messages"]
            or messages[2] != {"role": "assistant", "content": raw}):
        raise ValueError("remaining_F0_exact_external_own_D0_history_mismatch")


def check_sequence(summary):
    recorded = []
    cases = summary["cases"]
    for i, case in enumerate(cases):
        records = case.get("stages", [])
        names = [r.get("stage") for r in records]
        allowed = ([], ["F0"]) if i == 0 else ([], ["D0"], ["D0", "F0"])
        if names not in allowed:
            raise ValueError("unexpected_remaining_stage_sequence")
        later_exists = any(c.get("stages") for c in cases[i + 1:])
        finishing = summary["status"] == "attempt_sequence_finished"
        if not records and (later_exists or finishing):
            raise ValueError("skipped_independent_remaining_stage")
        if i and "F0" in names and records[0].get("status") != "completed":
            raise ValueError("remaining_F0_requires_completed_own_D0")
        if i and names == ["D0"] and records[0].get("status") == "completed" and (later_exists or finishing):
            raise ValueError("completed_D0_missing_F0_without_global_stop")
        recorded.extend((case["case_id"], r["stage"]) for r in records)
    return recorded


def segment_rows(run, declaration, summary, refs):
    recorded_slots = check_sequence(summary)
    records = {(c["case_id"], s["stage"]): s for c in summary["cases"] for s in c.get("stages", [])}
    rows, dirs, attempts, acknowledgements = [], set(), 0, []
    for slot in STAGE_ORDER:
        case, stage = slot.rsplit("__", 1)
        record = records.get((case, stage))
        if record is None:
            rows.append({"case_id": case, "stage": stage, "status": "unavailable", "rows": [],
                         "generation_requests_attempted": 0, "reasons": ["not_attempted"], "run_directory": str(run)})
            continue
        folder = run / slot
        dirs.add(slot)
        spec, spec_ref = math.read_artifact(folder / "worker_spec.json")
        if spec.get("runtime") != declaration["runtime"] or spec.get("review_gate") != declaration["review_gate"]:
            raise ValueError("remaining_stage_authority_differs")
        validate_stage(spec, folder)
        item = math.finalize_stage(folder)
        if (type(record.get("generation_requests_attempted")) is not int
                or record["generation_requests_attempted"] != item["generation_requests_attempted"]
                or record.get("status") != item["observed_transport_status"]):
            raise ValueError("remaining_summary_stage_accounting_mismatch")
        if stage == "F0":
            own_history(run, case, spec, declaration, refs)
        ack_result = {"case_id": case, "stage": stage, "status": "unavailable", "outcome_success_required": False}
        math_path = Path(declaration["output_root"]).resolve() / "allocation_math" / (slot + ".json")
        try:
            ack, ar = math.read_artifact(folder / "external_review_ack.json")
            validated = validate_acknowledgement(ack, spec=spec, directory=folder, math_path=math_path)
            refs.append(ar)
            for key in ("worker_spec_ref", "transport_ref", "stage_review_ref", "allocation_math_ref", "semantic_review_ref"):
                _, reference = campaign.checked(ack[key])
                refs.append(reference)
            saved, _ = math.read_artifact(math_path)
            if saved != item:
                raise ValueError("Acknowledged math differs from unchanged finalize_stage result")
            ack_result.update(validated, acknowledgement_ref=ar)
        except (OSError, ValueError, KeyError, TypeError) as error:
            ack_result.update(status="unavailable_or_invalid", reason=type(error).__name__ + ": " + str(error))
            if summary["status"] == "attempt_sequence_finished" or (case, stage) != recorded_slots[-1]:
                raise ValueError("progression_without_valid_remaining_review_ack") from error
        acknowledgements.append(ack_result)
        refs.extend([spec_ref, *item["input_refs"]])
        item["run_directory"] = str(run)
        rows.append(item)
        attempts += item["generation_requests_attempted"]
    if {p.name for p in run.iterdir() if p.is_dir()} != dirs:
        raise ValueError("unaccounted_remaining_stage_directory")
    expected = {"generation_requests_attempted": attempts, "max_generation_requests": 5,
                "historical_generation_requests": 6, "campaign_generation_requests_attempted": 6 + attempts,
                "campaign_max_generation_requests": 11, "post_final_calls": 0,
                "original_planned_final_cells": 5, "segment_planned_final_cells": 3}
    for key, value in expected.items():
        if type(summary.get(key)) is not int or summary[key] != value:
            raise ValueError("remaining_summary_total_mismatch:" + key)
    if attempts > 5:
        raise ValueError("remaining_request_ceiling_exceeded")
    return rows, attempts, acknowledgements


def extend_ledger(previous, rows):
    ledger = [dict(row) for row in previous["all_attempt_ledger"]]
    if len(ledger) != 6:
        raise ValueError("exact_historical_six_entry_ledger_required")
    historical_slots = {(r["case_id"], r["stage"]) for r in ledger}
    for row in rows:
        count = row.get("generation_requests_attempted", 0)
        if type(count) is not int or count not in (0, 1):
            raise ValueError("at_most_one_request_per_new_slot")
        if count == 0:
            continue
        if row["case_id"] + "__" + row["stage"] not in STAGE_ORDER or (row["case_id"], row["stage"]) in historical_slots:
            raise ValueError("remaining_request_repeats_historical_or_unplanned_slot")
        historical_slots.add((row["case_id"], row["stage"]))
        ledger.append({"campaign_request_ordinal": len(ledger) + 1, "segment": "remaining",
                       "case_id": row["case_id"], "stage": row["stage"], "logical_slot_attempt": 1,
                       "observed_transport_status": row["observed_transport_status"], "input_refs": row.get("input_refs", [])})
    return ledger


def finalize_remaining(run_dir, terminal_receipt=None):
    run = Path(run_dir).resolve()
    declaration, summary, refs = terminal_guard(run, terminal_receipt)
    protocol = authority(declaration, run, refs)
    retained, previous = historical_dataset(declaration, protocol, refs)
    rows, attempts, acknowledgements = segment_rows(run, declaration, summary, refs)
    selected_by_slot = {(r["case_id"], r["stage"]): r for r in retained}
    for row in rows:
        key = (row["case_id"], row["stage"])
        if key in selected_by_slot:
            raise ValueError("historical_selected_stage_replaced")
        selected_by_slot[key] = {**row, "selection_role": "fixed_remaining_slot"}
    selected = [selected_by_slot[(case, stage)] for case in campaign.PILOT for stage in ("D0", "F0")]
    if len(selected_by_slot) != 10:
        raise ValueError("exact_ten_logical_stage_slots_required")
    ledger = extend_ledger(previous, rows)
    if len(ledger) != 6 + attempts or len(ledger) > 11:
        raise ValueError("remaining_cumulative_attempt_mismatch")
    campaign.unchanged(refs)
    return {"version": VERSION, "purpose": "primary_exploratory_remaining_dataset", "analysis_role": "primary_exploratory",
            "not_prespecified_original_experiment": True, "case_order": list(campaign.PILOT),
            "planned_final_allocations": 5, "planned_final_sector_rows": 55, "logical_stage_slots": 10,
            "segment_case_order": list(CASES), "segment_planned_final_allocations": 3, "segment_planned_stage_slots": 5,
            "segment_stage_order": list(STAGE_ORDER), "original_generation_requests": 3,
            "prior_continuation_generation_requests": 2, "completion_generation_requests": 1,
            "remaining_generation_requests": attempts, "all_generation_requests_including_interrupted_attempt": len(ledger),
            "campaign_max_generation_requests": 11, "all_attempt_ledger": ledger,
            "prior_completion_derived_report": previous, "stage_records": selected, "remaining_stage_records": rows,
            "external_review_acknowledgements": acknowledgements, "external_draft_refs": declaration["external_draft_refs"],
            "external_draft_evidence_refs": declaration["external_draft_evidence_refs"],
            "derived_comparisons": campaign.pairs(selected, campaign.PILOT),
            "finalized_finals": sum(r["stage"] == "F0" and r["status"] == "finalized" for r in selected),
            "primary_final_allocation_endpoint": "F0_derived_integer_allocation", "raw_diagnostics_required": True,
            "input_refs": refs, "generation_calls": 0, "service_calls": 0, "main_model_calls": 0,
            "historical_failed_attempt_erased": False, "raw_artifacts_modified": False, "missing_finals_replaced": False,
            "semantic_review_status": "not_performed_by_finalizer",
            "limits": ["Raw and amended derived endpoints must both be reported; arithmetic is not semantic validation.",
                       "Five fixed logical conditions span four operational segments, including a preserved cross-segment D0/F0 pair.",
                       "The study role, endpoint and operating policy were amended after observed outputs and interruptions.",
                       "No causal, future-return, performance, independent-replication or independent-human validation claim."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--terminal-receipt", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    declaration, _ = math.read_artifact(args.run_dir / "campaign_declaration.json")
    roots = [args.run_dir.resolve()] + [Path(declaration[k]["path"]).resolve().parent for k in
             ("historical_summary_ref", "prior_continuation_summary_ref", "prior_completion_summary_ref")]
    output = args.output.resolve()
    if output.exists() or any(output.is_relative_to(root) for root in roots):
        parser.error("New derived output must remain outside all four immutable raw runs")
    result = finalize_remaining(args.run_dir, args.terminal_receipt)
    result["created_at_utc"] = datetime.now(timezone.utc).isoformat()
    encoded = json.dumps(result, ensure_ascii=True, allow_nan=False, indent=2) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(encoded)
    print(json.dumps({"output": str(output), "finalized_finals": result["finalized_finals"],
                      "all_attempts": result["all_generation_requests_including_interrupted_attempt"], "generation_calls": 0}))


if __name__ == "__main__":
    main()
