import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { analyzeReplay } from '../src/engine/analyze.js';
import { createPositionTracker, positionGeometry, selectGamePositions, POSITION_WINDOW_TICKS, MIN_POSITION_TICKS } from '../src/engine/positions.js';
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
    const replacement = red(lineup.map(p => p.id === 'keeper' ? { ...p, id: 'replacement' } : p));
    observe(tracker, replacement, 900, 900);
    const result = tracker.finish();
    expect(result.get('keeper').position).toBe('GK');
    expect(result.get('replacement').position).toBe('GK');
    expect(result.get('replacement').positionRoles[0].ticks).toBe(900);
  });

  it('retains equal-time role changes as primary and secondary positions', () => {
    const tracker = createPositionTracker(stadium);
    observe(tracker, red(lineup));
    const changed = lineup.map(p => p.id === 'keeper' ? { ...p, x: 180, y: -180 }
      : p.id === 'top' ? { ...p, x: -500, y: 0 } : p);
    observe(tracker, red(changed), POSITION_WINDOW_TICKS, POSITION_WINDOW_TICKS + 500);
    const keeper = tracker.finish().get('keeper');
    expect(keeper.primaryPosition).toBe('GK');
    expect(keeper.secondaryPosition).toBe('ST');
    expect(keeper.position).toBe(keeper.primaryPosition);
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

  it.each([600, 818, 869, MIN_POSITION_TICKS - 1])('suppresses all speculative roles for a %i-tick appearance', ticks => {
    for (const player of infer(red(lineup), ticks).values()) {
      expect(player.position).toBeNull();
      expect(player.primaryPosition).toBeNull();
      expect(player.secondaryPosition).toBeNull();
      expect(player.positionConfidence).toBe(0);
      expect(player.primaryPositionConfidence).toBe(0);
      expect(player.secondaryPositionConfidence).toBe(0);
      expect(player.positionRoles).toEqual([]);
      expect(player.positionPeriods.every(period => period.position === null && period.confidence === 0)).toBe(true);
      expect(player.positionPeriods.reduce((sum, period) => sum + period.observedTicks, 0)).toBe(ticks);
    }
  });

  it('starts reporting roles after fifteen seconds of active appearance', () => {
    expect(infer(red(lineup), MIN_POSITION_TICKS).get('keeper').position).toBe('GK');
    const tracker = createPositionTracker(stadium);
    observe(tracker, red(lineup), 450);
    observe(tracker, red(lineup), 450, 30000);
    expect(tracker.finish().get('keeper').position).toBe('GK');
  });

  it('does not count a long pause towards the minimum appearance', () => {
    const tracker = createPositionTracker(stadium);
    observe(tracker, red(lineup), 450);
    observe(tracker, red(lineup), 449, 30000);
    expect(tracker.finish().get('keeper').position).toBeNull();
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
    expect(result.positionVersion).toBe(3);
    for (const game of result.games) for (const player of game.players) {
      expect([null, 'GK', 'DM', 'AM', 'ST']).toContain(player.position);
      expect([null, 'GK', 'DM', 'AM', 'ST']).toContain(player.secondaryPosition);
      expect(player.position).toBe(player.primaryPosition);
      expect(player.positionConfidence).toBe(player.primaryPositionConfidence);
      if (player.secondaryPosition) {
        expect(player.secondaryPosition).not.toBe(player.primaryPosition);
        const role = player.positionRoles.find(p => p.position === player.secondaryPosition);
        expect(role.ticks).toBeGreaterThanOrEqual(MIN_POSITION_TICKS);
        expect(role.ticks / player.positionPeriods.reduce((sum, p) => sum + p.observedTicks, 0)).toBeGreaterThanOrEqual(0.25);
      }
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

// Tick counts represent observed time; confidence is the existing accumulated
// per-window evidence, not a probability that the label is correct.
function evidence(entries) {
  return new Map(entries.map(([position, seconds, confidence = 0.8]) => [position, {
    ticks: seconds * 60, confidence: seconds * 60 * confidence,
  }]));
}

describe('whole-game primary and secondary position selection', () => {
  it('selects the largest time share without requiring a majority', () => {
    const result = selectGamePositions(evidence([['ST', 40, 0.6], ['DM', 35, 0.9], ['AM', 25]]), 100 * 60);
    expect(result.primaryPosition).toBe('ST');
    expect(result.secondaryPosition).toBe('DM');
    expect(result.positionRoles).toHaveLength(3);
  });

  it('leaves the secondary null for a single role or an incidental alternative', () => {
    expect(selectGamePositions(evidence([['GK', 480]]), 480 * 60).secondaryPosition).toBeNull();
    expect(selectGamePositions(evidence([['ST', 420], ['DM', 60]]), 480 * 60).secondaryPosition).toBeNull();
  });

  it('requires an unrounded twenty-five percent share for a secondary', () => {
    expect(selectGamePositions(evidence([['ST', 360], ['DM', 120]]), 480 * 60).secondaryPosition).toBe('DM');
    const result = selectGamePositions(evidence([['ST', 360 + 1 / 60], ['DM', 120 - 1 / 60]]), 480 * 60);
    expect(result.positionRoles[1].share).toBe(0.25);
    expect(result.secondaryPosition).toBeNull();
  });

  it('requires fifteen seconds of evidence for each reported position', () => {
    const result = selectGamePositions(evidence([['ST', 20], ['DM', 14]]), 34 * 60);
    expect(result.primaryPosition).toBe('ST');
    expect(result.secondaryPosition).toBeNull();
    expect(selectGamePositions(evidence([['ST', 10], ['DM', 10]]), 30 * 60).primaryPosition).toBeNull();
    expect(selectGamePositions(evidence([['ST', 30], ['DM', 15]]), 45 * 60).secondaryPosition).toBe('DM');
  });

  it('includes unclassified time in secondary shares and confidence', () => {
    const result = selectGamePositions(evidence([['ST', 60], ['DM', 20]]), 100 * 60);
    expect(result.primaryPosition).toBe('ST');
    expect(result.secondaryPosition).toBeNull();
    expect(result.primaryPositionConfidence).toBe(0.48);
  });

  it('breaks equal-time ties by confidence and then first-observed order', () => {
    const unequal = selectGamePositions(evidence([['ST', 240, 0.7], ['DM', 240, 0.8]]), 480 * 60);
    expect(unequal.primaryPosition).toBe('DM');
    expect(unequal.secondaryPosition).toBe('ST');
    const equal = selectGamePositions(evidence([['ST', 240], ['DM', 240]]), 480 * 60);
    expect(equal.primaryPosition).toBe('ST');
    expect(equal.secondaryPosition).toBe('DM');
  });
});
