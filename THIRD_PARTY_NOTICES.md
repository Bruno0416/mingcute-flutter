# Third-party notices

## MingCute Icons (artwork)

- Original design: **MingCute Design** and its contributors.
- Upstream: <https://github.com/mingcute-design/mingcute-icons>
- Website: <https://www.mingcute.com>
- Original artwork licence: **Apache License, Version 2.0**, reproduced in
  [`UPSTREAM_APACHE_LICENSE.txt`](UPSTREAM_APACHE_LICENSE.txt).
- Included artwork: only the public **Core Regular** and **Core Filled** SVG
  files (`packages/svg/core-regular`, `packages/svg/core-filled`).
- Excluded: any premium style or asset distributed under other terms.
- Last synchronised upstream revision: `9dc7d3ad074fb16477096a6a8109a6467d0e2fe3`
  (recorded as `sourceRevision` in `tool/manifest.json`).

### Changes made to the original work

This community project is **unofficial**. To make the icons usable as Flutter
`IconData` it:

1. selects the public Core Regular and Core Filled SVG files;
2. converts their single-colour vector geometry into TrueType glyph outlines
   (SVG to font), normalising the coordinate system to a 1024 unit em;
3. flattens gradients and partial opacity into monochrome shapes and rejects
   SVG features a font cannot represent (masks, filters); affected icons are
   listed under `monochromeNotes` in `tool/manifest.json`;
4. maps file names to Dart identifiers and assigns stable private-use
   codepoints (`tool/codepoints.json`).

The converted font files remain under Apache-2.0. Generated Dart declarations,
accessors and catalogue entries incorporate upstream icon names and style
membership, plus this adapter's normalised identifiers, font-family references
and assigned codepoints. Generated files are distributed under Apache-2.0,
including their original template portions, to keep that scope unambiguous;
this does not claim that individual names or numbers are copyrightable.
The generator implementation itself is original MIT-licensed tooling.
The upstream licence text is included in this package. The artwork is not an
original creation of this project, and no upstream licence is replaced by MIT.

## Official MingCute banner

`doc/assets/branding/mingcute-banner.png` is an unchanged copy of upstream
`images/banner1.png` at commit `9dc7d3ad074fb16477096a6a8109a6467d0e2fe3`,
by MingCute Design and contributors. The repository-wide Apache-2.0 licence
applies; no additional banner-specific restriction was found in that revision.
The original URL, SHA-256 and licence source are recorded in
[`doc/assets/branding/ATTRIBUTION.json`](doc/assets/branding/ATTRIBUTION.json).
It identifies and credits the original project, not an official Flutter wrapper.
Apache-2.0 does not grant general trademark rights; no affiliation, endorsement
or rights to MingCute marks are claimed.

## Roboto (preview only, not published)

The development preview bundles Roboto Regular and Medium copied from the
Flutter SDK, under the Apache License 2.0 (see
`preview/assets/fonts/Roboto_LICENSE.txt`). These files are excluded from the
pub.dev package.

## This package's own code

Original, non-generated wrapper code, tooling and documentation are licensed under MIT, see
[`LICENSE`](LICENSE).
This scope excludes the artwork, derived fonts and generated Dart/catalogue
files described above, which are distributed under Apache-2.0.
