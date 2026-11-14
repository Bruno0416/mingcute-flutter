#!/usr/bin/env bash
# The ONE place that runs pana for CI and for local checks. Fail-closed:
# only grantedPoints == maxPoints == 160 exits 0.
#
#   bash tool/ci/run_pana.sh REPORT.json [PACKAGE_DIR|PACKAGE.tar.gz]
#
# `--exit-code-threshold=0` is the strictest setting: pana exits non-zero (127)
# as soon as ANY point is lost, and also fails when it breaks. It does not
# relax anything. Independently, check_pana_score.py demands the exact
# 160/160 in the JSON (and a maximum of 160). Both must succeed: the script
# runs the verifier even after a failed pana run only to print which sections
# lost points, and then exits with the first non-zero code.
set -euo pipefail
PANA_VERSION='0.23.19'   # pinned; bump deliberately together with the tests
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT="${1:?usage: run_pana.sh REPORT.json [PACKAGE_DIR]}"
PACKAGE_DIR="${2:-.}"

for tool in dart python3 mktemp cp rm dirname grep; do
  command -v "$tool" >/dev/null 2>&1 || {
    printf 'Missing required tool: %s\n' "$tool" >&2; exit 1;
  }
done
# Only our private workspace is cleaned up. The caller's report is an explicit
# output, never an input: truncate it before any operation that could fail.
test ! -L "$REPORT" || { echo 'Report must not be a symbolic link.' >&2; exit 1; }
: > "$REPORT"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/mingcute-pana.XXXXXX")"
trap 'rm -rf -- "$WORK"' EXIT

if [ -f "$PACKAGE_DIR" ]; then
  python3 - "$HERE" "$PACKAGE_DIR" "$WORK/package" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from release_guard import archive_files, check_archive_content
files = archive_files(Path(sys.argv[2]).read_bytes())
check_archive_content(files)
target = Path(sys.argv[3])
for name, data in files.items():
    path = target / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
PY
  PACKAGE_DIR="$WORK/package"
fi
test -d "$PACKAGE_DIR" || { echo 'Package directory/archive does not exist.' >&2; exit 1; }

bash "$HERE/check_pana_tools.sh"

dart pub global activate pana "$PANA_VERSION"
dart pub global list | grep -Fxq "pana $PANA_VERSION" \
  || { printf 'pana %s is not the active version; refusing to score.\n' "$PANA_VERSION" >&2; exit 1; }

# stdout is the JSON report; pana's logs go to stderr.
pana_rc=0
( cd "$PACKAGE_DIR" && dart pub global run pana:pana --json --exit-code-threshold=0 . ) > "$WORK/pana.json" || pana_rc=$?
cp -- "$WORK/pana.json" "$REPORT"
score_rc=0
score_message="$(python3 "$HERE/check_pana_score.py" "$REPORT")" || score_rc=$?

if [ "$pana_rc" -ne 0 ]; then
  printf 'pana exited with code %s: gate FAILED (a perfect-looking report cannot override it).\n' "$pana_rc" >&2
  exit "$pana_rc"
fi
if [ "$score_rc" -eq 0 ]; then printf '%s\n' "$score_message"; fi
exit "$score_rc"
