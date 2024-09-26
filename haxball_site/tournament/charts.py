import plotly.express as px
from decouple import config
from django.db.models import Case, Count, F, FloatField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Cast, Coalesce

from .models import Goal, Match, MatchResult, OtherEvents, Season


class StatCharts:
    def matches(self, player):
        matches_by_season = self.get_matches_by_season(player)
        (
            seasons,
            matches,
            wins,
            draws,
            losses
        ) = self.column_values_list(matches_by_season, 'season_title', 'matches', 'wins', 'draws', 'losses')

        matches_chart = Charts.matches_by_season(seasons, matches)
        wdl_chart = Charts.wdl(seasons, wins, draws, losses)
        wdl_percentage_chart = Charts.wdl_percentage(seasons, wins, draws, losses)

        matches_by_team = self.get_matches_by_team(player)
        teams, matches = self.column_values_list(matches_by_team, 'team', 'matches')
        matches_by_team_chart = Charts.matches_by_team(teams, matches)

        matches_by_tournament = self.get_matches_by_tournament(player)
        tournaments, matches = self.column_values_list(matches_by_tournament, 'tournament', 'matches')
        matches_by_tournament_chart = Charts.matches_by_tournament(tournaments, matches)

        return {
            'bar_charts': [matches_chart, wdl_chart, wdl_percentage_chart],
            'pie_charts': [matches_by_team_chart, matches_by_tournament_chart],
        }

    def goals_assists(self, player):
        goals_by_season = self.get_goals_by_season(player)
        goals_by_team = self.get_goals_by_team(player)
        goals_by_tournament = self.get_goals_by_tournament(player)

        (
            seasons,
            goals,
            assists,
            goals_per_match,
            assists_per_match,
            goals_assists_per_match,
        ) = self.column_values_list(
            goals_by_season,
            'season_title', 'goals', 'assists', 'goals_per_match', 'assists_per_match', 'goals_assists_per_match'
        )

        teams, goals_for_team, assists_for_team, goals_assists_for_team = self.column_values_list(
            goals_by_team,
            'team_title', 'goals', 'assists', 'goals_assists'
        )

        tournaments, goals_in_tournament, assists_in_tournament, goals_assists_in_tournament = self.column_values_list(
            goals_by_tournament,
            'tournament', 'goals', 'assists', 'goals_assists'
        )

        goals_chart = Charts.goals_by_season(seasons, goals)
        goals_per_match_chart = Charts.goals_per_match_by_season(seasons, goals_per_match)
        goals_by_team_chart = Charts.goals_by_team(teams, goals_for_team)
        goals_by_tournament_chart = Charts.goals_by_tournament(tournaments, goals_in_tournament)

        assists_chart = Charts.assists_by_season(seasons, assists)
        assists_per_match_chart = Charts.assists_per_match_by_season(seasons, assists_per_match)
        assists_by_team_chart = Charts.assists_by_team(teams, assists_for_team)
        assists_by_tournament_chart = Charts.assists_by_tournament(tournaments, assists_in_tournament)

        goals_assists_chart = Charts.goals_assists_by_season(seasons, goals, assists)
        goals_assists_per_match_chart = Charts.goals_assists_per_match_by_season(seasons, goals_assists_per_match)
        goals_assists_by_team_chart = Charts.goals_assists_by_team(teams, goals_assists_for_team)
        goals_assists_by_tournament_chart = Charts.goals_assists_by_tournament(tournaments, goals_assists_in_tournament)

        return {
            'bar_charts': [
                goals_chart, goals_per_match_chart,
                assists_chart, assists_per_match_chart,
                goals_assists_chart, goals_assists_per_match_chart,
            ],
            'pie_charts': [
                goals_by_team_chart, goals_by_tournament_chart,
                assists_by_team_chart, assists_by_tournament_chart,
                goals_assists_by_team_chart, goals_assists_by_tournament_chart,
            ]
        }

    def cs(self, player):
        cs_by_season = self.get_cs_by_season(player)
        cs_by_team = self.get_cs_by_team(player)
        cs_by_tournament = self.get_cs_by_tournament(player)

        seasons, cs, cs_per_match = self.column_values_list(cs_by_season, 'season_title', 'cs', 'cs_per_match')

        cs_by_season_chart = Charts.cs_by_season(seasons, cs)
        cs_per_match_by_season_chart = Charts.cs_per_match_by_season(seasons, cs_per_match)

        teams, cs = self.column_values_list(cs_by_team, 'team_title', 'cs')
        cs_by_team_chart = Charts.cs_by_team(teams, cs)

        tournaments, cs = self.column_values_list(cs_by_tournament, 'tournament', 'cs')
        cs_by_tournament_chart = Charts.cs_by_tournament(tournaments, cs)

        return {
            'bar_charts': [cs_by_season_chart, cs_per_match_by_season_chart],
            'pie_charts': [cs_by_team_chart, cs_by_tournament_chart],
        }

    def cards(self, player):
        cards_by_season = self.get_cards_by_season(player)
        cards_by_team = self.get_cards_by_team(player)
        cards_by_tournament = self.get_cards_by_tournament(player)

        (
            seasons,
            yellow_cards,
            red_cards,
            yellow_cards_per_match,
            red_cards_per_match
        ) = self.column_values_list(
            cards_by_season,
            'season_title', 'yellow_cards', 'red_cards', 'yellow_cards_per_match', 'red_cards_per_match'
        )

        cards_by_season_chart = Charts.cards_by_season(seasons, yellow_cards, red_cards)
        cards_per_match_by_season_chart = Charts.cards_per_match_by_season(
            seasons, yellow_cards_per_match, red_cards_per_match
        )

        teams, yellow_cards, red_cards = self.column_values_list(
            cards_by_team,
            'team_title', 'yellow_cards', 'red_cards'
        )
        yellow_cards_by_team_chart = Charts.yellow_cards_by_team(teams, yellow_cards)
        red_cards_by_team_chart = Charts.red_cards_by_team(teams, red_cards)

        tournaments, yellow_cards, red_cards = self.column_values_list(
            cards_by_tournament,
            'tournament', 'yellow_cards', 'red_cards'
        )
        yellow_cards_by_tournament_chart = Charts.yellow_cards_by_tournament(tournaments, yellow_cards)
        red_cards_by_tournament_chart = Charts.red_cards_by_tournament(tournaments, red_cards)

        return {
            'bar_charts': [cards_by_season_chart, cards_per_match_by_season_chart],
            'pie_charts': [yellow_cards_by_team_chart, yellow_cards_by_tournament_chart,
                           red_cards_by_team_chart, red_cards_by_tournament_chart],
        }

    @staticmethod
    def column_values_list(queryset, *columns):
        if not queryset.exists():
            return [[] for _ in columns]

        return list(zip(*queryset.values_list(*columns)))

    @staticmethod
    def get_matches_by_season(player):
        return (
            Match.objects
            .filter(Q(team_home_start=player) | Q(team_guest_start=player) | Q(match_substitutions__player_in=player),
                    is_played=True)
            .values(season_title=F('league__championship__short_title'))
            .annotate(
                matches=Count('pk', distinct=True),
                team=Case(
                    When(team_home_start=player, then=F('team_home')),
                    When(team_guest_start=player, then=F('team_guest')),
                    When(match_substitutions__player_in=player, then=F('match_substitutions__team')),
                    default=None
                )
            )
            .filter(matches__gt=0)
            .annotate(wins=Count('pk', distinct=True, filter=Q(result__winner=F('team'))),
                      draws=Count('pk', distinct=True, filter=Q(result__value=MatchResult.DRAW)),
                      losses=Count('pk', distinct=True,
                                   filter=~Q(result__value=MatchResult.DRAW) & ~Q(result__winner=F('team')))
                      )
            .annotate(
                wins_percentage=Cast(F('wins'), FloatField()) / F('matches'),
                draws_percentage=Cast(F('draws'), FloatField()) / F('matches'),
                losses_percentage=Cast(F('losses'), FloatField()) / F('matches'),
            )
            .order_by('league__championship__number')
        )

    @staticmethod
    def get_matches_by_team(player):
        return (
            Match.objects
            .filter(Q(team_home_start=player) | Q(team_guest_start=player) | Q(match_substitutions__player_in=player),
                    is_played=True)
            .annotate(
                team=Case(
                    When(team_home_start=player, then=F('team_home__title')),
                    When(team_guest_start=player, then=F('team_guest__title')),
                    When(match_substitutions__player_in=player, then=F('match_substitutions__team__title')),
                    default=Value('Unknown')
                )
            )
            .values('team')
            .annotate(matches=Count('pk', distinct=True))
            .filter(matches__gt=0)
            .order_by('-team')
        )

    @staticmethod
    def get_matches_by_tournament(player):
        return (
            Match.objects
            .filter(Q(team_home_start=player) | Q(team_guest_start=player) | Q(match_substitutions__player_in=player),
                    is_played=True)
            .annotate(
                tournament=Case(
                    When(
                        Q(league__title__istartswith='Высшая') | Q(league__title__istartswith='Единая'),
                        then=Value('Высшая лига')
                    ),
                    When(league__title__istartswith='Первая', then=Value('Первая лига')),
                    When(league__title__istartswith='Вторая', then=Value('Вторая лига')),
                    When(
                        Q(league__title__istartswith='Кубок Высшей') |
                        Q(league__title__istartswith='Кубок Первой') |
                        Q(league__title__istartswith='Кубок Второй') |
                        Q(league__title__istartswith='Кубок лиги'),
                        then=Value('Кубок лиги')
                    ),
                    When(league__title__istartswith='Лига Чемпионов', then=Value('Лига Чемпионов')),
                    When(league__title__istartswith='Кубок России', then=Value('Кубок России')),
                    default=Value('Unknown')
                )
            )
            .values('tournament')
            .annotate(matches=Count('pk', distinct=True),)
            .filter(matches__gt=0)
            .order_by('-matches')
        )

    @staticmethod
    def get_goals_by_season(player):
        matches_subquery = (
            Match.objects
            .filter(
                Q(team_home_start=player) | Q(team_guest_start=player) | Q(match_substitutions__player_in=player),
                league__championship=OuterRef('id'),
                is_played=True
            )
            .order_by()
            .values('league__championship')
            .annotate(c=Count('id', distinct=True))
            .values('c')
        )
        goals_subquery = (
            Goal.objects.filter(match__league__championship=OuterRef('id'), author=player)
            .order_by()
            .values('match__league__championship')
            .annotate(c=Count('*'))
            .values('c')
        )
        assists_subquery = (
            Goal.objects.filter(match__league__championship=OuterRef('id'), assistent=player)
            .order_by()
            .values('match__league__championship')
            .annotate(c=Count('*'))
            .values('c')
        )

        return (
            Season.objects
            .values(season_title=F('short_title'))
            .annotate(
                matches=Coalesce(Subquery(matches_subquery), 0),
                goals=Coalesce(Subquery(goals_subquery), 0),
                assists=Coalesce(Subquery(assists_subquery), 0),
            )
            .filter(matches__gt=0)
            .annotate(
                goals_per_match=Cast(F('goals'), FloatField()) / F('matches'),
                assists_per_match=Cast(F('assists'), FloatField()) / F('matches'),
                goals_assists_per_match=Cast(F('goals') + F('assists'), FloatField()) / F('matches'),
            )
            .order_by('number')
        )

    @staticmethod
    def get_goals_by_team(player):
        return (
            Goal.objects.filter(Q(author=player) | Q(assistent=player))
            .values(team_title=F('team__title'))
            .annotate(
                goals=Count('author', filter=Q(author=player)),
                assists=Count('assistent', filter=Q(assistent=player)),
                goals_assists=F('goals') + F('assists'),
            )
            .order_by('-goals')
        )

    @staticmethod
    def get_goals_by_tournament(player):
        return (
            Goal.objects.filter(Q(author=player) | Q(assistent=player))
            .annotate(
                tournament=Case(
                    When(
                        Q(match__league__title__istartswith='Высшая') | Q(match__league__title__istartswith='Единая'),
                        then=Value('Высшая лига')
                    ),
                    When(match__league__title__istartswith='Первая', then=Value('Первая лига')),
                    When(match__league__title__istartswith='Вторая', then=Value('Вторая лига')),
                    When(
                        Q(match__league__title__istartswith='Кубок Высшей') |
                        Q(match__league__title__istartswith='Кубок Первой') |
                        Q(match__league__title__istartswith='Кубок Второй') |
                        Q(match__league__title__istartswith='Кубок лиги'),
                        then=Value('Кубок лиги')
                    ),
                    When(match__league__title__istartswith='Лига Чемпионов', then=Value('Лига Чемпионов')),
                    When(match__league__title__istartswith='Кубок России', then=Value('Кубок России')),
                    default=Value('Unknown')
                )
            )
            .values('tournament')
            .annotate(
                goals=Count('author', filter=Q(author=player)),
                assists=Count('assistent', filter=Q(assistent=player)),
                goals_assists=F('goals') + F('assists'),
            )
            .order_by('-goals')
        )

    @staticmethod
    def get_cs_by_season(player):
        matches_subquery = (
            Match.objects
            .filter(
                Q(team_home_start=player) | Q(team_guest_start=player) | Q(match_substitutions__player_in=player),
                league__championship=OuterRef('id'),
                is_played=True
            )
            .order_by()
            .values('league__championship')
            .annotate(c=Count('id', distinct=True))
            .values('c')
        )
        cs_subquery = (
            OtherEvents.objects.cs().filter(match__league__championship=OuterRef('id'), author=player)
            .order_by()
            .values('match__league__championship')
            .annotate(c=Count('*'))
            .values('c')
        )

        return (
            Season.objects
            .values(season_title=F('short_title'))
            .annotate(
                matches=Coalesce(Subquery(matches_subquery), 0),
                cs=Coalesce(Subquery(cs_subquery), 0),
            )
            .filter(matches__gt=0)
            .annotate(cs_per_match=Cast(F('cs'), FloatField()) / F('matches'))
            .order_by('number')
        )

    @staticmethod
    def get_cs_by_team(player):
        return (
            OtherEvents.objects.cs().filter(author=player)
            .values(team_title=F('team__title'))
            .annotate(cs=Count('*'))
            .order_by('-cs')
        )

    @staticmethod
    def get_cs_by_tournament(player):
        return (
            OtherEvents.objects.cs().filter(author=player)
            .annotate(
                tournament=Case(
                    When(
                        Q(match__league__title__istartswith='Высшая') | Q(match__league__title__istartswith='Единая'),
                        then=Value('Высшая лига')
                    ),
                    When(match__league__title__istartswith='Первая', then=Value('Первая лига')),
                    When(match__league__title__istartswith='Вторая', then=Value('Вторая лига')),
                    When(
                        Q(match__league__title__istartswith='Кубок Высшей') |
                        Q(match__league__title__istartswith='Кубок Первой') |
                        Q(match__league__title__istartswith='Кубок Второй') |
                        Q(match__league__title__istartswith='Кубок лиги'),
                        then=Value('Кубок лиги')
                    ),
                    When(match__league__title__istartswith='Лига Чемпионов', then=Value('Лига Чемпионов')),
                    When(match__league__title__istartswith='Кубок России', then=Value('Кубок России')),
                    default=Value('Unknown')
                )
            )
            .values('tournament')
            .annotate(cs=Count('*'))
            .order_by('-cs')
        )

    @staticmethod
    def get_cards_by_season(player):
        matches_subquery = (
            Match.objects
            .filter(
                Q(team_home_start=player) | Q(team_guest_start=player) | Q(match_substitutions__player_in=player),
                league__championship=OuterRef('id'),
                is_played=True
            )
            .order_by()
            .values('league__championship')
            .annotate(c=Count('id', distinct=True))
            .values('c')
        )
        yellow_cards_subquery = (
            OtherEvents.objects.filter(match__league__championship=OuterRef('id'), author=player)
            .order_by()
            .values('match__league__championship')
            .annotate(c=Count('id', filter=Q(event=OtherEvents.YELLOW_CARD)))
            .values('c')
        )
        red_cards_subquery = (
            OtherEvents.objects.filter(match__league__championship=OuterRef('id'), author=player)
            .order_by()
            .values('match__league__championship')
            .annotate(c=Count('id', filter=Q(event=OtherEvents.RED_CARD)))
            .values('c')
        )

        return (
            Season.objects
            .values(season_title=F('short_title'))
            .annotate(
                matches=Coalesce(Subquery(matches_subquery), 0),
                yellow_cards=Coalesce(Subquery(yellow_cards_subquery), 0),
                red_cards=Coalesce(Subquery(red_cards_subquery), 0),
            )
            .filter(matches__gt=0)
            .annotate(
                yellow_cards_per_match=Cast(F('yellow_cards'), FloatField()) / F('matches'),
                red_cards_per_match=Cast(F('red_cards'), FloatField()) / F('matches'),
            )
            .order_by('number')
        )

    @staticmethod
    def get_cards_by_team(player):
        return (
            OtherEvents.objects.filter(author=player)
            .values(team_title=F('team__title'))
            .annotate(
                yellow_cards=Count('id', filter=Q(event=OtherEvents.YELLOW_CARD)),
                red_cards=Count('id', filter=Q(event=OtherEvents.RED_CARD)),
                cards=F('yellow_cards') + F('red_cards'),
            )
            .filter(cards__gt=0)
            .order_by('-cards')
        )

    @staticmethod
    def get_cards_by_tournament(player):
        return (
            OtherEvents.objects.filter(author=player)
            .annotate(
                tournament=Case(
                    When(
                        Q(match__league__title__istartswith='Высшая') | Q(match__league__title__istartswith='Единая'),
                        then=Value('Высшая лига')
                    ),
                    When(match__league__title__istartswith='Первая', then=Value('Первая лига')),
                    When(match__league__title__istartswith='Вторая', then=Value('Вторая лига')),
                    When(
                        Q(match__league__title__istartswith='Кубок Высшей') |
                        Q(match__league__title__istartswith='Кубок Первой') |
                        Q(match__league__title__istartswith='Кубок Второй') |
                        Q(match__league__title__istartswith='Кубок лиги'),
                        then=Value('Кубок лиги')
                    ),
                    When(match__league__title__istartswith='Лига Чемпионов', then=Value('Лига Чемпионов')),
                    When(match__league__title__istartswith='Кубок России', then=Value('Кубок России')),
                    default=Value('Unknown')
                )
            )
            .values('tournament')
            .annotate(
                yellow_cards=Count('id', filter=Q(event=OtherEvents.YELLOW_CARD)),
                red_cards=Count('id', filter=Q(event=OtherEvents.RED_CARD)),
                cards=F('yellow_cards') + F('red_cards'),
            )
            .filter(cards__gt=0)
            .order_by('-cards')
        )


class Charts:
    #region Matches
    @staticmethod
    def matches_by_season(seasons, matches):
        fig = px.histogram(
            x=seasons,
            y=matches,
            title='Количество матчей за сезон',
            text_auto=True,
            labels={'x': 'Сезон', 'y': 'Матчи'},
        )
        fig.update_layout(yaxis_title='Матчи')
        fig.update_traces(textfont_size=12, textangle=0, textposition='outside', cliponaxis=False)

        return Charts.render_to_html(fig)

    @staticmethod
    def matches_by_team(teams, matches):
        fig = px.pie(
            names=teams,
            values=matches,
            title='Распределение матчей по командам',
            labels={'values': 'Матчи', 'names': 'Команда'},
        )
        fig.update_layout(legend={'orientation': 'h'})
        fig.update_traces(texttemplate='%{percent} (%{value})')
        if is_empty_data(matches):
            add_no_data_annotation(fig)

        return Charts.render_to_html(fig)

    @staticmethod
    def matches_by_tournament(tournaments, matches):
        fig = px.pie(
            names=tournaments,
            values=matches,
            title='Распределение матчей по турнирам',
            labels={'values': 'Матчи', 'names': 'Турнир'},
        )
        fig.update_layout(legend={'orientation': 'h'})
        fig.update_traces(texttemplate='%{percent} (%{value})')
        if is_empty_data(matches):
            add_no_data_annotation(fig)

        return Charts.render_to_html(fig)

    @staticmethod
    def wdl(seasons, wins, draws, losses):
        data = {
            'seasons': seasons,
            'wins': wins,
            'draws': draws,
            'losses': losses,
        }
        fig = px.histogram(
            data,
            y='seasons',
            x=['wins', 'draws', 'losses'],
            orientation='h',
            text_auto=True,
            labels={'seasons': 'Сезон', 'value': 'Количество матчей', 'variable': 'Тип', },
            color_discrete_map={'wins': 'green', 'draws': 'gray', 'losses': 'red'}
        )
        fig.data[0].name = 'Победы'
        fig.data[1].name = 'Ничьи'
        fig.data[2].name = 'Поражения'
        fig.update_layout(legend={'title': ''})
        fig.update_layout(xaxis_title='Количество матчей', yaxis_autorange='reversed')
        fig.update_traces(textfont_size=12, textfont_color='white', textangle=0,
                          textposition='inside', insidetextanchor='middle')

        return Charts.render_to_html(fig)

    @staticmethod
    def wdl_percentage(seasons, wins, draws, losses):
        data = {
            'seasons': seasons,
            'wins': wins,
            'draws': draws,
            'losses': losses,
        }
        fig = px.histogram(
            data,
            y='seasons',
            x=['wins', 'draws', 'losses'],
            orientation='h',
            text_auto=True,
            labels={'seasons': 'Сезон', 'value': 'Доля матчей', 'variable': 'Тип', },
            color_discrete_map={'wins': 'green', 'draws': 'gray', 'losses': 'red'}
        )
        fig.data[0].name = 'Победы'
        fig.data[1].name = 'Ничьи'
        fig.data[2].name = 'Поражения'
        fig.update_layout(legend={'title': ''})
        fig.update_layout(xaxis_title='Доля матчей', barnorm='fraction',
                                         xaxis_tickformat='.0%', xaxis_dtick='0.25')
        fig.update_layout(yaxis_autorange='reversed')
        fig.update_traces(textfont_size=12, textfont_color='white', textposition='inside', insidetextanchor='middle')

        return Charts.render_to_html(fig)
    #endregion

    #region Goal/Assists
    @staticmethod
    def goals_by_season(seasons, goals):
        fig = px.bar(
            x=seasons,
            y=goals,
            title='Количество голов за сезон',
            text_auto=True,
            labels={'x': 'Сезон', 'y': 'Голы'},
            color_discrete_sequence=['orangered'],
        )
        fig.update_layout(yaxis_rangemode='nonnegative')
        fig.update_traces(textfont_size=12, textangle=0, textposition='outside', cliponaxis=False)

        return Charts.render_to_html(fig)

    @staticmethod
    def goals_per_match_by_season(seasons, goals_per_match):
        fig = px.bar(
            x=seasons,
            y=goals_per_match,
            title='Среднее количество голов за матч',
            text_auto=True,
            labels={'x': 'Сезон', 'y': 'Голы'},
            color_discrete_sequence=['orangered'],
        )
        fig.update_layout(yaxis_rangemode='nonnegative')
        fig.update_traces(textfont_size=12, textangle=0, textposition='outside', cliponaxis=False)
        fig.update_traces(texttemplate='%{y:.2f}', yhoverformat='.2f')

        return Charts.render_to_html(fig)

    @staticmethod
    def goals_by_team(teams, goals):
        fig = px.pie(
            names=teams,
            values=goals,
            title='Распределение голов по командам',
            labels={'values': 'Голы', 'names': 'Команда'},
        )
        fig.update_traces(texttemplate='%{percent} (%{value})')
        if is_empty_data(goals):
            add_no_data_annotation(fig)

        return Charts.render_to_html(fig)

    @staticmethod
    def goals_by_tournament(tournaments, goals):
        fig = px.pie(
            names=tournaments,
            values=goals,
            title='Распределение голов по турнирам',
            labels={'values': 'Голы', 'names': 'Турнир'},
        )
        fig.update_layout(legend={'orientation': 'v'})
        fig.update_traces(texttemplate='%{percent} (%{value})')
        if is_empty_data(goals):
            add_no_data_annotation(fig)

        return Charts.render_to_html(fig)

    @staticmethod
    def assists_by_season(seasons, assists):
        fig = px.bar(
            x=seasons,
            y=assists,
            title='Количество передач за сезон',
            text_auto=True,
            labels={'x': 'Сезон', 'y': 'Передачи'},
            color_discrete_sequence=['skyblue'],
        )
        fig.update_layout(yaxis_rangemode='nonnegative')
        fig.update_traces(textfont_size=12, textangle=0, textposition='outside', cliponaxis=False)

        return Charts.render_to_html(fig)

    @staticmethod
    def assists_per_match_by_season(seasons, assists_per_match):
        fig = px.bar(
            x=seasons,
            y=assists_per_match,
            title='Среднее количество передач за матч',
            text_auto=True,
            labels={'x': 'Сезон', 'y': 'Передачи'},
            color_discrete_sequence=['skyblue'],
        )
        fig.update_layout(yaxis_rangemode='nonnegative')
        fig.update_traces(textfont_size=12, textangle=0, textposition='outside', cliponaxis=False)
        fig.update_traces(texttemplate='%{y:.2f}', yhoverformat='.2f')

        return Charts.render_to_html(fig)

    @staticmethod
    def assists_by_team(teams, assists):
        fig = px.pie(
            names=teams,
            values=assists,
            title='Распределение передач по командам',
            labels={'values': 'Передачи', 'names': 'Команда'},
        )
        fig.update_traces(texttemplate='%{percent} (%{value})')
        if is_empty_data(assists):
            add_no_data_annotation(fig)

        return Charts.render_to_html(fig)

    @staticmethod
    def assists_by_tournament(tournaments, assists):
        fig = px.pie(
            names=tournaments,
            values=assists,
            title='Распределение передач по турнирам',
            labels={'values': 'Голы', 'names': 'Турнир'},
        )
        fig.update_traces(texttemplate='%{percent} (%{value})')
        if is_empty_data(assists):
            add_no_data_annotation(fig)

        return Charts.render_to_html(fig)

    @staticmethod
    def goals_assists_by_season(seasons, goals, assists):
        data = {
            'seasons': seasons,
            'goals': goals,
            'assists': assists,
        }
        fig = px.bar(
            data,
            x='seasons',
            y=['goals', 'assists'],
            title='Количество результативных действий за сезон',
            text_auto=True,
            labels={'seasons': 'Сезон', 'value': 'Результативные действия', 'variable': 'Тип'},
            color_discrete_map={'goals': 'orangered', 'assists': 'skyblue'},
        )
        fig.update_layout(legend={'title': ''})
        fig.update_layout(yaxis_rangemode='nonnegative')
        fig.update_layout(
            annotations=[
                dict(
                    x=xi,
                    y=yi1 + yi2,
                    text=str(yi1 + yi1),
                    xanchor='auto',
                    yanchor='bottom',
                    showarrow=False,
                ) for xi, yi1, yi2 in zip(seasons, goals, assists)
            ]
        )
        fig.update_traces(textfont_size=12, textangle=0, textposition='inside', insidetextanchor='middle')
        fig.update_traces(hovertemplate='Сезон=%{x}<br>Количество=%{y}')
        fig.data[0].name = 'Голы'
        fig.data[1].name = 'Передачи'

        return Charts.render_to_html(fig)

    @staticmethod
    def goals_assists_per_match_by_season(seasons, goals_assists_per_match):
        fig = px.bar(
            x=seasons,
            y=goals_assists_per_match,
            title='Среднее количество результативных действий за матч',
            text_auto=True,
            labels={'x': 'Сезон', 'y': 'Результативные действия'}
        )
        fig.update_layout(yaxis_rangemode='nonnegative')
        fig.update_traces(textfont_size=12, textangle=0, textposition='outside', cliponaxis=False)
        fig.update_traces(texttemplate='%{y:.2f}', yhoverformat='.2f')

        return Charts.render_to_html(fig)

    @staticmethod
    def goals_assists_by_team(teams, goals_assists):
        fig = px.pie(
            names=teams,
            values=goals_assists,
            title='Распределение результативных действий по командам',
            labels={'values': 'Результативные действия', 'names': 'Команда'},
        )
        fig.update_traces(texttemplate='%{percent} (%{value})')
        if is_empty_data(goals_assists):
            add_no_data_annotation(fig)

        return Charts.render_to_html(fig)

    @staticmethod
    def goals_assists_by_tournament(tournaments, goals_assists):
        fig = px.pie(
            names=tournaments,
            values=goals_assists,
            title='Распределение результативных действий по турнирам',
            labels={'values': 'Результативные действия', 'names': 'Турнир'},
        )
        fig.update_traces(texttemplate='%{percent} (%{value})')
        if is_empty_data(goals_assists):
            add_no_data_annotation(fig)

        return Charts.render_to_html(fig)
    #endregion

    #region CS
    @staticmethod
    def cs_by_season(seasons, cs):
        fig = px.bar(
            x=seasons, y=cs, title='Количество сухих таймов за сезон', text_auto=True,
            labels={'x': 'Сезон', 'y': 'Голы'}
        )
        fig.update_layout(yaxis_rangemode='nonnegative')
        fig.update_traces(textfont_size=12, textangle=0, textposition='outside', cliponaxis=False)

        return Charts.render_to_html(fig)

    @staticmethod
    def cs_per_match_by_season(seasons, cs):
        fig = px.bar(
            x=seasons,
            y=cs,
            title='Среднее количество сухих таймов за матч',
            text_auto=True,
            labels={'x': 'Сезон', 'y': 'Сухие таймы'}
        )
        fig.update_layout(yaxis_rangemode='nonnegative')
        fig.update_traces(textfont_size=12, textangle=0, textposition='outside', cliponaxis=False)
        fig.update_traces(texttemplate='%{y:.2f}', yhoverformat='.2f')

        return Charts.render_to_html(fig)

    @staticmethod
    def cs_by_team(teams, cs):
        fig = px.pie(
            names=teams,
            values=cs,
            title='Распределение сухих таймов по командам',
            labels={'values': 'Сухие таймы', 'names': 'Команда'},
        )
        fig.update_traces(texttemplate='%{percent} (%{value})')
        if is_empty_data(cs):
            add_no_data_annotation(fig)

        return Charts.render_to_html(fig)

    @staticmethod
    def cs_by_tournament(tournaments, cs):
        fig = px.pie(
            names=tournaments,
            values=cs,
            title='Распределение сухих таймов по турнирам',
            labels={'values': 'Сухие таймы', 'names': 'Турнир'},
        )
        fig.update_traces(texttemplate='%{percent} (%{value})')
        if is_empty_data(cs):
            add_no_data_annotation(fig)

        return Charts.render_to_html(fig)
    #endregion

    #region Cards
    @staticmethod
    def cards_by_season(seasons, yellow_cards, red_cards):
        data = {
            'seasons': seasons,
            'yellow': yellow_cards,
            'red': red_cards,
        }

        fig = px.bar(
            data,
            x='seasons',
            y=['yellow', 'red'],
            title='Количество карточек за сезон', text_auto=True,
            labels={'seasons': 'Сезон', 'value': 'Карточки', 'variable': 'Тип'},
            color_discrete_map={'yellow': 'yellow', 'red': 'red'},
        )
        fig.data[0].name = 'ЖК'
        fig.data[1].name = 'КК'
        fig.update_layout(legend={'title': ''})
        fig.update_layout(barmode='group', yaxis_rangemode='nonnegative')
        fig.update_traces(textfont_size=12, textangle=0, textposition='outside', cliponaxis=False)

        return Charts.render_to_html(fig)

    @staticmethod
    def cards_per_match_by_season(seasons, yellow_cards_per_match, red_cards_per_match):
        data = {
            'seasons': seasons,
            'yellow': yellow_cards_per_match,
            'red': red_cards_per_match,
        }

        fig = px.bar(
            data,
            x='seasons',
            y=['yellow', 'red'],
            title='Среднее количество карточек за матч',
            text_auto=True,
            labels={'seasons': 'Сезон', 'value': 'Карточки', 'variable': 'Тип'},
            color_discrete_map={'yellow': 'yellow', 'red': 'red'},
        )
        fig.data[0].name = 'ЖК'
        fig.data[1].name = 'КК'
        fig.update_layout(legend={'title': ''})
        fig.update_layout(barmode='group', yaxis_rangemode='nonnegative')
        fig.update_traces(textfont_size=12, textangle=0, textposition='outside', cliponaxis=False)
        fig.update_traces(texttemplate='%{y:.2f}', yhoverformat='.2f')

        return Charts.render_to_html(fig)

    @staticmethod
    def yellow_cards_by_team(teams, yellow_cards):
        fig = px.pie(
            names=teams,
            values=yellow_cards,
            title='Распределение желтых карточек по командам',
            labels={'values': 'Карточки', 'names': 'Команда'},
        )
        fig.update_traces(texttemplate='%{percent} (%{value})')
        if is_empty_data(yellow_cards):
            add_no_data_annotation(fig)

        return Charts.render_to_html(fig)

    @staticmethod
    def yellow_cards_by_tournament(tournaments, yellow_cards):
        fig = px.pie(
            names=tournaments,
            values=yellow_cards,
            title='Распределение желтых карточек по турнирам',
            labels={'values': 'Карточки', 'names': 'Турнир'},
        )
        fig.update_traces(texttemplate='%{percent} (%{value})')
        if is_empty_data(yellow_cards):
            add_no_data_annotation(fig)

        return Charts.render_to_html(fig)

    @staticmethod
    def red_cards_by_team(teams, red_cards):
        fig = px.pie(
            names=teams,
            values=red_cards,
            title='Распределение красных карточек по командам',
            labels={'values': 'Карточки', 'names': 'Команда'},
        )
        fig.update_traces(texttemplate='%{percent} (%{value})')
        if is_empty_data(red_cards):
            add_no_data_annotation(fig)

        return Charts.render_to_html(fig)

    @staticmethod
    def red_cards_by_tournament(tournaments, red_cards):
        fig = px.pie(
            names=tournaments,
            values=red_cards,
            title='Распределение красных карточек по турнирам',
            labels={'values': 'Карточки', 'names': 'Турнир'},
        )
        fig.update_traces(texttemplate='%{percent} (%{value})')
        if is_empty_data(red_cards):
            add_no_data_annotation(fig)

        return Charts.render_to_html(fig)
    #endregion

    @staticmethod
    def render_to_html(fig, modebar_remove=None):
        if modebar_remove is None:
            modebar_remove = ['lasso', 'select']
        fig.update_layout(title={'x': 0.5, 'y': 0.9, 'xanchor': 'center', 'yanchor': 'top'})
        fig.update_layout(modebar={'remove': modebar_remove})

        return fig.to_html(full_html=False, include_plotlyjs=False)


def add_no_data_annotation(fig, message='Нет данных', font_size=24):
    fig.update_layout(
        annotations=[
            dict(
                x=0.5,
                y=0.5,
                xanchor='center',
                yanchor='middle',
                text=message,
                font_size=font_size,
                showarrow=False,
            )
        ]
    )


def is_empty_data(data):
    return not data or all((x == 0 for x in data))