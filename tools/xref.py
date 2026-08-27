#!/usr/bin/env python3
"""Cross-reference finder for PITFALL.EXE.

Three reference kinds are reported:
  reloc   an absolute dword listed in the PE .reloc table that holds this VA
          (exact: covers mov reg,imm32 / push imm32 / [abs] operands / pointer
          tables in .data) — no false positives
  rel32   an E8/E9/0F8x branch in a code section whose computed target is this VA
  raw     any other little-endian dword equal to the VA (catches non-reloc data)

Usage:
    python3 tools/xref.py <addr> [--code] [-c N] [-r START END] [--no-raw]
"""
import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import instruction_set as isa  # noqa: E402
from labels import load_labels  # noqa: E402
from pe_map import load_pe  # noqa: E402


def reloc_sites(pe):
    """Yield file offsets of every HIGHLOW base relocation."""
    d = pe.data
    lfanew = struct.unpack_from("<I", d, 0x3C)[0]
    opt = lfanew + 24
    rva, size = struct.unpack_from("<II", d, opt + 96 + 5 * 8)
    if not rva:
        return
    base = pe.rva_to_off(rva)
    p, end = base, base + size
    while p < end:
        page_rva, blk = struct.unpack_from("<II", d, p)
        if blk < 8:
            break
        for i in range((blk - 8) // 2):
            e, = struct.unpack_from("<H", d, p + 8 + i * 2)
            typ, off12 = e >> 12, e & 0xFFF
            if typ == 3:  # IMAGE_REL_BASED_HIGHLOW
                o = pe.rva_to_off(page_rva + off12)
                if o is not None:
                    yield o
        p += blk


_reloc_cache = {}


def reloc_map(pe):
    key = id(pe)
    if key not in _reloc_cache:
        m = {}
        d = pe.data
        for o in reloc_sites(pe):
            v, = struct.unpack_from("<I", d, o)
            m.setdefault(v, []).append(o)
        _reloc_cache[key] = m
    return _reloc_cache[key]


def branch_refs(pe, target, lo=None, hi=None):
    d = pe.data
    for s in pe.sections:
        if not s.is_code or not s.rawsize:
            continue
        start, end = s.rawptr, s.rawptr + s.rawsize
        if lo is not None:
            start, end = max(start, lo), min(end, hi)
        for p in range(start, end - 5):
            b = d[p]
            if b in (0xE8, 0xE9):
                rel = struct.unpack_from("<i", d, p + 1)[0]
                va = pe.off_to_va(p)
                if va is not None and (va + 5 + rel) & 0xFFFFFFFF == target:
                    yield p, "rel32", "call" if b == 0xE8 else "jmp"
            elif b == 0x0F and 0x80 <= d[p + 1] <= 0x8F and p + 6 <= end:
                rel = struct.unpack_from("<i", d, p + 2)[0]
                va = pe.off_to_va(p)
                if va is not None and (va + 6 + rel) & 0xFFFFFFFF == target:
                    yield p, "rel32", "j" + isa.CC[d[p + 1] & 0xF]
            elif b == 0xEB or (0x70 <= b <= 0x7F):
                rel = struct.unpack_from("<b", d, p + 1)[0]
                va = pe.off_to_va(p)
                if va is not None and (va + 2 + rel) & 0xFFFFFFFF == target:
                    yield p, "rel8", "jmp" if b == 0xEB else "j" + isa.CC[b & 0xF]


def context(pe, lab, off, nbytes):
    """Disassemble a few instructions ending near off (best effort backwards scan)."""
    start = max(0, off - nbytes)
    out = []
    p = start
    while p < off + 8:
        va = pe.off_to_va(p)
        if va is None:
            break
        ins = isa.decode(pe.data, p, va)
        mark = "->" if p == off else "  "
        out.append(f"    {mark} 0x{va:08X}  {ins.text}")
        p += ins.length
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("addr")
    ap.add_argument("--code", action="store_true", help="only report hits inside code sections")
    ap.add_argument("-c", type=int, default=0, metavar="N", help="show N bytes of disassembly context")
    ap.add_argument("-r", nargs=2, metavar=("START", "END"), help="restrict raw/branch scan to a file range")
    ap.add_argument("--no-raw", action="store_true")
    args = ap.parse_args()

    pe = load_pe()
    lab = load_labels()
    _, target = pe.resolve(args.addr)
    if target is None:
        print("could not resolve address")
        return 1
    name = lab.name(target)
    print(f"xrefs to 0x{target:08X}" + (f" <{name}>" if name else ""))

    lo = hi = None
    if args.r:
        lo = int(args.r[0], 16)
        hi = int(args.r[1], 16)

    hits = []
    for o in reloc_map(pe).get(target, []):
        if lo is not None and not (lo <= o < hi):
            continue
        hits.append((o, "reloc", ""))
    for o, kind, mn in branch_refs(pe, target, lo, hi):
        hits.append((o, kind, mn))
    if not args.no_raw:
        needle = struct.pack("<I", target)
        known = {h[0] for h in hits}
        p = pe.data.find(needle, lo or 0, hi or len(pe.data))
        while p >= 0:
            if p not in known:
                hits.append((p, "raw", ""))
            p = pe.data.find(needle, p + 1, hi or len(pe.data))

    hits.sort()
    n = 0
    for off, kind, mn in hits:
        sec = None
        for s in pe.sections:
            if s.rawsize and s.rawptr <= off < s.rawptr + s.rawsize:
                sec = s
        if args.code and (sec is None or not sec.is_code):
            continue
        va = pe.off_to_va(off)
        sname = sec.name if sec else "?"
        lname = lab.name(va) if va else None
        print(f"  0x{off:06X}  va=0x{va:08X}  {sname:<7} {kind:<6} {mn}"
              + (f"   <{lname}>" if lname else ""))
        if args.c and sec and sec.is_code:
            for line in context(pe, lab, off, args.c):
                print(line)
        n += 1
    print(f"-- {n} references")
    return 0


if __name__ == "__main__":
    sys.exit(main())
