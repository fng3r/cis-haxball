# Standalone HaxBall replay analysis

Analyze local HBR2 recordings without a browser or external analysis service.
The original upstream analyzer is preserved under `legacy/`.

```sh
npm ci
npm test
node scripts/analyze.mjs recording.hbr2 > stats.json
```

See [DEVELOPMENT.md](./DEVELOPMENT.md) for the API and extraction notes.
