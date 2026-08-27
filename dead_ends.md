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
