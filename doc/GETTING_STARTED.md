# Getting started

```bash
flutter pub add mingcute_icons
```

```dart
import 'package:flutter/material.dart';
import 'package:mingcute_icons/mingcute_icons.dart';

class Buttons extends StatelessWidget {
  const Buttons({super.key});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        IconButton(onPressed: () {}, icon: Icon(MingCute.regular.search_2)),
        IconButton(onPressed: () {}, icon: Icon(MingCute.filled.heart)),
        IconTheme(
          data: const IconThemeData(size: 28, color: Colors.teal),
          child: Icon(MingCute.regular.home_1),
        ),
      ],
    );
  }
}
```

## Tips

The principal API above is recommended for convenience. In the verified SDK,
its getters retain all font glyphs; they are not individually subsetted.

For optimized release size, use the independent static API instead:

```dart
import 'package:flutter/material.dart';
import 'package:mingcute_icons/mingcute_static.dart';

const home = Icon(MingCuteRegularConst.home_1);
const heart = Icon(MingCuteFilledConst.heart);
```

Both APIs expose the same names, codepoints, fonts and native Flutter widgets.
The static library needs no app-side generator. Do not mix it with getter usage
when prioritising size: the mixed consumer retains all glyphs on Flutter 3.47.9.

- Use `Icon(MingCute.regular.home_1)` without `const`: the accessor is a getter,
  not a constant expression, even though its result is a reused constant object.
  Keep unrelated widgets constant where possible. See [Icons and API](ICONS.md).
- Regular and Filled are two font families (`MingCuteRegular`, `MingCuteFilled`),
  both declared by the package; you do not declare any font in your app.
- Find names in the [preview gallery](PREVIEW.md) or in
  `lib/src/generated/regular_icons.g.dart`.
- Colour and size come from `Icon`, `IconTheme` or the widget's theme.
