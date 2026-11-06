import { Inflate } from 'pako';
import { createRuntime } from './vendor-runtime.js';
import { createCollector, DEFAULT_OPTIONS } from './collector.js';
import { MATCH_COUNTERS } from './match-metrics.js';

export const MAX_FILE_BYTES = 32 * 1024 * 1024;
const MAX_INFLATED_BYTES = 128 * 1024 * 1024;
const COUNT_FIELDS = ['kicks', 'contacts', 'transfers', 'received', 'progressiveTransfers', 'turnovers', 'goals', 'ownGoals', 'assists', ...MATCH_COUNTERS];
function inflateRaw(bytes) {
  const decoder = new Inflate({ raw: true }), chunks = [];
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
function sum(items, field) { return items.reduce((total, item) => total + (item[field] || 0), 0); }
export function aggregateGames(games) {
  const groups = new Map();
  for (const game of games) for (const player of game.players) {
    if (!groups.has(player.id)) groups.set(player.id, []);
    groups.get(player.id).push(player);
  }
  return {
    gameCount: games.length, activeTicks: sum(games, 'activeTicks'), observedGoals: games.reduce((total, game) => total + game.goals.length, 0),
    players: [...groups.values()].map(items => {
      const first = items[0], activeTicks = sum(items, 'activeTicks');
      return { id: first.id, playerId: first.playerId, team: first.team, names: [...new Set(items.flatMap(item => item.names))],
        games: items.length, activeTicks, distance: sum(items, 'distance'),
        ...Object.fromEntries(COUNT_FIELDS.map(field => [field, sum(items, field)])),
        averageSpeed: activeTicks ? items.reduce((sum, p) => sum + p.averageSpeed * p.activeTicks, 0) / activeTicks : 0,
        peakSpeed: Math.max(...items.map(p => p.peakSpeed)), onFieldGoalDifference: sum(items, 'onFieldGoalDifference') };
    }),
    teams: Object.fromEntries(['red', 'blue'].map(team => [team, Object.fromEntries(
      [...COUNT_FIELDS, 'possessionTicks', 'observedGoalsFor', 'observedGoalsAgainst', 'distance', 'leadingTicks', 'drawingTicks', 'trailingTicks'].map(field => [field, sum(games.map(g => g.teams[team]), field)]),
    )])),
  };
}

/** Independent v2 pipeline. Run CPU work in its worker or the standalone CLI. */
export function analyzeReplay(input, { onProgress = () => {}, onEvent = () => {}, onFrame,
  includeEvents = true, includeTracking = false, trackingInterval = 6, metrics = {} } = {}) {
  const bytes = input instanceof ArrayBuffer ? new Uint8Array(input) : input;
  if (!(bytes instanceof Uint8Array) || bytes.byteLength < 12) throw new Error('Choose a valid .hbr2 recording.');
  if (bytes.byteLength > MAX_FILE_BYTES) throw new Error('Choose a recording smaller than 32 MB.');
  const header = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (header.getUint32(0) !== 0x48425232) throw new Error('This file is not an HBR2 recording.');
  if (header.getUint32(4) !== 3) throw new Error(`Replay format ${header.getUint32(4)} is not supported. Expected version 3.`);
  const ticks = header.getUint32(8);
  if (!ticks || ticks > 216000) throw new Error('Choose a non-empty recording up to one hour long.');
  if (!Number.isInteger(trackingInterval) || trackingInterval < 1) throw new Error('trackingInterval must be a positive integer.');
  const collector = createCollector({ ...metrics, includeEvents, onEvent });
  const runtime = createRuntime(inflateRaw), tracking = [];
  try {
    const { initial } = runtime.load(Uint8Array.from(bytes));
    collector.initial(initial); onProgress(0);
    for (let tick = 0; tick < ticks; tick++) {
      const packet = runtime.step();
      collector.consume(packet);
      if (onFrame) onFrame(packet);
      if (includeTracking && tick % trackingInterval === 0) {
        const { stadium, ...frame } = packet.after;
        if (frame.gameId != null) tracking.push(frame);
      }
      if (tick % 3600 === 0) onProgress(Math.floor(tick / ticks * 100));
    }
  } catch (error) {
    if (error instanceof Error && error.message) throw error;
    throw new Error('The recording is damaged or uses unsupported replay data.');
  }
  const games = collector.finish();
  if (!games.length) throw new Error('No played games were found in this recording.');
  onProgress(100);
  return { schemaVersion: 2, engine: 'replay-lab-v2', metricsVersion: 3, tickRate: 60, ticks,
    definitions: { timeBasis: 'live-play-only-including-the-kickoff-activation-tick', ...DEFAULT_OPTIONS, ...metrics, territory: 'three-equal-zones-between-defended-goal-centres',
      transfers: 'next-distinct-ball-interaction-after-kick', proximity: 'within-player-and-ball-radii-plus-4-not-possession',
      control: 'kick-or-uncontested-contact-settled-for-controlTicks-within-controlRelativeSpeed',
      possession: 'last-confirmed-controller-team-including-ball-flight; percentages-exclude-unassigned-time',
      completedPasses: 'kick-to-confirmed-teammate-control-within-transferWindowTicks; excludes-goal-bound-kicks-and-opponent-deflections',
      progressivePasses: 'completed-pass-reducing-goal-centre-distance-by-progressiveFraction-of-pitch-length',
      recoveries: 'confirmed-opponent-to-own-team-control; initial-unowned-ball-excluded',
      possessionLosses: 'confirmed-control-lost-to-opponent; shot-releases-excluded',
      shotsOnTarget: 'direct-unobstructed-goal-bound-kicks-with-damping-reach-and-ball-radius; excludes-bank-shots-and-gravity',
      keyPasses: 'final-completed-pass-to-shooter-within-assistWindowTicks; one-credit-per-pass',
      goalAttribution: 'last-distinct-interactions-within-assistWindowTicks', velocityUnits: 'world-units-per-tick', speedUnits: 'world-units-per-second' },
    games, summary: aggregateGames(games), ...(includeTracking ? { trackingInterval, tracking } : {}) };
}
