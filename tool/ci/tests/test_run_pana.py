"""Runs the real CI script (tool/ci/run_pana.sh) against a fake `dart` and fake
WebP tools in a throw-away PATH. Nothing here talks to pub.dev; this simulates
pana's *outputs*, so it proves the gate's exit codes, not pana itself."""
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import tarfile
import io
import unittest

from _helpers import ROOT
from release_guard import REQUIRED_FILES

SCRIPT = ROOT / 'tool/ci/run_pana.sh'
TOOLS = ('webpinfo', 'cwebp', 'dwebp', 'gif2webp', 'webpmux')
SYSTEM = ('bash', 'python3', 'rm', 'dirname', 'grep', 'cat', 'env', 'mktemp', 'cp')

FAKE_DART = """#!/usr/bin/env bash
echo "dart $*" >> "$FAKE_LOG"
case "$1 $2 $3" in
  "pub global activate") exit "${FAKE_ACTIVATE_EXIT:-0}" ;;
  "pub global list") echo "pana ${FAKE_PANA_VERSION:-0.23.19}"; exit 0 ;;
  "pub global run") if [ -n "${FAKE_EXPECT_PACKAGE:-}" ]; then test "$(cat pubspec.yaml)" = 'name: mingcute_flutter' || exit 98; fi; [ -n "${FAKE_PANA_JSON:-}" ] && cat "$FAKE_PANA_JSON"; echo 'pana log line' >&2; exit "${FAKE_PANA_EXIT:-0}" ;;
esac
exit 99
"""


def pana_json(granted, maximum=160):
    return json.dumps({
        'scores': {'grantedPoints': granted, 'maxPoints': maximum},
        'report': {'sections': [{'title': 'Follow Dart file conventions',
                                 'grantedPoints': 20 if granted < maximum else 30, 'maxPoints': 30}]},
    })


class RunPanaTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        self.bin = self.temp / 'bin'
        self.bin.mkdir()
        for tool in SYSTEM:
            (self.bin / tool).symlink_to(shutil.which(tool))
        self.write_exec('dart', FAKE_DART)
        for tool in TOOLS:
            self.write_exec(tool, '#!/bin/sh\nexit 0\n')
        (self.temp / 'pkg').mkdir()
        self.report = self.temp / 'out' / 'pana.json'
        self.report.parent.mkdir()
        self.log = self.temp / 'calls.log'

    def write_exec(self, name, text):
        path = self.bin / name
        path.write_text(text)
        path.chmod(path.stat().st_mode | stat.S_IEXEC)

    def run_script(self, *, text=None, package=None, **env):
        if text is not None:
            (self.temp / 'fake.json').write_text(text)
            env.setdefault('FAKE_PANA_JSON', str(self.temp / 'fake.json'))
        environment = {'PATH': str(self.bin), 'FAKE_LOG': str(self.log), **env}
        return subprocess.run(['bash', str(SCRIPT), str(self.report), str(package or self.temp / 'pkg')],
                              env=environment, capture_output=True, text=True)

    def test_exact_full_score_passes_with_exit_zero(self):
        result = self.run_script(text=pana_json(160))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('PASS: pana 160/160', result.stdout)
        calls = self.log.read_text()
        self.assertIn('pub global activate pana 0.23.19', calls)
        self.assertIn('pub global run pana:pana --json --exit-code-threshold=0 .', calls)

    def test_scores_below_160_fail(self):
        for granted in (159, 150, 120, 0):
            with self.subTest(granted=granted):
                result = self.run_script(text=pana_json(granted))
                self.assertEqual(1, result.returncode)
                self.assertIn(f'{granted}/160', result.stderr)

    def test_any_other_maximum_fails_even_when_everything_is_granted(self):
        for granted, maximum in ((170, 170), (150, 150), (160, 170), (160, 150), (100, 100)):
            with self.subTest(maximum=maximum):
                result = self.run_script(text=pana_json(granted, maximum))
                self.assertEqual(1, result.returncode)
                self.assertIn('model changed', result.stderr)

    def test_malformed_or_incomplete_output_fails(self):
        for text in ('', '   ', 'not json', '{', '{}', '{"scores": null}', '{"scores": {"grantedPoints": 160}}',
                     '{"scores": {"grantedPoints": "160", "maxPoints": "160"}}',
                     '{"scores": {"grantedPoints": 160, "maxPoints": 160.0}}'):
            with self.subTest(text=text):
                self.assertEqual(1, self.run_script(text=text).returncode)

    def test_no_output_at_all_fails(self):
        self.assertEqual(1, self.run_script().returncode)

    def test_pana_process_failure_fails_even_with_a_perfect_json(self):
        result = self.run_script(text=pana_json(160), FAKE_PANA_EXIT='1')
        self.assertNotEqual(0, result.returncode)
        self.assertNotIn('PASS', result.stdout)

    def test_real_pana_behaviour_lost_points_exit_nonzero_and_the_causes_are_printed(self):
        # Real pana 0.23.19 with --exit-code-threshold=0 exits 127 when points are lost.
        result = self.run_script(text=pana_json(150), FAKE_PANA_EXIT='127')
        self.assertEqual(127, result.returncode)
        self.assertIn('150/160', result.stderr)
        self.assertIn('Follow Dart file conventions: 20/30', result.stderr)
        self.assertIn('gate FAILED', result.stderr)

    def test_verifier_failure_alone_still_fails_when_pana_exits_zero(self):
        result = self.run_script(text=pana_json(159), FAKE_PANA_EXIT='0')
        self.assertEqual(1, result.returncode)

    def test_stale_report_from_a_previous_run_is_never_used(self):
        self.report.write_text(pana_json(160))
        result = self.run_script(FAKE_PANA_EXIT='0')  # fake pana prints nothing this time
        self.assertEqual(1, result.returncode)
        self.assertNotIn('PASS', result.stdout)

    def test_activation_failure_and_wrong_pinned_version_fail(self):
        self.assertNotEqual(0, self.run_script(text=pana_json(160), FAKE_ACTIVATE_EXIT='1').returncode)
        result = self.run_script(text=pana_json(160), FAKE_PANA_VERSION='0.23.20')
        self.assertNotEqual(0, result.returncode)
        self.assertIn('not the active version', result.stderr)

    def test_missing_webp_tools_fail_before_pana_runs(self):
        for tool in TOOLS:
            with self.subTest(tool=tool):
                (self.bin / tool).unlink()
                result = self.run_script(text=pana_json(160))
                self.assertNotEqual(0, result.returncode)
                self.assertIn(tool, result.stderr)
                self.assertFalse(self.log.exists() and 'pana:pana' in self.log.read_text())
                self.write_exec(tool, '#!/bin/sh\nexit 0\n')

    def test_the_expected_maximum_cannot_be_overridden_from_the_environment(self):
        result = self.run_script(text=pana_json(150, 150), EXPECTED_MAX='150', PANA_EXPECTED_MAX='150')
        self.assertEqual(1, result.returncode)

    def test_archive_is_validated_before_scoring(self):
        archive = self.temp / 'package.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            member = tarfile.TarInfo('../escape')
            member.size = 1
            tar.addfile(member, io.BytesIO(b'x'))
        result = subprocess.run(['bash', str(SCRIPT), str(self.report), str(archive)],
                                env={'PATH': str(self.bin), 'FAKE_LOG': str(self.log)},
                                capture_output=True, text=True)
        self.assertNotEqual(0, result.returncode)
        self.assertIn('unsafe path', result.stderr)
        self.assertFalse((self.temp / 'escape').exists())

    def test_missing_dart_is_reported(self):
        (self.bin / 'dart').unlink()
        result = self.run_script()
        self.assertNotEqual(0, result.returncode)
        self.assertIn('Missing required tool: dart', result.stderr)

    def test_interrupted_process_preserves_exit_code(self):
        self.assertEqual(143, self.run_script(FAKE_PANA_EXIT='143').returncode)

    def test_valid_archives_are_scored_from_their_extracted_package(self):
        for prefix in ('', 'package/'):
            archive = self.temp / 'valid.tar.gz'
            with tarfile.open(archive, 'w:gz') as tar:
                for name in REQUIRED_FILES:
                    data = b'name: mingcute_flutter' if name == 'pubspec.yaml' else b'fixture'
                    member = tarfile.TarInfo(prefix + name)
                    member.size = len(data)
                    tar.addfile(member, io.BytesIO(data))
            result = self.run_script(text=pana_json(160), package=archive, FAKE_EXPECT_PACKAGE='1')
            self.assertEqual(0, result.returncode, result.stderr)

    def test_report_symlink_is_not_followed(self):
        victim = self.temp / 'user-file'
        victim.write_text('keep me')
        self.report.symlink_to(victim)
        self.assertNotEqual(0, self.run_script(text=pana_json(160)).returncode)
        self.assertEqual('keep me', victim.read_text())


if __name__ == '__main__':
    unittest.main()
