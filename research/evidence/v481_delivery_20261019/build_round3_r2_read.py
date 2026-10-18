"""Bind the document-only third review to the corrected actual r2 outputs."""
from pathlib import Path
import hashlib
import html
from html.parser import HTMLParser
import json
from datetime import datetime, timezone
from difflib import SequenceMatcher

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).with_name("round3_r2.json")

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def ref(path):
    return {"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha(path)}

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

class Document(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.texts = []
        self.links = []
        self.feed(path.read_text(encoding="utf-8"))

    def handle_data(self, data):
        if data.strip():
            self.texts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.append(dict(attrs).get("href"))

initial_path = OUT.with_name("round3.json")
initial = read(initial_path)
assert sha(initial_path) == "d0f53cf74ef93d9253d8dd6e336d56ddfb12d8b72418ed0ab4ea2b6eaa3a1455"
receipt_path = ROOT / "research/v481_document_update_receipt_20261019_r2.json"
receipt = read(receipt_path)
paper = Path(receipt["outputs"][0]["path"])
plan = Path(receipt["outputs"][1]["path"])
expected = ["270b5a89614a1b4a49251275e569bb5e64e74aad10899d3d1e90b3af83db8e3b", "33cdd89e2d7db2cca78c19805995db537b550b868191519ca3551477ff2f43df"]
assert [sha(paper), sha(plan)] == expected
oldpaper = ROOT / initial["provenance"]["paper"]["path"]
oldplan = ROOT / initial["provenance"]["preparation_status"]["path"]
oldp, newp, oldq, newq = [Document(p) for p in (oldpaper, paper, oldplan, plan)]
changes = [(oldp.texts[i:j], newp.texts[k:l]) for op,i,j,k,l in SequenceMatcher(None, oldp.texts, newp.texts).get_opcodes() if op != "equal"]
old_status = "출처 ID 포함 엄격 진단과 읽을 수 있는 등급 문구 보존을 구분해야 한다. 아직 bundle 평가가 없는 이 기록에서 최종 점수를 생성하지 않는다."
new_status = "출처 ID 포함 엄격 진단과 읽을 수 있는 등급 문구 보존을 구분해야 한다. 종료 후 평가의 0/11은 출처 ID까지 일치해야 하는 진단이다. 제공된 등급 문구가 읽힌다는 관측과 구분한다."
old_note = "아래는 위치를 확인한 사례 관측이며 독립 사람의 의미 판정이나 전체 전략 보존 점수가 아니다. 같은 응답에서 인용한 여러 문장을 독립 표본으로 늘려 세지 않는다. 상세 근거와 검토 범위는 연결한 작성자 기록에 남겼다."
new_note = "아래는 위치를 확인한 사례 관측이며 독립 사람의 의미 판정이나 전체 전략 보존 점수가 아니다. 같은 응답에서 인용한 여러 문장을 독립 표본으로 늘려 세지 않는다. 작성자 주석의 평가 진행 상태 표현은 종료 후 평가에 맞춰 갱신했으며, 모델 인용문과 실행 중 작성한 원기록은 그대로 보존했다. 상세 근거와 검토 범위는 연결한 작성자 기록에 남겼다."
checks = []

def check(key, passed, detail):
    checks.append({"id": key, "passed": bool(passed), "detail": detail})

check("initial_changes_requested_preserved", initial["status"] == "CHANGES_REQUESTED", "First document review remains available without overwriting its requested change.")
for key, p in (("paper", oldpaper), ("preparation_status", oldplan)):
    check("old_document_preserved:"+key, sha(p) == initial["provenance"][key]["sha256"], "Original generated document bytes remain unchanged.")
check("exact_two_text_changes", changes == [([old_note], [new_note]), ([old_status], [new_status])], "Only the explanatory provenance note and the stale author-assessment sentence changed; no model quotation changed.")
check("preparation_text_unchanged", oldq.texts == newq.texts, "Preparation-status text is unchanged.")
for name, before, after in (("paper", oldp, newp), ("plan", oldq, newq)):
    check("links_only_r2_self_target:"+name, len(before.links) == len(after.links) and all(a == b or a.replace("20261019.html", "20261019_r2.html") == b for a,b in zip(before.links, after.links)), "The only changed link targets point from the first document to its r2 successor.")
for item in receipt["inputs"]:
    p = Path(item["path"])
    check("final_input_hash:"+p.name, sha(p) == item["sha256"], "The final generation receipt input still matches its recorded SHA256.")
author_path = ROOT / "research/evaluator_only/v48_guarded_pilot_author_review_20261019.json"
author = read(author_path)
paper_text = html.unescape(paper.read_text(encoding="utf-8"))
for i, item in enumerate(author["paper_observations"]):
    check("quote_verbatim:"+str(i), item["model_quote"] in paper_text, "Full model quotation is retained verbatim after HTML entity decoding.")
preserved = {
    author_path: "2c7512565cb8573528d6d19e5d37ac35ee32a41976e174c9854a0235e49a03cd",
    ROOT / "research/evaluator_only/v48_guarded_fidelity_R1_C0_author_observations_20261019.json": "aaff38c20048409887ee13c1266c50e43b0744d82cd90512b698fbc813f7dc05",
    ROOT / "research/evaluator_only/v48_guarded_fidelity_R1_C1_author_observations_20261019.json": "2d418c72505079942e8b296ed6798f68fbe95b80cf8afcc271c19b0951a64d22",
}
for p, h in preserved.items():
    check("author_record_preserved:"+p.name, sha(p) == h, "Historical interim and terminal author records are not silently rewritten.")
evaluation_path = ROOT / "research/evaluator_only/v48_pilot_guarded_20261019/evaluation_report.json"
evaluation = read(evaluation_path)
facts = evaluation["primary_C0_cases"][0]["source_fact_preservation"]
check("displayed_zero_of_eleven_bound_to_actual_diagnostic", facts["exact_label_correct_count"] == 0 and facts["expected_sector_count"] == 11 and facts["source_identity_matches"] is False, "The corrected display explains the existing source-ID-inclusive diagnostic; it does not add a score or change evaluation rules.")
check("stale_sentence_absent_in_final_paper", old_status not in paper_text and new_status in paper_text, "The first-review temporal inconsistency is resolved.")
for original in initial["checks"]:
    if original["id"] in {
        "topic_to_observable", "economic_management_connection", "control_is_procedure",
        "quantities_and_paper_adaptation", "public_source_and_paraphrase_limit", "source_date_types",
        "market_vintage_limit", "reference_year_suffixes", "latest_run_counts", "raw_c0_primary",
        "c2_no_completion_credit", "gpu_failure_not_model_judgment", "ubs_not_attempted",
        "old_and_guarded_separate", "awake_not_gpu_guarantee", "strict_label_scope",
        "all_pairs_unobserved", "invalid_vector_rationale_kept", "supported_and_unsupported_links",
        "no_neutral_or_strategy_threshold", "human_review_pending", "main_unexecuted_candidate_absent",
        "response_strategy_generalization_withheld", "proposed_response_effects_unmeasured", "operating_confounds_disclosed",
    }:
        check(original["id"], original["passed"], original["detail"] + " The exact text delta check confirms this reviewed content is unchanged in r2.")
check("actual_document_sha_at_finish", [sha(paper), sha(plan)] == expected, "Final documents remained unchanged during this read-only review.")
assert all(c["passed"] for c in checks), [c for c in checks if not c["passed"]]
report = {
    "round": 3,
    "status": "PASS",
    "status_meaning": "The final actual documents consistently report the available evidence and its limits. This is document-review PASS, not pilot readiness, strategy success, main execution authorization or independent human review.",
    "scope": "Actual r2 paper and preparation-status document: logical consistency, paper-topic/experiment connection, evidence limitations and literal preservation, with final delta against the fully read first version. Visual review belongs to root round1.",
    "created_at_utc": datetime.now(timezone.utc).isoformat(),
    "reviewer": initial["reviewer"],
    "authorship_disclosure": initial["authorship_disclosure"],
    "provenance": {"paper": ref(paper), "preparation_status": ref(plan), "document_receipt": ref(receipt_path), "initial_review": ref(initial_path), "author_review": ref(author_path), "evaluation": ref(evaluation_path), "review_generator": ref(Path(__file__))},
    "check_count": len(checks),
    "pass_count": sum(c["passed"] for c in checks),
    "checks": checks,
    "resolved_change": {"initial_location": "paper#readiness source_id author assessment", "old_text": old_status, "new_display_text": new_status, "new_note": new_note, "raw_model_or_source_records_changed": False},
    "required_changes": [],
    "remaining_research_status": {"actual_pilot_runtime_integrity": "FAIL", "institution_strategy_preservation_verdict": None, "main_candidate_created": False, "main_execution_authorized_by_this_review": False},
    "limits": initial["limits"],
    "review_process_note": "An overly expensive character-level inline diff was stopped after identifying its own process. A lightweight HTML text-node/link comparison then established the exact two text changes. No document or experiment artifact was modified by either comparison.",
    "model_calls": 0,
    "main_model_calls": 0,
    "independent_human_review_completed": False,
    "documents_modified_by_this_review": False,
    "frozen_inputs_modified": False,
}
assert not OUT.exists(), "Preserve existing review receipts."
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(json.dumps({"path": str(OUT), "sha256": sha(OUT), "status": report["status"], "check_count": len(checks), "pass_count": report["pass_count"]}))
