# Replay analysis engine v2 — first implementation

The original `src/engine/`, its generator, the pinned `legacy/` tree and native
player are unchanged. The app uses the original engine; Engine v2 and its header
switcher are hidden behind a disabled-by-default feature flag. V2 remains available as an independent API/CLI
and worker entry point with its own definitions and statistics views.

## Run

```sh
cd analyzer
npm run --silent analyze:v2 -- tests/fixtures/cis5.hbr2 > /tmp/cis5-v2.json
npm run --silent analyze:v2 -- tests/fixtures/futsal-multi.hbr2 --no-events > /tmp/futsal-v2.json
npm run --silent analyze:v2 -- tests/fixtures/cis4.hbr2 --tracking > /tmp/cis4-tracking-v2.json
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
the corresponding worker. Dedicated v2 views consume its fields directly with
explicit possession, passing and shot definitions.
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
4. `match-metrics.js` classifies confirmed control, passing, shooting and control
   changes independently of raw touches. `collector.js` consumes those observations
   and independently accumulates
   per-game, per-team and per-player metrics. It can be tested on synthetic states
   independently of replay decoding. `analyze.js` provides input limits, iteration,
   recording-wide aggregates and the versioned output.

## Implemented measurements

| Measurement | Definition |
|---|---|
| Recording/game boundaries | Recording start/end ticks, initial score, final native score and observed starts/ends. `truncatedStart` means the game was already present in the initial state; `truncatedEnd` means no finish/stop was observed. |
| Played time | The default denominator for all statistics: live simulation ticks, including the kickoff tick that activates play and the tick that produces a goal/end. Pauses, waiting for kickoff, celebrations and ended phases do not contribute. |
| Score-state time | Each team's active ticks leading, drawing and trailing. |
| Goals | Authoritative native scoring events, their scoring team, score, game-clock tick and recording tick. Existing initial goals in clipped recordings are not invented as observed events. Team `observedGoalsFor/Against` counts the actual scoring events, including own goals; team `goals` is the sum of individual scorer credits. |
| Goal attribution | Last distinct ball interaction within 480 ticks (8 seconds), own goal if that actor's team differs from the scoring team. Previous distinct teammate interaction in the same window is an assist. These are heuristics, not official intent/deflection adjudication. |
| On-field goal difference | Observed goals for minus against while each player is on the field, separate from scorer credit. |
| Successful kicks | Actual kick impulses applied to disc 0, with actor ID/team, location and before/after velocity. Kick-button presses outside kicking range do not count. Only live-play kicks enter counters and maps, including a kickoff kick that activates play; all other phases remain raw events only. |
| Contact episodes | Actual main-ball/player collision episodes, separate from kicks. Repeated collisions on consecutive simulation ticks count once; a gap of at least one non-contact tick opens another episode. Contact velocity-after is explicitly after the whole physics step. Only live-play episodes enter counters/maps; other phases remain raw events. |
| Team possession | Last confirmed controller's team owns time, including ball flight, until another player establishes control or a phase/restart/roster change resets the chain. A successful kick establishes control immediately. A contact requires six consecutive uncontested ticks within player radius + ball radius + 4 units, with relative speed ≤2 units/tick. Unknown time remains `possessionTicks.unassigned`; UI percentages divide only by the two teams' attributed time. This is an explicit estimation rule, not pass intent or exact continuous ball control. |
| Completed passes / passes received | Non-shot kick by A followed within 300 ticks by teammate B's confirmed control (another kick or a settled reception). The release is consumed once. Opponent deflections, ambiguous same-tick interactions, self-recovery, expiry, roster changes and phase boundaries break the candidate. Receptions without another kick are included. Maps retain linked raw event IDs and recording/game times. |
| Progressive passes | Completed passes that reduce distance to the opposing goal centre by at least 10% of the distance between defended goal centres. Works for either direction and rotated goals; unavailable without usable goal geometry. |
| Passing network | `passNetwork` sums directed completed-pass counts and displacement by native player ID/team. The older `transferNetwork` remains separate raw interaction telemetry. |
| Recoveries | A player's confirmed control after an opposing controller. Deflections alone, initial unowned balls and restart touches are excluded. These are team regains, without claiming tackle or interception intent. |
| Possession losses | Previous controller/releaser loses established team control to an opponent. Goal-bound shot releases are excluded, as are administrative changes/restarts and ambiguous touches without subsequent confirmed control. A shot followed by the shooter's settled self-recovery becomes ordinary possession again. |
| Shots on target | Successful kicks projected directly through the opposing goal mouth, allowing for ball radius at the posts and dynamic ball damping. Velocity must point toward the opposing goal and its geometric damping reach must exceed the goal-line distance. A counterfactual, unobstructed projection, like the original analyzer's goal-bound-kick heuristic; does not simulate walls, bank shots, static obstacles or shot outcomes. Nonzero gravity/unsupported physics disable `shotsAvailable` so the UI shows unavailable rather than a misleading zero. It is not an all-attempts dataset: no shooting accuracy/conversion denominator is invented. |
| Key passes | Final completed pass to a player who kicks a shot on target within 480 ticks, without an opposing touch or intervening confirmed recipient. A pass receives at most one key-pass credit. Map links pass → shooter → goal target; events reference the completed pass and shot. |
| Observed transfers | Kick by A followed within 300 ticks (5 seconds) by the next distinct player interaction B on the same team. Reception can be a physical contact without a kick. Not an inference about intended passes or settled possession. |
| Transfer receipts | Credit to B for the same linked event. Includes release/reception event IDs and times, endpoints, Euclidean displacement and progress toward the opposing goal. |
| Turnover proxy | The same release-to-interaction sequence when B is an opponent. Not labelled a tackle, interception, or proven loss of controlled possession. |
| Progressive transfers | Transfers reducing distance to the opponent's goal centre by at least 10% of goal-to-goal distance. |
| Transfer network | Directed actor-to-receiver counts and total transfer displacement. |
| Distance travelled | Sum of before/after positions for active physics steps with the same disc instance. No cross-tick subtraction across administrative teleports; waiting-for-kickoff, goal/pause/ended phases are excluded. |
| Average/peak speed | Mean/maximum native velocity magnitude during active ticks, converted to world units per second. Not metres or physical human exertion. |
| Average position | Active-tick mean world position. |
| Heatmaps | Active occupancy in 10-unit cells, with exact accumulated tick counts. Also event maps for goals, own goals, assists, kicks, completed/received/progressive passes, key passes, shots on target, recoveries and losses, plus raw interaction maps. |
| Kicks/minute | Successful kick count divided by active minutes; null if no active time. Numerator and denominator use the same live-play eligibility rule. |
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
  last-touch owner to a distant ball. Confirmed-control classifications are separate
  from those buckets. Carries,
  pressing, shot intent, saves/blocks and xG remain deferred. Saves require reliable
  shot outcome and goalkeeper-role rules; defender deflections are not automatically
  labelled saves or possession recoveries.
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

`tests/engine-v2.test.js` checks all four owner-supplied replay fixtures plus
synthetic scenarios for name collisions, phase filtering, reset/teleport exclusion, timed transfer
links, receipts, turnovers, expiry, contested contacts, rotated geometry and
clipped games. Invariants check player/team count conservation, heatmap time,
proximity/territory totals, score-state time, transfer-network totals, streaming
versus retained results, deterministic repeated runs, sliced buffers and input
validation. `tests/match-metrics.test.js` separately covers settled receptions, kicks,
deflections, contested and ambiguous touches, self-recovery, pauses/expiry,
progression in both directions and rotated pitches, control changes, flight
possession, shot exclusions from losses, trajectory/radius/damping rules, key-pass
links and expiry, and count/map/network conservation. UI tests exercise the
passing/defence groups, clickable maps, sorting, click-only selection and exports.
Original-engine regression and native physics-equivalence tests run on all
four recordings.

More recordings are valuable before calling classifications production-ready,
especially duplicate names and unusual custom physics. The current fixtures cover
multiple games, substitutions, pauses and recordings without a game-end event;
see `tests/fixtures/README.md` for provenance and validation limits.
See `METRICS_RESEARCH.md` for the broader unimplemented catalogue.

## Web UI

Set `VITE_ENABLE_ENGINE_V2=true` in `.env.local` and restart the dev server (or
set it when building) to enable experimental v2 access. With the flag unset or
false, the switcher is hidden and the original engine is always used, including
when a URL or saved browser preference requests v2. The standalone API/CLI remains
available independently of this web flag.

When enabled, choose Original or Engine v2 in the header. The choice is stored in browser
preferences and the `engine` URL parameter; URL selection takes precedence.
Switching engine navigates to a new document, clearing the session-only recording
library. A valid explicit URL parameter still works when local storage is blocked.

The overview includes possession, goals, assists, own goals, kicks, shots on
target, completed and progressive passes, key passes, recoveries and possession
losses, alongside ball territory. Team goals count observed scoring events,
including opponents' own goals. Player rows show individual scorer credit.

Player selection remains click-only, with sortable columns and event-map buttons.
Attack shows goals, assists, own goals, shots on target and kicks. Passing shows
completed passes, passes received, progressive passes and key passes. Defence
shows recoveries and possession losses. Played time appears in every group as
plain text. Grouping keeps the table usable next to the map on wide screens.
The map selector offers all those events plus the movement heatmap, regardless
of which column group is selected. A counting guide explains the rules in plain
language. Unsupported shooting/goal geometry produces unavailable values, not
a false zero.

Raw transfer/turnover proxies, contact episodes, proximity, team shape and
unscaled distance/speed measurements remain available in the v2 API/export for
research. The new football-facing metrics have their own classifications, linked
events and maps; raw transfer counters are not simply renamed.

Goals retain the shared timeline and native player's eight-second lead-in. A
view-only adapter reads scores from v2 goal arrays. Export preserves the original
v2 schema, summary, events, goal attribution and spatial maps.

All displayed statistics use live-play time by default. V2 does not expose a
separate active-time headline or accumulate all-phase on-field duration/phase-time
metrics. Raw phases and recording timestamps remain decoder metadata needed for
filtering and seeking. Metrics version 3 adds the confirmed-control, passing and
shooting definitions above while retaining the same live-tick rule for time,
interactions, maps and movement, including the kickoff activation tick.
