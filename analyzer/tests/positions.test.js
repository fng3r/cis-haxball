import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { analyzeReplay } from '../src/engine/analyze.js';
import { createPositionTracker, positionGeometry, POSITION_WINDOW_TICKS } from '../src/engine/positions.js';
import { replayCases } from './replay-fixtures.js';

const stadium = { goals: [
  { team: 'red', p0: [-600, -80], p1: [-600, 80] },
  { team: 'blue', p0: [600, 80], p1: [600, -80] },
] };
const lineup = [
  { id: 'keeper', x: -500, y: 0 },
  { id: 'defender', x: -160, y: 0 },
  { id: 'top', x: 180, y: -180 },
  { id: 'bottom', x: 160, y: 180 },
];
function observe(tracker, players, ticks = POSITION_WINDOW_TICKS, start = 0) {
  for (let tick = start; tick < start + ticks; tick++) tracker.observe(players, tick);
}
function infer(players, ticks = POSITION_WINDOW_TICKS, pitch = stadium) {
  const tracker = createPositionTracker(pitch);
  observe(tracker, players, ticks);
  return tracker.finish();
}
const red = players => players.map(p => ({ ...p, team: 'red' }));
const roles = result => Object.fromEntries([...result].map(([id, p]) => [id, p.position]));

describe('movement-based position inference', () => {
  it('recognizes two strikers on opposite flanks without imposing an AM', () => {
    expect(roles(infer(red(lineup)))).toEqual({ keeper: 'GK', defender: 'DM', top: 'ST', bottom: 'ST' });
  });

  it('recognizes an attacking midfielder when the front line is actually staggered', () => {
    const players = red(lineup.map(p => p.id === 'top' ? { ...p, x: 60, y: 0 }
      : p.id === 'bottom' ? { ...p, x: 420, y: 20 } : p));
    expect(roles(infer(players))).toEqual({ keeper: 'GK', defender: 'DM', top: 'AM', bottom: 'ST' });
  });

  it('is invariant to side switches, translation, pitch scaling and rotation', () => {
    const expected = roles(infer(red(lineup)));
    expect(roles(infer(lineup.map(p => ({ ...p, team: 'blue', x: -p.x, y: -p.y }))))).toEqual(expected);
    const transform = ({ x, y }) => ({ x: y * -2 + 123, y: x * 2 - 234 });
    const pitch = { goals: stadium.goals.map(g => ({ ...g,
      p0: Object.values(transform({ x: g.p0[0], y: g.p0[1] })),
      p1: Object.values(transform({ x: g.p1[0], y: g.p1[1] })),
    })) };
    expect(roles(infer(red(lineup.map(p => ({ ...p, ...transform(p) }))), POSITION_WINDOW_TICKS, pitch))).toEqual(expected);
  });

  it('does not require four teammates or force a goalkeeper into an attacking group', () => {
    expect(roles(infer(red(lineup.slice(0, 3))))).toEqual({ keeper: 'GK', defender: 'DM', top: 'ST' });
    const five = [...lineup, { id: 'extra', x: -150, y: 80 }];
    expect(roles(infer(red(five)))).toEqual({ keeper: 'GK', defender: 'DM', extra: 'DM', top: 'ST', bottom: 'ST' });
    expect([...infer(red(lineup.map(p => ({ ...p, x: 300 })))).values()].every(p => p.position !== 'GK')).toBe(true);
  });

  it('handles replacement keepers within a window using their contemporaneous teammates', () => {
    const tracker = createPositionTracker(stadium);
    observe(tracker, red(lineup), 900);
    observe(tracker, red(lineup.map(p => p.id === 'keeper' ? { ...p, id: 'replacement' } : p)), 900, 900);
    const result = tracker.finish();
    expect(result.get('keeper').position).toBe('GK');
    expect(result.get('replacement').position).toBe('GK');
    expect(result.get('replacement').positionRoles[0].ticks).toBe(900);
  });

  it('retains role changes instead of inventing a stable role from a whole-game average', () => {
    const tracker = createPositionTracker(stadium);
    observe(tracker, red(lineup));
    const changed = lineup.map(p => p.id === 'keeper' ? { ...p, x: 180, y: -180 }
      : p.id === 'top' ? { ...p, x: -500, y: 0 } : p);
    observe(tracker, red(changed), POSITION_WINDOW_TICKS, POSITION_WINDOW_TICKS + 500);
    const keeper = tracker.finish().get('keeper');
    expect(keeper.position).toBeNull();
    expect(keeper.positionRoles.map(p => p.position).sort()).toEqual(['GK', 'ST']);
    expect(keeper.positionPeriods.map(p => p.startTick)).toEqual([0, POSITION_WINDOW_TICKS + 500]);
    expect(keeper.positionRoles.reduce((sum, p) => sum + p.ticks, 0)).toBe(POSITION_WINDOW_TICKS * 2);
  });

  it('leaves brief appearances and unsupported goal layouts unclassified', () => {
    expect([...infer(red(lineup), 599).values()].every(p => p.position === null && p.positionConfidence === 0)).toBe(true);
    expect(positionGeometry({})).toBeNull();
    expect(positionGeometry({ goals: [...stadium.goals, stadium.goals[0]] })).toBeNull();
    expect(infer(red(lineup), 1800, {}).size).toBe(0);
  });

  it('retains unclassified presence even when an appearance falls between spatial samples', () => {
    const tracker = createPositionTracker(stadium);
    observe(tracker, red(lineup), 1799);
    tracker.observe(red([...lineup, { id: 'cameo', x: 100, y: 100 }]), 1799);
    const cameo = tracker.finish().get('cameo');
    expect(cameo.position).toBeNull();
    expect(cameo.positionPeriods[0].observedTicks).toBe(1);
    expect(cameo.positionRoles).toEqual([]);
  });

  it.each(replayCases)('exports bounded, deterministic role evidence for $file', fixture => {
    const result = analyzeReplay(readFileSync(new URL(`./fixtures/${fixture.file}`, import.meta.url)));
    expect(result.positionVersion).toBe(1);
    for (const game of result.games) for (const player of game.players) {
      expect([null, 'GK', 'DM', 'AM', 'ST']).toContain(player.position);
      expect(player.positionConfidence).toBeGreaterThanOrEqual(0);
      expect(player.positionConfidence).toBeLessThanOrEqual(1);
      const observed = player.positionPeriods.reduce((sum, p) => sum + p.observedTicks, 0);
      expect(observed).toBeLessThanOrEqual(player.playedTicks);
      expect(player.playedTicks - observed).toBeLessThanOrEqual(1);
      expect(player.positionPeriods.length).toBeLessThanOrEqual(Math.ceil(result.ticks / POSITION_WINDOW_TICKS));
      for (const period of player.positionPeriods) {
        expect(period.startTick).toBeGreaterThanOrEqual(game.startTick);
        expect(period.endTick).toBeLessThanOrEqual(result.ticks);
      }
    }
  });
});
