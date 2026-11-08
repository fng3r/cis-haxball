# Replay Lab proof of concept

The active application uses React 19, Vite, Tailwind CSS 4 and daisyUI 5. There is
no application framework, router, Redux, MUI, or Create React App. The original
player retains its jQuery dependency and its Sass styles inside an isolated frame.
The app runs as a static client application and analyzes local recordings in a dedicated Web Worker. No account or backend is required.

## Run

Requires Node 22.12 or newer.

```sh
cd analyzer
npm ci
npm run dev
```

Open http://127.0.0.1:3000/analyzer/. The dev server deliberately binds to IPv4 loopback.
`npm run dev` launches the Vite development server with hot reload. The port is
strict so it will not silently change addresses.

```sh
npm test
npm run build
npm start
```

`npm start` serves the existing `dist/` build using Vite preview; it does not
build the app or enable hot reload. `npm run preview` remains an equivalent alias.
For the staging systemd service, use `npm start -- --host 127.0.0.1 --port 3001 --strictPort`.
When using nvm, set the service PATH to include its Node bin directory; npm uses
`/usr/bin/env node` and cannot find Node from its absolute npm path alone.

Vite's base is configured as `/analyzer/` for development, builds, and preview.
`npm run build` needs no extra `--base` flag. When proxying to the preview server,
nginx must preserve that prefix: use `proxy_pass http://127.0.0.1:3001;` without a
trailing slash inside the `/analyzer/` location.

The production files are written to `dist/`. Deploy that directory to a static
host. The old upstream publishing scripts and homepage configuration are absent.

## Supported workflow

- Choose or drop multiple local `.hbr2` recordings at once, with per-file progress and errors.
- Switch between cached recordings, retry failed/cancelled analyses, and remove files.
- Switch between games in a recording, including changes of red/blue sides.
- Play/pause, restart, seek and change speed using the original HaxBall player.
- Compare possession, kicks, completed passes, shots on goal and ball territory.
- Sort player statistics; hover or select a player to view their movement heatmap.
- Click goals, assists, kicks, passes or on-target shot values for their event maps.
- Select goals to seek to the build-up, including assists and own goals.
- Use the native player’s previous/next goal buttons to step through all games.
  Both buttons and timeline clicks seek up to eight seconds before the goal,
  clamped to one recording tick after the preceding goal. Buttons
  disable at recording boundaries; scrubbing/reset recalculates their targets.
- Export statistics as JSON; browser analysis does not produce playback frames.

All required application resources are local. This proof of concept does not
connect to the old replay catalogue, upload recordings, or load advertising and
analytics. Catalogue browsing, team renaming, half merging, and stadium export
have not been ported. Native player room/chat controls, settings, audio and
transport are preserved. Django integration uses normalized Replay models and explicit read-only whole-match manifests; see [DJANGO_INTEGRATION.md](DJANGO_INTEGRATION.md).

Playback uses the original renderer, interpolation and requestAnimationFrame loop
from the pinned `game2.js`. React does not render playback frames or run a
playback timer. `NativePlayer.jsx` embeds `player.html` to isolate the original
styles and DOM controls from the modern workspace; it sends the original replay
bytes and occasional seek commands. The player starts paused at 1x and keeps its
native timeline, speed controls, settings, and canvas rendering.

`scripts/generate-player.mjs` adapts imports and startup without changing native
rendering or simulation. `src/player/native-adapter.inc` loads the bundled player
assets, mounts the original `Vb` controller and forwards seek commands to its
existing transport. Its resources are pinned in `public/player/upstream.json`.
The standalone analysis worker remains independent of playback.

```sh
npm run player:generate
```

## Shared engine

`src/engine/analyze.js` exports:

```js
import { analyzeReplay } from './src/engine/analyze.js';
const result = analyzeReplay(bytes, { onProgress: percent => {} });
```

It accepts an `ArrayBuffer` or `Uint8Array` (including Node Buffers and slices)
and returns plain structured data. Optional diagnostic frames require
`includeFrames: true`; the browser does not request them. Each call creates its own runtime state.
Errors throw. There are no DOM, React, network or filesystem requirements in the
analysis execution path. The browser invokes it from `analyze.worker.js`, sends
the file buffer by transfer, and terminates the worker on cancel/replacement.

Standalone usage:

```sh
node scripts/analyze.mjs /path/to/replay.hbr2 > stats.json
npm run analyze -- /path/to/replay.hbr2
node scripts/analyze.mjs /path/to/replay.hbr2 --frames > replay-with-frames.json
```

The CLI prints JSON and exits nonzero on failure. `schemaVersion: 1` includes
games, core metrics, goals, players and optional frames. This is a new schema,
not a replacement for the old replay.hax.ma response format. The standalone
function is synchronous; CPU-bound server usage should run it in a subprocess or
worker. The browser has a two-minute analysis timeout.

Proof-of-concept limits are replay format 3, 32 MB input, one hour of recording
time and 128 MB decompressed payload. The UI supports retry after an error.

## Upstream preservation and extraction

The original upstream snapshot is retained unchanged under `legacy/`, including
its source, README, license and dependency lockfile. Do not install its packages
to work on the new application. `upstream.json` gives the repository, pinned
commit and hashes relative to `baseDirectory: legacy`.

Upstream repository:
https://github.com/haxball-replay-analyzer/haxball-replay-analyzer.github.io

Pinned branch/commit: `react`, `8edd5339d3c19e907424efa04d450320a2979dd3`.

`scripts/generate-runtime.mjs` derives `src/engine/vendor-runtime.js` from the
untouched `legacy/src/game2.js`, checks its SHA-256, removes eager browser startup
and unbounded legacy heatmap sampling, and wraps it in a fresh function scope.
`runtime-adapter.inc` supplies explicit event callbacks, deterministic tick
advancement and frame capture. The generated module is imported statically;
there is no runtime eval, VM, proxy UI object, browser player, or fake DOM.

```sh
npm run engine:generate
npm test
```

This is an initial extraction boundary. The generated file still contains unused
legacy UI/networking definitions, and retains some generated type metadata on
built-in prototypes. They are not invoked to analyze a recording; the browser
isolates them in its worker. A subsequent engine cleanup can remove unreachable
definitions and those legacy side effects. Do not edit the generated file by
hand; put adapter changes in `runtime-adapter.inc` and regenerate.

The source still uses nickname-based heuristics for kicks, passes and assists.
Identical names or switching sides during a game can make individual event
attribution ambiguous. Playtime is tracked by player ID and side. At a new game,
the adapter resets kicker/toucher history so passes and assists do not leak
between games; this can remove a spurious cross-game pass counted by upstream.
Ratings and xG have not been added. The standalone adapter adds inferred playing
positions from live movement; the pinned upstream engine remains untouched.

## Inferred playing positions

The active engine emits `positionVersion: 2` and adds these fields to each player:

- `position`: `GK`, `DM`, `AM`, `ST`, or `null` when no role dominates.
- `positionConfidence`: 0–1 evidence consistency, **not a probability of correctness**.
- `positionRoles`: `{position, ticks, share}` entries for observed roles.
- `positionPeriods`: `{startTick, endTick, observedTicks, position, confidence}`
  entries. Bounds are recording ticks, end-exclusive; the player need not have
  been on the field throughout that interval. `observedTicks` is their live play
  within the window. Unclassified time remains in the share denominator.

`src/engine/positions.js` samples movement at 10 Hz during live play and counts
player presence at full tick resolution. Windows contain 30 seconds of live play,
so pauses and goal celebrations do not consume evidence. The upstream adapter
publishes stadium geometry after play begins; its first transition tick may be
absent from position evidence. Existing playtime and metric counters are unchanged.

Depth and lateral position are projected onto the axis between the side's own goal
and its opponent's goal. Translation, rotation, scaling, and red/blue changes
therefore preserve roles. GK requires sustained positioning behind contemporaneous
teammates with separation from them; it does not require staying in the goalmouth.
Outfield depth groups identify DM, AM and ST. Similar-depth forwards on opposite
flanks can both be ST. The detector does not prescribe four players, one role per
team, or an AM/ST split. It deliberately does not call a wide striker LW/RW.

Substitutions use native player ID plus replay side, not nicknames. No role is
reported until a player has at least **15 seconds of observed active play** in
that replay game. Shorter appearances have a null main role, zero confidence,
an empty role breakdown and unclassified periods retaining their observed time.
Paused or off-field time does not qualify. A local window still needs ten seconds
of evidence per player and two eligible players on that side, so substitutions
crossing a window boundary can contribute to a sufficiently long appearance.
The main role must cover at least 55% of observed play; otherwise it is null
while the breakdown remains available. Role changes have 30-second resolution,
not exact transition timestamps. Unsupported/multi-goal pitch layouts remain
unclassified. Roles are estimates of movement patterns, not declared assignments.

These fields are shared by the browser worker and original-engine CLI/export.
Engine v2 remains parked. No position column or Django domain field is added by
this change. New/reanalyzed `ReplayRecording.raw_response` values contain the
fields automatically; cached successful analyses require explicit reanalysis.

Validation and repeatable read-only audit instructions:
[ЧР #16 position comparison](../docs/reports/replay-positions-chr16.md).

The upstream MIT notice is preserved in `LICENSE.MD` and `legacy/LICENSE.MD`.
The provenance of apparent incorporated HaxBall client code has not been
independently established; the earlier research notes contain that distinction.

## Validation

`tests/engine.test.js` checks reference recording results, multiple games, own
goals, side swaps, consecutive-call isolation, sliced buffers and invalid input.
`tests/app.test.jsx` checks empty state, the worker handoff, game/player selection,
errors, retry and cancellation using a worker test double. Fixture origins are
recorded alongside the recordings. UI tests run in jsdom. Native-player tests cover the byte handoff, readiness,
seek queue and message isolation. Browser checks cover native playback and goal
seeking. The original canvas renderer was observed drawing at display cadence;
there is no 15 fps playback cap in the application.

## External replay links

The upload card offers “Use replay links” after an OR divider. It opens a modal
accepting multiple links in separate inputs with add/remove controls. Downloads run sequentially; each successful
download immediately enters the existing analysis queue. The first successful
download is selected; subsequent downloads in that submission keep the selection. Failed links remain for
retry, and closing/cancelling the modal aborts the current download and skips
remaining links without removing files already queued. Duplicate links within a
submission are downloaded once.

The modal accepts current `https://replay.thehax.pl/<id>` links (including
`/<id>/download`), legacy `https://thehax.pl/forum/powtorki.php?nagranie=<id>`
links, and VK away.php wrappers around those links. This follows the URL
resolution in Django's `tournament/replay_stats_client.py`; other hosts are not
yet supported. IDs are validated and downloads always use the fixed HTTPS URL
`https://replay.thehax.pl/<id>/download` rather than fetching an arbitrary URL.

The browser downloads directly with CORS and no credentials, with a 20-second
timeout and a 32 MiB streaming size limit. The response must have an HBR2 header
before it is queued as a local File for the existing analyzer and native player.
Download cancellation is separate from analysis queue cancellation. A cancelled
or failed download adds no recording; successful downloads remain session-only.

The host currently permits cross-origin downloads. If its CORS policy changes,
browser access may fail even if Django can still download server-side. The UI
reports network/CORS failures; no Django proxy or deployment changes are needed
for the current integration. Expired/private links must be publicly accessible.

## Multiple recordings and limits

The file picker and drop zone accept multiple recordings. Additional selections
append to the current library and select the first valid file in the new batch. Analysis
runs sequentially in disposable workers; only one native player is mounted.
Results stay associated with their original file, and switching files reuses the
cached statistics while restarting native playback at the beginning. Games and
JSON export apply to the selected recording; recordings are not merged.

A failed or timed-out file does not stop the queue. Cancel stops the current and
all queued analyses, preserving completed results. Each cancelled or failed item
can be retried. Removing an active item terminates its worker and advances the
queue; removing any item releases its stored file/result references. Late worker
messages and file reads cannot update a removed or cancelled job.

Existing limits apply independently to each file:

- At most 32 MiB compressed input and 128 MiB decompressed replay data.
- Replay format version 3, with at most one hour of recording ticks.
- Two-minute timeout per analysis, including reading the file.

There is no fixed file-count limit. Analysis time grows with recording duration,
player count and physics complexity. Retained results and the active player still
consume browser memory; the decompressed-data limit is not a total memory bound.
Remove recordings when finished to release their cached data. The library is
session-only and disappears on refresh; files are not uploaded or persisted.

## Spatial analysis and exports

Each player's `maps` object includes `heatmap`, `goals`, `assists`, `kicks`,
`passes` and `shots`. All of these fields are retained by JSON export and the
standalone CLI. Goal records also include the scoring kick, assisting kick and
ball coordinates at the goal when those locations are available.

Movement density counts every active tick in 10-unit spatial cells, exported as
`{ x, y, ticks }`; this avoids retaining millions of raw position objects without
sampling away playtime. Event locations retain the original world coordinates.
Kick maps contain points; passes, goals and shots contain `from`/`to` paths;
assists also include the receiving player's `via` point. The map background uses
the original analyzer's stadium drawing code, with local pitch textures extracted
from the pinned player resource archive. Maps redraw only when selected, and
are independent of native playback. They do not impose any playback frame cap.

Previously loaded results must be regenerated by reopening the recording to
include spatial data. Events without attributable coordinates remain visible in
numeric statistics; the map reports when it has no drawable events.

The selected game's statistics also follow manual player timeline seeks, reset,
and natural playback across game boundaries. During seeking, synchronization
uses the destination rather than intermediate simulation ticks. Reset clears a
pending seek before returning to the first game. Only game changes and explicit
seeks notify React; playback does not send per-frame position updates.

## Viewing controls

Focus mode fills the viewport with the native player, hiding the app sidebar,
outer scoreboard and player chat/buttons. Playback controls remain visible.
The exit button or Escape restores the workspace without remounting the player.
Escape from inside the iframe exits focus mode before the native menu handles it.

The player card's keyboard button or the ? key opens a daisyUI shortcut reference, also
available in focus mode. It lists seek, speed, playback and zoom keys. Native
1–4 zoom keys require focus inside the player; 0 restores fit-pitch view.
Playback shortcuts are suspended while a workspace dialog is open. The native
chat omits the introductory controls text; controls are listed in the reference.

F toggles focus mode from the page or player. [ and ] activate the existing
previous/next goal controls, including their eight-second lead-in and boundary
handling. Holding F does not repeatedly toggle focus mode.

The React UI uses named `lucide-react` icon imports for action buttons, theme,
focus, sorting and keyboard help. Icons alongside text are decorative; icon-only
buttons retain accessible labels. The custom brand mark and isolated legacy
player keep their existing artwork.

Player maps change only on explicit player-row or statistic clicks. Hovering
highlights rows without replacing the selected map. Player/map selection survives
stats-tab changes and resets on game/recording changes. Playtime is plain text,
not an event-map button. There is no separate pin/unpin state.

The native player is covered by a themed loading screen during iframe/file
initialization and recording switches. Its ready message reveals the same iframe
without restarting playback. Errors or a 45-second initialization timeout show
a retry action; retry mounts a fresh iframe without rerunning analysis.

## Replay preparation, checkpoints and chat

The shared native player runs one preprocessing simulation when opening a
recording. It builds native binary state checkpoints every 900 recording ticks
(15 seconds at 60 Hz) and indexes chat, announcements and system notices during
that same pass. It then restores the initial snapshot before showing the player.
Neither statistics engine is involved or changed.

Each checkpoint stores complete native serialized game state, the recording tick,
and the decoder cursor/base tick **before** decoding the pending action. Restoring
that cursor and decoding again preserves same-tick action ordering, player input,
kick cooldowns, scores, pauses, stadium state and lobby/match boundaries. Binary
buffers are copied to their exact size and discarded with the recording/player.

`src/player/checkpoints.js` replaces the shared replay seek entry point. Backward
seeks restore the nearest checkpoint at or before the destination. Forward seeks
restore only when a checkpoint is ahead of the actual simulation position; short
forward jumps keep the current state. Native fast-forward then simulates less than
15 seconds, normally completing within one or two animation frames. Playback
speed and paused state are preserved. Reset retains the native initial-state path.
Timeline clicks, goal controls, game selection and hotkeys all use this seek entry.

`src/player/chat-index.js` captures messages during preprocessing, including
physics-generated match results. `chat-sync.js` shows the most recent 100 entries
at or before the transport timestamp. During seeks it uses the destination while
physics catches up. Native append calls are suppressed to prevent duplicates.
The log updates only when the message window changes, preserves scrolling during
playback, and scrolls to the latest message after seeks. All content uses text
nodes, including announcements.

Tests compare complete serialized state with uninterrupted native playback on
all four recordings. They exercise both directions, checkpoint/goal boundaries,
substitutions, pauses, match transitions, end-of-file, reset, paused seeks and
subsequent simulation after restoration. Chat tests verify the captured timeline,
repeated playback, formatting, text safety and bounded DOM size.

## Independent analysis engine v2

An initial replacement engine lives in `src/engine-v2/`, alongside the unchanged
original engine. It has its own runtime generator, named observations, metric
collectors, versioned JSON schema, CLI and worker entry point. The header engine switcher reloads the page and selects the original or v2
worker; engine-specific views preserve their different metric definitions. See [ENGINE_V2.md](ENGINE_V2.md) for implemented
metrics, definitions, limits, usage and validation.
