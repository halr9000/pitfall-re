#!/usr/bin/env python3
"""Decode the animation-script blocks (blocks 1-4 of each level .PH).

Block layout:
    +0x00  u16[NSLOTS]   big-endian offsets, block-relative; 0 = empty slot
    ...    scripts

NSLOTS is derived from the first non-zero offset: the table runs right up to the
first script, so NSLOTS = min(offset) / 2. The offsets are **big-endian**, which
is unusual on x86 but is what the data says.

Script encoding, read straight off the interpreter `anim_advance`
(0x00401DBC, 7 callers):

    inc  byte [esi+0x29]          ; tick++
    cmp  byte [esi+0x29], [esi+0x28]
    jb   ret                      ; hold the current frame for [esi+0x28] ticks
    mov  byte [esi+0x29], 0
  next:
    inc  dword [esi+0x14]         ; advance the script pointer
    movzx eax, byte [ebx]
    cmp  al, 0xF0 -> loop: [esi+0x14] = [esi+0x18]   (rewind to script start)
    cmp  al, 0xFE -> read the next byte as an argument, put it in 0x00460180
                     and call 0x004261B0, then continue at `next`
    mov  [esi+0x0C], eax          ; anything else IS the frame index
    ret

So a script is a **flat byte stream**, not command/operand pairs:

    < 0xF0    a frame index; displayed for [esi+0x28] ticks
    0xFE arg  a one-argument side-effect call, does not consume a frame slot
    0xF0      loop back to the start of the script
    0xFF      end (used as the terminator throughout the data)

The per-frame hold time lives in the entity, not in the script.

Entity fields this pins down:
    +0x0C  current frame index      +0x14  script pointer
    +0x18  script start (for loop)  +0x28  ticks per frame
    +0x29  tick counter

    python3 tools/anim.py LEVEL13.PH 2        # one block
    python3 tools/anim.py --scan              # validate every block
    python3 tools/anim.py --opcodes           # frame/command statistics
"""
import argparse
import struct
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ph_dump import blocks, is_layer  # noqa: E402
from sprite import is_bank  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GAME = ROOT / "game"

END = 0xFF


class BadScript(Exception):
    pass


def is_script_block(data, off, size):
    """Blocks 1-4 that are neither a layer nor a sprite bank."""
    return size >= 8 and not is_layer(data, off, size) and not is_bank(data, off, size)


def parse(data, off, size):
    offs_be = []
    # find the table length: scan u16 BE until we hit the first script
    first = None
    i = 0
    while i + 2 <= size:
        v, = struct.unpack_from(">H", data, off + i)
        if v:
            if first is None:
                first = v
            if i >= first:
                break
        offs_be.append(v)
        i += 2
    if first is None:
        raise BadScript("no non-zero slot")
    nslots = first // 2
    if nslots == 0 or nslots * 2 > size:
        raise BadScript(f"table of {nslots} slots does not fit")
    slots = list(struct.unpack_from(">%dH" % nslots, data, off))

    scripts = {}
    for idx, o in enumerate(slots):
        if o == 0:
            continue
        if not (first <= o < size):
            raise BadScript(f"slot {idx} offset {o} out of range")
        p = off + o
        end = off + size
        ops = []          # ('frame', n) | ('call', arg) | ('loop',) | ('end',)
        while p < end:
            b = data[p]
            if b == 0xFF:
                ops.append(("end",))
                p += 1
                break
            if b == 0xF0:
                ops.append(("loop",))
                p += 1
                break
            if b == 0xFE:
                if p + 1 >= end:
                    raise BadScript(f"slot {idx}: 0xFE argument runs off the end")
                ops.append(("call", data[p + 1]))
                p += 2
                continue
            ops.append(("frame", b))
            p += 1
        else:
            raise BadScript(f"slot {idx} unterminated")
        scripts[idx] = dict(offset=o, ops=ops, end=p - off)
    return dict(nslots=nslots, slots=slots, scripts=scripts, size=size)


def coverage(par):
    """Do the scripts tile the region after the table with no gaps?"""
    if not par["scripts"]:
        return None
    spans = sorted((s["offset"], s["end"]) for s in par["scripts"].values())
    start = par["nslots"] * 2
    holes = []
    cur = spans[0][0]
    if cur != start:
        holes.append((start, cur))
    for a, b in spans:
        if a > cur:
            holes.append((cur, a))
        cur = max(cur, b)
    if cur != par["size"]:
        holes.append((cur, par["size"]))
    return holes


def show(path, blk):
    data = path.read_bytes()
    for i, _h, p, s in blocks(data):
        if i != blk:
            continue
        par = parse(data, p, s)
        print(f"{path.name} block {i}: {s} bytes, {par['nslots']} slots, "
              f"{len(par['scripts'])} used")
        holes = coverage(par)
        print(f"  unaccounted byte ranges: {holes if holes else 'none'}")
        for idx, sc in sorted(par["scripts"].items()):
            body = " ".join(
                f"f{o[1]}" if o[0] == "frame" else
                f"call(0x{o[1]:02X})" if o[0] == "call" else
                o[0].upper() for o in sc["ops"])
            print(f"  slot {idx:>3} @0x{sc['offset']:04X}  {body}")
        return 0
    print(f"block {blk} not found")
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("block", nargs="?", type=int)
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--opcodes", action="store_true")
    args = ap.parse_args()

    if args.scan or args.opcodes:
        ok = bad = clean = 0
        cmds = Counter()
        operands = {}
        for f in sorted(GAME.glob("LEVEL*.PH")):
            data = f.read_bytes()
            for i, _h, p, s in blocks(data):
                if i == 0 or i > 4 or not is_script_block(data, p, s):
                    continue
                try:
                    par = parse(data, p, s)
                except BadScript as e:
                    if args.scan:
                        print(f"  {f.name} block {i}: {e}")
                    bad += 1
                    continue
                ok += 1
                if not coverage(par):
                    clean += 1
                for sc in par["scripts"].values():
                    for o in sc["ops"]:
                        cmds[o[0]] += 1
                        if o[0] in ("frame", "call"):
                            operands.setdefault(o[0], set()).add(o[1])
        if args.scan:
            print(f"-- {ok} script blocks parsed, {bad} failed, "
                  f"{clean} tile their block with no gaps")
        if args.opcodes:
            print(f"{'op':>8} {'count':>8}  {'distinct':>9}  range")
            for c, n in cmds.most_common():
                vals = sorted(operands.get(c, []))
                rng = (f"0x{vals[0]:02X}..0x{vals[-1]:02X}" if vals else "-")
                print(f"{c:>8} {n:>8}  {len(vals):>9}  {rng}")
        return 0

    if not args.file:
        ap.error("give a .PH file and block, or --scan / --opcodes")
    path = Path(args.file)
    if not path.exists():
        path = GAME / args.file
    if args.block is None:
        data = path.read_bytes()
        for i, _h, p, s in blocks(data):
            if i and i <= 4 and is_script_block(data, p, s):
                try:
                    par = parse(data, p, s)
                    print(f"  block {i}: {s}B, {par['nslots']} slots, "
                          f"{len(par['scripts'])} used, gaps "
                          f"{coverage(par) or 'none'}")
                except BadScript as e:
                    print(f"  block {i}: {s}B, FAILED: {e}")
        return 0
    return show(path, args.block)


if __name__ == "__main__":
    sys.exit(main())
