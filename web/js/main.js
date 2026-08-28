// Pitfall: The Mayan Adventure — web port, stage 1: level explorer.
//
// Renders the decoded background at the game's own 320x224 logical resolution
// and scrolls it within the scroll limits the original computes in load_level.
// There is no player or physics yet — see REVERSE.md for what still has to be
// reverse-engineered before there is a game here.

import { loadManifest, loadLevel, cellAt } from './level.js';
import { makePlayer, findSpawn, step, px, TUNING, SOLID_BIT } from './physics.js';
import { loadSprites, drawFrame } from './sprites.js';
import { Demo } from './demo.js';

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
  play: document.getElementById('play'),
  demo: document.getElementById('demo'),
};

const demo = new Demo();

function setDemo(on) {
  demo.active = on;
  if (on) {
    demo.reset();
    ui.play.checked = true;      // the demo only means anything in play mode
  }
  ui.demo.textContent = on ? '\u23F8\uFE0E Stop' : '\u25B6\uFE0E Demo';
  ui.demo.setAttribute('aria-pressed', String(on));
}
ui.demo.addEventListener('click', () => setDemo(!demo.active));

const state = {
  manifest: null,
  level: null,
  camX: 0, camY: 0,
  speed: 3,
  keys: new Set(),
  mouse: null,
  fps: 0, frames: 0, fpsAt: 0,
  player: null,
  acc: 0,
  sprites: null,
  animT: 0,
  idleT: 0,
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
  if (demo.active) setDemo(false);    // a real key press always wins
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
    const sp = findSpawn(lv);
    state.player = makePlayer(sp.x, sp.y);
    if (demo.active) demo.reset();
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

const FIXED = 1 / 60;

function centreCamera(lv) {
  const p = state.player;
  state.camX = Math.max(0, Math.min(lv.scroll_max_x, px(p.x) + p.w / 2 - SCREEN_W / 2));
  state.camY = Math.max(0, Math.min(lv.scroll_max_y, px(p.y) + p.h / 2 - SCREEN_H / 2));
}

function update(dt) {
  const lv = state.level;
  if (!lv) return;

  if (ui.play.checked && state.player) {
    // fixed 60Hz steps so physics does not vary with frame rate
    state.acc = Math.min(state.acc + dt, 0.25);
    const input = demo.poll(dt, state.player, px) || {
      left: held('ArrowLeft', 'a'),
      right: held('ArrowRight', 'd'),
      jump: held(' ', 'ArrowUp', 'w'),
      run: held('Shift'),
    };
    while (state.acc >= FIXED) {
      step(lv, state.player, input);
      state.acc -= FIXED;
    }
    if (state.player.vx !== 0 && state.player.onGround) state.animT += dt;
    else state.idleT += dt;
    centreCamera(lv);
    return;
  }

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

// Harry, drawn from the banks the game itself names. The name -> INIT.PH block
// mapping comes from replaying LoadSprite's call order, so these really are
// hyiready / hyirun / hyihjump / hyifall rather than banks chosen by eye. The
// anchor is his bottom centre, matching the frame origins in the data.
//
// What is still ours rather than the game's: the state->animation choice below
// and the playback rate. The animation scripts hold the real cel order and the
// per-entity tick rate, and are not wired up yet.
function pickBank(S, p) {
  if (!p.onGround) return p.vy < 0 ? (S.harry_jump || S.harry_fall) : S.harry_fall;
  if (p.vx !== 0) return S.harry_run;
  return S.harry_idle;
}

function drawPlayer(ox, oy) {
  const p = state.player;
  if (!p) return;
  const ax = px(p.x) + p.w / 2;      // anchor: bottom centre of the box
  const ay = px(p.y) + p.h;
  const S = state.sprites;
  const bank = S && pickBank(S, p);

  if (!bank) {                       // sprites unavailable: fall back to a box
    const x = Math.round(px(p.x)) - ox, y = Math.round(px(p.y)) - oy;
    ctx.fillStyle = p.onGround ? '#ffd23c' : '#ff8a3c';
    ctx.fillRect(x, y, p.w, p.h);
    return;
  }

  const moving = p.onGround && p.vx !== 0;
  const frame = moving
    ? Math.floor(state.animT * 12) % bank.frames.length
    : (p.onGround ? Math.floor(state.idleT * 6) % bank.frames.length : 0);
  drawFrame(ctx, bank, frame, ax, ay, ox, oy, p.facing < 0);

  if (ui.solid.checked) {           // show the collision box against the art
    ctx.strokeStyle = '#ffd23c';
    ctx.strokeRect(Math.round(px(p.x)) - ox + 0.5,
                   Math.round(px(p.y)) - oy + 0.5, p.w - 1, p.h - 1);
  }
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

// Cell bit 12 (0x1000) is proven from code to select the opaque blit, and its
// spatial pattern is a textbook collision map: on forest1 it traces the tree
// trunks and ground mass, on level22 the ledges, ramps and poles, while
// decorative vines and grass stay unmarked. The collision *test* has not been
// found in the binary yet, so treating solid == bit 12 is inference, not proof.
// See REVERSE.md. SOLID_BIT is imported from physics.js.
function drawSolid(lv, ox, oy) {
  const L = lv.layers[0];
  const c0 = ox >> 3, c1 = Math.min(L.cell_w - 1, (ox + SCREEN_W) >> 3);
  const r0 = oy >> 3, r1 = Math.min(L.cell_h - 1, (oy + SCREEN_H) >> 3);
  ctx.globalAlpha = 0.45;
  ctx.fillStyle = '#ff2d55';
  for (let cy = r0; cy <= r1; cy++) {
    for (let cx = c0; cx <= c1; cx++) {
      if (L.cells[cy * L.cell_w + cx] & SOLID_BIT) {
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
  if (ui.play.checked) drawPlayer(ox, oy);

  if (state.mouse) {
    const px = ox + state.mouse.x, py = oy + state.mouse.y;
    const v = cellAt(lv, px, py);
    ui.probe.textContent =
      `px ${px},${py}  cell ${px >> 3},${py >> 3}  ` +
      `word 0x${v.toString(16).padStart(4, '0')}  ` +
      `tile ${v & 0xfff}  flags 0x${(v >> 12).toString(16).toUpperCase()}  ` +
      `${v & SOLID_BIT ? 'SOLID' : 'open'}`;
  } else if (ui.play.checked && state.player) {
    const p = state.player;
    ui.probe.textContent =
      `player ${px(p.x).toFixed(2)},${px(p.y).toFixed(2)}  ` +
      `vel ${px(p.vx).toFixed(2)},${px(p.vy).toFixed(2)}  ` +
      `${p.onGround ? 'on ground' : 'airborne'}  ` +
      `box ${p.w}x${p.h}  camera ${ox},${oy}`;
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

window.__game = state;   // for the headless test harness

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
  try {
    state.sprites = await loadSprites();
  } catch (err) {
    console.warn('sprites unavailable:', err.message);
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
