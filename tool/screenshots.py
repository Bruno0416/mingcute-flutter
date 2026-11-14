#!/usr/bin/env python3
"""Manifest + structural validation for the generated preview screenshots.

  python tool/screenshots.py manifest --results FILE   # write doc/assets/screenshots/manifest.json
  python tool/screenshots.py check                     # validate images + manifest (no browser)

The check never needs Chromium. Pixel comparison against a fresh capture is
done separately by ``tool/generate_screenshots.sh --check --pixels``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENES = ROOT / 'tool/screenshot_capture/scenes.json'
OUT = ROOT / 'doc/assets/screenshots'
MANIFEST = OUT / 'manifest.json'
UPSTREAM_MANIFEST = ROOT / 'tool/manifest.json'
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
MAX_BYTES = 1_500_000  # keeps the published package small (pana limit is 4 MB)
MIN_NAMES_PER_STYLE = 2263  # upstream baseline 9dc7d3a; may grow, never shrink silently
# Inputs that influence pixels. A change here makes stored images obsolete.
INPUT_FILES = (
    'tool/screenshot_capture/scenes.json',
    'preview/lib/capture.dart',
    'preview/assets/fonts/Roboto-Regular.ttf',
    'preview/assets/fonts/Roboto-Medium.ttf',
)
LEGACY_BRANDING = ('morph', 'fluent', 'mingcute_icons_kit')


class ScreenshotError(Exception):
    pass


def fingerprint(root: Path = ROOT, names: list[str] | tuple[str, ...] = ()) -> str:
    """Hash of everything that influences pixels: the capture code, scene
    definitions, preview fonts and the upstream artwork hash of each displayed
    icon (so an unrelated upstream addition does not make images obsolete)."""
    digest = hashlib.sha256()
    icons = json.loads((root / 'tool/manifest.json').read_text('utf8'))['icons']
    for name in sorted(set(names)):
        for style in ('regular', 'filled'):
            record = icons[style].get(name)
            digest.update(f'{style}/{name}/{record["sha256"] if record else "missing"}\n'.encode())
    for rel in INPUT_FILES:
        path = root / rel
        if not path.is_file():
            raise ScreenshotError(f'capture input missing: {rel}')
        digest.update(rel.encode() + b'\0' + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def png_info(data: bytes, label: str) -> tuple[int, int]:
    """Validate signature, chunk CRCs and IDAT inflation; return (w, h)."""
    if not data.startswith(PNG_SIGNATURE):
        raise ScreenshotError(f'{label}: not a PNG')
    pos, width, height, idat, seen_iend = len(PNG_SIGNATURE), 0, 0, bytearray(), False
    while pos + 12 <= len(data):
        length, kind = struct.unpack('>I4s', data[pos:pos + 8])
        if pos + 12 + length > len(data):
            raise ScreenshotError(f'{label}: truncated PNG')
        body = data[pos + 8:pos + 8 + length]
        crc = struct.unpack('>I', data[pos + 8 + length:pos + 12 + length])[0]
        if zlib.crc32(kind + body) & 0xFFFFFFFF != crc:
            raise ScreenshotError(f'{label}: corrupt PNG chunk {kind!r}')
        if kind == b'IHDR':
            width, height = struct.unpack('>II', body[:8])
        elif kind == b'IDAT':
            idat += body
        elif kind == b'IEND':
            seen_iend = True
            break
        pos += 12 + length
    if not seen_iend or not width or not height:
        raise ScreenshotError(f'{label}: truncated PNG')
    try:
        zlib.decompress(bytes(idat))
    except zlib.error as exc:
        raise ScreenshotError(f'{label}: corrupt PNG data: {exc}') from exc
    return width, height


def load_scenes(root: Path = ROOT) -> dict:
    return json.loads((root / 'tool/screenshot_capture/scenes.json').read_text('utf8'))


def upstream_revision(root: Path = ROOT) -> str:
    return json.loads((root / 'tool/manifest.json').read_text('utf8'))['sourceRevision']


def write_manifest(results_file: Path, root: Path = ROOT) -> dict:
    scenes = load_scenes(root)
    results = {r['name']: r for r in json.loads(results_file.read_text('utf8'))['results']}
    out = root / 'doc/assets/screenshots'
    entries = []
    for scene in scenes['scenes']:
        name = scene['name']
        image = out / f'{name}.png'
        if not image.is_file():
            raise ScreenshotError(f'{name}.png was not generated')
        data = image.read_bytes()
        width, height = png_info(data, name)
        entry = {
            'name': name,
            'file': f'{name}.png',
            'title': scene['title'],
            'params': scene['params'],
            'width': width,
            'height': height,
            'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest(),
        }
        if name in results:
            entry['icons'] = results[name]['names']
        elif MANIFEST.is_file():  # partial --only run: keep previous icon list
            previous = {e['name']: e for e in json.loads(MANIFEST.read_text('utf8'))['screenshots']}
            entry['icons'] = previous.get(name, {}).get('icons', [])
        entries.append(entry)
    shown = sorted({i for e in entries for i in e.get('icons', [])})
    manifest = {
        'generator': 'tool/generate_screenshots.sh',
        'upstreamRevision': upstream_revision(root),
        'inputFingerprint': fingerprint(root, shown),
        'viewport': scenes['viewport'],
        'deviceScaleFactor': scenes['deviceScaleFactor'],
        'screenshots': entries,
    }
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', 'utf8')
    return manifest


def check(root: Path = ROOT) -> list[str]:
    """Return every problem found (empty list means the screenshots are valid)."""
    problems: list[str] = []
    out = root / 'doc/assets/screenshots'
    manifest_path = out / 'manifest.json'
    try:
        scenes = load_scenes(root)
    except (OSError, ValueError) as exc:
        return [f'scenes.json unreadable: {exc}']
    if not manifest_path.is_file():
        return ['doc/assets/screenshots/manifest.json is missing']
    manifest = json.loads(manifest_path.read_text('utf8'))
    entries = {e['name']: e for e in manifest.get('screenshots', [])}
    expected_names = [s['name'] for s in scenes['scenes']]
    if sorted(entries) != sorted(expected_names):
        problems.append(f'manifest scenes {sorted(entries)} differ from scenes.json {sorted(expected_names)}')
    want_w = scenes['viewport']['width'] * scenes['deviceScaleFactor']
    want_h = scenes['viewport']['height'] * scenes['deviceScaleFactor']
    try:
        shown = [i for e in manifest.get('screenshots', []) for i in e.get('icons', [])]
        if manifest.get('inputFingerprint') != fingerprint(root, shown):
            problems.append('capture inputs changed since screenshots were generated (obsolete); run tool/generate_screenshots.sh')
    except ScreenshotError as exc:
        problems.append(str(exc))
    catalog = json.loads((root / 'tool/manifest.json').read_text('utf8'))['icons']
    for scene in scenes['scenes']:
        name = scene['name']
        path = out / f'{name}.png'
        entry = entries.get(name)
        if not path.is_file():
            problems.append(f'{name}.png is missing')
            continue
        if path.name != path.name.lower():
            problems.append(f'{name}: file name must be lower-case')
        data = path.read_bytes()
        try:
            width, height = png_info(data, name)
        except ScreenshotError as exc:
            problems.append(str(exc))
            continue
        if (width, height) != (want_w, want_h):
            problems.append(f'{name}: {width}x{height}, expected {want_w}x{want_h}')
        if len(data) > MAX_BYTES:
            problems.append(f'{name}: {len(data)} bytes exceeds {MAX_BYTES}')
        if entry is None:
            continue
        if entry.get('sha256') != hashlib.sha256(data).hexdigest():
            problems.append(f'{name}: image differs from the manifest sha256')
        if entry.get('params') != scene['params']:
            problems.append(f'{name}: manifest params differ from scenes.json')
        style = scene['params'].get('style', 'both')
        icons = entry.get('icons') or []
        if not icons:
            problems.append(f'{name}: manifest lists no rendered icons')
        for icon in icons:
            styles = ('regular', 'filled') if style == 'both' else (style,)
            for s in styles:
                if icon not in catalog[s]:
                    problems.append(f'{name}: icon {icon!r} does not exist in style {s}')
        if scene['params']['theme'] not in ('dark', 'light'):
            problems.append(f'{name}: invalid theme')
        for legacy in LEGACY_BRANDING:
            if legacy in json.dumps(entry).lower():
                problems.append(f'{name}: manifest contains legacy branding {legacy!r}')
    for style in ('regular', 'filled'):
        if len(catalog[style]) < MIN_NAMES_PER_STYLE:
            problems.append(f'catalogue has only {len(catalog[style])} {style} names (< {MIN_NAMES_PER_STYLE})')
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    m = sub.add_parser('manifest')
    m.add_argument('--results', type=Path, required=True)
    sub.add_parser('check')
    args = parser.parse_args(argv)
    try:
        if args.command == 'manifest':
            manifest = write_manifest(args.results)
            print(f'Wrote {MANIFEST.relative_to(ROOT)} with {len(manifest["screenshots"])} screenshots.')
            return 0
        problems = check()
        if problems:
            for p in problems:
                print(f'SCREENSHOT CHECK FAILED: {p}', file=sys.stderr)
            return 1
        print(f'PASS: {len(load_scenes()["scenes"])} screenshots match scenes, manifest and catalogue.')
        return 0
    except (ScreenshotError, OSError, ValueError, KeyError) as exc:
        print(f'Screenshot tooling FAILED: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
