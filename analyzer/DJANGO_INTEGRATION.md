# Django integration (original engine)

The Django match page links to `/analyzer/?match=<id>`. The static analyzer fetches
`/championship/match/<id>/analyzer` from its own origin, then downloads the real
recordings using the URLs in that manifest. With a Django URL prefix, serve the
analyzer beneath that same prefix. Standalone file/link uploads still work.
The manifest is bounded to the first 32 match recording links. The existing
Powtorki/thehax, VK-wrapped and Saviola formats are accepted by Django. Unsupported
hosts never become arbitrary download targets; redirects are rejected, IDs are
validated, downloads have time/32 MiB limits, and HBR2 headers are checked.

## Runtime and deployment

Celery invokes `scripts/analyze.mjs` in a subprocess, using `src/engine/` only.
It needs Node >=22.12 and the analyzer's installed npm dependencies; a Vite server
is not needed for analysis. Deploy the analyzer source and its dependencies to
the Celery host as well as deploying `npm run build`'s `dist/` to `/analyzer/`.
Django and the static analyzer must share an origin for session/CSRF handling.
A separate Vite development origin needs a reverse proxy for `/championship/`;
there is deliberately no production stats service or permissive CORS endpoint.

Django environment variables:

- `REPLAY_ANALYZER_URL`: static UI path, default `/analyzer/` (including the configured Django URL prefix).
- `REPLAY_ANALYZER_NODE`: Node executable; default `node`. With nvm/systemd, use
  its absolute executable path or set the Celery service PATH.
- `REPLAY_ANALYZER_CLI`: absolute CLI path; default `<repo>/analyzer/scripts/analyze.mjs`.
- `REPLAY_ANALYZER_TIMEOUT`: subprocess timeout in seconds; default 120.

The subprocess has a 512 MiB V8 heap cap. The unchanged engine enforces format,
compressed/decompressed size and recording-duration limits. Errors/timeouts are
stored on the local analysis and can be retried using the existing ingestion
command. Successful results are reused; repeating a request does not duplicate
games or overwrite saved mappings. A match lock serializes imports and mapping
changes. Separate matches can be analyzed by separate Celery workers.

## Storage and migration

`LocalReplayAnalysis` is independent of `MatchReplay`, `MatchReplayStats` and
`MatchReplayStatsPlayer`. Its `result` contains the original engine's native
schemaVersion 1 output (including all games, players, maps and goals), with
`engine_version`, content SHA-256, status and errors alongside it. No legacy
column is reused for an incompatible metric. Legacy raw responses, rows,
aggregates and existing display are retained; the match page displays local
statistics in a separate section. Removed links retain their local results as an archive, but only current match recordings enter local totals. Alternate links to the same host/recording ID are deduplicated.

This repository intentionally does not version Django migrations. On each
installation, follow the existing workflow before starting updated workers:

```sh
cd haxball_site
python manage.py makemigrations tournament
python manage.py migrate
```

The generated migration **only creates LocalReplayAnalysis** (and its unique
match/URL constraint). It does not change or migrate legacy tables. There is no
automatic import/backfill. Match replay edits schedule local ingestion through
the existing signal/task entry point. To explicitly ingest selected matches:

```sh
python manage.py build_match_stats --match-ids 6862 6867
```

`--season` uses the database's season **number**, not its display label or PK;
ЧР #17 is number 25 / PK 30 in the current dev database. The legacy task remains
available under `fetch_legacy_match_replay_stats`; existing legacy polling is
left intact. All newly scheduled default ingestion uses the local engine.

## Sides and permissions

Inference uses the actual match participants and nickname history, independently
for each game. Missing, ambiguous or conflicting evidence leaves the mapping
unresolved. Substitutions contribute evidence; between-game side swaps are
resolved independently. A within-game team-side change makes whole-game
attribution ambiguous, so that game stays neutral unless an editor explicitly
resolves it. Every unresolved game and player metric remains stored and visible
under Red/Blue; only its team-attributed aggregate is withheld.

Editors with `tournament.change_localreplayanalysis` can save a per-game mapping
from the analyzer (after the match has been ingested in Django). The endpoint is
POST-only, uses normal Django CSRF protection, validates the game index and
records the editor and timestamp. Choosing Unresolved explicitly persists null.
Manual overrides take precedence on every subsequent import and rendering.
The local admin shows results and mapping audit read-only. Grant the new model
permission explicitly to existing editor groups as appropriate.

The outer scoreboard shows teams/logos in replay red/blue order, while the
context card keeps home/away identity and official score separate. Back-to-match
and competition breadcrumbs are available without changing the native player.
The engine and native player/checkpoint/chat implementation are untouched.

## Verification

```sh
cd analyzer && npm ci && npm test && npm run build
cd ../haxball_site
python manage.py test tournament.test_replay_integration
```

Django tests require PostgreSQL, generated repository migrations and installed
analyzer dependencies. They invoke the original CLI on the real multi-game
fixture and cover independent storage, idempotency, preservation of legacy rows,
side swaps/substitutions/uncertainty, persisted overrides, CSRF/permissions,
match-scoped binary downloads, failures and retries.
