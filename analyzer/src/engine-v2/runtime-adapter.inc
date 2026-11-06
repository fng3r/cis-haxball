let replay, tick = 0, serial = -1, events = [], stadiumCache = new WeakMap();
let lastContacts = new Map(), bodies = new WeakMap(), bodySerial = 0;
const xy = value => ({ x: value.x, y: value.y });
const teamName = value => value === 1 ? 'red' : value === 2 ? 'blue' : 'spectators';
function identity(player) { return { playerId: player.V, nick: player.w, team: teamName(player.ea.$) }; }
function phase(game) { return !game ? 'lobby' : game.Oa > 0 ? 'paused' : ['kickoff', 'active', 'goal', 'ended'][game.Bb] || 'unknown'; }
function emit(type, data = {}) {
  const game = replay?.T.K;
  const event = { type, tick, gameId: game ? serial : null, gameTick: Math.round((game?.Hc || 0) * 60), phase: phase(game), ...data };
  events.push(event); return event;
}
function context() {
  return replay.T.I.filter(player => player.H).map(player => ({ ...identity(player), ...xy(player.H.a), velocity: xy(player.H.D), radius: player.H.Z }));
}
function captureKick(player, disc, before) {
  if (disc !== replay?.T.K?.ta.F[0]) return;
  emit('kick', { ...identity(player), position: xy(disc.a), velocityBefore: before, velocityAfter: xy(disc.D), players: context() });
}
function captureContact(a, b) {
  const game = replay?.T.K;
  if (!game) return;
  const ball = game.ta.F[0], other = a === ball ? b : b === ball ? a : null;
  if (!other) return;
  const player = replay.T.I.find(item => item.H === other);
  if (!player) return;
  const key = `${serial}:${player.V}:${bodyId(other)}`;
  const last = lastContacts.get(key);
  lastContacts.set(key, tick);
  if (last != null && tick - last <= 1) return;
  emit('contact', { ...identity(player), position: xy(ball.a), velocityBefore: xy(ball.D) });
}
function bodyId(body) {
  if (!bodies.has(body)) bodies.set(body, ++bodySerial);
  return bodies.get(body);
}
function roster() { return replay.T.I.map(player => ({ ...identity(player), input: player.ob })); }
function changes(before, after, actorId) {
  const old = new Map(before.map(player => [player.playerId, player]));
  for (const player of after) {
    const previous = old.get(player.playerId);
    if (!previous) emit('player_join', { ...player, actorId });
    else {
      if (previous.team !== player.team) emit('team_change', { ...player, previousTeam: previous.team, actorId });
      if (previous.nick !== player.nick) emit('rename', { ...player, previousNick: previous.nick, actorId });
      if (previous.input !== player.input) emit('input', { ...player, previousInput: previous.input, actorId });
    }
    old.delete(player.playerId);
  }
  for (const player of old.values()) emit('player_leave', { ...player, actorId });
}
function snapshot() {
  const state = replay.T, game = state.K;
  let stadium = null;
  if (game) {
    if (!stadiumCache.has(game.S)) stadiumCache.set(game.S, readStadium(game.S));
    stadium = stadiumCache.get(game.S);
  }
  return {
    tick, gameId: game ? serial : null, phase: phase(game),
    gameTick: Math.round((game?.Hc || 0) * 60), score: game ? [game.Pb, game.Kb] : [0, 0], stadium,
    discs: game ? game.ta.F.map((disc, id) => ({ id, ...xy(disc.a), velocity: xy(disc.D), gravity: xy(disc.oa), radius: disc.Z, damping: disc.Ca, invMass: disc.aa, bCoef: disc.m, cMask: disc.h, cGroup: disc.v })) : [],
    ball: game?.ta.F[0] ? { ...xy(game.ta.F[0].a), velocity: xy(game.ta.F[0].D), radius: game.ta.F[0].Z } : null,
    players: state.I.map(player => ({ ...identity(player), input: player.ob,
      bodyId: player.H ? bodyId(player.H) : null,
      ...(player.H ? { ...xy(player.H.a), velocity: xy(player.H.D), radius: player.H.Z } : {}) })),
  };
}
Jb.prototype.Dl = function () {
  if (this.Lc.a < this.Lc.o.byteLength) {
    this.hg += this.Lc.Ab(); const actor = this.Lc.Ob();
    this.gg = m.fh(this.Lc); this.gg.P = actor;
  } else this.gg = null;
};
return {
  load(bytes) {
    kc.fj(); keepUpdating = false;
    replay = new Jb(bytes, new fa, 3);
    serial = replay.T.K ? 0 : -1;
    replay.T.Ki = () => { serial++; lastContacts.clear(); emit('game_start'); };
    replay.T.Ni = scoringTeam => emit('goal', { team: teamName(scoringTeam.$), score: [replay.T.K.Pb, replay.T.K.Kb], position: xy(replay.T.K.ta.F[0].a), players: context() });
    replay.T.lq = () => { lastContacts.clear(); emit('restart'); };
    replay.T.Oi = winner => emit('game_end', { reason: 'finished', winner: teamName(winner.$) });
    replay.T.vf = () => emit('game_stop', { gameId: serial });
    return { ticks: replay.mf, initial: snapshot() };
  },
  step() {
    tick = replay.Y; events = [];
    while (replay.gg != null && replay.hg === replay.Y) {
      const previous = roster(), action = replay.gg;
      action.apply(replay.T); changes(previous, roster(), action.P); replay.Dl();
    }
    const before = snapshot();
    replay.Y++; replay.T.C(1);
    const after = snapshot();
    for (const event of events) if (event.type === 'contact' && after.ball) event.velocityAfterStep = { ...after.ball.velocity };
    return { tick, before, after, events };
  },
};
