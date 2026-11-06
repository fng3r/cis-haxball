import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { analyzeReplay } from '../src/engine-v2/analyze.js';
import { createCollector } from '../src/engine-v2/collector.js';
import { MATCH_COUNTERS } from '../src/engine-v2/match-metrics.js';
import { replayCases } from './replay-fixtures.js';
const single = readFileSync(new URL('./fixtures/cis5.hbr2', import.meta.url));
const multiple = readFileSync(new URL('./fixtures/futsal-multi.hbr2', import.meta.url));
// JSON has one zero; native physics can legitimately contain IEEE-754 negative zero.
// Preserve every other value/type so missing properties and non-finite values fail.
function normalizeSignedZero(value) {
  if (typeof value === 'number') return value === 0 ? 0 : value;
  if (Array.isArray(value)) return value.map(normalizeSignedZero);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, normalizeSignedZero(item)]));
  return value;
}
const stadium = { width: 120, height: 70, goals: [{ team: 'red', p0: [-100, -20], p1: [-100, 20] }, { team: 'blue', p0: [100, -20], p1: [100, 20] }] };
const member = (playerId, team, x = 0) => ({ playerId, nick: 'Same name', team, bodyId: playerId, x, y: 0, radius: 10, velocity: { x: 1, y: 0 }, input: 0 });
const frame = (tick, players, changes = {}) => ({ tick, gameId: 0, phase: 'active', gameTick: tick, score: [0, 0], stadium, ball: { x: 0, y: 0, radius: 5, velocity: { x: 0, y: 0 } }, players, ...changes });
const interaction = (type, tick, player, x = 0) => ({ type, tick, gameId: 0, gameTick: tick, phase: 'active', ...player, position: { x, y: 0 }, velocityBefore: { x: 0, y: 0 }, velocityAfter: { x: 5, y: 0 } });
function feed(collector, tick, players, events = [], changes = {}, afterChanges = {}) {
  const before = frame(tick, players, changes), after = frame(tick, players.map(p => ({ ...p, x: p.x + 1 })), { ...changes, ...afterChanges });
  collector.consume({ tick, before, after, events });
}

describe('new standalone replay engine', () => {
  it.each(replayCases)('reconstructs games and conserves metrics for $file', fixture => {
    const result = analyzeReplay(readFileSync(new URL(`./fixtures/${fixture.file}`, import.meta.url)));
    expect(result.ticks).toBe(fixture.ticks);
    expect(result).toMatchObject({ schemaVersion: 2, engine: 'replay-lab-v2', tickRate: 60 });
    expect(result.games.map(g => [g.scoreRed, g.scoreBlue])).toEqual(fixture.scores);
    expect(result.games.map(g => g.goals.map(goal => goal.tick))).toEqual(fixture.goalTicks);
    for (const [index, game] of result.games.entries()) {
      expect(game.stadium.name).toBe(fixture.stadium);
      expect(game.initialScore).toEqual([0, 0]);
      if (index) expect(game.startTick).toBeGreaterThan(result.games[index - 1].endTick);
      for (const goal of game.goals) {
        expect(goal.tick).toBeGreaterThanOrEqual(game.startTick);
        expect(goal.tick).toBeLessThan(game.endTick);
      }
      const eventsById = new Map(game.events.map(e => [e.id, e]));
      for (const event of game.events) {
        expect(event.gameId).toBe(game.id);
        if (event.type === 'completed_pass') {
          expect(eventsById.get(event.releaseEventId)).toMatchObject({ type: 'kick', playerId: event.playerId, team: event.team });
          expect(eventsById.get(event.receptionEventId).playerId).toBe(event.receiverId);
          expect(event.receiverTeam).toBe(event.team);
          expect(event.releaseTick).toBeGreaterThanOrEqual(game.startTick);
          expect(event.tick).toBeLessThan(game.endTick);
        }
        if (event.type === 'shot_on_target') expect(eventsById.get(event.sourceEventId).type).toBe('kick');
        if (event.type === 'key_pass') {
          expect(eventsById.get(event.passEventId).type).toBe('completed_pass');
          expect(eventsById.get(event.shotEventId).type).toBe('shot_on_target');
        }
      }
      expect(game.thirds.reduce((a, b) => a + b, 0)).toBe(game.activeTicks);
      expect(Object.values(game.proximityTicks).reduce((a, b) => a + b, 0)).toBe(game.activeTicks);
      for (const team of ['red', 'blue']) {
        for (const metric of MATCH_COUNTERS) expect(game.teams[team][metric], `${fixture.file}: ${team} ${metric}`).toBeGreaterThan(0);
        for (const metric of ['kicks', 'contacts', 'transfers', 'received', 'turnovers', 'goals', 'ownGoals', 'assists', ...MATCH_COUNTERS]) {
          expect(game.players.filter(p => p.team === team).reduce((sum, p) => sum + p[metric], 0)).toBe(game.teams[team][metric]);
        }
        const t = game.teams[team]; expect(t.leadingTicks + t.drawingTicks + t.trailingTicks).toBe(game.activeTicks);
      }
      expect(game.transferNetwork.reduce((sum, edge) => sum + edge.count, 0)).toBe(game.teams.red.transfers + game.teams.blue.transfers);
      expect(game.passNetwork.reduce((sum, edge) => sum + edge.count, 0)).toBe(game.teams.red.completedPasses + game.teams.blue.completedPasses);
      expect(Object.values(game.possessionTicks).reduce((sum, ticks) => sum + ticks, 0)).toBe(game.activeTicks);
      expect(game.teams.red.passesReceived).toBe(game.teams.red.completedPasses);
      expect(game.teams.blue.passesReceived).toBe(game.teams.blue.completedPasses);
      for (const player of game.players) {
        for (const metric of MATCH_COUNTERS) expect(player.maps[metric]).toHaveLength(player[metric]);
        expect(player.maps.heatmap.reduce((sum, cell) => sum + cell.ticks, 0)).toBe(player.activeTicks);
        expect(player).not.toHaveProperty('onFieldTicks');
        expect(player.peakSpeed).toBeGreaterThanOrEqual(player.averageSpeed);
        expect(player.distance).toBeGreaterThanOrEqual(0);
      }
    }
    expect(result.summary.observedGoals).toBe(fixture.goalTicks.flat().length);
    expect(result.summary.activeTicks).toBe(result.games.reduce((sum, g) => sum + g.activeTicks, 0));
    for (const team of ['red', 'blue']) for (const metric of [...MATCH_COUNTERS, 'possessionTicks']) {
      expect(result.summary.teams[team][metric]).toBe(result.games.reduce((sum, g) => sum + g.teams[team][metric], 0));
    }
  });

  it('keeps substitutions, player time and metrics isolated between real games', () => {
    const [first, second] = analyzeReplay(multiple).games;
    expect(first.players.some(p => p.nick === 'карпен')).toBe(false);
    const outgoing = second.players.find(p => p.nick === 'велосипедистка ленка');
    const incoming = second.players.find(p => p.nick === 'карпен');
    expect(outgoing.activeTicks).toBeGreaterThan(0);
    expect(incoming.activeTicks).toBeGreaterThan(0);
    expect(outgoing.activeTicks + incoming.activeTicks).toBe(second.activeTicks);
    expect(first.players.find(p => p.nick === 'R3venGe-').maps.kicks.every(e => e.tick < second.startTick)).toBe(true);
    expect(second.players.find(p => p.nick === 'R3venGe-').maps.kicks.every(e => e.tick >= second.startTick)).toBe(true);
    expect(second.events.some(e => e.type === 'team_change' && e.nick === 'карпен' && e.team === 'red')).toBe(true);
    const [bff] = analyzeReplay(readFileSync(new URL('./fixtures/cis4.hbr2', import.meta.url))).games;
    expect(bff.players.find(p => p.nick === 'Murphy').activeTicks + bff.players.find(p => p.nick === 'Олег Монгол').activeTicks).toBe(bff.activeTicks);
  });

  it('extracts timestamped impulses and contact episodes, and offers optional tracking', () => {
    let frames = 0; const streamed = [], progress = [];
    const result = analyzeReplay(single, { includeTracking: true, onFrame: () => frames++, onEvent: e => streamed.push(e), onProgress: p => progress.push(p) });
    expect(frames).toBe(result.ticks);
    expect(result.games[0].scoreRed).toBe(3); expect(result.games[0].scoreBlue).toBe(3);
    expect(progress.at(-1)).toBe(100);
    expect(result.tracking.length).toBeGreaterThan(1000);
    expect(result.tracking[0]).not.toHaveProperty('stadium');
    const events = result.games.flatMap(g => g.events);
    expect(streamed.length).toBe(events.length);
    expect(new Set(events.map(e => e.id)).size).toBe(events.length);
    for (const type of ['kick', 'contact', 'input', 'goal', 'transfer']) expect(events.some(e => e.type === type)).toBe(true);
    const kick = events.find(e => e.type === 'kick');
    expect(kick).toMatchObject({ playerId: expect.any(Number), tick: expect.any(Number), velocityBefore: { x: expect.any(Number), y: expect.any(Number) }, velocityAfter: { x: expect.any(Number), y: expect.any(Number) } });
    expect(kick.velocityBefore).not.toEqual(kick.velocityAfter);
    expect(events.find(e => e.type === 'contact').velocityAfterStep).toBeDefined();
    expect(JSON.parse(JSON.stringify(result))).toStrictEqual(normalizeSignedZero(result));
  }, 10000);

  it('isolates analyses, supports sliced buffers and optional event omission', () => {
    const first = analyzeReplay(single);
    analyzeReplay(multiple);
    const padded = Buffer.concat([Buffer.alloc(5), single, Buffer.alloc(7)]);
    expect(analyzeReplay(padded.subarray(5, 5 + single.length))).toEqual(first);
    const compact = analyzeReplay(single, { includeEvents: false });
    expect(compact).not.toHaveProperty('tracking');
    expect(compact.games[0]).not.toHaveProperty('events');
    expect(compact.summary).toEqual(first.summary);
  }, 10000);

  it('validates inputs and metric settings', () => {
    expect(() => analyzeReplay(new Uint8Array())).toThrow(/valid/);
    expect(() => analyzeReplay(single.subarray(0, 70))).toThrow();
    const bad = Uint8Array.from(single); new DataView(bad.buffer).setUint32(4, 4);
    expect(() => analyzeReplay(bad)).toThrow(/format 4/);
    new DataView(bad.buffer).setUint32(4, 3); new DataView(bad.buffer).setUint32(8, 216001);
    expect(() => analyzeReplay(bad)).toThrow(/one hour/);
    expect(() => analyzeReplay(single, { trackingInterval: 0 })).toThrow(/trackingInterval/);
    expect(() => analyzeReplay(single, { metrics: { heatmapCellSize: 0 } })).toThrow(/heatmapCellSize/);
  });
});

describe('new event and metric definitions', () => {
  it('keeps duplicate names separate and excludes pauses and reset teleports from movement', () => {
    const c = createCollector(), a = member(1, 'red'), b = member(2, 'red', 20);
    feed(c, 0, [a, b]);
    feed(c, 1, [a, b], [], { phase: 'paused' }, { players: [{ ...a, x: 999 }, b] });
    feed(c, 2, [a, b], [], { phase: 'goal' }, { phase: 'kickoff', players: [{ ...a, x: -100 }, b] });
    const game = c.finish()[0];
    expect(game.players).toHaveLength(2);
    expect(game.players.map(p => p.id)).toEqual(['1:red', '2:red']);
    expect(game.players.map(p => p.distance)).toEqual([1, 1]);
    expect(game.players[0]).toMatchObject({ activeTicks: 1, averageSpeed: 60 });
    expect(game).not.toHaveProperty('phaseTicks');
  });

  it('links kick-to-contact transfers, receptions, progression and opponent turnovers by ID', () => {
    const c = createCollector(), a = member(1, 'red', -80), b = member(2, 'red', 0), d = member(3, 'blue', 60);
    feed(c, 0, [a,b,d], [interaction('kick', 0, a, -80)]);
    feed(c, 1, [a,b,d], [interaction('contact', 1, b, 0)]);
    feed(c, 2, [a,b,d], [interaction('kick', 2, b, 0)]);
    feed(c, 3, [a,b,d], [interaction('contact', 3, d, 60)]);
    const game = c.finish()[0];
    expect(game.players.find(p => p.id === '1:red')).toMatchObject({ transfers: 1, progressiveTransfers: 1 });
    expect(game.players.find(p => p.id === '2:red')).toMatchObject({ received: 1, turnovers: 1 });
    expect(game.transferNetwork).toEqual([{ from: '1:red', to: '2:red', count: 1, distance: 80 }]);
    const transfer = game.events.find(e => e.type === 'transfer');
    expect(transfer).toMatchObject({ playerId: 1, receiverId: 2, releaseTick: 0, tick: 1 });
    expect(game.events.find(e => e.id === transfer.releaseEventId).type).toBe('kick');
    expect(game.events.find(e => e.id === transfer.receptionEventId).type).toBe('contact');
  });

  it('does not bridge paused play, stale releases, or ambiguous multi-player contacts', () => {
    for (const variant of ['pause', 'expired', 'contested']) {
      const c = createCollector(), a = member(1, 'red'), b = member(2, 'red'), d = member(3, 'blue');
      feed(c, 0, [a,b,d], [interaction('kick', 0, a)]);
      if (variant === 'pause') feed(c, 1, [a,b,d], [], { phase: 'paused' });
      const tick = variant === 'expired' ? 301 : 2;
      feed(c, tick, [a,b,d], [interaction('contact', tick, b), ...(variant === 'contested' ? [interaction('contact', tick, d)] : [])]);
      expect(c.finish()[0].teams.red.transfers).toBe(0);
    }
  });

  it('uses normalized goal geometry rather than assuming horizontal goals', () => {
    const c = createCollector();
    const rotated = { ...stadium, goals: [{ team: 'red', p0: [-20, -100], p1: [20, -100] }, { team: 'blue', p0: [-20, 100], p1: [20, 100] }] };
    feed(c, 0, [member(1, 'red')], [], { stadium: rotated, ball: { x: 0, y: -80, radius: 5 } });
    feed(c, 1, [member(1, 'red')], [], { stadium: rotated, ball: { x: 0, y: 0, radius: 5 } });
    feed(c, 2, [member(1, 'red')], [], { stadium: rotated, ball: { x: 0, y: 80, radius: 5 } });
    expect(c.finish()[0].thirds).toEqual([1,1,1]);
  });

  it('marks clipped games, records initial score and avoids scoring attribution across a reset', () => {
    const c = createCollector(), a = member(1, 'red');
    c.initial(frame(0, [a], { score: [2, 1] }));
    feed(c, 0, [a], [interaction('kick', 0, a)], { score: [2, 1] });
    feed(c, 1, [a], [], { phase: 'goal', score: [2, 1] });
    feed(c, 2, [a], [{ type: 'goal', tick: 2, gameId: 0, team: 'blue', position: { x: -100, y: 0 } }], { score: [2,1] }, { score: [2,2] });
    const game = c.finish()[0];
    expect(game.initialScore).toEqual([2,1]); expect(game.truncatedStart).toBe(true); expect(game.truncatedEnd).toBe(true);
    expect(game.goals[0].scorerId).toBeNull();
  });
});

it('attributes same-named scorer/assister by ID and keeps own goals separate from team scoring', () => {
  const c = createCollector(), a = member(1, 'red'), b = member(2, 'red');
  feed(c, 0, [a,b], [interaction('kick', 0, a)]);
  feed(c, 1, [a,b], [interaction('kick', 1, b)]);
  feed(c, 2, [a,b], [{ type: 'goal', gameId: 0, tick: 2, team: 'red', position: { x: 100, y: 0 } }]);
  feed(c, 3, [a,b], [], { phase: 'kickoff' });
  feed(c, 4, [a,b], [interaction('kick', 4, a)]);
  feed(c, 5, [a,b], [{ type: 'goal', gameId: 0, tick: 5, team: 'blue', position: { x: -100, y: 0 } }]);
  const game = c.finish()[0];
  expect(game.goals[0]).toMatchObject({ scorerId: 2, assistId: 1, ownGoal: false });
  expect(game.goals[1]).toMatchObject({ scorerId: 1, assistId: null, ownGoal: true });
  expect(game.players.find(p => p.playerId === 1)).toMatchObject({ goals: 0, assists: 1, ownGoals: 1 });
  expect(game.players.find(p => p.playerId === 2)).toMatchObject({ goals: 1, assists: 0 });
  expect(game.teams.blue.observedGoalsFor).toBe(1);
  expect(game.teams.red.observedGoalsFor).toBe(1);
});

it('does not carry transfer candidates across a team switch', () => {
  const c = createCollector(), a = member(1, 'red'), b = member(2, 'red');
  feed(c, 0, [a,b], [interaction('kick', 0, a)]);
  feed(c, 1, [{ ...a, team: 'blue' }, b], [{ type: 'team_change', gameId: 0, tick: 1, playerId: 1, team: 'blue', previousTeam: 'red' }, interaction('contact', 1, b)]);
  expect(c.finish()[0].teams.red.transfers).toBe(0);
});

it('records a stop even if the next game starts in the same recording tick', () => {
  const c = createCollector(), a = member(1, 'red');
  feed(c, 0, [a]);
  c.consume({ tick: 1, before: frame(1, [a], { gameId: 1 }), after: frame(1, [a], { gameId: 1 }), events: [
    { type: 'game_stop', gameId: 0, tick: 1 }, { type: 'game_start', gameId: 1, tick: 1 },
  ] });
  const [old, next] = c.finish();
  expect(old.endTick).toBe(1); expect(old.truncatedEnd).toBe(false);
  expect(old.events.at(-1).type).toBe('game_stop');
  expect(next.truncatedStart).toBe(false);
});

it('uses live play as the only metric time basis, including the activating kickoff tick', () => {
  const c = createCollector(), a = member(1, 'red'), b = member(2, 'red', 40);
  for (const [tick, phase] of ['kickoff', 'paused', 'goal', 'ended'].entries()) {
    feed(c, tick, [a,b], [{ ...interaction('kick', tick, a), phase }, { ...interaction('contact', tick, b), phase }], { phase });
  }
  feed(c, 4, [a,b], [{ ...interaction('kick', 4, a), phase: 'kickoff' }], { phase: 'kickoff' }, { phase: 'active' });
  feed(c, 5, [a,b], [interaction('contact', 5, b)]);
  const game = c.finish()[0];
  expect(game.activeTicks).toBe(2);
  expect(game.players.map(p => p.activeTicks)).toEqual([2,2]);
  expect(game.teams.red).toMatchObject({ kicks: 1, contacts: 1, transfers: 1 });
  expect(game.players.find(p => p.playerId === 1)).toMatchObject({ distance: 2, kicksPerMinute: 1800 });
  expect(game.thirds.reduce((a,b) => a+b, 0)).toBe(2);
  expect(game.events.filter(e => e.type === 'kick')).toHaveLength(5);
  expect(game.players.find(p => p.playerId === 1).maps.kicks).toHaveLength(1);
});
