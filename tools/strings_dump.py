#!/usr/bin/env python3
"""String scanner with grep filter and range restriction.

Usage:
    python3 tools/strings_dump.py [file] [-n MIN] [-g PATTERN] [-r START END] [--rva]

Default file is game/PITFALL.EXE. Offsets are file offsets; --rva also prints the
virtual address (image base + RVA) using the PE section table.
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pe_map import load_pe  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BIN = ROOT / "game" / "PITFALL.EXE"

PRINTABLE = re.compile(rb"[\x20-\x7e\t]{%d,}")


def num(s):
    return int(s, 16) if s.lower().startswith("0x") else int(s, 10)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=str(DEFAULT_BIN))
    ap.add_argument("-n", type=int, default=5, help="minimum length")
    ap.add_argument("-g", metavar="PATTERN", help="regex filter (case-insensitive)")
    ap.add_argument("-r", nargs=2, metavar=("START", "END"), help="restrict to file range")
    ap.add_argument("--rva", action="store_true", help="also show virtual address")
    args = ap.parse_args()

    data = Path(args.path).read_bytes()
    lo, hi = 0, len(data)
    if args.r:
        lo, hi = num(args.r[0]), num(args.r[1])

    pe = load_pe(Path(args.path)) if args.rva else None
    filt = re.compile(args.g, re.I) if args.g else None

    rx = re.compile(rb"[\x20-\x7e\t]{%d,}" % args.n)
    n = 0
    for m in rx.finditer(data, lo, hi):
        s = m.group().decode("latin-1")
        if filt and not filt.search(s):
            continue
        off = m.start()
        if pe:
            va = pe.off_to_va(off)
            va_s = f" va=0x{va:08X}" if va else " va=-"
        else:
            va_s = ""
        print(f"0x{off:06X}{va_s}  {s}")
        n += 1
    print(f"-- {n} strings", file=sys.stderr)


if __name__ == "__main__":
    main()
