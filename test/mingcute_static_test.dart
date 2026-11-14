import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mingcute_flutter/mingcute_static.dart';

void main() {
  test('static providers preserve native families and registered codepoints',
      () {
    const icons = [
      MingCuteRegularConst.home_1,
      MingCuteRegularConst.search_2,
      MingCuteFilledConst.heart,
      MingCuteFilledConst.star,
    ];
    expect(icons.map((i) => i.codePoint), [0xe36c, 0xe58c, 0xe354, 0xe5fd]);
    expect(icons.map((i) => i.fontFamily), [
      'MingCuteRegular',
      'MingCuteRegular',
      'MingCuteFilled',
      'MingCuteFilled',
    ]);
    expect(icons.every((i) => i.fontPackage == 'mingcute_flutter'), isTrue);
  });

  testWidgets('static constants work with IconButton and IconTheme',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: IconTheme(
        data: const IconThemeData(size: 40, color: Colors.teal),
        child: Row(children: [
          const Icon(MingCuteRegularConst.home_1),
          IconButton(
              onPressed: () {}, icon: const Icon(MingCuteFilledConst.heart)),
        ]),
      ),
    ));
    expect(find.byType(Icon), findsNWidgets(2));
    expect(tester.takeException(), isNull);
  });
}
