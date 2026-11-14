"""Open real archives to check the local source snapshot security boundary."""
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from _helpers import ROOT
sys.path.insert(0, str(ROOT / 'tool'))
from snapshot import create_snapshot


class SnapshotTest(unittest.TestCase):
    def test_private_files_caches_and_external_links_never_enter_zip(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'package'
            allowed = ['pubspec.yaml', 'lib/icons.dart', 'assets/fonts/icons.ttf',
                       'tool/tests/fixtures/home.svg', '.github/workflows/tests.yml']
            denied = ['.agents/PRIVATE.md', '.serena/memory.md', 'AGENTS.md',
                      'sub/AGENTS.md', '.env', '.env.local', 'sub/.env.production',
                      'PROMPT_MINGCUTE_R2_1_PANA_GATE.md', 'snapshots/old-snapshot.zip',
                      '.venv/bin/python', 'preview/build/main.js', '.dart_tool/config',
                      'node_modules/a.js', '__pycache__/x.pyc', '.pytest_cache/state',
                      'coverage/report', 'tool/.cache/file', 'old.zip',
                      '.github/credentials', 'service-account.json', 'gcloud.json',
                      'id_ed25519', 'cert.pem', 'key.p12', 'private.key',
                      '.netrc', '.npmrc', '.envrc', '.gitcookies', 'id_dsa', 'secret.p8',
                      'local.token', 'secrets.yaml', 'auth.json', 'gha-creds-fixture.json',
                      '.config/gcloud/application_default_credentials.json',
                      'scratch.tmp', 'file.dart~']
            for name in allowed + denied:
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('fixture')
            outside = Path(temp) / 'external-secret'
            outside.write_text('secret')
            (root / 'leak').symlink_to(outside)
            (root / 'linked-directory').symlink_to(outside.parent, target_is_directory=True)
            archives = []
            for n in range(2):
                archive = root / f'output{n}.zip'
                count, size = create_snapshot(root, archive)
                with ZipFile(archive) as z:
                    names = z.namelist()
                    self.assertEqual(sorted(allowed), names)
                    self.assertEqual(count, len(allowed))
                    self.assertEqual(size, sum(len(z.read(p)) for p in names))
                    self.assertTrue(all(not p.startswith('/') and '..' not in Path(p).parts for p in names))
                    archives.append(names)
            self.assertEqual(*archives)

    def test_recognizable_credentials_are_excluded_without_hiding_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'lib').mkdir()
            (root / 'pubspec.yaml').write_text('name: fixture')
            (root / 'lib/real.dart').write_text('class Real {}')
            (root / 'innocent.txt').write_text('-----BEGIN OPENSSH PRIVATE KEY-----\nfake')
            (root / 'renamed.json').write_text('{"type":"service_account","private_key":"fake"}')
            (root / 'notes.txt').write_text('token=ghp_' + 'a' * 36)
            archive = root / 'out.zip'
            create_snapshot(root, archive)
            with ZipFile(archive) as z:
                self.assertEqual(['lib/real.dart', 'pubspec.yaml'], z.namelist())
