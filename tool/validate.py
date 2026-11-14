#!/usr/bin/env python3
"""Strict release validation: all manifest entries, font cmap, Dart and sources."""
from __future__ import annotations
import argparse
import json
import re
import hashlib
from pathlib import Path
from fontTools.ttLib import TTFont
from sync_icons import ROOT, STYLES, PACKAGE, identifier, render_dart, render_entry, render_preview, render_static
from upstream_metadata import REPOSITORY, SHA, SEMVER


def validate(root: Path = ROOT, minimum: int = 0) -> dict:
    manifest = json.loads((root / 'tool/manifest.json').read_text('utf8'))
    upstream = manifest.get('upstream', {})
    assert upstream.get('repository') == REPOSITORY and upstream.get('versionSource') == 'release.json', 'Missing upstream provenance'
    if manifest['sourceRevision'] == 'local-source':
        assert upstream.get('version') is None, 'Local sources cannot claim a verified release version'
    else:
        assert SHA.fullmatch(manifest['sourceRevision']), 'Invalid upstream Git SHA'
        assert isinstance(upstream.get('version'), str) and SEMVER.fullmatch(upstream['version']), 'Invalid upstream version'
    ledger = json.loads((root / 'tool/codepoints.json').read_text('utf8'))['assignments']
    assert set(manifest['icons']['regular']) == set(manifest['icons']['filled']), 'Variant parity mismatch'
    all_cps = [int(v, 16) for v in ledger.values()]
    assert len(all_cps) == len(set(all_cps)), 'Collision in codepoints ledger'
    assert set(ledger) >= set().union(*(set(v) for v in manifest['icons'].values()))
    stats = {}
    for style, (_, family) in STYLES.items():
        records = manifest['icons'][style]
        assert len(records) >= minimum, f'{style} is incomplete: {len(records)} < {minimum}'
        assert records, 'Empty manifest'
        cps = {int(ledger[k], 16) for k in records}
        font = TTFont(root / 'assets/fonts' / f'{family}.ttf')
        assert hashlib.sha256((root / 'assets/fonts' / f'{family}.ttf').read_bytes()).hexdigest() == manifest['artifactSha256'][style], 'Font hash differs from manifest'
        assert font['name'].getDebugName(1) == family, 'Font family mismatch'
        cmap = font.getBestCmap()
        assert set(cmap) == cps, f'{style}: cmap does not match metadata'
        assert font['head'].unitsPerEm == 1024
        assert font['hhea'].ascent == 896 and font['hhea'].descent == -128
        dart = (root / 'lib/src/generated' / f'{style}_icons.g.dart').read_text('utf8')
        registry = {'assignments': ledger}
        assert dart == render_dart(style, records, registry), f'{style}: stale generated Dart'
        for name, info in records.items():
            assert name == identifier(name)
            assert info['codepoint'] == ledger[name]
            assert re.search(rf'\bstatic const IconData {re.escape(name)}\b', dart), f'{style} Dart {name}'
            glyph = font['glyf'][cmap[int(ledger[name], 16)]]
            assert glyph.numberOfContours > 0, f'Empty {style}/{name}'
            assert font['hmtx'][cmap[int(ledger[name], 16)]][0] == 1024
        font.close()
        stats[style] = len(records)
    assert (root / 'preview/lib/generated_catalog.dart').exists()
    assert (root / 'preview/lib/generated_catalog.dart').read_text('utf8') == render_preview(manifest['icons'])
    assert (root / 'lib/mingcute_icons.dart').read_text('utf8') == render_entry()
    assert (root / 'lib/mingcute_static.dart').read_text('utf8') == render_static(manifest['icons'], {'assignments': ledger}), 'Static API parity mismatch'
    assert f"fontPackage: '{PACKAGE}'" in (root / 'lib/src/generated/regular_icons.g.dart').read_text()
    assert (root / 'UPSTREAM_APACHE_LICENSE.txt').exists()
    print(f'PASS font/codepoint/Dart parity: {stats}')
    return stats


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--min-icons', type=int, default=0)
    parser.add_argument('--output', type=Path, default=ROOT)
    args = parser.parse_args()
    validate(args.output, args.min_icons)
