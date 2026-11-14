"""Regression tests for the R1 package rename, native preview bootstrapping, and upstream Git cache."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tool'))
from fontTools.ttLib import TTFont
from repair_project import migrate, LEGACY_FAMILIES
from sync_icons import run, fetch_upstream, STYLES, sha256
from validate import validate

FIXTURE = ROOT / 'tool/tests/fixtures/upstream'


class UpgradeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / 'project'
        self.out.mkdir()
        for name in ('pubspec.yaml', 'UPSTREAM_APACHE_LICENSE.txt'):
            shutil.copy2(ROOT / name, self.out / name)
        shutil.copytree(ROOT / 'preview', self.out / 'preview', ignore=shutil.ignore_patterns('linux','web','.dart_tool','build'))
        (self.out / 'lib').mkdir()
        shutil.copy2(ROOT / 'lib/mingcute_icons.dart', self.out / 'lib/mingcute_icons.dart')
        run(FIXTURE, self.out)

    def test_migration_keeps_glyphs_and_assignments_with_legacy_fonts(self):
        ledger_before = (self.out / 'tool/codepoints.json').read_bytes()
        for style, (_, family) in STYLES.items():
            new = self.out / 'assets/fonts' / f'{family}.ttf'
            old = self.out / 'assets/fonts' / f'{LEGACY_FAMILIES[style]}.ttf'
            font = TTFont(new)
            for record in font['name'].names:
                if record.nameID in (1,4,6,16):
                    val = record.toUnicode().replace(family, LEGACY_FAMILIES[style])
                    record.string = val.encode(record.getEncoding())
            font.save(old)
            font.close()
            new.unlink()
            generated = self.out / f'lib/src/generated/{style}_icons.g.dart'
            generated.write_text(generated.read_text().replace("part of '../../mingcute_icons.dart';", "part of '../../mingcute_icons_kit.dart';")
                                 .replace("fontPackage: 'mingcute_flutter'", "fontPackage: 'mingcute_icons_kit'")
                                 .replace(family, LEGACY_FAMILIES[style]))
        cat = self.out / 'preview/lib/generated_catalog.dart'
        cat.write_text(cat.read_text().replace('mingcute_flutter/mingcute_icons.dart','mingcute_icons_kit/mingcute_icons_kit.dart'))
        prior = json.loads((self.out / 'tool/manifest.json').read_text())
        for style in STYLES:
            prior['artifactSha256'][style] = sha256((self.out / 'assets/fonts' / f'{LEGACY_FAMILIES[style]}.ttf').read_bytes())
        (self.out / 'tool/manifest.json').write_text(json.dumps(prior))
        self.assertEqual(migrate(self.out)['convertedFonts'], ['regular', 'filled'])
        self.assertEqual(migrate(self.out)['convertedFonts'], [])
        self.assertEqual(ledger_before, (self.out / 'tool/codepoints.json').read_bytes())
        self.assertEqual(validate(self.out), {'regular': 4, 'filled': 4})
        self.assertTrue(run(FIXTURE, self.out)['skipped'])

    def test_bootstrap_uses_flutter_create_and_pub_get_once(self):
        # Fake flutter CLI is deliberate: no SDK required for validating calls.
        mockbin = self.out / 'fakebin'
        mockbin.mkdir()
        flutter = mockbin / 'flutter'
        flutter.write_text('#!/bin/sh\necho "$@" >> "' + str(self.out / 'flutter_calls') + '"\n'
                           'if [ "$1" = "create" ]; then mkdir -p linux web; touch linux/CMakeLists.txt web/index.html; fi\n')
        flutter.chmod(0o755)
        environment = dict(os.environ, PATH=str(mockbin) + os.pathsep + os.environ.get('PATH',''))
        command = [sys.executable, str(ROOT / 'tool/bootstrap_preview.py'), '--output', str(self.out), '--prepare-only']
        subprocess.run(command, check=True, env=environment, capture_output=True, text=True)
        subprocess.run(command, check=True, env=environment, capture_output=True, text=True)
        calls = (self.out / 'flutter_calls').read_text().splitlines()
        self.assertEqual(len([c for c in calls if c.startswith('create ')]), 1)
        self.assertEqual(len([c for c in calls if c.startswith('pub get')]), 2)

    def test_fetch_upstream_uses_isolated_clone_and_updates(self):
        git_root = Path(self.temp.name) / 'git-remote'
        shutil.copytree(FIXTURE, git_root)
        subprocess.run(['git','init','-b','main',str(git_root)],check=True,stdout=subprocess.DEVNULL)
        subprocess.run(['git','-C',str(git_root),'add','.'],check=True)
        subprocess.run(['git','-C',str(git_root),'-c','user.email=test@example.com',
                        '-c','user.name=Test','commit','-qm','baseline'],check=True)
        cache = Path(self.temp.name) / 'cache/upstream'
        with patch('sync_icons.REPO_URL', git_root.as_uri()):
            self.assertEqual(fetch_upstream(cache,'main'),cache.resolve())
            self.assertEqual(fetch_upstream(cache,'main'),cache.resolve())
            self.assertEqual(len(list((cache/'packages/svg/core-filled').glob('*.svg'))),4)
            with self.assertRaises(ValueError):
                fetch_upstream(cache,'../oops')


if __name__ == '__main__':
    unittest.main()
