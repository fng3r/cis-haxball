// @vitest-environment jsdom
import React from 'react';
import { readFileSync } from 'node:fs';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import App from '../src/App.jsx';
import { V2Overview } from '../src/components/V2Stats.jsx';
import { analyzeReplay } from '../src/engine-v2/analyze.js';
import { serializeStats } from '../src/export-stats.js';
const result = analyzeReplay(Uint8Array.from(readFileSync('tests/fixtures/big.hbr2')));
class FakeWorker {
  static instances = [];
  constructor(url) { this.url = url; FakeWorker.instances.push(this); }
  postMessage = vi.fn(); terminate = vi.fn();
  send(data) { this.onmessage({ data }); }
}
beforeEach(() => {
  localStorage.clear(); localStorage.setItem('replay-engine', 'v2'); FakeWorker.instances = [];
  vi.stubGlobal('Worker', FakeWorker);
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
async function open() {
  render(<App />);
  const file = new File(['replay'], 'fixture.hbr2'); file.arrayBuffer = async () => new ArrayBuffer(16);
  fireEvent.change(screen.getByLabelText('Open HaxBall replay'), { target: { files: [file] } });
  await waitFor(() => expect(FakeWorker.instances[0].postMessage).toHaveBeenCalled());
  const worker = FakeWorker.instances[0];
  act(() => worker.send({ type: 'result', result }));
  return worker;
}
it('uses the v2 worker and displays significant v2 metrics without legacy possession or shots', async () => {
  const worker = await open();
  expect(worker.url.pathname).toMatch(/engine-v2\/analyze.worker.js$/);
  expect(screen.getByRole('combobox', { name: 'Analysis engine' })).toHaveValue('v2');
  for (const label of ['Goals', 'Assists', 'Own goals', 'Kicks']) expect(screen.getByText(label)).toBeInTheDocument();
  for (const label of ['Loose ball', 'Contested ball', 'Ball proximity', 'Average width', 'Average depth', 'Observed transfers', 'Progressive transfers', 'Contact episodes', 'Turnovers', 'Distance travelled']) expect(screen.queryByText(label)).not.toBeInTheDocument();
  expect(screen.queryByText('Possession')).not.toBeInTheDocument();
  expect(screen.queryByText('Shots on goal')).not.toBeInTheDocument();
  expect(screen.getByRole('img', { name: /^Ball territory:/ })).toBeInTheDocument();
  const exported = JSON.parse(serializeStats(result));
  expect(exported.schemaVersion).toBe(2); expect(exported.summary).toEqual(result.summary);
  expect(exported.games[0].events.length).toBeGreaterThan(0);
});
it('selects new event maps by click, retains them on hover, and sorts player metrics', async () => {
  await open(); fireEvent.click(screen.getByRole('tab', { name: 'players' }));
  const player = result.games[0].players.find(p => p.team === 'red');
  fireEvent.click(screen.getByRole('button', { name: `Kicks map for ${player.nick}` }));
  expect(screen.getByRole('img', { name: `${player.nick}: Kicks` })).toBeInTheDocument();
  const other = result.games[0].players.find(p => p.id !== player.id);
  fireEvent.mouseEnter(screen.getByRole('button', { name: other.nick }));
  expect(screen.getByRole('img', { name: `${player.nick}: Kicks` })).toBeInTheDocument();
  fireEvent.change(screen.getByRole('combobox', { name: 'Map statistic' }), { target: { value: 'goals' } });
  expect(screen.getByRole('img', { name: `${player.nick}: Goals` })).toBeInTheDocument();
  expect(screen.queryByText('Average speed')).not.toBeInTheDocument();
  expect(screen.queryByRole('option', { name: 'Contacts' })).not.toBeInTheDocument();
  expect(screen.queryByRole('option', { name: 'Transfers' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Kicks' }));
  expect(screen.getByRole('columnheader', { name: 'Kicks' })).toHaveAttribute('aria-sort', 'descending');
  fireEvent.click(screen.getByRole('button', { name: 'Kicks' }));
  expect(screen.getByRole('columnheader', { name: 'Kicks' })).toHaveAttribute('aria-sort', 'ascending');
  fireEvent.click(screen.getByRole('button', { name: 'Kicks' }));
  expect(screen.getByRole('columnheader', { name: 'Kicks' })).not.toHaveAttribute('aria-sort');
});
it('adapts v2 goal scores to the existing timeline and seeks the native player', async () => {
  await open();
  const frame = screen.getByTitle('Original HaxBall replay player');
  const post = vi.spyOn(frame.contentWindow, 'postMessage').mockImplementation(() => {});
  act(() => window.dispatchEvent(new MessageEvent('message', { origin: location.origin, source: frame.contentWindow, data: { source: 'haxball-native-player', type: 'ready' } })));
  fireEvent.click(screen.getByRole('tab', { name: 'goals · 3' }));
  const goal = result.games[0].goals[0];
  fireEvent.click(screen.getByRole('button', { name: new RegExp(`score ${goal.score[0]}–${goal.score[1]}$`) }));
  expect(post).toHaveBeenLastCalledWith({ type: 'seek-goal', tick: goal.tick }, location.origin);
});
it('shows captured statistics without a coverage warning and handles missing geometry', () => {
  render(<V2Overview game={{ ...result.games[0], truncatedStart: true, territoryAvailable: false }} />);
  expect(screen.queryByText(/Partial recording:/)).not.toBeInTheDocument();
  expect(screen.queryByText('Active play')).not.toBeInTheDocument();
  expect(screen.getByText('Goals')).toBeInTheDocument();
  expect(screen.getByText(/Ball territory is unavailable/)).toBeInTheDocument();
  expect(screen.queryByRole('img')).not.toBeInTheDocument();
});

it('does not overlay horizontal zones on a rotated goal axis', () => {
  const game = result.games[0];
  render(<V2Overview game={{ ...game, stadium: { ...game.stadium, goals: [{ team: 'red', p0: [-20,-100], p1: [20,-100] }, { team: 'blue', p0: [-20,100], p1: [20,100] }] } }} />);
  expect(screen.getByText(/Time in each third/)).toBeInTheDocument();
  expect(screen.queryByRole('img', { name: /^Ball territory:/ })).not.toBeInTheDocument();
});
