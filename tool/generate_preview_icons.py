#!/usr/bin/env python3
"""Original neutral gallery tiles, not MingCute Design's logo (MIT).

Generate pixel-deterministic PNGs using only the standard library; compressed
bytes may vary across zlib versions. The drawing is a
four-cell grid: two outlined tiles and two solid tiles on a dark background.
All foreground pixels remain within the maskable icon's central safe circle.
"""
from pathlib import Path
import argparse
import struct
import zlib
from ci.png_assets import assert_same_png

WEB = Path(__file__).resolve().parents[1] / 'preview/web'


def png(size: int) -> bytes:
    background, ink = bytes.fromhex('101820'), bytes.fromhex('7de2cd')
    rows = bytearray()
    for y in range(size):
        rows.append(0)  # PNG scanline filter: none
        for x in range(size):
            u, v = (x + .5) / size, (y + .5) / size
            left = .25 <= u < .46
            right = .54 <= u < .75
            top = .25 <= v < .46
            bottom = .54 <= v < .75
            outer = (left or right) and (top or bottom)
            inner = ((.29 <= u < .42) or (.58 <= u < .71)) and .29 <= v < .42
            rows.extend(ink if outer and not inner else background)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack('>I', len(data)) + kind + data +
                struct.pack('>I', zlib.crc32(kind + data)))

    return (b'\x89PNG\r\n\x1a\n' +
            chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(bytes(rows), 9)) + chunk(b'IEND', b''))


def targets() -> dict[str, int]:
    targets = {'favicon.png': 32}
    for size in (192, 512):
        targets[f'icons/Icon-{size}.png'] = size
        targets[f'icons/Icon-maskable-{size}.png'] = size
    return targets


def verify(web: Path = WEB) -> None:
    for name, size in targets().items():
        assert_same_png((web / name).read_bytes(), png(size))


def generate(web: Path = WEB) -> None:
    for name, size in targets().items():
        path = web / name
        data = png(size)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file():
            try:
                assert_same_png(path.read_bytes(), data)
                continue  # Preserve equivalent PNGs regardless of zlib version.
            except ValueError:
                pass
        path.write_bytes(data)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    verify() if args.check else generate()
