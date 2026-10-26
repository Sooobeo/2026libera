"""Manifest-bound allocation sidecars for continuation and prospective main runs.

Original pilot artifacts and the original pilot finalizer remain immutable.
An explicit continuation completion dataset retains the failed historical attempt
and labels its selected cross-segment rows; it is not a first-attempt replication.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import finalize_sector_allocation as math

VERSION = "sector_campaign_finalizer_1"
PILOT = ("fidelity_q2_2026__E", "fidelity_q2_2026__L", "ubs_june_2026__E",
         "ubs_june_2026__L", "common_market_only__C")
MAIN = ("fidelity_q3_2026__E", "fidelity_q3_2026__L", "ubs_july_2026__E",
        "ubs_july_2026__L", "common_market_only__C")


def checked(reference):
    if (not isinstance(reference, dict) or set(reference) != {"path", "sha256"}
            or not isinstance(reference.get("path"), str) or not reference["path"]
            or not isinstance(reference.get("sha256"), str) or len(reference["sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in reference["sha256"])):
        raise ValueError("artifact_reference_required")
    value, actual = math.read_artifact(reference["path"])
    if actual["sha256"] != reference.get("sha256"):
        raise ValueError("artifact_hash_mismatch:" + reference["path"])
    return value, actual


def unchanged(references):
    for reference in references:
        if hashlib.sha256(Path(reference["path"]).read_bytes()).hexdigest() != reference["sha256"]:
            raise ValueError("artifact_changed_during_finalization:" + reference["path"])


def scope(value, purpose, cases, *, require_observed=True):
    if (not isinstance(value, dict) or value.get("purpose") != purpose
            or value.get("case_order") != list(cases)):
        raise ValueError("campaign_scope_binding_mismatch")
    expected = {"max_generation_requests": len(cases) * 2, "automatic_retries": 0}
    if purpose == "pilot_continuation":
        expected.update(historical_generation_requests=3, campaign_max_generation_requests=11)
        if (value.get("main_allowed") is not False
                or value.get("old_outputs_observed", not require_observed) is not True
                or value.get("explicit_retry_slots") != [PILOT[1] + "__D0"]):
            raise ValueError("explicit_continuation_scope_required")
    elif value.get("main_allowed") is not True:
        raise ValueError("explicit_main_scope_required")
    for key, number in expected.items():
        if type(value.get(key)) is not int or value[key] != number:
            raise ValueError("campaign_scope_accounting_mismatch:" + key)


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("prospective_timestamp_required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone_aware_prospective_timestamp_required")
    return parsed


def pairs(rows, cases):
    lookup = {(r["case_id"], r["stage"]): r for r in rows}
    def compare(a, b, sa="F0", sb="F0"):
        return math.compare_finalized(lookup[(a, sa)], lookup[(b, sb)])
    return {
        "within_source": [compare(cases[0], cases[1]), compare(cases[2], cases[3])],
        "between_source": [compare(cases[0], cases[2]), compare(cases[1], cases[3])],
        "shared_control": [compare(c, cases[4]) for c in cases[:4]],
        "own_D0_F0": [compare(c, c, "F0", "D0") for c in cases],
    }


def finalize_campaign(run_dir):
    run = Path(run_dir).resolve()
    declaration, dr = math.read_artifact(run / "campaign_declaration.json")
    summary, sr = math.read_artifact(run / "campaign_summary.json")
    if not isinstance(declaration, dict) or not isinstance(summary, dict):
        raise ValueError("campaign_objects_required")
    purpose = declaration.get("purpose")
    cases = PILOT[1:] if purpose == "pilot_continuation" else MAIN if purpose == "main" else ()
    if not cases or declaration.get("case_order") != list(cases):
        raise ValueError("declared_campaign_case_scope_required")
    limit = len(cases) * 2
    scope(declaration, purpose, cases)
    freeze, fr = checked(declaration.get("freeze_ref"))
    protocol, pr = checked(declaration.get("protocol_ref"))
    runtime, rr = checked(declaration.get("runtime_ref"))
    gate, gr = checked(declaration.get("review_gate"))
    started, er = math.read_artifact(run / "execution_started.json")
    refs = [dr, sr, fr, pr, rr, gr, er]
    for value in (freeze, gate):
        scope(value, purpose, cases)
    # The protocol records post-output chronology in prose; executable gate,
    # freeze and declaration must carry the explicit observed-output boolean.
    scope(protocol, purpose, cases, require_observed=False)
    if (declaration.get("runtime") != runtime
            or Path(declaration.get("run_directory", "")).resolve() != run):
        raise ValueError("declaration_runtime_or_run_binding_mismatch")
    for value in (freeze, gate):
        if (value.get("run_directory") != declaration.get("run_directory")
                or value.get("output_root") != declaration.get("output_root")):
            raise ValueError("gate_freeze_output_location_mismatch")
    if not isinstance(declaration.get("output_root"), str) or not declaration["output_root"]:
        raise ValueError("separate_report_root_required")
    report_root = Path(declaration["output_root"]).resolve()
    if run.is_relative_to(report_root) or report_root.is_relative_to(run):
        raise ValueError("separate_report_root_required")
    expected_gate_status = ("approved_for_continuation_before_generation"
                            if purpose == "pilot_continuation" else "approved_for_main_before_generation")
    if (gate.get("status") != expected_gate_status
            or not timestamp(freeze.get("recorded_at_utc")) <= timestamp(gate.get("recorded_at_utc"))
            <= timestamp(declaration.get("created_at_utc")) <= timestamp(started.get("at_utc"))):
        raise ValueError("prospective_approved_gate_required")
    if (gate.get("freeze_ref") != declaration["freeze_ref"]
            or gate.get("protocol_ref") != declaration["protocol_ref"]
            or gate.get("runtime_ref") != declaration["runtime_ref"]):
        raise ValueError("review_gate_declaration_binding_mismatch")
    if purpose == "pilot_continuation":
        for key in ("historical_gate_ref", "historical_terminal_ref", "historical_summary_ref",
                    "prepared_manifest_ref", "finalizer_acceptance_ref"):
            if declaration.get(key) != freeze.get(key) or declaration.get(key) != gate.get(key):
                raise ValueError("historical_reference_binding_mismatch:" + key)
            _, reference = checked(declaration.get(key))
            refs.append(reference)
    if (freeze.get("purpose") != purpose or freeze.get("case_order") != list(cases)
            or freeze.get("max_generation_requests") != limit
            or freeze.get("status") != ("frozen_for_pilot_continuation_only" if purpose == "pilot_continuation" else "frozen_for_main_only")
            or freeze.get("protocol_ref") != declaration["protocol_ref"]
            or freeze.get("runtime_ref") != declaration["runtime_ref"]
            or Path(freeze.get("run_directory", "")).resolve() != run):
        raise ValueError("freeze_declaration_scope_mismatch")
    code_refs = freeze.get("code_refs", [])
    if (not isinstance(code_refs, list) or any(not isinstance(r, dict)
            or set(r) != {"path", "sha256"} or not isinstance(r.get("path"), str)
            or not isinstance(r.get("sha256"), str) for r in code_refs)
            or len({str(Path(r["path"]).resolve()) for r in code_refs}) != len(code_refs)):
        raise ValueError("unique_frozen_code_references_required")
    for path in (Path(__file__).resolve(), Path(math.__file__).resolve()):
        matches = [r for r in code_refs if Path(r.get("path", "")).resolve() == path]
        if len(matches) != 1 or matches[0].get("sha256") != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError("both_finalizer_implementations_must_be_frozen")
    for reference in code_refs:
        path = Path(reference["path"]).resolve()
        refs.append({"path": str(path), "sha256": reference["sha256"]})
    if (summary.get("status") not in ("stopped", "attempt_sequence_finished")
            or summary.get("case_order") != list(cases)
            or [c.get("case_id") for c in summary.get("cases", [])] != list(cases)):
        raise ValueError("terminal_summary_and_full_planned_denominator_required")
    for key in ("automatic_retries", "post_final_calls"):
        if type(summary.get(key)) is not int or summary[key] != 0:
            raise ValueError("no_automatic_retry_or_postfinal_calls:" + key)
    rows, expected_dirs, attempts = [], set(), 0
    for case in summary["cases"]:
        recorded = case.get("stages", [])
        if [r.get("stage") for r in recorded] not in ([], ["D0"], ["D0", "F0"]):
            raise ValueError("unexpected_stage_sequence")
        by_stage = {r["stage"]: r for r in recorded}
        if "F0" in by_stage and by_stage["D0"].get("status") != "completed":
            raise ValueError("F0_requires_completed_own_new_D0")
        for stage in ("D0", "F0"):
            if stage not in by_stage:
                rows.append({"case_id": case["case_id"], "stage": stage, "status": "unavailable",
                             "rows": [], "reasons": ["not_attempted"], "run_directory": str(run)})
                continue
            name = case["case_id"] + "__" + stage
            expected_dirs.add(name)
            item = math.finalize_stage(run / name)
            record = by_stage[stage]
            if (type(record.get("generation_requests_attempted")) is not int
                    or record["generation_requests_attempted"] != item["generation_requests_attempted"]
                    or record.get("status") != item["observed_transport_status"]):
                raise ValueError("summary_transport_accounting_mismatch")
            spec, spec_ref = math.read_artifact(run / name / "worker_spec.json")
            if spec.get("runtime") != runtime or spec.get("review_gate") != declaration["review_gate"]:
                raise ValueError("stage_runtime_differs_from_declaration")
            if stage == "F0":
                draft_dir = run / (case["case_id"] + "__D0")
                draft_spec, dsr = math.read_artifact(draft_dir / "worker_spec.json")
                draft_transport, dtr = math.read_artifact(draft_dir / "transport_result.json")
                draft_response, drr = math.read_artifact(draft_dir / "http_0001_generation/response.json")
                expected_draft_refs = {"worker_spec": dsr, "transport_result": dtr, "response": drr}
                for role, filename in (("worker_summary", "worker_summary.json"),
                                       ("supervisor_result", "supervisor_result.json")):
                    _, reference = math.read_artifact(draft_dir / filename)
                    expected_draft_refs[role] = reference
                actual_draft_refs = spec.get("draft_artifacts")
                raw_draft = draft_response.get("message", {}).get("content")
                draft_messages = draft_spec.get("body", {}).get("messages")
                final_messages = spec.get("body", {}).get("messages")
                if (actual_draft_refs != expected_draft_refs
                        or draft_transport.get("continuation_eligible") is not True
                        or not isinstance(raw_draft, str) or spec.get("raw_draft") != raw_draft
                        or not isinstance(draft_messages, list) or len(draft_messages) != 2
                        or not isinstance(final_messages, list) or len(final_messages) != 4
                        or final_messages[:2] != draft_messages
                        or final_messages[2] != {"role": "assistant", "content": raw_draft}
                        or final_messages[3].get("role") != "user"):
                    raise ValueError("F0_new_D0_history_binding_mismatch")
                refs.extend(expected_draft_refs.values())
            item["run_directory"] = str(run)
            refs.extend(item["input_refs"])
            attempts += item["generation_requests_attempted"]
            rows.append(item)
    if {p.name for p in run.iterdir() if p.is_dir()} != expected_dirs:
        raise ValueError("unaccounted_raw_stage_directory")
    if (type(summary.get("generation_requests_attempted")) is not int
            or summary["generation_requests_attempted"] != attempts or attempts > limit
            or type(summary.get("main_model_calls")) is not int
            or summary["main_model_calls"] != (attempts if purpose == "main" else 0)):
        raise ValueError("campaign_attempt_accounting_mismatch")
    if purpose == "pilot_continuation":
        for key, expected in (("max_generation_requests", 8), ("historical_generation_requests", 3),
                              ("campaign_generation_requests_attempted", 3 + attempts),
                              ("campaign_max_generation_requests", 11),
                              ("original_planned_final_cells", 5), ("segment_planned_final_cells", 4)):
            if type(summary.get(key)) is not int or summary[key] != expected:
                raise ValueError("continuation_summary_accounting_mismatch:" + key)
    unchanged(refs)
    result = {"version": VERSION, "purpose": purpose, "case_order": list(cases),
              "planned_final_allocations": len(cases), "planned_stage_slots": limit,
              "generation_requests_attempted": attempts,
              "finalized_finals": sum(r["stage"] == "F0" and r["status"] == "finalized" for r in rows),
              "stage_records": rows, "input_refs": refs, "generation_calls": 0,
              "missing_finals_replaced": False, "raw_artifacts_modified": False,
              "interpretation": "Derived arithmetic only; raw allocation/citation/semantic errors remain measured outcomes."}
    if purpose == "main":
        result["derived_comparisons"] = pairs(rows, cases)
    return result


def complete_pilot_dataset(run_dir, historical_run):
    segment = finalize_campaign(run_dir)
    if segment["purpose"] != "pilot_continuation":
        raise ValueError("only_explicit_pilot_continuation_can_use_historical_rows")
    declaration, _ = math.read_artifact(Path(run_dir) / "campaign_declaration.json")
    freeze, _ = checked(declaration["freeze_ref"])
    _, expected = checked(freeze.get("historical_summary_ref"))
    old_summary, observed = math.read_artifact(Path(historical_run) / "pilot_summary.json")
    if expected != observed or freeze.get("historical_generation_requests") != 3:
        raise ValueError("historical_run_binding_mismatch")
    original = math.finalize_run(historical_run)
    old_stages = [[(s.get("stage"), s.get("status"), s.get("generation_requests_attempted"))
                   for s in c.get("stages", [])] for c in old_summary["cases"]]
    if (original["first_attempt_requests"] != 3 or original["finalized_finals"] != 1
            or old_stages != [[("D0", "completed", 1), ("F0", "completed", 1)],
                              [("D0", "hard_deadline", 1)], [], [], []]):
        raise ValueError("fixed_interruption_pattern_mismatch")
    retained = [r for r in original["stage_records"] if r["case_id"] == PILOT[0]]
    if len(retained) != 2 or any(r["status"] != "finalized" for r in retained):
        raise ValueError("completed_historical_case_required")
    rows = [{**r, "run_directory": str(Path(historical_run).resolve()),
             "selection_role": "prospectively_retained_completed_case"} for r in retained]
    rows += [{**r, "selection_role": "explicit_continuation_segment"} for r in segment["stage_records"]]
    attempts = original["first_attempt_requests"] + segment["generation_requests_attempted"]
    if attempts > 11 or freeze.get("campaign_max_generation_requests") != 11:
        raise ValueError("combined_request_budget_mismatch")
    historical_refs = [original["run_summary_ref"],
                       *(ref for row in original["stage_records"] for ref in row.get("input_refs", []))]
    unchanged([expected, *segment["input_refs"], *historical_refs])
    return {"version": VERSION, "purpose": "continuation_completion_dataset",
            "not_the_original_first_attempt_pilot": True, "case_order": list(PILOT),
            "planned_final_allocations": 5, "planned_stage_slots_in_completion_dataset": 10,
            "all_generation_requests_including_interrupted_attempt": attempts,
            "original_generation_requests": 3, "continuation_generation_requests": segment["generation_requests_attempted"],
            "explicit_infrastructure_retry_slot": PILOT[1] + "__D0",
            "original_first_attempt_derived_report": original, "continuation_derived_report": segment,
            "stage_records": rows, "derived_comparisons": pairs(rows, PILOT),
            "finalized_finals": sum(r["stage"] == "F0" and r["status"] == "finalized" for r in rows),
            "generation_calls": 0, "historical_failed_attempt_erased": False,
            "raw_artifacts_modified": False, "missing_finals_replaced": False,
            "limits": ["Cross-segment comparisons are descriptive and disclose the interruption and retry.",
                       "Old raw evaluation remains a separate1/5-final first-attempt result.",
                       "Exact100% arithmetic is not evidence of source fidelity or causal identification."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--historical-run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    for raw in (args.run_dir, args.historical_run):
        if raw and output.is_relative_to(raw.resolve()):
            parser.error("Derived output must remain outside every immutable raw run")
    result = (complete_pilot_dataset(args.run_dir, args.historical_run) if args.historical_run
              else finalize_campaign(args.run_dir))
    result["created_at_utc"] = datetime.now(timezone.utc).isoformat()
    encoded = (json.dumps(result, ensure_ascii=True, allow_nan=False, indent=2) + "\n").encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as handle:
        handle.write(encoded)
    print(json.dumps({"output": str(output), "finalized_finals": result["finalized_finals"], "generation_calls": 0}))


if __name__ == "__main__":
    main()
