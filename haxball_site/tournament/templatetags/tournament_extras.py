import datetime
from collections import defaultdict
from functools import reduce
from itertools import groupby
from typing import Optional

from django import template
from django.contrib.auth.models import User
from django.db.models import Q, Count, QuerySet, F, Max, Sum
from django.utils import timezone

from ..models import FreeAgent, OtherEvents, Goal, Match, League, Team, Player, Substitution, Season, PlayerTransfer, \
    Disqualification, Postponement, TourNumber

register = template.Library()


@register.filter
def user_in_agents(user):
    try:
        a = FreeAgent.objects.get(player=user, is_active=True)
        return True
    except:
        return False


@register.filter
def can_add_entry(user):
    try:
        if timezone.now() - user.user_free_agent.created > timezone.timedelta(hours=6):
            return True
        else:
            return False
    except:
        return True


@register.filter
def date_can(user):
    return user.user_free_agent.created + timezone.timedelta(hours=6)


# Евенты, всего/в текущем сезоне
def event_count(player, team, type):
    return OtherEvents.objects.filter(author=player, team=team, event=type, match__is_played=True).count()


@register.filter
def cs_count(player, team):
    return event_count(player, team, OtherEvents.CLEAN_SHEET)


@register.filter
def og_count(player, team):
    return event_count(player, team, OtherEvents.OWN_GOAL)


@register.filter
def yellow_cards_count(player, team):
    return event_count(player, team, OtherEvents.YELLOW_CARD)


@register.filter
def red_cards_count(player, team):
    return event_count(player, team, OtherEvents.RED_CARD)


@register.filter
def event_count_current(player, type):
    current = Season.objects.filter(is_active=True).first()
    return OtherEvents.objects.filter(author=player, team=player.team, event=type, match__is_played=True,
                                      match__league__championship=current).count()


@register.filter
def goals_in_team(player, team):
    return Goal.objects.filter(author=player, team=team, match__is_played=True).count()


@register.filter
def goals_in_team_current(player, team):
    current = Season.objects.filter(is_active=True).first()
    return Goal.objects.filter(author=player, team=team, match__is_played=True,
                               match__league__championship=current).count()


@register.filter
def assists_in_team(player, team):
    return Goal.objects.filter(assistent=player, team=team, match__is_played=True).count()


@register.filter
def assists_in_team_current(player, team):
    current = Season.objects.filter(is_active=True).first()
    return Goal.objects.filter(assistent=player, team=team, match__is_played=True,
                               match__league__championship=current).count()


@register.filter
def replaced_in_team(player, team):
    return Substitution.objects.filter(team=team, player_out=player, match__is_played=True).count()


@register.filter
def replaced_in_team_current(player, team):
    current = Season.objects.filter(is_active=True).first()
    return Substitution.objects.filter(team=team, player_out=player, match__is_played=True,
                                       match__league__championship=current).count()


#
@register.filter
def join_game_in_team(player, team):
    return Substitution.objects.filter(team=team, player_in=player, match__is_played=True).count()


@register.filter
def join_game_in_team_current(player, team):
    current = Season.objects.filter(is_active=True).first()
    return Substitution.objects.filter(team=team, player_in=player, match__is_played=True,
                                       match__league__championship=current).count()


@register.filter
def matches_in_team_current(player, team):
    return (Match.objects.filter(team_guest=team, team_guest_start=player, is_played=True,
                                 league__championship__is_active=True).count() +
            Match.objects.filter(team_home=team, team_home_start=player, is_played=True,
                                 league__championship__is_active=True).count() +
            Match.objects.filter(~(Q(team_guest_start=player) | Q(team_home_start=player)),
                                 is_played=True, match_substitutions__team=team,
                                 match_substitutions__player_in=player, league__championship__is_active=True
    ).distinct().count())


@register.filter
def matches_in_team(player, team):
    return (Match.objects.filter(team_guest=team, team_guest_start=player, is_played=True).count() +
            Match.objects.filter(team_home=team, team_home_start=player, is_played=True).count() +
            Match.objects.filter(~(Q(team_guest_start=player) | Q(team_home_start=player)), is_played=True,
                                 match_substitutions__team=team, match_substitutions__player_in=player).distinct().count())


@register.inclusion_tag('tournament/include/team_statistics.html')
def team_statistics(team: Team):
    stats_by_season = {}
    extra_stats_by_season = {}
    seasons = Season.objects.filter(tournaments_in_season__teams=team).distinct().order_by('number')
    for season in seasons:
        season_stats = {}
        season_extra_stats = {}

        leagues = list(League.objects.filter(championship=season, teams=team).order_by('id'))
        for league in leagues:
            matches_count = Match.objects.filter(Q(team_home=team) | Q(team_guest=team),
                                                 league=league, is_played=True).count()

            if matches_count == 0:
                continue

            goals = Goal.objects.filter(team=team, match__is_played=True, match__league=league).count()
            conceded_goals = (Goal.objects.filter(Q(match__team_home=team) | Q(match__team_guest=team),
                                                        ~Q(team=team), match__league=league).count())
            assists_count = Goal.objects.filter(team=team, assistent__isnull=False,
                                                match__is_played=True, match__league=league).count()
            clean_sheets = OtherEvents.objects.cs().filter(team=team, match__is_played=True,
                                                           match__league=league).count()
            yellow_cards = OtherEvents.objects.yellow_cards().filter(team=team, match__is_played=True,
                                                                     match__league=league).count()
            red_cards = OtherEvents.objects.red_cards().filter(team=team, match__is_played=True,
                                                               match__league=league).count()
            own_goals = OtherEvents.objects.ogs().filter(team=team, match__is_played=True,
                                                         match__league=league).count()
            subs = Substitution.objects.filter(team=team, match__is_played=True, match__league=league).count()

            wins = (Match.objects.filter(team_home=team, score_home__gt=F('score_guest'),
                                               league=league, is_played=True).count() +
                          Match.objects.filter(team_guest=team, score_guest__gt=F('score_home'),
                                               league=league, is_played=True).count())
            losses = (Match.objects.filter(team_home=team, score_home__lt=F('score_guest'),
                                                 league=league, is_played=True).count() +
                            Match.objects.filter(team_guest=team, score_guest__lt=F('score_home'),
                                                 league=league, is_played=True).count())
            draws = Match.objects.filter(Q(team_home=team) | Q(team_guest=team), score_home=F('score_guest'),
                                         league=league, is_played=True).count()
            winrate = wins / matches_count * 100

            league_stats = [matches_count, wins, draws, losses, winrate, goals, conceded_goals,
                            assists_count, clean_sheets, subs, own_goals, yellow_cards, red_cards]

            avg_goals = goals / matches_count
            avg_conceded_goals = conceded_goals / matches_count
            avg_assists = assists_count / matches_count
            avg_clean_sheets = clean_sheets / matches_count
            avg_yellow_cards = yellow_cards / matches_count
            avg_red_cards = red_cards / matches_count
            avg_own_goals = own_goals / matches_count
            avg_subs = subs / matches_count

            league_extra_stats = [matches_count, avg_goals, avg_conceded_goals, avg_assists, avg_clean_sheets,
                                  avg_subs, avg_own_goals, avg_yellow_cards, avg_red_cards]

            season_stats[league] = league_stats
            season_extra_stats[league] = league_extra_stats

        if season_stats:
            stats_by_season[season] = season_stats
            extra_stats_by_season[season] = season_extra_stats

    overall_matches_count = (Match.objects.filter(Q(team_home=team) | Q(team_guest=team), is_played=True).count())
    overall_goals = Goal.objects.filter(team=team, match__is_played=True,).count()
    overall_conceded_goals = (Goal.objects.filter(Q(match__team_home=team) | Q(match__team_guest=team),
                                                  ~Q(team=team)).count())
    overall_assists = Goal.objects.filter(assistent__isnull=False, team=team, match__is_played=True).count()
    overall_clean_sheets = OtherEvents.objects.cs().filter(team=team, match__is_played=True).count()
    overall_subs = Substitution.objects.filter(team=team, match__is_played=True).count()
    overall_ogs = OtherEvents.objects.ogs().filter(team=team, match__is_played=True).count()
    overall_yellow_cards = OtherEvents.objects.yellow_cards().filter(team=team, match__is_played=True).count()
    overall_red_cards = OtherEvents.objects.red_cards().filter(team=team, match__is_played=True).count()

    overall_wins = (Match.objects.filter(team_home=team, score_home__gt=F('score_guest'), is_played=True).count() +
                    Match.objects.filter(team_guest=team, score_guest__gt=F('score_home'), is_played=True).count())
    overall_losses = (Match.objects.filter(team_home=team, score_home__lt=F('score_guest'), is_played=True).count() +
                      Match.objects.filter(team_guest=team, score_guest__lt=F('score_home'), is_played=True).count())
    overall_draws = Match.objects.filter(Q(team_home=team) | Q(team_guest=team), score_home=F('score_guest'),
                                         is_played=True).count()
    overall_winrate = overall_wins / (overall_matches_count or 1) * 100

    overall_stats = [overall_matches_count, overall_wins, overall_draws, overall_losses, overall_winrate, overall_goals,
                     overall_conceded_goals, overall_assists, overall_clean_sheets, overall_subs, overall_ogs,
                     overall_yellow_cards, overall_red_cards]

    overall_avg_goals = overall_goals / (overall_matches_count or 1)
    overall_avg_conceded_goals = overall_conceded_goals / (overall_matches_count or 1)
    overall_avg_assists = overall_assists / (overall_matches_count or 1)
    overall_avg_clean_sheets = overall_clean_sheets / (overall_matches_count or 1)
    overall_avg_yellow_cards = overall_yellow_cards / (overall_matches_count or 1)
    overall_avg_red_cards = overall_red_cards / (overall_matches_count or 1)
    overall_avg_ogs = overall_ogs / (overall_matches_count or 1)
    overall_avg_subs = overall_subs / (overall_matches_count or 1)

    overall_avg_stats = [overall_matches_count, overall_avg_goals, overall_avg_conceded_goals, overall_avg_assists,
                         overall_avg_clean_sheets, overall_avg_subs, overall_avg_ogs, overall_avg_yellow_cards,
                         overall_avg_red_cards]

    other_stats = {}

    first_match = ((team.home_matches.all() | team.guest_matches.all())
                   .filter(is_played=True, match_date__isnull=False)
                   .order_by('match_date').first())

    biggest_home_win = (
        team.home_matches.filter(score_home__gt=F('score_guest')).annotate(goal_diff=F('score_home') - F('score_guest'))
    ).order_by('-goal_diff').first()
    biggest_guest_win = (
        team.guest_matches.filter(score_guest__gt=F('score_home')).annotate(goal_diff=F('score_guest') - F('score_home'))
    ).order_by('-goal_diff').first()

    biggest_home_loss = (
        team.home_matches.filter(score_home__lt=F('score_guest')).annotate(goal_diff=F('score_home') - F('score_guest'))
    ).order_by('goal_diff').first()

    biggest_guest_loss = (
        team.guest_matches.filter(score_guest__lt=F('score_home')).annotate(goal_diff=F('score_guest') - F('score_home'))
    ).order_by('goal_diff').first()

    most_effective_draw = ((team.home_matches.all() | team.guest_matches.all()).filter(score_guest=F('score_home'))
                           .annotate(scored_total=F('score_home') + F('score_guest')).order_by('-scored_total').first())

    cards_filter = Q(match_event__event=OtherEvents.YELLOW_CARD) | Q(match_event__event=OtherEvents.RED_CARD)
    most_biggest_cards_given = ((team.home_matches.all() | team.guest_matches.all())
                                .annotate(cards_count=Count('match_event', filter=cards_filter))
                                .order_by('-cards_count')).first()

    fastest_goal = Goal.objects.filter(team=team).order_by('time_min', 'time_sec').first()
    latest_goal = Goal.objects.filter(team=team).order_by('-time_min', '-time_sec').first()

    greatest_goalscorer = team.goals.values('author').annotate(goals=Count('author')).order_by('-goals').first()
    greatest_assistant = team.goals.values('assistent').annotate(assists=Count('assistent')).order_by('-assists').first()
    greatest_goalkeeper = team.team_events.filter(event=OtherEvents.CLEAN_SHEET).values('author').annotate(cs=Count('author')).order_by('-cs').first()

    home_matches = Match.objects.filter(team_home=team).values(player=F('team_home_start__id')).annotate(matches=Count('team_home_start__id')).order_by('-matches')
    guest_matches = Match.objects.filter(team_guest=team).values(player=F('team_guest_start__id')).annotate(matches=Count('team_guest_start__id')).order_by('-matches')
    sub_matches = Substitution.objects.filter(team=team).values(player=F('player_in')).distinct().annotate(matches=Count('player_in')).order_by('-matches')

    all_matches = list(home_matches) + list(guest_matches) + list(sub_matches)
    matches_by_player = defaultdict(int)
    for player_matches in all_matches:
        matches_by_player[player_matches['player']] += player_matches['matches']

    (greatest_player, greatest_sub_in) = (None, None)
    if len(all_matches) > 0:
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
            'count': greatest_goalscorer['goals']
        }
    if greatest_assistant:
        other_stats['greatest_assistant'] = {
            'player': User.objects.get(user_player=greatest_assistant['assistent']),
            'count': greatest_assistant['assists']
        }
    if greatest_goalkeeper:
        other_stats['greatest_goalkeeper'] = {
            'player': User.objects.get(user_player=greatest_goalkeeper['author']),
            'count': greatest_goalkeeper['cs']
        }
    if greatest_player:
        other_stats['greatest_player'] = {
            'player': User.objects.get(user_player=greatest_player[0]),
            'count': greatest_player[1]
        }
    if greatest_sub_in:
        other_stats['greatest_sub_in'] = {
            'player': User.objects.get(user_player=greatest_sub_in['player']),
            'count': greatest_sub_in['matches']
        }

    return {
        'team': team,
        'stats': stats_by_season,
        'extra_stats': extra_stats_by_season,
        'overall_stats': overall_stats,
        'overall_avg_stats': overall_avg_stats,
        'other_stats': other_stats}


@register.filter
def rows_team_stat(team: Team, season: Season):
    matches_filter = (
            (Q(matches_in_league__team_home=team) | Q(matches_in_league__team_guest=team)) &
            Q(matches_in_league__is_played=True)
    )
    leagues = (League.objects
                    .filter(teams=team, championship=season)
                    .annotate(matches_count=Count('matches_in_league', filter=matches_filter))
                    .filter(matches_count__gt=0))

    return leagues.count()


#   Для статы юзера по командам
@register.inclusion_tag('tournament/include/player_detailed_statistics.html')
def player_detailed_statistics(user: User):
    try:
        player = user.user_player
    except:
        return {}

    stats_by_season = {}
    extra_stats_by_season = {}
    player_transfers = PlayerTransfer.objects.filter(trans_player=player)
    transfer_seasons = []
    for player_transfer in player_transfers:
        if player_transfer.season_join not in transfer_seasons:
            transfer_seasons.append(player_transfer.season_join)
    seasons = sorted(transfer_seasons, key=lambda x: x.number)
    for season in seasons:
        season_stats_by_team = {}
        season_extra_stats_by_team = {}
        overall_by_season = [0 for _ in range(1, 11)]
        transfer_teams = list(
            PlayerTransfer.objects.filter(~Q(to_team=None), season_join=season, trans_player=player).distinct('to_team'))
        for transfer_team in transfer_teams:
            season_stats_in_single_team = {}
            season_extra_stats_in_single_team = {}
            team = transfer_team.to_team
            leagues = list(League.objects.filter(championship=season, teams=team).order_by('id'))
            for league in leagues:
                matches_count = (Match.objects.filter(team_guest=team, team_guest_start=player,
                                                      is_played=True, league=league).count() +
                                 Match.objects.filter(team_home=team, team_home_start=player,
                                                      is_played=True, league=league).count() +
                                 Match.objects.filter(~(Q(team_guest_start=player) | Q(team_home_start=player)),
                                                      is_played=True, match_substitutions__team=team,
                                                      match_substitutions__player_in=player, league=league).distinct().count())

                if matches_count == 0:
                    continue

                goals = Goal.objects.filter(author=user.user_player, team=team,
                                                 match__is_played=True, match__league=league).count()

                assists = Goal.objects.filter(assistent=user.user_player, team=team,
                                                    match__is_played=True, match__league=league).count()
                goals_assists = goals + assists
                clean_sheets = OtherEvents.objects.filter(author=user.user_player, team=team, event='CLN',
                                                          match__is_played=True, match__league=league).count()
                yellow_cards = OtherEvents.objects.filter(author=user.user_player, team=team, event='YEL',
                                                          match__is_played=True, match__league=league).count()
                red_cards = OtherEvents.objects.filter(author=user.user_player, team=team, event='RED',
                                                       match__is_played=True, match__league=league).count()
                own_goals = OtherEvents.objects.filter(author=user.user_player, team=team, event='OG',
                                                       match__is_played=True, match__league=league).count()
                subs_in = Substitution.objects.filter(team=team, player_in=user.user_player,
                                                      match__is_played=True, match__league=league).count()
                subs_out = Substitution.objects.filter(team=team, player_out=user.user_player,
                                                       match__is_played=True, match__league=league).count()

                league_stats = [matches_count, goals, assists, goals_assists, clean_sheets,
                                subs_out, subs_in, own_goals, yellow_cards, red_cards]

                avg_goals = goals / matches_count
                avg_assists = assists / matches_count
                avg_goals_assists = goals_assists / matches_count
                avg_clean_sheets = clean_sheets / matches_count
                avg_yellow_cards = yellow_cards / matches_count
                avg_red_cards = red_cards / matches_count
                avg_own_goals = own_goals / matches_count
                avg_subs_in = subs_in / matches_count
                avg_subs_out = subs_out / matches_count

                league_extra_stats = [matches_count, avg_goals, avg_assists, avg_goals_assists, avg_clean_sheets,
                                      avg_subs_out, avg_subs_in, avg_own_goals, avg_yellow_cards, avg_red_cards]

                season_stats_in_single_team[league] = league_stats
                season_extra_stats_in_single_team[league] = league_extra_stats
                overall_by_season = list(map(lambda t: t[0] + t[1], zip(overall_by_season, league_stats)))

            if season_stats_in_single_team:
                season_stats_by_team[team] = season_stats_in_single_team
                season_extra_stats_by_team[team] = season_extra_stats_in_single_team
        if season_stats_by_team:
            stats_by_season[season] = season_stats_by_team
            extra_stats_by_season[season] = season_extra_stats_by_team

    overall_matches = (Match.objects.filter(team_guest_start=player, is_played=True).count() +
                       Match.objects.filter(team_home_start=player, is_played=True).count() +
                       Match.objects.filter(~(Q(team_guest_start=player) | Q(team_home_start=player)),
                                            is_played=True, match_substitutions__player_in=player).distinct().count())

    overall_goals = Goal.objects.filter(author=player, match__is_played=True).count()
    overall_assists = Goal.objects.filter(assistent=player, match__is_played=True).count()
    overall_goals_assists = overall_goals + overall_assists
    overall_clean_sheets = OtherEvents.objects.cs().filter(author=player, match__is_played=True).count()
    overall_subs_out = Substitution.objects.filter(player_out=player, match__is_played=True).count()
    overall_subs_in = Substitution.objects.filter(player_in=player, match__is_played=True).count()
    overall_ogs = OtherEvents.objects.ogs().filter(author=player, match__is_played=True).count()
    overall_yellow_cards = OtherEvents.objects.yellow_cards().filter(author=player, match__is_played=True).count()
    overall_red_cards = OtherEvents.objects.red_cards().filter(author=player, match__is_played=True).count()

    overall_stats = [overall_matches, overall_goals, overall_assists, overall_goals_assists, overall_clean_sheets,
                     overall_subs_out, overall_subs_in, overall_ogs, overall_yellow_cards, overall_red_cards]

    overall_avg_goals = overall_goals / (overall_matches or 1)
    overall_avg_assists = overall_assists / (overall_matches or 1)
    overall_avg_goals_assists = overall_goals_assists / (overall_matches or 1)
    overall_avg_clean_sheets = overall_clean_sheets / (overall_matches or 1)
    overall_avg_yellow_cards = overall_yellow_cards / (overall_matches or 1)
    overall_avg_red_cards = overall_red_cards / (overall_matches or 1)
    overall_avg_own_goals = overall_ogs / (overall_matches or 1)
    overall_avg_subs_in = overall_subs_in / (overall_matches or 1)
    overall_avg_subs_out = overall_subs_out / (overall_matches or 1)

    overall_extra_stats = [overall_matches, overall_avg_goals, overall_avg_assists, overall_avg_goals_assists,
                           overall_avg_clean_sheets, overall_avg_subs_out, overall_avg_subs_in, overall_avg_own_goals,
                           overall_avg_yellow_cards, overall_avg_red_cards]

    first_match = (Match.objects.filter(Q(team_home_start=player) | Q(team_guest_start=player) |
                                        Q(match_substitutions__player_in=player))
                   .filter(is_played=True, match_date__isnull=False)
                   .order_by('match_date').first())

    fastest_goal = Goal.objects.filter(author=player).order_by('time_min', 'time_sec').first()
    latest_goal = Goal.objects.filter(author=player).order_by('-time_min', '-time_sec').first()
    most_goals_in_match = (Match.objects.filter(match_goal__author=player)
                           .annotate(goals=Count('id', filter=Q(match_goal__author=player)))
                           .order_by('-goals').first())
    most_assists_in_match = (Match.objects.filter(match_goal__assistent=player)
                             .annotate(assists=Count('id', filter=Q(match_goal__assistent=player)))
                             .order_by('-assists').first())
    most_goals_assists_in_match = (Match.objects.filter(Q(match_goal__author=player) | Q(match_goal__assistent=player))
                                   .annotate(actions=Count('id', filter=Q(match_goal__assistent=player) |
                                                                                  Q(match_goal__author=player)))
                                   .order_by('-actions').first())
    most_goals_in_season = (Goal.objects.filter(author=player)
                            .values(season=F('match__league__championship'))
                            .annotate(goals=Count('author'))
                            .order_by('-goals').first())
    most_assists_in_season = (Goal.objects.filter(assistent=player).
                              values(season=F('match__league__championship'))
                              .annotate(assists=Count('assistent'))
                              .order_by('-assists').first())
    most_goals_assists_in_season = (Goal.objects.filter(Q(author=player) | Q(assistent=player))
                                    .values(season=F('match__league__championship'))
                                    .annotate(actions=Count('author'))
                                    .order_by('-actions').first())
    most_cs_in_season = (OtherEvents.objects.cs().filter(Q(author=player))
                                    .values(season=F('match__league__championship'))
                                    .annotate(cs=Count('author'))
                                    .order_by('-cs').first())


    other_stats = {}
    other_stats['first_match'] = first_match
    other_stats['fastest_goal'] = fastest_goal
    other_stats['latest_goal'] = latest_goal
    other_stats['most_goals_in_match'] = most_goals_in_match
    other_stats['most_assists_in_match'] = most_assists_in_match
    other_stats['most_goals_assists_in_match'] = most_goals_assists_in_match
    if most_goals_in_season:
        other_stats['most_goals_in_season'] = {
            'goals': most_goals_in_season['goals'],
            'season': Season.objects.get(pk=most_goals_in_season['season'])
        }
    if most_assists_in_season:
        other_stats['most_assists_in_season'] = {
            'assists': most_assists_in_season['assists'],
            'season': Season.objects.get(pk=most_assists_in_season['season'])
        }
    if most_goals_assists_in_season:
        other_stats['most_goals_assists_in_season'] = {
            'actions': most_goals_assists_in_season['actions'],
            'season': Season.objects.get(pk=most_goals_assists_in_season['season'])
        }
    if most_cs_in_season:
        other_stats['most_cs_in_season'] = {
            'cs': most_cs_in_season['cs'],
            'season': Season.objects.get(pk=most_cs_in_season['season'])
        }

    return {
        'stats': stats_by_season,
        'extra_stats': extra_stats_by_season,
        'user': user,
        'overall_stats': overall_stats,
        'overall_extra_stats': overall_extra_stats,
        'other_stats': other_stats
    }


@register.filter
def rows_player_stat(user, season):
    try:
        player = user.user_player
    except:
        return 0
    rows_count = 0
    player_transfers = PlayerTransfer.objects.filter(~Q(to_team=None), season_join=season,
                                                     trans_player=player).distinct('to_team')
    leagues = season.tournaments_in_season.all()
    for transfer in player_transfers:
        for league in leagues:
            matches_in_league = (Match.objects.filter(team_guest=transfer.to_team, team_guest_start=player,
                                                      is_played=True, league=league).count() +
                                 Match.objects.filter(team_home=transfer.to_team, team_home_start=player,
                                                      is_played=True, league=league).count() +
                                 Match.objects.filter(~(Q(team_guest_start=player) | Q(team_home_start=player)),
                                                      is_played=True, match_substitutions__team=transfer.to_team,
                                                      match_substitutions__player_in=player,
                                                      league=league).distinct().count())

            if transfer.to_team in league.teams.all() and matches_in_league > 0:
                rows_count += 1
    return rows_count


#   Для детальной статы матча
@register.filter
def events_sorted(match: Match):
    events = match.match_event.all()
    substit = match.match_substitutions.all()
    all_events = list(match.match_goal.all())
    for e in events:
        all_events.append(e)
    for s in substit:
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
        if i != None:
            pi[i].append(m)
    pi = sorted(pi, key=lambda x: x[2].id)
    return pi


@register.filter
def team_score_in_match(team, match):
    if team == match.team_home:
        return match.score_home
    elif team == match.team_guest:
        return match.score_guest
    else:
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
    elif tour.number == tours_count - 1:
        return '1/2'
    elif tour.number == tours_count - 2:
        return '1/4'
    elif tour.number == tours_count - 3:
        return '1/8'
    else:
        return '{} раунд'.format(tour.number)


@register.inclusion_tag('tournament/include/league_table.html')
def league_table(league):
    b = list(Team.objects.filter(leagues=league))
    c = len(b)
    points = [0 for _ in range(c)]  # Количество очков
    diffrence = [0 for _ in range(c)]  # Разница мячей
    scores = [0 for _ in range(c)]  # Мячей забито
    consided = [0 for _ in range(c)]  # Мячей пропущено
    matches_played = [0 for _ in range(c)]  # Игр сыграно
    wins = [0 for _ in range(c)]  # Побед
    draws = [0 for _ in range(c)]  # Ничей
    looses = [0 for _ in range(c)]  # Поражений
    last_matches = [[] for _ in range(c)]
    for i, team in enumerate(b):
        matches = Match.objects.filter((Q(team_home=team) | Q(team_guest=team)), league=league, is_played=True)
        matches_played[i] = matches.count()
        # last_matches[i] = [(m, 0) for m in matches]
        win_count = 0
        draw_count = 0
        loose_count = 0
        goals_scores_all = 0
        goals_consided_all = 0
        for m in matches:

            if team == m.team_home:
                score_team = m.score_home
                score_opp = m.score_guest
            elif team == m.team_guest:
                score_team = m.score_guest
                score_opp = m.score_home
            else:
                return None

            goals_scores_all += score_team
            goals_consided_all += score_opp

            if score_team > score_opp:
                win_count += 1
                last_matches[i].append((m, 1))
            elif score_team == score_opp:
                draw_count += 1
                last_matches[i].append((m, 0))
            else:
                loose_count += 1
                last_matches[i].append((m, -1))

        last_matches[i] = sorted(last_matches[i], key=lambda x: x[0].numb_tour.number)[-5:]
        points[i] = win_count * 3 + draw_count * 1
        diffrence[i] = goals_scores_all - goals_consided_all
        scores[i] = goals_scores_all
        consided[i] = goals_consided_all
        wins[i] = win_count
        looses[i] = loose_count
        draws[i] = draw_count

    l = zip(b, matches_played, wins, draws, looses, scores, consided, diffrence, points, last_matches)
    s1 = sorted(l, key=lambda x: x[5], reverse=True)
    s2 = sorted(s1, key=lambda x: x[7], reverse=True)
    ls = sorted(s2, key=lambda x: x[8], reverse=True)

    result = []
    i = 0
    while i < len(ls) - 1:
        mini_table = [ls[i][0]]
        mini_res = [ls[i]]
        k = i
        for j in range(i + 1, len(ls)):
            if ls[i][8] == ls[j][8]:
                mini_table.append(ls[j][0])
                mini_res.append(ls[j])
                k += 1
            else:
                k += 1
                break
        if len(mini_table) >= 2:
            c = len(mini_table)
            points = [0 for _ in range(c)]  # Количество очков
            diffrence = [0 for _ in range(c)]  # Разница мячей
            scores = [0 for _ in range(c)]  # Мячей забито
            consided = [0 for _ in range(c)]  # Мячей пропущено
            matches_played = [0 for _ in range(c)]  # Игр сыграно
            wins = [0 for _ in range(c)]  # Побед
            draws = [0 for _ in range(c)]  # Ничей
            looses = [0 for _ in range(c)]  # Поражений
            for i, team in enumerate(mini_table):
                matches = []
                matches_all = Match.objects.filter((Q(team_home=team) | Q(team_guest=team)), league=league,
                                                   is_played=True)
                for mm in matches_all:
                    if (mm.team_home in mini_table) and (mm.team_guest in mini_table):
                        matches.append(mm)
                matches_played[i] = len(matches)
                win_count = 0
                draw_count = 0
                loose_count = 0
                goals_scores_all = 0
                goals_consided_all = 0
                for m in matches:

                    if team == m.team_home:
                        score_team = m.score_home
                        score_opp = m.score_guest
                    elif team == m.team_guest:
                        score_team = m.score_guest
                        score_opp = m.score_home
                    else:
                        return None

                    goals_scores_all += score_team
                    goals_consided_all += score_opp

                    if score_team > score_opp:
                        win_count += 1
                    elif score_team == score_opp:
                        draw_count += 1
                    else:
                        loose_count += 1
                points[i] = win_count * 3 + draw_count * 1
                diffrence[i] = goals_scores_all - goals_consided_all
                scores[i] = goals_scores_all
                consided[i] = goals_consided_all
                wins[i] = win_count
                looses[i] = loose_count
                draws[i] = draw_count
            l = zip(mini_table, matches_played, wins, draws, looses, scores, consided, diffrence, points)
            s1 = sorted(l, key=lambda x: x[5], reverse=True)
            s2 = sorted(s1, key=lambda x: x[7], reverse=True)
            lss = sorted(s2, key=lambda x: x[8], reverse=True)
            for lll in lss:
                for h in mini_res:
                    if lll[0] == h[0]:
                        result.append(h)
                        break
        else:
            result.append(mini_res[0])
        i = k
    if len(result) < len(ls):
        result.append(ls[len(ls) - 1])
    return {'teams': result}


# Конец тегов и фильтров для таблицы лиги


@register.filter
def top_goalscorers(league):
    players = Player.objects.filter(goals__match__league=league).annotate(
        goals_c=Count('goals__match__league')).order_by('-goals_c')
    return players


@register.filter
def top_assistent(league):
    players = Player.objects.filter(assists__match__league=league).annotate(
        ass_c=Count('assists__match__league')).order_by('-ass_c')
    return players


@register.filter
def top_clean_sheets(league):
    players = Player.objects.filter(event__match__league=league, event__event='CLN').annotate(
        event_c=Count('event__match__league')).order_by('-event_c')
    return players


#  Капитан и ассистент для профиля команды(контактов)
@register.filter
def get_captain(team):
    return Player.objects.filter(team=team, role='C')


@register.filter
def get_team_assistent(team):
    return Player.objects.filter(team=team, role='AC')


@register.filter
def all_league_season(team, season):
    return League.objects.filter(teams=team, championship=season).order_by('-id')


@register.filter
def all_seasons(team):
    return Season.objects.filter(tournaments_in_season__teams=team).distinct().order_by('-number')


def sort_teams(league):
    b = list(Team.objects.filter(leagues=league))
    c = len(b)
    points = [0 for _ in range(c)]  # Количество очков
    diffrence = [0 for _ in range(c)]  # Разница мячей
    scores = [0 for _ in range(c)]  # Мячей забито
    consided = [0 for _ in range(c)]  # Мячей пропущено
    matches_played = [0 for _ in range(c)]  # Игр сыграно
    wins = [0 for _ in range(c)]  # Побед
    draws = [0 for _ in range(c)]  # Ничей
    looses = [0 for _ in range(c)]  # Поражений
    last_matches = [[] for _ in range(c)]
    for i, team in enumerate(b):
        matches = Match.objects.filter((Q(team_home=team) | Q(team_guest=team)), league=league, is_played=True)
        matches_played[i] = matches.count()
        win_count = 0
        draw_count = 0
        loose_count = 0
        goals_scores_all = 0
        goals_consided_all = 0
        for m in matches:

            if team == m.team_home:
                score_team = m.score_home
                score_opp = m.score_guest
            elif team == m.team_guest:
                score_team = m.score_guest
                score_opp = m.score_home
            else:
                return None

            goals_scores_all += score_team
            goals_consided_all += score_opp

            if score_team > score_opp:
                win_count += 1
                last_matches[i].append((m, 1))
            elif score_team == score_opp:
                draw_count += 1
                last_matches[i].append((m, 0))
            else:
                loose_count += 1
                last_matches[i].append((m, -1))

        last_matches[i] = sorted(last_matches[i], key=lambda x: x[0].numb_tour.number)[-5:]
        points[i] = win_count * 3 + draw_count * 1
        diffrence[i] = goals_scores_all - goals_consided_all
        scores[i] = goals_scores_all
        consided[i] = goals_consided_all
        wins[i] = win_count
        looses[i] = loose_count
        draws[i] = draw_count

    l = zip(b, matches_played, wins, draws, looses, scores, consided, diffrence, points, last_matches)
    s1 = sorted(l, key=lambda x: x[5], reverse=True)
    s2 = sorted(s1, key=lambda x: x[7], reverse=True)
    ls = sorted(s2, key=lambda x: x[8], reverse=True)

    result = []
    i = 0
    while i < len(ls) - 1:
        mini_table = [ls[i][0]]
        mini_res = [ls[i]]
        k = i
        for j in range(i + 1, len(ls)):
            if ls[i][8] == ls[j][8]:
                mini_table.append(ls[j][0])
                mini_res.append(ls[j])
                k += 1
            else:
                k += 1
                break
        if len(mini_table) >= 2:
            c = len(mini_table)
            points = [0 for _ in range(c)]  # Количество очков
            diffrence = [0 for _ in range(c)]  # Разница мячей
            scores = [0 for _ in range(c)]  # Мячей забито
            consided = [0 for _ in range(c)]  # Мячей пропущено
            matches_played = [0 for _ in range(c)]  # Игр сыграно
            wins = [0 for _ in range(c)]  # Побед
            draws = [0 for _ in range(c)]  # Ничей
            looses = [0 for _ in range(c)]  # Поражений
            for i, team in enumerate(mini_table):
                matches = []
                matches_all = Match.objects.filter((Q(team_home=team) | Q(team_guest=team)), league=league,
                                                   is_played=True)
                for mm in matches_all:
                    if (mm.team_home in mini_table) and (mm.team_guest in mini_table):
                        matches.append(mm)
                matches_played[i] = len(matches)
                win_count = 0
                draw_count = 0
                loose_count = 0
                goals_scores_all = 0
                goals_consided_all = 0
                for m in matches:

                    if team == m.team_home:
                        score_team = m.score_home
                        score_opp = m.score_guest
                    elif team == m.team_guest:
                        score_team = m.score_guest
                        score_opp = m.score_home
                    else:
                        return None

                    goals_scores_all += score_team
                    goals_consided_all += score_opp

                    if score_team > score_opp:
                        win_count += 1
                    elif score_team == score_opp:
                        draw_count += 1
                    else:
                        loose_count += 1
                points[i] = win_count * 3 + draw_count * 1
                diffrence[i] = goals_scores_all - goals_consided_all
                scores[i] = goals_scores_all
                consided[i] = goals_consided_all
                wins[i] = win_count
                looses[i] = loose_count
                draws[i] = draw_count
            l = zip(mini_table, matches_played, wins, draws, looses, scores, consided, diffrence, points)
            s1 = sorted(l, key=lambda x: x[5], reverse=True)
            s2 = sorted(s1, key=lambda x: x[7], reverse=True)
            lss = sorted(s2, key=lambda x: x[8], reverse=True)
            for lll in lss:
                for h in mini_res:
                    if lll[0] == h[0]:
                        result.append(h)
                        break
        else:
            result.append(mini_res[0])
        i = k
    if len(result) < len(ls):
        result.append(ls[len(ls) - 1])
    lit = [i[0] for i in result]
    return lit


@register.filter
def current_league(team):
    try:
        return League.objects.filter(teams=team, is_cup=False, championship__is_active=True).first()
    except:
        return None


@register.filter
def current_position(team):
    league = current_league(team)
    if not league:
        return '-'

    a = list(sort_teams(league))
    return a.index(team) + 1


@register.filter
def teams_in_league_count(team):
    league = current_league(team)
    if not league:
        return '-'

    return league.teams.count()


@register.filter
def tour_matches_in_league(league, tour):
    return Match.objects.filter(league=league, tour_num=tour)


@register.filter
def team_matches_in_league(team, league):
    return Match.objects.filter((Q(team_home=team) | Q(team_guest=team)), league=league).order_by('numb_tour')


# сортировка игроков в профиле команды по играм
@register.filter
def sort_players(players):
    a = sorted(players, key=lambda x: matches_in_team_current(x, x.team), reverse=True)
    return a


@register.filter
def players_in_history(team):
    players_trans = PlayerTransfer.objects.filter(to_team=team)
    players = []
    for i in players_trans:
        if (matches_in_team(i.trans_player, team) > 0) and (i.trans_player not in players):
            players.append(i.trans_player)
    a = sorted(players, key=lambda x: matches_in_team(x, team), reverse=True)
    return a


@register.filter
def team_achievements_by_season(team):
    achievements = team.achievements.all()
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
    emergency_slots_count = league_slots.emergency_count
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
    matches = Match.objects.filter(Q(team_home__in=teams) | Q(team_guest__in=teams), league__in=leagues,
                                   is_played=False, numb_tour__date_from__lte=timezone.now().date())
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
