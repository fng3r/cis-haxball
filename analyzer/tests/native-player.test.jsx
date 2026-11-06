// @vitest-environment jsdom
import React, { act, createRef } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import NativePlayer from '../src/components/NativePlayer.jsx';

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it('sends goals from every game and queues a timeline goal seek until the player is ready', () => {
  const ref = createRef();
  const props = { file: { arrayBuffer: vi.fn() }, onError: vi.fn(), onStats: vi.fn(), onClose: vi.fn() };
  const games = [{ goals: [{ tick: 1200 }] }, { goals: [{ tick: 3600 }] }];
  const view = render(<NativePlayer ref={ref} {...props} games={games} />);
  const frame = screen.getByTitle('Original HaxBall replay player');
  const post = vi.spyOn(frame.contentWindow, 'postMessage').mockImplementation(() => {});
  ref.current.seekGoal(3600);
  expect(post).not.toHaveBeenCalled();
  act(() => window.dispatchEvent(new MessageEvent('message', {
    origin: location.origin, source: frame.contentWindow,
    data: { source: 'haxball-native-player', type: 'ready' },
  })));
  expect(post).toHaveBeenCalledWith({ type: 'goals', ticks: [1200, 3600], starts: [0, 0] }, location.origin);
  expect(post).toHaveBeenLastCalledWith({ type: 'seek-goal', tick: 3600 }, location.origin);
  view.rerender(<NativePlayer ref={ref} {...props} games={[...games, { goals: [{ tick: 5000 }] }]} />);
  expect(post).toHaveBeenLastCalledWith({ type: 'goals', ticks: [1200, 3600, 5000], starts: [0, 0, 0] }, location.origin);
});

it('passes the original recording to the player and queues seeks until it is ready', async () => {
  const ref = createRef();
  const buffer = new ArrayBuffer(16);
  const file = { arrayBuffer: vi.fn(async () => buffer) };
  render(<NativePlayer ref={ref} file={file} onError={vi.fn()} onStats={vi.fn()} onClose={vi.fn()} />);
  const frame = screen.getByTitle('Original HaxBall replay player');
  const post = vi.spyOn(frame.contentWindow, 'postMessage').mockImplementation(() => {});
  fireEvent.load(frame);
  await waitFor(() => expect(post).toHaveBeenCalledWith({ type: 'open', buffer }, location.origin, [buffer]));
  ref.current.seek(1234);
  expect(post).toHaveBeenCalledTimes(1);
  act(() => window.dispatchEvent(new MessageEvent('message', {
    origin: location.origin, source: frame.contentWindow,
    data: { source: 'haxball-native-player', type: 'ready' },
  })));
  expect(post).toHaveBeenLastCalledWith({ type: 'seek', tick: 1234 }, location.origin);
  ref.current.seek(5678);
  expect(post).toHaveBeenLastCalledWith({ type: 'seek', tick: 5678 }, location.origin);
  expect(document.querySelector('canvas')).toBeNull();
});

it('ignores messages from other windows and accepts player errors from its own frame', () => {
  const onError = vi.fn();
  render(<NativePlayer file={{ arrayBuffer: vi.fn() }} onError={onError} onStats={vi.fn()} onClose={vi.fn()} />);
  const frame = screen.getByTitle('Original HaxBall replay player');
  const data = { source: 'haxball-native-player', type: 'error', message: 'Invalid replay' };
  act(() => window.dispatchEvent(new MessageEvent('message', { origin: location.origin, source: window, data })));
  expect(onError).not.toHaveBeenCalled();
  act(() => window.dispatchEvent(new MessageEvent('message', { origin: location.origin, source: frame.contentWindow, data })));
  expect(onError).toHaveBeenCalledWith('Invalid replay');
});

it('forwards workspace shortcuts only when the replay is ready and removes them on unmount', () => {
  const view = render(<NativePlayer file={{ arrayBuffer: vi.fn() }} onError={vi.fn()} onStats={vi.fn()} onClose={vi.fn()} />);
  const frame = screen.getByTitle('Original HaxBall replay player');
  const post = vi.spyOn(frame.contentWindow, 'postMessage').mockImplementation(() => {});
  fireEvent.keyDown(window, { key: 'ArrowRight' });
  expect(post).not.toHaveBeenCalled();
  act(() => window.dispatchEvent(new MessageEvent('message', {
    origin: location.origin, source: frame.contentWindow,
    data: { source: 'haxball-native-player', type: 'ready' },
  })));
  post.mockClear();
  for (const [key, action] of [['ArrowLeft', 'backward'], ['ArrowRight', 'forward'], ['ArrowUp', 'faster'], ['ArrowDown', 'slower'], [' ', 'toggle'], ['0', 'reset-zoom'], ['[', 'previous-goal'], [']', 'next-goal']]) {
    fireEvent.keyDown(window, { key });
    expect(post).toHaveBeenLastCalledWith({ type: 'hotkey', action }, location.origin);
  }
  view.unmount();
  fireEvent.keyDown(window, { key: 'ArrowRight' });
  expect(post).toHaveBeenCalledTimes(8);
});
