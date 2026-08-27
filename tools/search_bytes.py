#!/usr/bin/env python3
"""Byte-pattern search over PITFALL.EXE (or any file with --bin).

    python3 tools/search_bytes.py "8b 0d ?? ?? 45 00" [--context N] [--disasm [N]]
    python3 tools/search_bytes.py 682c114700 --disasm 6

`??` is a wildcard nibble-pair. Spaces are optional. Hits inside code sections
can be disassembled inline; hits elsewhere are shown as hex + ASCII context.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import instruction_set as isa  # noqa: E402
from labels import load_labels  # noqa: E402
from pe_map import load_pe  # noqa: E402


def pattern_to_regex(spec):
    toks = spec.replace(",", " ").split()
    if len(toks) == 1 and len(toks[0]) > 2:
        s = toks[0]
        toks = [s[i:i + 2] for i in range(0, len(s), 2)]
    out = b""
    for t in toks:
        if t in ("??", "**"):
            out += b"."
        else:
            out += re.escape(bytes([int(t, 16)]))
    return re.compile(out, re.S)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pattern")
    ap.add_argument("--context", type=int, default=0, metavar="N")
    ap.add_argument("--disasm", nargs="?", type=int, const=6, default=None,
                    metavar="N", help="disassemble N instructions at each code hit")
    ap.add_argument("--bin")
    ap.add_argument("-r", nargs=2, metavar=("START", "END"))
    ap.add_argument("--max", type=int, default=200)
    args = ap.parse_args()

    if args.bin:
        data = Path(args.bin).read_bytes()
        pe = lab = None
    else:
        pe = load_pe()
        lab = load_labels()
        data = pe.data

    lo = int(args.r[0], 16) if args.r else 0
    hi = int(args.r[1], 16) if args.r else len(data)
    rx = pattern_to_regex(args.pattern)

    n = 0
    for m in rx.finditer(data, lo, hi):
        off = m.start()
        va = pe.off_to_va(off) if pe else None
        sec = None
        if pe:
            for s in pe.sections:
                if s.rawsize and s.rawptr <= off < s.rawptr + s.rawsize:
                    sec = s
        head = f"0x{off:06X}"
        if va:
            head += f"  va=0x{va:08X}"
        if sec:
            head += f"  {sec.name}"
        nm = lab.name(va) if (lab and va) else None
        if nm:
            head += f"  <{nm}>"
        print(head)
        if args.disasm and sec and sec.is_code:
            p, pva = off, va
            for _ in range(args.disasm):
                ins = isa.decode(data, p, pva)
                print(f"    0x{pva:08X}  {ins.raw.hex(' '):<20} {ins.text}")
                p += ins.length
                pva += ins.length
        elif args.context:
            c = args.context
            blob = data[max(0, off - c):off + c + (m.end() - m.start())]
            print("    " + blob.hex(" "))
            print("    " + "".join(chr(b) if 32 <= b < 127 else "." for b in blob))
        n += 1
        if n >= args.max:
            print(f"    ... stopped at {args.max} hits")
            break
    print(f"-- {n} hits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
