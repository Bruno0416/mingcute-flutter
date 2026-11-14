import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

import 'generated_catalog.dart';

/// Stable, named scenes used for the reproducible README / pub.dev images.
///
/// Capture mode is enabled with `?capture=<scene>`; see doc/PREVIEW.md.
/// Everything that influences pixels comes from the URL, never from state.
const captureScenes = <String>[
  'hero',
  'regular',
  'filled',
  'comparison',
  'detail',
];

/// Names shown by the `hero`, `regular` and `filled` scenes (all real icons).
const heroNames = <String>[
  'home_1',
  'search_2',
  'user_1',
  'settings_1',
  'heart',
  'star',
  'notification',
  'camera',
  'music',
  'mail',
  'lock',
  'calendar_1',
  'folder',
  'document',
  'location',
  'chat_1',
  'cloud',
  'gift',
  'video',
  'phone',
  'bookmark',
  'trophy',
  'shield',
  'wifi',
];

/// Regular/Filled pairs grouped by use case for the `comparison` scene.
const comparisonGroups = <String, List<String>>{
  'Navigation': [
    'home_1',
    'compass',
    'location',
    'menu',
    'search_2',
    'arrow_right'
  ],
  'Media': [
    'play_circle',
    'pause_circle',
    'music',
    'video',
    'camera',
    'volume'
  ],
  'Users': ['user_1', 'user_add', 'group', 'user_3', 'chat_1', 'message_1'],
  'Files': ['folder', 'file', 'document', 'save', 'copy', 'download_2'],
  'Actions': [
    'edit_2',
    'delete_2',
    'share_2',
    'add_circle',
    'check_circle',
    'close_circle'
  ],
};

/// Icons shown at several sizes by the `detail` scene.
const detailNames = <String>['home_1', 'heart', 'star', 'notification'];
const detailSizes = <double>[16, 24, 32, 48, 64];

enum CaptureVariant { both, regular, filled }

class CaptureConfig {
  const CaptureConfig({
    required this.scene,
    this.dark = true,
    this.variant = CaptureVariant.both,
    this.size = 32,
    this.query = '',
    this.names = const [],
    this.columns = 6,
    this.page = 1,
    this.limit = 24,
    this.guides = false,
  });

  final String scene;
  final bool dark;
  final CaptureVariant variant;
  final double size;
  final String query;
  final List<String> names;
  final int columns;
  final int page;
  final int limit;
  final bool guides;

  /// Parses URL parameters; throws [FormatException] for anything invalid.
  factory CaptureConfig.parse(Map<String, String> p) {
    final scene = p['capture'] ?? '';
    if (!captureScenes.contains(scene)) {
      throw FormatException(
          'Unknown scene "$scene"; expected one of ${captureScenes.join(', ')}');
    }
    int integer(String key, int fallback, int min, int max) {
      final raw = p[key];
      if (raw == null) return fallback;
      final value = int.tryParse(raw);
      if (value == null || value < min || value > max) {
        throw FormatException(
            'Parameter "$key" must be $min..$max, got "$raw"');
      }
      return value;
    }

    final theme = p['theme'] ?? 'dark';
    if (theme != 'dark' && theme != 'light') {
      throw FormatException(
          'Parameter "theme" must be dark or light, got "$theme"');
    }
    final styleRaw = p['style'] ??
        (scene == 'regular'
            ? 'regular'
            : scene == 'filled'
                ? 'filled'
                : 'both');
    final variant = CaptureVariant.values.where((v) => v.name == styleRaw);
    if (variant.isEmpty) {
      throw FormatException(
          'Parameter "style" must be both, regular or filled, got "$styleRaw"');
    }
    final names = (p['names'] ?? '')
        .split(',')
        .map((s) => s.trim())
        .where((s) => s.isNotEmpty)
        .toList();
    return CaptureConfig(
      scene: scene,
      dark: theme == 'dark',
      variant: variant.first,
      size: integer('size', 32, 12, 96).toDouble(),
      query: (p['q'] ?? '').trim().toLowerCase().replaceAll(' ', '_'),
      names: names,
      columns: integer('cols', 6, 1, 12),
      page: integer('page', 1, 1, 1000),
      limit: integer('limit', 24, 1, 200),
      guides: p['guides'] == '1' || p['guides'] == 'true',
    );
  }

  /// Icons selected for a scene, in a stable order. Throws if a requested
  /// name does not exist in the generated catalogue (never renders tofu).
  List<PreviewIcon> select() {
    final byName = {for (final i in previewIcons) i.name: i};
    List<String> wanted;
    if (names.isNotEmpty) {
      wanted = names;
    } else if (query.isNotEmpty) {
      final matches = previewIcons
          .where((i) => i.name.contains(query))
          .map((i) => i.name)
          .toList();
      final start = (page - 1) * limit;
      wanted = start >= matches.length
          ? const []
          : matches.sublist(start, (start + limit).clamp(0, matches.length));
      if (wanted.isEmpty) {
        throw FormatException('No icons for q="$query" page=$page');
      }
    } else {
      wanted = heroNames.sublist(
          0, limit < heroNames.length ? limit : heroNames.length);
    }
    final missing = wanted.where((n) => !byName.containsKey(n)).toList();
    if (missing.isNotEmpty) {
      throw FormatException('Unknown icon name(s): ${missing.join(', ')}');
    }
    return [for (final n in wanted) byName[n]!];
  }

  /// Every icon the scene will draw (used for the READY handshake).
  List<String> sceneNames() {
    switch (scene) {
      case 'comparison':
        return [for (final g in comparisonGroups.values) ...g];
      case 'detail':
        return detailNames;
      default:
        return [for (final i in select()) i.name];
    }
  }
}

class _Palette {
  const _Palette(
      this.background, this.surface, this.foreground, this.muted, this.line);
  final Color background;
  final Color surface;
  final Color foreground;
  final Color muted;
  final Color line;

  static const dark = _Palette(Color(0xFF14141C), Color(0xFF1F1F2B),
      Color(0xFFEDEDF7), Color(0xFF9A9AB0), Color(0xFF34344A));
  static const light = _Palette(Color(0xFFF6F6FB), Color(0xFFFFFFFF),
      Color(0xFF1B1B25), Color(0xFF6B6B80), Color(0xFFD8D8E6));
}

/// Static, animation-free app used only for deterministic screenshots.
class CaptureApp extends StatefulWidget {
  const CaptureApp({super.key, required this.config});
  final CaptureConfig config;

  @override
  State<CaptureApp> createState() => _CaptureAppState();
}

class _CaptureAppState extends State<CaptureApp> {
  @override
  void initState() {
    super.initState();
    // Two frames guarantee layout + paint of every glyph before the signal.
    SchedulerBinding.instance.addPostFrameCallback((_) {
      SchedulerBinding.instance.addPostFrameCallback((_) {
        final c = widget.config;
        final names = c.sceneNames();
        // ignore: avoid_print
        print('MINGCUTE_CAPTURE_READY ${jsonEncode({
              'scene': c.scene,
              'theme': c.dark ? 'dark' : 'light',
              'style': c.variant.name,
              'size': c.size,
              'count': names.length,
              'names': names,
            })}');
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.config;
    final pal = c.dark ? _Palette.dark : _Palette.light;
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        fontFamily: 'Roboto',
        brightness: c.dark ? Brightness.dark : Brightness.light,
        scaffoldBackgroundColor: pal.background,
        splashFactory: NoSplash.splashFactory,
      ),
      home: Scaffold(
        backgroundColor: pal.background,
        body: DefaultTextStyle(
          style: TextStyle(
              fontFamily: 'Roboto', color: pal.foreground, fontSize: 14),
          child: _scene(c, pal),
        ),
      ),
    );
  }

  Widget _scene(CaptureConfig c, _Palette pal) {
    switch (c.scene) {
      case 'comparison':
        return _Comparison(c, pal);
      case 'detail':
        return _Detail(c, pal);
      default:
        return _Grid(c, pal);
    }
  }
}

PreviewIcon _byName(String name) =>
    previewIcons.firstWhere((i) => i.name == name,
        orElse: () => throw FormatException('Unknown icon name: $name'));

Widget _glyph(IconData? data, double size, _Palette pal, bool guides) {
  if (data == null) {
    throw const FormatException('Icon variant missing in catalogue');
  }
  final box = SizedBox(
      width: size + 8,
      height: size + 8,
      child: Center(child: Icon(data, size: size, color: pal.foreground)));
  return guides
      ? DecoratedBox(
          decoration: BoxDecoration(border: Border.all(color: pal.line)),
          child: box)
      : box;
}

Widget _header(String title, String subtitle, _Palette pal) => Padding(
      padding: const EdgeInsets.fromLTRB(40, 32, 40, 8),
      child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
        Text(title,
            style: TextStyle(
                fontSize: 26,
                fontWeight: FontWeight.w500,
                color: pal.foreground)),
        const SizedBox(width: 16),
        Text(subtitle, style: TextStyle(fontSize: 14, color: pal.muted)),
      ]),
    );

class _Grid extends StatelessWidget {
  const _Grid(this.config, this.pal);
  final CaptureConfig config;
  final _Palette pal;

  @override
  Widget build(BuildContext context) {
    final icons = config.select();
    final both = config.variant == CaptureVariant.both;
    final label = switch (config.variant) {
      CaptureVariant.both => 'Regular + Filled',
      CaptureVariant.regular => 'Regular',
      CaptureVariant.filled => 'Filled',
    };
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _header(
          'MingCute Icons', 'Core $label · unofficial Flutter adapter', pal),
      Expanded(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(40, 16, 40, 32),
          child: GridView.count(
            physics: const NeverScrollableScrollPhysics(),
            crossAxisCount: config.columns,
            mainAxisSpacing: 14,
            crossAxisSpacing: 14,
            childAspectRatio: both ? 1.55 : 1.35,
            children: [
              for (final icon in icons)
                DecoratedBox(
                  decoration: BoxDecoration(
                      color: pal.surface,
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: pal.line)),
                  child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              if (config.variant != CaptureVariant.filled)
                                _glyph(icon.regular, config.size, pal,
                                    config.guides),
                              if (both) const SizedBox(width: 14),
                              if (config.variant != CaptureVariant.regular)
                                _glyph(icon.filled, config.size, pal,
                                    config.guides),
                            ]),
                        const SizedBox(height: 10),
                        Text(icon.name,
                            style: TextStyle(fontSize: 12, color: pal.muted)),
                      ]),
                ),
            ],
          ),
        ),
      ),
    ]);
  }
}

class _Comparison extends StatelessWidget {
  const _Comparison(this.config, this.pal);
  final CaptureConfig config;
  final _Palette pal;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _header(
          'Regular vs Filled', 'same names, two native IconData families', pal),
      Expanded(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(40, 8, 40, 24),
          child: Column(children: [
            for (final entry in comparisonGroups.entries)
              Expanded(
                child: Row(children: [
                  SizedBox(
                      width: 120,
                      child: Text(entry.key,
                          style: TextStyle(fontSize: 15, color: pal.muted))),
                  for (final name in entry.value)
                    Expanded(
                      child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Row(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  _glyph(_byName(name).regular, config.size,
                                      pal, config.guides),
                                  _glyph(_byName(name).filled, config.size, pal,
                                      config.guides),
                                ]),
                            const SizedBox(height: 4),
                            Text(name,
                                style:
                                    TextStyle(fontSize: 11, color: pal.muted)),
                          ]),
                    ),
                ]),
              ),
          ]),
        ),
      ),
    ]);
  }
}

class _Detail extends StatelessWidget {
  const _Detail(this.config, this.pal);
  final CaptureConfig config;
  final _Palette pal;

  @override
  Widget build(BuildContext context) {
    Widget panel(String title, bool dark, bool filled) {
      final p = dark ? _Palette.dark : _Palette.light;
      return Expanded(
        child: Container(
          margin: const EdgeInsets.all(8),
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
              color: p.background,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: pal.line)),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: TextStyle(fontSize: 14, color: p.muted)),
            Expanded(
              child: Column(children: [
                for (final name in detailNames)
                  Expanded(
                    child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                        children: [
                          for (final s in detailSizes)
                            Icon(
                                filled
                                    ? _byName(name).filled
                                    : _byName(name).regular,
                                size: s,
                                color: p.foreground),
                        ]),
                  ),
              ]),
            ),
            Row(mainAxisAlignment: MainAxisAlignment.spaceEvenly, children: [
              for (final s in detailSizes)
                Text('${s.round()} px',
                    style: TextStyle(fontSize: 11, color: p.muted)),
            ]),
          ]),
        ),
      );
    }

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _header('Sizes and surfaces',
          '16 – 64 px, tinted by IconTheme / Icon.color', pal),
      Expanded(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(32, 8, 32, 24),
          child: Column(children: [
            Expanded(
              child: Row(children: [
                panel('Regular · dark surface', true, false),
                panel('Filled · dark surface', true, true),
              ]),
            ),
            Expanded(
              child: Row(children: [
                panel('Regular · light surface', false, false),
                panel('Filled · light surface', false, true),
              ]),
            ),
          ]),
        ),
      ),
    ]);
  }
}
