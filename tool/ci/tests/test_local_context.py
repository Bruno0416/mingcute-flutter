"""Local agent context / snapshot exclusion works through .git/info/exclude only."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from _helpers import ROOT
import release_guard as guard

SCRIPT = ROOT / 'tool/ci/exclude_local_context.sh'
BASH = shutil.which('bash')


@unittest.skipUnless(shutil.which('git'), 'git is required')
class LocalContextTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'T')
        self.git('config', 'user.email', 't@example.invalid')
        (self.root / 'tool/ci').mkdir(parents=True)
        shutil.copy(SCRIPT, self.root / 'tool/ci/exclude_local_context.sh')
        (self.root / '.gitignore').write_text('build/\n')
        (self.root / 'lib').mkdir()
        (self.root / 'lib/a.dart').write_text('x')

    def git(self, *args, check=True):
        return subprocess.run(['git', '-C', str(self.root), *args], capture_output=True, text=True, check=check)

    def exclude(self):
        return subprocess.run([BASH, str(self.root / 'tool/ci/exclude_local_context.sh')],
                              capture_output=True, text=True)

    def create_context(self):
        (self.root / '.agents').mkdir()
        (self.root / '.agents/CONTEXT.md').write_text('ctx')
        (self.root / 'AGENTS.md').write_text('a')
        (self.root / 'sub').mkdir()
        (self.root / 'sub/AGENTS.md').write_text('n')
        (self.root / 'PROMPT_MINGCUTE_R2.md').write_text('p')
        (self.root / 'morph_expressive-snapshot-1.zip').write_bytes(b'zip')
        for name in ('PROMPT_MINGCUTE_R2_1_PANA_GATE.md', 'PROMPT_FUTURE.md',
                     'snapshots/mingcute_icons-snapshot-20261113.zip',
                     'mingcute_icons-snapshot-future.zip'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('local')

    def test_exclusion_is_idempotent_and_leaves_gitignore_untouched(self):
        self.create_context()
        before = (self.root / '.gitignore').read_text()
        self.assertEqual(0, self.exclude().returncode)
        first = Path(self.git('rev-parse', '--git-path', 'info/exclude').stdout.strip())
        first = first if first.is_absolute() else self.root / first
        content = first.read_text()
        self.assertEqual(0, self.exclude().returncode)
        self.assertEqual(content, first.read_text())
        self.assertEqual(before, (self.root / '.gitignore').read_text())
        for path in ('.agents/CONTEXT.md', 'AGENTS.md', 'sub/AGENTS.md', 'PROMPT_MINGCUTE_R2.md',
                     'morph_expressive-snapshot-1.zip', 'PROMPT_FUTURE.md',
                     'PROMPT_MINGCUTE_R2_1_PANA_GATE.md',
                     'snapshots/mingcute_icons-snapshot-20261113.zip',
                     'mingcute_icons-snapshot-future.zip'):
            self.assertEqual(0, self.git('check-ignore', '-q', path, check=False).returncode, path)
        status = self.git('status', '--short').stdout
        for hidden in ('.agents', 'AGENTS', 'PROMPT', 'snapshot'):
            self.assertNotIn(hidden, status)
        self.assertTrue((self.root / '.agents/CONTEXT.md').is_file())  # files stay on disk

    def test_tracked_entries_are_dropped_from_the_index_only(self):
        self.create_context()
        self.git('add', '-f', 'AGENTS.md', '.agents/CONTEXT.md', 'PROMPT_FUTURE.md', 'snapshots')
        self.assertEqual(0, self.exclude().returncode)
        self.assertEqual('', self.git('ls-files', 'AGENTS.md', '.agents', 'PROMPT_FUTURE.md', 'snapshots').stdout.strip())
        self.assertTrue((self.root / 'AGENTS.md').is_file())

    def test_linked_worktree_uses_common_git_exclude(self):
        self.git('add', 'lib/a.dart')
        self.git('commit', '-qm', 'fixture')
        worktree = self.root.parent / (self.root.name + '-worktree')
        self.git('worktree', 'add', '--detach', str(worktree))
        self.addCleanup(lambda: self.git('worktree', 'remove', '--force', str(worktree)))
        (worktree / 'tool/ci').mkdir(parents=True)
        shutil.copy(SCRIPT, worktree / 'tool/ci/exclude_local_context.sh')
        (worktree / 'PROMPT_FUTURE.md').write_text('local')
        result = subprocess.run([BASH, str(worktree / 'tool/ci/exclude_local_context.sh')],
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        ignored = subprocess.run(['git', '-C', str(worktree), 'check-ignore', '-v', 'PROMPT_FUTURE.md'],
                                 capture_output=True, text=True)
        self.assertEqual(0, ignored.returncode, ignored.stderr)
        self.assertIn('info/exclude', ignored.stdout)
        self.assertTrue((worktree / 'PROMPT_FUTURE.md').is_file())

    def test_missing_git_fails_clearly(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'tool/ci/exclude_local_context.sh'
            target.parent.mkdir(parents=True)
            shutil.copy(SCRIPT, target)
            result = subprocess.run([BASH, str(target)], capture_output=True, text=True)
            self.assertEqual(1, result.returncode)
            self.assertIn('Not a Git checkout', result.stderr)

    def test_tracked_context_fails_the_publication_guard_but_absent_context_passes(self):
        self.git('add', 'lib/a.dart', '.gitignore')
        guard.check_local_context_paths(self.root)  # CI clone without any local context
        self.create_context()
        self.git('add', '-f', 'AGENTS.md')
        with self.assertRaisesRegex(ValueError, 'must not be tracked'):
            guard.check_local_context_paths(self.root)

    def test_untracked_excluded_context_does_not_trip_the_guard(self):
        self.git('add', 'lib/a.dart')
        self.create_context()
        self.exclude()
        guard.check_local_context_paths(self.root)

    def test_hooks_installer_never_overwrites(self):
        shutil.copy(ROOT / 'tool/ci/install_git_hooks.sh', self.root / 'tool/ci/install_git_hooks.sh')
        run = lambda: subprocess.run([BASH, str(self.root / 'tool/ci/install_git_hooks.sh')], capture_output=True, text=True)
        self.assertEqual(0, run().returncode)
        hook = self.root / '.git/hooks/pre-commit'
        hook.write_text('#!/bin/sh\necho mine\n')
        self.assertEqual(1, run().returncode)
        self.assertIn('mine', hook.read_text())

    def test_real_ignore_rules_cover_generated_files_without_duplicate_rules(self):
        shutil.copy(ROOT / '.gitignore', self.root / '.gitignore')
        for name in ('preview/.gitignore', 'preview/linux/.gitignore'):
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / name, destination)
        self.assertEqual(0, self.exclude().returncode)
        for name in ('preview/linux/flutter/ephemeral/libflutter_linux_gtk.so',
                     'preview/build/file', '.venv/file', 'tool/.cache/file',
                     '.agents/README.md', 'AGENTS.md'):
            result = self.git('check-ignore', '-v', name, check=False)
            self.assertEqual(0, result.returncode, name)
            expected = '.git/info/exclude' if name.startswith('.agents/') or name == 'AGENTS.md' else '.gitignore'
            self.assertIn(expected, result.stdout)
        self.assertEqual('', self.git('diff', '--cached', '--name-only').stdout)


if __name__ == '__main__':
    unittest.main()
