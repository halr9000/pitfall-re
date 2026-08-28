#!/usr/bin/env python3
"""Export sprite banks to the web bundle.

Writes, into web/data/sprites/:
    <name>.png    all frames of one bank packed into a sheet, transparent
    sprites.json  per-bank frame rects and origins

Frame origins are (-w/2, -h)-ish: the anchor is the sprite's bottom centre, so
the port draws a frame at (anchorX + ox, anchorY + oy).

    python3 tools/export_sprites.py
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import png  # noqa: E402
from ph_dump import blocks  # noqa: E402
from sprite import decode_all, is_bank  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GAME = ROOT / "game"
OUT = ROOT / "web" / "data" / "sprites"

# Banks to ship. INIT.PH holds 81 banks sharing Harry's palette — his whole
# animation library — but which bank is which action is not decoded yet, so the
# port ships a small, named-by-observation subset.
WANTED = [
    ("harry_a", "INIT.PH", 72, "12 frames, consistent height; used as the walk cycle"),
    ("harry_b", "INIT.PH", 66, "12 frames; used for the airborne pose"),
    ("font", "INIT.PH", 32, "carved-stone font: A-Z 0-9 punctuation"),
]


def pack(bank, out_png, pad=1):
    frames = bank["frames"]
    cols = 8
    rowsn = (len(frames) + cols - 1) // cols
    fw = max(f["w"] for f in frames) + pad * 2
    fh = max(f["h"] for f in frames) + pad * 2
    W, H = cols * fw, rowsn * fh
    canvas = [bytearray([0]) * W for _ in range(H)]
    rects = []
    for i, f in enumerate(frames):
        cx, cy = (i % cols) * fw + pad, (i // cols) * fh + pad
        for y in range(f["h"]):
            row = f["rows"][y]
            for x in range(f["w"]):
                if row[x]:
                    canvas[cy + y][cx + x] = row[x]
        rects.append({"x": cx, "y": cy, "w": f["w"], "h": f["h"],
                      "ox": f["ox"], "oy": f["oy"]})
    pal = list(bank["palette"]) + [(0, 0, 0)] * (256 - len(bank["palette"]))
    png.write_indexed(out_png, W, H, [bytes(r) for r in canvas], pal,
                      transparent_index=0)
    return W, H, rects


def main():
    argparse.ArgumentParser().parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {}
    for name, fname, blk, note in WANTED:
        data = (GAME / fname).read_bytes()
        found = None
        for i, _h, p, s in blocks(data):
            if i == blk and is_bank(data, p, s):
                found = decode_all(data, p, s)
                break
        if not found:
            print(f"  {name}: {fname} block {blk} is not a sprite bank — skipped")
            continue
        W, H, rects = pack(found, OUT / f"{name}.png")
        meta[name] = {"sheet": f"{name}.png", "sheet_w": W, "sheet_h": H,
                      "source": f"{fname} block {blk}", "note": note,
                      "frames": rects}
        print(f"  {name:<9} {fname} blk {blk:<3} {len(rects):>3} frames  {W}x{H}")

    (OUT / "sprites.json").write_text(json.dumps({
        "note": ("Frame origins are relative to the sprite's bottom-centre "
                 "anchor: draw at (anchorX + ox, anchorY + oy). Which bank "
                 "corresponds to which player action is not decoded yet."),
        "banks": meta,
    }, indent=1))
    total = sum(f.stat().st_size for f in OUT.iterdir())
    print(f"\nwrote {(OUT / 'sprites.json').relative_to(ROOT)} — "
          f"{len(meta)} banks, {total / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
