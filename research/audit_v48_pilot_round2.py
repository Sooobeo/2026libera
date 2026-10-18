"""Independent offline v4.8 pilot arithmetic, denominator and policy audit.

No model, HTTP or online runner is imported. Decimal/Fraction arithmetic is
independent of sector_engine. PASS means recorded arithmetic/policy agrees with
captured artifacts, never that the model's allocation or strategy succeeded.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest

from sector_response_schema import validate_response

ROOT = Path(__file__).resolve().parents[1]
CODES = ("10", "15", "20", "25", "30", "35", "40", "45", "50", "55", "60")
SOURCES = ("fidelity_q2_2026", "ubs_june_2026")
ROSTER = tuple({"case_id": s + "__" + a, "source_id": s, "arm": a, "split": "pilot"}
               for s in SOURCES for a in ("R1", "R4"))
CORE = ("stage1", "stage2", "stage3", "C0")
ENDPOINTS = CORE + ("C1", "C2")
TOLERANCE = 1e-6  # Frozen serialization tolerance, not a behavioral threshold.


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def ref(path):
    p = Path(path).resolve()
    return {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def value_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def raw_object(text):
    """Keep decimal spellings; reject duplicate keys and non-finite numbers."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def invalid(_):
        raise ValueError("nonfinite JSON number")

    try:
        value = json.loads(text, parse_float=Decimal, parse_int=Decimal,
                           parse_constant=invalid, object_pairs_hook=pairs)
        if not isinstance(value, dict):
            return None
        def finite(item):
            if isinstance(item, Decimal):
                return item.is_finite() and math.isfinite(float(item))
            if isinstance(item, dict): return all(finite(v) for v in item.values())
            if isinstance(item, list): return all(finite(v) for v in item)
            return True
        return value if finite(value) else None
    except (ValueError, TypeError, OverflowError, RecursionError):
        return None


def recovered_text(folder):
    """Recover stored literal text without inferring endpoint completion."""
    generation = Path(folder) / "http_0001_generation"
    for name, nested in (("response.json", True), ("assembled_text.json", False)):
        try:
            capture = read(generation / name)
            container = capture.get("message") if nested and isinstance(capture, dict) else capture
            if isinstance(container, dict) and isinstance(container.get("content"), str):
                return container["content"], name
        except (OSError, ValueError, TypeError, UnicodeError):
            pass
    parts = []
    try:
        lines = (generation / "events.jsonl").read_bytes().splitlines()
    except OSError:
        return None, "no_response_material"
    for line in lines:
        try:
            wrapper = json.loads(line.decode("utf-8"))
            event = wrapper.get("event") if isinstance(wrapper, dict) else None
            message = event.get("message", {}) if isinstance(event, dict) else None
            part = message.get("content", "") if isinstance(message, dict) else None
            if not isinstance(part, str): break
            parts.append(part)
        except (ValueError, TypeError, UnicodeError):
            break
    return "".join(parts) or None, "events.jsonl"


def vector_hash(text):
    parsed = json.loads(text)
    rows = parsed.get("weights")
    coordinates = ([{"sector_code": row.get("sector_code"), "weight": row.get("weight")}
                    if isinstance(row, dict) else row for row in rows] if isinstance(rows, list) else rows)
    return value_hash(coordinates)


def vector(rows):
    """Independent coverage/bounds and exact binary64-input summation."""
    values, errors = {}, []
    if not isinstance(rows, list):
        rows, errors = [], ["not_a_list"]
    frequencies = Counter(row.get("sector_code") for row in rows if isinstance(row, dict)
                          and isinstance(row.get("sector_code"), str) and row["sector_code"] in CODES)
    for row in rows:
        if not isinstance(row, dict) or row.get("sector_code") not in CODES:
            errors.append("unknown_or_malformed_sector"); continue
        code, value = row["sector_code"], row.get("weight")
        if frequencies[code] != 1:
            errors.append("duplicate_sector:" + code); continue
        if isinstance(value, bool) or not isinstance(value, (Decimal, int, float)):
            errors.append("not_numeric:" + code); continue
        try:
            d = value if isinstance(value, Decimal) else Decimal(str(value))
            f = float(d)
            if not d.is_finite() or not math.isfinite(f): raise ValueError()
        except (ValueError, OverflowError):
            errors.append("nonfinite:" + code); continue
        values[code] = (d, f)
    missing = sorted(set(CODES) - set(values))
    complete = not errors and not missing and len(rows) == 11
    decimal_sum = binary_sum = residual = None
    # A malformed extra row invalidates the vector but does not erase the sum
    # of all eleven otherwise uniquely readable canonical coordinates.
    if len(values) == 11:
        # 80 decimal digits exceed the precision of the observed financial JSON
        # values; binary64 summation below is independently exact via Fraction.
        with localcontext() as context:
            context.prec = 80
            decimal_sum = str(sum((values[c][0] for c in CODES), Decimal(0)))
        exact_binary = sum((Fraction.from_float(values[c][1]) for c in CODES), Fraction(0))
        try:
            binary_sum = float(exact_binary)
            if not math.isfinite(binary_sum): binary_sum = None
        except OverflowError:
            binary_sum = None
        residual = binary_sum - 1.0 if binary_sum is not None else None
    bounds = [c for c, (_, f) in values.items() if f < 0 or f > 1]
    valid = bool(complete and not bounds and residual is not None and abs(residual) <= TOLERANCE)
    return {"complete": complete, "valid": valid, "missing": missing, "errors": errors,
            "bound_violation_codes": bounds, "decimal_raw_sum": decimal_sum,
            "binary64_sum": binary_sum, "signed_budget_residual": residual,
            "values": {c: f for c, (_, f) in values.items()},
            "decimal_values": {c: str(d) for c, (d, _) in values.items()}}


def same_number(observed, expected, *, bound=0.0):
    if expected is None: return observed is None
    if isinstance(observed, bool) or not isinstance(observed, (int, float)):
        return False
    if not math.isfinite(float(observed)) or not math.isfinite(float(expected)):
        return False
    # One binary64 rounding unit, plus an explicitly calculated operation bound.
    return abs(float(observed) - float(expected)) <= max(math.ulp(float(expected)), bound)


def operation_bound(terms, operations):
    epsilon = 2.0 ** -52
    gamma = operations * epsilon / (1.0 - operations * epsilon)
    return gamma * sum(abs(float(t)) for t in terms)


def risk_reference(v, market):
    codes, cov = market["sector_codes"], market["covariance"]
    terms = [Fraction.from_float(v["values"][a]) * Fraction.from_float(float(cov[i][j]))
             * Fraction.from_float(v["values"][b])
             for i, a in enumerate(codes) for j, b in enumerate(codes)]
    variance = float(sum(terms, Fraction(0)))
    bound = operation_bound(terms, 3 * len(terms))
    volatility = math.sqrt(variance) if variance >= 0 else None
    vol_bound = (bound / volatility if volatility and volatility > 0 else bound) + (
        math.ulp(volatility) if volatility is not None else 0)
    return variance, volatility, bound, vol_bound


def distance_reference(left, right):
    terms = [abs(Fraction.from_float(left[c]) - Fraction.from_float(right[c])) / 2 for c in CODES]
    return float(sum(terms, Fraction(0))), operation_bound(terms, 3 * len(terms))


def expected_facts(endpoint, v, market, prior, *, empty=False):
    """Independently construct the frozen arithmetic fact tuples and values."""
    result = {}

    def add(name, value, metric, formula, code=None, unit="decimal_weight", period=None,
            scope="raw_algebra", bound=0.0, previous_version=None):
        if value is None or not math.isfinite(value): return
        fact = {"fact_id": "C:" + endpoint + ":" + name, "sector_code": code,
                "subject": code if code is not None else "portfolio", "metric": metric,
                "unit": unit, "period": period,
                "period_scope": "candidate_local_no_calendar_period" if period is None else "market_observation_period",
                "calculation_id": "C:" + endpoint, "candidate_id": endpoint,
                "data_version": v.get("coordinate_hash"), "market_data_version": value_hash(market),
                "formula": formula, "interpretation_scope": scope, "valid_raw_allocation": v["valid"]}
        if previous_version is not None: fact["previous_data_version"] = previous_version
        result[fact["fact_id"]] = {"metadata": fact, "value": value, "bound": bound}

    if empty: return result
    add("sum", v["binary64_sum"], "sum_of_submitted_raw_weights", "sum_s(w_s)")
    add("budget_residual", v["signed_budget_residual"], "signed_budget_residual", "sum_s(w_s)-1")
    if v["complete"]:
        for code in CODES:
            add("active_weight:" + code, v["values"][code] - market["baseline_weights"][code],
                "raw_weight_minus_named_baseline", "current w_" + code + " - baseline b_" + code, code)
            if prior and prior["complete"]:
                add("weight_delta:" + code, v["values"][code] - prior["values"][code],
                    "current_minus_prior_submitted_weight", "current w_" + code + " - previous submitted w_" + code,
                    code, previous_version=prior["coordinate_hash"])
    if v["valid"] and "covariance" in market:
        variance, vol, var_bound, vol_bound = risk_reference(v, market)
        unit = market["covariance_unit"]
        vol_unit = unit[:-8] if unit.endswith("_squared") else "sqrt(" + unit + ")"
        add("variance", variance, "historical_portfolio_variance", "w^T Sigma w", unit=unit,
            period=market.get("lookback_return_dates"), scope="valid_portfolio_historical_diagnostic", bound=var_bound)
        add("volatility", vol, "historical_portfolio_standard_deviation", "sqrt(w^T Sigma w)", unit=vol_unit,
            period=market.get("lookback_return_dates"), scope="valid_portfolio_historical_diagnostic", bound=vol_bound)
    return result


def build_audit(manifest_path, run_root, evaluation_path):
    manifest_path, run_root, evaluation_path = map(Path, (manifest_path, run_root, evaluation_path))
    manifest, evaluation = read(manifest_path), read(evaluation_path)
    market = read(manifest_path.parent / "market_input.json")
    registry = read(manifest_path.parent / "public_numeric_registry.json")
    report_cases = {c["case_id"]: c for c in evaluation["primary_C0_cases"]}
    auxiliary = {(c["case_id"], c["endpoint"]): c for c in evaluation["auxiliary_endpoint_cases"]}
    bundle, checks, numeric_cases, policy_cases = evaluation["primary_C0_bundle"], [], [], []

    def check(name, passed, detail=None):
        checks.append({"id": name, "passed": bool(passed), "detail": detail})

    def check_evaluated_endpoint(case, endpoint, data, reported):
        prefix = case["case_id"] + ":evaluation_" + endpoint + ":"
        check(prefix + "identity", all(reported.get(k) == value for k, value in case.items())
              and reported.get("endpoint") == endpoint)
        v, execution, allocation = data["vector"], reported["execution"], reported["allocation"]
        valid = bool(data["attempted"] and data["complete"] and data["object"] is not None and v["valid"])
        check(prefix + "execution", execution.get("attempted") is data["attempted"]
              and execution.get("transport_completed") is data["complete"]
              and execution.get("valid_raw_allocation") is valid
              and execution.get("arithmetic_valid") is v["valid"]
              and execution.get("contract_valid") is data["schema"]
              and execution.get("no_external_weight_repair") is True)
        check(prefix + "raw_sum", same_number(allocation.get("raw_sum"), v["binary64_sum"])
              and same_number(execution.get("raw_sum"), v["binary64_sum"]))
        check(prefix + "raw_residual", same_number(allocation.get("raw_budget_residual"), v["signed_budget_residual"])
              and same_number(execution.get("signed_budget_residual"), v["signed_budget_residual"]))
        check(prefix + "raw_validity", allocation.get("valid") is v["valid"]
              and allocation.get("normalized_or_repaired") is False)
        weights = allocation.get("weights_by_code")
        check(prefix + "no_substitute_weights", (isinstance(weights, dict) and set(weights) == set(CODES)
              and all(same_number(weights[c], v["values"][c]) for c in CODES)) if v["valid"] else weights is None)
        risk = reported.get("valid_portfolio_risk")
        if not valid:
            check(prefix + "no_valid_portfolio_risk", risk is None)
        else:
            variance, vol, bound, vol_bound = risk_reference(v, market)
            check(prefix + "risk", isinstance(risk, dict) and same_number(risk.get("raw_variance"), variance, bound=bound)
                  and same_number(risk.get("volatility"), vol, bound=vol_bound)
                  and risk.get("covariance_unit") == market["covariance_unit"] and risk.get("annualized") is False)

    check("manifest_roster", manifest.get("roster") == list(ROSTER))
    check("pilot_only_no_main_authorization", manifest.get("main_authorized") is False)
    check("run_snapshot", read(run_root / "manifest_snapshot.json") == manifest)
    for rel, digest in manifest["input_hashes"].items():
        check("prepared_hash:" + rel, ref(manifest_path.parent / rel)["sha256"] == digest)
    check("evaluation_manifest", evaluation["provenance"]["prepared_manifest"]["sha256"] == ref(manifest_path)["sha256"])
    gold_ref = evaluation["provenance"]["gold_annotations"]
    gold_path = Path(gold_ref["path"])
    if not gold_path.is_absolute(): gold_path = ROOT / gold_path
    check("offline_gold_hash", ref(gold_path)["sha256"] == gold_ref["sha256"])
    golds = {g["source_id"]: g for g in (json.loads(line) for line in gold_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()) if g["source_id"] in SOURCES}
    check("offline_gold_roster", set(golds) == set(SOURCES))
    check("four_primary_cases_only", len(evaluation["primary_C0_cases"]) == 4 and set(report_cases) == {c["case_id"] for c in ROSTER})
    check("primary_endpoint_only", all(c["endpoint"] == "C0" for c in report_cases.values()))
    all_requests = [p for p in run_root.rglob("request.json") if p.parent.name.endswith("_generation")]
    expected_requests = {str(run_root / c["case_id"] / e / "http_0001_generation/request.json") for c in ROSTER for e in ENDPOINTS}
    check("no_unregistered_generations", all(str(p) in expected_requests for p in all_requests))
    expected_auxiliary = {(c["case_id"], e) for c in ROSTER for e in ("C1", "C2")
                          if (run_root / c["case_id"] / e / "record.json").is_file()
                          or (run_root / c["case_id"] / e / "http_0001_generation/request.json").is_file()}
    check("auxiliary_exact_unique_inventory", len(evaluation["auxiliary_endpoint_cases"]) == len(expected_auxiliary)
          and set(auxiliary) == expected_auxiliary)
    primary_vectors, correct_labels, attempted_workflows, completed_c0, attempted_c0 = {}, {}, 0, 0, 0
    recorded_totals = {"core": 0, "auxiliary": 0}
    for case in ROSTER:
        cid, source = case["case_id"], case["source_id"]
        folder = run_root / cid
        summary = read(folder / "case_summary.json") if (folder / "case_summary.json").is_file() else {}
        endpoint_data, prior_vector, actual_aux = {}, None, []
        requests = {e: (folder / e / "http_0001_generation/request.json").is_file() for e in ENDPOINTS}
        actual_aux = [e for e in ("C1", "C2") if requests[e]]
        attempted_workflows += any(requests.values())
        for kind, names in (("core", CORE), ("auxiliary", ("C1", "C2"))):
            total = sum(requests[e] for e in names)
            recorded_totals[kind] += total
            check(cid + ":" + kind + "_count", summary.get(kind + "_calls_attempted", 0) == total)
        for pos, endpoint in enumerate(ENDPOINTS):
            record_path = folder / endpoint / "record.json"
            stage = pos + 1 if pos < 3 else 4
            visible = case["arm"] == "R1" or stage == 4
            if not record_path.is_file():
                raw, origin = recovered_text(record_path.parent)
                obj = raw_object(raw)
                v = vector(obj.get("weights") if obj else None)
                if obj is not None: v["coordinate_hash"] = vector_hash(raw)
                visibility_path = record_path.parent / "visible_evidence_before_generation.json"
                visibility = read(visibility_path) if visibility_path.is_file() else {}
                endpoint_data[endpoint] = {"attempted": requests[endpoint], "complete": False,
                    "object": obj, "vector": v, "schema": validate_response(raw, stage, source if visible else None, visible)["valid"],
                    "raw_origin": origin, "visible_ids": visibility.get("ids") or [],
                    "visible_facts": visibility.get("calculator_facts") or []}
                continue
            record = read(record_path)
            raw = record.get("raw_response_text")
            obj = raw_object(raw)
            v = vector(obj.get("weights") if obj else None)
            if obj is not None: v["coordinate_hash"] = vector_hash(raw)
            schema = validate_response(raw, stage, source if visible else None, visible)
            complete = record.get("response_complete") is True
            response_path = folder / endpoint / "http_0001_generation/response.json"
            envelope = None
            if response_path.is_file():
                try: envelope = read(response_path)
                except (ValueError, UnicodeError): pass
            if complete:
                check(cid + ":" + endpoint + ":completed_capture", requests[endpoint] and isinstance(envelope, dict)
                      and envelope.get("done_reason") == "stop" and isinstance(envelope.get("message"), dict)
                      and envelope["message"].get("content") == raw)
            feedback = record.get("feedback")
            is_empty = stage < 3 and obj is not None and obj.get("weights") == []
            if feedback is not None:
                if obj is not None:
                    check(cid + ":" + endpoint + ":vector_lineage", feedback["lineage"]["submitted_vector_sha256"] == v["coordinate_hash"])
                    check(cid + ":" + endpoint + ":market_lineage", feedback["lineage"]["market_values_sha256"] == value_hash(market))
                allocation = feedback["allocation"]
                if is_empty:
                    check(cid + ":" + endpoint + ":empty_is_not_proposal", feedback["status"] == "not_yet_proposed"
                          and allocation.get("raw_sum") is None and allocation.get("valid") is None
                          and feedback.get("valid_portfolio_risk") is None and feedback.get("raw_algebra") is None
                          and feedback.get("raw_weight_deltas") is None and not feedback.get("facts"))
                else:
                    check(cid + ":" + endpoint + ":sum", same_number(allocation.get("raw_sum"), v["binary64_sum"]),
                          {"decimal_raw_sum": v["decimal_raw_sum"], "independent_binary64_sum": v["binary64_sum"], "recorded": allocation.get("raw_sum")})
                    check(cid + ":" + endpoint + ":residual", same_number(allocation.get("raw_budget_residual"), v["signed_budget_residual"]))
                    check(cid + ":" + endpoint + ":validity", allocation["valid"] is v["valid"])
                    check(cid + ":" + endpoint + ":no_normalization", feedback.get("repaired") is False and allocation.get("normalized_or_repaired") is False)
                    if not v["valid"]:
                        check(cid + ":" + endpoint + ":invalid_has_no_risk", feedback.get("valid_portfolio_risk") is None)
                    elif "covariance" in market:
                        risk = feedback.get("valid_portfolio_risk")
                        variance, vol, bound, vol_bound = risk_reference(v, market)
                        check(cid + ":" + endpoint + ":risk", isinstance(risk, dict)
                              and same_number(risk.get("raw_variance"), variance, bound=bound)
                              and same_number(risk.get("volatility"), vol, bound=vol_bound)
                              and risk.get("covariance_unit") == market["covariance_unit"] and risk.get("annualized") is False,
                              {"independent_variance": variance, "independent_volatility": vol, "binary64_operation_error_bound": bound})
                if not is_empty and v["complete"]:
                    active = feedback.get("raw_algebra", {}).get("active_weights")
                    check(cid + ":" + endpoint + ":raw_active_weights", isinstance(active, dict) and set(active) == set(CODES)
                          and all(same_number(active[c], v["values"][c] - market["baseline_weights"][c]) for c in CODES))
                elif not is_empty:
                    check(cid + ":" + endpoint + ":incomplete_no_active_weights",
                          feedback.get("raw_algebra", {}).get("active_weights") is None)
                expected = expected_facts(endpoint, v, market, prior_vector, empty=is_empty)
                actual_facts = feedback.get("facts", [])
                actual_ids = [f.get("fact_id") if isinstance(f, dict) else None for f in actual_facts]
                check(cid + ":" + endpoint + ":fact_exact_unique_inventory",
                      len(actual_ids) == len(expected) and Counter(actual_ids) == Counter(expected.keys()))
                for index, fact in enumerate(actual_facts):
                    fid = fact.get("fact_id") if isinstance(fact, dict) else None
                    reference = expected.get(fid) if isinstance(fid, str) else None
                    check(cid + ":" + endpoint + ":fact_tuple:" + str(index), reference is not None
                          and set(fact) == set(reference["metadata"]) | {"value"}
                          and all(fact.get(k) == value for k, value in reference["metadata"].items()))
                    check(cid + ":" + endpoint + ":fact_value:" + str(index), reference is not None
                          and same_number(fact.get("value"), reference["value"], bound=reference["bound"]))
                delta_expected = bool(not is_empty and prior_vector and prior_vector["complete"] and v["complete"])
                deltas = feedback.get("raw_weight_deltas")
                check(cid + ":" + endpoint + ":delta_presence", (isinstance(deltas, dict) and set(deltas) == set(CODES))
                      if delta_expected else deltas is None)
                if delta_expected:
                    check(cid + ":" + endpoint + ":prior_vector_lineage",
                          feedback["lineage"].get("previous_submitted_vector_sha256") == prior_vector["coordinate_hash"])
                    if isinstance(deltas, dict):
                        for code in CODES:
                            difference = v["values"][code] - prior_vector["values"][code]
                            check(cid + ":" + endpoint + ":delta:" + code,
                                  same_number(deltas.get(code), difference if math.isfinite(difference) else None))
            elif obj is not None:
                check(cid + ":" + endpoint + ":parsed_output_has_feedback", False)
            endpoint_data[endpoint] = {"attempted": requests[endpoint], "complete": complete,
                "object": obj, "vector": v, "schema": schema["valid"], "record": record,
                "visible_ids": record.get("visible_evidence_ids_before_generation") or [],
                "visible_facts": record.get("visible_calculator_facts_before_generation") or []}
            if record.get("transport_status") == "completed" and schema["valid"]:
                prior_vector = v
        # Later core stages require successful prior transport+contract, not arithmetic success.
        for left, right in zip(CORE, CORE[1:]):
            if requests[right]:
                previous = endpoint_data[left]
                check(cid + ":progression:" + right, previous["complete"] and previous["schema"]
                      and previous.get("record", {}).get("transport_status") == "completed")
        c0 = endpoint_data["C0"]
        attempted_c0 += c0["attempted"]
        completed_c0 += c0["complete"]
        valid_primary = bool(c0["attempted"] and c0["complete"] and c0["object"] is not None and c0["vector"]["valid"])
        evaluation_case = report_cases[cid]
        check_evaluated_endpoint(case, "C0", c0, evaluation_case)
        # Current source packets publish no explicit numeric constraints. A future
        # constrained version must add independent checks instead of ignoring them.
        check(cid + ":no_unimplemented_gold_numeric_constraint", not golds[source].get("constraints"))
        check(cid + ":primary_validity_independent_of_schema", evaluation_case["execution"]["valid_raw_allocation"] is valid_primary)
        check(cid + ":primary_attempted", evaluation_case["execution"]["attempted"] is c0["attempted"])
        check(cid + ":primary_completed", evaluation_case["execution"]["transport_completed"] is c0["complete"])
        reported_allocation = evaluation_case["allocation"]
        check(cid + ":evaluation_raw_sum", same_number(reported_allocation.get("raw_sum"), c0["vector"]["binary64_sum"]))
        check(cid + ":evaluation_raw_residual", same_number(reported_allocation.get("raw_budget_residual"), c0["vector"]["signed_budget_residual"]))
        check(cid + ":evaluation_arithmetic_valid", reported_allocation["valid"] is c0["vector"]["valid"])
        if c0["vector"]["valid"]:
            check(cid + ":evaluation_raw_weights", isinstance(reported_allocation.get("weights_by_code"), dict)
                  and all(same_number(reported_allocation["weights_by_code"].get(c), c0["vector"]["values"][c]) for c in CODES))
        else:
            check(cid + ":evaluation_no_substitute_weights", reported_allocation.get("weights_by_code") is None)
        if valid_primary: primary_vectors[cid] = c0["vector"]["values"]
        observed = c0["object"] or {}
        interprets = observed.get("interpretations", [])
        count, observed_count = 0, 0
        reviews = evaluation_case["review_preparation"]["sector_reviews"]
        visible_ids = set(c0["visible_ids"])
        fact_rows = list(registry.get("rows", [])) + list(registry.get("matrix_fact_references", [])) + list(c0["visible_facts"])
        fact_map = {f["fact_id"]: f for f in fact_rows}
        citation_counts = Counter()
        check(cid + ":eleven_review_rows", len(reviews) == 11 and {r["sector_code"] for r in reviews} == set(CODES))
        for code in CODES:
            matches = [row for row in interprets if isinstance(row, dict) and row.get("sector_code") == code] if isinstance(interprets, list) else []
            predicted = matches[0].get("rating") if len(matches) == 1 else None
            observed_correct = (observed.get("source_id") == source and isinstance(predicted, str)
                                and predicted.strip() == golds[source]["sector_ratings"][code]["rating"])
            correct = c0["attempted"] and c0["complete"] and observed_correct
            count += bool(correct)
            observed_count += bool(observed_correct)
            review = next(r for r in reviews if r["sector_code"] == code)
            check(cid + ":label:" + code, review["exact_label_correct"] is bool(correct))
            check(cid + ":observed_label_no_completion_credit:" + code,
                  review.get("observed_exact_label_in_readable_material") is bool(observed_correct))
            for field in ("interpretation_citations", "allocation_citations"):
                citation = review[field]
                check(cid + ":citation_not_semantics:" + code + ":" + field,
                      citation.get("semantic_entailment") is None and all(x.get("entails_claim") is None for x in citation.get("entries", [])))
                source_rows = matches if field == "interpretation_citations" else [r for r in observed.get("weights", []) if isinstance(r, dict) and r.get("sector_code") == code] if isinstance(observed.get("weights"), list) else []
                ids = source_rows[0].get("evidence_ids") if len(source_rows) == 1 else None
                syntactic = isinstance(ids, list) and all(isinstance(x, str) for x in ids)
                expected_ids = ids if syntactic else []
                entries = citation.get("entries", [])
                check(cid + ":citation_entries:" + code + ":" + field,
                      [e["evidence_id"] for e in entries] == expected_ids
                      and citation.get("syntax_valid") is bool(syntactic and len(ids) == len(set(ids))))
                for entry in entries:
                    eid = entry["evidence_id"]
                    expected_kind, expected_scope = "unknown", None
                    if eid in golds[source]["evidence_index"]:
                        expected_kind = "document"
                        expected_scope = code in golds[source]["evidence_index"][eid]["sector_codes"]
                    elif eid in fact_map:
                        fact = fact_map[eid]
                        expected_kind = "public_numeric" if eid.startswith("M:") else "calculator_numeric"
                        expected_scope = code in fact["sector_order"] if isinstance(fact.get("sector_order"), list) else fact.get("sector_code", fact.get("subject")) == code
                    check(cid + ":citation_resolution:" + code + ":" + field + ":" + eid,
                          entry.get("visible") is (eid in visible_ids) and entry.get("kind") == expected_kind
                          and entry.get("sector_scope_matches") is expected_scope)
                    citation_counts["entries"] += 1
                    citation_counts["not_visible"] += eid not in visible_ids
                    citation_counts["unknown_id"] += expected_kind == "unknown"
                    citation_counts["sector_scope_mismatch"] += expected_scope is False
            check(cid + ":semantic_pending:" + code, all(review.get(k) is None for k in ("literal_stance", "claim_support", "action_consistency", "source_to_action_assessment_status")))
        correct_labels[cid] = count
        check(cid + ":label_total", evaluation_case["source_fact_preservation"]["exact_label_correct_count"] == count
              and evaluation_case["source_fact_preservation"]["expected_sector_count"] == 11
              and evaluation_case["source_fact_preservation"]["observed_exact_labels_in_readable_material"] == observed_count)
        if not valid_primary:
            check(cid + ":no_primary_risk", evaluation_case["valid_portfolio_risk"] is None)
        elif "covariance" in market:
            variance, vol, bound, vol_bound = risk_reference(c0["vector"], market)
            risk = evaluation_case["valid_portfolio_risk"]
            check(cid + ":independent_primary_risk", isinstance(risk, dict) and same_number(risk.get("raw_variance"), variance, bound=bound)
                  and same_number(risk.get("volatility"), vol, bound=vol_bound)
                  and risk.get("covariance_unit") == market["covariance_unit"] and risk.get("annualized") is False)
        # Auxiliary authorization is stricter than eligibility of raw C0 numbers
        # for descriptive comparison: it also requires the full response contract.
        previous = c0
        for endpoint in ("C1", "C2"):
            if (cid, endpoint) in expected_auxiliary and (cid, endpoint) in auxiliary:
                check_evaluated_endpoint(case, endpoint, endpoint_data[endpoint], auxiliary[(cid, endpoint)])
            if requests[endpoint]:
                previous_v = previous["vector"]
                eligible = (previous["complete"] and previous["schema"] and previous_v["complete"] and not previous_v["valid"]
                            and previous.get("record", {}).get("transport_status") == "completed")
                check(cid + ":auxiliary_eligibility:" + endpoint, eligible)
                check(cid + ":auxiliary_separate_report:" + endpoint, (cid, endpoint) in auxiliary)
                previous = endpoint_data[endpoint]
            else:
                if endpoint == "C1": check(cid + ":no_C2_without_C1", not requests["C2"])
                if summary.get("status") in ("completed_core", "completed_core_and_auxiliary_policy"):
                    pv = previous["vector"]
                    still_eligible = previous["complete"] and previous["schema"] and pv["complete"] and not pv["valid"]
                    check(cid + ":normal_exit_respects_repair_allowance:" + endpoint, not still_eligible)
        check(cid + ":auxiliary_cap", sum(requests[e] for e in ("C1", "C2")) <= 2)
        if actual_aux and summary.get("auxiliary_terminal_record"):
            check(cid + ":terminal_is_last_attempt", Path(summary["auxiliary_terminal_record"]["path"]).parent.name == actual_aux[-1])
        if summary.get("primary_record"):
            check(cid + ":primary_reference_is_C0", Path(summary["primary_record"]["path"]).parent.name == "C0"
                  and summary["primary_record"]["sha256"] == ref(folder / "C0/record.json")["sha256"])
        numeric_cases.append({**case, "C0_attempted": c0["attempted"], "C0_completed": c0["complete"],
            "C0_schema_valid": c0["schema"], "C0_valid_raw_allocation": valid_primary,
            "decimal_raw_sum": c0["vector"]["decimal_raw_sum"], "raw_binary64_sum": c0["vector"]["binary64_sum"],
            "signed_budget_residual": c0["vector"]["signed_budget_residual"], "label_correct": count,
            "expected_sector_count": 11, "citation_resolution_diagnostics": dict(citation_counts),
            "citation_scope_counts_are_not_semantic_verdicts": True, "semantic_preservation": None})
        policy_cases.append({**case, "attempted_endpoints": [e for e in ENDPOINTS if requests[e]],
            "auxiliary_attempted_endpoints": actual_aux,
            "auxiliary_raw_sums": {e: endpoint_data[e]["vector"]["decimal_raw_sum"] for e in actual_aux},
            "primary_is_C0": True, "raw_vectors_never_normalized_by_auditor": True})
    check("fixed_denominators", bundle["planned_case_count"] == 4 and bundle["expected_sector_count"] == 44)
    check("workflow_attempted_denominator", bundle["attempted_case_count"] == attempted_workflows)
    check("C0_attempted_denominator", bundle["C0_attempted_case_count"] == attempted_c0)
    check("C0_completed_denominator", bundle["completed_response_count"] == completed_c0)
    check("C0_valid_denominator", bundle["valid_raw_allocation_count"] == len(primary_vectors))
    check("label_44_denominator", bundle["exact_label_correct_count"] == sum(correct_labels.values())
          and same_number(bundle["exact_label_accuracy"], sum(correct_labels.values()) / 44))
    for arm in ("R1", "R4"):
        arm_report = bundle["by_arm"][arm]
        check("arm_denominator:" + arm, arm_report["planned_case_count"] == 2 and arm_report["expected_sector_count"] == 22
              and arm_report["exact_label_correct_count"] == sum(correct_labels[c["case_id"]] for c in ROSTER if c["arm"] == arm))
    eligible_counts = {}
    for family in ("within_source", "between_source"):
        pairs = bundle[family + "_pairs"]
        check(family + ":two_planned_pairs", len(pairs) == 2)
        expected_pairs = ({"within:" + s: [s + "__R1", s + "__R4"] for s in SOURCES}
                          if family == "within_source" else
                          {"between:" + a: [s + "__" + a for s in SOURCES] for a in ("R1", "R4")})
        check(family + ":declared_pair_identities", {p["pair_id"]: p["case_ids"] for p in pairs} == expected_pairs)
        eligible_counts[family] = 0
        for pair in pairs:
            ids = pair["case_ids"]
            valid = len(ids) == 2 and all(i in primary_vectors for i in ids)
            eligible_counts[family] += valid
            check(pair["pair_id"] + ":eligibility", pair["eligible"] is valid)
            if valid:
                distance, bound = distance_reference(*(primary_vectors[i] for i in ids))
                check(pair["pair_id"] + ":independent_distance", same_number(pair["half_L1_distance"], distance, bound=bound))
            else:
                check(pair["pair_id"] + ":missing_is_not_zero", pair["half_L1_distance"] is None)
        check(family + ":pair_count", bundle["eligible_" + family + "_pair_count"] == eligible_counts[family])
    delta = bundle["between_source_distance_difference_R4_minus_R1"]
    if len(primary_vectors) == 4:
        r1, b1 = distance_reference(*(primary_vectors[s + "__R1"] for s in SOURCES))
        r4, b4 = distance_reference(*(primary_vectors[s + "__R4"] for s in SOURCES))
        check("four_valid_distance_difference", same_number(delta, r4 - r1, bound=b1 + b4 + math.ulp(r4 - r1)))
    else:
        check("unobserved_difference_is_not_zero", delta is None)
    check("no_semantic_verdict", evaluation.get("strategic_preservation_verdict") is None
          and bundle.get("strategic_preservation_verdict") is None and evaluation.get("independent_human_review_completed") is False)
    run_summary = read(run_root / "summary.json") if (run_root / "summary.json").is_file() else {}
    if run_summary:
        check("bundle_core_request_count", run_summary["core_generation_calls"] == recorded_totals["core"])
        check("bundle_auxiliary_request_count", run_summary["auxiliary_generation_calls"] == recorded_totals["auxiliary"])
    failed = [c for c in checks if not c["passed"]]
    return {"round": 2, "status": "PASS" if not failed else "FAIL", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "audit_kind": "independent_offline_numeric_denominator_policy_check", "reviewer_role": "AI arithmetic auditor; not independent human source or semantic review",
        "provenance": {"manifest": ref(manifest_path), "evaluation": ref(evaluation_path), "auditor": ref(__file__), "gold": ref(gold_path)},
        "instrument_record_consistency": "consistent" if not failed else "mismatch_found",
        "checks": checks, "failed_check_count": len(failed), "case_numerics": numeric_cases, "case_policy": policy_cases,
        "planned_case_count": 4, "expected_sector_count": 44, "recorded_generation_requests": recorded_totals,
        "model_arithmetic_outcome": {"completed_C0_count": completed_c0, "valid_C0_count": len(primary_vectors),
            "completed_but_invalid_C0_count": sum(c["C0_completed"] and not c["C0_valid_raw_allocation"] for c in numeric_cases),
            "model_failure_is_not_audit_failure": True},
        "numeric_method": {"raw_decimal_sum": "Decimal parse of literal response numbers, 80-digit reporting calculation; never a normalized allocation.",
            "binary64_sum": "Exact Fraction sum of each IEEE-754 parsed input, then one float rounding; independent of sector_engine/math.fsum.",
            "comparison_roundoff": "One binary64 ulp for scalar outputs; matrix/distance operations additionally use gamma_n = n*2^-52/(1-n*2^-52) times the sum of absolute terms. Engineering computation checks only, not outcome thresholds.",
            "frozen_feasibility_tolerance": TOLERANCE},
        "topic_alignment": {"status": "preserved_in_audit_scope", "connection": "Source judgment -> explanation -> actual raw C0 allocation under R1/R4. Arithmetic, label copying and citation resolution are separate supporting diagnostics.",
            "invalid_allocation": "Missing/invalid C0 has no portfolio distance or valid-portfolio risk; readable interpretation/rationale remains available for separate review.",
            "auxiliary": "C1/C2 are bounded operational recovery, not replacements for C0 or new independent cases.",
            "claim_limit": "No strategic-quality, future-return, harmful-homogenization or isolated-memory verdict is produced.",
            "free_text_numeric_claims": "Not automatically extracted or certified; literal numerical claims require separate tuple-grounded review."},
        "human_review_completed": False, "model_calls_by_audit": 0, "main_model_calls_by_audit": 0}


class SelfTests(unittest.TestCase):
    def rows(self, total):
        return [{"sector_code": c, "weight": total if i == 0 else Decimal(0)} for i, c in enumerate(CODES)]

    def test_raw_residual_no_normalization(self):
        v = vector(self.rows(Decimal("0.965")))
        self.assertEqual(v["decimal_raw_sum"], "0.965")
        self.assertFalse(v["valid"])
        self.assertEqual(v["values"]["10"], .965)
        self.assertTrue(same_number(v["signed_budget_residual"], .965 - 1))

    def test_bool_duplicate_missing_are_invalid(self):
        for kind in ("bool", "duplicate", "missing"):
            rows = self.rows(Decimal(1))
            if kind == "bool": rows[0]["weight"] = True
            elif kind == "duplicate": rows[-1]["sector_code"] = "10"
            else: rows.pop()
            self.assertFalse(vector(rows)["complete"])

    def test_bounds_not_hidden_by_full_sum(self):
        rows = self.rows(Decimal("1.1")); rows[1]["weight"] = Decimal("-0.1")
        self.assertFalse(vector(rows)["valid"])
        self.assertEqual(set(vector(rows)["bound_violation_codes"]), {"10", "15"})

    def test_parse_failures_and_exponent_overflow(self):
        for text in ('{"x":1,"x":2}', '{"x":1e309}', '{"x":NaN}', '{'):
            self.assertIsNone(raw_object(text))

    def test_extra_invalid_row_preserves_readable_sum_but_duplicates_do_not(self):
        rows = self.rows(Decimal(1)) + [{"sector_code": "unknown", "weight": .2}]
        v = vector(rows)
        self.assertFalse(v["complete"]); self.assertFalse(v["valid"])
        self.assertEqual(v["binary64_sum"], 1)
        rows[-1]["sector_code"] = "10"
        self.assertIsNone(vector(rows)["binary64_sum"])

    def test_literal_recovery_and_partial_utf8_tail(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); capture = folder / "http_0001_generation"
            capture.mkdir()
            (capture / "response.json").write_text('{"message":{"content":"literal"}}', encoding="utf-8")
            self.assertEqual(recovered_text(folder), ("literal", "response.json"))
            (capture / "response.json").write_text('{', encoding="utf-8")
            (capture / "assembled_text.json").write_text('{"content":"prefix"}', encoding="utf-8")
            self.assertEqual(recovered_text(folder), ("prefix", "assembled_text.json"))
            (capture / "assembled_text.json").write_text('{', encoding="utf-8")
            (capture / "events.jsonl").write_bytes(b'{"event":{"message":{"content":"retained"}}}\n\xe3\x81')
            self.assertEqual(recovered_text(folder), ("retained", "events.jsonl"))

    def test_covariance_and_pair_independent_math(self):
        v = vector(self.rows(Decimal(1)))
        market = {"sector_codes": list(CODES), "covariance": [[.0001 if i == j else 0 for j in range(11)] for i in range(11)]}
        variance, volatility, _, _ = risk_reference(v, market)
        self.assertAlmostEqual(variance, .0001); self.assertAlmostEqual(volatility, .01)
        other = dict(v["values"]); other["10"], other["15"] = 0, 1
        self.assertEqual(distance_reference(v["values"], other)[0], 1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest"); parser.add_argument("--run-root")
    parser.add_argument("--evaluation"); parser.add_argument("--output")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SelfTests))
        return 0 if result.wasSuccessful() else 1
    if not all((args.manifest, args.run_root, args.evaluation, args.output)):
        parser.error("--manifest, --run-root, --evaluation and --output are required")
    output = Path(args.output).resolve()
    if output.is_relative_to(Path(args.run_root).resolve()) or output.is_relative_to(Path(args.manifest).resolve().parent):
        raise ValueError("Write audit outside online and prepared artifact directories")
    report = build_audit(args.manifest, args.run_root, args.evaluation)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False); handle.write("\n")
    print(json.dumps({"status": report["status"], "checks": len(report["checks"]), "failed": report["failed_check_count"], "output": str(output)}))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
