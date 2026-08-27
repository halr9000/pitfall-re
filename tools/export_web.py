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
from ph_dump import blocks, layers, palette  # noqa: E402
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
    # index 0 is the transparent colour for masked cells (blit_cell_mode0)
    png.write_indexed(out, W, H, rows, full, transparent_index=0)
    return W, H, n


def export_layer(data, n, li, blk_index, b):
    pal = palette(data, b)
    stem = f"level{n:02d}_l{li}"
    sheet_w, sheet_h, ntiles = tile_sheet_png(data, b, pal, DATA / f"{stem}.png")
    cells = data[b["map_off"]:b["map_off"] + b["map_bytes"]]
    (DATA / f"{stem}.bin").write_bytes(cells)
    flags = {}
    for i in range(0, len(cells), 2):
        v, = struct.unpack_from("<H", cells, i)
        k = "%X" % (v >> 12)
        flags[k] = flags.get(k, 0) + 1
    return {
        "block": blk_index,
        "cell_w": b["cell_w"], "cell_h": b["cell_h"],
        "px_w": b["cell_w"] * 8, "px_h": b["cell_h"] * 8,
        "tile_count": ntiles,
        "sheet": f"{stem}.png", "sheet_w": sheet_w, "sheet_h": sheet_h,
        "cells": f"{stem}.bin",
        "palette": ["#%02x%02x%02x" % c for c in pal],
        "flags": dict(sorted(flags.items())),
    }


def export(n):
    p = GAME / f"LEVEL{n:02d}.PH"
    if not p.exists():
        return None
    data = p.read_bytes()
    ls = layers(data)
    entry = {
        "n": n,
        "bg": MANIFEST[n][0],
        "parallax": MANIFEST[n][1],
        "blocks": sum(1 for _ in blocks(data)),
    }
    if not ls:
        entry["empty"] = True
        return entry

    DATA.mkdir(parents=True, exist_ok=True)
    main_b = ls[0][1]
    cw, ch = main_b["cell_w"], main_b["cell_h"]
    entry.update({
        "cell_w": cw, "cell_h": ch,
        "px_w": cw * 8, "px_h": ch * 8,
        "tiles_w": cw // 2, "tiles_h": ch // 2,
        "scroll_max_x": (cw // 2 - 20) * 16,
        "scroll_max_y": (ch // 2 - 14) * 16,
        # layer 0 is the main background; layer 1 (when present) is the
        # parallax named in g_level_assets, drawn behind it.
        "layers": [export_layer(data, n, li, bi, b)
                   for li, (bi, b) in enumerate(ls)],
    })
    return entry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, default=None)
    args = ap.parse_args()

    targets = [args.level] if args.level is not None else range(25)
    levels = []
    for n in targets:
        e = export(n)
        if e:
            levels.append(e)
            if e.get("empty"):
                print(f"  level{n:02d}  no layer blocks, metadata only")
            else:
                desc = "  ".join(
                    f"L{i}(blk{L['block']}) {L['px_w']}x{L['px_h']} "
                    f"{L['tile_count']}t/{len(L['palette'])}c"
                    for i, L in enumerate(e["layers"]))
                print(f"  level{n:02d}  {e['bg']:<13} {desc}")

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
        "cell_bits": {
            "index": "0-11 tile index",
            "12": "set = opaque blit; clear = masked blit, palette index 0 transparent",
            "13-14": "either set routes to blit_cell_mode2 (0x00436BD8), not yet read",
            "15": "never tested while drawing; meaning unresolved",
        },
        "levels": levels,
    }, indent=1))
    total = sum(f.stat().st_size for f in DATA.iterdir())
    print(f"\nwrote {meta.relative_to(ROOT)} — {len(levels)} levels, "
          f"{total / 1024:.0f} KB total in {DATA.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
