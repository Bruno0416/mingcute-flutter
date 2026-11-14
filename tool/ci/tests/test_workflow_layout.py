"""Validate stage ordering and execute the real final gate under failure states.

Actionlint independently checks YAML/schema, expressions and reusable calls.
These tests cover the repository's release policy, not a general YAML parser.
"""
from pathlib import Path
import os
import re
import subprocess
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / '.github/workflows'


def job_blocks(text):
    jobs = text.split('\njobs:\n', 1)[1]
    return {m.group(1): m.group(2) for m in re.finditer(
        r'^  ([\w-]+):\n(.*?)(?=^  [\w-]+:\n|\Z)', jobs, re.M | re.S)}


class WorkflowLayoutTest(unittest.TestCase):
    def test_consumer_font_subsetting_is_an_actual_fail_closed_build(self):
        text = (ROOT / '.github/workflows/tests.yml').read_text()
        self.assertIn('tool/verify_consumer.py --report', text)
        self.assertIn('consumer-evidence-', text)
        self.assertNotIn('continue-on-error', text)
        for line in text.splitlines():
            if 'tool/verify_consumer.py' in line:
                self.assertNotIn('--experiment', line)

    def test_public_contracts_and_static_subsetting_are_separate_required_steps(self):
        text = (WORKFLOWS / 'tests.yml').read_text()
        for scenario in ('primary-contract', 'static-subsetting', 'mixed-contract'):
            self.assertIn('--scenario ' + scenario, text)
        self.assertNotIn('continue-on-error', text)
        self.assertNotIn('|| true', text)

    def test_release_runbook_matches_consumer_gates_and_first_push_policy(self):
        runbook = (ROOT / 'doc/RELEASE.md').read_text()
        local_gates = runbook.split('## Local gates', 1)[1].split('## GitHub Actions', 1)[0]
        consumer_commands = re.findall(r'^python tool/verify_consumer\.py (.+)$', local_gates, re.M)
        self.assertEqual(3, len(consumer_commands))
        for scenario in ('primary-contract', 'static-subsetting', 'mixed-contract'):
            matching = [line for line in consumer_commands if f'--scenario {scenario}' in line]
            self.assertEqual(1, len(matching), scenario)
            self.assertIn('--report ', matching[0])
        self.assertIn('historical', runbook.lower())
        self.assertIn('**not** the CI release gate', runbook)
        self.assertIn('ENABLE_AUTOMATIC_PUBLISH', runbook)
        self.assertIn('**unset**', runbook)
        self.assertIn('No publication workflow is included in the initial push', runbook)
        self.assertIn('All required quality checks', runbook)
        self.assertIn('real pana 160/160', runbook)
        self.assertIn('first `0.1.0` release', runbook)

    def test_upstream_metadata_and_readme_changes_are_proposed_without_publication(self):
        text = (WORKFLOWS / 'upstream-sync.yml').read_text()
        self.assertIn('tool/readme_metadata.py --refresh-latest --write', text)
        for line in text.splitlines():
            if 'git diff --quiet' in line or 'git diff --binary' in line:
                self.assertIn('README.md', line)
                self.assertIn('tool/upstream_status.json', line)
        self.assertNotIn('dart pub publish', text)

    def test_bootstrap_has_no_automatic_publication(self):
        self.assertNotIn('release', self.jobs)
        self.assertFalse((WORKFLOWS / 'publish.yml').exists())
        self.assertFalse(any(
            'workflows/publish.yml' in p.read_text()
            for p in WORKFLOWS.glob('*.yml')
        ))

    def setUp(self):
        self.caller = (WORKFLOWS / 'ci.yml').read_text()
        self.jobs = job_blocks(self.caller)

    def test_only_coordinator_handles_events_and_every_module_uses_same_commit(self):
        expected = {'tests', 'compatibility', 'documentation', 'package', 'quality'}
        self.assertEqual(expected, set(self.jobs))
        self.assertLess(len(self.caller.splitlines()), 100)
        self.assertNotIn('dart pub', self.caller)
        called = []
        for name in expected - {'quality'}:
            match = re.search(r'^    uses: (\./\.github/workflows/[\w-]+\.yml)$', self.jobs[name], re.M)
            self.assertIsNotNone(match, name)
            module = ROOT / match.group(1)
            self.assertTrue(module.is_file(), module)
            text = module.read_text()
            self.assertIn('\non:\n  workflow_call:\n', text)
            events = text.split('\npermissions:\n', 1)[0]
            self.assertNotRegex(events, r'(?m)^  (push|pull_request|workflow_run|workflow_dispatch|release):')
            called.append(module.name)
        self.assertEqual(set(called) | {'ci.yml', 'upstream-sync.yml', 'screenshots.yml'},
                         {f.name for f in WORKFLOWS.glob('*.yml')})

    def test_workflow_names_and_identifiers_have_no_inherited_or_package_prefix(self):
        for file in [*WORKFLOWS.glob('*.yml'), ROOT / '.github/actions/setup-flutter/action.yml']:
            self.assertNotRegex(file.name, r'(?i)(morph|mingcute)[-_]')
            self.assertNotRegex(file.read_text(), r'(?i)morph|fluent|mingcute_icons_kit')

    def test_stages_wait_for_previous_stage_and_gate_covers_all(self):
        for stage, dependency in [('compatibility', 'tests'), ('documentation', 'compatibility'),
                                  ('package', 'documentation')]:
            self.assertRegex(self.jobs[stage], rf'(?m)^    needs: {dependency}$')
        self.assertIn('needs: [tests, compatibility, documentation, package]', self.jobs['quality'])
        self.assertIn('if: ${{ always() }}', self.jobs['quality'])

    def test_real_gate_rejects_failed_cancelled_and_skipped_stages(self):
        script = textwrap.dedent(self.jobs['quality'].split('        run: |\n', 1)[1])
        names = ['TESTS_RESULT', 'COMPATIBILITY_RESULT', 'DOCUMENTATION_RESULT', 'PACKAGE_RESULT']
        cases = [(None, None)] + [(name, state) for name in names for state in ['failure', 'cancelled', 'skipped']]
        for name, state in cases:
            with self.subTest(stage=name, state=state):
                env = dict(os.environ, **{key: 'success' for key in names})
                if name:
                    env[name] = state
                result = subprocess.run(['bash', '--noprofile', '--norc', '-e', '-c', script],
                                        env=env, capture_output=True)
                self.assertEqual(name is None, result.returncode == 0)

    def test_quality_workflows_have_no_write_or_oidc_permissions(self):
        for name, body in self.jobs.items():
            self.assertNotIn('id-token: write', body, name)
            self.assertNotIn('contents: write', body, name)
        for path in WORKFLOWS.glob('*.yml'):
            if path.name != 'upstream-sync.yml':
                self.assertNotIn('id-token: write', path.read_text(), path.name)
                self.assertNotIn('contents: write', path.read_text(), path.name)

    def test_upstream_sync_is_scheduled_data_only_and_never_publishes(self):
        text = (WORKFLOWS / 'upstream-sync.yml').read_text()
        self.assertIn('schedule:', text)
        self.assertIn('workflow_dispatch:', text)
        self.assertNotIn('id-token', text)
        self.assertNotIn('pub publish', text)
        self.assertNotIn('--source', text)  # fetches upstream itself, no manual clone
        self.assertIn('tool/sync_icons.py --min-icons 2200', text)
        self.assertNotRegex(text, r'pull_request_target')
        jobs = job_blocks(text)
        self.assertNotIn('contents: write', jobs['sync'])
        self.assertIn('contents: write', jobs['propose'])

    def test_failed_upstream_checks_are_reported_in_a_draft_pr_and_never_merged(self):
        text = (WORKFLOWS / 'upstream-sync.yml').read_text()
        self.assertIn('bash tool/check.sh 2>&1 | tee', text)
        self.assertIn('PIPESTATUS[0]', text)          # real exit code, not tee's
        self.assertIn('CHECKS FAILED', text)
        self.assertIn('DO NOT MERGE', text)
        self.assertIn('--draft', text)                # failing proposals are drafts
        self.assertIn('check.log', text)              # causes travel into the PR
        self.assertNotRegex(text, r'gh pr merge|--auto|auto-merge|automerge')
        self.assertNotIn('pub publish', text)

    def test_actions_are_pinned_by_commit_sha(self):
        for path in [*WORKFLOWS.glob('*.yml'), ROOT / '.github/actions/setup-flutter/action.yml']:
            for use in re.findall(r'uses: ([^\s]+)', path.read_text()):
                if use.startswith('./'):
                    continue
                self.assertRegex(use, r'@[0-9a-f]{40}$', f'{path.name}: {use}')

    def test_no_workflow_can_swallow_a_failure(self):
        for path in WORKFLOWS.glob('*.yml'):
            text = path.read_text()
            self.assertNotIn('continue-on-error', text, path.name)
            self.assertNotRegex(text, r'\|\|\s*(true|echo|:)\b', path.name)
            self.assertNotRegex(text, r'(?m)^\s*if:.*failure\(\).*\n\s*run:.*(pana|publish)', path.name)

    def test_pana_has_a_single_source_of_truth_used_by_the_package_job(self):
        package = (WORKFLOWS / 'package.yml').read_text()
        self.assertIn('bash tool/ci/run_pana.sh', package)
        for path in WORKFLOWS.glob('*.yml'):
            self.assertNotIn('pana:pana', path.read_text(), path.name)  # never re-implemented inline
        script = (ROOT / 'tool/ci/run_pana.sh').read_text()
        self.assertIn('set -euo pipefail', script)
        self.assertIn("PANA_VERSION='0.23.19'", script)
        self.assertIn('--exit-code-threshold=0', script)
        self.assertIn('check_pana_score.py', script)
        self.assertNotRegex(script, r'\|\|\s*(true|:)')
        gate = (ROOT / 'tool/ci/check_pana_score.py').read_text()
        self.assertEqual(1, gate.count('EXPECTED_MAX = 160\n'))
        self.assertNotRegex(gate, r'environ|getenv|argv\[[2-9]\]')  # the bar is not configurable

    def test_package_failure_blocks_aggregate_gate(self):
        self.assertRegex(
            self.jobs['package'],
            r'(?m)^    needs: documentation$',
        )
        self.assertIn('package', self.jobs['quality'])
        self.assertNotIn('release', self.jobs)
        self.assertIn(
            'name: All required quality checks',
            self.jobs['quality'],
        )
        self.assertNotIn('continue-on-error', self.jobs['package'])

    def test_package_stage_requires_exact_full_score_and_archive_inspection(self):
        text = (WORKFLOWS / 'package.yml').read_text()
        self.assertIn('tool/ci/run_pana.sh', text)
        self.assertIn('check_pana_tools.sh', text)
        self.assertIn('archive-files', text)
        self.assertIn('dart pub publish --dry-run', text)

    def test_bootstrap_excludes_publish_workflow(self):
        self.assertFalse((WORKFLOWS / 'publish.yml').exists())
        for path in WORKFLOWS.glob('*.yml'):
            content = path.read_text()
            self.assertNotIn('workflows/publish.yml', content)
            self.assertNotIn('bash tool/ci/publish.sh', content)
            self.assertNotIn('tool/ci/release.py finalize', content)

    def test_each_flutter_job_checks_out_before_shared_sdk_setup(self):
        action = ROOT / '.github/actions/setup-flutter/action.yml'
        self.assertTrue(action.is_file())
        self.assertIn("flutter-version: '3.47.9'", action.read_text())
        for name in ['tests', 'compatibility', 'package']:
            text = (WORKFLOWS / f'{name}.yml').read_text()
            self.assertLess(text.index('uses: actions/checkout@'), text.index('uses: ./.github/actions/setup-flutter'))
            self.assertNotIn('flutter-version:', text)


if __name__ == '__main__':
    unittest.main()
