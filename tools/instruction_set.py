#!/usr/bin/env python3
"""x86 (i386, 32-bit protected mode) instruction decoder.

Built from scratch for this project — no third-party disassemblers.
Covers the integer instruction set a 1995 Watcom/MSC compiler emits, plus the
x87 FPU escape opcodes (D8-DF), string ops, and the common 0F two-byte space
(setcc, jcc rel32, movzx/movsx, bit ops, imul, bswap, cmovcc).

Public API:
    decode(data, off, va=None, bits=32) -> Insn
    Insn.length, .mnemonic, .ops (list of str), .text, .target, .mem_target,
        .imm, .is_call, .is_jump, .is_ret, .stops_flow

Operand specifier language (subset of the Intel/objdump convention):
    Eb/Ew/Ev  modrm r/m, byte / word / opsize
    Gb/Gw/Gv  modrm reg field
    Ib/Iw/Iz  immediate byte / word / opsize (sign-extended forms: Ibs)
    Jb/Jz     relative branch displacement
    Ob/Ov     moffs (absolute address, no modrm)
    Sw        segment register (modrm reg)
    M         memory-only modrm
    Cd/Dd     control / debug register
    eAX..eDI  fixed register, opsize-dependent
    AL..BH    fixed byte register
    1         literal 1
    Xb/Xv     ds:esi string source     Yb/Yv  es:edi string dest
"""

REG8 = ("al", "cl", "dl", "bl", "ah", "ch", "dh", "bh")
REG16 = ("ax", "cx", "dx", "bx", "sp", "bp", "si", "di")
REG32 = ("eax", "ecx", "edx", "ebx", "esp", "ebp", "esi", "edi")
SREG = ("es", "cs", "ss", "ds", "fs", "gs", "?s6", "?s7")

CC = ("o", "no", "b", "ae", "e", "ne", "be", "a",
      "s", "ns", "p", "np", "l", "ge", "le", "g")

SEG_PREFIX = {0x2E: "cs", 0x36: "ss", 0x3E: "ds", 0x26: "es", 0x64: "fs", 0x65: "gs"}

# ---------------------------------------------------------------- tables ---
# opcode -> (mnemonic, operand-spec tuple)
ONE = {}


def _fill_arith():
    for i, name in enumerate(("add", "or", "adc", "sbb", "and", "sub", "xor", "cmp")):
        b = i * 8
        ONE[b + 0] = (name, ("Eb", "Gb"))
        ONE[b + 1] = (name, ("Ev", "Gv"))
        ONE[b + 2] = (name, ("Gb", "Eb"))
        ONE[b + 3] = (name, ("Gv", "Ev"))
        ONE[b + 4] = (name, ("AL", "Ib"))
        ONE[b + 5] = (name, ("eAX", "Iz"))


_fill_arith()

for _i in range(8):
    ONE[0x40 + _i] = ("inc", ("eR%d" % _i,))
    ONE[0x48 + _i] = ("dec", ("eR%d" % _i,))
    ONE[0x50 + _i] = ("push", ("eR%d" % _i,))
    ONE[0x58 + _i] = ("pop", ("eR%d" % _i,))
    ONE[0x90 + _i] = ("xchg", ("eAX", "eR%d" % _i))
    ONE[0xB0 + _i] = ("mov", ("R8_%d" % _i, "Ib"))
    ONE[0xB8 + _i] = ("mov", ("eR%d" % _i, "Iv"))

ONE[0x90] = ("nop", ())

ONE.update({
    0x06: ("push", ("es",)), 0x07: ("pop", ("es",)),
    0x0E: ("push", ("cs",)),
    0x16: ("push", ("ss",)), 0x17: ("pop", ("ss",)),
    0x1E: ("push", ("ds",)), 0x1F: ("pop", ("ds",)),
    0x27: ("daa", ()), 0x2F: ("das", ()), 0x37: ("aaa", ()), 0x3F: ("aas", ()),
    0x60: ("pushad", ()), 0x61: ("popad", ()),
    0x62: ("bound", ("Gv", "Ma")), 0x63: ("arpl", ("Ew", "Gw")),
    0x68: ("push", ("Iz",)), 0x69: ("imul", ("Gv", "Ev", "Iz")),
    0x6A: ("push", ("Ibs",)), 0x6B: ("imul", ("Gv", "Ev", "Ibs")),
    0x6C: ("insb", ()), 0x6D: ("insd", ()), 0x6E: ("outsb", ()), 0x6F: ("outsd", ()),
    0x84: ("test", ("Eb", "Gb")), 0x85: ("test", ("Ev", "Gv")),
    0x86: ("xchg", ("Eb", "Gb")), 0x87: ("xchg", ("Ev", "Gv")),
    0x88: ("mov", ("Eb", "Gb")), 0x89: ("mov", ("Ev", "Gv")),
    0x8A: ("mov", ("Gb", "Eb")), 0x8B: ("mov", ("Gv", "Ev")),
    0x8C: ("mov", ("Ew", "Sw")), 0x8D: ("lea", ("Gv", "M")),
    0x8E: ("mov", ("Sw", "Ew")),
    0x98: ("cwde", ()), 0x99: ("cdq", ()),
    0x9A: ("callf", ("Ap",)), 0x9B: ("wait", ()),
    0x9C: ("pushfd", ()), 0x9D: ("popfd", ()), 0x9E: ("sahf", ()), 0x9F: ("lahf", ()),
    0xA0: ("mov", ("AL", "Ob")), 0xA1: ("mov", ("eAX", "Ov")),
    0xA2: ("mov", ("Ob", "AL")), 0xA3: ("mov", ("Ov", "eAX")),
    0xA4: ("movsb", ()), 0xA5: ("movsd", ()),
    0xA6: ("cmpsb", ()), 0xA7: ("cmpsd", ()),
    0xA8: ("test", ("AL", "Ib")), 0xA9: ("test", ("eAX", "Iz")),
    0xAA: ("stosb", ()), 0xAB: ("stosd", ()),
    0xAC: ("lodsb", ()), 0xAD: ("lodsd", ()),
    0xAE: ("scasb", ()), 0xAF: ("scasd", ()),
    0xC2: ("ret", ("Iw",)), 0xC3: ("ret", ()),
    0xC4: ("les", ("Gv", "M")), 0xC5: ("lds", ("Gv", "M")),
    0xC8: ("enter", ("Iw", "Ib")), 0xC9: ("leave", ()),
    0xCA: ("retf", ("Iw",)), 0xCB: ("retf", ()),
    0xCC: ("int3", ()), 0xCD: ("int", ("Ib",)), 0xCE: ("into", ()), 0xCF: ("iretd", ()),
    0xD7: ("xlatb", ()),
    0xE0: ("loopne", ("Jb",)), 0xE1: ("loope", ("Jb",)),
    0xE2: ("loop", ("Jb",)), 0xE3: ("jecxz", ("Jb",)),
    0xE4: ("in", ("AL", "Ib")), 0xE5: ("in", ("eAX", "Ib")),
    0xE6: ("out", ("Ib", "AL")), 0xE7: ("out", ("Ib", "eAX")),
    0xE8: ("call", ("Jz",)), 0xE9: ("jmp", ("Jz",)),
    0xEA: ("jmpf", ("Ap",)), 0xEB: ("jmp", ("Jb",)),
    0xEC: ("in", ("AL", "dx")), 0xED: ("in", ("eAX", "dx")),
    0xEE: ("out", ("dx", "AL")), 0xEF: ("out", ("dx", "eAX")),
    0xF4: ("hlt", ()), 0xF5: ("cmc", ()),
    0xF8: ("clc", ()), 0xF9: ("stc", ()), 0xFA: ("cli", ()), 0xFB: ("sti", ()),
    0xFC: ("cld", ()), 0xFD: ("std", ()),
})

for _i in range(16):
    ONE[0x70 + _i] = ("j" + CC[_i], ("Jb",))

# --- group opcodes: opcode -> (list of 8 mnemonics, operand spec) ----------
GRP1 = ("add", "or", "adc", "sbb", "and", "sub", "xor", "cmp")
GRP2 = ("rol", "ror", "rcl", "rcr", "shl", "shr", "sal", "sar")
GRP3 = ("test", "test", "not", "neg", "mul", "imul", "div", "idiv")
GRP5 = ("inc", "dec", "call", "callf", "jmp", "jmpf", "push", "?")
GRP_0F00 = ("sldt", "str", "lldt", "ltr", "verr", "verw", "?", "?")
GRP_0F01 = ("sgdt", "sidt", "lgdt", "lidt", "smsw", "?", "lmsw", "invlpg")
GRP8 = ("?", "?", "?", "?", "bt", "bts", "btr", "btc")

GROUPS = {
    0x80: (GRP1, "Eb", "Ib"),
    0x81: (GRP1, "Ev", "Iz"),
    0x83: (GRP1, "Ev", "Ibs"),
    0xC0: (GRP2, "Eb", "Ib"),
    0xC1: (GRP2, "Ev", "Ib"),
    0xD0: (GRP2, "Eb", "1"),
    0xD1: (GRP2, "Ev", "1"),
    0xD2: (GRP2, "Eb", "cl"),
    0xD3: (GRP2, "Ev", "cl"),
    0xF6: (GRP3, "Eb", None),
    0xF7: (GRP3, "Ev", None),
    0xFE: (("inc", "dec", "?", "?", "?", "?", "?", "?"), "Eb", None),
    0xFF: (GRP5, "Ev", None),
    0x8F: (("pop", "?", "?", "?", "?", "?", "?", "?"), "Ev", None),
    0xC6: (("mov", "?", "?", "?", "?", "?", "?", "?"), "Eb", "Ib"),
    0xC7: (("mov", "?", "?", "?", "?", "?", "?", "?"), "Ev", "Iz"),
}

# --- 0F two-byte opcodes ---------------------------------------------------
TWO = {
    0x00: ("GRP0F00", ("Ew",)), 0x01: ("GRP0F01", ("M",)),
    0x02: ("lar", ("Gv", "Ew")), 0x03: ("lsl", ("Gv", "Ew")),
    0x06: ("clts", ()), 0x08: ("invd", ()), 0x09: ("wbinvd", ()),
    0x0B: ("ud2", ()),
    0x20: ("mov", ("Rd", "Cd")), 0x21: ("mov", ("Rd", "Dd")),
    0x22: ("mov", ("Cd", "Rd")), 0x23: ("mov", ("Dd", "Rd")),
    0x30: ("wrmsr", ()), 0x31: ("rdtsc", ()), 0x32: ("rdmsr", ()), 0x33: ("rdpmc", ()),
    0xA0: ("push", ("fs",)), 0xA1: ("pop", ("fs",)), 0xA2: ("cpuid", ()),
    0xA3: ("bt", ("Ev", "Gv")), 0xA4: ("shld", ("Ev", "Gv", "Ib")),
    0xA5: ("shld", ("Ev", "Gv", "cl")),
    0xA8: ("push", ("gs",)), 0xA9: ("pop", ("gs",)),
    0xAB: ("bts", ("Ev", "Gv")), 0xAC: ("shrd", ("Ev", "Gv", "Ib")),
    0xAD: ("shrd", ("Ev", "Gv", "cl")), 0xAF: ("imul", ("Gv", "Ev")),
    0xB0: ("cmpxchg", ("Eb", "Gb")), 0xB1: ("cmpxchg", ("Ev", "Gv")),
    0xB2: ("lss", ("Gv", "M")), 0xB3: ("btr", ("Ev", "Gv")),
    0xB4: ("lfs", ("Gv", "M")), 0xB5: ("lgs", ("Gv", "M")),
    0xB6: ("movzx", ("Gv", "Eb")), 0xB7: ("movzx", ("Gv", "Ew")),
    0xBA: ("GRP8", ("Ev", "Ib")), 0xBB: ("btc", ("Ev", "Gv")),
    0xBC: ("bsf", ("Gv", "Ev")), 0xBD: ("bsr", ("Gv", "Ev")),
    0xBE: ("movsx", ("Gv", "Eb")), 0xBF: ("movsx", ("Gv", "Ew")),
    0xC0: ("xadd", ("Eb", "Gb")), 0xC1: ("xadd", ("Ev", "Gv")),
    0xC8: ("bswap", ("eAX",)),
}
for _i in range(16):
    TWO[0x40 + _i] = ("cmov" + CC[_i], ("Gv", "Ev"))
    TWO[0x80 + _i] = ("j" + CC[_i], ("Jz",))
    TWO[0x90 + _i] = ("set" + CC[_i], ("Eb",))
for _i in range(8):
    TWO[0xC8 + _i] = ("bswap", ("eR%d" % _i,))

# --- x87 FPU: escape opcode -> (mem-form mnemonics by reg, reg-form table) --
FPU_MEM = {
    0xD8: ("fadd", "fmul", "fcom", "fcomp", "fsub", "fsubr", "fdiv", "fdivr"),
    0xD9: ("fld", "?", "fst", "fstp", "fldenv", "fldcw", "fnstenv", "fnstcw"),
    0xDA: ("fiadd", "fimul", "ficom", "ficomp", "fisub", "fisubr", "fidiv", "fidivr"),
    0xDB: ("fild", "fisttp", "fist", "fistp", "?", "fld", "?", "fstp"),
    0xDC: ("fadd", "fmul", "fcom", "fcomp", "fsub", "fsubr", "fdiv", "fdivr"),
    0xDD: ("fld", "fisttp", "fst", "fstp", "frstor", "?", "fnsave", "fnstsw"),
    0xDE: ("fiadd", "fimul", "ficom", "ficomp", "fisub", "fisubr", "fidiv", "fidivr"),
    0xDF: ("fild", "fisttp", "fist", "fistp", "fbld", "fild", "fbstp", "fistp"),
}
# operand size suffix for the memory form, indexed by escape opcode and reg
FPU_MEMSZ = {
    0xD8: "dword", 0xD9: "dword", 0xDA: "dword", 0xDB: "dword",
    0xDC: "qword", 0xDD: "qword", 0xDE: "word", 0xDF: "word",
}
FPU_REG = {
    0xD8: lambda m, r: (("fadd", "fmul", "fcom", "fcomp", "fsub", "fsubr", "fdiv", "fdivr")[(m >> 3) & 7],
                        ["st(0)", "st(%d)" % (m & 7)]),
    0xDC: lambda m, r: (("fadd", "fmul", "fcom", "fcomp", "fsubr", "fsub", "fdivr", "fdiv")[(m >> 3) & 7],
                        ["st(%d)" % (m & 7), "st(0)"]),
    0xDE: lambda m, r: (("faddp", "fmulp", "fcomp", "fcompp", "fsubrp", "fsubp", "fdivrp", "fdivp")[(m >> 3) & 7],
                        [] if m == 0xD9 else ["st(%d)" % (m & 7), "st(0)"]),
    0xDD: lambda m, r: (("ffree", "?", "fst", "fstp", "fucom", "fucomp", "?", "?")[(m >> 3) & 7],
                        ["st(%d)" % (m & 7)]),
    0xDB: lambda m, r: (("?", "?", "?", "?", "?", "fucomi", "fcomi", "?")[(m >> 3) & 7],
                        ["st(0)", "st(%d)" % (m & 7)]),
    0xDA: lambda m, r: (("fcmovb", "fcmove", "fcmovbe", "fcmovu", "?", "?", "?", "?")[(m >> 3) & 7],
                        ["st(0)", "st(%d)" % (m & 7)]),
}
FPU_D9_FIXED = {
    0xD0: "fnop", 0xE0: "fchs", 0xE1: "fabs", 0xE4: "ftst", 0xE5: "fxam",
    0xE8: "fld1", 0xE9: "fldl2t", 0xEA: "fldl2e", 0xEB: "fldpi",
    0xEC: "fldlg2", 0xED: "fldln2", 0xEE: "fldz",
    0xF0: "f2xm1", 0xF1: "fyl2x", 0xF2: "fptan", 0xF3: "fpatan",
    0xF4: "fxtract", 0xF5: "fprem1", 0xF6: "fdecstp", 0xF7: "fincstp",
    0xF8: "fprem", 0xF9: "fyl2xp1", 0xFA: "fsqrt", 0xFB: "fsincos",
    0xFC: "frndint", 0xFD: "fscale", 0xFE: "fsin", 0xFF: "fcos",
}
FPU_DB_FIXED = {0xE2: "fnclex", 0xE3: "fninit"}
FPU_DF_FIXED = {0xE0: "fnstsw ax"}

STOP_FLOW = {"ret", "retf", "jmp", "jmpf", "iretd", "hlt", "ud2", "int3"}


class Insn:
    __slots__ = ("off", "va", "length", "mnemonic", "ops", "prefixes", "target",
                 "mem_target", "imm", "raw", "opsize", "valid")

    def __init__(self):
        self.off = 0
        self.va = None
        self.length = 1
        self.mnemonic = "(bad)"
        self.ops = []
        self.prefixes = []
        self.target = None       # branch/call destination VA
        self.mem_target = None   # absolute memory operand VA
        self.imm = None
        self.raw = b""
        self.opsize = 32
        self.valid = False

    @property
    def text(self):
        pre = " ".join(p for p in self.prefixes if p in ("lock", "rep", "repne"))
        body = self.mnemonic + (" " + ", ".join(self.ops) if self.ops else "")
        return (pre + " " + body).strip()

    @property
    def is_call(self):
        return self.mnemonic in ("call", "callf")

    @property
    def is_jump(self):
        return self.mnemonic.startswith("j") or self.mnemonic.startswith("loop")

    @property
    def is_ret(self):
        return self.mnemonic in ("ret", "retf", "iretd")

    @property
    def stops_flow(self):
        return self.mnemonic in STOP_FLOW

    def __repr__(self):
        return f"<{self.va and hex(self.va)} {self.text}>"


def _s8(b):
    return b - 256 if b > 127 else b


def _s16(v):
    return v - 0x10000 if v > 0x7FFF else v


def _s32(v):
    return v - 0x100000000 if v > 0x7FFFFFFF else v


def _hexi(v):
    return f"0x{v:X}" if v >= 0 else f"-0x{-v:X}"


class _Dec:
    def __init__(self, data, off, va, bits):
        self.d = data
        self.start = off
        self.p = off
        self.va = va
        self.opsize = bits
        self.addrsize = bits
        self.seg = None
        self.rep = None
        self.lock = False
        self.modrm = None
        self.mem_target = None

    # -- byte readers
    def u8(self):
        v = self.d[self.p]
        self.p += 1
        return v

    def u16(self):
        v = int.from_bytes(self.d[self.p:self.p + 2], "little")
        self.p += 2
        return v

    def u32(self):
        v = int.from_bytes(self.d[self.p:self.p + 4], "little")
        self.p += 4
        return v

    # -- modrm
    def fetch_modrm(self):
        if self.modrm is None:
            self.modrm = self.u8()
            self.mod = self.modrm >> 6
            self.reg = (self.modrm >> 3) & 7
            self.rm = self.modrm & 7
            self._rm_text = None
        return self.modrm

    def rm_string(self, size):
        """size: 8/16/32 for register form; returns operand text."""
        self.fetch_modrm()
        if self.mod == 3:
            return self.reg_name(self.rm, size)
        return self.mem_string(size)

    def mem_string(self, size=None):
        self.fetch_modrm()
        disp = 0
        parts = []
        if self.addrsize == 32:
            if self.rm == 4:
                sib = self.u8()
                scale, index, base = sib >> 6, (sib >> 3) & 7, sib & 7
                if index != 4:
                    parts.append(REG32[index] + ("*%d" % (1 << scale) if scale else ""))
                if base == 5 and self.mod == 0:
                    disp = _s32(self.u32())
                    absolute = not parts
                else:
                    parts.insert(0, REG32[base])
                    absolute = False
            elif self.rm == 5 and self.mod == 0:
                disp = _s32(self.u32())
                absolute = True
            else:
                parts.append(REG32[self.rm])
                absolute = False
            if self.mod == 1:
                disp = _s8(self.u8())
            elif self.mod == 2:
                disp = _s32(self.u32())
        else:  # 16-bit addressing
            bases = ("bx+si", "bx+di", "bp+si", "bp+di", "si", "di", "bp", "bx")
            absolute = False
            if self.rm == 6 and self.mod == 0:
                disp = _s16(self.u16())
                absolute = True
            else:
                parts.append(bases[self.rm])
            if self.mod == 1:
                disp = _s8(self.u8())
            elif self.mod == 2:
                disp = _s16(self.u16())

        if absolute and disp:
            self.mem_target = disp & 0xFFFFFFFF
        inner = "+".join(parts)
        if disp or not parts:
            if parts:
                inner += ("+0x%X" % disp) if disp >= 0 else ("-0x%X" % -disp)
            else:
                inner = "0x%X" % (disp & 0xFFFFFFFF)
        pfx = ""
        if size == 8:
            pfx = "byte "
        elif size == 16:
            pfx = "word "
        elif size == 32:
            pfx = "dword "
        elif isinstance(size, str):
            pfx = size + " "
        segp = (self.seg + ":") if self.seg else ""
        return f"{pfx}{segp}[{inner}]"

    def reg_name(self, n, size):
        if size == 8:
            return REG8[n]
        if size == 16:
            return REG16[n]
        return REG32[n]


def decode(data, off, va=None, bits=32):
    """Decode one instruction at data[off]. va = virtual address of that byte."""
    ins = Insn()
    ins.off = off
    ins.va = va
    if off >= len(data):
        return ins
    dec = _Dec(data, off, va, bits)

    # ---- prefixes
    while dec.p < len(data):
        b = data[dec.p]
        if b in SEG_PREFIX:
            dec.seg = SEG_PREFIX[b]
            ins.prefixes.append(dec.seg)
        elif b == 0x66:
            dec.opsize = 16 if bits == 32 else 32
            ins.prefixes.append("opsize")
        elif b == 0x67:
            dec.addrsize = 16 if bits == 32 else 32
            ins.prefixes.append("addrsize")
        elif b == 0xF0:
            dec.lock = True
            ins.prefixes.append("lock")
        elif b == 0xF2:
            dec.rep = "repne"
            ins.prefixes.append("repne")
        elif b == 0xF3:
            dec.rep = "rep"
            ins.prefixes.append("rep")
        else:
            break
        dec.p += 1
    ins.opsize = dec.opsize

    if dec.p >= len(data):
        ins.length = dec.p - off
        return ins

    op = dec.u8()

    # ---- x87
    if 0xD8 <= op <= 0xDF:
        _decode_fpu(dec, ins, op)
        _finish(dec, ins, data)
        return ins

    two = False
    if op == 0x0F:
        two = True
        if dec.p >= len(data):
            ins.length = dec.p - off
            return ins
        op = dec.u8()
        entry = TWO.get(op)
    else:
        entry = ONE.get(op)

    if entry is None and not two and op in GROUPS:
        entry = None
    if op in GROUPS and not two:
        names, rmspec, immspec = GROUPS[op]
        dec.fetch_modrm()
        mn = names[dec.reg]
        size = 8 if rmspec == "Eb" else dec.opsize
        rm = dec.rm_string(size)
        ops = [rm]
        # F6/F7 /0 and /1 are test with immediate; /2../7 have no second operand
        if op in (0xF6, 0xF7):
            if dec.reg in (0, 1):
                immspec = "Ib" if op == 0xF6 else "Iz"
            else:
                immspec = None
        if op == 0xFF and dec.reg in (2, 3, 4, 5, 6):
            ops = [rm]
        if immspec:
            # immspec may be a literal operand ("1", "cl") as well as a real
            # immediate, so go through _operand rather than _imm.
            ops.append(_operand(dec, ins, immspec))
        ins.mnemonic = mn
        ins.ops = ops
        if op == 0xFF and dec.reg in (2, 3):
            ins.mnemonic = "call" if dec.reg == 2 else "callf"
        elif op == 0xFF and dec.reg in (4, 5):
            ins.mnemonic = "jmp" if dec.reg == 4 else "jmpf"
        ins.valid = mn != "?"
        _finish(dec, ins, data)
        return ins

    if entry is None:
        ins.length = dec.p - off
        ins.raw = data[off:dec.p]
        return ins

    mn, spec = entry
    if mn == "GRP8":
        dec.fetch_modrm()
        mn = GRP8[dec.reg]
    elif mn == "GRP0F00":
        dec.fetch_modrm()
        mn = GRP_0F00[dec.reg]
    elif mn == "GRP0F01":
        dec.fetch_modrm()
        mn = GRP_0F01[dec.reg]

    # opsize-dependent mnemonic fixups
    if dec.opsize == 16:
        mn = {"cwde": "cbw", "cdq": "cwd", "pushad": "pushaw", "popad": "popaw",
              "pushfd": "pushfw", "popfd": "popfw", "iretd": "iretw",
              "movsd": "movsw", "stosd": "stosw", "lodsd": "lodsw",
              "scasd": "scasw", "cmpsd": "cmpsw", "insd": "insw",
              "outsd": "outsw"}.get(mn, mn)

    ops = []
    for s in spec:
        ops.append(_operand(dec, ins, s))
    ins.mnemonic = mn
    ins.ops = [o for o in ops if o is not None]
    ins.valid = True
    if dec.rep and mn.endswith(("sb", "sw", "sd")) and mn[0] in "mcslo":
        pass
    _finish(dec, ins, data)
    return ins


def _finish(dec, ins, data):
    ins.length = max(1, dec.p - dec.start)
    ins.raw = data[dec.start:dec.p]
    if dec.mem_target is not None:
        ins.mem_target = dec.mem_target


def _imm(dec, ins, spec):
    if spec == "Ib":
        v = dec.u8()
        ins.imm = v
        return _hexi(v)
    if spec == "Ibs":
        v = _s8(dec.u8())
        ins.imm = v
        return _hexi(v)
    if spec == "Iw":
        v = dec.u16()
        ins.imm = v
        return _hexi(v)
    if spec in ("Iz", "Iv"):
        if dec.opsize == 16:
            v = dec.u16()
        else:
            v = dec.u32()
        ins.imm = v
        return _hexi(v)
    if spec == "1":
        return "1"
    raise ValueError(spec)


def _operand(dec, ins, s):
    if s in ("Eb", "Ew", "Ev", "M", "Ma"):
        if s == "Eb":
            return dec.rm_string(8)
        if s == "Ew":
            return dec.rm_string(16)
        if s == "Ev":
            return dec.rm_string(dec.opsize)
        return dec.mem_string(None)
    if s in ("Gb", "Gw", "Gv"):
        dec.fetch_modrm()
        return dec.reg_name(dec.reg, {"Gb": 8, "Gw": 16}.get(s, dec.opsize))
    if s == "Sw":
        dec.fetch_modrm()
        return SREG[dec.reg]
    if s in ("Rd",):
        dec.fetch_modrm()
        return REG32[dec.rm]
    if s == "Cd":
        dec.fetch_modrm()
        return "cr%d" % dec.reg
    if s == "Dd":
        dec.fetch_modrm()
        return "dr%d" % dec.reg
    if s in ("Ib", "Ibs", "Iw", "Iz", "Iv", "1"):
        return _imm(dec, ins, s)
    if s == "Jb":
        rel = _s8(dec.u8())
        return _branch(dec, ins, rel)
    if s == "Jz":
        rel = _s16(dec.u16()) if dec.opsize == 16 else _s32(dec.u32())
        return _branch(dec, ins, rel)
    if s == "Ap":
        off_ = dec.u16() if dec.opsize == 16 else dec.u32()
        seg = dec.u16()
        return f"0x{seg:04X}:0x{off_:X}"
    if s in ("Ob", "Ov"):
        a = dec.u32() if dec.addrsize == 32 else dec.u16()
        dec.mem_target = a
        pfx = "byte " if s == "Ob" else ("word " if dec.opsize == 16 else "dword ")
        segp = (dec.seg + ":") if dec.seg else ""
        return f"{pfx}{segp}[0x{a:X}]"
    if s == "AL":
        return "al"
    if s == "eAX":
        return "ax" if dec.opsize == 16 else "eax"
    if s.startswith("eR"):
        n = int(s[2])
        return REG16[n] if dec.opsize == 16 else REG32[n]
    if s.startswith("R8_"):
        return REG8[int(s[3])]
    return s  # literal register name like "cl", "dx", "es"


def _branch(dec, ins, rel):
    nxt_off = dec.p
    if dec.va is not None:
        tgt = (dec.va + (nxt_off - dec.start) + rel) & 0xFFFFFFFF
    else:
        tgt = (nxt_off + rel) & 0xFFFFFFFF
    ins.target = tgt
    return f"0x{tgt:X}"


def _decode_fpu(dec, ins, op):
    modrm = dec.d[dec.p] if dec.p < len(dec.d) else 0
    if modrm < 0xC0:
        dec.fetch_modrm()
        mn = FPU_MEM[op][dec.reg]
        size = FPU_MEMSZ[op]
        # size overrides for specific forms
        if op == 0xD9 and dec.reg in (4, 6):
            size = ""
        elif op == 0xD9 and dec.reg in (5, 7):
            size = "word"
        elif op == 0xDB and dec.reg in (5, 7):
            size = "tbyte"
        elif op == 0xDD and dec.reg in (4, 6):
            size = ""
        elif op == 0xDD and dec.reg == 7:
            size = "word"
        elif op == 0xDF and dec.reg in (4, 6):
            size = "tbyte"
        elif op == 0xDF and dec.reg in (5, 7):
            size = "qword"
        ins.mnemonic = mn
        ins.ops = [dec.mem_string(size or None)]
        ins.valid = mn != "?"
        return
    dec.p += 1  # consume modrm
    if op == 0xD9:
        if modrm in FPU_D9_FIXED:
            ins.mnemonic = FPU_D9_FIXED[modrm]
            ins.valid = True
            return
        if 0xC0 <= modrm <= 0xC7:
            ins.mnemonic, ins.ops = "fld", ["st(%d)" % (modrm & 7)]
            ins.valid = True
            return
        if 0xC8 <= modrm <= 0xCF:
            ins.mnemonic, ins.ops = "fxch", ["st(%d)" % (modrm & 7)]
            ins.valid = True
            return
    if op == 0xDB and modrm in FPU_DB_FIXED:
        ins.mnemonic = FPU_DB_FIXED[modrm]
        ins.valid = True
        return
    if op == 0xDF and modrm in FPU_DF_FIXED:
        ins.mnemonic = FPU_DF_FIXED[modrm]
        ins.valid = True
        return
    if op == 0xDE and modrm == 0xD9:
        ins.mnemonic = "fcompp"
        ins.valid = True
        return
    if op == 0xDD and 0xE0 <= modrm <= 0xEF:
        ins.mnemonic = "fucom" if modrm < 0xE8 else "fucomp"
        ins.ops = ["st(%d)" % (modrm & 7)]
        ins.valid = True
        return
    fn = FPU_REG.get(op)
    if fn:
        mn, ops = fn(modrm, modrm & 7)
        ins.mnemonic, ins.ops = mn, ops
        ins.valid = mn != "?"
        return
    ins.mnemonic = "fesc%02X" % op
    ins.ops = ["0x%02X" % modrm]


def decode_range(data, off, end, va_base=None, bits=32):
    """Linear sweep from off to end; yields Insn."""
    p = off
    while p < end and p < len(data):
        va = None if va_base is None else va_base + (p - off)
        ins = decode(data, p, va, bits)
        yield ins
        p += ins.length


if __name__ == "__main__":
    # self-test on hand-assembled sequences
    tests = [
        (bytes.fromhex("55"), "push ebp"),
        (bytes.fromhex("89e5"), "mov ebp, esp"),
        (bytes.fromhex("8b4508"), "mov eax, dword [ebp+0x8]"),
        (bytes.fromhex("83ec10"), "sub esp, 0x10"),
        (bytes.fromhex("c3"), "ret"),
        (bytes.fromhex("e8ffffffff"), None),
        (bytes.fromhex("6a00"), "push 0x0"),
        (bytes.fromhex("68efbeadde"), "push 0xDEADBEEF"),
        (bytes.fromhex("0fb6c0"), "movzx eax, al"),
        (bytes.fromhex("f7d8"), "neg eax"),
        (bytes.fromhex("8d0485c0470400"), "lea eax, [eax*4+0x447C0]"),
        (bytes.fromhex("d905c0470400"), "fld dword [0x447C0]"),
        (bytes.fromhex("660fb7c0"), "movzx ax, ax"),
        (bytes.fromhex("f3a4"), "rep movsb"),
        (bytes.fromhex("0f8f10000000"), "jg 0x16"),
        (bytes.fromhex("ff2485c0470400"), "jmp dword [eax*4+0x447C0]"),
        (bytes.fromhex("d3e0"), "shl eax, cl"),
        (bytes.fromhex("d3fa"), "sar edx, cl"),
        (bytes.fromhex("d1e0"), "shl eax, 1"),
        (bytes.fromhex("c1f803"), "sar eax, 0x3"),
        (bytes.fromhex("d2e9"), "shr cl, cl"),
    ]
    ok = 0
    for raw, expect in tests:
        i = decode(raw, 0, 0)
        got = i.text
        mark = "ok " if (expect is None or got == expect) else "FAIL"
        if mark == "ok ":
            ok += 1
        print(f"{mark} {raw.hex():<16} len={i.length} {got}" + (f"   (expected {expect})" if mark == "FAIL" else ""))
    print(f"{ok}/{len(tests)} self-tests passed")
