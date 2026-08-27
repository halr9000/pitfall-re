#!/usr/bin/env python3
"""Verify the .PH block-0 model against every level file.

Checks, per level:
  * the container splits into blocks with zero bytes left over
  * pixel-data size is a whole number of 64-byte 8x8 tiles
  * the highest index used by the cellmap is < tile count
  * the palette region is exactly pal_count * 3 bytes and ends at block end

Usage: python3 tools/check_ph.py
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ph_dump import block0, blocks  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GAME = ROOT / "game"


def main():
    print(f"{'file':<13} {'cells':>9} {'tiles16':>9} {'8x8 tiles':>10} {'maxidx':>7} "
          f"{'colors':>7} {'blocks':>7}  status")
    bad = 0
    for p in sorted(GAME.glob("LEVEL*.PH")):
        data = p.read_bytes()
        try:
            b = block0(data)
        except Exception as e:  # noqa: BLE001
            print(f"{p.name:<13} block0 parse failed: {e}")
            bad += 1
            continue
        cw, ch = b["cell_w"], b["cell_h"]
        if cw == 0 or ch == 0:
            print(f"{p.name:<13} {'-':>9} {'-':>9} {'-':>10} {'-':>7} {'-':>7} "
                  f"{'-':>7}  EMPTY (zero header)")
            continue
        errs = []
        ntiles, rem = divmod(b["pix_bytes"], 64)
        if rem:
            errs.append(f"pixel bytes not /64 (rem {rem})")
        maxidx = 0
        for i in range(0, b["map_bytes"], 2):
            v, = struct.unpack_from("<H", data, b["map_off"] + i)
            maxidx = max(maxidx, v & 0xFFF)
        if maxidx >= ntiles:
            errs.append(f"cell index {maxidx} >= tile count {ntiles}")
        pal_bytes = b["off"] + b["size"] - b["pal_off"]
        if pal_bytes != b["pal_count"] * 3:
            errs.append(f"palette {pal_bytes} != {b['pal_count']}*3")
        total = sum(4 + s for _, _, _, s in blocks(data))
        nblocks = sum(1 for _ in blocks(data))
        if total != len(data):
            errs.append(f"{len(data) - total} bytes unaccounted")
        status = "ok" if not errs else "FAIL: " + "; ".join(errs)
        if errs:
            bad += 1
        print(f"{p.name:<13} {cw}x{ch:<5} {cw // 2}x{ch // 2:<5} {ntiles:>10} "
              f"{maxidx:>7} {b['pal_count']:>7} {nblocks:>7}  {status}")
    print(f"\n{bad} file(s) failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
