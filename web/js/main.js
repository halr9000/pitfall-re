// Pitfall: The Mayan Adventure — web port, stage 1: level explorer.
//
// Renders the decoded background at the game's own 320x224 logical resolution
// and scrolls it within the scroll limits the original computes in load_level.
// There is no player or physics yet — see REVERSE.md for what still has to be
// reverse-engineered before there is a game here.

import { loadManifest, loadLevel, cellAt } from './level.js';

const SCREEN_W = 320, SCREEN_H = 224;

const canvas = document.getElementById('screen');
const ctx = canvas.getContext('2d');
ctx.imageSmoothingEnabled = false;

const ui = {
  level: document.getElementById('level'),
  status: document.getElementById('status'),
  info: document.getElementById('info'),
  flags: document.getElementById('flags'),
  solid: document.getElementById('solid'),
  grid: document.getElementById('grid'),
  probe: document.getElementById('probe'),
};

const state = {
  manifest: null,
  level: null,
  camX: 0, camY: 0,
  speed: 3,
  keys: new Set(),
  mouse: null,
  fps: 0, frames: 0, fpsAt: 0,
};

// Debug palette for the unresolved cellmap flag nibble.
const FLAG_COLORS = [
  null, '#ff3b30', '#ff9500', '#ffcc00', '#34c759', '#00c7be', '#30b0c7',
  '#32ade6', '#007aff', '#5856d6', '#af52de', '#ff2d55', '#a2845e',
  '#8e8e93', '#ffffff', '#000000',
];

addEventListener('keydown', e => {
  if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', ' '].includes(e.key)) e.preventDefault();
  state.keys.add(e.key.length === 1 ? e.key.toLowerCase() : e.key);
});
addEventListener('keyup', e => state.keys.delete(e.key.length === 1 ? e.key.toLowerCase() : e.key));
addEventListener('blur', () => state.keys.clear());

canvas.addEventListener('mousemove', e => {
  const r = canvas.getBoundingClientRect();
  state.mouse = {
    x: Math.floor((e.clientX - r.left) / r.width * SCREEN_W),
    y: Math.floor((e.clientY - r.top) / r.height * SCREEN_H),
  };
});
canvas.addEventListener('mouseleave', () => { state.mouse = null; });

function held(...keys) {
  return keys.some(k => state.keys.has(k));
}

async function select(n) {
  const entry = state.manifest.levels.find(L => L.n === n);
  if (!entry) return;
  ui.status.textContent = `loading level ${String(n).padStart(2, '0')}…`;
  if (entry.empty) {
    state.level = null;
    ui.status.textContent =
      `level ${String(n).padStart(2, '0')} (${entry.bg || 'continue screen'}) ` +
      `has a zero block-0 header — the original falls back to built-in defaults`;
    ui.info.textContent = '';
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, SCREEN_W, SCREEN_H);
    return;
  }
  try {
    const lv = await loadLevel(entry);
    state.level = lv;
    state.camX = state.camY = 0;
    ui.status.textContent = '';
    const stack = lv.layers.map((L, i) =>
      `L${i} blk${L.block} ${L.px_w}×${L.px_h} ${L.tile_count}t/${L.palette.length}c`
    ).join(' · ');
    ui.info.innerHTML =
      `<b>${lv.bg}</b> · ${lv.px_w}×${lv.px_h}px · ${lv.tiles_w}×${lv.tiles_h} tiles · ` +
      `parallax <b>${lv.parallax || '—'}</b> · ${lv.blocks} blocks · ` +
      `${lv.layers.length} layer${lv.layers.length > 1 ? 's' : ''} (${stack}) · ` +
      `composited in ${lv.loadMs}ms`;
    location.hash = `#${n}`;
  } catch (err) {
    ui.status.textContent = `error: ${err.message}`;
  }
}

function update(dt) {
  const lv = state.level;
  if (!lv) return;
  const boost = held('Shift') ? 4 : 1;
  const v = state.speed * boost * dt * 60;
  if (held('ArrowLeft', 'a')) state.camX -= v;
  if (held('ArrowRight', 'd')) state.camX += v;
  if (held('ArrowUp', 'w')) state.camY -= v;
  if (held('ArrowDown', 's')) state.camY += v;
  // The original clamps to (tiles - viewport) * 16; mirror that exactly.
  state.camX = Math.max(0, Math.min(lv.scroll_max_x, state.camX));
  state.camY = Math.max(0, Math.min(lv.scroll_max_y, state.camY));
}

// The cellmap wraps horizontally (draw_background resets the column index at
// g_cell_w), so a layer smaller than the level repeats rather than running out.
// The per-layer scroll rate is still unknown, so every layer uses the same
// camera for now; layers the same size as layer 0 are correct either way.
function drawLayer(L, ox, oy) {
  const W = L.px_w, H = L.px_h;
  for (let dy = -(oy % H); dy < SCREEN_H; dy += H) {
    for (let dx = -(ox % W); dx < SCREEN_W; dx += W) {
      ctx.drawImage(L.canvas, dx, dy);
    }
  }
}

function drawFlags(lv, ox, oy) {
  const L = lv.layers[0];
  const c0 = ox >> 3, c1 = Math.min(L.cell_w - 1, (ox + SCREEN_W) >> 3);
  const r0 = oy >> 3, r1 = Math.min(L.cell_h - 1, (oy + SCREEN_H) >> 3);
  ctx.globalAlpha = 0.55;
  for (let cy = r0; cy <= r1; cy++) {
    for (let cx = c0; cx <= c1; cx++) {
      const nib = L.cells[cy * L.cell_w + cx] >> 12;
      const col = FLAG_COLORS[nib];
      if (!col) continue;
      ctx.fillStyle = col;
      ctx.fillRect(cx * 8 - ox, cy * 8 - oy, 8, 8);
    }
  }
  ctx.globalAlpha = 1;
}

// Cell bit 15 (0x8000) is the one nibble bit the tile blitter at 0x00436B2C
// never tests, so it carries no drawing meaning. What it *does* mean is still
// open: on LEVEL13 it covers exactly the walls and floor, but on LEVEL00 it
// misses obvious platforms, so it is not the whole collision map. Overlay kept
// as an investigation aid. See REVERSE.md.
function drawSolid(lv, ox, oy) {
  const L = lv.layers[0];
  const c0 = ox >> 3, c1 = Math.min(L.cell_w - 1, (ox + SCREEN_W) >> 3);
  const r0 = oy >> 3, r1 = Math.min(L.cell_h - 1, (oy + SCREEN_H) >> 3);
  ctx.globalAlpha = 0.45;
  ctx.fillStyle = '#ff2d55';
  for (let cy = r0; cy <= r1; cy++) {
    for (let cx = c0; cx <= c1; cx++) {
      if (L.cells[cy * L.cell_w + cx] & 0x8000) {
        ctx.fillRect(cx * 8 - ox, cy * 8 - oy, 8, 8);
      }
    }
  }
  ctx.globalAlpha = 1;
}

function drawGrid(ox, oy) {
  ctx.strokeStyle = 'rgba(255,255,255,.18)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let x = -(ox % 16); x <= SCREEN_W; x += 16) {
    ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, SCREEN_H);
  }
  for (let y = -(oy % 16); y <= SCREEN_H; y += 16) {
    ctx.moveTo(0, y + 0.5); ctx.lineTo(SCREEN_W, y + 0.5);
  }
  ctx.stroke();
}

function render() {
  const lv = state.level;
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, SCREEN_W, SCREEN_H);
  if (!lv) return;
  const ox = Math.round(state.camX), oy = Math.round(state.camY);
  for (const L of lv.order) drawLayer(L, ox, oy);
  if (ui.solid.checked) drawSolid(lv, ox, oy);
  if (ui.flags.checked) drawFlags(lv, ox, oy);
  if (ui.grid.checked) drawGrid(ox, oy);

  if (state.mouse) {
    const px = ox + state.mouse.x, py = oy + state.mouse.y;
    const v = cellAt(lv, px, py);
    ui.probe.textContent =
      `px ${px},${py}  cell ${px >> 3},${py >> 3}  ` +
      `word 0x${v.toString(16).padStart(4, '0')}  ` +
      `tile ${v & 0xfff}  flags 0x${(v >> 12).toString(16).toUpperCase()}`;
  } else {
    ui.probe.textContent = `camera ${ox},${oy} / ${lv.scroll_max_x},${lv.scroll_max_y}`;
  }
}

let last = performance.now();
function frame(now) {
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  update(dt);
  render();
  state.frames++;
  if (now - state.fpsAt > 500) {
    state.fps = Math.round(state.frames * 1000 / (now - state.fpsAt));
    state.frames = 0;
    state.fpsAt = now;
    document.getElementById('fps').textContent = `${state.fps} fps`;
  }
  requestAnimationFrame(frame);
}

(async function boot() {
  try {
    state.manifest = await loadManifest();
  } catch (err) {
    ui.status.innerHTML =
      `<b>Could not load data/levels.json (${err.message}).</b><br>` +
      `Put the retail files in <code>game/</code> and run ` +
      `<code>python3 tools/export_web.py</code>, then serve with ` +
      `<code>python3 -m http.server 8000</code>.`;
    return;
  }
  for (const L of state.manifest.levels) {
    const o = document.createElement('option');
    o.value = L.n;
    o.textContent = `${String(L.n).padStart(2, '0')} — ${L.bg || '(no background)'}` +
      (L.empty ? '  [empty]' : '');
    ui.level.append(o);
  }
  ui.level.onchange = () => select(Number(ui.level.value));
  const want = Number(location.hash.slice(1));
  const start = state.manifest.levels.some(L => L.n === want && !L.empty) ? want : 0;
  ui.level.value = start;
  await select(start);
  requestAnimationFrame(frame);
})();
