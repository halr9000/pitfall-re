// Level loading and layer compositing.
//
// Mirrors the original's draw path. draw_background (0x00436FB4) walks the
// cellmap and calls blit_cell (0x00436B2C) per 8x8 cell, which branches on the
// cell word's high bits:
//
//   bit 12 set    -> opaque copy, every pixel written
//   bit 12 clear  -> masked copy: palette index 0 is transparent, and tile
//                    index 0 returns immediately (nothing drawn at all)
//   bits 13-14    -> blit_cell_mode2 (0x00436BD8), not yet read; treated as
//                    masked here
//
// Layer draw order, back to front: layer 1 (the parallax named in
// g_level_assets) first, then layer 0, then any further layers on top. Layer 1
// is always the parallax — identified by cross-level sharing, e.g. the same
// 64x40 / 570-tile block appears in exactly the four levels whose manifest
// names clouds.bg. Layers 2+ are sparse foreground detail (vines, grass) and
// go in front. This ordering is inferred from the data, not yet confirmed
// against draw_background's two callers.

const SHEET_COLS = 32;

export async function loadManifest(base = 'data') {
  const r = await fetch(`${base}/levels.json`);
  if (!r.ok) throw new Error(`levels.json: HTTP ${r.status}`);
  return r.json();
}

function imageData(img) {
  const c = document.createElement('canvas');
  c.width = img.width;
  c.height = img.height;
  const g = c.getContext('2d', { willReadFrequently: true });
  g.drawImage(img, 0, 0);
  return g.getImageData(0, 0, img.width, img.height);
}

function loadImage(src) {
  return new Promise((res, rej) => {
    const img = new Image();
    img.onload = () => res(img);
    img.onerror = () => rej(new Error(`image: ${src}`));
    img.src = src;
  });
}

/**
 * Composite one layer into an RGBA canvas. Masked cells leave alpha 0 so the
 * layer beneath shows through. The exporter marks palette index 0 transparent
 * in the sheet PNG, so a zero alpha in the source means "index 0".
 */
function compositeLayer(meta, cells, sheet) {
  const { cell_w: cw, cell_h: ch } = meta;
  const W = cw * 8, H = ch * 8;
  const out = new ImageData(W, H);
  const dst = out.data, src = sheet.data;
  const sheetW = sheet.width;

  for (let cy = 0; cy < ch; cy++) {
    for (let cx = 0; cx < cw; cx++) {
      const v = cells[cy * cw + cx];
      const idx = v & 0x0fff;
      const opaque = (v & 0x1000) !== 0;
      // masked cell with tile 0 draws nothing at all (blit_cell_mode0 early-out)
      if (!opaque && idx === 0) continue;
      if (idx >= meta.tile_count) continue;
      const sx = (idx % SHEET_COLS) * 8;
      const sy = ((idx / SHEET_COLS) | 0) * 8;
      for (let y = 0; y < 8; y++) {
        let s = ((sy + y) * sheetW + sx) * 4;
        let d = ((cy * 8 + y) * W + cx * 8) * 4;
        for (let x = 0; x < 8; x++) {
          // alpha 0 in the sheet == palette index 0 == transparent
          if (opaque || src[s + 3] !== 0) {
            dst[d] = src[s];
            dst[d + 1] = src[s + 1];
            dst[d + 2] = src[s + 2];
            dst[d + 3] = 255;
          }
          s += 4; d += 4;
        }
      }
    }
  }
  const c = document.createElement('canvas');
  c.width = W;
  c.height = H;
  c.getContext('2d').putImageData(out, 0, 0);
  return c;
}

async function loadLayer(spec, base) {
  const [img, buf] = await Promise.all([
    loadImage(`${base}/${spec.sheet}`),
    fetch(`${base}/${spec.cells}`).then(r => {
      if (!r.ok) throw new Error(`${spec.cells}: HTTP ${r.status}`);
      return r.arrayBuffer();
    }),
  ]);
  const cells = new Uint16Array(buf);
  return { ...spec, cells, canvas: compositeLayer(spec, cells, imageData(img)) };
}

export async function loadLevel(entry, base = 'data') {
  if (entry.empty) throw new Error(`level ${entry.n} has no layer blocks`);
  const t0 = performance.now();
  const layers = await Promise.all(entry.layers.map(L => loadLayer(L, base)));
  const order = layers.length > 1
    ? [layers[1], layers[0], ...layers.slice(2)]
    : [...layers];
  return { ...entry, layers, order, loadMs: Math.round(performance.now() - t0) };
}

/** Cell word in layer 0 at a pixel position, or 0 outside the map. */
export function cellAt(level, px, py) {
  const L = level.layers[0];
  const cx = px >> 3, cy = py >> 3;
  if (cx < 0 || cy < 0 || cx >= L.cell_w || cy >= L.cell_h) return 0;
  return L.cells[cy * L.cell_w + cx];
}
