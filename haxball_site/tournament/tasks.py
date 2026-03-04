"""
Celery tasks for tournament app. fetch_match_replay_stats: pull replays from Powtorki,
upload to Haxball Analyzer, store raw response in MatchReplay; rebuild MatchReplayStats
and MatchReplayStatsPlayer from raw every run.
"""

import logging

from django.db import transaction
from django.db.models import Q
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
    fetch_analyzer_stats_once,
    is_powtorki_url,
    upload_replay_to_analyzer,
)

logger = logging.getLogger(__name__)
SUPPORTED_PLAYER_POSITIONS = {
    MatchReplayStatsPlayer.Position.GK,
    MatchReplayStatsPlayer.Position.DM,
    MatchReplayStatsPlayer.Position.AM,
    MatchReplayStatsPlayer.Position.ST,
}


def _resolve_player(match, nick: str):
    """Resolve player on replay to Player model."""
    lookup = Q(nickname__iexact=nick) | Q(name__previous_nicknames__nickname__iexact=nick)
    player = match.match_participants.filter(lookup).distinct().first()
    if not player:
        player = Player.objects.filter(lookup).distinct().first()

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
        raw_position = (metrics.get('position') or '').strip().upper()
        position = raw_position if raw_position in SUPPORTED_PLAYER_POSITIONS else None
        print(f'{raw_position} -> {position}')

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
            position=position,
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


def _derive_match_replay_status(match: Match) -> tuple[str, str]:
    replays = list(MatchReplay.objects.filter(match=match).values('replay_url', 'status', 'error_message'))
    if not replays:
        return MatchReplayStatsStatus.Status.FAILED, 'No supported replay links for match'

    total = len(replays)
    ready = sum(1 for r in replays if r['status'] == MatchReplay.ReplayStatus.READY)
    awaiting = sum(1 for r in replays if r['status'] == MatchReplay.ReplayStatus.AWAITING_STATS)
    pending = sum(1 for r in replays if r['status'] == MatchReplay.ReplayStatus.PENDING)

    if ready == total:
        status = MatchReplayStatsStatus.Status.SUCCESS
    elif ready > 0:
        status = MatchReplayStatsStatus.Status.PARTIAL
    elif awaiting > 0 or pending > 0:
        status = MatchReplayStatsStatus.Status.PENDING
    else:
        status = MatchReplayStatsStatus.Status.FAILED

    failed_details = [
        f'{r["replay_url"]}: {r["error_message"]}'
        for r in replays
        if r['status'] == MatchReplay.ReplayStatus.FAILED and r['error_message']
    ]
    if failed_details:
        prefix = (
            'Partial failures'
            if status in {MatchReplayStatsStatus.Status.PARTIAL, MatchReplayStatsStatus.Status.PENDING}
            else 'Replay stats fetch failed'
        )
        details = '; '.join(failed_details)
        if len(details) > 3000:
            details = f'{details[:3000]}...'
        return status, f'{prefix}. {details}'

    if status == MatchReplayStatsStatus.Status.PENDING:
        return status, 'Replay uploaded, waiting for analyzer stats'
    if status == MatchReplayStatsStatus.Status.FAILED:
        return status, 'No replay stats available'
    return status, ''


def _rebuild_match_replay_stats(match: Match) -> int:
    """Rebuild MatchReplayStats/MatchReplayStatsPlayer from READY MatchReplay.raw_stats_json."""
    replay_payloads = []
    for replay in MatchReplay.objects.filter(match=match, status=MatchReplay.ReplayStatus.READY).order_by('id'):
        if replay.raw_stats_json:
            replay_payloads.append((replay, list(replay.raw_stats_json)))

    total_created_count = 0
    with transaction.atomic():
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

    return total_created_count


def _update_match_replay_stats_status(match: Match) -> MatchReplayStatsStatus:
    status, _ = MatchReplayStatsStatus.objects.get_or_create(
        match=match,
        defaults={'status': MatchReplayStatsStatus.Status.PENDING},
    )
    final_status, error_message = _derive_match_replay_status(match)
    status.status = final_status
    status.fetched_at = timezone.now()
    status.error_message = error_message
    status.save(update_fields=['status', 'fetched_at', 'error_message'])
    return status


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
        match_replay, _ = MatchReplay.objects.get_or_create(
            match=match,
            replay_url=url,
            defaults={'status': MatchReplay.ReplayStatus.PENDING},
        )
        if match_replay and match_replay.raw_stats_json:
            stats_list = list(match_replay.raw_stats_json)
            if match_replay.status != MatchReplay.ReplayStatus.READY or match_replay.error_message:
                match_replay.status = MatchReplay.ReplayStatus.READY
                match_replay.error_message = ''
                match_replay.save(update_fields=['status', 'error_message'])
        else:
            analyzer_id = ''
            try:
                replay_file = download_replay(url)
                if replay_file is None:
                    logger.warning('[match_id=%s] Unsupported replay source for %s', match_id, url)
                    match_replay.status = MatchReplay.ReplayStatus.FAILED
                    match_replay.error_message = 'Unsupported replay source'
                    match_replay.save(update_fields=['status', 'error_message'])
                    continue
                logger.info('[match_id=%s] Downloaded replay file from %s', match_id, url)
                analyzer_id = upload_replay_to_analyzer(replay_file)
                logger.info('[match_id=%s] Uploaded replay to analyzer id=%s', match_id, analyzer_id)
                stats_list = fetch_analyzer_stats(analyzer_id)
                logger.info('[match_id=%s] Fetched analyzer stats id=%s', match_id, analyzer_id)
            except TimeoutError as exc:
                logger.warning('[match_id=%s] Stats not ready yet for %s', match_id, url)
                match_replay.analyzer_replay_id = analyzer_id or match_replay.analyzer_replay_id
                match_replay.status = MatchReplay.ReplayStatus.AWAITING_STATS
                match_replay.error_message = f'{type(exc).__name__}: {exc}'
                match_replay.save(update_fields=['analyzer_replay_id', 'status', 'error_message'])
                continue
            except Exception as exc:
                logger.exception('[match_id=%s] Failed to fetch replay stats for %s', match_id, url)
                match_replay.analyzer_replay_id = analyzer_id or match_replay.analyzer_replay_id
                match_replay.status = MatchReplay.ReplayStatus.FAILED
                match_replay.error_message = f'{type(exc).__name__}: {exc}'
                match_replay.save(update_fields=['analyzer_replay_id', 'status', 'error_message'])
                continue
            match_replay, _ = MatchReplay.objects.update_or_create(
                match=match,
                replay_url=url,
                defaults={
                    'analyzer_replay_id': analyzer_id,
                    'raw_stats_json': stats_list,
                    'status': MatchReplay.ReplayStatus.READY,
                    'error_message': '',
                    'fetched_at': timezone.now(),
                },
            )
    total_created_count = _rebuild_match_replay_stats(match)
    status = _update_match_replay_stats_status(match)

    return {'match_id': match_id, 'created_parts': total_created_count, 'status': status.status}


@shared_task
def refresh_awaiting_replay_stats(batch_size: int = 200):
    """
    Periodic task for replays stuck in AWAITING_STATS.
    One stats request per replay (no polling loop). If not ready yet, leave as-is.
    """
    awaiting_replays = list(
        MatchReplay.objects.filter(status=MatchReplay.ReplayStatus.AWAITING_STATS)
        .exclude(analyzer_replay_id='')
        .select_related('match')
        .order_by('id')[:batch_size]
    )

    if not awaiting_replays:
        return {'checked': 0, 'ready': 0, 'matches_rebuilt': 0}

    affected_match_ids = set()
    ready_count = 0

    for replay in awaiting_replays:
        try:
            stats_list = fetch_analyzer_stats_once(replay.analyzer_replay_id)
        except Exception as exc:
            logger.warning(
                '[replay_id=%s match_id=%s] Single-shot stats fetch failed: %s',
                replay.analyzer_replay_id,
                replay.match_id,
                exc,
            )
            continue

        if stats_list is None:
            continue

        replay.raw_stats_json = stats_list
        replay.status = MatchReplay.ReplayStatus.READY
        replay.error_message = ''
        replay.fetched_at = timezone.now()
        replay.save(update_fields=['raw_stats_json', 'status', 'error_message', 'fetched_at'])

        ready_count += 1
        affected_match_ids.add(replay.match_id)

    rebuilt_matches = 0
    for match_id in affected_match_ids:
        match = Match.objects.filter(pk=match_id).first()
        if not match:
            continue
        _rebuild_match_replay_stats(match)
        _update_match_replay_stats_status(match)
        rebuilt_matches += 1

    return {
        'checked': len(awaiting_replays),
        'ready': ready_count,
        'matches_rebuilt': rebuilt_matches,
    }
