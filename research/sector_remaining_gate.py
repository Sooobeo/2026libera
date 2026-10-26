"""Prospective five-stage remaining gate; completed drafts are immutable external evidence."""
from __future__ import annotations

import copy
import sector_continuation_gate as inherited
import sector_completion_gate as previous
from sector_remaining_awake import POWER_POLICY
import sector_v494_runtime as original

paths = inherited.paths
checked, require, timestamp = inherited.checked, inherited.require, inherited.timestamp
CASES = ("ubs_june_2026__E", "ubs_june_2026__L", "common_market_only__C")
STAGE_ORDER = ("ubs_june_2026__E__F0", "ubs_june_2026__L__D0", "ubs_june_2026__L__F0",
               "common_market_only__C__D0", "common_market_only__C__F0")
STAGES_BY_CASE = {CASES[0]: ("F0",), CASES[1]: ("D0", "F0"), CASES[2]: ("D0", "F0")}
EXTERNAL_GROUPS = ("external_draft_refs", "external_draft_evidence_refs")
BOUND = ("runtime_ref", "protocol_ref", "historical_gate_ref", "historical_terminal_ref",
         "historical_summary_ref", "prior_continuation_gate_ref", "prior_continuation_terminal_ref",
         "prior_continuation_summary_ref", "prior_continuation_declaration_ref",
         "prepared_manifest_ref", "finalizer_acceptance_ref", "completion_finalizer_review_ref",
         "prior_completion_gate_ref", "prior_completion_terminal_ref", "prior_completion_summary_ref",
         "prior_completion_declaration_ref", "remaining_finalizer_review_ref")
REMAINING_REVIEW_CODE = {"research/sector_remaining_gate.py", "research/sector_remaining_runtime.py",
    "research/sector_remaining_awake.py", "research/run_sector_remaining.py", "research/test_sector_remaining.py"}
REQUIRED_CODE = previous.REQUIRED_CODE | REMAINING_REVIEW_CODE | {
    "research/freeze_sector_remaining.py", "research/finalize_sector_remaining.py", "research/publish_remaining_review_ack.py"}


def scope(value):
    require(value.get("purpose") == "pilot_completion_resume" and value.get("case_order") == list(CASES)
            and value.get("stage_order") == list(STAGE_ORDER), "Exact five unattempted remaining stages required")
    for key, expected in (("max_generation_requests", 5), ("historical_generation_requests", 6),
                          ("campaign_max_generation_requests", 11), ("automatic_retries", 0), ("post_final_calls", 0), ("main_model_calls", 0)):
        require(type(value.get(key)) is int and value[key] == expected, "Wrong remaining accounting: " + key)
    require(value.get("main_allowed") is False and value.get("old_outputs_observed") is True
            and value.get("analysis_role") == "primary_exploratory"
            and value.get("excluded_new_main_execution") is True, "Observed exploratory scope and excluded main required")
    require(value.get("explicit_retry_slots") == []
            and value.get("historical_explicit_retry_slots") == ["fidelity_q2_2026__L__D0"], "No new retry slots")
    require(original.base.canonical(value.get("power_policy")) == original.base.canonical(POWER_POLICY),
            "Exact reviewed operational power policy required")


def verify_nested_refs(value):
    found = []
    if isinstance(value, dict):
        if "path" in value and "sha256" in value:
            reference = {key: value[key] for key in ("path", "sha256")}
            checked(reference, json_object=False)
            found.append(reference)
        else:
            for child in value.values():
                found.extend(verify_nested_refs(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(verify_nested_refs(child))
    return found


def validate_reviews(reviews, frozen_at):
    require(isinstance(reviews, list) and len(reviews) >= 3, "Three distinct completion reviews required")
    seen_paths, seen_hashes, reviewed = set(), set(), set()
    for reference in reviews:
        review = checked(reference)
        path = paths.workspace_path(reference["path"])
        require(path not in seen_paths and reference["sha256"] not in seen_hashes, "Duplicate completion review")
        seen_paths.add(path)
        seen_hashes.add(reference["sha256"])
        require(review.get("status") == "PASS" and timestamp(review["completed_at_utc"]) <= frozen_at,
                "Completed pre-freeze completion review required")
        for item in verify_nested_refs(review):
            reviewed.add(paths.workspace_path(item["path"]).relative_to(paths.ROOT).as_posix())
        for axis in ("errors", "consistency", "paper_topic"):
            evidence = review.get("review_axes", {}).get(axis, {})
            require(evidence.get("pass") is True and isinstance(evidence.get("reason"), str)
                    and evidence["reason"].strip(), "All three review axes need specific reasons")
    require(REMAINING_REVIEW_CODE.issubset(reviewed), "Reviews must bind current completion modules and tests")


def same_ref(left, right):
    return (isinstance(left, dict) and isinstance(right, dict)
            and left.get("sha256") == right.get("sha256")
            and paths.workspace_path(left.get("path", "")) == paths.workspace_path(right.get("path", "")))


def validate_history(objects, refs):
    previous.validate_history(objects, refs)
    old_gate = objects["prior_completion_gate_ref"]
    for key in previous.BOUND:
        if key in ("runtime_ref", "protocol_ref"):
            continue
        require(same_ref(old_gate.get(key), refs[key]), "Previous completion history binding differs: " + key)
    terminal, summary = objects["prior_completion_terminal_ref"], objects["prior_completion_summary_ref"]
    declaration = objects["prior_completion_declaration_ref"]
    require(terminal.get("purpose") == "pilot_completion"
            and terminal.get("status") == "stopped_semantic_review_pending"
            and terminal.get("awake_release", {}).get("status") == "released"
            and same_ref(terminal.get("summary_ref"), refs["prior_completion_summary_ref"])
            and same_ref(terminal.get("declaration_ref"), refs["prior_completion_declaration_ref"]),
            "Exact stopped completion terminal and explicit wake release required")
    require(declaration.get("purpose") == "pilot_completion"
            and same_ref(declaration.get("review_gate"), refs["prior_completion_gate_ref"])
            and same_ref(declaration.get("freeze_ref"), old_gate.get("freeze_ref")), "Completion declaration/gate differs")
    require(summary.get("purpose") == "pilot_completion" and summary.get("status") == "stopped"
            and summary.get("case_order") == list(CASES)
            and [r.get("case_id") for r in summary.get("cases", [])] == list(CASES), "Prior three-case denominator required")
    for obj in (summary, terminal):
        require(type(obj.get("generation_requests_attempted")) is int and obj["generation_requests_attempted"] == 1
                and type(obj.get("automatic_retries")) is int and obj["automatic_retries"] == 0
                and type(obj.get("main_model_calls")) is int and obj["main_model_calls"] == 0,
                "Previous completion must retain exactly one request")
    require(summary.get("historical_generation_requests") == 5 and summary.get("campaign_generation_requests_attempted") == 6,
            "Five earlier plus one completed UBS E draft must remain six")
    rows = summary["cases"]
    require([(s.get("stage"), s.get("status"), s.get("generation_requests_attempted")) for s in rows[0]["stages"]]
            == [("D0", "completed", 1)] and all(row.get("stages") == [] for row in rows[1:]),
            "Only UBS E D0 may be carried; remaining five stages must be unattempted")
    require(all(type(s.get("generation_requests_attempted")) is int for row in rows for s in row.get("stages", [])),
            "Previous completion stage counts must be integers")
    return terminal


def validated_external_draft(value):
    """Read-only exact provenance for the single explicitly carried UBS E D0."""
    import sector_completion_runtime as old_runtime
    from run_sector_completion import validate_external_review_ack
    refs, extras = (value.get(k) for k in EXTERNAL_GROUPS)
    require(isinstance(refs, dict) and set(refs) == set(old_runtime.DRAFT_ARTIFACTS), "Five external D0 artifacts required")
    names = {"stage_review", "allocation_math", "semantic_review", "external_review_ack", "terminal", "summary", "declaration", "final_construction"}
    require(isinstance(extras, dict) and set(extras) == names, "Eight external D0 evidence roles required")
    declaration = checked(value["prior_completion_declaration_ref"])
    run, reports = (paths.workspace_path(declaration[k]) for k in ("run_directory", "output_root"))
    folder = run / (CASES[0] + "__D0")
    records = {}
    for role, filename in old_runtime.DRAFT_ARTIFACTS.items():
        require(paths.workspace_path(refs[role]["path"]) == folder / filename, "External D0 path/role substitution")
        records[role] = checked(refs[role])
    expected = {"stage_review": folder / "stage_review.json", "external_review_ack": folder / "external_review_ack.json",
        "allocation_math": reports / "allocation_math" / (CASES[0] + "__D0.json"),
        "terminal": reports / "terminal_receipt.json", "summary": run / "campaign_summary.json",
        "declaration": run / "campaign_declaration.json", "final_construction": run / (CASES[0] + "__final_construction.json")}
    evidence = {key: checked(reference) for key, reference in extras.items()}
    for key, target in expected.items():
        require(paths.workspace_path(extras[key]["path"]) == target, "External evidence path/role substitution: " + key)
    for role, key in (("terminal", "prior_completion_terminal_ref"), ("summary", "prior_completion_summary_ref"),
                      ("declaration", "prior_completion_declaration_ref")):
        require(same_ref(extras[role], value[key]), "External draft/history identity differs")
    require(same_ref(evidence["external_review_ack"].get("semantic_review_ref"), extras["semantic_review"]),
            "External full semantic review must be the acknowledged review")
    old_spec = records["worker_spec"]
    require(old_spec.get("case_id") == CASES[0] and old_spec.get("stage") == "D0"
            and paths.workspace_path(old_spec["run_directory"]) == run, "Only fixed external UBS E D0 is allowed")
    old_runtime.validate_spec(old_spec)
    raw = records["response"]["message"]["content"]
    probe = copy.deepcopy(old_spec)
    canonical_refs = {role: old_runtime.artifact_ref(folder / filename)
                      for role, filename in old_runtime.DRAFT_ARTIFACTS.items()}
    require(all(same_ref(refs[role], canonical_refs[role]) for role in refs), "External D0 normalized identities differ")
    probe.update(stage="F0", raw_draft=raw, draft_artifacts=canonical_refs)
    old_runtime.validate_prior_draft(probe)
    validate_external_review_ack(evidence["external_review_ack"], spec=old_spec, folder=folder,
                                math_path=expected["allocation_math"])
    review = evidence["stage_review"]
    require(review.get("case_id") == CASES[0] and review.get("stage") == "D0"
            and review.get("instrument_integrity_pass") is True, "External D0 instrument review required")
    loaded, cases = old_runtime.load_bundle()
    case = next(c for c in cases if c["case_id"] == CASES[0])
    final = old_runtime.contract.build_final_messages(draft_messages=case["messages"], raw_draft=raw,
        assigned_packet=case["assigned_packet"], prompt_contract=loaded["prompt_contract"], response_schema=loaded["response_schema"])
    require(final.get("ready") is True and original.base.canonical(final) == original.base.canonical(evidence["final_construction"]),
            "Carried D0 final construction must remain exactly reproducible")
    return {"raw_draft": raw, "draft_artifacts": refs, "old_spec": old_spec, "final": final}


def validate_gate(path, expected_sha=None, *, runtime=None, run_directory=None):
    gate, reference = paths.read(path, expected_sha)
    gate_ref = {key: reference[key] for key in ("path", "sha256")}
    require(gate.get("receipt_version") == "sector_remaining_gate_1"
            and gate.get("status") == "approved_for_remaining_before_generation"
            and gate.get("review_mode") == "AI_delegated_by_user", "New prospective completion gate required")
    scope(gate)
    frozen = checked(gate.get("freeze_ref"))
    scope(frozen)
    require(frozen.get("freeze_version") == "sector_remaining_freeze_1"
            and frozen.get("status") == "frozen_for_pilot_remaining_only", "New completion freeze required")
    objects = {name: checked(gate.get(name)) for name in BOUND}
    for name in BOUND:
        require(gate[name] == frozen.get(name), "Freeze reference differs: " + name)
    for name in EXTERNAL_GROUPS:
        require(gate.get(name) == frozen.get(name), "Frozen external draft group differs")
    validated_external_draft(gate)
    run, reports = (paths.workspace_path(gate[name]) for name in ("run_directory", "output_root"))
    require(run.parent == paths.workspace_path("data/local_sector_runtime")
            and reports.is_relative_to(paths.workspace_path("research/remaining_20261026"))
            and run != reports and run not in reports.parents and reports not in run.parents,
            "Separate new raw and completion report namespaces required")
    for name in ("run_directory", "output_root"):
        require(gate[name] == frozen.get(name), "Output location differs from freeze")
    previous_ref = gate["prior_completion_gate_ref"]
    previous.validate_gate(previous_ref["path"], previous_ref["sha256"])
    terminal = validate_history(objects, gate)
    prior_frozen = checked(objects["prior_completion_gate_ref"]["freeze_ref"])
    for old in (objects["historical_gate_ref"], objects["prior_continuation_gate_ref"], objects["prior_completion_gate_ref"]):
        for key in ("run_directory", "output_root"):
            if key not in old:
                continue
            prior_path = paths.workspace_path(old[key])
            require(not run.is_relative_to(prior_path) and not prior_path.is_relative_to(run)
                    and not reports.is_relative_to(prior_path) and not prior_path.is_relative_to(reports),
                    "Completion cannot overlap any earlier raw/report tree")
    selected, old_runtime = objects["runtime_ref"], checked(objects["historical_gate_ref"]["runtime_ref"])
    original.validate_runtime(selected)
    expected = copy.deepcopy(old_runtime)
    expected["backend_evidence"][0] = selected["backend_evidence"][0]
    require(original.base.canonical(expected) == original.base.canonical(selected),
            "Only owned service receipt may differ; all scientific controls stay exact")
    if runtime is not None:
        require(original.base.canonical(runtime) == original.base.canonical(selected), "Caller runtime differs from completion freeze")
    protocol = objects["protocol_ref"]
    scope(protocol)
    require(protocol.get("status") == "approved_design_for_prospective_remaining_freeze"
            and protocol.get("historical_first_attempt_results_unchanged") is True
            and protocol.get("prepared_manifest_ref") == gate["prepared_manifest_ref"]
            and protocol.get("exact_math_policy_ref") == gate["finalizer_acceptance_ref"]
            and protocol.get("primary_final_allocation_endpoint") == "F0_derived_integer_allocation"
            and protocol.get("raw_diagnostics_required") is True, "Reviewed prospective exploratory protocol and exact endpoint required")
    for key in ("historical_gate_ref", "historical_terminal_ref", "historical_summary_ref",
                "prior_continuation_gate_ref", "prior_continuation_terminal_ref",
                "prior_continuation_summary_ref", "prior_continuation_declaration_ref",
                "prior_completion_gate_ref", "prior_completion_terminal_ref", "prior_completion_summary_ref",
                "prior_completion_declaration_ref", *EXTERNAL_GROUPS):
        require(protocol.get(key) == gate[key], "Protocol/history binding differs: " + key)
    acceptance = objects["finalizer_acceptance_ref"]
    require(acceptance.get("status") == "PASS" and acceptance.get("revision", {}).get("current_source_sha256")
            == original.remote.sha(paths.ROOT / "research/finalize_sector_allocation.py"), "Accepted unchanged exact math required")
    finalizer_review = objects["remaining_finalizer_review_ref"]
    require(finalizer_review.get("status") == "PASS", "Completion finalizer needs a separate passing review")
    refs = verify_nested_refs(finalizer_review)
    require("research/finalize_sector_remaining.py" in {
        paths.workspace_path(r["path"]).relative_to(paths.ROOT).as_posix() for r in refs},
        "Completion finalizer review must bind its actual current source")
    ft, gt = timestamp(frozen["recorded_at_utc"]), timestamp(gate["recorded_at_utc"])
    require(timestamp(terminal["at_utc"]) <= timestamp(protocol["recorded_at_utc"]) <= ft <= gt
            and timestamp(finalizer_review["completed_at_utc"]) <= ft, "Terminal/protocol/review/freeze/gate chronology differs")
    code = frozen.get("code_refs", [])
    names = [checked(r, json_object=False).relative_to(paths.ROOT).as_posix() for r in code]
    require(len(names) == len(set(names)) and REQUIRED_CODE.issubset(names), "All completion and inherited executable sources must be frozen")
    new_code_map = {paths.workspace_path(r["path"]): r["sha256"] for r in code}
    require(all(new_code_map.get(paths.workspace_path(r["path"])) == r["sha256"]
                for r in prior_frozen["code_refs"]), "All previously frozen dependency bytes must remain explicitly frozen")
    require(gate.get("review_refs") == frozen.get("review_refs"), "Freeze and gate review references differ")
    validate_reviews(frozen.get("review_refs"), ft)
    if run_directory is not None:
        require(paths.workspace_path(run_directory) == run, "Worker completion run differs")
        declaration = original.remote.read(run / "campaign_declaration.json")
        started = original.remote.read(run / "execution_started.json")
        scope(declaration)
        require(declaration.get("review_gate") == gate_ref and declaration.get("freeze_ref") == gate["freeze_ref"]
                and original.base.canonical(declaration.get("runtime")) == original.base.canonical(selected),
                "Declaration runtime/gate binding differs")
        for key in (*BOUND, *EXTERNAL_GROUPS):
            require(declaration.get(key) == gate[key], "Declaration reference differs: " + key)
        require(gt <= timestamp(declaration["created_at_utc"]) <= timestamp(started["at_utc"]), "Completion execution precedes its gate")
    return {"status": "prospective_remaining_gate_verified", "gate_ref": gate_ref, "freeze_ref": gate["freeze_ref"],
            "runtime_ref": gate["runtime_ref"], "protocol_ref": gate["protocol_ref"], "run_directory": str(run),
            "output_root": str(reports), "main_allowed": False, "analysis_role": "primary_exploratory"}
