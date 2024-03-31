import datetime
from typing import Optional

from django import template
from django.contrib.auth.models import User
from django.db.models import Q, Count, QuerySet
from django.utils import timezone

from ..models import FreeAgent, OtherEvents, Goal, Match, League, Team, Player, Substitution, Season, PlayerTransfer, \
    Disqualification, Postponement

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
@register.filter
def event_count(player, type):
    return OtherEvents.objects.filter(author=player, team=player.team, event=type).count()


@register.filter
def cln_count(player, team):
    return OtherEvents.objects.filter(author=player, team=team, event='CLN').count()


@register.filter
def og_count(player, team):
    return OtherEvents.objects.filter(author=player, team=team, event='OG').count()


@register.filter
def yel_count(player, team):
    return OtherEvents.objects.filter(author=player, team=team, event='YEL').count()


@register.filter
def red_count(player, team):
    return OtherEvents.objects.filter(author=player, team=team, event='RED').count()


@register.filter
def event_count_current(player, type):
    current = Season.objects.filter(is_active=True).first()
    return OtherEvents.objects.filter(author=player, team=player.team, event=type,
                                      match__league__championship=current).count()


#
@register.filter
def goals_in_team(player, team):
    return Goal.objects.filter(author=player, team=team).count()


@register.filter
def goals_in_team_current(player, team):
    current = Season.objects.filter(is_active=True).first()
    return Goal.objects.filter(author=player, team=team, match__league__championship=current).count()


#

@register.filter
def assists_in_team(player, team):
    return Goal.objects.filter(assistent=player, team=team).count()


@register.filter
def assists_in_team_current(player, team):
    current = Season.objects.filter(is_active=True).first()
    return Goal.objects.filter(assistent=player, team=team, match__league__championship=current).count()


#


@register.filter
def replaced_in_team(player, team):
    return Substitution.objects.filter(team=team, player_out=player).count()


@register.filter
def replaced_in_team_current(player, team):
    current = Season.objects.filter(is_active=True).first()
    return Substitution.objects.filter(team=team, player_out=player, match__league__championship=current).count()


#
@register.filter
def join_game_in_team(player, team):
    return Substitution.objects.filter(team=team, player_in=player).count()


@register.filter
def join_game_in_team_current(player, team):
    current = Season.objects.filter(is_active=True).first()
    return Substitution.objects.filter(team=team, player_in=player, match__league__championship=current).count()


#


@register.filter
def matches_in_team_current(player, team):
    return Match.objects.filter(team_guest=team, team_guest_start=player,
                                league__championship__is_active=True).count() + Match.objects.filter(
        team_home=team, team_home_start=player, league__championship__is_active=True).count() + Match.objects.filter(
        ~(Q(team_guest_start=player) | Q(team_home_start=player)), match_substitutions__team=team,
        match_substitutions__player_in=player, league__championship__is_active=True
    ).distinct().count()


@register.filter
def matches_in_team(player, team):
    return Match.objects.filter(team_guest=team, team_guest_start=player).count() + Match.objects.filter(
        team_home=team, team_home_start=player).count() + Match.objects.filter(
        ~(Q(team_guest_start=player) | Q(team_home_start=player)), match_substitutions__team=team,
        match_substitutions__player_in=player
    ).distinct().count()


@register.inclusion_tag('tournament/include/team_statistics.html')
def team_statistics(team: Team):
    stats_by_season = {}
    seasons = Season.objects.filter(tournaments_in_season__teams=team).distinct().order_by('number')
    print('seasons: ', seasons.count())
    for season in seasons:
        season_stats = {}

        leagues = list(League.objects.filter(championship=season, teams=team).order_by('id'))
        for league in leagues:
            league_stats = []
            matches_count = Match.objects.filter(Q(team_home=team) | Q(team_guest=team), league=league).count()

            if matches_count == 0:
                continue

            league_stats.append(matches_count)
            goal_count = Goal.objects.filter(team=team, match__league=league).count()
            league_stats.append(goal_count)
            assists_count = Goal.objects.filter(team=team, assistent__isnull=False, match__league=league).count()
            league_stats.append(assists_count)
            clean_sheets = OtherEvents.objects.filter(team=team, event='CLN', match__league=league).count()
            yellow_cards = OtherEvents.objects.filter(team=team, event='YEL', match__league=league).count()
            red_cards = OtherEvents.objects.filter(team=team, event='RED', match__league=league).count()
            own_goals = OtherEvents.objects.filter(team=team, event='OG', match__league=league).count()
            subs = Substitution.objects.filter(team=team, match__league=league).count()
            league_stats.append(clean_sheets)
            league_stats.append(subs)
            league_stats.append(own_goals)
            league_stats.append(yellow_cards)
            league_stats.append(red_cards)

            season_stats[league] = league_stats

        print(season_stats)

        if season_stats:
            stats_by_season[season] = season_stats

    print(stats_by_season)

    overall_stats = []
    matches = (Match.objects.filter(Q(team_home=team) | Q(team_guest=team)).count())
    overall_stats.append(matches)
    overall_stats.append(Goal.objects.filter(team=team).count())
    overall_stats.append(Goal.objects.filter(assistent__isnull=False, team=team).count())
    overall_stats.append(OtherEvents.objects.filter(event='CLN', team=team).count())
    overall_stats.append(Substitution.objects.filter(team=team).count())
    overall_stats.append(OtherEvents.objects.filter(event='OG', team=team).count())
    overall_stats.append(OtherEvents.objects.filter(event='YEL', team=team).count())
    overall_stats.append(OtherEvents.objects.filter(event='RED', team=team).count())

    return {'team': team, 'stats': stats_by_season, 'overall_stats': overall_stats}


@register.filter
def rows_team_stat(team: Team, season: Season):
    leagues = (League.objects
                    .filter(Q(matches_in_league__team_home=team) | Q(matches_in_league__team_guest=team),
                            teams=team, championship=season)
                    .annotate(matches_count=Count('matches_in_league'))
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
    player_transfers = PlayerTransfer.objects.filter(trans_player=player)
    sss = []
    for player_transfer in player_transfers:
        if player_transfer.season_join not in sss:
            sss.append(player_transfer.season_join)
    seasons = sorted(sss, key=lambda x: x.number)
    for season in seasons:
        season_stats_by_team = {}
        transfer_teams = list(
            PlayerTransfer.objects.filter(~Q(to_team=None), season_join=season, trans_player=player).distinct('to_team'))
        for transfer_team in transfer_teams:
            season_stats_in_single_team = {}
            team = transfer_team.to_team
            leagues = list(League.objects.filter(championship=season, teams=team).order_by('id'))
            for league in leagues:
                league_stats = []
                matches_count = (Match.objects.filter(team_guest=team, team_guest_start=player, league=league).count() +
                                 Match.objects.filter(team_home=team, team_home_start=player, league=league).count() +
                                 Match.objects.filter(~(Q(team_guest_start=player) | Q(team_home_start=player)),
                                                      match_substitutions__team=team,
                                                      match_substitutions__player_in=player, league=league).distinct().count())

                if matches_count == 0:
                    continue

                league_stats.append(matches_count)
                goal_count = Goal.objects.filter(author=user.user_player, team=team,
                                                 match__league=league).count()
                league_stats.append(goal_count)
                assists_count = Goal.objects.filter(assistent=user.user_player, team=team,
                                                    match__league=league).count()
                league_stats.append(assists_count)
                clean_sheets = OtherEvents.objects.filter(author=user.user_player, team=team, event='CLN',
                                                          match__league=league).count()
                yellow_cards = OtherEvents.objects.filter(author=user.user_player, team=team, event='YEL',
                                                          match__league=league).count()
                red_cards = OtherEvents.objects.filter(author=user.user_player, team=team, event='RED',
                                                       match__league=league).count()
                own_goals = OtherEvents.objects.filter(author=user.user_player, team=team, event='OG',
                                                       match__league=league).count()
                subs_in = Substitution.objects.filter(team=team, player_in=user.user_player,
                                                      match__league=league).count()
                subs_out = Substitution.objects.filter(team=team, player_out=user.user_player,
                                                       match__league=league).count()
                league_stats.append(clean_sheets)
                league_stats.append(subs_out)
                league_stats.append(subs_in)
                league_stats.append(own_goals)
                league_stats.append(yellow_cards)
                league_stats.append(red_cards)
                season_stats_in_single_team[league] = league_stats

            if season_stats_in_single_team:
                season_stats_by_team[team] = season_stats_in_single_team
        if season_stats_by_team:
            stats_by_season[season] = season_stats_by_team

    overall_stats = []
    mc = (Match.objects.filter(team_guest_start=player).count() +
          Match.objects.filter(team_home_start=player).count() +
          Match.objects.filter(~(Q(team_guest_start=player) | Q(team_home_start=player)),
                               match_substitutions__player_in=player).distinct().count())
    overall_stats.append(mc)

    overall_stats.append(Goal.objects.filter(author=player).count())
    overall_stats.append(Goal.objects.filter(assistent=player).count())
    overall_stats.append(OtherEvents.objects.filter(event='CLN', author=player).count())
    overall_stats.append(Substitution.objects.filter(player_out=player).count())
    overall_stats.append(Substitution.objects.filter(player_in=player).count())
    overall_stats.append(OtherEvents.objects.filter(event='OG', author=player).count())
    overall_stats.append(OtherEvents.objects.filter(event='YEL', author=player).count())
    overall_stats.append(OtherEvents.objects.filter(event='RED', author=player).count())

    return {'stat': stats_by_season, 'user': user, 'overall': overall_stats}


@register.filter
def rows_player_stat(user, season):
    try:
        player = user.user_player
    except:
        return 0
    rows_count = 0
    player_transfers = PlayerTransfer.objects.filter(~Q(to_team=None), season_join=season, trans_player=player).distinct('to_team')
    leagues = season.tournaments_in_season.all()
    for transfer in player_transfers:
        for league in leagues:
            matches_in_league = (Match.objects.filter(team_guest=transfer.to_team, team_guest_start=player, league=league).count() +
                                 Match.objects.filter(team_home=transfer.to_team, team_home_start=player, league=league).count() +
                                 Match.objects.filter(~(Q(team_guest_start=player) | Q(team_home_start=player)),
                                                     match_substitutions__team=transfer.to_team,
                                                     match_substitutions__player_in=player, league=league).distinct().count())

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
def event_time(event):
    return datetime.time(minute=event.time_min, second=event.time_sec).strftime('%M:%S')


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
