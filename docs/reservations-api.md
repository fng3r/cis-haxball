# Public broadcasting schedule

`GET https://cis-haxball.ru/api/reservations/?date=2026-11-13`

Django URL name: `reservations_api`. The relative path is `/api/reservations/`;
installations with `APP_URL_PREFIX` prepend that configured prefix, as for other
site routes. This is a public, read-only endpoint. No login, token or CORS setup
is required for a server-side consumer such as haxbotron.

Exactly one `date` parameter is required: ASCII `YYYY-MM-DD`, a real calendar
date between `0001-01-01` and `9999-12-30` inclusive (the next midnight must be
representable). Missing, empty, repeated, impossible or noncanonical dates return
HTTP 400, `application/json`, with `{"error": "Provide one valid date in YYYY-MM-DD format (before 9999-12-31)."}`.
Other methods return HTTP 405.

A successful response is HTTP 200, `application/json`:

```json
{
  "date": "2026-11-13",
  "timezone": "Europe/Moscow",
  "reservations": [
    {
      "id": 42,
      "startsAt": "2026-11-13T20:30:00+03:00",
      "host": {"codename": "room-ruid", "name": "Broadcast room"},
      "match": {
        "id": 123,
        "url": "https://cis-haxball.ru/championship/match/123",
        "season": {"id": 17, "name": "Season 17"},
        "league": {"id": 1, "name": "Premier league"},
        "stage": null,
        "group": null,
        "tour": {"id": 10, "name": "1 тур"},
        "series": null,
        "date": null,
        "officialScore": [0, 0],
        "isPlayed": false
      },
      "teams": {
        "home": {"id": 1, "name": "Home team", "shortName": "HOME", "logo": "https://cis-haxball.ru/media/team_logos/default.png"},
        "away": {"id": 2, "name": "Away team", "shortName": "AWAY", "logo": null}
      }
    }
  ]
}
```

`host.codename` maps **directly to haxbotron `room.ruid`**, never to a control
host ID. `startsAt` is ISO 8601 with the site's UTC offset. `timezone` is the
actual Django `TIME_ZONE` setting, currently `Europe/Moscow`. Match and logo URLs
are absolute public URLs based on `APP_BASE_URL`, production `https://cis-haxball.ru`.

Each entry's `match` and `teams` follow the analyzer manifest schemaVersion 2
context, inspected on the `analyzer` branch in `tournament/replay_integration.py`.
No recording or replay processing features are needed. The small reusable
`tournament.match_context.PublicMatchContext` helper serializes this context.
There are no `match.home`, `match.away` or `match.competition` aliases.

- All IDs are JSON numbers. `season`, `league`, `stage`, `group` and `tour` are
  `{id: number, name: string}` references or `null` when absent. Required model
  relations currently make `league` and `tour` always present.
- `stage` is shown only for leagues with multiple stages. Its name matches the
  analyzer's stage string (league title plus stage name).
- `tour.name` respects an explicit tour name, otherwise the regular tour or
  playoff round label, including third-place round handling.
- `series` is `{id: number, matchNumber: number}` only when the series contains
  multiple matches; numbering follows ascending match ID, just as in analyzer.
- `match.date` is the scheduled match calendar date (`YYYY-MM-DD`) or `null`;
  use reservation `startsAt` for broadcast timing. `officialScore` is the
  numeric home/away score pair; `isPlayed` is always false in this endpoint.
- `teams.home` and `teams.away` contain numeric `id`, string `name` and
  `shortName`, and absolute string `logo` or `null`.

The query covers `[local midnight, next local midnight)` in `TIME_ZONE`, even
when a request has another active timezone. It includes reservations earlier on
the requested date, including earlier today. Cancelled reservations, played
matches and inactive or missing hosts are excluded. Like the available
reservation list, it does not restrict by season activity. No author, canceller,
host control URL or other private user data is returned. An empty day returns
`reservations: []`.

Results are ordered by start time, then reservation ID. The main query uses
`select_related` and a bounded datetime range without a date cast; up to three
additional batch queries resolve stage counts, playoff round counts and series
numbering. Query count does not grow with the number of reservations.

## Verification

With normal development dependencies, environment and PostgreSQL configured:

```sh
cd haxball_site
python manage.py test reservation --settings=haxball_site.test_settings --noinput
python manage.py check
```

The test settings build all tables together without migrations, since this repo
tracks no app migrations. They use the separate `test_cis_haxball` database;
Django creates and destroys it. Tests cover the exact public schema, anonymous
access, validation, filtering, midnight and DST boundaries, earlier-today entries,
ordering, bounded query count, and analyzer stage/group/tour/series context.
