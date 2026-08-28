#!/usr/bin/env python3
"""Hunt for code that converts a pixel coordinate to a cellmap index.

The cellmap is 8x8 cells, so any consumer must divide a pixel coordinate by 8
(`sar`/`shr` reg, 3) and then scale a row by the map width. This scans .text for
shift-by-3 instructions, groups them by enclosing function (nearest rel32 call
target at or below), and scores each function by how many cellmap-shaped
operations it contains.

    python3 tools/find_cellmap_users.py [--min 2] [--show ADDR]
"""
import argparse
import sys
from bisect import bisect_right
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import instruction_set as isa  # noqa: E402
from find_callers import call_targets  # noqa: E402
from labels import load_labels  # noqa: E402
from pe_map import load_pe  # noqa: E402


def scan(pe):
    """Linear-sweep each code section, yielding (va, Insn)."""
    for s in pe.sections:
        if not s.is_code or not s.rawsize:
            continue
        p, end = s.rawptr, s.rawptr + s.rawsize
        va = pe.off_to_va(p)
        while p < end - 1:
            ins = isa.decode(pe.data, p, va)
            yield va, ins
            p += ins.length
            va += ins.length


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=2)
    args = ap.parse_args()

    pe = load_pe()
    lab = load_labels()
    keys = sorted(call_targets(pe))

    def owner(va):
        i = bisect_right(keys, va) - 1
        return keys[i] if i >= 0 else None

    hits = {}
    for va, ins in scan(pe):
        if not ins.valid:
            continue
        # pixel -> cell: shift right by 3
        if ins.mnemonic in ("sar", "shr") and ins.imm == 3:
            hits.setdefault(owner(va), []).append((va, ins.text))
        # cell word -> tile index, or a flag test on the high bits
        elif ins.imm in (0xFFF, 0x8000) and ins.mnemonic in ("and", "test", "cmp"):
            hits.setdefault(owner(va), []).append((va, ins.text))

    rows = []
    for fn, lst in hits.items():
        if fn is None or len(lst) < args.min:
            continue
        rows.append((len(lst), fn, lst))
    rows.sort(reverse=True)

    for n, fn, lst in rows:
        name = lab.name(fn)
        print(f"0x{fn:08X}  {n:3d} hits" + (f"  <{name}>" if name else ""))
        for va, txt in lst[:6]:
            print(f"      0x{va:08X}  {txt}")
        if len(lst) > 6:
            print(f"      ... {len(lst) - 6} more")
    print(f"-- {len(rows)} functions with >= {args.min} cellmap-shaped ops")
    return 0


if __name__ == "__main__":
    sys.exit(main())
