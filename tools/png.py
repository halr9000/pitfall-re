#!/usr/bin/env python3
"""Minimal PNG writer (stdlib only) — avoids a pypng dependency.

write_rgb(path, width, height, rows)      rows = iterable of bytes, 3*w each
write_indexed(path, w, h, rows, palette)  rows = bytes of palette indices,
                                          palette = list of (r,g,b)
"""
import struct
import zlib


def _chunk(tag, data):
    c = struct.pack(">I", len(data)) + tag + data
    return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def _write(path, width, height, bitdepth, colortype, raw_rows, palette=None,
           trns=None):
    out = [b"\x89PNG\r\n\x1a\n"]
    out.append(_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, bitdepth,
                                           colortype, 0, 0, 0)))
    if palette is not None:
        pal = bytearray()
        for r, g, b in palette:
            pal += bytes((r & 255, g & 255, b & 255))
        pal += bytes(3 * (256 - len(palette)))
        out.append(_chunk(b"PLTE", bytes(pal)))
        if trns is not None:
            out.append(_chunk(b"tRNS", bytes(trns)))
    body = bytearray()
    for row in raw_rows:
        body.append(0)  # filter type 0
        body += row
    out.append(_chunk(b"IDAT", zlib.compress(bytes(body), 9)))
    out.append(_chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(b"".join(out))


def write_rgb(path, width, height, rows):
    _write(path, width, height, 8, 2, rows)


def write_indexed(path, width, height, rows, palette, transparent_index=None):
    trns = None
    if transparent_index is not None:
        trns = bytes([255] * transparent_index + [0])
    _write(path, width, height, 8, 3, rows, palette, trns)


def scale_rows(rows, width, factor):
    """Nearest-neighbour upscale of 8-bit-per-pixel rows."""
    for row in rows:
        wide = bytes(b for b in row for _ in range(factor))
        for _ in range(factor):
            yield wide


if __name__ == "__main__":
    pal = [(i, 255 - i, (i * 7) & 255) for i in range(64)]
    rows = [bytes((x + y) % 64 for x in range(64)) for y in range(64)]
    write_indexed("/tmp/png_selftest.png", 64, 64, rows, pal)
    print("wrote /tmp/png_selftest.png")
