"""Verify archived research evidence; optionally restore missing files only."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def restore(manifest_path, destination, write=False):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    archive_name = manifest["archive"]
    if Path(archive_name).name != archive_name:
        raise ValueError("Archive must be beside its manifest")
    archive = manifest_path.parent / archive_name
    if digest(archive.read_bytes()) != manifest["archive_sha256"]:
        raise ValueError("Archive checksum mismatch")
    destination = destination.resolve()
    entries = manifest["files"]
    names = [entry["path"] for entry in entries]
    if len(set(names)) != len(names):
        raise ValueError("Duplicate manifest paths")
    pending, conflicts = [], []
    with zipfile.ZipFile(archive) as bundle:
        if sorted(bundle.namelist()) != sorted(names):
            raise ValueError("Archive entries differ from manifest")
        # Validate every byte and destination before writing anything.
        for entry in entries:
            relative = PurePosixPath(entry["path"])
            if (relative.is_absolute() or ".." in relative.parts
                    or "\\" in entry["path"] or ":" in entry["path"]):
                raise ValueError("Unsafe archive path")
            target = destination.joinpath(*relative.parts)
            if not target.resolve().is_relative_to(destination):
                raise ValueError("Destination escapes workspace")
            data = bundle.read(entry["path"])
            if len(data) != entry["bytes"] or digest(data) != entry["sha256"]:
                raise ValueError(f"Evidence checksum mismatch: {relative}")
            if write:
                if target.exists():
                    if not target.is_file() or digest(target.read_bytes()) != entry["sha256"]:
                        conflicts.append(str(relative))
                else:
                    pending.append((entry["path"], target))
        if conflicts:
            raise ValueError("Existing files differ; nothing overwritten: " + ", ".join(conflicts))
        for name, target in pending:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as handle:
                handle.write(bundle.read(name))
    return {"verified_files": len(entries), "restored_files": len(pending),
            "archive_sha256": manifest["archive_sha256"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--restore", action="store_true", help="Restore missing files; never overwrite")
    parser.add_argument("--destination", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(restore(args.manifest, args.destination, args.restore), ensure_ascii=False))
