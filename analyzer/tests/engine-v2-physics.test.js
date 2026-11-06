import { readFileSync } from 'node:fs';
import { inflateRaw } from 'pako';
import { expect, it } from 'vitest';
import { createRuntime as originalRuntime } from '../src/engine/vendor-runtime.js';
import { createRuntime as nextRuntime } from '../src/engine-v2/vendor-runtime.js';
import { replayCases } from './replay-fixtures.js';

it.each(replayCases)('preserves original simulation throughout $file', ({ file }) => {
  const bytes = Uint8Array.from(readFileSync(new URL(`./fixtures/${file}`, import.meta.url)));
  const original = originalRuntime(inflateRaw), next = nextRuntime(inflateRaw);
  const ticks = original.load(bytes); next.load(bytes);
  for (let tick = 0; tick < ticks; tick++) {
    original.step(); const { after } = next.step();
    if (tick % 60 !== 0 && tick !== ticks - 1) continue;
    const state = original.state, game = state.K;
    expect(after.gameTick).toBe(Math.round((game?.Hc || 0) * 60));
    expect(after.score).toEqual(game ? [game.Pb, game.Kb] : [0,0]);
    for (const player of state.I.filter(p => p.H)) {
      const actual = after.players.find(p => p.playerId === player.V);
      expect([actual.x, actual.y, actual.velocity.x, actual.velocity.y]).toEqual([player.H.a.x, player.H.a.y, player.H.D.x, player.H.D.y]);
    }
    if (game) expect([after.ball.x, after.ball.y, after.ball.velocity.x, after.ball.velocity.y]).toEqual([game.ta.F[0].a.x, game.ta.F[0].a.y, game.ta.F[0].D.x, game.ta.F[0].D.y]);
  }
});
