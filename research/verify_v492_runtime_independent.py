"""Independent offline v492 runtime review; no model/HTTP requests.

Synthetic runtime fixtures mock only the gate so case/body/lineage checks can
be exercised. The separate gate test suite exercises the real validator using
temporary, explicitly synthetic documents. Neither claims human completion.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import sector_v492_runtime as runtime
import sector_v492_contract as contract
import test_sector_v492_runtime as fixture_module

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def reference(path):
    return {"path": str(path).replace("\\", "/"),
            "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}


def functions(path):
    return {node.name: ast.dump(node, include_attributes=False)
            for node in ast.parse((ROOT / path).read_text(encoding="utf-8-sig")).body
            if isinstance(node, ast.FunctionDef)}


def main():
    round1_path = "research/v492_runtime_round1_20261019.json"
    round1 = read(round1_path)
    assert round1["status"] == "PASS" and round1["model_generation_requests"] == 0
    for ref in round1["artifact_refs"]:
        assert reference(ref["path"])["sha256"] == ref["sha256"], "Round1 source changed: " + ref["path"]
    checked_paths = [
        "research/sector_v492_runtime.py", "research/sector_v492_review_gate.py",
        "research/prepare_sector_v492.py", "research/sector_v492_contract.py",
        "research/test_sector_v492_runtime.py", "research/test_sector_v492_review_gate.py",
        "research/test_sector_v492_contract.py", "research/sector_v491_runtime.py",
        "research/sector_v491_contract.py", "research/sector_v491_tokenizer.py",
        "research/verify_v492_runtime_independent.py",
    ]
    before_refs = [reference(path) for path in checked_paths]
    old, new = functions("research/sector_v491_runtime.py"), functions("research/sector_v492_runtime.py")
    unchanged_functions = ["check_token_capacity", "worker", "supervise", "run_transport",
                           "expected_stage_directory", "validate_worker_location"]
    for name in unchanged_functions:
        assert old[name] == new[name], "Reviewed critical function changed: " + name
    assert old["validate_prior_draft"].replace("human_gate", "review_gate") == new["validate_prior_draft"]
    checks = [{"id": "critical_capacity_render_generation_cleanup_functions_unchanged", "pass": True,
               "functions": unchanged_functions},
              {"id": "persisted_D0_provenance_only_gate_field_renamed", "pass": True}]
    fixture = fixture_module.RuntimeTests()
    fixture.setUp()
    try:
        spec = fixture.spec(4)
        assert spec["case_id"] == "common_market_only__C"
        checked = runtime.validate_spec(spec)
        assert checked["expected_source_packet"] is None
        raw = fixture_module.response_for(spec)
        fixture.persist_completed_stage(spec, raw)
        final = contract.build_final_messages(
            draft_messages=fixture.cases[4]["messages"], raw_draft=raw, assigned_packet=None,
            prompt_contract=fixture.bundle["prompt_contract"], response_schema=fixture.bundle["response_schema"],
        )
        spec.update(stage="F0", raw_draft=raw,
                    draft_artifacts=runtime.prior_draft_refs(spec["run_directory"], spec["case_id"]),
                    body=runtime.request_body(fixture.config, final["messages"], fixture.bundle["response_schema"]))
        checked = runtime.validate_spec(spec)
        assert checked["expected_source_packet"] is None
        source_ids = set().union(*(contract.evidence_ids(case["assigned_packet"])
                                  for case in fixture.cases if case["assigned_packet"] is not None))
        assert source_ids.isdisjoint(checked["visible_evidence_ids"])
        checks.append({"id": "C_two_stages_use_saved_own_D0_with_no_source_evidence", "pass": True})

        def rejects(name, changed):
            try:
                runtime.validate_spec(changed)
            except (ValueError, KeyError) as exc:
                checks.append({"id": name, "pass": True, "rejection": str(exc)})
            else:
                raise AssertionError("Unsafe mutation accepted: " + name)

        injected = copy.deepcopy(spec)
        payload = contract.strict_json(injected["body"]["messages"][3]["content"])
        payload["institution_document"] = fixture.cases[0]["assigned_packet"]
        injected["body"]["messages"][3]["content"] = contract.canonical_json(payload)
        rejects("C_F0_cannot_inject_institution_document", injected)
        changed = copy.deepcopy(spec)
        changed["body"]["messages"][2]["content"] = raw.strip()
        rejects("C_F0_cannot_strip_own_D0_bytes", changed)
        changed = copy.deepcopy(spec)
        changed["raw_draft"] = raw + " "
        changed["body"]["messages"][2]["content"] = changed["raw_draft"]
        rejects("C_F0_self_consistent_replacement_cannot_override_saved_D0", changed)
        other_draft = fixture.spec(1)
        other_raw = fixture_module.response_for(other_draft)
        fixture.persist_completed_stage(other_draft, other_raw)
        changed = copy.deepcopy(spec)
        changed["draft_artifacts"] = runtime.prior_draft_refs(other_draft["run_directory"], other_draft["case_id"])
        rejects("C_F0_cannot_reuse_byte_identical_L_D0_artifacts", changed)
        changed = copy.deepcopy(spec)
        changed["case_id"] = "fidelity_q3_2026__E"
        rejects("main_case_unavailable_even_under_valid_runtime", changed)
        changed = copy.deepcopy(spec)
        changed["body"]["options"]["num_gpu"] = False
        rejects("JSON_boolean_cannot_impersonate_CPU_integer_zero", changed)
    finally:
        fixture.doCleanups()
    suites = subprocess.run(
        [sys.executable, "-B", "-X", "utf8", "-m", "unittest",
         "test_sector_v492_runtime", "test_sector_v492_review_gate", "-v"],
        cwd=ROOT / "research", capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if suites.returncode:
        raise AssertionError(suites.stdout + suites.stderr)
    match = re.search(r"Ran (\d+) tests", suites.stderr)
    assert match and int(match.group(1)) >= 43
    assert before_refs == [reference(path) for path in checked_paths], "Sources changed during review"
    manifest = reference(runtime.MANIFEST.relative_to(ROOT))
    evaluation_path = "research/v492_evaluation_protocol_20261019.json"
    evaluation = read(evaluation_path)
    assert evaluation["expected_cases_per_split"] == 5
    assert evaluation["denominators"]["planned_source_conditioned_rows"] == 44
    assert evaluation["denominators"]["planned_no_source_control_rows"] == 11
    assert evaluation["denominators"]["shared_C_count"] == 1
    assert evaluation["no_composite_score"] is True
    checks.append({"id": "evaluation_denominators_keep_shared_C_and_source_fidelity_distinct", "pass": True})
    report = {
        "artifact_kind": "independent_AI_code_and_methods_review_before_v492_pilot",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(), "status": "PASS",
        "model_calls": 0, "HTTP_calls": 0, "human_review_completed": False,
        "reviewer_role": "Separate Codex task; not an independent human or validated semantic scorer",
        "checks": checks,
        "test_suite": {"returncode": suites.returncode, "test_count": int(match.group(1)),
                       "stdout": suites.stdout, "stderr": suites.stderr,
                       "scope": "Synthetic fixtures only; no formal research response"},
        "source_refs": before_refs,
        "author_round1_ref": reference(round1_path),
        "prepared_manifest_ref": manifest,
        "evaluation_protocol_ref": reference(evaluation_path),
        "methods_review_ref": reference("research/v492_evaluation_methods_review_20261019.json"),
        "contract_verification_ref": reference("research/v492_contract_verification_20261019.json"),
        "methodological_acceptance": {
            "split_specific_preoutput_source_review": "Accepted amendment to the earlier report recommendation. Common rubric/formulas and source selection must be fixed before outputs; each split's source contrasts precede that split's outputs. Disclose if main source contrast review follows pilot outputs.",
            "C": "Matched-stage source-free strategic AI control; one shared C, not two independent controls.",
            "computation": "EqW/GMV are diagnostic policies, not institution truth or future-performance winners.",
            "semantics": "AI-assisted evidence-linked coding remains unvalidated; no human agreement is claimed.",
        },
        "limitations": [
            "This checks code and offline contracts, not real inference feasibility or semantic correctness.",
            "A final real gate/freeze receipt and live runtime pin must still be verified by the coordinator before generation.",
            "Persisted D0 hashes prevent accidental substitution, not deliberate forgery of an entire artifact tree.",
            "No main endpoint is supplied; pilot evidence cannot be relabeled as main or population causal evidence.",
        ],
    }
    path = ROOT / "research/v492_runtime_independent_review_20261019.json"
    if path.exists():
        raise FileExistsError("Preserve earlier review; write a separately versioned review instead")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({**reference(path.relative_to(ROOT)), "status": "PASS",
                      "checks": len(checks), "test_count": int(match.group(1))}))


if __name__ == "__main__":
    main()
