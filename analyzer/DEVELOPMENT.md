# Standalone replay engine

Requires Node 22.12 or newer. Install with `npm ci` and run the engine tests
with `npm test`. `npm run analyze -- recording.hbr2` invokes the JSON CLI;
use `node scripts/analyze.mjs recording.hbr2` for JSON-only stdout.

`src/engine/analyze.js` exports `analyzeReplay(bytes, options)`. It accepts an
ArrayBuffer or Uint8Array, including sliced Node Buffers, and returns a versioned
plain-data result. Each call owns its analysis state. It has no React, DOM,
network or filesystem dependencies in the execution path. `analyze.worker.js`
provides the browser worker message protocol for future UI integration.

Results include separate games, scores, possession, thirds, kicks, completed
passes, shots on goal, player playtime, goals and assists. Each player's `maps`
contains movement density and event coordinates. `serializeStats` retains these
fields while excluding optional diagnostic playback frames. Movement density
counts every active tick into 10-unit spatial cells. Passes, goals and shots
include from/to coordinates; assists also include a via point. Optional playback
samples require `includeFrames: true` or the CLI's `--frames` option.

Limits: replay format 3, 32 MB input, one hour of recording time, 128 MB inflated
payload. Errors throw; the CLI exits nonzero. Server callers should run this
synchronous CPU work in a subprocess or worker.

## Upstream preservation

The original upstream snapshot is unchanged under `legacy/`, including its
source, license and package lockfile. `upstream.json` records provenance and
SHA-256 hashes relative to `baseDirectory: legacy`.

`scripts/generate-runtime.mjs` verifies the pinned game2.js hash and creates the
statically imported `src/engine/vendor-runtime.js`. It removes eager browser
startup and per-tick legacy heatmap arrays. `runtime-adapter.inc` supplies
explicit callbacks, deterministic tick advancement and spatial event capture.
Regenerate with `npm run engine:generate`, then run `npm test`.

This is an initial extraction: unused legacy UI/network definitions and some
built-in prototype metadata remain in the generated runtime. They are not
invoked during analysis. Edit the adapter/generator rather than the generated
file. Nickname-based heuristics still make some identical-name or mid-game side
switch attribution ambiguous. Kicker/toucher history resets between games.

The upstream MIT notice is retained. Provenance of apparent incorporated HaxBall
client code has not been independently established.

## Validation

Engine tests cover baseline replay statistics, multiple games, side swaps, own
goals, spatial coordinates and JSON exports, consecutive-call isolation, sliced
buffers, invalid inputs and limits. Replay fixture provenance is recorded in
`tests/fixtures/README.md`.
