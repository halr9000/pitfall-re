#!/usr/bin/env python3
"""Split a .PH container into its length-prefixed blocks and decode block 0.

Container format (confirmed from the loader at 0x00446295):
    repeat { uint32 size ; uint8 payload[size] }   until EOF
Block 0 layout (level files):
    +0x00 u32 cell_w      map width  in 8x8 cells   (tiles across = /2)
    +0x04 u32 cell_h      map height in 8x8 cells   (tiles down   = /2)
    +0x08 u32 pix_off     block-relative end of map / start of pixel data
    +0x0C u32 pal_off     block-relative start of the RGB palette
    +0x10 u32 pal_count   number of 3-byte palette entries
    +0x14      uint16 cellmap[cell_w * cell_h]      (low 12 bits index, high 4 flags)
    pix_off .. pal_off    8bpp pixel data (palette indices)
    pal_off .. size       palette, 3 bytes per entry

Usage:
    python3 tools/ph_dump.py LEVEL00.PH                # block table
    python3 tools/ph_dump.py LEVEL00.PH --block0       # decoded block-0 header
    python3 tools/ph_dump.py LEVEL00.PH --palette      # palette listing
    python3 tools/ph_dump.py LEVEL00.PH --png          # gfx/ PNG exports
    python3 tools/ph_dump.py --all                     # block table for every file
"""
import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import png  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GAME = ROOT / "game"
GFX = ROOT / "gfx"


def blocks(data):
    """Yield (index, header_off, payload_off, size)."""
    p, i = 0, 0
    while p + 4 <= len(data):
        size, = struct.unpack_from("<I", data, p)
        if size == 0 or p + 4 + size > len(data):
            yield i, p, p + 4, len(data) - p - 4
            return
        yield i, p, p + 4, size
        p += 4 + size
        i += 1


def block0(data):
    _, _, off, size = next(iter(blocks(data)))
    cw, ch, pix, pal, ncol = struct.unpack_from("<5I", data, off)
    return dict(off=off, size=size, cell_w=cw, cell_h=ch,
                map_off=off + 0x14, map_bytes=cw * ch * 2,
                pix_off=off + pix, pal_off=off + pal, pal_count=ncol,
                pix_bytes=pal - pix, raw=(cw, ch, pix, pal, ncol))


def palette(data, b0):
    p = b0["pal_off"]
    return [tuple(data[p + i * 3: p + i * 3 + 3]) for i in range(b0["pal_count"])]


def show_blocks(path):
    data = path.read_bytes()
    print(f"== {path.name}  {len(data)} bytes ==")
    total = 0
    for i, hoff, poff, size in blocks(data):
        print(f"  block {i}: header @0x{hoff:06X}  payload @0x{poff:06X}  size 0x{size:06X} ({size})")
        total += 4 + size
    print(f"  {total} of {len(data)} bytes accounted for"
          + ("" if total == len(data) else f"  ({len(data) - total} trailing)"))


def show_block0(path):
    data = path.read_bytes()
    b = block0(data)
    cw, ch = b["cell_w"], b["cell_h"]
    print(f"== {path.name} block 0 ==")
    print(f"  cell grid      {cw} x {ch}   (8x8 cells)")
    print(f"  tile grid      {cw // 2} x {ch // 2}   (16x16 tiles)")
    print(f"  pixel size     {cw * 8} x {ch * 8}")
    print(f"  scroll limit   x {(cw // 2 - 20) * 16}  y {(ch // 2 - 14) * 16}"
          f"   (viewport 320x224)")
    print(f"  cellmap        0x{b['map_off']:06X} .. 0x{b['map_off'] + b['map_bytes']:06X}"
          f"  ({b['map_bytes']} bytes)")
    print(f"  pixel data     0x{b['pix_off']:06X} .. 0x{b['pal_off']:06X}"
          f"  ({b['pix_bytes']} bytes)")
    print(f"  palette        0x{b['pal_off']:06X}  {b['pal_count']} colors")
    gap = b["pix_off"] - (b["map_off"] + b["map_bytes"])
    print(f"  gap after map  {gap} bytes")
    # cellmap flag-nibble histogram
    hist = {}
    idx_max = 0
    for i in range(0, b["map_bytes"], 2):
        v, = struct.unpack_from("<H", data, b["map_off"] + i)
        hist[v >> 12] = hist.get(v >> 12, 0) + 1
        idx_max = max(idx_max, v & 0xFFF)
    print("  flag nibbles   " + " ".join(f"{k:X}:{v}" for k, v in sorted(hist.items())))
    print(f"  max cell index 0x{idx_max:03X} ({idx_max})")


def show_palette(path):
    data = path.read_bytes()
    b = block0(data)
    pal = palette(data, b)
    for i, (r, g, bl) in enumerate(pal):
        print(f"  {i:3d}  {r:02X} {g:02X} {bl:02X}   #{r:02X}{g:02X}{bl:02X}")


def export_png(path):
    data = path.read_bytes()
    b = block0(data)
    pal = palette(data, b)
    GFX.mkdir(exist_ok=True)
    stem = path.stem.lower()

    # 1. palette strip, 16 px per swatch
    sw, cols = 16, 16
    rows_n = (len(pal) + cols - 1) // cols
    strip = []
    for ry in range(rows_n):
        line = bytearray()
        for cx in range(cols):
            i = ry * cols + cx
            line += bytes([i if i < len(pal) else 0] * sw)
        for _ in range(sw):
            strip.append(bytes(line))
    out = GFX / f"{stem}_palette.png"
    png.write_indexed(out, cols * sw, rows_n * sw, strip,
                      pal + [(0, 0, 0)] * (256 - len(pal)))
    print(f"  wrote {out.relative_to(ROOT)}  ({len(pal)} colors)")

    # 2. raw pixel block, laid out at the map's pixel width
    w = b["cell_w"] * 8
    npix = b["pix_bytes"]
    if npix and w:
        h = npix // w
        if h:
            src = data[b["pix_off"]:b["pix_off"] + w * h]
            rows = [src[y * w:(y + 1) * w] for y in range(h)]
            out = GFX / f"{stem}_pixels_{w}x{h}.png"
            png.write_indexed(out, w, h, rows, pal + [(0, 0, 0)] * (256 - len(pal)))
            print(f"  wrote {out.relative_to(ROOT)}  ({w}x{h})")

    # 3. cellmap visualisation: index low byte as grayscale, flags as hue
    cw, ch = b["cell_w"], b["cell_h"]
    rows = []
    vis_pal = [(i, i, i) for i in range(256)]
    for y in range(ch):
        line = bytearray()
        for x in range(cw):
            v, = struct.unpack_from("<H", data, b["map_off"] + (y * cw + x) * 2)
            line.append((v & 0xFFF) & 0xFF)
        rows.append(bytes(line))
    out = GFX / f"{stem}_cellmap_{cw}x{ch}.png"
    png.write_indexed(out, cw, ch, rows, vis_pal)
    print(f"  wrote {out.relative_to(ROOT)}  ({cw}x{ch} cells)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--block0", action="store_true")
    ap.add_argument("--palette", action="store_true")
    ap.add_argument("--png", action="store_true")
    args = ap.parse_args()

    if args.all:
        for p in sorted(GAME.glob("LEVEL*.PH")):
            show_blocks(p)
        return 0
    if not args.file:
        ap.error("give a .PH file or --all")
    p = Path(args.file)
    if not p.exists():
        p = GAME / args.file
    if args.block0:
        show_block0(p)
    elif args.palette:
        show_palette(p)
    elif args.png:
        export_png(p)
    else:
        show_blocks(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
