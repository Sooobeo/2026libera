"""Read-only v4.8 main execution gate; no approval creation or model calls.

The immutable candidate describes preparation, so its false execution flags stay
false. A separately authored gate binds reviewed bytes, an independent human
source-review record, and explicit authorization for exactly one output root.
Recorded reviewer identities/roles are declarations, not identity authentication.
Source uncertainty can be a completed finding; future model semantic success is
never required. Existing pilot inputs and code are not rewritten or imported.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
GATE_VERSION = "v4.8-main-execution-gate-1"
AUTHORIZATION_VERSION = "v4.8-main-execution-authorization-1"
HUMAN_REVIEW_VERSION = "v4.8-main-source-review-1"
MAIN_SOURCES = ("fidelity_q3_2026", "ubs_july_2026")
SECTOR_CODES = ("10", "15", "20", "25", "30", "35", "40", "45", "50", "55", "60")
ARMS = ("R1", "R4")
SOFTWARE = (
    "run_sector_v48_main.py", "sector_v48_main_gate.py", "sector_v48_main_transport.py", "sector_v48_main_awake.py",
    "sector_v48_contract.py", "sector_response_schema.py", "sector_engine.py",
    "compact_sector_prompt.py", "local_sector_single_case.py", "remote_sector_runtime.py",
    "benchmark_sector_latency.py", "probe_ollama_runtime.py", "run_sector_workflow.py",
)
EVALUATOR_SOFTWARE = (
    "audit_v48_main_round1.py", "audit_v48_main_round2.py",
    "evaluate_sector_v48_main_artifacts.py", "render_v48_main_review_packet.py",
    "evaluate_sector_v48_artifacts.py", "evaluate_sector_v48.py", "render_v48_review_packet.py",
    "sector_engine.py", "sector_response_schema.py",
)
RELATIONSHIPS = {
    "substantive_difference_supported", "similarity_supported",
    "different_scales_not_directly_comparable", "insufficient_evidence", "uncertain",
}
REVIEWER_ROLES = {"independent_human", "author_human", "assistant_self_review", "deterministic_program"}
ISSUE_DISPOSITIONS = {"resolved", "accepted_limitation", "not_assessable"}
EVALUATOR_MATERIAL_KEYS = {"reference_annotations", "source_verification", "design_handoff",
                           "evaluation_protocol", "review_template", "source_comparison"}


def roster():
    return [{"case_id": sid + "__" + arm, "source_id": sid, "arm": arm, "split": "main"}
            for sid in MAIN_SOURCES for arm in ARMS]


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _timestamp(value, label):
    _require(_text(value), label + " is required")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(label + " must be an ISO timestamp") from exc
    _require(result.tzinfo is not None and result.utcoffset() is not None,
             label + " must include a timezone")
    return result


def read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("Nonfinite JSON number: " + value)
    def finite(value):
        result = float(value)
        if not math.isfinite(result):
            invalid(value)
        return result
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=pairs,
                      parse_constant=invalid, parse_float=finite)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _resolve(path, root):
    value = Path(path)
    return value.resolve() if value.is_absolute() else (root / value).resolve()


class _Inputs:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.seen = {}

    def file(self, path, expected=None):
        path = Path(path).resolve()
        actual = digest(path)
        _require(expected is None or (_sha(expected) and actual == expected), "Hash mismatch: " + str(path))
        _require(path not in self.seen or self.seen[path] == actual, "Changed during validation: " + str(path))
        self.seen[path] = actual
        return path

    def reference(self, value, expected_path=None):
        _require(isinstance(value, dict) and _text(value.get("path")) and _sha(value.get("sha256")),
                 "Reference must contain a path and lowercase SHA-256")
        path = _resolve(value["path"], self.root)
        _require(expected_path is None or path == Path(expected_path).resolve(), "Reference path mismatch")
        return self.file(path, value["sha256"])

    def json(self, path):
        result = read(self.file(path))
        _require(isinstance(result, dict), "Expected a JSON object: " + str(path))
        return result

    def stable(self):
        for path, sha in self.seen.items():
            _require(digest(path) == sha, "Changed during validation: " + str(path))


def _candidate_names():
    names = {"market_input.json", "public_numeric_registry.json", "runtime.json", "prompt_contract.json",
             "system_instruction.txt", "remaining_requirements.json"}
    names.update("packets/" + sid + ".json" for sid in MAIN_SOURCES)
    names.update(f"schemas/{arm}_stage{stage}.json" for arm in ARMS for stage in range(1, 5))
    names.update(f"previews/{case['case_id']}/stage{stage}_payload.json"
                 for case in roster() for stage in range(1, 5))
    return names


def _inventory(inputs, hashes, expected):
    _require(isinstance(hashes, dict) and set(hashes) == set(expected), "Software inventory mismatch")
    for name, sha in hashes.items():
        _require(_sha(sha), "Mandatory software hash must be lowercase SHA-256: " + name)
        inputs.file(inputs.root / "research" / name, sha)


def _protect_output(output, candidate, manifest_path, root):
    protected = {manifest_path.parent, root / "data/sector_documents",
                 root / "data/sector_protocol/v48_design_20261018"}
    prior = candidate.get("prior_pilot", {})
    for key in ("manifest", "registration", "run_summary"):
        reference = prior.get(key)
        _require(isinstance(reference, dict) and _text(reference.get("path"))
                 and _sha(reference.get("sha256")), "Bound prior pilot reference missing: " + key)
        protected.add(_resolve(reference["path"], root).parent)
    for original in candidate.get("original_documents", []):
        reference = original.get("original_pdf", {})
        _require(_text(reference.get("path")), "Original document path missing")
        protected.add(_resolve(reference["path"], root).parent)
    for folder in protected:
        folder = folder.resolve()
        _require(not output.is_relative_to(folder) and not folder.is_relative_to(output),
                 "Run output overlaps preserved input/pilot/source directory: " + str(folder))


def _reviewer(value, independent=False):
    _require(isinstance(value, dict), "Reviewer record missing")
    for key in ("reviewer_id", "name_or_model_identity"):
        _require(_text(value.get(key)), "Reviewer " + key + " missing")
    _require(value.get("reviewer_role") in REVIEWER_ROLES, "Reviewer role is not declared")
    if independent:
        _require(value["reviewer_role"] == "independent_human"
                 and value.get("independence_from_response_generation") is True,
                 "Independent human source-review declaration required")


def _human_review(inputs, human, candidate, manifest_path, gate):
    _require(human.get("review_version") == HUMAN_REVIEW_VERSION
             and human.get("review_status") == "completed"
             and human.get("independent_human_review_completed") is True
             and human.get("pending") == [], "Human source review remains incomplete")
    _timestamp(human.get("completed_at_utc"), "Source review completion time")
    _reviewer(human.get("reviewer"), independent=True)
    _require(human.get("candidate_manifest") == gate["candidate_manifest"], "Source review candidate differs")
    inputs.reference(human["candidate_manifest"], manifest_path)
    originals = candidate.get("original_documents")
    _require(isinstance(originals, list) and len(originals) == 2
             and {r.get("source_id") for r in originals if isinstance(r, dict)} == set(MAIN_SOURCES),
             "Two pinned original documents are required")
    materials = human.get("source_materials")
    _require(isinstance(materials, list) and len(materials) == 2
             and {r.get("source_id") for r in materials if isinstance(r, dict)} == set(MAIN_SOURCES),
             "Both main source materials must be reviewed")
    source_hashes = {}
    for sid in MAIN_SOURCES:
        original = next(r for r in originals if r["source_id"] == sid)
        material = next(r for r in materials if r["source_id"] == sid)
        _require(material.get("original_pdf") == original.get("original_pdf"), "Reviewed original differs")
        inputs.reference(material["original_pdf"])
        packet_name = "packets/" + sid + ".json"
        inputs.reference(material.get("packet"), manifest_path.parent / packet_name)
        _require(material["packet"]["sha256"] == candidate["files"][packet_name], "Reviewed packet differs")
        _require(material.get("review_status") == "completed" and _text(material.get("review_notes")),
                 "Source material review is unfinished")
        issues = original.get("known_source_issues")
        decisions = material.get("known_source_issue_dispositions")
        _require(isinstance(issues, list) and all(_text(x) for x in issues), "Known source issues missing")
        _require(isinstance(decisions, list) and len(decisions) == len(issues)
                 and all(isinstance(x, dict) for x in decisions)
                 and sorted(x.get("issue", "") for x in decisions) == sorted(issues),
                 "Known source issues must be explicitly retained")
        for decision in decisions:
            _require(decision.get("disposition") in ISSUE_DISPOSITIONS and _text(decision.get("reason")),
                     "Source issue requires a finding or an explicit limitation")
        source_hashes[sid] = material["original_pdf"]["sha256"]
    rows = human.get("source_difference_inventory")
    _require(isinstance(rows, list) and len(rows) == 11
             and all(isinstance(row, dict) for row in rows)
             and {row.get("sector_code") for row in rows} == set(SECTOR_CODES),
             "Source comparison must account for exactly 11 sectors")
    row_ids = set()
    for row in rows:
        rid = row.get("inventory_id")
        _require(_text(rid) and rid not in row_ids, "Comparison record IDs must be unique")
        row_ids.add(rid)
        _require(row.get("created_before_main_responses") is True and row.get("split") == "main"
                 and row.get("source_A_id") == MAIN_SOURCES[0] and row.get("source_B_id") == MAIN_SOURCES[1]
                 and row.get("review_status") == "completed" and row.get("independent_human_review_completed") is True
                 and row.get("reviewer_id") == human["reviewer"]["reviewer_id"]
                 and row.get("reviewer_role") == "independent_human", "Comparison completion or provenance missing")
        _require(row.get("relationship") in RELATIONSHIPS, "Comparison relationship is unrecorded")
        for key in ("rating_definition_scope", "period_and_universe_scope", "decision_relevance_reason"):
            _require(_text(row.get(key)), "Comparison " + key + " is unrecorded")
        _require(isinstance(row.get("comparability_limits"), list)
                 and all(_text(x) for x in row["comparability_limits"]), "Comparability limits must be explicit")
        for letter, sid in zip(("A", "B"), MAIN_SOURCES):
            prefix = "source_" + letter
            paraphrase_review = row.get(prefix + "_paraphrase_review")
            _require(isinstance(paraphrase_review, dict)
                     and paraphrase_review.get("status") in {"compared", "uncertain", "not_assessable", "not_present"}
                     and _text(paraphrase_review.get("reason")), "Researcher paraphrase review must be explicitly recorded")
            if paraphrase_review["status"] == "compared":
                _require(_text(row.get(prefix + "_researcher_paraphrase")), "Record the compared researcher paraphrase separately from original text")
            literal = row.get(prefix + "_literal_judgment")
            missing = row.get(prefix + "_missing_material_reason")
            _require(_text(literal) or _text(missing), "Record literal judgment or its specific absence")
            evidence = row.get(prefix + "_evidence_records")
            _require(isinstance(evidence, list) and (bool(evidence) or _text(missing)), "Source evidence locator missing")
            for record in evidence:
                _require(isinstance(record, dict)
                         and record.get("source_sha256") == source_hashes[sid]
                         and _text(record.get("source_path_or_url"))
                         and _text(record.get("page_section_or_fact_locator")), "Exact original-source evidence required")


def verify_main_gate(manifest_path, gate_path, *, workspace_root=ROOT):
    """Validate current bytes and return the agreed eight values, or raise.

    This certifies recorded bindings only. It cannot establish reviewer identity,
    truth of a semantic judgment, or permission beyond the recorded declaration.
    The caller enforces exclusive creation of authorized_run_root and rechecks at
    each endpoint; a valid gate does not itself start or count any generation.
    """
    inputs = _Inputs(workspace_root)
    manifest_path, gate_path = Path(manifest_path).resolve(), Path(gate_path).resolve()
    candidate, gate = inputs.json(manifest_path), inputs.json(gate_path)
    _require(candidate.get("candidate_version") == "v4.8-main-candidate-1"
             and candidate.get("protocol_version") == "4.8"
             and candidate.get("scope") == "offline_main_input_candidate_not_execution_registration"
             and candidate.get("main_authorized") is False and candidate.get("main_frozen") is False
             and candidate.get("human_review_completed") is False, "Expected unchanged preparation candidate")
    _require(candidate.get("roster") == roster() and candidate.get("planned_case_count") == 4
             and candidate.get("expected_sector_count") == 44
             and candidate.get("planned_core_calls_if_later_authorized") == 16
             and candidate.get("maximum_auxiliary_calls_if_later_authorized") == 8,
             "Main 4-case/44-sector plan differs")
    for key in ("model_calls_by_preparation", "main_model_calls", "actual_main_responses"):
        _require(type(candidate.get(key)) is int and candidate[key] == 0, "Preparation counters must remain zero")
    hashes = candidate.get("files")
    _require(isinstance(hashes, dict) and set(hashes) == _candidate_names(), "Candidate file inventory differs")
    for name, sha in hashes.items():
        _require(_sha(sha), "Mandatory candidate hash must be lowercase SHA-256: " + name)
        target = (manifest_path.parent / name).resolve()
        _require(target.is_relative_to(manifest_path.parent), "Candidate file escapes its root")
        inputs.file(target, sha)
    # Bind evaluator-only versions without opening, hashing or exposing their
    # contents online. The offline auditors verify the actual bytes later.
    evaluator_refs = candidate.get("evaluator_material_refs")
    _require(isinstance(evaluator_refs, dict) and set(evaluator_refs) == EVALUATOR_MATERIAL_KEYS,
             "Candidate must pre-bind the six evaluator-only material references")
    for key, reference in evaluator_refs.items():
        _require(isinstance(reference, dict) and _text(reference.get("path"))
                 and Path(reference["path"]).is_absolute() and _sha(reference.get("sha256")),
                 "Evaluator-only reference requires absolute path and lowercase SHA-256: " + key)
    _require(gate.get("gate_version") == GATE_VERSION and gate.get("frozen") is True
             and gate.get("main_authorized") is True, "Explicit frozen main gate is absent")
    inputs.reference(gate.get("candidate_manifest"), manifest_path)
    _require(gate.get("roster") == roster() and type(gate.get("maximum_generation_calls")) is int
             and gate["maximum_generation_calls"] == 24, "Gate roster or maximum call count differs")
    output = gate.get("authorized_run_root")
    _require(_text(output) and Path(output).is_absolute(), "An exact absolute authorized run root is required")
    output = Path(output).resolve()
    _protect_output(output, candidate, manifest_path, inputs.root)
    _inventory(inputs, gate.get("software_hashes"), SOFTWARE)
    _inventory(inputs, gate.get("evaluator_software_hashes"), EVALUATOR_SOFTWARE)
    reviews = gate.get("reviews")
    _require(isinstance(reviews, list) and len(reviews) == 3, "Three implementation reviews required")
    review_paths = set()
    for round_number, reference in enumerate(reviews, 1):
        path = inputs.reference(reference)
        _require(path not in review_paths, "Implementation reviews must be separate records")
        review_paths.add(path)
        review = inputs.json(path)
        _require(type(review.get("round")) is int and review["round"] == round_number
                 and review.get("status") == "PASS", "Implementation review is incomplete")
        _reviewer(review.get("reviewer"))
        for key in ("candidate_manifest", "software_hashes", "evaluator_software_hashes"):
            _require(review.get(key) == gate[key], "Implementation review binding differs: " + key)
    human = inputs.json(inputs.reference(gate.get("human_source_review")))
    _human_review(inputs, human, candidate, manifest_path, gate)
    authorization = inputs.json(inputs.reference(gate.get("main_execution_authorization")))
    _require(authorization.get("authorization_version") == AUTHORIZATION_VERSION
             and authorization.get("decision") == "authorize_main_execution"
             and _text(authorization.get("authorized_by")), "Separate explicit main authorization missing")
    authorized_at = _timestamp(authorization.get("authorized_at_utc"), "Authorization time")
    _require(_timestamp(human["completed_at_utc"], "Source review completion time") <= authorized_at,
             "Authorization predates the recorded source review completion")
    for key in ("candidate_manifest", "human_source_review", "software_hashes", "evaluator_software_hashes",
                "reviews", "roster", "maximum_generation_calls", "authorized_run_root"):
        _require(authorization.get(key) == gate[key], "Authorization binding differs: " + key)
    runtime = inputs.json(manifest_path.parent / "runtime.json")
    contract = inputs.json(manifest_path.parent / "prompt_contract.json")
    registry = inputs.json(manifest_path.parent / "public_numeric_registry.json")
    market = inputs.json(manifest_path.parent / "market_input.json")
    _require(registry.get("source", {}).get("sha256") == hashes["market_input.json"], "Registry market binding differs")
    inputs.stable()
    return candidate, runtime, contract, registry, market, gate, human, authorization
