# Replay admin performance

Measured on the development database on 2026-11-08 using rendered admin GET
responses with 20 rows per page. Baseline: `c69141f8`. No match or replay data was
changed during profiling. Times include database access, Python JSON decoding and
template rendering; these single-pass local measurements are indicative, not a
production latency guarantee. Query counts include fixed navigation/context queries.

| Admin model | Queries before | Queries after | Seconds before | Seconds after |
|---|---:|---:|---:|---:|
| ReplayRecording | 13 | 17 | 0.807 | 0.132 |
| ReplayGame | 13 | 18 | 1.134 | 0.041 |
| ReplayMatchPart | 16 | 20 | 0.719 | 0.074 |
| ReplayTeamStats | 11 | 17 | 0.704 | 0.039 |
| ReplayPlayerStats | 31 | 17 | 0.831 | 0.042 |
| MatchReplayStatsStatus | 13 | 17 | 0.075 | 0.041 |
| MatchReplay | 82 | 17 | 0.214 | 0.047 |
| MatchReplayStats | 102 | 18 | 0.206 | 0.050 |
| MatchReplayStatsPlayer | 160 | 27 | 0.147 | 0.081 |

Adding the new filters introduces a few fixed queries. This explains the higher
query counts on some already-bounded lists; eliminating large raw JSON transfers
is their main improvement. With 100 rows instead of 20, the optimized query counts
remain exactly the same for all nine lists.

## Causes and fixes

- Django's automatic `select_related()` followed every required FK through games,
  recordings and matches, loading large analyzer JSON repeatedly for each statistic
  row. Explicit joins now load only the relations needed for displayed labels;
  recording raw fields are deferred. Recording detail pages can still load them.
- Nullable player FKs were not automatically joined. The current player list now
  loads mapped players in the main query.
- Legacy statistics lists omitted match teams/tours needed by nested `__str__`
  calls. These are explicitly joined. The legacy player list additionally prefetches
  polymorphic tour stages and league stage collections so bracket/name formatting
  and `is_multistage_league()` do not issue queries per row.
- League dropdown labels called `League.__str__`, fetching each season separately
  (66 individual season queries in the baseline). The replay-specific dropdown
  joins seasons once; it does not change other applications' dropdown behavior.

## Filters

Every replay list, including the legacy models, supports season, league, stage
type, tour number and match ID. Additional filters are:

- Recordings/status rows: processing status and analysis/fetch date.
- Replay games: availability, recording status and stadium.
- Match parts: effective inclusion, automatic inclusion, manual override,
  mapping evidence and game availability.
- Team statistics: side, part inclusion and game availability.
- Player statistics: side, player autocomplete, resolved/unresolved identity
  and part inclusion. Legacy player statistics also offer team and position.
- Legacy match statistics: part label, side mapping and stadium.

Player/team selectors use autocomplete instead of eagerly rendering every account.
All existing admin edits, deletions, permissions and reanalysis actions remain.

## Regression checks

`python manage.py test tournament.test_replay_admin tournament.test_replay_integration`

The admin suite renders all nine lists with 1 and 20 rows and checks that query
counts do not grow with row count, raw payload columns are not selected, all
competition/match filters work, state filters return unique correct rows, raw
payloads remain accessible and league labels use one query across many choices.
