# Dead Ends & Investigation Notes

Read before starting a session. Append when stuck after 10+ tool calls with no progress.

Lifecycle: **Active** -> **Resolved** (prefix with RESOLVED + date once understood) -> delete after 20+ sessions.

## Entry format

## <Subsystem or Function Name>
- **Tried**: what approach was attempted
- **Failed because**: root cause of failure
- **Better approach**: what to do instead
- **Session**: NNN

---

## RESOLVED 2026-08-27 — .PH block-0 map start offset
- **Tried**: guessing whether the cellmap begins at block offset 0x14 or 0x20, from
  the header arithmetic alone (`pix_off == 0x20 + cell_w*cell_h*2` is consistent
  with either, since the two differ by exactly the 12 trailing bytes).
- **Failed because**: both readings satisfy the size equation.
- **Resolved by**: hexdumping the tail of LEVEL00.PH's map region. Non-zero cell
  words stop at file 0x18618 == 0x18 + cell_w*cell_h*2, so the map starts at block
  offset 0x14 (file 0x18) and 12 zero bytes pad up to `pix_off`. Confirmed for all
  24 non-empty levels by `tools/check_ph.py` (max cell index == tile count - 1).
- **Session**: 001

## Cellmap flag nibble — "bit 0 = opacity" hypothesis
- **Tried**: reading bit 0 of the cellmap flag nibble as an opacity/draw bit. The
  motivation was that levels with no parallax entry in `g_level_assets`
  (`temple1`, `map1`, `temple3`) have bit 0 set on *every* cell, while levels
  with a parallax layer have thousands of cells at nibble 0.
- **Failed because**: rendering with it (`render_level.py --alpha`) deletes the
  level. On LEVEL13 only 153 of 4096 cells survive — the vertical walls are
  nibble 8 and C (bit 0 clear) yet are plainly drawn in the correct render.
  Whatever bit 0 means, it is not "draw this cell".
- **Better approach**: stop guessing from statistics. xref the cellmap reader —
  find the code that indexes `g_block0_ptr + 0x14` (or a derived pointer) with a
  camera position, and read what it does with `v >> 12`. The blitter and the
  collision test are probably two separate consumers of the same word.
- **Session**: 002

## Cellmap bit 15 as the collision map
- **Tried**: after reading `blit_cell` (0x00436B2C) and finding bit 15 is the one
  cell bit the blitter never tests, taking it as the solidity/collision bit.
- **Failed because**: the web port's `solid cells` overlay contradicts it. On
  LEVEL13 bit 15 covers exactly the walls and floor, but on LEVEL00 it marks one
  tree trunk and misses branch platforms that are obviously standable.
- **Better approach**: find the *other* cellmap consumer. `g_map_tiles_w`
  (0x00450FB4) is read from only two places outside `load_level`; 0x00433060 is
  the one that is not the renderer. Read that. Also consider that collision may
  come from the `.trg` blocks rather than the cellmap at all.
- **Session**: 002

## RESOLVED 2026-08-27 (data side) — which cell bit is solid
- Bit **12** is the collision map, not bit 15. Proven from code to select the
  opaque blit; empirically its mask is a textbook platformer collision map on
  both LEVEL00 and LEVEL24 while decoration is excluded. The collision *test* in
  the binary is still unlocated, so this remains inference.

## Collision test — first search pass
- **Tried**: four routes to the code that reads the cellmap for collision —
  the second `g_map_tiles_w` consumer (0x0043305F), the `Flags(%d)` debug
  string, the readers of `g_cell_w` and of `g_block0_ptr`, and a byte search for
  mask-style bit-15 tests.
- **Failed because**: 0x0043305F is level init computing world bounds;
  `Flags(%d)` is a byte in the alien record at `[edi+3]`, not a cell flag; every
  `g_cell_w` reader is inside the renderer; `g_block0_ptr` is read only by
  `load_level` and `draw_background`. So collision works from a cached pointer
  this search did not reach.
- **Better approach**: bit 15 is the **sign bit** of the int16 cell word, and
  there are no mask-style tests of it anywhere in the binary. Look for
  `movsx r32, word` followed by a sign branch, or `cmp word [...], 0` + `jl`.
  Separately, come at it from the player: 0x00465B0F is a 16-bit pixel X
  clamped against the world bounds at 0x00465BAE — find who writes it during
  normal play, not the 7px debug mover at 0x00426810.
- **Session**: 002

## Animation scripts read as (command, operand) pairs
- **Tried**: splitting each 0xFF-terminated script record into 2-byte
  (command, operand) pairs, which fitted LEVEL13's short records neatly.
- **Failed because**: the opcode histogram across all levels came out flat —
  roughly 80 distinct "commands" each with ~80 distinct "operands" and similar
  frequencies. A bytecode has a small opcode set with skewed frequencies; that
  shape means the split itself was wrong.
- **Resolved by**: reading `anim_advance` (0x00401DBC). A script is a flat byte
  stream — each byte under 0xF0 is a frame index, 0xFE takes one argument byte,
  0xF0 loops, 0xFF ends. The per-frame hold time is an entity field, not script
  data, which is why no "duration" operand was ever there to find.
- **Session**: 003
