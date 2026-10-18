"""Synthetic diagnostic-probe checks; never contact a model or download weights."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import probe_ollama_runtime as probe


class FakeSocket:
    def settimeout(self, seconds):
        assert seconds > 0


class FakeResponse:
    status = 200

    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.closed = False

    def getheaders(self):
        return [("Content-Type", "application/x-ndjson")]

    def readline(self):
        value = next(self.chunks, b"")
        if isinstance(value, BaseException):
            raise value
        return value

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, chunks):
        self.sock = FakeSocket()
        self.response = FakeResponse(chunks)
        self.requests = []
        self.closed = False

    def connect(self):
        pass

    def request(self, *args):
        self.requests.append(args)

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


def line(value):
    return json.dumps(value).encode() + b"\n"


class ProbeTests(unittest.TestCase):
    def capture(self, chunks):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        target = Path(temporary.name)
        conn = FakeConnection(chunks)
        with patch.object(probe, "connection", return_value=conn):
            result = probe.capture_stream("http://fake", {"synthetic": True}, target, 30)
        self.assertEqual(len(conn.requests), 1)
        self.assertTrue(conn.closed)
        self.assertTrue(conn.response.closed)
        return result, target

    def test_raw_stream_and_thinking_answer_times_remain_separate(self):
        chunks = [line({"message": {"thinking": "synthetic"}}),
                  line({"message": {"content": '{"ok":true}'}}),
                  line({"done": True, "done_reason": "stop", "eval_count": 20, "eval_duration": 2000000000})]
        result, target = self.capture(chunks)
        self.assertEqual((target / "raw_stream.ndjson").read_bytes(), b"".join(chunks))
        self.assertEqual(result["status"], "completed_generation")
        self.assertLessEqual(result["first_thinking_chunk_seconds"], result["first_answer_chunk_seconds"])
        self.assertEqual(probe.metrics(result)["generation_tokens_per_second"], 10)

    def test_timeout_and_cancellation_keep_partial_but_no_invented_rate(self):
        chunk = line({"message": {"thinking": "partial"}})
        for failure, status in [(TimeoutError("synthetic deadline"), "timeout"), (KeyboardInterrupt(), "cancelled")]:
            result, target = self.capture([chunk, failure])
            self.assertEqual(result["status"], status)
            self.assertEqual(result["message"]["thinking"], "partial")
            self.assertEqual((target / "raw_stream.ndjson").read_bytes(), chunk)
            self.assertIsNone(probe.metrics(result)["generation_tokens_per_second"])

    def test_output_limit_is_not_completed_generation(self):
        result, _ = self.capture([line({"message": {"thinking": "only thinking"}, "done": True,
                                       "done_reason": "length", "eval_count": 256, "eval_duration": 1000000000})])
        self.assertEqual(result["status"], "output_limit_reached")
        self.assertEqual(result["answer_character_count"], 0)

    def test_cancel_control_file_is_observed_during_blocked_stream(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            (target / "CANCEL").touch()
            conn = FakeConnection([line({"message": {"thinking": "partial"}})])
            original = conn.response.readline
            def slow_read():
                time.sleep(0.15)
                return original()
            conn.response.readline = slow_read
            with patch.object(probe, "connection", return_value=conn):
                result = probe.capture_stream("http://fake", {}, target, 30)
            self.assertEqual(result["status"], "cancelled")
            self.assertEqual(len(conn.requests), 1)
            self.assertTrue((target / "raw_stream.ndjson").exists())

    def test_eof_without_terminal_is_censored(self):
        result, _ = self.capture([line({"message": {"content": "partial"}})])
        self.assertEqual(result["status"], "incomplete_stream")
        self.assertTrue(probe.metrics(result)["censored_without_terminal_response"])

    def test_request_preserves_exact_public_stage_and_separates_health_cap(self):
        request, _, _ = probe.build_request("stage1", "qwen3.6:35b", 131072, "0")
        template = json.loads(probe.PILOT_TEMPLATE.read_text(encoding="utf-8-sig"))
        self.assertEqual(request["messages"][1], template["stages"][0])
        self.assertEqual(request["messages"][0]["content"], template["system"])
        self.assertEqual(request["options"]["num_predict"], 8192)
        health, _, _ = probe.build_request("health", "qwen3.6:35b", 8192, "0")
        self.assertEqual(health["options"]["num_predict"], 256)
        with self.assertRaises(ValueError):
            probe.build_request("stage1", "qwen3.6:35b", 8192, "0")

    def test_output_directory_new_only_and_no_traversal(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(probe, "OUTPUT_ROOT", Path(temporary)):
            probe.new_directory("unique")
            with self.assertRaises(FileExistsError):
                probe.new_directory("unique")
            with self.assertRaises(ValueError):
                probe.new_directory("../escape")

    def test_cached_prompt_rate_and_missing_metrics_are_distinct(self):
        result = {"terminal_response": {"prompt_eval_count": 100, "prompt_eval_cached_count": 80,
                                        "prompt_eval_duration": 1000000000}}
        computed = probe.metrics(result)
        self.assertEqual(computed["prompt_reported_tokens_per_second"], 100)
        self.assertEqual(computed["uncached_prompt_tokens_per_second"], 20)
        self.assertIsNone(computed["generation_tokens_per_second"])

    def test_process_collection_allowlist_excludes_unrelated_names(self):
        for name in ("ollama.exe", "OLLAMA.EXE", "ollama app.exe", "llama-server.exe", "ollama_llama_server.exe"):
            self.assertTrue(probe.is_runtime_process(name))
        for name in (None, "", "python.exe", "chrome.exe", "my_ollama_backup.exe", "not-llama-server.exe"):
            self.assertFalse(probe.is_runtime_process(name))


if __name__ == "__main__":
    unittest.main()
