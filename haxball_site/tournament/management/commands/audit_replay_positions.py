"""Compare local position inference with saved legacy labels, without changing the database."""

import hashlib
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from tournament.local_replay_analyzer import analyze_local_replay, engine_revision
from tournament.models import MatchReplay, Season
from tournament.replay_stats_client import download_replay


def cohort(recording_id):
    # Stable split: tuning a classifier must not move examples into the holdout.
    return (
        'calibration' if int(hashlib.sha256(str(recording_id).encode()).hexdigest()[:8], 16) % 5 == 0 else 'validation'
    )


def roster(players):
    return {(p['nick'].strip(), p['team']) for p in players if p.get('ticks', 0) > 0}


def compare_games(legacy, current):
    """Never match a saved part to a new game merely by its ordinal or score."""
    rows, skipped, used = [], [], set()
    for index, old in enumerate(legacy):
        references = [
            {'nick': p['nick'], 'team': p.get('team'), **(p.get('metrics') or {})}
            for p in old.get('players', [])
            if (p.get('metrics') or {}).get('position') in {'GK', 'DM', 'AM', 'ST', 'LW', 'RW'}
            and (p.get('metrics') or {}).get('playedTicks', 0) > 0
        ]
        old_roster = roster([{**p, 'ticks': p.get('playedTicks', 0)} for p in references])
        candidates = [
            g
            for g in current['games']
            if g['id'] not in used
            and [g['scoreRed'], g['scoreBlue']] == [old.get('scoreRed'), old.get('scoreBlue')]
            and abs(g['gameTicks'] - old.get('gameTicks', 0)) <= 60
            and old_roster
            and old_roster <= roster([{**p, 'ticks': p['playedTicks']} for p in g['players']])
        ]
        if len(candidates) != 1:
            skipped.append(
                {'legacy_index': index, 'reason': 'ambiguous_or_incompatible_game', 'candidates': len(candidates)}
            )
            continue
        game = candidates[0]
        used.add(game['id'])
        for old_player in references:
            players = [
                p
                for p in game['players']
                if p['nick'].strip() == old_player['nick'].strip() and p['team'] == old_player['team']
            ]
            if len(players) != 1:
                skipped.append(
                    {'legacy_index': index, 'nick': old_player['nick'], 'reason': 'ambiguous_player_identity'}
                )
                continue
            player = players[0]
            rows.append(
                {
                    'game_id': game['id'],
                    'stadium': game['stadium']['name'],
                    'nick': player['nick'],
                    'side': player['team'],
                    'ticks': player['playedTicks'],
                    'legacy_position': old_player['position'],
                    'position': player['position'],
                    'confidence': player['positionConfidence'],
                    'roles': player['positionRoles'],
                }
            )
    return rows, skipped


def summarize(rows):
    classified = [r for r in rows if r['position']]

    # The old engine frequently called one of two futsal forwards AM. Report
    # exact labels AND broader roles, without hiding that semantic disagreement.
    def family(position):
        return 'attack' if position in {'AM', 'ST', 'LW', 'RW'} else position

    return {
        'players': len(rows),
        'classified': len(classified),
        'exact_agreement': sum(r['position'] == r['legacy_position'] for r in rows),
        'role_family_agreement': sum(family(r['position']) == family(r['legacy_position']) for r in rows),
        'confusion': dict(
            sorted(Counter(f'{r["legacy_position"]}->{r["position"] or "unknown"}' for r in rows).items())
        ),
    }


class Command(BaseCommand):
    help = 'Read-only replay position comparison against legacy data; downloads replays into an explicit local cache.'

    def add_arguments(self, parser):
        parser.add_argument('--season', type=int, required=True, help='Season primary key, not displayed season number')
        parser.add_argument('--cohort', choices=['calibration', 'validation', 'all'], default='validation')
        parser.add_argument('--limit', type=int, default=40, help='Stratified recording sample; 0 means all')
        parser.add_argument('--cache-dir', type=Path, required=True)
        parser.add_argument('--output', type=Path, required=True)
        parser.add_argument('--workers', type=int, default=4)

    def handle(self, *args, **options):
        season = Season.objects.get(pk=options['season'])
        if options['limit'] < 0 or not 1 <= options['workers'] <= 8:
            raise CommandError('Use a nonnegative limit and 1–8 workers')
        cache = options['cache_dir']
        cache.mkdir(parents=True, exist_ok=True)
        recordings = list(MatchReplay.objects.filter(match__league__championship=season).exclude(raw_stats_json=[]))
        recordings = [r for r in recordings if options['cohort'] == 'all' or cohort(r.pk) == options['cohort']]
        # Alternate futsal/BFF groups; order each by a stable hash instead of only
        # taking early-season matches. No expected labels influence sampling.
        groups = {}
        for recording in recordings:
            group = (
                'bff' if any('bff' in g.get('stadiumName', '').lower() for g in recording.raw_stats_json) else 'other'
            )
            groups.setdefault(group, []).append(recording)
        for group in groups.values():
            group.sort(key=lambda r: hashlib.sha256(str(r.pk).encode()).hexdigest())
        sample = []
        while any(groups.values()):
            for group in groups.values():
                if group:
                    sample.append(group.pop(0))
        if options['limit']:
            sample = sample[: options['limit']]

        def evaluate(recording):
            try:
                path = cache / f'{recording.pk}.hbr2'
                if not path.exists():
                    data = download_replay(recording.replay_url)
                    if data is None:
                        raise ValueError('Unsupported replay source')
                    path.write_bytes(data)
                data = path.read_bytes()
                result = analyze_local_replay(data)
                rows, skipped = compare_games(recording.raw_stats_json, result)
                return {
                    'recording_id': recording.pk,
                    'match_id': recording.match_id,
                    'source': recording.replay_url,
                    'sha256': hashlib.sha256(data).hexdigest(),
                    'cohort': cohort(recording.pk),
                    'rows': rows,
                    'skipped': skipped,
                }
            except Exception as error:
                return {'recording_id': recording.pk, 'match_id': recording.match_id, 'error': str(error)}

        results = []
        with ThreadPoolExecutor(max_workers=options['workers']) as pool:
            for result in pool.map(evaluate, sample):
                results.append(result)
                self.stdout.write(
                    f'{len(results)}/{len(sample)} recording {result["recording_id"]}: '
                    f'{result.get("error", str(len(result["rows"])) + " players" if "rows" in result else "error")}'
                )
        rows = [row for result in results for row in result.get('rows', [])]
        report = {
            'season': str(season),
            'season_id': season.pk,
            'cohort': options['cohort'],
            'engine_revision': engine_revision(),
            'summary': summarize(rows),
            'recordings': results,
        }
        options['output'].parent.mkdir(parents=True, exist_ok=True)
        options['output'].write_text(json.dumps(report, ensure_ascii=False, indent=2))
        self.stdout.write(json.dumps(report['summary'], ensure_ascii=False))
