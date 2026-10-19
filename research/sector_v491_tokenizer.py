"""Exact native tokenizer for the installed, pinned Ollama 0.35.1 GGUF.

Loads vocabulary only through the very libllama DLL shipped with the runner.
No inference context, tensor weights, backend initialization, HTTP or generation.
The ABI is pinned to llama.cpp 6f767fe96/include/llama.h. This module deliberately
fails closed for other binaries/models; updating an installation requires review.
"""
from __future__ import annotations

import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import struct

VERSION = "v491_native_vocab_only_1"
COMMIT = "6f767fe96"
MODEL_DIGEST = "d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04"
GGUF_SHA256 = "a9d0a3e1d8c91732a3812becd31f8d4a8ff57414903f226306069f0437e2ac50"
TEMPLATE_SHA256 = "b507b9c2f6ca642bffcd06665ea7c91f235fd32daeefdf875a0f938db05fb315"
LIBRARY_HASHES = {
    "libllama.dll": "0335cae1bc3429fd8fe2a98f02777653d6680380a5e5698c514e6c928d36abb3",
    "ggml-base.dll": "b385871a358e2a1e750921b0233b5bb73c32b4dda9ee2a64cba2d853d3efd4ae",
    "ggml.dll": "ebe3ffe406e27d08c8e34d1d8e49ee62e007b761ea126b49c04096106ef078b9",
}


class ModelParams(C.Structure):
    # Exact declaration from the pinned official header, Windows AMD64 ABI.
    _fields_ = [("devices", C.c_void_p), ("tensor_buft_overrides", C.c_void_p),
                ("n_gpu_layers", C.c_int32), ("split_mode", C.c_int),
                ("load_mode", C.c_int), ("lazy_mode", C.c_int),
                ("main_gpu", C.c_int32), ("tensor_split", C.c_void_p),
                ("progress_callback", C.c_void_p),
                ("progress_callback_user_data", C.c_void_p),
                ("kv_overrides", C.c_void_p), ("vocab_only", C.c_bool),
                ("check_tensors", C.c_bool), ("use_extra_bufts", C.c_bool),
                ("no_host", C.c_bool), ("no_alloc", C.c_bool),
                ("load_mtp", C.c_bool)]


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


class NativeTokenizer:
    def __init__(self, tokenizer_config=None):
        config = tokenizer_config or {}
        if not isinstance(config, dict) or set(config) - {"library_dir", "gguf_path"}:
            raise ValueError("Only library_dir and gguf_path tokenizer overrides are accepted")
        if os.name != "nt" or C.sizeof(C.c_void_p) != 8 or C.sizeof(ModelParams) != 80:
            raise RuntimeError("Tokenizer ABI is pinned to Windows AMD64, 80-byte model params")
        libdir = Path(config.get("library_dir", Path(os.environ["LOCALAPPDATA"]) /
                                 "Programs/Ollama/lib/ollama")).resolve()
        gguf = Path(config.get("gguf_path", Path.home() / ".ollama/models/blobs" /
                               ("sha256-" + GGUF_SHA256))).resolve()
        self.hashes = {}
        for name, expected in LIBRARY_HASHES.items():
            observed = sha_file(libdir / name)
            if observed != expected:
                raise RuntimeError("Tokenizer binary pin mismatch: " + name)
            self.hashes[name] = observed
        if sha_file(gguf) != GGUF_SHA256:
            raise RuntimeError("GGUF content hash mismatch")
        self.dll_directory = os.add_dll_directory(str(libdir))
        self.dll = C.CDLL(str(libdir / "libllama.dll"))
        self.dll.llama_model_default_params.argtypes = []
        self.dll.llama_model_default_params.restype = ModelParams
        self.dll.llama_model_load_from_file.argtypes = [C.c_char_p, ModelParams]
        self.dll.llama_model_load_from_file.restype = C.c_void_p
        self.dll.llama_model_free.argtypes = [C.c_void_p]
        self.dll.llama_model_free.restype = None
        self.dll.llama_model_get_vocab.argtypes = [C.c_void_p]
        self.dll.llama_model_get_vocab.restype = C.c_void_p
        self.dll.llama_vocab_n_tokens.argtypes = [C.c_void_p]
        self.dll.llama_vocab_n_tokens.restype = C.c_int32
        for name in ["llama_vocab_get_add_bos", "llama_vocab_get_add_eos"]:
            getattr(self.dll, name).argtypes = [C.c_void_p]
            getattr(self.dll, name).restype = C.c_bool
        self.dll.llama_tokenize.argtypes = [C.c_void_p, C.c_char_p, C.c_int32,
                                           C.POINTER(C.c_int32), C.c_int32,
                                           C.c_bool, C.c_bool]
        self.dll.llama_tokenize.restype = C.c_int32
        params = self.dll.llama_model_default_params()
        params.vocab_only = True
        params.n_gpu_layers = 0
        params.use_extra_bufts = False
        # Do not call llama_backend_init or create any inference context.
        self.model = self.dll.llama_model_load_from_file(str(gguf).encode("utf-8"), params)
        if not self.model:
            raise RuntimeError("Pinned GGUF vocabulary load failed")
        self.vocab = self.dll.llama_model_get_vocab(self.model)
        self.vocab_size = int(self.dll.llama_vocab_n_tokens(self.vocab))
        self.add_bos = bool(self.dll.llama_vocab_get_add_bos(self.vocab))
        self.add_eos = bool(self.dll.llama_vocab_get_add_eos(self.vocab))
        self.gguf_path = str(gguf)
        self.library_dir = str(libdir)
        if self.vocab_size != 248320 or self.add_bos or self.add_eos:
            self.close()
            raise RuntimeError("Unexpected pinned Qwen tokenizer metadata")

    def tokens(self, text):
        if not isinstance(text, str):
            raise TypeError("rendered_text must be an exact string")
        raw = text.encode("utf-8", "strict")
        if len(raw) > 2**31 - 1:
            raise ValueError("Input exceeds native API length")
        # server-context.cpp handle_completions_impl calls true,true (special
        # additions enabled, special-token parsing enabled). This GGUF adds no BOS/EOS.
        size = self.dll.llama_tokenize(self.vocab, raw, len(raw), None, 0, True, True)
        if size > 0:
            raise RuntimeError("Unexpected tokenizer allocation response")
        if size == 0:
            return []
        buffer = (C.c_int32 * -size)()
        count = self.dll.llama_tokenize(self.vocab, raw, len(raw), buffer, -size, True, True)
        if count != -size:
            raise RuntimeError("Native token sizing and count disagree")
        return list(buffer)

    def count(self, rendered_text):
        token_ids = self.tokens(rendered_text)
        raw = rendered_text.encode("utf-8")
        return {"tokenizer_version": VERSION, "token_count": len(token_ids),
                "method": "exact_installed_libllama_vocab_only",
                "rendered_utf8_sha256": hashlib.sha256(raw).hexdigest(),
                "rendered_utf8_bytes": len(raw),
                "token_ids_sha256": hashlib.sha256(struct.pack("<" + "i" * len(token_ids), *token_ids)).hexdigest(),
                "token_ids_hash_encoding": "little_endian_signed_int32",
                "model_digest": MODEL_DIGEST, "gguf_sha256": GGUF_SHA256,
                "template_sha256": TEMPLATE_SHA256, "library_hashes": self.hashes,
                "manifest_template_scope": "Expected runtime pins; this tokenizer verifies GGUF and native-library bytes. The caller must independently verify the live model manifest/template and rendered text.",
                "llama_cpp_commit": COMMIT, "vocabulary_size": self.vocab_size,
                "add_special": True, "parse_special": True,
                "model_add_bos": self.add_bos, "model_add_eos": self.add_eos,
                "vocab_only": True, "inference_context_created": False,
                "generation_calls": 0, "tensor_weights_loaded": False,
                "limitation": "Exact tokens for the supplied rendered text; renderer equality, context allocation and runtime memory require separate checks."}

    def close(self):
        if getattr(self, "model", None):
            self.dll.llama_model_free(self.model)
            self.model = None
        if getattr(self, "dll_directory", None):
            self.dll_directory.close()
            self.dll_directory = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def count_rendered_tokens(rendered_text, tokenizer_config=None):
    """Fail-closed exact count; intended once per runtime worker before generation."""
    with NativeTokenizer(tokenizer_config) as tokenizer:
        return tokenizer.count(rendered_text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rendered-text", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    # read_text() applies universal-newline translation; rendered bytes must stay exact.
    result = count_rendered_tokens(args.rendered_text.read_bytes().decode("utf-8"))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
