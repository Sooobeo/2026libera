"""Read-only completion accounting for the amended five-cell exploratory study.

Old pilot/continuation arithmetic and raw artifacts are never rewritten.  This
adapter accepts only a new three-cell completion authority and a terminal run.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import finalize_sector_allocation as math
import finalize_sector_campaign as campaign

VERSION = "sector_completion_finalizer_1"
PURPOSE = "pilot_completion"
CASES = campaign.PILOT[2:]
BOUND = ("historical_gate_ref", "historical_terminal_ref", "historical_summary_ref",
         "prior_continuation_gate_ref", "prior_continuation_terminal_ref",
         "prior_continuation_summary_ref", "prior_continuation_declaration_ref",
         "prepared_manifest_ref", "finalizer_acceptance_ref", "completion_finalizer_review_ref")


def same_ref(left, right):
    return (isinstance(left, dict) and isinstance(right, dict)
            and Path(left.get("path", "")).resolve() == Path(right.get("path", "")).resolve()
            and left.get("sha256") == right.get("sha256"))


def scope(value):
    expected = {"purpose": PURPOSE, "case_order": list(CASES),
                "max_generation_requests": 6, "historical_generation_requests": 5,
                "campaign_max_generation_requests": 11, "automatic_retries": 0,
                "main_allowed": False, "old_outputs_observed": True,
                "historical_first_attempt_results_unchanged": True,
                "explicit_retry_slots": [],
                "historical_explicit_retry_slots": [campaign.PILOT[1] + "__D0"],
                "analysis_role": "primary_exploratory", "excluded_new_main_execution": True}
    for key, wanted in expected.items():
        actual = value.get(key)
        if type(actual) is not type(wanted) or actual != wanted:
            raise ValueError("completion_scope_mismatch:" + key)


def validate_run(declaration, run):
    import sector_completion_runtime as runtime
    runtime.validate_runtime(declaration["runtime"])
    runtime.validate_gate(declaration["review_gate"]["path"], declaration["review_gate"]["sha256"],
                          runtime=declaration["runtime"], run_directory=run)


def validate_stage(spec, directory):
    import sector_completion_runtime as runtime
    runtime.validate_spec(spec)
    runtime.validate_worker_location(spec, directory)


def validate_acknowledgement(ack, *, spec, directory, math_path):
    # Pure file validation only; never call the coordinator or its wait loop.
    from run_sector_completion import validate_external_review_ack
    return validate_external_review_ack(ack, spec=spec, folder=directory, math_path=math_path)


def terminal_guard(run, terminal_path=None):
    """Metadata only; must precede raw stage or historical model-text traversal."""
    declaration, dr = math.read_artifact(run / "campaign_declaration.json")
    scope(declaration)
    reports = Path(declaration["output_root"]).resolve()
    terminal_path = Path(terminal_path).resolve() if terminal_path else reports / "terminal_receipt.json"
    if (terminal_path != reports / "terminal_receipt.json"
            or run.is_relative_to(reports) or reports.is_relative_to(run)):
        raise ValueError("separate_declared_terminal_report_required")
    summary, sr = math.read_artifact(run / "campaign_summary.json")
    terminal, tr = math.read_artifact(terminal_path)
    if (summary.get("purpose") != PURPOSE or terminal.get("purpose") != PURPOSE
            or summary.get("status") not in {"stopped", "attempt_sequence_finished"}
            or terminal.get("status") not in {"stopped_semantic_review_pending", "completed_semantic_review_pending"}
            or (summary["status"] == "attempt_sequence_finished") != (terminal["status"] == "completed_semantic_review_pending")):
        raise ValueError("terminal_completion_campaign_required")
    if (Path(declaration["run_directory"]).resolve() != run
            or Path(terminal["run_directory"]).resolve() != run
            or Path(terminal["output_root"]).resolve() != reports
            or not same_ref(terminal.get("declaration_ref"), dr)
            or not same_ref(terminal.get("summary_ref"), sr)):
        raise ValueError("terminal_binding_mismatch")
    if (summary.get("case_order") != list(CASES)
            or [r.get("case_id") for r in summary.get("cases", [])] != list(CASES)):
        raise ValueError("full_three_case_denominator_required")
    attempts = summary.get("generation_requests_attempted")
    if type(attempts) is not int or not 0 <= attempts <= 6:
        raise ValueError("completion_request_count_invalid")
    for value in (summary, terminal):
        for key, expected in (("generation_requests_attempted", attempts), ("automatic_retries", 0), ("main_model_calls", 0)):
            if type(value.get(key)) is not int or value[key] != expected:
                raise ValueError("terminal_accounting_mismatch:" + key)
    if campaign.timestamp(terminal["at_utc"]) < campaign.timestamp(summary["at_utc"]):
        raise ValueError("terminal_receipt_predates_summary")
    return declaration, summary, [dr, sr, tr]


def authority(declaration, run, refs):
    freeze, fr = campaign.checked(declaration["freeze_ref"])
    protocol, pr = campaign.checked(declaration["protocol_ref"])
    runtime, rr = campaign.checked(declaration["runtime_ref"])
    gate, gr = campaign.checked(declaration["review_gate"])
    started, er = math.read_artifact(run / "execution_started.json")
    refs += [fr, pr, rr, gr, er]
    for value in (freeze, protocol, gate):
        scope(value)
    if (protocol.get("status") != "approved_design_for_prospective_completion_freeze"
            or protocol.get("raw_diagnostics_required") is not True
            or protocol.get("primary_final_allocation_endpoint") != "F0_derived_integer_allocation"
            or not same_ref(protocol.get("exact_math_policy_ref"), declaration.get("finalizer_acceptance_ref"))):
        raise ValueError("approved_amended_endpoint_protocol_required")
    if (freeze.get("status") != "frozen_for_pilot_completion_only"
            or gate.get("status") != "approved_for_completion_before_generation"
            or declaration.get("runtime") != runtime):
        raise ValueError("approved_completion_authority_required")
    if not (campaign.timestamp(protocol.get("recorded_at_utc"))
            <= campaign.timestamp(freeze.get("recorded_at_utc"))
            <= campaign.timestamp(gate.get("recorded_at_utc"))
            <= campaign.timestamp(declaration.get("created_at_utc"))
            <= campaign.timestamp(started.get("at_utc"))):
        raise ValueError("prospective_completion_chronology_required")
    for value in (freeze, gate):
        for key in ("protocol_ref", "runtime_ref", *BOUND):
            if value.get(key) != declaration.get(key):
                raise ValueError("completion_reference_binding_mismatch:" + key)
        if (Path(value["run_directory"]).resolve() != run
                or Path(value["output_root"]).resolve() != Path(declaration["output_root"]).resolve()):
            raise ValueError("completion_location_binding_mismatch")
    if gate.get("freeze_ref") != declaration["freeze_ref"]:
        raise ValueError("completion_freeze_binding_mismatch")
    for key in BOUND:
        _, reference = campaign.checked(declaration[key])
        refs.append(reference)
    code_refs = freeze.get("code_refs", [])
    if (not isinstance(code_refs, list)
            or len({str(Path(r["path"]).resolve()) for r in code_refs}) != len(code_refs)):
        raise ValueError("unique_frozen_code_refs_required")
    for path in (Path(__file__).resolve(), Path(math.__file__).resolve(), Path(campaign.__file__).resolve()):
        expected = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        if sum(same_ref(r, expected) for r in code_refs) != 1:
            raise ValueError("all_three_finalizer_sources_must_be_frozen")
    refs.extend({"path": str(Path(r["path"]).resolve()), "sha256": r["sha256"]} for r in code_refs)
    campaign.unchanged(refs)
    validate_run(declaration, run)
    return protocol


def own_history(run, case, spec, refs):
    draft_dir = run / (case + "__D0")
    expected = {}
    values = {}
    for role, name in (("worker_spec", "worker_spec.json"), ("transport_result", "transport_result.json"),
                       ("response", "http_0001_generation/response.json"),
                       ("worker_summary", "worker_summary.json"), ("supervisor_result", "supervisor_result.json")):
        values[role], expected[role] = math.read_artifact(draft_dir / name)
    raw = values["response"].get("message", {}).get("content")
    initial = values["worker_spec"].get("body", {}).get("messages")
    final = spec.get("body", {}).get("messages")
    if (spec.get("draft_artifacts") != expected or values["transport_result"].get("continuation_eligible") is not True
            or not isinstance(raw, str) or spec.get("raw_draft") != raw
            or not isinstance(initial, list) or len(initial) != 2
            or not isinstance(final, list) or len(final) != 4 or final[:2] != initial
            or final[2] != {"role": "assistant", "content": raw} or final[3].get("role") != "user"):
        raise ValueError("completion_F0_own_new_D0_binding_mismatch")
    refs.extend(expected.values())


def segment_rows(run, declaration, summary, refs):
    rows, directories, attempts, acknowledgements = [], set(), 0, []
    recorded_slots = [(case["case_id"], record["stage"]) for case in summary["cases"]
                      for record in case.get("stages", [])]
    for case in summary["cases"]:
        records = case.get("stages", [])
        if [r.get("stage") for r in records] not in ([], ["D0"], ["D0", "F0"]):
            raise ValueError("unexpected_completion_stage_sequence")
        by_stage = {r["stage"]: r for r in records}
        if "F0" in by_stage and by_stage["D0"].get("status") != "completed":
            raise ValueError("completion_F0_requires_completed_own_D0")
        for stage in ("D0", "F0"):
            if stage not in by_stage:
                rows.append({"case_id": case["case_id"], "stage": stage, "status": "unavailable", "rows": [],
                             "generation_requests_attempted": 0, "reasons": ["not_attempted"], "run_directory": str(run)})
                continue
            directory = run / (case["case_id"] + "__" + stage)
            directories.add(directory.name)
            spec, _ = math.read_artifact(directory / "worker_spec.json")
            if spec.get("runtime") != declaration["runtime"] or spec.get("review_gate") != declaration["review_gate"]:
                raise ValueError("completion_stage_authority_differs")
            validate_stage(spec, directory)
            item = math.finalize_stage(directory)
            record = by_stage[stage]
            if (type(record.get("generation_requests_attempted")) is not int
                    or record["generation_requests_attempted"] != item["generation_requests_attempted"]
                    or record.get("status") != item["observed_transport_status"]):
                raise ValueError("completion_summary_stage_accounting_mismatch")
            if stage == "F0":
                own_history(run, case["case_id"], spec, refs)
            ack_path = directory / "external_review_ack.json"
            math_path = Path(declaration["output_root"]).resolve() / "allocation_math" / (directory.name + ".json")
            ack_result = {"case_id": case["case_id"], "stage": stage,
                          "status": "unavailable", "outcome_success_required": False}
            try:
                ack, ack_ref = math.read_artifact(ack_path)
                validated = validate_acknowledgement(ack, spec=spec, directory=directory, math_path=math_path)
                refs.append(ack_ref)
                for key in ("worker_spec_ref", "transport_ref", "stage_review_ref", "allocation_math_ref", "semantic_review_ref"):
                    _, reference = campaign.checked(ack[key])
                    refs.append(reference)
                saved_math, _ = math.read_artifact(math_path)
                if saved_math != item:
                    raise ValueError("Acknowledged math differs from unchanged finalize_stage result")
                ack_result.update(validated, acknowledgement_ref=ack_ref)
            except (OSError, ValueError, KeyError, TypeError) as error:
                ack_result.update(status="unavailable_or_invalid", reason=type(error).__name__ + ": " + str(error))
                # A terminal stop may itself be caused by a missing/stale ACK.
                # Preserve that last audit gap; it cannot authorize a later slot.
                if (summary["status"] == "attempt_sequence_finished"
                        or (case["case_id"], stage) != recorded_slots[-1]):
                    raise ValueError("progression_without_valid_external_review_acknowledgement") from error
            acknowledgements.append(ack_result)
            item["run_directory"] = str(run)
            refs.extend(item["input_refs"])
            rows.append(item)
            attempts += item["generation_requests_attempted"]
    if {p.name for p in run.iterdir() if p.is_dir()} != directories:
        raise ValueError("unaccounted_completion_stage_directory")
    checks = {"generation_requests_attempted": attempts, "max_generation_requests": 6,
              "historical_generation_requests": 5, "campaign_generation_requests_attempted": 5 + attempts,
              "campaign_max_generation_requests": 11, "post_final_calls": 0,
              "original_planned_final_cells": 5, "segment_planned_final_cells": 3}
    for key, expected in checks.items():
        if type(summary.get(key)) is not int or summary[key] != expected:
            raise ValueError("completion_summary_total_mismatch:" + key)
    if attempts > 6:
        raise ValueError("completion_request_ceiling_exceeded")
    return rows, attempts, acknowledgements


def historical_rows(declaration, protocol, refs):
    """Validate exact three-plus-two past pattern, without selecting by quality."""
    old_summary, osr = campaign.checked(declaration["historical_summary_ref"])
    old_terminal, otr = campaign.checked(declaration["historical_terminal_ref"])
    prior_summary, psr = campaign.checked(declaration["prior_continuation_summary_ref"])
    prior_terminal, ptr = campaign.checked(declaration["prior_continuation_terminal_ref"])
    prior_declaration, pdr = campaign.checked(declaration["prior_continuation_declaration_ref"])
    old_run, prior_run = Path(osr["path"]).parent, Path(psr["path"]).parent
    if (Path(osr["path"]).name != "pilot_summary.json" or Path(psr["path"]).name != "campaign_summary.json"
            or not same_ref(old_terminal.get("summary_ref"), osr)
            or not same_ref(prior_terminal.get("summary_ref"), psr)
            or not same_ref(prior_terminal.get("declaration_ref"), pdr)
            or old_terminal.get("status") != "stopped_semantic_review_pending"
            or prior_terminal.get("status") != "stopped_semantic_review_pending"
            or old_terminal.get("generation_requests_attempted") != 3
            or prior_terminal.get("generation_requests_attempted") != 2
            or Path(old_terminal["run_directory"]).resolve() != old_run
            or Path(prior_terminal["run_directory"]).resolve() != prior_run):
        raise ValueError("historical_terminal_binding_mismatch")
    for terminal in (old_terminal, prior_terminal):
        if campaign.timestamp(terminal["at_utc"]) > campaign.timestamp(protocol["recorded_at_utc"]):
            raise ValueError("completion_protocol_predates_historical_terminal")
    if (not same_ref(prior_declaration.get("review_gate"), declaration["prior_continuation_gate_ref"])
            or not same_ref(prior_declaration.get("historical_summary_ref"), declaration["historical_summary_ref"])
            or not same_ref(prior_declaration.get("historical_gate_ref"), declaration["historical_gate_ref"])
            or not same_ref(prior_declaration.get("prepared_manifest_ref"), declaration["prepared_manifest_ref"])
            or not same_ref(prior_declaration.get("finalizer_acceptance_ref"), declaration["finalizer_acceptance_ref"])):
        raise ValueError("historical_segments_or_inputs_differ")
    def pattern(summary):
        return [[(s.get("stage"), s.get("status"), s.get("generation_requests_attempted"))
                 for s in c.get("stages", [])] for c in summary.get("cases", [])]
    if (pattern(old_summary) != [[("D0", "completed", 1), ("F0", "completed", 1)], [("D0", "hard_deadline", 1)], [], [], []]
            or pattern(prior_summary) != [[("D0", "completed", 1), ("F0", "completed", 1)], [], [], []]
            or prior_summary.get("status") != "stopped"):
        raise ValueError("fixed_historical_three_plus_two_pattern_required")
    original = math.finalize_run(old_run)
    prior = campaign.finalize_campaign(prior_run)
    if original["first_attempt_requests"] != 3 or prior["generation_requests_attempted"] != 2:
        raise ValueError("historical_five_request_accounting_mismatch")
    refs += [osr, otr, psr, ptr, pdr, original["run_summary_ref"], *prior["input_refs"]]
    refs.extend(r for row in original["stage_records"] for r in row.get("input_refs", []))
    retained = [{**r, "run_directory": str(old_run), "selection_role": "fixed_original_Fidelity_E"}
                for r in original["stage_records"] if r["case_id"] == campaign.PILOT[0]]
    retained += [{**r, "selection_role": "fixed_prior_continuation_Fidelity_L"}
                 for r in prior["stage_records"] if r["case_id"] == campaign.PILOT[1]]
    if len(retained) != 4:
        raise ValueError("fixed_two_historical_cells_required")
    return retained, original, prior


def attempt_ledger(original, prior, completion_rows):
    ledger, slot_counts = [], {}
    for segment, rows in (("original_v494", original["stage_records"]),
                           ("prior_continuation", prior["stage_records"]), ("completion", completion_rows)):
        for row in rows:
            count = row.get("generation_requests_attempted", 0)
            if count == 0:
                continue
            if type(count) is not int or count != 1:
                raise ValueError("single_actual_request_per_segment_slot_required")
            slot = row["case_id"] + "__" + row["stage"]
            slot_counts[slot] = slot_counts.get(slot, 0) + 1
            ledger.append({"campaign_request_ordinal": len(ledger) + 1, "segment": segment,
                           "case_id": row["case_id"], "stage": row["stage"],
                           "logical_slot_attempt": slot_counts[slot],
                           "observed_transport_status": row["observed_transport_status"],
                           "input_refs": row.get("input_refs", [])})
    repeats = {slot: count for slot, count in slot_counts.items() if count > 1}
    if repeats != {campaign.PILOT[1] + "__D0": 2}:
        raise ValueError("only_declared_historical_infrastructure_retry_allowed")
    return ledger


def finalize_completion(run_dir, terminal_receipt=None):
    run = Path(run_dir).resolve()
    declaration, summary, refs = terminal_guard(run, terminal_receipt)
    protocol = authority(declaration, run, refs)
    retained, original, prior = historical_rows(declaration, protocol, refs)
    rows, attempts, acknowledgements = segment_rows(run, declaration, summary, refs)
    selected = retained + [{**r, "selection_role": "fixed_new_completion_slot"} for r in rows]
    ledger = attempt_ledger(original, prior, rows)
    if len(ledger) != 5 + attempts or len(ledger) > 11:
        raise ValueError("all_attempt_ledger_mismatch")
    campaign.unchanged(refs)
    return {"version": VERSION, "purpose": "primary_exploratory_completion_dataset",
            "analysis_role": "primary_exploratory", "not_prespecified_original_experiment": True,
            "case_order": list(campaign.PILOT), "planned_final_allocations": 5,
            "planned_final_sector_rows": 55, "logical_stage_slots": 10,
            "segment_case_order": list(CASES), "segment_planned_final_allocations": 3,
            "segment_planned_stage_slots": 6, "original_generation_requests": 3,
            "prior_continuation_generation_requests": 2, "completion_generation_requests": attempts,
            "all_generation_requests_including_interrupted_attempt": len(ledger),
            "campaign_max_generation_requests": 11, "all_attempt_ledger": ledger,
            "original_first_attempt_derived_report": original, "prior_continuation_derived_report": prior,
            "stage_records": selected, "completion_stage_records": rows,
            "external_review_acknowledgements": acknowledgements,
            "derived_comparisons": campaign.pairs(selected, campaign.PILOT),
            "finalized_finals": sum(r["stage"] == "F0" and r["status"] == "finalized" for r in selected),
            "primary_final_allocation_endpoint": "F0_derived_integer_allocation", "raw_diagnostics_required": True,
            "input_refs": refs, "generation_calls": 0, "service_calls": 0, "main_model_calls": 0,
            "historical_failed_attempt_erased": False, "raw_artifacts_modified": False,
            "missing_finals_replaced": False, "semantic_review_status": "not_performed_by_finalizer",
            "limits": ["Raw vectors and post-start amended 100% endpoint must both be reported; exact arithmetic is not semantic validation.",
                       "Five logical conditions across three segments are exploratory descriptive cases, not independent replications.",
                       "No causal, future-return, performance or independent-human validation claim.",
                       "Absent or unfinalizable finals and unavailable pairwise comparisons remain explicit outcomes."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--terminal-receipt", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    declaration, _ = math.read_artifact(args.run_dir / "campaign_declaration.json")
    raw_runs = [args.run_dir.resolve(), Path(declaration["historical_summary_ref"]["path"]).resolve().parent,
                Path(declaration["prior_continuation_summary_ref"]["path"]).resolve().parent]
    output = args.output.resolve()
    if output.exists() or any(output.is_relative_to(raw) for raw in raw_runs):
        parser.error("New derived output must remain outside all three immutable raw runs")
    result = finalize_completion(args.run_dir, args.terminal_receipt)
    result["created_at_utc"] = datetime.now(timezone.utc).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=True, allow_nan=False, indent=2)
        stream.write("\n")
    print(json.dumps({"output": str(output), "finalized_finals": result["finalized_finals"],
                      "all_attempts": result["all_generation_requests_including_interrupted_attempt"], "generation_calls": 0}))


if __name__ == "__main__":
    main()
