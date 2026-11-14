"""Strict stdlib decoder for our non-interlaced, 8-bit RGB/RGBA Web PNGs.

Comparison is of decoded RGBA pixels, not compressor-specific IDAT bytes.
Unsupported encodings fail closed rather than pretending they were decoded.
"""
import hashlib
import struct
import zlib


def decode_png(data: bytes) -> tuple[int, int, str, bytes]:
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Not a PNG')
    pos, header, ended, idat_closed = 8, None, False, False
    idat = bytearray()
    while pos + 12 <= len(data):
        length, kind = struct.unpack('>I4s', data[pos:pos + 8])
        end = pos + 12 + length
        if end > len(data):
            raise ValueError('Truncated PNG chunk')
        body = data[pos + 8:end - 4]
        crc = struct.unpack('>I', data[end - 4:end])[0]
        if zlib.crc32(kind + body) != crc:
            raise ValueError(f'Corrupt PNG CRC: {kind!r}')
        if header is None and kind != b'IHDR':
            raise ValueError('IHDR must be first')
        if kind == b'IHDR':
            if header is not None or length != 13:
                raise ValueError('Invalid/duplicate IHDR')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', body)
            if not (0 < width <= 4096 and 0 < height <= 4096):
                raise ValueError('Invalid or excessive dimensions')
            if depth != 8 or color not in (2, 6) or (compression, filtering, interlace) != (0, 0, 0):
                raise ValueError('Expected non-interlaced 8-bit RGB/RGBA PNG')
            header = width, height, 3 if color == 2 else 4
        elif kind == b'IDAT':
            if idat_closed:
                raise ValueError('Non-contiguous IDAT')
            idat.extend(body)
        elif kind == b'IEND':
            if body or not idat or end != len(data):
                raise ValueError('Invalid IEND or trailing data')
            ended = True
            break
        else:
            if idat:
                idat_closed = True
            # These generated assets have no palette, colour transforms or APNG.
            if not kind[0] & 32 or kind in (b'tRNS', b'acTL', b'fcTL', b'fdAT'):
                raise ValueError(f'Unsupported PNG chunk: {kind!r}')
        pos = end
    if not ended or header is None:
        raise ValueError('Missing IEND / truncated PNG')
    width, height, channels = header
    stride = width * channels
    expected = (stride + 1) * height
    try:
        inflater = zlib.decompressobj()
        raw = inflater.decompress(bytes(idat), expected + 1)
    except zlib.error as exc:
        raise ValueError('Invalid PNG compression') from exc
    if len(raw) != expected or not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
        raise ValueError('Incomplete or oversized PNG pixel stream')
    pixels, previous = bytearray(), bytearray(stride)
    for y in range(height):
        offset = y * (stride + 1)
        filter_type = raw[offset]
        if filter_type > 4:
            raise ValueError('Invalid PNG filter')
        row = bytearray(raw[offset + 1:offset + 1 + stride])
        for x in range(stride):
            left = row[x - channels] if x >= channels else 0
            up, corner = previous[x], previous[x - channels] if x >= channels else 0
            if filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = up
            elif filter_type == 3:
                predictor = (left + up) // 2
            elif filter_type == 4:
                p = left + up - corner
                distances = (abs(p - left), abs(p - up), abs(p - corner))
                predictor = (left, up, corner)[distances.index(min(distances))]
            else:
                predictor = 0
            row[x] = (row[x] + predictor) & 255
        if channels == 4:
            pixels.extend(row)
        else:
            for x in range(0, stride, 3):
                pixels.extend(row[x:x + 3])
                pixels.append(255)
        previous = row
    return width, height, 'RGB' if channels == 3 else 'RGBA', bytes(pixels)


def assert_same_png(actual: bytes, expected: bytes) -> None:
    a, b = decode_png(actual), decode_png(expected)
    if a[:2] != b[:2] or a[3] != b[3]:
        raise ValueError('PNG dimensions or RGBA pixels differ; compressed SHA-256: '
                         f'{hashlib.sha256(actual).hexdigest()} != {hashlib.sha256(expected).hexdigest()}')
