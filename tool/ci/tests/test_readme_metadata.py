"""README blocks are offline, traceable and never overwrite manual prose."""
import json
import shutil
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from _helpers import ROOT
sys.path.insert(0, str(ROOT / 'tool'))


class ReadmeMetadataTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'tool').mkdir()
        (self.root / 'pubspec.yaml').write_text('name: mingcute_icons\nversion: 0.1.0\n')
        self.manifest = {'sourceRevision': 'a' * 40, 'upstream': {
            'repository': 'mingcute-design/mingcute-icons', 'version': '3.1.0', 'versionSource': 'release.json'},
            'icons': {'regular': {'home_1': {}}, 'filled': {'home_1': {}}}}
        (self.root / 'tool/manifest.json').write_text(json.dumps(self.manifest))
        self.observation = {'repository': 'mingcute-design/mingcute-icons', 'version': '3.2.0',
                            'revision': 'b' * 40, 'versionSource': 'release.json', 'ref': 'main'}
        (self.root / 'tool/upstream_status.json').write_text(json.dumps(self.observation))
        (self.root / 'README.md').write_text('Manual intro\n<!-- BEGIN MINGCUTE BADGES -->\nold\n<!-- END MINGCUTE BADGES -->\n'
            'Keep my prose\n<!-- BEGIN MINGCUTE STATUS -->\nold\n<!-- END MINGCUTE STATUS -->\nManual end\n')

    def test_blocks_are_idempotent_and_preserve_manual_prose(self):
        from readme_metadata import update
        self.assertTrue(update(self.root, write=True))
        text = (self.root / 'README.md').read_text()
        self.assertIn('Manual intro', text)
        self.assertIn('Keep my prose', text)
        self.assertIn('Manual end', text)
        self.assertFalse(update(self.root, write=True))
        self.assertFalse(update(self.root))
        self.assertIn('0.1.0', text)
        self.assertIn('3.1.0', text)
        self.assertIn('3.2.0', text)
        self.assertIn('Update available', text)
        self.assertIn('https://www.mingcute.com/', text)
        self.assertIn('https://github.com/mingcute-design/mingcute-icons', text)
        self.assertNotIn('github/actions', text)
        self.assertNotIn('https://pub.dev/packages/', text)
        self.assertNotIn('owner/', text)
        self.assertIn('style=for-the-badge', text)
        self.assertIn('labelColor=', text)
        self.assertIn('color=555555', text)

    def test_confirmed_repository_enables_branded_ci_and_absolute_banner(self):
        from readme_metadata import update, banner_line
        repo = 'https://github.com/Bruno0416/mingcute-flutter'
        spec = self.root / 'pubspec.yaml'
        spec.write_text(spec.read_text() + 'repository: ' + repo + '\n')
        update(self.root, write=True)
        text = (self.root / 'README.md').read_text()
        self.assertIn('github/actions/workflow/status/Bruno0416/mingcute-flutter/ci.yml', text)
        self.assertIn('style=for-the-badge', text)
        self.assertIn('labelColor=2088FF', text)
        self.assertIn('color=555555', text)
        self.assertIn(f'{repo}/blob/main/pubspec.yaml', text)
        self.assertIn('https://raw.githubusercontent.com/Bruno0416/mingcute-flutter/main/',
                      banner_line(self.root))

    def test_wrapper_only_change_does_not_reassign_upstream_version(self):
        from readme_metadata import update
        original = (self.root / 'tool/manifest.json').read_bytes()
        (self.root / 'pubspec.yaml').write_text('name: mingcute_icons\nversion: 0.2.0\n')
        update(self.root, write=True)
        self.assertEqual(original, (self.root / 'tool/manifest.json').read_bytes())
        text = (self.root / 'README.md').read_text()
        self.assertIn('0.2.0', text)
        self.assertIn('3.1.0', text)

    def test_missing_latest_is_unknown_and_never_borrowed_from_synced(self):
        from readme_metadata import update
        (self.root / 'tool/upstream_status.json').unlink()
        update(self.root, write=True)
        self.assertIn('Unknown', (self.root / 'README.md').read_text())

    def test_refresh_failure_and_missing_markers_never_destroy_readme_or_cache(self):
        from readme_metadata import update
        text = (self.root / 'README.md').read_bytes()
        cache = (self.root / 'tool/upstream_status.json').read_bytes()
        with patch('readme_metadata.latest', side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):
                update(self.root, write=True, refresh=True)
        self.assertEqual(text, (self.root / 'README.md').read_bytes())
        self.assertEqual(cache, (self.root / 'tool/upstream_status.json').read_bytes())
        (self.root / 'README.md').write_text('manual README without markers')
        with self.assertRaises(ValueError):
            update(self.root, write=True)

    def test_latest_older_than_synced_is_not_reported_as_current(self):
        from readme_metadata import update
        self.observation['version'] = '3.0.0'
        (self.root / 'tool/upstream_status.json').write_text(json.dumps(self.observation))
        update(self.root, write=True)
        self.assertIn('Refresh required', (self.root / 'README.md').read_text())


class BannerLayoutTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        shutil.copytree(ROOT / 'doc/assets/branding', self.root / 'doc/assets/branding')
        shutil.copy(ROOT / 'THIRD_PARTY_NOTICES.md', self.root)
        from readme_metadata import BANNER_LINE
        self.banner = BANNER_LINE
        self.title = '# MingCute Icons for Flutter'
        self.badges = '<!-- BEGIN MINGCUTE BADGES -->\n[![badge](https://img.shields.io/test)](LICENSE)\n<!-- END MINGCUTE BADGES -->'
        self.notice = '> **Unofficial Flutter package**\n> Independent adapter, MingCute Design, Apache 2.0.'
        self.intro = 'MingCute Core Regular and Filled as native Flutter `IconData`.'
        self.valid = '\n\n'.join([self.title, self.badges, self.banner, self.notice, self.intro]) + '\n'

    def check(self, text):
        from readme_metadata import check_banner
        (self.root / 'README.md').write_text(text)
        check_banner(self.root)

    def test_title_badges_banner_notice_introduction_order_passes(self):
        self.check(self.valid)

    def test_structural_layout_regressions_fail(self):
        variants = [
            self.banner + '\n\n' + self.valid.replace(self.banner + '\n\n', ''),
            self.valid.replace(self.notice, ''),
            self.valid.replace(self.badges + '\n\n', '').replace(self.intro, self.badges + '\n\n' + self.intro),
            self.valid + '\n' + self.banner,
            self.valid + '\n' + self.title,
            self.valid + '\n' + self.badges,
            self.valid.replace(self.banner, self.banner.replace('mingcute-banner.png', 'other.png')),
            self.valid.replace(self.notice, 'Intervening text\n\n' + self.notice),
            self.valid + '\n[![duplicate](https://img.shields.io/test)](LICENSE)',
            self.valid + '\nhttps://github.com/YOUR_USERNAME/your-repo',
        ]
        for index, text in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.check(text)

    def test_modified_banner_and_wrong_attribution_hash_fail(self):
        banner = self.root / 'doc/assets/branding/mingcute-banner.png'
        original = banner.read_bytes()
        banner.write_bytes(original + b'altered')
        with self.assertRaises(ValueError):
            self.check(self.valid)
        banner.write_bytes(original)
        attribution = self.root / 'doc/assets/branding/ATTRIBUTION.json'
        data = json.loads(attribution.read_text())
        data['sha256'] = '0' * 64
        attribution.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            self.check(self.valid)
