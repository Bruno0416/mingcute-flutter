"""SemVer helper: consistency checks, previews and explicit writes only."""
import json
from pathlib import Path
import tempfile
import unittest

from _helpers import make_project
import version as ver


class VersionTest(unittest.TestCase):
    def project(self, **kwargs):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return make_project(Path(temp.name), **kwargs)

    def test_check_detects_mismatch_duplicates_and_order(self):
        self.assertEqual('0.2.0', ver.check(self.project()))
        with self.assertRaises(ValueError):
            ver.check(self.project(version='0.3.0'))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            ver.check(self.project(changelog='## 0.2.0\n\n- a\n\n## 0.2.0\n\n- b\n'))
        with self.assertRaisesRegex(ValueError, 'descending'):
            ver.check(self.project(changelog='## 0.2.0\n\n- a\n\n## 0.3.0\n\n- b\n'))

    def test_bump_arithmetic_and_monotonicity(self):
        self.assertEqual('0.2.1', ver.bumped('0.2.0', 'patch', None))
        self.assertEqual('0.3.0', ver.bumped('0.2.0', 'minor', None))
        self.assertEqual('1.0.0', ver.bumped('0.2.0', 'major', None))
        self.assertEqual('0.2.5', ver.bumped('0.2.0', None, '0.2.5'))
        for bad in ('0.2.0', '0.1.9', '1.0'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                ver.bumped('0.2.0', None, bad)

    def test_preview_writes_nothing_and_write_requires_real_notes(self):
        root = self.project()
        before = (root / 'pubspec.yaml').read_text(), (root / 'CHANGELOG.md').read_text()
        self.assertEqual(0, ver.main(['--root', str(root), 'bump', '--part', 'minor']))
        self.assertEqual(before, ((root / 'pubspec.yaml').read_text(), (root / 'CHANGELOG.md').read_text()))
        self.assertEqual(1, ver.main(['--root', str(root), 'bump', '--part', 'minor', '--write']))
        empty = root / 'notes.md'
        empty.write_text('  \n')
        self.assertEqual(1, ver.main(['--root', str(root), 'bump', '--part', 'minor', '--write', '--notes', str(empty)]))
        self.assertEqual(before, ((root / 'pubspec.yaml').read_text(), (root / 'CHANGELOG.md').read_text()))

    def test_write_updates_pubspec_and_changelog_together(self):
        root = self.project()
        notes = root / 'notes.md'
        notes.write_text('- Real note.\n')
        self.assertEqual(0, ver.main(['--root', str(root), 'bump', '--part', 'patch', '--write', '--notes', str(notes)]))
        self.assertEqual('0.2.1', ver.check(root))
        self.assertTrue((root / 'CHANGELOG.md').read_text().index('## 0.2.1') < (root / 'CHANGELOG.md').read_text().index('## 0.2.0'))

    def test_suggest_maps_api_changes_to_parts(self):
        def manifest(names, cp=None):
            icons = {s: {n: {'codepoint': (cp or {}).get(n, 'E001')} for n in names} for s in ('regular', 'filled')}
            return {'icons': icons}
        root = self.project()
        (root / 'tool').mkdir()
        baseline = root / 'old.json'
        baseline.write_text(json.dumps(manifest(['a', 'b'])))
        for names, cps, expected in ((['a', 'b'], None, 'patch'), (['a', 'b', 'c'], None, 'minor'),
                                     (['a'], None, 'major'), (['a', 'b'], {'b': 'E999'}, 'major')):
            (root / 'tool/manifest.json').write_text(json.dumps(manifest(names, cps)))
            self.assertEqual(expected, ver.suggest(root, baseline)[0], names)


if __name__ == '__main__':
    unittest.main()
