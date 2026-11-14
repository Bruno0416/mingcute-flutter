# R1.2 — Clean rebuild verification (before enabling GitHub Actions)

Run this **from the `mingcute_icons` project**, after applying the overlay:

```bash
source .venv/bin/activate
python -m unittest discover -s tool/tests -v
python tool/verify_rebuild.py
```

The last command does **not** require a manual upstream `git clone` or a
`--source` argument. It clones `mingcute-design/mingcute-icons` into a fresh
temporary checkout and checks at least **2,200 icons in EACH style**.

It performs five stages:

1. Clone the official upstream into a temporary directory, no shared checkout.
2. Copy the current persistent codepoint ledger; generate all TTFs, Dart classes,
   preview catalogue and manifest **from scratch**; run parity validation.
3. Delete BOTH generated TTF fonts, BOTH generated Dart classes and the gallery
   catalogue **within that disposable directory only**.
4. Regenerate the missing files using the intact ledger and manifest; assert
   every glyph is reconverted and all produced files are **byte-identical** to
   the initial fresh build; run parity validation again.
5. Run the generator one final time, require `skipped: true`, and verify hashes
   did not change.

If all stages pass, output ends with `PASS:` and a report is written to
`tool/.cache/rebuild_report.json`. The test does **not** delete or modify your
working project's generated fonts or Dart classes. It writes only the ignored
report. When interrupted or failing, temporary files are cleaned up.

An optional *offline fixture* smoke check (4 icons per style) is:

```bash
python tool/verify_rebuild.py --source tool/tests/fixtures/upstream --min-icons 4
```

This fixture check is **not** a substitute for the automatic Git + full-catalogue
verification. Only proceed to publication/CI after a full-catalogue pass and
`flutter analyze` / `flutter test` in the package and preview.

Why not simply delete the real fonts? The temporary test exercises exactly the
same missing-artifact rebuild code path while preserving a working package in
case the new upstream commit contains an unsupported SVG.
