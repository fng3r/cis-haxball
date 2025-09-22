import datetime
from collections import defaultdict
from dataclasses import dataclass
from itertools import groupby
from typing import Iterable

from django import template
from django.contrib.auth.models import User
from django.db.models import Count, Exists, F, FloatField, OuterRef, Prefetch, Q, Subquery
from django.db.models.functions import Cast, Coalesce
from django.db.models.lookups import GreaterThan
from django.utils import timezone

from haxball_site import settings

from ..models import (
    Disqualification,
    FreeAgent,
    Goal,
    Group,
    League,
    Match,
    OtherEvents,
    Player,
    PlayerMatchStatistics,
    PlayerTransfer,
    PlayoffBracketSlotStub,
    PlayOffStage,
    Postponement,
    Season,
    Substitution,
    Team,
    TeamPenaltyPoints,
    TournamentStage,
    TourNumber,
)

register = template.Library()


@register.filter
def user_in_agents(user):
    return FreeAgent.objects.filter(player=user, is_active=True).exists()


@register.filter
def can_add_entry(user):
    try:
        return timezone.now() - user.user_free_agent.created > timezone.timedelta(hours=6)
    except:
        return True


@register.filter
def date_can(user):
    return user.user_free_agent.created + timezone.timedelta(hours=6)


@register.filter
def current_squad_stats(team):
    return get_team_squad_stats(team, for_current_season=True)


@register.filter
def all_time_squad_stats(team):
    return get_team_squad_stats(team, for_current_season=False)


def get_team_squad_stats(team, for_current_season=False, season=None):
    if not season and for_current_season:
        season = Season.objects.filter(is_active=True).first()
    season_condition = Q(match__league__championship=season) if season else ~Q(pk__in=[])

    team_players = get_team_squad(team, for_current_season, season)
    players_matches = {pl: get_player_matches(pl, team, season) for pl in team_players}

    goals_subquery = (
        Goal.objects.filter(season_condition, team=team, author=OuterRef('id'))
        .order_by()
        .values('author')
        .annotate(c=Count('*'))
        .values('c')
    )

    assists_subquery = (
        Goal.objects.filter(season_condition, team=team, assistent=OuterRef('id'))
        .order_by()
        .values('assistent')
        .annotate(c=Count('*'))
        .values('c')
    )

    subs_out_subquery = (
        Substitution.objects.filter(season_condition, team=team, player_out=OuterRef('id'))
        .order_by()
        .values('player_out')
        .annotate(c=Count('*'))
        .values('c')
    )

    subs_in_subquery = (
        Substitution.objects.filter(season_condition, team=team, player_in=OuterRef('id'))
        .order_by()
        .values('player_in')
        .annotate(c=Count('*'))
        .values('c')
    )

    cs_subquery = (
        OtherEvents.objects.cs()
        .filter(season_condition, team=team, author=OuterRef('id'))
        .order_by()
        .values('author')
        .annotate(c=Count('*'))
        .values('c')
    )

    ogs_subquery = (
        OtherEvents.objects.ogs()
        .filter(season_condition, team=team, author=OuterRef('id'))
        .order_by()
        .values('author')
        .annotate(c=Count('*'))
        .values('c')
    )

    yellow_cards_subquery = (
        OtherEvents.objects.yellow_cards()
        .filter(season_condition, team=team, author=OuterRef('id'))
        .order_by()
        .values('author')
        .annotate(c=Count('*'))
        .values('c')
    )

    red_cards_subquery = (
        OtherEvents.objects.red_cards()
        .filter(season_condition, team=team, author=OuterRef('id'))
        .order_by()
        .values('author')
        .annotate(c=Count('*'))
        .values('c')
    )

    players_stats = team_players.annotate(
        goals_c=Coalesce(Subquery(goals_subquery), 0),
        assists_c=Coalesce(Subquery(assists_subquery), 0),
        cs_c=Coalesce(Subquery(cs_subquery), 0),
        ogs_c=Coalesce(Subquery(ogs_subquery), 0),
        subs_out_c=Coalesce(Subquery(subs_out_subquery), 0),
        subs_in_c=Coalesce(Subquery(subs_in_subquery), 0),
        yellow_cards_c=Coalesce(Subquery(yellow_cards_subquery), 0),
        red_cards_c=Coalesce(Subquery(red_cards_subquery), 0),
    ).select_related('name__user_profile', 'player_nation')

    for player in players_stats:
        player.__setattr__('matches_c', players_matches[player])

    if not for_current_season and season is None:
        players_stats = list(filter(lambda stats: stats.matches_c > 0, players_stats))

    return sorted(players_stats, key=lambda player: player.matches_c, reverse=True)


def get_team_squad(team, current=False, season=None):
    if current:
        return team.players_in_team.all()

    season_condition = Q(season_join=season) if season else ~Q(season_join__in=[])

    return Player.objects.filter(
        Exists(PlayerTransfer.objects.filter(season_condition, to_team=team, trans_player=OuterRef('id')))
    )


def get_player_matches(player, team, season=None):
    season_condition = Q(league__championship=season) if season else ~Q(pk__in=[])

    return PlayerMatchStatistics.objects.filter(
        season_condition,
        player=player,
        team=team,
        match__is_played=True,
    ).count()


@register.filter
def team_stats_rows_count(stats: defaultdict, season):
    return len(stats[season])


@register.filter
def player_stats_rows_count(stats: defaultdict, season):
    count = 0
    for team in stats[season]:
        count += len(stats[season][team])

    return count


#   Для детальной статы матча
@register.filter
def events_sorted(match: Match):
    events = match.match_event.select_related('team', 'author').all()
    substitutions = match.match_substitutions.select_related('team', 'player_in', 'player_out').all()
    all_events = list(match.match_goal.select_related('team', 'author', 'assistent').all())
    for e in events:
        all_events.append(e)
    for s in substitutions:
        all_events.append(s)

    sorted_events = sorted(all_events, key=lambda event: datetime.time(minute=event.time_min, second=event.time_sec))
    events_by_time = {'first_time': [], 'second_time': [], 'extra_time': []}
    for event in sorted_events:
        if event.time_min < 8 or event.time_min == 8 and event.time_sec == 0:
            events_by_time['first_time'].append(event)
        elif event.time_min < 16 or event.time_min == 16 and event.time_sec == 0:
            events_by_time['second_time'].append(event)
        else:
            events_by_time['extra_time'].append(event)
    return events_by_time


@register.inclusion_tag('tournament/tournament/partials/cup_bracket.html')
def cup_bracket(stage, bracket):
    tours = bracket_tours(stage.tours, bracket)
    slots = get_slots_by_tours(tours)
    return {
        'stage': stage,
        'tours': tours,
        'slots_by_tour': slots,
        'bracket': bracket,
        'bracket_types': PlayOffStage.Bracket,
    }


@register.filter
def group_matches(matches):
    matches_by_group = {}
    for match in matches:
        if match.group not in matches_by_group:
            matches_by_group[match.group] = []
        matches_by_group[match.group].append(match)

    return matches_by_group


@register.filter
def bracket_tours(tours, bracket):
    return [tour for tour in tours.all() if tour.bracket == bracket]


@register.filter
def tours_ordered_by_date(tours, bracket):
    return tours.filter(bracket=bracket)


def get_bracket_slots(tours):
    if len(tours) == 0:
        return []

    bracket = tours[0].bracket
    stage = tours[0].stage
    slots = []
    if bracket == PlayOffStage.Bracket.UPPER or stage.has_match_for_third_place:
        slots = [1] + [2 ** (tour.number - 1) for tour in tours][:-1]
    elif bracket == PlayOffStage.Bracket.LOWER:
        slots = [2 ** (tour.number - tour.number // 2 - 1) for tour in tours]
    elif bracket is None:
        slots = [2 ** (tour.number - 1) for tour in tours]

    return slots[::-1]


@dataclass
class BracketSlot:
    number: int
    pair: tuple[Team, Team]
    matches: Iterable[Match]
    stub: PlayoffBracketSlotStub
    label: str | None = None

    def is_empty(self):
        return self.pair is None and self.stub is None


@register.filter
def pairs_in_tour(tour):
    pairs = {}
    for match in tour.tour_matches.all():
        pair = frozenset((match.team_home, match.team_guest))
        if pair not in pairs:
            pairs[pair] = []
        pairs[pair].append(match)

    return {
        # there's guaranteed to be at least one match per pair
        (matches[0].team_home, matches[0].team_guest): matches
        for pair, matches in sorted(pairs.items(), key=lambda x: min(m.id for m in x[1]))
    }


def get_slots_by_tours(tours):
    slots_by_tour = {}
    count = 1
    for tour in tours:
        slots = get_tour_slots(tour, tours)
        bracket = tour.bracket
        match bracket:
            case PlayOffStage.Bracket.UPPER:
                bracket_prefix = 'U'
            case PlayOffStage.Bracket.LOWER:
                bracket_prefix = 'L'
            case _:
                bracket_prefix = ''

        for slot in slots:
            if tour.number > 1 or not slot.is_empty():
                slot.label = f'{bracket_prefix}{count}'
                count += 1
        slots_by_tour[tour] = slots

    return slots_by_tour.items()


def get_tour_slots(tour, tours):
    pairs = pairs_in_tour(tour)
    stubs = list(tour.stubs.all())
    slots_count = get_bracket_slots(tours)[tour.number - 1]
    slots = []
    for slot in range(1, slots_count + 1):
        pair, matches = get_pair_in_slot(pairs, slot)
        stub = get_slot_stub(stubs, slot)
        slots.append(BracketSlot(slot, pair, matches, stub))

    return slots


def get_pair_in_slot(pairs, slot):
    for pair in pairs:
        matches = pairs[pair]
        if any(match.bracket_slot == slot for match in matches):
            return pair, matches

    return None, None


def get_slot_stub(stubs, slot):
    return next((stub for stub in stubs if stub.slot == slot), None)


@register.filter
def has_more_slots_than_next_round(tour, tours):
    slots = get_bracket_slots(tours)
    if tour.number >= len(slots):
        return False

    current_round_slots = slots[tour.number - 1]
    next_round_slots = slots[tour.number]

    return current_round_slots > next_round_slots


@register.filter
def show_connector(tour: TourNumber, tours: Iterable[TourNumber]):
    tours_total = len(tours)
    # since match for third place played in extra tour, ignore that tour
    if tour.stage.has_match_for_third_place:
        tours_total -= 1

    return tour.number < tours_total


@register.filter
def connector_line_height(tour: TourNumber, tours: Iterable[TourNumber]):
    pair_height = 64
    initial_gap = 24

    if tour.number == len(tours) or not has_more_slots_than_next_round(tour, tours):
        return 0

    tour_number = 1
    gap = initial_gap
    slots = get_bracket_slots(tours)
    while tour_number < tour.number:
        current_round_slots = slots[tour_number - 1]
        next_round_slots = slots[tour_number]
        if current_round_slots > next_round_slots:
            gap = pair_height + 2 * gap
        tour_number += 1

    return (pair_height + gap) // 2


def has_match_for_third_place(league):
    return (
        league.title.startswith('Лига Чемпионов')
        and league.championship.number < 12
        or league.title.startswith('Итоговый турнир')
    )


@register.filter
def team_score_in_match(team, match):
    if team == match.team_home:
        return match.score_home
    if team == match.team_guest:
        return match.score_guest
    return None


@register.filter
def is_match_winner(team, match):
    return match.is_win(team)


@register.simple_tag
def get_series_result(teams, matches):
    if not all((match.is_played for match in matches)):
        return None

    team1, team2 = teams
    team1_series_score = 0
    team2_series_score = 0
    for match in matches:
        team1_score = team_score_in_match(team1, match)
        team2_score = team_score_in_match(team2, match)
        winner_determinator = match.stage.winner_determinator
        if winner_determinator == PlayOffStage.WinnerDeterminator.GOALS:
            team1_series_score += team1_score
            team2_series_score += team2_score
        elif winner_determinator == PlayOffStage.WinnerDeterminator.MATCHES:
            if team1_score > team2_score:
                team1_series_score += 1
            elif team2_score > team1_score:
                team2_series_score += 1

    if team1_series_score == team2_series_score:
        return None

    if team1_series_score > team2_series_score:
        winner, loser = team1, team2
    else:
        winner, loser = team2, team1

    return {'winner': winner, 'loser': loser}


@register.filter
def tour_name(tour: TourNumber):
    if tour.name:
        return tour.name

    return f'{tour.number} тур'


@register.filter
def round_name(tour, tours_total):
    if tour.name:
        return tour.name

    # since match for third place played in extra tour, ignore that tour
    if tour.stage.is_playoff and tour.stage.has_match_for_third_place:
        tours_total -= 1

    if tour.number == tours_total:
        return 'Финал'
    if tour.number == tours_total - 1:
        return '1/2 Финала'
    if tour.number == tours_total - 2:
        return '1/4 Финала'
    if tour.number == tours_total - 3:
        return '1/8 Финала'

    return f'{tour.number} Раунд'


@register.filter
def cup_round_name(tour: TourNumber):
    return round_name(tour, tour.stage.tours.filter(bracket=tour.bracket).count())


@register.inclusion_tag('tournament/tournament/partials/tournament_table.html')
def tournament_table(league: League, stage: TournamentStage, group: Group | None):
    table = get_league_table(league, stage, group)
    has_penalties = any(x[10] > 0 for x in table)
    return {'teams': table, 'stage': stage, 'has_penalties': has_penalties}


# Конец тегов и фильтров для таблицы лиги


@register.filter
def top_goalscorers(league: League):
    return (
        Player.objects.select_related('team', 'name__user_profile')
        .filter(goals__match__league=league)
        .annotate(count=Count('goals'), last_team_logo=get_player_last_team_logo_subquery(league))
        .order_by('-count')
    )


@register.filter
def top_goalscorers_per_match(league: League):
    return (
        Player.objects.select_related('team', 'name__user_profile')
        .filter(
            Exists(PlayerMatchStatistics.objects.filter(player=OuterRef('id'), league=league)),
            goals__match__league=league,
        )
        .annotate(
            goals_count=Count('goals'),
            matches_count=Coalesce(get_player_matches_subquery(league), 0),
            count=Cast(F('goals_count'), FloatField()) / F('matches_count'),
            last_team_logo=get_player_last_team_logo_subquery(league),
        )
        .filter(count__gt=0, matches_count__gte=3)
        .order_by('-count')
    )


@register.filter
def top_assistants(league: League):
    return (
        Player.objects.select_related('team', 'name__user_profile')
        .filter(assists__match__league=league)
        .annotate(
            count=Count('assists'),
            last_team_logo=get_player_last_team_logo_subquery(league),
        )
        .order_by('-count')
    )


@register.filter
def top_assistants_per_match(league: League):
    return (
        Player.objects.select_related('team', 'name__user_profile')
        .filter(
            Exists(PlayerMatchStatistics.objects.filter(player=OuterRef('id'), league=league)),
            assists__match__league=league,
        )
        .annotate(
            assists_count=Count('assists'),
            matches_count=Coalesce(get_player_matches_subquery(league), 0),
            count=Cast(F('assists_count'), FloatField()) / F('matches_count'),
            last_team_logo=get_player_last_team_logo_subquery(league),
        )
        .filter(count__gt=0, matches_count__gte=3)
        .order_by('-count')
    )


def _get_player_goals_assists_data(league: League):
    goals_data = (
        Goal.objects.filter(match__league=league, author__isnull=False)
        .values('author')
        .annotate(goals_count=Count('id'))
    )
    goals_lookup = {data['author']: data['goals_count'] for data in goals_data}

    assists_data = (
        Goal.objects.filter(match__league=league, assistent__isnull=False)
        .values('assistent')
        .annotate(assists_count=Count('id'))
    )
    assists_lookup = {data['assistent']: data['assists_count'] for data in assists_data}

    matches_data = (
        PlayerMatchStatistics.objects.filter(league=league)
        .values('player')
        .annotate(matches_count=Count('id', distinct=True))
    )
    matches_lookup = {data['player']: data['matches_count'] for data in matches_data}

    return goals_lookup, assists_lookup, matches_lookup


@register.filter
def top_goals_assists(league: League):
    goals_lookup, assists_lookup, matches_lookup = _get_player_goals_assists_data(league)

    players = (
        Player.objects.select_related('team', 'name__user_profile')
        .filter(id__in=matches_lookup.keys())
        .annotate(last_team_logo=get_player_last_team_logo_subquery(league))
    )

    result = []
    for player in players:
        goals_count = goals_lookup.get(player.id, 0)
        assists_count = assists_lookup.get(player.id, 0)
        matches_count = matches_lookup.get(player.id, 0)
        total_count = goals_count + assists_count

        if total_count > 0 and matches_count > 0:
            player.goals_count = goals_count
            player.assists_count = assists_count
            player.matches_count = matches_count
            player.count = total_count
            result.append(player)

    return sorted(result, key=lambda x: x.count, reverse=True)


@register.filter
def top_goals_assists_per_match(league: League):
    goals_lookup, assists_lookup, matches_lookup = _get_player_goals_assists_data(league)

    players = (
        Player.objects.select_related('team', 'name__user_profile')
        .filter(id__in=matches_lookup.keys())
        .annotate(last_team_logo=get_player_last_team_logo_subquery(league))
    )

    result = []
    for player in players:
        goals_count = goals_lookup.get(player.id, 0)
        assists_count = assists_lookup.get(player.id, 0)
        matches_count = matches_lookup.get(player.id, 0)

        if matches_count >= 3:
            total_count = goals_count + assists_count
            if total_count > 0:
                player.goals_count = goals_count
                player.assists_count = assists_count
                player.matches_count = matches_count
                player.count = float(total_count) / matches_count
                result.append(player)

    return sorted(result, key=lambda x: x.count, reverse=True)


@register.filter
def top_clean_sheets(league: League):
    return (
        Player.objects.select_related('team', 'name__user_profile')
        .filter(event__match__league=league, event__event='CLN')
        .annotate(
            count=Count('event__match__league'),
            last_team_logo=get_player_last_team_logo_subquery(league),
        )
        .order_by('-count')
    )


@register.filter
def top_clean_sheets_per_match(league: League):
    return (
        Player.objects.select_related('team', 'name__user_profile')
        .filter(event__match__league=league, event__event='CLN')
        .annotate(
            cs_count=Count('event__match__league'),
            matches_count=Coalesce(get_player_matches_subquery(league), 0),
            count=Cast(F('cs_count'), FloatField()) / F('matches_count'),
            last_team_logo=get_player_last_team_logo_subquery(league),
        )
        .filter(matches_count__gte=3)
        .order_by('-count')
    )


@register.filter
def top_yellow_cards(league: League):
    return (
        Player.objects.select_related('team', 'name__user_profile')
        .filter(event__match__league=league, event__event='YEL')
        .annotate(
            count=Count('event__match__league'),
            last_team_logo=get_player_last_team_logo_subquery(league),
        )
        .order_by('-count')
    )


@register.filter
def top_yellow_cards_per_match(league: League):
    return (
        Player.objects.select_related('team', 'name__user_profile')
        .filter(
            Exists(PlayerMatchStatistics.objects.filter(player=OuterRef('id'), league=league)),
            event__match__league=league,
            event__event='YEL',
        )
        .annotate(
            yellow_cards_count=Count('event__match__league'),
            matches_count=Coalesce(get_player_matches_subquery(league), 0),
            count=Cast(F('yellow_cards_count'), FloatField()) / F('matches_count'),
            last_team_logo=get_player_last_team_logo_subquery(league),
        )
        .order_by('-count')
    )


@register.filter
def top_red_cards(league: League):
    return (
        Player.objects.select_related('team', 'name__user_profile')
        .filter(event__match__league=league, event__event='RED')
        .annotate(
            count=Count('event__match__league'),
            last_team_logo=get_player_last_team_logo_subquery(league),
        )
        .order_by('-count')
    )


@register.filter
def top_red_cards_per_match(league: League):
    return (
        Player.objects.select_related('team', 'name__user_profile')
        .filter(
            Exists(PlayerMatchStatistics.objects.filter(player=OuterRef('id'), league=league)),
            event__match__league=league,
            event__event='RED',
        )
        .annotate(
            red_cards_count=Count('event__match__league'),
            matches_count=Coalesce(get_player_matches_subquery(league), 0),
            count=Cast(F('red_cards_count'), FloatField()) / F('matches_count'),
            last_team_logo=get_player_last_team_logo_subquery(league),
        )
        .order_by('-count')
    )


def get_player_last_team_logo_subquery(league: League):
    return Subquery(
        PlayerTransfer.objects.filter(
            trans_player=OuterRef('id'),
            season_join=league.championship,
            to_team__leagues=league,
        )
        .values('to_team__logo')
        .order_by('-date_join')[:1]
    )


def get_player_matches_subquery(league: League):
    return Subquery(
        PlayerMatchStatistics.objects.filter(player=OuterRef('id'), league=league)
        .order_by()
        .values('player')
        .annotate(c=Count('id', distinct=True))
        .values('c')
    )


def get_player_goals_subquery(league: League):
    return Subquery(
        Goal.objects.filter(author=OuterRef('id'), match__league=league)
        .order_by()
        .values('author')
        .annotate(c=Count('id', distinct=True))
        .values('c')
    )


def get_player_assists_subquery(league: League):
    return Subquery(
        Goal.objects.filter(assistent=OuterRef('id'), match__league=league)
        .order_by()
        .values('assistent')
        .annotate(c=Count('id', distinct=True))
        .values('c')
    )


@register.simple_tag
def team_seasons(team):
    return (
        Season.objects.filter(tournaments_in_season__teams=team)
        .distinct()
        .prefetch_related(
            Prefetch(
                'tournaments_in_season',
                queryset=League.objects.filter(teams=team)
                .prefetch_related(
                    Prefetch(
                        'stages',
                        queryset=TournamentStage.objects.filter(teams=team)
                        .distinct()
                        .prefetch_related(
                            'tours__league',
                            Prefetch(
                                'matches',
                                queryset=Match.objects.filter(Q(team_home=team) | Q(team_guest=team))
                                .select_related('team_home', 'team_guest', 'numb_tour__league')
                                .prefetch_related('numb_tour__stage')
                                .order_by('numb_tour'),
                                to_attr='team_matches',
                            ),
                        )
                        .order_by('order'),
                    ),
                )
                .annotate(has_multiple_stages=GreaterThan(Coalesce(Count('stages'), 0), 1))
                .order_by('-id'),
                to_attr='team_leagues',
            ),
        )
        .order_by('-number')
    )


@register.simple_tag
def player_seasons(player):
    return (
        Season.objects.filter(
            Exists(PlayerMatchStatistics.objects.filter(player=player, league__championship=OuterRef('id')))
        )
        .prefetch_related(
            Prefetch(
                'tournaments_in_season',
                queryset=League.objects.filter(
                    Exists(PlayerMatchStatistics.objects.filter(player=player, league=OuterRef('id')))
                )
                .prefetch_related(
                    Prefetch(
                        'stages',
                        queryset=TournamentStage.objects.filter(
                            Exists(PlayerMatchStatistics.objects.filter(player=player, match__stage=OuterRef('id')))
                        )
                        .distinct()
                        .prefetch_related(
                            'tours__league',
                            Prefetch(
                                'matches',
                                queryset=Match.objects.filter(
                                    Exists(PlayerMatchStatistics.objects.filter(player=player, match=OuterRef('id'))),
                                    is_played=True,
                                )
                                .select_related('team_home', 'team_guest', 'numb_tour__league')
                                .prefetch_related('numb_tour__stage')
                                .annotate(
                                    player_team_id=Subquery(
                                        PlayerMatchStatistics.objects.filter(
                                            player=player,
                                            match=OuterRef('id'),
                                        ).values('team')[:1]
                                    )
                                )
                                .order_by('numb_tour'),
                                to_attr='player_matches',
                            ),
                        )
                        .order_by('order'),
                    ),
                )
                .annotate(has_multiple_stages=GreaterThan(Coalesce(Count('stages'), 0), 1))
                .order_by('-id'),
                to_attr='player_leagues',
            ),
        )
        .order_by('-number')
    )


@register.simple_tag
def player_transfers_by_season(player):
    transfers = (
        PlayerTransfer.objects.filter(trans_player=player, is_technical=False)
        .select_related('from_team', 'to_team', 'season_join', 'trans_player__name__user_profile')
        .order_by('-date_join')
    )
    return {season: list(transfers) for season, transfers in groupby(transfers, lambda x: x.season_join)}


def sort_teams(league: League):
    lt = get_league_table(league)
    return [i[0] for i in lt]


def get_league_table(league: League, stage: TournamentStage = None, group: Group = None):
    always_true = ~Q(pk__in=[])
    stage_condition = Q(stages=stage) if stage is not None else always_true
    group_condition = Q(groups=group) if group is not None else always_true
    teams = list(Team.objects.filter(stage_condition, group_condition, leagues=league))
    teams_count = len(teams)

    points = [0 for _ in range(teams_count)]  # Количество очков
    penalties = [0 for _ in range(teams_count)]  # Количество очков
    goal_diff = [0 for _ in range(teams_count)]  # Разница мячей
    scored = [0 for _ in range(teams_count)]  # Мячей забито
    conceded = [0 for _ in range(teams_count)]  # Мячей пропущено
    matches_played = [0 for _ in range(teams_count)]  # Игр сыграно
    wins = [0 for _ in range(teams_count)]  # Побед
    draws = [0 for _ in range(teams_count)]  # Ничей
    losses = [0 for _ in range(teams_count)]  # Поражений
    last_matches = [[] for _ in range(teams_count)]
    teams_indexes = {}
    opponents_by_team = defaultdict(list)
    for i, team in enumerate(teams):
        teams_indexes[team] = i
        matches = Match.objects.select_related('team_home', 'team_guest', 'result__winner', 'numb_tour').filter(
            Q(team_home=team) | Q(team_guest=team),
            league=league,
            stage=stage,
            group=group,
            is_played=True,
        )
        matches_played[i] = matches.count()
        penalty = TeamPenaltyPoints.objects.filter(stage=stage, team=team).first()
        penalty_points = penalty.penalty_points if penalty else 0

        wins_count = 0
        draws_count = 0
        losses_count = 0
        goals_scored = 0
        goals_conceded = 0
        for match in matches:
            goals_scored += match.scored_by(team)
            goals_conceded += match.conceded_by(team)

            if match.is_win(team):
                wins_count += 1
                last_matches[i].append((match, 1))
            elif match.is_draw():
                draws_count += 1
                last_matches[i].append((match, 0))
            else:
                losses_count += 1
                last_matches[i].append((match, -1))

            if team == match.team_home:
                opponents_by_team[team].append(match.team_guest)
            elif team == match.team_guest:
                opponents_by_team[team].append(match.team_home)

        last_matches[i] = sorted(last_matches[i], key=lambda x: x[0].numb_tour.number)[-5:]
        points[i] = wins_count * 3 + draws_count * 1 - penalty_points
        penalties[i] = penalty_points
        goal_diff[i] = goals_scored - goals_conceded
        scored[i] = goals_scored
        conceded[i] = goals_conceded
        wins[i] = wins_count
        losses[i] = losses_count
        draws[i] = draws_count

    if stage is not None and stage.use_buchholz:
        buccholz = [0 for _ in range(teams_count)]
        for i, team in enumerate(teams):
            for opponent in opponents_by_team[team]:
                opponent_index = teams_indexes[opponent]
                buccholz[i] += points[opponent_index]

        table = zip(
            teams,
            matches_played,
            wins,
            draws,
            losses,
            scored,
            conceded,
            goal_diff,
            points,
            last_matches,
            penalties,
            buccholz,
        )
        return sorted(table, key=lambda x: (x[8], x[11], x[7], x[5]), reverse=True)

    table = zip(
        teams, matches_played, wins, draws, losses, scored, conceded, goal_diff, points, last_matches, penalties
    )
    sorted_table = sorted(table, key=lambda x: (x[8], x[7], x[5]), reverse=True)
    result = []
    i = 0
    while i < len(sorted_table) - 1:
        mini_table = [sorted_table[i][0]]
        mini_res = [sorted_table[i]]
        k = i
        for j in range(i + 1, len(sorted_table)):
            if sorted_table[i][8] == sorted_table[j][8]:
                mini_table.append(sorted_table[j][0])
                mini_res.append(sorted_table[j])
                k += 1
            else:
                k += 1
                break
        if len(mini_table) >= 2:
            teams_count = len(mini_table)
            points = [0 for _ in range(teams_count)]  # Количество очков
            goal_diff = [0 for _ in range(teams_count)]  # Разница мячей
            scored = [0 for _ in range(teams_count)]  # Мячей забито
            conceded = [0 for _ in range(teams_count)]  # Мячей пропущено
            matches_played = [0 for _ in range(teams_count)]  # Игр сыграно
            wins = [0 for _ in range(teams_count)]  # Побед
            draws = [0 for _ in range(teams_count)]  # Ничей
            losses = [0 for _ in range(teams_count)]  # Поражений
            for i, team in enumerate(mini_table):
                matches = []
                matches_all = Match.objects.select_related(
                    'team_home', 'team_guest', 'result__winner', 'numb_tour'
                ).filter(
                    Q(team_home=team) | Q(team_guest=team),
                    league=league,
                    is_played=True,
                )
                for match in matches_all:
                    if (match.team_home in mini_table) and (match.team_guest in mini_table):
                        matches.append(match)
                matches_played[i] = len(matches)

                wins_count = 0
                draws_count = 0
                losses_count = 0
                goals_scored = 0
                goals_conceded = 0
                for match in matches:
                    goals_scored += match.scored_by(team)
                    goals_conceded += match.conceded_by(team)

                    if match.is_win(team):
                        wins_count += 1
                    elif match.is_draw():
                        draws_count += 1
                    else:
                        losses_count += 1
                points[i] = wins_count * 3 + draws_count * 1
                goal_diff[i] = goals_scored - goals_conceded
                scored[i] = goals_scored
                conceded[i] = goals_conceded
                wins[i] = wins_count
                losses[i] = losses_count
                draws[i] = draws_count
            table = zip(mini_table, matches_played, wins, draws, losses, scored, conceded, goal_diff, points)
            lss = sorted(table, key=lambda x: (x[8], x[7], x[5]), reverse=True)
            for lll in lss:
                for h in mini_res:
                    if lll[0] == h[0]:
                        result.append(h)
                        break
        else:
            result.append(mini_res[0])
        i = k

    if len(result) < len(sorted_table):
        result.append(sorted_table[len(sorted_table) - 1])

    return result


@register.filter
def current_league(team):
    primary_leagues = ['Высшая лига', 'Первая лига', 'Вторая лига']
    primary_league = League.objects.filter(teams=team, title__in=primary_leagues, championship__is_active=True).first()

    if primary_league is not None:
        return primary_league

    return League.objects.filter(teams=team, championship__is_active=True).first()


@register.filter
def current_position(team):
    league = current_league(team)
    if not league:
        return '-'

    teams = list(league.teams.all())
    if team not in teams:
        return '-'

    sorted_teams = list(sort_teams(league))
    return sorted_teams.index(team) + 1


@register.inclusion_tag('core/include/teams_in_navbar.html')
def teams_in_navbar():
    primary_leagues = ['Высшая лига', 'Первая лига', 'Вторая лига', 'Лига Чемпионов', 'Итоговый турнир']
    leagues = (
        League.objects.filter(title__in=primary_leagues, championship__is_active=True)
        .prefetch_related(Prefetch('teams', queryset=Team.objects.order_by('title')))
        .annotate(teams_count=Count('teams'))
        .filter(teams_count__gt=0)
        .order_by('priority')
    )

    if leagues:
        return {'leagues': leagues}

    all_teams = Team.objects.filter(leagues__championship__is_active=True).order_by('title')
    return {'leagues': leagues, 'all_teams': all_teams}


@register.filter
def team_achievements_by_season(team):
    achievements = team.achievements.select_related('season').all()
    achievements_by_season = dict()
    for achievement in achievements:
        season = achievement.season
        if season not in achievements_by_season:
            achievements_by_season[season] = list()
        achievements_by_season[season].append(achievement)

    return achievements_by_season.items()


@register.filter
def team_squad_in_season(season_achievements):
    if len(season_achievements) > 0:
        return season_achievements[0].players_raw_list

    return ''


@register.filter
def event_time(event: OtherEvents):
    return datetime.time(minute=event.time_min, second=event.time_sec).strftime('%M:%S')


@register.filter
def goal_time(goal: Goal):
    return datetime.time(minute=goal.time_min, second=goal.time_sec).strftime('%M:%S')


@register.filter
def card_name(card: OtherEvents):
    if card.event == OtherEvents.YELLOW_CARD:
        return 'желтая карточка'
    if card.event == OtherEvents.RED_CARD:
        return 'красная карточка'
    return ''


@register.filter
def get_lifted_string(disqualification: Disqualification):
    tours = disqualification.tours.all()
    lifted_tours = disqualification.lifted_tours.all()
    if len(lifted_tours) == 0:
        return 'Нет'

    diff = set(tours).difference(set(lifted_tours))
    if len(diff) == 0:
        return 'Да'

    return 'Частично\n' + '\n'.join(map(lambda t: str(t), diff))


@register.filter
def postponements_in_league(team: Team, league: League) -> list[Postponement | None]:
    postponements = team.get_postponements(league)
    league_slots = league.get_postponement_slots()
    common_slots_count = league_slots.common_count
    total_slots_count = league_slots.total_count
    slots = [None for _ in range(1, total_slots_count + 1)]

    common_count = 0
    emergency_count = 0
    for postponement in postponements:
        if postponement.is_emergency:
            slots[common_slots_count + emergency_count] = postponement
            emergency_count += 1
        else:
            if common_count < common_slots_count:
                slots[common_count] = postponement
                common_count += 1
            else:
                slots[common_slots_count + emergency_count] = postponement
                emergency_count += 1

    return slots


@register.filter
def can_be_cancelled_by_user(postponement: Postponement, user: User):
    if not postponement.can_be_cancelled:
        return False

    user_teams = get_user_teams(user)

    return postponement.match.team_home in user_teams or postponement.match.team_guest in user_teams


@register.inclusion_tag('tournament/postponements/postponements_form.html')
def postponements_form(user: User, league: League):
    teams = get_user_teams(user)

    # Выбираем все матчи игрока, которые уже можно играть, но которые еще не были сыграны
    matches = Match.objects.filter(
        Q(team_home__in=teams) | Q(team_guest__in=teams),
        league=league,
        is_played=False,
        numb_tour__date_from__lte=timezone.localdate(),
    )
    available_matches = [match for match in matches if match.can_be_postponed]

    return {
        'matches': available_matches,
        'user': user,
        'league': league,
    }


def get_user_teams(user: User):
    try:
        player = user.user_player
    except:
        return []
    teams = []
    current_team = player.team
    if current_team is not None and (player == current_team.captain or player == current_team.captain_assistant):
        teams.append(current_team)

    owned_teams = Team.objects.filter(owner=user, leagues__championship__is_active=True)
    for team in owned_teams:
        teams.append(team)

    return teams


@register.filter
def ru_pluralize(value, variants):
    variants = variants.split(',')
    value = abs(int(value))

    if value % 10 == 1 and value % 100 != 11:
        variant = 0
    elif 2 <= value % 10 <= 4 and not (12 <= value % 100 <= 14):
        variant = 1
    else:
        variant = 2

    return variants[variant]


@register.filter
def previous_rating_rank(team, previous_rating):
    if team not in previous_rating:
        return None

    return previous_rating[team]


@register.simple_tag
def get_season_rating(team, season, seasons_rating):
    if team not in seasons_rating[season]:
        return None

    return seasons_rating[season][team]


@register.filter
def get_season_weight(season, seasons_weights):
    return seasons_weights[season]


@register.filter
def dd_items(dictionary: defaultdict):
    return dictionary.items()


@register.filter
def sorted_by_season(dictionary: defaultdict):
    return sorted(dictionary.items(), key=lambda item: item[0].number)


@register.filter
def sorted_by_league(dictionary: defaultdict):
    return sorted(dictionary.items(), key=lambda item: item[0].id)


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.simple_tag
def stats_percentage(stat1, stat2):
    sum = stat1 + stat2
    if sum == 0:
        percentage1 = 0
        percentage2 = 0
    else:
        percentage1 = round(float(stat1) / sum * 100)
        percentage2 = round(float(stat2) / sum * 100)

    return percentage1, percentage2


@register.filter
def user_teams(user: User):
    if not settings.SHOW_USER_TEAM_ICONS:
        return []

    teams = []
    try:
        player = user.user_player
    except:
        player = None

    current_team = None
    if player and player.team:
        player_titles = []
        current_team = player.team
        if user == current_team.owner:
            player_titles.append('Владелец')

        if player == current_team.captain:
            player_titles.append('Капитан')
        elif player == current_team.captain_assistant:
            player_titles.append('Ассистент капитана')
        else:
            player_titles.append('Игрок')

        teams.append(
            {
                'team': player.team,
                'titles': f'{"/".join(player_titles)} команды {player.team}',
            }
        )

    if hasattr(user, 'active_owned_teams'):
        active_owned_teams = user.active_owned_teams
    else:
        active_owned_teams = Team.objects.filter(owner=user, leagues__championship__is_active=True).distinct()
    for owned_team in active_owned_teams:
        if owned_team != current_team:
            teams.append({'team': owned_team, 'titles': f'Владелец команды {owned_team}'})

    return teams


@register.filter
def grade_class(grade):
    """Convert grade to CSS class name for styling"""
    grade_lower = grade.lower()
    if grade_lower == 'b+':
        return 'b-plus'
    return grade_lower
