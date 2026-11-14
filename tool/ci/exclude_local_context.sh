#!/usr/bin/env bash
# Idempotently keep local agent context and reference snapshots out of Git via
# .git/info/exclude (never .gitignore). Supports worktrees. Entries that are
# already in the index are removed from the index only (files stay on disk).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
git rev-parse --show-toplevel >/dev/null 2>&1 || { echo 'Not a Git checkout: nothing to configure.' >&2; exit 1; }
EXCLUDE="$(git rev-parse --git-path info/exclude)"
mkdir -p "$(dirname "$EXCLUDE")"
touch "$EXCLUDE"
PATTERNS=(
  '/.agents/'
  '/.serena/'
  '/AGENTS.md'
  '/**/AGENTS.md'
  '/PROMPT_*.md'
  '/snapshots/'
  '/mingcute_icons-snapshot-*.zip'
  '/morph_expressive-snapshot-*.zip'
)
for pattern in "${PATTERNS[@]}"; do
  grep -qxF -- "$pattern" "$EXCLUDE" || printf '%s\n' "$pattern" >> "$EXCLUDE"
done
# Already tracked? Drop only the index entries (review with `git status`).
# NUL separators also protect filenames containing spaces or newlines.
while IFS= read -r -d '' file; do
  git rm --cached --quiet -- "$file"
  printf 'Removed local-context entry from index (kept on disk): %q\n' "$file"
done < <(git ls-files -z --cached -- .agents .serena AGENTS.md '**/AGENTS.md' \
  ':(top,glob)PROMPT_*.md' snapshots ':(top,glob)mingcute_icons-snapshot-*.zip' \
  ':(top,glob)morph_expressive-snapshot-*.zip')
echo "Local context excluded via $EXCLUDE"
