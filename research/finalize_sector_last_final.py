"""One unattempted control final, preserving all five operational segments."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path

import finalize_sector_remaining as previous

math, campaign, completion = previous.math, previous.campaign, previous.completion
ROOT = Path(__file__).resolve().parents[1]
VERSION = "sector_last_final_finalizer_1"
PURPOSE = "pilot_last_final"
CASE = campaign.PILOT[-1]
CASES, STAGE_ORDER = (CASE,), (CASE + "__F0",)
BOUND = (*previous.BOUND, "prior_remaining_gate_ref", "prior_remaining_terminal_ref",
         "prior_remaining_summary_ref", "prior_remaining_declaration_ref", "prior_remaining_cancel_ref",
         "prior_pause_checkpoint_ref", "resumption_design_ref", "last_finalizer_review_ref")


def adapter():
    path = ROOT / "research/last_final_20261026/runtime_adapter.py"
    spec = importlib.util.spec_from_file_location("last_final_numeric_runtime_adapter", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scope(value):
    expected = {"purpose": PURPOSE, "case_order": list(CASES), "stage_order": list(STAGE_ORDER),
                "max_generation_requests": 1, "historical_generation_requests": 10,
                "campaign_max_generation_requests": 11, "automatic_retries": 0,
                "post_final_calls": 0, "main_model_calls": 0, "main_allowed": False,
                "old_outputs_observed": True, "historical_first_attempt_results_unchanged": True,
                "explicit_retry_slots": [], "historical_explicit_retry_slots": [campaign.PILOT[1] + "__D0"],
                "analysis_role": "primary_exploratory", "excluded_new_main_execution": True}
    for key, expected_value in expected.items():
        if type(value.get(key)) is not type(expected_value) or value[key] != expected_value:
            raise ValueError("last_final_scope_mismatch:" + key)


def validate_run(declaration, run):
    runtime = adapter()
    return runtime.validate_gate(declaration["review_gate"]["path"], declaration["review_gate"]["sha256"],
                                 runtime=declaration["runtime"], run_directory=run)


def validate_stage(spec, directory):
    runtime = adapter()
    runtime.validate_spec(spec)
    runtime.validate_worker_location(spec, directory)


def validate_acknowledgement(ack, *, spec, directory, math_path):
    from run_sector_last_final import validate_external_review_ack
    return validate_external_review_ack(ack, spec=spec, folder=directory, math_path=math_path)


def terminal_guard(run, terminal_receipt=None):
    declaration, dr = math.read_artifact(run / "campaign_declaration.json")
    scope(declaration)
    reports = Path(declaration["output_root"]).resolve()
    target = Path(terminal_receipt).resolve() if terminal_receipt else reports / "terminal_receipt.json"
    if target != reports / "terminal_receipt.json" or run.is_relative_to(reports) or reports.is_relative_to(run):
        raise ValueError("separate_declared_last_final_terminal_required")
    summary, sr = math.read_artifact(run / "campaign_summary.json")
    terminal, tr = math.read_artifact(target)
    if (summary.get("purpose") != PURPOSE or terminal.get("purpose") != PURPOSE
            or summary.get("status") not in {"stopped", "attempt_sequence_finished"}
            or terminal.get("status") not in {"stopped_semantic_review_pending", "completed_semantic_review_pending"}
            or (summary["status"] == "attempt_sequence_finished") != (terminal["status"] == "completed_semantic_review_pending")):
        raise ValueError("terminal_last_final_campaign_required")
    if (Path(declaration["run_directory"]).resolve() != run or Path(terminal["run_directory"]).resolve() != run
            or Path(terminal["output_root"]).resolve() != reports
            or not completion.same_ref(terminal.get("declaration_ref"), dr)
            or not completion.same_ref(terminal.get("summary_ref"), sr)):
        raise ValueError("last_final_terminal_binding_mismatch")
    if (summary.get("case_order") != list(CASES) or summary.get("stage_order") != list(STAGE_ORDER)
            or [row.get("case_id") for row in summary.get("cases", [])] != list(CASES)):
        raise ValueError("one_control_final_slot_required")
    count = summary.get("generation_requests_attempted")
    if type(count) is not int or count not in (0, 1):
        raise ValueError("last_final_request_limit")
    for value in (summary, terminal):
        for key, wanted in (("generation_requests_attempted", count), ("automatic_retries", 0), ("main_model_calls", 0)):
            if type(value.get(key)) is not int or value[key] != wanted:
                raise ValueError("last_final_terminal_count_mismatch:" + key)
    if campaign.timestamp(terminal["at_utc"]) < campaign.timestamp(summary["at_utc"]):
        raise ValueError("last_final_terminal_predates_summary")
    return declaration, summary, [dr, sr, tr]


def authority(declaration, run, refs):
    loaded = {}
    for key in ("freeze_ref", "review_gate", "runtime_ref", "protocol_ref", *BOUND):
        if key == "prior_remaining_cancel_ref":
            reference = declaration[key]
            campaign.unchanged([reference])
            loaded[key] = None  # CANCEL is a byte artifact, not necessarily JSON.
        else:
            loaded[key], reference = campaign.checked(declaration[key])
        refs.append(reference)
    frozen, protocol, gate = (loaded[k] for k in ("freeze_ref", "protocol_ref", "review_gate"))
    for value in (frozen, protocol, gate):
        scope(value)
    if (protocol.get("status") != "approved_design_for_prospective_last_final_freeze"
            or frozen.get("status") != "frozen_for_pilot_last_final_only"
            or gate.get("status") != "approved_for_last_final_before_generation"
            or protocol.get("raw_diagnostics_required") is not True
            or protocol.get("primary_final_allocation_endpoint") != "F0_derived_integer_allocation"
            or not completion.same_ref(protocol.get("exact_math_policy_ref"), declaration["finalizer_acceptance_ref"])):
        raise ValueError("approved_last_final_authority_required")
    for value in (frozen, gate):
        for key in ("runtime_ref", "protocol_ref", *BOUND, *previous.EXTERNAL_GROUPS, "power_policy"):
            if value.get(key) != declaration.get(key):
                raise ValueError("last_final_authority_ref_differs:" + key)
        if (Path(value["run_directory"]).resolve() != run
                or Path(value["output_root"]).resolve() != Path(declaration["output_root"]).resolve()):
            raise ValueError("last_final_authority_locations_differ")
    for key in (*previous.EXTERNAL_GROUPS, "power_policy"):
        if protocol.get(key) != declaration.get(key):
            raise ValueError("last_final_protocol_operating_refs_differ")
    if gate.get("freeze_ref") != declaration["freeze_ref"] or declaration["runtime"] != loaded["runtime_ref"]:
        raise ValueError("last_final_runtime_or_freeze_differs")
    started, er = math.read_artifact(run / "execution_started.json")
    refs.append(er)
    if not (campaign.timestamp(protocol["recorded_at_utc"]) <= campaign.timestamp(frozen["recorded_at_utc"])
            <= campaign.timestamp(gate["recorded_at_utc"]) <= campaign.timestamp(declaration["created_at_utc"])
            <= campaign.timestamp(started["at_utc"])):
        raise ValueError("prospective_last_final_chronology_required")
    code = frozen.get("code_refs", [])
    if len({str(Path(r["path"]).resolve()) for r in code}) != len(code):
        raise ValueError("duplicate_frozen_last_final_source")
    for file in [Path(m.__file__) for m in (math, campaign, completion, previous)] + [Path(__file__)]:
        expected = {"path": str(file.resolve()), "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}
        if sum(completion.same_ref(r, expected) for r in code) != 1:
            raise ValueError("all_five_finalizer_sources_must_be_frozen")
    refs.extend(code)
    campaign.unchanged(refs)
    validate_run(declaration, run)
    return protocol


def historical_dataset(declaration, protocol, refs):
    old, sr = campaign.checked(declaration["prior_remaining_summary_ref"])
    terminal, tr = campaign.checked(declaration["prior_remaining_terminal_ref"])
    decl, dr = campaign.checked(declaration["prior_remaining_declaration_ref"])
    old_run = Path(sr["path"]).resolve().parent
    pattern = [[(s.get("stage"), s.get("status"), s.get("generation_requests_attempted"))
                for s in row.get("stages", [])] for row in old.get("cases", [])]
    if (old.get("status") != "stopped" or old.get("generation_requests_attempted") != 4
            or pattern != [[("F0", "completed", 1)], [("D0", "completed", 1), ("F0", "completed", 1)], [("D0", "completed", 1)]]
            or not completion.same_ref(terminal.get("summary_ref"), sr)
            or not completion.same_ref(terminal.get("declaration_ref"), dr)
            or not completion.same_ref(decl.get("review_gate"), declaration["prior_remaining_gate_ref"])
            or campaign.timestamp(terminal["at_utc"]) > campaign.timestamp(protocol["recorded_at_utc"])):
        raise ValueError("fixed_four_request_paused_remaining_history_required")
    for key in previous.BOUND:
        if key not in ("runtime_ref", "protocol_ref") and decl.get(key) != declaration.get(key):
            raise ValueError("last_final_prior_history_ref_changed:" + key)
    prior = previous.finalize_remaining(old_run, tr["path"])
    if (prior["remaining_generation_requests"] != 4 or prior["all_generation_requests_including_interrupted_attempt"] != 10
            or len(prior["all_attempt_ledger"]) != 10):
        raise ValueError("exact_ten_historical_attempts_required")
    missing = [row for row in prior["stage_records"] if row["case_id"] == CASE and row["stage"] == "F0"]
    if len(missing) != 1 or missing[0]["status"] != "unavailable" or missing[0].get("generation_requests_attempted") != 0:
        raise ValueError("only_unattempted_control_final_can_be_added")
    folder = old_run / (CASE + "__D0")
    if (folder / "external_review_ack.json").exists() or (old_run / (CASE + "__F0")).exists():
        raise ValueError("old_control_ACK_or_F0_must_not_be_backfilled")
    evidence = declaration["external_draft_evidence_refs"]
    required = {"stage_review", "allocation_math", "semantic_review", "semantic_validation", "root_review",
                "terminal", "summary", "declaration", "final_construction"}
    if set(evidence) != required:
        raise ValueError("exact_late_review_reconciliation_evidence_required")
    values = {}
    for key, reference in evidence.items():
        values[key], rr = campaign.checked(reference)
        refs.append(rr)
    for short, full in (("terminal", "prior_remaining_terminal_ref"), ("summary", "prior_remaining_summary_ref"),
                        ("declaration", "prior_remaining_declaration_ref")):
        if not completion.same_ref(evidence[short], declaration[full]):
            raise ValueError("late_review_history_binding_mismatch")
    spec, spec_ref = math.read_artifact(folder / "worker_spec.json")
    transport_ref = math.read_artifact(folder / "transport_result.json")[1]
    semantic = values["semantic_review"]
    if (semantic.get("review_status") != "completed" or semantic.get("case_id") != CASE or semantic.get("stage") != "D0"
            or not completion.same_ref(semantic.get("transport_ref"), transport_ref)):
        raise ValueError("actual_control_D0_semantic_review_required")
    if not (campaign.timestamp(terminal["at_utc"]) <= campaign.timestamp(semantic["completed_at_utc"])
            <= campaign.timestamp(protocol["recorded_at_utc"])):
        raise ValueError("explicit_after_terminal_review_before_new_protocol_required")
    for axis in ("errors", "consistency", "paper_topic"):
        item = semantic.get("review_axes", {}).get(axis, {})
        if item.get("reviewed") is not True or not isinstance(item.get("reason"), str) or not item["reason"].strip():
            raise ValueError("late_semantic_review_axes_incomplete")
    if (not completion.same_ref(evidence["stage_review"], math.read_artifact(folder / "stage_review.json")[1])
            or values["allocation_math"] != math.finalize_stage(folder)):
        raise ValueError("carried_control_review_or_math_differs")
    refs.extend([sr, tr, dr, spec_ref, transport_ref, *prior["input_refs"]])
    return prior, {"status": "completed_after_prior_terminal_without_backfilled_ACK",
        "case_id": CASE, "stage": "D0", "prior_terminal_ref": tr,
        "semantic_review_ref": evidence["semantic_review"], "semantic_validation_ref": evidence["semantic_validation"],
        "root_review_ref": evidence["root_review"], "old_ACK_created": False,
        "prior_terminal_and_original_ACK_gap_preserved": True, "outcome_success_required": False}


def own_history(run, case, spec, declaration, refs):
    if case != CASE or spec.get("stage") != "F0":
        raise ValueError("only_control_F0_history_allowed")
    names = {"response": "http_0001_generation/response.json", "worker_spec": "worker_spec.json",
             "worker_summary": "worker_summary.json", "supervisor_result": "supervisor_result.json",
             "transport_result": "transport_result.json"}
    if set(declaration["external_draft_refs"]) != set(names):
        raise ValueError("five_control_draft_artifacts_required")
    old_decl, _ = campaign.checked(declaration["prior_remaining_declaration_ref"])
    folder = Path(old_decl["run_directory"]).resolve() / (CASE + "__D0")
    records = {}
    for key, filename in names.items():
        records[key], reference = campaign.checked(declaration["external_draft_refs"][key])
        if Path(reference["path"]).resolve() != folder / filename:
            raise ValueError("external_control_D0_path_substitution")
        refs.append(reference)
    final, fr = campaign.checked(declaration["external_draft_evidence_refs"]["final_construction"])
    refs.append(fr)
    raw, messages = records["response"]["message"]["content"], spec.get("body", {}).get("messages")
    if (spec.get("draft_artifacts") != declaration["external_draft_refs"] or spec.get("raw_draft") != raw
            or final.get("ready") is not True or messages != final.get("messages")
            or len(messages) != 4 or messages[:2] != records["worker_spec"]["body"]["messages"]
            or messages[2] != {"role": "assistant", "content": raw}):
        raise ValueError("last_final_exact_external_own_D0_history_mismatch")


def final_stage(run, declaration, summary, refs):
    records = summary["cases"][0].get("stages", [])
    if [r.get("stage") for r in records] not in ([], ["F0"]):
        raise ValueError("only_one_final_record_allowed")
    folder = run / STAGE_ORDER[0]
    expected_dirs = {STAGE_ORDER[0]} if records else set()
    if {p.name for p in run.iterdir() if p.is_dir()} != expected_dirs:
        raise ValueError("unaccounted_last_final_stage_directory")
    if not records:
        if summary["status"] != "stopped" or summary["generation_requests_attempted"] != 0:
            raise ValueError("missing_final_requires_zero_request_stop")
        return {"case_id": CASE, "stage": "F0", "status": "unavailable", "rows": [],
                "reasons": ["not_attempted"], "generation_requests_attempted": 0, "run_directory": str(run)}, None
    spec, sr = math.read_artifact(folder / "worker_spec.json")
    if spec.get("runtime") != declaration["runtime"] or spec.get("review_gate") != declaration["review_gate"]:
        raise ValueError("last_final_stage_authority_differs")
    validate_stage(spec, folder)
    own_history(run, CASE, spec, declaration, refs)
    item = math.finalize_stage(folder)
    count = records[0].get("generation_requests_attempted")
    if (type(count) is not int or count not in (0, 1) or item["generation_requests_attempted"] != count
            or item["observed_transport_status"] != records[0].get("status") or summary["generation_requests_attempted"] != count):
        raise ValueError("last_final_stage_count_mismatch")
    result = {"case_id": CASE, "stage": "F0", "status": "unavailable_or_invalid", "outcome_success_required": False}
    math_path = Path(declaration["output_root"]).resolve() / "allocation_math" / (folder.name + ".json")
    try:
        ack, ar = math.read_artifact(folder / "external_review_ack.json")
        validated = validate_acknowledgement(ack, spec=spec, directory=folder, math_path=math_path)
        saved, mr = math.read_artifact(math_path)
        if saved != item:
            raise ValueError("last_final_saved_math_differs")
        refs.extend([ar, mr])
        for key in ("worker_spec_ref", "transport_ref", "stage_review_ref", "allocation_math_ref", "semantic_review_ref"):
            refs.append(campaign.checked(ack[key])[1])
        result.update(validated, acknowledgement_ref=ar)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result["reason"] = type(error).__name__ + ": " + str(error)
        if summary["status"] == "attempt_sequence_finished":
            raise ValueError("normal_last_final_finish_requires_completed_review_ACK") from error
    refs.extend([sr, *item["input_refs"]])
    item["run_directory"] = str(run)
    return item, result


def finalize_last_final(run_dir, terminal_receipt=None):
    run = Path(run_dir).resolve()
    declaration, summary, refs = terminal_guard(run, terminal_receipt)
    protocol = authority(declaration, run, refs)
    prior, reconciliation = historical_dataset(declaration, protocol, refs)
    final, ack = final_stage(run, declaration, summary, refs)
    attempts = final["generation_requests_attempted"]
    for key, expected in (("max_generation_requests", 1), ("historical_generation_requests", 10),
                          ("campaign_generation_requests_attempted", 10 + attempts), ("campaign_max_generation_requests", 11),
                          ("post_final_calls", 0), ("original_planned_final_cells", 5), ("segment_planned_final_cells", 1)):
        if type(summary.get(key)) is not int or summary[key] != expected:
            raise ValueError("last_final_summary_count_mismatch:" + key)
    selected = [dict(final, selection_role="fixed_last_unattempted_control_final")
                if r["case_id"] == CASE and r["stage"] == "F0" else dict(r) for r in prior["stage_records"]]
    ledger = [dict(r) for r in prior["all_attempt_ledger"]]
    if any(r["case_id"] == CASE and r["stage"] == "F0" for r in ledger):
        raise ValueError("control_final_was_previously_attempted")
    if attempts:
        ledger.append({"campaign_request_ordinal": 11, "segment": "last_final", "case_id": CASE, "stage": "F0",
                       "logical_slot_attempt": 1, "observed_transport_status": final["observed_transport_status"],
                       "input_refs": final.get("input_refs", [])})
    campaign.unchanged(refs)
    return {"version": VERSION, "purpose": "primary_exploratory_last_final_dataset", "analysis_role": "primary_exploratory",
            "not_prespecified_original_experiment": True, "case_order": list(campaign.PILOT),
            "planned_final_allocations": 5, "planned_final_sector_rows": 55, "logical_stage_slots": 10,
            "segment_case_order": list(CASES), "segment_planned_final_allocations": 1, "segment_planned_stage_slots": 1,
            "segment_stage_order": list(STAGE_ORDER), "original_generation_requests": 3,
            "prior_continuation_generation_requests": 2, "completion_generation_requests": 1,
            "remaining_generation_requests": 4, "last_final_generation_requests": attempts,
            "all_generation_requests_including_interrupted_attempt": len(ledger), "campaign_max_generation_requests": 11,
            "all_attempt_ledger": ledger, "prior_remaining_derived_report": prior, "stage_records": selected,
            "last_final_stage_records": [final], "external_review_reconciliation": reconciliation,
            "external_review_acknowledgements": [] if ack is None else [ack],
            "external_draft_refs": declaration["external_draft_refs"], "external_draft_evidence_refs": declaration["external_draft_evidence_refs"],
            "derived_comparisons": campaign.pairs(selected, campaign.PILOT),
            "finalized_finals": sum(r["stage"] == "F0" and r["status"] == "finalized" for r in selected),
            "primary_final_allocation_endpoint": "F0_derived_integer_allocation", "raw_diagnostics_required": True,
            "input_refs": refs, "generation_calls": 0, "service_calls": 0, "main_model_calls": 0,
            "historical_failed_attempt_erased": False, "raw_artifacts_modified": False, "missing_finals_replaced": False,
            "semantic_review_status": "not_performed_by_finalizer",
            "limits": ["Five logical cases across five operational segments, including two exact external own-D0 handoffs.",
                       "The previous control draft review was completed after its stopped terminal; no prior ACK is backfilled.",
                       "Raw/model errors and all attempts remain; final100% arithmetic is not semantic or causal success.",
                       "Study role, math endpoint and operational resumptions were amended after observed outputs."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--terminal-receipt", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    declaration = math.read_artifact(args.run_dir / "campaign_declaration.json")[0]
    roots = [args.run_dir.resolve()] + [Path(declaration[k]["path"]).resolve().parent for k in
        ("historical_summary_ref", "prior_continuation_summary_ref", "prior_completion_summary_ref", "prior_remaining_summary_ref")]
    target = args.output.resolve()
    if target.exists() or any(target.is_relative_to(root) for root in roots):
        parser.error("New result outside all five immutable raw runs required")
    result = finalize_last_final(args.run_dir, args.terminal_receipt)
    result["created_at_utc"] = datetime.now(timezone.utc).isoformat()
    encoded = json.dumps(result, ensure_ascii=True, allow_nan=False, indent=2) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded)
    print(json.dumps({"output": str(target), "finalized_finals": result["finalized_finals"],
                      "all_attempts": len(result["all_attempt_ledger"]), "generation_calls": 0}))


if __name__ == "__main__":
    main()
