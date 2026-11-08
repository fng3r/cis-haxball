// Role inference uses live movement, not nicknames, actions or a prescribed lineup.
// Coordinates are relative to the goal a replay side defends, never Django home/away.
export const POSITION_VERSION = 1;
export const POSITION_WINDOW_TICKS = 30 * 60;
const SAMPLE_TICKS = 6;
const MIN_TICKS = 10 * 60;
const clamp = value => Math.max(0, Math.min(1, value));
const round = value => Math.round(value * 1000) / 1000;

export function positionGeometry(stadium) {
  const center = team => {
    const goals = stadium?.goals?.filter(goal => goal.team === team);
    // Multiple goals per side do not define a conventional football pitch.
    if (goals?.length !== 1) return null;
    const { p0, p1 } = goals[0];
    if (![...p0, ...p1].every(Number.isFinite)) return null;
    return { x: (p0[0] + p1[0]) / 2, y: (p0[1] + p1[1]) / 2 };
  };
  const red = center('red'), blue = center('blue');
  if (!red || !blue) return null;
  const length = Math.hypot(blue.x - red.x, blue.y - red.y);
  if (length < 1) return null;
  return { red, blue, length };
}

/** Classify contemporaneous teammates; no fixed player count or mandatory role slots. */
export function classifyPositionWindow(players) {
  const eligible = players.filter(p => p.ticks >= MIN_TICKS).sort((a, b) => a.depth - b.depth);
  const result = new Map();
  if (eligible.length < 2) return result;
  for (const player of eligible) {
    if (player.depth < 0.6 && player.rearShare >= 0.6 && player.aheadGap >= 0.04) {
      result.set(player.id, { position: 'GK', confidence: clamp(0.5 + player.rearShare * 0.35 + player.aheadGap) });
    }
  }
  const field = eligible.filter(p => !result.has(p.id));
  if (!field.length) return result;
  const front = field.at(-1).depth;
  const back = field[0].depth;
  const leader = field.at(-1);
  for (const player of field) {
    // Similar-depth forwards on opposite flanks are both strikers, not an
    // automatically imposed AM/ST pair. Lateral movement never changes ST to LW/RW.
    const oppositeForward = player.lateral * leader.lateral < 0
      && Math.min(Math.abs(player.lateral), Math.abs(leader.lateral)) > 0.065
      && front - player.depth < 0.13;
    const forward = front - player.depth <= 0.065 || oppositeForward;
    const defensive = !forward && player.depth - back <= 0.06;
    const position = forward ? 'ST' : defensive ? 'DM' : 'AM';
    const margin = forward ? Math.max(0, 0.13 - (front - player.depth)) : front - player.depth;
    result.set(player.id, { position, confidence: clamp(0.55 + margin * 1.5) });
  }
  return result;
}

/** Bounded per-window moments: no per-tick movement history is retained. */
export function createPositionTracker(stadium) {
  const geometry = positionGeometry(stadium);
  const totals = new Map();
  let window = new Map(), activeTicks = 0, windowTicks = 0, windowStart = null, windowEnd = null;
  function flush() {
    if (!window.size) return;
    for (const side of ['red', 'blue']) {
      const moments = [...window.values()].filter(p => p.team === side).map(p => ({
        ...p, depth: p.depth / (p.samples || 1), lateral: p.lateral / (p.samples || 1),
        rearShare: p.rear / (p.samples || 1), aheadGap: p.aheadGap / (p.samples || 1),
      }));
      const assignments = classifyPositionWindow(moments);
      for (const player of moments) {
        const assignment = assignments.get(player.id);
        const total = totals.get(player.id) || { ticks: 0, roles: new Map(), periods: [] };
        total.ticks += player.ticks;
        if (assignment) {
          const role = total.roles.get(assignment.position) || { ticks: 0, confidence: 0 };
          role.ticks += player.ticks;
          role.confidence += assignment.confidence * player.ticks;
          total.roles.set(assignment.position, role);
        }
        total.periods.push({ startTick: windowStart, endTick: windowEnd + 1,
          observedTicks: player.ticks, position: assignment?.position || null,
          confidence: assignment ? round(assignment.confidence) : 0 });
        totals.set(player.id, total);
      }
    }
    window = new Map(); windowTicks = 0; windowStart = null;
  }
  return {
    observe(players, tick) {
      if (!geometry) return;
      activeTicks++;
      windowTicks++;
      windowStart ??= tick;
      windowEnd = tick;
      const sample = activeTicks % SAMPLE_TICKS === 1;
      for (const player of players) {
        const moment = window.get(player.id) || { id: player.id, team: player.team, ticks: 0, samples: 0, depth: 0, lateral: 0, rear: 0, aheadGap: 0 };
        moment.ticks++;
        if (sample) {
          const own = geometry[player.team], other = geometry[player.team === 'red' ? 'blue' : 'red'];
          const dx = other.x - own.x, dy = other.y - own.y, length2 = geometry.length ** 2;
          const depth = ((player.x - own.x) * dx + (player.y - own.y) * dy) / length2;
          const lateral = ((player.y - own.y) * dx - (player.x - own.x) * dy) / length2;
          const teammates = players.filter(p => p.team === player.team && p.id !== player.id);
          const gaps = teammates.map(p => ((p.x - own.x) * dx + (p.y - own.y) * dy) / length2 - depth);
          const rear = gaps.length > 0 && gaps.every(gap => gap >= -0.015);
          moment.samples++; moment.depth += depth; moment.lateral += lateral; moment.rear += Number(rear);
          moment.aheadGap += gaps.length ? Math.max(0, Math.min(...gaps)) : 0;
        }
        window.set(player.id, moment);
      }
      if (windowTicks === POSITION_WINDOW_TICKS) flush();
    },
    finish() {
      flush();
      return new Map([...totals].map(([id, total]) => {
        const roles = [...total.roles].sort((a, b) => b[1].ticks - a[1].ticks);
        const dominant = roles[0];
        // Confidence is evidence consistency, not a calibrated probability.
        const share = dominant ? dominant[1].ticks / total.ticks : 0;
        const position = total.ticks >= MIN_TICKS && share >= 0.55 ? dominant[0] : null;
        return [id, { position,
          positionConfidence: position ? round(share * dominant[1].confidence / dominant[1].ticks) : 0,
          positionRoles: roles.map(([position, role]) => ({ position, ticks: role.ticks, share: round(role.ticks / total.ticks) })),
          positionPeriods: total.periods,
        }];
      }));
    },
  };
}
