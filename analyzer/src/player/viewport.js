// Native stadium dimensions are half-extents in world units. Leave a small
// margin around the bounds and reserve the native scoreboard's 35px bar.
export function fitPitchZoom(width, height, halfWidth, halfHeight) {
  if (!(width > 0 && height > 35 && halfWidth > 0 && halfHeight > 0)) return 1;
  return Math.min(width / (2 * (halfWidth + 16)), (height - 35) / (2 * (halfHeight + 16)));
}

export function mountFitPitch(controller) {
  const original = controller.uf;
  controller.uf = function (mode) {
    const view = this.j.Fb;
    const renderer = view.Eb;
    const stadium = this.ya.T.K?.S || this.ya.T.S;
    renderer.fitPitch = mode === -1;
    if (!renderer.fitPitch || !stadium) {
      renderer.jf = 0;
      return original.call(this, mode);
    }
    view.Gg(false);
    renderer.jf = 0;
    renderer.xf = 35;
    renderer.kf = fitPitchZoom(renderer.sa.clientWidth, renderer.sa.clientHeight, stadium.$b, stadium.qc);
  };
}
