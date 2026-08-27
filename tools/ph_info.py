#!/usr/bin/env python3
"""Survey the .PH level container files: header fields + candidate offsets.

Usage:
    python3 tools/ph_info.py                # table of all game/*.PH headers
    python3 tools/ph_info.py LEVEL00.PH -v  # verbose single-file dump
"""
import argparse
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAME = ROOT / "game"

HDR_DWORDS = 6


def survey(paths):
    print(f"{'file':<13} {'size':>9} " + " ".join(f"{'d%d' % i:>10}" for i in range(HDR_DWORDS))
          + "   notes")
    for p in paths:
        d = p.read_bytes()
        h = struct.unpack_from("<%dI" % HDR_DWORDS, d, 0)
        notes = []
        for i, v in enumerate(h):
            if v and v < len(d):
                notes.append(f"d{i}<size")
        # d3 == w*h*2 + 32 hypothesis
        w, hgt = h[1], h[2]
        if w and hgt:
            pred = w * hgt * 2 + 32
            if pred == h[3]:
                notes.append("d3==w*h*2+32")
            else:
                notes.append(f"d3-w*h*2={h[3] - w * hgt * 2}")
        print(f"{p.name:<13} {len(d):>9} " + " ".join(f"0x{v:08X}" for v in h) + "   " + ",".join(notes))


def verbose(p):
    d = p.read_bytes()
    print(f"== {p.name}  {len(d)} bytes (0x{len(d):X}) ==")
    h = struct.unpack_from("<%dI" % HDR_DWORDS, d, 0)
    for i, v in enumerate(h):
        print(f"  d{i} @0x{i * 4:02X} = 0x{v:08X} ({v})")
    print("  word table @0x18:")
    n = h[5] if h[5] < 4096 else 64
    for i in range(0, min(n, 128)):
        off = 0x18 + i * 2
        if off + 2 > len(d):
            break
        w, = struct.unpack_from("<H", d, off)
        if i % 8 == 0:
            print(f"\n    [{i:3d}] ", end="")
        print(f"{w:04X} ", end="")
    print()
    # tail of file
    print(f"\n  last 32 bytes: {d[-32:].hex(' ')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("-v", action="store_true")
    args = ap.parse_args()
    if args.file:
        p = GAME / args.file if not Path(args.file).exists() else Path(args.file)
        verbose(p) if args.v else survey([p])
    else:
        survey(sorted(GAME.glob("*.PH")))


if __name__ == "__main__":
    main()
