"""Meaningful HTML checks on synthetic artifacts; no browser or model grading."""
import copy
from html.parser import HTMLParser
from pathlib import Path
import unittest

import test_evaluate_sector_v48_artifacts as fixture_module
from evaluate_sector_v48_artifacts import ROSTER
from render_v48_review_packet import render_packet, write_packet, weight


class Inspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.links, self.scripts = [], [], 0
    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.ids.append(values["id"])
        if tag == "a":
            self.links.append(values.get("href", ""))
        if tag == "script":
            self.scripts += 1


class RenderPacketTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.ArtifactLoaderTests()
        self.fixture.setUp()
        self.fixture.endpoint(ROSTER[0], "stage1")
        self.fixture.endpoint(ROSTER[0], "C0", total=0.975)
        self.fixture.endpoint(ROSTER[0], "C1", total=1)
        self.fixture.case_summary(ROSTER[0], ["stage1", "C0", "C1"])
        self.report, self.worksheet = self.fixture.load()
        self.worksheet = copy.deepcopy(self.worksheet)
        self.paths = {"report_path": self.fixture.root / "evaluation_report.json",
                      "worksheet_path": self.fixture.root / "semantic_review_worksheet.json",
                      "output_path": self.fixture.root / "preview.html"}

    def tearDown(self):
        self.fixture.tearDown()

    def render(self, **kwargs):
        return render_packet(self.report, self.worksheet, **self.paths, **kwargs)

    def test_primary_precedes_auxiliary_and_pending_is_explicit(self):
        html = self.render()
        self.assertLess(html.index('id="primary"'), html.index('id="auxiliary"'))
        self.assertIn('id="' + ROSTER[0]["case_id"] + '-C0"', html)
        self.assertIn('id="' + ROSTER[0]["case_id"] + '-C1"', html)
        self.assertIn("독립 사람 검토 전", html)
        self.assertIn("세 차례 AI 자체 검증은 독립 사람 검토를 대신하지 않습니다", html)
        self.assertIn("97.5%", html)
        self.assertIn("44개 산업행", html)

    def test_literal_text_is_escaped_not_executed(self):
        row = self.worksheet["primary_C0_reviews"][0]["sector_reviews"][0]
        row["allocation_rationale_literal"] = '<script>alert("x")</script><img src=x onerror=alert(1)>'
        row["source_passages"][0]["text"] = "Source <b>literal</b> & uncertainty"
        html = self.render()
        parser = Inspector(); parser.feed(html)
        self.assertEqual(parser.scripts, 0)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("Source &lt;b&gt;literal&lt;/b&gt; &amp; uncertainty", html)

    def test_dangerous_source_url_is_not_a_link(self):
        self.worksheet["primary_C0_reviews"][0]["source_material_context"]["source_url"] = "javascript:alert(1)"
        parser = Inspector(); parser.feed(self.render())
        self.assertFalse(any(href.startswith("javascript:") for href in parser.links))

    def test_anchor_targets_unique_and_internal_links_resolve(self):
        parser = Inspector(); parser.feed(self.render())
        self.assertEqual(len(parser.ids), len(set(parser.ids)))
        for href in parser.links:
            if href.startswith("#"):
                self.assertIn(href[1:], parser.ids)

    def test_unknown_missing_and_zero_are_distinct(self):
        self.assertIn("0%", weight(0))
        self.assertEqual(weight(None), "미기록·계산 불가")
        self.assertIn("앞 단계 원문", self.render())
        self.assertIn("새로운 독립 표본이나 최종안으로 세지 않습니다", self.render())

    def test_synthetic_banner_prevents_empirical_result_confusion(self):
        html = self.render(synthetic=True)
        self.assertIn("합성 데이터 화면 점검용 · 실제 모델·실험 결과 아님", html)
        self.assertIn("연구 결과로 인용하지 않습니다", html)

    def test_mismatched_provenance_and_endpoint_mixing_rejected(self):
        original = copy.deepcopy(self.worksheet)
        self.worksheet["provenance"]["different"] = True
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.render()
        self.worksheet = original
        self.worksheet["primary_C0_reviews"][0]["endpoint"] = "C1"
        with self.assertRaisesRegex(ValueError, "endpoint collections"):
            self.render()

    def test_write_refuses_to_overwrite_review_packet(self):
        fixture_module.save(self.paths["report_path"], self.report)
        fixture_module.save(self.paths["worksheet_path"], self.worksheet)
        path = write_packet(**self.paths, synthetic=True)
        self.assertTrue(path.is_file())
        with self.assertRaises(FileExistsError):
            write_packet(**self.paths, synthetic=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
