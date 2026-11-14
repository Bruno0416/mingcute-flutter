# Versioning, quality gates and release

## Versioning (SemVer)

- Glyph outline fixes, tooling, docs: **patch**.
- New icon constants (additive): **minor**.
- Removing or renaming a public constant, or changing a codepoint: **major**, or
  blocked: the append-only ledger exists to avoid this. Codepoints are never reused.
- A new upstream revision does not by itself mean a release or a version bump.

```bash
python tool/ci/version.py check                       # pubspec.yaml and CHANGELOG.md agree, descending, no duplicates
python tool/ci/version.py suggest --baseline OLD_manifest.json   # patch/minor/major from the API diff
python tool/ci/version.py bump --part minor            # preview only
python tool/ci/version.py bump --part minor --notes notes.md --write   # applies; real notes are mandatory
```

`pubspec.yaml`, the top `CHANGELOG.md` section and the GitHub Release text stay
in sync: release notes are the exact `## X.Y.Z` section of the changelog
(`release_guard.py notes`), never generated text, and must not be empty.
Only stable `x.y.z` versions are published (no provisional-release labels),
enforced by `tool/ci/check_final_release_language.py`.

## Local gates

```bash
bash tool/check.sh
bash tool/check_dependency_matrix.sh all
python tool/verify_consumer.py --scenario primary-contract --report /tmp/consumer-primary.json
python tool/verify_consumer.py --scenario static-subsetting --report /tmp/consumer-static.json
python tool/verify_consumer.py --scenario mixed-contract --report /tmp/consumer-mixed.json
python tool/ci/check_docs.py
python tool/ci/check_markdown_links.py
python tool/ci/release_guard.py metadata
python tool/ci/release_guard.py check-local-context   # needs a Git checkout
dart pub publish --dry-run
dart pub publish --to-archive=/tmp/mingcute-icons-package.tar.gz   # writes a file, uploads nothing
python tool/ci/release_guard.py archive-files --archive /tmp/mingcute-icons-package.tar.gz
bash tool/ci/check_pana_tools.sh
bash tool/ci/run_pana.sh /tmp/pana.json /tmp/mingcute-icons-package.tar.gz
```

The pana gate demands `grantedPoints == maxPoints == 160`: a missing, partial or
failed run blocks, and if pub.dev changes the maximum the gate stops for review
instead of lowering the bar.

The consumer checks compile real examples, verify their widgets and inspect
release font cmaps. **All three explicit scenarios above must pass:**
`primary-contract` verifies the getter API's functional behaviour and records
its full-font retention; `static-subsetting` **requires** actual unused-glyph
removal and exactly the selected codepoints; `mixed-contract` verifies mixed
usage and records its full-font retention. The getter and mixed cases are not
claimed to provide subsetting (see [Icons and API](ICONS.md)). The historical
invocation *without* `--scenario` still requires subsetting of the getter API
and intentionally fails; it is **not** the CI release gate. `tests.yml` invokes
all three explicit scenarios, with mandatory static-font subsetting. Successful
compilation or `tool/check.sh` alone is insufficient release approval.

The shared runner pins pana 0.23.19 and scores the actual pub archive in a
private temporary directory. Archive paths, regular-file types, required files
and publication exclusions are validated before extraction. The JSON output is
fresh on every run; a failed pana process cannot be overridden by a perfect
score in its output. Both the process and exact-score checks must succeed.

### SDK compatibility evidence

The consumer constraints remain Dart >=3.5.0 and Flutter >=3.24.0. Development
uses Flutter 3.47.9; `flutter_lints` 6 requires Dart >=3.8.0 and is a development
dependency, not a consumer dependency. The latest/lowest dependency matrix uses
the configured current Flutter SDK: it does **not** prove Flutter 3.24 support.
A consumer build on Flutter 3.24 is still required to verify the declared
minimum independently of that matrix. Earlier validation recorded a successful
Flutter 3.24.0 / Dart 3.5.0 consumer for the previous API; that is not evidence
for the new getter API. The current API's local runtime/build evidence uses
Flutter 3.47.9 / Dart 3.13.7. The declared minimum and other native platforms
have not been revalidated in this patch.

## GitHub Actions

`ci.yml` coordinates reusable modules from the same commit: `tests.yml`
(pipeline, unit tests, Flutter analyze/test, Web build, clean-room rebuild,
functional primary/mixed consumer contracts and mandatory static subsetting),
`compatibility.yml` (latest/lowest, Web build and a consumer app),
`documentation.yml` (docs, metadata, links, screenshots, local-context, pinned
`actionlint`) and `package.yml` (pub archive inspection and pana 160/160).
No publication workflow is included in the initial push. The final job **All required quality checks** fails when any stage
failed, was cancelled or was skipped. `upstream-sync.yml` (weekly) proposes a
review pull request when upstream changes; `screenshots.yml` is manual.

## Publication route

### Consumer contracts

CI runs three explicit release checks using `tool/verify_consumer.py`:

```bash
python tool/verify_consumer.py --scenario primary-contract --report /tmp/consumer-primary.json
python tool/verify_consumer.py --scenario static-subsetting --report /tmp/consumer-static.json
python tool/verify_consumer.py --scenario mixed-contract --report /tmp/consumer-mixed.json
```

The principal and mixed contracts require successful analyze/test/build, native
families and all four nonempty glyphs; their measured subsetting status is
reported independently, not claimed as passing. The static contract must accept
`const Icon`, reduce both fonts and retain **exactly** the selected codepoints;
missing, ambiguous, complete or extra-glyph fonts fail CI. No continue-on-error
is used. The historical default invocation without a scenario still requires
subsetting and fails for the getter API; its meaning was not silently changed.

On Flutter 3.47.9 the static-only consumer produces 2 glyphs per font (920 / 852
bytes). Principal and mixed usage retain 2,263 each (682,180 / 576,724 bytes).
Prefer exclusively the static library for optimized release size. These are
local measured results; remote Actions runtime remains a separate verification.

Automatic publication is **not installed for the initial push**:
`publish.yml` and the caller `release` job are absent. The unpublished workflow
is backed up locally in `.agents/INITIAL_PUSH_BACKUP/`, outside Git. Keep
`ENABLE_AUTOMATIC_PUBLISH` **unset**. Quality validation, archive inspection,
static subsetting and the strict Pana 160/160 gate remain mandatory.

After the first manual pub.dev release, restore the workflow and its caller,
reintroduce their release-policy tests, configure Google WIF/OIDC and require
explicit authorization before activating automatic publishing.

Chosen route: **`main` push + quality gate + Google Workload Identity Federation**
(pub.dev "Publish from anywhere using a service account / Workload Identity
Federation"), with short-lived OIDC tokens and no long-lived secrets. The
alternative, pub.dev's native GitHub OIDC on a `v{{version}}` tag push, is also
supported by pub.dev but is not mixed with this one. Reason: it keeps the
release gated on the same SHA as `main` and reuses the same release guard logic.

`release.py plan` decides one of `validate-only`, `stale`, `bootstrap-pending`,
`blocked`, `conflict`, `already-published`, `recover`, `publish`. Everything
uncertain (network, checksum, credentials, tag conflict, moved `main`) fails
closed. After a confirmed upload the flow verifies the published archive,
creates the immutable tag `vX.Y.Z` on the validated SHA and then the GitHub
Release with the changelog section. Tags are never moved.

## First publication (manual, owner-authorised)

pub.dev does not allow automation to publish the **first** version of a new
package. The pipeline reports `bootstrap-pending` and does nothing until then.

1. Create the **empty public GitHub repository**, confirm its real owner/name
   and intended `main` branch, but do **not push** yet.
2. Set the verified `homepage`, `repository` and `issue_tracker` in
   `pubspec.yaml`; update the README screenshot URLs to
   `raw.githubusercontent.com/<owner>/<repo>/main/...` using that *actual*
   repository. Keep the banner attribution and real upstream links. No fake URLs.
3. Leave the GitHub repository variable `ENABLE_AUTOMATIC_PUBLISH` **unset**.
   The first push excludes `publish.yml` and `ci.yml` has no `release` job.
   No publication workflow is included in the initial push; the original
   files are backed up under ignored `.agents/INITIAL_PUSH_BACKUP/`.
4. Run all local gates above, including the **three explicit consumer scenarios**,
   archive validation, `dart pub publish --dry-run` and **real pana 160/160**.
   Fix every actionable failure before pushing. If an empty GitHub repository
   makes a verified asset URL temporarily unavailable, record that *bootstrap*
   limitation; it does **not** waive the 160/160 release requirement.
5. Push to `main` only after reviewing the files and bootstrap limitations.
   Confirm **All required quality checks** succeeds for that SHA in GitHub
   Actions, rerunning the real pana gate once URLs are live. No manual pub.dev
   release while quality or pana is red. Publication remains disabled.
6. Only then, the package owner manually runs and authorises `dart pub publish`
   for the first `0.1.0` release. Do not enable automated publishing yet.
7. After pub.dev confirms the release, update any README text stating that the
   first publication is pending, rerun documentation/package checks, and push
   that documentation update. Then, in a separate, authorized patch,
   restore the publication workflow and caller, their tests, configure WIF/OIDC
   and opt in to automated releases for **future** versions.

## External configuration (pending until verified)

- GitHub: environment `pub.dev` with protection, rulesets for `main`/tags,
  variables `WIF_PROVIDER` and `PUBLISH_SERVICE_ACCOUNT`.
- Google Cloud: workload identity pool/provider bound to this repository and a
  service account; the same account authorised for the package on pub.dev.
- None of this is considered configured merely because the YAML exists.
