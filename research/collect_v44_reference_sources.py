"""Archive public primary implementation sources; no local service/model calls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "research/evidence/v44_primary_sources_20261018"
SOURCES = {
    "ollama_api_types_v0351.go": "https://raw.githubusercontent.com/ollama/ollama/v0.35.1/api/types.go",
    "ollama_server_routes_v0351.go": "https://raw.githubusercontent.com/ollama/ollama/v0.35.1/server/routes.go",
    "ollama_server_prompt_v0351.go": "https://raw.githubusercontent.com/ollama/ollama/v0.35.1/server/prompt.go",
    "ollama_llama_server_v0351.go": "https://raw.githubusercontent.com/ollama/ollama/v0.35.1/llm/llama_server.go",
    "finvector_public_inference_mlx.py": "https://raw.githubusercontent.com/alinakhay/FinVector-Market-4B/main/examples/inference_mlx.py",
    "mlx_lm_generate_v0313.py": "https://raw.githubusercontent.com/ml-explore/mlx-lm/v0.31.3/mlx_lm/generate.py",
}


def fetch(item):
    name, url = item
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "LIBERA-primary-reference-audit/1.0"}), timeout=45) as response:
        body = response.read()
        if response.status != 200:
            raise RuntimeError(f"Unexpected HTTP status: {url}")
    return name, url, body


def main():
    if DEST.exists():
        raise FileExistsError("Preserve the existing reference snapshot; choose a new dated directory to refresh")
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(fetch, SOURCES.items()))
    DEST.mkdir(parents=True)
    records = []
    for name, url, body in results:
        path = DEST / name
        path.write_bytes(body)
        records.append({"path": path.relative_to(ROOT).as_posix(), "url": url, "bytes": len(body),
                        "sha256": hashlib.sha256(body).hexdigest(), "line_count": len(body.splitlines())})
    manifest = {"observed_at_utc": datetime.now(timezone.utc).isoformat(), "scope": "Public primary code snapshot only; no model/service calls",
                "immutable_version_tags": ["ollama/v0.35.1", "mlx-lm/v0.31.3"],
                "mutable_source_note": "FinVector author example uses main; this saved content hash fixes the retrieved example, not the private benchmark runner.",
                "records": records}
    (DEST / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"directory": DEST.relative_to(ROOT).as_posix(), "source_count": len(records), "model_calls": 0}))


if __name__ == "__main__":
    main()
