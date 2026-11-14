"""Documentation guard against intentionally broken fixtures (copies of the real docs)."""
from pathlib import Path
import shutil
import tempfile
import unittest

from _helpers import ROOT
import check_docs

FILES = [*check_docs.REQUIRED_DOCS, 'tool/manifest.json', 'pubspec.yaml']
SHOTS = sorted((ROOT / 'doc/assets/screenshots').glob('*.png'))


class DocsGuardTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name in FILES:
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / name, self.root / name)
        (self.root / 'doc/assets/screenshots').mkdir(parents=True, exist_ok=True)
        for shot in SHOTS:
            shutil.copy(shot, self.root / 'doc/assets/screenshots' / shot.name)

    def errors(self):
        return check_docs.check(self.root)[0]

    def edit(self, name, old, new):
        path = self.root / name
        text = path.read_text()
        self.assertIn(old, text)
        path.write_text(text.replace(old, new))

    def test_real_documents_pass_with_confirmed_repository_metadata(self):
        errors, warnings = check_docs.check(self.root)
        self.assertEqual([], errors)
        self.assertFalse(any('PENDING' in w for w in warnings))

    def test_inherited_identity_is_rejected(self):
        for token in ('Morph', 'Fluent', 'mingcute_icons_kit'):
            with self.subTest(token=token):
                (self.root / 'doc/GETTING_STARTED.md').write_text(
                    (ROOT / 'doc/GETTING_STARTED.md').read_text() + f'\nSee {token}.\n')
                self.assertTrue(any('legacy identity' in e for e in self.errors()))

    def test_readme_api_examples_must_exist_in_the_generated_api(self):
        for style in ('regular', 'filled', 'line', 'invalid'):
            path = self.root / 'doc/GETTING_STARTED.md'
            original = path.read_text()
            path.write_text(original + f'\nMingCute.{style}.icon_that_does_not_exist\n')
            self.assertTrue(any('icon_that_does_not_exist' in e for e in self.errors()))
            path.write_text(original)

    def test_obsolete_api_is_rejected_but_font_names_are_allowed(self):
        path = self.root / 'doc/GETTING_STARTED.md'
        original = path.read_text()
        for ref in ('MingCuteRegular.home_1', 'MingCuteFilled.heart',
                    'MingCuteIcons.regular.home_1', 'MingCuteIcons.line.heart'):
            path.write_text(original + '\n' + ref)
            self.assertTrue(any('obsolete API' in e for e in self.errors()))
        path.write_text(original + '\nMingCuteRegular.ttf MingCuteFilled\n'
                        'MingCute.regular.home_1 MingCute.filled.heart\n')
        self.assertEqual([], self.errors())

    def test_credits_install_and_counts_are_required(self):
        self.edit('README.md', 'flutter pub add mingcute_flutter', 'dart pub add other')
        self.assertTrue(any('install command' in e for e in self.errors()))

    def test_stale_counts_are_rejected(self):
        self.edit('README.md', '| Regular icons | 2,263 |', '| Regular icons | 1,000 |')
        self.edit('README.md', '| Total glyphs | 4,526 |', '| Total glyphs | 2,000 |')
        self.assertTrue(any('stale generated' in e for e in self.errors()))

    def test_broken_remote_screenshot_is_rejected(self):
        self.edit('README.md', 'doc/assets/screenshots/hero-dark.png', 'doc/assets/screenshots/missing.png')
        self.assertTrue(any('missing/case-different' in e for e in self.errors()))

    def test_raw_urls_need_matching_repository_branch_and_exact_case(self):
        original = (self.root / 'README.md').read_text()
        readme = self.root / 'README.md'
        url = 'https://raw.githubusercontent.com/Bruno0416/mingcute-flutter/main/doc/assets/screenshots/hero-dark.png'
        self.assertIn(url, original)
        self.assertEqual([], self.errors())
        readme.write_text(original.replace(url, url.replace('/main/', '/dev/')))
        self.assertTrue(any('main branch' in e for e in self.errors()))
        readme.write_text(original.replace(url, url.replace('Bruno0416/', 'another/')))
        self.assertTrue(any('differs from pubspec repository' in e for e in self.errors()))
        readme.write_text(original.replace(url, url.replace('hero-dark.png', 'Hero-Dark.png')))
        self.assertTrue(any('missing/case-different' in e for e in self.errors()))
        readme.write_text(original)
        spec = self.root / 'pubspec.yaml'
        spec.write_text(spec.read_text().replace(
            'repository: https://github.com/Bruno0416/mingcute-flutter\n', ''))
        self.assertTrue(any('no confirmed repository' in e for e in self.errors()))

    def test_licence_notices_are_required(self):
        self.edit('THIRD_PARTY_NOTICES.md', 'MingCute Design', 'someone')
        self.assertTrue(any('THIRD_PARTY_NOTICES' in e for e in self.errors()))

    def test_banner_hash_and_immediate_unofficial_notice_are_required(self):
        banner = self.root / 'doc/assets/branding/mingcute-banner.png'
        original = banner.read_bytes()
        banner.write_bytes(original + b'changed')
        self.assertTrue(any('banner' in e for e in self.errors()))
        banner.write_bytes(original)
        self.edit('README.md', '> **Unofficial Flutter package**', '> Independent package')
        self.assertTrue(any('unofficial notice' in e for e in self.errors()))

    def test_stale_generated_version_badges_are_rejected(self):
        self.edit('README.md', 'message=0.1.0', 'message=9.9.9')
        self.assertTrue(any('stale generated' in e for e in self.errors()))

    def test_banner_before_title_and_duplicate_banner_are_rejected(self):
        from readme_metadata import banner_line
        path = self.root / 'README.md'
        original = path.read_text()
        banner = banner_line(self.root)
        for text in (banner + '\n\n' + original.replace(banner + '\n\n', ''),
                     original + '\n' + banner):
            path.write_text(text)
            self.assertTrue(any('README' in e for e in self.errors()))

    def test_static_documented_names_are_checked_against_manifest(self):
        path = self.root / 'doc/GETTING_STARTED.md'
        path.write_text(path.read_text() + '\nMingCuteRegularConst.nonexistent_icon\n')
        self.assertTrue(any('nonexistent_icon' in e for e in self.errors()))


if __name__ == '__main__':
    unittest.main()
