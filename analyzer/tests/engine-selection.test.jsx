// @vitest-environment jsdom
import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import * as selection from '../src/engine-selection.js';
import EngineSwitcher from '../src/components/EngineSwitcher.jsx';
beforeEach(() => localStorage.clear());
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
it('defaults to the original engine, restores saved choices and allows URL overrides', () => {
  expect(selection.getEngine()).toBe('legacy');
  localStorage.setItem('replay-engine', 'v2');
  expect(selection.getEngine()).toBe('v2');
  expect(selection.getEngine('https://example.com/analyzer/?engine=legacy')).toBe('legacy');
  expect(selection.getEngine('https://example.com/analyzer/?engine=invalid')).toBe('v2');
});
it('persists a changed engine and navigates to a new document with the selected engine', () => {
  const navigate = vi.fn();
  selection.changeEngine('v2', { navigate });
  expect(localStorage.getItem('replay-engine')).toBe('v2');
  expect(navigate).toHaveBeenCalledTimes(1);
  expect(new URL(navigate.mock.calls[0][0]).searchParams.get('engine')).toBe('v2');
  selection.changeEngine('v2', { navigate });
  selection.changeEngine('invalid', { navigate });
  expect(navigate).toHaveBeenCalledTimes(1);
});
it('uses the URL even when browser storage is unavailable', () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Unavailable'); });
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Unavailable'); });
  const navigate = vi.fn();
  selection.changeEngine('v2', { navigate });
  expect(selection.getEngine(navigate.mock.calls[0][0])).toBe('v2');
});
it('offers both engines and triggers switching from the select', () => {
  const change = vi.spyOn(selection, 'changeEngine').mockImplementation(() => {});
  render(<EngineSwitcher engine="legacy" />);
  expect(screen.getByRole('option', { name: 'Original' })).toBeInTheDocument();
  fireEvent.change(screen.getByRole('combobox', { name: 'Analysis engine' }), { target: { value: 'v2' } });
  expect(change).toHaveBeenCalledWith('v2');
});
