// Player physics against the bit-12 collision map.
//
// What is taken from the binary:
//   * cell grid is 8x8 px, cellmap row-major with a cell_w stride (draw_background)
//   * a cell is solid when bit 12 of its word is set — proven to select the
//     opaque blit, and empirically the solid world (see REVERSE.md). This is
//     inference from the data, not from the collision code, which is unlocated.
//   * entity positions are 1/4-pixel fixed point: the alien update at
//     0x004426E0 repeatedly does `sar eax, 2` to turn a position into pixels
//   * the world clamp is (map tiles * 16) - 32, from init_world_bounds
//
// What is still guessed, and flagged as such in the UI: the player box size and
// every movement constant. Those come out of the physics code once it is found.

export const SOLID_BIT = 0x1000;
export const SUB = 4;            // position fixed-point: 1/4 px, as the original

// --- provisional movement constants, in 1/4-px units per frame at 60Hz -----
export const TUNING = {
  walk: 6,          // 1.5 px/frame
  run: 10,          // 2.5 px/frame
  gravity: 1.4,
  jump: -21,        // ~5.25 px/frame initial rise
  maxFall: 40,
  boxW: 12,
  boxH: 28,
};

export function isSolid(level, px, py) {
  const L = level.layers[0];
  const cx = px >> 3, cy = py >> 3;
  if (cx < 0 || cx >= L.cell_w || cy < 0 || cy >= L.cell_h) return false;
  return (L.cells[cy * L.cell_w + cx] & SOLID_BIT) !== 0;
}

/** Any solid cell overlapping the box [x,y,w,h] in pixels. */
export function boxHits(level, x, y, w, h) {
  const x0 = Math.floor(x), y0 = Math.floor(y);
  const x1 = Math.ceil(x + w) - 1, y1 = Math.ceil(y + h) - 1;
  for (let py = y0; py <= y1; py++) {
    for (let px = x0; px <= x1; px++) {
      if (isSolid(level, px, py)) return true;
    }
  }
  return false;
}

export function makePlayer(x, y) {
  return {
    x: x * SUB, y: y * SUB,        // 1/4-px fixed point
    vx: 0, vy: 0,
    w: TUNING.boxW, h: TUNING.boxH,
    onGround: false,
    facing: 1,
  };
}

/**
 * Pick a spawn: the first surface with a genuinely walkable run on it, not just
 * the leftmost solid cell — in forest1 that is wedged between tree trunks.
 * Requires the player box to fit along `runPx` of clear space to the right.
 */
export function findSpawn(level, runPx = 48) {
  const L = level.layers[0];
  const { boxW, boxH } = TUNING;
  let fallback = null;
  for (let cx = 2; cx < L.cell_w - 8; cx++) {
    for (let cy = 1; cy < L.cell_h; cy++) {
      if (!(L.cells[cy * L.cell_w + cx] & SOLID_BIT)) continue;
      const px = cx * 8, py = cy * 8 - boxH;
      if (py >= 0 && !boxHits(level, px, py, boxW, boxH)) {
        if (!fallback) fallback = { x: px, y: py };
        // walkable if the box clears every step along the run and the floor
        // stays under it
        let ok = true;
        for (let d = 0; d <= runPx && ok; d += 8) {
          if (boxHits(level, px + d, py, boxW, boxH)) ok = false;
          else if (!boxHits(level, px + d, py + 1, boxW, boxH + 8)) ok = false;
        }
        if (ok) return { x: px, y: py };
      }
      break;   // only the topmost surface in this column
    }
  }
  return fallback || { x: 16, y: 16 };
}

/** One fixed step. `input` = {left, right, jump, run}. */
export function step(level, p, input) {
  const L = level.layers[0];
  const worldW = L.cell_w * 8, worldH = L.cell_h * 8;
  const speed = input.run ? TUNING.run : TUNING.walk;

  p.vx = input.left ? -speed : input.right ? speed : 0;
  if (input.left) p.facing = -1;
  if (input.right) p.facing = 1;

  if (input.jump && p.onGround) {
    p.vy = TUNING.jump;
    p.onGround = false;
  }
  p.vy = Math.min(p.vy + TUNING.gravity, TUNING.maxFall);

  // --- X axis, one pixel at a time so a fast step cannot tunnel
  let remaining = p.vx;
  const stepX = Math.sign(remaining);
  while (remaining !== 0) {
    const d = Math.abs(remaining) < SUB ? remaining : stepX * SUB;
    const nx = p.x + d;
    const px = nx / SUB, py = p.y / SUB;
    if (boxHits(level, px, py, p.w, p.h) || px < 0 || px + p.w > worldW) {
      p.vx = 0;
      break;
    }
    p.x = nx;
    remaining -= d;
  }

  // --- Y axis
  remaining = p.vy;
  const stepY = Math.sign(remaining);
  let landed = false;
  while (remaining !== 0) {
    const d = Math.abs(remaining) < SUB ? remaining : stepY * SUB;
    const ny = p.y + d;
    const px = p.x / SUB, py = ny / SUB;
    if (boxHits(level, px, py, p.w, p.h) || py + p.h > worldH) {
      if (stepY > 0) landed = true;
      p.vy = 0;
      break;
    }
    p.y = ny;
    remaining -= d;
  }
  p.onGround = landed;
  if (p.y < 0) { p.y = 0; p.vy = 0; }
  return p;
}

export const px = v => v / SUB;
