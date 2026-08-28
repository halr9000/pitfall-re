// Sprite banks decoded from the 0x34561234 blocks (see tools/sprite.py).
//
// Each frame carries an origin from the original data: the anchor is the
// sprite's bottom centre, so a frame draws at (anchorX + ox, anchorY + oy).
// Which bank belongs to which player action is NOT decoded yet — the bank
// names here are observational, and the state->animation mapping lives in the
// animation scripts (blocks 1-4 of each level) that are still unread.

export async function loadSprites(base = 'data/sprites') {
  const r = await fetch(`${base}/sprites.json`);
  if (!r.ok) throw new Error(`sprites.json: HTTP ${r.status}`);
  const meta = await r.json();
  const banks = {};
  await Promise.all(Object.entries(meta.banks).map(([name, b]) =>
    new Promise((res, rej) => {
      const img = new Image();
      img.onload = () => { banks[name] = { ...b, img }; res(); };
      img.onerror = () => rej(new Error(`sprite sheet: ${b.sheet}`));
      img.src = `${base}/${b.sheet}`;
    })));
  return banks;
}

/** Draw frame `i` of `bank` with its anchor at world (ax, ay), camera (ox, oy). */
export function drawFrame(ctx, bank, i, ax, ay, ox, oy, flip = false) {
  if (!bank) return;
  const f = bank.frames[i % bank.frames.length];
  const dx = Math.round(ax + (flip ? -f.ox - f.w : f.ox)) - ox;
  const dy = Math.round(ay + f.oy) - oy;
  if (!flip) {
    ctx.drawImage(bank.img, f.x, f.y, f.w, f.h, dx, dy, f.w, f.h);
    return;
  }
  ctx.save();
  ctx.translate(dx + f.w, dy);
  ctx.scale(-1, 1);
  ctx.drawImage(bank.img, f.x, f.y, f.w, f.h, 0, 0, f.w, f.h);
  ctx.restore();
}
