#!/usr/bin/env python3
"""Inventory Git-ignored remote data; create missing empty files in a local clone.

Python 3.9+, standard library only. Neither command reads dataset file contents.
Run --help, or see README.md beside this script.
"""

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile


FORMAT = "dataset-shadow-v1"
MARKER = ".dataset-shadow-local"


def git(root, *args, input_bytes=None, allowed=(0,)):
    result = subprocess.run(
        ["git", "-C", str(root), *args], input=input_bytes,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode not in allowed:
        raise ValueError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def repo_root(path):
    root = Path(path).resolve(strict=True)
    actual = Path(os.fsdecode(git(root, "rev-parse", "--show-toplevel")).strip()).resolve()
    if root != actual:
        raise ValueError("--root must name the Git repository root: " + str(actual))
    return root


def relative_parts(name):
    if not isinstance(name, str) or not name or "\\" in name or "\0" in name:
        raise ValueError("Invalid repository-relative path: " + repr(name))
    parts = name.split("/")
    if any(p in ("", ".", "..") or p.casefold() == ".git" for p in parts):
        raise ValueError("Unsafe repository-relative path: " + repr(name))
    if ":" in parts[0]:
        raise ValueError("Drive-qualified path is not allowed: " + repr(name))
    return parts


def safe_path(root, name):
    parts = relative_parts(name)
    if os.name == "nt":
        reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
        reserved |= {prefix + str(i) for prefix in ("COM", "LPT") for i in range(1, 10)}
        for part in parts:
            if (any(c in '<>:"|?*' or ord(c) < 32 for c in part)
                    or part.endswith((".", " "))
                    or part.split(".")[0].upper() in reserved):
                raise ValueError("Filename cannot be recreated on Windows: " + repr(name))
    target = root.joinpath(*parts)
    target.resolve().relative_to(root)
    return target


def ignored(root, names):
    if not names:
        return set()
    payload = b"".join(os.fsencode(name) + b"\0" for name in names)
    output = git(root, "check-ignore", "--stdin", "-z", input_bytes=payload, allowed=(0, 1))
    return {os.fsdecode(p) for p in output.split(b"\0") if p}


def read_manifest(path):
    with path.open(encoding="utf-8") as handle:
        header = json.loads(handle.readline())
        if not isinstance(header, dict) or header.get("format") != FORMAT:
            raise ValueError("Not a dataset-shadow manifest: " + str(path))
        records = [json.loads(line) for line in handle if line.strip()]
        if any(not isinstance(record, dict) for record in records):
            raise ValueError("Invalid record in dataset-shadow manifest: " + str(path))
    return header, records


def export(args, root, manifest):
    if (root / MARKER).exists():
        raise ValueError("This clone contains local shadows. Export only on the real-data server.")
    manifest_name = manifest.relative_to(root).as_posix()
    if manifest_name in ignored(root, [manifest_name]):
        raise ValueError("The manifest must be outside ignored directories so Git can sync it.")
    if manifest.exists():
        read_manifest(manifest)  # Refuse to overwrite an unrelated existing file.
    scopes = args.scope or ["."]
    for scope in scopes:
        if scope != ".":
            safe_path(root, scope)
    raw = git(root, "ls-files", "--others", "--ignored", "--exclude-standard", "-z", "--", *scopes)
    paths = sorted({os.fsdecode(p) for p in raw.split(b"\0") if p})
    manifest.parent.mkdir(parents=True, exist_ok=True)
    count = total = links = 0
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=manifest.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps({"format": FORMAT, "source_root": str(root),
                                     "scopes": scopes}) + "\n")
            for name in paths:
                if name in (manifest_name, MARKER):
                    continue
                parts = relative_parts(name)
                path = root.joinpath(*parts)
                info = path.lstat()
                record = {"path": name, "size_bytes": info.st_size,
                          "mtime_ns": info.st_mtime_ns}
                if stat.S_ISLNK(info.st_mode):
                    record.update(kind="symlink", target=os.readlink(path))
                    links += 1
                elif stat.S_ISREG(info.st_mode):
                    record["kind"] = "file"
                    count += 1
                    total += info.st_size
                else:
                    continue
                handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        temporary.replace(manifest)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    print(f"Exported {count:,} files ({total:,} bytes) and {links:,} symlinks to {manifest}")
    print("Only metadata was read; real data files were not changed.")


def materialize(args, root, manifest):
    header, records = read_manifest(manifest)
    if str(root) == header.get("source_root"):
        raise ValueError("Destination equals the recorded server path. Use a separate local clone.")
    files = [r for r in records if r.get("kind") == "file"]
    planned = []
    keys = set()
    for record in files:
        name = record["path"]
        if type(record.get("size_bytes")) is not int or record["size_bytes"] < 0:
            raise ValueError("Invalid original file size for " + repr(name))
        path = safe_path(root, name)
        key = os.path.normcase(str(path))
        if key in keys:
            raise ValueError("Duplicate or case-colliding file path: " + repr(name))
        keys.add(key)
        planned.append((name, path))
    names = [name for name, _ in planned] + [MARKER]
    not_ignored = set(names) - ignored(root, names)
    if not_ignored:
        examples = ", ".join(repr(p) for p in sorted(not_ignored)[:5])
        raise ValueError("Refusing non-ignored or tracked paths. Update .gitignore first: " + examples)
    # Validate every parent before writing, and refuse symlinks / Windows junctions.
    for _, path in planned:
        for parent in (path, *path.parents):
            if parent == root:
                break
            if parent.is_symlink():
                raise ValueError("Refusing to create shadows through a symbolic link: " + str(parent))
            if parent.exists():
                attrs = getattr(parent.lstat(), "st_file_attributes", 0)
                if attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                    raise ValueError("Refusing a filesystem junction: " + str(parent))
                if parent != path and not parent.is_dir():
                    raise ValueError("Parent is not a directory: " + str(parent))
                if parent == path and not parent.is_file():
                    raise ValueError("Expected a file path: " + str(parent))
    if args.dry_run:
        missing = sum(not path.exists() for _, path in planned)
        print(f"Would create {missing:,} missing 0-byte files; preserve {len(planned) - missing:,} existing files.")
        return
    try:
        with (root / MARKER).open("x", encoding="utf-8") as handle:
            handle.write("Local placeholders; export manifests only on the real-data server.\n")
    except FileExistsError:
        pass
    created = kept = 0
    for _, path in planned:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb"):
                pass
            created += 1
        except FileExistsError:
            kept += 1
    links = sum(r.get("kind") == "symlink" for r in records)
    print(f"Created {created:,} empty files; preserved {kept:,} existing files.")
    print(f"Symlinks ({links:,}) remain inventory-only. No existing files were truncated or deleted.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("export", "materialize"))
    parser.add_argument("--root", default=".", help="Git repository root (default: current directory)")
    parser.add_argument("--manifest", default="dataset-manifest.jsonl", help="Path relative to repository root")
    parser.add_argument("--scope", action="append", help="Export only ignored files under this relative path; repeatable")
    parser.add_argument("--dry-run", action="store_true", help="Check materialization without creating files")
    args = parser.parse_args()
    try:
        root = repo_root(args.root)
        manifest = safe_path(root, args.manifest)
        if args.command == "export":
            if args.dry_run:
                raise ValueError("--dry-run is for materialize; export itself only writes metadata.")
            export(args, root, manifest)
        else:
            if args.scope:
                raise ValueError("--scope is an export option; regenerate the desired manifest on the server.")
            materialize(args, root, manifest)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("Error: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
