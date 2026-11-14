#!/usr/bin/env python3
"""Fail-closed checks and changelog release notes for mingcute_flutter publishing.

Metadata and archive-file checks are local; registry commands use HTTPS.
Exit code for 'published': 0 = version exists, 10 = not published, 1 = error.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import posixpath
import re
import subprocess
import sys
import tarfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
VERSION_RE = re.compile(r"\d+\.\d+\.\d+\Z")
PUBSPEC_VERSION = re.compile(r"(?m)^version:\s*([^\s#]+)\s*(?:#.*)?$")
PACKAGE = 'mingcute_flutter'
TOPICS_MAX = 5
SCREENSHOTS_MAX = 10
LOCAL_CONTEXT_PARTS = {'.agents', '.serena'}
LOCAL_CONTEXT_FILES = {'AGENTS.md', 'PROMPT_MINGCUTE_R2.md'}
CHANGELOG_HEADER = re.compile(r"(?m)^##[ \t]+(\d+\.\d+\.\d+)(?:[ \t]+[-—][^\n]*|[ \t]*\([^\n]*\))?[ \t]*$")


def read_metadata(root: Path, tag: str | None = None) -> tuple[str, str]:
    pubspec = (root / 'pubspec.yaml').read_text(encoding='utf-8')
    name_match = re.search(r'(?m)^name:\s*([^\s#]+)', pubspec)
    if not name_match or name_match.group(1) != PACKAGE:
        raise ValueError('Incorrect package identity in pubspec.yaml')
    m = PUBSPEC_VERSION.search(pubspec)
    if not m:
        raise ValueError('No pubspec.yaml version found')
    version = m.group(1)
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f'Only stable x.y.z versions can be published: {version}')
    if tag is not None and tag != f'v{version}':
        raise ValueError(f'Tag {tag!r} differs from pubspec version v{version}')
    if re.search(r'(?m)^publish_to:\s*none\b', pubspec):
        raise ValueError('pubspec.yaml still declares publish_to: none')
    changelog = (root / 'CHANGELOG.md').read_text(encoding='utf-8')
    headers = list(CHANGELOG_HEADER.finditer(changelog))
    if not headers or headers[0].group(1) != version:
        raise ValueError(f'First CHANGELOG.md entry must be for {version}')
    if sum(1 for item in headers if item.group(1) == version) != 1:
        raise ValueError(f'Duplicate CHANGELOG.md entry for {version}')
    start = headers[0].end()
    end = headers[1].start() if len(headers) > 1 else len(changelog)
    body = changelog[start:end].strip()
    if not body:
        raise ValueError(f'CHANGELOG.md entry {version} has no release notes')
    return version, body


def pubspec_report(root: Path, *, require_public_urls: bool = False) -> list[str]:
    """Validate store metadata. Returns warnings; raises ValueError on errors.

    homepage/repository/issue_tracker are never invented: while the real
    remote is unknown they are reported as pending, and --require-public-urls
    (used by the release path) turns that into a failure.
    """
    pubspec = (root / 'pubspec.yaml').read_text(encoding='utf-8')
    warnings: list[str] = []
    if not re.search(r'(?m)^description:\s*\S', pubspec):
        raise ValueError('pubspec.yaml has no description')
    description = re.search(r'(?m)^description:\s*(.+)$', pubspec).group(1).strip('\'"')
    if not 60 <= len(description) <= 180:
        raise ValueError(f'description must be 60-180 characters for pub.dev, got {len(description)}')
    topics = re.search(r'(?ms)^topics:\s*\n((?:\s+-\s+\S+\s*\n)+)', pubspec)
    if topics:
        items = re.findall(r'-\s+(\S+)', topics.group(1))
        if len(items) > TOPICS_MAX or any(not re.fullmatch(r'[a-z][a-z0-9-]{0,30}[a-z0-9]', t) for t in items):
            raise ValueError(f'topics must be at most {TOPICS_MAX} lowercase slugs: {items}')
    else:
        warnings.append('pubspec.yaml has no topics')
    shots = re.findall(r'(?m)^\s+path:\s*(\S+\.png)\s*$', pubspec)
    if len(shots) > SCREENSHOTS_MAX:
        raise ValueError(f'at most {SCREENSHOTS_MAX} screenshots are allowed, found {len(shots)}')
    for shot in shots:
        path = root / shot
        if not path.is_file() or (path.parent / path.name).resolve().name != path.name:
            raise ValueError(f'screenshot is missing or has a different case: {shot}')
    if not shots:
        warnings.append('pubspec.yaml declares no screenshots')
    for field in ('repository', 'issue_tracker', 'homepage'):
        match = re.search(rf'(?m)^{field}:\s*(\S+)', pubspec)
        if not match:
            warnings.append(f'pubspec.yaml has no {field}: public remote not confirmed yet')
        elif not match.group(1).startswith('https://'):
            raise ValueError(f'{field} must be an https URL')
    if require_public_urls and warnings:
        raise ValueError('public metadata incomplete: ' + '; '.join(warnings))
    return warnings


def registry_state(version: str, package: str = PACKAGE) -> str:
    """Return 'no-package' (never published: bootstrap pending), 'absent'
    (package exists, this version does not) or 'published'. Anything
    unexpected raises, so callers fail closed."""
    if not VERSION_RE.fullmatch(version):
        raise ValueError('Version must be stable x.y.z')
    url = f'https://pub.dev/api/packages/{package}'
    request = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'mingcute-icons-release-guard/1'})
    try:
        with urlopen(request, timeout=20) as response:
            record = json.load(response)
    except HTTPError as exc:
        if exc.code == 404:
            return 'no-package'
        raise RuntimeError(f'Cannot verify package versions on pub.dev: HTTP {exc.code}') from exc
    except (URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f'Cannot verify package versions on pub.dev: {exc}') from exc
    versions = record.get('versions') if isinstance(record, dict) else None
    if not isinstance(versions, list) or any(
        not isinstance(item, dict) or not isinstance(item.get('version'), str)
        for item in versions
    ):
        raise RuntimeError('Unexpected pub.dev package metadata response')
    return 'published' if any(item.get('version') == version for item in versions) else 'absent'


def published_status(version: str, package: str = PACKAGE) -> bool:
    """True when the version exists. A missing package is *not* 'absent'."""
    state = registry_state(version, package)
    if state == 'no-package':
        raise RuntimeError('Package is not on pub.dev yet: manual bootstrap publication required')
    return state == 'published'


def release_decision(
    *,
    event: str,
    ref: str,
    gates_passed: bool,
    validated_sha: str,
    main_sha: str,
    published_state: str,
    archive_matches: bool = False,
    publish_state: str = 'not-started',
    publication_confirmed: bool = False,
    existing_tag_sha: str | None = None,
    tag_is_ancestor: bool = False,
    release_exists: bool = False,
) -> str:
    """Return the only safe next action for a release attempt.

    Results: validate-only, stale, bootstrap-pending, blocked, conflict,
    already-published, recover, await-confirmation, publication-failed, publish.

    Branches, pull requests and tags are validation-only. On main, publishing
    needs a current, fully gated snapshot of a package that already exists on
    pub.dev: the first version of a package is always a manual publication, so
    'no-package' never authorises an automated upload.
    """
    if event != 'push' or ref != 'refs/heads/main':
        return 'validate-only'
    if validated_sha != main_sha:
        return 'stale'
    if not gates_passed or published_state == 'error':
        return 'blocked'
    if published_state == 'no-package':
        return 'bootstrap-pending'
    if existing_tag_sha is not None and existing_tag_sha != validated_sha and not tag_is_ancestor:
        return 'conflict'
    if published_state not in {'absent', 'published'}:
        return 'blocked'
    if published_state == 'published':
        if not archive_matches:
            return 'conflict'
        return 'already-published' if existing_tag_sha and release_exists else 'recover'
    if existing_tag_sha is not None or release_exists:
        return 'conflict'
    if publish_state == 'failed':
        return 'publication-failed'
    if publish_state == 'succeeded':
        return 'recover' if publication_confirmed else 'await-confirmation'
    if publish_state != 'not-started':
        return 'blocked'
    return 'publish'


def check_local_context_paths(root: Path, revision: str | None = None) -> None:
    """Reject tracked/staged context; excluded local instructions may exist.

    A ZIP has no index and cannot establish tracking status. Check its actual
    pub archive separately with 'archive-files'; never infer Git state from it.
    """
    probe = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'],
                           capture_output=True, text=True, check=False)
    if probe.returncode or Path(probe.stdout.strip()).resolve() != root.resolve():
        raise ValueError('check-local-context requires this root to be a Git checkout')
    args = ['ls-tree', '-r', '-z', '--name-only', revision] if revision else ['ls-files', '--cached', '-z']
    result = subprocess.run(['git', '-C', str(root), *args],
                            capture_output=True, check=True)
    check_context_names(p.decode('utf-8', errors='surrogateescape')
                        for p in result.stdout.split(b'\0') if p)


def check_context_names(names) -> None:
    for name in names:
        parts = Path(name).parts
        if any(part in LOCAL_CONTEXT_PARTS for part in parts) or \
                Path(name).name in LOCAL_CONTEXT_FILES or Path(name).suffix.lower() == '.zip':
            raise ValueError(f'local agent context/snapshot path must not be tracked or published: {name}')


def archive_files(archive_bytes: bytes) -> dict[str, bytes]:
    """Read package members without extraction, ignoring tar metadata only."""
    actual: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as archive:
            members = archive.getmembers()
            paths = [m.name for m in members if m.isfile()]
            prefix = 'package/' if paths and all(p.startswith('package/') for p in paths) else ''
            for member in members:
                name = member.name.removeprefix(prefix)
                normalized = posixpath.normpath(name)
                if normalized.startswith('../') or normalized.startswith('/') or normalized == '..':
                    raise ValueError('Package archive contains an unsafe path')
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ValueError('Package archive contains a non-regular file')
                if normalized == '.' or normalized in actual:
                    raise ValueError('Package archive contains an invalid or duplicate path')
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError('Cannot read a package archive file')
                actual[normalized] = stream.read()
    except tarfile.TarError as exc:
        raise ValueError(f'Cannot read package archive: {exc}') from exc
    if not actual or 'pubspec.yaml' not in actual:
        raise ValueError('Package archive has no pubspec.yaml')
    check_context_names(actual)
    return actual


SECRET_PATTERNS = (
    re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),
    re.compile(rb'-----BEGIN [A-Z ]*PRIVATE KEY-----'),
    re.compile(rb'AIza[0-9A-Za-z_-]{35}'),
    re.compile(rb'(?i)pub[_-]?dev[_-]?token\s*[:=]\s*\S{12,}'),
)
FORBIDDEN_PREFIXES = ('.github/', 'preview/', 'tool/', 'tests/', '.agents/', 'doc/assets/screenshots/manifest.json')
REQUIRED_FILES = ('pubspec.yaml', 'README.md', 'CHANGELOG.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md',
                  'UPSTREAM_APACHE_LICENSE.txt', 'lib/mingcute_icons.dart', 'lib/mingcute_static.dart',
                  'assets/fonts/MingCuteRegular.ttf', 'assets/fonts/MingCuteFilled.ttf',
                  'lib/src/generated/regular_icons.g.dart', 'lib/src/generated/filled_icons.g.dart')


def check_archive_content(files: dict[str, bytes]) -> None:
    """Semantic inspection of pub's real archive (never a .pubignore regex)."""
    for name in REQUIRED_FILES:
        if name not in files:
            raise ValueError(f'Package archive is missing required file: {name}')
    for name in files:
        if name.startswith(FORBIDDEN_PREFIXES) or Path(name).name in LOCAL_CONTEXT_FILES:
            raise ValueError(f'Package archive contains a non-package file: {name}')
        if name.lower().endswith(('.zip', '.patch', '.log')) or Path(name).name.startswith('gha-creds'):
            raise ValueError(f'Package archive contains a forbidden artifact: {name}')
    pubspec = files['pubspec.yaml'].decode('utf-8')
    for shot in re.findall(r'(?m)^\s+path:\s*(doc/assets/screenshots/\S+\.png)\s*$', pubspec):
        if shot not in files:
            raise ValueError(f'Declared screenshot is absent from the archive: {shot}')
    readme = files['README.md'].decode('utf8')
    for banner in re.findall(r'(doc/assets/branding/[\w-]+\.png)', readme):
        attribution_path = 'doc/assets/branding/ATTRIBUTION.json'
        if banner not in files or attribution_path not in files:
            raise ValueError('README banner/attribution is absent from the archive')
        try:
            attribution = json.loads(files[attribution_path])
            if (attribution['repository'] != 'mingcute-design/mingcute-icons' or
                    attribution['license'] != 'Apache-2.0' or
                    attribution['sha256'] != hashlib.sha256(files[banner]).hexdigest()):
                raise ValueError('Archive banner attribution/hash mismatch')
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError('Invalid archive banner attribution') from exc
    for name, data in files.items():
        if any(p.search(data) for p in SECRET_PATTERNS):
            raise ValueError(f'Possible secret/token inside archive file: {name}')
    if b'morph' in pubspec.lower().encode() or 'mingcute_icons_kit' in pubspec:
        raise ValueError('Package archive pubspec carries legacy identity')


def published_archive_matches(local_archive: Path, version: str) -> bool:
    """Compare pub's real local archive to pub.dev's checksum-verified archive.

    Generate the local file with `dart pub publish --to-archive=...` (no upload).
    Do not emulate pub's nested ignore rules or implicit exclusions.
    """
    if not VERSION_RE.fullmatch(version):
        raise ValueError('Version must be stable x.y.z')
    expected = archive_files(local_archive.read_bytes())
    local_version = PUBSPEC_VERSION.search(expected['pubspec.yaml'].decode())
    if not local_version or local_version.group(1) != version:
        raise ValueError('Local package archive version differs from requested version')
    api_url = f'https://pub.dev/api/packages/{PACKAGE}/versions/{version}'
    try:
        with urlopen(Request(api_url, headers={'Accept': 'application/json'}), timeout=30) as response:
            metadata = json.loads(response.read())
        if not isinstance(metadata, dict):
            raise ValueError('Unexpected pub.dev version metadata response')
        archive_url = metadata.get('archive_url')
        expected_url = f'https://pub.dev/api/archives/{PACKAGE}-{version}.tar.gz'
        if archive_url != expected_url:
            raise RuntimeError('Unexpected pub.dev archive URL')
        with urlopen(Request(archive_url), timeout=60) as response:
            archive_bytes = response.read()
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        raise RuntimeError(f'Cannot verify published archive: {exc}') from exc
    digest = metadata.get('archive_sha256')
    if not isinstance(digest, str) or hashlib.sha256(archive_bytes).hexdigest() != digest:
        raise RuntimeError('Published archive checksum does not match pub.dev metadata')

    return archive_files(archive_bytes) == expected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    sub = parser.add_subparsers(dest='command', required=True)
    m = sub.add_parser('metadata')
    m.add_argument('--tag')
    m.add_argument('--require-public-urls', action='store_true',
                   help='fail when repository/issue_tracker/homepage are missing')
    context = sub.add_parser('check-local-context')
    context.add_argument('--revision', help='inspect this exact commit instead of the index')
    p = sub.add_parser('published')
    p.add_argument('--version', required=True)
    a = sub.add_parser('archive-matches')
    a.add_argument('--version', required=True)
    a.add_argument('--archive', type=Path, required=True)
    f = sub.add_parser('archive-files')
    f.add_argument('--archive', type=Path, required=True)
    n = sub.add_parser('notes')
    n.add_argument('--version', required=True)
    n.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'check-local-context':
            check_local_context_paths(args.root, args.revision)
            print('PASS: no local agent context paths in the publication snapshot.')
            return 0
        if args.command == 'published':
            return 0 if published_status(args.version) else 10
        if args.command == 'archive-matches':
            return 0 if published_archive_matches(args.archive, args.version) else 10
        if args.command == 'archive-files':
            files = archive_files(args.archive.read_bytes())
            check_archive_content(files)
            print(f'PASS: {len(files)} package files; required content present, no local context or secrets.')
            return 0
        version, notes = read_metadata(args.root, getattr(args, 'tag', None))
        if args.command == 'metadata':
            for warning in pubspec_report(args.root, require_public_urls=args.require_public_urls):
                print(f'WARNING: {warning}', file=sys.stderr)
            print(version)
            return 0
        if args.version != version:
            raise ValueError('Requested notes version differs from current metadata')
        args.output.write_text(notes + '\n', encoding='utf-8')
        print(f'Extracted changelog notes to {args.output}', file=sys.stderr)
        return 0
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f'Release guard FAILED: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
