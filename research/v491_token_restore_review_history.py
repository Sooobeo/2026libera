"""Restore exact r1 code snapshots from the recorded, narrowly scoped r2 edits.

Every reconstructed byte sequence must match the r1 receipt before it is saved.
No reviewed input or original report is modified.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    report = json.loads((ROOT / "research/v491_token_review_20261019.json").read_text(encoding="utf-8"))
    target = ROOT / "research/evidence/v491_tokenizer_20261019/review_history_r1"
    target.mkdir(exist_ok=True)
    rows = []
    for ref in report["code"]:
        path = ROOT / ref["path"]
        existing_snapshot = target / path.name
        content = existing_snapshot.read_bytes() if existing_snapshot.is_file() else path.read_bytes()
        if path.name == "v491_token_capacity_audit.py":
            text = content.decode("utf-8")
            text = text.replace('    schema_ref = manifest["inputs"]["response_schema"]\n    schema_path = ROOT / schema_ref["path"]\n    if sha_file(schema_path) != schema_ref["sha256"]:\n        raise ValueError("Response schema hash mismatch")\n    schema = load(schema_path)\n', '')
            text = text.replace('"format": schema, "_debug_render_only": True}', '"_debug_render_only": True}')
            text = text.replace('                "structured_format_schema_sha256": schema_ref["sha256"],\n', '')
            content = text.encode("utf-8")
        elif path.name == "v491_token_review_finalize.py":
            text = content.decode("utf-8").replace('import argparse\n', '')
            text = text.replace('    parser = argparse.ArgumentParser()\n    parser.add_argument("--revision", default="r2", choices=["r2"])\n    parser.parse_args()\n', '')
            text = text.replace('d0_capacity_with_format/summary.json', 'd0_capacity/summary.json')
            text = text.replace('v491_tokenizer_evidence_20261019_r2.zip', 'v491_tokenizer_evidence_20261019.zip')
            text = text.replace('        "historical_render_only_calls_without_format": 8,\n        "review_history": "Original r1 counts remain preserved. r2 repeats all 8 exact render-only requests with the API format schema included, and is the current capacity receipt.",\n', '')
            text = text.replace('v491_token_review_20261019_r2.json', 'v491_token_review_20261019.json')
            content = text.encode("utf-8")
        observed = hashlib.sha256(content).hexdigest()
        if observed != ref["sha256"]:
            raise ValueError("Reconstructed snapshot does not match original receipt: " + path.name)
        output = target / path.name
        if output.exists() and output.read_bytes() != content:
            raise ValueError("Refusing to overwrite a different historical snapshot")
        output.write_bytes(content)
        rows.append({"original_path": ref["path"], "original_sha256": ref["sha256"],
                     "snapshot_path": output.relative_to(ROOT).as_posix(), "snapshot_sha256": observed,
                     "exact_original_bytes_recovered": True})
    (target / "snapshot_manifest.json").write_text(json.dumps({"historical_report": "research/v491_token_review_20261019.json",
        "recovery_method": "Exact inverse of the small recorded r2 patches; every restored byte hash matches the original r1 receipt",
        "files": rows}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"restored": len(rows), "all_original_hashes_match": True}))


if __name__ == "__main__":
    main()
