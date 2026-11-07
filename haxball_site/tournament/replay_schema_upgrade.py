"""Data migration from the first experimental JSON-only model, using historical ORM models."""

import hashlib
import json


def copy_previous_analyses(apps, schema_editor):
    from .replay_stats_client import get_replay_source_and_id

    old_model = apps.get_model('tournament', 'LocalReplayAnalysis')
    recording_model = apps.get_model('tournament', 'ReplayRecording')
    game_model = apps.get_model('tournament', 'ReplayGame')
    part_model = apps.get_model('tournament', 'ReplayMatchPart')
    team_model = apps.get_model('tournament', 'ReplayTeamStats')
    player_model = apps.get_model('tournament', 'ReplayPlayerStats')
    database = schema_editor.connection.alias
    orders = {}
    for old in old_model.objects.using(database).order_by('id'):
        identity = get_replay_source_and_id(old.replay_url)
        key = ':'.join(identity) if identity else f'archived:{old.pk}'
        recording, _ = recording_model.objects.using(database).get_or_create(
            match_id=old.match_id,
            source_key=key,
            defaults={
                'replay_url': old.replay_url,
                'raw_response': old.result,
                'content_sha256': old.content_sha256,
                'status': old.status,
                'engine_version': old.engine_version,
                'error_message': old.error_message,
                'analyzed_at': old.analyzed_at,
                'schema_version': old.result.get('schemaVersion', 1),
                'response_sha256': hashlib.sha256(json.dumps(old.result, sort_keys=True).encode()).hexdigest(),
            },
        )
        for index, raw in enumerate(old.result.get('games', [])):
            game, _ = game_model.objects.using(database).get_or_create(
                recording_id=recording.pk,
                engine_game_id=raw['id'],
                defaults={
                    'start_tick': raw['startTick'],
                    'active_ticks': raw['gameTicks'],
                    'stadium_name': raw['stadium']['name'],
                },
            )
            order = orders.get(old.match_id, 0)
            orders[old.match_id] = order + 1
            mapping = old.inferred_sides.get(str(index))
            override = old.side_overrides.get(str(index))
            part_model.objects.using(database).get_or_create(
                game_id=game.pk,
                defaults={
                    'match_id': old.match_id,
                    'generated_order': order,
                    'generated_label': f'{order + 1} тайм',
                    'inferred_red_is_home': mapping if isinstance(mapping, bool) else True,
                    'red_is_home_override': override if isinstance(override, bool) else None,
                    'mapping_evidence': 'roster' if isinstance(mapping, bool) else 'default',
                },
            )
            for side, i in [('red', 0), ('blue', 1)]:
                team_model.objects.using(database).get_or_create(
                    game_id=game.pk,
                    side=side,
                    defaults={
                        'goals': raw['scoreRed' if side == 'red' else 'scoreBlue'],
                        'possession_ticks': raw['possession'][i],
                        'kicks': raw['kicks'][i],
                        'passes_completed': raw['passes'][i],
                        'shots_on_target': raw['shots'][i],
                        'territory_ticks': raw['thirds'][0 if side == 'red' else 2],
                        'middle_ticks': raw['thirds'][1],
                    },
                )
            for p in raw['players']:
                player_model.objects.using(database).get_or_create(
                    game_id=game.pk,
                    replay_player_id=str(p['id']),
                    defaults={
                        'nick': p['nick'],
                        'side': p['team'],
                        'active_ticks': p['playedTicks'],
                        'goals': p['goals'],
                        'assists': p['assists'],
                        'kicks': p['kicks'],
                        'passes_completed': p['passes'],
                        'shots_on_target': p['shots'],
                    },
                )


def restore_previous_analyses(apps, schema_editor):
    """Retain raw results and effective mappings if the experimental-schema upgrade is reversed."""
    old_model = apps.get_model('tournament', 'LocalReplayAnalysis')
    recording_model = apps.get_model('tournament', 'ReplayRecording')
    part_model = apps.get_model('tournament', 'ReplayMatchPart')
    database = schema_editor.connection.alias
    for recording in recording_model.objects.using(database).all():
        parts = {
            part.game.engine_game_id: part
            for part in part_model.objects.using(database)
            .filter(match_id=recording.match_id, game__recording_id=recording.pk)
            .select_related('game')
        }
        inferred, overrides = {}, {}
        for index, game in enumerate(recording.raw_response.get('games', [])):
            part = parts.get(game['id'])
            if part:
                inferred[str(index)] = part.inferred_red_is_home
                if part.red_is_home_override is not None:
                    overrides[str(index)] = part.red_is_home_override
        old_model.objects.using(database).update_or_create(
            match_id=recording.match_id,
            replay_url=recording.replay_url,
            defaults={
                'engine_version': recording.engine_version,
                'result': recording.raw_response,
                'inferred_sides': inferred,
                'side_overrides': overrides,
                'content_sha256': recording.content_sha256,
                'status': recording.status,
                'error_message': recording.error_message,
                'analyzed_at': recording.analyzed_at,
            },
        )
