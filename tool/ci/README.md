# CI and release tooling

Versioned guards used by `.github/workflows/*`. They use only the Python
standard library and never depend on local agent context.

| Script | Purpose |
|---|---|
| `release_guard.py metadata\|check-local-context\|archive-files\|notes\|published` | pubspec/changelog/store metadata, tracked-context check, semantic inspection of pub's real archive, exact release notes |
| `release.py plan\|assert-current-main\|finalize` | main-only release orchestration: decisions `validate-only`, `stale`, `bootstrap-pending`, `blocked`, `conflict`, `already-published`, `recover`, `publish` |
| `publish.sh` | upload step, only after a `publish` decision and short-lived credentials |
| `version.py check\|suggest\|bump` | SemVer helper; `bump` previews unless `--write` and real `--notes` are given |
| `check_docs.py` | identity, credits, README API vs generated API, counts, screenshot URLs, licences |
| `check_markdown_links.py` | local Markdown/HTML link and asset targets |
| `check_final_release_language.py` | blocks provisional-release labels (`--all`, `--staged`, `--revision`) |
| `check_pana_score.py` | requires exactly 160/160 from `pana --json` |
| `check_pana_tools.sh` | verifies the WebP tools pana needs |
| `exclude_local_context.sh` | idempotent `.git/info/exclude` entries for local agent context |
| `install_git_hooks.sh` | optional pre-commit hook; never overwrites an existing one |

Run the tests with `python -m unittest discover -s tool/ci/tests -v`. They use
mocks and temporary repositories; no test touches pub.dev, GitHub or the network.

Publication route and external configuration: [doc/RELEASE.md](../../doc/RELEASE.md).
