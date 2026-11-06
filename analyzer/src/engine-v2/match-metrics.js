// Football-facing classifications, separate from raw collision/transfer telemetry.
export const MATCH_COUNTERS = ['completedPasses', 'passesReceived', 'progressivePasses', 'recoveries', 'possessionLosses', 'shotsOnTarget', 'keyPasses'];
export const MATCH_OPTIONS = Object.freeze({ controlTicks: 6, controlRelativeSpeed: 2, controlReach: 4 });
const identity = player => `${player.playerId}:${player.team}`;
const point = value => ({ x: value.x, y: value.y });
const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
const cross = (a, b) => a.x * b.y - a.y * b.x;
function ballPhysics(frame) { return frame.discs?.find(disc => disc.id === 0) || frame.stadium?.ballPhysics; }
export function canProjectShots(frame) {
  const physics = ballPhysics(frame), goals = frame.stadium?.goals || [];
  if (!physics || !(physics.damping > 0 && physics.damping <= 1)) return false;
  if (!['red', 'blue'].every(team => goals.some(goal => goal.team === team
    && Math.hypot(goal.p1[0] - goal.p0[0], goal.p1[1] - goal.p0[1]) > 2 * (frame.ball?.radius ?? physics.radius ?? 0)))) return false;
  const gravity = physics.gravity;
  return !gravity || !(gravity.x || gravity.y || gravity[0] || gravity[1]);
}

/** Direct, unobstructed goal-bound kick. This is not an all-attempts classifier. */
export function projectShot(event, frame) {
  if (!canProjectShots(frame)) return null;
  const goal = frame.stadium?.goals.find(goal => goal.team !== event.team);
  const physics = ballPhysics(frame);
  if (!event.velocityAfter) return null;
  const damping = physics.damping;
  const start = event.position, velocity = event.velocityAfter;
  const edge = { x: goal.p1[0] - goal.p0[0], y: goal.p1[1] - goal.p0[1] };
  const denominator = cross(velocity, edge);
  if (Math.abs(denominator) < 1e-9) return null;
  const delta = { x: goal.p0[0] - start.x, y: goal.p0[1] - start.y };
  const travel = cross(delta, edge) / denominator, fraction = cross(delta, velocity) / denominator;
  // Stay inside the posts, allowing for the ball's radius.
  const margin = (frame.ball?.radius ?? physics.radius ?? 0) / Math.hypot(edge.x, edge.y);
  if (travel <= 0 || fraction <= margin || fraction >= 1 - margin) return null;
  const own = frame.stadium.goals.find(goal => goal.team === event.team);
  if (!own) return null;
  const axis = { x: (goal.p0[0] + goal.p1[0] - own.p0[0] - own.p1[0]) / 2,
    y: (goal.p0[1] + goal.p1[1] - own.p0[1] - own.p1[1]) / 2 };
  if (velocity.x * axis.x + velocity.y * axis.y <= 0) return null;
  // The native step moves first, then damps velocity. Infinite geometric reach.
  if (damping < 1 && travel >= 1 / (1 - damping)) return null;
  return { x: start.x + velocity.x * travel, y: start.y + velocity.y * travel };
}

export function createMatchMetrics(game, { options, playerFor, count, record }) {
  let controller = null, release = null, lastPass = null, priorPhase;
  const pending = new Map();
  game.possessionTicks = { red: 0, blue: 0, unassigned: 0 };
  game.shotsAvailable = true;
  game.passNetwork = new Map();
  function reset() { controller = release = lastPass = null; pending.clear(); }
  function derived(type, actor, extra = {}) {
    const event = { type, gameId: game.id, tick: actor.tick, gameTick: actor.gameTick,
      phase: 'active', playerId: actor.playerId, nick: actor.nick, team: actor.team, ...extra };
    record(game, event); return event;
  }
  function control(actor, sourceEventId) {
    const player = playerFor(game, actor), previous = controller;
    if (!player) return;
    const changed = !previous || identity(previous) !== identity(actor);
    if (changed) {
      derived('control', actor, { position: actor.position, sourceEventId, method: actor.method });
      if (previous && previous.team !== actor.team) {
        const recovery = derived('recovery', actor, { from: previous.position, to: actor.position, previousPlayerId: previous.playerId });
        count(game, player, 'recoveries', recovery);
        // Ending a shot is not treated as a failed pass or dispossession.
        if (!previous.shot) {
          const loss = derived('possession_loss', previous, { tick: actor.tick, gameTick: actor.gameTick,
            from: previous.position, to: actor.position, winnerId: actor.playerId, winnerTeam: actor.team });
          count(game, playerFor(game, previous), 'possessionLosses', loss);
        }
        lastPass = null;
      }
      if (release && identity(release) !== identity(actor) && release.team === actor.team
        && actor.tick - release.tick <= options.transferWindowTicks) {
        const progress = game.geometry ? distance(release.position, actor.team === 'red' ? game.geometry.b : game.geometry.a)
          - distance(actor.position, actor.team === 'red' ? game.geometry.b : game.geometry.a) : 0;
        const progressive = Boolean(game.geometry && progress >= game.geometry.length * options.progressiveFraction);
        const pass = derived('completed_pass', release, { tick: actor.tick, gameTick: actor.gameTick,
          receiverId: actor.playerId, receiverTeam: actor.team, releaseTick: release.tick,
          releaseEventId: release.id, receptionEventId: sourceEventId, from: release.position, to: actor.position,
          distance: distance(release.position, actor.position), progress, progressive,
          definition: 'kick-to-confirmed-teammate-control' });
        const sender = playerFor(game, release);
        count(game, sender, 'completedPasses', pass); count(game, player, 'passesReceived', pass);
        if (progressive) count(game, sender, 'progressivePasses', pass);
        const pair = `${sender.id}>${player.id}`;
        const edge = game.passNetwork.get(pair) || { from: sender.id, to: player.id, count: 0, distance: 0 };
        edge.count++; edge.distance += pass.distance; game.passNetwork.set(pair, edge);
        lastPass = pass;
      } else if (lastPass && lastPass.receiverId !== actor.playerId) lastPass = null;
      release = null;
    } else if (actor.method === 'settled-contact') release = null; // Self-recovery.
    controller = { ...actor, shot: changed || actor.method === 'settled-contact' ? false : previous.shot };
  }
  return {
    consume({ tick, before, after, events }, active) {
      if (priorPhase !== before.phase && !(priorPhase === 'kickoff' && before.phase === 'active')) reset();
      priorPhase = before.phase;
      if (!active) { reset(); return; }
      // Retain partial classifications in the export, but do not present an incomplete
      // shooting total as a full-game zero/count in the UI.
      if (!canProjectShots(before)) game.shotsAvailable = false;
      if (release && tick - release.tick > options.transferWindowTicks) release = null;
      const interactions = events.filter(event => ['kick', 'contact'].includes(event.type)
        && event.gameId === game.id && (event.phase === 'active' || event.phase === 'kickoff'));
      const ambiguous = new Set(interactions.map(identity)).size > 1;
      if (ambiguous) { release = lastPass = null; pending.clear(); }
      let endsPlay = false;
      for (const event of events) {
        if (event.gameId !== game.id) continue;
        if (['game_start', 'team_change', 'player_leave'].includes(event.type)) reset();
        if (['goal', 'restart', 'game_end', 'game_stop'].includes(event.type)) endsPlay = true;
        if (!interactions.includes(event)) continue;
        if (event.type === 'contact') {
          pending.set(identity(event), { ...event, stable: 0 });
          // A defender's deflection breaks the direct passing chain even without control.
          if (release && release.team !== event.team) release = null;
          if (lastPass && lastPass.team !== event.team) lastPass = null;
          continue;
        }
        if (ambiguous) continue;
        pending.clear();
        control({ ...event, method: 'kick' }, event.id);
        const target = projectShot(event, before);
        if (target) {
          const shot = derived('shot_on_target', event, { from: event.position, to: target, sourceEventId: event.id,
            definition: 'direct-unobstructed-goal-bound-kick' });
          count(game, playerFor(game, event), 'shotsOnTarget', shot);
          if (lastPass && lastPass.receiverId === event.playerId && lastPass.team === event.team
            && tick - lastPass.tick <= options.assistWindowTicks) {
            const keyPass = derived('key_pass', lastPass, { tick, gameTick: event.gameTick,
              from: lastPass.from, via: event.position, to: target, passEventId: lastPass.id, shotEventId: shot.id });
            count(game, playerFor(game, lastPass), 'keyPasses', keyPass);
          }
          lastPass = release = null; controller.shot = true;
        } else { release = event; controller.shot = false; }
      }
      if (pending.size && !endsPlay && after.gameId === game.id) {
        const settled = [];
        for (const [id, candidate] of pending) {
          const actor = after.players.find(player => identity(player) === id && player.bodyId);
          const ball = after.ball;
          const close = actor && ball && distance(actor, ball) <= actor.radius + ball.radius + options.controlReach;
          const slow = close && distance(actor.velocity, ball.velocity) <= options.controlRelativeSpeed;
          const contested = close && after.players.some(other => other.bodyId && other.team !== actor.team
            && ['red', 'blue'].includes(other.team) && distance(other, ball) <= other.radius + ball.radius + options.controlReach);
          candidate.stable = slow && !contested ? candidate.stable + 1 : 0;
          if (candidate.stable >= options.controlTicks) settled.push(candidate);
          else if (!close) pending.delete(id);
        }
        if (settled.length === 1) {
          const candidate = settled[0];
          control({ ...candidate, tick, gameTick: after.gameTick, position: point(after.ball), method: 'settled-contact' }, candidate.id);
          pending.clear();
        }
      }
      const team = controller?.team ?? 'unassigned';
      game.possessionTicks[team]++;
      if (controller) game.teams[team].possessionTicks++;
      if (endsPlay) reset();
    },
  };
}
