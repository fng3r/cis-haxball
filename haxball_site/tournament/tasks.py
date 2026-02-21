"""
Celery tasks for tournament app. fetch_match_replay_stats: pull replays from Powtorki,
upload to Haxball Analyzer, store raw response in MatchReplay; rebuild MatchReplayStats
and MatchReplayStatsPlayer from raw every run.
"""

from django.utils import timezone

from celery import shared_task

from tournament.models import (
    Match,
    MatchReplay,
    MatchReplayStats,
    MatchReplayStatsPlayer,
    MatchReplayStatsStatus,
    Player,
)
from tournament.replay_stats_client import (
    download_powtorki_replay,
    fetch_analyzer_stats,
    is_powtorki_url,
    upload_replay_to_analyzer,
)


def _resolve_player(match, nick: str, team: str, red_is_home: bool):
    """
    Resolve replay nick+team to our Player using stored mapping (red_is_home).
    Prefer players in team_home_start / team_guest_start.
    """
    team_obj = match.team_home if (team == 'red') == red_is_home else match.team_guest
    start_players = (
        list(match.team_home_start.all()) if team_obj.id == match.team_home_id else list(match.team_guest_start.all())
    )
    nick_normalized = (nick or '').strip()
    if not nick_normalized:
        return None
    for p in start_players:
        if (p.nickname or '').strip().lower() == nick_normalized.lower():
            return p
    return Player.objects.filter(team=team_obj, nickname__iexact=nick_normalized).first()


def _create_replay_stats_from_part(
    match_replay: MatchReplay,
    part_order: int,
    part_label: str,
    red_is_home: bool,
    stats_obj: dict,
):
    """Create one MatchReplayStats and related MatchReplayStatsPlayer from one API stats object."""
    match = match_replay.match
    red_team_nicks = stats_obj.get('redTeam') or []
    blue_team_nicks = stats_obj.get('blueTeam') or []
    player_ratings = stats_obj.get('playerRatings') or {}
    mvp_nick = (player_ratings.get('mvpNick') or '').strip()
    kicks_list = stats_obj.get('kicks') or []
    kicks_red = sum(1 for k in kicks_list if (k.get('team') or '').lower() == 'red')
    kicks_blue = sum(1 for k in kicks_list if (k.get('team') or '').lower() == 'blue')

    part = MatchReplayStats.objects.create(
        match=match,
        match_replay=match_replay,
        part_order=part_order,
        part_label=part_label,
        red_is_home=red_is_home,
        score_red=int(stats_obj.get('scoreRed') or 0),
        score_blue=int(stats_obj.get('scoreBlue') or 0),
        game_ticks=int(stats_obj.get('gameTicks') or 0),
        minutes=int(stats_obj.get('minutes') or 0),
        poss_red=int(stats_obj.get('possRed') or 0),
        poss_blue=int(stats_obj.get('possBlue') or 0),
        shots_red=int(stats_obj.get('shotsRed') or 0),
        shots_blue=int(stats_obj.get('shotsBlue') or 0),
        shots_off_target_red=int(stats_obj.get('shotsOffTargetRed') or 0),
        shots_off_target_blue=int(stats_obj.get('shotsOffTargetBlue') or 0),
        shots_total_red=int(stats_obj.get('shotsTotalRed') or 0),
        shots_total_blue=int(stats_obj.get('shotsTotalBlue') or 0),
        kicks_red=kicks_red,
        kicks_blue=kicks_blue,
        stadium_name=(stats_obj.get('stadiumName') or '')[:255],
        red_team_nicks=[str(n)[:150] for n in red_team_nicks],
        blue_team_nicks=[str(n)[:150] for n in blue_team_nicks],
        mvp_nick=mvp_nick[:150] if mvp_nick else '',
    )

    # Per-player (skip zero playtime and "*" own-goal placeholder)
    players_data = stats_obj.get('players') or []
    for p in players_data:
        nick = (p.get('nick') or p.get('name') or '').strip()[:150]
        if nick == '*' or not nick:
            continue
        team_key = (p.get('team') or '')[:10]
        metrics = p.get('metrics') or {}
        played_ticks = int(metrics.get('playedTicks') or p.get('playedTicks') or 0)
        if played_ticks == 0:
            continue
        rating_obj = p.get('rating') or {}
        rating = rating_obj.get('rating')
        if rating is not None:
            try:
                rating = float(rating)
            except (TypeError, ValueError):
                rating = None

        player = _resolve_player(match, nick, team_key, red_is_home) if nick and team_key else None
        team_obj = part.get_match_team_for_replay_side(team_key)

        MatchReplayStatsPlayer.objects.create(
            replay_stats=part,
            player=player,
            nick=nick,
            team=team_obj,
            goals=int(metrics.get('goals') or 0),
            assists=int(metrics.get('assists') or 0),
            played_ticks=played_ticks,
            rating=rating,
            shots_total=int(metrics.get('shotsTotal') or 0),
            shots_on_target=int(metrics.get('shotsOnTarget') or 0),
            shots_off_target=int(metrics.get('shotsOffTarget') or 0),
            passes_completed=int(metrics.get('passesCompleted') or 0),
            pass_attempts=int(metrics.get('passAttempts') or 0),
            pass_completion_rate=_float_or_none(metrics.get('passCompletionRate')),
            touches=int(metrics.get('touches') or 0),
            saves=int(metrics.get('saves') or 0),
            clearances=int(metrics.get('clearances') or 0),
            interceptions=int(metrics.get('interceptions') or 0),
            duel_wins=int(metrics.get('duelWins') or 0),
            duel_losses=int(metrics.get('duelLosses') or 0),
            xg=_float_or_none(metrics.get('xg')),
        )
    return part


def _float_or_none(x):
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


@shared_task
def fetch_match_replay_stats(match_id: int):
    """
    For a Match: cleanup stats for removed replays; for each replay URL that we don't
    have yet, download from Powtorki, upload to Haxball Analyzer, poll for stats,
    create MatchReplayStats + MatchReplayStatsPlayer. Update MatchReplayStatsStatus.
    """
    match = (
        Match.objects.filter(pk=match_id)
        .select_related('team_home', 'team_guest')
        .prefetch_related('team_home_start', 'team_guest_start')
        .first()
    )
    if not match:
        return {'error': 'Match not found', 'match_id': match_id}

    current_replay_urls = set(match.replays or [])

    # Ensure status exists and set pending
    status, _ = MatchReplayStatsStatus.objects.get_or_create(
        match=match,
        defaults={'status': MatchReplayStatsStatus.Status.PENDING},
    )
    status.status = MatchReplayStatsStatus.Status.PENDING
    status.save(update_fields=['status'])

    # Remove replays no longer in match.replays (CASCADE deletes their MatchReplayStats)
    MatchReplay.objects.filter(match=match).exclude(replay_url__in=current_replay_urls).delete()

    for url in match.replays or []:
        if not is_powtorki_url(url):
            continue
        match_replay = MatchReplay.objects.filter(match=match, replay_url=url).first()
        if match_replay and match_replay.raw_stats_json:
            stats_list = list(match_replay.raw_stats_json)
        else:
            try:
                replay_file = download_powtorki_replay(url)
                analyzer_id = upload_replay_to_analyzer(replay_file)
                stats_list = fetch_analyzer_stats(analyzer_id)
            except Exception:
                continue
            match_replay, _ = MatchReplay.objects.update_or_create(
                match=match,
                replay_url=url,
                defaults={
                    'analyzer_replay_id': analyzer_id,
                    'raw_stats_json': stats_list,
                    'fetched_at': timezone.now(),
                },
            )
        # Rebuild preprocessed parts from raw (every time task runs)
        MatchReplayStats.objects.filter(match_replay=match_replay).delete()
        created_count = 0
        existing_count = MatchReplayStats.objects.filter(match=match).count()
        for idx, stats_obj in enumerate(stats_list):
            played_minutes = stats_obj.get('minutes')
            score_red = stats_obj.get('scoreRed')
            score_blue = stats_obj.get('scoreBlue')
            if played_minutes < 1 and (score_red == 0 and score_blue == 0):
                continue

            part_order = existing_count + created_count
            match part_order:
                case 0:
                    part_label = MatchReplayStats.PartLabel.FIRST_HALF
                case 1:
                    part_label = MatchReplayStats.PartLabel.SECOND_HALF
                case _:
                    part_label = MatchReplayStats.PartLabel.EXTRA_TIME
            red_is_home = True
            _create_replay_stats_from_part(match_replay, part_order, part_label, red_is_home, stats_obj)
            created_count += 1

    # Update status
    has_any = MatchReplayStats.objects.filter(match=match).exists()
    status.status = MatchReplayStatsStatus.Status.SUCCESS if has_any else MatchReplayStatsStatus.Status.FAILED
    status.fetched_at = timezone.now()
    status.error_message = '' if has_any else 'No Powtorki replays or all fetches failed'
    status.save(update_fields=['status', 'fetched_at', 'error_message'])

    return {'match_id': match_id, 'created_parts': created_count, 'status': status.status}
