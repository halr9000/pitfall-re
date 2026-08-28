#!/usr/bin/env python3
"""Decode the 0x34561234 sprite banks found in INIT.PH and the level files.

Bank layout (block payload):
    +0x00  u32   magic 0x34561234
    +0x04  u32   palette offset, block-relative (== block size - ncol*3)
    +0x08  u16   ncol      palette entries
    +0x0A  u16   nframes
    +0x0C  u32[nframes]    frame offsets, block-relative
    frame:
        +0x00 s32 width
        +0x04 s32 height
        +0x08 s32 x origin   (signed, usually negative — a hotspot offset)
        +0x0C s32 y origin
        +0x10 RLE rows
    palette: ncol * 3 bytes, RGB

Row RLE, one stream per row:
    b >= 0x80   emit (b & 0x7F) literal pixels, taken from the following bytes
    b <  0x7E   skip b pixels (transparent)
    b == 0x7F   end of row
    b == 0x7E   end of sprite
Palette index 0 is transparent, matching the tile blitter's masked mode.

    python3 tools/sprite.py --list INIT.PH
    python3 tools/sprite.py INIT.PH 32 --png
    python3 tools/sprite.py --scan            # every bank in every file
"""
import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import png  # noqa: E402
from ph_dump import blocks  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GAME = ROOT / "game"
GFX = ROOT / "gfx"
MAGIC = 0x34561234

END_ROW = 0x7F
END_SPRITE = 0x7E


class BadBank(Exception):
    pass


def is_bank(data, off, size):
    return size >= 16 and struct.unpack_from("<I", data, off)[0] == MAGIC


def parse_bank(data, off, size):
    pal_off, = struct.unpack_from("<I", data, off + 4)
    ncol, nframes = struct.unpack_from("<HH", data, off + 8)
    if pal_off + ncol * 3 != size or nframes == 0:
        raise BadBank(f"palette {pal_off}+{ncol}*3 != {size}")
    offs = list(struct.unpack_from("<%dI" % nframes, data, off + 0x0C))
    for o in offs:
        if not (0x0C + 4 * nframes <= o < pal_off):
            raise BadBank(f"frame offset 0x{o:X} out of range")
    pal = [tuple(data[off + pal_off + i * 3: off + pal_off + i * 3 + 3])
           for i in range(ncol)]
    return dict(off=off, size=size, ncol=ncol, nframes=nframes,
                pal_off=pal_off, frame_offs=offs, palette=pal)


def decode_frame(data, base, foff, limit):
    w, h, ox, oy = struct.unpack_from("<4i", data, base + foff)
    if not (0 <= w <= 512 and 0 <= h <= 512):
        raise BadBank(f"frame {w}x{h}")
    if w == 0 or h == 0:       # legitimately empty frame (blank animation cel)
        return dict(w=max(w, 1), h=max(h, 1), ox=ox, oy=oy,
                    rows=[bytes(max(w, 1))], bytes_used=0x10)
    rows = [bytearray(w) for _ in range(h)]
    p = base + foff + 0x10
    y = x = 0
    end = base + limit
    while y < h and p < end:
        b = data[p]
        p += 1
        if b == END_SPRITE:
            break
        if b == END_ROW:
            y += 1
            x = 0
            continue
        if b & 0x80:
            n = b & 0x7F
            for _ in range(n):
                if p >= end:
                    break
                if x < w:
                    rows[y][x] = data[p]
                x += 1
                p += 1
        else:
            x += b
    return dict(w=w, h=h, ox=ox, oy=oy, rows=[bytes(r) for r in rows],
                bytes_used=p - (base + foff))


def decode_all(data, off, size):
    bank = parse_bank(data, off, size)
    frames = []
    for i, fo in enumerate(bank["frame_offs"]):
        frames.append(decode_frame(data, off, fo, bank["pal_off"]))
    bank["frames"] = frames
    return bank


def sheet_png(bank, out, scale=2, pad=1):
    """Lay every frame out in a row-major sheet, transparent background."""
    frames = bank["frames"]
    cols = min(8, len(frames))
    rowsn = (len(frames) + cols - 1) // cols
    fw = max(f["w"] for f in frames) + pad * 2
    fh = max(f["h"] for f in frames) + pad * 2
    W, H = cols * fw, rowsn * fh
    canvas = [bytearray([0]) * W for _ in range(H)]
    for i, f in enumerate(frames):
        cx, cy = (i % cols) * fw + pad, (i // cols) * fh + pad
        for y in range(f["h"]):
            row = f["rows"][y]
            for x in range(f["w"]):
                if row[x]:
                    canvas[cy + y][cx + x] = row[x]
    pal = list(bank["palette"]) + [(0, 0, 0)] * (256 - len(bank["palette"]))
    rows = [bytes(r) for r in canvas]
    if scale > 1:
        rows = list(png.scale_rows(rows, W, scale))
        W, H = W * scale, H * scale
    png.write_indexed(out, W, H, rows, pal, transparent_index=0)
    return W, H


def iter_banks(path):
    data = path.read_bytes()
    for i, _h, p, s in blocks(data):
        if is_bank(data, p, s):
            yield i, p, s, data


def cmd_list(path):
    ok = bad = 0
    for i, p, s, data in iter_banks(path):
        try:
            b = decode_all(data, p, s)
            used = sum(f["bytes_used"] for f in b["frames"])
            span = b["pal_off"] - (0x0C + 4 * b["nframes"])
            print(f"  block {i:>4}  {s:>7}B  {b['nframes']:>3} frames  "
                  f"{b['ncol']:>3} colors  sizes "
                  + ",".join(f"{f['w']}x{f['h']}" for f in b["frames"][:5])
                  + ("…" if b["nframes"] > 5 else "")
                  + f"   rle {used}/{span}B")
            ok += 1
        except BadBank as e:
            print(f"  block {i:>4}  {s:>7}B  UNPARSED: {e}")
            bad += 1
    print(f"-- {ok} banks parsed, {bad} unparsed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("block", nargs="?", type=int)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--png", action="store_true")
    ap.add_argument("--scale", type=int, default=2)
    args = ap.parse_args()

    if args.scan:
        tot = okc = 0
        for f in sorted(GAME.glob("*.PH")):
            data = f.read_bytes()
            for i, _h, p, s in blocks(data):
                if not is_bank(data, p, s):
                    continue
                tot += 1
                try:
                    decode_all(data, p, s)
                    okc += 1
                except BadBank as e:
                    print(f"  {f.name} block {i}: {e}")
        print(f"-- {okc}/{tot} sprite banks decode cleanly")
        return 0 if okc == tot else 1

    if not args.file:
        ap.error("give a .PH file, or --scan")
    path = Path(args.file)
    if not path.exists():
        path = GAME / args.file

    if args.list or args.block is None:
        print(f"== {path.name} ==")
        cmd_list(path)
        return 0

    data = path.read_bytes()
    for i, _h, p, s in blocks(data):
        if i != args.block:
            continue
        bank = decode_all(data, p, s)
        print(f"{path.name} block {i}: {bank['nframes']} frames, "
              f"{bank['ncol']} colors")
        for j, f in enumerate(bank["frames"]):
            print(f"  frame {j:>3}  {f['w']:>3}x{f['h']:<3}  "
                  f"origin ({f['ox']},{f['oy']})  {f['bytes_used']}B")
        if args.png:
            GFX.mkdir(exist_ok=True)
            out = GFX / f"{path.stem.lower()}_bank{i:03d}.png"
            W, H = sheet_png(bank, out, args.scale)
            print(f"  wrote {out.relative_to(ROOT)}  {W}x{H}")
        return 0
    print(f"block {args.block} not found")
    return 1


if __name__ == "__main__":
    sys.exit(main())
