import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { analyzeReplay } from '../src/engine/analyze.js';
import { serializeStats } from '../src/export-stats.js';

const single = readFileSync(new URL('./fixtures/big.hbr2', import.meta.url));
const multiple = readFileSync(new URL('./fixtures/handball.hbr2', import.meta.url));

describe('standalone replay analysis', () => {
  it('retains movement density and event coordinates in exported statistics', () => {
    const result = analyzeReplay(single, { includeFrames: true });
    const game = result.games[0];
    for (const player of game.players) {
      expect(player.maps.heatmap.reduce((total, cell) => total + cell.ticks, 0)).toBe(player.playedTicks);
      for (const key of ['kicks', 'passes', 'shots', 'goals', 'assists']) {
        expect(player.maps[key]).toHaveLength(player[key]);
      }
      for (const kick of player.maps.kicks) {
        expect(Number.isFinite(kick.x) && Number.isFinite(kick.y)).toBe(true);
      }
      for (const key of ['passes', 'shots', 'goals', 'assists']) {
        for (const event of player.maps[key]) {
          expect(Number.isFinite(event.from.x) && Number.isFinite(event.to.y)).toBe(true);
        }
      }
    }
    const exported = JSON.parse(serializeStats(result));
    expect(exported.games[0].players.map(p => p.maps)).toEqual(game.players.map(p => p.maps));
    expect(exported.games[0]).not.toHaveProperty('frames');
    expect(exported.games[0].goals[0].shot).toEqual(game.goals[0].shot);
  });

  it('reproduces the baseline core statistics and creates playback samples', () => {
    const progress = [];
    const result = analyzeReplay(single, { includeFrames: true, onProgress: value => progress.push(value) });
    expect(result.ticks).toBe(20494);
    expect(result.games).toHaveLength(1);
    const game = result.games[0];
    expect(game).toMatchObject({
      scoreRed: 1, scoreBlue: 2, gameTicks: 18375,
      kicks: [157, 196], passes: [17, 34], shots: [2, 14],
      possession: [7755, 10621], thirds: [9133, 5643, 3600],
      stadium: { name: 'Big' },
    });
    expect(game.goals.map(g => g.scorer)).toEqual(['#Nike#', 'kasia', 'kasia']);
    expect(game.goals.at(-1).assist).toBe('Reszka#18');
    expect(game.players.find(p => p.nick === 'kasia')).toMatchObject({ team: 'blue', goals: 2, playedTicks: 18376 });
    expect(game.frames.length).toBeGreaterThan(4000);
    expect(game.frames[20].players.length).toBeGreaterThan(0);
    expect(game.frames[20].discs.length).toBeGreaterThan(0);
    expect(progress.at(-1)).toBe(100);
  });

  it('separates games, side swaps and own goals', () => {
    const result = analyzeReplay(multiple, { includeFrames: true });
    expect(result.games.map(g => [g.scoreRed, g.scoreBlue, g.gameTicks])).toEqual([[2, 3, 36000], [0, 1, 36000]]);
    expect(result.games[0].goals.filter(g => g.ownGoal)).toHaveLength(1);
    expect(result.games[0].players.find(p => p.nick === 'Neymar')).toMatchObject({ team: 'red', goals: 1 });
    expect(result.games[1].players.find(p => p.nick === 'Neymar')).toMatchObject({ team: 'blue', goals: 1 });
    expect(result.games[1].frames[0].tick).toBeGreaterThan(result.games[0].frames.at(-1).tick);
  });

  it('isolates consecutive analyses and supports sliced Node buffers', () => {
    const first = analyzeReplay(single);
    expect(first.games[0]).not.toHaveProperty('frames');
    expect(first.games[0].startTick).toBeGreaterThanOrEqual(0);
    analyzeReplay(multiple);
    const backing = Buffer.concat([Buffer.alloc(13), single, Buffer.alloc(7)]);
    const again = analyzeReplay(backing.subarray(13, 13 + single.length));
    expect(again).toEqual(first);
  });

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
