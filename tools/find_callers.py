#!/usr/bin/env python3
"""Call-graph helpers.

    python3 tools/find_callers.py <addr>        callers of a function
    python3 tools/find_callers.py --entries     every distinct rel32 call target
                                                (i.e. the function table)
    python3 tools/find_callers.py --owner <addr>
                                                the nearest call target at or
                                                below <addr> — the function that
                                                contains it
    python3 tools/find_callers.py --callees <addr> [--max N]
                                                functions called from <addr>
"""
import argparse
import struct
import sys
from bisect import bisect_right
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import instruction_set as isa  # noqa: E402
from labels import load_labels  # noqa: E402
from pe_map import load_pe  # noqa: E402


def call_targets(pe):
    """All rel32 call destinations inside code sections, with their call sites."""
    out = {}
    d = pe.data
    for s in pe.sections:
        if not s.is_code or not s.rawsize:
            continue
        for p in range(s.rawptr, s.rawptr + s.rawsize - 5):
            if d[p] != 0xE8:
                continue
            rel = struct.unpack_from("<i", d, p + 1)[0]
            va = pe.off_to_va(p)
            tgt = (va + 5 + rel) & 0xFFFFFFFF
            if pe.is_valid_va(tgt) and pe.section_of_va(tgt).is_code:
                out.setdefault(tgt, []).append(va)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("addr", nargs="?")
    ap.add_argument("--entries", action="store_true")
    ap.add_argument("--owner", metavar="ADDR")
    ap.add_argument("--callees", metavar="ADDR")
    ap.add_argument("--max", type=int, default=400)
    args = ap.parse_args()

    pe = load_pe()
    lab = load_labels()
    targets = call_targets(pe)

    if args.entries:
        for t in sorted(targets):
            n = lab.name(t)
            print(f"0x{t:08X}  {len(targets[t]):4d} callers" + (f"  <{n}>" if n else ""))
        print(f"-- {len(targets)} distinct call targets")
        return 0

    if args.owner:
        _, va = pe.resolve(args.owner)
        keys = sorted(targets)
        i = bisect_right(keys, va) - 1
        if i < 0:
            print("no call target below that address")
            return 1
        f = keys[i]
        n = lab.name(f)
        print(f"0x{va:08X} is inside 0x{f:08X}" + (f" <{n}>" if n else "")
              + f"  (+0x{va - f:X}, {len(targets[f])} callers)")
        return 0

    if args.callees:
        _, va = pe.resolve(args.callees)
        off = pe.va_to_off(va)
        seen = []
        p, pva, n = off, va, 0
        while n < args.max:
            ins = isa.decode(pe.data, p, pva)
            if ins.is_call and ins.target and ins.target not in seen:
                seen.append(ins.target)
            if ins.is_ret:
                break
            p += ins.length
            pva += ins.length
            n += 1
        for t in seen:
            nm = lab.name(t)
            print(f"  0x{t:08X}" + (f"  <{nm}>" if nm else ""))
        print(f"-- {len(seen)} callees")
        return 0

    if not args.addr:
        ap.error("give an address or --entries")
    _, va = pe.resolve(args.addr)
    for c in targets.get(va, []):
        nm = lab.name(c)
        print(f"  0x{c:08X}" + (f"  <{nm}>" if nm else ""))
    print(f"-- {len(targets.get(va, []))} callers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
