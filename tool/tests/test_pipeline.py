import json
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tool'))
from sync_icons import collect, convert_svg, identifier, run, STYLES
from validate import validate

FIXTURE = ROOT / 'tool/tests/fixtures/upstream'

class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / 'out'
        self.out.mkdir()
        shutil.copy(ROOT / 'UPSTREAM_APACHE_LICENSE.txt', self.out)

    def test_identifiers_preserve_upstream_semantics(self):
        self.assertEqual(identifier('home-1'), 'home_1')
        self.assertEqual(identifier('mgc-home-1'), 'mgc_home_1')
        self.assertEqual(identifier('mgc-home-1', 'mgc-'), 'home_1')
        self.assertEqual(identifier('class'), 'icon_class')
        self.assertEqual(identifier('1password'), 'icon_1password')

    def test_real_upstream_svg_sample_parses_into_nonempty_contours(self):
        raw = (FIXTURE / 'packages/svg/core-regular/home-1.svg').read_bytes()
        self.assertGreater(convert_svg(raw).numberOfContours, 0)
        with self.assertRaises(ValueError):
            convert_svg(b'<svg viewBox="0 0 24 24"><mask id="m"/></svg>')

    def test_roundtrip_and_idempotency(self):
        first = run(FIXTURE, self.out)
        self.assertEqual(first['counts'], {'regular': 4, 'filled': 4})
        self.assertFalse(first['skipped'])
        from fontTools.ttLib import TTFont
        for style, (_, family) in STYLES.items():
            ft = TTFont(self.out / 'assets/fonts' / f'{family}.ttf')
            self.assertEqual(len(ft.getBestCmap()), 4)
            self.assertEqual(set(ft.getBestCmap()), {0xE36C,0xE58C,0xE006,0xE354})
            ft.close()
        hashes = {s: (self.out / 'assets/fonts' / (f[1] + '.ttf')).read_bytes() for s,f in STYLES.items()}
        second = run(FIXTURE, self.out)
        self.assertTrue(second['skipped'])
        for s,(_,fam) in STYLES.items():
            self.assertEqual(hashes[s], (self.out / 'assets/fonts' / f'{fam}.ttf').read_bytes())
        validate(self.out)

    def test_incremental_reuse_preserves_codepoints(self):
        source = Path(self.tmp.name) / 'upstream'
        shutil.copytree(FIXTURE, source)
        run(source, self.out)
        target = source / 'packages/svg/core-regular/add.svg'
        target.write_text(target.read_text().replace('M11 3H13', 'M11 4H13'))
        next_report = run(source, self.out)
        self.assertEqual(next_report['modified']['regular'], ['add'])
        self.assertEqual(next_report['generated']['regular'], 1)
        self.assertEqual(next_report['reused']['regular'], 3)
        self.assertEqual(next_report['generated']['filled'], 0)
        self.assertEqual(next_report['reused']['filled'], 4)
        previous_codes = json.loads((self.out / 'tool/codepoints.json').read_text())['assignments']
        (source / 'packages/svg/core-regular/heart.svg').unlink()
        (source / 'packages/svg/core-filled/heart.svg').unlink()
        run(source, self.out)
        now_codes = json.loads((self.out / 'tool/codepoints.json').read_text())['assignments']
        self.assertEqual(previous_codes, now_codes)
        validate(self.out)

    def test_incomplete_source_gate(self):
        with self.assertRaises(RuntimeError):
            run(FIXTURE, self.out, min_icons=2000)

    def test_generated_api_is_private_with_single_public_entry(self):
        run(FIXTURE, self.out)
        entry = (self.out / 'lib/mingcute_icons.dart').read_text()
        self.assertIn('abstract final class MingCute {', entry)
        self.assertNotIn('static const line', entry)
        for style in STYLES:
            dart = (self.out / f'lib/src/generated/{style}_icons.g.dart').read_text()
            cls = f'_MingCute{style.capitalize()}'
            self.assertIn(f'abstract final class {cls} {{', dart)
            self.assertIn('@staticIconProvider\n' + f'abstract final class {cls}', dart)
            self.assertIn(f'IconData get home_1 => {cls}.home_1;', dart)
            self.assertIn('/// MingCute Core', dart)
        catalog = (self.out / 'preview/lib/generated_catalog.dart').read_text()
        self.assertIn('MingCute.regular.home_1', catalog)
        self.assertIn('MingCute.filled.home_1', catalog)
        self.assertNotIn('const List<PreviewIcon> previewIcons', catalog)

    def test_api_repair_never_rebuilds_unchanged_fonts(self):
        run(FIXTURE, self.out)
        protected = [self.out / f'assets/fonts/{family}.ttf' for _, family in STYLES.values()]
        protected.append(self.out / 'tool/codepoints.json')
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in protected}
        (self.out / 'lib/src/generated/regular_icons.g.dart').write_text('stale API')
        (self.out / 'lib/mingcute_icons.dart').write_text('stale entry')
        with patch('sync_icons.build_font', side_effect=AssertionError('font rebuild')), \
             patch('sync_icons.convert_svg', side_effect=AssertionError('SVG conversion')):
            self.assertFalse(run(FIXTURE, self.out)['skipped'])
            self.assertTrue(run(FIXTURE, self.out)['skipped'])
        for p in protected:
            self.assertEqual(before[p], (p.read_bytes(), p.stat().st_mtime_ns))
        (self.out / 'lib/mingcute_icons.dart').write_text('obsolete entry only')
        self.assertFalse(run(FIXTURE, self.out)['skipped'])
        self.assertTrue(run(FIXTURE, self.out)['skipped'])

    def test_api_version_changes_do_not_invalidate_font_pipeline(self):
        import sync_icons
        run(FIXTURE, self.out)
        with patch.object(sync_icons, 'API_VERSION', sync_icons.API_VERSION + 1), \
             patch('sync_icons.build_font', side_effect=AssertionError('font rebuild')):
            self.assertFalse(run(FIXTURE, self.out)['skipped'])
            self.assertTrue(run(FIXTURE, self.out)['skipped'])

    def test_static_library_is_independent_complete_and_repaired_without_fonts(self):
        run(FIXTURE, self.out)
        path = self.out / 'lib/mingcute_static.dart'
        self.assertTrue(path.is_file(), 'Missing independently importable static API')
        text = path.read_text()
        self.assertNotIn('mingcute_icons.dart', text)
        self.assertNotIn('Access', text)
        self.assertEqual(2, text.count('@staticIconProvider'))
        self.assertEqual(8, text.count('static const IconData '))
        for style in STYLES:
            self.assertIn(f'abstract final class MingCute{style.capitalize()}Const', text)
        protected = [self.out / f'assets/fonts/{f}.ttf' for _, f in STYLES.values()]
        protected.append(self.out / 'tool/codepoints.json')
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in protected}
        path.write_text(text.replace('0xe36c', '0xe000'))
        with self.assertRaises(AssertionError):
            validate(self.out)
        with patch('sync_icons.build_font', side_effect=AssertionError('font rebuild')):
            self.assertFalse(run(FIXTURE, self.out)['skipped'])
            self.assertEqual(text, path.read_text())
            self.assertTrue(run(FIXTURE, self.out)['skipped'])
        for p in protected:
            self.assertEqual(before[p], (p.read_bytes(), p.stat().st_mtime_ns))

    def test_provenance_only_change_never_rebuilds_fonts(self):
        source_info = {'repository': 'mingcute-design/mingcute-icons', 'revision': 'a' * 40,
                       'version': '3.1.0', 'versionSource': 'release.json'}
        with patch('sync_icons.provenance', return_value=source_info):
            run(FIXTURE, self.out)
        before = {family: (self.out / f'assets/fonts/{family}.ttf').read_bytes()
                  for _, family in STYLES.values()}
        with patch('sync_icons.provenance', return_value={**source_info, 'revision': 'b' * 40, 'version': '3.2.0'}), \
             patch('sync_icons.build_font', side_effect=AssertionError('font rebuild')):
            run(FIXTURE, self.out)
        manifest = json.loads((self.out / 'tool/manifest.json').read_text())
        self.assertEqual('3.2.0', manifest['upstream']['version'])
        self.assertEqual('b' * 40, manifest['sourceRevision'])
        for family, data in before.items():
            self.assertEqual(data, (self.out / f'assets/fonts/{family}.ttf').read_bytes())

    def test_validator_rejects_unverified_version_claims(self):
        run(FIXTURE, self.out)
        path = self.out / 'tool/manifest.json'
        manifest = json.loads(path.read_text())
        manifest['upstream']['version'] = 'invented'
        path.write_text(json.dumps(manifest))
        with self.assertRaises(AssertionError):
            validate(self.out)

    def test_name_collision_fails_before_writing(self):
        source = Path(self.tmp.name) / 'upstream'
        shutil.copytree(FIXTURE, source)
        source_file = source / 'packages/svg/core-regular/home-1.svg'
        (source_file.parent / 'home_1.svg').write_bytes(source_file.read_bytes())
        with self.assertRaisesRegex(ValueError, 'collision'):
            collect(source)

if __name__ == '__main__':
    unittest.main()

class GeometryTest(unittest.TestCase):
    def test_evenodd_hole_orients_opposite_to_parent(self):
        svg = b'''<svg viewBox="0 0 24 24"><path fill="#000" fill-rule="evenodd"
          d="M2 2H22V22H2Z M7 7H17V17H7Z"/></svg>'''
        glyph = convert_svg(svg)
        self.assertEqual(glyph.numberOfContours, 2)
        areas = []
        begin = 0
        for end in glyph.endPtsOfContours:
            pts = glyph.coordinates[begin:end + 1]
            areas.append(sum(pts[i][0] * pts[(i + 1) % len(pts)][1]
                - pts[(i + 1) % len(pts)][0] * pts[i][1]
                for i in range(len(pts))))
            begin = end + 1
        self.assertLess(areas[0] * areas[1], 0)

    def test_gradients_and_transforms_record_monochrome_approximations(self):
        from sync_icons import monochrome_notes
        svg = b'''<svg viewBox="0 0 24 24"><defs><linearGradient id="a">
          <stop offset="0" stop-color="currentColor" stop-opacity=".2"/>
          <stop offset="1" stop-color="currentColor"/></linearGradient></defs>
          <circle cx="8" cy="10" r="4" transform="translate(2 1)"
           opacity=".5" fill="url(#a)"/></svg>'''
        glyph = convert_svg(svg)
        self.assertGreater(glyph.numberOfContours, 0)
        self.assertEqual(len(monochrome_notes(svg)), 2)

    def test_reject_unsupported_mask(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported SVG element'):
            convert_svg(b'<svg viewBox="0 0 24 24"><mask id="m"/></svg>')
