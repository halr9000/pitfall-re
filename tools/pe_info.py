#!/usr/bin/env python3
"""Ph1 — identify a DOS/Windows executable: MZ stub, NE or PE header, sections,
data directories, imports.

Usage:
    python3 tools/pe_info.py [path/to/file.exe] [--imports] [--dirs]

Defaults to the project binary (game/PITFALL.EXE).
"""
import argparse
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BIN = ROOT / "game" / "PITFALL.EXE"

MACHINE = {
    0x014C: "i386",
    0x0162: "MIPS R3000",
    0x0166: "MIPS R4000",
    0x0184: "Alpha AXP",
    0x01C0: "ARM",
    0x01F0: "PowerPC",
    0x8664: "x86-64",
}

SUBSYS = {
    0: "unknown", 1: "native", 2: "Windows GUI", 3: "Windows CUI",
    5: "OS/2 CUI", 7: "POSIX CUI",
}

SECTION_FLAGS = [
    (0x00000020, "CODE"),
    (0x00000040, "INIT_DATA"),
    (0x00000080, "UNINIT_DATA"),
    (0x02000000, "DISCARDABLE"),
    (0x10000000, "SHARED"),
    (0x20000000, "EXEC"),
    (0x40000000, "READ"),
    (0x80000000, "WRITE"),
]

DIR_NAMES = [
    "Export", "Import", "Resource", "Exception", "Certificate", "BaseReloc",
    "Debug", "Architecture", "GlobalPtr", "TLS", "LoadConfig", "BoundImport",
    "IAT", "DelayImport", "CLRRuntime", "Reserved",
]


def flag_names(ch):
    return "|".join(name for bit, name in SECTION_FLAGS if ch & bit)


def rva_to_off(rva, sections):
    for s in sections:
        if s["vaddr"] <= rva < s["vaddr"] + max(s["vsize"], s["rawsize"]):
            return s["rawptr"] + (rva - s["vaddr"])
    return None


def cstr(data, off, limit=256):
    end = data.find(b"\0", off, off + limit)
    if end < 0:
        end = off + limit
    return data[off:end].decode("latin-1")


def dump_mz(data):
    (e_magic, e_cblp, e_cp, e_crlc, e_cparhdr, e_minalloc, e_maxalloc,
     e_ss, e_sp, e_csum, e_ip, e_cs, e_lfarlc, e_ovno) = struct.unpack_from("<14H", data, 0)
    print("== MZ header ==")
    print(f"  magic            {data[0:2].decode('latin-1')}")
    print(f"  pages/last-page  {e_cp} x 512, last {e_cblp}  -> load image {(e_cp - 1) * 512 + (e_cblp or 512)} bytes")
    print(f"  header paras     {e_cparhdr}  (header size 0x{e_cparhdr * 16:X})")
    print(f"  relocations      {e_crlc} at 0x{e_lfarlc:X}")
    print(f"  entry (CS:IP)    {e_cs:04X}:{e_ip:04X}")
    print(f"  stack (SS:SP)    {e_ss:04X}:{e_sp:04X}")
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0] if len(data) >= 0x40 else 0
    print(f"  e_lfanew         0x{e_lfanew:X}")
    stub = data[0x40:0x200]
    msgs = [m.decode("latin-1") for m in stub.split(b"\0") if len(m) > 8 and all(32 <= c < 127 or c in (13, 10) for c in m)]
    for m in msgs[:4]:
        print(f"  stub string      {m.strip()!r}")
    return e_lfanew


def dump_ne(data, off):
    print("== NE header (16-bit Windows) ==")
    ver, rev = data[off + 2], data[off + 3]
    entry_off, entry_len = struct.unpack_from("<HH", data, off + 4)
    flags = struct.unpack_from("<H", data, off + 0x0C)[0]
    nsegs, nmods, nonres_len = struct.unpack_from("<HHH", data, off + 0x1C)
    seg_tab, res_tab, resident_tab, mod_tab, imp_tab = struct.unpack_from("<HHHHH", data, off + 0x22)
    csip = struct.unpack_from("<I", data, off + 0x14)[0]
    sssp = struct.unpack_from("<I", data, off + 0x18)[0]
    align = struct.unpack_from("<H", data, off + 0x32)[0]
    exetype = data[off + 0x36]
    print(f"  linker           {ver}.{rev}")
    print(f"  flags            0x{flags:04X}")
    print(f"  entry CS:IP      {csip >> 16:04X}:{csip & 0xFFFF:04X}")
    print(f"  stack SS:SP      {sssp >> 16:04X}:{sssp & 0xFFFF:04X}")
    print(f"  segments         {nsegs}  (table @ 0x{off + seg_tab:X}, align shift {align})")
    print(f"  module refs      {nmods}")
    print(f"  target OS        0x{exetype:02X}")
    shift = align or 9
    print("  idx  sector    file-off   size     minalloc  flags")
    for i in range(nsegs):
        so = off + seg_tab + i * 8
        sector, slen, sflags, minalloc = struct.unpack_from("<HHHH", data, so)
        print(f"  {i + 1:3d}  0x{sector:04X}    0x{sector << shift:08X} 0x{slen or 65536:05X}  0x{minalloc or 65536:05X}   0x{sflags:04X}"
              f" {'DATA' if sflags & 1 else 'CODE'}")
    # module reference table -> imported DLL names
    names = []
    for i in range(nmods):
        noff = struct.unpack_from("<H", data, off + mod_tab + i * 2)[0]
        p = off + imp_tab + noff
        ln = data[p]
        names.append(data[p + 1:p + 1 + ln].decode("latin-1"))
    print(f"  imports          {', '.join(names)}")


def dump_pe(data, off, show_imports, show_dirs):
    machine, nsec, tstamp, symptr, nsym, optsize, chars = struct.unpack_from("<HHIIIHH", data, off + 4)
    print("== PE header (32-bit Windows) ==")
    print(f"  machine          0x{machine:04X} ({MACHINE.get(machine, '?')})")
    print(f"  sections         {nsec}")
    print(f"  timestamp        {tstamp} (0x{tstamp:08X})")
    print(f"  characteristics  0x{chars:04X}")
    opt = off + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    lmaj, lmin = data[opt + 2], data[opt + 3]
    (codesz, initsz, uninitsz, entry, codebase, database) = struct.unpack_from("<6I", data, opt + 4)
    imagebase, secalign, filealign = struct.unpack_from("<3I", data, opt + 28)
    subsys = struct.unpack_from("<H", data, opt + 68)[0]
    imagesz, hdrsz = struct.unpack_from("<II", data, opt + 56)
    ndirs = struct.unpack_from("<I", data, opt + 92)[0]
    print(f"  opt magic        0x{magic:04X} ({'PE32' if magic == 0x10B else 'PE32+' if magic == 0x20B else '?'})")
    print(f"  linker           {lmaj}.{lmin}")
    print(f"  entry RVA        0x{entry:X}")
    print(f"  image base       0x{imagebase:X}   -> entry VA 0x{imagebase + entry:X}")
    print(f"  code base        0x{codebase:X}   data base 0x{database:X}")
    print(f"  sizeof code      0x{codesz:X}  init data 0x{initsz:X}  uninit 0x{uninitsz:X}")
    print(f"  section align    0x{secalign:X}  file align 0x{filealign:X}")
    print(f"  image size       0x{imagesz:X}  headers 0x{hdrsz:X}")
    print(f"  subsystem        {subsys} ({SUBSYS.get(subsys, '?')})")

    dirs = []
    for i in range(ndirs):
        rva, size = struct.unpack_from("<II", data, opt + 96 + i * 8)
        dirs.append((rva, size))

    sec_off = opt + optsize
    sections = []
    print("\n== Sections ==")
    print("  name      vaddr      vsize      rawptr     rawsize    flags")
    for i in range(nsec):
        so = sec_off + i * 40
        name = data[so:so + 8].rstrip(b"\0").decode("latin-1")
        vsize, vaddr, rawsize, rawptr = struct.unpack_from("<4I", data, so + 8)
        ch = struct.unpack_from("<I", data, so + 36)[0]
        sections.append(dict(name=name, vaddr=vaddr, vsize=vsize, rawptr=rawptr, rawsize=rawsize, chars=ch))
        print(f"  {name:<9} 0x{vaddr:08X} 0x{vsize:08X} 0x{rawptr:08X} 0x{rawsize:08X} {flag_names(ch)}")

    if show_dirs:
        print("\n== Data directories ==")
        for i, (rva, size) in enumerate(dirs):
            if rva or size:
                fo = rva_to_off(rva, sections)
                fo_s = f"0x{fo:X}" if fo is not None else "-"
                print(f"  {DIR_NAMES[i] if i < len(DIR_NAMES) else i:<14} rva 0x{rva:08X} size 0x{size:06X} file {fo_s}")

    if show_imports and dirs[1][0]:
        print("\n== Imports ==")
        it = rva_to_off(dirs[1][0], sections)
        n = 0
        while True:
            desc = data[it + n * 20: it + n * 20 + 20]
            if len(desc) < 20 or desc == b"\0" * 20:
                break
            olt, _, _, namerva, firstthunk = struct.unpack("<5I", desc)
            dll = cstr(data, rva_to_off(namerva, sections))
            thunk_rva = olt or firstthunk
            names = []
            t = rva_to_off(thunk_rva, sections)
            while True:
                val = struct.unpack_from("<I", data, t)[0]
                if val == 0:
                    break
                if val & 0x80000000:
                    names.append(f"#{val & 0xFFFF}")
                else:
                    ho = rva_to_off(val & 0x7FFFFFFF, sections)
                    names.append(cstr(data, ho + 2))
                t += 4
            print(f"  {dll} ({len(names)})")
            print("    " + ", ".join(names[:24]) + (" ..." if len(names) > 24 else ""))
            n += 1
    return sections


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=str(DEFAULT_BIN))
    ap.add_argument("--imports", action="store_true")
    ap.add_argument("--dirs", action="store_true")
    args = ap.parse_args()

    data = Path(args.path).read_bytes()
    print(f"file   {args.path}")
    print(f"size   {len(data)} bytes (0x{len(data):X})")
    print(f"magic  {data[:2]!r}\n")

    if data[:2] != b"MZ":
        print("not an MZ executable")
        return 1
    lfanew = dump_mz(data)
    if lfanew and lfanew + 4 <= len(data):
        sig = data[lfanew:lfanew + 2]
        print()
        if sig == b"PE":
            dump_pe(data, lfanew, args.imports, args.dirs)
        elif sig == b"NE":
            dump_ne(data, lfanew)
        elif sig == b"LE" or sig == b"LX":
            print(f"== {sig.decode()} header (linear executable) at 0x{lfanew:X} ==")
        else:
            print(f"unknown extended header signature {sig!r} at 0x{lfanew:X}")
    else:
        print("\npure DOS MZ executable (no extended header)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
