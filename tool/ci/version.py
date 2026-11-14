#!/usr/bin/env python3
"""SemVer helper for mingcute_flutter: check, suggest and (explicitly) bump.

  version.py check                         pubspec <-> CHANGELOG consistency (read-only)
  version.py suggest --baseline OLD.json   recommend patch/minor/major from the icon API diff
  version.py bump --part patch|minor|major [--notes FILE] [--write]
  version.py bump --version X.Y.Z          [--notes FILE] [--write]

``bump`` only previews unless ``--write`` is given, and ``--write`` needs a
non-empty ``--notes`` file: release notes are never invented. A new upstream
revision does not by itself change the version.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
SEMVER = re.compile(r'(\d+)\.(\d+)\.(\d+)\Z')
PUBSPEC_VERSION = re.compile(r'(?m)^version:\s*([^\s#]+)\s*(?:#.*)?$')
HEADER = re.compile(r'(?m)^##[ \t]+(\d+\.\d+\.\d+)(?:[ \t]+[-—][^\n]*|[ \t]*\([^\n]*\))?[ \t]*$')


def parse(version: str) -> tuple[int, int, int]:
    m = SEMVER.fullmatch(version)
    if not m:
        raise ValueError(f'Not a stable x.y.z version: {version!r}')
    return tuple(int(x) for x in m.groups())  # type: ignore[return-value]


def current(root: Path) -> str:
    m = PUBSPEC_VERSION.search((root / 'pubspec.yaml').read_text('utf-8'))
    if not m:
        raise ValueError('No version in pubspec.yaml')
    parse(m.group(1))
    return m.group(1)


def changelog_versions(root: Path) -> list[str]:
    return [m.group(1) for m in HEADER.finditer((root / 'CHANGELOG.md').read_text('utf-8'))]


def check(root: Path) -> str:
    version = current(root)
    versions = changelog_versions(root)
    if not versions or versions[0] != version:
        raise ValueError(f'CHANGELOG.md must start with {version}, found {versions[:1]}')
    if len(set(versions)) != len(versions):
        raise ValueError('CHANGELOG.md contains duplicate versions')
    parsed = [parse(v) for v in versions]
    if parsed != sorted(parsed, reverse=True):
        raise ValueError('CHANGELOG.md versions are not in strictly descending order')
    return version


def bumped(version: str, part: str | None, explicit: str | None) -> str:
    old = parse(version)
    if explicit:
        new = parse(explicit)
    else:
        major, minor, patch = old
        new = {'major': (major + 1, 0, 0), 'minor': (major, minor + 1, 0),
               'patch': (major, minor, patch + 1)}[part or 'patch']
    if new <= old:
        raise ValueError(f'New version {".".join(map(str, new))} must be greater than {version}')
    return '.'.join(map(str, new))


def suggest(root: Path, baseline: Path) -> tuple[str, list[str], list[str]]:
    old = json.loads(baseline.read_text('utf-8'))['icons']
    new = json.loads((root / 'tool/manifest.json').read_text('utf-8'))['icons']
    removed, added = [], []
    for style in ('regular', 'filled'):
        removed += [f'{style}.{n}' for n in sorted(set(old.get(style, {})) - set(new[style]))]
        added += [f'{style}.{n}' for n in sorted(set(new[style]) - set(old.get(style, {})))]
    # A changed codepoint breaks previously compiled references as well.
    for style in ('regular', 'filled'):
        for name in set(old.get(style, {})) & set(new[style]):
            if old[style][name]['codepoint'] != new[style][name]['codepoint']:
                removed.append(f'{style}.{name} (codepoint changed)')
    part = 'major' if removed else 'minor' if added else 'patch'
    return part, added, removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, default=ROOT)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('check')
    s = sub.add_parser('suggest')
    s.add_argument('--baseline', type=Path, required=True)
    b = sub.add_parser('bump')
    group = b.add_mutually_exclusive_group(required=True)
    group.add_argument('--part', choices=['patch', 'minor', 'major'])
    group.add_argument('--version')
    b.add_argument('--notes', type=Path, help='file with the real release notes (required with --write)')
    b.add_argument('--write', action='store_true', help='apply the change; without it only a preview is printed')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == 'check':
            print(f'PASS: pubspec.yaml and CHANGELOG.md agree on {check(root)}.')
            return 0
        if args.command == 'suggest':
            part, added, removed = suggest(root, args.baseline)
            print(f'Suggested bump: {part} (+{len(added)} added, -{len(removed)} removed/changed)')
            for item in removed:
                print(f'  BREAKING: {item}')
            if removed:
                print('Removals/renames/codepoint changes are major, or blocked by the append-only ledger policy.')
            return 0
        check(root)
        old = current(root)
        new = bumped(old, args.part, args.version)
        print(f'Preview: {old} -> {new}')
        print(f'  pubspec.yaml: version: {new}')
        print(f'  CHANGELOG.md: new top section "## {new}"')
        if not args.write:
            print('Nothing written. Re-run with --notes FILE --write to apply.')
            return 0
        if not args.notes or not args.notes.is_file() or not args.notes.read_text('utf-8').strip():
            raise ValueError('--write needs --notes FILE with non-empty, real release notes')
        notes = args.notes.read_text('utf-8').strip()
        pubspec = root / 'pubspec.yaml'
        pubspec.write_text(PUBSPEC_VERSION.sub(f'version: {new}', pubspec.read_text('utf-8'), count=1), 'utf-8')
        log = root / 'CHANGELOG.md'
        text = log.read_text('utf-8')
        first = HEADER.search(text)
        log.write_text(text[:first.start()] + f'## {new}\n\n{notes}\n\n' + text[first.start():], 'utf-8')
        print(f'Wrote version {new}.')
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f'version.py FAILED: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
