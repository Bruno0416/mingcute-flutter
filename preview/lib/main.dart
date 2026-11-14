import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'capture.dart';
import 'generated_catalog.dart';

/// Normal launch opens the interactive gallery. `?capture=<scene>` selects the
/// static, deterministic capture mode used by tool/generate_screenshots.sh.
void main() {
  final params = Uri.base.queryParameters;
  if (params.containsKey('capture')) {
    try {
      final config = CaptureConfig.parse(params);
      config.select(); // fail before drawing if a name is missing
      config.sceneNames();
      runApp(CaptureApp(config: config));
    } on FormatException catch (error) {
      // ignore: avoid_print
      print('MINGCUTE_CAPTURE_ERROR ${error.message}');
      runApp(const Directionality(
          textDirection: TextDirection.ltr,
          child: Center(child: Text('capture error'))));
    }
    return;
  }
  runApp(const MingCutePreview());
}

enum PreviewVariant { both, regular, filled }

class MingCutePreview extends StatefulWidget {
  const MingCutePreview({super.key});

  @override
  State<MingCutePreview> createState() => _MingCutePreviewState();
}

class _MingCutePreviewState extends State<MingCutePreview> {
  ThemeMode mode = ThemeMode.system;
  PreviewVariant variant = PreviewVariant.both;
  double size = 30;
  String filter = '';
  bool grid = false;

  @override
  Widget build(BuildContext context) {
    final filtered = previewIcons
        .where((icon) =>
            icon.name.contains(filter) &&
            (variant == PreviewVariant.both ||
                (variant == PreviewVariant.regular
                    ? icon.regular != null
                    : icon.filled != null)))
        .toList();
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      themeMode: mode,
      theme: ThemeData(
          useMaterial3: true,
          colorScheme:
              ColorScheme.fromSeed(seedColor: const Color(0xFF5969DB))),
      darkTheme: ThemeData(
          useMaterial3: true,
          colorScheme: ColorScheme.fromSeed(
              seedColor: const Color(0xFF899AFF), brightness: Brightness.dark)),
      home: Builder(builder: (context) {
        final scheme = Theme.of(context).colorScheme;
        return Scaffold(
          appBar: AppBar(title: const Text('MingCute Icons'), actions: [
            IconButton(
                tooltip: 'Toggle theme',
                onPressed: () => setState(() => mode =
                    mode == ThemeMode.dark ? ThemeMode.light : ThemeMode.dark),
                icon: const Icon(Icons.brightness_6_rounded)),
          ]),
          body: Column(children: [
            Padding(
                padding: const EdgeInsets.all(16),
                child: Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      SizedBox(
                          width: 280,
                          child: TextField(
                              decoration: const InputDecoration(
                                  prefixIcon: Icon(Icons.search),
                                  labelText: 'Search icons',
                                  border: OutlineInputBorder()),
                              onChanged: (s) => setState(() => filter = s
                                  .trim()
                                  .toLowerCase()
                                  .replaceAll(' ', '_')))),
                      SegmentedButton<PreviewVariant>(
                          selected: {variant},
                          onSelectionChanged: (s) =>
                              setState(() => variant = s.first),
                          segments: const [
                            ButtonSegment(
                                value: PreviewVariant.both,
                                label: Text('Compare')),
                            ButtonSegment(
                                value: PreviewVariant.regular,
                                label: Text('Regular')),
                            ButtonSegment(
                                value: PreviewVariant.filled,
                                label: Text('Filled')),
                          ]),
                      Text('${size.round()} px'),
                      SizedBox(
                          width: 130,
                          child: Slider(
                              min: 16,
                              max: 64,
                              value: size,
                              onChanged: (x) => setState(() => size = x))),
                      FilterChip(
                          label: const Text('Alignment guides'),
                          selected: grid,
                          onSelected: (x) => setState(() => grid = x)),
                    ])),
            Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                        '${filtered.length} designs · ${previewIcons.length} total'))),
            const SizedBox(height: 8),
            Expanded(child: LayoutBuilder(builder: (context, constraints) {
              final cols = (constraints.maxWidth /
                      (variant == PreviewVariant.both ? 180 : 140))
                  .floor()
                  .clamp(2, 10)
                  .toInt();
              return GridView.builder(
                  padding: const EdgeInsets.all(16),
                  gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: cols,
                      mainAxisSpacing: 8,
                      crossAxisSpacing: 8,
                      mainAxisExtent:
                          variant == PreviewVariant.both ? 116 : 106),
                  itemCount: filtered.length,
                  itemBuilder: (context, index) {
                    final item = filtered[index];
                    Widget glyph(IconData? data) => data == null
                        ? const Text('—')
                        : DecoratedBox(
                            decoration: BoxDecoration(
                                border: grid
                                    ? Border.all(color: scheme.outlineVariant)
                                    : null),
                            child: SizedBox(
                                width: size + 8,
                                height: size + 8,
                                child: Center(child: Icon(data, size: size))));
                    return Card(
                        clipBehavior: Clip.antiAlias,
                        child: InkWell(
                          onTap: () async {
                            final code =
                                'Icon(MingCute.${variant == PreviewVariant.filled ? 'filled' : 'regular'}.${item.name})';
                            await Clipboard.setData(ClipboardData(text: code));
                            if (context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                  SnackBar(
                                      content: Text('Copied: $code'),
                                      duration: const Duration(seconds: 1)));
                            }
                          },
                          child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Row(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      if (variant != PreviewVariant.filled)
                                        glyph(item.regular),
                                      if (variant == PreviewVariant.both)
                                        const SizedBox(width: 10),
                                      if (variant != PreviewVariant.regular)
                                        glyph(item.filled),
                                    ]),
                                const SizedBox(height: 8),
                                Padding(
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 4),
                                    child: Text(item.name,
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        style: Theme.of(context)
                                            .textTheme
                                            .labelSmall)),
                              ]),
                        ));
                  });
            })),
          ]),
        );
      }),
    );
  }
}
