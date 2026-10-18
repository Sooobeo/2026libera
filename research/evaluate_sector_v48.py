"""Offline v4.8 factual checks and unfilled semantic review preparation.

Pure public functions perform no file, network or model access. Annotation gold
is explicitly evaluator-only. Citation resolution is not entailment, and no
automatic strategic score is produced. C0 and repairs must be evaluated apart.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from collections import Counter
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, ROUND_HALF_UP
from typing import Any

from sector_engine import SECTOR_CODES, calculate_portfolio, validate_gold, validate_weights
from sector_response_schema import validate_response

VERSION = "v4.8-offline-1"
ARMS = ("R1", "R4")
TUPLE_FIELDS = ("subject", "predicate_or_metric", "value_or_relation", "unit",
                "period_or_as_of", "source_or_fact_id", "data_version")


def _decimal(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _json_parse(text):
    """Retain duplicate/nonfinite distinctions; never extract JSON from prose."""
    if not isinstance(text, str) or not text:
        return None, "no_response"

    def pairs(items):
        answer = {}
        for key, value in items:
            if key in answer:
                raise ValueError("duplicate_keys")
            answer[key] = value
        return answer

    def constant(_):
        raise ValueError("nonfinite_number")

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
        if not isinstance(value, dict):
            return None, "invalid_json_object"
        # Overflowed legal exponent syntax is still nonfinite after parsing.
        def finite(item):
            if isinstance(item, float):
                return math.isfinite(item)
            if isinstance(item, dict):
                return all(finite(v) for v in item.values())
            if isinstance(item, list):
                return all(finite(v) for v in item)
            return True
        return (value, "valid_json") if finite(value) else (None, "nonfinite_number")
    except ValueError as exc:
        return None, str(exc) if str(exc) in ("duplicate_keys", "nonfinite_number") else "invalid_json"
    except (TypeError, OverflowError, RecursionError):
        return None, "invalid_json"


def _rows(rows):
    """All duplicate occurrences remain available for review, none earns credit."""
    indexed = {code: [] for code in SECTOR_CODES}
    if isinstance(rows, list):
        for position, item in enumerate(rows):
            if isinstance(item, dict) and isinstance(item.get("sector_code"), str):
                if item["sector_code"] in indexed:
                    indexed[item["sector_code"]].append((position, item))
    return indexed


def _fact_map(registry, calculator_facts=()):
    """Normalize facts; non-sector public subjects use their exact JSON pointer."""
    registry = registry or {}
    default_version = registry.get("source", {}).get("sha256") or registry.get("version")
    result = {}
    for row in list(registry.get("rows", [])) + list(registry.get("matrix_fact_references", [])) + list(calculator_facts or []):
        if not isinstance(row, dict):
            raise ValueError("Fact registry rows must be objects")
        identifier = row.get("fact_id", row.get("source_or_fact_id"))
        if not isinstance(identifier, str) or not identifier or identifier in result:
            raise ValueError("Fact IDs must be explicit and unique")
        item = copy.deepcopy(row)
        item.update({
            "subject": row.get("subject", row.get("sector_code") or row.get("source_json_pointer")),
            "predicate_or_metric": row.get("predicate_or_metric", row.get("metric")),
            "value_or_relation": row.get("value_or_relation", row.get("value")),
            "unit": row.get("unit"),
            "period_or_as_of": row.get("period_or_as_of", row.get("period")),
            "source_or_fact_id": identifier,
            "data_version": row.get("data_version", default_version if identifier.startswith("M:") else None),
        })
        result[identifier] = item
    return result


def verify_claim(claim, registry, calculator_facts=(), *, visible_fact_ids=None,
                 current_candidate_id=None):
    """Check one manually transcribed literal numeric claim, never free prose.

The caller must record the quoted response location and normalized tuple. A
missing tuple component stays not-assessable. Exact decimal comparison is the
default. Display rounding is allowed only via the reference fact's pre-recorded
precision_policy {kind: decimal_places, places: N, rounding: HALF_EVEN|HALF_UP}.
The claim cannot supply its own favorable tolerance. No unit conversion or
period/entity inference occurs. A fact ID must have been visible before the
response. Model-derived pending claims instead name a captured candidate and a
supported formula, and are checked against explicit evaluator-derived facts.
"""
    output = {"assessment_status": "not_assessable", "reason": None,
              "numeric_discrepancy_raw": None, "tuple_mismatches": [],
              "semantic_claim_extraction_automated": False,
              "reference_tuple": None, "precision_rule": None}
    if not isinstance(claim, dict):
        output["reason"] = "claim_record_missing"
        return output
    normalized = claim.get("normalized_claim_tuple", claim)
    if not isinstance(normalized, dict):
        output["reason"] = "claim_tuple_missing"
        return output
    # Transcription and numeric verification are separate responsibilities.
    if not claim.get("literal_claim_text") or not claim.get("response_field_and_span"):
        output["reason"] = "literal_quote_or_response_locator_missing"
        return output
    derived = claim.get("provenance_type") == "model_derived_pending"
    facts = _fact_map(registry, calculator_facts)
    identifier = normalized.get("source_or_fact_id")
    if derived:
        candidate = claim.get("candidate_id")
        formula = claim.get("formula")
        matches = [fact for fact in facts.values()
                   if fact.get("evaluator_only") is True
                   and fact.get("candidate_id") == candidate
                   and fact.get("formula") == formula
                   and fact.get("subject") == normalized.get("subject")
                   and fact.get("predicate_or_metric") == normalized.get("predicate_or_metric")]
        if not candidate or candidate != current_candidate_id or not formula or len(matches) != 1:
            output["reason"] = "current_candidate_or_formula_not_established"
            return output
        if claim.get("identified_as_model_derived_pending") is not True:
            output["reason"] = "derivation_not_identified_as_pending"
            return output
        reference = matches[0]
    else:
        if identifier not in facts:
            output.update(assessment_status="not_stated_in_visible_evidence", reason="unknown_fact_id")
            return output
        reference = facts[identifier]
        if reference.get("evaluator_only") is True or visible_fact_ids is None or identifier not in visible_fact_ids:
            output.update(assessment_status="not_stated_in_visible_evidence", reason="fact_not_visible_before_response")
            return output
        claimed_candidate = claim.get("candidate_id")
        if claimed_candidate is not None and claimed_candidate != reference.get("candidate_id"):
            output.update(assessment_status="contradicted", reason="wrong_candidate_lineage")
            return output
        if claim.get("applies_to_current_candidate") is True and reference.get("candidate_id") != current_candidate_id:
            output.update(assessment_status="contradicted", reason="earlier_candidate_is_not_current_verification")
            return output
    output["reference_tuple"] = {key: reference.get(key) for key in TUPLE_FIELDS}
    fields = [key for key in TUPLE_FIELDS if key != "value_or_relation"
              and not (derived and key == "source_or_fact_id")]
    # Candidate-local algebra has no calendar period. Nonapplicability must be
    # declared by the fact and the transcription, with matched candidate lineage.
    period_not_applicable = (
        reference.get("period_scope") == "candidate_local_no_calendar_period"
        and claim.get("period_scope") == "candidate_local_no_calendar_period"
        and claim.get("candidate_id") == reference.get("candidate_id")
        and claim.get("candidate_id") is not None
        and "period_or_as_of" in normalized and normalized["period_or_as_of"] is None
        and reference.get("period_or_as_of") is None)
    missing = [key for key in fields if (normalized.get(key) is None or reference.get(key) is None)
               and not (key == "period_or_as_of" and period_not_applicable)]
    if missing:
        output["reason"] = "incomplete_tuple:" + ",".join(missing)
        return output
    mismatches = [key for key in fields if normalized[key] != reference[key]]
    output["tuple_mismatches"] = mismatches
    actual, expected = _decimal(normalized.get("value_or_relation")), _decimal(reference.get("value_or_relation"))
    if actual is None or expected is None:
        output["reason"] = "non_numeric_or_missing_value"
        return output
    output["numeric_discrepancy_raw"] = str(actual - expected)
    precision = reference.get("precision_policy")
    output["precision_rule"] = copy.deepcopy(precision) if precision else {"kind": "exact_decimal", "tolerance": "0"}
    if precision:
        rounding = {"HALF_EVEN": ROUND_HALF_EVEN, "HALF_UP": ROUND_HALF_UP}
        if (precision.get("kind") != "decimal_places" or type(precision.get("places")) is not int
                or precision["places"] < 0 or precision.get("rounding") not in rounding):
            output["reason"] = "unsupported_reference_precision_rule"
            return output
        try:
            expected = expected.quantize(Decimal(1).scaleb(-precision["places"]), rounding=rounding[precision["rounding"]])
        except InvalidOperation:
            output["reason"] = "reference_precision_cannot_be_applied"
            return output
    supported = not mismatches and actual == expected
    output.update(assessment_status="supported" if supported else "contradicted",
                  reason="full_tuple_and_numeric_match" if supported else "tuple_or_value_mismatch")
    return output


def _citations(ids, code, gold, facts, visible_ids):
    if not isinstance(ids, list) or any(not isinstance(eid, str) for eid in ids):
        return {"syntax_valid": False, "entries": [], "semantic_entailment": None}
    entries = []
    for eid in ids:
        entry = {"evidence_id": eid, "visible": eid in visible_ids,
                 "kind": "unknown", "sector_scope_matches": None, "entails_claim": None}
        if eid in gold["evidence_index"]:
            reference = gold["evidence_index"][eid]
            entry.update(kind="document", sector_scope_matches=code in reference["sector_codes"],
                         annotated_claim_kinds=list(reference["claims"]))
        elif eid in facts:
            reference = facts[eid]
            scope = (code in reference["sector_order"] if isinstance(reference.get("sector_order"), list)
                     else reference.get("sector_code", reference.get("subject")) == code)
            entry.update(kind="public_numeric" if eid.startswith("M:") else "calculator_numeric",
                         sector_scope_matches=scope)
        entries.append(entry)
    return {"syntax_valid": len(ids) == len(set(ids)), "entries": entries,
            "semantic_entailment": None, "meaning": "resolution_and_scope_only_not_support_verdict"}


def _execution(metadata, text, parse_status, schema, weights):
    attempted = metadata.get("attempted") is True
    completed = metadata.get("transport_completed") is True
    status = metadata.get("attempt_status")
    if status is None:
        status = "completed_response" if completed else "attempted_no_response" if attempted else "not_attempted"
    if not attempted:
        category = "not_attempted"
    elif not completed:
        category = "execution_or_infrastructure_failure"
    elif parse_status != "valid_json" or not schema["valid"]:
        category = "model_response_contract_failure"
    elif not weights["valid"]:
        category = "model_allocation_arithmetic_failure"
    else:
        category = "completed_contract_and_arithmetic_valid"
    return {"attempted": attempted, "transport_completed": completed,
            "workflow_generation_attempted": metadata.get("workflow_generation_attempted", attempted) is True,
            "workflow_status": metadata.get("workflow_status"),
            "workflow_termination_reason": metadata.get("workflow_termination_reason"),
            "attempt_status": status, "outcome_category": category,
            "termination_reason": metadata.get("termination_reason"),
            "transport_status": metadata.get("transport_status"),
            "parse_status": parse_status, "contract_status": schema["status"],
            "contract_valid": schema["valid"], "human_readable_text_present": bool(isinstance(text, str) and text.strip()),
            "readability_scope": "nonempty_text_present; actual interpretability requires review",
            "raw_sum": weights["raw_sum"], "signed_budget_residual": weights["raw_budget_residual"],
            "arithmetic_valid": weights["valid"],
            # A missing explanation does not alter an otherwise identifiable raw
            # vector. Contract compliance and financial feasibility stay separate.
            "valid_raw_allocation": attempted and completed and parse_status == "valid_json" and weights["valid"],
            "elapsed_seconds": metadata.get("elapsed_seconds"), "no_external_weight_repair": True}


def evaluate_case(response_text_or_none, source_packet, gold, market, registry, execution_metadata):
    """Evaluate one captured endpoint and prepare 11 unjudged sector reviews."""
    validate_gold(gold)
    metadata = copy.deepcopy(execution_metadata)
    source = gold["source_id"]
    if source_packet.get("source_id") != source or metadata.get("source_id", source) != source:
        raise ValueError("Packet, gold and metadata source identities disagree")
    arm = metadata.get("arm")
    if arm not in ARMS:
        raise ValueError("A declared R1/R4 arm is required")
    endpoint = metadata.get("endpoint", "C0")
    if endpoint not in ("C0", "C1", "C2"):
        raise ValueError("Endpoint must be C0, C1 or C2; stages are not independent cases")
    case_id = metadata.get("case_id", source + "__" + arm)
    if case_id != source + "__" + arm:
        raise ValueError("Case ID must match the declared source and arm")
    if metadata.get("transport_completed") is True and metadata.get("attempted") is not True:
        raise ValueError("A completed response cannot be unattempted")
    text = response_text_or_none
    parsed, parse_status = _json_parse(text)
    schema = validate_response(text, 4, source, True)
    response = parsed or {}
    weights = validate_weights(response.get("weights"))
    execution = _execution(metadata, text, parse_status, schema, weights)
    # Visibility comes from the actual request record, never the model's citations.
    supplied_visible = metadata.get("visible_evidence_ids", metadata.get("visible_evidence_ids_before_generation"))
    visible = set(supplied_visible or [])
    calculator_facts = metadata.get("calculator_facts", metadata.get("visible_calculator_facts_before_generation", []))
    facts = _fact_map(registry, calculator_facts)
    calculation = calculate_portfolio(response.get("weights"), market, sorted(visible), response.get("submitted_constraints", []))
    source_constraints = calculate_portfolio(response.get("weights"), None,
                                            list(gold["evidence_index"]), gold.get("constraints", []))
    constraint_checks = source_constraints["submitted_constraint_checks"]
    violations = [row for row in constraint_checks["checks"] if row.get("violation") is not None and row["violation"] > 0]
    execution["explicit_document_constraint_violations"] = violations
    execution["valid_raw_allocation"] = execution["valid_raw_allocation"] and not violations
    if violations and execution["outcome_category"] == "completed_contract_and_arithmetic_valid":
        execution["outcome_category"] = "model_explicit_document_constraint_failure"
    interpretations, allocations = _rows(response.get("interpretations")), _rows(response.get("weights"))
    source_matches = response.get("source_id") == source
    passages = {item["evidence_id"]: item for item in source_packet.get("evidence_passages", [])}
    baseline = market.get("baseline_weights", {}) if isinstance(market, dict) else {}
    rows, quote_fields = [], []
    for code in SECTOR_CODES:
        irows, wrows = interpretations[code], allocations[code]
        interpretation = irows[0][1] if len(irows) == 1 else None
        allocation = wrows[0][1] if len(wrows) == 1 else None
        expected = gold["sector_ratings"][code]
        rating = interpretation.get("rating") if interpretation else None
        observed_label_correct = source_matches and isinstance(rating, str) and rating.strip() == expected["rating"]
        label_correct = observed_label_correct and execution["attempted"] and execution["transport_completed"]
        raw_weight = allocation.get("weight") if allocation else None
        numeric_weight = _decimal(raw_weight) if isinstance(raw_weight, (int, float)) and not isinstance(raw_weight, bool) else None
        base = _decimal(baseline.get(code))
        for field, occurrences, key in (("interpretations", irows, "reason"), ("weights", wrows, "rationale")):
            for index, item in occurrences:
                if isinstance(item.get(key), str):
                    quote_fields.append({"literal_text": item[key], "response_field_and_span": f"/{field}/{index}/{key}",
                                         "sector_code": code, "claim_extraction_status": "manual_review_pending",
                                         "normalized_claim_tuples": [], "semantic_assessment": None})
        rows.append({
            "sector_code": code, "source_id": source,
            "source_literal_rating": expected["rating"], "model_literal_rating": rating,
            "exact_label_correct": bool(label_correct),
            "observed_exact_label_in_readable_material": bool(observed_label_correct),
            "interpretation_occurrences": copy.deepcopy(irows), "weight_occurrences": copy.deepcopy(wrows),
            "source_separate_reason_available": bool(expected.get("reason_evidence_ids")),
            "source_passages": [copy.deepcopy(passages[eid]) for eid in dict.fromkeys(expected["evidence_ids"] + expected.get("reason_evidence_ids", [])) if eid in passages],
            "interpretation_reason_literal": interpretation.get("reason") if interpretation else None,
            "allocation_rationale_literal": allocation.get("rationale") if allocation else None,
            "interpretation_citations": _citations(interpretation.get("evidence_ids") if interpretation else None, code, gold, facts, visible),
            "allocation_citations": _citations(allocation.get("evidence_ids") if allocation else None, code, gold, facts, visible),
            "weight_row_presence": "present" if len(wrows) == 1 else "missing" if not wrows else "duplicate",
            "raw_weight": raw_weight, "baseline_id": market.get("baseline_id") if isinstance(market, dict) else None,
            "raw_baseline_weight": baseline.get(code),
            "raw_active_weight_decimal": str(numeric_weight - base) if numeric_weight is not None and base is not None else None,
            "vector_validity_at_endpoint": execution["valid_raw_allocation"],
            "literal_stance": None, "claim_support": None, "action_consistency": None,
            "source_to_action_assessment_status": None, "reviewer_id": None,
            "review_status": "not_started", "independent_human_review_completed": False,
        })
    for field in ("alternatives", "risk_discussion", "unresolved"):
        value = response.get(field)
        values = list(enumerate(value)) if isinstance(value, list) else [(None, value)]
        for index, item in values:
            if isinstance(item, str):
                quote_fields.append({"literal_text": item, "response_field_and_span": "/" + field + ("/" + str(index) if index is not None else ""),
                                     "sector_code": None, "claim_extraction_status": "manual_review_pending",
                                     "normalized_claim_tuples": [], "semantic_assessment": None})
    if parsed is None and isinstance(text, str) and text.strip():
        quote_fields.append({"literal_text": text, "response_field_and_span": "raw_response_text:entire",
                             "sector_code": None, "claim_extraction_status": "manual_review_pending_unparsed_fragment",
                             "normalized_claim_tuples": [], "semantic_assessment": None})
    correct = sum(row["exact_label_correct"] for row in rows)
    risk = calculation.get("market_diagnostics", {}).get("risk") if execution["valid_raw_allocation"] else None
    return {
        "evaluation_version": VERSION, "case_id": case_id, "source_id": source, "arm": arm,
        "split": metadata.get("split", source_packet.get("split")), "endpoint": endpoint,
        "response_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if isinstance(text, str) else None,
        "execution": execution, "schema_validation": schema, "allocation": weights,
        "source_fact_preservation": {"exact_label_correct_count": correct, "expected_sector_count": 11,
                                     "observed_exact_labels_in_readable_material": sum(row["observed_exact_label_in_readable_material"] for row in rows),
                                     "accuracy": correct / 11, "source_identity_matches": source_matches,
                                     "endpoint_credit_rule": "Primary credit requires completed captured endpoint; partial readable labels remain a separate diagnostic.",
                                     "role": "supporting_factual_diagnostic_not_strategic_preservation"},
        "source_annotation_status": copy.deepcopy(gold.get("review_status", {})),
        "source_material_context": {key: copy.deepcopy(source_packet.get(key)) for key in
                                    ("title", "issuer", "source_url", "dates", "task_scope", "rating_vocabulary", "evidence_passages")},
        "visibility_metadata_present": supplied_visible is not None,
        "raw_calculator_diagnostics": calculation,
        "valid_portfolio_risk": risk,
        "review_preparation": {"review_status": "not_started", "reviewer_role": None,
                               "independent_human_review_completed": False,
                               "automatic_semantic_certification": False,
                               "sector_reviews": rows, "literal_fields_for_manual_claim_review": quote_fields,
                               "semantic_assessed_sector_count": 0, "expected_sector_count": 11,
                               "strategic_preservation_verdict": None},
        "interpretation_limits": ["No unique correct portfolio is supplied by qualitative source ratings.",
                                  "Citation resolution and exact labels do not establish evidence-to-action preservation.",
                                  "Invalid allocations retain assessable text but have no valid-portfolio distance or risk.",
                                  "This evaluator does not replace independent human source or semantic review."],
    }


def evaluate_bundle(cases, source_ids):
    """C0-only fixed four-case report; absence never shrinks the denominator."""
    if len(source_ids) != 2 or len(set(source_ids)) != 2 or any(not isinstance(s, str) for s in source_ids):
        raise ValueError("Exactly two prespecified distinct source IDs are required")
    roster = [(source, arm, source + "__" + arm) for source in source_ids for arm in ARMS]
    expected = {case_id for _, _, case_id in roster}
    by_id = {}
    for case in cases:
        if case.get("endpoint") != "C0":
            raise ValueError("Primary bundles accept only C0; repairs must remain separate")
        case_id = case.get("case_id")
        if case_id not in expected or case_id in by_id:
            raise ValueError("Unknown or duplicate case; no silent selection")
        if case_id != case.get("source_id", "") + "__" + case.get("arm", ""):
            raise ValueError("Inconsistent source/arm identity")
        by_id[case_id] = case
    case_rows = []
    for source, arm, case_id in roster:
        case = by_id.get(case_id)
        execution = case["execution"] if case else {}
        case_rows.append({"case_id": case_id, "source_id": source, "arm": arm,
                          "artifact_present": case is not None,
                          "workflow_generation_attempted": execution.get("workflow_generation_attempted", False),
                          "C0_attempted": execution.get("attempted", False),
                          "workflow_status": execution.get("workflow_status"),
                          "workflow_termination_reason": execution.get("workflow_termination_reason"),
                          "transport_completed": execution.get("transport_completed", False),
                          "outcome_category": execution.get("outcome_category", "not_attempted_artifact_absent"),
                          "valid_raw_allocation": execution.get("valid_raw_allocation", False),
                          "label_correct": case["source_fact_preservation"]["exact_label_correct_count"] if case else 0,
                          "expected_sectors": 11})

    def pair(pair_id, left_id, right_id):
        members = [by_id.get(left_id), by_id.get(right_id)]
        excluded = [identifier for identifier, member in zip((left_id, right_id), members)
                    if member is None or not member["execution"]["valid_raw_allocation"]]
        distance = None
        if not excluded:
            left, right = [member["allocation"]["weights_by_code"] for member in members]
            distance = math.fsum(abs(left[code] - right[code]) for code in SECTOR_CODES) / 2
        return {"pair_id": pair_id, "case_ids": [left_id, right_id], "eligible": not excluded,
                "half_L1_distance": distance, "excluded_case_ids": excluded,
                "reason_if_ineligible": "missing_or_invalid_C0" if excluded else None}

    within = [pair("within:" + source, source + "__R1", source + "__R4") for source in source_ids]
    between = [pair("between:" + arm, source_ids[0] + "__" + arm, source_ids[1] + "__" + arm) for arm in ARMS]
    all_valid = all(row["valid_raw_allocation"] for row in case_rows)
    correct = sum(row["label_correct"] for row in case_rows)
    counts = Counter(row["outcome_category"] for row in case_rows)
    return {"evaluation_version": VERSION, "endpoint": "C0", "planned_case_count": 4,
            "artifact_case_count": len(by_id),
            "attempted_case_count": sum(row["workflow_generation_attempted"] for row in case_rows),
            "C0_attempted_case_count": sum(row["C0_attempted"] for row in case_rows),
            "completed_response_count": sum(row["transport_completed"] for row in case_rows),
            "valid_raw_allocation_count": sum(row["valid_raw_allocation"] for row in case_rows),
            "exact_label_correct_count": correct, "expected_sector_count": 44,
            "exact_label_accuracy": correct / 44,
            "by_arm": {arm: {"planned_case_count": 2, "expected_sector_count": 22,
                             "exact_label_correct_count": sum(row["label_correct"] for row in case_rows if row["arm"] == arm),
                             "valid_allocation_count": sum(row["valid_raw_allocation"] for row in case_rows if row["arm"] == arm)} for arm in ARMS},
            "case_accounting": case_rows, "outcome_counts": dict(counts),
            "within_source_pairs": within, "between_source_pairs": between,
            "eligible_within_source_pair_count": sum(row["eligible"] for row in within),
            "eligible_between_source_pair_count": sum(row["eligible"] for row in between),
            "between_source_distance_difference_R4_minus_R1": between[1]["half_L1_distance"] - between[0]["half_L1_distance"] if all_valid else None,
            "allocation_comparison_status": "all_four_observed" if all_valid else "conditional_or_unobserved",
            "semantic_assessed_sector_count": 0, "independent_human_review_completed": False,
            "strategic_preservation_verdict": None,
            "limits": ["Missing or invalid allocations never become zero distance.",
                       "Two documents and their dependent sector rows do not establish a population effect.",
                       "Conditional distances require joint interpretation with source differences and reviewed rationale.",
                       "Arithmetic success and copied ratings alone do not answer the paper's research question."]}
