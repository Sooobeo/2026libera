"""Offline one-output review copies after an entire continuation/main campaign ends.

This adapter validates the explicit campaign runtime and accounting, then reuses
only the frozen builder's rubric, text extraction and final-visible evidence
helpers. It never changes globals in an old module and never calls a service.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import secrets
import uuid

import build_v494_masked_review as original
import finalize_sector_campaign as campaign

ROOT = Path(__file__).resolve().parents[1]
VERSION = "campaign_masked_review_1"
RUNTIMES = {"pilot_continuation": "sector_continuation_runtime", "main": "sector_main_runtime"}


def read(path):
    return original.read(path)


def ref(path):
    return original.ref(path)


def resolve_reference(reference):
    path = Path(reference["path"])
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def same_ref(reference, expected):
    return (isinstance(reference, dict) and set(reference) == {"path", "sha256"}
            and resolve_reference(reference) == Path(expected).resolve()
            and reference["sha256"] == ref(expected)["sha256"])


def checked(reference):
    path = resolve_reference(reference)
    if not same_ref(reference, path):
        raise ValueError("Artifact hash mismatch")
    return read(path)


def runtime_module(purpose):
    if purpose not in RUNTIMES:
        raise ValueError("Explicit main or pilot_continuation purpose required")
    return importlib.import_module(RUNTIMES[purpose])


def validate_run(declaration, run, purpose):
    runtime = runtime_module(purpose)
    runtime.validate_runtime(declaration["runtime"])
    runtime.validate_gate(declaration["review_gate"]["path"], declaration["review_gate"]["sha256"],
                          runtime=declaration["runtime"], run_directory=run)


def validate_stage(spec, folder, purpose):
    runtime = runtime_module(purpose)
    runtime.validate_spec(spec)
    runtime.validate_worker_location(spec, folder)


def campaign_accounting(run):
    # This computes deterministic sidecars in memory as a consequence of reusing
    # the accepted artifact/accounting validator. None is sent to a judge.
    return campaign.finalize_campaign(run)


def locations(run, output, mapping):
    run, output, mapping = [Path(p).resolve() for p in (run, output, mapping)]
    for left, right in ((run, output), (run, mapping), (output, mapping)):
        if left.is_relative_to(right) or right.is_relative_to(left):
            raise ValueError("Raw, judge and private mapping trees must be separate")
    if output.exists() or mapping.exists():
        raise FileExistsError("Review output paths must be new")
    return run, output, mapping


def terminal_guard(run, terminal_path, purpose):
    """Only metadata is read here, before any response or accounting traversal."""
    if purpose not in RUNTIMES:
        raise ValueError("Explicit campaign purpose required")
    summary_path, declaration_path = run / "campaign_summary.json", run / "campaign_declaration.json"
    terminal_path = Path(terminal_path).resolve()
    if not summary_path.is_file() or not terminal_path.is_file():
        raise ValueError("Both terminal summary and terminal receipt required; no live output reading")
    summary, terminal, declaration = read(summary_path), read(terminal_path), read(declaration_path)
    cases = campaign.PILOT[1:] if purpose == "pilot_continuation" else campaign.MAIN
    if any(value.get("purpose") != purpose for value in (summary, terminal, declaration)):
        raise ValueError("Requested campaign purpose differs from terminal records")
    if (summary.get("status") not in {"stopped", "attempt_sequence_finished"}
            or terminal.get("status") not in {"stopped_semantic_review_pending", "completed_semantic_review_pending"}
            or (summary["status"] == "attempt_sequence_finished") != (terminal["status"] == "completed_semantic_review_pending")):
        raise ValueError("An entire terminal attempt sequence is required")
    if (summary.get("case_order") != list(cases) or declaration.get("case_order") != list(cases)
            or [r.get("case_id") for r in summary.get("cases", [])] != list(cases)):
        raise ValueError("Full planned campaign denominator required")
    report_root = Path(declaration["output_root"]).resolve()
    if terminal_path != report_root / "terminal_receipt.json":
        raise ValueError("Terminal receipt must be in this campaign's declared report tree")
    if (Path(declaration["run_directory"]).resolve() != run
            or Path(terminal["run_directory"]).resolve() != run
            or Path(terminal["output_root"]).resolve() != report_root
            or not same_ref(terminal.get("summary_ref"), summary_path)
            or not same_ref(terminal.get("declaration_ref"), declaration_path)):
        raise ValueError("Terminal receipt does not bind this exact declaration and summary")
    attempts = summary.get("generation_requests_attempted")
    if (type(attempts) is not int or not 0 <= attempts <= len(cases) * 2
            or type(terminal.get("generation_requests_attempted")) is not int
            or terminal["generation_requests_attempted"] != attempts):
        raise ValueError("Terminal request accounting differs")
    for record in (summary, terminal):
        if (type(record.get("automatic_retries")) is not int or record["automatic_retries"] != 0
                or type(record.get("main_model_calls")) is not int
                or record["main_model_calls"] != (attempts if purpose == "main" else 0)):
            raise ValueError("Terminal scope or retry accounting differs")
    if campaign.timestamp(terminal["at_utc"]) < campaign.timestamp(summary["at_utc"]):
        raise ValueError("Terminal receipt predates its summary")
    return declaration, summary, cases, [ref(declaration_path), ref(summary_path), ref(terminal_path)]


def inspect_stage(run, case, stage, record, expected_draft, purpose):
    folder = run / (case + "__" + stage)
    if record is None:
        if folder.exists():
            raise ValueError("Unaccounted stage directory")
        return {"status": "not_attempted", "generation_requests_attempted": 0, "text": None,
                "text_state": "no_recorded_content", "response_artifact_bound": False,
                "normal_generation_completed": False, "spec": None, "input_refs": []}
    spec_path, transport_path = folder / "worker_spec.json", folder / "transport_result.json"
    spec, transport = read(spec_path), read(transport_path)
    if spec.get("case_id") != case or spec.get("stage") != stage or Path(spec["run_directory"]).resolve() != run:
        raise ValueError("Stage execution identity differs")
    validate_stage(spec, folder, purpose)
    if spec["body"]["messages"][:2] != expected_draft:
        raise ValueError("Stage initial history differs from frozen own input")
    count = record.get("generation_requests_attempted")
    if (type(count) is not int or count not in (0, 1)
            or type(transport.get("generation_requests_attempted")) is not int
            or transport["generation_requests_attempted"] != count
            or transport.get("status") != record.get("status")):
        raise ValueError("Stage transport and summary accounting disagree")
    generations = list(folder.glob("http_*_generation"))
    if len(generations) > 1 or any(p.name != "http_0001_generation" for p in generations) or (count == 0 and generations):
        raise ValueError("Extra or undeclared generation evidence")
    response_path = folder / "http_0001_generation/response.json"
    bound, normal = False, False
    if response_path.exists():
        declared = transport.get("response_artifact")
        bound = same_ref(declared, response_path)
        if not bound and (declared is not None or transport["status"] == "completed"):
            raise ValueError("Saved response differs from bound transport")
        if bound:
            response = read(response_path)
            if response != transport.get("response"):
                raise ValueError("Saved response and transport envelope differ")
            normal = (count == 1 and transport["status"] in {"completed", "model_structure_failure"}
                      and response.get("done") is True and response.get("done_reason") == "stop")
    if transport["status"] == "completed" and not normal:
        raise ValueError("Completed transport lacks a bound normally stopped response")
    content = original.extract_text(folder)
    if response_path.exists() and not bound:
        content["text_state"] = "unbound_saved_response_content_after_interruption"
    private_refs = [ref(p) for p in sorted(folder.glob("*.json")) if p.is_file()]
    return {"status": record["status"], "generation_requests_attempted": count, **content,
            "response_artifact_bound": bound, "normal_generation_completed": normal,
            "spec": spec, "input_refs": private_refs + content["artifacts"]}


def submission(stage, *, prior=False):
    return {"status": stage["status"], "text_state": stage["text_state"],
            "text_file": ("prior.txt" if prior else "final.txt") if stage["text"] is not None else None,
            "saved_response_is_bound": stage["response_artifact_bound"],
            "normal_generation_completed": stage["normal_generation_completed"],
            "partial_or_unbound_diagnostic_only": stage["text"] is not None and not stage["normal_generation_completed"],
            "availability_limit": "A partial, failed or unbound response is a diagnostic, never a completed replacement final. Normal transport is not schema or semantic success.",
            **({"scope": "Own process evidence only; never an independent observation or substitute final."} if prior else {})}


def build(run_dir, terminal_receipt, output_dir, mapping_dir, *, purpose):
    run, output, mapping = locations(run_dir, output_dir, mapping_dir)
    declaration, summary, cases, terminal_refs = terminal_guard(run, terminal_receipt, purpose)
    report_root = Path(declaration["output_root"]).resolve()
    # A judge tree must never contain private operating/evaluation metadata.
    if output.is_relative_to(report_root) or report_root.is_relative_to(output):
        raise ValueError("Judge tree must be separate from private campaign reports")
    validate_run(declaration, run, purpose)
    accounting = campaign_accounting(run)
    if (accounting.get("purpose") != purpose or accounting.get("case_order") != list(cases)
            or accounting.get("generation_requests_attempted") != summary["generation_requests_attempted"]
            or accounting.get("planned_final_allocations") != len(cases)
            or accounting.get("planned_stage_slots") != 2 * len(cases)):
        raise ValueError("Validated campaign accounting differs")
    evaluation_ref = ref(original.EVALUATION)
    if evaluation_ref["sha256"] != original.EVALUATION_SHA:
        raise ValueError("Original r2 evaluation bytes changed")
    evaluation = read(original.EVALUATION)
    manifest_ref = declaration["prepared_manifest_ref"]
    manifest = checked(manifest_ref)
    prepared = {row["case_id"]: row for row in manifest["prepared_cases"]}
    allowed_prepared = campaign.PILOT if purpose == "pilot_continuation" else campaign.MAIN
    if len(prepared) != len(manifest["prepared_cases"]) or set(prepared) != set(allowed_prepared):
        raise ValueError("Frozen preparation inventory differs")
    items, private_rows, all_refs, total = [], [], terminal_refs + [evaluation_ref, ref(resolve_reference(manifest_ref))], 0
    for row in summary["cases"]:
        case = row["case_id"]
        stage_rows = row.get("stages", [])
        if [r.get("stage") for r in stage_rows] not in ([], ["D0"], ["D0", "F0"]):
            raise ValueError("Unexpected stage order")
        records = {r["stage"]: r for r in stage_rows}
        draft_ref = {key: prepared[case][key] for key in ("path", "sha256")}
        expected_draft = checked(draft_ref)
        all_refs.append(ref(resolve_reference(draft_ref)))
        draft = inspect_stage(run, case, "D0", records.get("D0"), expected_draft, purpose)
        final = inspect_stage(run, case, "F0", records.get("F0"), expected_draft, purpose)
        total += draft["generation_requests_attempted"] + final["generation_requests_attempted"]
        evidence = None
        if final["generation_requests_attempted"] == 1:
            if draft["text"] is None or not draft["normal_generation_completed"]:
                raise ValueError("Attempted final lacks its normally completed actual own draft")
            evidence = original.visible_final_evidence(final["spec"], draft["text"], expected_draft)
        item_id = uuid.uuid4().hex
        item = {"item_id": item_id, "rubric": "../rubric.json", "masking_notice": original.MASKING_NOTICE,
                "final_submission": submission(final), "own_prior_submission": submission(draft, prior=True),
                "supplied_final_evidence": evidence,
                "evidence_delivery_scope": "Recorded input of the attempted final; failed-request consumption is not inferred." if evidence is not None else "No final generation request recorded; no final evidence represented as supplied.",
                "missing_final_rule": "A missing final is unobserved, never zero-scored or replaced by a draft.",
                "raw_claim_review_scope": "Judge exact raw claims and own prior changes against supplied evidence. No externally computed portfolio is supplied as evidence for those claims."}
        items.append((item_id, item, draft["text"], final["text"]))
        private_rows.append({"item_id": item_id, "case_id": case, "case_status": row.get("status"),
                             "stages": {name: {key: value for key, value in item.items() if key not in {"spec", "text"}}
                                        for name, item in (("D0", draft), ("F0", final))}})
        all_refs.extend(draft["input_refs"] + final["input_refs"])
    if total != summary["generation_requests_attempted"]:
        raise ValueError("All planned stage accounting differs")
    all_refs.extend(accounting["input_refs"])
    campaign.unchanged(all_refs)
    # All validation is complete before creating output directories.
    secrets.SystemRandom().shuffle(items)
    output.mkdir(parents=True)
    mapping.mkdir(parents=True)
    original.write_json(output / "rubric.json", original.review_rubric(evaluation))
    for item_id, item, prior_text, final_text in items:
        folder = output / item_id
        folder.mkdir()
        original.write_json(folder / "item.json", item)
        for name, text in (("prior.txt", prior_text), ("final.txt", final_text)):
            if text is not None:
                with (folder / name).open("x", encoding="utf-8", newline="") as stream:
                    stream.write(text)
    index = {"bundle_version": VERSION, "items": [item[0] for item in items],
             "planned_final_submissions": len(cases), "planned_final_sector_rows": 11 * len(cases),
             "instruction": "Read one item at a time. Do not rank conditions or choose a winning answer.",
             "masking_notice": original.MASKING_NOTICE, "scoring_performed": False,
             "independent_human_review_completed": False}
    original.write_json(output / "index.json", index)
    receipt = {"version": VERSION, "status": "completed_offline_packaging_only",
               "created_at_utc": datetime.now(timezone.utc).isoformat(), "purpose": purpose,
               "model_generation_calls": 0, "service_calls": 0, "script_ref": ref(__file__),
               "helper_ref": ref(original.__file__), "campaign_validator_ref": ref(campaign.__file__),
               "source_terminal_refs": terminal_refs, "evaluation_ref": evaluation_ref,
               "planned_final_submissions": len(cases), "planned_stage_slots": 2 * len(cases),
               "actual_generation_requests": total, "mapping": private_rows,
               "accounting_and_derived_diagnostics_private_only": accounting,
               "endpoint_amendment_private_only": "Prospective main operational allocation is derived F0; raw claims retain the unchanged original r2 semantic dimensions. The amendment and derived vectors are deliberately absent from judge evidence.",
               "source_refs": all_refs,
               "judge_artifacts": [ref(p) for p in sorted(output.rglob("*")) if p.is_file()],
               "limitations": [original.MASKING_NOTICE, "Unvalidated AI-assisted descriptive review; no independent human, statistical-rater reliability or balanced independent sample claim.",
                               "Raw output may itself reveal a condition; verbatim text is not redacted or corrected.",
                               "Packaging a stopped campaign preserves failures and missing finals; it does not establish main readiness or semantic success."]}
    campaign.unchanged(all_refs)
    original.write_json(mapping / "private_mapping.json", receipt)
    original.write_json(output / "COMPLETE.json", {"status": "complete", "items": len(cases), "scoring_performed": False})
    return {"status": receipt["status"], "items": len(cases), "model_generation_calls": 0,
            "service_calls": 0, "output_dir": str(output), "mapping_dir": str(mapping)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run-dir", "terminal-receipt", "output-dir", "mapping-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--purpose", choices=tuple(RUNTIMES), required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.run_dir, args.terminal_receipt, args.output_dir, args.mapping_dir, purpose=args.purpose)))


if __name__ == "__main__":
    main()
