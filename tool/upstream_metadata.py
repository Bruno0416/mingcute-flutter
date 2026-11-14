"""Verified upstream release.json provenance. No package.json/tag inference."""
import json
from pathlib import Path
import re
import subprocess
from urllib.request import urlopen

REPOSITORY = 'mingcute-design/mingcute-icons'
REPO_URL = f'https://github.com/{REPOSITORY}.git'
RAW = f'https://raw.githubusercontent.com/{REPOSITORY}'
SEMVER = re.compile(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z')
SHA = re.compile(r'[a-f0-9]{40}\Z')


def parse_release(raw: bytes) -> str:
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ValueError('Invalid release.json') from exc
    if (not isinstance(data, dict) or type(data.get('schemaVersion')) is not int or
            data['schemaVersion'] != 1 or not isinstance(data.get('version'), str) or
            not SEMVER.fullmatch(data['version'])):
        raise ValueError('release.json requires schemaVersion 1 and a stable x.y.z version')
    return data['version']


def git(*args: str) -> str:
    result = subprocess.run(['git', *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f'Git provenance failed: {result.stderr.strip()}')
    return result.stdout.strip()


def provenance(source: Path) -> dict:
    source = source.resolve()
    local = {'repository': REPOSITORY, 'revision': 'local-source',
             'version': None, 'versionSource': 'release.json'}
    try:
        top = git('-C', str(source), 'rev-parse', '--show-toplevel')
    except RuntimeError:
        return local
    if Path(top).resolve() != source:
        return local  # A fixture must never inherit its parent wrapper's Git SHA.
    revision = git('-C', str(source), 'rev-parse', 'HEAD')
    if not SHA.fullmatch(revision):
        raise ValueError('Unverified upstream Git revision')
    dirty = git('-C', str(source), 'status', '--porcelain', '--untracked-files=all', '--',
                'release.json', 'packages/svg/core-regular', 'packages/svg/core-filled')
    if dirty:
        raise ValueError('Upstream release/artwork is modified; cannot claim the HEAD revision')
    raw = git('-C', str(source), 'show', f'{revision}:release.json').encode('utf8')
    return {**local, 'revision': revision, 'version': parse_release(raw)}


def latest() -> dict:
    """Optional network observation of the coordinated version declared on main.

    Pin the raw JSON fetch to Git's observed SHA to avoid a moving-ref race.
    A failure never invents a version or replaces a previous observation.
    """
    remote = git('ls-remote', '--exit-code', REPO_URL, 'refs/heads/main').split()
    if len(remote) != 2 or remote[1] != 'refs/heads/main' or not SHA.fullmatch(remote[0]):
        raise ValueError('Cannot verify upstream main revision')
    with urlopen(f'{RAW}/{remote[0]}/release.json', timeout=30) as response:
        raw = response.read(1024 * 1024)
    return {'repository': REPOSITORY, 'revision': remote[0], 'version': parse_release(raw),
            'versionSource': 'release.json', 'ref': 'main'}
