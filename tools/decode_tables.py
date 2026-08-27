#!/usr/bin/env python3
"""Struct / table decoder for PITFALL.EXE (and any raw file with --bin).

    python3 tools/decode_tables.py <addr> <count> <fmt> [options]

fmt:
    u8 s8 u16 s16 u32 s32 f32 f64      scalar arrays
    ptr32                              pointer array (VAs, annotated with labels)
    strN                               fixed-size string array, N bytes each
    nullstr                            consecutive NUL-terminated strings
    struct:<size>:<f1,f2,...>          struct array; fields are scalar codes
                                       above, or strN, padN

options:
    --follow FMT COUNT     for ptr32: decode COUNT entries of FMT at each target
    --bin PATH             decode a raw file instead of the EXE (addr = offset)
"""
import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from labels import load_labels  # noqa: E402
from pe_map import load_pe  # noqa: E402

SCALAR = {
    "u8": ("<B", 1), "s8": ("<b", 1), "u16": ("<H", 2), "s16": ("<h", 2),
    "u32": ("<I", 4), "s32": ("<i", 4), "f32": ("<f", 4), "f64": ("<d", 8),
    "ptr32": ("<I", 4),
}


def field_size(code):
    if code in SCALAR:
        return SCALAR[code][1]
    if code.startswith("str"):
        return int(code[3:])
    if code.startswith("pad"):
        return int(code[3:])
    raise ValueError(f"unknown field code {code!r}")


def read_field(data, off, code):
    if code in SCALAR:
        f, n = SCALAR[code]
        return struct.unpack_from(f, data, off)[0]
    if code.startswith("str"):
        n = int(code[3:])
        raw = data[off:off + n]
        end = raw.find(b"\0")
        return raw[:end if end >= 0 else n].decode("latin-1")
    if code.startswith("pad"):
        return None
    raise ValueError(code)


def fmt_value(v, code, pe, lab):
    if code == "ptr32":
        n = lab.name(v) if lab else None
        extra = f" <{n}>" if n else ""
        if pe and pe.is_valid_va(v):
            o = pe.va_to_off(v)
            if o is not None:
                blob = pe.data[o:o + 32]
                e = blob.find(b"\0")
                if 2 < e < 32 and all(32 <= c < 127 for c in blob[:e]):
                    extra += " " + repr(blob[:e].decode("latin-1"))
        return f"0x{v:08X}{extra}"
    if isinstance(v, float):
        return f"{v:g}"
    if isinstance(v, str):
        return repr(v)
    if isinstance(v, int):
        return f"0x{v:X} ({v})" if abs(v) > 9 else str(v)
    return str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("addr")
    ap.add_argument("count", type=int)
    ap.add_argument("fmt")
    ap.add_argument("--follow", nargs=2, metavar=("FMT", "COUNT"))
    ap.add_argument("--bin")
    args = ap.parse_args()

    if args.bin:
        pe, lab = None, None
        data = Path(args.bin).read_bytes()
        off = int(args.addr, 16)
        base_va = None
    else:
        pe = load_pe()
        lab = load_labels()
        data = pe.data
        off, base_va = pe.resolve(args.addr)
        if off is None:
            print("address not mapped")
            return 1

    fmt = args.fmt
    if fmt == "nullstr":
        p = off
        for i in range(args.count):
            e = data.find(b"\0", p)
            s = data[p:e].decode("latin-1")
            va = pe.off_to_va(p) if pe else None
            print(f"  [{i:3d}] " + (f"0x{va:08X}  " if va else f"0x{p:06X}  ") + repr(s))
            p = e + 1
        return 0

    if fmt.startswith("struct:"):
        _, size_s, fields_s = fmt.split(":", 2)
        size = int(size_s, 0)
        fields = fields_s.split(",")
        for i in range(args.count):
            base = off + i * size
            va = pe.off_to_va(base) if pe else None
            head = f"  [{i:3d}] " + (f"0x{va:08X}" if va else f"0x{base:06X}")
            vals, fo = [], base
            for f in fields:
                v = read_field(data, fo, f)
                if v is not None:
                    vals.append(f"{f}={fmt_value(v, f, pe, lab)}")
                fo += field_size(f)
            print(head + "  " + "  ".join(vals))
        return 0

    if fmt.startswith("str"):
        n = int(fmt[3:])
        for i in range(args.count):
            base = off + i * n
            v = read_field(data, base, fmt)
            va = pe.off_to_va(base) if pe else None
            print(f"  [{i:3d}] " + (f"0x{va:08X}  " if va else f"0x{base:06X}  ") + repr(v))
        return 0

    if fmt not in SCALAR:
        print(f"unknown fmt {fmt}")
        return 1
    _, esz = SCALAR[fmt]
    for i in range(args.count):
        base = off + i * esz
        v = read_field(data, base, fmt)
        va = pe.off_to_va(base) if pe else None
        line = f"  [{i:3d}] " + (f"0x{va:08X}  " if va else f"0x{base:06X}  ") \
            + fmt_value(v, fmt, pe, lab)
        print(line)
        if args.follow and fmt == "ptr32" and pe and pe.is_valid_va(v):
            sub_fmt, sub_n = args.follow[0], int(args.follow[1])
            so = pe.va_to_off(v)
            ssz = field_size(sub_fmt)
            vals = [fmt_value(read_field(data, so + k * ssz, sub_fmt), sub_fmt, pe, lab)
                    for k in range(sub_n)]
            print("          -> " + "  ".join(vals))
    return 0


if __name__ == "__main__":
    sys.exit(main())
