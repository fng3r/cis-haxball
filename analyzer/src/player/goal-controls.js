export const GOAL_LEAD_IN_TICKS = 8 * 60;
export const goalSeekTick = (tick, previousGoal = -1) => Math.max(0, tick - GOAL_LEAD_IN_TICKS, previousGoal + 1);

export function adjacentGoal(goals, position, direction, anchor = null) {
  const index = goals.indexOf(anchor);
  // While watching a selected goal's build-up, repeated clicks move to the
  // adjacent goal rather than seeking to the same upcoming goal again.
  if (index >= 0 && position >= goalSeekTick(anchor, goals[index - 1]) - 1 && position <= anchor + 1) {
    return goals[index + direction];
  }
  return direction > 0 ? goals.find(tick => tick > position + 1) : goals.findLast(tick => tick < position - 1);
}

export function mountGoalControls(controls, replay, seek, onGoal = () => {}) {
  let goals = [], anchor = null;
  const document = controls.g.ownerDocument;
  function button(label, path) {
    const element = document.createElement('button');
    element.type = 'button';
    element.title = label;
    element.setAttribute('aria-label', label);
    element.disabled = true;
    element.innerHTML = `<svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true"><path d="${path}"/></svg>`;
    return element;
  }
  const previous = button('Previous goal', 'M1 1h2v10H1zm10 0L3 6l8 5z');
  const next = button('Next goal', 'M9 1h2v10H9zM1 1l8 5-8 5z');
  controls.g.querySelector('[data-hook=play]').after(previous, next);
  const position = () => (replay.Fd > 0 ? replay.Fd : replay.Qb) / replay.mh;
  function update() {
    const previousDisabled = adjacentGoal(goals, position(), -1, anchor) == null;
    const nextDisabled = adjacentGoal(goals, position(), 1, anchor) == null;
    if (previous.disabled !== previousDisabled) previous.disabled = previousDisabled;
    if (next.disabled !== nextDisabled) next.disabled = nextDisabled;
  }
  function seekGoal(tick) {
    const previousGoal = goals.findLast(goal => goal < tick);
    seek(goalSeekTick(tick, previousGoal));
    anchor = tick;
    update();
    onGoal(tick);
  }
  previous.onclick = () => { const tick = adjacentGoal(goals, position(), -1, anchor); if (tick != null) seekGoal(tick); };
  next.onclick = () => { const tick = adjacentGoal(goals, position(), 1, anchor); if (tick != null) seekGoal(tick); };
  // Manual scrubbing, game selection and reset invalidate the goal cursor.
  for (const method of ['er', 'ui']) {
    const original = replay[method];
    replay[method] = function (...args) { anchor = null; return original.apply(this, args); };
  }
  const refresh = controls.C;
  controls.C = function () { refresh.call(this); update(); };
  return {
    seekGoal,
    setGoals(ticks) {
      goals = [...new Set(ticks.filter(tick => Number.isFinite(tick) && tick >= 0 && tick <= replay.mf))].sort((a, b) => a - b);
      anchor = null;
      update();
    },
  };
}
