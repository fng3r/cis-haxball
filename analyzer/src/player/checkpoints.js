import { captureChat } from './chat-index.js';

export const CHECKPOINT_INTERVAL_TICKS = 15 * 60;

export function stepReplay(replay) {
  while (replay.gg && replay.hg === replay.Y) {
    replay.gg.apply(replay.T);
    replay.Dl();
  }
  replay.Y++;
  replay.T.C(1);
}

export function prepareReplayCheckpoints(replay, save) {
  const checkpoints = [save(replay)];
  const chatEntries = captureChat(replay.T, () => replay.Y);
  while (replay.Y < replay.mf) {
    stepReplay(replay);
    if (replay.Y % CHECKPOINT_INTERVAL_TICKS === 0) checkpoints.push(save(replay));
  }
  return { checkpoints, chatEntries };
}

export function checkpointAt(checkpoints, tick) {
  let lo = 0, hi = checkpoints.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (checkpoints[mid].tick <= tick) lo = mid + 1;
    else hi = mid;
  }
  return checkpoints[Math.max(0, lo - 1)];
}

export function mountCheckpointSeek(replay, checkpoints, restore, now = () => performance.now()) {
  replay.er = function (milliseconds) {
    if (!Number.isFinite(milliseconds)) return;
    const target = Math.max(0, Math.min(this.mf * this.mh, milliseconds));
    const tick = Math.floor(target * this.Ac);
    const checkpoint = checkpointAt(checkpoints, tick);
    // Keep current state for short forward jumps. Backward jumps always restore;
    // long forward jumps can skip directly to a checkpoint ahead of the player.
    if (tick < this.Y || checkpoint.tick > this.Y) {
      restore(this, checkpoint);
      this.Qb = checkpoint.tick * this.mh;
      this.sk = 0;
    }
    this.Fd = target;
    this.Wh = now();
  };
}
