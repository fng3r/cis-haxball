import { expect, it, vi } from 'vitest';
import { fitPitchZoom, mountFitPitch } from '../src/player/viewport.js';

it('fits both stadium dimensions below the scoreboard on wide and narrow screens', () => {
  for (const [width, height] of [[1500, 650], [2200, 1000], [360, 280], [900, 350]]) {
    const zoom = fitPitchZoom(width, height, 700, 350);
    expect(2 * 716 * zoom).toBeLessThanOrEqual(width + 0.001);
    expect(2 * 366 * zoom).toBeLessThanOrEqual(height - 35 + 0.001);
    expect(Math.min(width - 2 * 716 * zoom, height - 35 - 2 * 366 * zoom)).toBeCloseTo(0);
  }
  expect(fitPitchZoom(0, 0, 700, 350)).toBe(1);
});

it('updates native zoom on resize and stadium changes while retaining manual view modes', () => {
  const renderer = { sa: { clientWidth: 1500, clientHeight: 650 }, jf: 450 };
  const stadium = { $b: 700, qc: 350 };
  const original = vi.fn();
  const controller = { j: { Fb: { Eb: renderer, Gg: vi.fn() } }, ya: { T: { K: { S: stadium } } }, uf: original };
  mountFitPitch(controller);
  controller.uf(-1);
  expect(renderer.fitPitch).toBe(true);
  expect(renderer.jf).toBe(0);
  expect(renderer.kf).toBe(fitPitchZoom(1500, 650, 700, 350));
  expect(controller.j.Fb.Gg).toHaveBeenCalledWith(false);
  renderer.sa.clientHeight = 450;
  controller.uf(-1);
  expect(renderer.kf).toBe(fitPitchZoom(1500, 450, 700, 350));
  controller.ya.T.K.S = { $b: 900, qc: 500 };
  controller.uf(-1);
  expect(renderer.kf).toBe(fitPitchZoom(1500, 450, 900, 500));
  expect(original).not.toHaveBeenCalled();
  for (const mode of [0, 1, 2, 3]) {
    controller.uf(mode);
    expect(renderer.fitPitch).toBe(false);
    expect(original).toHaveBeenLastCalledWith(mode);
  }
});
