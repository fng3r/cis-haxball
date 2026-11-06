// @vitest-environment jsdom
import React, { act, createRef } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import NativePlayer from '../src/components/NativePlayer.jsx';

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

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
