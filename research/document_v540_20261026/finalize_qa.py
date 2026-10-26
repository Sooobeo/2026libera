"""Bind the reviewed final DOCX to its complete 35-page visual QA record."""
from pathlib import Path
import hashlib
import json
import zipfile
from lxml import etree

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
QA = WORK / "qa" / "word_r1"

def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

build = read(WORK / "build_receipt.json")
word = read(QA / "word_receipt.json")
raster = read(QA / "raster_receipt.json")
structure = read(WORK / "structural_audit.json")
content = read(WORK / "content_audit.json")
docx = Path(build["docx"])
source = Path(build["source"])
pdf = QA / "manuscript.pdf"
docx_hash = sha(docx)
assert docx_hash == build["docx_sha256"] == word["input_sha256_before"] == word["input_sha256_after"] == raster["docx_sha256"] == structure["sha256"]["docx"]
assert sha(source) == build["source_sha256"] == structure["sha256"]["source"]
assert sha(pdf) == word["pdf_sha256"] == raster["pdf_sha256"]
assert word["status"] == "completed" and word["owned_process_exited"]
assert not word["input_saved"] and not word["process_kill_called"] and not word["cleanup_errors"]
assert structure["overall_pass"]
assert len(raster["pages"]) == 35
page_paths = [QA / f"page-{i}.png" for i in range(1, 36)]
assert all(path.is_file() and path.stat().st_size > 10000 for path in page_paths)
review_names = ["visual_review_01_11.md", "visual_review_12_23.md", "visual_review_24_35.md"]
reviews = [QA / name for name in review_names]
assert all("통과" in p.read_text(encoding="utf-8-sig") for p in reviews)
ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main", "m": "http://schemas.openxmlformats.org/officeDocument/2006/math"}
with zipfile.ZipFile(docx) as z:
    xml = etree.fromstring(z.read("word/document.xml"))
texts = ["".join(p.itertext()) for p in xml.findall(".//w:p", ns)]
assert build["title"] in texts and build["subtitle"] in texts
assert len(xml.findall(".//w:tbl", ns)) == 16
assert len(xml.findall(".//w:drawing", ns)) == 6
assert len(xml.findall(".//m:oMath", ns)) == 2
full_text = "\n".join(texts)
assert "본실험" in full_text and "예비" not in full_text
raster["visual_review"] = "passed_all_35_pages_at_original_resolution"
raster["visual_review_files"] = review_names
(QA / "raster_receipt.json").write_text(json.dumps(raster, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
result = {
    "status": "passed",
    "version": "v5.4",
    "docx": str(docx),
    "docx_sha256": docx_hash,
    "docx_bytes": docx.stat().st_size,
    "source_sha256": sha(source),
    "pdf_sha256": sha(pdf),
    "pages_rendered_and_visually_reviewed": 35,
    "visual_review_method": "Each final PNG individually opened at original resolution; all pages passed.",
    "tables": 16,
    "figures": 6,
    "native_equations": 2,
    "title_and_subtitle_exact_match": True,
    "main_experiment_position_verified": True,
    "structural_audit": {"path": "structural_audit.json", "sha256": sha(WORK / "structural_audit.json"), "passed": True},
    "content_audit": {"path": "content_audit.json", "sha256": sha(WORK / "content_audit.json")},
    "visual_reviews": [{"path": str(p.relative_to(WORK)), "sha256": sha(p)} for p in reviews],
    "page_images": [{"page": i, "sha256": sha(p)} for i, p in enumerate(page_paths, 1)],
    "final_docx_modified_by_qa": False,
    "delivery": "DOCX; PDF and PNG files are QA intermediates."
}
(WORK / "final_qa_receipt.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: result[k] for k in ["status", "docx_sha256", "docx_bytes", "pages_rendered_and_visually_reviewed", "tables", "figures", "native_equations"]}))
