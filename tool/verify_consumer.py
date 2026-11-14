#!/usr/bin/env python3
"""Release-build the real four-icon example and inspect actual font subsetting.

Default: legacy strict subsetting check (unchanged). Explicit --scenario splits
primary-contract, static-subsetting and mixed-contract gates. Optional --experiment
builds generated candidate APIs ONLY in a disposable package copy. Experiments
do not add a secondary API to the published library or weaken the primary gate.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = {'regular': 'MingCuteRegular', 'filled': 'MingCuteFilled'}
SELECTION = {'regular': ('home_1', 'search_2'), 'filled': ('heart', 'star')}


def inspect_fonts(package: Path, web: Path, manifest: dict, selection: dict) -> tuple[dict, bool]:
    evidence, passed = {}, True
    for style, family in FAMILIES.items():
        candidates = list(web.rglob(f'{family}.ttf'))
        expected_path = web / f'assets/packages/mingcute_flutter/assets/fonts/{family}.ttf'
        if len(candidates) != 1 or candidates[0] != expected_path:
            raise ValueError(f'{family}: missing or ambiguous release font: {candidates}')
        original = package / f'assets/fonts/{family}.ttf'
        with TTFont(original) as font:
            original_count = len(font.getBestCmap())
        required = {int(manifest['icons'][style][name]['codepoint'], 16) for name in selection[style]}
        with TTFont(expected_path) as font:
            cmap = font.getBestCmap()
            actual = set(cmap)
            contours = all(cp in cmap and font['glyf'][cmap[cp]].numberOfContours > 0 for cp in required)
            family_valid = font['name'].getDebugName(1) == family
        missing = sorted(required - actual)
        subset = (not missing and contours and family_valid and
                  len(actual) < original_count and expected_path.stat().st_size < original.stat().st_size)
        passed = passed and subset
        evidence[style] = {'status': 'PASS' if subset else 'FAIL', 'glyphs': len(actual),
                           'originalGlyphs': original_count, 'codepoints': sorted(actual),
                           'requiredNames': list(selection[style]), 'requiredCodepoints': sorted(required),
                           'missingCodepoints': missing, 'requiredOutlinesNonempty': contours,
                           'familyValid': family_valid, 'asset': expected_path.relative_to(web).as_posix(),
                           'bytes': expected_path.stat().st_size, 'originalBytes': original.stat().st_size}
    return evidence, passed


def candidate_library(manifest: dict, kind: str) -> str:
    """All 4,526 declarations, not a hardcoded four-icon shortcut."""
    lines = ["import 'package:flutter/widgets.dart';"]
    if kind == 'record':
        lines.append('abstract final class MingCute {')
    for style, family in FAMILIES.items():
        if kind == 'static-const':
            lines.extend(['@staticIconProvider', f'abstract final class {family}Icons {{'])
        else:
            lines.append(f'  static const {style} = (')
        for name, record in sorted(manifest['icons'][style].items()):
            value = f"IconData(0x{int(record['codepoint'], 16):x}, fontFamily: '{family}', fontPackage: 'mingcute_flutter')"
            lines.append(f'  static const {name} = {value};' if kind == 'static-const' else f'    {name}: {value},')
        lines.append('}' if kind == 'static-const' else '  );')
    if kind == 'record':
        lines.append('}')
    return '\n'.join(lines) + '\n'


def contract_passed(evidence: dict, *, require_subset: bool) -> bool:
    """Functional validity is independent of the measured optimization result."""
    return all(not f['missingCodepoints'] and f['requiredOutlinesNonempty'] and f['familyValid']
               and (not require_subset or (f['status'] == 'PASS' and
                    set(f['codepoints']) == set(f['requiredCodepoints'])))
               for f in evidence.values())


def verify(report: Path, *, experiment: str = 'primary', scenario: str | None = None,
           artifacts: Path | None = None) -> None:
    if artifacts is not None and artifacts.resolve().is_relative_to(ROOT):
        raise ValueError('Consumer artifacts must stay outside the source checkout')
    report.parent.mkdir(parents=True, exist_ok=True)
    if scenario is not None and experiment != 'primary':
        raise ValueError('Public contracts cannot use experimental package copies')
    result = {'status': 'ERROR', 'experiment': experiment, 'scenario': scenario or 'legacy-strict-subsetting', 'commands': []}
    report.write_text(json.dumps(result) + '\n')  # Never leave stale success evidence.
    manifest = json.loads((ROOT / 'tool/manifest.json').read_text())
    with tempfile.TemporaryDirectory(prefix='mingcute-consumer-') as temp, report.with_suffix('.log').open('w') as log:
        sandbox, app = Path(temp), Path(temp) / 'consumer'

        def command(*args: str, allow_const_error: bool = False) -> subprocess.CompletedProcess:
            process = subprocess.run(args, cwd=app if app.exists() else sandbox, text=True,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            result['commands'].append({'command': list(args), 'exitCode': process.returncode})
            log.write(f'$ {" ".join(args)}\n{process.stdout}\nexit={process.returncode}\n')
            log.flush()
            report.write_text(json.dumps(result, indent=2) + '\n')
            if process.returncode and not allow_const_error:
                raise RuntimeError(f'{args[0]} failed with {process.returncode}; see {log.name}')
            return process

        command('flutter', '--version')
        command('flutter', 'create', '--platforms=web', '--no-pub', '--project-name=consumer', str(app))
        package = ROOT
        if experiment != 'primary':
            package = sandbox / 'candidate-package'
            (package / 'lib').mkdir(parents=True)
            shutil.copy2(ROOT / 'pubspec.yaml', package / 'pubspec.yaml')
            shutil.copytree(ROOT / 'assets/fonts', package / 'assets/fonts')
            (package / 'lib/mingcute_icons.dart').write_text(candidate_library(manifest, experiment))
        (app / 'pubspec.yaml').write_text(
            'name: consumer\npublish_to: none\nenvironment:\n  sdk: ">=3.5.0 <4.0.0"\n'
            'dependencies:\n  flutter:\n    sdk: flutter\n  mingcute_flutter:\n'
            f'    path: {json.dumps(str(package))}\n'
            'dev_dependencies:\n  flutter_test:\n    sdk: flutter\n  flutter_lints: ^6.0.0\n'
            'flutter:\n  uses-material-design: true\n')
        source = (ROOT / 'example/lib/main.dart').read_text()
        api_import = "import 'package:mingcute_flutter/mingcute_icons.dart';"
        static_import = "import 'package:mingcute_flutter/mingcute_static.dart';"
        imports = api_import
        references = [f'MingCute.{style}.{name}' for style, names in SELECTION.items() for name in names]
        if scenario in ('static-subsetting', 'mixed-contract'):
            imports = static_import if scenario == 'static-subsetting' else api_import + '\n' + static_import
            source = source.replace(api_import, imports)
            for index, ref in enumerate(references):
                if scenario == 'static-subsetting' or index in (1, 3):
                    static_ref = ref.replace('MingCute.regular.', 'MingCuteRegularConst.').replace('MingCute.filled.', 'MingCuteFilledConst.')
                    source = source.replace('Icon(' + ref, 'const Icon(' + static_ref)
                    references[index] = static_ref
        if experiment == 'static-const':
            source = source.replace('MingCute.regular.', 'MingCuteRegularIcons.').replace('MingCute.filled.', 'MingCuteFilledIcons.')
            references = [ref.replace('MingCute.regular.', 'MingCuteRegularIcons.').replace('MingCute.filled.', 'MingCuteFilledIcons.') for ref in references]
        (app / 'lib/main.dart').write_text(source)
        (app / 'test/widget_test.dart').write_text('''import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:consumer/main.dart';
''' + imports + '''
void main() {
  testWidgets('all four selected glyphs render with their native families', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: ExampleScreen()));
    final expected = <IconData>[''' + ', '.join(references) + '''];
    final icons = tester.widgetList<Icon>(find.byType(Icon)).toList();
    expect(icons.map((i) => i.icon).toList(), expected);
    final texts = tester.widgetList<RichText>(find.byType(RichText)).where(
      (t) => t.text.style?.fontFamily?.contains('MingCute') ?? false).toList();
    expect(texts.length, 4);
    for (var i = 0; i < 4; i++) {
      expect(texts[i].text.toPlainText(), String.fromCharCode(expected[i].codePoint));
      expect(texts[i].text.style?.fontFamily, 'packages/mingcute_flutter/${expected[i].fontFamily}');
    }
    expect(tester.takeException(), isNull);
  });
}
''')
        command('flutter', 'pub', 'get')
        command('flutter', 'analyze')
        command('flutter', 'test')
        result['exampleWidgetTests'] = 1
        negative = app / 'lib/const_probe.dart'
        negative.write_text("import 'package:flutter/widgets.dart';\n" +
                            imports + '\n' +
                            f'const probe = Icon({references[0]});\n')
        probe = command('dart', 'analyze', str(negative), allow_const_error=True)
        if probe.returncode and not any(code in probe.stdout for code in ('invalid_constant', 'const_eval_property_access')):
            raise AssertionError(f'Unexpected const-probe failure: {probe.stdout}')
        result['constExpressionAccepted'] = probe.returncode == 0
        if scenario == 'static-subsetting' and probe.returncode:
            raise AssertionError('Public static API must support const Icon expressions')
        negative.unlink()  # Only our own deliberate probe, in the sandbox.
        build = command('flutter', 'build', 'web', '--release', '--no-web-resources-cdn').stdout
        result['compilerWarnings'] = [line for line in build.splitlines() if 'warning' in line.lower() or 'Expected to find fonts' in line]
        if 'non-constant instances of IconData' in build or 'cannot tree shake' in build:
            raise AssertionError('Compiler cannot tree shake these icons')
        web = app / 'build/web'
        evidence, subset = inspect_fonts(ROOT, web, manifest, SELECTION)
        passed = subset if scenario is None else contract_passed(evidence, require_subset=scenario == 'static-subsetting')
        result.update(status='PASS' if passed else 'FAIL', fonts=evidence,
                      subsettingStatus='PASS' if subset else 'FAIL',
                      subsettingRequired=scenario not in ('primary-contract', 'mixed-contract'))
        if artifacts is not None:
            shutil.copytree(web, artifacts / 'web', dirs_exist_ok=True)
            shutil.copy2(app / 'lib/main.dart', artifacts / 'main.dart')
        report.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({**result, 'fonts': {s: {k: v for k, v in f.items() if k != 'codepoints'} for s, f in evidence.items()}}, indent=2))
        if not passed:
            raise AssertionError('Consumer contract FAILED; inspect functional and subsetting evidence')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--experiment', choices=('primary', 'record', 'static-const'), default='primary')
    mode.add_argument('--scenario', choices=('primary-contract', 'static-subsetting', 'mixed-contract'))
    parser.add_argument('--artifacts', type=Path, help='Optional retained Web build, outside the checkout')
    args = parser.parse_args()
    verify(args.report.resolve(), experiment=args.experiment, scenario=args.scenario, artifacts=args.artifacts)
