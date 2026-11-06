import { readFileSync } from 'node:fs';
import { beforeAll, describe, expect, it } from 'vitest';
import { analyzeReplay } from '../src/engine/analyze.js';
import { serializeStats } from '../src/export-stats.js';
import { replayCases } from './replay-fixtures.js';

const single = readFileSync(new URL('./fixtures/cis5.hbr2', import.meta.url));
const multiple = readFileSync(new URL('./fixtures/futsal-multi.hbr2', import.meta.url));

describe.each(replayCases)('original engine: $file', fixture => {
  let result;
  beforeAll(() => { result = analyzeReplay(readFileSync(new URL(`./fixtures/${fixture.file}`, import.meta.url)), { includeFrames: true }); });

  it('preserves native scores and original-engine regression statistics', () => {
    expect(result.ticks).toBe(fixture.ticks);
    expect(result.games.map(g => [g.scoreRed, g.scoreBlue])).toEqual(fixture.scores);
    for (const [i, game] of result.games.entries()) {
      expect(game).toMatchObject({ ...fixture.original[i], stadium: { name: fixture.stadium } });
      expect(game.goals.map(g => g.tick)).toEqual(fixture.goalTicks[i]);
    }
  });

  it('retains movement density, event coordinates and goal data in exports', () => {
    for (const game of result.games) for (const player of game.players) {
      expect(player.maps.heatmap.reduce((total, cell) => total + cell.ticks, 0)).toBe(player.playedTicks);
      for (const key of ['kicks', 'passes', 'shots', 'goals', 'assists']) expect(player.maps[key]).toHaveLength(player[key]);
      for (const kick of player.maps.kicks) expect(Number.isFinite(kick.x) && Number.isFinite(kick.y)).toBe(true);
      for (const key of ['passes', 'shots', 'goals', 'assists']) for (const event of player.maps[key]) {
        expect(Number.isFinite(event.from.x) && Number.isFinite(event.to.y)).toBe(true);
      }
    }
    const exported = JSON.parse(serializeStats(result));
    for (const [i, game] of result.games.entries()) {
      expect(exported.games[i].players.map(p => p.maps)).toEqual(game.players.map(p => p.maps));
      expect(exported.games[i]).not.toHaveProperty('frames');
      expect(exported.games[i].goals).toEqual(game.goals);
    }
  });

  it('keeps playback samples within the corresponding game', () => {
    for (const [i, game] of result.games.entries()) {
      expect(game.frames.length).toBeGreaterThan(4000);
      expect(game.frames.some(frame => frame.players.length && frame.discs.length)).toBe(true);
      if (i) expect(game.frames[0].tick).toBeGreaterThan(result.games[i - 1].frames.at(-1).tick);
    }
  });
});

describe('standalone replay analysis', () => {
  it('keeps substitutions and own-goal credits separate between matches', () => {
    const [first, second] = analyzeReplay(multiple).games;
    expect(first.goals.some(g => g.ownGoal)).toBe(true);
    expect(first.players.find(p => p.nick === 'R3venGe-')).toMatchObject({ team: 'red', goals: 3 });
    expect(second.players.find(p => p.nick === 'R3venGe-')).toMatchObject({ team: 'red', goals: 4 });
    expect(first.players.some(p => p.nick === 'карпен')).toBe(false);
    expect(second.players.find(p => p.nick === 'карпен')).toMatchObject({ team: 'red', playedTicks: 15836 });
  });

  it('isolates consecutive analyses, supports sliced buffers and reports completion', () => {
    const progress = [], first = analyzeReplay(single, { onProgress: value => progress.push(value) });
    expect(first.games[0]).not.toHaveProperty('frames');
    expect(first.games[0].startTick).toBeGreaterThanOrEqual(0);
    expect(progress.at(-1)).toBe(100);
    analyzeReplay(multiple);
    const backing = Buffer.concat([Buffer.alloc(13), single, Buffer.alloc(7)]);
    expect(analyzeReplay(backing.subarray(13, 13 + single.length))).toEqual(first);
  }, 10000);

  it('rejects invalid, unsupported, truncated and excessive recordings', () => {
    expect(() => analyzeReplay(new Uint8Array(0))).toThrow(/valid/);
    expect(() => analyzeReplay(new Uint8Array(20))).toThrow(/not an HBR2/);
    const header = Uint8Array.from(single);
    new DataView(header.buffer).setUint32(4, 4);
    expect(() => analyzeReplay(header)).toThrow(/format 4/);
    new DataView(header.buffer).setUint32(4, 3);
    new DataView(header.buffer).setUint32(8, 216001);
    expect(() => analyzeReplay(header)).toThrow(/one hour/);
    expect(() => analyzeReplay(single.subarray(0, 100))).toThrow();
  });
});
