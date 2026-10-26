"""Offline remaining-stage semantic evidence bundle, never a score or repaired response."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from decimal import Decimal, DecimalException
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "research" / "remaining_20261026"
PARSER_PATH = ROOT / "research/continuation_20261026/prepare_stage_semantic_audit.py"
PARSER_SHA = "efb82936ee541f187d8b352a1a28afa8ecea3d83401439a6e92a82df9731fb04"
if hashlib.sha256(PARSER_PATH.read_bytes()).hexdigest() != PARSER_SHA:
    raise ValueError("Accepted semantic parser source changed")
_module_spec = importlib.util.spec_from_file_location("accepted_semantic_parser", PARSER_PATH)
accepted = importlib.util.module_from_spec(_module_spec)
_module_spec.loader.exec_module(accepted)
strict, sha = accepted.strict, accepted.sha
visible_ids, citation_occurrences = accepted.visible_ids, accepted.citation_occurrences
source_passages, explicit_rating = accepted.source_passages, accepted.explicit_rating
decimal_vector, decimal_sum, decimal_delta = accepted.decimal_vector, accepted.decimal_sum, accepted.decimal_delta
CODES, RUBRIC_REF = accepted.CODES, accepted.RUBRIC_REF
CASES = ("ubs_june_2026__E", "ubs_june_2026__L", "common_market_only__C")
STAGE_ORDER = ("ubs_june_2026__E__F0", "ubs_june_2026__L__D0", "ubs_june_2026__L__F0",
               "common_market_only__C__D0", "common_market_only__C__F0")
EXTERNAL_CASE = "ubs_june_2026__E"
EXTERNAL_EVIDENCE_KEYS = {"stage_review", "allocation_math", "semantic_review", "external_review_ack",
                          "terminal", "summary", "declaration", "final_construction"}
DRAFT_FILES = {"response": "http_0001_generation/response.json", "worker_spec": "worker_spec.json",
               "worker_summary": "worker_summary.json", "supervisor_result": "supervisor_result.json",
               "transport_result": "transport_result.json"}
CODE_PATHS = {"research/sector_remaining_runtime.py", "research/sector_remaining_gate.py",
              "research/remaining_20261026/prepare_stage_semantic_audit.py",
              "research/continuation_20261026/prepare_stage_semantic_audit.py"}


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


def same_ref(left, right):
    return (isinstance(left, dict) and isinstance(right, dict)
            and workspace_path(left.get("path", "")) == workspace_path(right.get("path", ""))
            and left.get("sha256") == right.get("sha256"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def scope(value):
    require(value.get("purpose") == "pilot_completion_resume" and value.get("case_order") == list(CASES),
            "Only the three declared completion conditions are supported")
    require(value.get("stage_order") == list(STAGE_ORDER), "Only the five unattempted stages are allowed")
    for key, number in (("max_generation_requests", 5), ("historical_generation_requests", 6),
                        ("campaign_max_generation_requests", 11), ("automatic_retries", 0), ("main_model_calls", 0)):
        require(type(value.get(key)) is int and value[key] == number, "Wrong completion accounting: " + key)
    require(value.get("main_allowed") is False and value.get("old_outputs_observed") is True
            and value.get("analysis_role") == "primary_exploratory"
            and value.get("excluded_new_main_execution") is True, "Exploratory completion scope required")
    require(value.get("explicit_retry_slots") == []
            and value.get("historical_explicit_retry_slots") == ["fidelity_q2_2026__L__D0"],
            "No new retries; historical retry must remain explicit")


def validate_worker_spec(spec):
    # validate_spec reads artifacts/builds the expected body. It never renders,
    # tokenizes, loads a model or calls the service.
    research = str(ROOT / "research")
    if research not in sys.path:
        sys.path.insert(0, research)
    import sector_remaining_runtime
    return sector_remaining_runtime.validate_spec(spec)


def guard(stage_dir, spec, transport, review, refs):
    require(review.get("case_id") == spec["case_id"] and review.get("stage") == spec["stage"],
            "Stage review identity mismatch")
    if transport.get("status") not in {"completed", "model_structure_failure"} or review.get("instrument_integrity_pass") is not True:
        return False
    checks = review.get("checks")
    require(isinstance(checks, dict) and checks and all(v is True for v in checks.values()),
            "Instrument pass must have nonempty passing checks")
    required = [stage_dir / name for name in ("worker_spec.json", "transport_result.json", "http_0001_generation/response.json")]
    if transport["status"] == "completed":
        required.append(stage_dir / "response_contract_validation.json")
    seen = {}
    for reference in review.get("input_refs", []):
        path = workspace_path(reference["path"])
        require(path not in seen, "Duplicate stage review reference")
        require(path in {stage_dir / name for name in ("worker_spec.json", "transport_result.json",
                "http_0001_generation/response.json", "response_contract_validation.json")},
                "Foreign stage review reference refused")
        seen[path] = reference
    require(all(p in seen for p in required), "Required stage review binding missing")
    # The durable normal-completion/instrument guard precedes response reads.
    for reference in seen.values():
        _, actual = read_bound(reference)
        refs.append(actual)
    if transport["status"] == "completed":
        contract_result, _ = read_stable(stage_dir / "response_contract_validation.json")
        require(contract_result.get("continuation_eligible") is True, "Completed worker contract eligibility differs")
    worker, worker_ref = read_stable(stage_dir / "worker_summary.json")
    supervisor, supervisor_ref = read_stable(stage_dir / "supervisor_result.json")
    refs.extend([worker_ref, supervisor_ref])
    for item in (worker, supervisor, transport):
        require(type(item.get("generation_requests_attempted")) is int and item["generation_requests_attempted"] == 1,
                "Exactly one integer generation attempt required")
    eligible = transport["status"] == "completed"
    require(worker.get("status") == transport["status"]
            and worker.get("continuation_eligible") is eligible and transport.get("continuation_eligible") is eligible
            and worker.get("system_integrity_incident") is False and transport.get("system_integrity_incident") is False,
            "Worker and transport outcome mismatch")
    require(supervisor.get("status") == "worker_exited" and type(supervisor.get("worker_exit_code")) is int
            and supervisor["worker_exit_code"] == (0 if eligible else 1)
            and supervisor.get("worker") == worker and transport.get("supervisor") == supervisor,
            "Supervisor and worker completion mismatch")
    require(sorted(p.name for p in stage_dir.iterdir() if p.is_dir() and p.name.startswith("http_") and p.name.endswith("_generation"))
            == ["http_0001_generation"], "Unexpected generation attempt directory")
    return True


def remaining_binding(declaration, run, spec, refs):
    gate, gate_ref = read_bound(declaration["review_gate"])
    frozen, frozen_ref = read_bound(declaration["freeze_ref"])
    for value in (gate, frozen):
        scope(value)
        require(workspace_path(value["run_directory"]) == run, "Gate/freeze run differs")
    require(gate.get("receipt_version") == "sector_remaining_gate_1"
            and gate.get("status") == "approved_for_remaining_before_generation"
            and frozen.get("freeze_version") == "sector_remaining_freeze_1"
            and frozen.get("status") == "frozen_for_pilot_remaining_only", "Completion gate/freeze status differs")
    require(same_ref(gate.get("freeze_ref"), frozen_ref) and same_ref(spec.get("review_gate"), gate_ref),
            "Worker/declaration/gate freeze binding differs")
    for key in ("runtime_ref", "protocol_ref", "prepared_manifest_ref", "prior_completion_gate_ref",
                "prior_completion_terminal_ref", "prior_completion_summary_ref", "prior_completion_declaration_ref"):
        require(same_ref(declaration.get(key), gate.get(key)) and same_ref(gate.get(key), frozen.get(key)),
                "Completion reference differs: " + key)
        _, ref = read_bound(gate[key])
        refs.append(ref)
    for name in ("external_draft_refs", "external_draft_evidence_refs"):
        require(declaration.get(name) == gate.get(name) == frozen.get(name), "External draft group differs: " + name)
    require(declaration.get("power_policy") == gate.get("power_policy") == frozen.get("power_policy"),
            "Operational power policy binding differs")
    runtime, _ = read_bound(gate["runtime_ref"])
    require(spec.get("runtime") == runtime == declaration.get("runtime"), "Worker runtime differs")
    require(workspace_path(declaration["run_directory"]) == run and spec.get("origin") == declaration.get("origin"),
            "Worker run/origin differs from declaration")
    names = []
    for ref in frozen.get("code_refs", []):
        path = workspace_path(ref["path"])
        name = path.relative_to(ROOT).as_posix()
        require(name not in names, "Duplicate frozen code reference")
        names.append(name)
        raw = path.read_bytes()
        require(sha(raw) == ref["sha256"] and path.read_bytes() == raw, "Frozen code changed")
        refs.append({"path": name, "sha256": sha(raw)})
    require(CODE_PATHS.issubset(names), "Semantic preparer and runtime/parser sources must be frozen")
    refs.extend([gate_ref, frozen_ref])


def external_draft_bindings(declaration, spec, refs):
    """The sole cross-segment draft is the already reviewed UBS E D0.

    Called only after this current F0 has a durable normal-completion guard.
    No historical response is copied or relabelled as a new request.
    """
    require(spec.get("case_id") == EXTERNAL_CASE and spec.get("stage") == "F0", "Only UBS E F0 may use an external draft")
    draft_refs, evidence = declaration.get("external_draft_refs"), declaration.get("external_draft_evidence_refs")
    require(isinstance(draft_refs, dict) and set(draft_refs) == set(DRAFT_FILES)
            and isinstance(evidence, dict) and set(evidence) == EXTERNAL_EVIDENCE_KEYS,
            "Exact external five artifacts and eight evidence records required")
    require(spec.get("draft_artifacts") == draft_refs, "Worker external draft refs differ from declared fixed draft")
    prior_run = workspace_path("data/local_sector_runtime/v494_completion_20261026")
    prior_dir = prior_run / (EXTERNAL_CASE + "__D0")
    old_declaration, old_decl_ref = read_bound(evidence["declaration"], prior_run / "campaign_declaration.json")
    require(old_declaration.get("purpose") == "pilot_completion"
            and workspace_path(old_declaration["run_directory"]) == prior_run,
            "External D0 belongs to the fixed prior completion authority")
    require(same_ref(declaration["prior_completion_declaration_ref"], old_decl_ref), "Prior declaration ref differs")
    old_reports = workspace_path(old_declaration["output_root"])
    early_spec, esr = read_bound(draft_refs["worker_spec"], prior_dir / "worker_spec.json")
    early_transport, etr = read_bound(draft_refs["transport_result"], prior_dir / "transport_result.json")
    early_review, err = read_bound(evidence["stage_review"], prior_dir / "stage_review.json")
    require(early_spec.get("case_id") == EXTERNAL_CASE and early_spec.get("stage") == "D0"
            and workspace_path(early_spec["run_directory"]) == prior_run
            and early_transport.get("status") == "completed", "Fixed external D0 must be normally completed")
    refs.extend([esr, etr, err])
    require(guard(prior_dir, early_spec, early_transport, early_review, refs), "Fixed external D0 instrument guard failed")
    expected = {"stage_review": prior_dir / "stage_review.json",
                "allocation_math": old_reports / "allocation_math" / (EXTERNAL_CASE + "__D0.json"),
                "external_review_ack": prior_dir / "external_review_ack.json",
                "terminal": old_reports / "terminal_receipt.json", "summary": prior_run / "campaign_summary.json",
                "declaration": prior_run / "campaign_declaration.json",
                "final_construction": prior_run / (EXTERNAL_CASE + "__final_construction.json")}
    require(workspace_path(evidence["semantic_review"]["path"]).is_relative_to(old_reports.parent / "semantic"),
            "External semantic review must belong to the prior completion semantic tree")
    records = {}
    for role, reference in evidence.items():
        records[role], actual = read_bound(reference, expected.get(role))
        refs.append(actual)
    for role, filename in DRAFT_FILES.items():
        # Response is not opened until the historical metadata guard below.
        require(workspace_path(draft_refs[role]["path"]) == prior_dir / filename, "External draft path differs")
    terminal, summary = records["terminal"], records["summary"]
    require(same_ref(declaration["prior_completion_terminal_ref"], evidence["terminal"])
            and same_ref(declaration["prior_completion_summary_ref"], evidence["summary"])
            and same_ref(old_declaration.get("review_gate"), declaration["prior_completion_gate_ref"]),
            "Prior completion authority chain differs")
    require(terminal.get("purpose") == "pilot_completion" and terminal.get("status") == "stopped_semantic_review_pending"
            and summary.get("purpose") == "pilot_completion" and summary.get("status") == "stopped"
            and same_ref(terminal.get("declaration_ref"), evidence["declaration"])
            and same_ref(terminal.get("summary_ref"), evidence["summary"]), "Prior stopped terminal binding differs")
    for record in (terminal, summary):
        require(type(record.get("generation_requests_attempted")) is int and record["generation_requests_attempted"] == 1,
                "Exactly one historical completion request required")
    require(summary.get("case_order") == list(CASES)
            and [r.get("case_id") for r in summary.get("cases", [])] == list(CASES)
            and len(summary["cases"][0].get("stages", [])) == 1
            and summary["cases"][0]["stages"][0].get("stage") == "D0"
            and summary["cases"][0]["stages"][0].get("status") == "completed"
            and type(summary["cases"][0]["stages"][0].get("generation_requests_attempted")) is int
            and summary["cases"][0]["stages"][0]["generation_requests_attempted"] == 1
            and all(r.get("stages") == [] for r in summary["cases"][1:]),
            "Only the completed UBS E D0 may precede the five remaining stages")
    semantic, ack, math = records["semantic_review"], records["external_review_ack"], records["allocation_math"]
    require(semantic.get("review_status") == "completed" and semantic.get("case_id") == EXTERNAL_CASE
            and semantic.get("stage") == "D0" and same_ref(semantic.get("transport_ref"), draft_refs["transport_result"]),
            "External D0 semantic review must be complete and exactly bound")
    require(ack.get("schema_version") == "sector_completion_stage_external_review_ack_1"
            and ack.get("status") == "completed" and ack.get("case_id") == EXTERNAL_CASE and ack.get("stage") == "D0"
            and ack.get("raw_model_content_modified") is False and type(ack.get("model_calls")) is int
            and ack["model_calls"] == 0, "External D0 original ACK required")
    for key, reference in (("worker_spec_ref", draft_refs["worker_spec"]),
            ("transport_ref", draft_refs["transport_result"]), ("stage_review_ref", evidence["stage_review"]),
            ("allocation_math_ref", evidence["allocation_math"]), ("semantic_review_ref", evidence["semantic_review"])):
        require(same_ref(ack.get(key), reference), "External D0 ACK binding differs: " + key)
    for record in (semantic, ack):
        for axis in ("errors", "consistency", "paper_topic"):
            item = record.get("review_axes", {}).get(axis, {})
            require(item.get("reviewed") is True and isinstance(item.get("reason"), str) and item["reason"].strip(),
                    "External D0 review axes must be complete; adverse findings remain allowed")
    require(math.get("case_id") == EXTERNAL_CASE and math.get("stage") == "D0"
            and math.get("observed_transport_status") == "completed", "External D0 math identity differs")
    require(records["final_construction"].get("ready") is True
            and records["final_construction"].get("messages") == spec["body"]["messages"],
            "UBS E F0 must retain the exact prior saved final construction")
    return prior_dir


def prepare(stage_directory):
    stage_dir = workspace_path(stage_directory)
    run = stage_dir.parent
    declaration, declaration_ref = read_stable(run / "campaign_declaration.json")
    scope(declaration)
    spec, spec_ref = read_stable(stage_dir / "worker_spec.json")
    case, stage = spec.get("case_id"), spec.get("stage")
    if case not in CASES or stage not in ("D0", "F0") or case + "__" + stage not in STAGE_ORDER or stage_dir.name != case + "__" + stage:
        raise ValueError("Case/stage identity mismatch")
    if workspace_path(spec["run_directory"]) != run:
        raise ValueError("Run identity mismatch")
    # Both receipts must exist before any saved model response is opened.
    transport, transport_ref = read_stable(stage_dir / "transport_result.json")
    review, review_ref = read_stable(stage_dir / "stage_review.json")
    if review.get("case_id") != case or review.get("stage") != stage:
        raise ValueError("Stage review identity mismatch")
    refs = [declaration_ref, spec_ref, transport_ref, review_ref]
    result = {"version": "remaining_semantic_bundle_1", "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "case_id": case, "stage": stage, "scope": "Unmasked stagewise audit preparation, not semantic scoring",
              "status": "unavailable_for_completed_output_review", "semantic_review_status": "not_assessed",
              "observed_transport_status": transport.get("status"), "refs": refs,
              "model_calls": 0, "normalization": False, "input_files_modified": False}
    if not guard(stage_dir, spec, transport, review, refs):
        result["reason"] = "Normal completed transport and instrument binding required; no partial model text extracted."
        return result
    remaining_binding(declaration, run, spec, refs)
    if stage == "F0":
        prior_dir = external_draft_bindings(declaration, spec, refs) if case == EXTERNAL_CASE else run / (case + "__D0")
        prior_spec, prior_spec_ref = read_stable(prior_dir / "worker_spec.json")
        prior_transport, prior_transport_ref = read_stable(prior_dir / "transport_result.json")
        prior_review, prior_review_ref = read_stable(prior_dir / "stage_review.json")
        require(prior_spec.get("case_id") == case and prior_spec.get("stage") == "D0"
                and workspace_path(prior_spec["run_directory"]) == prior_dir.parent
                and prior_transport.get("status") == "completed", "Own new D0 must be normally completed")
        refs.extend([prior_spec_ref, prior_transport_ref, prior_review_ref])
        require(guard(prior_dir, prior_spec, prior_transport, prior_review, refs), "Own D0 instrument guard failed")
        if case != EXTERNAL_CASE:
            remaining_binding(declaration, run, prior_spec, refs)
        require(isinstance(spec.get("draft_artifacts"), dict) and set(spec["draft_artifacts"]) == set(DRAFT_FILES),
                "Exactly five own D0 artifacts required")
        for role, filename in DRAFT_FILES.items():
            _, bound = read_bound(spec["draft_artifacts"][role], prior_dir / filename)
            refs.append(bound)
    validation = validate_worker_spec(spec)
    require(validation.get("status") == "validated" and validation.get("case_id") == case
            and validation.get("stage") == stage, "Offline worker validation identity differs")
    _, rubric_ref = read_bound(RUBRIC_REF)
    response, response_ref = read_bound(transport["response_artifact"], stage_dir / "http_0001_generation" / "response.json")
    if response != transport.get("response") or response.get("done") is not True or response.get("done_reason") != "stop":
        raise ValueError("Completed response envelope mismatch")
    raw = response["message"]["content"]
    try:
        parsed, exact = strict(raw), strict(raw, exact=True)
        parse_error = None
    except (ValueError, TypeError, DecimalException) as error:
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
        prior_response, prior_actual_ref = read_bound(prior_ref, prior_dir / "http_0001_generation" / "response.json")
        prior_text = prior_response["message"]["content"]
        if prior_response.get("done") is not True or prior_response.get("done_reason") != "stop" or prior_text != spec["raw_draft"] or prior_text != messages[2]["content"]:
            raise ValueError("Final does not retain its exact actual own D0")
        try:
            prior_vector = decimal_vector(strict(prior_text, exact=True))
        except (ValueError, TypeError, AttributeError, DecimalException):
            prior_vector = None
        refs.append(prior_actual_ref)
    require(validation.get("expected_source_packet") == packet, "Offline worker source differs")
    passages = source_passages(packet)
    visible = visible_ids(initial) | visible_ids(final or {})
    require(set(validation.get("visible_evidence_ids", [])) == visible, "Offline worker visible IDs differ")
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
    result.update(purpose="pilot_completion_resume", analysis_role="primary_exploratory",
                  own_D0_stage_directory=prior_dir.relative_to(ROOT).as_posix() if stage == "F0" else None,
                  own_D0_origin=("fixed_previous_completion_segment" if case == EXTERNAL_CASE else "same_remaining_run") if stage == "F0" else None,
                  own_D0_declaration_ref=(declaration["external_draft_evidence_refs"]["declaration"] if case == EXTERNAL_CASE else declaration_ref) if stage == "F0" else None,
                  worker_validation=validation, external_allocation_math="separate_derived_artifact_not_applied_here",
                  reported_source_identity_matches=(parsed.get("source_id") == expected_source) if isinstance(parsed, dict) else None,
                  source_reading_scope="Actual assigned visible packet; labels are not mandatory weight targets.")
    # Reject a race/change across preparation. No record is rewritten.
    unique = {}
    for ref in refs:
        path = workspace_path(ref["path"])
        require(sha(path.read_bytes()) == ref["sha256"], "Bound artifact changed during preparation")
        unique[(ref["path"], ref["sha256"])] = ref
    result["refs"] = list(unique.values())
    return result



def write_new(stage_directory, output):
    output = workspace_path(output)
    if not output.is_relative_to(REPORT_ROOT) or output.exists():
        raise ValueError("A new exclusive report path under remaining_20261026 is required")
    result = prepare(stage_directory)
    # Full safe serialization precedes exclusive creation; raw strings preserved.
    content = json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False) + "\n"
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = write_new(args.stage_dir, args.output)
    print(json.dumps({"status": result["status"], "output": str(args.output),
                      "semantic_review_status": result["semantic_review_status"]}))


if __name__ == "__main__":
    main()
