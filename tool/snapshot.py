#!/usr/bin/env python3
"""Create a MingCute Icons source ZIP without private context, secrets or caches.

Usage:
    python tool/snapshot.py
    python tool/snapshot.py --output ~/Downloads/mingcute_icons-snapshot-20261113-230126.zip

Requires Python 3.10+ and only the standard library.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

# Directory names are omitted wherever they occur, including preview/.
EXCLUDED_DIRS = frozenset({
    ".git", ".dart_tool", ".idea", ".gradle", ".cache",
    ".pub-cache", ".venv", ".pytest_cache", "__pycache__",
    "build", "ephemeral", "coverage", "node_modules", "dist",
    "target", "snapshots", ".agents", ".serena", ".ssh", ".aws", ".azure",
    ".config", ".kube", ".docker", ".auth",
})
EXCLUDED_FILES = frozenset({
    ".DS_Store", ".flutter-plugins", ".flutter-plugins-dependencies",
    "AGENTS.md", ".env", ".envrc", ".netrc", ".npmrc", ".pypirc", ".git-credentials", ".gitcookies",
    "credentials", "credentials.json", "gcloud.json", "secrets.json",
    "application_default_credentials.json", "kubeconfig", "token", "tokens.json",
    "auth.json", "auth.yaml", "auth.yml", "secrets.yaml", "secrets.yml",
    "tokens.yaml", "tokens.yml",
})
EXCLUDED_SUFFIXES = frozenset({".pyc", ".pyo", ".iml", ".log", ".zip",
    ".pem", ".key", ".p12", ".pfx", ".p8", ".pkcs8", ".pkcs12", ".jks", ".jceks",
    ".keystore", ".kdbx", ".token", ".credentials", ".tmp", ".temp", ".swp", ".swo", ".bak"})
SENSITIVE_NAMES = (".env.*", "PROMPT_*.md", "id_rsa*", "id_ed25519*", "id_ecdsa*", "id_dsa*",
                   "*service-account*.json", "*service_account*.json", "gha-creds-*.json",
                   "credentials.*", "*.credentials.json", "*.secret", "*~")
SECRET = re.compile(rb"(?m)^-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----|"
                    rb"\b(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{22,255}|"
                    rb"AIza[A-Za-z0-9_-]{35}|AKIA[A-Z0-9]{16})\b")


def sensitive_content(path: Path) -> bool:
    """Exclude recognizable credentials even when renamed; not a secret audit.

    Stream with overlap so large source/assets need not be loaded into memory.
    Arbitrary or encrypted secrets still require review before sharing a ZIP.
    """
    with path.open('rb') as stream:
        overlap = b''
        while chunk := stream.read(64 * 1024):
            data = overlap + chunk
            if SECRET.search(data):
                return True
            overlap = data[-512:]
    if path.suffix.lower() == '.json':
        try:
            data = json.loads(path.read_text('utf8'))
            return (isinstance(data, dict) and
                    (data.get('type') == 'service_account' or
                     data.get('type') == 'authorized_user' or
                     bool(data.get('private_key'))))
        except (ValueError, UnicodeError):
            pass
    return False


def source_files(project_root: Path, archive: Path):
    """Yield files in sorted order, skipping caches, symlinks and the output ZIP."""
    archive = archive.resolve()
    for parent, subdirs, filenames in os.walk(project_root, followlinks=False):
        base = Path(parent)
        subdirs[:] = sorted(
            name for name in subdirs
            if name not in EXCLUDED_DIRS and not (base / name).is_symlink()
        )
        for name in sorted(filenames):
            path = base / name
            if (
                name in EXCLUDED_FILES
                or any(fnmatch.fnmatchcase(name, pattern) for pattern in SENSITIVE_NAMES)
                or path.suffix.lower() in EXCLUDED_SUFFIXES
                or path.is_symlink()
                or not path.is_file()
                or path.resolve() == archive
                or '\\' in path.relative_to(project_root).as_posix()
                or sensitive_content(path)
            ):
                continue
            yield path


def create_snapshot(project_root: Path, archive: Path) -> tuple[int, int]:
    project_root = project_root.expanduser().resolve()
    archive = archive.expanduser()
    if archive.is_symlink():
        raise ValueError('Snapshot output must not be a symlink')
    archive = archive.resolve()
    if archive.suffix.lower() != '.zip':
        raise ValueError('Snapshot output must use the .zip extension')
    if not (project_root / "pubspec.yaml").is_file() or not (project_root / "lib").is_dir():
        raise ValueError(f"Not a Flutter package root: {project_root}")
    archive.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    total_bytes = 0
    # The archive gets built from sources only; never follow links outside root.
    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=7) as out:
        for path in sorted(source_files(project_root, archive)):
            out.write(path, arcname=path.relative_to(project_root).as_posix())
            count += 1
            total_bytes += path.stat().st_size
    return count, total_bytes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, help="ZIP path (default: ./snapshots/<package>-snapshot-<date>.zip)"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    output = args.output or (root / "snapshots" / f"mingcute_icons-snapshot-{timestamp}.zip")
    count, total_bytes = create_snapshot(root, output)
    archive = output.expanduser().resolve()
    print(f"Snapshot: {archive}")
    print(f"Files: {count} | source size: {total_bytes / 1024:.1f} KiB | zip: {archive.stat().st_size / 1024:.1f} KiB")


if __name__ == "__main__":
    main()
