import { describe, expect, it } from 'vitest';
import { createCollector } from '../src/engine-v2/collector.js';
import { projectShot, MATCH_COUNTERS } from '../src/engine-v2/match-metrics.js';
import { aggregateGames } from '../src/engine-v2/analyze.js';
const stadium = { goals: [{ team: 'red', p0: [-100,-20], p1: [-100,20] }, { team: 'blue', p0: [100,-20], p1: [100,20] }], ballPhysics: { damping: 0.99, radius: 5, gravity: [0,0] } };
const member = (playerId, team, x = -50) => ({ playerId, nick: 'Same name', team, bodyId: playerId, x, y: 0, radius: 10, velocity: { x: 0, y: 0 } });
const a = member(1, 'red', -80), b = member(2, 'red', -20), d = member(3, 'blue', 70);
const touch = (type, tick, player, velocity = { x: 0, y: 5 }) => ({ ...player, type, tick, gameId: 0, gameTick: tick, phase: 'active', position: { x: player.x, y: player.y }, velocityAfter: velocity });
function step(c, tick, events = [], { players = [a,b,d], ball, phase = 'active', afterPhase = phase, changes = {}, afterChanges = {} } = {}) {
  const frame = { gameId: 0, gameTick: tick, phase, score: [0,0], stadium, ball: ball || { x: 0, y: 0, radius: 5, velocity: { x: 0, y: 0 } }, players, ...changes };
  c.consume({ tick, before: frame, after: { ...frame, gameTick: tick + 1, phase: afterPhase, ...afterChanges }, events });
}
const player = (c, id = 1) => c.finish()[0].players.find(p => p.playerId === id);
function receive(c, tick, receiver = b) {
  for (let i = 0; i < 6; i++) step(c, tick + i, i ? [] : [touch('contact', tick, receiver)], { ball: { x: receiver.x + 12, y: 0, radius: 5, velocity: { x: 0, y: 0 } } });
}

describe('completed passes and control', () => {
  it('confirms settled reception without a second kick and creates linked maps/network', () => {
    const c = createCollector(); step(c, 0, [touch('kick', 0, a)]); receive(c, 1);
    expect(player(c)).toMatchObject({ completedPasses: 1, progressivePasses: 1 });
    expect(player(c, 2).passesReceived).toBe(1);
    expect(player(c).maps.completedPasses[0]).toMatchObject({ receiverId: 2, releaseTick: 0, tick: 6, from: { x: -80, y: 0 }, to: { x: -8, y: 0 } });
    expect(c.finish()[0].passNetwork).toEqual([{ from: '1:red', to: '2:red', count: 1, distance: 72 }]);
    const events = c.finish()[0].events, pass = events.find(e => e.type === 'completed_pass');
    expect(events.find(e => e.id === pass.releaseEventId).type).toBe('kick');
    expect(events.find(e => e.id === pass.receptionEventId).type).toBe('contact');
  });
  it('confirms a next-player kick immediately without double-counting later contact', () => {
    const c = createCollector(); step(c, 0, [touch('kick', 0, a)]); step(c, 1, [touch('kick', 1, b)]); receive(c, 2);
    expect(player(c).completedPasses).toBe(1);
    expect(player(c, 2)).toMatchObject({ passesReceived: 1, completedPasses: 0 });
  });
  it('rejects deflections, simultaneous contacts and unstable or contested receptions', () => {
    for (const variant of ['deflection', 'simultaneous', 'contested', 'unstable']) {
      const c = createCollector(); step(c, 0, [touch('kick', 0, a)]);
      const players = variant === 'contested' ? [a,b,{ ...d, x: b.x }] : [a,b,d];
      for (let i = 1; i <= 8; i++) step(c, i, i === 1 ? [touch('contact', i, b), ...(variant === 'simultaneous' ? [touch('contact', i, d)] : [])] : [], {
        players, ball: { x: b.x + 12, y: 0, radius: 5, velocity: { x: variant === 'deflection' || (variant === 'unstable' && i % 2 === 0) ? 6 : 0, y: 0 } },
      });
      expect(player(c).completedPasses, variant).toBe(0);
    }
  });
  it('clears passes on expiry, pauses, restarts, self-recovery, team changes and defensive deflections', () => {
    for (const variant of ['expired', 'pause', 'restart', 'self', 'team_change', 'deflection']) {
      const c = createCollector(); step(c, 0, [touch('kick', 0, a)]);
      if (variant === 'pause') step(c, 1, [], { phase: 'paused' });
      if (variant === 'restart') step(c, 1, [{ type: 'restart', tick: 1, gameId: 0 }]);
      if (variant === 'self') receive(c, 1, a);
      if (variant === 'team_change') step(c, 1, [{ type: 'team_change', tick: 1, gameId: 0, playerId: 1, team: 'blue' }]);
      if (variant === 'deflection') step(c, 1, [touch('contact', 1, d)]);
      const tick = variant === 'expired' ? 301 : 10;
      step(c, tick, [touch('kick', tick, b)]);
      expect(player(c).completedPasses, variant).toBe(0);
    }
  });
  it('applies pitch-relative progression in both directions and rotated pitches', () => {
    const c = createCollector(); step(c, 0, [touch('kick', 0, a)]); step(c, 1, [touch('kick', 1, b)]); step(c, 2, [touch('kick', 2, a)]);
    expect(player(c).progressivePasses).toBe(1); expect(player(c, 2).progressivePasses).toBe(0);
    const e = member(4, 'blue', -30);
    step(c, 3, [touch('kick', 3, d)]); step(c, 4, [touch('kick', 4, e)], { players: [a,b,d,e] });
    expect(player(c, 3).progressivePasses).toBe(1);
    const rotated = { ...stadium, goals: [{ team: 'red', p0: [-20,-100], p1: [20,-100] }, { team: 'blue', p0: [-20,100], p1: [20,100] }] };
    const r = createCollector(), p = { ...a, x: 0, y: -80 }, q = { ...b, x: 0, y: 0 };
    step(r, 0, [touch('kick', 0, p, { x: 5, y: 0 })], { players: [p,q], changes: { stadium: rotated } });
    step(r, 1, [touch('kick', 1, q)], { players: [p,q], changes: { stadium: rotated } });
    expect(player(r).progressivePasses).toBe(1);
  });
});

describe('possession, recoveries and losses', () => {
  it('retains possession through flight and ignores deflections until control is established', () => {
    const c = createCollector(); step(c, 0); step(c, 1, [touch('kick', 1, a)]); step(c, 2, [touch('contact', 2, d)]); step(c, 3);
    expect(c.finish()[0].possessionTicks).toEqual({ red: 3, blue: 0, unassigned: 1 });
    expect(player(c).possessionLosses).toBe(0); expect(player(c, 3).recoveries).toBe(0);
    step(c, 4, [touch('kick', 4, d)]); step(c, 5, [touch('kick', 5, d)]);
    expect(player(c).possessionLosses).toBe(1); expect(player(c, 3).recoveries).toBe(1);
    expect(player(c, 3).maps.recoveries[0]).toMatchObject({ previousPlayerId: 1, to: { x: 70, y: 0 } });
  });
  it('recognizes controlled contact recoveries but not initial unowned reception', () => {
    const c = createCollector(); receive(c, 0, d); expect(player(c, 3).recoveries).toBe(0);
    receive(c, 6, b); expect(player(c, 2).recoveries).toBe(1); expect(player(c, 3).possessionLosses).toBe(1);
  });
  it('confirms the eventual winner of a contact duel without needing another collision event', () => {
    const c = createCollector(), opponent = { ...d, x: b.x + 3 };
    step(c, 0, [touch('kick', 0, a)]);
    step(c, 1, [touch('contact', 1, b), touch('contact', 1, opponent)], { players: [a,b,opponent], ball: { x: b.x + 12, y: 0, radius: 5, velocity: { x: 0, y: 0 } } });
    for (let tick = 2; tick < 8; tick++) step(c, tick, [], { players: [a,{ ...b, x: -60 },opponent], ball: { x: opponent.x + 12, y: 0, radius: 5, velocity: { x: 0, y: 0 } } });
    expect(player(c, 3).recoveries).toBe(1);
    expect(player(c).possessionLosses).toBe(1);
    expect(player(c).completedPasses).toBe(0);
  });
  it('treats a shot followed by settled self-recovery as ordinary possession again', () => {
    const c = createCollector(); step(c, 0, [touch('kick', 0, a, { x: 5, y: 0 })]); receive(c, 1, a);
    step(c, 7, [touch('kick', 7, d)]);
    expect(player(c).possessionLosses).toBe(1);
  });
  it('excludes shots from losses and all non-live activity from statistics', () => {
    const c = createCollector(); step(c, 0, [touch('kick', 0, a, { x: 5, y: 0 })]); step(c, 1, [touch('kick', 1, d)]);
    expect(player(c).shotsOnTarget).toBe(1); expect(player(c).possessionLosses).toBe(0); expect(player(c, 3).recoveries).toBe(1);
    for (const phase of ['paused', 'kickoff', 'goal', 'ended']) step(c, 2, [{ ...touch('kick', 2, a), phase }], { phase });
    expect(player(c).shotsOnTarget).toBe(1);
    expect(c.finish()[0].possessionTicks).toEqual({ red: 1, blue: 1, unassigned: 0 });
    step(c, 3, [{ ...touch('kick', 3, a), phase: 'kickoff' }], { phase: 'kickoff', afterPhase: 'active' });
    expect(player(c, 3).possessionLosses).toBe(0); expect(c.finish()[0].possessionTicks.red).toBe(2);
  });
});

describe('shots and key passes', () => {
  it('marks shooting unavailable instead of inventing zeros for unsupported ball physics', () => {
    const c = createCollector();
    step(c, 0, [touch('kick', 0, a, { x: 5, y: 0 })], { changes: { stadium: { ...stadium, ballPhysics: { ...stadium.ballPhysics, gravity: [0,1] } } } });
    expect(c.finish()[0].shotsAvailable).toBe(false);
    expect(player(c).shotsOnTarget).toBe(0);
    expect(() => createCollector({ controlTicks: 1.5 })).toThrow(/controlTicks/);
  });
  it('projects goal-mouth crossings with damping, radius and orientation', () => {
    const frame = { stadium, ball: { radius: 5 } };
    expect(projectShot(touch('kick', 0, a, { x: 5, y: 0 }), frame)).toEqual({ x: 100, y: 0 });
    for (const velocity of [{ x: -5, y: 0 }, { x: 5, y: 2 }, { x: 0, y: 5 }, { x: 0.1, y: 0 }]) expect(projectShot(touch('kick', 0, a, velocity), frame)).toBeNull();
    expect(projectShot({ ...touch('kick', 0, a, { x: 5, y: 0 }), position: { x: 0, y: 18 } }, frame)).toBeNull();
    expect(projectShot(touch('kick', 0, d, { x: -5, y: 0 }), frame)).toEqual({ x: -100, y: 0 });
    expect(projectShot(touch('kick', 0, a, { x: 5, y: 0 }), { ...frame, discs: [{ id: 0, damping: 0.99, gravity: { x: 0, y: 0.1 } }] })).toBeNull();
    const rotated = { ...stadium, goals: [{ team: 'red', p0: [-20,-100], p1: [20,-100] }, { team: 'blue', p0: [-20,100], p1: [20,100] }] };
    expect(projectShot({ ...touch('kick', 0, a, { x: 0, y: 5 }), position: { x: 0, y: 0 } }, { ...frame, stadium: rotated })).toEqual({ x: 0, y: 100 });
  });
  it('links the final completed pass to the receiver’s shot only once per pass', () => {
    const c = createCollector(); step(c, 0, [touch('kick', 0, a)]); step(c, 1, [touch('kick', 1, b, { x: 5, y: 0 })]); step(c, 2, [touch('kick', 2, b, { x: 5, y: 0 })]);
    expect(player(c)).toMatchObject({ completedPasses: 1, keyPasses: 1 }); expect(player(c, 2)).toMatchObject({ shotsOnTarget: 2, passesReceived: 1 });
    const game = c.finish()[0], pass = game.events.find(e => e.type === 'key_pass');
    expect(game.events.find(e => e.id === pass.passEventId).type).toBe('completed_pass'); expect(game.events.find(e => e.id === pass.shotEventId).type).toBe('shot_on_target');
    expect(player(c).maps.keyPasses[0]).toMatchObject({ from: { x: -80, y: 0 }, via: { x: -20, y: 0 }, to: { x: 100, y: 0 } });
  });
  it('does not create key passes after expiry or an opposing touch', () => {
    for (const variant of ['expired', 'deflected']) {
      const c = createCollector(); step(c, 0, [touch('kick', 0, a)]); step(c, 1, [touch('kick', 1, b)]);
      if (variant === 'deflected') step(c, 2, [touch('contact', 2, d)]);
      const tick = variant === 'expired' ? 482 : 3; step(c, tick, [touch('kick', tick, b, { x: 5, y: 0 })]);
      expect(player(c).keyPasses).toBe(0);
    }
  });
  it('conserves every displayed counter in player/team/recording totals and maps', () => {
    const c = createCollector(); step(c, 0, [touch('kick', 0, a)]); step(c, 1, [touch('kick', 1, b, { x: 5, y: 0 })]); step(c, 2, [touch('kick', 2, d)]);
    const games = c.finish(), summary = aggregateGames(games), game = games[0];
    for (const metric of MATCH_COUNTERS) for (const team of ['red', 'blue']) {
      expect(game.teams[team][metric]).toBe(game.players.filter(p => p.team === team).reduce((sum, p) => sum + p[metric], 0));
      expect(summary.teams[team][metric]).toBe(game.teams[team][metric]);
      for (const p of game.players) expect(p.maps[metric].length).toBe(p[metric]);
    }
    expect(Object.values(game.possessionTicks).reduce((sum, n) => sum + n, 0)).toBe(game.activeTicks);
    expect(summary.teams.red.possessionTicks).toBe(game.teams.red.possessionTicks);
  });
});
