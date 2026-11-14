"""Release guard: metadata, changelog notes, decision table, archive and context checks."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from _helpers import ROOT, CHANGELOG, make_project, package_files, tarball
import release_guard as guard

SHA, OTHER = 'a' * 40, 'b' * 40


def decide(**overrides):
    base = dict(event='push', ref='refs/heads/main', gates_passed=True, validated_sha=SHA,
                main_sha=SHA, published_state='absent')
    base.update(overrides)
    return guard.release_decision(**base)


class MetadataTest(unittest.TestCase):
    def project(self, **kwargs):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return make_project(Path(temp.name), **kwargs)

    def test_valid_metadata_and_exact_notes_section(self):
        version, notes = guard.read_metadata(self.project())
        self.assertEqual('0.2.0', version)
        self.assertEqual('- Added icons.', notes)
        self.assertNotIn('First version', notes)

    def test_changelog_mismatch_blocks(self):
        with self.assertRaisesRegex(ValueError, 'First CHANGELOG.md entry'):
            guard.read_metadata(self.project(version='0.3.0'))

    def test_empty_or_duplicate_notes_block(self):
        with self.assertRaisesRegex(ValueError, 'no release notes'):
            guard.read_metadata(self.project(changelog='## 0.2.0\n\n## 0.1.0\n\n- x\n'))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            guard.read_metadata(self.project(changelog='## 0.2.0\n\n- a\n\n## 0.2.0\n\n- b\n'))

    def test_only_stable_versions_publishable_and_publish_to_none_blocks(self):
        with self.assertRaisesRegex(ValueError, 'stable'):
            guard.read_metadata(self.project(version='0.2.0-dev.1', changelog='## 0.2.0\n\n- x\n'))
        with self.assertRaisesRegex(ValueError, 'publish_to'):
            guard.read_metadata(self.project(extra='publish_to: none'))

    def test_tag_must_match_version(self):
        root = self.project()
        self.assertEqual('0.2.0', guard.read_metadata(root, 'v0.2.0')[0])
        with self.assertRaisesRegex(ValueError, 'differs'):
            guard.read_metadata(root, 'v0.2.1')

    def test_identity_must_be_exact(self):
        root = self.project()
        spec = (root / 'pubspec.yaml').read_text().replace('name: mingcute_icons', 'name: mingcute_icons_kit')
        (root / 'pubspec.yaml').write_text(spec)
        with self.assertRaisesRegex(ValueError, 'identity'):
            guard.read_metadata(root)

    def test_public_url_metadata_is_pending_not_invented(self):
        root = self.project()
        warnings = guard.pubspec_report(root)
        self.assertTrue(any('repository' in w for w in warnings))
        with self.assertRaisesRegex(ValueError, 'public metadata incomplete'):
            guard.pubspec_report(root, require_public_urls=True)
        complete = self.project(extra='repository: https://github.com/o/mingcute_icons\n'
                                      'issue_tracker: https://github.com/o/mingcute_icons/issues\n'
                                      'homepage: https://github.com/o/mingcute_icons')
        self.assertEqual([], guard.pubspec_report(complete, require_public_urls=True))

    def test_topics_screenshots_and_urls_are_validated(self):
        root = self.project()
        spec = root / 'pubspec.yaml'
        spec.write_text(spec.read_text().replace('  - flutter\n', '  - flutter\n  - a1\n  - a2\n  - a3\n  - a4\n'))
        with self.assertRaisesRegex(ValueError, 'topics'):
            guard.pubspec_report(root)
        root = self.project()
        (root / 'doc/assets/screenshots/hero-dark.png').unlink()
        with self.assertRaisesRegex(ValueError, 'screenshot'):
            guard.pubspec_report(root)
        root = self.project(extra='repository: http://insecure.example/x')
        with self.assertRaisesRegex(ValueError, 'https'):
            guard.pubspec_report(root)


class DecisionTableTest(unittest.TestCase):
    def test_every_documented_state(self):
        self.assertEqual('validate-only', decide(event='pull_request'))
        self.assertEqual('validate-only', decide(ref='refs/heads/feature'))
        self.assertEqual('stale', decide(main_sha=OTHER))
        self.assertEqual('blocked', decide(gates_passed=False))
        self.assertEqual('blocked', decide(published_state='error'))
        self.assertEqual('bootstrap-pending', decide(published_state='no-package'))
        self.assertEqual('publish', decide())
        self.assertEqual('already-published', decide(
            published_state='published', archive_matches=True, existing_tag_sha=SHA, release_exists=True))
        self.assertEqual('recover', decide(published_state='published', archive_matches=True))
        self.assertEqual('conflict', decide(published_state='published', archive_matches=False))
        self.assertEqual('conflict', decide(existing_tag_sha=OTHER, tag_is_ancestor=False))
        self.assertEqual('conflict', decide(release_exists=True))

    def test_bootstrap_never_authorises_upload_even_when_everything_else_is_green(self):
        self.assertNotEqual('publish', decide(published_state='no-package', archive_matches=True))

    def test_failed_and_unconfirmed_publication(self):
        self.assertEqual('publication-failed', decide(publish_state='failed'))
        self.assertEqual('await-confirmation', decide(publish_state='succeeded'))
        self.assertEqual('recover', decide(publish_state='succeeded', publication_confirmed=True))
        self.assertEqual('blocked', decide(publish_state='weird'))


class RegistryTest(unittest.TestCase):
    def reply(self, payload):
        class Response:
            def __enter__(self_inner):
                return self_inner
            def __exit__(self_inner, *a):
                return False
            def read(self_inner):
                return json.dumps(payload).encode()
        return Response()

    def test_missing_package_is_bootstrap_not_absent(self):
        err = HTTPError('u', 404, 'nf', {}, None)
        with patch.object(guard, 'urlopen', side_effect=err):
            self.assertEqual('no-package', guard.registry_state('0.1.0'))
            with self.assertRaisesRegex(RuntimeError, 'bootstrap'):
                guard.published_status('0.1.0')

    def test_states_and_fail_closed_errors(self):
        data = {'versions': [{'version': '0.1.0'}]}
        with patch.object(guard, 'urlopen', return_value=self.reply(data)):
            self.assertEqual('published', guard.registry_state('0.1.0'))
            self.assertEqual('absent', guard.registry_state('0.2.0'))
        for error in (HTTPError('u', 500, 'x', {}, None), URLError('offline'), TimeoutError()):
            with patch.object(guard, 'urlopen', side_effect=error), self.assertRaises(RuntimeError):
                guard.registry_state('0.1.0')
        with patch.object(guard, 'urlopen', return_value=self.reply({'oops': 1})), self.assertRaises(RuntimeError):
            guard.registry_state('0.1.0')


class ArchiveTest(unittest.TestCase):
    def check(self, **overrides):
        files = guard.archive_files(tarball(package_files(**overrides), 'package/'))
        guard.check_archive_content(files)

    def test_valid_archive_passes(self):
        self.check()

    def test_required_content_is_enforced(self):
        for name in ('assets/fonts/MingCuteRegular.ttf', 'THIRD_PARTY_NOTICES.md',
                     'lib/src/generated/filled_icons.g.dart', 'lib/mingcute_static.dart', 'UPSTREAM_APACHE_LICENSE.txt', 'LICENSE'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'missing required'):
                self.check(**{name: None})

    def test_declared_screenshot_must_be_inside_the_archive(self):
        with self.assertRaisesRegex(ValueError, 'screenshot'):
            self.check(**{'doc/assets/screenshots/hero-dark.png': None})

    def test_readme_banner_and_attribution_must_be_inside_the_archive(self):
        banner = 'doc/assets/branding/mingcute-banner.png'
        attribution = 'doc/assets/branding/ATTRIBUTION.json'
        readme = f'![Original banner]({banner})'.encode()
        with self.assertRaisesRegex(ValueError, 'banner'):
            self.check(**{'README.md': readme})
        extras = {'README.md': readme, banner: (ROOT / banner).read_bytes(),
                  attribution: (ROOT / attribution).read_bytes()}
        self.check(**extras)
        with self.assertRaisesRegex(ValueError, 'banner'):
            self.check(**{**extras, banner: b'changed'})

    def test_snapshots_agent_context_and_secrets_are_rejected(self):
        for extra in ('morph_expressive-snapshot.zip', 'AGENTS.md', '.agents/CONTEXT.md', 'sub/AGENTS.md',
                      'PROMPT_MINGCUTE_R2.md', 'preview/lib/main.dart', 'tool/ci/release.py',
                      '.github/workflows/ci.yml', 'gha-creds-1.json', 'x.patch'):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.check(**{extra: b'x'})
        with self.assertRaisesRegex(ValueError, 'secret'):
            self.check(**{'README.md': b'token ghp_' + b'a' * 36})

    def test_unsafe_paths_and_non_files_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            guard.archive_files(tarball({**package_files(), '../evil': b'x'}, 'package/'))
        with self.assertRaisesRegex(ValueError, 'Cannot read'):
            guard.archive_files(b'not a tar')

    def test_real_tar_is_inspected_not_pubignore_text(self):
        # A .pubignore that *claims* to exclude the context proves nothing: the archive decides.
        with self.assertRaises(ValueError):
            self.check(**{'.pubignore': b'/.agents/', '.agents/README.md': b'leak'})


class LocalContextTest(unittest.TestCase):
    def test_names(self):
        guard.check_context_names(['lib/a.dart', 'README.md'])
        for bad in ('AGENTS.md', 'x/AGENTS.md', '.agents/a.md', 'PROMPT_MINGCUTE_R2.md', 'snap.zip', '.serena/m'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                guard.check_context_names([bad])


if __name__ == '__main__':
    unittest.main()
