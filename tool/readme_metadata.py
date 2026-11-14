#!/usr/bin/env python3
"""Update only delimited README metadata; offline by default, network opt-in.

--write regenerates blocks from local files. --refresh-latest --write also
observes official main/release.json, pinned to Git's verified SHA. Neither
command claims that a wrapper version has been published to pub.dev.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlencode

from upstream_metadata import REPOSITORY, RAW, SHA, SEMVER, latest

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = f'https://github.com/{REPOSITORY}'
WEBSITE = 'https://www.mingcute.com/'
BANNER = 'doc/assets/branding/mingcute-banner.png'
BANNER_LINE = f'[![MingCute Icons — Original artwork]({BANNER})]({OFFICIAL})'


def repository_url(spec: str) -> str | None:
    match = re.search(r'(?m)^repository:\s*(https://github\.com/[\w.-]+/[\w.-]+?)(?:\.git)?\s*$', spec)
    return match[1] if match else None


def banner_line(root: Path) -> str:
    spec = (root / 'pubspec.yaml').read_text('utf8') if (root / 'pubspec.yaml').is_file() else ''
    repo = repository_url(spec)
    source = (f'https://raw.githubusercontent.com/{repo.removeprefix("https://github.com/")}/main/{BANNER}'
              if repo else BANNER)
    return f'[![MingCute Icons — Original artwork]({source})]({OFFICIAL})'


def badge(label: str, value: str, label_color: str, target: str, *, logo: str | None = None) -> str:
    params = {'label': label, 'message': value, 'color': '555555',
              'style': 'for-the-badge', 'labelColor': label_color}
    if logo:
        params.update(logo=logo, logoColor='white')
    image = 'https://img.shields.io/static/v1?' + urlencode(params)
    return f'[![{label}: {value}]({image})]({target})'


def blocks(root: Path, observation: dict | None) -> dict[str, str]:
    spec = (root / 'pubspec.yaml').read_text('utf8')
    wrapper = re.search(r'(?m)^version:\s*(\S+)\s*$', spec)
    if not wrapper or not SEMVER.fullmatch(wrapper[1]):
        raise ValueError('Invalid wrapper version')
    manifest = json.loads((root / 'tool/manifest.json').read_text('utf8'))
    upstream = manifest.get('upstream', {})
    revision, synced = manifest['sourceRevision'], upstream.get('version')
    if upstream.get('repository') != REPOSITORY or not isinstance(revision, str) or not SHA.fullmatch(revision) or not isinstance(synced, str) or not SEMVER.fullmatch(synced):
        raise ValueError('README requires verified synced Git/release.json provenance')
    latest_version = None
    if observation is not None:
        if not isinstance(observation, dict):
            raise ValueError('Invalid latest-upstream observation')
        latest_version = observation.get('version')
        if (observation.get('repository') != REPOSITORY or observation.get('versionSource') != 'release.json' or
                observation.get('ref') != 'main' or not SHA.fullmatch(observation.get('revision', '')) or
                not isinstance(latest_version, str) or not SEMVER.fullmatch(latest_version)):
            raise ValueError('Invalid latest-upstream observation')
    commit = f'{OFFICIAL}/commit/{revision}'
    counts = {style: len(manifest['icons'][style]) for style in ('regular', 'filled')}
    base = repository_url(spec)
    dynamic = 'https://img.shields.io/badge/dynamic/json?' + urlencode({
        'url': f'{RAW}/main/release.json', 'query': '$.version',
        'label': 'upstream latest', 'color': '555555',
        'style': 'for-the-badge', 'labelColor': '007AFF',
    })
    wrapper_target = f'{base}/blob/main/pubspec.yaml' if base else 'pubspec.yaml'
    badges = [badge('Flutter source', wrapper[1], '02569B', wrapper_target, logo='flutter'),
              badge('Icons', f'{sum(counts.values()):,}', '7466E0', 'doc/ICONS.md'),
              badge('Upstream synced', synced, '007AFF', commit),
              f'[![Upstream latest declared version]({dynamic})]({OFFICIAL}/blob/main/release.json)',
              badge('MingCute original', 'GitHub', '24292F', OFFICIAL, logo='github'),
              badge('Official website', 'mingcute.com', '00A8A8', WEBSITE),
              badge('Wrapper code', 'MIT', '279B75', 'LICENSE'),
              badge('Artwork', 'Apache-2.0', '279B75', 'UPSTREAM_APACHE_LICENSE.txt')]
    if base:
        slug = base.removeprefix('https://github.com/')
        ci = 'https://img.shields.io/github/actions/workflow/status/' + slug + '/ci.yml?' + urlencode({
            'branch': 'main', 'style': 'for-the-badge', 'logo': 'githubactions',
            'logoColor': 'white', 'labelColor': '2088FF'})
        badges.insert(1, f'[![GitHub Actions]({ci})]({base}/actions/workflows/ci.yml)')
    if latest_version is None:
        observed, status = 'Unknown — optional refresh not performed', 'Unknown; no version invented'
    else:
        observed = f'[{latest_version}]({RAW}/{observation["revision"]}/release.json) (last checked `{observation["revision"][:7]}`)'
        a, b = tuple(map(int, synced.split('.'))), tuple(map(int, latest_version.split('.')))
        status = 'In sync at the last observation' if a == b else (
            'Update available upstream; not yet integrated' if a < b else 'Refresh required: observation is older than the synced source')
    table = ['| Component | Version / status |', '|---|---|',
             f'| Flutter wrapper (source, not publication status) | {wrapper[1]} |',
             f'| MingCute synced | {synced} |', f'| MingCute latest declared on main | {observed} |',
             f'| Synced revision | [{revision[:7]}]({commit}) |', f'| Upstream comparison | {status} |', '',
             '| Catalogue | Count |', '|---|---|', f'| Regular icons | {counts["regular"]:,} |',
             f'| Filled icons | {counts["filled"]:,} |', f'| Total glyphs | {sum(counts.values()):,} |']
    return {'BADGES': '\n'.join(badges), 'STATUS': '\n'.join(table)}


def replace_blocks(text: str, generated: dict[str, str]) -> str:
    for label, body in generated.items():
        start, end = f'<!-- BEGIN MINGCUTE {label} -->', f'<!-- END MINGCUTE {label} -->'
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError(f'Expected exactly one README {label} block')
        pattern = re.compile(re.escape(start) + r'.*?' + re.escape(end), re.S)
        if not pattern.search(text):
            raise ValueError('README marker order is invalid')
        text = pattern.sub(lambda _: start + '\n' + body + '\n' + end, text)
    return text


def write_changed(path: Path, data: str) -> None:
    if not path.is_file() or path.read_text('utf8') != data:
        path.write_text(data, encoding='utf8')


def update(root: Path = ROOT, *, write: bool = False, refresh: bool = False) -> bool:
    cache = root / 'tool/upstream_status.json'
    observation = json.loads(cache.read_text('utf8')) if cache.is_file() else None
    if refresh:
        if not write:
            raise ValueError('--refresh-latest requires --write (explicit network/cache update)')
        observation = latest()  # Fetch and validate before touching either file.
    readme = root / 'README.md'
    old = readme.read_text('utf8')
    new = replace_blocks(old, blocks(root, observation))
    if write:
        if refresh:
            write_changed(cache, json.dumps(observation, sort_keys=True, indent=2) + '\n')
        write_changed(readme, new)
    return old != new


def check_banner(root: Path = ROOT) -> None:
    attribution = json.loads((root / 'doc/assets/branding/ATTRIBUTION.json').read_text('utf8'))
    revision = attribution['revision']
    source = attribution['sourcePath']
    if (attribution['repository'] != REPOSITORY or not SHA.fullmatch(revision) or
            source != 'images/banner1.png' or attribution['license'] != 'Apache-2.0' or
            attribution['sourceUrl'] != f'{RAW}/{revision}/{source}' or
            attribution['sha256'] != hashlib.sha256((root / BANNER).read_bytes()).hexdigest()):
        raise ValueError('Invalid official banner provenance/hash')
    readme = (root / 'README.md').read_text('utf8')
    title = '# MingCute Icons for Flutter'
    if not readme.startswith(title + '\n\n') or len(re.findall(r'(?m)^#\s+', readme)) != 1:
        raise ValueError('Exactly one leading README title is required')
    start, end = '<!-- BEGIN MINGCUTE BADGES -->', '<!-- END MINGCUTE BADGES -->'
    if readme.count(start) != 1 or readme.count(end) != 1:
        raise ValueError('Exactly one generated badges block is required')
    expected_banner = banner_line(root)
    header = re.fullmatch(re.escape(title) + r'\n\n' + re.escape(start) +
                          r'\n(?P<badges>.*?)\n' + re.escape(end) + r'\n\n' +
                          re.escape(expected_banner) + r'\n\n' +
                          r'(?P<notice>> \*\*Unofficial Flutter package\*\*\n(?:>[^\n]*\n)+)' +
                          r'\nMingCute Core Regular and Filled as native Flutter `IconData`.*', readme, re.S)
    if not header:
        raise ValueError('README order must be title, badges, official banner, immediate unofficial notice, introduction')
    if readme.count(BANNER) != 1 or readme.count(expected_banner) != 1:
        raise ValueError('Exactly one official banner is required')
    badge_urls = re.findall(r'https://img\.shields\.io/[^\s)"<>]+', readme)
    block_urls = re.findall(r'https://img\.shields\.io/[^\s)"<>]+', header['badges'])
    if not block_urls or badge_urls != block_urls or len(badge_urls) != len(set(badge_urls)):
        raise ValueError('Badges must occur once, exclusively in their generated block')
    if re.search(r'https?://[^\s)<>]*(?:YOUR_USERNAME|your-repo|example\.com|github\.com/owner/repo\b)', readme, re.I):
        raise ValueError('Fictitious README URL')
    if 'banner1.png' not in (root / 'THIRD_PARTY_NOTICES.md').read_text('utf8'):
        raise ValueError('Missing banner attribution in THIRD_PARTY_NOTICES.md')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--write', action='store_true')
    mode.add_argument('--check', action='store_true', help='offline check (default)')
    parser.add_argument('--refresh-latest', action='store_true')
    args = parser.parse_args()
    try:
        changed = update(args.root, write=args.write, refresh=args.refresh_latest)
        check_banner(args.root)
        if changed and not args.write:
            raise ValueError('Stale generated README blocks; run tool/readme_metadata.py --write')
        print('PASS: README metadata, official links and banner provenance (no publication claim).')
        return 0
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
        print(f'README metadata FAILED: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
