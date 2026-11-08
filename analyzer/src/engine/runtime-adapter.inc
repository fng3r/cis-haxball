// This code runs inside a fresh legacy-runtime closure for each recording.
// Explicit replay callbacks replace Gb, the old DOM/audio-driven controller.
let recordingTick = 0;
let replay;

Jb.prototype.Dl = function () {
  if (this.Lc.a < this.Lc.o.byteLength) {
    this.hg += this.Lc.Ab();
    const actor = this.Lc.Ob();
    this.gg = m.fh(this.Lc);
    this.gg.P = actor;
  } else this.gg = null;
};

function freshMatch() {
  return {
    stadium: false, started: true, stopped: false, spaceMode: false,
    realSoccerMode: false, touches: [], thirds: [0, 0, 0], changes: [],
    gameTicks: -1, kicks: [], shots: [], redTeam: [], blueTeam: [],
    shotsRed: 0, shotsBlue: 0, passes: [], passesRed: 0, passesBlue: 0,
    kicksRed: 0, kicksBlue: 0, possRed: 0, possBlue: 0,
    scoreRed: 0, scoreBlue: 0, player: [], goals: [],
  };
}

function attachCallbacks(state) {
  state.tl = function (item) {
    players.push(item);
    if (!playerList.includes(item.w)) {
      playerList.push(item.w);
      match.at(-1).player.push({ id: item.V, nick: item.w, nation: item.Kd });
    }
    checkTeams = true;
  };
  state.xl = function () { checkTeams = true; };
  state.Ni = function (team) {
    const current = match.at(-1);
    if (team.w === 'Red') current.scoreRed++;
    else current.scoreBlue++;
    const scorer = current.spaceMode ? toucher : kicker;
    const previous = current.spaceMode ? lastToucher : lastKicker;
    const ownGoal = Boolean(scorer && scorer.team !== team.w);
    const shot = current.spaceMode ? scorer?.position : current.kicks.findLast(kick => kick.player === scorer?.name);
    const assistShot = current.spaceMode ? previous?.position : current.kicks.findLast(kick => kick.player === previous?.name);
    const ball = state.K?.ta.F[0]?.a;
    current.goals.push({
      scorer: scorer?.name || null,
      assist: !ownGoal && previous?.team === team.w ? previous.name : null,
      ownGoal, team: team.w.toLowerCase(), tick: recordingTick,
      gameTick: Math.max(0, current.gameTicks),
      scoreRed: current.scoreRed, scoreBlue: current.scoreBlue,
      playerId: scorer?.id, assistId: previous?.id,
      shot: shot ? { x: shot.x, y: shot.y } : null,
      assistShot: assistShot ? { x: assistShot.x, y: assistShot.y } : null,
      ballCoord: ball ? { x: ball.x, y: ball.y } : null,
    });
  };
  state.Oi = state.Pi = function () { match.at(-1).stopped = true; };
  state.vf = function () {
    match.at(-1).stopped = true;
    checkTeams = true;
  };
  state.Ki = function () {
    if (match.at(-1).stopped) {
      if (match.at(-1).gameTicks < 0) match.pop();
      match.push(freshMatch());
      playerPos.push([]);
    }
    checkTeams = true;
    updatePlayers = true;
    kicker = lastKicker = undefined;
    toucher = { name: '', team: '0' };
    lastToucher = '';
    redGoalCord = [];
    blueGoalCord = [];
  };
}

return {
  load(bytes) {
    kc.fj();
    replay = new Jb(bytes, new fa, 3);
    // Replace the playback-progress heuristic with direct event decoding.
    // The first event has already been decoded by Jb.ui().
    attachCallbacks(replay.T);
    return replay.mf;
  },
  step() {
    recordingTick = replay.Y;
    while (replay.gg != null && replay.hg === replay.Y) {
      replay.gg.apply(replay.T);
      replay.Dl();
    }
    replay.Y++;
    replay.T.C(1);
  },
  get currentMatch() { return match.length - 1; },
  get matches() { return match; },
  get state() { return replay.T; },
  frame() {
    const state = replay.T;
    const game = state.K;
    if (!game) return null;
    return {
      tick: recordingTick,
      gameTick: Math.max(0, match.at(-1).gameTicks),
      score: [game.Pb, game.Kb],
      discs: game.ta.F.map(disc => [disc.a.x, disc.a.y, disc.Z, disc.R]),
      players: state.I.filter(item => item.H != null).map(item => ({
        id: item.V, nick: item.w, team: item.ea.$,
        x: item.H.a.x, y: item.H.a.y, radius: item.H.Z,
        avatar: item.Jd ?? item.Xb ?? null,
      })),
    };
  },
};
