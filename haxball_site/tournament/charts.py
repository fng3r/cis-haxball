import plotly.express as px

from .models import OtherEvents
from .stats import PlayerStatsSource, TeamStatsSource


class StatCharts:
    @staticmethod
    def for_player(player):
        return PlayerStatCharts(player)

    @staticmethod
    def for_team(team):
        return TeamStatCharts(team)


class PlayerStatCharts:
    def __init__(self, player):
        self.pcs = PlayerStatsSource(player)

    def matches(self):
        matches_by_season = self.pcs.get_matches_by_season()
        (
            seasons,
            matches,
            wins,
            draws,
            losses
        ) = column_values_list(matches_by_season, 'season_title', 'matches', 'wins', 'draws', 'losses')

        matches_chart = Charts.matches_by_season(seasons, matches)
        wdl_chart = Charts.wdl(seasons, wins, draws, losses)
        wdl_percentage_chart = Charts.wdl_percentage(seasons, wins, draws, losses)

        total_season_chart = Charts.recap_chart('Сезоны', len(set(seasons)))
        total_matches = sum(matches)
        total_matches_chart = Charts.recap_chart('Матчи', total_matches)
        total_winrate = sum(wins) / max(1, total_matches) * 100
        total_winrate_chart = Charts.recap_chart('Процент побед', total_winrate, percentage=True)

        matches_by_team = self.pcs.get_matches_by_team()
        teams, matches = column_values_list(matches_by_team, 'team', 'matches')
        matches_by_team_chart = Charts.matches_by_team(teams, matches)

        total_teams_chart = Charts.recap_chart('Команды', len(set(teams)))

        matches_by_tournament = self.pcs.get_matches_by_tournament()
        tournaments, matches = column_values_list(matches_by_tournament, 'tournament', 'matches')
        matches_by_tournament_chart = Charts.matches_by_tournament(tournaments, matches)

        return {
            'recap_charts': [total_season_chart, total_matches_chart, total_teams_chart, total_winrate_chart],
            'bar_charts': [matches_chart, wdl_chart, wdl_percentage_chart],
            'pie_charts': [matches_by_team_chart, matches_by_tournament_chart],
        }

    def goals_assists(self):
        goals_by_season = self.pcs.get_goals_by_season()
        goals_by_team = self.pcs.get_goals_by_team()
        goals_by_tournament = self.pcs.get_goals_by_tournament()

        (
            seasons,
            goals,
            assists,
            goals_per_match,
            assists_per_match,
            goals_assists_per_match,
        ) = column_values_list(
            goals_by_season,
            'season_title', 'goals', 'assists', 'goals_per_match', 'assists_per_match',
            'goals_assists_per_match'
        )

        teams, goals_for_team, assists_for_team, goals_assists_for_team = column_values_list(
            goals_by_team,
            'team_title', 'goals', 'assists', 'goals_assists'
        )

        tournaments, goals_in_tournament, assists_in_tournament, goals_assists_in_tournament = column_values_list(
            goals_by_tournament,
            'tournament', 'goals', 'assists', 'goals_assists'
        )

        total_goals_chart = Charts.recap_chart('Голы', sum(goals))
        total_assists_chart = Charts.recap_chart('Голевые передачи', sum(assists))

        goals_chart = Charts.goals_by_season(seasons, goals)
        goals_per_match_chart = Charts.goals_per_match_by_season(seasons, goals_per_match)
        goals_by_team_chart = Charts.goals_by_team(teams, goals_for_team)
        goals_by_tournament_chart = Charts.goals_by_tournament(tournaments, goals_in_tournament)

        assists_chart = Charts.assists_by_season(seasons, assists)
        assists_per_match_chart = Charts.assists_per_match_by_season(seasons, assists_per_match)
        assists_by_team_chart = Charts.assists_by_team(teams, assists_for_team)
        assists_by_tournament_chart = Charts.assists_by_tournament(tournaments, assists_in_tournament)

        goals_assists_chart = Charts.goals_assists_by_season(seasons, goals, assists)
        goals_assists_per_match_chart = Charts.goals_assists_per_match_by_season(seasons,
                                                                                 goals_assists_per_match)
        goals_assists_by_team_chart = Charts.goals_assists_by_team(teams, goals_assists_for_team)
        goals_assists_by_tournament_chart = Charts.goals_assists_by_tournament(tournaments,
                                                                               goals_assists_in_tournament)

        return {
            'recap_charts': [total_goals_chart, total_assists_chart],
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

    def cs(self):
        cs_by_season = self.pcs.get_cs_by_season()
        cs_by_team = self.pcs.get_cs_by_team()
        cs_by_tournament = self.pcs.get_cs_by_tournament()

        seasons, cs, cs_per_match = column_values_list(cs_by_season, 'season_title', 'cs', 'cs_per_match')

        cs_by_season_chart = Charts.cs_by_season(seasons, cs)
        cs_per_match_by_season_chart = Charts.cs_per_match_by_season(seasons, cs_per_match)

        total_cs_chart = Charts.recap_chart('Сухие таймы', sum(cs))

        teams, cs = column_values_list(cs_by_team, 'team_title', 'cs')
        cs_by_team_chart = Charts.cs_by_team(teams, cs)

        tournaments, cs = column_values_list(cs_by_tournament, 'tournament', 'cs')
        cs_by_tournament_chart = Charts.cs_by_tournament(tournaments, cs)

        return {
            'recap_charts': [total_cs_chart],
            'bar_charts': [cs_by_season_chart, cs_per_match_by_season_chart],
            'pie_charts': [cs_by_team_chart, cs_by_tournament_chart],
        }

    def cards(self):
        cards_by_season = self.pcs.get_cards_by_season()
        cards_by_team = self.pcs.get_cards_by_team()
        cards_by_tournament = self.pcs.get_cards_by_tournament()

        (
            seasons,
            yellow_cards,
            red_cards,
            yellow_cards_per_match,
            red_cards_per_match
        ) = column_values_list(
            cards_by_season,
            'season_title', 'yellow_cards', 'red_cards', 'yellow_cards_per_match', 'red_cards_per_match'
        )

        cards_by_season_chart = Charts.cards_by_season(seasons, yellow_cards, red_cards)
        cards_per_match_by_season_chart = Charts.cards_per_match_by_season(
            seasons, yellow_cards_per_match, red_cards_per_match
        )

        teams, yellow_cards, red_cards = column_values_list(
            cards_by_team,
            'team_title', 'yellow_cards', 'red_cards'
        )
        yellow_cards_by_team_chart = Charts.yellow_cards_by_team(teams, yellow_cards)
        red_cards_by_team_chart = Charts.red_cards_by_team(teams, red_cards)

        total_yellow_cards_chart = Charts.recap_chart('Желтые карточки', sum(yellow_cards), color='yellow')
        total_red_cards_chart = Charts.recap_chart('Красные карточки', sum(red_cards), color='red')

        tournaments, yellow_cards, red_cards = column_values_list(
            cards_by_tournament,
            'tournament', 'yellow_cards', 'red_cards'
        )
        yellow_cards_by_tournament_chart = Charts.yellow_cards_by_tournament(tournaments, yellow_cards)
        red_cards_by_tournament_chart = Charts.red_cards_by_tournament(tournaments, red_cards)

        return {
            'recap_charts': [total_yellow_cards_chart, total_red_cards_chart],
            'bar_charts': [cards_by_season_chart, cards_per_match_by_season_chart],
            'pie_charts': [yellow_cards_by_team_chart, yellow_cards_by_tournament_chart,
                           red_cards_by_team_chart, red_cards_by_tournament_chart],
        }


class TeamStatCharts:
    def __init__(self, team):
        self.tcs = TeamStatsSource(team)

    def matches(self):
        matches_by_season = self.tcs.get_matches_by_season()
        (
            seasons,
            matches,
            wins,
            draws,
            losses
        ) = column_values_list(matches_by_season, 'season_title', 'matches', 'wins', 'draws', 'losses')

        matches_chart = Charts.matches_by_season(seasons, matches)
        wdl_chart = Charts.wdl(seasons, wins, draws, losses)
        wdl_percentage_chart = Charts.wdl_percentage(seasons, wins, draws, losses)

        total_season_chart = Charts.recap_chart('Сезоны', len(set(seasons)))
        total_matches = sum(matches)
        total_matches_chart = Charts.recap_chart('Матчи', total_matches)
        total_winrate = sum(wins) / max(1, total_matches) * 100
        total_winrate_chart = Charts.recap_chart('Процент побед', total_winrate, percentage=True)

        matches_in_league_by_season = self.tcs.get_matches_in_league_by_season()
        (
            seasons,
            matches,
            wins,
            draws,
            losses,
            points_per_match
        ) = column_values_list(
            matches_in_league_by_season,
            'season_title', 'matches', 'wins', 'draws', 'losses', 'points_per_match'
        )
        points_per_match_chart = Charts.points_per_match_by_season(seasons, points_per_match)

        matches_by_tournament = self.tcs.get_matches_by_tournament()
        tournaments, matches = column_values_list(matches_by_tournament, 'tournament', 'matches')
        matches_by_tournament_chart = Charts.matches_by_tournament(tournaments, matches)

        top_players_by_matches = self.tcs.get_top_players_by_matches()
        players, matches_by_player = column_values_list(top_players_by_matches, 'player', 'matches')
        top_players_by_matches_chart = Charts.top_players_by_matches(players, matches_by_player)

        return {
            'recap_charts': [total_season_chart, total_matches_chart, total_winrate_chart],
            'bar_charts': [matches_chart, wdl_chart, wdl_percentage_chart,
                           points_per_match_chart, top_players_by_matches_chart],
            'pie_charts': [matches_by_tournament_chart],
        }

    def goals_assists(self):
        goals_by_season = self.tcs.get_goals_by_season()
        goals_by_tournament = self.tcs.get_goals_by_tournament()

        (
            seasons,
            goals,
            conceded_goals,
            goals_per_match,
            conceded_goals_per_match,
            assists,
            assists_per_match,
            goals_assists_per_match,
        ) = column_values_list(
            goals_by_season,
            'season_title', 'goals', 'conceded_goals',
            'goals_per_match', 'conceded_goals_per_match',
            'assists', 'assists_per_match', 'goals_assists_per_match'
        )

        tournaments, goals_in_tournament, assists_in_tournament, goals_assists_in_tournament = column_values_list(
            goals_by_tournament,
            'tournament', 'goals', 'assists', 'goals_assists'
        )

        total_goals_chart = Charts.recap_chart('Голы', sum(goals))
        total_assists_chart = Charts.recap_chart('Голевые передачи', sum(assists))

        goals_chart = Charts.goals_by_season(seasons, goals, conceded_goals)
        goals_per_match_chart = Charts.goals_per_match_by_season(seasons, goals_per_match, conceded_goals_per_match)
        goals_by_tournament_chart = Charts.goals_by_tournament(tournaments, goals_in_tournament)

        goals_by_player = self.tcs.get_top_players_by_goals()
        players, goals = column_values_list(goals_by_player, 'player', 'goals')
        top_players_by_goals_chart = Charts.top_players_by_goals(players, goals)

        goals_per_match_by_player = self.tcs.get_top_players_by_goals_per_match()
        players, goals_per_match = column_values_list(goals_per_match_by_player, 'player', 'goals_per_match')
        top_players_by_goals_per_match_chart = Charts.top_players_by_goals_per_match(players, goals_per_match)

        assists_chart = Charts.assists_by_season(seasons, assists)
        assists_per_match_chart = Charts.assists_per_match_by_season(seasons, assists_per_match)
        assists_by_tournament_chart = Charts.assists_by_tournament(tournaments, assists_in_tournament)

        assists_by_player = self.tcs.get_top_players_by_assists()
        players, assists = column_values_list(assists_by_player, 'player', 'assists')
        top_players_by_assists_chart = Charts.top_players_by_assists(players, assists)

        assists_per_match_by_player = self.tcs.get_top_players_by_assists_per_match()
        players, assists_per_match = column_values_list(assists_per_match_by_player, 'player', 'assists_per_match')
        top_players_by_assists_per_match_chart = Charts.top_players_by_assists_per_match(players, assists_per_match)

        return {
            'recap_charts': [total_goals_chart, total_assists_chart],
            'bar_charts': [
                goals_chart, goals_per_match_chart,
                assists_chart, assists_per_match_chart,
                top_players_by_goals_chart, top_players_by_goals_per_match_chart,
                top_players_by_assists_chart, top_players_by_assists_per_match_chart,
            ],
            'pie_charts': [
                goals_by_tournament_chart,
                assists_by_tournament_chart,
            ]
        }

    def cs(self):
        cs_by_season = self.tcs.get_cs_by_season()
        cs_by_tournament = self.tcs.get_cs_by_tournament()

        seasons, cs, cs_per_match = column_values_list(cs_by_season, 'season_title', 'cs', 'cs_per_match')

        cs_by_season_chart = Charts.cs_by_season(seasons, cs)
        cs_per_match_by_season_chart = Charts.cs_per_match_by_season(seasons, cs_per_match)

        total_cs_chart = Charts.recap_chart('Сухие таймы', sum(cs))

        tournaments, cs = column_values_list(cs_by_tournament, 'tournament', 'cs')
        cs_by_tournament_chart = Charts.cs_by_tournament(tournaments, cs)

        cs_by_player = self.tcs.get_top_players_by_cs()
        players, cs = column_values_list(cs_by_player, 'player', 'cs')
        top_players_by_cs_chart = Charts.top_players_by_cs(players, cs)

        cs_per_match_by_player = self.tcs.get_top_players_by_cs_per_match()
        players, cs_per_match = column_values_list(cs_per_match_by_player, 'player', 'cs_per_match')
        top_players_by_cs_per_match_chart = Charts.top_players_by_cs_per_match(players, cs_per_match)

        return {
            'recap_charts': [total_cs_chart],
            'bar_charts': [cs_by_season_chart, cs_per_match_by_season_chart,
                           top_players_by_cs_chart, top_players_by_cs_per_match_chart],
            'pie_charts': [cs_by_tournament_chart],
        }

    def cards(self):
        cards_by_season = self.tcs.get_cards_by_season()
        cards_by_tournament = self.tcs.get_cards_by_tournament()

        (
            seasons,
            yellow_cards,
            red_cards,
            yellow_cards_per_match,
            red_cards_per_match
        ) = column_values_list(
            cards_by_season,
            'season_title', 'yellow_cards', 'red_cards', 'yellow_cards_per_match', 'red_cards_per_match'
        )

        cards_by_season_chart = Charts.cards_by_season(seasons, yellow_cards, red_cards)
        cards_per_match_by_season_chart = Charts.cards_per_match_by_season(
            seasons, yellow_cards_per_match, red_cards_per_match
        )

        total_yellow_cards_chart = Charts.recap_chart('Желтые карточки', sum(yellow_cards), color='yellow')
        total_red_cards_chart = Charts.recap_chart('Красные карточки', sum(red_cards), color='red')

        tournaments, yellow_cards, red_cards = column_values_list(
            cards_by_tournament,
            'tournament', 'yellow_cards', 'red_cards'
        )
        yellow_cards_by_tournament_chart = Charts.yellow_cards_by_tournament(tournaments, yellow_cards)
        red_cards_by_tournament_chart = Charts.red_cards_by_tournament(tournaments, red_cards)

        yellow_cards_by_player = self.tcs.get_top_players_by_cards(OtherEvents.YELLOW_CARD)
        players, yellow_cards = column_values_list(yellow_cards_by_player, 'player', 'cards')
        top_players_by_yellow_cards_chart = Charts.top_players_by_yellow_cards(players, yellow_cards)

        red_cards_by_player = self.tcs.get_top_players_by_cards(OtherEvents.RED_CARD)
        players, red_cards = column_values_list(red_cards_by_player, 'player', 'cards')
        top_players_by_red_cards_chart = Charts.top_players_by_red_cards(players, red_cards)

        return {
            'recap_charts': [total_yellow_cards_chart, total_red_cards_chart],
            'bar_charts': [cards_by_season_chart, cards_per_match_by_season_chart,
                           top_players_by_yellow_cards_chart, top_players_by_red_cards_chart],
            'pie_charts': [yellow_cards_by_tournament_chart, red_cards_by_tournament_chart],
        }


class Charts:
    #region Common
    @staticmethod
    def histogram(data=None, x=None, y=None, values_names=None, orientation='v',
                  title=None, labels=None, color_discrete_map=None):
        fig = px.histogram(
            data,
            x=x,
            y=y,
            orientation=orientation,
            title=title,
            text_auto=True,
            labels=labels,
            color_discrete_map=color_discrete_map,
        )
        fig.update_traces(textfont_size=12, textangle=0, textposition='outside', cliponaxis=False)
        if values_names:
            for idx, name in enumerate(values_names):
                fig.data[idx].name = name

        return fig

    @staticmethod
    def bar(data=None, x=None, y=None, values_names=None, orientation='v', title=None, labels=None,
            color=None, color_discrete_map=None, color_discrete_sequence=None):
        fig = px.bar(
            data,
            x=x,
            y=y,
            orientation=orientation,
            title=title,
            text_auto=True,
            labels=labels,
            color=color,
            color_discrete_map=color_discrete_map,
            color_discrete_sequence=color_discrete_sequence,
        )
        fig.update_layout(yaxis_rangemode='nonnegative')
        fig.update_traces(textfont_size=12, textangle=0, textposition='outside', cliponaxis=False)
        if values_names:
            for idx, name in enumerate(values_names):
                fig.data[idx].name = name

        return fig

    @staticmethod
    def pie(data=None, names=None, values=None, title=None, labels=None):
        fig = px.pie(
            data,
            names=names,
            values=values,
            title=title,
            labels=labels,
        )
        fig.update_traces(texttemplate='%{percent} (%{value})')
        if is_empty_data(values):
            Charts.add_no_data_annotation(fig)

        return fig

    @staticmethod
    def recap_chart(title, value, percentage=False, color=None):
        color_discrete_sequence = None
        if color:
            color_discrete_sequence = [color]

        fig = px.pie(
            names=['name'],
            values=[1],
            title=title,
            color_discrete_sequence=color_discrete_sequence,
        )
        fig.update_layout(height=250, margin_t=50, margin_b=20, hovermode=False, showlegend=False)
        annotation_text = f'{value:.1f}%' if percentage else str(value)
        fig.update_layout(
            annotations=[
                dict(text=annotation_text, x=0.5, y=0.5, xanchor='center', font_size=25, showarrow=False)
            ])
        fig.update_traces(textinfo='none', hole=0.95)

        return Charts.render_to_html(fig)
    #endregion

    #region Matches
    @staticmethod
    def matches_by_season(seasons, matches):
        fig = Charts.histogram(
            x=seasons,
            y=matches,
            title='Количество матчей за сезон',
            labels={'x': 'Сезон', 'y': 'Матчи'},
        )
        fig.update_layout(yaxis_title='Матчи')

        return Charts.render_to_html(fig)

    @staticmethod
    def matches_by_team(teams, matches):
        fig = Charts.pie(
            names=teams,
            values=matches,
            title='Распределение матчей по командам',
            labels={'values': 'Матчи', 'names': 'Команда'},
        )
        fig.update_layout(legend={'orientation': 'h'})

        return Charts.render_to_html(fig)

    @staticmethod
    def matches_by_tournament(tournaments, matches):
        fig = Charts.pie(
            names=tournaments,
            values=matches,
            title='Распределение матчей по турнирам',
            labels={'values': 'Матчи', 'names': 'Турнир'},
        )
        fig.update_layout(legend={'orientation': 'h'})

        return Charts.render_to_html(fig)

    @staticmethod
    def wdl(seasons, wins, draws, losses):
        fig = Charts.histogram(
            data={
                'seasons': seasons,
                'wins': wins,
                'draws': draws,
                'losses': losses,
            },
            y='seasons',
            x=['wins', 'draws', 'losses'],
            values_names=['Победы', 'Ничьи', 'Поражения'],
            orientation='h',
            title='Результаты во всех турнирах',
            labels={'seasons': 'Сезон', 'value': 'Количество матчей', 'variable': 'Тип', },
            color_discrete_map={'wins': 'green', 'draws': 'gray', 'losses': 'red'}
        )
        fig.update_layout(legend={'title': ''})
        fig.update_layout(xaxis_title='Количество матчей', yaxis_autorange='reversed')
        fig.update_traces(textfont_color='white', textposition='inside', insidetextanchor='middle')

        return Charts.render_to_html(fig)

    @staticmethod
    def wdl_percentage(seasons, wins, draws, losses):
        fig = Charts.histogram(
            data={
                'seasons': seasons,
                'wins': wins,
                'draws': draws,
                'losses': losses,
            },
            y='seasons',
            x=['wins', 'draws', 'losses'],
            values_names=['Победы', 'Ничьи', 'Поражения'],
            orientation='h',
            title='Результаты во всех турнирах',
            labels={'seasons': 'Сезон', 'value': 'Доля матчей', 'variable': 'Тип', },
            color_discrete_map={'wins': 'green', 'draws': 'gray', 'losses': 'red'}
        )
        fig.update_layout(xaxis_title='Доля матчей', legend={'title': ''})
        fig.update_layout(barnorm='fraction', xaxis_tickformat='.0%', xaxis_dtick='0.25', yaxis_autorange='reversed')
        fig.update_traces(textfont_size=12, textfont_color='white', textposition='inside', insidetextanchor='middle')

        return Charts.render_to_html(fig)

    @staticmethod
    def points_per_match_by_season(seasons, point_per_match):
        fig = Charts.histogram(
            x=seasons,
            y=point_per_match,
            title='Среднее количество очков за сезон (в лиге)',
            labels={'x': 'Сезон', 'y': 'Очки'},
        )
        fig.update_layout(yaxis_title='Очки')
        fig.update_traces(texttemplate='%{y:.2f}', yhoverformat='.2f')

        return Charts.render_to_html(fig)

    @staticmethod
    def top_players_by_matches(players, matches, nmin=10):
        if not players:
            return None

        fig = Charts.bar(
            x=players,
            y=matches,
            title=f'Топ-{max(nmin, len(players))} игроков по количеству матчей',
            labels={'x': 'Игрок', 'y': 'Матчи'},
        )

        return Charts.render_to_html(fig)
    #endregion

    #region Goal/Assists
    @staticmethod
    def goals_by_season(seasons, goals, conceded_goals=None):
        if conceded_goals is not None:
            y=[goals, conceded_goals]
            values_names = ['Забитые', 'Пропущенные']
            color_discrete_sequence = ['orangered', 'orange']
            labels = {'x': 'Сезон', 'value': 'Голы', 'variable': 'Тип'}
        else:
            y=goals
            values_names = None
            color_discrete_sequence = ['orangered']
            labels = {'x': 'Сезон', 'y': 'Голы'}

        fig = Charts.bar(
            x=seasons,
            y=y,
            values_names=values_names,
            title='Количество голов за сезон',
            labels=labels,
            color_discrete_sequence=color_discrete_sequence,
        )
        if conceded_goals is not None:
            fig.update_layout(legend={'title': 'Голы'}, barmode='group')
            fig.update_traces(hovertemplate='Сезон=%{x}<br>Голы=%{y}')

        return Charts.render_to_html(fig)

    @staticmethod
    def goals_per_match_by_season(seasons, goals, conceded_goals=None):
        if conceded_goals is not None:
            y=[goals, conceded_goals]
            values_names = ['Забитые', 'Пропущенные']
            color_discrete_sequence = ['orangered', 'orange']
            labels = {'x': 'Сезон', 'value': 'Голы', 'variable': 'Тип'}
        else:
            y=goals
            values_names = None
            color_discrete_sequence = ['orangered']
            labels = {'x': 'Сезон', 'y': 'Голы'}
        fig = Charts.bar(
            x=seasons,
            y=y,
            values_names=values_names,
            title='Среднее количество голов за матч',
            labels=labels,
            color_discrete_sequence=color_discrete_sequence,
        )
        fig.update_traces(texttemplate='%{y:.2f}', yhoverformat='.2f')
        if conceded_goals is not None:
            fig.update_layout(legend={'title': 'Голы'}, barmode='group')
            fig.update_traces(hovertemplate='Сезон=%{x}<br>Голы=%{y}')

        return Charts.render_to_html(fig)

    @staticmethod
    def goals_by_team(teams, goals):
        fig = Charts.pie(
            names=teams,
            values=goals,
            title='Распределение голов по командам',
            labels={'values': 'Голы', 'names': 'Команда'},
        )

        return Charts.render_to_html(fig)

    @staticmethod
    def goals_by_tournament(tournaments, goals):
        fig = Charts.pie(
            names=tournaments,
            values=goals,
            title='Распределение голов по турнирам',
            labels={'values': 'Голы', 'names': 'Турнир'},
        )

        return Charts.render_to_html(fig)

    @staticmethod
    def top_players_by_goals(players, goals, nmin=10):
        if not players:
            return None

        fig = Charts.bar(
            x=players,
            y=goals,
            title=f'Топ-{max(nmin, len(players))} игроков по количеству голов',
            labels={'x': 'Игрок', 'y': 'Голы'},
            color_discrete_sequence=['orangered'],
        )

        return Charts.render_to_html(fig)

    @staticmethod
    def top_players_by_goals_per_match(players, goals, nmin=10):
        if not players:
            return None

        fig = Charts.bar(
            x=players,
            y=goals,
            title=f'Топ-{max(nmin, len(players))} игроков по количеству голов за матч (10+ матчей)',
            labels={'x': 'Игрок', 'y': 'Голы'},
            color_discrete_sequence=['orangered'],
        )
        fig.update_traces(texttemplate='%{y:.2f}', yhoverformat='.2f')

        return Charts.render_to_html(fig)

    @staticmethod
    def assists_by_season(seasons, assists):
        fig = Charts.bar(
            x=seasons,
            y=assists,
            title='Количество голевых передач за сезон',
            labels={'x': 'Сезон', 'y': 'Передачи'},
            color_discrete_sequence=['deepskyblue'],
        )
        fig.update_traces(textfont_size=12, textangle=0, textposition='outside', cliponaxis=False)

        return Charts.render_to_html(fig)

    @staticmethod
    def assists_per_match_by_season(seasons, assists_per_match):
        fig = Charts.bar(
            x=seasons,
            y=assists_per_match,
            title='Среднее количество голевых передач за матч',
            labels={'x': 'Сезон', 'y': 'Передачи'},
            color_discrete_sequence=['deepskyblue'],
        )
        fig.update_traces(texttemplate='%{y:.2f}', yhoverformat='.2f')

        return Charts.render_to_html(fig)

    @staticmethod
    def assists_by_team(teams, assists):
        fig = Charts.pie(
            names=teams,
            values=assists,
            title='Распределение голевых передач по командам',
            labels={'values': 'Передачи', 'names': 'Команда'},
        )

        return Charts.render_to_html(fig)

    @staticmethod
    def assists_by_tournament(tournaments, assists):
        fig = Charts.pie(
            names=tournaments,
            values=assists,
            title='Распределение голевых передач по турнирам',
            labels={'values': 'Передачи', 'names': 'Турнир'},
        )

        return Charts.render_to_html(fig)

    @staticmethod
    def top_players_by_assists(players, assists, nmin=10):
        if not players:
            return None

        fig = Charts.bar(
            x=players,
            y=assists,
            title=f'Топ-{max(nmin, len(players))} игроков по количеству голевых передач',
            labels={'x': 'Игрок', 'y': 'Передачи'},
            color_discrete_sequence=['deepskyblue'],
        )

        return Charts.render_to_html(fig)

    @staticmethod
    def top_players_by_assists_per_match(players, assists, nmin=10):
        if not players:
            return None

        fig = Charts.bar(
            x=players,
            y=assists,
            title=f'Топ-{max(nmin, len(players))} игроков по количеству голевых передач за матч (10+ матчей)',
            labels={'x': 'Игрок', 'y': 'Передачи'},
            color_discrete_sequence=['deepskyblue'],
        )
        fig.update_traces(texttemplate='%{y:.2f}', yhoverformat='.2f')

        return Charts.render_to_html(fig)

    @staticmethod
    def goals_assists_by_season(seasons, goals, assists):
        fig = Charts.bar(
            data={
                'seasons': seasons,
                'goals': goals,
                'assists': assists,
            },
            x='seasons',
            y=['goals', 'assists'],
            values_names=['Голы', 'Передачи'],
            title='Количество результативных действий за сезон',
            labels={'seasons': 'Сезон', 'value': 'Результативные действия', 'variable': 'Тип'},
            color_discrete_map={'goals': 'orangered', 'assists': 'deepskyblue'},
        )
        fig.update_layout(
            legend={'title': '', 'traceorder': 'reversed', 'itemclick': False, 'itemdoubleclick': False}
        )
        fig.update_layout(
            annotations=[
                dict(
                    x=xi,
                    y=yi1 + yi2,
                    text=str(yi1 + yi2) if yi1 + yi2 > max(yi1, yi2) else '',
                    xanchor='auto',
                    yanchor='bottom',
                    showarrow=False,
                ) for xi, yi1, yi2 in zip(seasons, goals, assists)
            ]
        )
        fig.update_traces(textfont_size=12, textangle=0, textposition='inside', insidetextanchor='middle')
        fig.update_traces(hovertemplate='Сезон=%{x}<br>Количество=%{y}')

        return Charts.render_to_html(fig)

    @staticmethod
    def goals_assists_per_match_by_season(seasons, goals_assists_per_match):
        fig = Charts.bar(
            x=seasons,
            y=goals_assists_per_match,
            title='Среднее количество результативных действий за матч',
            labels={'x': 'Сезон', 'y': 'Результативные действия'}
        )
        fig.update_traces(texttemplate='%{y:.2f}', yhoverformat='.2f')

        return Charts.render_to_html(fig)

    @staticmethod
    def goals_assists_by_team(teams, goals_assists):
        fig = Charts.pie(
            names=teams,
            values=goals_assists,
            title='Распределение результативных действий по командам',
            labels={'values': 'Результативные действия', 'names': 'Команда'},
        )

        return Charts.render_to_html(fig)

    @staticmethod
    def goals_assists_by_tournament(tournaments, goals_assists):
        fig = Charts.pie(
            names=tournaments,
            values=goals_assists,
            title='Распределение результативных действий по турнирам',
            labels={'values': 'Результативные действия', 'names': 'Турнир'},
        )

        return Charts.render_to_html(fig)
    #endregion

    #region CS
    @staticmethod
    def cs_by_season(seasons, cs):
        fig = Charts.bar(
            x=seasons,
            y=cs,
            title='Количество сухих таймов за сезон',
            labels={'x': 'Сезон', 'y': 'Голы'},
        )

        return Charts.render_to_html(fig)

    @staticmethod
    def cs_per_match_by_season(seasons, cs):
        fig = Charts.bar(
            x=seasons,
            y=cs,
            title='Среднее количество сухих таймов за матч',
            labels={'x': 'Сезон', 'y': 'Сухие таймы'}
        )
        fig.update_traces(texttemplate='%{y:.2f}', yhoverformat='.2f')

        return Charts.render_to_html(fig)

    @staticmethod
    def cs_by_team(teams, cs):
        fig = Charts.pie(
            names=teams,
            values=cs,
            title='Распределение сухих таймов по командам',
            labels={'values': 'Сухие таймы', 'names': 'Команда'},
        )

        return Charts.render_to_html(fig)

    @staticmethod
    def cs_by_tournament(tournaments, cs):
        fig = Charts.pie(
            names=tournaments,
            values=cs,
            title='Распределение сухих таймов по турнирам',
            labels={'values': 'Сухие таймы', 'names': 'Турнир'},
        )

        return Charts.render_to_html(fig)

    @staticmethod
    def top_players_by_cs(players, cs, nmin=5):
        if not players:
            return None

        fig = Charts.bar(
            x=players,
            y=cs,
            title=f'Топ-{max(nmin, len(players))} игроков по количеству сухих таймов',
            labels={'x': 'Игрок', 'y': 'Сухие таймы'},
        )

        return Charts.render_to_html(fig)

    @staticmethod
    def top_players_by_cs_per_match(players, cs, nmin=5):
        if not players:
            return None

        fig = Charts.bar(
            x=players,
            y=cs,
            title=f'Топ-{max(nmin, len(players))} игроков по количеству сухих таймов за матч (10+ матчей)',
            labels={'x': 'Игрок', 'y': 'Сухие таймы'},
        )
        fig.update_traces(texttemplate='%{y:.2f}', yhoverformat='.2f')

        return Charts.render_to_html(fig)
    #endregion

    #region Cards
    @staticmethod
    def cards_by_season(seasons, yellow_cards, red_cards):
        fig = Charts.bar(
            data={
                'seasons': seasons,
                'yellow': yellow_cards,
                'red': red_cards,
            },
            x='seasons',
            y=['yellow', 'red'],
            values_names=['ЖК', 'КК'],
            title='Количество карточек за сезон',
            labels={'seasons': 'Сезон', 'value': 'Карточки', 'variable': 'Тип'},
            color_discrete_map={'yellow': 'yellow', 'red': 'red'},
        )
        fig.update_layout(legend={'title': ''}, barmode='group')

        return Charts.render_to_html(fig)

    @staticmethod
    def cards_per_match_by_season(seasons, yellow_cards_per_match, red_cards_per_match):
        fig = Charts.bar(
            data={
                'seasons': seasons,
                'yellow': yellow_cards_per_match,
                'red': red_cards_per_match,
            },
            x='seasons',
            y=['yellow', 'red'],
            values_names=['ЖК', 'КК'],
            title='Среднее количество карточек за матч',
            labels={'seasons': 'Сезон', 'value': 'Карточки', 'variable': 'Тип'},
            color_discrete_map={'yellow': 'yellow', 'red': 'red'},
        )
        fig.update_layout(legend={'title': ''}, barmode='group')
        fig.update_traces(texttemplate='%{y:.2f}', yhoverformat='.2f')

        return Charts.render_to_html(fig)

    @staticmethod
    def yellow_cards_by_team(teams, yellow_cards):
        fig = Charts.pie(
            names=teams,
            values=yellow_cards,
            title='Распределение желтых карточек по командам',
            labels={'values': 'Карточки', 'names': 'Команда'},
        )

        return Charts.render_to_html(fig)

    @staticmethod
    def yellow_cards_by_tournament(tournaments, yellow_cards):
        fig = Charts.pie(
            names=tournaments,
            values=yellow_cards,
            title='Распределение желтых карточек по турнирам',
            labels={'values': 'Карточки', 'names': 'Турнир'},
        )

        return Charts.render_to_html(fig)

    @staticmethod
    def top_players_by_yellow_cards(players, cards, nmin=5):
        if not players:
            return None

        fig = Charts.bar(
            x=players,
            y=cards,
            title=f'Топ-{max(nmin, len(players))} игроков по количеству желтых карточек',
            labels={'x': 'Игрок', 'y': 'Карточки'},
            color_discrete_sequence=['yellow'],
        )

        return Charts.render_to_html(fig)

    @staticmethod
    def red_cards_by_team(teams, red_cards):
        fig = Charts.pie(
            names=teams,
            values=red_cards,
            title='Распределение красных карточек по командам',
            labels={'values': 'Карточки', 'names': 'Команда'},
        )

        return Charts.render_to_html(fig)

    @staticmethod
    def red_cards_by_tournament(tournaments, red_cards):
        fig = Charts.pie(
            names=tournaments,
            values=red_cards,
            title='Распределение красных карточек по турнирам',
            labels={'values': 'Карточки', 'names': 'Турнир'},
        )

        return Charts.render_to_html(fig)

    @staticmethod
    def top_players_by_red_cards(players, cards, nmin=5):
        if not players:
            return None

        fig = Charts.bar(
            x=players,
            y=cards,
            title=f'Топ-{max(nmin, len(players))} игроков по количеству красных карточек',
            labels={'x': 'Игрок', 'y': 'Карточки'},
            color_discrete_sequence=['red'],
        )

        return Charts.render_to_html(fig)
    #endregion

    @staticmethod
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

    @staticmethod
    def render_to_html(fig, modebar_remove=None):
        if modebar_remove is None:
            modebar_remove = ['lasso', 'select']
        fig.update_layout(title={'x': 0.5, 'y': 0.9, 'xanchor': 'center', 'yanchor': 'top'})
        fig.update_layout(modebar={'remove': modebar_remove})

        return fig.to_html(full_html=False, include_plotlyjs=False)


def column_values_list(queryset, *columns):
    if not queryset.exists():
        return [[] for _ in columns]

    return list(zip(*queryset.values_list(*columns)))


def is_empty_data(data):
    return not data or all((x == 0 for x in data))
