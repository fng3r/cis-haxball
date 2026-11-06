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
    key(window, 'ArrowUp');
    key(window, 'ArrowDown');
    key(window, '0');
    for (const keyName of ['1', '2', '3', '4']) expect(key(window, keyName).defaultPrevented).toBe(false);
    key(window, ' ');
    key(window, ' ', { repeat: true });
    expect(dispatch.mock.calls.flat()).toEqual(['backward', 'forward', 'forward', 'faster', 'slower', 'reset-zoom', 'toggle']);
    unmount();
    expect(key(window, 'ArrowLeft').defaultPrevented).toBe(false);
    expect(dispatch).toHaveBeenCalledTimes(7);
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
      key(element, '0');
    }
    key(container.querySelector('button'), ' ');
    for (const modifier of ['ctrlKey', 'metaKey', 'altKey', 'shiftKey']) key(window, 'ArrowRight', { [modifier]: true });
    expect(dispatch).not.toHaveBeenCalled();
    expect(key(window, 'ArrowLeft').defaultPrevented).toBe(false);
    expect(dispatch).toHaveBeenCalledWith('backward');
  } finally { unmount(); container.remove(); }
});

it('suspends playback shortcuts while a workspace dialog is open', () => {
  const dispatch = vi.fn();
  const unmount = mountReplayHotkeys(window, dispatch);
  const dialog = document.createElement('dialog'); dialog.open = true;
  document.body.append(dialog);
  try {
    key(window, 'ArrowLeft'); key(window, ' ');
    expect(dispatch).not.toHaveBeenCalled();
  } finally { unmount(); dialog.remove(); }
});
