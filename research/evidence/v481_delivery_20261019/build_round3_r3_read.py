"""Read-only content/provenance review of the final vertical observation layout."""
from pathlib import Path
import hashlib
from html.parser import HTMLParser
import json
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).with_name("round3_r3.json")

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def ref(path):
    return {"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha(path)}

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

class Node:
    def __init__(self, tag, attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def walk(self, tag=None):
        if tag is None or self.tag == tag:
            yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk(tag)

    def texts(self, excluded=()):
        if id(self) in excluded or self.tag in ("style", "script"):
            return []
        result = []
        for child in self.children:
            if isinstance(child, Node):
                result.extend(child.texts(excluded))
            elif child.strip():
                result.append(child.strip())
        return result

class Document(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, path):
        super().__init__()
        self.root = Node("document")
        self.stack = [self.root]
        self.feed(path.read_text(encoding="utf-8"))

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)

prior_path = OUT.with_name("round3_r2.json")
prior = read(prior_path)
assert sha(prior_path) == "ab4b7d3ebb127b884b50f72f2c60e21ca970b8f80542ac039746bcb75123bd8f"
receipt_path = ROOT / "research/v481_document_update_receipt_20261019_r3.json"
receipt = read(receipt_path)
paper, plan = [Path(x["path"]) for x in receipt["outputs"]]
expected = ["4e05b630509256d8f0188892fe0d1f43d718c2400010203940805df5c0eb319a", "68c601b1b2a780f2bada5e67fbd52e6a33f5c16f65f49b93d33dc4492f5d2289"]
assert [sha(paper), sha(plan)] == expected
oldpaper = ROOT / prior["provenance"]["paper"]["path"]
oldplan = ROOT / prior["provenance"]["preparation_status"]["path"]
oldp, newp, oldq, newq = [Document(p).root for p in (oldpaper, paper, oldplan, plan)]
oldtables = [n for n in oldp.walk("table") if "사례·응답" in n.texts()]
newgroups = [n for n in newp.walk("div") if n.attrs.get("class") == "observations"]
assert len(oldtables) == len(newgroups) == 1
oldtable, newgroup = oldtables[0], newgroups[0]
rows = [[n for n in row.children if isinstance(n, Node) and n.tag == "td"] for row in oldtable.walk("tr")]
rows = [row for row in rows if row]
articles = list(newgroup.walk("article"))
checks = []

def check(key, passed, detail, **extra):
    checks.append({"id": key, "passed": bool(passed), "detail": detail, **extra})

check("r2_review_and_outputs_preserved", prior["status"] == "PASS" and all(sha(ROOT/prior["provenance"][k]["path"]) == prior["provenance"][k]["sha256"] for k in ("paper", "preparation_status", "document_receipt")), "The previously reviewed r2 documents and receipt remain byte-identical.")
check("eight_rows_to_eight_articles", len(rows) == len(articles) == 8, "Eight completed-C0 observations remain eight observations, with no added or dropped case.")
article_comparisons = []
for i, (row, article) in enumerate(zip(rows, articles)):
    headings = list(article.walk("h4"))
    paragraphs = [n for n in article.children if isinstance(n, Node) and n.tag == "p"]
    check(f"five_fields_structure:{i}", len(row) == 5 and len(headings) == 1 and len(paragraphs) == 3, "Old five-column row is represented by case+claim heading and three labelled content blocks.")
    header = row[0].texts()[0] + " · " + row[1].texts()[0]
    actual = [headings[0].texts(), *[p.texts()[1:] for p in paragraphs]]
    wanted = [[header], row[2].texts(), row[3].texts(), row[4].texts()]
    check(f"five_fields_verbatim_order:{i}", actual == wanted, "Case/endpoint, claim/action, model quote+locator, evidence summary, and author assessment+limits remain in their original order and retain their exact text.")
    check(f"three_labels:{i}", [p.texts()[0] for p in paragraphs] == ["모델 표현과 위치", "대조 근거", "작성자 판단과 한계"], "Repeated labels are presentation only and do not insert new interpretation.")
    article_comparisons.append({"observation_index": i, "case_and_claim": header, "field_texts_match": actual == wanted})
check("paper_outside_observations_unchanged", oldp.texts({id(oldtable)}) == newp.texts({id(newgroup)}), "Outside the converted table/article group, all visible text is identical; CSS is excluded from this content comparison.")
check("plan_visible_text_unchanged", oldq.texts() == newq.texts(), "The preparation-status document has identical visible content.")
for name, before, after in (("paper", oldp, newp), ("plan", oldq, newq)):
    links_a = [n.attrs.get("href") for n in before.walk("a")]
    links_b = [n.attrs.get("href") for n in after.walk("a")]
    check("only_current_self_link:"+name, len(links_a) == len(links_b) and all(a == b or a.replace("20261019_r2.html", "20261019_r3.html") == b for a,b in zip(links_a, links_b)), "Only the document's current-version self link changes; evidence, source, runtime and observation locator links remain in order.")

prior_receipt = read(ROOT / prior["provenance"]["document_receipt"]["path"])
check("same_input_inventory_as_r2", receipt["inputs"] == prior_receipt["inputs"], "The r3 renderer consumes the same evidence and rules as the reviewed r2 output.")
for i, item in enumerate(receipt["inputs"]):
    p = Path(item["path"])
    check(f"input_bytes:{i}", sha(p) == item["sha256"], "Current input SHA256 checked again against r3 receipt.", artifact=ref(p))
author_path = ROOT / "research/evaluator_only/v48_guarded_pilot_author_review_20261019.json"
author = read(author_path)
qtexts = ["".join(n.texts()) for n in newgroup.walk("q")]
check("all_eight_model_quotations_exact", qtexts == [x["model_quote"] for x in author["paper_observations"]], "All eight model quotations exactly match the terminal author-review quotes, in the same order.")
preserved = {
    author_path: "2c7512565cb8573528d6d19e5d37ac35ee32a41976e174c9854a0235e49a03cd",
    ROOT / "research/evaluator_only/v48_guarded_fidelity_R1_C0_author_observations_20261019.json": "aaff38c20048409887ee13c1266c50e43b0744d82cd90512b698fbc813f7dc05",
    ROOT / "research/evaluator_only/v48_guarded_fidelity_R1_C1_author_observations_20261019.json": "2d418c72505079942e8b296ed6798f68fbe95b80cf8afcc271c19b0951a64d22",
}
for p, h in preserved.items():
    check("source_note_preserved:"+p.name, sha(p) == h, "No historical note or terminal author-review bytes were changed for this layout.")
evaluation_path = ROOT / "research/evaluator_only/v48_pilot_guarded_20261019/evaluation_report.json"
evaluation = read(evaluation_path)
facts = evaluation["primary_C0_cases"][0]["source_fact_preservation"]
check("existing_strict_zero_of_eleven_diagnostic", facts["exact_label_correct_count"] == 0 and facts["expected_sector_count"] == 11 and facts["source_identity_matches"] is False, "The retained source-ID-inclusive diagnostic explanation remains bound to the unchanged actual report.")
new_text = "\n".join(newp.texts())
check("corrected_current_status_retained", "아직 bundle 평가가 없는 이 기록에서 최종 점수를 생성하지 않는다." not in new_text and "종료 후 평가의 0/11은 출처 ID까지 일치해야 하는 진단이다." in new_text, "r2's temporal-status correction remains intact.")
check("builder_matches_receipt", sha(Path(receipt["builder"]["path"])) == receipt["builder"]["sha256"], "The final renderer version matches the recorded generation code.")
check("actual_r3_hashes_at_finish", [sha(paper), sha(plan)] == expected, "Actual r3 document hashes remain unchanged during this review.")
assert all(c["passed"] for c in checks), [c for c in checks if not c["passed"]]

# The prior 96 items include historical r1->r2 preservation checks as well as
# semantic/content items. They are carried forward explicitly as a chain,
# not misrepresented as 96 fresh human judgments or 96 new model trials.
prior_revalidation = []
for index, previous in enumerate(prior["checks"]):
    prior_revalidation.append({"prior_check_index": index, "prior_check_id": previous["id"], "passed": previous["passed"], "basis": "r2 historical check receipt and referenced bytes remain intact; current r3 evidence hashes and exact content/field/order preservation are rechecked above."})
assert len(prior_revalidation) == 96 and all(c["passed"] for c in prior_revalidation)
report = {
    "round": 3,
    "status": "PASS",
    "status_meaning": "Final actual-document consistency/readability-content review passes. The actual pilot runtime remains failed; this is not strategy success, main readiness or independent human review.",
    "created_at_utc": datetime.now(timezone.utc).isoformat(),
    "scope": "Read-only r3 semantic/content delta and provenance review: eight table observations converted to vertical articles, with the prior 96-item logic/evidence review preserved and rebound to unchanged content. Visual layout QA is performed separately by root.",
    "reviewer": prior["reviewer"],
    "authorship_disclosure": prior["authorship_disclosure"],
    "provenance": {"paper": ref(paper), "preparation_status": ref(plan), "document_receipt": ref(receipt_path), "prior_round3_r2": ref(prior_path), "author_review": ref(author_path), "evaluation": ref(evaluation_path), "review_generator": ref(Path(__file__))},
    "check_count": len(checks),
    "pass_count": sum(c["passed"] for c in checks),
    "checks": checks,
    "prior_96_item_revalidation": prior_revalidation,
    "prior_96_item_revalidation_count": 96,
    "article_field_comparisons": article_comparisons,
    "required_changes": [],
    "remaining_research_status": prior["remaining_research_status"],
    "limits": prior["limits"],
    "model_calls": 0,
    "main_model_calls": 0,
    "independent_human_review_completed": False,
    "documents_modified_by_this_review": False,
    "frozen_inputs_modified": False,
}
assert not OUT.exists(), "Preserve existing review receipts."
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(json.dumps({"path": str(OUT), "sha256": sha(OUT), "status": report["status"], "check_count": len(checks), "prior_items_revalidated": 96}))
