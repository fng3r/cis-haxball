"""Offline relevance experiment. No ingestion, downloads or database updates."""

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from tournament.models import Match, Season
from tournament.replay_stats_client import get_replay_source_and_id
from tournament.services.local_replays import recording_sources
from tournament.services.replay_audit import evaluate_match
from tournament.services.replay_rosters import player_aliases, protocol_players


def audit_match(match, aliases, required_players):
    sources = list(recording_sources(match))
    recordings = {r.source_key: r for r in match.replay_recordings.all()}
    parts = {p.game_id: p for p in match.replay_parts.all()}
    games = []
    missing = []
    seen_hashes = set()
    duplicate_recording = False
    for ordinal, (key, url) in enumerate(sources, 1):
        recording = recordings.get(key)
        if not recording or not recording.raw_response:
            missing.append({'source': key, 'reason': 'not_analyzed'})
            continue
        if recording.status != 'ready':
            missing.append({'source': key, 'reason': recording.status})
        if recording.content_sha256:
            duplicate_recording |= recording.content_sha256 in seen_hashes
            seen_hashes.add(recording.content_sha256)
        stored_games = {g.engine_game_id: g for g in recording.games.all() if g.available}
        for raw in sorted(recording.raw_response['games'], key=lambda g: g['id']):
            stored_game = stored_games.get(raw['id'])
            part = parts.get(stored_game.pk) if stored_game else None
            games.append(
                {
                    'raw': raw,
                    'recording_id': recording.pk,
                    'recording_number': ordinal,
                    'game_id': raw['id'],
                    'part_id': part.pk if part else None,
                    'label': part.label if part else '',
                    'saved_included': part.included if part else None,
                    'included_override': part.included_override if part else None,
                    'red_is_home_override': part.red_is_home_override if part else None,
                    'source_url': url,
                }
            )
    result = evaluate_match(
        games,
        protocol_players(match),
        aliases,
        playoff=bool(match.stage and match.stage.type == 'PO'),
        duration_seconds=match.duration.total_seconds(),
        required_players=required_players,
    )
    if missing:
        result['issues'].append('missing_or_failed_recordings')
    if duplicate_recording:
        result['issues'].append('duplicate_recording_content')
    if any(not get_replay_source_and_id(url) for url in match.replays):
        result['issues'].append('unsupported_recording_links')
    if not match.replays:
        result['issues'].append('no_recordings_attached')
    technical = hasattr(match, 'result') and match.result.value in {'HDW', 'ADW', 'MTD'}
    if technical:
        # A technical result is not expected to match recorded goals or have recordings.
        result['issues'] = [issue for issue in result['issues'] if issue in {'missing_or_failed_recordings'}]
    if not technical and result['window_score'] != [match.score_home, match.score_guest]:
        result['issues'].append('score_difference_review_only')
    for game in result['games']:
        if game['saved_included'] is not None and game['saved_included'] != (game['recommendation'] != 'exclude'):
            game['reasons'].append('differs_from_saved_inclusion')
    return {
        'match_id': match.pk,
        'url': settings.BASE_URL.rstrip('/') + match.get_absolute_url(),
        'teams': [match.team_home.title, match.team_guest.title],
        'league': match.league.title,
        'tour': str(match.numb_tour),
        'playoff': bool(match.stage and match.stage.type == 'PO'),
        'official_score': [match.score_home, match.score_guest],
        'technical_result': technical,
        'duration_seconds': match.duration.total_seconds(),
        'missing_recordings': missing,
        'recording_count': len(sources),
        **result,
    }


def clock(seconds):
    seconds = round(seconds)
    return f'{seconds // 60}:{seconds % 60:02}'


def escape(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')


def needs_review(match):
    return bool(match['issues']) or any(
        g['recommendation'] == 'review'
        or g['saved_included'] is None
        or g['saved_included'] != (g['recommendation'] != 'exclude')
        or set(g['reasons']) & {'conflicting_side_evidence', 'mostly_unresolved_nicknames', 'short_of_eight_minutes'}
        for g in match['games']
    )


def review_notes(match):
    notes = []
    if any(g['recommendation'] == 'exclude' and g['saved_included'] is True for g in match['games']):
        notes.append('Review the newly proposed exclusion below against the surrounding regulation candidates.')
    if 'recorded_time_short_of_match_duration' in match['issues']:
        notes.append(
            'The retained recorded play is shorter than the match duration. Check for a missing recording '
            'or a recording started mid-half; retain the short game until its role is established.'
        )
    if 'score_difference_review_only' in match['issues']:
        delta = [
            recorded - official
            for recorded, official in zip(
                match['window_score'],
                match['official_score'],
                strict=True,
            )
        ]
        if delta[0] == delta[1] and delta[0] > 0:
            notes.append(
                f'Both teams have {delta[0]} extra replay goal(s). This is consistent with a fair-play '
                'exchange, but requires confirmation. Keep the games; do not force the replay score to match.'
            )
    return notes


def render_report(report):
    matches = report['matches']
    games = [g for m in matches for g in m['games']]
    suspicious = [m for m in matches if needs_review(m)]
    counts = Counter(g['recommendation'] for g in games)
    changed = [
        (m, g) for m in matches for g in m['games'] if g['recommendation'] == 'exclude' and g['saved_included'] is True
    ]
    major_mismatches = sum(g['roster']['major_mismatch'] for g in games)
    lines = [
        f'# Replay relevance audit — {report["season"]}',
        '',
        f'Snapshot: {report["generated_at"]}. Heuristic: `{report["heuristic"]}`. '
        '**Read-only; no saved decisions changed.**',
        '',
        f'{len(matches)} played matches, {sum(m["recording_count"] for m in matches)} supported recording links, '
        f'{len(games)} analyzed games. {len(suspicious)} matches need review; {len(matches) - len(suspicious)} '
        'have no outstanding flags (including already-excluded restarts and expected technical-result gaps).',
        '',
        f'Proposals: {counts["retain"]} retain, {counts["exclude"]} exclusion candidates, '
        f'{counts["review"]} retain pending review.',
        '',
        f'**{len(changed)} newly proposed exclusions**; the remaining exclusion candidates already match saved '
        'decisions. Review these first:',
        '',
        *[
            f'- Match [{m["match_id"]}]({m["url"]}), R{g["recording_number"]}/G{g["game_id"] + 1}, '
            f'part ID {g["part_id"]}: {g["seconds"]:.2f}s, red/blue score {g["score"][0]}:{g["score"][1]}. '
            f'Evidence: {", ".join(g["reasons"])}.'
            for m, g in changed
        ],
        '',
        f'Observed major protocol mismatches: {major_mismatches}. That branch, split-half cases and golden-goal '
        'overtime are covered by synthetic tests but need real examples before claiming validation.',
        '',
        '## How to read this experiment',
        '',
        '- Exclusion is a recommendation, never an applied edit. Raw results and historical data are untouched.',
        '- R/B counts are distinct active players over the entire game, including substitutions. Known aliases '
        'are deduplicated; spectators are ignored. This run assumes 4v4.',
        '- Fewer than four on either side is strong evidence. A major protocol mismatch requires a complete '
        'protocol (≥4 per team), ≥4 confidently identified outsiders and outsiders exceeding half the roster '
        'or occupying ≥75% of one side. '
        'Unknown/ambiguous nicknames are not outsiders.',
        '- Games ≥7:30 are potential full parts (recognition tolerance). The first two are regulation candidates. '
        'Extra games <4:00 beside two full halves are restart candidates, including scored warmups. '
        'Short games after regulation in playoffs remain under review for golden goals.',
        '- When two full halves are absent, adjacent groups of 2–4 shorter games totaling 8:00±15s are possible '
        'continuations, retained for review. Missing halves never justify including an obviously unrelated game.',
        '- Only goal events through 8:00 per retained game enter the diagnostic score. Later goals do not. '
        'Fair-play goals can still differ from the report. Score mismatch requests review, never exclusion.',
        '- Source-list order is provisional across recordings. No native clock-offset/end-reason metadata is '
        'available in the stored export; continuation and golden-goal classification remain tentative. '
        'The score for split halves is also tentative because the eight-minute boundary spans segments.',
        '- Saved inclusion is shown separately: it may be a deliberate correction. No training labels or '
        'manual ground truth exist yet, so this is a consistency audit, not a measured accuracy claim.',
        '- Technical results are exempt from score/coverage checks. Confirmed exclusions already matching saved '
        'decisions are listed in the exclusion appendix, not counted as outstanding review cases.',
        '',
        '## Review index',
        '',
        '| Match | Competition / tour | Official | Through 8:00¹ | Review reasons |',
        '|---|---|---|---|---|',
    ]
    for m in suspicious:
        game_reasons = {reason for g in m['games'] for reason in g['reasons']}
        reasons = sorted(set(m['issues']) | game_reasons)
        lines.append(
            f'| [{m["match_id"]}]({m["url"]}) {escape(" — ".join(m["teams"]))} '
            f'| {escape(m["league"])} / {escape(m["tour"])} '
            f'| {m["official_score"][0]}:{m["official_score"][1]} '
            f'| {m["window_score"][0]}:{m["window_score"][1]} | {", ".join(reasons)} |'
        )
    lines.extend(
        [
            '',
            '¹ Diagnostic only; source order, side mapping, continuations, fair-play and overtime need review.',
            '',
            '## Game-by-game evidence for flagged matches',
            '',
        ]
    )
    for m in suspicious:
        lines.extend(
            [
                f'### Match {m["match_id"]}: {" — ".join(m["teams"])}',
                '',
                f'[Open match]({m["url"]}). Official {m["official_score"][0]}:{m["official_score"][1]}, '
                f'duration {clock(m["duration_seconds"])}. Issues: {", ".join(m["issues"]) or "game-level only"}.',
                '',
                *[note + '\n' for note in review_notes(m)],
                '| Recording / game² / part ID | Saved label; included | Active | R:B | Players R/B | Matched; '
                'outsiders; unknown | Proposal / role | Evidence |',
                '|---|---|---|---|---|---|---|---|',
            ]
        )
        roster_notes = []
        for g in m['games']:
            sides = g['roster']['sides']
            lines.append(
                f'| [R{g["recording_number"]} / G{g["game_id"] + 1}]({g["source_url"]}) / '
                f'{g["part_id"]} | {escape(g["label"])}; {g["saved_included"]} '
                f'| {clock(g["seconds"])} | {g["score"][0]}:{g["score"][1]} '
                f'| {sides["red"]["total"]}/{sides["blue"]["total"]} '
                f'| {g["roster"]["matched"]}; {sum(s["outside"] for s in sides.values())}; {g["roster"]["unknown"]} '
                f'| {g["recommendation"]} / {g["role"]} | {", ".join(g["reasons"]) or "—"} |'
            )
            if g['roster']['major_mismatch'] or 'mostly_unresolved_nicknames' in g['reasons']:
                for side, evidence in sides.items():
                    matched_names = evidence['names']['home'] + evidence['names']['away']
                    roster_notes.append(
                        f'R{g["recording_number"]}/G{g["game_id"] + 1} {side}: '
                        f'protocol {escape(", ".join(matched_names)) or "—"}; '
                        f'outsiders {escape(", ".join(evidence["names"]["outside"])) or "—"}; '
                        f'unknown {escape(", ".join(evidence["names"]["unknown"])) or "—"}.\n'
                    )
        lines.extend(['', *roster_notes, ''])
    lines.extend(
        [
            '## All exclusion candidates',
            '',
            '| Match | Recording / game / part ID | Active | R:B | Currently included | Evidence |',
            '|---|---|---|---|---|---|',
        ]
    )
    for m in matches:
        for g in m['games']:
            if g['recommendation'] == 'exclude':
                lines.append(
                    f'| [{m["match_id"]}]({m["url"]}) | R{g["recording_number"]}/G{g["game_id"] + 1} '
                    f'/ {g["part_id"]} | {clock(g["seconds"])} | {g["score"][0]}:{g["score"][1]} '
                    f'| {g["saved_included"]} | {", ".join(g["reasons"])} |'
                )
    lines.append('')
    lines.extend(['² G is one-based for review; JSON `game_id` is the engine’s zero-based identifier.', ''])
    return '\n'.join(lines)


class Command(BaseCommand):
    help = 'Read-only relevance audit of stored replay results; writes Markdown and JSON, never changes inclusion.'

    def add_arguments(self, parser):
        parser.add_argument('--season-id', type=int, required=True)
        parser.add_argument('--required-players', type=int, default=4)
        parser.add_argument('--output', type=Path, required=True, help='Output filename prefix (without extension)')

    def handle(self, *args, **options):
        if options['required_players'] < 1:
            raise CommandError('--required-players must be positive')
        # Enforced by PostgreSQL, including any accidental writes in called helpers.
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            season = Season.objects.get(pk=options['season_id'])
            aliases = player_aliases()
            matches = (
                Match.objects.filter(league__championship=season, is_played=True)
                .select_related(
                    'league',
                    'stage',
                    'numb_tour',
                    'team_home',
                    'team_guest',
                    'result',
                )
                .prefetch_related('replay_recordings__games', 'replay_parts', 'match_substitutions')
                .order_by('pk')
            )
            report = {
                'heuristic': 'experimental-v1',
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'season': season.title,
                'season_id': season.pk,
                'required_players': options['required_players'],
                'matches': [audit_match(m, aliases, options['required_players']) for m in matches],
            }
        prefix = options['output']
        prefix.parent.mkdir(parents=True, exist_ok=True)
        prefix.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        prefix.with_suffix('.md').write_text(render_report(report))
        self.stdout.write(f'Read-only audit complete: {prefix.with_suffix(".md")} and {prefix.with_suffix(".json")}')
