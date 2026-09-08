"""CrossInk PXC2 transport and COIX index (little endian, ZIP_STORED)."""
import struct
import zlib


def encode_pxc2(raw_pxc: bytes) -> bytes:
    width, height = struct.unpack_from('<HH', raw_pxc)
    raw = raw_pxc[4:]
    row_bytes = (width + 3) // 4
    if not (0 < width <= 1024 and 0 < height <= 1024 and
            len(raw) == row_bytes * height and len(raw) <= 128 * 1024):
        raise ValueError('Unsupported PXC dimensions')
    blocks = []
    for sequence, offset in enumerate(range(0, len(raw), 2048)):
        block = raw[offset:offset + 2048]
        compressor = zlib.compressobj(level=8, wbits=-15)
        encoded = compressor.compress(block) + compressor.flush()
        codec = 1
        if len(encoded) >= len(block):
            codec, encoded = 0, block
        blocks.append(struct.pack('<BBHHHI', codec, 0, len(block), len(encoded), sequence,
                                  zlib.crc32(block)) + encoded)
    body = b''.join(blocks)
    return struct.pack('<4sBB7H3I', b'PXC2', 2, 1, 32, width, height, row_bytes, 2048,
                       len(blocks), 0, len(raw), zlib.crc32(raw), 32 + len(body)) + body


def safe_path(value: str, limit: int) -> bool:
    return (isinstance(value, str) and bool(value) and len(value.encode('utf-8')) <= limit and
            not value.startswith('/') and '..' not in value and
            not any(ord(c) < 32 or c in '\\:%' for c in value))


def index_entries(entries: list[dict]) -> list[dict]:
    """Unsupported optional entries are omitted; original images stay readable."""
    result, seen = [], set()
    for entry in entries:
        href, pxc = entry.get('href', ''), entry.get('pxc', '')
        if (len(result) == 256 or href in seen or not safe_path(href, 128) or
                not safe_path(pxc, 64) or not pxc.startswith('META-INF/crossink/pxc/')):
            continue
        width, height = entry['width'], entry['height']
        if not (0 < width <= 1024 and 0 < height <= 1024 and (width + 3) // 4 * height <= 131072):
            continue
        seen.add(href)
        result.append(entry)
    return result


def encode_index(manifest: bytes, entries: list[dict]) -> bytes:
    if index_entries(entries) != entries:
        raise ValueError('Invalid optimizer index records')
    records = b''.join(struct.pack('<129s65sHHBBII', e['href'].encode(), e['pxc'].encode(),
                                  e['width'], e['height'], 2, 0, e['pxcBytes'], e['pixelCrc32'])
                       for e in entries)
    header = struct.pack('<4sHHHHIIII', b'COIX', 1, 32, 208, len(entries), 0,
                         zlib.crc32(manifest), len(manifest), zlib.crc32(records))
    return header + struct.pack('<I', zlib.crc32(header)) + records
