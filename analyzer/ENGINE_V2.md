# Replay analysis engine v2 — first implementation

The original `src/engine/`, its generator, the pinned `legacy/` tree and native
player are unchanged. The app defaults to the original engine and offers Engine v2
through the header switcher. V2 also remains available as an independent API/CLI
and worker entry point with its own definitions and statistics views.

## Run

```sh
cd analyzer
npm run --silent analyze:v2 -- tests/fixtures/big.hbr2 > /tmp/big-v2.json
npm run --silent analyze:v2 -- tests/fixtures/handball.hbr2 --no-events > /tmp/handball-v2.json
npm run --silent analyze:v2 -- tests/fixtures/big.hbr2 --tracking > /tmp/big-tracking-v2.json
npm run engine:v2:generate
```

`analyzeReplay` is exported from `src/engine-v2/analyze.js`. It accepts an
ArrayBuffer, Uint8Array or sliced Node Buffer. Options:

- `onProgress(percent)`: periodic progress and a final 100 on success.
- `includeEvents` (default true): retain the timed event log in each game.
- `onEvent(event)`: consume the same event stream without retaining the log.
- `onFrame(packet)`: full 60 Hz normalized before/after simulation states and
  events, including player inputs, velocities, radii and dynamic disc physics.
  Packets use recording ticks; snapshots are before/after that tick's physics,
  after recorded actions have been applied. Treat these observations as read-only.
- `includeTracking` (default false): retain sampled after-step states, including
  dynamic discs, player positions/velocities/inputs, ball, phase and score.
- `trackingInterval` (default 6): sample interval in simulation ticks; 1 retains
  every tick and can produce very large JSON. Stadium geometry is stored per game.
- `metrics`: override the explicitly versioned classification settings below.

`src/engine-v2/analyze.worker.js` uses the same input/result/progress/error message
contract as the original worker, but returns schema v2. The engine switcher selects
the corresponding worker. Dedicated v2 views consume its fields directly rather
than pretending they are the old possession, passing or shot definitions.
A bundler can reference it with `new Worker(new URL('./engine-v2/analyze.worker.js',
import.meta.url), { type: 'module' })` from a module in `src`.

## Architecture

1. `scripts/generate-runtime-v2.mjs` independently derives a runtime from the
   hash-pinned upstream simulation. Strictly checked instrumentation points
   observe successful impulses to the main ball and actual disc collisions.
2. Inherited analytics are disabled; their stadium-initialization block is
   removed from this generated copy. The simulation, event decoding and physics
   remain the foundation. Neither old generated runtime is regenerated/edited.
3. `runtime-adapter.inc` translates native fields into named observations and
   records game boundaries, input changes, roster changes, kicks and contact
   episodes. Successful kicks capture immediate before/after ball velocity and a
   player-position freeze frame; goals also capture all player positions.
4. `collector.js` consumes those observations and independently accumulates
   per-game, per-team and per-player metrics. It can be tested on synthetic states
   independently of replay decoding. `analyze.js` provides input limits, iteration,
   recording-wide aggregates and the versioned output.

## Implemented measurements

| Measurement | Definition |
|---|---|
| Recording/game boundaries | Recording start/end ticks, initial score, final native score and observed starts/ends. `truncatedStart` means the game was already present in the initial state; `truncatedEnd` means no finish/stop was observed. |
| Phase time | Ticks observed in kickoff, active play, pause/resume countdown, goal celebration and ended phases. Every tick is classified from its pre-physics state. |
| On-field time | Presence of a playing-team disc during a game, including pauses, kickoff and celebration. Separate from active time. |
| Active playtime | On-field ticks whose pre-physics phase is active, excluding pause and resets. Includes a tick that produces a goal/end. |
| Score-state time | Each team's active ticks leading, drawing and trailing. |
| Goals | Authoritative native scoring events, their scoring team, score, game-clock tick and recording tick. Existing initial goals in clipped recordings are not invented as observed events. Team `observedGoalsFor/Against` counts the actual scoring events, including own goals; team `goals` is the sum of individual scorer credits. |
| Goal attribution | Last distinct ball interaction within 480 ticks (8 seconds), own goal if that actor's team differs from the scoring team. Previous distinct teammate interaction in the same window is an assist. These are heuristics, not official intent/deflection adjudication. |
| On-field goal difference | Observed goals for minus against while each player is on the field, separate from scorer credit. |
| Successful kicks | Actual kick impulses applied to disc 0, with actor ID/team, location and before/after velocity. Kick-button presses outside kicking range do not count. Kickoff kicks are included; goal/ended-phase impulses remain raw events but are excluded from counters. |
| Contact episodes | Actual main-ball/player collision episodes, separate from kicks. Repeated collisions on consecutive simulation ticks count once; a gap of at least one non-contact tick opens another episode. Contact velocity-after is explicitly after the whole physics step. Only kickoff/active episodes enter counters; other phases remain raw events. |
| Observed transfers | Kick by A followed within 300 ticks (5 seconds) by the next distinct player interaction B on the same team. Reception can be a physical contact without a kick. Not an inference about intended passes or settled possession. |
| Transfer receipts | Credit to B for the same linked event. Includes release/reception event IDs and times, endpoints, Euclidean displacement and progress toward the opposing goal. |
| Turnover proxy | The same release-to-interaction sequence when B is an opponent. Not labelled a tackle, interception, or proven loss of controlled possession. |
| Progressive transfers | Transfers reducing distance to the opponent's goal centre by at least 10% of goal-to-goal distance. |
| Transfer network | Directed actor-to-receiver counts and total transfer displacement. |
| Distance travelled | Sum of before/after positions for active physics steps with the same disc instance. No cross-tick subtraction across administrative teleports; kickoff/goal/pause phases are excluded. |
| Average/peak speed | Mean/maximum native velocity magnitude during active ticks, converted to world units per second. Not metres or physical human exertion. |
| Average position | Active-tick mean world position. |
| Heatmaps | Active occupancy in 10-unit cells, with exact accumulated tick counts. Also event maps for kicks, contacts, transfers, receipts, turnovers, goals and assists. |
| Kicks/minute | Successful kick count divided by active minutes; null if no active time. Kickoff kicks are included in numerator, so this is an exposure-normalized rate, not active-phase-only kicks. |
| Ball thirds | Three equal longitudinal regions between the centres of the red and blue defended goals, supporting rotated goals and reversed sides. Outer positions belong to the nearest end third. Unavailable if either goal is missing. |
| Ball proximity | Active ticks with only red, only blue, both teams, or neither team within player radius + ball radius + 4 units. This is explicitly not possession. |
| Team shape | Active-tick mean width/depth projected along/across the goal-to-goal axis. Includes all on-field players; unavailable without usable goal geometry. |
| Recording aggregates | Sum counts/time/distance per player ID and team across games, weighted average speed, peak speed, aliases, and observed goals. |

Maps and event logs stay in the v2 JSON. `--no-events` omits the raw log, but keeps
aggregates, maps and goal records. `--tracking` adds sampled tracking; default
analysis does not retain full tick histories. No browser globals or DOM shims are
required for analysis.

## Classification boundaries and limitations

- Native IDs, not nicknames, are authoritative within a recording. A team switch
  produces separate `playerId:team` aggregates, and renamed players retain aliases.
  IDs are not account identities across unrelated files.
- Transfers expire, clear across phase changes/restarts and roster changes, and are not inferred
  when multiple players physically contact the ball in the same tick. A later
  same-player contact ends the release candidate as a self-recovery.
- The proximity buckets always sum to active game time. They do not assign a
  last-touch owner to a distant ball. Actual controlled possession, recoveries,
  carries, pressing, shot intent, saves/blocks and xG are deliberately deferred.
- Only disc 0 is treated as the ball for interactions. Multi-ball/custom scoring
  maps require additional definitions. Native goal totals can include other
  scoring discs; their main-ball attribution should not be treated as reliable.
- Goal attribution can differ from the original engine because physical contacts
  now count as interactions. Last-touch own goals/assists are imperfect; events
  and freeze frames are retained to make those decisions reviewable.
- Recording ticks and native match-clock ticks are different. Native floating
  clock accumulation can result in an extra active tick at the time limit; the
  engine reports the observed simulation tick count rather than copying the old
  analyzer's zero-based `gameTicks` counter.
- Game event streams exclude lobby-only events. Recorded actions within a game
  preserve joins/leaves/team switches/renames/input changes; player input state
  is also present in normalized frame observations. No chat messages are retained.
- Input limits remain 32 MiB compressed, 128 MiB decompressed, HBR2 version 3,
  and one hour of ticks. Streaming collectors do not make exported event logs,
  spatial maps or optional tracking free of memory cost.

## Validation

`tests/engine-v2.test.js` checks two real replay fixtures plus synthetic scenarios
for name collisions, phase filtering, reset/teleport exclusion, timed transfer
links, receipts, turnovers, expiry, contested contacts, rotated geometry and
clipped games. Invariants check player/team count conservation, heatmap time,
proximity/territory totals, score-state time, transfer-network totals, streaming
versus retained results, deterministic repeated runs, sliced buffers and input
validation. All existing legacy tests remain in the suite.

More recordings are valuable before calling classifications production-ready,
especially mid-game starts/stops, substitutions, pauses, duplicate names and
custom physics. See `METRICS_RESEARCH.md` for the broader unimplemented catalogue.

## Web UI

Choose Original or Engine v2 in the header. The choice is stored in browser
preferences and the `engine` URL parameter; URL selection takes precedence.
Switching engine navigates to a new document, clearing the session-only recording
library. A valid explicit URL parameter still works when local storage is blocked.

V2 Overview emphasizes active time, loose/contested ball proximity, kicks,
contacts, observed/progressive transfers and turnover proxies. Territory uses
three equal pitch zones. Movement shows team distance and average width/depth.
Statistics describe the captured play. Unavailable goal geometry is explained inline.

V2 Players sorts goals, assists, kicks, transfers, receipts, turnovers, distance
and active time, initially red then blue. Click-only player/map selection survives
tab changes. The map selector adds contacts, transfers, receptions and turnovers;
selected-player details show movement speed, contacts, progressive transfers and
on-field goal difference. Wide layouts show table and maps side by side.

Goals retain the shared timeline and native player's eight-second lead-in. A
view-only adapter reads scores from v2 goal arrays. Export preserves the original
v2 schema, summary, events, goal attribution and spatial maps.
