#!/usr/bin/env python3
"""Targeted disassembler for PITFALL.EXE (i386 PE).

Usage:
    python3 tools/dis.py <addr> [count]        # count instructions (default 40)
    python3 tools/dis.py <addr> --func         # follow until ret / unconditional exit
    python3 tools/dis.py <addr> --bytes N      # disassemble N bytes
    python3 tools/dis.py <addr> --raw          # no label annotation

<addr> is a virtual address (0x0044A8FF) or a file offset (off:0x4A8FF).
Labels from labels.csv are shown inline for branch targets, call targets and
absolute memory operands, and appended as trailing comments.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import instruction_set as isa  # noqa: E402
from labels import load_labels  # noqa: E402
from pe_map import load_pe  # noqa: E402


def fmt_target(pe, lab, va, raw):
    if raw:
        return f"0x{va:08X}"
    n = lab.name(va)
    if n:
        return f"0x{va:08X} <{n}>"
    return f"0x{va:08X}"


def annotate_line(pe, lab, ins, raw):
    """Return (text, trailing_comment)."""
    text = ins.text
    notes = []
    if ins.target is not None and not raw:
        n = lab.name(ins.target)
        if n:
            text = text.replace(f"0x{ins.target:X}", f"{n}")
            notes.append(f"0x{ins.target:08X}")
        c = lab.comment(ins.target)
        if c:
            notes.append(c)
    if ins.mem_target is not None and not raw:
        e = lab.get(ins.mem_target)
        if e:
            notes.append(f"{e[0]}" + (f" — {e[1]}" if e[1] else ""))
        else:
            sec = pe.section_of_va(ins.mem_target)
            if sec:
                notes.append(f"[{sec.name}]")
            # inline a small string if the target looks like text
            off = pe.va_to_off(ins.mem_target)
            if off is not None:
                blob = pe.data[off:off + 40]
                end = blob.find(b"\0")
                if 3 < end < 40 and all(32 <= c < 127 for c in blob[:end]):
                    notes.append(repr(blob[:end].decode("latin-1")))
    if ins.imm is not None and pe.is_valid_va(ins.imm) and ins.imm >= pe.imagebase and not raw:
        e = lab.get(ins.imm)
        if e:
            notes.append(f"imm-> {e[0]}")
        else:
            off = pe.va_to_off(ins.imm)
            if off is not None:
                blob = pe.data[off:off + 40]
                end = blob.find(b"\0")
                if 3 < end < 40 and all(32 <= c < 127 for c in blob[:end]):
                    notes.append("imm-> " + repr(blob[:end].decode("latin-1")))
    return text, "  ; " + " ".join(notes) if notes else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("addr")
    ap.add_argument("count", nargs="?", type=int, default=40)
    ap.add_argument("--bytes", type=int, default=None, dest="nbytes")
    ap.add_argument("--func", action="store_true", help="stop at the function's ret")
    ap.add_argument("--raw", action="store_true", help="no label annotation")
    ap.add_argument("--bin", default=None)
    args = ap.parse_args()

    pe = load_pe(Path(args.bin)) if args.bin else load_pe()
    lab = load_labels()
    off, va = pe.resolve(args.addr)
    if off is None:
        print(f"address {args.addr} is not mapped to file data")
        return 1

    data = pe.data
    end = off + (args.nbytes if args.nbytes else 1 << 30)
    n = 0
    limit = args.count if not args.nbytes and not args.func else 100000
    seen_ret = False
    p, pva = off, va
    while n < limit and p < end and p < len(data) and not seen_ret:
        e = lab.get(pva)
        if e and n:
            print(f"\n{e[0]}:" + (f"   ; {e[1]}" if e[1] else ""))
        elif e:
            print(f"{e[0]}:" + (f"   ; {e[1]}" if e[1] else ""))
        ins = isa.decode(data, p, pva)
        text, note = annotate_line(pe, lab, ins, args.raw)
        raw_hex = ins.raw.hex(" ") if ins.raw else f"{data[p]:02x}"
        print(f"0x{pva:08X}  {raw_hex:<21} {text}{note}")
        if args.func and (ins.is_ret or (ins.mnemonic == "jmp" and ins.target is None)):
            seen_ret = True
        p += ins.length
        pva += ins.length
        n += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
