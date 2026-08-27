# Pitfall: The Mayan Adventure (Win32, 1995) — Reverse Engineering Notes

## Binary Identification

| Field | Value |
|-------|-------|
| File | `game/PITFALL.EXE` |
| Format | PE32 (MZ stub + `PE\0\0` at 0x80), 7 sections, base relocations present |
| Platform | Win32 (Windows 95 / NT), subsystem 2 = GUI |
| CPU | i386 (machine 0x014C), 32-bit protected mode |
| File size | 710144 bytes (0xAD600) |
| Header size | 0x400 |
| Image base | 0x00400000, image size 0xB7000 |
| Entry point | RVA 0x4A8FF → VA `0x0044A8FF` (`WinMainCRTStartup`) |
| Toolchain | Microsoft C/C++ (linker 2.55); MSVC 2.x CRT startup, SEH frame at entry, `__except_handler` table at 0x44C8E8 |
| Build date | timestamp 0x301F2888 = 1995-08-23 (matches the 1995-08-23 file dates on all game data) |
| Renderer | GDI `CreateDIBSection` + `SetDIBColorTable` + `StretchBlt` with a palettised (8bpp) back buffer; `AnimatePalette` / `RealizePalette` for palette effects |
| Audio | WINMM (`sndPlaySoundA`, `mciSendCommandA`, `timeSetEvent`) plus `WAIL32.DLL` (Wail MIDI/digital audio library) |
| Input | keyboard (`GetAsyncKeyState`) and joystick (`joyGetPos`, `joySetCapture`) |

This is the **RIP (stripped) release**: the EXE references 200+ `SOUNDxx.WAV`
files and the `.AVI`/audio assets that are absent from the archive. The 25
`LEVELnn.PH` level containers, `INIT.PH`, `PITFALL0.HLP`/`.FTS` and
`WAIL32.DLL` are present.

### Sections

| Name | VA | VSize | File off | Raw size | Flags |
|------|----|-------|----------|----------|-------|
| .text | 0x00401000 | 0x4E3C4 | 0x000400 | 0x4E400 | CODE EXEC READ |
| .bss | 0x00450000 | 0x0473C | — | 0 | UNINIT RW |
| .rdata | 0x00455000 | 0x00230 | 0x04E800 | 0x00400 | INIT READ |
| .data | 0x00456000 | 0x1D1B4 | 0x04EC00 | 0x1D200 | INIT RW |
| .idata | 0x00474000 | 0x011EE | 0x06BE00 | 0x01200 | INIT RW |
| .rsrc | 0x00476000 | 0x30C7C | 0x06D000 | 0x30E00 | INIT READ |
| .reloc | 0x004A7000 | 0x0F686 | 0x09DE00 | 0x0F800 | INIT DISCARDABLE READ |

Imports: KERNEL32 (63), USER32 (64), GDI32 (26), WINMM (17), ADVAPI32 (6),
COMCTL32 (4). 180 IAT slots, all named in `labels.csv` as `imp_*`.

---

## Memory Map

Flat 32-bit address space; addresses in this document are virtual addresses
with image base 0x400000 already applied.

| Address Range | Purpose |
|---------------|---------|
| 0x00401000–0x0044F3C4 | `.text` — 482 distinct rel32 call targets (function count upper bound) |
| 0x00450000–0x0045473C | `.bss` — game state globals, level pointers, string buffers filled by `LoadStringA` |
| 0x00455000–0x00455230 | `.rdata` |
| 0x00456000–0x004731B4 | `.data` — level manifest, string literals, static tables |
| 0x00474000–0x004751EE | `.idata` — import thunks (`imp_*` labels) |
| 0x00476000–0x004A6C7C | `.rsrc` — dialogs, bitmaps, strings, menus |

Level data lives on the heap: `g_level_heap` (0x004504E0) is the arena that
`load_level` fills from the `.PH` file, and `g_next_block_ptr` (0x00450510) is
the 16-byte-aligned write cursor for successive blocks.

---

## Data-Range Map

| Start | End | Size | Classification | Notes |
|-------|-----|------|----------------|-------|
| 0x00400000 | 0x00400400 | 0x400 | header | MZ + PE headers, section table |
| 0x00401000 | 0x0044F3C4 | 0x4E3C4 | code | i386, MSVC; `load_level` at 0x004460E0 traced |
| 0x0044A8FF | — | — | code | `WinMainCRTStartup` |
| 0x0046E084 | 0x0046E090 | 0xC | data (string) | `'init.ph'` |
| 0x0046E5B8 | 0x0046F0D0 | ~0xB18 | data (strings) | `SOUNDxx.WAV` name table (assets absent in RIP build) |
| 0x0046F0D8 | 0x0046F9D8+0x60 | 0x960 | data (table) | `g_level_assets` — 25 × 6 × 16-byte asset names |
| 0x0047112C | 0x0047113A | 0xE | data (string) | `'level%2.2d.ph'` |
| 0x00476000 | 0x004A6C7C | 0x30C7C | resources | `.rsrc` — not yet enumerated |
| 0x004A7000 | 0x004A7000+0xEFE4 | 0xEFE4 | reloc | base relocation table (used by `xref.py`) |
| rest of .text/.data | — | — | **unclassified** | |

---

## Key Findings

### Architecture

Ordinary Win32 GDI game: a palettised 8bpp DIB section is composited in
software and blitted with `StretchBlt`. The logical screen is **320×224**
(20×14 tiles of 16×16), derived from the scroll-limit arithmetic in
`load_level` — the map is clamped to `(tiles_w − 20) × 16` horizontally and
`(tiles_h − 14) × 16` vertically.

`load_level` (0x004460E0, 16 callers) is the entry point for level setup:

```
sprintf(g_level_filename, "level%2.2d.ph", g_level_num)     ; 0x004462DB
CreateFileA(name, GENERIC_READ, FILE_SHARE_READ, 0,
            OPEN_EXISTING, FILE_FLAG_SEQUENTIAL_SCAN, 0)     ; 0x00446330
  -> g_level_file                                            ; failure = MessageBoxA + fatal_exit
ReadFile(g_level_file, &g_block_size, 4, ...)                ; 0x004463CD  block length
ReadFile(g_level_file, g_block0_ptr, g_block_size, ...)      ; 0x00446433  block payload
  parse block-0 header  -> g_map_tiles_w/h, g_scroll_max_x/y,
                           g_pixel_data, g_palette           ; 0x00446483..0x004464CB
build_palette_remap(g_palette, pal_count + 1, 1)             ; 0x004464F9
remap every byte in [g_pixel_data, g_palette) through
  g_pal_remap                                                ; 0x0044650E loop
g_next_block_ptr = g_block0_ptr + align16(block_size)        ; 0x00446560
repeat { ReadFile 4-byte length ; ReadFile payload ;
         g_next_block_ptr += align16(length) }               ; 0x00446594 onward
```

When the level has no `.bg` entry in `g_level_assets` the loader takes the
default branch at 0x00446526 and installs constants instead
(`tiles_w=0x28, tiles_h=0x0E, scroll_max=(0x280, 0xE0)`). `LEVEL14.PH`
(`continu`, the continue screen) is exactly this case — its block-0 header is
all zeros.

### Data Structures

#### `.PH` container (VERIFIED — all 26 files parse with zero bytes left over)

A `.PH` file is a flat sequence of length-prefixed blocks, read one after the
other by the loop above:

| Field | Type | Notes |
|-------|------|-------|
| size | u32 | byte length of the payload that follows |
| payload | u8[size] | loaded at the current 16-byte-aligned arena cursor |

repeated until EOF. Block counts range from 2 (`LEVEL19`) to 74 (`LEVEL08`);
`LEVEL00` has 51. Block 0 is the background layer described below; the
remaining blocks correspond to the per-level `.det` / `.dt2` / `.trg` / `.als`
source assets named in `g_level_assets`, in that order, followed by one block
per sprite (the debug string `LoadSprite("%s",&%s_s);\t\t//Level %d` at
0x0046FA88 is the level-editor's code generator for exactly this).

#### `.PH` block 0 — background layer (VERIFIED on all 24 non-empty levels)

Offsets are relative to the start of the block payload (file offset 4).

| Offset | Type | Name | Notes |
|--------|------|------|-------|
| 0x00 | u32 | `cell_w` | map width in **8×8 cells**; tiles across = `cell_w / 2` |
| 0x04 | u32 | `cell_h` | map height in 8×8 cells; tiles down = `cell_h / 2` |
| 0x08 | u32 | `pix_off` | block-relative offset of the 8bpp tile sheet |
| 0x0C | u32 | `pal_off` | block-relative offset of the palette |
| 0x10 | u32 | `pal_count` | number of 3-byte palette entries |
| 0x14 | u16[] | `cellmap` | `cell_w * cell_h` entries, row-major |
| `pix_off` | u8[] | `tiles` | `(pal_off − pix_off) / 64` tiles of 8×8 pixels, 1 byte per pixel |
| `pal_off` | u8[3][] | `palette` | `pal_count` RGB triples, 8 bits per channel |

`pix_off` is always `0x20 + cell_w * cell_h * 2`, i.e. 12 bytes of zero padding
follow the cellmap before the tile sheet.

**cellmap entry** (u16):

| Bits | Meaning |
|------|---------|
| 0–11 | tile index into the 8×8 tile sheet |
| 12–15 | flag nibble — collision / behaviour class |

All 16 nibble values occur across the 24 playable levels. The meaning is
**not yet determined**, but the web port's flag overlay (`web/index.html`,
"flag nibbles") makes the spatial pattern legible, and it is strongly
structured rather than noise:

- On `LEVEL13`, **vertical walls carry 8 and 9** in vertical runs, while the
  **horizontal floor strip carries B, D and F**. Nibble 0 is everything else.
- Levels whose `g_level_assets` entry has **no parallax name** (`temple1`,
  `map1`, `temple3`) have **bit 0 set on every single cell**; levels with a
  parallax layer have thousands of cells at 0.
- `LEVEL21` (the vine intro, one screen tall) is 1785 cells of nibble 0 and
  7 of nibble 1.

**The draw-mode bits are now confirmed from code** (VERIFIED). The per-cell
blitter `blit_cell` (0x00436B2C) receives the whole cell word in `ebx` and
opens with:

```
0x00436B2C  test bh, 0x10          ; bit 12
0x00436B2F  je   blit_cell_mode0   ;   clear -> a different blit path
0x00436B35  test bh, 0x60          ; bits 13-14
0x00436B38  jne  blit_cell_mode2   ;   set -> another blit path
0x00436B3E  and  ebx, 0xFFF        ; tile index
0x00436B44  shl  ebx, 6            ; * 64 bytes per tile
0x00436B47  add  ebx, g_tile_sheet
            ... fully unrolled 8x8 copy, 8 bytes per row, stride 0x1C0
```

| Cell bit | Meaning |
|----------|---------|
| 0–11 | tile index |
| 12 (0x1000) | selects the plain blit; clear routes to `blit_cell_mode0` |
| 13–14 (0x6000) | either set routes to `blit_cell_mode2` |
| 15 (0x8000) | **never tested while drawing** — carries no rendering meaning |

So the nibble is a **draw-mode selector**, not an opacity flag, which is why
the "bit 12 = opacity" experiment deleted the walls: those cells are still
drawn, just by another routine. `blit_cell_mode0` and `blit_cell_mode2` have
not been read yet.

`blit_cell_mode0` (0x00436DF4) is the **masked** blit: `and ebx,0xFFF; je ret`
returns immediately on tile index 0, then each pixel byte is written only if
non-zero (`test al,al; je skip; mov [edi],al`). So **palette index 0 is the
transparent colour**, and a masked cell lets whatever was drawn earlier show
through. This is what the rejected opacity experiment got wrong: those cells
are drawn, just masked, so skipping them deleted the walls.

Bit 15's meaning is **still open**. It is the obvious collision candidate, but
the web port's overlay rules out the simple reading: on `LEVEL13` it covers
exactly the walls and floor, while on `LEVEL00` it marks one tree trunk and
misses platforms Harry plainly stands on. Either collision lives elsewhere
(the `.trg` blocks?) or bit 15 is only one input to it.

**Where the collision search stands.** Not found yet. Ruled out so far:

| Candidate | Result |
|-----------|--------|
| 0x0043305F, the other `g_map_tiles_w` reader | level init: derives world bounds `0x00465BAE/B0 = (tiles x 16) - 0x20`, an entity clamp box in pixels. No cellmap access. |
| `Flags(%d)` in the `BAD-...` debug string | reads `[edi+3]` — a byte in the **alien record**, unrelated to cell flags |
| `g_cell_w` (0x0046B248) readers | all 21 are inside the renderer, 0x004372xx–0x004374xx |
| `g_block0_ptr` (0x00450FC4) readers | only `load_level` and `draw_background` — so collision uses a cached pointer, not this one |
| mask-style bit-15 tests (`test ah,0x80`, `and ax,0x8000`, `bt ...,15`) | **zero hits** in code outside two CRT float routines |

That last one is the useful lead: bit 15 is the **sign bit of the `int16` cell
word**, so a test would be a sign check — `movsx` then `js`/`jns`, or
`cmp word [...],0` / `jl` — not a mask. Search those forms next.

Also worth noting from 0x0042685B: entity positions are **16-bit pixel
coordinates** (0x00465B0F is one) clamped against those world bounds, and that
routine steps by 7 px per frame.

**Verification** — `tools/check_ph.py` confirms for every level file that the
tile sheet is a whole number of 64-byte tiles and that the highest index used
by the cellmap is exactly `tile_count − 1`:

| File | cells | tiles (16px) | 8×8 tiles | max index | colors | blocks |
|------|-------|--------------|-----------|-----------|--------|--------|
| LEVEL00 | 384×130 | 192×65 | 1019 | 1018 | 44 | 51 |
| LEVEL01 | 128×352 | 64×176 | 1114 | 1113 | 61 | 37 |
| LEVEL13 | 64×64 | 32×32 | 34 | 33 | 39 | 12 |
| LEVEL21 | 64×28 | 32×14 | 240 | 239 | 16 | 3 |
| LEVEL24 | 192×120 | 96×60 | 299 | 298 | 21 | 9 |
| LEVEL14 | — | — | — | — | — | — (zero header) |

(Full table: `python3 tools/check_ph.py`.)

#### Layer blocks (VERIFIED)

Blocks other than block 0 can carry the **same layer layout**. `tools/ph_dump.py`
detects them structurally (`pix_off == 0x20 + cell_w*cell_h*2`, palette exactly
`pal_count*3` bytes at the end). Across the 24 non-empty levels there are 46
layer blocks:

- **Block 0** is always the main background.
- **The second layer block is the parallax** named in `g_level_assets`. Proof by
  cross-level sharing: a 64x40 / 570-tile block appears in exactly the four
  levels whose manifest names `clouds.bg`; a 98x64 / 136-tile block in exactly
  the three naming `waterlax.bg`; a 64x32 / 343-tile block in the two naming
  `mine_lax.bg`. The four levels with **no** parallax name (`temple1`, `temple3`,
  `map1`, `gene2600`) have exactly **one** layer block.
- On gameplay levels the parallax sits at **block 5** (blocks 1-4 are the
  non-layer `.det` / `.dt2` / `.trg` / `.als` payloads); on the special screens,
  which have no such assets, it is block 1.
- Further layer blocks (levels 15 and 22) are sparse **foreground detail** —
  vines and grass with mostly transparent cells.

Blocks whose payload begins with **`0x34561234`** are sprite banks — the same
magic that opens `INIT.PH`. Levels 15's blocks 3-5 are of this kind.

#### `g_level_assets` — per-level manifest (VERIFIED)

25 entries of 96 bytes at 0x0046F0D8; each entry is six 16-byte NUL-padded
names. Addressed in code as `byte [eax + eax*2 + 0x46F0D8]` with
`eax = g_level_num << 5`.

| # | bg | parallax | det | dt2 | trg | als |
|---|-----|----------|-----|-----|-----|-----|
| 0 | forest1.bg | for_par.bg | forest1.det | forest1.dt2 | forest1.trg | forest1.als |
| 1 | waterf1.bg | waterlax.bg | … | | | |
| 2 | mine1.bg | mine_lax.bg | | | | |
| 3 | ruins1.bg | clouds.bg | | | | |
| 4 | temple1.bg | *(none)* | | | | |
| 5 | forest2.bg | for_par2.bg | | | | |
| 6 | waterf2.bg | waterlax.bg | | | | |
| 7 | mine2.bg | mine_lax.bg | | | | |
| 8 | ruins2.bg | clouds.bg | | | | |
| 9 | temple2.bg | templax2.bg | | | | |
| 10 | wsarena.bg | clouds.bg | | | | |
| 11–13 | ceil1–3.bg | simon1–3.bg | simon1–3.* | | | |
| 14 | *(none)* | *(none)* | continu.det | continu.dt2 | continu.trg | continu.als |
| 15 | logo2.bg | logo3.bg | — | — | — | — |
| 16 | ruins3.bg | clouds.bg | | | | |
| 17 | temple3.bg | *(none)* | | | | |
| 18 | waterfal.bg | waterlax.bg | | | | |
| 19 | map1.bg | — | — | — | — | — |
| 20 | gene2600.bg | — | — | — | — | — |
| 21 | vines.bg | intro.bg | — | — | — | — |
| 22 | room2.bg | clouds.bg | — | — | — | — |
| 23 | cred1.bg | cred2.bg | — | — | — | — |
| 24 | level22.bg | parlax22.bg | level22.det | level22.dt2 | level22.trg | level22.als |

Levels 15 and 19–23 are non-gameplay screens (logo, world map, the Atari 2600
*Pitfall!* easter egg, the vine intro, the credits). `level22` at index 24 is
the level-editor's working set left in the shipping build.

Reproduce with:
`python3 tools/decode_tables.py 0x0046F0D8 25 'struct:96:str16,str16,str16,str16,str16,str16'`

### Background renderer (VERIFIED by trace)

`draw_background` (0x00436FB4, 2 callers) composites the visible cellmap into
the back buffer each frame. It special-cases levels 0x0B–0x0D (the `simon`
rooms), 0x13 (`map1`), 0x14 (`gene2600`), 0x15 (`vines`) and 0x16 (`room2`),
then falls through to the general path at 0x004371A5:

```
edx = block0[0x00] -> g_cell_w            ; cellmap width
edx = block0[0x04] -> g_cell_h            ; cellmap height
edx = block0[0x08] + block0 -> g_tile_sheet
esi = block0 + cell_col*2 + 0x14          ; cellmap base is block0 + 0x14
edi -= 0x1C0 * (camera_y & 7)             ; back buffer stride is 448 bytes
esi += (cell_w * 2) * cell_row            ; row-major
loop 0x29 = 41 columns:
    ebx = *esi ; esi += 2 ; call blit_cell ; edi += 8
    wrap the column index at g_cell_w      ; the cellmap wraps horizontally
after each row: edi += 0xCB8               ; 0xCB8 + 41*8 = 3584 = 448 * 8
```

Confirmations this yields, independent of `load_level`:

- the cellmap really does start at **block offset 0x14** and is row-major with
  a `cell_w` stride, 2 bytes per cell
- the back buffer row stride is **0x1C0 = 448 bytes** (320 visible + 128 slack)
- 41 columns × 8 px = 328 px drawn per row, one cell more than the 320-px
  viewport, which is what allows sub-cell horizontal scrolling
- the cellmap **wraps horizontally**, so levels scroll around

### State Machine

Not yet mapped. `load_level`'s 16 callers (0x0043A417, 0x0043BA16–0x0043BF5F
in a run of eight, 0x0043C136, 0x0043C802, 0x004410D6, 0x00444766–0x0044487C)
look like the state-transition table for screen changes — the run of eight
consecutive callers 0x0043BA16…0x0043BE3C each set up a different level index.

---

## Intermediate Output Files

| File | Contents |
|------|----------|
| `gfx/<level>_map.png` | full level background composited from cellmap + tiles + palette |
| `gfx/<level>_map_flags.png` | same with the flag nibble overlaid as coloured corner pixels |
| `gfx/<level>_tiles.png` | the 8×8 tile sheet laid out 32 per row, 2× scale |
| `gfx/<level>_palette.png` | palette swatches |
| `gfx/<level>_pixels_WxH.png` | raw tile-sheet bytes as a linear image |

| `web/data/levelNN.png` | 8x8 tile sheet for the web port, 32 tiles per row |
| `web/data/levelNN.bin` | raw cellmap for the web port, `cell_w * cell_h` uint16 |
| `web/data/levels.json` | per-level metadata for the web port |

`gfx/` is regenerated from `game/` by `tools/render_level.py` and
`tools/ph_dump.py --png`, and neither it nor `game/` is committed. `web/data/`
is produced by `tools/export_web.py` and **is** committed, because GitHub Pages
has to serve it.

---

## Verification Checklist

- [x] Ph1: binary identified — PE32/i386/MSVC, entry point and section map recorded
- [x] Ph2: no packing — sections are plain, `.text` disassembles linearly from the entry point
- [ ] Ph3: 3+ functions traced and cross-checked against a running copy
      (1 of 3 done: `load_level` traced end-to-end and statically consistent)
- [x] Ph4: level artwork decoded and visually validated — `LEVEL21` renders as the
      vine curtain named by its manifest entry (`vines.bg`), `LEVEL13` as a walled
      pit with water, both from cellmap + tiles + palette with no manual fixes
- [x] Ph5: `.PH` container and block-0 struct confirmed across all 26 files with
      zero unaccounted bytes and `max cell index == tile count − 1` everywhere
- [ ] Ph6: full game session played, no major logic gaps found
- [ ] Ph7: web port pixel-compared against the original
      (stage 1 done: backgrounds composite and scroll in-browser at 320x224,
      verified in headless Chromium; no player or physics yet)

---

## Reference Resources

- Intel 386 Programmer's Reference — opcode map behind `tools/instruction_set.py`
- PE/COFF specification — section table, base relocations, import descriptors
- The game's own debug strings (0x0046FA88–0x0046FF98) name subsystems:
  `LoadSprite`, `Level %d Alien %d`, `[LEVEL DESIGN]`, `Debug Pitfall`

---

## Next Tasks

### RE Investigation

- [ ] Decode blocks 1..n of a `.PH`: confirm the `.det` / `.dt2` / `.trg` / `.als`
      order against the ReadFile sequence after 0x00446594, and give each its own
      struct table
- [ ] Determine the meaning of the cellmap flag nibbles (8, 9, B, C, D, F) —
      xref the cellmap reader and find the collision test
- [ ] Find the sprite (alien) record format: start from the debug string
      `BAD-%X %X %X %X (%s) Flags(%d) Level %d Alien %d` at 0x0046FAD4 and
      `Stop at %s on Level %d, Alien %d` at 0x0046FF28
- [ ] Trace the blitter: xref `imp_CreateDIBSection` and `imp_StretchBlt` to find
      the frame composition path and confirm the 320×224 logical screen
- [ ] Map the game state machine from `load_level`'s 16 callers
- [ ] Decode `INIT.PH` — different header (`0x34561234` magic at +4), 2 MB, likely
      the shared sprite/sound bank
- [ ] Enumerate `.rsrc` (0x00476000, 0x30C7C) — dialogs, bitmaps, string table
- [ ] Identify the parallax layer: which block holds `for_par.bg` and how it is
      offset per frame
- [ ] Validate `LEVEL19` (`map1.bg`, the world map): it renders as dense Mayan
      stonework with pyramid glyphs rather than a legible map — plausible, but
      cross-check against the running game before trusting the layer assignment
- [ ] Label the 482 call targets that matter: start with the ones reachable from
      `WinMainCRTStartup` and from the window procedure

### Web Port — road to a playable build

Stage 1 (background renderer + asset pipeline + Pages deploy) is done. The
remaining work, in dependency order:

- [ ] **Collision.** Draw-mode bits are resolved; the collision source is not.
      See the elimination table under Data Structures. Next: search for sign
      tests on a 16-bit load (`movsx` + `js`, `cmp word [...],0` + `jl`) rather
      than mask tests, since bit 15 is the cell word's sign bit. Then add
      `web/js/physics.js`. Blocks everything else.
- [ ] Read `blit_cell_mode0` (0x00436DF4) and `blit_cell_mode2` (0x00436BD8) —
      almost certainly the transparent/masked variants, needed for correct
      layering in the port
- [ ] Find the per-layer **scroll rate**. All layers currently use the same
      camera; `draw_background` reads a second camera pair (0x0046FBA8 /
      0x0046FBAC) on some paths, which is probably it.
- [ ] Confirm the layer **draw order** against `draw_background`'s two callers.
      The port infers parallax-behind / detail-in-front from the data.
- [ ] Read `blit_cell_mode2` (0x00436BD8) — the bits 13-14 variant, currently
      treated as masked
- [ ] **Web port performance**: compositing whole levels up front costs 2.8s for
      `forest1` on mobile. Blit only the visible 41x29 cells per frame, the way
      `draw_background` does, instead of pre-flattening the level.
- [ ] Decode the `.als` sprite blocks; render Harry and the entities
- [ ] Extract the movement constants (walk/run speed, jump impulse, gravity)
      from the physics code
- [ ] Decode the `.trg` trigger blocks — level transitions, hazards, pickups
- [ ] Wire the state machine from `load_level`'s 16 callers so levels connect

### Documentation

- [ ] `docs/architecture_exe.md` — expand the call graph beyond `load_level`
- [ ] `docs/architecture_web.md` — write once a web module structure exists
