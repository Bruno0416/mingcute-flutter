#!/usr/bin/env bash
# Optional: install a pre-commit hook that runs the final-language and local
# context guards. Never overwrites an existing hook.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
HOOKS="$(git rev-parse --git-path hooks)"
mkdir -p "$HOOKS"
if [[ -e "$HOOKS/pre-commit" ]]; then
  echo "A pre-commit hook already exists at $HOOKS/pre-commit; not overwriting it." >&2
  exit 1
fi
cat > "$HOOKS/pre-commit" <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
python3 "$root/tool/ci/check_final_release_language.py" --staged
python3 "$root/tool/ci/release_guard.py" check-local-context
HOOK
chmod +x "$HOOKS/pre-commit"
echo "Installed $HOOKS/pre-commit"
