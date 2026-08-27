# PITFALL.EXE — binary architecture

Status: **partial**. The level-loading path is traced end to end; the render
loop, input, sprite system and state machine are not yet mapped.

## Image layout

PE32, i386, image base `0x00400000`, entry `0x0044A8FF`, built 1995-08-23 with
Microsoft C/C++ (linker 2.55).

```
0x00400000  headers        0x400
0x00401000  .text          0x4E3C4   code — 482 distinct rel32 call targets
0x00450000  .bss           0x473C    globals, level pointers, LoadStringA buffers
0x00455000  .rdata         0x230
0x00456000  .data          0x1D1B4   level manifest, literals, static tables
0x00474000  .idata         0x11EE    180 import thunks (labelled imp_*)
0x00476000  .rsrc          0x30C7C   dialogs, bitmaps, strings, menus
0x004A7000  .reloc         0xF686    base relocations (drives xref.py)
```

No packing: `.text` decodes linearly from the entry point with the from-scratch
decoder in `tools/instruction_set.py`, so phase 2 (decompress) is a no-op for
this binary.

## Subsystem map from imports

| Subsystem | Evidence |
|-----------|----------|
| Video | GDI32 `CreateDIBSection`, `SetDIBColorTable`, `SetDIBits`, `StretchBlt`, `BitBlt`, `CreatePalette`, `RealizePalette`, `AnimatePalette`, `SetSystemPaletteUse` — software-composited 8bpp DIB, stretched to the window |
| Audio | WINMM `sndPlaySoundA`, `mciSendCommandA`, `waveOutGetNumDevs`, `timeSetEvent`/`timeKillEvent`; plus `WAIL32.DLL` for music |
| Input | USER32 `GetAsyncKeyState`; WINMM `joyGetPos`, `joySetCapture`, `joyGetDevCaps` |
| Timing | WINMM `timeGetTime`, `timeBeginPeriod`, `timeSetEvent` — the frame clock |
| Config | ADVAPI32 `RegOpenKeyA`/`RegQueryValueExA`/`RegSetValueExA` — settings in the registry |
| UI | USER32 dialogs + COMCTL32 `PropertySheetA` — the options property sheet |

## Entry path

```
0x0044A8FF  WinMainCRTStartup
              fs:[0] SEH frame, __except handler table at 0x0044C8E8
              GetVersion -> 0x00471240/44/48/4C (version globals)
              0x0044C83D  CRT heap/IO init
              0x0044AE55  CRT init; failure -> exit(0x10)
              ... (not yet traced to WinMain)
```

## Level loading — `load_level` @ 0x004460E0 (VERIFIED by trace)

16 callers, all in the 0x0043A417–0x0044487C range; the run of eight consecutive
callers at 0x0043BA16…0x0043BE3C looks like a screen-transition table.

```
0x004460E0  prologue: sub esp, 0x218 ; several .data flags cleared
0x004462DB  eax = g_level_num
            sprintf(local, "level%2.2d.ph", eax)
0x004462F0  inline strlen + rep movsd -> g_level_filename (0x004502B0)
0x00446330  CreateFileA(g_level_filename,
                        GENERIC_READ, FILE_SHARE_READ, NULL,
                        OPEN_EXISTING, FILE_FLAG_SEQUENTIAL_SCAN, NULL)
            -> g_level_file ; INVALID_HANDLE_VALUE -> MessageBoxA + fatal_exit
0x00446385  if g_level_assets[g_level_num].bg[0] == 0 -> 0x00446526 (defaults)
0x004463CD  ReadFile(g_level_file, &g_block_size, 4, &n, NULL)   ; block length
0x00446433  ReadFile(g_level_file, g_block0_ptr, g_block_size, &n, NULL)
0x00446483  parse block-0 header:
              g_map_tiles_w = cell_w / 2                (0x00450FB4)
              g_map_tiles_h = cell_h / 2                (0x00450FB0)
              g_scroll_max_x = (g_map_tiles_w - 20) * 16 (0x00450FB8)
              g_scroll_max_y = (g_map_tiles_h - 14) * 16 (0x00450FBC)
              g_pixel_data   = block0 + pix_off          (0x00450298)
              g_palette      = block0 + pal_off          (0x004502A0)
0x004464F9  build_palette_remap(g_palette, pal_count + 1, 1)  -> g_pal_remap
0x0044650E  for (p = g_pixel_data; p != g_palette; p++)
                *p = g_pal_remap[*p]          ; retint the tile sheet
0x00446526  (no-background path) constants:
              tiles_w=0x28 tiles_h=0x0E scroll_max=(0x280, 0xE0)
0x00446560  g_next_block_ptr = g_block0_ptr + ((block_size + 15) & ~15)
0x00446594  per remaining asset slot, if g_level_assets[level][slot][0] != 0:
              ReadFile 4-byte length -> g_block_size
              ReadFile g_block_size bytes -> g_next_block_ptr
              g_next_block_ptr += align16(g_block_size)
            slots are addressed as byte [eax + eax*2 + 0x0046F0D8 + slot*0x10]
            with eax = g_level_num << 5; observed slots 0x00 (.bg), 0x40 (.trg),
            0x50 (.als), 0x28/0x30 for the detail layers.
```

The 20 × 14 tile constants in the scroll clamp fix the logical screen at
**320 × 224**. `LEVEL21` (the vine intro, 32 × 14 tiles) has
`scroll_max_y == 0`, i.e. exactly one screen tall — an independent confirmation.

Every error path is the same three-step idiom: `sprintf` into a stack buffer
with the `LoadStringA`-loaded format at `g_str_load_error`, `MessageBoxA` with
`g_hwnd_main` and the caption at `g_str_msgbox_title`, then `fatal_exit`
(0x0043C820).

## Shared data regions

| VA | Name | Notes |
|----|------|-------|
| 0x00451A2C | `g_level_num` | current level 0..24, index into `g_level_assets` |
| 0x0046F0D8 | `g_level_assets` | 25 × 6 × 16 bytes of asset names (see REVERSE.md) |
| 0x004504E0 | `g_level_heap` | arena base for all `.PH` blocks |
| 0x00450FC4 | `g_block0_ptr` | block-0 payload |
| 0x00450510 | `g_next_block_ptr` | 16-byte-aligned cursor for blocks 1..n |
| 0x004503C0 | `g_pal_remap` | 256-byte index translation table |
| 0x0046D3CC | `g_hwnd_main` | main window handle |

## Not yet mapped

- `WinMain` and the window procedure
- the frame loop: `timeSetEvent` callback vs. message-pump driven
- the blitter — start from xrefs to `imp_CreateDIBSection` and `imp_StretchBlt`
- sprite ("alien") records and the `.als` block format
- the cellmap collision test that consumes the flag nibbles
- `INIT.PH` (2 MB, `0x34561234` magic at +4) — probably the shared sprite bank
- `.rsrc` contents
