// Level loading and background compositing.
//
// The browser rebuilds the background the same way load_level (0x004460E0) does:
// an 8x8 tile sheet indexed by a cell_w * cell_h array of uint16 cells, where
// the low 12 bits are the tile index. Nothing is pre-flattened, so the tile
// indices and flag nibbles stay available for collision work.

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
 * Composite the whole level into one canvas by copying 8x8 blocks out of the
 * tile sheet. Done once at load; the frame loop only blits a camera rect.
 */
function composite(meta, sheet) {
  const { cell_w: cw, cell_h: ch, px_w: W, px_h: H } = meta;
  const out = new ImageData(W, H);
  const dst = out.data, src = sheet.data;
  const sheetW = sheet.width;

  for (let cy = 0; cy < ch; cy++) {
    for (let cx = 0; cx < cw; cx++) {
      const v = meta.cells[cy * cw + cx];
      const idx = v & 0x0fff;
      if (idx >= meta.tile_count) continue;
      const sx = (idx % SHEET_COLS) * 8;
      const sy = ((idx / SHEET_COLS) | 0) * 8;
      for (let y = 0; y < 8; y++) {
        let s = ((sy + y) * sheetW + sx) * 4;
        let d = ((cy * 8 + y) * W + cx * 8) * 4;
        for (let x = 0; x < 8; x++) {
          dst[d] = src[s];
          dst[d + 1] = src[s + 1];
          dst[d + 2] = src[s + 2];
          dst[d + 3] = 255;
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

export async function loadLevel(entry, base = 'data') {
  if (entry.empty) throw new Error(`level ${entry.n} has no background layer`);
  const t0 = performance.now();
  const [img, cellsBuf] = await Promise.all([
    loadImage(`${base}/${entry.sheet}`),
    fetch(`${base}/${entry.cells}`).then(r => {
      if (!r.ok) throw new Error(`${entry.cells}: HTTP ${r.status}`);
      return r.arrayBuffer();
    }),
  ]);
  const meta = { ...entry, cells: new Uint16Array(cellsBuf) };
  const canvas = composite(meta, imageData(img));
  meta.canvas = canvas;
  meta.loadMs = Math.round(performance.now() - t0);
  return meta;
}

/** Cell word at a pixel position, or 0 outside the map. */
export function cellAt(level, px, py) {
  const cx = px >> 3, cy = py >> 3;
  if (cx < 0 || cy < 0 || cx >= level.cell_w || cy >= level.cell_h) return 0;
  return level.cells[cy * level.cell_w + cx];
}
