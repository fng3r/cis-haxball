"""Read-only presentation adapter to the established match statistics UI."""

from types import SimpleNamespace

from .local_replays import active_parts, analyzer_link, recording_sources
from .replay_stats import MatchReplayStatsAggregator


class Rows(list):
    def all(self):
        return self


def statistics(match, request=None):
    candidates = [part for part in active_parts(match) if part.included]
    parts = [part for part in candidates if {row.side for row in part.game.team_stats.all()} == {'red', 'blue'}]
    incomplete = len(parts) != len(candidates)
    adapted = []
    for index, part in enumerate(parts):
        teams = {stats.side: stats for stats in part.game.team_stats.all()}
        red, blue = teams['red'], teams['blue']
        players = Rows()
        for row in part.game.player_stats.all():
            team = match.team_home if (row.side == 'red') == part.red_is_home else match.team_guest
            players.append(
                SimpleNamespace(
                    player=row.player,
                    player_id=row.player_id,
                    nick=row.nick,
                    team=team,
                    team_id=team.pk,
                    goals=row.goals,
                    assists=row.assists,
                    played_ticks=row.active_ticks,
                    shots_on_target=row.shots_on_target,
                    passes_completed=row.passes_completed,
                    position=None,
                    rating=None,
                    shots_total=0,
                    pass_attempts=0,
                    touches=0,
                    saves=0,
                    clearances=0,
                    interceptions=0,
                    duel_wins=0,
                    duel_losses=0,
                )
            )
        adapted.append(
            SimpleNamespace(
                id=part.pk,
                part_order=index,
                get_part_label_display=lambda p=part: p.label,
                home_guest=lambda a, b, p=part: (a, b) if p.red_is_home else (b, a),
                players=players,
                score_red=red.goals,
                score_blue=blue.goals,
                poss_red=red.possession_ticks,
                poss_blue=blue.possession_ticks,
                shots_red=red.shots_on_target,
                shots_blue=blue.shots_on_target,
                shots_total_red=0,
                shots_total_blue=0,
                kicks_red=red.kicks,
                kicks_blue=blue.kicks,
                thirds_red=red.territory_ticks,
                thirds_blue=blue.territory_ticks,
                thirds_mid=red.middle_ticks,
                game_ticks=part.game.active_ticks,
                minutes=part.game.active_ticks // 3600,
                stadium_name=part.game.stadium_name,
                match_replay=SimpleNamespace(analyzer_replay_id=''),
            )
        )
    payload = MatchReplayStatsAggregator(match=match, parts=adapted).build()
    payload['is_current'] = True
    payload['replay_links'] = [{'label': 'Открыть матч в анализаторе', 'analyzer_url': analyzer_link(match, request)}]
    for summary, part in zip(payload['parts_summary'], parts):
        summary['analyzer_url'] = analyzer_link(match, request, part)
        by_side = {row.side: row for row in part.game.team_stats.all()}
        summary['passes_home'] = by_side['red' if part.red_is_home else 'blue'].passes_completed
        summary['passes_guest'] = by_side['blue' if part.red_is_home else 'red'].passes_completed
    for side in ('home', 'guest'):
        payload['team'][f'passes_{side}'] = sum(row[f'passes_{side}'] for row in payload['parts_summary'])
    # Unsupported metrics are absent in the new schema and unavailable in the UI.
    for row in [*payload['players'], *(row for part in payload['parts_players'] for row in part['players'])]:
        for field in ('shots_total', 'pass_attempts', 'pass_accuracy', 'touches', 'saves', 'rating'):
            row[field] = None
    comparisons = [payload['players_comparison_data']['total'], *payload['players_comparison_data']['parts']]
    for group in comparisons:
        for row in [*group['home'], *group['guest']]:
            for field in ('shots_total', 'pass_accuracy', 'touches', 'saves', 'rating'):
                row[field] = None
    kicks = {}
    per_part_kicks = {}
    for index, part in enumerate(parts):
        per_part_kicks[index + 1] = {}
        for source in part.game.player_stats.all():
            team_id = match.team_home_id if (source.side == 'red') == part.red_is_home else match.team_guest_id
            key = (source.player_id,) if source.player_id else (source.nick, team_id)
            kicks[key] = kicks.get(key, 0) + source.kicks
            per_part_kicks[index + 1][key] = per_part_kicks[index + 1].get(key, 0) + source.kicks

    def add_kicks(rows, counts):
        for row in rows:
            key = (row['player'].pk,) if row['player'] else (row['nick'], row['team_obj'].pk)
            row['kicks'] = counts.get(key, 0)

    add_kicks(payload['players'], kicks)
    for part in payload['parts_players']:
        add_kicks(part['players'], per_part_kicks[part['index']])
    for side in ('home', 'guest'):
        for row, player in zip(payload['players_comparison_data']['total'][side], payload[f'{side}_players']):
            row['kicks'] = player['kicks']
    for comparison, part in zip(payload['players_comparison_data']['parts'], payload['parts_players']):
        for side, team_id in [('home', match.team_home_id), ('guest', match.team_guest_id)]:
            rows = [row for row in part['players'] if row['team_obj'].pk == team_id]
            for row, player in zip(comparison[side], rows):
                row['kicks'] = player['kicks']
    keys = [key for key, _ in recording_sources(match)]
    records = list(match.replay_recordings.filter(source_key__in=keys).defer('raw_response'))
    payload['recordings'] = records
    payload['has_data'] = bool(parts)
    payload['needs_review'] = (
        incomplete or match.replay_parts.filter(game__available=False, game__recording__source_key__in=keys).exists()
    )
    return payload
