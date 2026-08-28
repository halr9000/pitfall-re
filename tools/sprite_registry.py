#!/usr/bin/env python3
"""Extract the sprite registry: every LoadSprite(name, &dest) call site.

The shipping build contains hundreds of generated call sites of the form

    push <dest global>          ; &<name>_s
    push <name string>
    call LoadSprite             ; 0x004453A0
    add  esp, 8

which is precisely the code the level editor emits, per the debug string
`LoadSprite("%s",&%s_s);\\t\\t//Level %d` at 0x0046FA88. Each pair binds a named
sprite bank to the global that the rest of the engine reads it from, so this
table is the sprite-name -> bank-pointer-slot mapping.

    python3 tools/sprite_registry.py                # the whole table
    python3 tools/sprite_registry.py -g harry       # filter by name
    python3 tools/sprite_registry.py --by-global    # sort by destination
"""
import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from labels import load_labels  # noqa: E402
from pe_map import load_pe  # noqa: E402

LOADSPRITE = 0x004453A0
PUSH_IMM32 = 0x68
CALL_REL32 = 0xE8


def cstring(pe, va, limit=64):
    off = pe.va_to_off(va)
    if off is None:
        return None
    blob = pe.data[off:off + limit]
    end = blob.find(b"\0")
    if end < 0:
        return None
    s = blob[:end].decode("latin-1")
    return s if s and all(32 <= ord(c) < 127 for c in s) else None


def scan(pe, target=LOADSPRITE):
    """Yield (call_va, name, name_va, dest_va)."""
    d = pe.data
    for s in pe.sections:
        if not s.is_code or not s.rawsize:
            continue
        lo, hi = s.rawptr, s.rawptr + s.rawsize
        p = lo
        while p < hi - 15:
            # push imm32 ; push imm32 ; call rel32
            if d[p] == PUSH_IMM32 and d[p + 5] == PUSH_IMM32 and d[p + 10] == CALL_REL32:
                dest = struct.unpack_from("<I", d, p + 1)[0]
                name_va = struct.unpack_from("<I", d, p + 6)[0]
                rel = struct.unpack_from("<i", d, p + 11)[0]
                va = pe.off_to_va(p)
                if va is not None and (va + 15 + rel) & 0xFFFFFFFF == target:
                    nm = cstring(pe, name_va)
                    if nm:
                        yield va, nm, name_va, dest
                    p += 15
                    continue
            p += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-g", metavar="SUBSTR", help="filter names by substring")
    ap.add_argument("--by-global", action="store_true")
    ap.add_argument("--target", default=hex(LOADSPRITE))
    args = ap.parse_args()

    pe = load_pe()
    lab = load_labels()
    rows = list(scan(pe, int(args.target, 16)))
    if args.g:
        rows = [r for r in rows if args.g.lower() in r[1].lower()]
    rows.sort(key=(lambda r: r[3]) if args.by_global else (lambda r: r[1]))

    print(f"{'name':<14} {'dest global':<12} {'name str':<12} call site")
    for va, nm, nva, dest in rows:
        lname = lab.name(dest)
        print(f"{nm:<14} 0x{dest:08X}   0x{nva:08X}   0x{va:08X}"
              + (f"  <{lname}>" if lname else ""))
    print(f"-- {len(rows)} sprite bindings")

    if not args.g:
        dests = {r[3] for r in rows}
        names = {r[1] for r in rows}
        print(f"   {len(names)} distinct names, {len(dests)} distinct destination globals")
    return 0


if __name__ == "__main__":
    sys.exit(main())
