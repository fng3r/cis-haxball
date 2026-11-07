"""Local engine ingestion, identity resolution and presentation. No legacy writes."""

import hashlib

from django.db import transaction
from django.utils import timezone

from tournament.local_replay_analyzer import analyze_local_replay
from tournament.models import LocalReplayAnalysis, Match
from tournament.replay_stats_client import download_replay, get_replay_source_and_id

MAX_RECORDINGS = 32


def match_recordings(match):
    recordings, seen = [], set()
    for index, url in enumerate((match.replays or [])[:MAX_RECORDINGS]):
        source = get_replay_source_and_id(url)
        if source and source not in seen:
            recordings.append((index, url))
            seen.add(source)
    return recordings


def match_rosters(match):
    rosters = {'home': set(), 'away': set()}
    participants = dict(
        match.match_participants.through.objects.filter(match=match).values_list('player_id', 'team_id')
    )
    for player in match.match_participants.select_related('name'):
        team_id = participants.get(player.pk)
        if team_id not in {match.team_home_id, match.team_guest_id}:
            continue
        side = 'home' if team_id == match.team_home_id else 'away'
        rosters[side].add(player.nickname.strip().casefold())
        if player.name_id:
            rosters[side].update(
                n.strip().casefold()
                for n in player.name.usernicknamehistoryitem_set.values_list('nickname', flat=True)
                if n.strip()
            )
    return rosters


def infer_mapping(game, rosters):
    votes = set()
    for player in game['players']:
        if not player.get('playedTicks') or player.get('team') not in {'red', 'blue'}:
            continue
        nick = player['nick'].strip().casefold()
        home, away = nick in rosters['home'], nick in rosters['away']
        if home == away:
            continue
        votes.add(home == (player['team'] == 'red'))
    # Conflicting evidence includes within-game switches; do not assign a whole game's
    # red-side metrics to a team when its identity changes during that game.
    return votes.pop() if len(votes) == 1 else None


def ingest_match(match_id):
    match = Match.objects.filter(pk=match_id).first()
    if match is None:
        return {'error': 'Match not found', 'match_id': match_id}
    rosters = match_rosters(match)
    created, errors = 0, 0
    for _, url in match_recordings(match):
        # Hold a row lock across this bounded subprocess so retries cannot overwrite
        # successful results or race an editor's mapping. Distinct matches run independently.
        with transaction.atomic():
            Match.objects.select_for_update().get(pk=match.pk)
            analysis, _ = LocalReplayAnalysis.objects.get_or_create(match=match, replay_url=url)
            analysis = LocalReplayAnalysis.objects.select_for_update().get(pk=analysis.pk)
            if analysis.status == LocalReplayAnalysis.Status.READY and analysis.result:
                continue
            try:
                data = download_replay(url)
                result = analyze_local_replay(data)
                analysis.result = result
                analysis.inferred_sides = {
                    str(i): infer_mapping(game, rosters) for i, game in enumerate(result['games'])
                }
                analysis.content_sha256 = hashlib.sha256(data).hexdigest()
                analysis.status = LocalReplayAnalysis.Status.READY
                analysis.analyzed_at = timezone.now()
                analysis.error_message = ''
                created += len(result['games'])
            except Exception as exc:
                analysis.status = LocalReplayAnalysis.Status.FAILED
                analysis.error_message = f'{type(exc).__name__}: {exc}'[:2000]
                errors += 1
            analysis.save()
    return {'match_id': match_id, 'created_games': created, 'failed_recordings': errors}


def duration(ticks):
    minutes, seconds = divmod(round(ticks / 60), 60)
    return f'{minutes:02d}:{seconds:02d}'


def match_statistics(match):
    """Only supported metrics, with unresolved games retained outside team totals."""
    active_urls = [url for _, url in match_recordings(match)]
    games, analyses = [], list(match.local_replay_analyses.filter(replay_url__in=active_urls))
    totals = {'score': [0, 0], 'possession': [0, 0], 'kicks': [0, 0], 'passes': [0, 0], 'shots': [0, 0]}
    ticks = 0
    for analysis in analyses:
        for index, game in enumerate(analysis.result.get('games', [])):
            mapping = analysis.game_mapping(index)
            players = [{**p, 'playtime': duration(p['playedTicks'])} for p in game['players']]
            games.append(
                {
                    'analysis': analysis,
                    'index': index,
                    'game': game,
                    'players': players,
                    'red_is_home': mapping,
                    'duration': duration(game['gameTicks']),
                }
            )
            if mapping is None:
                continue
            ticks += game['gameTicks']
            values = {
                'score': [game['scoreRed'], game['scoreBlue']],
                **{key: game[key] for key in ('possession', 'kicks', 'passes', 'shots')},
            }
            for key, pair in values.items():
                pair = pair if mapping else pair[::-1]
                totals[key] = [sum(values) for values in zip(totals[key], pair)]
    possession = sum(totals['possession'])
    return {
        'analyses': analyses,
        'games': games,
        'duration': duration(ticks),
        'totals': totals,
        'possession_pct': [round(value / possession * 100) if possession else 0 for value in totals['possession']],
        'unresolved': sum(game['red_is_home'] is None for game in games),
    }
