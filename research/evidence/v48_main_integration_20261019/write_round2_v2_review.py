"""Record the corrected bounded review without editing the superseded record."""
from datetime import datetime, timezone
from pathlib import Path
import ast
import hashlib
import json

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).with_name("round2_v2.json")
PINNED = {
    "run_sector_v48_main.py": "add603e5a13ea960842941b12183722e8b2a228edffb5ee264b517244eaced36",
    "sector_v48_main_transport.py": "aa0fea0b02573ad7836eeea50ad004e1c70078b00bd0fcaf91c2d41c36781c04",
    "audit_v48_main_round1.py": "cfa8c42cca8e0ceae3c7ac0159d862247679eced12ecee7c9bf08d3eac0b10ec",
    "sector_v48_main_gate.py": "c4c00f70277cce0784190018ea07dc3d2fbe097b2af0b2a802a12b416eaea64b",
    "audit_v48_main_round2.py": "98252a6a067fc788dd349fdb928038ca0fcfdf6f83c54c2911c97b7535be5557",
    "evaluate_sector_v48_main_artifacts.py": "3a06ad795fa74f107f917c76fd626eefe0bd8676cd129485bb1679542d17a94a",
    "render_v48_main_review_packet.py": "94d3ae40bce47d0c8d48ada9ed4ce1d630bbb0fe6c55c3faf0311c1b9b837e66",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference(relative):
    return {"path": relative, "sha256": sha(ROOT / relative)}


def assignments(path, names):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in names}


def main():
    if OUT.exists():
        raise FileExistsError("Preserve this review; use another version")
    prior_path = OUT.with_name("round2.json")
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    inventory = assignments(ROOT / "research/sector_v48_main_gate.py", ("SOFTWARE", "EVALUATOR_SOFTWARE"))
    online = {name: sha(ROOT / "research" / name) for name in inventory["SOFTWARE"]}
    evaluator = {name: sha(ROOT / "research" / name) for name in inventory["EVALUATOR_SOFTWARE"]}
    for name, expected in PINNED.items():
        if sha(ROOT / "research" / name) != expected:
            raise ValueError("Reviewed final file changed: " + name)
    checks = []

    def check(identifier, passed, evidence, method="static_read_and_contract_comparison"):
        checks.append({"id": identifier, "passed": bool(passed), "method": method, "evidence": evidence})

    check("two_exact_inventory_maps", len(online) == 13 and len(evaluator) == 9
          and len(set(online) | set(evaluator)) == 20,
          "13 online and 9 evaluator entries contain 20 distinct files; engine and response schema are shared.", "deterministic_inventory_check")
    prepare_inventory = assignments(ROOT / "research/prepare_sector_v48_main_candidate.py", ("MAIN_SOFTWARE", "MAIN_EVALUATOR_SOFTWARE"))
    check("preparer_gate_inventory_compatibility", set(prepare_inventory["MAIN_SOFTWARE"]) == set(online)
          and set(prepare_inventory["MAIN_EVALUATOR_SOFTWARE"]) == set(evaluator),
          "The preparer and execution gate bind the same two final code inventories.", "deterministic_inventory_check")
    pilot_path = ROOT / "data/sector_protocol/v48_pilot_r2_20261018/manifest.json"
    pilot = json.loads(pilot_path.read_text(encoding="utf-8"))
    protected = {name: sha(ROOT / "research" / name) == expected for name, expected in pilot["software_hashes"].items()}
    check("frozen_pilot_software_unchanged", len(protected) == 11 and all(protected.values()),
          protected, "sha256_comparison_to_registered_pilot")

    # These contract observations were read in the initial cross-review. They
    # remain applicable after the specifically re-read fixes recorded below.
    excluded = {"two_exact_inventory_maps", "preparer_gate_inventory_compatibility",
                "frozen_pilot_software_unchanged", "reviewed_software_stable"}
    for original in prior["checks"]:
        if original["id"] not in excluded:
            entry = dict(original)
            if entry["id"] == "scope_and_paper_connection":
                entry["evidence"] = "Tools support public source -> interpretation -> reason -> actual sector-weight tracing in a small document-conditioned R1/R4 workflow comparison. They do not establish private mandates, causal memory effects, harmful homogenization, financial performance, population effects or organizational net benefit."
            if entry["id"] == "literal_renderer_preservation":
                entry["evidence"] = "Only the exact generated heading tag prefix is replaced. Source/model strings are escaped and preserved; the literal-heading regression passed. New criteria-reference validation changes validation only, not quoted text or human judgments."
            checks.append(entry)

    observations = [
        ("required_sha_cannot_use_optional_none_sentinel", "Gate _inventory explicitly validates lowercase 64-character SHA-256 before _Inputs.file for both software inventories, and the candidate.files loop does the same. Null, blank, bool or uppercase values cannot select the optional expected=None path. The prior review missed this boundary; that initial PASS is superseded."),
        ("six_prebound_offline_evaluation_materials", "Candidate metadata binds exactly reference_annotations, source_verification, design_handoff, evaluation_protocol, review_template and source_comparison. Preparation checks annotation bytes against source verification and checks criteria paths/hashes against the design handoff already pinned by the pilot. These six references are separate from the 32 public prepared files."),
        ("online_evaluator_metadata_only", "Online gate validates six reference names, absolute paths and lowercase SHA strings without opening or hashing those evaluator-only files. Prompt payloads and recorded online histories do not include annotations, offline review criteria or human semantic answers."),
        ("actual_gold_and_criteria_fail_closed_before_scoring", "Main loader requires the actual --gold resolved path and bytes to match the candidate-bound annotation reference, even if a different file has identical bytes. All six byte hashes are checked before annotation parsing/scoring and again after artifact analysis. Changes raise ValueError; no changed-criteria score is emitted and captured raw inputs remain untouched."),
        ("renderer_rechecks_current_candidate_criteria", "Main renderer requires evaluation_materials_verified, rechecks all six actual byte hashes and the candidate manifest hash, and compares candidate-bound references with report provenance before rendering. Report and worksheet provenance must match."),
        ("both_main_auditors_bind_evaluation_materials", "Main round1 independently checks all six bytes, annotation hash against original verification, and criteria against the design handoff. Main round2 checks six references and actual hashes, exact gold path/hash and equality of report provenance references to candidate metadata. Actual numerical checks retain the independently recomputed raw-vector and fact-tuple contract."),
        ("test_scope_is_not_inflated", "The local evaluator suite passed 21 tests before the final after-analysis recheck was added; the added mutation-during-analysis test passed separately. The final suite now contains 22 tests and is delegated to the root's integration round1 full capture. This static round2 does not claim that 21+1 was one final-version full-suite run."),
        ("prior_omissions_and_nonexecution_scope", "The initial review missed required-hash None handling and the lack of a prebound arbitrary --gold restriction. Both findings and the original review are preserved. This corrected review creates neither a main candidate nor human review, main authorization, model request or a successful experimental outcome."),
    ]
    for identifier, evidence in observations:
        check(identifier, True, evidence)
    check("reviewed_software_stable", all(sha(ROOT / "research" / name) == expected
          for name, expected in {**online, **evaluator}.items()),
          "Final reviewed inventory hashes remained unchanged through report construction.", "sha256_recheck")
    result = {
        "round": 2, "status": "PASS" if all(item["passed"] for item in checks) else "FAIL",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "review_scope": "Corrected static integration review of final main 13 online/9 evaluator entries; no empirical main output or execution authorization.",
        "software_hashes": online, "evaluator_software_hashes": evaluator,
        "reviewer": {"reviewer_id": "v48_offline_evaluator_integration_round2_v2",
                     "name_or_model_identity": "Codex author-AI reviewer /root/v48_offline_evaluator",
                     "reviewer_role": "assistant_self_review"},
        "checks": checks,
        "authorship_disclosure": "This reviewer authored the pure evaluator and pilot/main offline loaders/renderers, so these portions are self-review. Other agents authored the main coordinator, transport, awake helper, gate and independent arithmetic/execution auditors; those were cross-read. Root identified missing evaluation-material binding; runtime reviewer identified the required-SHA optional-sentinel bug; calculator reviewer identified literal renderer replacement. Those external findings were incorporated, not represented as discoveries of this review. No AI review replaces an independent human source or response-semantic review.",
        "supersedes": reference("research/evidence/v48_main_integration_20261019/round2.json"),
        "supersession_notice": reference("research/evidence/v48_main_integration_20261019/round2_supersession_notice.json"),
        "source_review_template": reference("research/evaluator_only/v48_main_source_review_template_20261018_v2.json"),
        "protected_pilot_manifest": reference("data/sector_protocol/v48_pilot_r2_20261018/manifest.json"),
        "status_limit": "PASS concerns the named static code/contracts. Full final synthetic test results belong to integration round1; root topic/contract review is round3. It does not attest actual main operation, source correctness, model success, a human review or permission to execute.",
        "model_calls": 0, "independent_human_review_completed": False,
        "main_execution_authorized": False, "actual_main_data_generated": False,
        "frozen_pilot_files_modified": False, "blocking_findings": [],
    }
    with OUT.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"path": str(OUT.relative_to(ROOT)), "sha256": sha(OUT),
                      "status": result["status"], "check_count": len(checks)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
