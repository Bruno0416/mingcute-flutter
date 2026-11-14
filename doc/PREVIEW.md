# Preview and screenshots

## Interactive gallery

```bash
cd preview
flutter pub get
flutter run -d linux      # or -d chrome
```

Search by name, compare Regular/Filled, change the size, toggle alignment guides
and tap an icon to copy its `Icon(MingCute...)` code.

## Capture mode

The same app has a static, animation-free mode controlled only by URL
parameters, so images never depend on manual state:

`?capture=<hero|regular|filled|comparison|detail>` plus optional `theme=dark|light`,
`style=both|regular|filled`, `size=12..96`, `cols=1..12`, `q=<search>`,
`names=a,b,c`, `page=N`, `limit=N`, `guides=1`.

Unknown scenes, invalid values and unknown icon names are rejected
(`MINGCUTE_CAPTURE_ERROR` on the console) instead of drawing placeholder boxes.
When every glyph is laid out the page prints `MINGCUTE_CAPTURE_READY {json}`;
the capturer waits for that signal, not for a timer.

## Generating the screenshots

```bash
bash tool/generate_screenshots.sh                 # build, serve on 127.0.0.1, capture all scenes
bash tool/generate_screenshots.sh --only hero-dark,detail
bash tool/generate_screenshots.sh --skip-build    # reuse preview/build/web
bash tool/generate_screenshots.sh --check         # validate PNGs, manifest and freshness (no browser)
bash tool/generate_screenshots.sh --check --pixels --skip-build   # re-capture and require 0 differing pixels
```

Needs Flutter, Node 20+ and Playwright's Chromium (`npm ci` runs inside
`tool/screenshot_capture`; set `MINGCUTE_SCREENSHOT_BROWSER` to use another
Chromium). The Web build uses `--no-web-resources-cdn`, so no network is needed
while capturing. Scenes and viewport (1280x800 at 2x, 2560x1600 PNG) live in
`tool/screenshot_capture/scenes.json`; the result goes to
`doc/assets/screenshots/` with a `manifest.json` that records the scene
parameters, the displayed icons, hashes and an input fingerprint. The pixel
comparison prints the exact number of differing pixels and demands zero; it is
meant for the same environment (Chromium build and fonts) that created the images.

## README images on pub.dev

`pubspec.yaml` lists the screenshots by local path, so they remain part of the
pub.dev archive. The README uses absolute `raw.githubusercontent.com` links to
`Bruno0416/mingcute-flutter/main` for screenshots and its original upstream
banner, so images work on GitHub and pub.dev after the first push. The
`tool/ci/check_docs.py` validator checks the screenshot owner, branch, and
local asset case; `tool/readme_metadata.py` verifies the banner source,
provenance and expected repository link. These are configured URLs, not a claim
that the remote has been populated or that the package is already published.
