"""Verify this reference package without requiring the original machine."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
manifest = json.loads((root / "자료목록.json").read_text(encoding="utf-8"))
errors = []
records = manifest["files"] + manifest["generated_files"]
for row in records:
    path = (root / row["copy"]).resolve()
    if not path.is_relative_to(root):
        errors.append({"path": row["copy"], "reason": "outside package"})
        continue
    if not path.is_file():
        errors.append({"path": row["copy"], "reason": "missing"})
        continue
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != row["sha256"] or path.stat().st_size != row["bytes"]:
        errors.append({"path": row["copy"], "reason": "bytes differ"})
result = {"status": "passed" if not errors else "failed", "source_copies": len(manifest["files"]), "generated_files": len(manifest["generated_files"]), "checked_files": len(records), "errors": errors}
(root / "검증결과.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
raise SystemExit(1 if errors else 0)
