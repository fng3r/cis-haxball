"""Original engine ingestion and normalized statistics. Never writes legacy tables."""

import hashlib
import json
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from tournament.local_replay_analyzer import analyze_local_replay, engine_revision
from tournament.models import (
    Match,
    ReplayGame,
    ReplayMatchPart,
    ReplayPlayerStats,
    ReplayRecording,
    ReplayTeamStats,
)
from tournament.replay_stats_client import get_replay_source_and_id
from tournament.services.replay_audit import evaluate_match, exclusion_description
from tournament.services.replay_positions import player_position_fields
from tournament.services.replay_rosters import player_aliases, protocol_players
from tournament.services.replay_storage import recording_bytes


def recording_sources(match):
    seen = set()
    for url in match.replays or []:
        identity = get_replay_source_and_id(url)
        if identity:
            key = ':'.join(identity)
            if key not in seen:
                seen.add(key)
                yield key, url


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
        if home != away:
            votes.add(home == (player['team'] == 'red'))
    return (votes.pop(), 'roster') if len(votes) == 1 else (True, 'conflict' if votes else 'default')


def resolve_players(match):
    """Only unique match-roster identities are safe to attach to a replay player."""
    aliases = {}
    for player in match.match_participants.select_related('name'):
        names = [player.nickname]
        if player.name_id:
            names += list(player.name.usernicknamehistoryitem_set.values_list('nickname', flat=True))
        for name in names:
            if name and name.strip():
                aliases.setdefault(name.strip().casefold(), set()).add(player.pk)
    return {name: next(iter(ids)) for name, ids in aliases.items() if len(ids) == 1}


def materialize(recording, result, rosters, players):
    """Caller holds the match lock and transaction. Retain editorial rows, even for vanished games."""
    game_ids = [game['id'] for game in result['games']]
    if len(game_ids) != len(set(game_ids)):
        raise ValueError('Analyzer returned duplicate game IDs')
    recording.games.exclude(engine_game_id__in=game_ids).update(available=False)
    for raw in result['games']:
        game, _ = ReplayGame.objects.update_or_create(
            recording=recording,
            engine_game_id=raw['id'],
            defaults={
                'start_tick': raw['startTick'],
                'stadium_name': raw['stadium']['name'],
                'active_ticks': raw['gameTicks'],
                'available': True,
            },
        )
        mapping, evidence = infer_mapping(raw, rosters)
        part, _ = ReplayMatchPart.objects.get_or_create(
            match=recording.match, game=game, defaults={'auto_included': True}
        )
        part.inferred_red_is_home, part.mapping_evidence = mapping, evidence
        part.save(update_fields=['inferred_red_is_home', 'mapping_evidence'])
        for index, side in enumerate(('red', 'blue')):
            ReplayTeamStats.objects.update_or_create(
                game=game,
                side=side,
                defaults={
                    'goals': raw['scoreRed' if side == 'red' else 'scoreBlue'],
                    'possession_ticks': raw['possession'][index],
                    'kicks': raw['kicks'][index],
                    'passes_completed': raw['passes'][index],
                    'shots_on_target': raw['shots'][index],
                    'territory_ticks': raw['thirds'][0 if side == 'red' else 2],
                    'middle_ticks': raw['thirds'][1],
                },
            )
        seen_players = []
        for p in raw['players']:
            identity = str(p['id'])
            seen_players.append(identity)
            ReplayPlayerStats.objects.update_or_create(
                game=game,
                replay_player_id=identity,
                defaults={
                    'side': p['team'],
                    'nick': p['nick'],
                    'avatar': p.get('avatar'),
                    'player_id': players.get(p['nick'].strip().casefold()),
                    'active_ticks': p['playedTicks'],
                    'goals': p['goals'],
                    'assists': p['assists'],
                    'kicks': p['kicks'],
                    'passes_completed': p['passes'],
                    'shots_on_target': p['shots'],
                    **player_position_fields(p),
                },
            )
        game.player_stats.exclude(replay_player_id__in=seen_players).delete()


def classify_parts(match, reset_override_ids=()):
    """Caller holds the match lock. Reevaluate all current games without rebuilding raw statistics."""
    recordings = {r.source_key: r for r in match.replay_recordings.exclude(raw_response={}).prefetch_related('games')}
    parts = {p.game_id: p for p in match.replay_parts.all()}
    inputs = []
    for key, _ in recording_sources(match):
        recording = recordings.get(key)
        if recording is None:
            continue
        stored = {g.engine_game_id: g for g in recording.games.all() if g.available}
        for raw in sorted(recording.raw_response['games'], key=lambda g: g['id']):
            game = stored.get(raw['id'])
            part = parts.get(game.pk) if game else None
            if part is not None:
                # Old rows have no provenance. Preserve detectable corrections
                # relative to the former short-scoreless filter.
                previous_auto = part.auto_included
                if previous_auto is None:
                    previous_auto = not (raw['gameTicks'] < 3600 and not (raw['scoreRed'] or raw['scoreBlue']))
                if (
                    part.pk not in reset_override_ids
                    and part.included_override is None
                    and part.included != previous_auto
                ):
                    part.included_override = part.included
                inputs.append(
                    {
                        'raw': raw,
                        'part_id': part.pk,
                        'red_is_home_override': part.red_is_home_override,
                        'included_override': part.included_override,
                    }
                )
    if not inputs:
        return
    result = evaluate_match(
        inputs,
        protocol_players(match),
        player_aliases(),
        playoff=bool(match.stage_id and match.stage.type == 'PO'),
        duration_seconds=match.duration.total_seconds(),
        required_players=getattr(settings, 'REPLAY_REQUIRED_PLAYERS', 4),
    )
    by_id = {p.pk: p for p in parts.values()}
    for source, decision in zip(inputs, result['games'], strict=True):
        part = by_id[source['part_id']]
        part.auto_included = decision['recommendation'] != 'exclude'
        part.included = part.included_override if part.included_override is not None else part.auto_included
        part.exclusion_reason = (
            ''
            if part.included
            else 'Исключена вручную.'
            if part.included_override is False
            else exclusion_description(decision)
        )
        ReplayMatchPart.objects.filter(pk=part.pk).update(
            auto_included=part.auto_included,
            included_override=part.included_override,
            included=part.included,
            exclusion_reason=part.exclusion_reason,
        )


def reconcile_parts(match):
    keys = {key: i for i, (key, _) in enumerate(recording_sources(match))}
    parts = list(match.replay_parts.select_related('game__recording'))
    parts = [part for part in parts if part.game.available and part.game.recording.source_key in keys]
    parts.sort(key=lambda p: (keys[p.game.recording.source_key], p.game.engine_game_id))
    included_index = 0
    for index, part in enumerate(parts):
        part.generated_order = index
        if part.included:
            part.generated_label = (
                f'{included_index + 1} тайм' if included_index < 2 else f'Доп. время [{included_index - 1}]'
            )
            included_index += 1
        else:
            part.generated_label = f'Игра {part.game.engine_game_id + 1} (не учитывается)'
        part.save(update_fields=['generated_order', 'generated_label'])


def ingest_match(match_id, force=False, recording_ids=None):
    if not Match.objects.filter(pk=match_id).exists():
        return {'error': 'Match not found', 'match_id': match_id}
    created, errors = 0, 0
    # Serializes list reconciliation, raw publication and all derived metrics with admin edits.
    with transaction.atomic():
        match = Match.objects.select_for_update().get(pk=match_id)
        rosters, players = match_rosters(match), resolve_players(match)
        sources = list(recording_sources(match))
        if recording_ids is not None:
            selected = list(
                match.replay_recordings.filter(pk__in=recording_ids).values_list('source_key', 'replay_url')
            )
            selected_keys = {key for key, _ in selected}
            sources = [(key, url) for key, url in sources if key in selected_keys]
            if force:
                current_keys = {key for key, _ in sources}
                sources.extend((key, url) for key, url in selected if key not in current_keys)
        for key, url in sources:
            recording, _ = ReplayRecording.objects.get_or_create(
                match=match, source_key=key, defaults={'replay_url': url}
            )
            if recording_ids is not None and recording.pk not in recording_ids:
                continue
            recording.replay_url = url
            if recording.raw_response and recording.status == ReplayRecording.Status.READY and not force:
                recording.save(update_fields=['replay_url'])
                continue
            try:
                data = recording_bytes(recording)
                result = analyze_local_replay(data)
                checksum = hashlib.sha256(data).hexdigest()
                # Same-byte reanalysis always refreshes output. Changed bytes cannot inherit game mappings blindly.
                if recording.content_sha256 and checksum != recording.content_sha256:
                    raise ValueError('Recording bytes changed; review the source before remapping existing parts')
                with transaction.atomic():
                    materialize(recording, result, rosters, players)
                    recording.raw_response = result
                    recording.content_sha256 = checksum
                    recording.response_sha256 = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
                    recording.engine_version = engine_revision()
                    recording.schema_version = result['schemaVersion']
                    recording.status = ReplayRecording.Status.READY
                    recording.analyzed_at = timezone.now()
                    recording.error_message = ''
                    recording.save()
                    created += len(result['games'])
            except Exception as exc:
                # Keep the last successful raw response and domain rows together on failure.
                recording.refresh_from_db()
                recording.status = ReplayRecording.Status.FAILED
                recording.error_message = f'{type(exc).__name__}: {exc}'[:2000]
                recording.save(update_fields=['status', 'error_message'])
                errors += 1
        classify_parts(match)
        reconcile_parts(match)
    return {'match_id': match_id, 'created_games': created, 'failed_recordings': errors}


def active_parts(match):
    keys = [key for key, _ in recording_sources(match)]
    parts = (
        match.replay_parts.filter(game__available=True, game__recording__source_key__in=keys)
        .select_related('game__recording', 'match__team_home', 'match__team_guest')
        .defer('game__recording__raw_response')
        .prefetch_related('game__team_stats', 'game__player_stats__player__name__user_profile')
    )
    return sorted(parts, key=lambda part: (part.order, part.pk))


def analyzer_link(match, request=None, part=None):
    manifest = reverse('tournament:analyzer_manifest', args=[match.pk])
    manifest = request.build_absolute_uri(manifest) if request else settings.BASE_URL.rstrip('/') + manifest
    params = {'context': manifest}
    if part is not None:
        params['part'] = part.pk
    return settings.REPLAY_ANALYZER_URL + '?' + urlencode(params)
