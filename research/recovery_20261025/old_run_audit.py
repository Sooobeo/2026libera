"""Read-only recovery audit of the interrupted 2026-10-19 pilot.

Writes only new recovery receipts. No model calls or original-run summary writes.
Independent Decimal/citation checks precede frozen offline analyzer functions.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUN = ROOT / "data/local_sector_runtime/v492_pilot_20261019"
CASES = ["fidelity_q2_2026__E", "fidelity_q2_2026__L", "ubs_june_2026__E", "ubs_june_2026__L", "common_market_only__C"]
CODES = ["10", "15", "20", "25", "30", "35", "40", "45", "50", "55", "60"]
TOL = Decimal("0.000001")

def ref(path):
    path = Path(path)
    raw = path.read_bytes()
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}

def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate_JSON_key:" + key)
        result[key] = value
    return result

def parse(raw, decimal=False):
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)),
                      **({"parse_float": Decimal, "parse_int": Decimal} if decimal else {}))

def read(path):
    return parse(Path(path).read_text(encoding="utf-8-sig"))

def declarations(value):
    """Find only explicit ID declarations, including column-encoded fact tables."""
    found = set()
    if isinstance(value, dict):
        for key in ("fact_id", "evidence_id"):
            if isinstance(value.get(key), str):
                found.add(value[key])
        if isinstance(value.get("columns"), list) and isinstance(value.get("rows"), list):
            for row in value["rows"]:
                if isinstance(row, list) and len(row) == len(value["columns"]):
                    found.update(declarations(dict(zip(value["columns"], row))))
        for child in value.values():
            found.update(declarations(child))
    elif isinstance(value, list):
        for child in value:
            found.update(declarations(child))
    return found

def citations(value, path=()):
    found, malformed = [], []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ("source_evidence_ids", "decision_evidence_ids", "evidence_ids"):
                if isinstance(child, list) and all(isinstance(v, str) for v in child):
                    found.extend({"path": list(path + (key,)), "id": v} for v in child)
                else:
                    malformed.append(list(path + (key,)))
            else:
                a, b = citations(child, path + (key,)); found.extend(a); malformed.extend(b)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            a, b = citations(child, path + (i,)); found.extend(a); malformed.extend(b)
    return found, malformed

def independent_stage(case, stage):
    target = RUN / (case + "__" + stage)
    requests = sorted(target.glob("http_*_generation/request.json")) if target.exists() else []
    row = {"case_id": case, "stage": stage, "durable_generation_requests": len(requests),
           "request_refs": [ref(p) for p in requests], "raw_sum_exact_decimal": None,
           "valid_raw_allocation": False, "whole_response_observed": False,
           "error_review": [], "integrity_review": [], "topic_connection_review": []}
    if not requests:
        row.update(classification="missing_observation_not_attempted", runtime_terminal_status=None)
        row["topic_connection_review"].append("Unattempted slots stay in the five-case denominator; no institutional-effect inference from absence.")
        return row, None
    spec = read(target / "worker_spec.json")
    row["spec_ref"] = ref(target / "worker_spec.json")
    allowed, institutions, vocab = set(), [], set()
    for message in spec["body"]["messages"]:
        if message["role"] != "user":
            continue
        payload = parse(message["content"])
        for key in ("common_context", "common_market", "public_numeric_fact_index", "institution_document", "actual_draft_calculator_feedback"):
            if key in payload:
                allowed.update(declarations(payload[key]))
        if "institution_document" in payload:
            source = payload["institution_document"]
            institutions.append(source["source_id"])
            v = source.get("rating_vocabulary", [])
            vocab.update(v.keys() if isinstance(v, dict) else v)
    row.update(allowed_evidence_id_count=len(allowed), supplied_institution_ids=institutions)
    row["integrity_review"].append("Allowed IDs were independently extracted only from actual user input payloads; prior assistant output was excluded.")
    whole = target / "http_0001_generation/response.json"
    worker_path = target / "worker_summary.json"
    worker = read(worker_path) if worker_path.exists() else None
    row["runtime_terminal_status"] = worker.get("status") if worker else None
    record = {"stage": stage, "status": worker["status"] if worker else "reconciled_interruption_unknown_cause",
              "generation_requests_attempted": len(requests)}
    if not whole.exists():
        row.update(classification="infrastructure_interruption_terminal_record_missing",
                   stream_bytes=(target / "http_0001_generation/raw_stream.bin").stat().st_size,
                   event_bytes=(target / "http_0001_generation/events.jsonl").stat().st_size,
                   absent_terminal_artifacts=[p for p in ("worker_summary.json", "transport_result.json", "supervisor_result.json", "http_0001_generation/response.json") if not (target / p).exists()])
        row["error_review"].append("A durable request exists but no response, terminal status, or timeout receipt survives. Root cause remains unknown; this is not an observed model allocation failure.")
        row["topic_connection_review"].append("Missing final is not zero distance, non-adoption, or evidence of convergence.")
        return row, record
    response = read(whole)
    value = parse(response["message"]["content"], decimal=True)
    transport = read(target / "transport_result.json")
    binding = transport["response_artifact"]
    bound = binding["sha256"] == ref(whole)["sha256"] and Path(binding["path"]).resolve() == whole.resolve() and transport["response"] == response
    rows = value["sectors"]
    code_counts = Counter(r.get("sector_code") for r in rows)
    complete = len(rows) == 11 and set(code_counts) == set(CODES) and all(n == 1 for n in code_counts.values())
    weights = [r["weight"] for r in rows]
    finite = all(isinstance(v, Decimal) and v.is_finite() for v in weights)
    total = sum(weights, Decimal(0)) if complete and finite else None
    valid = total is not None and all(0 <= v <= 1 for v in weights) and abs(total - 1) <= TOL
    cited, malformed = citations(value)
    unavailable = [c for c in cited if c["id"] not in allowed]
    row.update(classification="ordinary_model_output_with_recorded_transport_completion",
               whole_response_observed=True, response_ref=ref(whole), response_artifact_bound=bound,
               response_done=response.get("done"), done_reason=response.get("done_reason"),
               complete_eleven_vector=complete, raw_weights_exact_decimal={r["sector_code"]: str(r["weight"]) for r in rows},
               raw_sum_exact_decimal=str(total) if total is not None else None,
               raw_budget_residual_exact_decimal=str(total - 1) if total is not None else None,
               valid_raw_allocation=valid, citation_occurrences=len(cited),
               unavailable_citations=unavailable, malformed_citation_fields=malformed,
               semantic_citation_support_verified=False,
               source_label_outside_supplied_vocabulary=[{"sector_code": r["sector_code"], "source_label": r["source_label"]} for r in rows if vocab and r["source_label"] not in vocab],
               recorded_contract_diagnostics_ref=ref(target / "response_contract_validation.json"))
    row["error_review"].extend((["Raw budget constraint fails; no normalization or residual repair."] if not valid else []) +
                               (["Unavailable citation IDs occur in visible output."] if unavailable else []))
    row["integrity_review"].append("Whole response SHA and original absolute artifact binding match: " + str(bound))
    row["topic_connection_review"].append("Allocation validity and ID availability are diagnostics; source interpretation and reason-choice agreement require semantic review. Failed budget blocks portfolio distance, not descriptive inspection of reasons.")
    return row, record

def write_new(name, value):
    path = OUT / name
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return path

def main():
    created = datetime.now(timezone.utc).isoformat()
    before = {str(p.resolve()): ref(p) for p in RUN.rglob("*") if p.is_file()}
    declaration = read(RUN / "pilot_declaration.json")
    assert declaration["case_order"] == CASES
    rows, cases = [], []
    for case in CASES:
        records = []
        for stage in ("D0", "F0"):
            row, record = independent_stage(case, stage); rows.append(row)
            if record: records.append(record)
        cases.append({"case_id": case, "stages": records})
    total = sum(r["durable_generation_requests"] for r in rows)
    summary = {"recovery_version": "old_run_reconciliation_1", "created_at_utc": created,
               "status": "externally_reconciled_interrupted_sequence", "original_runtime_summary_exists": (RUN / "pilot_summary.json").exists(),
               "not_a_runtime_completion_receipt": True, "original_run_directory": str(RUN),
               "provenance": "Reconstructed from durable request envelopes, original worker summaries and whole response artifacts on 2026-10-25; never written into original run.",
               "declaration_ref": ref(RUN / "pilot_declaration.json"), "cases": cases,
               "generation_requests_attempted": total, "durable_render_requests": len(list(RUN.glob("*/render_only/request.json"))),
               "generation_request_count_scope": "Durable envelopes; does not prove every request reached inference.",
               "main_model_calls_observed": 0, "automatic_retries_observed": 0, "post_final_calls_observed": 0,
               "remaining_planned_generation_slots": 10 - total, "root_cause": "unknown",
               "recovery_model_calls": 0, "original_artifacts_modified": False}
    summary_path = write_new("old_run_reconciled_summary.json", summary)
    finals = [r for r in rows if r["stage"] == "F0"]
    watcher = read(ROOT / "research/v492_postpilot_status_20261019.json")
    audit = {"audit_version": "old_run_independent_audit_1", "created_at_utc": created,
             "reconciled_summary_ref": ref(summary_path), "original_manifest": list(before.values()),
             "planned_cases": 5, "planned_final_sector_rows": 55, "planned_stage_slots": 10,
             "observed_terminal_stages": sum(r["whole_response_observed"] for r in rows),
             "observed_finals": sum(r["whole_response_observed"] for r in finals),
             "valid_final_allocations": sum(r["valid_raw_allocation"] for r in finals),
             "stage_records": rows,
             "watcher_incident": {"ref": ref(ROOT / "research/v492_postpilot_status_20261019.json"), "state": watcher["state"], "error_type": watcher["error_type"], "finished_at_utc": watcher["finished_at_utc"],
                  "causality": "Watcher error occurred before UBS E F0 began; it establishes postprocessing failure, not the cause of model-run interruption."},
             "interruption_evidence": {"last_worker_phase": read_jsonl_last(RUN / "ubs_june_2026__E__F0/worker_phases.jsonl"),
                  "last_monitor": {k: v for k, v in read_jsonl_last(RUN / "ubs_june_2026__E__F0/monitor.jsonl").items() if k == "elapsed_seconds"},
                  "monitor_ref": ref(RUN / "ubs_june_2026__E__F0/monitor.jsonl"),
                  "server_log_ref": ref(ROOT / "data/local_sector_runtime/v492_pilot_cpu_20261019/server.stderr.log"),
                  "observed_server_tail": "Last task reached 16,384 prompt tokens then a cancel-task entry. Cancellation initiator and reason are not recorded.",
                  "not_inferred": ["deadline timeout", "out of memory", "model semantic refusal", "watcher caused generation cancellation"]},
             "topic_review": "Preserves the narrowed paper question: whether public institutional evidence is retained in visible reasons and actual sector choices under a shared AI workflow. E/L timing and the common-only C remain the design; failures are not recoded as convergence or ignored evidence.",
             "error_integrity_topic_stage_gate": "PASS for read-only recovery accounting; FAIL for complete valid five-case pilot; semantic support pending.",
             "model_calls": 0, "normalized_or_repaired": False}
    # Call frozen functions on original absolute paths. Do not manufacture a
    # pilot_summary to bypass its completed-run gate or alter bound artifacts.
    analyzer_path = ROOT / "research/analyze_v492_pilot.py"
    assert ref(analyzer_path)["sha256"] == "841c1f941e2c39165f84f51f5df283ca7a3c5727de285d4ad56edfa50166529f"
    spec = importlib.util.spec_from_file_location("frozen_v492_analyzer", analyzer_path)
    analyzer = importlib.util.module_from_spec(spec); spec.loader.exec_module(analyzer)
    protocol, protocol_ref = analyzer.pinned(ROOT / analyzer.PROTOCOL, analyzer.PROTOCOL_SHA)
    schema, schema_ref = analyzer.pinned(ROOT / analyzer.SCHEMA, analyzer.SCHEMA_SHA)
    cr = protocol["computational_references_ref"]
    comp, comp_ref = analyzer.pinned(ROOT / cr["path"], cr["sha256"])
    artifacts, recovered = [], []
    for case in cases:
        records = {s["stage"]: s for s in case["stages"]}
        for stage in ("D0", "F0"):
            recovered.append(analyzer.load_stage(RUN, case["case_id"], stage, records.get(stage), schema, artifacts))
    crosschecks = []
    for a, b in zip(rows, recovered):
        if a["whole_response_observed"]:
            same = Decimal(a["raw_sum_exact_decimal"]) == Decimal(b["vector"]["raw_sum_exact_decimal"])
            same_ids = a["unavailable_citations"] == b["citation_visibility"]["unavailable_citations"]
            crosschecks.append({"case_id": a["case_id"], "stage": a["stage"], "exact_sum_agrees": same, "unavailable_citations_agree": same_ids, "response_bound": b["response_artifact_bound"]})
            assert same and same_ids and b["response_artifact_bound"]
    after = {str(p.resolve()): ref(p) for p in RUN.rglob("*") if p.is_file()}
    assert before == after, "original_run_changed_during_audit"
    audit["original_manifest_unchanged_after_analysis"] = True
    audit["independent_crosschecks_against_frozen_functions"] = crosschecks
    audit_path = write_new("old_run_interruption_audit.json", audit)
    offline = {"recovery_adapter_version": "read_only_frozen_functions_1", "created_at_utc": created,
               "scope": "Arithmetic and ID-availability recovery analysis of interrupted run. Not an original runtime completion or semantic review.",
               "original_run_directory": str(RUN), "reconciled_summary_ref": ref(summary_path), "independent_audit_ref": ref(audit_path),
               "analyzer_ref": ref(analyzer_path), "evaluation_protocol_ref": protocol_ref, "response_schema_ref": schema_ref,
               "computational_references_ref": comp_ref, "input_artifacts": artifacts, "stage_records": recovered,
               "recovery_caveat": "Frozen load_stage flags the interrupted UBS E F0 missing transport_result as artifact_integrity_failure. The independent audit separately identifies terminal-record absence after an attempted request; no tampering, schema failure, or budget failure is inferred for the missing output.",
               "original_summary_gate_not_invoked": True, "original_artifacts_modified": False,
               "generation_requests_made_by_adapter": 0, "semantic_support_verified": False,
               **analyzer.aggregate(recovered, comp["references"])}
    result = write_new("old_run_recovered_arithmetic.json", offline)
    print(json.dumps({"audit": str(audit_path), "arithmetic": str(result), "generation_requests": total,
                      "completed_stages": audit["observed_terminal_stages"], "finals": audit["observed_finals"],
                      "stage_diagnostics": [{k: r.get(k) for k in ("case_id", "stage", "raw_sum_exact_decimal", "unavailable_citations")} for r in rows if r["whole_response_observed"]]}, ensure_ascii=False))

def read_jsonl_last(path):
    return parse(Path(path).read_text(encoding="utf-8").splitlines()[-1])

if __name__ == "__main__":
    main()
