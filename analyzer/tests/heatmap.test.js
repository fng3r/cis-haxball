import { expect, it } from 'vitest';
import { densityPixels } from '../src/components/heatmap-density.js';

const stadium = { width: 500, height: 250 };
it('renders empty movement as transparent', () => {
  expect(densityPixels([], stadium).pixels.every(value => value === 0)).toBe(true);
});

it('makes busy areas warmer and more opaque while smoothing nearby movement', () => {
  const { pixels, width } = densityPixels([
    { x: -200, y: 0, ticks: 1000 }, { x: 200, y: 0, ticks: 50 },
  ], stadium);
  const busy = (62 * width + 75) * 4;
  const quiet = (62 * width + 175) * 4;
  expect(pixels[busy]).toBeGreaterThan(pixels[quiet]);
  expect(pixels[busy + 3]).toBeGreaterThan(pixels[quiet + 3]);
  expect(pixels[busy + 4 + 3]).toBeGreaterThan(0);
  expect(pixels[3]).toBe(0);
});

it('keeps relative density stable for the same movement over a longer duration', () => {
  const cells = [{ x: -100, y: 0, ticks: 100 }, { x: 100, y: 0, ticks: 40 }];
  const first = densityPixels(cells, stadium).pixels;
  const longer = densityPixels(cells.map(cell => ({ ...cell, ticks: cell.ticks * 4 })), stadium).pixels;
  expect(longer).toEqual(first);
});
