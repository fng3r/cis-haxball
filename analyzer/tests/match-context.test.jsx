// @vitest-environment jsdom
import React from 'react';
import { File as NodeFile } from 'node:buffer';
import { webcrypto } from 'node:crypto';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { inferMapping, matchId, saveMapping, fetchMatchRecording } from '../src/match-context.js';
import MatchContext, { TeamIdentity } from '../src/components/MatchContext.jsx';

const context = {
  match: { id: 6862, url: '/championship/match/6862', season: { name: 'ЧР #17' }, league: { name: 'League' }, officialScore: [2, 1], isPlayed: true },
  teams: { home: { name: 'Home', logo: '/home.png' }, away: { name: 'Away', logo: '/away.png' } },
  rosters: { home: ['alice', 'sub'], away: ['bob'] }, canMap: true,
};
const game = { players: [
  { nick: 'Alice', team: 'red', playedTicks: 100 }, { nick: 'sub', team: 'red', playedTicks: 5 },
  { nick: 'Bob', team: 'blue', playedTicks: 100 },
] };
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('resolves each game independently across side swaps and substitutions, without guessing', () => {
  expect(inferMapping(game, context)).toBe(true);
  const swapped = { players: game.players.map(p => ({ ...p, team: p.team === 'red' ? 'blue' : 'red' })) };
  expect(inferMapping(swapped, context)).toBe(false);
  expect(inferMapping({ players: [...game.players, ...swapped.players] }, context)).toBe(null);
  expect(inferMapping(game, { ...context, rosters: { home: [], away: [] } })).toBe(null);
  expect(inferMapping(game, null)).toBe(null);
  expect(matchId('https://example.test/analyzer/')).toBe(null);
  expect(matchId('https://example.test/analyzer/?match=6862')).toBe('6862');
  expect(() => matchId('https://example.test/analyzer/?match=../x')).toThrow();
});

it('shows context, official score, unresolved state, and a per-game editor control', () => {
  const onMapping = vi.fn();
  render(<MatchContext context={context} mapping={null} game={game} onMapping={onMapping} />);
  expect(screen.getByRole('link', { name: /Back to match/ })).toHaveAttribute('href', '/championship/match/6862');
  expect(screen.getByText(/ЧР #17/)).toBeInTheDocument();
  expect(screen.getByText(/Official score 2:1/)).toBeInTheDocument();
  expect(screen.getByText(/Team mapping unresolved/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Red side team'), { target: { value: 'false' } });
  expect(onMapping).toHaveBeenCalledWith(false);
});

it('keeps standalone neutral labels and restricts editing to authorized users', () => {
  const { rerender } = render(<TeamIdentity fallback="Red team" />);
  expect(screen.getByText('Red team')).toBeInTheDocument();
  rerender(<TeamIdentity team={context.teams.away} fallback="Red team" />);
  expect(screen.getByText('Away')).toBeInTheDocument();
  expect(document.querySelector('img')).toHaveAttribute('src', '/away.png');
  rerender(<MatchContext context={{ ...context, canMap: false }} mapping={null} game={game} />);
  expect(screen.queryByRole('combobox')).toBeNull();
});

it('persists a mapping through the same-origin CSRF protected endpoint', async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true });
  vi.stubGlobal('fetch', fetch);
  document.cookie = 'csrftoken=token';
  await saveMapping({ mappingUrl: '/championship/match/6862/analyzer/recordings/0/mapping' }, 1, false);
  expect(fetch).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({
    method: 'POST', body: JSON.stringify({ game: 1, redIsHome: false }),
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': 'token' },
  }));
});


it('loads actual HBR2 bytes with size and server fingerprint checks', async () => {
  vi.stubGlobal('File', NodeFile);
  vi.stubGlobal('crypto', webcrypto);
  const bytes = new Uint8Array(12);
  bytes.set([0x48, 0x42, 0x52, 0x32]);
  const fetch = vi.fn().mockImplementation(async () => new Response(bytes));
  vi.stubGlobal('fetch', fetch);
  const recording = { name: 'match.hbr2', url: '/recording' };
  const file = await fetchMatchRecording(recording, new AbortController().signal);
  expect(new Uint8Array(await file.arrayBuffer())).toEqual(bytes);
  await expect(fetchMatchRecording({ ...recording, sha256: 'wrong' }, new AbortController().signal)).rejects.toThrow('changed');
  fetch.mockResolvedValue(new Response(bytes, { headers: { 'content-length': String(33 * 1024 * 1024) } }));
  await expect(fetchMatchRecording(recording, new AbortController().signal)).rejects.toThrow('32 MiB');
});
