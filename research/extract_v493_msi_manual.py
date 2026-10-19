"""Extract the pinned LibreOffice MSI as data, without installing a product.

No msiexec, install action, registry change, service control, or model call.
The input MSI is copied to an isolated work directory before read-only access.
This does not guarantee that msi.dll will succeed while another installation is
running. A failure is recorded and is never retried by this helper.

Primary API/layout references:
https://learn.microsoft.com/en-us/windows/win32/api/msiquery/nf-msiquery-msiopendatabasew
https://learn.microsoft.com/en-us/windows/win32/api/msiquery/nf-msiquery-msirecordreadstream
https://learn.microsoft.com/en-us/windows/win32/msi/using-the-directory-table
https://learn.microsoft.com/en-us/windows/win32/msi/media-table
https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/expand
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import shutil
import subprocess
import sys

EXPECTED_SHA = "c6298b10cfa1748bcbedad94c62ce771e240e5021bfd6d7a967cd571b04b5312"
TASK_ROOT = Path("C:/Users/Insun/AppData/Local/Temp/libera_v493_render_20261019")
DEFAULT_MSI = TASK_ROOT / "LibreOffice_26.8.1_Win_x86-64.msi"
DEFAULT_WORK = TASK_ROOT / "portable_manual"


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(value):
    if (not value or value in {".", ".."} or
            any(c in value for c in '\\/:*?"<>|\x00') or
            value.endswith((" ", ".")) or PureWindowsPath(value).is_absolute()):
        raise ValueError(f"Unsafe path component: {value!r}")
    return value


def target_name(value):
    # MSI DefaultDir uses target:source and short|long syntax.
    target = value.split(":", 1)[0].split("|")[-1]
    return "" if target == "." else safe_name(target)


def directory_paths(rows):
    table = {r[0]: (r[1], r[2]) for r in rows}
    if len(table) != len(rows):
        raise ValueError("Duplicate directory identifiers")
    resolved = {}

    def resolve(key, stack=()):
        if key in resolved:
            return resolved[key]
        if key in stack:
            raise ValueError("Cyclic directory table")
        parent, default = table[key]
        if not parent:
            result = ()  # Every installation root stays inside our local tree.
        else:
            base = resolve(parent, stack + (key,))
            name = target_name(default)
            result = base + ((name,) if name else ())
        resolved[key] = result
        return result

    for key in table:
        resolve(key)
    return resolved


class MsiDatabase:
    def __init__(self, path):
        self.dll = ctypes.WinDLL("msi.dll")
        uint = ctypes.c_uint
        uintp = ctypes.POINTER(uint)
        definitions = {
            "MsiOpenDatabaseW": ([ctypes.c_wchar_p, ctypes.c_void_p, uintp], uint),
            "MsiDatabaseOpenViewW": ([uint, ctypes.c_wchar_p, uintp], uint),
            "MsiViewExecute": ([uint, uint], uint),
            "MsiViewFetch": ([uint, uintp], uint),
            "MsiRecordGetStringW": ([uint, uint, ctypes.c_wchar_p, uintp], uint),
            "MsiRecordReadStream": ([uint, uint, ctypes.c_void_p, uintp], uint),
            "MsiCloseHandle": ([uint], uint),
        }
        for name, (args, result) in definitions.items():
            fn = getattr(self.dll, name)
            fn.argtypes, fn.restype = args, result
        self.handle = uint()
        # MSIDBOPEN_READONLY == 0. Never invoke MsiInstallProduct/DoAction.
        self.check(self.dll.MsiOpenDatabaseW(str(path), None,
                                           ctypes.byref(self.handle)), "open read-only")

    @staticmethod
    def check(code, operation):
        if code:
            raise OSError(code, f"Windows Installer data API: {operation}")

    def close(self):
        if self.handle.value:
            self.dll.MsiCloseHandle(self.handle)
            self.handle.value = 0

    def records(self, sql):
        view = ctypes.c_uint()
        self.check(self.dll.MsiDatabaseOpenViewW(self.handle, sql,
                                               ctypes.byref(view)), "open view")
        try:
            self.check(self.dll.MsiViewExecute(view, 0), "execute SELECT")
            while True:
                record = ctypes.c_uint()
                result = self.dll.MsiViewFetch(view, ctypes.byref(record))
                if result == 259:  # ERROR_NO_MORE_ITEMS
                    break
                self.check(result, "fetch")
                try:
                    yield record
                finally:
                    self.dll.MsiCloseHandle(record)
        finally:
            self.dll.MsiCloseHandle(view)

    def string(self, record, field):
        count = ctypes.c_uint(0)
        code = self.dll.MsiRecordGetStringW(record, field, None, ctypes.byref(count))
        if code not in (0, 234):
            self.check(code, "string length")
        buffer = ctypes.create_unicode_buffer(count.value + 1)
        count.value += 1
        self.check(self.dll.MsiRecordGetStringW(record, field, buffer,
                                              ctypes.byref(count)), "string")
        return buffer.value

    def table(self, table, columns):
        query = "SELECT " + ", ".join(f"`{c}`" for c in columns) + f" FROM `{table}`"
        return [[self.string(record, i + 1) for i in range(len(columns))]
                for record in self.records(query)]

    def save_stream(self, name, path):
        escaped = name.replace("'", "''")
        found = 0
        for record in self.records(f"SELECT `Data` FROM `_Streams` WHERE `Name`='{escaped}'"):
            found += 1
            if found != 1:
                raise ValueError("Duplicate CAB stream")
            with path.open("xb") as output:
                buffer = ctypes.create_string_buffer(1024 * 1024)
                while True:
                    count = ctypes.c_uint(len(buffer))
                    self.check(self.dll.MsiRecordReadStream(record, 1, buffer,
                                                           ctypes.byref(count)), "read CAB")
                    if not count.value:
                        break
                    output.write(buffer.raw[:count.value])
        if found != 1:
            raise ValueError(f"Embedded CAB stream missing: {name}")
        with path.open("rb") as source:
            if source.read(4) != b"MSCF":
                raise ValueError("Invalid CAB header")


def write_receipt(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def run(args):
    msi = args.msi.resolve(strict=True)
    work = args.work.resolve()
    allowed = TASK_ROOT.resolve()
    if not work.is_relative_to(allowed) or work == allowed or work.exists():
        raise ValueError("Work path must be a NEW child of the named task TEMP directory")
    if sha(msi) != EXPECTED_SHA:
        raise ValueError("Official MSI SHA256 mismatch")
    work.mkdir()
    receipt = {"started_at_utc": now(), "status": "starting",
               "operation": args.mode, "source_msi": str(msi), "source_sha256": EXPECTED_SHA,
               "work_directory": str(work), "system_installation_performed": False,
               "other_processes_touched": False, "model_calls": 0,
               "read_only_database": True, "retry_count": 0}
    receipt_path = work / "manual_extraction_receipt.json"
    write_receipt(receipt_path, receipt)
    database = None
    try:
        isolated_msi = work / "source_copy.msi"
        shutil.copyfile(msi, isolated_msi)
        if sha(isolated_msi) != EXPECTED_SHA:
            raise ValueError("Copied MSI hash mismatch")
        database = MsiDatabase(isolated_msi)
        media = database.table("Media", ["DiskId", "LastSequence", "Cabinet"])
        directories = database.table("Directory", ["Directory", "Directory_Parent", "DefaultDir"])
        components = database.table("Component", ["Component", "Directory_"])
        files = database.table("File", ["File", "Component_", "FileName", "FileSize", "Sequence"])
        paths = directory_paths(directories)
        component_dirs = dict(components)
        mappings = []
        for key, component, filename, size, sequence in files:
            key = safe_name(key)
            name = safe_name(filename.split("|")[-1])
            target = paths[component_dirs[component]] + (name,)
            mappings.append({"file_key": key, "relative_path": "/".join(target),
                             "expected_size": int(size), "sequence": int(sequence)})
        cabins = sorted(media, key=lambda row: int(row[0]))
        if not cabins or any(not row[2].startswith("#") for row in cabins):
            raise ValueError("Only embedded-CAB media are supported")
        receipt.update({"status": "read_only_inventory_complete", "files": len(files),
                        "total_uncompressed_file_bytes": sum(x["expected_size"] for x in mappings),
                        "media": media, "directory_rows": len(directories),
                        "soffice_candidates": [m for m in mappings if m["relative_path"].endswith("/program/soffice.com") or m["relative_path"].endswith("/program/soffice.exe")]})
        write_receipt(work / "file_mapping.json", mappings)
        write_receipt(work / "directory_table.json", directories)
        write_receipt(receipt_path, receipt)
        if args.mode == "inspect":
            return receipt
        cabinet_dir = work / "cabinets"
        raw_dir = work / "cab_files"
        tree = work / "tree"
        for folder in (cabinet_dir, raw_dir, tree):
            folder.mkdir()
        for disk, last_sequence, cabinet in cabins:
            name = safe_name(cabinet[1:])
            database.save_stream(name, cabinet_dir / name)
        database.close()
        database = None
        expand = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/expand.exe"
        if not expand.is_file():
            raise FileNotFoundError(expand)
        receipt["expansions"] = []
        for disk, last_sequence, cabinet in cabins:
            command = [str(expand), str(cabinet_dir / cabinet[1:]), "-F:*", str(raw_dir)]
            with (work / f"expand_disk_{int(disk)}.log").open("wb") as log:
                result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=600,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            receipt["expansions"].append({"disk": int(disk), "exit_code": result.returncode})
            write_receipt(receipt_path, receipt)
            if result.returncode:
                raise RuntimeError(f"CAB expansion failed for disk {disk}: {result.returncode}")
        # CAB members use the MSI File key. No installer actions are executed.
        raw_index = {}
        for item in raw_dir.rglob("*"):
            if item.is_file():
                if item.name.casefold() in raw_index:
                    raise ValueError("Duplicate expanded CAB member")
                raw_index[item.name.casefold()] = item
        verified = 0
        for mapping in mappings:
            source = raw_index.get(mapping["file_key"].casefold())
            if source is None or source.stat().st_size != mapping["expected_size"]:
                raise ValueError(f"Missing or wrong-size CAB file: {mapping['file_key']}")
            target = tree.joinpath(*mapping["relative_path"].split("/"))
            if not target.resolve().is_relative_to(tree.resolve()):
                raise ValueError("Target escaped extraction tree")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if sha(target) != sha(source):
                    raise ValueError(f"Conflicting target path: {target}")
            else:
                shutil.copyfile(source, target)
            verified += 1
        executables = list(tree.rglob("soffice.com"))
        if len(executables) != 1:
            raise ValueError(f"Expected one soffice.com, found {len(executables)}")
        receipt.update({"status": "files_extracted_and_sizes_verified",
                        "mapped_files_verified": verified, "soffice_com": str(executables[0]),
                        "soffice_exe": str(executables[0].with_suffix(".exe")),
                        "engine_execution_tested": False, "rendering_tested": False})
        return receipt
    except BaseException as error:
        receipt.update({"status": "failed_no_retry", "error": repr(error)})
        raise
    finally:
        if database is not None:
            database.close()
        receipt["finished_at_utc"] = now()
        write_receipt(receipt_path, receipt)


def self_test():
    assert directory_paths([("ROOT", "", "SourceDir"), ("APP", "ROOT", "SHORT|LibreOffice"),
                            ("BIN", "APP", ".:source"), ("P", "BIN", "program")])["P"] == ("LibreOffice", "program")
    for bad in ("..", "a/b", "a\\b", "C:evil", "bad.", "x\x00y"):
        try:
            safe_name(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(bad)
    try:
        directory_paths([("A", "B", "a"), ("B", "A", "b")])
    except ValueError:
        pass
    else:
        raise AssertionError("Cycle accepted")
    print(json.dumps({"status": "pure_path_safety_checks_passed", "MSI_API_calls": 0,
                      "extraction_calls": 0, "installation_calls": 0}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["inspect", "extract", "self-test"])
    parser.add_argument("--msi", type=Path, default=DEFAULT_MSI)
    parser.add_argument("--work", type=Path, default=DEFAULT_WORK)
    args = parser.parse_args()
    if args.mode == "self-test":
        self_test()
    else:
        print(json.dumps(run(args), ensure_ascii=False, indent=2))
