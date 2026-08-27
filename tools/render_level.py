#!/usr/bin/env python3
"""Composite a level's cellmap + 8x8 tile sheet + palette into a PNG.

    python3 tools/render_level.py LEVEL13.PH            -> gfx/level13_map.png
    python3 tools/render_level.py LEVEL13.PH --tiles    -> gfx/level13_tiles.png
    python3 tools/render_level.py --all                 -> every level map

The cellmap word is  (flags << 12) | tile_index ; only the index is used for
drawing. --flags overlays the flag nibble as a colour wash so collision data can
be eyeballed against the artwork.
"""
import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import png  # noqa: E402
from ph_dump import block0, palette  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GAME = ROOT / "game"
GFX = ROOT / "gfx"


def tile_sheet(data, b):
    """Return list of 34-ish 8x8 tiles, each a list of 8 bytes-rows."""
    n = b["pix_bytes"] // 64
    base = b["pix_off"]
    return [[data[base + t * 64 + y * 8: base + t * 64 + y * 8 + 8] for y in range(8)]
            for t in range(n)]


def render_map(path, show_flags=False, alpha=False):
    data = path.read_bytes()
    b = block0(data)
    if not b["cell_w"]:
        print(f"  {path.name}: empty header, skipped")
        return
    pal = palette(data, b)
    tiles = tile_sheet(data, b)
    cw, ch = b["cell_w"], b["cell_h"]
    W, H = cw * 8, ch * 8

    # palette: level colours 0..n-1, then flag-overlay colours at 240+
    full = list(pal) + [(0, 0, 0)] * (256 - len(pal))
    full[255] = (255, 0, 255)   # transparent slot when --alpha
    flag_colors = {8: (255, 0, 0), 9: (255, 128, 0), 0xB: (255, 255, 0),
                   0xC: (0, 255, 255), 0xD: (0, 128, 255), 0xF: (255, 0, 255)}
    for i, (k, c) in enumerate(sorted(flag_colors.items())):
        full[240 + i] = c
    flag_slot = {k: 240 + i for i, (k, _) in enumerate(sorted(flag_colors.items()))}

    rows = []
    for cy in range(ch):
        fill = 255 if alpha else 0
        band = [bytearray([fill]) * W for _ in range(8)]
        for cx in range(cw):
            v, = struct.unpack_from("<H", data, b["map_off"] + (cy * cw + cx) * 2)
            idx, fl = v & 0xFFF, v >> 12
            if alpha and not (fl & 1):
                continue          # bit 0 clear -> cell is transparent
            if idx < len(tiles):
                t = tiles[idx]
                for y in range(8):
                    band[y][cx * 8:cx * 8 + 8] = t[y]
            if show_flags and fl in flag_slot:
                band[0][cx * 8] = flag_slot[fl]
                band[0][cx * 8 + 1] = flag_slot[fl]
                band[1][cx * 8] = flag_slot[fl]
        rows.extend(bytes(r) for r in band)

    GFX.mkdir(exist_ok=True)
    suffix = "_flags" if show_flags else ("_alpha" if alpha else "")
    out = GFX / f"{path.stem.lower()}_map{suffix}.png"
    png.write_indexed(out, W, H, rows, full,
                      transparent_index=255 if alpha else None)
    print(f"  {out.relative_to(ROOT)}  {W}x{H}  {len(tiles)} tiles  {len(pal)} colors")


def render_tiles(path, cols=32, scale=2):
    data = path.read_bytes()
    b = block0(data)
    if not b["cell_w"]:
        return
    pal = palette(data, b)
    tiles = tile_sheet(data, b)
    full = list(pal) + [(255, 0, 255)] * (256 - len(pal))
    rows_n = (len(tiles) + cols - 1) // cols
    W, H = cols * 8, rows_n * 8
    rows = []
    for ry in range(rows_n):
        band = [bytearray(b"\xff" * W) for _ in range(8)]
        for cx in range(cols):
            t = ry * cols + cx
            if t >= len(tiles):
                break
            for y in range(8):
                band[y][cx * 8:cx * 8 + 8] = tiles[t][y]
        rows.extend(bytes(r) for r in band)
    if scale > 1:
        rows = list(png.scale_rows(rows, W, scale))
        W, H = W * scale, H * scale
    GFX.mkdir(exist_ok=True)
    out = GFX / f"{path.stem.lower()}_tiles.png"
    png.write_indexed(out, W, H, rows, full)
    print(f"  {out.relative_to(ROOT)}  {W}x{H}  {len(tiles)} tiles")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--tiles", action="store_true")
    ap.add_argument("--flags", action="store_true")
    ap.add_argument("--alpha", action="store_true",
                    help="treat cellmap flag bit 0 as an opacity bit")
    args = ap.parse_args()

    targets = sorted(GAME.glob("LEVEL*.PH")) if args.all else None
    if targets is None:
        if not args.file:
            ap.error("give a .PH file or --all")
        p = Path(args.file)
        targets = [p if p.exists() else GAME / args.file]
    for p in targets:
        if args.tiles:
            render_tiles(p)
        else:
            render_map(p, args.flags, args.alpha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
