export function gameAtTick(starts, tick) {
  if (!starts.length) return null;
  const index = starts.findLastIndex(start => start <= tick);
  return Math.max(0, index);
}

export function mountGameSync(controls, replay, onGame) {
  let starts = [], selected = null;
  function sync(force = false) {
    // During a seek the destination is authoritative, not the intermediate
    // simulation position while the original player catches up.
    const tick = (replay.Fd > 0 ? replay.Fd : replay.Qb) / replay.mh;
    const index = gameAtTick(starts, tick);
    if (index != null && (force || index !== selected)) {
      selected = index;
      onGame(index);
    }
  }
  for (const method of ['er', 'ui']) {
    const original = replay[method];
    replay[method] = function (...args) {
      const result = original.apply(this, args);
      sync(true);
      return result;
    };
  }
  const reset = controls.g.querySelector('[data-hook=reset]');
  const originalReset = reset.onclick;
  reset.onclick = function (...args) {
    // The native reset leaves a pending seek destination intact. Clear it so
    // resetting during a seek really returns to the beginning as well.
    replay.Fd = -1;
    return originalReset.apply(this, args);
  };
  const refresh = controls.C;
  controls.C = function () { refresh.call(this); sync(); };
  return { setGames(gameStarts) { starts = gameStarts; selected = null; sync(); } };
}
