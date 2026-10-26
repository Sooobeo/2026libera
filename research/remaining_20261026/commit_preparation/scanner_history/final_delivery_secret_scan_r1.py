"""Bounded, explicit-scope delivery scan. No extraction, network, model or Git calls.

Run only after the selected inputs are quiet. A clean result covers the recorded
bytes and patterns, not unknown secret formats or the whole repository.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import unittest
import zipfile

VERSION = "bounded_delivery_secret_scan_1"
MIB = 1024 * 1024
TEXT = {".py", ".ps1", ".json", ".jsonl", ".md", ".txt", ".csv", ".tsv",
        ".html", ".htm", ".css", ".js", ".mjs", ".ts", ".yaml", ".yml",
        ".toml", ".ini", ".cfg", ".xml", ".svg", ".log", ".rst", ".sh"}
BINARY = {".zip", ".gz", ".7z", ".pdf", ".png", ".jpg", ".jpeg", ".gif",
          ".webp", ".ico", ".woff", ".woff2", ".ttf", ".exe", ".dll",
          ".bin", ".gguf", ".pyc", ".docx", ".xlsx", ".pptx", ".mp4", ".mp3"}
RULES = [
    ("private_key_PEM", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"), 0),
    ("AWS_access_key_id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), 0),
    ("GitHub_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"), 0),
    ("OpenAI_style_token", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}\b"), 0),
    ("Slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"), 0),
    ("Google_API_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), 0),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), 0),
    ("authorization_bearer", re.compile(r"\bBearer\s+([A-Za-z0-9._~+/=-]{12,})", re.I), 1),
    ("quoted_credential_assignment", re.compile(
        r"\b(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|passwd|secret|authorization)"
        r"[\"']?\s*[:=]\s*([\"'])([^\"'\r\n]{8,})\2", re.I), 3),
    ("environment_credential_assignment", re.compile(
        r"\b(?:OPENAI_API_KEY|ANTHROPIC_API_KEY|AWS_SECRET_ACCESS_KEY|GITHUB_TOKEN|GH_TOKEN|SLACK_BOT_TOKEN)"
        r"\s*=\s*([A-Za-z0-9_./+~=-]{12,})"), 1),
    ("credential_in_URL", re.compile(
        r"\b(?:https?|mongodb(?:\+srv)?|postgres(?:ql)?|mysql)://[^\s/\"'<>:]+:[^\s/\"'<>@]+@[^\s\"'<>]+", re.I), 0),
    ("sensitive_URL_query", re.compile(
        r"\bhttps?://[^\s\"'<>]+[?&](?:access_token|refresh_token|api_key|apikey|token|secret|password|signature|sig|X-Amz-Signature|X-Amz-Credential)=[^&\s\"'<>]{8,}", re.I), 0),
]


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


class BoundaryError(ValueError):
    """Only fixed codes, never input values, may be used as messages."""


def safe_path(workspace, value, *, exists=True):
    p = Path(value)
    if ".." in p.parts:
        raise BoundaryError("parent_traversal_forbidden")
    p = p if p.is_absolute() else workspace / p
    if not p.absolute().is_relative_to(workspace):
        raise BoundaryError("path_outside_workspace")
    for part in (p, *p.parents):
        if part == workspace.parent:
            break
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise BoundaryError("symlink_or_reparse_point_forbidden")
    p = p.resolve()
    if not p.is_relative_to(workspace):
        raise BoundaryError("resolved_path_outside_workspace")
    if exists and not p.is_file():
        raise BoundaryError("explicit_regular_file_required")
    return p


def member_name(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\x00" in value:
        raise BoundaryError("unsafe_zip_member_name")
    p = PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts or p.as_posix() != value or value.endswith("/"):
        raise BoundaryError("unsafe_zip_member_name")
    return value


def stamp(path):
    s = path.stat()
    return s.st_size, s.st_mtime_ns, s.st_ino


def classify(kind, match, value):
    if re.fullmatch(r"(?:\$\{[A-Za-z_][A-Za-z0-9_]*\}|\$env:[A-Za-z_][A-Za-z0-9_]*|\[(?:REDACTED|MASKED)\]|<(?:TOKEN|SECRET|API_KEY|PASSWORD)>|YOUR_(?:TOKEN|SECRET|API_KEY|PASSWORD)(?:_HERE)?)", value, re.I):
        return "explicit_placeholder"
    if (kind == "quoted_credential_assignment" and match.group(1).lower() == "authorization"
            and re.search(r"\s", value)
            and re.search(r"user|approved|approval|requested|permission|delegat|사용자|요청|승인", value, re.I)
            and not re.search(r"[A-Za-z0-9_+/=-]{24,}|\b(?:Bearer|Basic)\s|\b(?:sk-|gh[pousr]_|github_pat_|xox[baprs]-|AKIA|ASIA)", value, re.I)):
        return "execution_authorization_prose"
    return "unresolved_requires_review"


class Scanner:
    def __init__(self, workspace, *, max_text_bytes=8*MIB, max_scan_bytes=64*MIB,
                 max_io_bytes=512*MIB, max_archive_bytes=512*MIB, max_entries=10000,
                 max_candidates=200):
        self.workspace = Path(workspace).resolve()
        self.limits = dict(max_text_bytes=max_text_bytes, max_scan_bytes=max_scan_bytes,
                           max_io_bytes=max_io_bytes, max_archive_bytes=max_archive_bytes,
                           max_entries=max_entries, max_candidates=max_candidates)
        if any(type(v) is not int or v <= 0 for v in self.limits.values()):
            raise BoundaryError("positive_integer_limits_required")
        self.io_bytes = self.scan_bytes = 0
        self.seen = set()
        self.file_hashes = {}
        self.report = {"version": VERSION, "started_at_utc": now(), "scope": "explicit_files_and_verified_zip_text_members",
                       "limits": self.limits, "covered_text": [], "excluded": [], "pending": [],
                       "candidates": [], "verified_archives": [], "control_refs": [],
                       "candidate_values_saved": False, "network_model_git_calls": 0, "extraction_performed": False}

    def label(self, path):
        return path.relative_to(self.workspace).as_posix()

    def chunked(self, stream, expected, *, retain=False):
        if type(expected) is not int or expected < 0 or self.io_bytes + expected > self.limits["max_io_bytes"]:
            raise BoundaryError("total_io_size_bound")
        digest, count, pieces = hashlib.sha256(), 0, []
        while True:
            data = stream.read(min(MIB, expected - count + 1))
            if not data:
                break
            count += len(data)
            self.io_bytes += len(data)
            if count > expected or self.io_bytes > self.limits["max_io_bytes"]:
                raise BoundaryError("stream_size_exceeds_declared_bound")
            digest.update(data)
            if retain:
                pieces.append(data)
        if count != expected:
            raise BoundaryError("stream_size_differs_from_declared_bytes")
        return digest.hexdigest(), b"".join(pieces) if retain else None

    def control(self, value):
        p = safe_path(self.workspace, value)
        before = stamp(p)
        if before[0] > 4*MIB:
            raise BoundaryError("control_json_size_bound")
        with p.open("rb") as handle:
            digest, data = self.chunked(handle, before[0], retain=True)
        if stamp(p) != before:
            raise BoundaryError("control_file_changed_during_read")
        self.report["control_refs"].append({"path": self.label(p), "sha256": digest})
        try:
            obj = json.loads(data.decode("utf-8-sig"))
        except (ValueError, UnicodeError):
            raise BoundaryError("invalid_control_json") from None
        self.file_text(p, data if len(data) <= self.limits["max_text_bytes"] else None,
                       digest, before[0])
        return p, obj

    def file_text(self, path, data, digest, length):
        label = self.label(path)
        if label in self.file_hashes:
            if self.file_hashes[label] != digest:
                raise BoundaryError("file_bytes_changed_between_explicit_uses")
            return
        self.file_hashes[label] = digest
        self.inspect_text({"path": label}, data, digest, length, suffix=path.suffix.lower())

    def inspect_text(self, origin, data, digest, length, *, suffix):
        row = {**origin, "sha256": digest, "bytes": length}
        if suffix in BINARY:
            self.report["excluded"].append({**row, "reason": "known_binary_extension_not_text_scanned"})
            return
        if data is None:
            self.report["pending"].append({**row, "reason": "text_or_unknown_file_exceeds_per_file_size_bound"})
            return
        try:
            content = data.decode("utf-8-sig")
            if "\x00" in content:
                raise UnicodeError()
        except UnicodeError:
            collection = "pending" if suffix in TEXT else "excluded"
            self.report[collection].append({**row, "reason": "declared_text_not_UTF8_or_contains_NUL" if suffix in TEXT else "binary_or_non_UTF8_unknown_type_not_text_scanned"})
            return
        if self.scan_bytes + length > self.limits["max_scan_bytes"]:
            self.report["pending"].append({**row, "reason": "total_text_scan_size_bound"})
            return
        self.scan_bytes += length
        candidate_ids = []
        for kind, regex, group in RULES:
            for match in regex.finditer(content):
                if len(self.report["candidates"]) >= self.limits["max_candidates"]:
                    self.report["pending"].append({**row, "reason": "candidate_count_bound_scan_incomplete"})
                    return
                value = match.group(group)
                item = {**origin, "id": "candidate_%04d" % (len(self.report["candidates"]) + 1),
                        "line": content.count("\n", 0, match.start()) + 1, "kind": kind,
                        "disposition": classify(kind, match, value), "value": "[REDACTED]"}
                self.report["candidates"].append(item)
                candidate_ids.append(item["id"])
        self.report["covered_text"].append({**row, "candidate_ids": candidate_ids})

    def file(self, value):
        p = safe_path(self.workspace, value)
        before = stamp(p)
        suffix = p.suffix.lower()
        retain = suffix not in BINARY and before[0] <= self.limits["max_text_bytes"]
        with p.open("rb") as handle:
            digest, data = self.chunked(handle, before[0], retain=retain)
        if stamp(p) != before:
            raise BoundaryError("input_file_changed_during_read")
        self.file_text(p, data, digest, before[0])

    def archive(self, value):
        manifest_path, manifest = self.control(value)
        if not isinstance(manifest, dict):
            raise BoundaryError("manifest_object_required")
        name, rows = manifest.get("archive"), manifest.get("files")
        if not isinstance(name, str) or Path(name).name != name or "/" in name or "\\" in name:
            raise BoundaryError("archive_basename_required")
        if not isinstance(rows, list) or not rows or len(rows) > self.limits["max_entries"]:
            raise BoundaryError("bounded_nonempty_manifest_entries_required")
        archive = safe_path(self.workspace, manifest_path.parent / name)
        if ("archive", str(archive)) in self.seen:
            raise BoundaryError("duplicate_archive_input")
        self.seen.add(("archive", str(archive)))
        expected = {}
        for row in rows:
            if (not isinstance(row, dict) or type(row.get("bytes")) is not int or row["bytes"] < 0
                    or not re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256", "")))):
                raise BoundaryError("invalid_manifest_member")
            member = member_name(row.get("path"))
            if member in expected:
                raise BoundaryError("duplicate_manifest_member")
            expected[member] = row
        if sum(r["bytes"] for r in rows) > self.limits["max_archive_bytes"]:
            raise BoundaryError("archive_uncompressed_size_bound")
        before = stamp(archive)
        if before[0] > self.limits["max_archive_bytes"]:
            raise BoundaryError("archive_container_size_bound")
        with archive.open("rb") as handle:
            digest, _ = self.chunked(handle, before[0])
        if digest != manifest.get("archive_sha256"):
            raise BoundaryError("archive_sha256_mismatch")
        # Do not scan any member until every member is byte-verified. Buffers are
        # discarded; a second bounded read below rehashes each scanned member.
        with zipfile.ZipFile(archive) as bundle:
            infos = bundle.infolist()
            if len(infos) != len(expected) or {i.filename for i in infos} != set(expected):
                raise BoundaryError("zip_manifest_membership_mismatch")
            for info in infos:
                member_name(info.filename)
                if info.flag_bits & 1 or stat.S_ISLNK(info.external_attr >> 16):
                    raise BoundaryError("encrypted_or_symlink_member_forbidden")
                row = expected[info.filename]
                if info.file_size != row["bytes"]:
                    raise BoundaryError("zip_declared_member_size_mismatch")
                with bundle.open(info) as handle:
                    member_digest, _ = self.chunked(handle, row["bytes"])
                if member_digest != row["sha256"]:
                    raise BoundaryError("zip_member_sha256_mismatch")
            for info in infos:
                row = expected[info.filename]
                suffix = PurePosixPath(info.filename).suffix.lower()
                retain = suffix not in BINARY and row["bytes"] <= self.limits["max_text_bytes"]
                if retain:
                    with bundle.open(info) as handle:
                        member_digest, data = self.chunked(handle, row["bytes"], retain=True)
                    if member_digest != row["sha256"]:
                        raise BoundaryError("zip_member_changed_between_verification_and_scan")
                else:
                    data = None
                self.inspect_text({"archive_path": self.label(archive), "member": info.filename},
                                  data, row["sha256"], row["bytes"], suffix=suffix)
        if stamp(archive) != before:
            raise BoundaryError("archive_changed_during_read")
        # A second container hash detects a same-size/mtime mutation as well.
        with archive.open("rb") as handle:
            after_digest, _ = self.chunked(handle, before[0])
        if after_digest != digest:
            raise BoundaryError("archive_bytes_changed_during_scan")
        self.report["verified_archives"].append({"manifest_path": self.label(manifest_path),
            "archive_path": self.label(archive), "archive_sha256": digest, "verified_members": len(rows)})

    def attempt(self, operation, value, ordinal):
        try:
            operation(value)
        except Exception as exc:
            self.report["pending"].append({"input_ordinal": ordinal,
                "reason": str(exc) if isinstance(exc, BoundaryError) else "input_operation_failed",
                "error_type": type(exc).__name__})

    def finish(self):
        unresolved = sum(c["disposition"] == "unresolved_requires_review" for c in self.report["candidates"])
        self.report.update(completed_at_utc=now(), io_bytes=self.io_bytes, scanned_text_bytes=self.scan_bytes,
            unresolved_candidates=unresolved,
            status="review_required" if unresolved else "pending_incomplete_scope" if self.report["pending"] else "no_unresolved_pattern_candidates_in_covered_text",
            limitations=["Bounded pattern scan does not prove all secret formats absent.",
                         "Binary/non-UTF8 exclusions are not secret-scanned; ZIP integrity is distinct from content scanning.",
                         "Only explicitly supplied current bytes are covered; no Git index, recursive dependency or whole-repository claim.",
                         "Public source URLs without credential syntax do not trigger a credential finding."])
        return self.report


def execute(workspace, files=(), lists=(), manifests=(), **limits):
    scanner = Scanner(workspace, **limits)
    selected = list(files)
    for i, listing in enumerate(lists):
        try:
            _, values = scanner.control(listing)
            if (not isinstance(values, list) or len(values) > scanner.limits["max_entries"]
                    or any(not isinstance(v, str) or not v for v in values)):
                raise BoundaryError("file_list_must_be_bounded_path_string_array")
            selected.extend(values)
        except Exception as exc:
            scanner.report["pending"].append({"list_ordinal": i,
                "reason": str(exc) if isinstance(exc, BoundaryError) else "file_list_read_failed",
                "error_type": type(exc).__name__})
    if not selected and not manifests:
        scanner.report["pending"].append({"reason": "no_explicit_inputs"})
    if len(selected) + len(manifests) > scanner.limits["max_entries"]:
        scanner.report["pending"].append({"reason": "explicit_input_count_bound"})
    else:
        for i, value in enumerate(selected):
            scanner.attempt(scanner.file, value, i)
        for i, value in enumerate(manifests):
            scanner.attempt(scanner.archive, value, i)
    return scanner.finish()


def self_test():
    class Checks(unittest.TestCase):
        def setUp(self):
            self.tmp = tempfile.TemporaryDirectory()
            self.root = Path(self.tmp.name)
        def tearDown(self):
            self.tmp.cleanup()
        def put(self, name, data):
            p = self.root / name
            p.write_bytes(data)
            return name
        def bundle(self, entries, rows=None):
            p = self.root / "bundle.zip"
            with zipfile.ZipFile(p, "w") as z:
                for k, v in entries.items():
                    z.writestr(k, v)
            data = {"archive": p.name, "archive_sha256": sha(p.read_bytes()),
                    "files": rows if rows is not None else [{"path": k, "bytes": len(v), "sha256": sha(v)} for k, v in entries.items()]}
            return self.put("manifest.json", json.dumps(data).encode())
        def test_detection_redaction_and_prose(self):
            token = "gh" + "p_" + "Ab3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY"
            p = self.put("sample.json", json.dumps({"authorization": "User approved this offline review.", "sample": token}).encode())
            r = execute(self.root, [p])
            self.assertEqual(r["status"], "review_required")
            self.assertTrue(any(c["disposition"] == "execution_authorization_prose" for c in r["candidates"]))
            self.assertTrue(any(c["kind"] == "GitHub_token" for c in r["candidates"]))
            self.assertNotIn(token, json.dumps(r))
            self.assertNotIn("User approved this offline review.", json.dumps(r))
        def test_binary_and_public_url(self):
            b = self.put("image.png", b"\x89PNG\x00\xff")
            t = self.put("source.txt", b"https://learn.microsoft.com/en-us/windows/")
            r = execute(self.root, [b, t])
            self.assertEqual(len(r["excluded"]), 1)
            self.assertEqual(len(r["covered_text"]), 1)
            self.assertEqual(r["unresolved_candidates"], 0)
        def test_text_size_bound_is_pending(self):
            p = self.put("large.txt", b"a" * 17)
            r = execute(self.root, [p], max_text_bytes=16)
            self.assertEqual(r["status"], "pending_incomplete_scope")
            self.assertEqual(r["covered_text"], [])
        def test_zip_integrity_membership_and_no_extraction(self):
            m = self.bundle({"nested/source.txt": b"public text", "image.png": b"\x00\xff"})
            r = execute(self.root, manifests=[m])
            self.assertEqual(len(r["verified_archives"]), 1)
            self.assertEqual(len(r["covered_text"]), 2)
            self.assertFalse((self.root / "nested").exists())
            obj = json.loads((self.root / m).read_text())
            obj["files"].pop()
            (self.root / m).write_text(json.dumps(obj))
            bad = execute(self.root, manifests=[m])
            self.assertEqual(bad["status"], "pending_incomplete_scope")
            self.assertFalse(any("member" in x for x in bad["covered_text"]))
        def test_unsafe_path_and_wrong_member_hash(self):
            m = self.bundle({"../escape.txt": b"x"})
            self.assertEqual(execute(self.root, manifests=[m])["status"], "pending_incomplete_scope")
            m = self.bundle({"ok.txt": b"x"}, [{"path": "ok.txt", "bytes": 1, "sha256": "0" * 64}])
            r = execute(self.root, manifests=[m])
            self.assertEqual(r["status"], "pending_incomplete_scope")
            self.assertFalse(any("member" in x for x in r["covered_text"]))
        def test_file_list_scope_and_output_free_error(self):
            self.put("chosen.txt", b"public")
            listing = self.put("list.json", b'["chosen.txt"]')
            r = execute(self.root, lists=[listing])
            self.assertEqual([x["path"] for x in r["covered_text"]], ["list.json", "chosen.txt"])
            bad = execute(self.root, ["../out.txt"])
            self.assertEqual(bad["status"], "pending_incomplete_scope")
            self.assertNotIn("out.txt", json.dumps(bad))
        def test_zip_secret_and_control_metadata_are_redacted(self):
            token = "sk" + "-" + "Ab3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY"
            m = self.bundle({"inner.txt": token.encode()})
            obj = json.loads((self.root / m).read_text())
            obj["note"] = token
            (self.root / m).write_text(json.dumps(obj))
            r = execute(self.root, [m], manifests=[m])
            self.assertEqual(r["status"], "review_required")
            self.assertEqual(len(r["verified_archives"]), 1)
            self.assertEqual(len(r["covered_text"]), 2)
            self.assertEqual(r["unresolved_candidates"], 2)
            self.assertNotIn(token, json.dumps(r))
        def test_zip_declared_size_bound_and_candidate_cap(self):
            m = self.bundle({"inner.txt": b"a" * 17})
            r = execute(self.root, manifests=[m], max_archive_bytes=16)
            self.assertEqual(r["status"], "pending_incomplete_scope")
            self.assertFalse(any("member" in x for x in r["covered_text"]))
            token = "gh" + "p_" + "Ab3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY"
            p = self.put("many.txt", (token + "\n" + token).encode())
            r = execute(self.root, [p], max_candidates=1)
            self.assertEqual(len(r["candidates"]), 1)
            self.assertTrue(r["pending"])
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
    return {"status": "PASS" if result.wasSuccessful() else "FAIL", "tests_run": result.testsRun,
            "failures": len(result.failures), "errors": len(result.errors), "actual_delivery_inputs_read": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--file", action="append", default=[])
    parser.add_argument("--file-list", action="append", default=[], help="JSON array of workspace-relative explicit paths")
    parser.add_argument("--zip-manifest", action="append", default=[], help="Exact ZIP manifest; ZIP and every member are independently byte-verified")
    parser.add_argument("--output", type=Path)
    for name, default in (("max-text-bytes", 8*MIB), ("max-scan-bytes", 64*MIB),
                          ("max-io-bytes", 512*MIB), ("max-archive-bytes", 512*MIB),
                          ("max-entries", 10000), ("max-candidates", 200)):
        parser.add_argument("--" + name, type=int, default=default)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result = self_test()
        print(json.dumps(result))
        return 0 if result["status"] == "PASS" else 1
    try:
        if args.output is None:
            raise BoundaryError("exclusive_output_required")
        output = safe_path(args.workspace.resolve(), args.output, exists=False)
        if output.exists():
            raise BoundaryError("output_already_exists")
        limits = {key: getattr(args, key) for key in ("max_text_bytes", "max_scan_bytes", "max_io_bytes", "max_archive_bytes", "max_entries", "max_candidates")}
        result = execute(args.workspace, args.file, args.file_list, args.zip_manifest, **limits)
        result["scanner_source_sha256"] = sha(Path(__file__).read_bytes())
        result["output_receipt_not_self_scanned"] = True
        encoded = (json.dumps(result, ensure_ascii=True, allow_nan=False, indent=2) + "\n").encode()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as handle:
            handle.write(encoded)
        print(json.dumps({"status": result["status"], "covered_text_files": len(result["covered_text"]),
                          "pending": len(result["pending"]), "unresolved_candidates": result["unresolved_candidates"],
                          "receipt_sha256": sha(encoded)}))
        return 2 if result["status"] == "review_required" else 3 if result["pending"] else 0
    except Exception as exc:
        print(json.dumps({"status": "scanner_failed_no_success_claim", "error_type": type(exc).__name__,
                          "reason": str(exc) if isinstance(exc, BoundaryError) else "operation_failed"}))
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
