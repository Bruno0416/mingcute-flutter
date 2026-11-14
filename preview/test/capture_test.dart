import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mingcute_flutter_preview/capture.dart';
import 'package:mingcute_flutter_preview/generated_catalog.dart';

void main() {
  group('CaptureConfig.parse', () {
    test('defaults and explicit parameters', () {
      final c = CaptureConfig.parse({'capture': 'hero'});
      expect(c.dark, isTrue);
      expect(c.variant, CaptureVariant.both);
      expect(c.columns, 6);
      final r = CaptureConfig.parse({
        'capture': 'regular',
        'theme': 'light',
        'size': '40',
        'cols': '4',
        'guides': '1',
      });
      expect(r.dark, isFalse);
      expect(r.variant, CaptureVariant.regular);
      expect(r.size, 40);
      expect(r.guides, isTrue);
    });

    test('rejects invalid scene, theme, style and ranges', () {
      for (final bad in [
        {'capture': 'nope'},
        {'capture': 'hero', 'theme': 'sepia'},
        {'capture': 'hero', 'style': 'duotone'},
        {'capture': 'hero', 'size': '2'},
        {'capture': 'hero', 'cols': 'x'},
        {'capture': 'hero', 'page': '0'},
      ]) {
        expect(() => CaptureConfig.parse(bad), throwsFormatException,
            reason: '$bad');
      }
    });
  });

  group('icon selection', () {
    test('every scene icon exists in both variants', () {
      final byName = {for (final i in previewIcons) i.name: i};
      final names = <String>{
        ...heroNames,
        ...detailNames,
        for (final g in comparisonGroups.values) ...g,
      };
      for (final n in names) {
        expect(byName[n], isNotNull, reason: n);
        expect(byName[n]!.regular, isNotNull, reason: n);
        expect(byName[n]!.filled, isNotNull, reason: n);
      }
    });

    test('unknown names and empty queries fail instead of drawing tofu', () {
      expect(
          () => CaptureConfig.parse(
              {'capture': 'hero', 'names': 'home_1,not_an_icon'}).select(),
          throwsFormatException);
      expect(
          () =>
              CaptureConfig.parse({'capture': 'hero', 'q': 'zzzzzz'}).select(),
          throwsFormatException);
    });

    test('query pages are stable', () {
      final first = CaptureConfig.parse(
          {'capture': 'regular', 'q': 'arrow', 'limit': '5'}).select();
      final second = CaptureConfig.parse(
              {'capture': 'regular', 'q': 'arrow', 'limit': '5', 'page': '2'})
          .select();
      expect(first.length, 5);
      expect(
          first
              .map((i) => i.name)
              .toSet()
              .intersection(second.map((i) => i.name).toSet()),
          isEmpty);
    });
  });

  testWidgets('every scene builds without exceptions', (tester) async {
    tester.view.physicalSize = const Size(1200, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    for (final scene in captureScenes) {
      await tester.pumpWidget(
          CaptureApp(config: CaptureConfig.parse({'capture': scene})));
      await tester.pump();
      expect(tester.takeException(), isNull, reason: scene);
      expect(find.byType(Icon), findsWidgets, reason: scene);
    }
  });
}
