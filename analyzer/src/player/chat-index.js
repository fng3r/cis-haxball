// Capture chat during the shared player's preprocessing pass, independent of stats.
export function captureChat(state, currentTick) {
  const entries = [];
  const add = (type, text, extra = {}) => entries.push({ tick: currentTick(), type, text, ...extra });
  const by = actor => actor ? ` by ${actor.w}` : '';
  const notice = text => add('notice', text);
  state.rl = (player, text) => add('chat', `${player.w}: ${text}`, { playerId: player.V });
  state.Vl = (text, color, style) => add('announcement', text, { color, style });
  state.tl = player => notice(`${player.w} has joined`);
  state.ul = (player, reason, banned, actor) => notice(reason == null ? `${player.w} has left`
    : `${player.w} was ${banned ? 'banned' : 'kicked'}${by(actor)}${reason ? ` (${reason})` : ''}`);
  state.ii = (actor, player) => notice(`${player.w}${player.cb ? ' was given admin rights' : "'s admin rights were taken away"}${by(actor)}`);
  state.xl = (actor, player, team) => { if (state.K) notice(`${player.w} was moved to ${team.w}${by(actor)}`); };
  state.Ki = actor => notice(`Game started${by(actor)}`);
  state.Oi = team => notice(`${team.w} team won the match`);
  state.ml = (actor, paused, alreadyPaused) => { if (paused && !alreadyPaused) notice(`Game paused${by(actor)}`); };
  state.Ii = (actor, stadium) => { if (!stadium.Pe()) notice(`Stadium "${stadium.w}" loaded${by(actor)}`); };
  state.vf = actor => { if (actor) notice(`Game stopped${by(actor)}`); };
  state.sl = player => notice(`${player.w} ${player.Ld ? 'has desynchronized' : 'is back in sync'}`);
  state.Hk = (actor, min, rate, burst) => notice(`Kick Rate Limit set to (min: ${min}, rate: ${rate}, burst: ${burst})${by(actor)}`);
  return entries;
}
