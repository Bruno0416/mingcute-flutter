#!/usr/bin/env python3
"""One-time, repeatable migration from mingcute_icons_kit to mingcute_flutter.

Keeps the entire locally generated icon catalogue, stable codepoints, and glyphs.
Does not fetch the network or regenerate any SVGs. The original font files are
backed up under tool/.cache/migration_backup and can be restored if necessary.
"""
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

from fontTools.ttLib import TTFont
from sync_icons import ROOT, STYLES, dump_json, sha256, write_if_changed

OLD_PACKAGE = 'mingcute_icons_kit'
NEW_PACKAGE = 'mingcute_flutter'
LEGACY_FAMILIES = {'regular': 'MingCuteKitRegular', 'filled': 'MingCuteKitFilled'}


def assert_configuration(root: Path) -> None:
    root_pubspec = root / 'pubspec.yaml'
    preview_pubspec = root / 'preview/pubspec.yaml'
    for path in (root_pubspec, preview_pubspec):
        if not path.is_file():
            raise FileNotFoundError(f'Missing {path}')
    if not re.search(r'^name:\s*mingcute_flutter\s*$', root_pubspec.read_text('utf8'), re.M):
        raise RuntimeError('Package pubspec must declare name: mingcute_flutter. Apply the overlay first.')
    if not re.search(r'^  mingcute_flutter:\s*$', preview_pubspec.read_text('utf8'), re.M):
        raise RuntimeError('preview/pubspec.yaml must depend on mingcute_flutter. Apply the overlay first.')


def migrate_font(old: Path, new: Path, old_family: str, new_family: str, backup: Path) -> bool:
    if new.exists():
        with TTFont(new) as font:
            if not font.getBestCmap():
                raise ValueError(f'Empty font at {new}')
        return False
    if not old.is_file():
        raise FileNotFoundError(f'Neither new font {new} nor legacy font {old} exists. Run the SVG generator.')
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copy2(old, backup)
    font = TTFont(old, recalcTimestamp=False)
    try:
        expected_cmap = dict(font.getBestCmap() or {})
        if not expected_cmap:
            raise ValueError(f'Empty legacy font: {old}')
        for record in font['name'].names:
            if record.nameID in (1, 4, 6, 16):
                original = record.toUnicode()
                changed = original.replace(old_family, new_family)
                if changed != original:
                    record.string = changed.encode(record.getEncoding())
        font.recalcTimestamp = False
        new.parent.mkdir(parents=True, exist_ok=True)
        tmp = new.with_suffix('.tmp.ttf')
        try:
            font.save(tmp)
            with TTFont(tmp) as check:
                if dict(check.getBestCmap() or {}) != expected_cmap:
                    raise ValueError(f'Codepoints changed while migrating {old.name}')
            tmp.replace(new)
        finally:
            tmp.unlink(missing_ok=True)
    finally:
        font.close()
    return True


def migrate(root: Path = ROOT) -> dict:
    root = root.resolve()
    assert_configuration(root)
    old_lib = root / 'lib/mingcute_icons_kit.dart'
    new_lib = root / 'lib/mingcute_icons.dart'
    if not new_lib.exists():
        if not old_lib.exists():
            raise FileNotFoundError('No lib/mingcute_icons.dart or legacy library found.')
        write_if_changed(new_lib, old_lib.read_text('utf8').replace('MingCute Icons Kit', 'MingCute Icons'))
    backup_dir = root / 'tool/.cache/migration_backup'
    if old_lib.exists():
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / old_lib.name
        if not backup.exists():
            shutil.copy2(old_lib, backup)
        old_lib.unlink()  # Otherwise analyzer sees duplicate part ownership.

    updated_files = []
    paths = [*(root / f'lib/src/generated/{style}_icons.g.dart' for style in STYLES),
             root / 'preview/lib/generated_catalog.dart']
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f'Missing local generated data: {path}')
        content = path.read_text('utf8')
        migrated = (content.replace('mingcute_icons_kit.dart', 'mingcute_icons.dart')
                           .replace('package:mingcute_icons_kit/', 'package:mingcute_flutter/')
                           .replace("fontPackage: 'mingcute_icons_kit'", "fontPackage: 'mingcute_flutter'")
                           .replace('MingCuteKitRegular', 'MingCuteRegular')
                           .replace('MingCuteKitFilled', 'MingCuteFilled'))
        if write_if_changed(path, migrated):
            updated_files.append(path.relative_to(root).as_posix())

    migrated_fonts = []
    manifest_path = root / 'tool/manifest.json'
    for style, (_, family) in STYLES.items():
        legacy = LEGACY_FAMILIES[style]
        old = root / 'assets/fonts' / (legacy + '.ttf')
        new = root / 'assets/fonts' / (family + '.ttf')
        if migrate_font(old, new, legacy, family, backup_dir / old.name):
            migrated_fonts.append(style)

    if manifest_path.exists():
        import json
        manifest = json.loads(manifest_path.read_text('utf8'))
        if 'artifactSha256' in manifest:
            manifest['artifactSha256'] = {
                style: sha256((root / 'assets/fonts' / (family + '.ttf')).read_bytes())
                for style, (_, family) in STYLES.items()
            }
            write_if_changed(manifest_path, dump_json(manifest))

    # Preserve old fonts until successful renaming of BOTH variants above.
    for legacy in LEGACY_FAMILIES.values():
        (root / 'assets/fonts' / (legacy + '.ttf')).unlink(missing_ok=True)
    return {'updatedGenerated': updated_files, 'convertedFonts': migrated_fonts,
            'preservedGlyphs': True, 'backups': str(backup_dir)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT, help='Flutter package root')
    args = parser.parse_args()
    result = migrate(args.output)
    print('Migration complete. Existing glyphs and codepoints preserved.')
    print(f"Updated generated Dart files: {len(result['updatedGenerated'])}.")
    print(f"Renamed font files: {result['convertedFonts'] or 'already migrated'}.")


if __name__ == '__main__':
    main()
