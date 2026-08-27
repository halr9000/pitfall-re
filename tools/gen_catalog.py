#!/usr/bin/env python3
"""Generate web/catalog_data.json for the asset browser.

Run after tools/render_level.py --all (and --tiles) so the PNGs it references
exist. Output is derived game data and is not committed.

    python3 tools/gen_catalog.py
"""
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ph_dump import block0, blocks, palette  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GAME = ROOT / "game"
WEB = ROOT / "web"
GFX = ROOT / "gfx"

# g_level_assets at 0x0046F0D8 — decoded with decode_tables.py, pasted here so
# the catalog works without re-parsing the EXE.
MANIFEST = [
    ("forest1.bg", "for_par.bg"), ("waterf1.bg", "waterlax.bg"),
    ("mine1.bg", "mine_lax.bg"), ("ruins1.bg", "clouds.bg"),
    ("temple1.bg", ""), ("forest2.bg", "for_par2.bg"),
    ("waterf2.bg", "waterlax.bg"), ("mine2.bg", "mine_lax.bg"),
    ("ruins2.bg", "clouds.bg"), ("temple2.bg", "templax2.bg"),
    ("wsarena.bg", "clouds.bg"), ("ceil1.bg", "simon1.bg"),
    ("ceil2.bg", "simon2.bg"), ("ceil3.bg", "simon3.bg"),
    ("", ""), ("logo2.bg", "logo3.bg"), ("ruins3.bg", "clouds.bg"),
    ("temple3.bg", ""), ("waterfal.bg", "waterlax.bg"), ("map1.bg", ""),
    ("gene2600.bg", ""), ("vines.bg", "intro.bg"), ("room2.bg", "clouds.bg"),
    ("cred1.bg", "cred2.bg"), ("level22.bg", "parlax22.bg"),
]


def main():
    levels = []
    for n in range(25):
        p = GAME / f"LEVEL{n:02d}.PH"
        if not p.exists():
            continue
        data = p.read_bytes()
        stem = p.stem.lower()
        b = block0(data)
        nblocks = sum(1 for _ in blocks(data))
        entry = {
            "n": n,
            "file": p.name,
            "bytes": len(data),
            "blocks": nblocks,
            "bg": MANIFEST[n][0],
            "parallax": MANIFEST[n][1],
            "empty": b["cell_w"] == 0,
        }
        if b["cell_w"]:
            pal = palette(data, b)
            flags = {}
            for i in range(0, b["map_bytes"], 2):
                v, = struct.unpack_from("<H", data, b["map_off"] + i)
                k = f"{v >> 12:X}"
                flags[k] = flags.get(k, 0) + 1
            entry.update({
                "cell_w": b["cell_w"], "cell_h": b["cell_h"],
                "px_w": b["cell_w"] * 8, "px_h": b["cell_h"] * 8,
                "tiles16_w": b["cell_w"] // 2, "tiles16_h": b["cell_h"] // 2,
                "scroll_max_x": (b["cell_w"] // 2 - 20) * 16,
                "scroll_max_y": (b["cell_h"] // 2 - 14) * 16,
                "tile_count": b["pix_bytes"] // 64,
                "palette": ["#%02x%02x%02x" % c for c in pal],
                "flags": dict(sorted(flags.items())),
                "map_png": f"../gfx/{stem}_map.png",
                "tiles_png": f"../gfx/{stem}_tiles.png",
            })
            for k in ("map_png", "tiles_png"):
                if not (GFX / Path(entry[k]).name).exists():
                    entry[k] = None
        levels.append(entry)

    WEB.mkdir(exist_ok=True)
    out = WEB / "catalog_data.json"
    out.write_text(json.dumps({"levels": levels}, indent=1))
    print(f"wrote {out.relative_to(ROOT)}  ({len(levels)} levels)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
