# pitfall-re — project conventions

Reverse-engineering workspace for *Pitfall: The Mayan Adventure* (Win32, 1995),
driven by the [`/re` skill](https://github.com/vgrichina/re-skill).

## Binary and data

- Binary: `game/PITFALL.EXE` — PE32, i386, image base `0x00400000`,
  entry `0x0044A8FF`
- Data: `game/LEVEL00.PH` … `game/LEVEL24.PH`, `game/INIT.PH`
- **`game/` is not committed** — it is the copyrighted retail game data. Drop
  the files in yourself before running any tool. Everything under `gfx/` is
  regenerated from it and is not committed either.

## Address notation

Flat PE, so addresses are **virtual addresses** with the image base applied:
`0x0044A8FF`. Tools also accept `off:0x4A8FF` for a raw file offset and print
both where it helps. `tools/pe_map.py` does the conversion.

`labels.csv` keys:

| Key form | Meaning | Example |
|----------|---------|---------|
| `0xXXXXXXXX` | virtual address in PITFALL.EXE | `0x004460E0,load_level,...` |
| `off:0xXXXX` | raw file offset in PITFALL.EXE | `off:0x4A8FF,...` |
| `ph:FILE:0xXXXX` | offset inside a `.PH` data file | `ph:LEVEL13.PH:0x2024,...` |

Every tool loads `labels.csv` automatically, so a name added once shows up in
all later disassembly.

## Tool prefix

`python3 tools/<name>.py` from `pitfall-re/`. No third-party disassemblers, no
build step, stdlib only (there is a hand-rolled PNG writer in `tools/png.py`
precisely so `pypng` is not needed).

| Tool | Purpose |
|------|---------|
| `pe_info.py` | PE/NE/MZ header, sections, data directories, imports |
| `pe_map.py` | shared VA ↔ file-offset map (library) |
| `labels.py` | `labels.csv` loader (library) |
| `instruction_set.py` | i386 opcode database + decoder; run it for self-tests |
| `dis.py` | annotated disassembler — `dis.py 0x004460E0 40`, `--func`, `--bytes N` |
| `xref.py` | references via the `.reloc` table, rel32 branches and raw dwords |
| `find_callers.py` | callers, `--entries` (function table), `--owner`, `--callees` |
| `search_bytes.py` | byte-pattern search with context and inline disassembly |
| `strings_dump.py` | string scanner, `-g` regex filter, `--rva` |
| `decode_tables.py` | scalar / pointer / string / struct array decoder |
| `gen_iat_labels.py` | emit `imp_*` labels for all 180 import thunks |
| `hexdump.py` | generic hex viewer for any file |
| `ph_info.py` | `.PH` header survey across every level file |
| `ph_dump.py` | `.PH` block splitter + block-0 decode + PNG export |
| `check_ph.py` | validates the block-0 model against all 26 `.PH` files |
| `render_level.py` | composites cellmap + tiles + palette into `gfx/*.png` |
| `png.py` | minimal stdlib PNG writer (library) |
| `export_web.py` | writes the `web/data/` asset bundle for the browser port |
| `gen_catalog.py` | writes `web/catalog_data.json` for the asset browser |

## Working rules

- Write findings to `REVERSE.md` every 2–3 tool calls; do not batch.
- New addresses go into `labels.csv` as soon as they are named.
- Stuck for 10 tool calls → append to `dead_ends.md`, split the task, move on.
- `re_loop.sh` is for the human to run; the agent never invokes it.
