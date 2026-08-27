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
