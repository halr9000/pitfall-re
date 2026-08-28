# pitfall-re — project conventions

Reverse-engineering workspace for *Pitfall: The Mayan Adventure* (Win32, 1995)
and a browser port, driven by the [`/re` skill](https://github.com/vgrichina/re-skill).

**Start with [`HANDOFF.md`](HANDOFF.md)** — current state, what is proven versus
inferred, and where to pick up. This file is conventions only.

## Setup

- **Install the `/re` skill** if the session lacks it:
  `git clone https://github.com/vgrichina/re-skill.git && cd re-skill && ./install.sh`
- **Game files** go in `game/` and are not committed. Take the **4 MB "RIP
  Version"** Windows entry from myabandonware (not the 541 MB ISO); see
  `HANDOFF.md` for checksums. Every address here is relative to that exact build.
- `curl` and `WebFetch` cannot reach myabandonware — the sandbox egress proxy
  blocks it. The **Tavily MCP tools** can. Don't rediscover that.

## Binary and data

- Binary: `game/PITFALL.EXE` — PE32, i386, image base `0x00400000`,
  entry `0x0044A8FF`
- Data: `game/INIT.PH` (258 blocks, 120 sprite banks), `game/LEVEL00.PH` …
  `game/LEVEL24.PH`
- **Not committed:** `game/` (retail data) and `gfx/` (regenerated).
  **Committed:** `web/data/` — GitHub Pages has to serve it.

## Address notation

Flat PE, so addresses are **virtual addresses** with the image base applied:
`0x0044A8FF`. Tools also accept `off:0x4A8FF` for a raw file offset.
`tools/pe_map.py` does the conversion.

`labels.csv` keys:

| Key form | Meaning | Example |
|----------|---------|---------|
| `0xXXXXXXXX` | virtual address in PITFALL.EXE | `0x004460E0,load_level,...` |
| `off:0xXXXX` | raw file offset in PITFALL.EXE | `off:0x4A8FF,...` |
| `ph:FILE:0xXXXX` | offset inside a `.PH` data file | `ph:LEVEL13.PH:0x2024,...` |

Every tool loads `labels.csv` automatically, so a name added once shows up in
all later disassembly.

## Tools

`python3 tools/<name>.py` from `pitfall-re/`. No third-party disassemblers, no
build step, stdlib only — there is a hand-rolled PNG writer in `tools/png.py`
precisely so `pypng` is not needed.

**Binary analysis**

| Tool | Purpose |
|------|---------|
| `pe_info.py` | PE/NE/MZ header, sections, data directories, imports |
| `instruction_set.py` | i386 opcode database + decoder; run it for self-tests (21/21) |
| `dis.py` | annotated disassembler — `dis.py 0x004460E0 40`, `--func`, `--bytes N` |
| `xref.py` | references via `.reloc`, rel32 branches and raw dwords |
| `find_callers.py` | `--entries` (function table), `--owner`, `--callees` |
| `search_bytes.py` | byte-pattern search, `??` wildcards, `--disasm` |
| `strings_dump.py` | string scanner, `-g` regex filter, `--rva` |
| `decode_tables.py` | scalar / pointer / string / struct array decoder |
| `gen_iat_labels.py` | emit `imp_*` labels for all 180 import thunks |
| `find_cellmap_users.py` | scans `.text` for pixel→cell conversions |
| `hexdump.py` | generic hex viewer |

**Game data**

| Tool | Purpose |
|------|---------|
| `ph_info.py` | `.PH` header survey across every level file |
| `ph_dump.py` | block splitter, layer detection, block-0 decode, PNG export |
| `check_ph.py` | validates the layer model against all 26 `.PH` files |
| `sprite.py` | `0x34561234` sprite banks — `--scan`, `--list`, `--png` |
| `sprite_registry.py` | the 646 `LoadSprite(name, &dest)` bindings; `init_ph_mapping()` gives name → `INIT.PH` block |
| `anim.py` | the record blocks (1–4) — `--scan`, `--opcodes` |
| `render_level.py` | composites cellmap + tiles + palette into `gfx/*.png` |

**Web port pipeline** — both exporters must run after any decoder change:

| Tool | Purpose |
|------|---------|
| `export_web.py` | writes `web/data/` — layers, cellmaps, palettes |
| `export_sprites.py` | writes `web/data/sprites/` — banks resolved *by name* |
| `gen_catalog.py` | writes `web/catalog_data.json` for the asset browser |
| `png.py` | minimal stdlib PNG writer (library) |
| `pe_map.py`, `labels.py` | shared libraries |

## Verifying a change

```bash
python3 tools/instruction_set.py   # 21/21
python3 tools/check_ph.py          # 0 failures
python3 tools/sprite.py --scan     # 646/648 (the 2 are fonts)
python3 tools/export_web.py && python3 tools/export_sprites.py
cd web && python3 -m http.server 8000
```

For the browser port, drive it headless rather than eyeballing: Playwright with
the preinstalled Chromium at `/opt/pw-browsers/chromium`. `window.__game`
exposes the live state for assertions.

## Working rules

Process:

- Write findings to `REVERSE.md` every 2–3 tool calls; do not batch.
- New addresses go into `labels.csv` as soon as they are named.
- Stuck for 10 tool calls → append to `dead_ends.md`, split the task, move on.
- `re_loop.sh` is for the human to run; the agent never invokes it.

Evidence — these were all learned by getting them wrong:

- **Find the code.** Every solid finding here came from reading the routine that
  consumes the data. Every retraction came from inferring structure by staring
  at bytes.
- **Validate with a metric the encoding cannot absorb.** The sprite RLE run
  length was wrong for four sessions while byte-consumption checks passed, because
  the `0x7E` terminator absorbed the error. Row geometry caught it at once.
- **A permissive parser succeeding is not evidence.** All of blocks 1–4 parse as
  animation scripts; only block 1 uses the format's control codes.
- **Prefer predictions that can fail.** Name → bank was confirmed by checking
  that all 83 `hyi*` names land on Harry-palette banks and none of the other 35
  do.
- **Keep proven and inferred apart** in `REVERSE.md`, in code comments, and in
  the port's UI. `solid == cell bit 12` is still inference.

## Gotchas

- **`xref` reports the address of a relocated *operand*, not the instruction
  start.** Disassembling straight from an xref hit usually desyncs — back up
  1–2 bytes until it reads sensibly.
- Linear sweep desyncs on data embedded in `.text`; treat a run of nonsense as
  misalignment, not a decoder bug.
- The RIP build has no `SOUNDxx.WAV` or `.AVI` assets by construction. Their
  absence is not a decoding failure.
- `INIT.PH` blocks 0 and 1 are fonts with a different header; they fail
  `sprite.py` by design.
