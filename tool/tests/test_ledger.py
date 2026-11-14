import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tool'))
from sync_icons import run
from validate import validate

FIXTURE = ROOT / 'tool/tests/fixtures/upstream'


class LedgerPolicyTest(unittest.TestCase):
    """Removed icons keep their codepoint forever; new icons never reuse it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / 'out'
        self.out.mkdir()
        shutil.copy(ROOT / 'UPSTREAM_APACHE_LICENSE.txt', self.out)
        self.source = Path(self.tmp.name) / 'upstream'
        shutil.copytree(FIXTURE, self.source)

    def ledger(self):
        return json.loads((self.out / 'tool/codepoints.json').read_text())['assignments']

    def test_removed_icon_codepoint_is_not_reused_by_a_new_icon(self):
        run(self.source, self.out)
        heart = self.ledger()['heart']
        for style in ('core-regular', 'core-filled'):
            base = self.source / 'packages/svg' / style
            (base / 'heart.svg').unlink()
            shutil.copy(base / 'add.svg', base / 'brand-new.svg')
        report = run(self.source, self.out)
        self.assertEqual(['heart'], report['removed']['regular'])
        assignments = self.ledger()
        self.assertEqual(heart, assignments['heart'])  # still reserved
        self.assertNotEqual(heart, assignments['brand_new'])
        self.assertEqual(len(assignments.values()), len(set(assignments.values())))
        validate(self.out)

    def test_modified_icon_keeps_identity_and_two_runs_are_byte_identical(self):
        run(self.source, self.out)
        snapshot = {p.name: p.read_bytes() for p in (self.out / 'assets/fonts').glob('*.ttf')}
        before = self.ledger()
        run(self.source, self.out)
        self.assertEqual(snapshot, {p.name: p.read_bytes() for p in (self.out / 'assets/fonts').glob('*.ttf')})
        self.assertEqual(before, self.ledger())

    def test_unsafe_svg_blocks_every_artifact(self):
        bad = self.source / 'packages/svg/core-regular/add.svg'
        bad.write_text('<svg viewBox="0 0 24 24"><script>alert(1)</script><path d="M0 0"/></svg>')
        with self.assertRaises(Exception):
            run(self.source, self.out)
        self.assertFalse((self.out / 'assets/fonts/MingCuteRegular.ttf').exists())
        self.assertFalse((self.out / 'lib/src/generated').exists())


if __name__ == '__main__':
    unittest.main()
