"""Run read-only runtime inventory and synthetic engineering checks, never inference."""
from __future__ import annotations

import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import unittest

from research.v63 import runtime as rt, retrieval as retrieval
from research.v63.test_runtime_retrieval import packet


def main():
    target = rt.ROOT / "data/v63_20261027/runtime"
    target.mkdir(parents=True, exist_ok=True)
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromNames(["research.v63.test_runtime_retrieval","research.v63.test_ollama_transport"])
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (target / "engineering_tests.log").write_text(stream.getvalue(), encoding="utf-8")
    rt.write_json(target / "engineering_retrieval.json", packet())
    if not (target / "runtime_probe.json").is_file():
        rt.write_json(target / "runtime_probe.json", rt.probe_runtime())
    schedule = rt.planned_schedule()
    rt.write_json(target / "planned_schedule.json", {"status": "not_attempted", "trajectories": len(schedule),
                   "logical_stages": sum(x["logical_stages"] for x in schedule), "model_calls": 0,
                   "seed": 5001, "schedule": schedule})
    sources = [Path(retrieval.__file__), Path(rt.__file__), Path(__file__),
               *[Path(__file__).with_name(name) for name in ("test_runtime_retrieval.py","test_ollama_transport.py","ollama_transport.py","transport_errors.py")]]
    report = {"scope": "synthetic_engineering_and_read_only_environment_only", "actual_experimental_model_calls": 0,
              "new_v63_results": False, "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "success": result.wasSuccessful(), "planned_trajectories": len(schedule), "planned_logical_stages": 9816,
              "candidate_implementation": ["Actual rank-bm25 0.2.2 BM25Okapi retrieval", "Pre-ranking eligibility filters",
                                           "Atomic evidence boundaries and merged overlap", "Frozen packet replay across onset arms",
                                           "Three-stage full-history state machine", "Strict JSON response schemas",
                                           "Two-tool-roundtrip limit", "Same-byte bounded infrastructure retries",
                                           "Ollama 0.35.1 candidate HTTP adapter with per-request digest/template/version pins and raw byte logs",
                                           "Invalid raw allocations preserved; no normalization", "Explicit unattempted/parent/model/operational/protocol statuses"],
              "remaining": ["Frozen exact model tokenizer and chat renderer not available",
                            "Ollama adapter candidate passes fake HTTP tests; integration with the actual server and full v6.3 schemas remains unverified",
                            "Real full-history token, latency, usage, resource, and budget measurements not available",
                            "B numerical tool adapter and actual human-audited fund data not yet integrated",
                            "A/C official-document semantic-evidence extraction and audit not validated",
                            "No development pilot, main experiment, counterfactual, negative-control, A, or C model requests executed"],
              "test_counter": "Synthetic whitespace counter used ONLY for engineering tests; forbidden in production",
              "package_versions": {name: importlib.metadata.version(name) for name in ("rank-bm25", "numpy", "jsonschema")},
              "dependency_directory": "tmp/v63_python_deps; rank-bm25==0.2.2 installed with --no-deps",
              "primary_implementation_source": "https://github.com/dorianbrown/rank_bm25",
              "transport_primary_sources": ["https://raw.githubusercontent.com/ollama/ollama/v0.35.1/api/types.go",
                                            "https://docs.ollama.com/api/chat","https://docs.ollama.com/api/tags"],
              "source_hashes": [{"path": str(p.relative_to(rt.ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources]}
    rt.write_json(target / "engineering_verification.json", report)
    print(json.dumps({k: report[k] for k in ("scope", "tests_run", "success", "actual_experimental_model_calls")}))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
