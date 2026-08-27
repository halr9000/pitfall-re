# Web port — architecture

Status: **stage 1 of 4**. The asset pipeline and background renderer are done and
deployable. There is no player, no physics and no sprites yet.

Plain ES modules, no bundler, no dependencies. Served as static files; deployed
to GitHub Pages from `web/` by `.github/workflows/pages.yml`.

## Module graph

```
web/index.html
  └── js/main.js          (entry, ES module)
        ├── loadManifest  ─┐
        ├── loadLevel      ├── js/level.js
        └── cellAt        ─┘
```

| Module | Exports | Responsibility |
|--------|---------|----------------|
| `js/level.js` | `loadManifest`, `loadLevel`, `cellAt` | fetch the bundle, composite the background, expose cell lookup |
| `js/main.js` | — | camera, input, frame loop, debug overlays, level picker |

`level.js` holds no DOM state beyond the offscreen canvas it builds; `main.js`
owns everything user-facing. Collision and entities will slot in as
`js/physics.js` and `js/sprites.js` alongside `level.js`, both consuming
`cellAt`.

## Asset bundle

`tools/export_web.py` writes `web/data/`:

| File | Contents |
|------|----------|
| `levels.json` | per-level metadata: dimensions, scroll limits, tile count, palette, flag histogram |
| `levelNN.png` | 8×8 tile sheet, 32 tiles per row, indexed PNG in the level's own palette |
| `levelNN.bin` | raw cellmap, `cell_w * cell_h` little-endian `uint16` |

25 levels, ~1.9 MB total. Deliberately **not** pre-flattened screenshots: the
browser composites from tile sheet + cellmap the way the original does, so the
tile indices and flag nibbles survive into the port for collision work.

## EXE → web mapping

| Original | Web port |
|----------|----------|
| `load_level` @ 0x004460E0 — `CreateFileA` + block read loop | `tools/export_web.py` (offline) + `loadLevel()` (fetch) |
| block-0 header parse @ 0x00446483 | `levels.json` fields, precomputed |
| `g_map_tiles_w/h` (0x00450FB4 / 0x00450FB0) | `tiles_w`, `tiles_h` |
| `g_scroll_max_x/y` = `(tiles − 20/14) × 16` | `scroll_max_x`, `scroll_max_y`, clamped in `update()` |
| 8bpp DIB + `SetDIBColorTable` + `StretchBlt` | `ImageData` composite + `drawImage` of the camera rect onto a 320×224 canvas, CSS-scaled with `image-rendering: pixelated` |
| `build_palette_remap` + the retint loop @ 0x0044650E | not needed — the exporter bakes the level palette into the PNG |
| `g_level_num` (0x00451A2C) | `location.hash` / the level `<select>` |

The palette remap is a Windows-palette-management artifact (the original had to
share a 256-entry system palette with GDI). A browser canvas has no such
constraint, so the exporter resolves it statically. That is the one place the
port deliberately diverges from the original's behaviour.

## Frame loop

```
requestAnimationFrame(frame)
  dt clamped to 50ms
  update(dt)   camera from held keys, clamped to scroll_max_x/y
  render()     fill black
               drawImage(level.canvas, camX, camY, 320, 224 -> 0,0,320,224)
               optional flag-nibble overlay
               optional 16px tile grid
               cell probe readout under the cursor
```

Compositing cost measured in headless Chromium: 20 ms for `LEVEL13`
(512×512), 252 ms for `LEVEL00` (3072×1040). One-off at level load; the frame
loop is a single `drawImage`.

## State machine

Not yet implemented. Today the only state is "which level is loaded", driven by
the picker and the URL hash. The original's screen flow — traced through
`load_level`'s 16 callers — has to be mapped before the port needs more.

## Remaining stages

2. **Collision** — resolve the cellmap flag nibble, add `js/physics.js`, and give
   the camera a player box that stands on the floor.
3. **Sprites** — decode the `.als` / detail blocks, render Harry and the
   entities, animate them.
4. **Game** — movement constants, triggers (`.trg`), level transitions, scoring.
