"""End-to-end clean-room test, with a LOCAL Git origin to avoid public network."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tool'))
from verify_rebuild import verify

FIXTURE = ROOT / 'tool/tests/fixtures/upstream'


class CleanRebuildTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)

    def test_without_manual_checkout_clones_and_regenerates_after_deletion(self):
        git_root = self.tmp / 'origin'
        shutil.copytree(FIXTURE, git_root)
        subprocess.run(['git', 'init', '-b', 'main', str(git_root)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['git', '-C', str(git_root), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(git_root), '-c', 'user.name=Test',
                        '-c', 'user.email=test@example.com', 'commit', '-qm', 'fixture'], check=True)
        report = self.tmp / 'result.json'
        with patch('sync_icons.REPO_URL', git_root.as_uri()):
            result = verify(min_icons=4, report_path=report)
        self.assertEqual(result['sourceMode'], 'fresh-automatic-git-clone')
        self.assertEqual(result['iconsPerStyle'], {'regular': 4, 'filled': 4})
        self.assertEqual(result['deletedAndRegenerated'], {'regular': 4, 'filled': 4})
        self.assertEqual(result['reusedAfterDeletion'], {'regular': 0, 'filled': 0})
        self.assertTrue(result['thirdSyncSkipped'])
        self.assertTrue(result['byteIdentical'])
        self.assertTrue(report.is_file())

    def test_reject_incomplete_corpus_before_writing_pass_report(self):
        report = self.tmp / 'never_written.json'
        with self.assertRaises(RuntimeError):
            verify(source=FIXTURE, min_icons=2200, report_path=report)
        self.assertFalse(report.exists())


if __name__ == '__main__':
    unittest.main()
