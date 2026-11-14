# Contributing

Thanks for helping. This is an unofficial adapter of MingCute Design's icons;
icon artwork issues belong upstream
([mingcute-design/mingcute-icons](https://github.com/mingcute-design/mingcute-icons)).

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
python -m pip install -r tool/requirements.txt
flutter pub get && (cd preview && flutter pub get)
```

## Before opening a pull request

```bash
bash tool/check.sh                      # Python tests, guards, Flutter analyze/test (root and preview)
bash tool/check_dependency_matrix.sh all   # latest and lowest dependency resolution
```

Do not hand-edit generated files (`lib/src/generated`, `assets/fonts`,
`preview/lib/generated_catalog.dart`, `tool/manifest.json`, `tool/codepoints.json`):
change the generator and regenerate. If a change affects icons or the capture
scenes, regenerate screenshots with `bash tool/generate_screenshots.sh`.

Changes that alter the public API need a `CHANGELOG.md` entry; versions are
managed with `python tool/ci/version.py` (see [doc/RELEASE.md](doc/RELEASE.md)).
Never remove or reuse a codepoint.

## Licensing

Contributions to code are accepted under the MIT licence. Do not add artwork
that is not covered by the upstream Apache-2.0 licence.
