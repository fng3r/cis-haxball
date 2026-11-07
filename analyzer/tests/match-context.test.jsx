// @vitest-environment jsdom
import React from 'react';
import { File as NodeFile } from 'node:buffer';
import { webcrypto } from 'node:crypto';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { contextURL, fetchMatchContext, fetchMatchRecording } from '../src/match-context.js';
import MatchContext, { TeamIdentity } from '../src/components/MatchContext.jsx';

const manifestURL = 'https://django.test/championship/match/6862/analyzer';
const context = {
  schemaVersion: 2,
  match: { id: 6862, url: '/championship/match/6862', season: { name: 'ЧР #17' }, officialScore: [2, 1], isPlayed: true },
  teams: { home: { name: 'Home', logo: '/home.png' }, away: { name: 'Away', logo: '/away.png' } },
  recordings: [{ id: 1, name: 'match.hbr2', url: '/recording' }],
  parts: [{ id: 10, recordingId: 1, gameId: 7, label: 'Second half', order: 1, included: true, redIsHome: false },
    { id: 11, recordingId: 1, gameId: 3, label: 'Warmup', order: 0, included: false, redIsHome: true }],
};
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('uses an explicitly supplied Django URL independent of the analyzer origin, retaining standalone use', () => {
  expect(contextURL('https://analyzer.test/analyzer/')).toBe(null);
  expect(contextURL(`https://analyzer.test/analyzer/?context=${encodeURIComponent(manifestURL)}`).href).toBe(manifestURL);
  expect(() => contextURL('https://analyzer.test/?context=file:///etc/passwd')).toThrow();
});

it('reads a whole-match manifest without credentials and resolves URLs against Django', async () => {
  const fetch = vi.fn().mockImplementation(async () => new Response(JSON.stringify(context)));
  vi.stubGlobal('fetch', fetch);
  const loaded = await fetchMatchContext(manifestURL, new AbortController().signal);
  expect(fetch).toHaveBeenCalledWith(manifestURL, expect.objectContaining({ credentials: 'omit' }));
  expect(loaded.match.url).toBe('https://django.test/championship/match/6862');
  expect(loaded.recordings[0].url).toBe('https://django.test/recording');
  expect(loaded.teams.home.logo).toBe('https://django.test/home.png');
  expect(loaded.parts.map(part => part.id)).toEqual([11, 10]);
});

it('rejects malformed manifests and recording URLs outside the supplied Django origin', async () => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => new Response(JSON.stringify({ ...context, recordings: [{ id: 1, url: 'https://evil.test/file' }] }))));
  await expect(fetchMatchContext(manifestURL, new AbortController().signal)).rejects.toThrow('manifest origin');
});

it('displays Django context and mappings read-only, without selectors or editing controls', () => {
  render(<MatchContext context={context} part={context.parts[0]} />);
  expect(screen.queryByRole('link', { name: /Back to match/ })).toBeNull();
  expect(screen.getByText(/ЧР #17/)).toBeInTheDocument();
  const score = screen.getByText('2:1');
  expect(score.previousElementSibling).toHaveTextContent('Home');
  expect(score.nextElementSibling).toHaveTextContent('Away');
  expect(screen.queryByText(/Official score/)).toBeNull();
  expect(screen.queryByText('Second half')).toBeNull();
  expect(screen.queryByText(/Replay statistics cover/)).toBeNull();
  expect(screen.getByLabelText('Match context').querySelectorAll('img')).toHaveLength(2);
  expect(screen.queryByRole('combobox')).toBeNull();
});

it('retains neutral standalone branding and displays the supplied team logo', () => {
  const { rerender } = render(<TeamIdentity fallback="Red team" />);
  expect(screen.getByText('Red team')).toBeInTheDocument();
  rerender(<TeamIdentity team={context.teams.away} fallback="Red team" />);
  expect(screen.getByText('Away')).toBeInTheDocument();
  expect(document.querySelector('img')).toHaveAttribute('src', '/away.png');
});

it('loads actual HBR2 bytes with size and fingerprint checks', async () => {
  vi.stubGlobal('File', NodeFile);
  vi.stubGlobal('crypto', webcrypto);
  const bytes = new Uint8Array(12);
  bytes.set([0x48, 0x42, 0x52, 0x32]);
  const fetch = vi.fn().mockImplementation(async () => new Response(bytes));
  vi.stubGlobal('fetch', fetch);
  const recording = { name: 'match.hbr2', url: 'https://django.test/recording' };
  const file = await fetchMatchRecording(recording, new AbortController().signal);
  expect(new Uint8Array(await file.arrayBuffer())).toEqual(bytes);
  expect(fetch).toHaveBeenCalledWith(recording.url, expect.objectContaining({ credentials: 'omit' }));
  await expect(fetchMatchRecording({ ...recording, sha256: 'wrong' }, new AbortController().signal)).rejects.toThrow('changed');
  fetch.mockResolvedValue(new Response(bytes, { headers: { 'content-length': String(33 * 1024 * 1024) } }));
  await expect(fetchMatchRecording(recording, new AbortController().signal)).rejects.toThrow('32 MiB');
});


it('shows the concise season, league-stage and tour line without repeating the league or group', () => {
  const { rerender } = render(<MatchContext context={{ ...context, match: { ...context.match,
    season: { name: 'ЧР, 17 сезон' }, league: { name: 'Единая лига' },
    stage: { name: 'Единая лига – Регулярка' }, group: { name: 'Группа A' }, tour: { name: '1 тур' },
  } }} />);
  expect(screen.getByText('ЧР, 17 сезон · Единая лига – Регулярка · 1 тур')).toBeInTheDocument();
  expect(screen.queryByText(/Группа A/)).toBeNull();
  rerender(<MatchContext context={{ ...context, match: { ...context.match,
    season: { name: 'ЧР, 17 сезон' }, league: { name: 'Единая лига' }, stage: null, tour: { name: '1 тур' },
  } }} part={{ ...context.parts[0], label: 'Тайм', displayLabel: 'Тайм [2]' }} />);
  expect(screen.getByText('ЧР, 17 сезон · Единая лига · 1 тур')).toBeInTheDocument();
  expect(screen.queryByText('Тайм [2]')).toBeNull();
});


it('uses short team titles on small screens in every team identity, retaining full titles on larger screens', () => {
  render(<TeamIdentity team={{ name: 'A long away team name', shortName: 'AWAY', logo: '/away.png' }} logoAfter />);
  expect(screen.getByText('AWAY')).toBeInTheDocument();
  expect(screen.getByText('A long away team name')).toBeInTheDocument();
  expect(screen.getByText('AWAY').parentElement.parentElement.lastElementChild).toHaveAttribute('src', '/away.png');
});
