"""Preserve the actual first v4.8.1 document review, including its requested fix."""
from pathlib import Path
import hashlib
import html
import json
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).with_name("round3.json")

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def ref(path):
    return {"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha(path)}

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

receipt_path = ROOT / "research/v481_document_update_receipt_20261019.json"
receipt = read(receipt_path)
paper = Path(receipt["outputs"][0]["path"])
plan = Path(receipt["outputs"][1]["path"])
expected = [
    "f6eaeae7409cddb287096ade09bc04fdc90cd391ff302a4fe89f7c779b149eee",
    "43e2fa7733c9875617488fb1bcb86996189d74c3c68cafaf180b2a65090d45fc",
]
assert [sha(paper), sha(plan)] == expected
paper_text = html.unescape(paper.read_text(encoding="utf-8"))
plan_text = html.unescape(plan.read_text(encoding="utf-8"))
author_path = ROOT / "research/evaluator_only/v48_guarded_pilot_author_review_20261019.json"
author = read(author_path)
checks = []

def check(key, passed, detail, locator):
    checks.append({"id": key, "passed": bool(passed), "detail": detail, "document_locator": locator})

check("actual_document_identity", True, "Both generated document bytes match the supplied review hashes and generation receipt.", "paper+plan")
for item in receipt["inputs"]:
    p = Path(item["path"])
    check("input_hash:" + p.name, sha(p) == item["sha256"], "Recorded input bytes checked; this is provenance verification, not fresh validation of every cited paper.", "generation receipt inputs")
for i, observation in enumerate(author["paper_observations"]):
    quote = observation["model_quote"]
    check("model_quote_preserved:" + str(i), quote in paper_text, "The displayed model quotation is present verbatim after HTML entity decoding.", "paper#readiness representative observation table")
manual = [
    ("topic_to_observable", "Public institutional outlook → interpretation/reasons → submitted sector weights is the concrete observation, not reconstruction of private mandates.", "paper#framework; plan research-question explanation"),
    ("economic_management_connection", "Capital allocation and organizational responsibility for evidence transmission are connected without claiming observed welfare losses.", "paper#intro; paper#implications"),
    ("control_is_procedure", "R1/R4 are workflow conditions with common calculator support; time, placement, history and reuse opportunities are not represented as a pure timing mechanism.", "paper#design"),
    ("quantities_and_paper_adaptation", "Paper-derived numeric precedents, task adaptations and operating parameters are distinguished; operating settings are not claimed to be optimal thresholds from papers.", "paper#readiness conditions and development record"),
    ("public_source_and_paraphrase_limit", "Researcher-selected short packets and public opinions are distinguished from full-document retrieval, actual holdings and confidential objectives.", "paper#design; paper#implications"),
    ("source_date_types", "Fidelity Q2 April 17 and Q3 July 16 are official landing-page update dates, not verified PDF publication dates; UBS dates and as-of dates are separately identified.", "paper#design; paper#readiness; source references"),
    ("market_vintage_limit", "The 60-day market input, June 30 baseline, different document dates and currently downloaded price vintage are not represented as a contemporaneous backtest.", "paper#design; paper#readiness"),
    ("reference_year_suffixes", "Fidelity/UBS pilot documents use 2026a and main documents use 2026b; section 4.1 anchors and four source entries resolve to the intended versions.", "paper#design; paper#references"),
    ("latest_run_counts", "The guarded run is described as 4 planned cases, 2 attempted workflows, 1 completed C0, 0 valid raw C0 and 8 core + 2 auxiliary requests.", "paper#readiness; plan results"),
    ("raw_c0_primary", "C0 103.5% is retained as the primary invalid allocation; C1 99.5% and partial C2 remain separate auxiliary results.", "paper#readiness; plan primary/auxiliary tables"),
    ("c2_no_completion_credit", "The partial C2 has no imputed vector, sum or recovery success; no auxiliary result replaces C0.", "paper#design; paper#readiness; plan tables"),
    ("gpu_failure_not_model_judgment", "The R4 C0 failure reports preserved Vulkan device-loss evidence, no final response, and an unresolved device-error cause.", "paper#readiness; plan results"),
    ("ubs_not_attempted", "Both UBS cases are explicitly not attempted after the device failure; missing C0 rows do not become observed strategy failures.", "paper#readiness; plan results"),
    ("old_and_guarded_separate", "The first interrupted execution and guarded repeat have separate counts and environmental records, with no pooling, best-of-run replacement or independent-sample claim.", "paper#readiness; plan prior run/repeat explanation"),
    ("awake_not_gpu_guarantee", "Successful execution-state requests do not establish GPU stability; the reported cause is not assigned to sleep, memory exhaustion or driver with certainty.", "paper#readiness; plan results"),
    ("strict_label_scope", "The table states that exact source ID is required for the strict label diagnostic and that 0/11 is not a strategic preservation score.", "paper#readiness; plan primary table caption"),
    ("all_pairs_unobserved", "All within-source and between-source comparisons are unavailable with zero valid pairs; missing distances are not zeros or proof of no effect.", "paper#evaluation; paper#readiness; plan distance table"),
    ("invalid_vector_rationale_kept", "Readable explanations are reviewed even for invalid allocations; no normalization is used to manufacture comparable portfolios.", "paper#evaluation; paper#readiness; plan research connection"),
    ("supported_and_unsupported_links", "Industrial/IT evidence-to-coordinate links and unsupported numerical/causal additions are both represented, without asserting model-internal confusion mechanisms.", "paper#readiness representative table"),
    ("no_neutral_or_strategy_threshold", "Neutral is not defined as exact baseline equality and numerical proximity is not converted into a new strategy scoring threshold.", "paper#evaluation; paper#readiness Health Care observation"),
    ("human_review_pending", "Author-AI case readings and three technical reviews explicitly do not replace independent human original-source/semantic judgments.", "paper#readiness; plan remaining requirements"),
    ("main_unexecuted_candidate_absent", "Technical implementation review is complete, but main data candidate generation, main freeze and actual main execution are not claimed complete.", "paper#readiness main preparation; plan main preparation"),
    ("response_strategy_generalization_withheld", "One completed invalid C0 is not generalized to institutional strategy preservation, market homogenization or a treatment effect.", "paper#implications; paper#conclusion"),
    ("proposed_response_effects_unmeasured", "Source-checking roles, actual-delta checks and workflow comparisons are proposed directions; costs, human review time, net benefits and causal effectiveness are unmeasured.", "paper#implications"),
    ("operating_confounds_disclosed", "Fixed run order, shared-machine offline work, quantization, unknown training exposure and long-generation limits are disclosed as limits on interpretation.", "paper#readiness"),
]
for key, detail, locator in manual:
    check(key, True, detail, locator)
stale = "아직 bundle 평가가 없는 이 기록에서 최종 점수를 생성하지 않는다."
assert stale in paper_text
check("observation_temporal_status_current", False,
      "A historical interim-note sentence says bundle evaluation is absent, but this terminal document already includes the completed evaluation. Preserve raw quotations and source notes; update only the rendered author explanation.",
      "paper#readiness / source_id representative observation / author assessment")
report = {
    "round": 3,
    "status": "CHANGES_REQUESTED",
    "scope": "Actual generated paper and preparation-status document: consistency, reasoning, topic-to-observation connection, limits and literal preservation. Not visual layout QA or independent human review.",
    "created_at_utc": datetime.now(timezone.utc).isoformat(),
    "reviewer": {"reviewer_id": "/root/v48_offline_evaluator", "name_or_model_identity": "Codex assistant", "reviewer_role": "assistant_self_review"},
    "authorship_disclosure": "Reviewer authored offline evaluation/rendering and author-AI observations. The document builder was authored by the root agent. This is an AI cross-review with implementation involvement, not an independent human source review.",
    "provenance": {"paper": ref(paper), "preparation_status": ref(plan), "document_receipt": ref(receipt_path), "author_review": ref(author_path), "review_generator": ref(Path(__file__))},
    "check_count": len(checks),
    "pass_count": sum(c["passed"] for c in checks),
    "checks": checks,
    "required_changes": [{"location": "paper#readiness, source_id observation, author assessment", "old_text": stale, "suggested_display_text": "완료된 평가의 0/11은 출처 ID까지 요구한 진단이다. 제공된 11개 등급 문구가 읽힌다는 관측과 구분한다.", "preserve": "Model quote, original interim note, terminal author-review bytes and earlier generated documents."}],
    "limits": ["This pass checks the generated document against existing local evidence; it does not revalidate every referenced publication or independently read all original PDFs.", "The actual runtime failed. This document review cannot authorize main execution or change its readiness status."],
    "model_calls": 0,
    "main_model_calls": 0,
    "independent_human_review_completed": False,
    "documents_modified_by_this_review": False,
    "frozen_inputs_modified": False,
}
assert not OUT.exists(), "Preserve any existing review receipt."
assert [sha(paper), sha(plan)] == expected
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"path": str(OUT), "sha256": sha(OUT), "status": report["status"], "checks": len(checks), "pass_count": report["pass_count"]}))
