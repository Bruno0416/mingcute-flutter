# Icons and API

## Classes

| Symbol | Meaning |
|---|---|
| `MingCute.regular` | typed getters returning native `IconData`, font family `MingCuteRegular` |
| `MingCute.filled` | typed getters returning native `IconData`, font family `MingCuteFilled` |

`IconData` is the standard Flutter type; no custom widget is required.

In `mingcute_icons.dart`, the public entry class is `MingCute`. Each namespace is a constant instance
of a private generated accessor class. Its getters return private static constant
`IconData` objects, so repeated reads reuse the same object.

Use `Icon(MingCute.regular.home_1)`, not a `const Icon` expression: Dart does not
evaluate getter calls as compile-time constants. Font subsetting is a separate
Flutter release-build check, not a consequence of widget constness. The local
consumer check builds the real example and inspects both resulting font cmaps:

```bash
python tool/verify_consumer.py --scenario primary-contract --report /tmp/mingcute-primary.json
```

**Known getter limitation:** the verified Flutter SDK's constant finder
visits every generated getter body. Annotating the private static constant
providers with `@staticIconProvider` excludes their declarations, but does not
exclude the getters' constant references. The two-icon-per-style release example
therefore retains all 2,263 glyphs in each font. The primary functional contract
records this separately from successful rendering; no claim of unused-glyph elimination is made for this
API. Fixing that without changing the requested call syntax or depending on a
custom build pipeline remains unresolved. The preview deliberately references
the complete catalogue, so its full fonts are expected.

## Static API — Recommended for optimized release size

```dart
import 'package:flutter/material.dart';
import 'package:mingcute_icons/mingcute_static.dart';

const home = Icon(MingCuteRegularConst.home_1);
const heart = Icon(MingCuteFilledConst.heart);
```

The independently generated library exposes 2,263 symbols per style through
`@staticIconProvider` classes containing static const IconData fields. It has no
import/export of `mingcute_icons.dart` or dependency on private accessors. It uses
the same names, ledger, families and codepoints. No generator is required in the
consumer. All standard Icon, IconButton and IconTheme behaviour is preserved.

The principal API is recommended for convenience; this static API is recommended
for optimized release size. **Use only the static library when size matters.**
The tested mixed app uses getters for Regular home and Filled heart, and static
constants for Regular search and Filled star: both complete fonts are retained.
This demonstrates mixed usage, not a guarantee about every possible import graph.

### Reproducible consumer comparison

The strict four-icon consumer uses Regular `home_1`/`search_2` and Filled
`heart`/`star`. Its widget test checks all four rendered glyph strings and native
families; the release check reads the actual TTF cmaps, validates the required
outlines and rejects missing or ambiguous font assets.

The three public consumer scenarios build against the actual checkout package,
not a synthetic static provider or a copied subset of declarations:

```bash
python tool/verify_consumer.py --scenario primary-contract --report /tmp/mingcute-primary.json
python tool/verify_consumer.py --scenario static-subsetting --report /tmp/mingcute-static.json
python tool/verify_consumer.py --scenario mixed-contract --report /tmp/mingcute-mixed.json
```

| SDK 3.47.9 release consumer | Regular glyphs / bytes | Filled glyphs / bytes | Gate |
|---|---:|---:|---|
| Principal getters | 2,263 / 682,180 | 2,263 / 576,724 | Functional PASS; no subsetting |
| Public static-only library | 2 / 920 | 2 / 852 | Mandatory subsetting PASS |
| Both APIs used together | 2,263 / 682,180 | 2,263 / 576,724 | Functional PASS; no subsetting |

Original TTF sizes are 716,772 and 611,312 bytes. The public static library generates
all 4,526 fields, not just the four used by the app. Its consumer requires exactly
the selected cmap codepoints, nonempty outlines and smaller fonts. It also accepts
a constant Icon expression; the getter probe does not on this SDK. `@staticIconProvider` is only
applied to valid static-constant classes, never to instance getter classes in
violation of Flutter's annotation contract.

Historical R2.3 record/static experiments remain available with `--experiment`;
the record failed subsetting, while the isolated static prototype matched the
public static library's measured 920 / 852 bytes. Without `--scenario`, the
historical strict check still fails if the principal API retains full fonts.
CI explicitly selects functional contracts for principal/mixed and mandatory
subsetting for static: it does not reinterpret getter retention as optimization.
Missing glyphs, wrong families or failed builds remain failures in every mode.

## Naming

Names derive from the upstream SVG file names (`home-1.svg` becomes `home_1`).
Numeric suffixes are part of the upstream name and are preserved. Names that are
Dart reserved words or start with a digit receive an `icon_` prefix
(`icon_class`, `icon_1password`). Regular and Filled expose exactly the same set
of names; this parity is validated.

## Baseline

Last synchronised upstream revision: `9dc7d3a`
(`9dc7d3ad074fb16477096a6a8109a6467d0e2fe3`): **2,263 icons per style, 4,526
glyphs**. This is the verified baseline, not an upper limit; later
synchronisations may add icons. Removed upstream icons keep their codepoints in
the ledger and are never reassigned.

## Limitations

Monochrome font glyphs only: no gradients, multi-colour, per-shape opacity or
transforms. Gradient or partial-opacity sources are flattened and listed in
`tool/manifest.json` (`monochromeNotes`).

## Stability policy

Adding icons is a minor change; fixing glyph outlines is a patch; removing or
renaming a public icon getter, or changing a codepoint, is a major change (and the
ledger is designed to avoid it). See [RELEASE.md](RELEASE.md).
