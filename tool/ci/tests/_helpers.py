"""Shared fixtures: a minimal valid project tree and a pub-like archive."""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tarfile

TOOL = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
if str(TOOL) not in sys.path:
    sys.path.insert(0, str(TOOL))

PUBSPEC = """name: mingcute_flutter
description: Unofficial MingCute Core icon fonts for Flutter, with native Regular and Filled IconData constants.
version: {version}
{extra}
topics:
  - icons
  - flutter

screenshots:
  - description: Demo
    path: doc/assets/screenshots/hero-dark.png

environment:
  sdk: '>=3.5.0 <4.0.0'
"""

CHANGELOG = """# Changelog

## 0.2.0

- Added icons.

## 0.1.0

- First version.
"""


def make_project(root: Path, version: str = '0.2.0', extra: str = '', changelog: str = CHANGELOG) -> Path:
    (root / 'doc/assets/screenshots').mkdir(parents=True, exist_ok=True)
    (root / 'doc/assets/screenshots/hero-dark.png').write_bytes(b'png')
    (root / 'pubspec.yaml').write_text(PUBSPEC.format(version=version, extra=extra), 'utf-8')
    (root / 'CHANGELOG.md').write_text(changelog, 'utf-8')
    return root


def package_files(version: str = '0.2.0', **overrides: bytes | None) -> dict[str, bytes]:
    files = {
        'pubspec.yaml': PUBSPEC.format(version=version, extra='').encode(),
        'README.md': b'readme', 'CHANGELOG.md': b'changelog', 'LICENSE': b'MIT',
        'THIRD_PARTY_NOTICES.md': b'notices', 'UPSTREAM_APACHE_LICENSE.txt': b'Apache License',
        'lib/mingcute_icons.dart': b'library;',
        'lib/mingcute_static.dart': b'library;',
        'assets/fonts/MingCuteRegular.ttf': b'ttf', 'assets/fonts/MingCuteFilled.ttf': b'ttf',
        'lib/src/generated/regular_icons.g.dart': b'dart', 'lib/src/generated/filled_icons.g.dart': b'dart',
        'doc/assets/screenshots/hero-dark.png': b'png',
    }
    for name, data in overrides.items():
        if data is None:
            files.pop(name)
        else:
            files[name] = data
    return files


def tarball(files: dict[str, bytes], prefix: str = '') -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(prefix + name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()
