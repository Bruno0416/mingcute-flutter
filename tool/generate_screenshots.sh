#!/usr/bin/env bash
# Generate or verify the PNG screenshots from the real Flutter Web preview.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CAPTURE="$ROOT/tool/screenshot_capture"
OUT="$ROOT/doc/assets/screenshots"
ONLY=""; CHECK=0; PIXELS=0; SKIP_BUILD=0; PORT="${MINGCUTE_SCREENSHOT_PORT:-0}"

usage() {
  cat <<'USAGE'
Usage: bash tool/generate_screenshots.sh [options]

  --only a,b     capture only these scenes (see tool/screenshot_capture/scenes.json)
  --check        do not write images: validate PNGs, manifest, catalogue and freshness
  --pixels       with --check, also re-capture and require a pixel-identical result
                 (differing pixel counts are always printed; needs Chromium + build)
  --skip-build   reuse preview/build/web instead of running flutter build web
  --port N       local server port on 127.0.0.1 (default: a free port)
  -h, --help     show this help

Needs: Flutter (build), Node >= 20 and Playwright Chromium (npm ci runs here).
Set MINGCUTE_SCREENSHOT_BROWSER to use a specific Chromium executable.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --only) [[ $# -ge 2 ]] || { echo '--only needs a value' >&2; exit 2; }; ONLY="$2"; shift 2 ;;
    --check) CHECK=1; shift ;;
    --pixels) PIXELS=1; shift ;;
    --skip-build) SKIP_BUILD=1; shift ;;
    --port) [[ $# -ge 2 ]] || { echo '--port needs a value' >&2; exit 2; }; PORT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done
[[ "$PIXELS" == 0 || "$CHECK" == 1 ]] || { echo '--pixels requires --check' >&2; exit 2; }

if [[ "$CHECK" == 1 ]]; then
  python3 "$ROOT/tool/screenshots.py" check
  [[ "$PIXELS" == 1 ]] || exit 0
fi

command -v node >/dev/null || { echo 'Node.js is required.' >&2; exit 1; }
if [[ "$SKIP_BUILD" == 0 ]]; then
  command -v flutter >/dev/null || { echo 'Flutter SDK is required for the build.' >&2; exit 1; }
  (cd "$ROOT/preview" && flutter pub get && flutter build web --release --no-web-resources-cdn)
fi
[[ -f "$ROOT/preview/build/web/index.html" ]] || { echo 'preview/build/web is missing; run without --skip-build.' >&2; exit 1; }
(cd "$CAPTURE" && npm ci --no-audit --no-fund)
(cd "$CAPTURE" && node -e "require('node:fs').accessSync(require('playwright').chromium.executablePath())" 2>/dev/null) \
  || [[ -n "${MINGCUTE_SCREENSHOT_BROWSER:-}" ]] \
  || (cd "$CAPTURE" && npx playwright install chromium)

WORK="$(mktemp -d "${TMPDIR:-/tmp}/mingcute-shots.XXXXXX")"
SERVER_PID=""
cleanup() { [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null || true; rm -rf "$WORK"; }
trap cleanup EXIT INT TERM

if [[ "$PORT" == 0 ]]; then
  PORT="$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])')"
fi
python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$ROOT/preview/build/web" >"$WORK/server.log" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 50); do
  curl --silent --fail "http://127.0.0.1:$PORT/" >/dev/null 2>&1 && break
  kill -0 "$SERVER_PID" 2>/dev/null || { cat "$WORK/server.log" >&2; echo 'Local server failed to start.' >&2; exit 1; }
  sleep 0.2
done

ARGS=(--url "http://127.0.0.1:$PORT/" --results "$WORK/results.json")
[[ -n "$ONLY" ]] && ARGS+=(--only "$ONLY")
if [[ "$CHECK" == 1 ]]; then
  ARGS+=(--compare "$OUT" --out "$WORK/unused")
  (cd "$CAPTURE" && node capture.mjs "${ARGS[@]}")
  echo 'PASS: fresh captures are pixel-identical to the stored images.'
  exit 0
fi
mkdir -p "$OUT"
ARGS+=(--out "$OUT")
(cd "$CAPTURE" && node capture.mjs "${ARGS[@]}")
python3 "$ROOT/tool/screenshots.py" manifest --results "$WORK/results.json"
python3 "$ROOT/tool/screenshots.py" check
