// @vitest-environment jsdom
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import App from '../src/App.jsx';
import * as matchIntegration from '../src/match-context.js';

class FakeWorker {
  static instances = [];
  constructor() { FakeWorker.instances.push(this); }
  postMessage = vi.fn();
  terminate = vi.fn();
  send(data) { this.onmessage({ data }); }
}

const game = {
  id: 0, stadium: { name: 'Big', width: 420, height: 200, vertexes: [], segments: [], goals: [] },
  gameTicks: 3600, scoreRed: 1, scoreBlue: 0, possession: [60, 40],
  thirds: [20, 30, 50], kicks: [3, 2], passes: [2, 1], shots: [1, 0],
  players: [{ id: '1:red', nick: 'Alice', team: 'red', goals: 1, assists: 0, kicks: 3, passes: 2, shots: 1, playedTicks: 3600 }],
  goals: [{ scorer: 'Alice', team: 'red', tick: 400, gameTick: 300, scoreRed: 1, scoreBlue: 0 }],
  frames: [{ tick: 0, gameTick: 0, discs: [], players: [] }, { tick: 400, gameTick: 300, discs: [], players: [] }],
};

beforeEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
  FakeWorker.instances = [];
  vi.stubGlobal('Worker', FakeWorker);
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

async function loadFile() {
  const file = new File(['replay'], 'match.hbr2');
  file.arrayBuffer = async () => new ArrayBuffer(16);
  fireEvent.change(screen.getByLabelText('Open HaxBall replay'), { target: { files: [file] } });
  await waitFor(() => expect(FakeWorker.instances.at(-1).postMessage).toHaveBeenCalled());
  return FakeWorker.instances.at(-1);
}

describe('local replay workspace', () => {
  it('switches game statistics on native timeline seeks and back to the first game on reset', async () => {
    render(<App />);
    const worker = await loadFile();
    act(() => worker.send({ type: 'result', result: { games: [game, { ...game, id: 1, startTick: 10000 }] } }));
    const frame = screen.getByTitle('Original HaxBall replay player');
    function playerGame(index) {
      act(() => window.dispatchEvent(new MessageEvent('message', {
        origin: location.origin, source: frame.contentWindow,
        data: { source: 'haxball-native-player', type: 'game', message: index },
      })));
    }
    playerGame(1);
    expect(screen.getByRole('button', { name: /Game 2/ })).toHaveAttribute('aria-pressed', 'true');
    playerGame(0);
    expect(screen.getByRole('button', { name: /Game 1/ })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: /Game 2/ })).toHaveAttribute('aria-pressed', 'false');
  });

  it('keeps game selection in sync when native goal navigation crosses games', async () => {
    render(<App />);
    const worker = await loadFile();
    const second = { ...game, id: 1, goals: [{ ...game.goals[0], tick: 10000 }] };
    act(() => worker.send({ type: 'result', result: { games: [game, second] } }));
    const frame = screen.getByTitle('Original HaxBall replay player');
    const secondButton = screen.getByRole('button', { name: /Game 2/ });
    expect(secondButton).toHaveAttribute('aria-pressed', 'false');
    act(() => window.dispatchEvent(new MessageEvent('message', {
      origin: location.origin, source: frame.contentWindow,
      data: { source: 'haxball-native-player', type: 'goal', message: 10000 },
    })));
    expect(secondButton).toHaveAttribute('aria-pressed', 'true');
  });

  it('shows movement heatmaps on player selection and event maps on statistic clicks', async () => {
    render(<App />);
    const worker = await loadFile();
    const maps = { heatmap: [{ x: 0, y: 0, ticks: 20 }], goals: [], assists: [], kicks: [{ x: 10, y: 20 }], passes: [], shots: [] };
    act(() => worker.send({ type: 'result', result: { games: [{ ...game, players: [{ ...game.players[0], maps }] }] } }));
    fireEvent.click(screen.getByRole('tab', { name: 'players' }));
    fireEvent.mouseEnter(screen.getByRole('button', { name: 'Alice' }));
    expect(screen.getByRole('img', { name: 'Alice: Movement heatmap' })).toBeInTheDocument();
    for (const [column, map] of [['Goals', 'Goals'], ['Assists', 'Assists'], ['Kicks', 'Kicks'], ['Passes', 'Passes'], ['On target', 'Shots on goal']]) {
      fireEvent.click(screen.getByRole('button', { name: `${column} map for Alice` }));
      expect(screen.getByRole('img', { name: `Alice: ${map}` })).toBeInTheDocument();
    }
    fireEvent.click(screen.getByRole('button', { name: 'Alice' }));
    expect(screen.getByRole('img', { name: 'Alice: Movement heatmap' })).toBeInTheDocument();
  });

  it('cycles metric sorting through descending, ascending, and default team order', async () => {
    render(<App />);
    const worker = await loadFile();
    const players = [
      { ...game.players[0], id: '2:blue', nick: 'Bob', team: 'blue', goals: 3 },
      { ...game.players[0], id: '3:red', nick: 'Charlie', goals: 2 },
      game.players[0],
    ];
    act(() => worker.send({ type: 'result', result: { games: [{ ...game, players }] } }));
    fireEvent.click(screen.getByRole('tab', { name: 'players' }));
    const order = () => screen.getAllByRole('row').slice(1).map(row => within(row).getAllByRole('button')[0].textContent.trim());
    expect(order()).toEqual(['Charlie', 'Alice', 'Bob']);
    fireEvent.click(screen.getByRole('button', { name: 'Goals' }));
    expect(order()).toEqual(['Bob', 'Charlie', 'Alice']);
    expect(screen.getByRole('columnheader', { name: /Goals/ })).toHaveAttribute('aria-sort', 'descending');
    fireEvent.click(screen.getByRole('button', { name: /^Goals(?: [↑↓])?$/ }));
    expect(order()).toEqual(['Alice', 'Charlie', 'Bob']);
    expect(screen.getByRole('columnheader', { name: /Goals/ })).toHaveAttribute('aria-sort', 'ascending');
    fireEvent.click(screen.getByRole('button', { name: /^Goals(?: [↑↓])?$/ }));
    expect(order()).toEqual(['Charlie', 'Alice', 'Bob']);
    expect(screen.getByRole('columnheader', { name: 'Goals' })).not.toHaveAttribute('aria-sort');
  });

  it('defaults to dark mode and remembers a light-mode choice across mounts', () => {
    const view = render(<App />);
    expect(document.documentElement).toHaveAttribute('data-theme', 'replay-dark');
    fireEvent.click(screen.getByRole('button', { name: 'Switch to light mode' }));
    expect(document.documentElement).toHaveAttribute('data-theme', 'replay');
    expect(localStorage.getItem('replay-theme')).toBe('replay');
    view.unmount();
    render(<App />);
    expect(screen.getByRole('button', { name: 'Switch to dark mode' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Switch to dark mode' }));
    expect(document.documentElement).toHaveAttribute('data-theme', 'replay-dark');
    expect(localStorage.getItem('replay-theme')).toBe('replay-dark');
  });

  it('starts with an empty workspace and never starts a worker until a file is selected', () => {
    render(<App />);
    expect(screen.getByText('Every match has a story.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Play' })).not.toBeInTheDocument();
    expect(FakeWorker.instances).toHaveLength(0);
  });

  it('loads a recording, selects a second game and shows player statistics', async () => {
    render(<App />);
    const worker = await loadFile();
    worker.send({ type: 'result', result: { games: [game, { ...game, id: 1, stadium: { ...game.stadium, name: 'Second pitch' } }] } });
    await waitFor(() => expect(screen.getByRole('button', { name: /Game 2/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Game 2/ }));
    expect(screen.getByTitle('Original HaxBall replay player')).toHaveAttribute('src', `${import.meta.env.BASE_URL}player.html`);
    expect(screen.getByRole('img', { name: 'Ball territory: Red third 20%, Middle 30%, Blue third 50%' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'players' }));
    fireEvent.click(screen.getByRole('button', { name: 'Alice' }));
    expect(screen.getByRole('button', { name: 'Alice' })).toHaveAttribute('aria-pressed', 'true');
    expect(worker.terminate).toHaveBeenCalled();
  });

  it('reports a worker failure and allows choosing another file', async () => {
    render(<App />);
    const worker = await loadFile();
    worker.send({ type: 'error', message: 'The recording is damaged.' });
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('The recording is damaged.'));
    expect(screen.queryByText(/Analyzing recording/)).not.toBeInTheDocument();
    await loadFile();
    expect(FakeWorker.instances).toHaveLength(2);
  });

  it('cancels analysis and ignores a late response from the cancelled worker', async () => {
    render(<App />);
    const worker = await loadFile();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    worker.send({ type: 'result', result: { games: [game] } });
    expect(worker.terminate).toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Play' })).not.toBeInTheDocument();
    expect(screen.getByText('Every match has a story.')).toBeInTheDocument();
  });
});

function recordingFile(name) {
  const file = new File(['replay'], name);
  file.arrayBuffer = vi.fn(async () => new ArrayBuffer(16));
  return file;
}
async function addRecordings(files, drop = false) {
  if (drop) fireEvent.drop(screen.getByText('Bring your replays.').parentElement, { dataTransfer: { files } });
  else fireEvent.change(screen.getByLabelText('Open HaxBall replay'), { target: { files } });
  await waitFor(() => expect(FakeWorker.instances.at(-1).postMessage).toHaveBeenCalled());
  return FakeWorker.instances.at(-1);
}

describe('multiple recordings', () => {
  it('analyzes one file at a time and switches cached results without mixing games', async () => {
    render(<App />);
    expect(screen.getByLabelText('Open HaxBall replay')).toHaveAttribute('multiple');
    const first = await addRecordings([recordingFile('first.hbr2'), recordingFile('second.hbr2')]);
    expect(FakeWorker.instances).toHaveLength(1);
    act(() => first.send({ type: 'result', result: { games: [game, { ...game, id: 1 }] } }));
    await waitFor(() => expect(FakeWorker.instances).toHaveLength(2));
    const second = FakeWorker.instances[1];
    await waitFor(() => expect(second.postMessage).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: /Game 2/ }));
    act(() => second.send({ type: 'result', result: { games: [{ ...game, goals: [] }] } }));
    expect(screen.getByRole('button', { name: /Game 2/ })).toHaveAttribute('aria-pressed', 'true');
    const frame = screen.getByTitle('Original HaxBall replay player');
    fireEvent.click(screen.getByRole('button', { name: 'Open recording second.hbr2' }));
    expect(screen.queryByRole('button', { name: /Game 2/ })).not.toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'goals · 0' })).toBeInTheDocument();
    expect(screen.getByTitle('Original HaxBall replay player')).not.toBe(frame);
    fireEvent.click(screen.getByRole('button', { name: 'Open recording first.hbr2' }));
    expect(screen.getByRole('button', { name: /Game 2/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'goals · 1' })).toBeInTheDocument();
    expect(FakeWorker.instances).toHaveLength(2);
    expect(screen.getAllByTitle('Original HaxBall replay player')).toHaveLength(1);
  });

  it('accepts multiple dropped files and continues after an individual analysis fails', async () => {
    render(<App />);
    const first = await addRecordings([recordingFile('broken.hbr2'), recordingFile('good.hbr2')], true);
    act(() => first.send({ type: 'error', message: 'Damaged recording.' }));
    await waitFor(() => expect(FakeWorker.instances).toHaveLength(2));
    const second = FakeWorker.instances[1];
    await waitFor(() => expect(second.postMessage).toHaveBeenCalled());
    act(() => second.send({ type: 'result', result: { games: [game] } }));
    expect(screen.getByRole('alert')).toHaveTextContent('broken.hbr2: Damaged recording.');
    fireEvent.click(screen.getByRole('button', { name: 'Open recording good.hbr2' }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Game 1/ })).toBeInTheDocument();
  });

  it('validates each file independently while retaining valid files from the batch', async () => {
    render(<App />);
    const large = recordingFile('large.hbr2');
    Object.defineProperty(large, 'size', { value: 33 * 1024 * 1024 });
    await addRecordings([recordingFile('notes.txt'), large, recordingFile('good.hbr2')]);
    expect(screen.getByRole('alert')).toHaveTextContent('notes.txt:');
    expect(screen.getByRole('alert')).toHaveTextContent('large.hbr2:');
    expect(screen.getByRole('button', { name: 'Open recording good.hbr2' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Open recording large.hbr2' })).not.toBeInTheDocument();
    expect(FakeWorker.instances).toHaveLength(1);
  });

  it('cancels the queue, ignores late messages and can retry a cancelled recording', async () => {
    render(<App />);
    const first = await addRecordings([recordingFile('first.hbr2'), recordingFile('second.hbr2')]);
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    act(() => first.send({ type: 'result', result: { games: [game] } }));
    expect(first.terminate).toHaveBeenCalled();
    expect(FakeWorker.instances).toHaveLength(1);
    expect(screen.getAllByText('Cancelled')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: /Game 1/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry analysis of second.hbr2' }));
    await waitFor(() => expect(FakeWorker.instances).toHaveLength(2));
    await waitFor(() => expect(FakeWorker.instances[1].postMessage).toHaveBeenCalled());
  });

  it('removes an active recording, advances the queue and ignores the removed result', async () => {
    render(<App />);
    const first = await addRecordings([recordingFile('first.hbr2'), recordingFile('second.hbr2')]);
    fireEvent.click(screen.getByRole('button', { name: 'Remove recording first.hbr2' }));
    await waitFor(() => expect(FakeWorker.instances).toHaveLength(2));
    expect(first.terminate).toHaveBeenCalled();
    act(() => first.send({ type: 'result', result: { games: [game] } }));
    expect(screen.queryByRole('button', { name: 'Open recording first.hbr2' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open recording second.hbr2' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByRole('button', { name: /Game 1/ })).not.toBeInTheDocument();
  });

  it('selects the first newly added file while retaining earlier recordings', async () => {
    const view = render(<App />);
    const first = await addRecordings([recordingFile('first.hbr2')]);
    act(() => first.send({ type: 'result', result: { games: [game] } }));
    const frame = screen.getByTitle('Original HaxBall replay player');
    const second = await addRecordings([recordingFile('second.hbr2'), recordingFile('third.hbr2')]);
    expect(FakeWorker.instances).toHaveLength(2);
    expect(screen.getByTitle('Original HaxBall replay player')).not.toBe(frame);
    expect(screen.getByRole('button', { name: 'Open recording first.hbr2' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: 'Open recording second.hbr2' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Open recording third.hbr2' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.queryByRole('button', { name: /Game 1/ })).not.toBeInTheDocument();
    view.unmount();
    expect(second.terminate).toHaveBeenCalled();
    act(() => second.send({ type: 'result', result: { games: [game] } }));
    expect(FakeWorker.instances).toHaveLength(2);
  });
});

it('continues the batch after an unreadable file', async () => {
  render(<App />);
  const broken = recordingFile('unreadable.hbr2');
  broken.arrayBuffer.mockRejectedValue(new Error('Read failed'));
  await addRecordings([broken, recordingFile('good.hbr2')]);
  await waitFor(() => expect(FakeWorker.instances).toHaveLength(2));
  expect(FakeWorker.instances[0].terminate).toHaveBeenCalled();
  expect(screen.getByRole('alert')).toHaveTextContent('Could not read the recording.');
  expect(FakeWorker.instances[1].postMessage).toHaveBeenCalled();
});

it('times out only the active file and advances to the next recording', async () => {
  vi.useFakeTimers();
  try {
    render(<App />);
    await act(async () => {
      fireEvent.change(screen.getByLabelText('Open HaxBall replay'), {
        target: { files: [recordingFile('slow.hbr2'), recordingFile('next.hbr2')] },
      });
    });
    expect(FakeWorker.instances).toHaveLength(1);
    const first = FakeWorker.instances[0];
    const frame = screen.getByTitle('Original HaxBall replay player');
    act(() => window.dispatchEvent(new MessageEvent('message', { origin: location.origin, source: frame.contentWindow, data: { source: 'haxball-native-player', type: 'ready' } })));
    await act(async () => vi.advanceTimersByTime(120_000));
    expect(first.terminate).toHaveBeenCalled();
    expect(FakeWorker.instances).toHaveLength(2);
    expect(FakeWorker.instances[1].postMessage).toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('Analysis took longer than two minutes.');
    act(() => first.send({ type: 'result', result: { games: [game] } }));
    expect(screen.queryByRole('button', { name: /Game 1/ })).not.toBeInTheDocument();
  } finally { cleanup(); vi.useRealTimers(); }
});

it('clears completed, active and queued recordings and ignores late results', async () => {
  render(<App />);
  const first = await addRecordings([recordingFile('done.hbr2'), recordingFile('active.hbr2'), recordingFile('queued.hbr2')]);
  act(() => first.send({ type: 'result', result: { games: [game] } }));
  await waitFor(() => expect(FakeWorker.instances).toHaveLength(2));
  const active = FakeWorker.instances[1];
  await waitFor(() => expect(active.postMessage).toHaveBeenCalled());
  expect(screen.getByRole('button', { name: /Game 1/ })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Clear all recordings' }));
  expect(active.terminate).toHaveBeenCalled();
  expect(screen.queryByRole('region', { name: 'Recordings' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Open recording/ })).not.toBeInTheDocument();
  expect(screen.queryByTitle('Original HaxBall replay player')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Game 1/ })).not.toBeInTheDocument();
  act(() => active.send({ type: 'result', result: { games: [game] } }));
  expect(FakeWorker.instances).toHaveLength(2);
  expect(screen.queryByRole('button', { name: /Game 1/ })).not.toBeInTheDocument();
  await addRecordings([recordingFile('fresh.hbr2')]);
  expect(FakeWorker.instances).toHaveLength(3);
  expect(screen.getByRole('button', { name: 'Open recording fresh.hbr2' })).toHaveAttribute('aria-pressed', 'true');
});

it('enters and exits focus mode without replacing the native player', async () => {
  render(<App />);
  const worker = await loadFile();
  act(() => worker.send({ type: 'result', result: { games: [game] } }));
  const frame = screen.getByTitle('Original HaxBall replay player');
  fireEvent.keyDown(window, { key: 'f' });
  fireEvent.keyDown(window, { key: 'f', repeat: true });
  expect(screen.getByRole('button', { name: 'Exit focus mode' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.queryByRole('tab', { name: 'overview' })).not.toBeInTheDocument();
  expect(document.body.style.overflow).toBe('hidden');
  expect(screen.getByTitle('Original HaxBall replay player')).toBe(frame);
  fireEvent.keyDown(window, { key: 'Escape' });
  expect(screen.getByRole('tab', { name: 'overview' })).toBeInTheDocument();
  expect(document.body.style.overflow).not.toBe('hidden');
  fireEvent.click(screen.getByRole('button', { name: 'Focus mode' }));
  act(() => window.dispatchEvent(new MessageEvent('message', { origin: location.origin, source: frame.contentWindow, data: { source: 'haxball-native-player', type: 'toggle-focus' } })));
  expect(screen.getByRole('button', { name: 'Focus mode' })).toHaveAttribute('aria-pressed', 'false');
  expect(screen.getByTitle('Original HaxBall replay player')).toBe(frame);
});

it('changes player maps only on click and displays playtime as plain text', async () => {
  render(<App />);
  const worker = await loadFile();
  const bob = { ...game.players[0], id: '2:blue', nick: 'Bob', team: 'blue' };
  act(() => worker.send({ type: 'result', result: { games: [{ ...game, players: [...game.players, bob] }, { ...game, id: 1 }] } }));
  fireEvent.click(screen.getByRole('tab', { name: 'players' }));
  expect(screen.getByRole('button', { name: 'Alice' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('button', { name: 'Alice' }).closest('tr')).toHaveClass('bg-base-200');
  expect(screen.getByRole('button', { name: 'Bob' })).toHaveAttribute('aria-pressed', 'false');
  fireEvent.mouseEnter(screen.getByRole('button', { name: 'Bob' }));
  expect(screen.getByRole('img', { name: 'Alice: Movement heatmap' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Kicks map for Alice' }));
  fireEvent.mouseEnter(screen.getByRole('button', { name: 'Bob' }));
  fireEvent.focus(screen.getByRole('button', { name: 'Bob' }));
  fireEvent.mouseEnter(screen.getByRole('button', { name: 'Alice' }));
  expect(screen.getByRole('img', { name: 'Alice: Kicks' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('tab', { name: 'overview' }));
  fireEvent.click(screen.getByRole('tab', { name: 'players' }));
  fireEvent.mouseEnter(screen.getByRole('button', { name: 'Bob' }));
  expect(screen.getByRole('img', { name: 'Alice: Kicks' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Bob' }).closest('tr'));
  expect(screen.getByRole('img', { name: 'Bob: Movement heatmap' })).toBeInTheDocument();
  fireEvent.mouseEnter(screen.getByRole('button', { name: 'Alice' }));
  expect(screen.getByRole('img', { name: 'Bob: Movement heatmap' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Played map for Bob' })).not.toBeInTheDocument();
  expect(within(screen.getByRole('button', { name: 'Bob' }).closest('tr')).getByText('1:00')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Alice' }));
  fireEvent.click(screen.getByRole('button', { name: /Game 2/ }));
  expect(screen.queryByRole('button', { name: 'Unpin player' })).not.toBeInTheDocument();
});



it.each([null, 100])('loads the whole match and selects the requested part %s by game ID', async requestedPart => {
  const previous = window.location.href;
  const url = 'https://django.test/championship/match/6862/analyzer';
  window.history.replaceState({}, '', `/analyzer/?context=${encodeURIComponent(url)}${requestedPart ? `&part=${requestedPart}` : ''}`);
  const context = {
    schemaVersion: 2,
    match: { id: 6862, url: 'https://django.test/championship/match/6862', season: { name: 'ЧР #17' }, officialScore: [2, 1] },
    teams: { home: { name: 'Home', logo: '/home.png' }, away: { name: 'Away', logo: '/away.png' } },
    recordings: [{ id: 10, name: 'a.hbr2', url: 'https://django.test/a' }, { id: 11, name: 'b.hbr2', url: 'https://django.test/b' }],
    parts: [{ id: 101, recordingId: 11, gameId: 0, order: 0, included: true, redIsHome: false, label: 'Half', displayLabel: 'Half [1]' },
      { id: 100, recordingId: 10, gameId: 1, order: 1, included: true, redIsHome: true, label: 'Half', displayLabel: 'Half [2]' },
      { id: 102, recordingId: 10, gameId: 0, order: 2, included: false, redIsHome: true, label: 'Warmup' }],
  };
  vi.spyOn(matchIntegration, 'fetchMatchContext').mockResolvedValue(context);
  vi.spyOn(matchIntegration, 'fetchMatchRecording').mockImplementation(async item => {
    const file = new File(['HBR2'], item.name);
    file.arrayBuffer = async () => new ArrayBuffer(16);
    return file;
  });
  try {
    render(<App />);
    await waitFor(() => expect(FakeWorker.instances.at(-1)?.postMessage).toHaveBeenCalled());
    act(() => FakeWorker.instances[0].send({ type: 'result', result: { games: [game, { ...game, id: 1, startTick: 1000 }] } }));
    await waitFor(() => expect(FakeWorker.instances).toHaveLength(2));
    await waitFor(() => expect(FakeWorker.instances[1].postMessage).toHaveBeenCalled());
    act(() => FakeWorker.instances[1].send({ type: 'result', result: { games: [game] } }));
    await waitFor(() => expect(screen.getByRole('button', { name: requestedPart ? 'Half [2]' : 'Half [1]' })).toHaveAttribute('aria-pressed', 'true'));
    expect(matchIntegration.fetchMatchContext).toHaveBeenCalledWith(expect.objectContaining({ href: url }), expect.any(AbortSignal));
    expect(matchIntegration.fetchMatchRecording).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('button', { name: 'Warmup' })).toBeNull();
    const scoreboard = screen.getByLabelText('Replay scoreboard');
    const red = scoreboard.firstElementChild.firstElementChild;
    expect(document.querySelector('.bg-error').parentElement).toHaveTextContent('Red team');
    const away = within(scoreboard).getByText('Away').parentElement;
    expect(away.lastElementChild.tagName).toBe('IMG');
    expect(red).toHaveTextContent(requestedPart ? 'Home' : 'Away');
    expect(red.querySelector('img')).toHaveAttribute('src', requestedPart ? '/home.png' : '/away.png');
    const destination = requestedPart ? 'Half [1]' : 'Half [2]';
    fireEvent.click(screen.getByRole('button', { name: destination }));
    await waitFor(() => expect(scoreboard.firstElementChild.firstElementChild).toHaveTextContent(requestedPart ? 'Away' : 'Home'));
    expect(screen.getByRole('button', { name: destination })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Open recording b.hbr2' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Half [1]' })).toHaveAttribute('aria-pressed', 'true'));
    const partCard = screen.getByRole('button', { name: 'Half [1]' });
    expect(partCard).toHaveTextContent('Big');
    expect(partCard).toHaveTextContent('1:0');
    expect(screen.getByRole('heading', { name: 'Half [1]' })).toBeInTheDocument();
    expect(scoreboard).toHaveTextContent('Half [1]');
    fireEvent.click(screen.getByRole('tab', { name: 'players' }));
    const playerButton = screen.getByRole('button', { name: 'Away Alice' });
    expect(playerButton.querySelector('img')).toHaveAttribute('src', '/away.png');
    expect(playerButton.querySelector('img').nextSibling.textContent).toContain('Alice');
    expect(screen.queryByRole('combobox', { name: 'Red side team' })).toBeNull();
  } finally { window.history.replaceState({}, '', previous); }
});
