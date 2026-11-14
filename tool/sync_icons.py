#!/usr/bin/env python3
"""Deterministic, incremental MingCute Core SVG -> Flutter TTF + IconData pipeline.

No HTML scraping: fetch a shallow Git checkout or read a preexisting local checkout.
No network calls when --source is supplied. No third-party runtime dependency in Flutter.

Requires Python 3.10+ and fonttools 4.58+ only.
"""
from __future__ import annotations

import argparse
from array import array
import copy
import hashlib
import math
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as ET
from fontTools.misc.transform import Transform
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.svgLib.path import parse_path
from fontTools.ttLib import TTFont

from upstream_metadata import provenance

ROOT = Path(__file__).resolve().parent.parent
REPO_URL = 'https://github.com/mingcute-design/mingcute-icons.git'
PACKAGE = 'mingcute_icons'
VERSION = 5
API_VERSION = 1  # Dart-only changes must not invalidate the font pipeline.
START = 0xE001
END = 0xF8FF
EM = 1024
ASCENT = 896
DESCENT = -128
STYLES = {'regular': ('core-regular', 'MingCuteRegular'),
          'filled': ('core-filled', 'MingCuteFilled')}
KEYWORDS = set(('abstract as assert async await base break case catch class const continue '
    'covariant default deferred do dynamic else enum export extends extension external factory '
    'false final finally for Function get hide if implements import in interface is late '
    'library mixin new null of on operator part required rethrow return sealed set show '
    'static super switch sync this throw true try typedef var void when while with yield '
    'augment macro type').split())
OBJECT_NAMES = {'hashCode', 'runtimeType', 'toString', 'noSuchMethod'}
SAFE_NAME = re.compile(r'^[a-z][a-z0-9_]*$')
SUPPORTED_TAGS = {'svg', 'g', 'path', 'title', 'desc', 'defs', 'linearGradient', 'stop', 'circle', 'ellipse', 'rect', 'polygon', 'polyline'}
# Raise if conversion could silently lose SVG geometry, color layers, effects or clipping.
FORBIDDEN = {'filter', 'mask', 'clip-path', 'style', 'vector-effect', 'mix-blend-mode'}


def dump_json(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + '\n'


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_if_changed(path: Path, data: str | bytes) -> bool:
    raw = data.encode('utf-8') if isinstance(data, str) else data
    if path.is_file() and path.read_bytes() == raw:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return True


def identifier(name: str, prefix: str = '') -> str:
    # Strip only the *explicitly configured* source prefix, not semantic names.
    if prefix and name.startswith(prefix):
        name = name[len(prefix):]
    name = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
    if not name:
        raise ValueError('Unidentifiable SVG file name')
    if name[0].isdigit() or name in KEYWORDS or name in OBJECT_NAMES:
        name = 'icon_' + name
    if not SAFE_NAME.fullmatch(name):
        raise ValueError(f'Invalid Dart identifier: {name}')
    return name


def git(*args: str) -> str:
    p = subprocess.run(['git', *args], capture_output=True, text=True, check=False)
    if p.returncode:
        raise RuntimeError(f'Git failed: {" ".join(args)}\n{p.stderr.strip()}')
    return p.stdout.strip()


def fetch_upstream(cache: Path, branch: str) -> Path:
    """Only operates on an isolated managed cache directory."""
    if not re.fullmatch(r'[A-Za-z0-9_.\-/]+', branch) or branch.startswith('-') or '..' in branch:
        raise ValueError('Invalid branch/ref')
    cache = cache.resolve()
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        git('clone', '--depth=1', '--single-branch', '--branch', branch, REPO_URL, str(cache))
    else:
        if not (cache / '.git').exists() or git('-C', str(cache), 'remote', 'get-url', 'origin') != REPO_URL:
            raise RuntimeError('Cache is not an isolated MingCute Git clone; refusing to change it')
        git('-C', str(cache), 'fetch', '--depth=1', 'origin', branch)
        git('-C', str(cache), 'checkout', '--detach', 'FETCH_HEAD')
    return cache


def collect(source: Path, strip_prefix: str = '') -> dict[str, dict[str, tuple[str, bytes]]]:
    data: dict[str, dict[str, tuple[str, bytes]]] = {style: {} for style in STYLES}
    for style, (folder, _) in STYLES.items():
        directory = source / 'packages' / 'svg' / folder
        if not directory.is_dir():
            raise FileNotFoundError(f'No public SVG style directory: {directory}')
        used: dict[str, str] = {}
        files = sorted(directory.glob('*.svg'))
        if not files:
            raise RuntimeError(f'No SVG files in {directory}')
        metadata = directory / 'metadata.json'
        if metadata.is_file():
            metadata_rows = json.loads(metadata.read_text('utf8'))
            expected_files = {item['file'] for item in metadata_rows}
            actual_files = {svg.name for svg in files}
            if expected_files != actual_files or len(metadata_rows) != len(expected_files):
                raise ValueError(f'{style}: SVG file list differs from upstream metadata.json')
        for svg in files:
            name = identifier(svg.stem, strip_prefix)
            if name in used:
                raise ValueError(f'Identifier collision ({style}): {used[name]} vs {svg.name} -> {name}')
            used[name] = svg.name
            data[style][name] = (svg.relative_to(source).as_posix(), svg.read_bytes())
    if set(data['regular']) != set(data['filled']):
        left = sorted(set(data['regular']) - set(data['filled']))[:10]
        right = sorted(set(data['filled']) - set(data['regular']))[:10]
        raise ValueError(f'MingCute variant parity mismatch: only regular={left}, only filled={right}')
    return data


def load_registry(out: Path, source: Path, names: set[str]) -> dict:
    registry_path = out / 'tool' / 'codepoints.json'
    if registry_path.is_file():
        registry = json.loads(registry_path.read_text('utf8'))
    else:
        registry = {'schemaVersion': 1, 'assignments': {}}
    if registry.get('schemaVersion') != 1 or not isinstance(registry.get('assignments'), dict):
        raise ValueError('Invalid persistent codepoint registry')
    assignments: dict[str, str] = registry['assignments']
    existing_cp: dict[int, str] = {}
    for key, value in assignments.items():
        cp = int(value, 16)
        if cp < START or cp > END or cp in existing_cp:
            raise ValueError(f'Invalid/duplicated persistent codepoint: {key} {value}')
        existing_cp[cp] = key
    # The upstream registry is authoritative only at initial assignment.
    # Local existing entries remain fixed even if upstream moves the codepoint.
    upstream_path = source / 'packages/font/metadata/codepoints.json'
    upstream = json.loads(upstream_path.read_text('utf8')).get('assignments', {}) if upstream_path.exists() else {}
    for name in sorted(names):
        if name in assignments:
            continue
        raw_name = name.replace('_', '-')
        suggested = upstream.get(raw_name)
        cp = int(suggested, 16) if isinstance(suggested, str) else None
        if cp is None or cp < START or cp > END or cp in existing_cp:
            cp = next((n for n in range(START, END + 1) if n not in existing_cp), None)
        if cp is None:
            raise RuntimeError('Private Use Area exhausted')
        assignments[name] = f'{cp:04X}'
        existing_cp[cp] = name
    return registry


def svg_transform(expr: str) -> Transform:
    """Parse SVG affine transformations, respecting SVG composition order."""
    if not expr.strip():
        return Transform()
    commands = list(re.finditer(r'([A-Za-z]+)\s*\(([^)]*)\)', expr))
    if not commands or re.sub(r'[\s,]+', '', re.sub(r'([A-Za-z]+)\s*\(([^)]*)\)', '', expr)):
        raise ValueError(f'Invalid SVG transform: {expr}')
    total = Transform()
    for match in commands:
        action, raw = match.groups()
        vals = [float(v) for v in re.split(r'[\s,]+', raw.strip()) if v]
        if not all(math.isfinite(v) for v in vals):
            raise ValueError('Non-finite SVG transform')
        if action == 'matrix' and len(vals) == 6:
            step = Transform(*vals)
        elif action == 'translate' and len(vals) in (1, 2):
            step = Transform().translate(vals[0], vals[1] if len(vals) == 2 else 0)
        elif action == 'scale' and len(vals) in (1, 2):
            step = Transform().scale(vals[0], vals[1] if len(vals) == 2 else vals[0])
        elif action == 'rotate' and len(vals) in (1, 3):
            angle = math.radians(vals[0])
            if len(vals) == 1:
                step = Transform().rotate(angle)
            else:
                cx, cy = vals[1:]
                step = Transform().translate(cx, cy).rotate(angle).translate(-cx, -cy)
        elif action == 'skewX' and len(vals) == 1:
            step = Transform(1, 0, math.tan(math.radians(vals[0])), 1, 0, 0)
        elif action == 'skewY' and len(vals) == 1:
            step = Transform(1, math.tan(math.radians(vals[0])), 0, 1, 0, 0)
        else:
            raise ValueError(f'Unsupported SVG transform: {action}{vals}')
        total = total.transform(step)
    return total


def shape_to_path(element, tag: str) -> str:
    def num(name: str, default: float = 0.0) -> float:
        return float(element.get(name, default))
    if tag == 'path':
        return element.get('d', '')
    if tag in ('circle', 'ellipse'):
        x, y = num('cx'), num('cy')
        rx = num('r') if tag == 'circle' else num('rx')
        ry = num('r') if tag == 'circle' else num('ry')
        if rx <= 0 or ry <= 0:
            raise ValueError(f'{tag} with invalid radius')
        return (f'M{x-rx} {y} a{rx} {ry} 0 1 0 {2*rx} 0 '
                f'a{rx} {ry} 0 1 0 {-2*rx} 0 Z')
    if tag == 'rect':
        x,y,w,h = num('x'),num('y'),num('width'),num('height')
        if w <= 0 or h <= 0:
            raise ValueError('Invalid rectangle dimensions')
        rx = min(max(num('rx', num('ry')),0),w/2)
        ry = min(max(num('ry',rx),0),h/2)
        if not rx and not ry:
            return f'M{x} {y} h{w} v{h} h{-w} Z'
        return (f'M{x+rx} {y} H{x+w-rx} A{rx} {ry} 0 0 1 {x+w} {y+ry} '
                f'V{y+h-ry} A{rx} {ry} 0 0 1 {x+w-rx} {y+h} '
                f'H{x+rx} A{rx} {ry} 0 0 1 {x} {y+h-ry} '
                f'V{y+ry} A{rx} {ry} 0 0 1 {x+rx} {y} Z')
    if tag in ('polygon','polyline'):
        pts = element.get('points','').strip()
        if not pts:
            raise ValueError('Missing points')
        return 'M' + pts + ('Z' if tag == 'polygon' else '')
    return ''


def monochrome_notes(raw: bytes) -> list[str]:
    """State explicitly when a monochrome font necessarily simplifies SVG paint."""
    root = ET.fromstring(raw)
    notes = set()
    for e in root.iter():
        tag = e.tag.rsplit('}',1)[-1]
        if tag in ('linearGradient','radialGradient') or e.get('fill','').startswith('url('):
            notes.add('gradient flattened to solid monochrome')
        if any(e.get(x) not in (None,'1','1.0') for x in ('opacity','fill-opacity')):
            notes.add('partial alpha flattened to solid monochrome')
        if e.get('fill-rule') == 'evenodd':
            notes.add('evenodd winding normalized; visual verification recommended')
    return sorted(notes)


def reorient_evenodd(glyph) -> None:
    """Make nested even-odd contours alternate winding for TrueType nonzero fill.

    Handles nested subpaths without altering their original quadratic curves.
    Intersecting non-nested even-odd contours still need a vector boolean backend.
    """
    ranges = []
    start = 0
    for end in glyph.endPtsOfContours:
        points = list(glyph.coordinates[start:end + 1])
        if not points:
            start = end + 1
            continue
        area = sum(points[i][0] * points[(i+1)%len(points)][1]
                   - points[(i+1)%len(points)][0] * points[i][1]
                   for i in range(len(points))) / 2
        bounds = (min(p[0] for p in points),min(p[1] for p in points),
                  max(p[0] for p in points),max(p[1] for p in points))
        ranges.append({'start':start,'end':end+1,'points':points,'area':area,'bounds':bounds})
        start = end + 1

    def inside(point, boundary):
        x,y=point
        crossing=False
        for index in range(len(boundary)):
            (x1,y1),(x2,y2)=boundary[index],boundary[(index+1)%len(boundary)]
            if (y1 > y) != (y2 > y) and x < (x2-x1)*(y-y1)/(y2-y1)+x1:
                crossing=not crossing
        return crossing

    # Work outside-in, so the chosen parent has already been oriented.
    for child in sorted(ranges,key=lambda item:-abs(item['area'])):
        rect=child['bounds']
        enclosing=[]
        for parent in ranges:
            if parent is child or abs(parent['area']) <= abs(child['area']):
                continue
            box=parent['bounds']
            if not (box[0]<rect[0] and box[1]<rect[1] and box[2]>rect[2] and box[3]>rect[3]):
                continue
            if inside(child['points'][0],parent['points']):
                enclosing.append(parent)
        if not enclosing:
            continue
        parent=min(enclosing,key=lambda item: abs(item['area']))
        parent_sign=1 if parent['area']>0 else -1
        current_sign=1 if child['area']>0 else -1
        if current_sign == parent_sign:
            begin,end=child['start'],child['end']
            glyph.coordinates[begin:end]=list(reversed(glyph.coordinates[begin:end]))
            glyph.flags[begin:end]=array('B',reversed(glyph.flags[begin:end]))
            child['area']=-child['area']
            child['points'].reverse()


def convert_svg(raw: bytes):
    """SVG to single-color glyph; no unacknowledged masks, filters or stroke loss."""
    root = ET.fromstring(raw)
    if root.tag.rsplit('}', 1)[-1] != 'svg':
        raise ValueError('Root element is not SVG')
    vb = root.get('viewBox')
    if not vb:
        raise ValueError('SVG missing viewBox')
    coords = [float(s) for s in re.split(r'[\s,]+', vb.strip())]
    if len(coords) != 4 or not all(math.isfinite(n) for n in coords) or coords[2] <= 0 or coords[3] <= 0:
        raise ValueError(f'Bad viewBox: {vb}')
    x, y, width, height = coords
    scale = EM / max(width, height)
    ox = (EM - width * scale) / 2 - x * scale
    oy = ASCENT + y * scale
    global_transform = Transform(scale, 0, 0, -scale, ox, oy)
    declared_gradients = {}
    for child in root.iter():
        tag = child.tag.rsplit('}',1)[-1]
        if tag == 'linearGradient':
            declared_gradients[child.get('id')] = child
    pen = TTGlyphPen(None)
    rendered = 0
    has_evenodd = False
    def walk(element, current_transform: Transform, inside_defs: bool = False):
        nonlocal rendered, has_evenodd
        tag = element.tag.rsplit('}', 1)[-1]
        if tag not in SUPPORTED_TAGS:
            raise ValueError(f'Unsupported SVG element <{tag}>')
        for attr, value in element.attrib.items():
            key = attr.rsplit('}',1)[-1]
            if key in FORBIDDEN and value not in ('none', '1'):
                raise ValueError(f'Unsupported SVG attribute {key}={value!r}')
            if key in ('stroke','stroke-width','stroke-linecap','stroke-linejoin') and key == 'stroke' and value not in ('none',):
                raise ValueError('Stroked SVG path needs explicit stroke-to-path conversion')
            if key == 'fill' and value.lower() not in ('currentcolor','black','#000','#000000','none'):
                if not re.fullmatch(r'url\(#[-\w]+\)',value) or value[5:-1] not in declared_gradients:
                    raise ValueError(f'Unsupported SVG fill={value!r}')
        if element.get('fill-rule') == 'evenodd':
            has_evenodd = True
        if element.get('fill-rule') not in (None,'nonzero','evenodd'):
            raise ValueError('Unsupported fill-rule')
        local = current_transform.transform(svg_transform(element.get('transform','')))
        if tag in ('svg','g','defs','linearGradient'):
            for child in element:
                walk(child, local, inside_defs or tag in ('defs','linearGradient'))
            return
        if tag in ('stop','title','desc'):
            return
        if inside_defs or element.get('fill') == 'none':
            return
        path = shape_to_path(element,tag)
        if path:
            path_pen = TransformPen(Cu2QuPen(pen, max_err=1.0, reverse_direction=False),
                                    global_transform.transform(local))
            parse_path(path,path_pen)
            rendered += 1
    walk(root,Transform())
    if not rendered:
        raise ValueError('No drawable SVG paths')
    glyph = pen.glyph()
    if has_evenodd:
        reorient_evenodd(glyph)
    if glyph.numberOfContours <= 0:
        raise ValueError('Empty icon outline')
    glyph.recalcBounds(None)
    if glyph.xMin < -EM // 2 or glyph.xMax > 3 * EM // 2 or glyph.yMin < -EM or glyph.yMax > 2 * EM:
        raise ValueError('SVG glyph outside expected em bounds')
    return glyph


def font_glyph_name(identifier_: str) -> str:
    return 'g_' + identifier_


def build_font(output: Path, style: str, registry: dict, records: dict, previous: dict, *, force: bool = False) -> tuple[int, int]:
    folder, family = STYLES[style]
    target = output / 'assets/fonts' / f'{family}.ttf'
    old = None
    old_style = previous.get('icons', {}).get(style, {})
    if target.exists() and previous.get('generatorVersion') == VERSION:
        try:
            old = TTFont(target, recalcTimestamp=False)
        except Exception:
            old = None
    old_cmap = old.getBestCmap() if old else {}
    glyphs = {'.notdef': TTGlyphPen(None).glyph()}
    widths = {'.notdef': (EM, 0)}
    cmap = {}
    reused = 0
    generated = 0
    for name in sorted(records):
        record = records[name]
        cp = int(registry['assignments'][name], 16)
        gname = font_glyph_name(name)
        old_record = old_style.get(name)
        if (not force and old is not None and old_record and old_record.get('sha256') == record['sha256']
                and old_cmap.get(cp) in old['glyf']):
            original = old_cmap[cp]
            glyphs[gname] = copy.deepcopy(old['glyf'][original])
            widths[gname] = old['hmtx'][original]
            reused += 1
        else:
            try:
                glyphs[gname] = convert_svg(record['content'])
            except Exception as exc:
                raise ValueError(f'{style}/{name}: {exc}') from exc
            widths[gname] = (EM, glyphs[gname].xMin)
            generated += 1
        cmap[cp] = gname
    if old is not None:
        old.close()
    fb = FontBuilder(EM, isTTF=True)
    fb.setupGlyphOrder(['.notdef', *[font_glyph_name(x) for x in sorted(records)]])
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(widths)
    fb.setupHorizontalHeader(ascent=ASCENT, descent=DESCENT)
    fb.setupNameTable({'familyName': family, 'styleName': 'Regular',
                       'fullName': family, 'psName': family, 'version': 'Version 1.000'})
    fb.setupOS2(sTypoAscender=ASCENT, sTypoDescender=DESCENT,
                usWinAscent=ASCENT, usWinDescent=abs(DESCENT))
    fb.setupPost(keepGlyphNames=True)
    fb.setupMaxp()
    fb.setupHead(unitsPerEm=EM, created=3406620150, modified=3406620150)
    fb.font.recalcTimestamp = False
    # Save in memory first, so a failed glyph doesn't corrupt an existing font.
    temp = target.with_suffix('.tmp.ttf')
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        fb.save(temp)
        TTFont(temp).close()  # verify font can be read
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    return generated, reused


def render_entry() -> str:
    return '''// GENERATED. Do not edit by hand.
// SPDX-License-Identifier: Apache-2.0
/// MingCute Core Regular and Core Filled as native Flutter IconData.
///
/// Unofficial community Flutter adapter; icon artwork by MingCute Design,
/// licensed under Apache-2.0. See THIRD_PARTY_NOTICES.md.
library;

import 'package:flutter/widgets.dart';

part 'src/generated/regular_icons.g.dart';
part 'src/generated/filled_icons.g.dart';

/// Native icons, for example `Icon(MingCute.regular.home_1)`.
///
/// Accessors reuse internal constant IconData objects. Getter expressions are
/// not compile-time constants: use Icon(...), not const Icon(...).
abstract final class MingCute {
  MingCute._();

  /// MingCute Core Regular icons.
  static const regular = _MingCuteRegularAccess();

  /// MingCute Core Filled icons.
  static const filled = _MingCuteFilledAccess();
}
'''


def render_dart(style: str, records: dict, registry: dict) -> str:
    """Emit Dart already formatted like ``dart format`` (short style, 80 columns)
    so the published files pass pana's formatting check byte for byte."""
    cls = '_MingCuteRegular' if style == 'regular' else '_MingCuteFilled'
    access = '_MingCuteRegularAccess' if style == 'regular' else '_MingCuteFilledAccess'
    fam = STYLES[style][1]
    out = ['// GENERATED. Do not edit by hand.',
           '// SPDX-License-Identifier: Apache-2.0',
           '// ignore_for_file: non_constant_identifier_names, constant_identifier_names',
           "part of '../../mingcute_icons.dart';", '',
           '/// Internal constants reused by the typed accessors.',
           '@staticIconProvider',
           f'abstract final class {cls} {{', f'  {cls}._();']
    for name in sorted(records):
        cp = int(registry['assignments'][name], 16)
        out.extend(['', f'  /// MingCute Core {style.capitalize()} `{name}` icon.',
                    f'  static const IconData {name} = IconData(',
                    f'    0x{cp:04x},',
                    f"    fontFamily: '{fam}',",
                    f"    fontPackage: '{PACKAGE}',",
                    '  );'])
    out.extend(['}', '', f'class {access} {{', f'  const {access}();'])
    for name in sorted(records):
        line = f'  IconData get {name} => {cls}.{name};'
        out.extend(['', f'  /// MingCute Core {style.capitalize()} `{name}` icon.'])
        out.extend([line] if len(line) <= 80 else [f'  IconData get {name} =>', f'      {cls}.{name};'])
    out.extend(['}', ''])
    return '\n'.join(out)


def render_static(records: dict[str, dict], registry: dict) -> str:
    """Independent public static providers, from the existing shared ledger."""
    out = ['// GENERATED. Do not edit by hand.',
           '// SPDX-License-Identifier: Apache-2.0',
           '// ignore_for_file: non_constant_identifier_names, constant_identifier_names',
           '/// Static MingCute providers for optimized release font subsetting.',
           '///',
           '/// Unofficial adapter; artwork by MingCute Design, Apache-2.0.',
           'library;', '', "import 'package:flutter/widgets.dart';"]
    for style, (_, family) in STYLES.items():
        cls = f'MingCute{style.capitalize()}Const'
        out.extend(['', f'/// MingCute Core {style.capitalize()} static icon constants.',
                    '@staticIconProvider', f'abstract final class {cls} {{', f'  {cls}._();'])
        for name in sorted(records[style]):
            cp = int(registry['assignments'][name], 16)
            out.extend(['', f'  /// MingCute Core {style.capitalize()} `{name}` icon.',
                        f'  static const IconData {name} = IconData(', f'    0x{cp:04x},',
                        f"    fontFamily: '{family}',", f"    fontPackage: '{PACKAGE}',", '  );'])
        out.append('}')
    return '\n'.join([*out, ''])


def render_preview(records: dict[str, dict]) -> str:
    names = sorted(set(records['regular']) | set(records['filled']))
    out = ['// GENERATED. Do not edit by hand.', '// SPDX-License-Identifier: Apache-2.0',
           "import 'package:flutter/widgets.dart';",
           f"import 'package:{PACKAGE}/mingcute_icons.dart';", '',
           'class PreviewIcon {',
           '  const PreviewIcon(this.name, {this.regular, this.filled});',
           '  final String name;', '  final IconData? regular;', '  final IconData? filled;',
           '}', '', 'final List<PreviewIcon> previewIcons = List.unmodifiable([']
    for name in names:
        v = [f'{style}: MingCute.{style}.{name}' for style in STYLES if name in records[style]]
        line = f"  PreviewIcon('{name}', {', '.join(v)}),"
        if len(line) <= 80:  # same wrapping as `dart format` (short style)
            out.append(line)
        else:
            out.extend(['  PreviewIcon(', f"    '{name}',", *[f'    {arg},' for arg in v], '  ),'])
    out.extend([']);', ''])
    return '\n'.join(out)


def run(source: Path, output: Path, *, strip_prefix: str = '', min_icons: int = 0,
        force: bool = False) -> dict:
    source, output = source.resolve(), output.resolve()
    raw = collect(source, strip_prefix)
    counts = {style: len(v) for style, v in raw.items()}
    if any(n < min_icons for n in counts.values()):
        raise RuntimeError(f'Upstream source incomplete: {counts}, required >= {min_icons} per style')
    found = set().union(*(set(x) for x in raw.values()))
    registry = load_registry(output, source, found)
    manifest_path = output / 'tool/manifest.json'
    previous = json.loads(manifest_path.read_text('utf8')) if manifest_path.exists() else {}
    records: dict[str, dict] = {}
    new_manifest: dict[str, dict] = {}
    for style, group in raw.items():
        records[style] = {}
        new_manifest[style] = {}
        for name, (path, content) in group.items():
            info = {'sha256': sha256(content), 'source': path, 'codepoint': registry['assignments'][name], 'monochromeNotes': monochrome_notes(content)}
            records[style][name] = {**info, 'content': content}
            new_manifest[style][name] = info
    source_info = provenance(source)
    rev = source_info['revision']
    upstream = {key: value for key, value in source_info.items() if key != 'revision'}
    provenance_changed = previous.get('sourceRevision') != rev or previous.get('upstream') != upstream
    artifacts = previous.get('artifactSha256', {})
    font_paths = {style: output / 'assets/fonts' / (family + '.ttf')
                  for style, (_, family) in STYLES.items()}
    same = (not force and previous.get('generatorVersion') == VERSION and
            previous.get('apiVersion') == API_VERSION and
            (output / 'lib/mingcute_icons.dart').is_file() and
             (output / 'lib/mingcute_icons.dart').read_text('utf8') == render_entry() and
             (output / 'lib/mingcute_static.dart').is_file() and
             (output / 'lib/mingcute_static.dart').read_text('utf8') == render_static(records, registry) and
            previous.get('icons') == new_manifest and
            all(path.is_file() and artifacts.get(style) == sha256(path.read_bytes())
                for style, path in font_paths.items()) and
            all((output / 'lib/src/generated' / f'{s}_icons.g.dart').is_file()
                and (output / 'lib/src/generated' / f'{s}_icons.g.dart').read_text('utf8') == render_dart(s, records[s], registry)
                for s in STYLES) and
            (output / 'preview/lib/generated_catalog.dart').is_file() and
            (output / 'preview/lib/generated_catalog.dart').read_text('utf8') == render_preview(records))
    report = {'sourceRevision': rev, 'counts': counts, 'generated': {}, 'reused': {},
              'provenanceChanged': provenance_changed,
              'skipped': same, 'added': {}, 'modified': {}, 'removed': {},
              'monochromeApproximations': {style: sum(bool(v['monochromeNotes']) for v in new_manifest[style].values()) for style in STYLES}}
    for style in STYLES:
        before, after = previous.get('icons', {}).get(style, {}), new_manifest[style]
        report['added'][style] = sorted(set(after) - set(before))
        report['removed'][style] = sorted(set(before) - set(after))
        report['modified'][style] = sorted(k for k in set(before) & set(after) if before[k]['sha256'] != after[k]['sha256'])
    if not same:
        # Preflight all new/modified paths before overwriting fonts (fail early).
        for style in STYLES:
            for name, item in records[style].items():
                prev = previous.get('icons', {}).get(style, {}).get(name)
                if force or not prev or prev.get('sha256') != item['sha256']:
                    try:
                        convert_svg(item['content'])
                    except Exception as exc:
                        raise ValueError(f'Unsupported source SVG: {style}/{name}: {exc}') from exc
        for style in STYLES:
            path = font_paths[style]
            font_unchanged = (not force and previous.get('generatorVersion') == VERSION
                              and previous.get('icons', {}).get(style) == new_manifest[style]
                              and path.is_file() and artifacts.get(style) == sha256(path.read_bytes()))
            if font_unchanged:
                made, reused = 0, len(records[style])
            else:
                made, reused = build_font(output, style, registry, records[style], previous, force=force)
            report['generated'][style] = made
            report['reused'][style] = reused
            write_if_changed(output / 'lib/src/generated' / f'{style}_icons.g.dart', render_dart(style, records[style], registry))
        write_if_changed(output / 'preview/lib/generated_catalog.dart', render_preview(records))
        write_if_changed(output / 'lib/mingcute_icons.dart', render_entry())
        write_if_changed(output / 'lib/mingcute_static.dart', render_static(records, registry))
        write_if_changed(output / 'tool/codepoints.json', dump_json(registry))
        write_if_changed(manifest_path, dump_json({'generatorVersion': VERSION, 'apiVersion': API_VERSION, 'sourceRevision': rev,
            'upstream': upstream,
            'artifactSha256': {style: sha256(path.read_bytes()) for style,path in font_paths.items()},
            'icons': new_manifest}))
    elif provenance_changed:
        previous['sourceRevision'] = rev
        previous['upstream'] = upstream
        write_if_changed(manifest_path, dump_json(previous))
    write_if_changed(output / 'tool/last_sync_report.json', dump_json(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('--source', type=Path, help='Local checkout of mingcute-icons, never modified')
    group.add_argument('--sync', action='store_true', help='Explicit alias for default automatic clone/fetch')
    parser.add_argument('--ref', default='main', help='Branch to fetch with --sync')
    parser.add_argument('--output', type=Path, default=ROOT)
    parser.add_argument('--strip-prefix', default='', help='Optional explicit filename prefix; normally empty')
    parser.add_argument('--min-icons', type=int, default=0, help='Guard against accidentally publishing partial corpus')
    parser.add_argument('--force', action='store_true', help='Rebuild all glyphs, even if source unchanged')
    args = parser.parse_args()
    source = args.source if args.source is not None else fetch_upstream(ROOT / 'tool/.cache/upstream', args.ref)
    report = run(source, args.output, strip_prefix=args.strip_prefix,
                  min_icons=args.min_icons, force=args.force)
    if (args.output / 'README.md').is_file():
        from readme_metadata import update
        update(args.output, write=True)
    print(f"Revision: {report['sourceRevision']} | SVG: {report['counts']} | skipped: {report['skipped']}")
    print(f"Converted: {report['generated']} | reused: {report['reused']}")
    print('Changes: ' + ', '.join(f'{key}={ {s:len(x) for s,x in by.items()} }' for key,by in report.items() if key in ('added','modified','removed')))


if __name__ == '__main__':
    main()
