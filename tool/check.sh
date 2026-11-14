#!/usr/bin/env bash
# Single verification entry point: Python pipeline, repository guards, Flutter
# analysis/tests for the package and the preview. Requires a configured .venv or
# an environment with tool/requirements.txt installed.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY=python3
[[ -x "$ROOT/.venv/bin/python" ]] && PY="$ROOT/.venv/bin/python"
"$PY" -c 'import fontTools, defusedxml' 2>/dev/null || {
  printf '%s\n' 'Install tool/requirements.txt first (python -m pip install -r tool/requirements.txt).' >&2
  exit 1
}

"$PY" -m unittest discover -s tool/tests -p 'test_*.py'
"$PY" tool/validate.py --min-icons 2200
"$PY" -m unittest discover -s tool/ci/tests -p 'test_*.py'
"$PY" tool/ci/check_docs.py
"$PY" tool/ci/check_markdown_links.py
"$PY" tool/ci/check_final_release_language.py --all
"$PY" tool/ci/version.py check
"$PY" tool/ci/release_guard.py metadata
"$PY" tool/screenshots.py check

command -v flutter >/dev/null || { printf '%s\n' 'Flutter SDK is required for analysis and tests.' >&2; exit 1; }
# Resolve BOTH package configurations before the first analysis or test.
flutter pub get
(cd preview && flutter pub get)
for package_config in .dart_tool/package_config.json preview/.dart_tool/package_config.json; do
  test -s "$package_config" || { printf 'Missing package configuration: %s\n' "$package_config" >&2; exit 1; }
done
flutter analyze
flutter test
(
  cd preview
  flutter analyze
  flutter test
)
printf '%s\n' 'mingcute_icons: all checks completed.'
