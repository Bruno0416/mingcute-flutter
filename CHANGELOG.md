# Changelog

All notable changes to `mingcute_icons` are documented here. The project follows
[Semantic Versioning](https://semver.org/); see [doc/RELEASE.md](doc/RELEASE.md)
for how icon changes map to version parts.

## 0.1.0

First public version of the unofficial MingCute Core adapter for Flutter.

- Independent generated `mingcute_static.dart` with `MingCuteRegularConst` and
  `MingCuteFilledConst` for verified native font subsetting and const widgets.
- Separate primary functional, static mandatory-subsetting and mixed consumer
  checks; getter and mixed-use full-font retention remains documented.
- README header ordered as title, badges, original banner and unofficial notice,
  with structural regression checks and existing artwork preserved.

- Official upstream banner with pinned provenance and a visible unofficial notice.
- Generated README badges/catalogue status distinguish wrapper source, synced
  MingCute `release.json` and an independently refreshed latest observation.
- Web PNG reproducibility compares fully decoded RGBA pixels and integrity,
  not compressor-specific bytes; corrupt, missing or altered assets fail.
- Four-icon consumer evidence and isolated record/static-constant experiments
  preserve the strict failure of the primary getter API's subsetting gate.

- Native `IconData` for **MingCute Core Regular** and **Core Filled**:
  2,263 icons per style, 4,526 glyphs,
  generated from upstream revision `9dc7d3ad074fb16477096a6a8109a6467d0e2fe3`.
- Definitive single-entry API: `MingCute.regular.home_1` and
  `MingCute.filled.home_1`, generated typed getters reusing private constants.
  Getter expressions are not valid inside `const Icon(...)`.
  The current Flutter release consumer retains all glyphs through these getters;
  unused-glyph subsetting remains a documented, failing local acceptance gate.
- Dart-only regeneration preserves unchanged fonts without reconverting SVGs.
- Source snapshots exclude private context, credentials, caches and symlinks;
  local Git exclusions cover current and future prompts and snapshots.
- Gallery-specific Web metadata and original neutral demo icons.
- Two bundled TrueType fonts (`MingCuteRegular`, `MingCuteFilled`) converted
  from the upstream SVG files, with a persistent append-only codepoint ledger so
  codepoints are never reused.
- Reproducible generator (`tool/sync_icons.py`), validator, upstream audit and a
  clean-room rebuild check (`tool/verify_rebuild.py`).
- Local preview gallery and reproducible pub.dev screenshots.
- SVG artwork by MingCute Design under Apache-2.0; adapter code under MIT. See
  `THIRD_PARTY_NOTICES.md`.
