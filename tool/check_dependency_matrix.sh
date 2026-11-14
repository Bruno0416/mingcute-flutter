#!/usr/bin/env bash
# Resolve `latest` and `lowest` dependencies in disposable copies (the working
# pubspec.lock files are never rewritten), then analyse, test, build the Web
# preview and compile a minimal consumer app that imports the package.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-all}"
case "$MODE" in
  all) MODES=(latest lowest) ;;
  latest|lowest) MODES=("$MODE") ;;
  *) printf 'Usage: bash tool/check_dependency_matrix.sh [all|latest|lowest]\n' >&2; exit 2 ;;
esac
command -v flutter >/dev/null || { printf 'Flutter SDK is required.\n' >&2; exit 1; }
WORK="$(mktemp -d "${TMPDIR:-/tmp}/mingcute-dependencies.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

for resolution in "${MODES[@]}"; do
  target="$WORK/$resolution"
  python3 - "$ROOT" "$target" <<'PY'
from pathlib import Path
import shutil
import sys

source, target = map(Path, sys.argv[1:])
shutil.copytree(
    source, target,
    ignore=shutil.ignore_patterns(
        '.git', '.idea', '.dart_tool', '.gradle', '.cxx', '.venv', '.agents', 'node_modules',
        '.plugin_symlinks', 'build', 'coverage', '__pycache__', 'ephemeral', 'Pods',
        '*.zip', '*.patch', 'pubspec.lock', '.flutter-plugins-dependencies',
        'AGENTS.md', 'PROMPT_*.md', '.cache',
    ),
)
PY
  (
    cd "$target"
    printf '\nDependency resolution: %s\n' "$resolution"
    if [[ "$resolution" == latest ]]; then
      flutter pub upgrade
      (cd preview && flutter pub upgrade)
    else
      flutter pub downgrade
      (cd preview && flutter pub downgrade)
    fi
    flutter pub deps --style=compact
    dart format --output=none --set-exit-if-changed lib example/lib preview/lib preview/test
    flutter analyze
    flutter test
    (cd preview && flutter analyze && flutter test && flutter build web --release --no-pub)
    # Consumer app: depends on the package by path, as a real app would.
    mkdir "$WORK/consumer-$resolution" && cp -r example/. "$WORK/consumer-$resolution/"
    (
      cd "$WORK/consumer-$resolution"
      sed -i "s#path: ../#path: $target#" pubspec.yaml
      flutter create --platforms=web --no-pub . >/dev/null
      rm -rf test analysis_options.yaml
      mkdir test
      cat > test/consumer_test.dart <<'DART'
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mingcute_icons/mingcute_icons.dart';

void main() {
  testWidgets('consumer renders Regular and Filled IconData', (tester) async {
    await tester.pumpWidget(MaterialApp(home: Row(children: [
      Icon(MingCute.regular.home_1),
      Icon(MingCute.filled.home_1),
    ])));
    expect(find.byType(Icon), findsNWidgets(2));
    expect(MingCute.regular.home_1.fontFamily, 'MingCuteRegular');
    expect(MingCute.filled.home_1.fontPackage, 'mingcute_icons');
  });
}
DART
      flutter pub add 'dev:flutter_test:{"sdk":"flutter"}'
      flutter analyze
      flutter test
      flutter build web --release --no-pub
    )
  )
done
printf '%s\n' 'Dependency matrix completed.'
