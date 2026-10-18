"""Offline document delta verification; no model, network, or source mutations."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).with_name("round2_r3.json")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ref(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": digest(path)}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def soup(path):
    return BeautifulSoup(Path(path).read_text(encoding="utf-8"), "html.parser")


checks = []


def check(name, passed, evidence):
    checks.append({"id": name, "pass": bool(passed), "evidence": evidence})


previous_path = OUT.with_name("round2.json")
previous = read(previous_path)
receipt_path = ROOT / "research/v481_document_update_receipt_20261019_r3.json"
receipt = read(receipt_path)
paths = {
    (folder, version): next((ROOT / folder).glob(f"*_v4.8.1_20261019{version}.html"))
    for folder in ("paper", "plan") for version in ("", "_r2", "_r3")
}
docs = {key: soup(path) for key, path in paths.items()}
check("original_review_preserved", digest(previous_path) == "38f1305b7b39ee92e960a78c9325c9b8fc4f45e98bb38ca98053d78c05a582fa", ref(previous_path))
check("original_finding_preserved", previous["status"] == "CHANGES_REQUESTED" and len(previous["required_changes"]) == 1, previous["required_changes"])
for item in previous["inputs"]:
    check("previous_input_unchanged:" + item["path"], digest(item["path"]) == item["sha256"], item)
for item in receipt["inputs"] + receipt["outputs"] + [receipt["builder"]]:
    check("current_receipt_ref:" + item["path"], digest(item["path"]) == item["sha256"], item)
check("final_paper_hash", digest(paths[("paper", "_r3")]) == "4e05b630509256d8f0188892fe0d1f43d718c2400010203940805df5c0eb319a", ref(paths[("paper", "_r3")]))
check("final_plan_hash", digest(paths[("plan", "_r3")]) == "68c601b1b2a780f2bada5e67fbd52e6a33f5c16f65f49b93d33dc4492f5d2289", ref(paths[("plan", "_r3")]))

old = docs[("paper", "")]
r2 = docs[("paper", "_r2")]
r3 = docs[("paper", "_r3")]
old_table = old.find("q").find_parent("table")
r2_table = r2.find("q").find_parent("table")
old_rows = old_table.find_all("tr")[1:]
r2_rows = r2_table.find_all("tr")[1:]
articles = r3.find_all("article", class_="observation")
check("observation_roster", len(old_rows) == len(r2_rows) == len(articles) == 8, {"old_rows": len(old_rows), "r2_rows": len(r2_rows), "r3_articles": len(articles)})
changed_cells = []
for index, (a, b, article) in enumerate(zip(old_rows, r2_rows, articles)):
    ac, bc = a.find_all("td"), b.find_all("td")
    for column, (left, right) in enumerate(zip(ac, bc)):
        if left.get_text("\n", strip=True) != right.get_text("\n", strip=True):
            changed_cells.append({"row": index, "column": column, "before": left.get_text("\n", strip=True), "after": right.get_text("\n", strip=True)})
    paragraphs = article.find_all("p", recursive=False)
    check(f"observation_{index}:title", article.h4.get_text(" ", strip=True) == bc[0].get_text(" ", strip=True) + " · " + bc[1].get_text(" ", strip=True), article.h4.get_text(" ", strip=True))
    for column, paragraph in zip((2, 3, 4), paragraphs):
        lines = paragraph.get_text("\n", strip=True).splitlines()
        check(f"observation_{index}:field_{column}", "\n".join(lines[1:]) == bc[column].get_text("\n", strip=True), "All model quote/location, comparison evidence, assessment and limitation text matches r2 field exactly.")
    check(f"observation_{index}:quote_unchanged", a.q.get_text() == b.q.get_text() == article.q.get_text(), {"quote": article.q.get_text(), "location": article.a.get_text(), "artifact_link": article.a["href"]})
    check(f"observation_{index}:link_unchanged", a.a["href"] == b.a["href"] == article.a["href"], article.a["href"])
check("only_required_assessment_changed", [(c["row"], c["column"]) for c in changed_cells] == [(6, 4)], changed_cells)
stale = previous["required_changes"][0]["observed_text"]
check("stale_status_removed", stale not in r3.get_text(), "Historical interim no-bundle sentence removed from current display only; original notes remain hash-identical.")
check("current_strict_diagnostic_explained", "종료 후 평가의 0/11은 출처 ID까지 일치해야 하는 진단이다." in articles[6].get_text() and "제공된 11개 등급 문자열은 옮겼지만 source_id는 null이다." in articles[6].get_text(), articles[6].get_text("\n", strip=True))
note = r3.find_all("article")[0].find_previous("p").get_text(" ", strip=True)
check("display_update_disclosed", "작성자 주석의 평가 진행 상태 표현은 종료 후 평가에 맞춰 갱신" in note and "모델 인용문과 실행 중 작성한 원기록은 그대로 보존" in note, note)

# Remove only the changed observation presentation and its update note. The
# remaining scientific text, result tables and reference text must be identical.
clean = {}
for version in ("", "_r2", "_r3"):
    tree = soup(paths[("paper", version)])
    first_quote = tree.find("q")
    container = first_quote.find_parent("article") or first_quote.find_parent("table")
    container.find_previous("p").decompose()
    if version == "_r3":
        for article in tree.find_all("article", class_="observation"):
            article.decompose()
    else:
        container.decompose()
    clean[version] = tree.get_text("\n", strip=True)
check("remaining_scientific_text_unchanged", clean[""] == clean["_r2"] == clean["_r3"], "Full non-observation text, fixed result tables, source dates, parameters, citations, limitations and topic statements are byte-identical after HTML text extraction.")
check("plan_text_unchanged", len({docs[("plan", v)].get_text("\n", strip=True) for v in ("", "_r2", "_r3")}) == 1, "Only link target revision changed; all text and result tables are unchanged.")
for folder in ("paper", "plan"):
    for a in docs[(folder, "_r3")].find_all("a", href=True):
        if "v4.8.1_20261019" in a["href"] and ".html" in a["href"]:
            check(folder + ":current_document_link", "_r3.html" in a["href"], a["href"])

evaluation_path = ROOT / "research/evaluator_only/v48_pilot_guarded_20261019/evaluation_report.json"
evaluation = read(evaluation_path)
check("environment_failure_retained", evaluation["system_integrity_incidents_present"] is True and "Vulkan device lost" in r3.get_text(), "Arithmetic/record consistency PASS does not change operational FAIL; main remains unexecuted.")
check("no_main_or_human_completion_claim", receipt["main_model_calls"] == 0 and receipt["model_calls_by_builder"] == 0 and receipt["independent_human_review_completed"] is False and receipt["frozen_v48_modified"] is False, {k: receipt[k] for k in ("main_model_calls", "model_calls_by_builder", "independent_human_review_completed", "frozen_v48_modified")})
check("actual_request_accounting_retained", receipt["observed_core_requests"] == 8 and receipt["observed_auxiliary_requests"] == 2, {"core": 8, "auxiliary": 2})

report = {
    "round": 2,
    "stage": "stage2_actual_document_review_r3",
    "status": "PASS" if all(c["pass"] for c in checks) else "CHANGES_REQUESTED",
    "created_at_utc": datetime.now(timezone.utc).isoformat(),
    "reviewer": previous["reviewer"],
    "inputs": [ref(previous_path), ref(receipt_path), ref(Path(__file__))] + [ref(p) for p in paths.values()] + previous["inputs"][3:],
    "previous_review": {**ref(previous_path), "status": "CHANGES_REQUESTED", "preserved": True, "resolution": "Required stale time-scope correction is resolved in current display; interim author record and model output unchanged."},
    "checks": checks,
    "manual_read_findings": [
        "Read the corrected source-ID paragraph and all eight final observation articles. Strict 0/11 diagnosis remains distinct from eleven readable copied rating strings and from strategic preservation.",
        "Four C0 rows/44 fixed labels, C0 sum 103.5%, separate C1 sum 99.5%, partial C2, missing R4 response and unattempted UBS cases are unchanged from the checked terminal report. No normalization or C0 substitution.",
        "All valid-pair distances remain unavailable; current environment failure, prior sleep failure, technical implementation PASS and no main execution are separate.",
        "Institution 2026a/b references and document dates, paper-derived precedents versus engineering settings, pretraining uncertainty, fixed-order/concurrent-work caveats, and public judgment-to-reason-to-allocation research scope remain unchanged.",
        "Layout conversion preserves exact model quotes, evidence locations, comparison statements and limitations for eight observations. No new numerical or semantic scoring rule was introduced."
    ],
    "inherited_review_basis": "The original 90 successful checks are not counted as newly rerun tests. Their source bytes remain unchanged, and the non-observation final document text is unchanged. Exact observation field comparisons and current receipt hashes were checked anew above.",
    "scope": "Text/table/quote and provenance consistency review of actual final HTML. Does not substitute for visual rendering review, fresh independent paper replication, or independent human source/semantic assessment.",
    "required_changes": [] if all(c["pass"] for c in checks) else [c["id"] for c in checks if not c["pass"]],
    "pilot_readiness": "FAIL_environment_integrity_unresolved",
    "main_candidate_created": False,
    "main_execution_authorized": False,
    "independent_human_review_completed": False,
    "model_calls": 0,
    "documents_modified_by_reviewer": False,
    "source_v48_modified": False,
}
with OUT.open("x", encoding="utf-8") as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({"path": str(OUT), "sha256": digest(OUT), "status": report["status"], "checks": len(checks), "failures": report["required_changes"]}, ensure_ascii=False))
