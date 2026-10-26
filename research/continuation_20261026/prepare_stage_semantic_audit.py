"""Prepare a read-only evidence bundle from a durable continuation stage.

No generation, normalization, automatic entailment verdict or extraction of
partial model text. A reviewer must read the bundle and write a separate record.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "research" / "continuation_20261026"
CASES = ("fidelity_q2_2026__L", "ubs_june_2026__E", "ubs_june_2026__L", "common_market_only__C")
CODES = ("10", "15", "20", "25", "30", "35", "40", "45", "50", "55", "60")
RUBRIC_REF = {"path": "research/v492_evaluation_protocol_20261019_r2.json",
              "sha256": "807def444cc36d4a702321401a52e653b3f9a304383911e13f3c0389183086f1"}


def strict(raw, exact=False):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result

    def constant(value):
        raise ValueError("nonfinite JSON constant: " + value)

    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("JSON numeric literal exceeds finite binary-float range: " + value)
        return parsed

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant,
                      **({"parse_float": Decimal, "parse_int": Decimal} if exact else {"parse_float": finite_float}))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def workspace_path(value):
    path = Path(value)
    path = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Outside workspace")
    return path


def read_stable(path):
    path = workspace_path(path)
    first = path.read_bytes()
    value = strict(first.decode("utf-8-sig"))
    if path.read_bytes() != first:
        raise ValueError("Artifact changed while reading: " + str(path))
    return value, {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(first)}


def read_bound(reference, expected=None):
    path = workspace_path(reference["path"])
    if expected is not None and path != workspace_path(expected):
        raise ValueError("Unexpected bound path")
    value, actual = read_stable(path)
    if actual["sha256"] != reference["sha256"]:
        raise ValueError("Artifact hash mismatch")
    return value, actual


def visible_ids(value):
    found = set()
    if isinstance(value, dict):
        for key in ("evidence_id", "fact_id"):
            if isinstance(value.get(key), str):
                found.add(value[key])
        columns, rows = value.get("columns"), value.get("rows")
        if isinstance(columns, list) and isinstance(rows, list):
            for key in ("evidence_id", "fact_id"):
                if key in columns:
                    index = columns.index(key)
                    for row in rows:
                        if isinstance(row, list) and len(row) > index and isinstance(row[index], str):
                            found.add(row[index])
        for child in value.values():
            found.update(visible_ids(child))
    elif isinstance(value, list):
        for child in value:
            found.update(visible_ids(child))
    return found


def citation_occurrences(value, pointer=""):
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            escaped = key.replace("~", "~0").replace("/", "~1")
            location = pointer + "/" + escaped
            if isinstance(child, list) and (key == "evidence_ids" or key.endswith("_evidence_ids")):
                found.extend({"id": item, "output_pointer": location + "/" + str(i)}
                             for i, item in enumerate(child))
            else:
                found.extend(citation_occurrences(child, location))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            found.extend(citation_occurrences(child, pointer + "/" + str(i)))
    return found


def source_passages(packet):
    if packet is None:
        return []
    table = packet.get("evidence_table", {})
    return [dict(zip(table["columns"], row)) for row in table.get("rows", [])]


def explicit_rating(text, vocabulary):
    # Extract only an explicit published-label sentence; do not infer a rating.
    matches = [label for label in vocabulary if " receives " + label + "." in text.split(".")[0] + "."]
    return matches[0] if len(matches) == 1 else None


def decimal_vector(parsed):
    if not isinstance(parsed, dict):
        raise ValueError("Output is not a JSON object")
    rows = parsed.get("sectors")
    if not isinstance(rows, list) or len(rows) != len(CODES):
        raise ValueError("Exactly eleven sector rows required")
    by_code = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Sector row is not an object")
        code, value = row.get("sector_code"), row.get("weight")
        if code not in CODES or code in by_code or not isinstance(value, Decimal) or not value.is_finite():
            raise ValueError("Complete unique finite numeric vector required")
        if max(len(value.as_tuple().digits), abs(value.as_tuple().exponent), abs(value.adjusted())) > 512:
            raise ValueError("Numeric resource limit; raw text remains available for review")
        by_code[code] = value
    return by_code


def decimal_sum(values):
    with localcontext() as context:
        context.prec = 2048
        return sum(values, Decimal(0))


def decimal_delta(left, right):
    with localcontext() as context:
        context.prec = 2048
        return left - right


def prepare(stage_directory):
    stage_dir = workspace_path(stage_directory)
    run = stage_dir.parent
    declaration, declaration_ref = read_stable(run / "campaign_declaration.json")
    if declaration.get("purpose") != "pilot_continuation" or declaration.get("case_order") != list(CASES):
        raise ValueError("Only the declared four-cell continuation is supported")
    spec, spec_ref = read_stable(stage_dir / "worker_spec.json")
    case, stage = spec.get("case_id"), spec.get("stage")
    if case not in CASES or stage not in ("D0", "F0") or stage_dir.name != case + "__" + stage:
        raise ValueError("Case/stage identity mismatch")
    if workspace_path(spec["run_directory"]) != run:
        raise ValueError("Run identity mismatch")
    # Both receipts must exist before any saved model response is opened.
    transport, transport_ref = read_stable(stage_dir / "transport_result.json")
    review, review_ref = read_stable(stage_dir / "stage_review.json")
    if review.get("case_id") != case or review.get("stage") != stage:
        raise ValueError("Stage review identity mismatch")
    refs = [declaration_ref, spec_ref, transport_ref, review_ref]
    result = {"version": "continuation_semantic_bundle_1", "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "case_id": case, "stage": stage, "scope": "Unmasked stagewise audit preparation, not semantic scoring",
              "status": "unavailable_for_completed_output_review", "semantic_review_status": "not_assessed",
              "observed_transport_status": transport.get("status"), "refs": refs,
              "model_calls": 0, "normalization": False, "input_files_modified": False}
    if transport.get("status") not in {"completed", "model_structure_failure"} or review.get("instrument_integrity_pass") is not True:
        result["reason"] = "Normal completed transport and instrument binding required; no partial model text extracted."
        return result
    # Bind model artifacts only after the durable completion/instrument guard.
    for bound in review.get("input_refs", []):
        _, checked = read_bound(bound)
        refs.append(checked)
    if transport.get("generation_requests_attempted") != 1:
        raise ValueError("Exactly one request required for this segment stage")
    _, rubric_ref = read_bound(RUBRIC_REF)
    response, response_ref = read_bound(transport["response_artifact"], stage_dir / "http_0001_generation" / "response.json")
    if response != transport.get("response") or response.get("done") is not True or response.get("done_reason") != "stop":
        raise ValueError("Completed response envelope mismatch")
    raw = response["message"]["content"]
    try:
        parsed, exact = strict(raw), strict(raw, exact=True)
        parse_error = None
    except (ValueError, TypeError) as error:
        parsed, exact, parse_error = None, None, str(error)
    try:
        vector, vector_error = decimal_vector(exact), None
    except (ValueError, TypeError, AttributeError) as error:
        vector, vector_error = None, str(error)
    messages = spec["body"]["messages"]
    if len(messages) != (2 if stage == "D0" else 4):
        raise ValueError("Unexpected message history")
    initial = strict(messages[1]["content"])
    final = strict(messages[3]["content"]) if stage == "F0" else None
    manifest, manifest_ref = read_bound(declaration["prepared_manifest_ref"])
    prepared = next(row for row in manifest["prepared_cases"] if row["case_id"] == case and row["stage"] == "D0")
    original_messages, prepared_ref = read_bound({key: prepared[key] for key in ("path", "sha256")})
    if messages[:2] != original_messages:
        raise ValueError("Initial history differs from frozen prepared input")
    packet = (final if final else initial).get("institution_document")
    expected_source = None if case.endswith("__C") or (stage == "D0" and case.endswith("__L")) else case.rsplit("__", 1)[0]
    if (packet or {}).get("source_id") != expected_source:
        raise ValueError("Source visibility or identity mismatch")
    aggregate, aggregate_ref = read_bound(manifest["inputs"]["public_aggregate_never_sent"])
    expected_packet = aggregate["public_source_packets"][expected_source] if expected_source else None
    if packet != expected_packet:
        raise ValueError("Visible source packet differs from frozen packet")
    prior_vector, prior_text = None, None
    if stage == "F0":
        prior_ref = spec["draft_artifacts"]["response"]
        prior_response, prior_actual_ref = read_bound(prior_ref, run / (case + "__D0") / "http_0001_generation" / "response.json")
        prior_text = prior_response["message"]["content"]
        if prior_response.get("done") is not True or prior_response.get("done_reason") != "stop" or prior_text != spec["raw_draft"] or prior_text != messages[2]["content"]:
            raise ValueError("Final does not retain its exact actual own D0")
        try:
            prior_vector = decimal_vector(strict(prior_text, exact=True))
        except (ValueError, TypeError, AttributeError):
            prior_vector = None
        refs.append(prior_actual_ref)
    passages = source_passages(packet)
    visible = visible_ids(initial) | visible_ids(final or {})
    citations = citation_occurrences(parsed)
    market = initial["common_market"]
    rows = []
    sector_rows = parsed.get("sectors", []) if isinstance(parsed, dict) else []
    if not isinstance(sector_rows, list):
        sector_rows = []
    for i, row in enumerate(sector_rows):
        if not isinstance(row, dict):
            continue
        code = row.get("sector_code")
        if code not in CODES:
            continue
        matching = [p for p in passages if p.get("evidence_id", "").endswith(":sector:" + code)]
        source = matching[0] if len(matching) == 1 else None
        label = explicit_rating(source["text"], packet["rating_vocabulary"]) if source else None
        rows.append({"sector_code": code, "output_pointer": "/sectors/" + str(i),
                     "source_evidence": source, "explicit_published_label": label,
                     "source_label_as_submitted": row.get("source_label"), "source_stance": row.get("source_stance"),
                     "source_reading_exact_quote": row.get("source_reading"), "decision_reason_exact_quote": row.get("decision_reason"),
                     "source_reading_verbatim_match": source is not None and row.get("source_reading") == source["text"],
                     "source_label_matches_explicit_label": label is not None and row.get("source_label") == label,
                     "source_label_in_visible_vocabulary": row.get("source_label") in (packet or {}).get("rating_vocabulary", []),
                     "source_free_field_check": None if packet else row.get("source_label") is None and row.get("source_stance") == "not_available" and row.get("source_evidence_ids") == [],
                     "raw_weight_exact_decimal": str(vector[code]) if vector else None,
                     "own_D0_raw_delta_exact_decimal": str(decimal_delta(vector[code], prior_vector[code])) if vector and prior_vector else None,
                     "baseline_input_locator": "/common_market/baseline_weights/" + code,
                     "baseline_comparison_value": market["baseline_weights"][code],
                     "market_sector_index": market["sector_codes"].index(code),
                     "semantic_category": "pending_actual_AI_reading"})
    refs.extend([response_ref, manifest_ref, prepared_ref, aggregate_ref])
    result.update(status="prepared_for_semantic_reading", semantic_review_status="pending_actual_AI_reading",
                  raw_response_content_sha256=sha(raw.encode("utf-8")), raw_final_or_draft_text=raw,
                  own_prior_text=prior_text, raw_sum_exact_decimal=str(decimal_sum(vector.values())) if vector else None,
                  raw_residual_exact_decimal=str(decimal_delta(decimal_sum(vector.values()), Decimal(1))) if vector else None,
                  output_json_parse_error=parse_error, raw_vector_diagnostic_error=vector_error, sector_rows=rows,
                  source_fidelity_applicability="applicable" if packet else "not_applicable_no_source_supplied",
                  source_packet=packet, common_context=initial["common_context"], common_market=market,
                  public_numeric_fact_index=initial["public_numeric_fact_index"],
                  actual_draft_feedback=(final or {}).get("actual_draft_calculator_feedback"),
                  citation_occurrences=citations,
                  unavailable_id_occurrences=[c for c in citations if not isinstance(c["id"], str) or c["id"] not in visible],
                  rubric_ref=rubric_ref,
                  coverage={"structural_sector_rows_prepared": len(rows), "semantic_rows_read": 0,
                            "numeric_claim_occurrences_checked": None, "semantic_scores_generated": False},
                  interpretation_limits=["Exact text/label matching is a structural aid, not a whole-decision semantic verdict.",
                                         "A visible citation ID does not establish entailment.",
                                         "C or source-free D0 has no missing-institution fidelity penalty.",
                                         "Read claims against supplied evidence and raw choices; derived math is a separate artifact.",
                                         "No aggregate pass score, independent-human claim or condition ranking."])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = workspace_path(args.output)
    if not output.is_relative_to(REPORT_ROOT) or output.exists():
        raise ValueError("A new exclusive report path under continuation_20261026 is required")
    result = prepare(args.stage_dir)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "output": str(output), "semantic_review_status": result["semantic_review_status"]}))


if __name__ == "__main__":
    main()
