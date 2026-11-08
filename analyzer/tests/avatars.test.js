import { beforeEach, describe, expect, it, vi } from 'vitest';
import { analyzeReplay } from '../src/engine/analyze.js';
import { createRuntime } from '../src/engine/vendor-runtime.js';

vi.mock('../src/engine/vendor-runtime.js', () => ({ createRuntime: vi.fn() }));

function analyzeStates(states) {
  const matches = Array.from({ length: Math.max(...states.map(s => s.game || 0)) + 1 }, () => ({
    stadium: { name: 'Avatar test', goals: [] }, gameTicks: states.length,
    scoreRed: 0, scoreBlue: 0, possRed: 0, possBlue: 0, thirds: [0, 0, 0],
    kicks: [], passes: [], shots: [], goals: [],
    kicksRed: 0, kicksBlue: 0, passesRed: 0, passesBlue: 0, shotsRed: 0, shotsBlue: 0,
  }));
  createRuntime.mockImplementation(() => {
    let current = -1;
    return {
      load() {}, step() { current++; }, matches,
      get currentMatch() { return states[current].game || 0; },
      get state() {
        const s = states[current];
        return {
          K: { Bb: s.live === false ? 2 : 1, Oa: s.paused ? 1 : 0 },
          I: [{ V: 1, w: 'Player', ea: { $: s.team || 1 },
            H: s.offField ? null : { a: { x: 0, y: 0 } }, Xb: s.avatar, Jd: s.override }],
        };
      },
    };
  });
  const bytes = new Uint8Array(12), header = new DataView(bytes.buffer);
  header.setUint32(0, 0x48425232); header.setUint32(4, 3); header.setUint32(8, states.length);
  return analyzeReplay(bytes);
}

beforeEach(() => createRuntime.mockReset());

describe('effective avatar during observed play', () => {
  it('uses the room override before the player-selected avatar', () => {
    const player = analyzeStates([{ avatar: '9', override: 'GK' }]).games[0].players[0];
    expect(player.avatar).toBe('GK');
  });

  it('keeps the last active value, ignoring later goal celebrations and pauses', () => {
    const player = analyzeStates([
      { avatar: '9' }, { avatar: '😀' }, { avatar: 'NO', live: false }, { avatar: 'XX', paused: true },
    ]).games[0].players[0];
    expect(player.avatar).toBe('😀');
    expect(player.playedTicks).toBe(2);
  });

  it('retains an explicit clear instead of the previous nonempty avatar', () => {
    expect(analyzeStates([{ avatar: 'R3' }, { avatar: null }]).games[0].players[0].avatar).toBeNull();
  });

  it('preserves a blank override instead of falling back to the selected avatar', () => {
    expect(analyzeStates([{ avatar: '9', override: '' }]).games[0].players[0].avatar).toBe('');
  });

  it('restores the selected avatar when the room override is removed', () => {
    expect(analyzeStates([{ avatar: 'R3', override: 'GK' }, { avatar: 'R3', override: null }])
      .games[0].players[0].avatar).toBe('R3');
  });

  it('keeps separate values for games and replay sides', () => {
    const result = analyzeStates([
      { avatar: 'R3' }, { avatar: '57', team: 2 }, { avatar: 'Kz', game: 1 },
    ]);
    expect(result.games[0].players.map(p => [p.team, p.avatar])).toEqual([['red', 'R3'], ['blue', '57']]);
    expect(result.games[1].players[0].avatar).toBe('Kz');
  });

  it('ignores avatar changes after the player leaves the field', () => {
    expect(analyzeStates([{ avatar: 'R3' }, { avatar: 'NO', offField: true }]).games[0].players[0].avatar).toBe('R3');
  });
});
