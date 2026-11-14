# Generator

Pipeline: upstream SVG (data only) to normalised glyph outlines to two TTF files
to generated Dart `IconData` classes plus a preview catalogue.

| Step | Where |
|---|---|
| Fetch upstream (shallow clone in `tool/.cache/upstream/`, or `--source DIR`) | `tool/sync_icons.py` |
| Parse SVG with `defusedxml`, reject masks/filters, flatten gradients/opacity | `convert_svg` in `tool/sync_icons.py` |
| Normalise to a 1024 unit em (ascent 896, descent -128) and build glyphs | `fontTools` in `tool/sync_icons.py` |
| Assign codepoints from the ledger, new ones appended | `tool/codepoints.json` |
| Write fonts and Dart | `assets/fonts/*.ttf`, `lib/mingcute_icons.dart`, `lib/src/generated/*.g.dart`, `preview/lib/generated_catalog.dart` |
| Record metadata (`sourceRevision`, per-icon hashes, notes) | `tool/manifest.json`, `tool/last_sync_report.json` |
| Generate independent public static constants from the same ledger | `lib/mingcute_static.dart` |
| Verify coordinated version at that exact Git SHA | upstream `release.json` → manifest `upstream` |
| Refresh README blocks, optionally observe latest main | `tool/readme_metadata.py`, `tool/upstream_status.json` |

## Commands

```bash
python tool/sync_icons.py --min-icons 2200   # no --source: clone/fetch automatically
python tool/sync_icons.py --source ../mingcute-icons   # offline, checkout never modified
python tool/audit_upstream.py                # read-only support audit
python tool/validate.py --min-icons 2200     # cmap == ledger, Dart names, glyph shapes, parity
python tool/verify_rebuild.py                # sandbox: fresh clone, build, delete outputs, rebuild, idempotence
python -m unittest discover -s tool/tests -v
```

Upstream content is only ever read as data; none of its code is executed.

The generated public entry is `MingCute`; private constants back the generated
`MingCute.regular` and `MingCute.filled` getters. `generatorVersion` identifies
the font pipeline; `apiVersion` identifies the Dart API independently. An API-only
repair rewrites stale Dart/catalogue files without calling the font builder or
SVG converter when artwork metadata and font hashes still match. The catalogue
is a single unmodifiable, lazily initialised list; getters reuse constant icons.
An unchanged sync reports `skipped: true`. The sync report records each run's
status and can change once from the generating run to the skipped run; generated
artefacts are not rewritten when their bytes match.

## The ledger is append-only

`tool/codepoints.json` maps every icon name ever generated to its private-use
codepoint. A removed upstream icon is reported but keeps its codepoint, which is
never reused for another icon. Re-running the generator with unchanged input is
a no-op (identical bytes); a modified SVG keeps its identity and codepoint.
A name collision or an unsafe/unsupported SVG stops the run before any output
is written.

## Source versus derived files

SVG files are the sources (not copied into this repository). Fonts, generated
Dart, the catalogue and the manifest are derived and should not be edited by
hand. `sourceRevision` in `tool/manifest.json` records the upstream commit used.
Icons with approximations are listed in `monochromeNotes`.

## Three independent version values

Both APIs are generated from the same records and append-only ledger. The
principal `MingCute` getters remain in `mingcute_icons.dart`; the independently
importable `mingcute_static.dart` defines annotated `MingCuteRegularConst` and
`MingCuteFilledConst` providers with only static constant IconData fields. It
neither imports nor exports the getters. Do not hand-edit these declarations.
`validate.py` checks byte-for-byte rendered parity of both libraries; the rebuild
check deletes/regenerates both only inside its sandbox. Missing or stale static
Dart is repaired on sync without rebuilding unchanged fonts. A repeated sync
skips identical outputs. There is no second registry or new runtime dependency.

- **Wrapper source version:** `pubspec.yaml`. This is not evidence of publication.
- **Synced MingCute version:** `upstream.version` in `tool/manifest.json`, read
  with `git show <sourceRevision>:release.json`. `sourceRevision` remains the
  canonical SHA; it is not duplicated inside `upstream`. Modified tracked SVGs,
  extra untracked SVGs or a modified release file prevent a verified Git claim.
- **Latest declared MingCute version:** an optional observation of official
  `main`, stored in `tool/upstream_status.json`. Git identifies the SHA first;
  the raw `release.json` request is pinned to that SHA. It does not infer a
  version from package.json, tags or GitHub Releases.

The generator treats release/provenance changes independently of artwork.
An upstream version-only commit updates the manifest without rebuilding TTFs.
Changing the wrapper version never changes the synced upstream version.
Non-Git test fixtures are explicitly `local-source`, with no verified version.
Missing or invalid `release.json` in a Git source fails closed before writes.

```bash
python tool/readme_metadata.py --check                   # offline, no writes
python tool/readme_metadata.py --write                   # offline block update
python tool/readme_metadata.py --refresh-latest --write  # explicit network observation
```

Only `MINGCUTE BADGES` and `MINGCUTE STATUS` delimited blocks are generated.
Manual prose is left untouched; missing/duplicate markers cause an error.
Unchanged content is not rewritten. A failed latest-version query does not
invent a value or replace the previous observation. An absent observation is
reported as unknown. If the synced version is newer than the cached observation,
the table requires a refresh instead of claiming the catalogue is current.

The latest badge reads the official `main/release.json` through Shields.io;
the adjacent table labels its last checked revision explicitly. A newer live
badge does not mean those icons are already integrated. PR documentation checks
are offline. The scheduled upstream workflow explicitly refreshes the observation
and proposes manifest/README changes for review, never a publication.

## Banner and Web assets

The README banner is the unchanged upstream `images/banner1.png`, pinned and
attributed in [the branding record](assets/branding/ATTRIBUTION.json). Licence
and trademark scope are described in [third-party notices](../THIRD_PARTY_NOTICES.md).
It is not the wrapper's logo. The Web favicon/PWA tiles are separate original
demo graphics. `python tool/generate_preview_icons.py --check` validates PNG
structure, CRCs, dimensions, RGB/RGBA decoding and exact RGBA pixels against the
generated geometry. Equivalent zlib streams pass; any pixel/alpha change fails.
