# Handoff — pitfall-re

Reverse engineering *Pitfall: The Mayan Adventure* (Win32, 1995) and porting it
to the browser. Written for whoever picks this up next, including a future
Claude session.

**Live port:** https://halr9000.github.io/pitfall-re/ ·
**Repo:** https://github.com/halr9000/pitfall-re · 18 commits, 142 files.

---

## Where things stand

The browser port renders every level's real backgrounds with correct layering,
Harry walks and jumps against the game's own collision map, and he is drawn from
the game's own named animation banks. The title screen renders correctly. A
▶︎ Demo button walks him around without a keyboard.

It is **not a game yet**: no entities, no hazards, no pickups, no level
transitions, and the movement constants are invented.

| Phase | State |
|-------|-------|
| Identify the binary | done |
| Decompress | n/a — not packed |
| Disassemble | tooling complete; ~15 functions labelled of 482 call targets |
| Extract assets | backgrounds, tile sheets, palettes, sprites, fonts — all decoding |
| Data structures | container, layers, sprite banks, animation scripts, registry |
| Validate | done piecemeal against the data; never against a running original |
| Web port | stages 1–3 of 4 |

---

## Before you start

**Install the `/re` skill** if this session doesn't already have it. The whole
project is built around it — it defines the phase structure, the
`REVERSE.md` / `labels.csv` / `dead_ends.md` workflow, and the tool conventions
in `CLAUDE.md`. Check for it first; a session that already lists `re` among its
skills needs nothing.

```bash
git clone https://github.com/vgrichina/re-skill.git
cd re-skill && ./install.sh          # copies to ~/.claude/skills/re
```

Then `/re` continues from `REVERSE.md`, and `/re <binary>` bootstraps a new
project. `re_loop.sh` in this repo is already configured for autonomous
sessions — the human runs it, the agent never invokes it.

## Getting the game files

`game/` is gitignored — it holds retail files. You need `PITFALL.EXE`,
`INIT.PH`, `LEVEL00.PH`…`LEVEL24.PH` and `WAIL32.DLL`.

Source: https://www.myabandonware.com/game/pitfall-the-mayan-adventure-876#download

Pick the **Windows** entry. The package this project was developed against is
`PitfallTheMayanAdventure_Win_EN_RIPVersion.zip` — the "RIP" build, meaning
audio and video were stripped. That matters: the EXE references 200+
`SOUNDxx.WAV` files and the `.AVI` cutscenes that are simply absent, so don't
treat their absence as a decoding failure.

Verify you have the same bytes:

```
32 files, 8.7 MB unpacked

sha256  c7dadc1b511d8ae16dd713f826fd49d706b4286b6cc6d5b5ee9283aa344ca2fd  PITFALL.EXE   710144 B
sha256  c369523c295ad13e16ad35b653424c4caa49ec2dae7d668422092413a198d090  INIT.PH      2057605 B
```

Every address in this document and in `labels.csv` is relative to that exact
`PITFALL.EXE`. A different build — a non-RIP release, a patched version, a
different language — will not line up, and nothing will tell you except that
the disassembly stops making sense.

I could not fetch the direct download URL: the domain is blocked by this
environment's network egress proxy. The package name above is the identifier to
look for on that page.

## Getting running in five minutes

Everything below is stdlib-only Python 3.8+.

```bash
python3 tools/instruction_set.py      # decoder self-tests, expect 21/21
python3 tools/check_ph.py             # validates the .PH model on all 26 files
python3 tools/sprite.py --scan        # expect 646/648 banks (2 are fonts)
python3 tools/anim.py --scan          # record blocks
python3 tools/export_web.py           # rebuild web/data/
python3 tools/export_sprites.py       # rebuild web/data/sprites/
cd web && python3 -m http.server 8000
```

No disassembler library, no PNG library, no build step. Headless verification
uses Playwright with the preinstalled Chromium at `/opt/pw-browsers/chromium`.

---

## Proven vs inferred — read this before trusting anything

The single most useful thing in this repo is that these are kept apart. Do not
collapse them.

**Read from code, safe to build on:**

- `.PH` container: `{u32 size; payload}` repeated. Verified — every byte of all
  26 files is accounted for.
- Layer block: `cell_w, cell_h, pix_off, pal_off, pal_count`, then a `u16`
  cellmap, an 8×8 tile sheet, an RGB palette. Confirmed twice, from `load_level`
  and independently from `draw_background`.
- Cell word: bits 0–11 tile index; bit 12 opaque vs masked blit; bits 13–14
  select a third blit path; bit 15 untested while drawing.
- Sprite bank + RLE, including **run length = `b − 0x7F`** — read off
  `LoadSprite`'s remap pass.
- Animation VM: frame bytes, `0xFE arg` call, `0xF0` loop, `0xFF` end; hold time
  is a per-entity field, not script data.
- Sprite registry: 646 `LoadSprite(name, &dest)` sites, 311 names.
- Name → `INIT.PH` block, by replaying call order.

**Inferred, plausible, unproven:**

- **`solid == cell bit 12`.** The collision *test* in the binary has never been
  found. Bit 12 is proven to select the opaque blit, and its mask is a textbook
  collision map on every level checked, and physics built on it behaves
  correctly — but that is circumstantial. If something later contradicts it,
  believe the contradiction.
- Layer draw order (parallax behind, detail in front) — from the data, not from
  `draw_background`'s callers.
- Blocks 2–4 being `.dt2`/`.trg`/`.als` placements. They are 2-byte records with
  no VM control codes; the positional mapping to manifest names is a guess.
- Every movement constant and the player box size.

---

## Key addresses

| Address | What |
|---------|------|
| `0x0044A8FF` | entry, MSVC CRT |
| `0x004460E0` | `load_level` — filename, `CreateFileA`, block loop, header parse |
| `0x00436FB4` | `draw_background` — composites the cellmap |
| `0x00436B2C` | `blit_cell` — branches on the cell word's high bits |
| `0x00436DF4` | `blit_cell_mode0` — masked blit, palette index 0 transparent |
| `0x00436BD8` | `blit_cell_mode2` — **not yet read** |
| `0x004453A0` | `LoadSprite`, 646 callers |
| `0x004457D0` | the 118 calls that load `INIT.PH` in order |
| `0x00401DBC` | `anim_advance` — the animation VM |
| `0x0043387E` | `rand` |
| `0x0046F0D8` | `g_level_assets` — 25 × 6 × 16-byte manifest |
| `0x004601B8` | current entity pointer |

`labels.csv` holds 242 labels and is auto-loaded by every tool.

---

## The tools

`tools/` is stdlib-only and self-contained. `CLAUDE.md` has the full index; the
ones you will reach for:

- `dis.py <addr>` — annotated disassembly, resolves labels and strings
- `xref.py <addr>` — references via `.reloc`, rel32 branches, raw dwords
- `find_callers.py --entries / --owner / --callees` — call graph
- `sprite.py --list / --png` and `sprite_registry.py` — sprites and the registry
- `ph_dump.py`, `check_ph.py`, `render_level.py` — level data
- `anim.py` — record blocks

**A caveat on `dis.py`:** `xref` reports the address of a relocated *operand*,
not the instruction start. Disassembling straight from an xref hit usually
desyncs. Back up 1–2 bytes until it reads sensibly. This cost time more than
once.

---

## Where to pick up

Ranked by value, with why:

1. **Level entities.** Blocks 2–4 hold 2-byte records that are probably
   placements. Decoding them puts hazards, pickups and enemies into the port —
   the change that makes it a game rather than a walkthrough. Start by finding
   the code that reads those blocks, not by staring at the bytes.
2. **The collision test.** Turning `solid == bit 12` from inference into proof,
   or discovering it is wrong. Everything physical rests on it. Prior search
   ruled out: the second `g_map_tiles_w` reader, the alien update functions,
   `g_cell_w` readers, a per-tile attribute table, and mask-style bit-15 tests.
3. **Movement constants.** Currently invented. Find the player physics and
   replace them; the one real datum is that positions are 1/4-pixel fixed point.
4. **Animation timing.** Both halves are decoded — scripts hold cel order,
   `[esi+0x28]` holds tick rate — but the player's *script pointer* field is
   still unlocated. Do not infer it from what sits next to a bank assignment;
   that already failed once.
5. **Port performance.** Compositing whole levels up front costs ~2.8 s for
   `forest1` on mobile. Blit only the visible 41×29 cells per frame, the way
   `draw_background` does.

`REVERSE.md`'s task list has 30 open items, but several are stale — it grew
faster than it was pruned. Trust this ranking over that list.

---

## How to work on this

The method that produced the good results, and the one that produced the bad
ones, are both worth knowing.

**What worked:** find the code. Every solid finding here came from reading the
routine that consumes the data — `load_level`, `blit_cell`, `anim_advance`,
`LoadSprite`. Every retraction came from inferring structure by staring at
bytes.

**Validate with a metric the encoding cannot absorb.** The sprite RLE run length
was wrong for four sessions. Byte-consumption checks passed the whole time,
because the `0x7E` terminator absorbed the error. Row geometry caught it
instantly: 50% of rows overran the frame width under the wrong rule, 0% under
the right one.

**A permissive parser succeeding is not evidence.** All of blocks 1–4 parse as
animation scripts because any byte under `0xF0` reads as a frame index. Only
block 1 actually uses the format's control codes.

**Prefer predictions that can fail.** The name → bank mapping was confirmed by
checking that all 83 `hyi*` names land on Harry-palette banks and none of the
other 35 do. That test had a real chance of failing and didn't.

`dead_ends.md` has 12 entries. Read it before starting — several are approaches
that look obviously correct and are not. It is the highest-value-per-line file
in the repo.

---

## Legal note

`game/` and `gfx/` are gitignored. `web/data/` **is** committed, because GitHub
Pages has to serve it; it contains decoded artwork. The repo owner's position is
that the title is abandonware with no active rights holder and that US fair use
applies. That is their call, not a settled fact — anyone forking this should
form their own view.
