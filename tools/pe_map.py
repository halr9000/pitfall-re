#!/usr/bin/env python3
"""Shared PE section map: virtual address <-> file offset conversion.

Every disassembly tool imports this so addresses can be given either as a file
offset (0x1234) or as a virtual address (va:0x401234 / 0x401234 when it falls in
the image range).
"""
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BIN = ROOT / "game" / "PITFALL.EXE"


class Section:
    __slots__ = ("name", "vaddr", "vsize", "rawptr", "rawsize", "chars")

    def __init__(self, name, vaddr, vsize, rawptr, rawsize, chars):
        self.name = name
        self.vaddr = vaddr
        self.vsize = vsize
        self.rawptr = rawptr
        self.rawsize = rawsize
        self.chars = chars

    @property
    def is_code(self):
        return bool(self.chars & 0x20)

    def __repr__(self):
        return f"<{self.name} va=0x{self.vaddr:X} raw=0x{self.rawptr:X}>"


class PE:
    def __init__(self, path=DEFAULT_BIN):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        d = self.data
        lfanew = struct.unpack_from("<I", d, 0x3C)[0]
        assert d[lfanew:lfanew + 2] == b"PE", "not a PE file"
        nsec, = struct.unpack_from("<H", d, lfanew + 6)
        optsize, = struct.unpack_from("<H", d, lfanew + 20)
        opt = lfanew + 24
        self.entry_rva, = struct.unpack_from("<I", d, opt + 16)
        self.imagebase, = struct.unpack_from("<I", d, opt + 28)
        self.sections = []
        sec_off = opt + optsize
        for i in range(nsec):
            so = sec_off + i * 40
            name = d[so:so + 8].rstrip(b"\0").decode("latin-1")
            vsize, vaddr, rawsize, rawptr = struct.unpack_from("<4I", d, so + 8)
            chars, = struct.unpack_from("<I", d, so + 36)
            self.sections.append(Section(name, vaddr, vsize, rawptr, rawsize, chars))
        self.entry_off = self.rva_to_off(self.entry_rva)

    # ---- conversions -------------------------------------------------
    def rva_to_off(self, rva):
        for s in self.sections:
            if s.rawsize and s.vaddr <= rva < s.vaddr + max(s.vsize, s.rawsize):
                o = s.rawptr + (rva - s.vaddr)
                if o < len(self.data):
                    return o
        return None

    def va_to_off(self, va):
        return self.rva_to_off(va - self.imagebase)

    def off_to_rva(self, off):
        for s in self.sections:
            if s.rawsize and s.rawptr <= off < s.rawptr + s.rawsize:
                return s.vaddr + (off - s.rawptr)
        return None

    def off_to_va(self, off):
        rva = self.off_to_rva(off)
        return None if rva is None else self.imagebase + rva

    def section_of_va(self, va):
        rva = va - self.imagebase
        for s in self.sections:
            if s.vaddr <= rva < s.vaddr + max(s.vsize, s.rawsize):
                return s
        return None

    def is_valid_va(self, va):
        return self.section_of_va(va) is not None

    def resolve(self, spec):
        """Accept '0x401234', 'va:0x401234', 'off:0x1234' -> (file_offset, va)."""
        if isinstance(spec, str):
            spec = spec.strip()
            if spec.startswith("va:"):
                va = int(spec[3:], 16)
                return self.va_to_off(va), va
            if spec.startswith("off:"):
                off = int(spec[4:], 16)
                return off, self.off_to_va(off)
            n = int(spec, 16) if spec.lower().startswith("0x") else int(spec, 16)
        else:
            n = spec
        # heuristic: inside the mapped image -> treat as VA
        if self.imagebase <= n < self.imagebase + 0x1000000 and self.is_valid_va(n):
            return self.va_to_off(n), n
        return n, self.off_to_va(n)


_cache = {}


def load_pe(path=DEFAULT_BIN):
    key = str(path)
    if key not in _cache:
        _cache[key] = PE(path)
    return _cache[key]
