from collections import OrderedDict
from dataclasses import dataclass

from django.db.models import Prefetch

from ..models import Group, League, Match, PlayOffStage, Team, TournamentStage
from ..templatetags.tournament_extras import get_league_table, round_name


@dataclass(frozen=True)
class TeamTournamentResult:
    league: League
    stage_name: str | None
    result: str


@dataclass(frozen=True)
class TeamSeasonResults:
    season: object
    tournaments: list[TeamTournamentResult]


def get_team_results(team: Team) -> list[TeamSeasonResults]:
    league_matches = Match.objects.select_related('numb_tour', 'result__winner', 'team_home', 'team_guest', 'series')
    leagues = (
        League.objects.filter(teams=team)
        .select_related('championship')
        .prefetch_related(
            Prefetch('stages', queryset=TournamentStage.objects.order_by('order')),
            Prefetch('matches_in_league', queryset=league_matches, to_attr='prefetched_matches'),
            'stages__teams',
            'stages__tours',
            'winners__winner',
        )
        .order_by('-championship__number', 'priority', 'title')
    )
    results_by_season = OrderedDict()

    for league in leagues:
        is_tournament_winner = any(winner.winner_id == team.id for winner in league.winners.all())
        result = infer_team_tournament_result(team, league, is_tournament_winner)
        if result is None:
            continue
        results_by_season.setdefault(league.championship_id, (league.championship, []))[1].append(result)

    return [TeamSeasonResults(season, tournaments) for season, tournaments in results_by_season.values()]


def infer_team_tournament_result(
    team: Team, league: League, is_tournament_winner: bool = False
) -> TeamTournamentResult | None:
    stages = [stage for stage in league.stages.all() if _team_reached_stage(team, stage, league.prefetched_matches)]
    if not stages:
        return None

    stage = max(stages, key=lambda item: item.order)
    stage_name = stage.stage_name if len(league.stages.all()) > 1 else None

    if stage.is_playoff:
        result, bracket_name = _playoff_result(team, stage, league.prefetched_matches, is_tournament_winner)
        if bracket_name:
            stage_name = f'{stage_name} · {bracket_name}' if stage_name else bracket_name
    elif stage.is_group_stage:
        group = next((group for group in stage.groups.all() if team in group.teams.all()), None)
        result = _table_result(team, league, stage, group, league.prefetched_matches) if group else None
    else:
        result = _table_result(team, league, stage, None, league.prefetched_matches)

    if result is None:
        return None
    return TeamTournamentResult(league=league, stage_name=stage_name, result=result)


def _team_reached_stage(team: Team, stage: TournamentStage, matches: list[Match]) -> bool:
    return team in stage.teams.all() or any(match.stage_id == stage.id for match in matches)


def _table_result(
    team: Team,
    league: League,
    stage: TournamentStage,
    group: Group | None,
    matches: list[Match],
) -> str | None:
    table = get_league_table(league, stage, group, prefetched_matches=matches)
    place = next((place for place, row in enumerate(table, start=1) if row[0] == team), None)
    return _format_place(place) if place is not None else None


def _playoff_result(
    team: Team,
    stage: PlayOffStage,
    league_matches: list[Match],
    is_tournament_winner: bool,
) -> tuple[str | None, str | None]:
    all_matches = [match for match in league_matches if match.stage_id == stage.id and match.is_played]
    matches = [match for match in all_matches if _team_in_match(team, match)]
    if is_tournament_winner:
        return 'Победитель', None
    if not matches:
        return None, None

    if stage.is_double_elimination():
        place = _double_elimination_place(team, stage, matches)
        if place is not None:
            return _format_place(place), None

    if stage.has_match_for_third_place:
        tournament_winner = next(iter(stage.league.winners.all()), None)
        if tournament_winner:
            winner_matches = [match for match in all_matches if _team_in_match(tournament_winner.winner, match)]
            if winner_matches:
                final = max(winner_matches, key=_match_round_key)
                if _team_in_match(team, final):
                    return '2-е место', None

                third_place_candidates = [
                    match
                    for match in all_matches
                    if not _team_in_match(tournament_winner.winner, match)
                    and _match_round_key(match) >= _match_round_key(final)
                ]
                if third_place_candidates:
                    third_place_match = max(third_place_candidates, key=_match_round_key)
                    if third_place_match.result.winner_id == team.id:
                        return '3-е место', None

    last_match = max(matches, key=_match_round_key)
    tours_total = sum(tour.bracket == last_match.numb_tour.bracket for tour in stage.tours.all())
    result = round_name(last_match.numb_tour, tours_total)
    bracket_name = None
    if stage.is_double_elimination() and last_match.numb_tour.bracket is not None:
        bracket_name = last_match.numb_tour.get_bracket_display()
    return result, bracket_name


def _double_elimination_place(team: Team, stage: PlayOffStage, matches: list[Match]) -> int | None:
    bracket_places = (
        (PlayOffStage.Bracket.UPPER, 2),
        (PlayOffStage.Bracket.LOWER, 3),
    )
    for bracket, place in bracket_places:
        final_tour = max(
            (tour for tour in stage.tours.all() if tour.bracket == bracket),
            key=lambda tour: tour.number,
            default=None,
        )
        if final_tour is None:
            continue
        final_matches = [match for match in matches if match.numb_tour_id == final_tour.id]
        if final_matches and _team_lost_series(team, stage, final_matches):
            return place
    return None


def _team_lost_series(team: Team, stage: PlayOffStage, matches: list[Match]) -> bool:
    opponent = matches[0].opponent_of(team)
    if any(match.opponent_of(team) != opponent for match in matches):
        return False

    series = matches[0].series
    if series is not None and len(series.matches.all()) == len(matches):
        result = series.result
        return result is not None and result['loser'].id == team.id

    if stage.winner_determinator == PlayOffStage.WinnerDeterminator.MATCHES:
        team_score = sum(match.result.winner_id == team.id for match in matches)
        opponent_score = sum(match.result.winner_id == opponent.id for match in matches)
    else:
        team_score = sum(match.scored_by(team) for match in matches)
        opponent_score = sum(match.scored_by(opponent) for match in matches)
    return team_score < opponent_score


def _team_in_match(team: Team, match: Match) -> bool:
    return team.id in (match.team_home_id, match.team_guest_id)


def _match_round_key(match: Match) -> tuple:
    return (match.numb_tour.number, match.match_date or match.numb_tour.date_to, match.id)


def _format_place(place: int) -> str:
    return f'{place}-е место'
