# Local analyzer development

This directory vendors the existing HaxBall Replay Analyzer web application as a starting point for a shared replay analysis engine. The Django application does not invoke it yet.

## Upstream snapshot

- Repository: https://github.com/haxball-replay-analyzer/haxball-replay-analyzer.github.io
- Branch: `react`
- Commit: `8edd5339d3c19e907424efa04d450320a2979dd3`
- Upstream commit date: 2023-07-22
- Imported: 2026-11-06

All upstream tracked files were copied unchanged, including `README.md`, `LICENSE.MD`, and the npm lockfile. `upstream.json` records their original SHA-256 hashes so future extraction changes can be distinguished from the imported baseline. There is no nested Git repository or submodule. `DEVELOPMENT.md` and `upstream.json` are local additions.

The upstream repository declares MIT; its notice is preserved verbatim. The apparent incorporated HaxBall client code has not had its original provenance or permissions independently established.

## Run the existing web application

From this directory:

```sh
npm ci --no-audit --no-fund
npm start
```

Create a production build with `npm run build`. The existing application uses Create React App and retains upstream's dependencies and behavior. Its `homepage` and deploy scripts still target upstream GitHub Pages; do not use `npm run deploy` to publish this local copy.

This import does not make the web app offline: it still references upstream WebSocket services and remote assets. Local engine extraction must remove these dependencies from the analysis path.

## Shared engine direction

The intended dependency flow is:

```text
standalone Node command -> shared analysis engine <- analyzer web app
                                 ^
                     replay bytes in, results out
```

Keep the engine independent of React, Redux, jQuery, DOM, audio, networking, and filesystem APIs. Input should be replay bytes; output should be plain data. Each analysis must own its state so multiple recordings can be analyzed independently. Supply callbacks or cancellation separately if needed.

Suggested extraction sequence:

1. Establish replay fixtures and expected core results from the existing implementation.
2. Extract the decoder, event registration, and deterministic replay tick loop from `src/game2.js`, retaining the original simulation behavior.
3. Move analysis state and callbacks into the shared module. Separate game boundaries and player identities explicitly. UI functions and no-op proxies must not become engine dependencies.
4. Expose the same engine through a Node command and a browser adapter. The web app can run analysis in a worker and pass its result to Redux; rendering and interactive playback remain separate concerns.
5. Define a versioned result schema, including available metrics and engine version, then connect Django/Celery to the standalone command.

The executable feasibility experiment and detailed integration findings are in `../.docs/research/replay-analysis/`. That experiment runs this pinned source directly under Node without npm dependencies:

```sh
node ../.docs/research/replay-analysis/proof.cjs . /path/to/recording.hbr2
```

The experiment patches source in memory and stubs UI callbacks. It demonstrates direct execution, but is not the future engine API or a production runner. It deliberately rejects a changed `game2.js` hash.

No engine extraction, browser integration, or Django task changes are included in this initial import.

## Import validation

Validated with Node v22.18.0 and npm 10.9.3:

- All 47 upstream tracked files match the hashes in `upstream.json`.
- `npm ci --no-audit --no-fund` succeeds without changing the lockfile.
- `npm run build` succeeds with upstream lint/CSS and outdated Browserslist warnings.
- The research Node harness processes the upstream Big-stadium sample against this vendored copy, producing one game with a 1–2 score and 18,375 active ticks.

The web app has not been exercised in a browser as part of this import.
