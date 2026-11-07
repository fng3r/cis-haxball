// @vitest-environment jsdom
import { expect, it, vi } from 'vitest';
import { adjacentGoal, goalSeekTick, mountGoalControls } from '../src/player/goal-controls.js';

it('uses an eight-second lead-in for every goal and clamps early goals to replay start', () => {
  expect(goalSeekTick(1200)).toBe(720);
  expect(goalSeekTick(200)).toBe(0);
  expect(goalSeekTick(1000, 580)).toBe(581);
  expect(goalSeekTick(200, 100)).toBe(101);
  expect(goalSeekTick(2000, 1000)).toBe(1520);
});

it('finds goals around the playback position without wrapping at the ends', () => {
  const goals = [1000, 2000, 3000];
  expect(adjacentGoal(goals, 1500, -1)).toBe(1000);
  expect(adjacentGoal(goals, 1500, 1)).toBe(2000);
  expect(adjacentGoal(goals, 0, -1)).toBeUndefined();
  expect(adjacentGoal(goals, 3500, 1)).toBeUndefined();
  expect(adjacentGoal([], 1500, 1)).toBeUndefined();
});

it('steps through successive goals while a seek is pending and after manual scrubbing', () => {
  const g = document.createElement('div');
  g.innerHTML = '<button data-hook="play">Play</button>';
  const replay = {
    mf: 4000, mh: 1000 / 60, Fd: -1, Qb: 0,
    er(ms) { this.Fd = ms; },
    ui() { this.Qb = 0; this.Fd = -1; },
  };
  const controls = { g, C: vi.fn() };
  const seek = vi.fn(tick => replay.er(tick * replay.mh));
  const navigation = mountGoalControls(controls, replay, seek);
  const previous = g.querySelector('[aria-label="Previous goal"]');
  const next = g.querySelector('[aria-label="Next goal"]');
  expect(previous.disabled).toBe(true);
  expect(next.disabled).toBe(true);
  navigation.setGoals([3000, 1000, 2000, 2000, NaN]);
  expect(next.disabled).toBe(false);
  next.click(); expect(seek).toHaveBeenLastCalledWith(520);
  next.click(); expect(seek).toHaveBeenLastCalledWith(1520);
  previous.click(); expect(seek).toHaveBeenLastCalledWith(520);
  expect(previous.disabled).toBe(true);
  next.click(); next.click();
  expect(seek).toHaveBeenLastCalledWith(2520);
  expect(next.disabled).toBe(true);
  // Timeline goal selection uses the same navigation cursor and lead-in.
  navigation.seekGoal(2000);
  expect(seek).toHaveBeenLastCalledWith(1520);
  previous.click(); expect(seek).toHaveBeenLastCalledWith(520);
  // A manual scrub replaces the cursor with the actual playback position.
  replay.er(2500 * replay.mh); controls.C();
  next.click(); expect(seek).toHaveBeenLastCalledWith(2520);
  replay.ui(); controls.C();
  expect(previous.disabled).toBe(true);
  expect(next.disabled).toBe(false);
});

it('distinguishes early goals with lead-ins clamped after the previous goal', () => {
  expect(adjacentGoal([100, 200], 0, 1, 100)).toBe(200);
  expect(adjacentGoal([100, 200], 101, -1, 200)).toBe(100);
});

it('keeps clustered goal controls and timeline seeks after the preceding goal', () => {
  const g = document.createElement('div');
  g.innerHTML = '<button data-hook="play">Play</button>';
  const replay = { mf: 4000, mh: 1000 / 60, Fd: -1, Qb: 0,
    er(ms) { this.Fd = ms; }, ui() { this.Qb = 0; this.Fd = -1; } };
  const seek = vi.fn(tick => replay.er(tick * replay.mh));
  const navigation = mountGoalControls({ g, C: vi.fn() }, replay, seek);
  navigation.setGoals([1000, 1420, 1800]);
  const next = g.querySelector('[aria-label="Next goal"]');
  const previous = g.querySelector('[aria-label="Previous goal"]');
  next.click(); expect(seek).toHaveBeenLastCalledWith(520);
  next.click(); expect(seek).toHaveBeenLastCalledWith(1001);
  next.click(); expect(seek).toHaveBeenLastCalledWith(1421);
  previous.click(); expect(seek).toHaveBeenLastCalledWith(1001);
  previous.click(); expect(seek).toHaveBeenLastCalledWith(520);
  navigation.seekGoal(1800); expect(seek).toHaveBeenLastCalledWith(1421);
  previous.click(); expect(seek).toHaveBeenLastCalledWith(1001);
});
