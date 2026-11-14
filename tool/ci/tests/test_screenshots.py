"""Screenshot manifest/check: missing, corrupt, wrong size, stale and legacy-branded images fail."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from _helpers import ROOT
import sys
sys.path.insert(0, str(ROOT / 'tool'))
import screenshots as shots

COPY = [*shots.INPUT_FILES, 'tool/manifest.json']


class ScreenshotCheckTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name in COPY:
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / name, self.root / name)
        shutil.copytree(ROOT / 'doc/assets/screenshots', self.root / 'doc/assets/screenshots')
        self.manifest = self.root / 'doc/assets/screenshots/manifest.json'

    def problems(self):
        return shots.check(self.root)

    def test_committed_screenshots_are_valid(self):
        self.assertEqual([], self.problems())

    def test_missing_image_and_manifest(self):
        (self.root / 'doc/assets/screenshots/hero-dark.png').unlink()
        self.assertTrue(any('hero-dark.png is missing' in p for p in self.problems()))
        self.manifest.unlink()
        self.assertEqual(['doc/assets/screenshots/manifest.json is missing'], self.problems())

    def test_corrupt_and_truncated_png(self):
        image = self.root / 'doc/assets/screenshots/regular.png'
        data = bytearray(image.read_bytes())
        data[100] ^= 0xFF
        image.write_bytes(bytes(data))
        self.assertTrue(any('corrupt' in p or 'differs from the manifest' in p for p in self.problems()))
        image.write_bytes(image.read_bytes()[:60])
        self.assertTrue(any('truncated' in p or 'corrupt' in p or 'not a PNG' in p for p in self.problems()))
        image.write_bytes(b'not a png')
        self.assertTrue(any('not a PNG' in p for p in self.problems()))

    def test_wrong_dimensions(self):
        scenes = self.root / 'tool/screenshot_capture/scenes.json'
        data = json.loads(scenes.read_text())
        data['viewport']['width'] = 999
        scenes.write_text(json.dumps(data))
        problems = self.problems()
        self.assertTrue(any('expected 1998x1600' in p for p in problems))

    def test_obsolete_after_capture_code_or_artwork_change(self):
        (self.root / 'preview/lib/capture.dart').write_text('// changed\n')
        self.assertTrue(any('obsolete' in p for p in self.problems()))

    def test_obsolete_when_a_displayed_icon_artwork_changes_but_unrelated_icons_do_not(self):
        path = self.root / 'tool/manifest.json'
        manifest = json.loads(path.read_text())
        manifest['icons']['regular']['abs']['sha256'] = '0' * 64  # not displayed in any scene
        manifest['icons']['regular']['aiming']['sha256'] = '0' * 64
        path.write_text(json.dumps(manifest))
        self.assertEqual([], self.problems())
        manifest['icons']['regular']['home_1']['sha256'] = '0' * 64  # displayed in several scenes
        path.write_text(json.dumps(manifest))
        self.assertTrue(any('obsolete' in p for p in self.problems()))

    def test_missing_icon_name_and_wrong_style(self):
        data = json.loads(self.manifest.read_text())
        data['screenshots'][0]['icons'].append('not_an_icon')
        self.manifest.write_text(json.dumps(data))
        self.assertTrue(any("'not_an_icon' does not exist" in p for p in self.problems()))

    def test_params_mismatch_and_legacy_branding(self):
        data = json.loads(self.manifest.read_text())
        data['screenshots'][0]['params']['theme'] = 'light'
        data['screenshots'][1]['title'] = 'Morph Expressive demo'
        self.manifest.write_text(json.dumps(data))
        problems = self.problems()
        self.assertTrue(any('params differ' in p for p in problems))
        self.assertTrue(any('legacy branding' in p for p in problems))

    def test_catalogue_must_keep_the_verified_baseline(self):
        path = self.root / 'tool/manifest.json'
        manifest = json.loads(path.read_text())
        for name in list(manifest['icons']['filled'])[:50]:
            del manifest['icons']['filled'][name]
        path.write_text(json.dumps(manifest))
        self.assertTrue(any('catalogue has only' in p for p in self.problems()))

    def test_scene_count_inside_pubspec_limit(self):
        self.assertLessEqual(len(json.loads((ROOT / 'tool/screenshot_capture/scenes.json').read_text())['scenes']), 10)


if __name__ == '__main__':
    unittest.main()
