"""Build one-output-at-a-time review copies after a v4.9.2 pilot ends.

This is an offline packaging tool, not a scorer. It never imports evaluator
source comparisons or computational reference portfolios into judge copies.
The original output strings are retained, including errors and partial text.
Source identity and output content can reveal a condition: masking is partial.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import secrets
import uuid

ROOT = Path(__file__).resolve().parents[1]
EVALUATION = ROOT / "research/v492_evaluation_protocol_20261019_r2.json"
EVALUATION_SHA = "807def444cc36d4a702321401a52e653b3f9a304383911e13f3c0389183086f1"
CASES = ("fidelity_q2_2026__E", "fidelity_q2_2026__L", "ubs_june_2026__E",
         "ubs_june_2026__L", "common_market_only__C")
COMMON_KEYS = {"common_context", "common_market", "public_numeric_fact_index", "response_schema"}
MASKING_NOTICE = ("Arm labels, execution order, run paths and comparative hypotheses are withheld. "
                  "Actual source identities, dates and verbatim output remain necessary evidence; "
                  "source presence or the output itself can reveal a condition. Masking is incomplete.")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"),
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def ref(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def checked(reference):
    path = Path(reference["path"])
    if not path.is_absolute():
        path = ROOT / path
    if ref(path)["sha256"] != reference["sha256"]:
        raise ValueError("An input artifact changed")
    return read(path)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def validate_run_gate(declaration, run_dir):
    # Lazy import keeps this packaging module and its synthetic tests lightweight.
    # Both calls below are file validation only; neither contacts Ollama.
    import sector_v492_runtime as runtime
    runtime.validate_runtime(declaration["runtime"])
    runtime.validate_review_gate(declaration["review_gate"]["path"],
                                 declaration["review_gate"]["sha256"],
                                 runtime=declaration["runtime"], run_directory=run_dir)


def validate_stage_spec(spec, spec_path):
    import sector_v492_runtime as runtime
    runtime.validate_spec(spec)
    runtime.validate_worker_location(spec, Path(spec_path).parent)


def review_rubric(evaluation):
    if evaluation.get("protocol_version") != "4.9.2" or evaluation.get("no_composite_score") is not True:
        raise ValueError("Only the frozen non-composite v4.9.2 rubric is supported")
    dimensions = copy.deepcopy(evaluation["dimensions"])
    source = dimensions["source_fidelity"]
    source["when_no_institution_supplied"] = source.pop("C_rule")
    return {"dimensions": dimensions, "no_composite_score": True,
            "review_status": "Unvalidated AI-assisted descriptive semantic coding; no human validation claim.",
            "instruction": "Inspect one item using only its supplied evidence before comparing any items. "
                           "Retain supported, unsupported, unresolved and unassessable findings with evidence. "
                           "Do not select a winning answer or infer hidden reasoning. This bundle contains no scores.",
            "prior_submission_scope": "The prior submission is process evidence for actual change claims, "
                                      "never an independent observation or substitute final answer.",
            "masking_notice": MASKING_NOTICE}


def extract_text(stage_dir):
    """Retain complete/partial content; never parse, repair or filter its JSON."""
    folder = stage_dir / "http_0001_generation"
    response_path, assembled_path = folder / "response.json", folder / "assembled_text.json"
    references = [ref(p) for p in sorted(folder.glob("*")) if p.is_file()] if folder.exists() else []
    if response_path.exists():
        response = read(response_path)
        text = response.get("message", {}).get("content")
        if not isinstance(text, str):
            raise ValueError("Saved response has no verbatim content string")
        if assembled_path.exists() and read(assembled_path).get("content") != text:
            raise ValueError("Response and assembled content disagree")
        return {"text": text, "text_state": "saved_response_content", "artifacts": references}
    if assembled_path.exists():
        assembled = read(assembled_path)
        if not isinstance(assembled.get("content"), str):
            raise ValueError("Assembled partial content is not a string")
        return {"text": assembled["content"], "text_state": "saved_assembled_partial_content",
                "artifacts": references}
    events_path = folder / "events.jsonl"
    if events_path.exists():
        chunks, malformed = [], False
        event_bytes = events_path.read_bytes()
        try:
            event_text = event_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            event_text, malformed = event_bytes[:exc.start].decode("utf-8"), True
        for line in event_text.splitlines():
            if not line.strip():
                continue
            try:
                message = json.loads(line)["event"].get("message", {})
                content = message.get("content", "")
                if not isinstance(content, str):
                    raise ValueError("Non-string stream content")
                chunks.append(content)
            except (ValueError, TypeError, KeyError, AttributeError):
                malformed = True
                break  # A corrupt tail is retained privately, not guessed or repaired.
        return {"text": "".join(chunks) if chunks else None,
                "text_state": "recorded_event_prefix_partial" if chunks else "no_recorded_content",
                "unreadable_event_tail": malformed, "artifacts": references}
    return {"text": None, "text_state": "no_recorded_content", "artifacts": references}


def visible_final_evidence(spec, own_draft, expected_draft):
    """Select actual final-visible facts, without earlier exposure metadata."""
    messages = spec["body"]["messages"]
    if len(messages) != 4 or canonical(messages[:2]) != canonical(expected_draft):
        raise ValueError("Final history differs from the prepared own draft input")
    if messages[2] != {"role": "assistant", "content": own_draft}:
        raise ValueError("Final history is not the exact saved own prior output")
    first, final = read_content(messages[1]), read_content(messages[3])
    if set(first) - (COMMON_KEYS | {"stage", "task", "institution_document"}):
        raise ValueError("Unexpected hidden metadata in draft input")
    if set(final) not in ({"stage", "task", "actual_draft_calculator_feedback"},
                          {"stage", "task", "actual_draft_calculator_feedback", "institution_document"}):
        raise ValueError("Unexpected final input keys")
    packet = final.get("institution_document")
    case_id = spec["case_id"]
    if case_id == CASES[-1]:
        if packet is not None or "institution_document" in final or "institution_document" in first:
            raise ValueError("No-source final contains institution evidence")
    else:
        source_id = case_id.rsplit("__", 1)[0]
        if not isinstance(packet, dict) or packet.get("source_id") != source_id:
            raise ValueError("Final contains an unassigned or hidden main source")
    return {**{key: first[key] for key in sorted(COMMON_KEYS)},
            "institution_document": copy.deepcopy(packet),
            "actual_draft_calculator_feedback": copy.deepcopy(final["actual_draft_calculator_feedback"])}


def read_content(message):
    if message.get("role") != "user" or not isinstance(message.get("content"), str):
        raise ValueError("Malformed saved user message")
    return json.loads(message["content"])


def inspect_stage(run_dir, case_id, stage, stage_record, expected_draft):
    folder = run_dir / (case_id + "__" + stage)
    if stage_record is None:
        if folder.exists():
            raise ValueError("Stage artifacts exist but are omitted from the completed summary")
        return {"stage_status": "not_attempted", "generation_requests_attempted": 0,
                "text": None, "text_state": "no_recorded_content", "artifacts": [], "spec": None}
    count = stage_record.get("generation_requests_attempted")
    if type(count) is not int or count not in (0, 1):
        raise ValueError("First-attempt-only accounting violated")
    spec_path = folder / "worker_spec.json"
    spec = read(spec_path)
    if spec.get("case_id") != case_id or spec.get("stage") != stage:
        raise ValueError("Saved stage identity differs from its declared case")
    validate_stage_spec(spec, spec_path)
    if canonical(spec["body"]["messages"][:2]) != canonical(expected_draft):
        raise ValueError("Stage contains inputs other than its frozen pilot inputs")
    transport_path = folder / "transport_result.json"
    transport = read(transport_path)
    if (type(transport.get("generation_requests_attempted")) is not int
            or transport["generation_requests_attempted"] != count
            or transport.get("status") != stage_record["status"]):
        raise ValueError("Stage and coordinator accounting disagree")
    generations = list(folder.glob("http_*_generation"))
    if len(generations) > 1 or (generations and generations[0].name != "http_0001_generation"):
        raise ValueError("Extra or replacement generation attempt found")
    if count == 0 and generations:
        raise ValueError("Undeclared generation artifacts found")
    response_path = folder / "http_0001_generation/response.json"
    bound = None
    if response_path.exists():
        declared_ref = transport.get("response_artifact")
        bound = declared_ref == ref(response_path)
        if not bound and (declared_ref is not None or transport.get("status") == "completed"):
            raise ValueError("Saved response is not bound by the transport receipt")
        if bound and canonical(transport.get("response")) != canonical(read(response_path)):
            raise ValueError("Transport response differs from the saved response")
    content = extract_text(folder)
    if bound is False:
        content["text_state"] = "unbound_saved_response_content_after_interruption"
    return {"stage_status": stage_record["status"], "generation_requests_attempted": count,
            **content, "response_artifact_bound": bound, "spec": spec,
            "private_stage_refs": [ref(p) for p in sorted(folder.glob("*.json")) if p.is_file()]}


def build(run_dir, output_dir, mapping_dir):
    run_dir, output_dir, mapping_dir = [Path(p).resolve() for p in (run_dir, output_dir, mapping_dir)]
    if (output_dir == mapping_dir or output_dir in mapping_dir.parents or mapping_dir in output_dir.parents
            or run_dir == output_dir or run_dir in output_dir.parents
            or run_dir == mapping_dir or run_dir in mapping_dir.parents):
        raise ValueError("Judge bundle and private mapping must be separate, outside the original run")
    if output_dir.exists() or mapping_dir.exists():
        raise FileExistsError("Review artifacts are never overwritten")
    # This check comes before opening any response artifact: no live-output tuning.
    summary_path = run_dir / "pilot_summary.json"
    if not summary_path.is_file():
        raise ValueError("Completed pilot_summary.json required; live outputs are not read")
    summary = read(summary_path)
    summary_ref = ref(summary_path)
    if summary.get("status") not in ("stopped", "pilot_attempt_sequence_finished"):
        raise ValueError("Completed attempt-sequence status is required")
    if [row.get("case_id") for row in summary.get("cases", [])] != list(CASES):
        raise ValueError("Exactly the five declared pilot cases are required; no main inputs")
    for field in ("main_model_calls", "automatic_retries", "post_final_calls"):
        if type(summary.get(field)) is not int or summary[field] != 0:
            raise ValueError("Main execution, retries or post-final calls are outside this bundle")
    declaration = read(run_dir / "pilot_declaration.json")
    validate_run_gate(declaration, run_dir)
    gate = checked(declaration["review_gate"])
    evaluation = checked(gate["evaluation_protocol_ref"])
    if (gate["evaluation_protocol_ref"]["sha256"] != EVALUATION_SHA
            or ref(EVALUATION)["sha256"] != EVALUATION_SHA
            or canonical(evaluation) != canonical(read(EVALUATION))):
        raise ValueError("Run is not bound to the declared frozen evaluation revision")
    prepared = checked(gate["prepared_manifest_ref"])
    prepared_cases = {row["case_id"]: row for row in prepared["prepared_cases"]}
    if len(prepared["prepared_cases"]) != 5 or set(prepared_cases) != set(CASES):
        raise ValueError("Prepared input manifest has unexpected cases")
    expected_dirs = {case + "__" + stage for case in CASES for stage in ("D0", "F0")}
    if any(p.is_dir() and p.name.endswith(("__D0", "__F0")) and p.name not in expected_dirs for p in run_dir.iterdir()):
        raise ValueError("Unexpected main or additional stage directory")
    items, mapping, total = [], [], 0
    for row in summary["cases"]:
        case_id = row["case_id"]
        stages = row.get("stages", [])
        if [s.get("stage") for s in stages] not in ([], ["D0"], ["D0", "F0"]):
            raise ValueError("Unexpected stage order or duplicate first attempt")
        # Prepared D0 has the exact source visibility of this one case.
        draft_ref = prepared_cases[case_id]
        expected_draft = checked(draft_ref)
        records = {s["stage"]: s for s in stages}
        draft = inspect_stage(run_dir, case_id, "D0", records.get("D0"), expected_draft)
        final = inspect_stage(run_dir, case_id, "F0", records.get("F0"), expected_draft)
        total += draft["generation_requests_attempted"] + final["generation_requests_attempted"]
        evidence = None
        if final["spec"] is not None and final["generation_requests_attempted"] == 1:
            if draft["text"] is None:
                raise ValueError("Final lacks its actual own draft")
            evidence = visible_final_evidence(final["spec"], draft["text"], expected_draft)
        item_id = uuid.uuid4().hex
        item = {"item_id": item_id, "rubric": "../rubric.json", "masking_notice": MASKING_NOTICE,
                "final_submission": {"status": final["stage_status"], "text_state": final["text_state"],
                                     "text_file": "final.txt" if final["text"] is not None else None,
                                     "diagnostic_only": final["text_state"] != "saved_response_content",
                                     "availability_limit": "Partial or unbound text is a diagnostic only, not a completed final or evidence of success."},
                "own_prior_submission": {"status": draft["stage_status"], "text_state": draft["text_state"],
                                         "text_file": "prior.txt" if draft["text"] is not None else None,
                                         "scope": "Process evidence only; never a replacement final."},
                "supplied_final_evidence": evidence,
                "evidence_delivery_scope": "Recorded input of the attempted final request; consumption is not inferred from a failed request."
                                           if evidence is not None else "No final generation request is recorded; no final evidence is represented as supplied.",
                "missing_final_rule": "A missing final is not scored as zero and is not replaced with its prior submission."}
        items.append((item_id, item, draft["text"], final["text"]))
        mapping.append({"item_id": item_id, "case_id": case_id, "case_status": row.get("status"),
                        "stages": {name: {k: v for k, v in stage.items() if k not in ("text", "spec")}
                                   for name, stage in (("D0", draft), ("F0", final))}})
    if type(summary.get("generation_requests_attempted")) is not int or total != summary["generation_requests_attempted"] or total > 10:
        raise ValueError("Completed run and all-attempt denominator disagree")
    if ref(summary_path) != summary_ref:
        raise ValueError("Completed summary changed while constructing review copies")
    secrets.SystemRandom().shuffle(items)
    output_dir.mkdir(parents=True)
    mapping_dir.mkdir(parents=True)
    write_json(output_dir / "rubric.json", review_rubric(evaluation))
    for item_id, item, draft_text, final_text in items:
        folder = output_dir / item_id
        folder.mkdir()
        write_json(folder / "item.json", item)
        for name, value in (("prior.txt", draft_text), ("final.txt", final_text)):
            if value is not None:
                with (folder / name).open("x", encoding="utf-8", newline="") as handle:
                    handle.write(value)
    index = {"bundle_version": "v492_masked_review_1", "items": [item[0] for item in items],
             "planned_final_submissions": 5, "planned_final_sector_rows": 55,
             "instruction": "Open one item at a time. Do not compare answer quality side by side.",
             "masking_notice": MASKING_NOTICE, "scoring_performed": False,
             "independent_human_review_completed": False}
    write_json(output_dir / "index.json", index)
    receipt = {"status": "completed_offline_packaging_only", "generation_requests": 0,
               "source_run_summary": summary_ref, "evaluation_ref": gate["evaluation_protocol_ref"],
               "script_ref": ref(__file__), "total_first_attempt_requests": total,
               "planned_stage_slots": 10, "planned_final_submissions": 5, "mapping": mapping,
               "judge_artifacts": [ref(p) for p in sorted(output_dir.rglob("*")) if p.is_file()],
               "raw_text_policy": "Exact assistant strings; no normalization, correction, scoring or missing-final replacement."}
    write_json(mapping_dir / "private_mapping.json", receipt)
    write_json(output_dir / "COMPLETE.json", {"status": "complete", "items": 5, "scoring_performed": False})
    return {"status": receipt["status"], "items": 5, "first_attempt_requests": total,
            "judge_bundle": str(output_dir), "private_mapping": str(mapping_dir), "model_calls": 0}


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mapping-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.run_dir, args.output_dir, args.mapping_dir), ensure_ascii=False))


if __name__ == "__main__":
    main()
