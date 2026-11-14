#!/usr/bin/env python3
"""Documentation guard: identity, credits, README API vs the generated API,
counts, screenshot references (raw URLs vs relative paths) and licences.

Pending external facts (the public remote) are reported as warnings, never
invented. Everything else is an error.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_final_release_language import relative_names  # noqa: E402
from readme_metadata import update as check_readme_blocks, check_banner

LEGACY = re.compile(r'(?i)morph|fluent|mingcute_icons_kit')
IDENTITY_SCAN_SUFFIXES = {'.md', '.dart', '.yaml', '.yml', '.json', '.txt', '.sh', '.mjs'}
IDENTITY_SKIP = ('.agents/', 'tool/ci/', 'tests/', 'node_modules/', 'preview/assets/', 'tool/manifest.json',
                 'tool/last_sync_report.json', 'tool/codepoints.json', 'preview/lib/generated_catalog.dart',
                 'lib/src/generated/', 'package-lock.json', 'UPSTREAM_APACHE_LICENSE.txt',
                 'pubspec.lock', 'preview/build/', 'AGENTS.md', 'PROMPT_', 'doc/assets/screenshots/manifest.json')
API_REF = re.compile(r'\bMingCute\.([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\b')
OBSOLETE_API = re.compile(r'\b(?:MingCute(?:Regular|Filled)\.[a-z_][a-z0-9_]*|MingCuteIcons\.(?:regular|line|filled)(?:\.[a-z_][a-z0-9_]*)?)\b')
RAW_URL = re.compile(r'https://raw\.githubusercontent\.com/([\w.-]+)/([\w.-]+)/([\w./-]+?)/(doc/assets/screenshots/[^\s)"\'<>]+)')
IMG_REL = re.compile(r'''(?:!\[[^\]]*\]\(|src=["'])(?!https?:)(doc/assets/screenshots/[^\s)"'<>]+)''')
REQUIRED_DOCS = ('README.md', 'CHANGELOG.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'UPSTREAM_APACHE_LICENSE.txt',
                 'CONTRIBUTING.md', 'doc/README.md', 'doc/GETTING_STARTED.md', 'doc/ICONS.md',
                 'doc/GENERATOR.md', 'doc/RELEASE.md', 'doc/PREVIEW.md',
                 'doc/assets/branding/ATTRIBUTION.json', 'doc/assets/branding/mingcute-banner.png',
                 'tool/upstream_status.json')


def check(root: Path = ROOT) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for name in REQUIRED_DOCS:
        if not (root / name).is_file():
            errors.append(f'missing document: {name}')
    if errors:
        return errors, warnings
    manifest = json.loads((root / 'tool/manifest.json').read_text('utf-8'))
    icons = manifest['icons']
    names = [n for n in relative_names(root, 'all', None)]
    docs = [n for n in names if n.endswith('.md') and not n.startswith(('.agents/', 'tool/screenshot_capture/node_modules/'))
            and n not in ('AGENTS.md',) and not n.startswith('PROMPT_')]
    pubspec = (root / 'pubspec.yaml').read_text('utf-8')

    # 1. identity: no inherited names anywhere that is published or versioned
    for name in names:
        if name.startswith(IDENTITY_SKIP) or Path(name).suffix.lower() not in IDENTITY_SCAN_SUFFIXES:
            continue
        path = root / name
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        for line_no, line in enumerate(path.read_text('utf-8', errors='replace').splitlines(), 1):
            if LEGACY.search(line):
                errors.append(f'{name}:{line_no}: inherited/legacy identity: {line.strip()[:100]}')
    if not re.search(r'(?m)^name:\s*mingcute_icons\s*$', pubspec):
        errors.append('pubspec.yaml name must be exactly mingcute_icons')

    # 2. README essentials
    readme = (root / 'README.md').read_text('utf-8')
    for needle, why in (('flutter pub add mingcute_icons', 'install command'),
                        ("import 'package:mingcute_icons/mingcute_icons.dart';", 'import'),
                        ('https://github.com/mingcute-design/mingcute-icons', 'credit link to MingCute Design'),
                        ('MingCute Design', 'credit to MingCute Design'),
                        ('Apache', 'upstream licence mention'),
                        ('THIRD_PARTY_NOTICES.md', 'notices link'),
                        ('unofficial', 'unofficial wrapper statement')):
        if needle.lower() not in readme.lower():
            errors.append(f'README.md lacks {why} ({needle!r})')
    counts = {s: len(icons[s]) for s in ('regular', 'filled')}
    if f'{counts["regular"]:,}' not in readme or f'{counts["regular"] + counts["filled"]:,}' not in readme:
        errors.append(f'README.md must state {counts["regular"]:,} icons per style / {sum(counts.values()):,} glyphs (current manifest)')
    revision = manifest['sourceRevision']
    if revision[:7] not in readme and revision[:7] not in (root / 'doc/ICONS.md').read_text('utf-8'):
        errors.append(f'README.md or doc/ICONS.md must record the upstream revision {revision[:7]}')

    # 3. every documented API reference exists in the generated API
    for name in docs:
        text = (root / name).read_text('utf-8')
        for style, ident in API_REF.findall(text):
            if style not in icons or ident not in icons[style]:
                errors.append(f'{name}: MingCute.{style}.{ident} does not exist in the generated API')
        for style, ident in re.findall(r'MingCute(Regular|Filled)Const\.([a-zA-Z_][a-zA-Z_0-9]*)', text):
            if ident not in icons[style.lower()]:
                errors.append(f'{name}: MingCute{style}Const.{ident} does not exist in the generated API')
        for match in OBSOLETE_API.finditer(text):
            if not match.group().endswith('.ttf'):
                errors.append(f'{name}: obsolete API: {match.group()}')

    # 4. screenshots referenced by documents
    repo = re.search(r'(?m)^repository:\s*https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?\s*$', pubspec)
    for name in docs:
        text = (root / name).read_text('utf-8')
        for owner, project, ref, rel in RAW_URL.findall(text):
            if ref != 'main':
                errors.append(f'{name}: raw URL must use the main branch, got {ref}')
            if not repo:
                errors.append(f'{name}: raw URL present but pubspec.yaml has no confirmed repository')
            elif (owner, project) != repo.groups():
                errors.append(f'{name}: raw URL owner/repo {owner}/{project} differs from pubspec repository')
            target = root / rel
            if not target.is_file() or target.resolve().name != Path(rel).name:
                errors.append(f'{name}: raw URL points to a missing/case-different file: {rel}')
        for rel in IMG_REL.findall(text):
            if name == 'README.md' and repo:
                errors.append(f'README.md: use an absolute raw.githubusercontent.com URL for {rel} (repository is configured)')
            if not (root / rel).is_file():
                errors.append(f'{name}: image not found: {rel}')
    if name_readme_images(readme) == 0:
        errors.append('README.md shows no screenshots')
    if not repo:
        warnings.append('PENDING: pubspec.yaml has no repository; README screenshots use relative paths and '
                        'must switch to raw.githubusercontent.com URLs once the real remote is confirmed')

    # 5. licences
    notices = (root / 'THIRD_PARTY_NOTICES.md').read_text('utf-8')
    if 'Apache' not in notices or 'MingCute Design' not in notices or 'UPSTREAM_APACHE_LICENSE.txt' not in notices:
        errors.append('THIRD_PARTY_NOTICES.md must credit MingCute Design and reference the Apache-2.0 licence')
    if 'Apache License' not in (root / 'UPSTREAM_APACHE_LICENSE.txt').read_text('utf-8'):
        errors.append('UPSTREAM_APACHE_LICENSE.txt is not the Apache licence text')
    try:
        if check_readme_blocks(root):
            errors.append('README.md has stale generated badges/catalogue/version blocks')
        check_banner(root)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        errors.append(f'README/banner metadata: {exc}')
    return errors, warnings


def name_readme_images(readme: str) -> int:
    return len(re.findall(r'doc/assets/screenshots/[\w-]+\.png', readme))


def main() -> int:
    errors, warnings = check()
    for w in warnings:
        print(f'WARNING: {w}', file=sys.stderr)
    if errors:
        for e in errors:
            print(f'DOC CHECK FAILED: {e}', file=sys.stderr)
        return 1
    print('PASS: documentation, identity, credits, API references and screenshot links.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
