// @vitest-environment jsdom
import { expect, it, vi } from 'vitest';
import { mountReplayHotkeys } from '../src/player/hotkeys.js';

function key(target, key, options = {}) {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...options });
  target.dispatchEvent(event);
  return event;
}

it('handles arrows and Space, allows repeated seeks, and cleans up its listener', () => {
  const dispatch = vi.fn();
  const unmount = mountReplayHotkeys(window, dispatch);
  try {
    expect(key(window, 'ArrowLeft').defaultPrevented).toBe(true);
    key(window, 'ArrowRight');
    key(window, 'ArrowRight', { repeat: true });
    key(window, ' ');
    key(window, ' ', { repeat: true });
    expect(dispatch.mock.calls.flat()).toEqual(['backward', 'forward', 'forward', 'toggle']);
    unmount();
    expect(key(window, 'ArrowLeft').defaultPrevented).toBe(false);
    expect(dispatch).toHaveBeenCalledTimes(4);
  } finally { unmount(); }
});

it('preserves editing, button activation, modified shortcuts, and scrolling before a replay is ready', () => {
  const dispatch = vi.fn(() => false);
  const unmount = mountReplayHotkeys(window, dispatch);
  const container = document.createElement('div');
  container.innerHTML = '<input /><textarea></textarea><select></select><div contenteditable="true"><span>Edit</span></div><button>Play</button>';
  document.body.append(container);
  try {
    for (const element of container.querySelectorAll('input, textarea, select, span')) {
      expect(key(element, 'ArrowLeft').defaultPrevented).toBe(false);
      key(element, ' ');
    }
    key(container.querySelector('button'), ' ');
    for (const modifier of ['ctrlKey', 'metaKey', 'altKey', 'shiftKey']) key(window, 'ArrowRight', { [modifier]: true });
    expect(dispatch).not.toHaveBeenCalled();
    expect(key(window, 'ArrowLeft').defaultPrevented).toBe(false);
    expect(dispatch).toHaveBeenCalledWith('backward');
  } finally { unmount(); container.remove(); }
});
