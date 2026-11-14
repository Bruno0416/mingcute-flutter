"""Gallery metadata and deterministic original raster assets."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import sys
import zlib

from _helpers import ROOT
sys.path.insert(0, str(ROOT / 'tool'))


def encoded(width, height, pixels, *, alpha=False, level=9):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    channels = 4 if alpha else 3
    rows = b''.join(b'\0' + pixels[y * width * channels:(y + 1) * width * channels] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' +
            chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6 if alpha else 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(rows, level)) + chunk(b'IEND', b''))


class PreviewWebTest(unittest.TestCase):
    def test_metadata_and_declared_icon_dimensions(self):
        web = ROOT / 'preview/web'
        manifest = json.loads((web / 'manifest.json').read_text())
        self.assertEqual('MingCute Icons Gallery', manifest['name'])
        self.assertNotIn('A new Flutter project', (web / 'index.html').read_text())
        for icon in manifest['icons']:
            data = (web / icon['src']).read_bytes()
            self.assertEqual(b'\x89PNG\r\n\x1a\n', data[:8])
            self.assertEqual(icon['sizes'], '%dx%d' % struct.unpack('>II', data[16:24]))

    def test_web_assets_are_reproducible(self):
        from png_assets import assert_same_png
        spec = importlib.util.spec_from_file_location('preview_icons', ROOT / 'tool/generate_preview_icons.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            module.generate(Path(temp))
            for path in Path(temp).rglob('*.png'):
                assert_same_png(path.read_bytes(), (ROOT / 'preview/web' / path.relative_to(temp)).read_bytes())

    def test_different_compression_with_identical_pixels_passes(self):
        from png_assets import assert_same_png
        pixels = b'\x10\x18\x20' * 256
        a, b = encoded(16, 16, pixels, level=0), encoded(16, 16, pixels, level=9)
        self.assertNotEqual(a, b)
        assert_same_png(a, b)

    def test_truncation_non_png_dimensions_pixels_and_alpha_fail(self):
        from png_assets import assert_same_png
        rgba = b'\x10\x18\x20\xff' * 4
        original = encoded(2, 2, rgba, alpha=True)
        changed_pixel = bytes([rgba[0] ^ 1]) + rgba[1:]
        changed_alpha = rgba[:3] + b'\xfe' + rgba[4:]
        for bad in (original[:-4], b'not a PNG', encoded(1, 4, rgba, alpha=True),
                    encoded(2, 2, changed_pixel, alpha=True), encoded(2, 2, changed_alpha, alpha=True)):
            with self.subTest(data=bad[:16]), self.assertRaises(ValueError):
                assert_same_png(bad, original)

    def test_crc_and_inflation_integrity_fail(self):
        from png_assets import assert_same_png
        original = encoded(2, 2, b'\x00\x10\x20' * 4)
        corrupt = bytearray(original)
        corrupt[45] ^= 1
        with self.assertRaises(ValueError):
            assert_same_png(bytes(corrupt), original)
        # Valid CRC and zlib stream, but not enough scanline data.
        with self.assertRaises(ValueError):
            assert_same_png(encoded(2, 2, b'\x00'), original)

    def test_missing_and_wrong_geometry_assets_fail(self):
        import generate_preview_icons as icons
        with tempfile.TemporaryDirectory() as temp:
            web = Path(temp)
            icons.generate(web)
            target = web / 'icons/Icon-192.png'
            target.write_bytes(encoded(192, 192, b'\0\0\0' * (192 * 192)))
            with self.assertRaises(ValueError):
                icons.verify(web)
            target.unlink()
            with self.assertRaises(FileNotFoundError):
                icons.verify(web)
