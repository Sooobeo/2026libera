"""Offline checks of additive document updates; no model requests."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import build_local_engineering_addendum as builder


class AddendumTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        evidence = self.root / "data/raw.json"
        evidence.parent.mkdir()
        evidence.write_text('{"done":true}', encoding="utf-8")
        self.config = {
            "protocol_version": "4.3",
            "model": {"ollama_tag": "qwen3.5:4b-q4_K_M", "max_output_tokens": 8192,
                      "context_tokens": 65536, "thinking": False},
            "observed_execution": {"main": {"status": "not_run", "frozen": False,
                                               "completed_cases": 0, "completed_calls": 0},
                                   "pilot": {"attempted_calls": 1, "completed_calls": 0}},
            "results": {"main_execution_ready": False, "ai_runs": 0},
            "evaluation": {"original_rule": "preserve"},
        }
        self.html = '<html><body><main><p>Original values: 1.5000 &amp; unknown.</p><section id="runtime-v43"><h2>Old record</h2><p>unchanged</p></section><footer>existing</footer></main></body></html>'
        for key, name in builder.FILES.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.config) if key == "config" else self.html, encoding="utf-8")
        self.report = {
            "schema_version": "local_remote_engineering_comparison_1.0", "generated_at_utc": "2026-10-18T08:00:00Z",
            "builder_model_calls": 0, "pilot_model_calls": 0, "main_model_calls": 0,
            "research_suitability_certified": False, "latency_solution_certified": False,
            "source_files": [{"path": "data/raw.json", "exists": True,
                              "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}],
            "observations": [{"environment": "local_windows", "input_kind": "synthetic",
                              "model": "qwen3:1.7b", "probe_id": "1p7b_threads2", "status": "ok",
                              "saved_details": {"requests": [{"settings": {"num_predict": 32}}]},
                              "calls": [{"metrics": {"wall_seconds": 6.4, "eval_count": 6}, "raw_stream_bytes": 900}]}],
            "warnings": [],
        }
        self.report_path = self.root / builder.REPORT
        self.report_path.parent.mkdir(exist_ok=True)
        self.save_report()
        self.report_path.with_suffix(".html").write_text("<html><body>Readable report</body></html>", encoding="utf-8")

    def save_report(self):
        self.report_path.write_text(json.dumps(self.report), encoding="utf-8")

    def test_exact_preservation_and_shared_appendix(self):
        before = {key: (self.root / name).read_bytes() for key, name in builder.FILES.items()}
        outputs, record = builder.build_documents(self.root, self.report_path)
        self.assertEqual({key: (self.root / name).read_bytes() for key, name in builder.FILES.items()}, before)
        for key in ("plan", "paper"):
            self.assertEqual(builder.strip_own_blocks(outputs[key]), self.html)
        self.assertEqual(outputs["plan"], outputs["paper"])
        new = json.loads(outputs["config"])
        self.assertEqual(new.pop(builder.KEY), record)
        self.assertEqual(new, self.config)
        self.assertEqual(record["pilot_model_calls_added"], 0)
        self.assertFalse(record["compact_prompt_adopted_for_research"])
        self.assertIn('href="../research/local_sector_latency_20261018.html"', outputs["plan"])
        self.assertIn('href="../research/local_sector_latency_20261018.json"', outputs["plan"])
        self.assertLess(outputs["plan"].index('id="local-engineering-20261018"'), outputs["plan"].index("<footer>"))

    def test_styled_article_placement_and_main_fallback(self):
        paper = self.html.replace("<main>", "<main><article>").replace("<footer>", "</article><footer>")
        (self.root / builder.FILES["paper"]).write_text(paper, encoding="utf-8")
        outputs, _ = builder.build_documents(self.root, self.report_path)
        self.assertLess(outputs["paper"].index('id="local-engineering-20261018"'), outputs["paper"].index("</article>"))
        self.assertEqual(builder.strip_own_blocks(outputs["paper"]), paper)
        self.assertEqual(builder.appendix_position("<main>x</main>"), len("<main>x"))
        with self.assertRaises(ValueError):
            builder.appendix_position("<body>No styled wrapper</body>")

    def test_repeat_is_idempotent(self):
        first, _ = builder.build_documents(self.root, self.report_path)
        for key, value in first.items():
            (self.root / builder.FILES[key]).write_text(value, encoding="utf-8")
        second, _ = builder.build_documents(self.root, self.report_path)
        self.assertEqual(first, second)

    def test_changed_evidence_is_not_silently_used(self):
        (self.root / "data/raw.json").write_text('{"done":false}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Evidence changed"):
            builder.build_documents(self.root, self.report_path)

    def test_research_counts_or_readiness_cannot_be_imported(self):
        for key, value in [("main_model_calls", 1), ("pilot_model_calls", None),
                           ("research_suitability_certified", True), ("latency_solution_certified", True)]:
            with self.subTest(key=key):
                candidate = copy.deepcopy(self.report)
                candidate[key] = value
                with self.assertRaises(ValueError):
                    builder.validate_report(candidate, self.root)
        candidate = copy.deepcopy(self.config)
        candidate["observed_execution"]["main"]["frozen"] = True
        with self.assertRaises(ValueError):
            builder.validate_study(candidate)

    def test_missing_metrics_stay_unknown_and_bad_markers_fail(self):
        self.report["observations"][0]["calls"] = []
        self.save_report()
        outputs, _ = builder.build_documents(self.root, self.report_path)
        self.assertIn("미관측", outputs["plan"])
        self.assertNotIn("6.400", outputs["plan"])
        with self.assertRaises(ValueError):
            builder.strip_own_blocks("<!-- LOCAL_ENGINEERING_APPENDIX:BEGIN -->broken")


if __name__ == "__main__":
    unittest.main()
