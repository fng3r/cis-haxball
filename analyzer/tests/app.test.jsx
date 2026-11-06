// @vitest-environment jsdom
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import App from '../src/App.jsx';

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
    expect(screen.getByTitle('Original HaxBall replay player')).toHaveAttribute('src', '/player.html');
    expect(document.querySelector('canvas')).toBeNull();
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
