# Django / Replay Analyzer integration

Production serves Django at `https://cis-haxball.ru` and the static analyzer at
`https://cis-haxball.ru/analyzer/`. Requests are same-origin; there is no separate
statistics API service, CORS requirement, or Vite dependency in production.

The match-page link supplies an absolute Django manifest URL:

```text
/analyzer/?context=<encoded absolute Django manifest URL>
```

The manifest describes the whole match: competition hierarchy and official score,
home/away teams and logos, all associated supported recordings, and saved match
parts with labels, order, inclusion, engine game IDs and team-side mappings.
For a match in a series, `match.series` supplies its ID and `matchNumber`, using
the same ascending match-ID order as the Django match page. The header appends
that number to the tour, e.g. `Финал (2 матч)`.
An individual part link adds `part=<persistent ReplayMatchPart ID>` but still
loads the whole match. Recording bytes are fetched separately through bounded
Django endpoints, then analyzed using the existing original-engine worker library.
Neither the original engine nor native playback/checkpoint/chat code is modified.

The analyzer is **read-only** with respect to Django. There are no mapping-save
endpoints, editor controls, or credential-bearing cross-origin requests. Local
playback, seeking and selection do not modify Django. Excluded games remain in
the recording and can be reached through native playback, but do not appear as
included match parts or contribute to the Django match totals. The analyzer does
not infer or override the team mappings supplied by Django.

## Current domain models

Legacy `MatchReplay*` models and their stored results remain independent.

- `ReplayRecording`: match/source identity, source URL, raw response, file and
  response SHA-256, engine implementation revision, schema version, status/error,
  and analysis time. Canonical source host + replay ID deduplicates URL variants.
- `ReplayGame`: recording + engine game ID is its unique identity. Start tick is
  playback metadata, not identity. Also stores stadium, active ticks and whether
  the game exists in the latest successful analysis.
- `ReplayMatchPart`: persistent match-to-game association. Celery supplies order,
  label and side inference. Optional admin overrides replace generated values;
  `included=False` retains the association and prevents automatic resurrection.
- `ReplayTeamStats`: one row per game/red-or-blue side, with captured goals,
  possession ticks, kicks, completed passes, on-target shots and territory ticks.
- `ReplayPlayerStats`: one row per game/replay player identity (including side),
  with recorded nickname, optional resolved Django player and supported metrics.

Raw goals, event locations and maps remain in the raw engine response. Domain
models do not invent xG, ratings, saves, pass attempts or other unavailable data.
The established match statistics components render current metrics through a
presentation adapter. Current statistics are shown automatically when usable;
legacy statistics are a fallback when current results are unavailable. There is
no source selector, and query parameters cannot override this choice. Both sources
use the same pending, failed and partial-result UI; their metrics are never combined.

## Ingestion and editing

The existing match replay-list signal schedules Celery after transaction commit.
A normal run reuses successful analyses; new/failed recordings are analyzed.
Removed sources retain their stored data and part corrections, but cease to
contribute to the active match. Re-adding a source reuses the same identities.
Generated order follows the replay list and game IDs; explicit overrides survive.
After all recording updates, the shared match-level relevance evaluator classifies
all available games across currently attached recordings, including cached results.
Strong roster problems and short extra games beside two full halves are excluded;
ambiguous partial games, continuations and possible golden-goal overtime remain
included. Score differences never exclude a game. Raw and domain statistics for
excluded games remain stored, while existing presentation/aggregation excludes them.

`ReplayMatchPart.auto_included` stores the automatic decision; `included_override`
is a nullable manual correction and `included` is the effective persisted value.
`exclusion_reason` contains a readable explanation when effectively excluded,
including manual exclusion, and is empty when included. Admin shows the reason
and automatic decision read-only. Changing the inclusion checkbox pins a manual
override; clearing “Учитывать (исправление)” to “Неизвестно” resumes automatic
classification immediately. Reanalysis preserves overrides, labels and order.

Existing current-model parts initially have `auto_included=NULL`. On their first
classification, saved decisions differing from the former short-scoreless filter
are preserved as overrides; unchanged old defaults adopt the new policy. There
was no provenance for decisions equal to the old default. Set an explicit override
before processing if such a value must be pinned. Legacy `MatchReplay*` rows are
not classified or changed. `REPLAY_REQUIRED_PLAYERS` defaults to 4; other competition
formats require the matching Django setting. No bulk classification runs on migration;
the next ordinary ingestion classifies cached recordings without running the engine.

Team recognition uses actual match participants and nickname history separately
for every game. Unambiguous roster evidence can reverse sides. Missing or
conflicting evidence falls back to **home=red, away=blue**, following competition
rules. Admin overrides take precedence. Player associations use unique match
roster aliases; ambiguous aliases are not attached to arbitrary accounts.

Admin's tournament application index groups current replay models under
“Реплеи и статистика” and legacy entries separately. Generated statistic fields are read-only, but all replay models can be deleted
with the usual admin permissions. Deleting a recording or game cascades to its
parts and statistics. Match parts support rare corrections to inclusion, label,
order and side mapping, including changelist editing; normal admin history records
these changes. Exclusion survives rebuilding; deletion can be recreated by ingestion.

Explicit reanalysis is available through “Повторно проанализировать выбранные
записи” in the recordings admin, or:

```sh
python manage.py build_match_stats --match-ids 6862 6867 --reanalyze
```

Reanalysis **always invokes the engine**, even for identical file bytes. Changed
output replaces raw and extracted statistics atomically; editorial part records
keep their IDs and corrections. A failed run keeps the previous successful raw
response and derived metrics, recording the failure separately. Disappeared games
are marked unavailable and flagged for review, retaining their part records.
Changed recording bytes are rejected for review instead of silently reusing game
mappings for different content. Recording source corrections should use the correct
immutable host recording ID. Normal retries and reanalysis serialize with admin
part edits using a match lock. Separate matches can run on separate workers.

## Runtime and deployment

Celery needs Node >=22.12, the analyzer source and installed npm dependencies.
It invokes `scripts/analyze.mjs` as a bounded subprocess, independent of Vite.
Deploy `npm run build`'s `dist/` under `/analyzer/` and deploy matching source and
npm dependencies to the Celery host. Restart Django/Celery with the updated code
after migrating; no automatic production backfill is performed.

Django migrations are intentionally generated locally in this repository.
Before applying schema changes, run:

```sh
cd haxball_site
python manage.py makemigrations tournament
python manage.py migrate
```

These are ordinary Django schema migrations for the five current `Replay*` models.
There is no transitional data-transfer command. The legacy `MatchReplay*` tables
are never transformed or backfilled. For a fresh checkout also generate the other
applications' migrations following the repository's existing setup instructions.

Configuration:

- `REPLAY_ANALYZER_NODE`: Node executable, default `node`. Set an absolute nvm
  path or the Celery service PATH when required.
- `REPLAY_ANALYZER_CLI`: CLI path, default `<repo>/analyzer/scripts/analyze.mjs`.
- `REPLAY_ANALYZER_TIMEOUT`: subprocess timeout, default 120 seconds; V8 heap cap
  is 512 MiB. The unchanged engine enforces its size/format/duration limits.
- `REPLAY_ANALYZER_URL`: analyzer base URL. Defaults to `/analyzer/` (with Django
  URL prefix) in production and `http://localhost:3000/analyzer/` with DEBUG.
- `REPLAY_ANALYZER_ORIGINS`: optional comma-separated origins permitted to read
  public manifests/recordings. Defaults to localhost/127.0.0.1 port 3000 in DEBUG,
  empty in production. An absolute configured analyzer URL also permits its origin.

Only local development typically crosses origins: Django on its development port
and Vite on port 3000. The explicit manifest URL targets Django directly, and the
small origin allowlist permits public reads without cookies. Relative URLs are
resolved against the manifest's Django origin. Production uses ordinary same-origin
requests. Binary downloads still use fixed allowlisted replay hosts, validated
IDs, no redirects, timeout/32 MiB limits and HBR2-header checks; GET endpoints
cannot proxy arbitrary supplied URLs or write match data.

## Checks

```sh
cd analyzer && npm ci && npm test && npm run build
cd ../haxball_site
python manage.py test tournament.test_replay_integration
```

Django tests require PostgreSQL, generated migrations and analyzer dependencies.
They invoke the original CLI on the real multi-game fixture, check normalization,
legacy preservation, automatic recognition/defaults, explicit reanalysis with
changed output for identical input, editorial preservation, unavailable games,
atomic failure, URL deduplication/removal/re-addition, public read-only manifests,
scoped CORS, existing statistics components and admin editing/grouping.
Analyzer tests cover a distinct Django origin, binary downloads, standalone use,
multiple recordings, game-ID selection, part order/exclusion, and team/logo mapping.

## Experimental replay relevance audit

`audit_replay_games` evaluates all stored original-engine games across a match's
currently attached recordings using the same evaluator as Celery ingestion. The
audit command does **not** change saved parts, raw results or statistics. It performs no downloads/reanalysis and
enforces a PostgreSQL repeatable-read, read-only transaction. Run against a local
database with existing replay analyses:

```sh
cd haxball_site
python manage.py audit_replay_games --season-id 30 --output /tmp/replay-audit-chr17
python manage.py test tournament.test_replay_audit
```

The command writes a Markdown review report and a complete JSON evidence snapshot.
The season ID is explicit; 30 is ЧР #17 in the development snapshot. Only played
matches are assessed. `--required-players` defaults to 4; use the competition's
format, not the stadium filename, for other seasons. Current rules and thresholds
are documented in the generated report, including roster mismatches, possible
split halves, technical results and score differences that never cause exclusion.
Missing native clock offsets and overtime rules limit automatic classification;
ambiguous short parts remain available for review. Inclusion differences are
suggestions, since saved values may be deliberate manual corrections.

The initial [ЧР #17 report](../docs/reports/replay-audit-chr17.md) records the actual
development-database findings and subsequent user confirmations. It is a consistency
check, not an accuracy estimate. The audit itself requires no extra schema beyond
the current ingestion models; generate/apply ordinary migrations for the relevance
fields before running updated Django/Celery code.
