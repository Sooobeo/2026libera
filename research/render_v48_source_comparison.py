"""Render a Korean evaluator-only source worksheet from pinned local files.

No network, model call, frozen-input edit, or automatic substantive verdict.
PDF row images and text excerpts remain separate from model-input paraphrases.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research/evaluator_only/v48_source_comparison_20261018.json"
MANIFEST = ROOT / "data/sector_documents/source_manifest.json"
OUT = SOURCE.with_suffix(".html")
ASSETS = SOURCE.parent / "v48_source_comparison_assets_20261018"
EXCERPTS = SOURCE.parent / "v48_source_comparison_original_excerpts_20261018.json"
RECEIPT = SOURCE.parent / "v48_source_comparison_render_receipt_20261018.json"
KOREAN = {"10": "에너지", "15": "소재", "20": "산업재", "25": "경기소비재", "30": "필수소비재",
          "35": "헬스케어", "40": "금융", "45": "정보기술", "50": "커뮤니케이션 서비스", "55": "유틸리티", "60": "부동산"}
CATEGORIES = ["실질적 차이를 뒷받침하는 근거 있음", "유사성을 뒷받침하는 근거 있음", "척도가 달라 직접 비교하기 어려움", "근거 부족", "불확실"]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def ref(path):
    path = Path(path).resolve()
    return {"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def text(value):
    return escape("미제공" if value is None else str(value), quote=True)


def public_link(url, label, page=None):
    parsed = urlsplit(url)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise ValueError("Only public HTTP(S) source links are allowed")
    target = url + ("#page=" + str(page) if page else "")
    return '<a href="' + text(target) + '" target="_blank" rel="noopener noreferrer">' + text(label) + '</a>'


def extract_pdf(packet, source, assets):
    import fitz
    path = ROOT / source["cache"]["path"]
    if ref(path)["sha256"] != source["cache"]["sha256"]:
        raise ValueError("PDF checksum differs: " + str(path))
    sid = packet["source_id"]
    fidelity = sid.startswith("fidelity_")
    rating_page, definition_page = (3, 2) if fidelity else (21, 27)
    document = fitz.open(path)
    page = document[rating_page - 1]
    blocks = page.get_text("blocks")
    definition_blocks = document[definition_page - 1].get_text("blocks")
    if fidelity:
        selected = [b[4] for b in definition_blocks if "Overweight and underweight views" in b[4]]
        if len(selected) != 1: raise ValueError("Expected one Fidelity definition footnote")
        definition = selected[0]
        start = definition.index("Strategist view, fundamentals")
        end = definition.index("Time horizon view factors")
        definition = definition[start:end].strip()
        sector_context = None
    else:
        selected = [b[4] for b in definition_blocks if b[4].startswith(("Global asset class preferences definitions", "Attractive:", "Note: For equities"))]
        if len(selected) != 3: raise ValueError("Expected UBS definition and tier note")
        definition = "\n".join(selected)
        context = [b[4] for b in blocks if b[4].startswith("US equities – sectors")]
        if len(context) != 1: raise ValueError("Expected one US sector paragraph")
        sector_context = context[0]
    excerpts = {"source_id": sid, "pdf": ref(path), "rating_page": rating_page, "definition_page": definition_page,
                "definition_literal_extracted": definition, "sector_context_literal_extracted": sector_context,
                "extraction_note": "PDF text layer; original line breaks and soft hyphens retained. Row images preserve color/column-position ratings. No rating inferred from text extraction.", "rows": {}}
    for sector in packet["sectors"]:
        code, name = sector["sector_code"], sector["sector_name"]
        matched = [b for b in blocks if b[4].splitlines() and b[4].splitlines()[0].strip().casefold() == name.casefold()]
        if len(matched) != 1: raise ValueError("Expected one exact sector row: " + sid + ":" + code)
        block = matched[0]
        lines = block[4].splitlines()
        if fidelity:
            if sid == "fidelity_q3_2026":
                comment = "\n".join(lines[2:]).strip()
                crop = fitz.Rect(35, block[1] - 2, 439, block[3] + 2)
            else:
                first = next(i for i, line in enumerate(lines[1:], 1) if line.strip() and line.strip()[0].isalpha())
                comment = "\n".join(lines[first:]).strip()
                crop = fitz.Rect(35, block[1] - 2, 307, block[3] + 2)
        else:
            comment = None
            crop = fitz.Rect(310, block[1] - 3, 570, block[3] + 3)
        image_path = assets / (sid + "_" + code + ".png")
        page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=crop, alpha=False).save(image_path)
        excerpts["rows"][code] = {"sector_name": name, "literal_comment": comment,
            "original_row_image": ref(image_path), "clip_pdf_points": list(crop),
            "full_page_source_link": packet["source_url"] + "#page=" + str(rating_page),
            "human_transcription_review": None}
    document.close()
    return excerpts


STYLE = """body{margin:0;background:#f3f5f7;color:#172b3b;font:16px/1.65 'Malgun Gothic',system-ui,sans-serif}main{max-width:1460px;margin:auto;padding:32px 24px 72px}h1{font-size:30px;line-height:1.35}h2{margin-top:40px;font-size:24px}h3{font-size:18px}a{color:#125780;overflow-wrap:anywhere}p{margin:8px 0 14px}.intro,.source-card,.limitations{background:white;border:1px solid #ccd6de;border-radius:10px;padding:22px;margin:20px 0}.notice{border-left:5px solid #b88726;padding:14px 18px;background:#fff7e4}.muted{font-size:13px;color:#506171}.pending{display:inline-block;background:#fff0c9;color:#67450a;border:1px solid #c7a966;border-radius:4px;padding:3px 8px}.source-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.source-card{margin:0}dl{display:grid;grid-template-columns:145px 1fr;gap:4px 12px}dt{font-weight:bold}dd{margin:0;overflow-wrap:anywhere}blockquote{margin:12px 0;padding:12px 14px;border-left:3px solid #8296a7;background:#f6f8fa;white-space:pre-line;font:14px/1.65 Georgia,serif}table{border-collapse:collapse;width:100%;table-layout:fixed;background:white}th,td{border:1px solid #c4d0da;padding:15px;vertical-align:top;overflow-wrap:anywhere}thead th{background:#203e55;color:white;text-align:left}thead th:first-child{width:11%}thead th:last-child{width:17%}td img{display:block;width:100%;height:auto;background:white;border:1px solid #d5dce1;margin:10px 0}.paraphrase{border-top:1px dashed #a7b5c2;padding-top:10px;font-size:14px}.review-lines{font-size:14px;line-height:2.1}.review-lines span{display:block;border-bottom:1px solid #b6c1ca;min-height:30px}summary{cursor:pointer;color:#125780;font-weight:bold}.key{font-family:monospace;font-size:11px;word-break:break-all}nav{display:flex;flex-wrap:wrap;gap:16px}.split-note{padding:8px 0}.questions li{margin-bottom:10px}@media(max-width:850px){main{padding:20px 12px}.source-grid{grid-template-columns:1fr}table,thead,tbody,tr,th,td{display:block;width:auto!important}thead{display:none}tr{margin-bottom:24px;border:2px solid #92a7b8}td,th{border:0;border-bottom:1px solid #c4d0da}td:before{display:block;font-weight:bold;content:attr(data-label)}dl{grid-template-columns:1fr}}@media print{body{background:white;font-size:10pt}main{padding:0}nav{display:none}.source-grid{display:block}.source-card{margin:15px 0}details{display:block}tr{break-inside:avoid}h2{break-before:page}a{color:#172b3b}blockquote{font-size:9pt}.notice{background:white}}"""


def source_card(packet, excerpts):
    sid, dates = packet["source_id"], packet["dates"]
    definition_note = ("Fidelity의 전략가 견해는 회사 전체의 견해라고 단정할 수 없으며, 광범위 시장 대비 가상의 비중 조정을 설명합니다."
                       if sid.startswith("fidelity") else
                       "아래 정의의 원문 제목은 Global asset class preferences definitions입니다. 이를 개별 산업의 정확한 목표 비중 규칙으로 확대하지 마세요. 12개월 기회 판단과 실제 전술적 자산배분은 구별됩니다.")
    fields = [("출처에 기록된 날짜", dates["publisher_document_date"]), ("날짜의 근거 유형", dates["publisher_date_kind"]),
              ("산업 판단일 원표기", dates["sector_view_as_of_raw"]), ("정규화된 판단일", dates["sector_view_as_of_normalized"]),
              ("날짜 확인 상태", dates["sector_view_date_status"]), ("시장 통계 기준일", dates["market_statistics_as_of"]),
              ("문서 수집 기준일", dates["snapshot_cutoff"])]
    warning = ('<p class="notice">원문에는 존재하지 않는 날짜 6/31/26이 인쇄되어 있습니다. 6/30/26으로 임의 수정하지 않았으며 판단 기준일은 미해결입니다.</p>'
               if sid == "fidelity_q3_2026" and dates["sector_view_as_of_raw"] == "6/31/26" else "")
    context = ('<h4>산업 설명 원문 전체 · PDF ' + str(excerpts["rating_page"]) + '쪽</h4><blockquote>'
               + text(excerpts["sector_context_literal_extracted"]) + '</blockquote>') if excerpts["sector_context_literal_extracted"] else ""
    return ('<article class="source-card" id="source-' + text(sid) + '"><h3>' + text(packet["title"]) + '</h3><p>'
            + text(packet["issuer"]) + '</p><p>' + public_link(packet["source_url"], "발행기관 원문 PDF")
            + ' · ' + public_link(packet["source_url"], "등급 도표 " + str(excerpts["rating_page"]) + "쪽", excerpts["rating_page"])
            + ' · ' + public_link(packet["source_url"], "정의 " + str(excerpts["definition_page"]) + "쪽", excerpts["definition_page"])
            + '</p><dl>' + ''.join('<dt>' + text(k) + '</dt><dd>' + text(v) + '</dd>' for k, v in fields) + '</dl>' + warning
            + ('<p class="muted">위 날짜는 공식 소개 페이지에 표시된 갱신일이며 PDF 자체의 발행일과 동일하다고 단정하지 않습니다.</p>' if sid.startswith("fidelity") else '')
            + '<p><b>등급 어휘:</b> ' + text(' / '.join(packet["rating_vocabulary"])) + '</p><p>' + definition_note
            + '</p><details><summary>정의 원문 확인</summary><blockquote>' + text(excerpts["definition_literal_extracted"])
            + '</blockquote></details>' + context + '<p class="muted">선정 구간에는 수치 목표 비중이 발표되어 있지 않습니다. PDF 체크섬: <span class="key">'
            + text(excerpts["pdf"]["sha256"]) + '</span></p></article>')


def source_cell(source, packet, excerpt, code):
    row = excerpt["rows"][code]
    image_name = ASSETS.name + "/" + Path(row["original_row_image"]["path"]).name
    literal = ('<blockquote data-kind="original-comment">' + text(row["literal_comment"]) + '</blockquote>') if row["literal_comment"] else (
        '<p class="muted">이 칸은 원문 도표의 산업 행을 보여줍니다. 개별 산업의 설명 유무·근거는 아래 링크의 US equities – sectors 원문 전체에서 사람이 확인해야 합니다.</p>')
    paragraphs = ''.join('<p data-evidence-id="' + text(p["evidence_id"]) + '">' + text(p["text"])
                         + '<br><span class="key">' + text(p["evidence_id"]) + '</span></p>' for p in source["passages"])
    return ('<td data-label="' + text(packet["issuer"]) + '" data-source-id="' + text(source["source_id"]) + '"><b>'
            + text(packet["issuer"]) + '</b><p class="muted">판단일 원표기: ' + text(packet["dates"]["sector_view_as_of_raw"])
            + ' · 등급 어휘: ' + text(' / '.join(source["rating_vocabulary"])) + '</p><p><b>실제 원문 도표 행</b> (PDF '
            + str(excerpt["rating_page"]) + '쪽)</p><a href="' + text(image_name) + '"><img src="' + text(image_name)
            + '" alt="' + text(source["source_id"] + ' ' + code + ' 원문 도표 행; 색과 열 위치를 원문 범례와 함께 확인')
            + '" loading="lazy"></a>' + literal + '<p>' + public_link(packet["source_url"], "해당 원문 페이지", excerpt["rating_page"])
            + ' · <a href="#source-' + text(source["source_id"]) + '">정의·날짜·문맥 확인</a></p><div class="paraphrase"><b>기존 모델 입력의 연구자 의역</b> (직접 인용 아님)'
            + paragraphs + '</div><p class="muted">이 출처의 사람 검토: <b>미작성</b></p></td>')


def render(comparison, packets, excerpts):
    pieces = ['<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>v4.8 기관 문서 비교 검토표</title><style>' + STYLE + '</style></head><body><main>',
        '<h1>기관 문서 비교 검토표</h1><p>v4.8 · 예비실험 11개 산업 + 본실험 후보 11개 산업 · 평가자 전용</p><p class="notice"><b>독립적인 사람 검토는 아직 미완료입니다.</b> 두 문서의 차이·유사성·비교 가능성을 자동 판정하지 않았습니다. 이 표는 모델 입력이 아니며, 모델 응답이나 실험 결과도 포함하지 않습니다.</p>',
        '<nav><a href="#limits">해석 범위와 검토 질문</a><a href="#pilot">예비실험 11행</a><a href="#main">본실험 후보 11행</a><a href="#sources">원문 정의·날짜</a></nav>',
        '<section class="limitations" id="limits"><h2>무엇을 확인하는 표인가</h2><p>논문의 핵심은 공개된 판단이 모델의 설명과 실제 산업 비중 결정으로 이어지는 과정입니다. 이 표에서는 먼저 입력 문서 자체에 비교할 만한 차이와 근거가 있는지 확인합니다. 문서의 차이와 모델의 차이는 별개의 판단입니다.</p><ul><li>Fidelity의 Overweight와 UBS의 Attractive를 같은 등급으로 자동 변환하지 않습니다. Neutral도 정확한 기준 비중을 뜻한다고 가정하지 않습니다.</li><li>자료는 공개된 전략가·하우스뷰입니다. 비공개 투자 목적, 고객 위험회피계수, 자본·차입 제약, 실제 보유 비중을 식별한 자료가 아닙니다.</li><li>문서마다 발행일과 판단일이 다릅니다. 동일 시점·동일 정보에 근거한 기관 고유 성향의 차이라고 단정할 수 없습니다.</li><li>이 자료는 과거 시점에 보존된 원본 바이트를 인증한 역사 재현이 아닙니다. 현재 확보한 PDF의 체크섬을 고정한 회고적 문서 사례입니다.</li><li>서로 다른 문서가 비슷한 판단을 보여도 이를 억지로 반대 입장으로 만들지 않습니다. 차이가 확인되지 않으면 그 사실과 비교 한계를 기록합니다.</li><li>원문 도표 행은 PDF에서 잘라낸 이미지입니다. 설명의 인용문은 PDF 텍스트층에서 읽었고 줄바꿈·소프트 하이픈을 유지했습니다. 연구자 의역은 별도로 표시합니다.</li></ul>',
        '<h3>본실험 전에 사람이 답할 질문</h3><ol class="questions"><li>등급의 의미·대상 시장·판단 기간이 실제로 비교 가능한가? 어느 정의와 페이지가 이를 뒷받침하는가?</li><li>등급 표기만 다른가, 판단 이유·조건·전망에도 차이가 있는가? 해당 원문 문장을 각각 기록했는가?</li><li>개별 산업의 이유가 직접 제시됐는가? 미국 주식 전체나 다른 자산군의 설명을 산업별 이유로 잘못 옮기지 않았는가?</li><li>발행·판단 기준일 차이와 Fidelity Q3의 날짜 오류를 어떻게 제한할 것인가?</li><li>모델 입력의 의역이 원문 의미를 빠뜨리거나 강하게 만들지 않았는가? 사람 수정이 필요하면 별도 변경안과 이유를 남겼는가?</li><li>비교를 통해 주장할 수 있는 범위를 문서 해석 사례로 제한했는가? 실제 기관 전략·보유·투자 성과를 재현했다는 주장을 피했는가?</li></ol><p>행별 판정 후보: '
        + text(' / '.join(CATEGORIES)) + '. 아직 아무 후보도 선택하지 않았습니다.</p><p class="muted">열람·인쇄용 표입니다. 판정은 검토자·날짜·원문 위치와 함께 별도 기록해야 하며, 이 화면은 기존 JSON을 저장하거나 수정하지 않습니다.</p></section>',
        '<section id="sources"><h2>원문 정의·발행일·판단일</h2><div class="source-grid">']
    for sid, packet in packets.items(): pieces.append(source_card(packet, excerpts[sid]))
    pieces.append('</div></section>')
    for split, group in comparison["splits"].items():
        title = "예비실험" if split == "pilot" else "본실험 후보 문서"
        pieces.append('<section id="' + text(split) + '"><h2>' + title + ' · 11개 산업</h2><p class="split-note">'
                      + ('기계적 실행과 기록을 확인하는 예비 자료입니다.' if split == "pilot" else '문서 비교를 위한 열람입니다. 본실험을 실행했다는 뜻이 아닙니다.')
                      + '</p><table><thead><tr><th>산업</th><th>Fidelity 원문과 입력 의역</th><th>UBS 원문과 입력 의역</th><th>사람의 비교 판정</th></tr></thead><tbody>')
        for row in group["rows"]:
            code = row["sector_code"]
            pieces.append('<tr data-record-id="' + text(row["record_id"]) + '" data-review-state="unreviewed"><th scope="row">'
                          + text(code + ' ' + KOREAN[code]) + '<br><span class="muted">' + text(excerpts[row["sources"][0]["source_id"]]["rows"][code]["sector_name"]) + '</span></th>')
            for source in row["sources"]:
                sid = source["source_id"]
                pieces.append(source_cell(source, packets[sid], excerpts[sid], code))
            pieces.append('<td data-label="사람의 비교 판정"><span class="pending">미작성</span><div class="review-lines"><span>판정: 미작성</span><span>근거·페이지: 미작성</span><span>검토자: 미작성</span><span>검토일: 미작성</span></div><p class="muted">등급 어휘가 다르다는 사실만으로 실질적 차이를 판정할 수 없습니다.</p></td></tr>')
        pieces.append('</tbody></table></section>')
    pieces.append('<p class="muted">원본 비교 JSON·고정 모델 입력은 변경하지 않았습니다. 모든 사람 판정은 미작성 상태입니다. 자동 보존 판정과 가중 종합 점수는 제공하지 않습니다.</p></main></body></html>')
    return ''.join(pieces)


class Inventory(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows = []; self.sources = []; self.evidence = []; self.images = []; self.scripts = 0
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr" and "data-record-id" in attrs: self.rows.append(attrs)
        if "data-source-id" in attrs: self.sources.append(attrs["data-source-id"])
        if "data-evidence-id" in attrs: self.evidence.append(attrs["data-evidence-id"])
        if tag == "img": self.images.append(attrs["src"])
        if tag == "script": self.scripts += 1


class RendererTests(unittest.TestCase):
    def test_escape(self):
        self.assertEqual(text('<script x="y">&'), '&lt;script x=&quot;y&quot;&gt;&amp;')
        parser = Inventory(); parser.feed('<p>' + text('</p><script>alert(1)</script>') + '</p>')
        self.assertEqual(parser.scripts, 0)
    def test_url_protocol(self):
        with self.assertRaises(ValueError): public_link('javascript:alert(1)', 'x')
        self.assertIn('a=1&amp;b=2#page=3', public_link('https://example.org/a?a=1&b=2', 'x', 3))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RendererTests))
        return 0 if result.wasSuccessful() else 1
    for path in (OUT, EXCERPTS, RECEIPT, ASSETS):
        if path.exists(): raise FileExistsError('Use a new version instead of overwriting: ' + str(path))
    comparison = read(SOURCE)
    before = ref(SOURCE)
    manifest = read(MANIFEST)
    sources = {s['source_id']: s for s in manifest['sources']}
    packets, input_refs = {}, [before, ref(MANIFEST)]
    for split, group in comparison['splits'].items():
        assert len(group['rows']) == 11 and {r['sector_code'] for r in group['rows']} == set(KOREAN)
        for item in group['inputs']:
            path = ROOT / item['path']; packet = read(path)
            assert ref(path)['sha256'] == item['sha256'] and packet['split'] == split
            packets[packet['source_id']] = packet; input_refs.append(ref(path))
        for row in group['rows']:
            assert all(row[k] is None for k in ('comparison', 'reviewer', 'review_evidence'))
            assert len(row['sources']) == 2 and all(s['source_review'] is None for s in row['sources'])
    ASSETS.mkdir()
    excerpts = {sid: extract_pdf(packet, sources[sid], ASSETS) for sid, packet in packets.items()}
    EXCERPTS.write_text(json.dumps({'visibility': 'EVALUATOR_ONLY_NEVER_MODEL_INPUT', 'human_review_completed': False,
        'sources': excerpts}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    rendered = render(comparison, packets, excerpts)
    inventory = Inventory(); inventory.feed(rendered)
    expected_rows = [row for group in comparison['splits'].values() for row in group['rows']]
    checks = {
        '22_unique_rows': len(inventory.rows) == 22 and len({r['data-record-id'] for r in inventory.rows}) == 22,
        '44_source_cells_no_drops': len(inventory.sources) == 44 and Counter(inventory.sources) == Counter({s: 11 for s in packets}),
        'all_passage_ids_present': Counter(inventory.evidence) == Counter(p['evidence_id'] for r in expected_rows for s in r['sources'] for p in s['passages']),
        'all_paraphrases_escaped_and_present': all(text(p['text']) in rendered for r in expected_rows for s in r['sources'] for p in s['passages']),
        '44_original_row_images': len(inventory.images) == 44 and all((OUT.parent / name).is_file() for name in inventory.images),
        'all_dates_and_source_links_present': all(text(p['dates']['sector_view_as_of_raw']) in rendered and text(p['source_url']) in rendered for p in packets.values()),
        'all_definitions_present': all(text(e['definition_literal_extracted']) in rendered for e in excerpts.values()),
        'all_human_rows_unreviewed': all(r['data-review-state'] == 'unreviewed' for r in inventory.rows),
        'no_scripts_or_automatic_verdict': inventory.scripts == 0 and 'PASS' not in rendered and '자동 판정하지 않았습니다' in rendered,
        'invalid_date_retained': '6/31/26' in rendered and '판단 기준일은 미해결' in rendered,
        'comparison_unchanged': ref(SOURCE) == before,
        'packet_inputs_unchanged': all(ref(ROOT / item['path']) == item for item in input_refs),
        'escape_probe': text('<script>&"') == '&lt;script&gt;&amp;&quot;',
    }
    if not all(checks.values()): raise AssertionError(checks)
    OUT.write_text(rendered + '\n', encoding='utf-8')
    receipt = {'status': 'RENDERED_UNREVIEWED', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'renderer': ref(__file__), 'html': ref(OUT), 'excerpts': ref(EXCERPTS), 'inputs': input_refs,
        'pdfs': [e['pdf'] for e in excerpts.values()], 'checks': checks, 'check_count': len(checks),
        'human_review_completed': False, 'automatic_substantive_verdict': None,
        'model_calls': 0, 'network_calls': 0, 'frozen_inputs_modified': False,
        'visual_review_scope': 'AI inspected the four complete rating-page PNGs before extraction; rendered row crops preserve original image positions. This is not independent substantive human verification.',
        'quote_scope': 'Selected source material for local research review; existing paraphrases explicitly distinguished. No complete PDFs copied into the output.',
        'topic_connection': 'Verify whether published judgments and reasons can be compared before assessing source-to-rationale-to-allocation preservation.'}
    RECEIPT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': receipt['status'], 'checks': len(checks), 'html': str(OUT), 'receipt': str(RECEIPT)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
