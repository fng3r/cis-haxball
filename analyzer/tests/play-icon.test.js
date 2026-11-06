// @vitest-environment jsdom
import { expect, it } from 'vitest';
import { setNativePlayIcon } from '../src/player/play-icon.js';

it('renders font-independent play and pause icons and updates the button label', () => {
  const button = document.createElement('button');
  const icon = document.createElement('i');
  button.append(icon);
  setNativePlayIcon(icon, false);
  expect(button.getAttribute('aria-label')).toBe('Play replay');
  expect(icon.querySelector('svg path')).not.toBeNull();
  expect(icon.textContent).toBe('');
  const playShape = icon.querySelector('path').getAttribute('d');
  setNativePlayIcon(icon, true);
  expect(button.getAttribute('aria-label')).toBe('Pause replay');
  expect(icon.querySelector('path').getAttribute('d')).not.toBe(playShape);
  expect(icon.querySelectorAll('svg')).toHaveLength(1);
  setNativePlayIcon(icon, false);
  expect(icon.querySelector('path').getAttribute('d')).toBe(playShape);
});
