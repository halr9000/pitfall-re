#!/usr/bin/env python3
"""Generic hex viewer for any project file.

Usage:
    python3 tools/hexdump.py <file> [offset] [length]
    python3 tools/hexdump.py <file> 0x1000 256

Offsets accept 0x hex or decimal. Negative offset counts from EOF.
"""
import sys
from pathlib import Path


def num(s):
    return int(s, 16) if s.lower().startswith("0x") else int(s, 10)


def dump(data, base, width=16):
    for i in range(0, len(data), width):
        chunk = data[i:i + width]
        hexs = " ".join(f"{b:02X}" for b in chunk)
        txt = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"{base + i:08X}  {hexs:<{width * 3}} |{txt}|")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    path = Path(sys.argv[1])
    off = num(sys.argv[2]) if len(sys.argv) > 2 else 0
    length = num(sys.argv[3]) if len(sys.argv) > 3 else 256
    data = path.read_bytes()
    if off < 0:
        off += len(data)
    dump(data[off:off + length], off)
    print(f"({path.name}: {len(data)} bytes / 0x{len(data):X})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
