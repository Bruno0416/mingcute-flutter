"""The release evidence gate must reject full, missing and ambiguous fonts."""
from pathlib import Path
import json
import shutil
import sys
import tempfile
import unittest

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tool'))
from sync_icons import run, STYLES


class ConsumerEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package, self.web = self.root / 'package', self.root / 'web'
        run(ROOT / 'tool/tests/fixtures/upstream', self.package)
        self.manifest = json.loads((self.package / 'tool/manifest.json').read_text())
        self.selection = {s: ('home_1', 'search_2') for s in STYLES}
        self.fonts = self.web / 'assets/packages/mingcute_flutter/assets/fonts'
        self.fonts.mkdir(parents=True)
        for _, family in STYLES.values():
            shutil.copy(self.package / f'assets/fonts/{family}.ttf', self.fonts)

    def inspect(self):
        from verify_consumer import inspect_fonts
        return inspect_fonts(self.package, self.web, self.manifest, self.selection)

    def subset_fonts(self, names):
        for style, (_, family) in STYLES.items():
            path = self.fonts / f'{family}.ttf'
            with TTFont(path) as font:
                worker = subset.Subsetter()
                worker.populate(unicodes=[int(self.manifest['icons'][style][n]['codepoint'], 16) for n in names])
                worker.subset(font)
                font.save(path)

    def test_full_fonts_fail_even_though_required_glyphs_exist(self):
        evidence, passed = self.inspect()
        self.assertFalse(passed)
        self.assertEqual(4, evidence['regular']['glyphs'])

    def test_candidates_emit_numeric_codepoints_not_dart_identifiers(self):
        from verify_consumer import candidate_library
        for kind in ('record', 'static-const'):
            text = candidate_library(self.manifest, kind)
            self.assertIn('IconData(0xe36c,', text)
            self.assertNotIn('IconData(E36C,', text)

    def test_subset_missing_a_required_glyph_fails(self):
        self.subset_fonts(['home_1'])
        evidence, passed = self.inspect()
        self.assertFalse(passed)
        self.assertTrue(evidence['filled']['missingCodepoints'])

    def test_real_subset_with_every_required_glyph_passes(self):
        self.subset_fonts(['home_1', 'search_2'])
        evidence, passed = self.inspect()
        self.assertTrue(passed)
        self.assertEqual(2, evidence['filled']['glyphs'])
        self.assertEqual([], evidence['regular']['missingCodepoints'])

    def test_missing_or_ambiguous_fonts_fail_closed(self):
        from verify_consumer import inspect_fonts
        duplicate = self.web / 'duplicate/MingCuteRegular.ttf'
        duplicate.parent.mkdir()
        shutil.copy(self.fonts / 'MingCuteRegular.ttf', duplicate)
        with self.assertRaises(ValueError):
            self.inspect()
        duplicate.unlink()
        (self.fonts / 'MingCuteFilled.ttf').unlink()
        with self.assertRaises(ValueError):
            self.inspect()

    def test_functional_gate_accepts_retention_but_static_gate_rejects_it(self):
        from verify_consumer import inspect_fonts, contract_passed
        evidence, subset = self.inspect()
        self.assertFalse(subset)
        self.assertTrue(contract_passed(evidence, require_subset=False))
        self.assertFalse(contract_passed(evidence, require_subset=True))
        evidence['regular']['missingCodepoints'] = [0xe36c]
        self.assertFalse(contract_passed(evidence, require_subset=False))

    def test_static_contract_rejects_extra_unused_glyphs(self):
        from verify_consumer import contract_passed
        self.subset_fonts(['home_1', 'search_2', 'heart'])
        evidence, subset = self.inspect()
        self.assertTrue(subset)  # Historical strict check still reports a real subset.
        self.assertFalse(contract_passed(evidence, require_subset=True))
