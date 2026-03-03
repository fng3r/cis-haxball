"""
Celery tasks for tournament app. fetch_match_replay_stats: pull replays from Powtorki,
upload to Haxball Analyzer, store raw response in MatchReplay; rebuild MatchReplayStats
and MatchReplayStatsPlayer from raw every run.
"""

import logging

from django.db import transaction
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
    download_replay,
    fetch_analyzer_stats,
    is_powtorki_url,
    upload_replay_to_analyzer,
)

logger = logging.getLogger(__name__)


def _resolve_player(match, nick: str):
    """Resolve player on replay to Player model."""
    player = match.match_participants.filter(nickname__iexact=nick).first()
    if not player:
        player = Player.objects.filter(nickname__iexact=nick).first()
    return player


def _create_replay_stats_from_part(
    match_replay: MatchReplay,
    part_order: int,
    part_label: str,
    red_is_home: bool,
    stats: dict,
):
    """Create one MatchReplayStats and related MatchReplayStatsPlayer from one API stats object."""
    match = match_replay.match
    red_team_nicks = stats.get('redTeam', [])
    blue_team_nicks = stats.get('blueTeam', [])
    player_ratings = stats.get('playerRatings', {})
    kicks_list = stats.get('kicks', [])
    kicks_red = sum(1 for k in kicks_list if k.get('team', '').lower() == 'red')
    kicks_blue = sum(1 for k in kicks_list if k.get('team', '').lower() == 'blue')

    part = MatchReplayStats.objects.create(
        match=match,
        match_replay=match_replay,
        part_order=part_order,
        part_label=part_label,
        red_is_home=red_is_home,
        score_red=stats.get('scoreRed', 0),
        score_blue=stats.get('scoreBlue', 0),
        game_ticks=stats.get('gameTicks', 0),
        minutes=stats.get('minutes', 0),
        poss_red=stats.get('possRed', 0),
        poss_blue=stats.get('possBlue', 0),
        shots_red=stats.get('shotsRed', 0),
        shots_blue=stats.get('shotsBlue', 0),
        shots_off_target_red=stats.get('shotsOffTargetRed', 0),
        shots_off_target_blue=stats.get('shotsOffTargetBlue', 0),
        shots_total_red=stats.get('shotsTotalRed', 0),
        shots_total_blue=stats.get('shotsTotalBlue', 0),
        kicks_red=kicks_red,
        kicks_blue=kicks_blue,
        stadium_name=stats.get('stadiumName', ''),
        red_team_nicks=[n.strip() for n in red_team_nicks],
        blue_team_nicks=[n.strip() for n in blue_team_nicks],
        mvp_nick=player_ratings.get('mvpNick', '').strip(),
    )

    # Per-player (skip zero playtime and '* (own goal)' fake players)
    players_data = stats.get('players', [])
    for p in players_data:
        nick = p.get('nick', '').strip()
        if not nick or '(own goal)' in nick:
            continue
        metrics = p.get('metrics') or {}
        samples_count = metrics.get('samples') or 0
        if samples_count <= 0:
            continue
        played_ticks = metrics.get('playedTicks') or p.get('playedTicks') or 0

        rating_obj = p.get('rating') or {}
        rating = _float_or_none(rating_obj.get('rating'))

        team_key = p.get('team')
        player = _resolve_player(match, nick)
        team_obj = part.get_match_team_for_replay_side(team_key)

        MatchReplayStatsPlayer.objects.create(
            replay_stats=part,
            player=player,
            nick=nick,
            team=team_obj,
            goals=metrics.get('goals', 0),
            assists=metrics.get('assists', 0),
            played_ticks=played_ticks,
            rating=rating,
            shots_total=metrics.get('shotsTotal', 0),
            shots_on_target=metrics.get('shotsOnTarget', 0),
            shots_off_target=metrics.get('shotsOffTarget', 0),
            passes_completed=metrics.get('passesCompleted', 0),
            pass_attempts=metrics.get('passAttempts', 0),
            pass_completion_rate=_float_or_none(metrics.get('passCompletionRate')),
            touches=metrics.get('touches', 0),
            saves=metrics.get('saves', 0),
            clearances=metrics.get('clearances', 0),
            interceptions=metrics.get('interceptions', 0),
            duel_wins=metrics.get('duelWins', 0),
            duel_losses=metrics.get('duelLosses', 0),
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


def _build_error_message(failed_replays: list[tuple[str, str]], has_any_stats: bool) -> str:
    if not failed_replays:
        return ''

    prefix = 'Partial failures' if has_any_stats else 'Replay stats fetch failed'
    details = '; '.join(f'{url}: {error}' for url, error in failed_replays)
    max_len = 3000
    if len(details) > max_len:
        details = f'{details[:max_len]}...'
    return f'{prefix}. {details}'


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

    replay_payloads = []
    failed_replays = []

    for url in match.replays or []:
        if not is_powtorki_url(url):
            continue
        match_replay = MatchReplay.objects.filter(match=match, replay_url=url).first()
        if match_replay and match_replay.raw_stats_json:
            stats_list = list(match_replay.raw_stats_json)
        else:
            try:
                replay_file = download_replay(url)
                if replay_file is None:
                    logger.warning('[match_id=%s] Unsupported replay source for %s', match_id, url)
                    failed_replays.append((url, 'Unsupported replay source'))
                    continue
                logger.info('[match_id=%s] Downloaded replay file from %s', match_id, url)
                analyzer_id = upload_replay_to_analyzer(replay_file)
                logger.info('[match_id=%s] Uploaded replay to analyzer id=%s', match_id, analyzer_id)
                stats_list = fetch_analyzer_stats(analyzer_id)
                logger.info('[match_id=%s] Fetched analyzer stats id=%s', match_id, analyzer_id)
            except Exception as exc:
                logger.exception('[match_id=%s] Failed to fetch replay stats for %s', match_id, url)
                failed_replays.append((url, f'{type(exc).__name__}: {exc}'))
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
        replay_payloads.append((match_replay, stats_list))

    total_created_count = 0
    with transaction.atomic():
        # Full rebuild: clear all derived replay stats for the match first.
        MatchReplayStatsPlayer.objects.filter(replay_stats__match=match).delete()
        MatchReplayStats.objects.filter(match=match).delete()

        part_order = 0
        for match_replay, stats_list in replay_payloads:
            for stats_obj in stats_list:
                played_minutes = stats_obj.get('minutes')
                score_red = stats_obj.get('scoreRed')
                score_blue = stats_obj.get('scoreBlue')
                if played_minutes < 1 and (score_red == 0 and score_blue == 0):
                    continue
                match part_order:
                    case 0:
                        part_label = MatchReplayStats.PartLabel.FIRST_HALF
                    case 1:
                        part_label = MatchReplayStats.PartLabel.SECOND_HALF
                    case _:
                        part_label = MatchReplayStats.PartLabel.EXTRA_TIME
                red_is_home = True
                _create_replay_stats_from_part(match_replay, part_order, part_label, red_is_home, stats_obj)
                part_order += 1
                total_created_count += 1

    has_any = total_created_count > 0
    if has_any and failed_replays:
        final_status = MatchReplayStatsStatus.Status.PARTIAL
    elif has_any:
        final_status = MatchReplayStatsStatus.Status.SUCCESS
    else:
        final_status = MatchReplayStatsStatus.Status.FAILED
    status.status = final_status
    status.fetched_at = timezone.now()
    status.error_message = _build_error_message(failed_replays, has_any)
    if not status.error_message and not has_any:
        status.error_message = 'No Powtorki replays found or all replay parts were filtered out'
    status.save(update_fields=['status', 'fetched_at', 'error_message'])

    return {'match_id': match_id, 'created_parts': total_created_count, 'status': status.status}
