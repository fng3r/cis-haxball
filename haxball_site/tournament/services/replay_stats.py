from dataclasses import dataclass
from typing import TypedDict

from tournament.models import Match, MatchReplayStats


class PlayerRow(TypedDict):
    player: object | None
    nick: str
    team_obj: object | None
    goals: int
    assists: int
    position: str | None
    position_label: str | None
    played_ticks: int
    playtime: str
    shots_total: int
    shots_on_target: int
    passes_completed: int
    pass_attempts: int
    pass_accuracy: float | None
    touches: int
    saves: int
    rating: float | None
    is_mvp: bool


class PlayersPartPayload(TypedDict):
    index: int
    part_label: str
    players: list[PlayerRow]


class TeamStatsBase(TypedDict):
    score_home: int
    score_guest: int
    poss_home: int
    poss_guest: int
    poss_home_pct: int
    poss_guest_pct: int
    shots_home: int
    shots_guest: int
    shots_total_home: int
    shots_total_guest: int
    passes_home: int
    passes_guest: int
    kicks_home: int
    kicks_guest: int
    saves_home: int
    saves_guest: int


class TeamPartSummary(TeamStatsBase):
    index: int
    part_label: str
    minutes: int
    analyzer_replay_id: str | None
    analyzer_url: str


class ReplayLink(TypedDict):
    analyzer_url: str
    label: str


class TeamPayload(TypedDict):
    team: TeamStatsBase
    parts_summary: list[TeamPartSummary]
    replay_links: list[ReplayLink]


def _pct(left: int, right: int) -> tuple[int, int]:
    total = left + right
    if not total:
        return 0, 0
    return round(100 * left / total), round(100 * right / total)


def _pass_accuracy(passes_completed: int, pass_attempts: int) -> float | None:
    if not pass_attempts:
        return None
    return round(100 * passes_completed / pass_attempts, 1)


def _format_playtime(played_ticks: int) -> str:
    # Haxball Analyzer exposes playedTicks in game ticks (60 ticks ~= 1 second).
    total_seconds = max(0, round((played_ticks or 0) / 60))
    minutes, seconds = divmod(total_seconds, 60)
    return f'{minutes:02d}:{seconds:02d}'


def _analyzer_url(analyzer_replay_id: str | None) -> str:
    if not analyzer_replay_id:
        return ''
    return f'https://replay.hax.ma/?replayId={analyzer_replay_id}'


def _position_label(position: str | None) -> str | None:
    if position == 'GK':
        return 'ГК'
    if position == 'DM':
        return 'ОП'
    if position in {'AM', 'ST'}:
        return 'НАП'
    return None


@dataclass(slots=True)
class MatchReplayStatsAggregator:
    match: Match
    parts: list[MatchReplayStats]

    def __post_init__(self):
        self.parts = sorted(self.parts, key=lambda part: part.part_order)

    def build(self) -> dict:
        teams = self._build_teams_stats()
        players = self._build_players_stats()
        return {**teams, **players}

    def _build_teams_stats(self) -> TeamPayload:
        aggregate: TeamStatsBase = {
            'score_home': 0,
            'score_guest': 0,
            'poss_home': 0,
            'poss_guest': 0,
            'poss_home_pct': 0,
            'poss_guest_pct': 0,
            'shots_home': 0,
            'shots_guest': 0,
            'shots_total_home': 0,
            'shots_total_guest': 0,
            'passes_home': 0,
            'passes_guest': 0,
            'kicks_home': 0,
            'kicks_guest': 0,
            'saves_home': 0,
            'saves_guest': 0,
        }
        parts_summary: list[TeamPartSummary] = []
        team_home_id = self.match.team_home_id
        team_guest_id = self.match.team_guest_id

        for part in self.parts:
            score_home, score_guest = part.home_guest(part.score_red, part.score_blue)
            poss_home, poss_guest = part.home_guest(part.poss_red, part.poss_blue)
            shots_home, shots_guest = part.home_guest(part.shots_red, part.shots_blue)
            shots_total_home, shots_total_guest = part.home_guest(part.shots_total_red, part.shots_total_blue)
            kicks_home, kicks_guest = part.home_guest(part.kicks_red, part.kicks_blue)
            poss_home_pct, poss_guest_pct = _pct(poss_home, poss_guest)

            passes_home = passes_guest = saves_home = saves_guest = 0
            for player_stat in part.players.all():
                if player_stat.team_id == team_home_id:
                    passes_home += player_stat.passes_completed
                    saves_home += player_stat.saves
                elif player_stat.team_id == team_guest_id:
                    passes_guest += player_stat.passes_completed
                    saves_guest += player_stat.saves

            part_summary: TeamPartSummary = {
                'index': part.part_order + 1,
                'part_label': part.get_part_label_display(),
                'score_home': score_home,
                'score_guest': score_guest,
                'poss_home': poss_home,
                'poss_guest': poss_guest,
                'poss_home_pct': poss_home_pct,
                'poss_guest_pct': poss_guest_pct,
                'shots_home': shots_home,
                'shots_guest': shots_guest,
                'shots_total_home': shots_total_home,
                'shots_total_guest': shots_total_guest,
                'passes_home': passes_home,
                'passes_guest': passes_guest,
                'kicks_home': kicks_home,
                'kicks_guest': kicks_guest,
                'saves_home': saves_home,
                'saves_guest': saves_guest,
                'minutes': part.minutes,
                'analyzer_replay_id': part.match_replay.analyzer_replay_id,
                'analyzer_url': _analyzer_url(part.match_replay.analyzer_replay_id),
            }
            parts_summary.append(part_summary)

            aggregate['score_home'] += score_home
            aggregate['score_guest'] += score_guest
            aggregate['poss_home'] += poss_home
            aggregate['poss_guest'] += poss_guest
            aggregate['shots_home'] += shots_home
            aggregate['shots_guest'] += shots_guest
            aggregate['shots_total_home'] += shots_total_home
            aggregate['shots_total_guest'] += shots_total_guest
            aggregate['passes_home'] += passes_home
            aggregate['passes_guest'] += passes_guest
            aggregate['kicks_home'] += kicks_home
            aggregate['kicks_guest'] += kicks_guest
            aggregate['saves_home'] += saves_home
            aggregate['saves_guest'] += saves_guest

        poss_home_pct, poss_guest_pct = _pct(aggregate['poss_home'], aggregate['poss_guest'])
        aggregate['poss_home_pct'] = poss_home_pct
        aggregate['poss_guest_pct'] = poss_guest_pct

        replay_groups: dict[str, dict] = {}
        for part in parts_summary:
            analyzer_url = part['analyzer_url']
            if not analyzer_url:
                continue
            key = part['analyzer_replay_id'] or analyzer_url
            if key not in replay_groups:
                replay_groups[key] = {'analyzer_url': analyzer_url, 'parts': []}
            replay_groups[key]['parts'].append(part['part_label'])

        replay_links: list[ReplayLink] = []
        single_replay = len(replay_groups) == 1
        for group in replay_groups.values():
            replay_links.append(
                {
                    'analyzer_url': group['analyzer_url'],
                    'label': 'Матч' if single_replay else ' • '.join(group['parts']),
                }
            )

        return {'team': aggregate, 'parts_summary': parts_summary, 'replay_links': replay_links}

    def _build_players_stats(self) -> dict:
        team_home_id = self.match.team_home_id
        team_guest_id = self.match.team_guest_id
        player_aggregate: dict[tuple, dict] = {}

        for part in self.parts:
            for player_stat in part.players.all():
                key = (player_stat.player_id,) if player_stat.player_id else (player_stat.nick, player_stat.team_id)
                if key not in player_aggregate:
                    player_aggregate[key] = {
                        'player': player_stat.player,
                        'nick': player_stat.nick,
                        'team_obj': player_stat.team,
                        'goals': 0,
                        'assists': 0,
                        'position_ticks': {},
                        'played_ticks': 0,
                        'rating_weighted_sum': 0.0,
                        'rating_weights_sum': 0,
                        'shots_total': 0,
                        'shots_on_target': 0,
                        'passes_completed': 0,
                        'pass_attempts': 0,
                        'touches': 0,
                        'saves': 0,
                        'clearances': 0,
                        'interceptions': 0,
                        'duel_wins': 0,
                        'duel_losses': 0,
                    }

                acc = player_aggregate[key]
                acc['goals'] += player_stat.goals
                acc['assists'] += player_stat.assists
                acc['played_ticks'] += player_stat.played_ticks
                if player_stat.position and player_stat.played_ticks > 0:
                    position_ticks = acc['position_ticks']
                    position_ticks[player_stat.position] = (
                        position_ticks.get(player_stat.position, 0) + player_stat.played_ticks
                    )
                if player_stat.rating is not None and player_stat.played_ticks > 0:
                    acc['rating_weighted_sum'] += player_stat.rating * player_stat.played_ticks
                    acc['rating_weights_sum'] += player_stat.played_ticks
                acc['shots_total'] += player_stat.shots_total
                acc['shots_on_target'] += player_stat.shots_on_target
                acc['passes_completed'] += player_stat.passes_completed
                acc['pass_attempts'] += player_stat.pass_attempts
                acc['touches'] += player_stat.touches
                acc['saves'] += player_stat.saves
                acc['clearances'] += player_stat.clearances
                acc['interceptions'] += player_stat.interceptions
                acc['duel_wins'] += player_stat.duel_wins
                acc['duel_losses'] += player_stat.duel_losses

        aggregated_players: list[PlayerRow] = []
        for acc in player_aggregate.values():
            rating = (acc['rating_weighted_sum'] / acc['rating_weights_sum']) if acc['rating_weights_sum'] else None
            dominant_position = None
            if acc['position_ticks']:
                dominant_position = max(
                    acc['position_ticks'].items(),
                    key=lambda item: (item[1], 1 if item[0] == 'GK' else 0, 1 if item[0] == 'DM' else 0),
                )[0]
            aggregated_players.append(
                self._player_row(
                    player=acc.get('player'),
                    nick=acc.get('nick', ''),
                    team_obj=acc.get('team_obj'),
                    goals=acc.get('goals', 0),
                    assists=acc.get('assists', 0),
                    position=dominant_position,
                    played_ticks=acc.get('played_ticks', 0),
                    shots_total=acc.get('shots_total', 0),
                    shots_on_target=acc.get('shots_on_target', 0),
                    passes_completed=acc.get('passes_completed', 0),
                    pass_attempts=acc.get('pass_attempts', 0),
                    touches=acc.get('touches', 0),
                    saves=acc.get('saves', 0),
                    rating=rating,
                )
            )

        rated_players = [p for p in aggregated_players if p.get('rating') is not None]
        if rated_players:
            max_rating = max(p['rating'] for p in rated_players)
            for player in aggregated_players:
                player['is_mvp'] = player.get('rating') == max_rating

        aggregated_players.sort(key=lambda item: self._player_sort_key(item, team_home_id))

        home_players = [p for p in aggregated_players if p.get('team_obj') and p['team_obj'].id == team_home_id]
        guest_players = [p for p in aggregated_players if p.get('team_obj') and p['team_obj'].id == team_guest_id]

        players_comparison_data = {
            'total': {
                'home': [self._comparison_player_dict(player, i) for i, player in enumerate(home_players)],
                'guest': [self._comparison_player_dict(player, i) for i, player in enumerate(guest_players)],
            },
            'parts': [],
        }

        parts_players: list[PlayersPartPayload] = []
        for part in self.parts:
            part_index = part.part_order + 1
            part_players: list[PlayerRow] = []
            for player_stat in part.players.all():
                part_players.append(
                    self._player_row(
                        player=player_stat.player,
                        nick=player_stat.nick,
                        team_obj=player_stat.team,
                        goals=player_stat.goals,
                        assists=player_stat.assists,
                        position=player_stat.position,
                        played_ticks=player_stat.played_ticks,
                        shots_total=player_stat.shots_total,
                        shots_on_target=player_stat.shots_on_target,
                        passes_completed=player_stat.passes_completed,
                        pass_attempts=player_stat.pass_attempts or 0,
                        touches=player_stat.touches,
                        saves=player_stat.saves,
                        rating=player_stat.rating,
                    )
                )

            part_players.sort(key=lambda item: self._player_sort_key(item, team_home_id))
            home_part_players = [p for p in part_players if p.get('team_obj') and p['team_obj'].id == team_home_id]
            guest_part_players = [p for p in part_players if p.get('team_obj') and p['team_obj'].id == team_guest_id]

            players_comparison_data['parts'].append(
                {
                    'index': part_index,
                    'part_label': part.part_label,
                    'home': [self._comparison_player_dict(player, j) for j, player in enumerate(home_part_players)],
                    'guest': [self._comparison_player_dict(player, j) for j, player in enumerate(guest_part_players)],
                }
            )
            parts_players.append(
                {'index': part_index, 'part_label': part.get_part_label_display(), 'players': part_players}
            )

        return {
            'players': aggregated_players,
            'parts_players': parts_players,
            'home_players': home_players,
            'guest_players': guest_players,
            'players_comparison_data': players_comparison_data,
        }

    @staticmethod
    def _player_sort_key(player: dict, team_home_id: int) -> tuple:
        is_home = player.get('team_obj') and player['team_obj'].id == team_home_id
        return (0 if is_home else 1, player.get('nick') or '')

    @staticmethod
    def _player_row(
        *,
        player,
        nick: str,
        team_obj,
        goals: int,
        assists: int,
        position: str | None,
        played_ticks: int,
        shots_total: int,
        shots_on_target: int,
        passes_completed: int,
        pass_attempts: int,
        touches: int,
        saves: int,
        rating: float | None,
        is_mvp: bool = False,
    ) -> PlayerRow:
        return {
            'player': player,
            'nick': nick,
            'team_obj': team_obj,
            'goals': goals,
            'assists': assists,
            'position': position,
            'position_label': _position_label(position),
            'played_ticks': played_ticks,
            'playtime': _format_playtime(played_ticks),
            'shots_total': shots_total,
            'shots_on_target': shots_on_target,
            'passes_completed': passes_completed,
            'pass_attempts': pass_attempts,
            'pass_accuracy': _pass_accuracy(passes_completed, pass_attempts),
            'touches': touches,
            'saves': saves,
            'rating': round(rating, 2) if rating is not None else None,
            'is_mvp': is_mvp,
        }

    @staticmethod
    def _comparison_player_dict(player: dict, index: int) -> dict:
        rating = player.get('rating')
        return {
            'i': index,
            'name': (player.get('player') and player['player'].nickname) or player.get('nick') or '—',
            'goals': player.get('goals', 0),
            'assists': player.get('assists', 0),
            'shots_total': player.get('shots_total', 0),
            'shots_on_target': player.get('shots_on_target', 0),
            'passes_completed': player.get('passes_completed', 0),
            'pass_accuracy': player.get('pass_accuracy'),
            'touches': player.get('touches', 0),
            'saves': player.get('saves', 0),
            'rating': round(float(rating), 2) if rating is not None else None,
        }
