import { readFile } from 'node:fs/promises';
import { inflateRaw } from 'pako';
import { afterAll, expect, it, vi } from 'vitest';
import { CHECKPOINT_INTERVAL_TICKS, checkpointAt, prepareReplayCheckpoints, stepReplay, mountCheckpointSeek } from '../src/player/checkpoints.js';
import { replayCases } from './replay-fixtures.js';
import { nativeReplayFixture } from './native-replay-fixture.js';
const runtime = await nativeReplayFixture();
afterAll(runtime.dispose);

it.each(replayCases)('restores complete native state and seeks correctly throughout $file', async fixture => {
  const bytes = Uint8Array.from(await readFile(new URL(`./fixtures/${fixture.file}`, import.meta.url)));
  const { replay, save, restore } = runtime.create(bytes, inflateRaw);
  const { checkpoints } = prepareReplayCheckpoints(replay, save);
  expect(CHECKPOINT_INTERVAL_TICKS).toBe(900);
  expect(checkpoints.map(c => c.tick)).toEqual(Array.from({ length: Math.floor(replay.mf / 900) + 1 }, (_,i) => i * 900));
  const targets = new Set([0, replay.mf, replay.mf - 1]);
  for (const c of checkpoints) for (const d of [-1,0,1,417]) if (c.tick+d >= 0 && c.tick+d <= replay.mf) targets.add(c.tick+d);
  for (const goal of fixture.goalTicks.flat()) for (const d of [-1,0,1,151]) if (goal+d <= replay.mf) targets.add(goal+d);
  const reference = runtime.create(bytes, inflateRaw), expected = new Map();
  if (targets.has(0)) expected.set(0, reference.save(reference.replay).data);
  while (reference.replay.Y < reference.replay.mf) {
    stepReplay(reference.replay);
    if (targets.has(reference.replay.Y)) expected.set(reference.replay.Y, reference.save(reference.replay).data);
  }
  // Descending targets exercise backward seeks, including crossing match and
  // administrative boundaries; then ascending targets exercise forward skipping.
  replay.pl = 0;
  replay.Qb = replay.mf * replay.mh;
  const restored = vi.fn((r,c) => restore(r,c));
  mountCheckpointSeek(replay, checkpoints, restored, () => 0);
  const ordered = [...targets].sort((a,b) => b-a);
  for (const target of [...ordered, ...ordered.toReversed()]) {
    // A tiny fractional tick avoids floating point multiplication rounding an
    // integer destination below its native tick. End-of-file stays clamped.
    replay.er(Math.min(replay.mf * replay.mh, (target + 0.001) * replay.mh));
    const nativeTarget = Math.floor(replay.Fd * replay.Ac);
    expect(nativeTarget).toBe(target);
    const start = replay.Y;
    expect(target - start).toBeGreaterThanOrEqual(0);
    expect(target - start).toBeLessThan(900);
    let frames = 0;
    while (replay.Fd > 0) { replay.C(); frames++; expect(frames).toBeLessThanOrEqual(2); }
    expect(replay.Y).toBe(target);
    expect(save(replay).data, `native state at tick ${target}`).toEqual(expected.get(target));
    expect(replay.pl).toBe(0);
  }
  expect(restored).toHaveBeenCalled();
  // Restoring a checkpoint must not leave the event cursor at the destination
  // of a previous seek: subsequent actions and physics must match too.
  const target = Math.min(1234, replay.mf);
  restore(replay, checkpointAt(checkpoints, target));
  while (replay.Y < target) stepReplay(replay);
  restore(reference.replay, checkpointAt(checkpoints, target));
  while (reference.replay.Y < target + 600) stepReplay(reference.replay);
  for (let i=0;i<600;i++) stepReplay(replay);
  expect(save(replay).data).toEqual(reference.save(reference.replay).data);
  replay.ui();
  expect(replay.Y).toBe(0);
  expect(save(replay).data).toEqual(checkpoints[0].data);
}, 15000);

it('keeps short forward seeks on the current state and clamps invalid destinations', () => {
  const replay = {Y: 950, Qb: 950, Fd:-1, mf: 2000, mh:1, Ac:1, pl:2, Wh:0};
  const checkpoints = [0,900,1800].map(tick => ({tick}));
  const restore = vi.fn((r,c) => {r.Y=c.tick;});
  mountCheckpointSeek(replay, checkpoints, restore, () => 123);
  replay.er(960); expect(restore).not.toHaveBeenCalled(); expect(replay.Fd).toBe(960);
  replay.er(1900); expect(restore).toHaveBeenLastCalledWith(replay, checkpoints[2]);
  expect(replay.Qb).toBe(1800); expect(replay.pl).toBe(2); expect(replay.Wh).toBe(123);
  replay.er(-10); expect(replay.Y).toBe(0); expect(replay.Fd).toBe(0);
  replay.er(9999); expect(replay.Fd).toBe(2000);
  replay.er(NaN); expect(replay.Fd).toBe(2000);
});
