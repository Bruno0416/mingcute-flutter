import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/services.dart';
import 'package:mingcute_icons_preview/main.dart' as app;

void main() {
  testWidgets('renders searchable icon catalogue', (tester) async {
    await tester.pumpWidget(const app.MingCutePreview());
    expect(find.text('MingCute Icons'), findsOneWidget);
    expect(find.byType(GridView), findsOneWidget);
    await tester.enterText(find.byType(TextField), 'home');
    await tester.pump();
    expect(find.text('home_1'), findsWidgets);
  });

  testWidgets('copy uses the definitive API', (tester) async {
    final copied = <String>[];
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async {
        if (call.method == 'Clipboard.setData') {
          copied.add((call.arguments as Map)['text'] as String);
        }
        return null;
      },
    );
    addTearDown(() => tester.binding.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, null));
    await tester.pumpWidget(const app.MingCutePreview());
    await tester.enterText(find.byType(TextField), 'home_1');
    await tester.pumpAndSettle();
    final label = find.descendant(
        of: find.byType(GridView), matching: find.text('home_1'));
    final tile = find.ancestor(of: label, matching: find.byType(InkWell)).first;
    await tester.ensureVisible(tile);
    await tester.tap(tile);
    await tester.pumpAndSettle();
    expect(copied, ['Icon(MingCute.regular.home_1)']);
    await tester.tap(find.text('Filled'));
    await tester.pumpAndSettle();
    await tester.tap(tile);
    await tester.pumpAndSettle();
    expect(copied.last, 'Icon(MingCute.filled.home_1)');
  });
}
