import { Inflate } from 'pako';
import { createRuntime } from './vendor-runtime.js';
import { createPositionTracker, POSITION_VERSION } from './positions.js';

export const MAX_FILE_BYTES = 32 * 1024 * 1024;
const MAX_INFLATED_BYTES = 128 * 1024 * 1024;
const MAX_TICKS = 60 * 60 * 60;
export const SAMPLE_INTERVAL = 4;

function inflateRaw(bytes) {
  const decoder = new Inflate({ raw: true });
  const chunks = [];
  let length = 0;
  decoder.onData = chunk => {
    length += chunk.length;
    if (length > MAX_INFLATED_BYTES) throw new Error('The replay expands beyond the 128 MB limit.');
    chunks.push(chunk);
  };
  decoder.push(bytes, true);
  if (decoder.err || !decoder.ended) throw new Error('The replay contains invalid or incomplete compressed data.');
  const result = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) { result.set(chunk, offset); offset += chunk.length; }
  return result;
}

function playerMaps(game, player, cells) {
  const belongs = event => event.playerId != null
    ? `${event.playerId}:${event.team}` === player.id
    : event.player === player.nick && (!event.team || event.team === player.team);
  const goals = game.goals.filter(g => !g.ownGoal && g.scorer === player.nick && g.team === player.team);
  const assists = game.goals.filter(g => g.assist === player.nick && g.team === player.team);
  return {
    heatmap: [...(cells?.values() || [])],
    kicks: game.kicks.filter(belongs).map(k => ({ x: k.x, y: k.y })),
    passes: game.passes.filter(p => typeof p !== 'string' && belongs(p) && p.lastShot && p.shot).map(p => ({ from: p.lastShot, to: { x: p.shot.x, y: p.shot.y } })),
    shots: game.shots.filter(belongs).map(s => ({ from: s.from, to: s.to })),
    goals: goals.filter(g => g.shot && g.ballCoord).map(g => ({ from: g.shot, to: g.ballCoord })),
    assists: assists.filter(g => g.assistShot && g.shot && g.ballCoord).map(g => ({ from: g.assistShot, via: g.shot, to: g.ballCoord })),
  };
}

function normalizeGame(game, index, frames, roster, startTick, includeFrames, heatmaps, positions) {
  const players = [...roster.values()].map(player => ({
    ...player,
    ...(positions?.get(player.id) || {
      primaryPosition: null, secondaryPosition: null,
      primaryPositionConfidence: 0, secondaryPositionConfidence: 0,
      positionObservedTicks: 0,
      positionRoles: [], positionPeriods: [],
    }),
    goals: game.goals.filter(g => !g.ownGoal && g.scorer === player.nick && g.team === player.team).length,
    assists: game.goals.filter(g => g.assist === player.nick && g.team === player.team).length,
    kicks: game.kicks.filter(k => k.player === player.nick).length,
    passes: game.passes.filter(p => (typeof p === 'string' ? p : p.player) === player.nick).length,
    shots: game.shots.filter(s => s.player === player.nick).length,
    maps: playerMaps(game, player, heatmaps?.get(player.id)),
  }));
  return {
    id: index, stadium: game.stadium, gameTicks: Math.max(0, game.gameTicks),
    scoreRed: game.scoreRed, scoreBlue: game.scoreBlue,
    possession: [game.possRed, game.possBlue], thirds: game.thirds,
    kicks: [game.kicksRed, game.kicksBlue],
    passes: [game.passesRed, game.passesBlue], shots: [game.shotsRed, game.shotsBlue],
    spaceMode: game.spaceMode, goals: game.goals, players, startTick,
    ...(includeFrames ? { frames } : {}),
  };
}

/** Browser/Node entry point. Synchronous CPU work; run inside a worker in the UI. */
export function analyzeReplay(input, { onProgress = () => {}, includeFrames = false } = {}) {
  const bytes = input instanceof ArrayBuffer ? new Uint8Array(input) : input;
  if (!(bytes instanceof Uint8Array) || bytes.byteLength < 12) throw new Error('Choose a valid .hbr2 recording.');
  if (bytes.byteLength > MAX_FILE_BYTES) throw new Error('Choose a recording smaller than 32 MB.');
  const header = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (header.getUint32(0) !== 0x48425232) throw new Error('This file is not an HBR2 recording.');
  if (header.getUint32(4) !== 3) throw new Error(`Replay format ${header.getUint32(4)} is not supported. Expected version 3.`);
  const ticks = header.getUint32(8);
  if (!ticks || ticks > MAX_TICKS) throw new Error('Choose a non-empty recording up to one hour long.');
  const runtime = createRuntime(inflateRaw);
  const frameSets = [], rosters = [], starts = [], heatmaps = [], positionTrackers = [];
  try {
    runtime.load(Uint8Array.from(bytes));
    onProgress(0);
    for (let tick = 0; tick < ticks; tick++) {
      runtime.step();
      const index = runtime.currentMatch;
      if (runtime.state.K && starts[index] == null) starts[index] = tick;
      const roster = rosters[index] ||= new Map();
      const live = runtime.state.K?.Bb === 1 && !(runtime.state.K?.Oa > 0);
      const livePositions = [];
      // Track playtime at full tick resolution, independently of native playback.
      for (const item of runtime.state.I) {
        if (!item.H || !item.ea.$ || runtime.state.K?.Bb !== 1 || runtime.state.K?.Oa > 0) continue;
        const team = item.ea.$ === 1 ? 'red' : 'blue';
        const key = `${item.V}:${team}`;
        const player = roster.get(key) || { id: key, nick: item.w, team, playedTicks: 0 };
        player.playedTicks++;
        // Match native display precedence and retain the last value used in play,
        // including an explicitly cleared or blank avatar.
        player.avatar = item.Jd ?? item.Xb ?? null;
        roster.set(key, player);
        livePositions.push({ id: key, team, x: item.H.a.x, y: item.H.a.y });
        // Accumulate occupancy at every active tick; no playback sampling and
        // no unbounded per-tick position arrays are needed for a density map.
        const cells = heatmaps[index] ||= new Map();
        const positions = cells.get(key) || new Map();
        const x = Math.round(item.H.a.x / 10) * 10 || 0;
        const y = Math.round(item.H.a.y / 10) * 10 || 0;
        const positionKey = `${x},${y}`;
        const cell = positions.get(positionKey) || { x, y, ticks: 0 };
        cell.ticks++;
        positions.set(positionKey, cell);
        cells.set(key, positions);
      }
      if (live && runtime.matches[index]?.stadium) {
        const tracker = positionTrackers[index] ||= createPositionTracker(runtime.matches[index]?.stadium);
        tracker.observe(livePositions, tick);
      }
      if (includeFrames && (tick % SAMPLE_INTERVAL === 0 || tick === ticks - 1)) {
        const frame = runtime.frame();
        if (frame) (frameSets[index] ||= []).push(frame);
      }
      if (tick % 3600 === 0) onProgress(Math.floor(tick / ticks * 100));
    }
  } catch (error) {
    if (error instanceof Error && error.message) throw error;
    throw new Error('The recording is damaged or uses unsupported replay data.');
  }
  const games = runtime.matches.flatMap((game, i) => game.stadium && game.gameTicks >= 0
    ? [normalizeGame(game, i, frameSets[i] || [], rosters[i] || new Map(), starts[i] || 0, includeFrames, heatmaps[i], positionTrackers[i]?.finish())] : []);
  if (!games.length) throw new Error('No played games were found in this recording.');
  onProgress(100);
  return { schemaVersion: 1, engine: 'haxball-replay-analyzer-poc', positionVersion: POSITION_VERSION, ticks, sampleInterval: SAMPLE_INTERVAL, games };
}
