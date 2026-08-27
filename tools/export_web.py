#!/usr/bin/env python3
"""Export the decoded level data as a web asset bundle for the browser port.

Per level it emits, into web/data/:
    levelNN.png    unscaled 8x8 tile sheet, 32 tiles per row, indexed PNG
    levelNN.bin    the raw cellmap, cell_w * cell_h little-endian uint16
    levels.json    metadata for every level (dimensions, palette, tile count)

The browser composites the background from the tile sheet + cellmap, exactly the
way `load_level` does, rather than being handed a pre-flattened screenshot — so
the port keeps the tile indices it needs for collision later.

    python3 tools/export_web.py            # all levels
    python3 tools/export_web.py --level 13
"""
import argparse
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import png  # noqa: E402
from ph_dump import block0, blocks, palette  # noqa: E402
from gen_catalog import MANIFEST  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GAME = ROOT / "game"
DATA = ROOT / "web" / "data"

TILES_PER_ROW = 32


def tile_sheet_png(data, b, pal, out):
    """Write the tile sheet unscaled, 32 tiles per row, index 255 = unused."""
    n = b["pix_bytes"] // 64
    base = b["pix_off"]
    rows_n = (n + TILES_PER_ROW - 1) // TILES_PER_ROW
    W, H = TILES_PER_ROW * 8, rows_n * 8
    full = list(pal) + [(0, 0, 0)] * (256 - len(pal))
    full[255] = (255, 0, 255)
    rows = []
    for ry in range(rows_n):
        band = [bytearray([255]) * W for _ in range(8)]
        for cx in range(TILES_PER_ROW):
            t = ry * TILES_PER_ROW + cx
            if t >= n:
                break
            for y in range(8):
                src = base + t * 64 + y * 8
                band[y][cx * 8:cx * 8 + 8] = data[src:src + 8]
        rows.extend(bytes(r) for r in band)
    png.write_indexed(out, W, H, rows, full)
    return W, H, n


def export(n, index):
    p = GAME / f"LEVEL{n:02d}.PH"
    if not p.exists():
        return None
    data = p.read_bytes()
    b = block0(data)
    entry = {
        "n": n,
        "bg": MANIFEST[n][0],
        "parallax": MANIFEST[n][1],
        "blocks": sum(1 for _ in blocks(data)),
    }
    if not b["cell_w"]:
        entry["empty"] = True
        return entry

    pal = palette(data, b)
    DATA.mkdir(parents=True, exist_ok=True)
    sheet_w, sheet_h, ntiles = tile_sheet_png(
        data, b, pal, DATA / f"level{n:02d}.png")

    cw, ch = b["cell_w"], b["cell_h"]
    cells = data[b["map_off"]:b["map_off"] + b["map_bytes"]]
    (DATA / f"level{n:02d}.bin").write_bytes(cells)

    # flag-nibble histogram, useful for the debug overlay
    flags = {}
    for i in range(0, len(cells), 2):
        v, = struct.unpack_from("<H", cells, i)
        k = "%X" % (v >> 12)
        flags[k] = flags.get(k, 0) + 1

    entry.update({
        "cell_w": cw, "cell_h": ch,
        "px_w": cw * 8, "px_h": ch * 8,
        "tiles_w": cw // 2, "tiles_h": ch // 2,
        "scroll_max_x": (cw // 2 - 20) * 16,
        "scroll_max_y": (ch // 2 - 14) * 16,
        "tile_count": ntiles,
        "sheet": f"level{n:02d}.png",
        "sheet_w": sheet_w, "sheet_h": sheet_h,
        "cells": f"level{n:02d}.bin",
        "palette": ["#%02x%02x%02x" % c for c in pal],
        "flags": dict(sorted(flags.items())),
    })
    return entry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, default=None)
    args = ap.parse_args()

    targets = [args.level] if args.level is not None else range(25)
    levels = []
    for n in targets:
        e = export(n, len(levels))
        if e:
            levels.append(e)
            if e.get("empty"):
                print(f"  level{n:02d}  empty header, metadata only")
            else:
                print(f"  level{n:02d}  {e['bg']:<13} {e['px_w']}x{e['px_h']}px  "
                      f"{e['tile_count']} tiles  {len(e['palette'])} colors")

    DATA.mkdir(parents=True, exist_ok=True)
    meta = DATA / "levels.json"
    if args.level is not None and meta.exists():
        old = json.loads(meta.read_text())
        by_n = {L["n"]: L for L in old["levels"]}
        for L in levels:
            by_n[L["n"]] = L
        levels = [by_n[k] for k in sorted(by_n)]
    meta.write_text(json.dumps({
        "game": "Pitfall: The Mayan Adventure",
        "screen": {"w": 320, "h": 224},
        "tile": 16, "cell": 8,
        "levels": levels,
    }, indent=1))
    total = sum(f.stat().st_size for f in DATA.iterdir())
    print(f"\nwrote {meta.relative_to(ROOT)} — {len(levels)} levels, "
          f"{total / 1024:.0f} KB total in {DATA.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
