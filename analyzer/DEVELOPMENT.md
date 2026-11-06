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

- Choose or drop a local `.hbr2` recording, with progress, cancellation, and errors.
- Switch between games in a recording, including changes of red/blue sides.
- Play/pause, restart, seek and change speed using the original HaxBall player.
- Compare possession, kicks, completed passes, shots on goal and ball territory.
- Sort player statistics; hover or select a player to view their movement heatmap.
- Click goals, assists, kicks, passes or on-target shot values for their event maps.
- Select goals to seek to the build-up, including assists and own goals.
- Use the native player’s previous/next goal buttons to step through all games.
  Both buttons and timeline clicks seek eight seconds before the goal. Buttons
  disable at recording boundaries; scrubbing/reset recalculates their targets.
- Export statistics as JSON; browser analysis does not produce playback frames.

All required application resources are local. This proof of concept does not
connect to the old replay catalogue, upload recordings, or load advertising and
analytics. Catalogue browsing, team renaming, half merging, and stadium export
have not been ported. Native player room/chat controls, settings, audio and
transport are preserved. Django integration is unchanged.

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
Ratings, positions, xG and other enriched metrics have not been added.

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
