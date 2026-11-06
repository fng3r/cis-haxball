# Replay Lab

A local HaxBall replay analysis workspace built with React and Vite.

```sh
npm ci
npm run dev
```

Open **http://127.0.0.1:3000/analyzer/** and choose an `.hbr2` recording.

Use `npm run build` followed by `npm start` to serve the built app.

Run `npm test` for checks, `npm run build` for a static production build, or
`node scripts/analyze.mjs recording.hbr2` for standalone JSON analysis.

See [DEVELOPMENT.md](./DEVELOPMENT.md) for the shared engine API, architecture,
supported features and proof-of-concept limits. The original upstream application
is preserved in [legacy/](./legacy/README.md); its provenance is in
[upstream.json](./upstream.json).
