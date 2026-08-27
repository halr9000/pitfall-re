#!/usr/bin/env python3
"""Emit labels.csv lines for every import thunk (IAT slot) in PITFALL.EXE.

Calls compile to `call dword [0x4744C4]`; naming each IAT slot turns those into
`call dword [imp_ReadFile]` in dis.py output.

    python3 tools/gen_iat_labels.py            # print the CSV lines
    python3 tools/gen_iat_labels.py --append   # append them to labels.csv
"""
import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from labels import LABELS_CSV, load_labels  # noqa: E402
from pe_map import load_pe  # noqa: E402


def iat_labels(pe):
    d = pe.data
    lfanew = struct.unpack_from("<I", d, 0x3C)[0]
    opt = lfanew + 24
    imp_rva, _ = struct.unpack_from("<II", d, opt + 96 + 1 * 8)
    it = pe.rva_to_off(imp_rva)
    out = []
    n = 0
    while True:
        desc = d[it + n * 20: it + n * 20 + 20]
        if len(desc) < 20 or desc == b"\0" * 20:
            break
        olt, _, _, namerva, firstthunk = struct.unpack("<5I", desc)
        dll = d[pe.rva_to_off(namerva):].split(b"\0")[0].decode("latin-1")
        dll_short = dll.split(".")[0]
        t_names = pe.rva_to_off(olt or firstthunk)
        slot_rva = firstthunk
        k = 0
        while True:
            val, = struct.unpack_from("<I", d, t_names + k * 4)
            if val == 0:
                break
            if val & 0x80000000:
                sym = f"{dll_short}_ord{val & 0xFFFF}"
            else:
                ho = pe.rva_to_off(val & 0x7FFFFFFF)
                sym = d[ho + 2:].split(b"\0")[0].decode("latin-1")
            va = pe.imagebase + slot_rva + k * 4
            out.append((va, f"imp_{sym}", f"{dll} import thunk"))
            k += 1
        n += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--append", action="store_true")
    args = ap.parse_args()
    pe = load_pe()
    rows = iat_labels(pe)
    if args.append:
        existing = set(load_labels().by_va)
        added = 0
        with LABELS_CSV.open("a", newline="") as fh:
            for va, name, comment in rows:
                if va in existing:
                    continue
                fh.write(f"0x{va:08X},{name},{comment}\n")
                added += 1
        print(f"appended {added} of {len(rows)} import labels to labels.csv")
    else:
        for va, name, comment in rows:
            print(f"0x{va:08X},{name},{comment}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
