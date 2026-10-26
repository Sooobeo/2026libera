"""Offline, partially masked copy of the sole last control final after terminal."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import uuid

import build_remaining_masked_review as shared
import finalize_sector_last_final as last

original, campaign = shared.original, shared.campaign
VERSION = "last_final_masked_review_1"


def accounting(run, terminal):
    return last.finalize_last_final(run, terminal)


def current_validator(spec, folder):
    last.validate_stage(spec, folder)


def prior_validator(spec, folder):
    last.previous.validate_stage(spec, folder)


def build(run_dir, terminal_receipt, output_dir, mapping_dir):
    run, output, mapping = shared.locations(run_dir, output_dir, mapping_dir)
    # Only terminal metadata may be read before this guard succeeds.
    declaration, summary, terminal_refs = last.terminal_guard(run, terminal_receipt)
    history_keys = ("historical_summary_ref", "prior_continuation_summary_ref",
                    "prior_completion_summary_ref", "prior_remaining_summary_ref",
                    "historical_terminal_ref", "prior_continuation_terminal_ref",
                    "prior_completion_terminal_ref", "prior_remaining_terminal_ref")
    private_roots = [shared.resolve_reference(declaration[k]).parent for k in history_keys]
    private_roots.append(Path(declaration["output_root"]).resolve())
    for tree in private_roots:
        for target in (output, mapping):
            if target.is_relative_to(tree) or tree.is_relative_to(target):
                raise ValueError("Review copies must remain separate from all historical and current private trees")
    validated = accounting(run, terminal_receipt)
    expected = {"version": last.VERSION, "purpose": "primary_exploratory_last_final_dataset",
                "case_order": list(campaign.PILOT), "segment_case_order": list(last.CASES),
                "segment_planned_final_allocations": 1, "segment_planned_stage_slots": 1,
                "planned_final_allocations": 5, "planned_final_sector_rows": 55,
                "logical_stage_slots": 10,
                "last_final_generation_requests": summary["generation_requests_attempted"],
                "all_generation_requests_including_interrupted_attempt": 10 + summary["generation_requests_attempted"]}
    if any(validated.get(k) != v for k, v in expected.items()):
        raise ValueError("Last-final campaign accounting differs")
    evaluation_ref = shared.ref(original.EVALUATION)
    if evaluation_ref["sha256"] != original.EVALUATION_SHA:
        raise ValueError("Original r2 rubric changed")
    evaluation = shared.read(original.EVALUATION)
    manifest = shared.checked(declaration["prepared_manifest_ref"])
    prepared = {r["case_id"]: r for r in manifest["prepared_cases"]}
    if len(prepared) != len(manifest["prepared_cases"]) or set(prepared) != set(campaign.PILOT):
        raise ValueError("All five frozen prepared cases required")
    draft_ref = {k: prepared[last.CASE][k] for k in ("path", "sha256")}
    expected_draft = shared.checked(draft_ref)
    old = shared.checked(declaration["prior_remaining_declaration_ref"])
    old_summary = shared.checked(declaration["prior_remaining_summary_ref"])
    old_run = Path(old["run_directory"]).resolve()
    old_row = next(r for r in old_summary["cases"] if r["case_id"] == last.CASE)
    if [(r.get("stage"), r.get("status")) for r in old_row.get("stages", [])] != [("D0", "completed")]:
        raise ValueError("Exactly the preserved completed control draft required")
    prior = shared.inspect_stage(old_run, last.CASE, "D0", old_row["stages"][0], expected_draft,
                                 validator=prior_validator)
    if prior["text"] is None or not prior["normal_generation_completed"]:
        raise ValueError("External own draft must be completed")
    stages = summary["cases"][0].get("stages", [])
    if [r.get("stage") for r in stages] not in ([], ["F0"]):
        raise ValueError("One final only")
    final = shared.inspect_stage(run, last.CASE, "F0", stages[0] if stages else None,
                                 expected_draft, validator=current_validator)
    if final["generation_requests_attempted"] != summary["generation_requests_attempted"]:
        raise ValueError("Final request accounting differs")
    refs = [*terminal_refs, evaluation_ref, declaration["prepared_manifest_ref"], draft_ref,
            *prior["input_refs"], *final["input_refs"], *validated["input_refs"]]
    evidence = None
    if final["generation_requests_attempted"] == 1:
        last.own_history(run, last.CASE, final["spec"], declaration, refs)
        evidence = original.visible_final_evidence(final["spec"], prior["text"], expected_draft)
    opaque = uuid.uuid4().hex
    item = {"item_id": opaque, "rubric": "../rubric.json", "masking_notice": original.MASKING_NOTICE,
            "final_submission": shared.submission(final), "own_prior_submission": shared.submission(prior, prior=True),
            "supplied_final_evidence": evidence,
            "evidence_delivery_scope": "Recorded input of the attempted final; failed-request consumption is not inferred."
                if evidence is not None else "No final request recorded; evidence is not represented as supplied to a final.",
            "missing_final_rule": "A missing final is unobserved, never zero-scored or replaced by its draft.",
            "raw_claim_review_scope": "Read exact raw claims and own prior changes against supplied evidence; no external computed allocation is supplied as grounds."}
    items = [(opaque, item, prior["text"], final["text"])]
    secrets.SystemRandom().shuffle(items)  # One item: random identity, no comparative order inference.
    campaign.unchanged(refs)
    output.mkdir(parents=True)
    mapping.mkdir(parents=True)
    original.write_json(output / "rubric.json", original.review_rubric(evaluation))
    for item_id, value, prior_text, final_text in items:
        folder = output / item_id
        folder.mkdir()
        original.write_json(folder / "item.json", value)
        for filename, text in (("prior.txt", prior_text), ("final.txt", final_text)):
            if text is not None:
                with (folder / filename).open("x", encoding="utf-8", newline="") as stream:
                    stream.write(text)
    original.write_json(output / "index.json", {"bundle_version": VERSION, "items": [r[0] for r in items],
        "planned_final_submissions": 1, "planned_final_sector_rows": 11,
        "instruction": "Read the item against its evidence; no condition ranking or winning answer.",
        "masking_notice": original.MASKING_NOTICE, "scoring_performed": False,
        "independent_human_review_completed": False})
    campaign.unchanged(refs)
    receipt = {"version": VERSION, "status": "completed_offline_packaging_only", "purpose": last.PURPOSE,
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "model_generation_calls": 0, "service_calls": 0,
        "code_refs": [shared.ref(m.__file__) for m in (last, shared, original)],
        "source_refs": refs, "planned_final_submissions": 1, "planned_final_sector_rows": 11,
        "campaign_planned_final_submissions_private": 5, "campaign_planned_sector_rows_private": 55,
        "mapping": [{"item_id": opaque, "case_id": last.CASE, "own_D0_origin": "fixed_prior_remaining_after_terminal_review",
            "stages": {name: {k: v for k, v in stage.items() if k not in ("spec", "text")}
                       for name, stage in (("D0", prior), ("F0", final))}}],
        "accounting_and_derived_diagnostics_private_only": validated,
        "endpoint_amendment_private_only": "Five original conditions became primary exploratory evidence and the derived100% endpoint was amended after early outputs. Original raw claims retain the r2 rubric. Prior reviews and derived math are not judging evidence.",
        "judge_artifacts": [shared.ref(p) for p in sorted(output.rglob("*")) if p.is_file()],
        "limitations": [original.MASKING_NOTICE, "Single partially masked AI-assisted descriptive item, not independent human reliability or a balanced independent sample.",
                       "Verbatim input/output can reveal condition; no redaction or repair.",
                       "Late prior review and absent old ACK remain private provenance; packaging does not claim semantic success."]}
    original.write_json(mapping / "private_mapping.json", receipt)
    original.write_json(output / "COMPLETE.json", {"status": "complete", "items": 1, "scoring_performed": False})
    return {"status": receipt["status"], "items": 1, "model_generation_calls": 0, "service_calls": 0,
            "output_dir": str(output), "mapping_dir": str(mapping)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run-dir", "terminal-receipt", "output-dir", "mapping-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.run_dir, args.terminal_receipt, args.output_dir, args.mapping_dir)))


if __name__ == "__main__":
    main()
