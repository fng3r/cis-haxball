export const DEFAULT_OPTIONS = Object.freeze({ heatmapCellSize: 10, transferWindowTicks: 300, assistWindowTicks: 480, progressiveFraction: 0.1 });
const point = value => ({ x: value.x, y: value.y });
const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
const key = player => `${player.playerId}:${player.team}`;
const playing = player => player.team === 'red' || player.team === 'blue';
const counters = () => ({ kicks: 0, contacts: 0, transfers: 0, received: 0, progressiveTransfers: 0, turnovers: 0, goals: 0, ownGoals: 0, assists: 0 });
function geometry(stadium) {
  const red = stadium.goals.find(goal => goal.team === 'red');
  const blue = stadium.goals.find(goal => goal.team === 'blue');
  if (!red || !blue) return null;
  const center = goal => ({ x: (goal.p0[0] + goal.p1[0]) / 2, y: (goal.p0[1] + goal.p1[1]) / 2 });
  const a = center(red), b = center(blue), length = distance(a, b);
  return length > 0 ? { a, b, length, axis: { x: (b.x - a.x) / length, y: (b.y - a.y) / length } } : null;
}
export function createCollector({ includeEvents = true, onEvent = () => {}, ...settings } = {}) {
  const options = { ...DEFAULT_OPTIONS, ...settings }, games = new Map();
  for (const field of Object.keys(settings)) if (!(field in DEFAULT_OPTIONS)) throw new Error(`Unknown metric setting: ${field}.`);
  for (const field of ['heatmapCellSize', 'transferWindowTicks', 'assistWindowTicks', 'progressiveFraction']) {
    if (!(Number.isFinite(options[field]) && options[field] > 0)) throw new Error(`Invalid ${field}.`);
  }
  function gameFor(frame, tick) {
    if (frame.gameId == null) return null;
    if (!games.has(frame.gameId)) games.set(frame.gameId, {
      id: frame.gameId, startTick: tick, endTick: tick, stadium: frame.stadium,
      scoreRed: frame.score[0], scoreBlue: frame.score[1], initialScore: [...frame.score],
      activeTicks: 0, phaseTicks: {}, thirds: [0, 0, 0], territoryAvailable: Boolean(geometry(frame.stadium)),
      proximityTicks: { red: 0, blue: 0, contested: 0, loose: 0 },
      teams: { red: { ...counters(), observedGoalsFor: 0, observedGoalsAgainst: 0, leadingTicks: 0, drawingTicks: 0, trailingTicks: 0, widthSum: 0, depthSum: 0, shapeTicks: 0 }, blue: { ...counters(), observedGoalsFor: 0, observedGoalsAgainst: 0, leadingTicks: 0, drawingTicks: 0, trailingTicks: 0, widthSum: 0, depthSum: 0, shapeTicks: 0 } },
      players: new Map(), events: [], goals: [], network: new Map(), release: null, interactions: [],
      geometry: geometry(frame.stadium), observedStart: false, observedEnd: false,
    });
    return games.get(frame.gameId);
  }
  function playerFor(game, player) {
    if (!player || !playing(player)) return null;
    const id = key(player);
    if (!game.players.has(id)) game.players.set(id, {
      id, playerId: player.playerId, nick: player.nick, names: new Set(), team: player.team,
      ...counters(), onFieldTicks: 0, activeTicks: 0, distance: 0, speedSum: 0, peakSpeed: 0,
      xSum: 0, ySum: 0, cells: new Map(), maps: { kicks: [], contacts: [], transfers: [], received: [], turnovers: [], goals: [], assists: [] },
    });
    const item = game.players.get(id); item.names.add(player.nick); item.nick = player.nick;
    return item;
  }
  function record(game, event) {
    event.id ??= ++eventId;
    if (includeEvents) game.events.push(event);
    onEvent(event);
  }
  function count(game, player, metric, location) {
    player[metric]++; game.teams[player.team][metric]++;
    if (location && player.maps[metric]) player.maps[metric].push(location);
  }
  function interact(game, event, ambiguous) {
    const player = playerFor(game, event);
    if (!player) return;
    count(game, player, event.type === 'kick' ? 'kicks' : 'contacts', { ...event.position, tick: event.tick });
    const release = game.release;
    if (ambiguous) game.release = null;
    else if (release && event.tick - release.tick <= options.transferWindowTicks && key(event) !== key(release)) {
      const sender = playerFor(game, release), sameTeam = release.team === event.team;
      const progress = game.geometry ? (distance(release.position, release.team === 'red' ? game.geometry.b : game.geometry.a)
        - distance(event.position, release.team === 'red' ? game.geometry.b : game.geometry.a)) : 0;
      const transfer = { type: sameTeam ? 'transfer' : 'turnover', gameId: game.id, tick: event.tick, gameTick: event.gameTick,
        phase: event.phase, playerId: release.playerId, nick: release.nick, team: release.team,
        receiverId: event.playerId, receiverTeam: event.team, releaseTick: release.tick, releaseEventId: release.id,
        receptionEventId: event.id, from: release.position, to: event.position,
        distance: distance(release.position, event.position), progress, definition: 'next-distinct-ball-interaction' };
      count(game, sender, sameTeam ? 'transfers' : 'turnovers', transfer);
      if (sameTeam) {
        count(game, player, 'received', transfer);
        if (game.geometry && progress >= game.geometry.length * options.progressiveFraction) count(game, sender, 'progressiveTransfers');
        const pair = `${sender.id}>${player.id}`;
        const edge = game.network.get(pair) || { from: sender.id, to: player.id, count: 0, distance: 0 };
        edge.count++; edge.distance += transfer.distance; game.network.set(pair, edge);
      }
      record(game, transfer); game.release = null;
    } else if (release && event.type === 'contact' && event.tick > release.tick + 1) game.release = null;
    if (event.type === 'kick' && !ambiguous) game.release = event;
    const last = game.interactions.at(-1);
    if (!last || key(last) !== key(event)) game.interactions.push(event);
    else game.interactions[game.interactions.length - 1] = event;
    if (game.interactions.length > 2) game.interactions.shift();
  }
  function goal(game, event, participants) {
    const last = game.interactions.at(-1), previous = game.interactions.at(-2);
    // This is a documented attribution rule, not ground truth about intent.
    const scorer = last && event.tick - last.tick <= options.assistWindowTicks ? last : null;
    const ownGoal = Boolean(scorer && scorer.team !== event.team);
    const assist = scorer && !ownGoal && previous?.team === scorer.team && event.tick - previous.tick <= options.assistWindowTicks ? previous : null;
    const result = { ...event, scorerId: scorer?.playerId ?? null, scorer: scorer?.nick ?? null,
      assistId: assist?.playerId ?? null, assist: assist?.nick ?? null, ownGoal,
      attribution: 'last-distinct-interactions-within-window' };
    game.goals.push(result);
    game.teams[event.team].observedGoalsFor++;
    game.teams[event.team === 'red' ? 'blue' : 'red'].observedGoalsAgainst++;
    if (scorer) count(game, playerFor(game, scorer), ownGoal ? 'ownGoals' : 'goals', { from: scorer.position, to: event.position, tick: event.tick });
    if (assist) count(game, playerFor(game, assist), 'assists', { from: assist.position, via: scorer.position, to: event.position, tick: event.tick });
    for (const member of participants.filter(playing)) {
      const player = playerFor(game, member);
      player.onFieldGoalsFor = (player.onFieldGoalsFor || 0) + Number(member.team === event.team);
      player.onFieldGoalsAgainst = (player.onFieldGoalsAgainst || 0) + Number(member.team !== event.team);
    }
    game.release = null; game.interactions = [];
    return result;
  }
  let eventId = 0, previousPhase = new Map();
  return {
    initial(frame) { const game = gameFor(frame, 0); if (game) game.truncatedStart = true; },
    consume({ tick, before, after, events }) {
      const game = gameFor(before, tick) || gameFor(after, tick) || games.get(events.find(event => event.gameId != null)?.gameId);
      if (!game) return;
      game.endTick = before.gameId === game.id ? tick + 1 : tick;
      const scoreFrame = after.gameId === game.id ? after : before;
      [game.scoreRed, game.scoreBlue] = scoreFrame.score;
      const priorPhase = previousPhase.get(game.id);
      if (priorPhase !== before.phase) {
        record(game, { id: ++eventId, type: 'phase', gameId: game.id, tick, gameTick: before.gameTick, phase: before.phase, previousPhase: priorPhase ?? null });
        // Phases interrupt candidate transfers, contact attribution and movement.
        if (priorPhase !== undefined) { game.release = null; game.interactions = []; }
        previousPhase.set(game.id, before.phase);
      }
      const ambiguous = new Set(events.filter(e => e.type === 'contact').map(key)).size > 1;
      for (const raw of events) {
        if (raw.gameId !== game.id) {
          const previous = games.get(raw.gameId);
          if (previous && ['game_stop', 'game_end'].includes(raw.type)) { previous.observedEnd = true; previous.endTick = tick; record(previous, { ...raw, id: ++eventId }); }
          continue;
        }
        let event = { ...raw, id: ++eventId };
        if (['game_start', 'restart', 'game_end', 'team_change', 'player_leave'].includes(event.type)) { game.release = null; game.interactions = []; }
        if (event.type === 'game_start') { game.observedStart = true; game.truncatedStart = false; }
        if (event.type === 'game_end' || event.type === 'game_stop') game.observedEnd = true;
        if (event.type === 'kick' || event.type === 'contact') {
          record(game, event);
          if (event.phase === 'active' || event.phase === 'kickoff') interact(game, event, ambiguous);
          continue;
        }
        if (event.type === 'goal') event = goal(game, event, before.players);
        record(game, event);
      }
      if (before.gameId !== game.id) return;
      game.phaseTicks[before.phase] = (game.phaseTicks[before.phase] || 0) + 1;
      const active = before.phase === 'active';
      if (active) {
        game.activeTicks++;
        if (game.geometry && before.ball) {
          const { a, axis, length } = game.geometry;
          const progress = ((before.ball.x - a.x) * axis.x + (before.ball.y - a.y) * axis.y) / length;
          game.thirds[progress < 1 / 3 ? 0 : progress < 2 / 3 ? 1 : 2]++;
        }
        const near = new Set(before.players.filter(p => p.bodyId && playing(p) && before.ball && distance(p, before.ball) <= p.radius + before.ball.radius + 4).map(p => p.team));
        game.proximityTicks[near.size > 1 ? 'contested' : near.size ? [...near][0] : 'loose']++;
      }
      for (const member of before.players.filter(p => p.bodyId && playing(p))) {
        const player = playerFor(game, member); player.onFieldTicks++;
        if (!active) continue;
        player.activeTicks++;
        const end = after.players.find(p => p.bodyId === member.bodyId);
        if (end && after.gameId === before.gameId && after.phase !== 'kickoff') player.distance += distance(member, end);
        const speed = Math.hypot(member.velocity.x, member.velocity.y) * 60;
        player.speedSum += speed; player.peakSpeed = Math.max(player.peakSpeed, speed);
        player.xSum += member.x; player.ySum += member.y;
        const size = options.heatmapCellSize, x = Math.round(member.x / size) * size || 0, y = Math.round(member.y / size) * size || 0;
        const id = `${x},${y}`, cell = player.cells.get(id) || { x, y, ticks: 0 };
        cell.ticks++; player.cells.set(id, cell);
      }
      if (active) for (const team of ['red', 'blue']) {
        const metrics = game.teams[team], difference = before.score[0] - before.score[1];
        metrics[difference === 0 ? 'drawingTicks' : (team === 'red' ? difference > 0 : difference < 0) ? 'leadingTicks' : 'trailingTicks']++;
        const players = before.players.filter(p => p.bodyId && p.team === team);
        if (players.length && game.geometry) {
          const { axis } = game.geometry;
          const depth = players.map(p => p.x * axis.x + p.y * axis.y), width = players.map(p => -p.x * axis.y + p.y * axis.x);
          metrics.depthSum += Math.max(...depth) - Math.min(...depth); metrics.widthSum += Math.max(...width) - Math.min(...width); metrics.shapeTicks++;
        }
      }
    },
    finish() {
      return [...games.values()].filter(game => game.activeTicks || game.goals.length).map(game => {
        const players = [...game.players.values()].map(({ cells, speedSum, xSum, ySum, ...player }) => ({
          ...player, names: [...player.names], playedTicks: player.activeTicks,
          averageSpeed: player.activeTicks ? speedSum / player.activeTicks : 0,
          averagePosition: player.activeTicks ? { x: xSum / player.activeTicks, y: ySum / player.activeTicks } : null,
          kicksPerMinute: player.activeTicks ? player.kicks * 3600 / player.activeTicks : null,
          onFieldGoalDifference: (player.onFieldGoalsFor || 0) - (player.onFieldGoalsAgainst || 0),
          maps: { ...player.maps, heatmap: [...cells.values()] },
        }));
        const teams = Object.fromEntries(Object.entries(game.teams).map(([team, { widthSum, depthSum, shapeTicks, ...stats }]) => [team, {
          ...stats, shapeTicks, averageWidth: shapeTicks ? widthSum / shapeTicks : null, averageDepth: shapeTicks ? depthSum / shapeTicks : null,
          distance: players.filter(p => p.team === team).reduce((sum, p) => sum + p.distance, 0),
        }]));
        return { id: game.id, startTick: game.startTick, endTick: game.endTick, stadium: game.stadium,
          initialScore: game.initialScore, scoreRed: game.scoreRed, scoreBlue: game.scoreBlue,
          activeTicks: game.activeTicks, phaseTicks: game.phaseTicks, thirds: game.thirds, territoryAvailable: game.territoryAvailable,
          proximityTicks: game.proximityTicks, truncatedStart: Boolean(game.truncatedStart), truncatedEnd: !game.observedEnd,
          teams, players, goals: game.goals, transferNetwork: [...game.network.values()], ...(includeEvents ? { events: game.events } : {}) };
      });
    },
  };
}
