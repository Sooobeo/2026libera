"""Native tokenizer integration/safety checks; never calls a model/server."""
import ctypes
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from sector_v491_tokenizer import NativeTokenizer, ModelParams

ROOT = Path(__file__).resolve().parent.parent


class NativeIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokenizer = NativeTokenizer()

    @classmethod
    def tearDownClass(cls):
        cls.tokenizer.close()

    def test_exact_native_abi_size_and_vocab_offset(self):
        self.assertEqual(ctypes.sizeof(ModelParams), 80)
        self.assertEqual(ModelParams.vocab_only.offset, 72)

    def test_special_chat_tokens_match_model_vocabulary(self):
        self.assertEqual(self.tokenizer.tokens("<|im_start|>"), [248045])
        self.assertEqual(self.tokenizer.tokens("<|im_end|>"), [248046])

    def test_no_implicit_bos_or_eos(self):
        self.assertFalse(self.tokenizer.add_bos)
        self.assertFalse(self.tokenizer.add_eos)
        self.assertEqual(self.tokenizer.tokens(""), [])

    def test_utf8_hash_uses_exact_korean_and_outer_whitespace(self):
        text = " \n한글 시장 및 투자 보고서\r\n "
        result = self.tokenizer.count(text)
        self.assertEqual(result["rendered_utf8_sha256"], hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual(result["rendered_utf8_bytes"], len(text.encode()))
        self.assertNotEqual(result["rendered_utf8_sha256"], self.tokenizer.count(text.strip())["rendered_utf8_sha256"])

    def test_embedded_nul_does_not_silently_truncate(self):
        self.assertGreater(len(self.tokenizer.tokens("hello\0 world after null")), len(self.tokenizer.tokens("hello")))

    def test_non_text_rejected(self):
        with self.assertRaises(TypeError):
            self.tokenizer.count({"content": "hello"})

    def test_unpaired_surrogate_rejected(self):
        with self.assertRaises(UnicodeEncodeError):
            self.tokenizer.count("\ud800")

    def test_repeated_count_same_id_hash(self):
        text = "<|im_start|>user\n{\"a\":0.1}\n<|im_end|>"
        self.assertEqual(self.tokenizer.count(text), self.tokenizer.count(text))

    def test_actual_old_render_matches_archived_provider_counter(self):
        base = ROOT / "data/local_sector_runtime/pilot_v48_guarded_20261019/fidelity_q2_2026__R1/stage1"
        if not base.exists():
            self.skipTest("Historical evidence not restored")
        rendered = (base / "render_only/rendered_prompt.txt").read_bytes().decode("utf-8")
        result = json.loads((base / "http_0001_generation/result.json").read_text(encoding="utf-8"))
        self.assertEqual(self.tokenizer.count(rendered)["token_count"], result["metrics"]["prompt_eval_count"])


class FailClosed(unittest.TestCase):
    def test_unrecognized_override_rejected(self):
        with self.assertRaises(ValueError):
            NativeTokenizer({"skip_hash_check": True})

    def test_model_with_wrong_bytes_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            fake = Path(temp) / "model.gguf"
            fake.write_bytes(b"not the pinned model")
            with self.assertRaisesRegex(RuntimeError, "GGUF content hash mismatch"):
                NativeTokenizer({"gguf_path": str(fake)})

    def test_library_with_wrong_bytes_rejected_before_loading(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "libllama.dll").write_bytes(b"not the pinned DLL")
            with self.assertRaisesRegex(RuntimeError, "Tokenizer binary pin mismatch"):
                NativeTokenizer({"library_dir": temp})


if __name__ == "__main__":
    unittest.main()
