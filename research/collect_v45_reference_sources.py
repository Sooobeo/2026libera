"""Archive public primary sources for schema-only revision; no model/API calls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'research/evidence/v45_structured_output_20261018'
SOURCES = {
    'finvector_2610_08882.pdf': 'https://arxiv.org/pdf/2610.08882',
    'ollama_structured_outputs.html': 'https://docs.ollama.com/capabilities/structured-outputs',
    'ollama_chat_api.html': 'https://docs.ollama.com/api/chat',
    'ollama_llama_server_v0351.go': 'https://raw.githubusercontent.com/ollama/ollama/v0.35.1/llm/llama_server.go',
    'ollama_structured_output_test_v0351.go': 'https://raw.githubusercontent.com/ollama/ollama/v0.35.1/integration/structured_output_test.go',
    'ollama_LLAMA_CPP_VERSION_v0351.txt': 'https://raw.githubusercontent.com/ollama/ollama/v0.35.1/LLAMA_CPP_VERSION',
    'ollama_llama_README_v0351.md': 'https://raw.githubusercontent.com/ollama/ollama/v0.35.1/llama/README.md',
    'ollama_llama_CMakeLists_v0351.txt': 'https://raw.githubusercontent.com/ollama/ollama/v0.35.1/llama/server/CMakeLists.txt',
    'ollama_compat_001_v0351.patch': 'https://raw.githubusercontent.com/ollama/ollama/v0.35.1/llama/compat/001-llama-cpp-hooks.patch',
    'ollama_compat_002_v0351.patch': 'https://raw.githubusercontent.com/ollama/ollama/v0.35.1/llama/compat/002-clef.patch',
    'llamacpp_grammar_README_b11232.md': 'https://raw.githubusercontent.com/ggml-org/llama.cpp/b11232/grammars/README.md',
    'llamacpp_json_schema_to_grammar_b11232.cpp': 'https://raw.githubusercontent.com/ggml-org/llama.cpp/b11232/common/json-schema-to-grammar.cpp',
    'llamacpp_schema_tests_b11232.cpp': 'https://raw.githubusercontent.com/ggml-org/llama.cpp/b11232/tests/test-json-schema-to-grammar.cpp',
}


def fetch(item):
    name, url = item
    request = urllib.request.Request(url, headers={'User-Agent': 'LIBERA-primary-reference-audit/1.0'})
    with urllib.request.urlopen(request, timeout=45) as response:
        if response.status != 200:
            raise RuntimeError('Unexpected HTTP status for ' + url)
        return name, url, response.read()


def main():
    if DEST.exists():
        raise FileExistsError('Preserve existing immutable reference snapshot')
    with ThreadPoolExecutor(max_workers=6) as pool:
        fetched = list(pool.map(fetch, SOURCES.items()))
    DEST.mkdir(parents=True)
    records = []
    for name, url, body in fetched:
        path = DEST / name
        path.write_bytes(body)
        records.append({'path': path.relative_to(ROOT).as_posix(), 'url': url,
                        'sha256': hashlib.sha256(body).hexdigest(), 'size_bytes': len(body)})
    manifest = {'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
                'scope': 'Primary public sources only; not model generation or local service access',
                'ollama_version_tag': 'v0.35.1', 'declared_upstream_llamacpp_ref': 'b11232',
                'records': records, 'model_calls': 0}
    (DEST / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'directory': str(DEST), 'sources': len(records), 'model_calls': 0}))


if __name__ == '__main__':
    main()
