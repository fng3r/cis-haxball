// @vitest-environment jsdom
import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import KeyboardShortcuts from '../src/components/KeyboardShortcuts.jsx';
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
it('opens the daisyUI reference from its button and the question mark key', () => {
  render(<KeyboardShortcuts />);
  fireEvent.click(screen.getByRole('button', { name: 'Keyboard shortcuts' }));
  const dialog = screen.getByRole('dialog', { name: 'Keyboard shortcuts' });
  expect(dialog).toHaveClass('modal');
  expect(screen.getByText('Pause / resume')).toBeInTheDocument();
  expect(screen.getByText('Native zoom modes')).toBeInTheDocument();
  dialog.open = false;
  fireEvent.keyDown(window, { key: '?', shiftKey: true });
  expect(dialog.open).toBe(true);
});
it('keeps text entry and other open dialogs undisturbed', () => {
  render(<><KeyboardShortcuts /><input aria-label="Text" /><dialog open aria-label="Other dialog" /></>);
  fireEvent.keyDown(screen.getByLabelText('Text'), { key: '?' });
  expect(screen.queryByRole('dialog', { name: 'Keyboard shortcuts' })).not.toBeInTheDocument();
  fireEvent.keyDown(window, { key: '?' });
  expect(screen.queryByRole('dialog', { name: 'Keyboard shortcuts' })).not.toBeInTheDocument();
});
it('accepts shortcut requests only from the native replay frame', () => {
  render(<><KeyboardShortcuts /><iframe title="Original HaxBall replay player" /></>);
  const frame = screen.getByTitle('Original HaxBall replay player');
  const data = { source: 'haxball-native-player', type: 'shortcuts' };
  fireEvent(window, new MessageEvent('message', { origin: location.origin, source: window, data }));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  fireEvent(window, new MessageEvent('message', { origin: location.origin, source: frame.contentWindow, data }));
  expect(screen.getByRole('dialog', { name: 'Keyboard shortcuts' })).toBeInTheDocument();
});
