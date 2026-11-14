import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mingcute_icons/mingcute_icons.dart';

void main() {
  test('Regular and Filled expose IconData from their own font families', () {
    expect(MingCute.regular.home_1, isA<IconData>());
    expect(MingCute.filled.home_1, isA<IconData>());
    expect(MingCute.regular.home_1.fontFamily, 'MingCuteRegular');
    expect(MingCute.filled.home_1.fontFamily, 'MingCuteFilled');
    expect(MingCute.regular.home_1.fontPackage, 'mingcute_icons');
    expect(MingCute.filled.home_1.fontPackage, 'mingcute_icons');
  });

  test('the same name shares one stable codepoint across both styles', () {
    expect(MingCute.regular.home_1.codePoint, MingCute.filled.home_1.codePoint);
    expect(MingCute.regular.search_2.codePoint,
        isNot(MingCute.regular.home_1.codePoint));
    // Private-use area only.
    expect(MingCute.regular.home_1.codePoint, inInclusiveRange(0xE000, 0xF8FF));
  });

  test('accessors reuse identical IconData objects', () {
    expect(identical(MingCute.regular.home_1, MingCute.regular.home_1), isTrue);
    expect(
        identical(MingCute.filled.search_2, MingCute.filled.search_2), isTrue);
  });

  testWidgets('both styles render as native themed icons', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: IconTheme(
          data: const IconThemeData(size: 40, color: Colors.teal),
          child: Row(
            children: [
              Icon(MingCute.regular.home_1),
              Icon(MingCute.filled.home_1),
            ],
          ),
        ),
      ),
    );
    expect(find.byType(Icon), findsNWidgets(2));
    final icon = tester.widget<Icon>(find.byType(Icon).first);
    expect(icon.icon, MingCute.regular.home_1);
    final texts = tester.widgetList<RichText>(find.byType(RichText)).toList();
    expect(
        texts.map((t) => t.text.style?.fontFamily),
        containsAll([
          'packages/mingcute_icons/MingCuteRegular',
          'packages/mingcute_icons/MingCuteFilled'
        ]));
    expect(texts.first.text.style?.fontSize, 40);
    expect(texts.first.text.style?.color, Colors.teal);
    expect(tester.takeException(), isNull);
  });
}
