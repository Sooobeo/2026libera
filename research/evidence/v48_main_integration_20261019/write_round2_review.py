"""Record a bounded static cross-review; never create main authorization."""
from datetime import datetime, timezone
from pathlib import Path
import ast
import hashlib
import json

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).with_name("round2.json")
PINNED_NEW_FILES = {
    "run_sector_v48_main.py": "add603e5a13ea960842941b12183722e8b2a228edffb5ee264b517244eaced36",
    "sector_v48_main_transport.py": "aa0fea0b02573ad7836eeea50ad004e1c70078b00bd0fcaf91c2d41c36781c04",
    "audit_v48_main_round1.py": "612d618a674f0395555a109b8a9270b454b15c4cd98ad7571b0e1f048d9dbf5d",
    "sector_v48_main_gate.py": "a1b8ead0da7ad6bf89e1146f0235d4c59aef3d81e1cdce85de109b41433ba0c4",
    "audit_v48_main_round2.py": "035a641ce960973f4728b8bf6b927350f10ae2e18bf6cb328cb1873e4fc0244e",
    "render_v48_main_review_packet.py": "3f453c3062712cb0ba0ca671414b87d7232842dd7892acdd7ec7cd65041f8a5f",
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
        raise FileExistsError("Preserve the previous review; use a new version")
    inventory = assignments(ROOT / "research/sector_v48_main_gate.py", ("SOFTWARE", "EVALUATOR_SOFTWARE"))
    online = {name: sha(ROOT / "research" / name) for name in inventory["SOFTWARE"]}
    evaluator = {name: sha(ROOT / "research" / name) for name in inventory["EVALUATOR_SOFTWARE"]}
    for name, expected in PINNED_NEW_FILES.items():
        if sha(ROOT / "research" / name) != expected:
            raise ValueError("Reviewed file changed: " + name)
    checks = []
    def check(identifier, passed, evidence, kind="static_read_and_contract_comparison"):
        checks.append({"id": identifier, "passed": bool(passed), "method": kind, "evidence": evidence})
    check("two_exact_inventory_maps", len(online) == 13 and len(evaluator) == 9,
          "13 online plus 9 evaluator entries; sector_engine.py and sector_response_schema.py occur in both, so there are 20 distinct files.", "deterministic_inventory_check")
    prepare_inventory = assignments(ROOT / "research/prepare_sector_v48_main_candidate.py", ("MAIN_SOFTWARE", "MAIN_EVALUATOR_SOFTWARE"))
    check("preparer_gate_inventory_compatibility", set(prepare_inventory["MAIN_SOFTWARE"]) == set(online) and set(prepare_inventory["MAIN_EVALUATOR_SOFTWARE"]) == set(evaluator),
          "The non-executable candidate preparer and gate name the same current implementation inventories.", "deterministic_inventory_check")
    pilot_path = ROOT / "data/sector_protocol/v48_pilot_r2_20261018/manifest.json"
    pilot = json.loads(pilot_path.read_text(encoding="utf-8"))
    protected = {name: sha(ROOT / "research" / name) == expected for name, expected in pilot["software_hashes"].items()}
    check("frozen_pilot_software_unchanged", len(protected) == 11 and all(protected.values()), protected, "sha256_comparison_to_registered_pilot")
    observations = [
        ("source_reason_actual_choice", "sector_v48_contract.SYSTEM_BASIS/stage_payload preserve the supplied public judgment, literal interpretation and evidence-linked rationale; raw allocations and later actual deltas remain separate. Reasoned departure is allowed; no private mandate, risk coefficient, uniquely correct weight or future expected return is invented by the execution contract."),
        ("source_scales_and_unknowns", "Contract distinguishes benchmark-relative Overweight, UBS opportunity language and Neutral without forcing equal meanings or exact baseline weights. Source comparison requires definitions, period/universe scope and decision relevance, and permits uncertainty, insufficient evidence or noncomparability."),
        ("R1_R4_frozen_history", "Main transport reconstructs each request from candidate previews and the complete captured assistant/feedback history. R1 receives assigned source at stage1; R4 at stage4. Prior R4 authored messages exclude assigned institution_document and evidence IDs, while the shared market baseline's public provenance is allowed."),
        ("fixed_four_cases_and_44_slots", "Main roster is Fidelity Q3 and UBS July crossed with R1/R4. Loader retains four C0 cases and eleven sector slots each even without an endpoint; workflow attempts and C0 requests are counted separately. No repeated sector row is called an independent experiment."),
        ("C0_raw_primary_not_best", "C0 is the first stage4 response. Schema/transport completion, financial validity and human semantic judgments are distinct. A complete valid raw vector can be described despite an unrelated schema failure; incomplete capture never receives completed credit."),
        ("bounded_C1_C2", "Only completed schema-valid complete finite but arithmetically invalid predecessor vectors permit C1/C2. At most two auxiliary revisions, no C2 without eligible C1, no retry after interruption, no best-response selection or replacement of C0."),
        ("no_response_normalization", "Calculator and evaluators preserve the submitted numbers. Invalid or missing vectors have no valid-portfolio distance or risk; no clipping, repair or replacement baseline enters a model response. The predeclared normalized descriptive baseline is separately labeled, not an institutional target."),
        ("finite_fact_lineage", "Calculator facts bind metric, subject, unit, observation period or explicit candidate-local nonapplicability, current candidate/vector hash, market hash and previous vector where relevant. Future and prior-candidate facts cannot silently certify a new candidate."),
        ("numerical_claim_vs_language_review", "MIDs and CIDs resolve against visible facts rather than document-label gold. Citation resolution and copied source labels do not certify support. Free prose is preserved for manual claim tuples and independent human source/reason/action review; no NLP heuristic or new behavioral threshold scores strategy."),
        ("actual_main_request_counts", "Worker, supervisor, coordinator, main loader and both auditors distinguish durable main generation requests from evaluator zero calls. Candidate preparation's zero counter is not substituted for observed main requests, including interrupted attempts that may fail before provider inference."),
        ("candidate_freeze_and_authorization_separate", "Candidate remains main_authorized=false/main_frozen=false/human_review_completed=false. Separate gate snapshots bind candidate, 13+9 current software inventories, three reviews, independent human source review and explicit one-root authorization. Reviewer identity is declared, not authenticated."),
        ("human_source_paraphrase_gate", "The amended gate requires source_A/B_paraphrase_review status and reason on all eleven rows. Compared requires a separate researcher-paraphrase text; uncertain/not_assessable/not_present remain allowed with a reason. Original literal judgments or specific absence, locators, scales, dates and known issues are retained. The v2 blank template remains unfilled."),
        ("pre_source_review_not_future_response_pass", "A recorded pre-generation human source review does not pre-judge new model outputs. Loader/renderer and auditors retain post-generation human judgments null and no strategy-preservation verdict. Three AI checks cannot replace independent human review."),
        ("awake_lifecycle_and_timing", "Main coordinator requests temporary Windows execution state before generation and restores the prior state in finally on the owning thread. Acquire/release failures are explicit incidents. Neither API acceptance nor the configured 900-second threshold certifies uninterrupted operation; actual supervisor elapsed is retained without clipping or CPU-time inference."),
        ("main_runtime_loader_artifacts", "Endpoint names, case/summary references, request hashes, pre-generation evidence/facts, raw and partial response paths, snapshot names and nested timing fields match the main loader. Orphan/partial captures remain review material without automatic completion."),
        ("main_round1_record_audit", "Main round1 checks recorded gate/context binding, fixed authored history, render/stream preservation, sequence, actual feedback, C0/auxiliary references, awake receipts and actual counts. Model outcome failure and captured-record integrity are not conflated."),
        ("main_round2_independent_math", "Main round2 independently computes raw sums with Decimal/Fraction, covariance risk and half-L1 distances; checks complete unique fact tuples and auxiliary inventory; preserves 4/44 and unavailable pairs as null. Binary64 roundoff allowances are computational checks, not outcome thresholds."),
        ("literal_renderer_preservation", "Main HTML adapter now replaces only an exact generated heading tag prefix; model/source text is escaped and left literal. The targeted five-test run includes all three source/interpretation/rationale columns containing that heading-like text and passed. Source comparison links to preserved v2."),
        ("scope_and_paper_connection", "Tools enable source→reason→actual choice tracing for a small public-document-conditioned workflow comparison. They do not establish private institutional strategy, causal memory effects, harmful homogenization, portfolio performance, population effects or organizational net benefit."),
    ]
    for identifier, evidence in observations:
        check(identifier, True, evidence)
    # Recheck all consulted software immediately before recording the review.
    check("reviewed_software_stable", all(sha(ROOT / "research" / n) == h for n, h in {**online, **evaluator}.items()),
          "Current hashes still match this review's inventory.", "sha256_recheck")
    result = {
        "round": 2, "status": "PASS" if all(c["passed"] for c in checks) else "FAIL",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "review_scope": "Pre-execution technical integration review of the named 13 online/9 evaluator entries. No actual main candidate, freeze, human judgment or execution authorization is created.",
        "software_hashes": online, "evaluator_software_hashes": evaluator,
        "reviewer": {"reviewer_id": "v48_offline_evaluator_integration_round2", "name_or_model_identity": "Codex author-AI reviewer /root/v48_offline_evaluator", "reviewer_role": "assistant_self_review"},
        "checks": checks,
        "authorship_disclosure": "This reviewer authored the pure v4.8 evaluator, pilot/main artifact loaders and review renderers; those parts are self-review. Main coordinator, transport, awake helper, gate and independent arithmetic/execution auditors were authored by other agents and were cross-read here. The calculator agent independently found the renderer literal-replacement bug, which was fixed and tested. Shared pilot dependencies are verified against their frozen hashes. Three AI reviews are not independent human source or semantic review.",
        "prior_review_refs": [reference("research/evidence/v48_main_runtime_validation_20261018/round2_offline_compatibility_20261019.json"), reference("research/evidence/v48_main_offline_validation_20261018/renderer_literal_fix_20261019.json")],
        "source_review_template": reference("research/evaluator_only/v48_main_source_review_template_20261018_v2.json"),
        "protected_pilot_manifest": reference("data/sector_protocol/v48_pilot_r2_20261018/manifest.json"),
        "status_limit": "PASS applies to these code/contract checks. Runtime unit tests are separately recorded by integration round1. This neither attests actual main operation nor supplies source correctness or model success.",
        "model_calls": 0, "independent_human_review_completed": False,
        "main_execution_authorized": False, "actual_main_data_generated": False,
        "frozen_pilot_files_modified": False, "blocking_findings": [],
    }
    with OUT.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2); handle.write("\n")
    print(json.dumps({"path": str(OUT.relative_to(ROOT)), "sha256": sha(OUT), "status": result["status"], "check_count": len(checks)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
