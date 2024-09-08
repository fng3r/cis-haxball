import datetime
from collections import defaultdict
from typing import Optional

from django import template
from django.contrib.auth.models import User
from django.db.models import Count, Exists, F, OuterRef, Prefetch, Q, QuerySet, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from ..models import (
    Disqualification,
    FreeAgent,
    Goal,
    League,
    Match,
    MatchResult,
    OtherEvents,
    Player,
    PlayerTransfer,
    Postponement,
    Season,
    Substitution,
    Team,
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


def get_team_squad_stats(team, for_current_season=False):
    team_players = get_team_players(team, for_current_season)
    players_matches = {pl: get_player_matches(pl, team, for_current_season) for pl in team_players}

    current_season_condition = Q(match__league__championship__is_active=True) if for_current_season else ~Q(pk__in=[])

    goals_subquery = (
        Goal.objects.filter(current_season_condition, team=team, author=OuterRef('id'))
        .order_by()
        .values('author')
        .annotate(c=Count('*'))
        .values('c')
    )

    assists_subquery = (
        Goal.objects.filter(current_season_condition, team=team, assistent=OuterRef('id'))
        .order_by()
        .values('assistent')
        .annotate(c=Count('*'))
        .values('c')
    )

    subs_out_subquery = (
        Substitution.objects.filter(current_season_condition, team=team, player_out=OuterRef('id'))
        .order_by()
        .values('player_out')
        .annotate(c=Count('*'))
        .values('c')
    )

    subs_in_subquery = (
        Substitution.objects.filter(current_season_condition, team=team, player_in=OuterRef('id'))
        .order_by()
        .values('player_in')
        .annotate(c=Count('*'))
        .values('c')
    )

    cs_subquery = (
        OtherEvents.objects.cs()
        .filter(current_season_condition, team=team, author=OuterRef('id'))
        .order_by()
        .values('author')
        .annotate(c=Count('*'))
        .values('c')
    )

    ogs_subquery = (
        OtherEvents.objects.ogs()
        .filter(current_season_condition, team=team, author=OuterRef('id'))
        .order_by()
        .values('author')
        .annotate(c=Count('*'))
        .values('c')
    )

    yellow_cards_subquery = (
        OtherEvents.objects.yellow_cards()
        .filter(current_season_condition, team=team, author=OuterRef('id'))
        .order_by()
        .values('author')
        .annotate(c=Count('*'))
        .values('c')
    )

    red_cards_subquery = (
        OtherEvents.objects.red_cards()
        .filter(current_season_condition, team=team, author=OuterRef('id'))
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

    if not for_current_season:
        players_stats = list(filter(lambda stats: stats.matches_c > 0, players_stats))

    return sorted(players_stats, key=lambda player: player.matches_c, reverse=True)


def get_team_players(team, current=False):
    if current:
        return team.players_in_team.all()

    return Player.objects.filter(Exists(PlayerTransfer.objects.filter(to_team=team, trans_player=OuterRef('id'))))


def get_player_matches(player, team, for_current_season=False):
    current_season_condition = Q(league__championship__is_active=True) if for_current_season else ~Q(pk__in=[])

    return (
        Match.objects.filter(current_season_condition, team_guest=team, team_guest_start=player, is_played=True).count()
        + Match.objects.filter(current_season_condition, team_home=team, team_home_start=player, is_played=True).count()
        + Match.objects.filter(
            current_season_condition,
            ~(Q(team_guest_start=player) | Q(team_home_start=player)),
            is_played=True,
            match_substitutions__team=team,
            match_substitutions__player_in=player,
        )
        .distinct()
        .count()
    )


@register.inclusion_tag('tournament/include/team_statistics.html')
def team_statistics(team: Team):
    prefetches = (
        Prefetch('match_goal', queryset=Goal.objects.filter(team=team, match__is_played=True), to_attr='goals'),
        Prefetch(
            'match_goal', queryset=Goal.objects.filter(~Q(team=team), match__is_played=True), to_attr='conceded_goals'
        ),
        Prefetch(
            'match_goal',
            queryset=Goal.objects.filter(team=team, assistent__isnull=False, match__is_played=True),
            to_attr='assists',
        ),
        Prefetch(
            'match_event', queryset=OtherEvents.objects.cs().filter(team=team, match__is_played=True), to_attr='cs'
        ),
        Prefetch('match_event', queryset=Substitution.objects.filter(team=team, match__is_played=True), to_attr='subs'),
        Prefetch(
            'match_event', queryset=OtherEvents.objects.ogs().filter(team=team, match__is_played=True), to_attr='ogs'
        ),
        Prefetch(
            'match_event',
            queryset=OtherEvents.objects.yellow_cards().filter(team=team, match__is_played=True),
            to_attr='yellow_cards',
        ),
        Prefetch(
            'match_event',
            queryset=OtherEvents.objects.red_cards().filter(team=team, match__is_played=True),
            to_attr='red_cards',
        ),
    )

    all_matches = (
        Match.objects.filter(Q(team_home=team) | Q(team_guest=team), is_played=True)
        .select_related('league__championship', 'result__winner')
        .prefetch_related(*prefetches)
    )

    stats_by_season = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for match in all_matches:
        league = match.league
        season = league.championship

        stats_by_league = stats_by_season[season][league]
        stats_by_league['matches'] += 1
        stats_by_league['wins'] = stats_by_league['wins']
        stats_by_league['draws'] = stats_by_league['draws']
        stats_by_league['losses'] = stats_by_league['losses']
        if match.winner == team:
            stats_by_league['wins'] += 1
        elif match.result == MatchResult.DRAW:
            stats_by_league['draws'] += 1
        else:
            stats_by_league['losses'] += 1
        stats_by_league['winrate'] = 0
        stats_by_league['goals'] += len(match.goals)
        stats_by_league['conceded_goals'] += len(match.conceded_goals)
        stats_by_league['assists'] += len(match.assists)
        stats_by_league['cs'] += len(match.cs)
        stats_by_league['subs'] += len(match.subs)
        stats_by_league['ogs'] += len(match.ogs)
        stats_by_league['yellow_cards'] += len(match.yellow_cards)
        stats_by_league['red_cards'] += len(match.red_cards)

    for season in stats_by_season:
        for league in stats_by_season[season]:
            league_stats = stats_by_season[season][league]
            league_matches = league_stats['matches']
            league_wins = league_stats['wins']
            league_stats['winrate'] = float(league_wins) / (league_matches or 1) * 100

    all_wins = Match.objects.filter(Q(team_home=team) | Q(team_guest=team), result__winner=team, is_played=True)
    all_draws = Match.objects.filter(
        Q(team_home=team) | Q(team_guest=team), result__value=MatchResult.DRAW, is_played=True
    )
    all_losses = Match.objects.filter(
        Q(team_home=team) | Q(team_guest=team),
        ~Q(result__winner=team),
        ~Q(result__value=MatchResult.DRAW),
        is_played=True,
    )
    all_goals = Goal.objects.filter(team=team, match__is_played=True)
    all_conceded_goals = Goal.objects.filter(
        Q(match__team_home=team) | Q(match__team_guest=team), ~Q(team=team), match__is_played=True
    )
    all_assists = Goal.objects.filter(team=team, assistent__isnull=False, match__is_played=True)
    all_clean_sheets = OtherEvents.objects.cs().filter(team=team, match__is_played=True)
    all_subs = Substitution.objects.filter(team=team, match__is_played=True)
    all_ogs = OtherEvents.objects.ogs().filter(team=team, match__is_played=True)
    all_yellow_cards = OtherEvents.objects.yellow_cards().filter(team=team, match__is_played=True)
    all_red_cards = OtherEvents.objects.red_cards().filter(team=team, match__is_played=True)

    overall_matches = len(all_matches)
    overall_wins = all_wins.count()
    overall_draws = all_draws.count()
    overall_losses = all_losses.count()
    overall_winrate = float(overall_wins) / (overall_matches or 1) * 100
    overall_goals = all_goals.count()
    overall_conceded_goals = all_conceded_goals.count()
    overall_assists = all_assists.count()
    overall_clean_sheets = all_clean_sheets.count()
    overall_subs = all_subs.count()
    overall_ogs = all_ogs.count()
    overall_yellow_cards = all_yellow_cards.count()
    overall_red_cards = all_red_cards.count()

    overall_stats = [
        overall_matches,
        overall_wins,
        overall_draws,
        overall_losses,
        overall_winrate,
        overall_goals,
        overall_conceded_goals,
        overall_assists,
        overall_clean_sheets,
        overall_subs,
        overall_ogs,
        overall_yellow_cards,
        overall_red_cards,
    ]

    overall_avg_goals = overall_goals / (overall_matches or 1)
    overall_avg_conceded_goals = overall_conceded_goals / (overall_matches or 1)
    overall_avg_assists = overall_assists / (overall_matches or 1)
    overall_avg_clean_sheets = overall_clean_sheets / (overall_matches or 1)
    overall_avg_yellow_cards = overall_yellow_cards / (overall_matches or 1)
    overall_avg_red_cards = overall_red_cards / (overall_matches or 1)
    overall_avg_own_goals = overall_ogs / (overall_matches or 1)
    overall_avg_subs = overall_subs / (overall_matches or 1)

    overall_avg_stats = [
        overall_matches,
        overall_avg_goals,
        overall_avg_conceded_goals,
        overall_avg_assists,
        overall_avg_clean_sheets,
        overall_avg_subs,
        overall_avg_own_goals,
        overall_avg_yellow_cards,
        overall_avg_red_cards,
    ]

    extra_stats_by_season = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    if overall_matches > 0:
        for season in stats_by_season:
            for league in stats_by_season[season]:
                league_stats = stats_by_season[season][league]
                league_matches_count = league_stats['matches']
                if league_matches_count == 0:
                    continue

                extra_stats_by_league = extra_stats_by_season[season][league]
                extra_stats_by_league['matches'] = league_stats['matches']
                extra_stats_by_league['goals'] = league_stats['goals'] / league_matches_count
                extra_stats_by_league['conceded_goals'] = league_stats['conceded_goals'] / league_matches_count
                extra_stats_by_league['assists'] = league_stats['assists'] / league_matches_count
                extra_stats_by_league['cs'] = league_stats['cs'] / league_matches_count
                extra_stats_by_league['subs'] = league_stats['subs'] / league_matches_count
                extra_stats_by_league['ogs'] = league_stats['ogs'] / league_matches_count
                extra_stats_by_league['yellow_cards'] = league_stats['yellow_cards'] / league_matches_count
                extra_stats_by_league['red_cards'] = league_stats['red_cards'] / league_matches_count

    other_stats = {}

    first_match = (
        (team.home_matches.all() | team.guest_matches.all())
        .filter(is_played=True, match_date__isnull=False)
        .select_related('league__championship')
        .order_by('match_date')
        .first()
    )

    biggest_home_win = (
        team.home_matches.filter(score_home__gt=F('score_guest'))
        .annotate(goal_diff=F('score_home') - F('score_guest'))
        .select_related('league__championship')
        .order_by('-goal_diff')
        .first()
    )

    biggest_guest_win = (
        team.guest_matches.filter(score_guest__gt=F('score_home'))
        .annotate(goal_diff=F('score_guest') - F('score_home'))
        .select_related('league__championship')
        .order_by('-goal_diff')
        .first()
    )

    biggest_home_loss = (
        team.home_matches.filter(score_home__lt=F('score_guest'))
        .annotate(goal_diff=F('score_home') - F('score_guest'))
        .select_related('league__championship')
        .order_by('goal_diff')
        .first()
    )

    biggest_guest_loss = (
        team.guest_matches.filter(score_guest__lt=F('score_home'))
        .annotate(goal_diff=F('score_guest') - F('score_home'))
        .select_related('league__championship')
        .order_by('goal_diff')
        .first()
    )

    most_effective_draw = (
        (team.home_matches.all() | team.guest_matches.all())
        .filter(score_guest=F('score_home'))
        .annotate(scored_total=F('score_home') + F('score_guest'))
        .select_related('league__championship')
        .order_by('-scored_total')
        .first()
    )

    cards_filter = Q(match_event__event=OtherEvents.YELLOW_CARD) | Q(match_event__event=OtherEvents.RED_CARD)
    most_biggest_cards_given = (
        (team.home_matches.all() | team.guest_matches.all())
        .annotate(cards_count=Count('match_event', filter=cards_filter))
        .select_related('league__championship')
        .order_by('-cards_count')
    ).first()

    fastest_goal = (
        Goal.objects.filter(team=team)
        .select_related('match__team_home', 'match__team_guest', 'match__league__championship')
        .order_by('time_min', 'time_sec')
        .first()
    )
    latest_goal = (
        Goal.objects.filter(team=team)
        .select_related('match__team_home', 'match__team_guest', 'match__league__championship')
        .order_by('-time_min', '-time_sec')
        .first()
    )

    greatest_goalscorer = team.goals.values('author').annotate(goals=Count('author')).order_by('-goals').first()
    greatest_assistant = (
        team.goals.values('assistent').annotate(assists=Count('assistent')).order_by('-assists').first()
    )
    greatest_goalkeeper = (
        team.team_events.filter(event=OtherEvents.CLEAN_SHEET)
        .values('author')
        .annotate(cs=Count('author'))
        .order_by('-cs')
        .first()
    )

    home_matches = (
        Match.objects.filter(team_home=team, is_played=True)
        .values(player=F('team_home_start__id'))
        .annotate(matches=Count('team_home_start__id'))
        .order_by('-matches')
    )
    guest_matches = (
        Match.objects.filter(team_guest=team, is_played=True)
        .values(player=F('team_guest_start__id'))
        .annotate(matches=Count('team_guest_start__id'))
        .order_by('-matches')
    )
    sub_matches = (
        Substitution.objects.filter(team=team)
        .values(player=F('player_in'))
        .distinct()
        .annotate(matches=Count('player_in'))
        .order_by('-matches')
    )

    all_team_matches = list(home_matches) + list(guest_matches) + list(sub_matches)
    matches_by_player = defaultdict(int)
    for player_matches in all_team_matches:
        matches_by_player[player_matches['player']] += player_matches['matches']

    (greatest_player, greatest_sub_in) = (None, None)
    if len(all_team_matches) > 0:
        greatest_player = sorted(matches_by_player.items(), key=lambda kv: kv[1], reverse=True)[0]
    if len(sub_matches) > 0:
        greatest_sub_in = sorted(sub_matches, key=lambda x: x['matches'], reverse=True)[0]

    other_stats['first_match'] = first_match
    other_stats['biggest_home_win'] = biggest_home_win
    other_stats['biggest_guest_win'] = biggest_guest_win
    other_stats['biggest_home_loss'] = biggest_home_loss
    other_stats['biggest_guest_loss'] = biggest_guest_loss
    other_stats['most_effective_draw'] = most_effective_draw
    other_stats['most_biggest_cards_given'] = most_biggest_cards_given
    other_stats['fastest_goal'] = fastest_goal
    other_stats['latest_goal'] = latest_goal

    if greatest_goalscorer:
        other_stats['greatest_goalscorer'] = {
            'player': User.objects.get(user_player=greatest_goalscorer['author']),
            'count': greatest_goalscorer['goals'],
        }
    if greatest_assistant:
        other_stats['greatest_assistant'] = {
            'player': User.objects.get(user_player=greatest_assistant['assistent']),
            'count': greatest_assistant['assists'],
        }
    if greatest_goalkeeper:
        other_stats['greatest_goalkeeper'] = {
            'player': User.objects.get(user_player=greatest_goalkeeper['author']),
            'count': greatest_goalkeeper['cs'],
        }
    if greatest_player:
        other_stats['greatest_player'] = {
            'player': User.objects.get(user_player=greatest_player[0]),
            'count': greatest_player[1],
        }
    if greatest_sub_in:
        other_stats['greatest_sub_in'] = {
            'player': User.objects.get(user_player=greatest_sub_in['player']),
            'count': greatest_sub_in['matches'],
        }

    return {
        'team': team,
        'stats': stats_by_season,
        'extra_stats': extra_stats_by_season,
        'overall_stats': overall_stats,
        'overall_avg_stats': overall_avg_stats,
        'other_stats': other_stats,
    }


@register.filter
def team_stats_rows_count(stats: defaultdict, season):
    return len(stats[season])


#   Для статы юзера по командам
@register.inclusion_tag('tournament/include/player_detailed_statistics.html')
def player_detailed_statistics(user: User):
    try:
        player = user.user_player
    except:
        return {}

    prefetches = (
        Prefetch('match_goal', queryset=Goal.objects.filter(author=player, match__is_played=True), to_attr='goals'),
        Prefetch(
            'match_goal', queryset=Goal.objects.filter(assistent=player, match__is_played=True), to_attr='assists'
        ),
        Prefetch(
            'match_event', queryset=OtherEvents.objects.cs().filter(author=player, match__is_played=True), to_attr='cs'
        ),
        Prefetch(
            'match_event',
            queryset=Substitution.objects.filter(player_out=player, match__is_played=True),
            to_attr='subs_out',
        ),
        Prefetch(
            'match_event',
            queryset=Substitution.objects.filter(player_in=player, match__is_played=True),
            to_attr='subs_in',
        ),
        Prefetch(
            'match_event',
            queryset=OtherEvents.objects.ogs().filter(author=player, match__is_played=True),
            to_attr='ogs',
        ),
        Prefetch(
            'match_event',
            queryset=OtherEvents.objects.yellow_cards().filter(author=player, match__is_played=True),
            to_attr='yellow_cards',
        ),
        Prefetch(
            'match_event',
            queryset=OtherEvents.objects.red_cards().filter(author=player, match__is_played=True),
            to_attr='red_cards',
        ),
    )

    matches = Match.objects.select_related('league__championship')
    home_matches = (
        matches.filter(team_home_start=player, is_played=True)
        .select_related('league__championship')
        .prefetch_related(Prefetch('team_home', to_attr='player_team'), *prefetches)
    )
    guest_matches = (
        matches.filter(team_guest_start=player, is_played=True)
        .select_related('league__championship')
        .prefetch_related(Prefetch('team_guest', to_attr='player_team'), *prefetches)
    )
    sub_matches = (
        Match.objects.filter(
            ~(Q(team_guest_start=player) | Q(team_home_start=player)),
            is_played=True,
            match_substitutions__player_in=player,
        )
        .select_related('league__championship')
        .prefetch_related(
            Prefetch(
                'match_substitutions',
                queryset=Substitution.objects.filter(player_in=player, match__is_played=True).select_related('team'),
                to_attr='player_subs',
            ),
            *prefetches,
        )
    )

    all_matches = list(sub_matches) + list(home_matches) + list(guest_matches)

    stats_by_season = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(int))))
    for match in all_matches:
        team = match.player_team if hasattr(match, 'player_team') else match.player_subs[0].team
        league = match.league
        season = league.championship

        stats_by_league = stats_by_season[season][team][league]
        stats_by_league['matches'] += 1
        stats_by_league['goals'] += len(match.goals)
        stats_by_league['assists'] += len(match.assists)
        stats_by_league['goals_assists'] += len(match.goals) + len(match.assists)
        stats_by_league['cs'] += len(match.cs)
        stats_by_league['subs_out'] += len(match.subs_out)
        stats_by_league['subs_in'] += len(match.subs_in)
        stats_by_league['ogs'] += len(match.ogs)
        stats_by_league['yellow_cards'] += len(match.yellow_cards)
        stats_by_league['red_cards'] += len(match.red_cards)

    all_goals = Goal.objects.filter(author=player, match__is_played=True)
    all_assists = Goal.objects.filter(assistent=player, match__is_played=True)
    all_clean_sheets = OtherEvents.objects.cs().filter(author=player, match__is_played=True)
    all_subs_out = Substitution.objects.filter(player_out=player, match__is_played=True)
    all_subs_in = Substitution.objects.filter(player_in=player, match__is_played=True)
    all_ogs = OtherEvents.objects.ogs().filter(author=player, match__is_played=True)
    all_yellow_cards = OtherEvents.objects.yellow_cards().filter(author=player, match__is_played=True)
    all_red_cards = OtherEvents.objects.red_cards().filter(author=player, match__is_played=True)

    overall_matches = len(all_matches)
    overall_goals = all_goals.count()
    overall_assists = all_assists.count()
    overall_goals_assists = overall_goals + overall_assists
    overall_clean_sheets = all_clean_sheets.count()
    overall_subs_out = all_subs_out.count()
    overall_subs_in = all_subs_in.count()
    overall_ogs = all_ogs.count()
    overall_yellow_cards = all_yellow_cards.count()
    overall_red_cards = all_red_cards.count()

    overall_stats = [
        overall_matches,
        overall_goals,
        overall_assists,
        overall_goals_assists,
        overall_clean_sheets,
        overall_subs_out,
        overall_subs_in,
        overall_ogs,
        overall_yellow_cards,
        overall_red_cards,
    ]

    overall_avg_goals = overall_goals / (overall_matches or 1)
    overall_avg_assists = overall_assists / (overall_matches or 1)
    overall_avg_goals_assists = overall_goals_assists / (overall_matches or 1)
    overall_avg_clean_sheets = overall_clean_sheets / (overall_matches or 1)
    overall_avg_yellow_cards = overall_yellow_cards / (overall_matches or 1)
    overall_avg_red_cards = overall_red_cards / (overall_matches or 1)
    overall_avg_own_goals = overall_ogs / (overall_matches or 1)
    overall_avg_subs_in = overall_subs_in / (overall_matches or 1)
    overall_avg_subs_out = overall_subs_out / (overall_matches or 1)

    overall_extra_stats = [
        overall_matches,
        overall_avg_goals,
        overall_avg_assists,
        overall_avg_goals_assists,
        overall_avg_clean_sheets,
        overall_avg_subs_out,
        overall_avg_subs_in,
        overall_avg_own_goals,
        overall_avg_yellow_cards,
        overall_avg_red_cards,
    ]

    extra_stats_by_season = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(float))))
    if overall_matches > 0:
        for season in stats_by_season:
            for team in stats_by_season[season]:
                for league in stats_by_season[season][team]:
                    league_stats = stats_by_season[season][team][league]
                    league_matches_count = league_stats['matches']
                    if league_matches_count == 0:
                        continue

                    extra_stats_by_league = extra_stats_by_season[season][team][league]
                    extra_stats_by_league['matches'] = league_stats['matches']
                    extra_stats_by_league['goals'] = league_stats['goals'] / league_matches_count
                    extra_stats_by_league['assists'] = league_stats['assists'] / league_matches_count
                    extra_stats_by_league['goals_assists'] = league_stats['goals_assists'] / league_matches_count
                    extra_stats_by_league['cs'] = league_stats['cs'] / league_matches_count
                    extra_stats_by_league['subs_out'] = league_stats['subs_out'] / league_matches_count
                    extra_stats_by_league['subs_in'] = league_stats['subs_in'] / league_matches_count
                    extra_stats_by_league['ogs'] = league_stats['ogs'] / league_matches_count
                    extra_stats_by_league['yellow_cards'] = league_stats['yellow_cards'] / league_matches_count
                    extra_stats_by_league['red_cards'] = league_stats['red_cards'] / league_matches_count

    first_match = (
        Match.objects.filter(
            Q(team_home_start=player) | Q(team_guest_start=player) | Q(match_substitutions__player_in=player)
        )
        .filter(is_played=True, match_date__isnull=False)
        .select_related('team_home', 'team_guest', 'league__championship')
        .order_by('match_date')
        .first()
    )

    fastest_goal = (
        Goal.objects.filter(author=player)
        .select_related('match__team_home', 'match__team_guest', 'match__league__championship')
        .order_by('time_min', 'time_sec')
        .first()
    )
    latest_goal = (
        Goal.objects.filter(author=player)
        .select_related('match__team_home', 'match__team_guest', 'match__league__championship')
        .order_by('-time_min', '-time_sec')
        .first()
    )
    most_goals_in_match = (
        Match.objects.filter(match_goal__author=player)
        .select_related('team_home', 'team_guest', 'league__championship')
        .annotate(goals=Count('id', filter=Q(match_goal__author=player)))
        .order_by('-goals')
        .first()
    )
    most_assists_in_match = (
        Match.objects.filter(match_goal__assistent=player)
        .select_related('team_home', 'team_guest', 'league__championship')
        .annotate(assists=Count('id', filter=Q(match_goal__assistent=player)))
        .order_by('-assists')
        .first()
    )
    most_goals_assists_in_match = (
        Match.objects.filter(Q(match_goal__author=player) | Q(match_goal__assistent=player))
        .select_related('team_home', 'team_guest', 'league__championship')
        .annotate(actions=Count('id', filter=Q(match_goal__assistent=player) | Q(match_goal__author=player)))
        .order_by('-actions')
        .first()
    )

    goals_subquery = (
        Goal.objects.filter(author=player, match__league__championship=OuterRef('id'))
        .order_by()
        .values('match__league__championship')
        .annotate(c=Count('*'))
        .values('c')
    )

    assists_subquery = (
        Goal.objects.filter(assistent=player, match__league__championship=OuterRef('id'))
        .order_by()
        .values('match__league__championship')
        .annotate(c=Count('*'))
        .values('c')
    )

    goals_assists_subquery = (
        Goal.objects.filter(Q(author=player) | Q(assistent=player), match__league__championship=OuterRef('id'))
        .order_by()
        .values('match__league__championship')
        .annotate(c=Count('*'))
        .values('c')
    )

    cs_subquery = (
        OtherEvents.objects.cs()
        .filter(author=player, match__league__championship=OuterRef('id'))
        .order_by()
        .values('match__league__championship')
        .annotate(c=Count('*'))
        .values('c')
    )

    most_goals_in_season = (
        Season.objects.annotate(goals=Subquery(goals_subquery)).filter(goals__isnull=False).order_by('-goals').first()
    )
    most_assists_in_season = (
        Season.objects.annotate(assists=Subquery(assists_subquery))
        .filter(assists__isnull=False)
        .order_by('-assists')
        .first()
    )
    most_goals_assists_in_season = (
        Season.objects.annotate(actions=Subquery(goals_assists_subquery))
        .filter(actions__isnull=False)
        .order_by('-actions')
        .first()
    )
    most_cs_in_season = (
        Season.objects.annotate(cs=Subquery(cs_subquery)).filter(cs__isnull=False).order_by('-cs').first()
    )

    other_stats = {
        'first_match': first_match,
        'fastest_goal': fastest_goal,
        'latest_goal': latest_goal,
        'most_goals_in_match': most_goals_in_match,
        'most_assists_in_match': most_assists_in_match,
        'most_goals_assists_in_match': most_goals_assists_in_match,
        'most_goals_in_season': most_goals_in_season,
        'most_assists_in_season': most_assists_in_season,
        'most_goals_assists_in_season': most_goals_assists_in_season,
        'most_cs_in_season': most_cs_in_season,
    }

    return {
        'stats': stats_by_season,
        'extra_stats': extra_stats_by_season,
        'user': user,
        'overall_stats': overall_stats,
        'overall_extra_stats': overall_extra_stats,
        'other_stats': other_stats,
    }


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


#   Фильтры для таблички лиги
#   и теги
@register.inclusion_tag('tournament/include/cup_table.html')
def cup_table(league):
    return {'league': league}


@register.filter
def pairs_in_round(tour):
    matches = Match.objects.filter(numb_tour=tour)
    pairs = []
    for m in matches:
        pair = set()
        pair.add(m.team_home)
        pair.add(m.team_guest)
        if pair not in pairs:
            pairs.append(pair)
    pi = []
    for p in pairs:
        pi.append(sorted(list(p), key=lambda x: x.id))
    for m in matches:
        for p in pi:
            if (p[0] == m.team_home and p[1] == m.team_guest) or (p[1] == m.team_home and p[0] == m.team_guest):
                i = pi.index(p)
        if i is not None:
            pi[i].append(m)

    return sorted(pi, key=lambda x: x[2].id)


@register.filter
def team_score_in_match(team, match):
    if team == match.team_home:
        return match.score_home
    if team == match.team_guest:
        return match.score_guest
    return None


@register.filter
def round_name(tour, all_tours):
    if tour == all_tours:
        return 'Финал'
    if tour == all_tours - 1:
        return '1/2 Финала'
    if tour == all_tours - 2:
        return '1/4 Финала'
    if tour == all_tours - 3:
        return '1/8 Финала'

    return '{} Раунд'.format(tour)


@register.filter
def cup_round_name(tour: TourNumber):
    tours_count = tour.league.tours.count()
    if tour.number == tours_count:
        return 'Финал'
    if tour.number == tours_count - 1:
        return '1/2'
    if tour.number == tours_count - 2:
        return '1/4'
    if tour.number == tours_count - 3:
        return '1/8'
    return '{} раунд'.format(tour.number)


@register.inclusion_tag('tournament/include/league_table.html')
def league_table(league: League):
    result = get_league_table(league)
    return {'teams': result}


# Конец тегов и фильтров для таблицы лиги


@register.filter
def top_goalscorers(league):
    return (
        Player.objects.select_related('team', 'name__user_profile')
        .filter(goals__match__league=league)
        .annotate(goals_c=Count('goals__match__league'))
        .order_by('-goals_c')
    )


@register.filter
def top_assistent(league):
    return (
        Player.objects.select_related('team', 'name__user_profile')
        .filter(assists__match__league=league)
        .annotate(ass_c=Count('assists__match__league'))
        .order_by('-ass_c')
    )


@register.filter
def top_clean_sheets(league):
    return (
        Player.objects.select_related('team', 'name__user_profile')
        .filter(event__match__league=league, event__event='CLN')
        .annotate(event_c=Count('event__match__league'))
        .order_by('-event_c')
    )


#  Капитан и ассистент для профиля команды(контактов)
@register.filter
def get_captain(team):
    return Player.objects.filter(team=team, role='C').select_related('name__user_profile')


@register.filter
def get_team_assistent(team):
    return Player.objects.filter(team=team, role='AC').select_related('name__user_profile')


@register.filter
def all_league_season(team, season):
    return League.objects.filter(teams=team, championship=season).order_by('-id')


@register.filter
def all_seasons(team):
    return (
        Season.objects.filter(tournaments_in_season__teams=team)
        .distinct()
        .prefetch_related(
            Prefetch(
                'tournaments_in_season',
                queryset=League.objects.filter(teams=team)
                .prefetch_related(
                    'tours',
                    Prefetch(
                        'matches_in_league',
                        queryset=Match.objects.filter(Q(team_home=team) | Q(team_guest=team))
                        .select_related('team_home', 'team_guest', 'numb_tour')
                        .order_by('numb_tour'),
                        to_attr='team_matches',
                    ),
                )
                .order_by('-id'),
                to_attr='team_leagues',
            ),
        )
        .order_by('-number')
    )


def sort_teams(league: League):
    lt = get_league_table(league)
    return [i[0] for i in lt]


def get_league_table(league: League):
    teams = list(Team.objects.filter(leagues=league))
    teams_count = len(teams)
    points = [0 for _ in range(teams_count)]  # Количество очков
    goal_diff = [0 for _ in range(teams_count)]  # Разница мячей
    scored = [0 for _ in range(teams_count)]  # Мячей забито
    conceded = [0 for _ in range(teams_count)]  # Мячей пропущено
    matches_played = [0 for _ in range(teams_count)]  # Игр сыграно
    wins = [0 for _ in range(teams_count)]  # Побед
    draws = [0 for _ in range(teams_count)]  # Ничей
    losses = [0 for _ in range(teams_count)]  # Поражений
    last_matches = [[] for _ in range(teams_count)]
    for i, team in enumerate(teams):
        matches = Match.objects.select_related('team_home', 'team_guest', 'result__winner', 'numb_tour').filter(
            (Q(team_home=team) | Q(team_guest=team)), league=league, is_played=True
        )
        matches_played[i] = matches.count()

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

        last_matches[i] = sorted(last_matches[i], key=lambda x: x[0].numb_tour.number)[-5:]
        points[i] = wins_count * 3 + draws_count * 1
        goal_diff[i] = goals_scored - goals_conceded
        scored[i] = goals_scored
        conceded[i] = goals_conceded
        wins[i] = wins_count
        losses[i] = losses_count
        draws[i] = draws_count

    table = zip(teams, matches_played, wins, draws, losses, scored, conceded, goal_diff, points, last_matches)
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
                matches_all = Match.objects.filter(
                    (Q(team_home=team) | Q(team_guest=team)), league=league, is_played=True
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
    try:
        primary_league = League.objects.filter(
            teams=team, title__in=primary_leagues, championship__is_active=True
        ).first()
        if not primary_league:
            return League.objects.filter(teams=team, championship__is_active=True).first()
    except:
        return None


@register.filter
def current_position(team):
    league = current_league(team)
    if not league:
        return '-'

    sorted_teams = list(sort_teams(league))
    return sorted_teams.index(team) + 1


@register.filter
def teams_in_league_count(team):
    league = current_league(team)
    if not league:
        return '-'

    return league.teams.count()


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
def get(d: {}, key):
    return d[key]


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
def postponements_in_leagues(team: Team, leagues: QuerySet) -> list[Optional[Postponement]]:
    postponements = team.get_postponements(leagues)
    league = leagues.first()
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
def postponements_form(user: User, leagues: QuerySet):
    teams = get_user_teams(user)

    # Выбираем все матчи игрока, которые уже можно играть, но котоыре еще не были сыграны
    matches = Match.objects.filter(
        Q(team_home__in=teams) | Q(team_guest__in=teams),
        league__in=leagues,
        is_played=False,
        numb_tour__date_from__lte=timezone.now().date(),
    )
    available_matches = [match for match in matches.all() if match.can_be_postponed]

    return {
        'matches': available_matches,
        'user': user,
    }


def get_user_teams(user: User):
    try:
        player = user.user_player
    except Exception as e:
        print(e)
        return []
    teams = []
    if player.role == Player.CAPTAIN or player.role == Player.ASSISTENT:
        teams.append(player.team)

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
