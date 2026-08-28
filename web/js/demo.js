// Scripted demo walk — a "▶ Demo" button so the port previews itself without a
// keyboard, which is the only practical way to look at it on a phone.
//
// The script is a loop of timed input segments. Levels differ wildly in layout,
// so a fixed sequence would walk Harry into a trunk and stall on some of them;
// the driver watches whether he is actually moving and jumps, then turns
// around, when he stops making progress.

const SCRIPT = [
  { input: { right: true }, secs: 2.0 },
  { input: { right: true, jump: true }, secs: 0.25 },
  { input: { right: true }, secs: 1.4 },
  { input: {}, secs: 0.5 },
  { input: { right: true, run: true }, secs: 1.6 },
  { input: { right: true, jump: true }, secs: 0.25 },
  { input: { right: true }, secs: 1.0 },
  { input: {}, secs: 0.6 },
  { input: { left: true }, secs: 2.2 },
  { input: { left: true, jump: true }, secs: 0.25 },
  { input: { left: true }, secs: 1.4 },
  { input: {}, secs: 0.6 },
];

const STUCK_SECS = 0.45;     // no progress for this long => try something
const STUCK_PX = 2;          // "progress" threshold

export class Demo {
  constructor() {
    this.active = false;
    this.reset();
  }

  reset() {
    this.step = 0;
    this.t = 0;
    this.stuckT = 0;
    this.lastX = null;
    this.flip = 1;            // 1 = follow the script, -1 = mirrored
    this.nudge = 0;           // frames of forced jump after getting stuck
  }

  start() {
    this.reset();
    this.active = true;
  }

  stop() {
    this.active = false;
  }

  toggle() {
    this.active ? this.stop() : this.start();
    return this.active;
  }

  /** Advance the script and return the input object for this frame. */
  poll(dt, player, px) {
    if (!this.active) return null;
    const seg = SCRIPT[this.step % SCRIPT.length];

    this.t += dt;
    if (this.t >= seg.secs) {
      this.t = 0;
      this.step++;
    }

    // progress watchdog: if Harry is meant to be walking but isn't, jump; if
    // that does not help either, mirror the script so he heads back.
    const x = px(player.x);
    const wants = !!(seg.input.left || seg.input.right);
    if (this.lastX !== null && wants && Math.abs(x - this.lastX) < STUCK_PX) {
      this.stuckT += dt;
    } else {
      this.stuckT = 0;
    }
    this.lastX = x;

    if (this.stuckT > STUCK_SECS) {
      this.stuckT = 0;
      if (this.nudge > 0) {
        this.flip = -this.flip;   // jumping did not help — turn around
        this.nudge = 0;
      } else {
        this.nudge = 1;
      }
    }

    const jumpNudge = this.nudge > 0 && player.onGround;
    if (jumpNudge) this.nudge = 0;

    const left = this.flip > 0 ? seg.input.left : seg.input.right;
    const right = this.flip > 0 ? seg.input.right : seg.input.left;
    return {
      left: !!left,
      right: !!right,
      jump: !!seg.input.jump || jumpNudge,
      run: !!seg.input.run,
    };
  }
}
