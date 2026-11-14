"""Release orchestration with mocks only: no registry, Git remote or GitHub call is made."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from _helpers import make_project
import release
import release_guard as guard

SHA, OLD = 'a' * 40, 'b' * 40


class PlanTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = make_project(Path(temp.name), extra='repository: https://github.com/o/mingcute_icons\n'
                                 'issue_tracker: https://github.com/o/mingcute_icons/issues\n'
                                 'homepage: https://github.com/o/mingcute_icons')

    def plan(self, *, state='absent', main=SHA, tag=None, ancestor=True, matches=False, exists=False, tag_version='0.2.0'):
        git_show = subprocess.CompletedProcess([], 0, f'name: mingcute_icons\nversion: {tag_version}\n', '')
        with patch.object(release, 'require_main_push', return_value=SHA), \
             patch.object(release.guard, 'check_local_context_paths'), \
             patch.object(release, 'current_main', return_value=main), \
             patch.object(release, 'remote_tag_sha', return_value=tag), \
             patch.object(release, 'run', return_value=git_show) as run, \
             patch.object(release.guard, 'registry_state', return_value=state), \
             patch.object(release.guard, 'published_archive_matches', return_value=matches), \
             patch.object(release, 'verify_tagged_archive'), \
             patch.object(release, 'github_release_exists', return_value=exists):
            run.side_effect = lambda *a, **k: subprocess.CompletedProcess(
                a, 0 if a[:2] != ('git', 'merge-base') or ancestor else 1, git_show.stdout, '')
            return release.plan(self.root, Path('archive.tgz'))

    def test_unpublished_package_is_bootstrap_pending_and_never_publish(self):
        self.assertEqual('bootstrap-pending', self.plan(state='no-package')['decision'])

    def test_new_version_of_existing_package_publishes(self):
        self.assertEqual('publish', self.plan()['decision'])

    def test_main_advanced_is_stale(self):
        self.assertEqual('stale', self.plan(main=OLD)['decision'])

    def test_published_version_with_different_bytes_blocks(self):
        with self.assertRaisesRegex(ValueError, 'blocked'):
            self.plan(state='published', matches=False)

    def test_conflicting_tag_blocks(self):
        with self.assertRaises(ValueError):
            self.plan(tag=OLD, ancestor=False)
        with self.assertRaises(ValueError):
            self.plan(tag=OLD, tag_version='0.1.0')

    def test_same_bytes_without_tag_recovers_and_complete_state_is_idempotent(self):
        self.assertEqual('recover', self.plan(state='published', matches=True)['decision'])
        done = self.plan(state='published', matches=True, tag=SHA, exists=True)
        self.assertEqual('already-published', done['decision'])

    def test_missing_public_metadata_blocks_before_publishing(self):
        spec = self.root / 'pubspec.yaml'
        spec.write_text(spec.read_text().replace('repository: https://github.com/o/mingcute_icons\n', ''))
        with self.assertRaisesRegex(ValueError, 'public metadata'):
            self.plan()

    def test_non_main_events_cannot_reach_release(self):
        with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'pull_request', 'GITHUB_REF': 'refs/pull/1/merge'}):
            with self.assertRaisesRegex(ValueError, 'push to main'):
                release.require_main_push()


class FinalizeTest(unittest.TestCase):
    def test_registry_error_prevents_tag_and_release(self):
        with patch.object(release, 'require_main_push', return_value=SHA), \
             patch.object(release.guard, 'read_metadata', return_value=('0.2.0', 'notes')), \
             patch.object(release.guard, 'published_status', side_effect=RuntimeError('offline')), \
             patch.object(release, 'run') as run, patch.object(release.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'offline'):
                release.finalize(Path('.'), Path('archive'), SHA)
            run.assert_not_called()

    def test_checksum_mismatch_prevents_tag(self):
        with patch.object(release.guard, 'published_status', return_value=True), \
             patch.object(release.guard, 'published_archive_matches', return_value=False), \
             patch.object(release, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'differs'):
                release.confirm(Path('archive'), '0.2.0')
            run.assert_not_called()

    def test_tags_the_validated_sha_then_creates_release_with_changelog_notes(self):
        events = []
        def run(*args, **kwargs):
            events.append(args)
            return subprocess.CompletedProcess(args, 0, '', '')
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'RUNNER_TEMP': temp}), \
             patch.object(release, 'require_main_push', return_value=SHA), \
             patch.object(release.guard, 'read_metadata', return_value=('0.2.0', 'real notes')), \
             patch.object(release, 'confirm'), \
             patch.object(release, 'remote_tag_sha', side_effect=[None, SHA]), \
             patch.object(release, 'github_release_exists', side_effect=[False, True]), \
             patch.object(release, 'run', side_effect=run):
            release.finalize(Path('.'), Path('archive'), SHA)
            self.assertEqual('real notes\n', (Path(temp) / 'release-notes.md').read_text())
        self.assertEqual(('git', 'tag', 'v0.2.0', SHA), events[0])
        self.assertIn('release', events[2])
        self.assertIn('MingCute Icons 0.2.0', events[2])

    def test_recovery_never_retags_a_different_sha_and_is_idempotent(self):
        with patch.object(release, 'require_main_push', return_value=SHA), \
             patch.object(release.guard, 'read_metadata', return_value=('0.2.0', 'n')), \
             patch.object(release, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')), \
             patch.object(release, 'confirm'), patch.object(release, 'remote_tag_sha', return_value=None):
            with self.assertRaisesRegex(ValueError, 'refusing to recreate'):
                release.finalize(Path('.'), Path('archive'), OLD)
        with patch.object(release, 'require_main_push', return_value=SHA), \
             patch.object(release.guard, 'read_metadata', return_value=('0.2.0', 'n')), \
             patch.object(release, 'run') as run, patch.object(release, 'confirm'), \
             patch.object(release, 'remote_tag_sha', return_value=OLD), \
             patch.object(release, 'github_release_exists', return_value=True):
            run.return_value = subprocess.CompletedProcess([], 0, '', '')
            release.finalize(Path('.'), Path('archive'), OLD)  # already complete: nothing created
            self.assertFalse(any('tag' in call.args[:2] for call in run.call_args_list))
            self.assertFalse(any('create' in call.args for call in run.call_args_list))

    def test_moved_tag_is_never_overwritten(self):
        with patch.object(release, 'require_main_push', return_value=SHA), \
             patch.object(release.guard, 'read_metadata', return_value=('0.2.0', 'n')), \
             patch.object(release, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')), \
             patch.object(release, 'confirm'), patch.object(release, 'remote_tag_sha', return_value=OLD):
            with self.assertRaisesRegex(ValueError, 'never overwrite'):
                release.finalize(Path('.'), Path('archive'), SHA)


if __name__ == '__main__':
    unittest.main()
