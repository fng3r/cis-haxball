// @vitest-environment jsdom
import { expect, it, vi } from 'vitest';
import { gameAtTick, mountGameSync } from '../src/player/game-sync.js';

it('selects the first game before play and the latest game at its start boundary', () => {
  expect(gameAtTick([], 0)).toBeNull();
  expect(gameAtTick([100, 1000, 2000], 0)).toBe(0);
  expect(gameAtTick([100, 1000, 2000], 999)).toBe(0);
  expect(gameAtTick([100, 1000, 2000], 1000)).toBe(1);
  expect(gameAtTick([100, 1000, 2000], 5000)).toBe(2);
});

it('syncs manual seeks, pending backward seeks, reset and normal playback without per-frame messages', () => {
  const g = document.createElement('div');
  g.innerHTML = '<button data-hook="reset">Reset</button>';
  const replay = {
    mh: 1000 / 60, Qb: 0, Fd: -1,
    ui() { this.Qb = 0; },
    er(ms) { this.Fd = ms; if (ms < this.Qb) this.ui(); },
  };
  const reset = g.querySelector('button');
  reset.onclick = () => replay.ui();
  const refresh = vi.fn();
  const controls = { g, C: refresh };
  const onGame = vi.fn();
  const sync = mountGameSync(controls, replay, onGame);
  sync.setGames([100, 1000, 2000]);
  expect(onGame).toHaveBeenLastCalledWith(0);
  // The destination, not the intermediate tick, determines the selected game.
  replay.er(2200 * replay.mh);
  expect(onGame).toHaveBeenLastCalledWith(2);
  replay.Qb = 400 * replay.mh; controls.C();
  expect(onGame).toHaveBeenLastCalledWith(2);
  // A backward native seek resets the simulation internally, but remains in
  // the destination game instead of flashing back to game one.
  replay.Qb = 2200 * replay.mh;
  replay.er(1500 * replay.mh);
  expect(onGame).toHaveBeenLastCalledWith(1);
  // Reset must discard the pending destination as well as the clock.
  reset.click();
  expect(replay.Fd).toBe(-1);
  expect(onGame).toHaveBeenLastCalledWith(0);
  onGame.mockClear();
  controls.C(); controls.C();
  expect(onGame).not.toHaveBeenCalled();
  replay.Qb = 1000 * replay.mh; controls.C();
  expect(onGame).toHaveBeenCalledExactlyOnceWith(1);
  controls.C();
  expect(onGame).toHaveBeenCalledTimes(1);
  expect(refresh).toHaveBeenCalled();
});
