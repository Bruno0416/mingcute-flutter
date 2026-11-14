import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class UpstreamMetadataTest(unittest.TestCase):
    def test_release_json_is_authoritative_and_stable_semver(self):
        from upstream_metadata import parse_release
        self.assertEqual('3.1.0', parse_release(b'{"schemaVersion":1,"version":"3.1.0"}'))
        for version in ('3.1', 'v3.1.0', '03.1.0', '3.1.0extra', '', None, 310):
            with self.subTest(version=version), self.assertRaises(ValueError):
                parse_release(json.dumps({'schemaVersion': 1, 'version': version}).encode())
        for raw in (b'{}', b'[]', b'bad JSON', b'{"schemaVersion":2,"version":"3.1.0"}'):
            with self.assertRaises(ValueError):
                parse_release(raw)

    def test_verified_git_release_is_read_at_the_synced_sha(self):
        from upstream_metadata import provenance
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            sha = 'a' * 40
            replies = [str(root), sha, '', '{"schemaVersion":1,"version":"3.1.0"}']
            with patch('upstream_metadata.git', side_effect=replies) as command:
                info = provenance(root)
            self.assertEqual(sha, info['revision'])
            self.assertEqual('3.1.0', info['version'])
            self.assertIn(f'{sha}:release.json', command.call_args.args)

    def test_missing_release_for_verified_git_fails_closed(self):
        from upstream_metadata import provenance
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            with patch('upstream_metadata.git', side_effect=[str(root), 'a' * 40, '', RuntimeError('missing release.json')]):
                with self.assertRaisesRegex(RuntimeError, 'release.json'):
                    provenance(root)

    def test_local_fixture_never_borrows_parent_git_or_invents_version(self):
        from upstream_metadata import provenance
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch('upstream_metadata.git', return_value=str(root.parent)):
                info = provenance(root)
            self.assertEqual('local-source', info['revision'])
            self.assertIsNone(info['version'])

    def test_dirty_artwork_cannot_claim_a_verified_revision(self):
        from upstream_metadata import provenance
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            with patch('upstream_metadata.git', side_effect=[str(root), 'a' * 40, ' M packages/svg/core-regular/home-1.svg']):
                with self.assertRaisesRegex(ValueError, 'modified'):
                    provenance(root)
