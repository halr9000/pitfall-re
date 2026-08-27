#!/usr/bin/env python3
"""labels.csv loader shared by every disassembly tool.

Format (one per line, `#` starts a comment):
    va,name,comment

`va` is a virtual address with 0x prefix (image base 0x400000), e.g.
    0x0044A8FF,_start,PE entry point
A `off:` prefix means a raw file offset instead, and a `ph:` prefix names an
offset inside a .PH data file rather than the EXE.
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LABELS_CSV = ROOT / "labels.csv"


class Labels:
    def __init__(self, path=LABELS_CSV):
        self.path = Path(path)
        self.by_va = {}
        self.by_off = {}
        self.by_ph = {}
        self.load()

    def load(self):
        if not self.path.exists():
            return
        with self.path.open(newline="") as fh:
            for row in csv.reader(fh):
                if not row or not row[0].strip() or row[0].lstrip().startswith("#"):
                    continue
                key = row[0].strip()
                name = row[1].strip() if len(row) > 1 else ""
                comment = row[2].strip() if len(row) > 2 else ""
                if key.startswith("off:"):
                    self.by_off[int(key[4:], 16)] = (name, comment)
                elif key.startswith("ph:"):
                    self.by_ph[key[3:]] = (name, comment)
                else:
                    self.by_va[int(key, 16)] = (name, comment)

    def name(self, va):
        e = self.by_va.get(va)
        return e[0] if e else None

    def comment(self, va):
        e = self.by_va.get(va)
        return e[1] if e else None

    def get(self, va):
        return self.by_va.get(va)

    def annotate(self, va):
        """'0x00401234 <name>' when known, else '0x00401234'."""
        n = self.name(va)
        return f"0x{va:08X} <{n}>" if n else f"0x{va:08X}"

    def add(self, va, name, comment=""):
        self.by_va[va] = (name, comment)
        with self.path.open("a", newline="") as fh:
            csv.writer(fh).writerow([f"0x{va:08X}", name, comment])


_cache = {}


def load_labels(path=LABELS_CSV):
    key = str(path)
    if key not in _cache:
        _cache[key] = Labels(path)
    return _cache[key]
