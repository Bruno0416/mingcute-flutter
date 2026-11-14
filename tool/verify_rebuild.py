#!/usr/bin/env python3
"""Full clean-room rebuild check for the MingCute Flutter font adapter.

Defaults to a FRESH automatic upstream Git clone. Generates the full catalogue,
deletes TTF and generated Dart files *only inside a temporary directory*, then
regenerates them and confirms deterministic bytes, stable codepoints, and an
idempotent third pass. NEVER deletes the current project's fonts or metadata.

Run from any directory: python tool/verify_rebuild.py
For local tests: python tool/verify_rebuild.py --source tool/tests/fixtures/upstream --min-icons 4
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from sync_icons import ROOT, STYLES, fetch_upstream, run, sha256, write_if_changed
from validate import validate


def artifact_paths(root: Path) -> dict[str, Path]:
    result = {
        f'font/{style}': root / 'assets' / 'fonts' / f'{family}.ttf'
        for style, (_, family) in STYLES.items()
    }
    result.update({
        f'dart/{style}': root / 'lib' / 'src' / 'generated' / f'{style}_icons.g.dart'
        for style in STYLES
    })
    result['preview/catalog'] = root / 'preview' / 'lib' / 'generated_catalog.dart'
    result['dart/entry'] = root / 'lib' / 'mingcute_icons.dart'
    result['dart/static'] = root / 'lib' / 'mingcute_static.dart'
    result['ledger'] = root / 'tool' / 'codepoints.json'
    result['manifest'] = root / 'tool' / 'manifest.json'
    return result


def snapshots(root: Path) -> dict[str, str]:
    paths = artifact_paths(root)
    missing = [key for key, path in paths.items() if not path.is_file()]
    if missing:
        raise AssertionError(f'Generated artifacts missing: {missing}')
    return {key: sha256(path.read_bytes()) for key, path in paths.items()}


def verify(*, source: Path | None = None, ref: str = 'main', min_icons: int = 2200,
           report_path: Path | None = None) -> dict:
    if min_icons < 1:
        raise ValueError('A positive --min-icons is required for rebuild validation')
    if report_path is None:
        report_path = ROOT / 'tool' / '.cache' / 'rebuild_report.json'
    # All build outputs + Git clone are disposable. The checked-out Flutter
    # project and its existing fonts remain untouched even on failure.
    with tempfile.TemporaryDirectory(prefix='mingcute_verify_') as temporary:
        sandbox = Path(temporary)
        if source is None:
            print('[1/5] Cloning official MingCute upstream (fresh Git checkout)...', flush=True)
            checkout = fetch_upstream(sandbox / 'upstream', ref)
        else:
            checkout = source.resolve()
            print(f'[1/5] Using local fixture/source: {checkout}', flush=True)
        project = sandbox / 'flutter_package'
        project.mkdir()
        if not (ROOT / 'UPSTREAM_APACHE_LICENSE.txt').is_file():
            raise FileNotFoundError('Required upstream license missing from the Flutter package')
        shutil.copy2(ROOT / 'UPSTREAM_APACHE_LICENSE.txt', project / 'UPSTREAM_APACHE_LICENSE.txt')
        baseline_ledger = ROOT / 'tool' / 'codepoints.json'
        baseline_assignments: dict[str, str] = {}
        if baseline_ledger.is_file():
            (project / 'tool').mkdir(parents=True, exist_ok=True)
            shutil.copy2(baseline_ledger, project / 'tool' / 'codepoints.json')
            baseline_assignments = json.loads(baseline_ledger.read_text('utf8'))['assignments']

        print('[2/5] Generating all fonts and Dart classes from empty outputs...', flush=True)
        initial = run(checkout, project, min_icons=min_icons)
        if initial['skipped'] or any(initial['generated'].get(s) != initial['counts'][s]
                                     or initial['reused'].get(s) != 0 for s in STYLES):
            raise AssertionError(f'Clean build did not convert all SVGs: {initial}')
        validate(project, min_icons)
        first_hashes = snapshots(project)
        first_ledger = json.loads((project / 'tool/codepoints.json').read_text('utf8'))['assignments']
        if any(first_ledger.get(k) != cp for k, cp in baseline_assignments.items()):
            raise AssertionError('Existing codepoints were reassigned by the clean build')

        print('[3/5] Deleting BOTH fonts, Dart classes and gallery catalogue inside sandbox...', flush=True)
        for key, artifact in artifact_paths(project).items():
            if key.startswith(('font/', 'dart/')) or key == 'preview/catalog':
                artifact.unlink()  # ONLY files under the disposable temp dir.
        if any(path.exists() for key, path in artifact_paths(project).items()
               if key.startswith(('font/', 'dart/')) or key == 'preview/catalog'):
            raise AssertionError('The disposable generated outputs were not fully deleted')

        print('[4/5] Rebuilding from intact ledger/manifest; comparing output hashes...', flush=True)
        rebuilt = run(checkout, project, min_icons=min_icons)
        if rebuilt['skipped'] or any(rebuilt['generated'].get(s) != rebuilt['counts'][s]
                                     or rebuilt['reused'].get(s) != 0 for s in STYLES):
            raise AssertionError(f'Rebuild did not fully regenerate missing fonts: {rebuilt}')
        validate(project, min_icons)
        rebuilt_hashes = snapshots(project)
        mismatched = {key: [first_hashes[key], rebuilt_hashes[key]]
                      for key in first_hashes if first_hashes[key] != rebuilt_hashes[key]}
        if mismatched:
            raise AssertionError(f'Fresh vs missing-artifact rebuild differs: {mismatched}')

        print('[5/5] Running unchanged sync; expecting skip and byte-identical artifacts...', flush=True)
        repeated = run(checkout, project, min_icons=min_icons)
        if not repeated['skipped']:
            raise AssertionError('Unchanged sync unnecessarily regenerated outputs')
        if snapshots(project) != first_hashes:
            raise AssertionError('Unchanged sync modified generated files')

        result = {
            'status': 'PASS',
            'requiredMinimumPerStyle': min_icons,
            'upstreamRevision': initial['sourceRevision'],
            'sourceMode': 'fresh-automatic-git-clone' if source is None else 'local-source',
            'iconsPerStyle': initial['counts'],
            'firstGeneration': initial['generated'],
            'deletedAndRegenerated': rebuilt['generated'],
            'reusedAfterDeletion': rebuilt['reused'],
            'thirdSyncSkipped': repeated['skipped'],
            'byteIdentical': True,
            'originalGeneratedAssetsModified': False,
            'hashes': first_hashes,
            'preservedPriorCodepoints': len(baseline_assignments),
        }
    # The report is written ONLY after the whole clean-room test passed.
    write_if_changed(report_path.resolve(), json.dumps(result, sort_keys=True, indent=2) + '\n')
    print('PASS: independent clone/generation/deletion/regeneration/idempotence.', flush=True)
    print(f"Counts: {result['iconsPerStyle']}; codepoints preserved: {len(baseline_assignments)}", flush=True)
    print(f'Report: {report_path.resolve()}', flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='Optional offline checkout for test fixtures (not needed normally)')
    parser.add_argument('--ref', default='main', help='Official upstream branch for fresh clone')
    parser.add_argument('--min-icons', type=int, default=2200, help='Minimum symbols in EACH variant')
    parser.add_argument('--report', type=Path, default=ROOT / 'tool' / '.cache' / 'rebuild_report.json')
    args = parser.parse_args()
    verify(source=args.source, ref=args.ref, min_icons=args.min_icons, report_path=args.report)


if __name__ == '__main__':
    main()
