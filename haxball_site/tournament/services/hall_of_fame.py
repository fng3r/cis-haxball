from enum import Enum

from django.core.paginator import Paginator
from django.db.models import Count, F, FloatField, OuterRef, Q, Subquery, Window
from django.db.models.functions import Cast, Coalesce, RowNumber

from ..models import Match, OtherEvents, Player, Team


class PlayerStatChoices(str, Enum):
    GOALS = 'goals'
    ASSISTS = 'assists'
    GOALS_ASSISTS = 'goals_assists'
    CLEAN_SHEETS = 'clean_sheets'
    YELLOW_CARDS = 'yellow_cards'
    RED_CARDS = 'red_cards'
    OWN_GOALS = 'own_goals'
    MATCHES = 'matches'
    WINS = 'wins'
    WINRATES = 'winrates'
    SUBS_IN = 'subs_in'
    SUBS_OUT = 'subs_out'


class HallOfFameService:
    def get_teams_tops(self, seasons=None, tournaments=None):
        """Get top team statistics across various categories.

        Args:
            seasons: QuerySet of Season objects to filter by
            tournaments: QuerySet of League objects to filter by

        Returns:
            Dictionary containing top teams for each statistical category
        """
        top_goalscorers = (
            Team.objects.annotate(
                count=Count(
                    'goals__match__league',
                    filter=Q(goals__match__league__in=tournaments) & Q(goals__match__league__championship__in=seasons),
                )
            )
            .filter(count__gt=0)
            .order_by('-count')
        )

        top_assistants = (
            Team.objects.annotate(
                count=Count(
                    'goals__match__league',
                    filter=Q(goals__assistent__isnull=False)
                    & Q(goals__match__league__in=tournaments)
                    & Q(goals__match__league__championship__in=seasons),
                )
            )
            .filter(count__gt=0)
            .order_by('-count')
        )

        top_cs = (
            Team.objects.filter(team_events__event=OtherEvents.CLEAN_SHEET)
            .annotate(
                count=Count(
                    'team_events__match__league',
                    filter=Q(team_events__match__league__in=tournaments)
                    & Q(team_events__match__league__championship__in=seasons),
                )
            )
            .filter(count__gt=0)
            .order_by('-count')
        )

        top_ogs = (
            Team.objects.filter(team_events__event=OtherEvents.OWN_GOAL)
            .annotate(
                count=Count(
                    'team_events__match__league',
                    filter=Q(team_events__match__league__in=tournaments)
                    & Q(team_events__match__league__championship__in=seasons),
                )
            )
            .filter(count__gt=0)
            .order_by('-count')
        )

        top_yellow_cards = (
            Team.objects.filter(team_events__event=OtherEvents.YELLOW_CARD)
            .annotate(
                count=Count(
                    'team_events__match__league',
                    filter=Q(team_events__match__league__in=tournaments)
                    & Q(team_events__match__league__championship__in=seasons),
                )
            )
            .filter(count__gt=0)
            .order_by('-count')
        )

        top_red_cards = (
            Team.objects.filter(team_events__event=OtherEvents.RED_CARD)
            .annotate(
                count=Count(
                    'team_events__match__league',
                    filter=Q(team_events__match__league__in=tournaments)
                    & Q(team_events__match__league__championship__in=seasons),
                )
            )
            .filter(count__gt=0)
            .order_by('-count')
        )

        top_subs = (
            Team.objects.annotate(
                count=Count(
                    'substitutions',
                    filter=Q(substitutions__match__league__in=tournaments)
                    & Q(substitutions__match__league__championship__in=seasons),
                )
            )
            .filter(count__gt=0)
            .order_by('-count')
        )

        home_matches_subquery = (
            Match.objects.filter(
                team_home=OuterRef('id'), is_played=True, league__in=tournaments, league__championship__in=seasons
            )
            .order_by()
            .values('team_home')
            .annotate(c=Count('*'))
            .values('c')
        )
        guest_matches_subquery = (
            Match.objects.filter(
                team_guest=OuterRef('id'), is_played=True, league__in=tournaments, league__championship__in=seasons
            )
            .order_by()
            .values('team_guest')
            .annotate(c=Count('*'))
            .values('c')
        )

        matches = (
            Team.objects.annotate(
                home_matches_count=Coalesce(Subquery(home_matches_subquery), 0),
                guest_matches_count=Coalesce(Subquery(guest_matches_subquery), 0),
                matches_count=F('home_matches_count') + F('guest_matches_count'),
            )
            .filter(matches_count__gt=0)
            .annotate(
                wins_count=Count(
                    'won_matches',
                    filter=Q(won_matches__match__league__in=tournaments)
                    & Q(won_matches__match__league__championship__in=seasons),
                ),
                winrate=Cast(F('wins_count'), FloatField()) / F('matches_count') * 100,
            )
            .order_by()
        )

        top_matches = matches.annotate(count=F('matches_count')).order_by('-count')
        top_wins = matches.annotate(count=F('wins_count')).order_by('-count')
        top_winrate = matches.filter(matches_count__gt=10).order_by('-winrate')

        return {
            'goals': top_goalscorers,
            'assists': top_assistants,
            'clean_sheets': top_cs,
            'yellow_cards': top_yellow_cards,
            'red_cards': top_red_cards,
            'ogs': top_ogs,
            'matches': top_matches,
            'wins': top_wins,
            'winrates': top_winrate,
            'subs': top_subs,
        }

    def get_players_tops(self, seasons=None, tournaments=None, nation=None, count=50):
        """Get top player statistics across various categories.

        Args:
            seasons: QuerySet of Season objects to filter by
            tournaments: QuerySet of League objects to filter by
            nation: Nation object to filter players by
            count: Number of top players to return per category

        Returns:
            Dictionary containing top players for each statistical category
        """
        players = Player.objects.select_related('team', 'name__user_profile')
        if nation:
            players = players.filter(player_nation=nation)

        return {
            'goals': Paginator(self._get_top_goalscorers(players, seasons, tournaments), count).get_page(1),
            'assists': Paginator(self._get_top_assistants(players, seasons, tournaments), count).get_page(1),
            'clean_sheets': Paginator(self._get_top_clean_sheets(players, seasons, tournaments), count).get_page(1),
            'yellow_cards': Paginator(self._get_top_yellow_cards(players, seasons, tournaments), count).get_page(1),
            'red_cards': Paginator(self._get_top_red_cards(players, seasons, tournaments), count).get_page(1),
            'own_goals': Paginator(self._get_top_own_goals(players, seasons, tournaments), count).get_page(1),
            'matches': Paginator(self._get_top_matches(players, seasons, tournaments), count).get_page(1),
            'wins': Paginator(self._get_top_wins(players, seasons, tournaments), count).get_page(1),
            'winrates': Paginator(self._get_top_winrates(players, seasons, tournaments), count).get_page(1),
            'subs_in': Paginator(self._get_top_subs_in(players, seasons, tournaments), count).get_page(1),
            'subs_out': Paginator(self._get_top_subs_out(players, seasons, tournaments), count).get_page(1),
        }

    def get_players_top_by_stat(self, seasons, tournaments, nation, stat, page, count=50):
        players = Player.objects.select_related('team', 'name__user_profile')
        if nation:
            players = players.filter(player_nation=nation)

        match stat:
            case PlayerStatChoices.GOALS:
                result = self._get_top_goalscorers(players, seasons, tournaments)
            case PlayerStatChoices.ASSISTS:
                result = self._get_top_assistants(players, seasons, tournaments)
            case PlayerStatChoices.CLEAN_SHEETS:
                result = self._get_top_clean_sheets(players, seasons, tournaments)
            case PlayerStatChoices.YELLOW_CARDS:
                result = self._get_top_yellow_cards(players, seasons, tournaments)
            case PlayerStatChoices.RED_CARDS:
                result = self._get_top_red_cards(players, seasons, tournaments)
            case PlayerStatChoices.OWN_GOALS:
                result = self._get_top_own_goals(players, seasons, tournaments)
            case PlayerStatChoices.MATCHES:
                result = self._get_top_matches(players, seasons, tournaments)
            case PlayerStatChoices.WINS:
                result = self._get_top_wins(players, seasons, tournaments)
            case PlayerStatChoices.WINRATES:
                result = self._get_top_winrates(players, seasons, tournaments)
            case PlayerStatChoices.SUBS_IN:
                result = self._get_top_subs_in(players, seasons, tournaments)
            case PlayerStatChoices.SUBS_OUT:
                result = self._get_top_subs_out(players, seasons, tournaments)

        return Paginator(result, count).get_page(page)

    def _get_top_goalscorers(self, players, seasons, tournaments):
        return (
            players.annotate(
                count=Count(
                    'goals__match__league',
                    filter=Q(goals__match__league__in=tournaments) & Q(goals__match__league__championship__in=seasons),
                ),
                rank=Window(
                    expression=RowNumber(),
                    order_by=('-count',),
                ),
            )
            .filter(count__gt=0)
            .order_by('-count')
        )

    def _get_top_assistants(self, players, seasons, tournaments):
        return (
            players.annotate(
                count=Count(
                    'assists__match__league',
                    filter=Q(assists__match__league__in=tournaments)
                    & Q(assists__match__league__championship__in=seasons),
                ),
                rank=Window(
                    expression=RowNumber(),
                    order_by=('-count',),
                ),
            )
            .filter(count__gt=0)
            .order_by('-count')
        )

    def _get_top_clean_sheets(self, players, seasons, tournaments):
        return (
            players.filter(event__event=OtherEvents.CLEAN_SHEET)
            .annotate(
                count=Count(
                    'event__match__league',
                    filter=Q(event__match__league__in=tournaments) & Q(event__match__league__championship__in=seasons),
                ),
                rank=Window(
                    expression=RowNumber(),
                    order_by=('-count',),
                ),
            )
            .filter(count__gt=0)
            .order_by('-count')
        )

    def _get_top_own_goals(self, players, seasons, tournaments):
        return (
            players.filter(event__event=OtherEvents.OWN_GOAL)
            .annotate(
                count=Count(
                    'event__match__league',
                    filter=Q(event__match__league__in=tournaments) & Q(event__match__league__championship__in=seasons),
                ),
                rank=Window(
                    expression=RowNumber(),
                    order_by=('-count',),
                ),
            )
            .filter(count__gt=0)
            .order_by('-count')
        )

    def _get_top_yellow_cards(self, players, seasons, tournaments):
        return (
            players.filter(event__event=OtherEvents.YELLOW_CARD)
            .annotate(
                count=Count(
                    'event__match__league',
                    filter=Q(event__match__league__in=tournaments) & Q(event__match__league__championship__in=seasons),
                ),
                rank=Window(
                    expression=RowNumber(),
                    order_by=('-count',),
                ),
            )
            .filter(count__gt=0)
            .order_by('-count')
        )

    def _get_top_red_cards(self, players, seasons, tournaments):
        return (
            players.filter(event__event=OtherEvents.RED_CARD)
            .annotate(
                count=Count(
                    'event__match__league',
                    filter=Q(event__match__league__in=tournaments) & Q(event__match__league__championship__in=seasons),
                ),
                rank=Window(
                    expression=RowNumber(),
                    order_by=('-count',),
                ),
            )
            .filter(count__gt=0)
            .order_by('-count')
        )

    def _get_top_subs_in(self, players, seasons, tournaments):
        return (
            players.annotate(
                count=Count(
                    'join_game__player_in',
                    filter=Q(join_game__match__league__in=tournaments)
                    & Q(join_game__match__league__championship__in=seasons),
                ),
                rank=Window(
                    expression=RowNumber(),
                    order_by=('-count',),
                ),
            )
            .filter(count__gt=0)
            .order_by('-count')
        )

    def _get_top_subs_out(self, players, seasons, tournaments):
        return (
            players.annotate(
                count=Count(
                    'replaced__player_out',
                    filter=Q(replaced__match__league__in=tournaments)
                    & Q(replaced__match__league__championship__in=seasons),
                ),
                rank=Window(
                    expression=RowNumber(),
                    order_by=('-count',),
                ),
            )
            .filter(count__gt=0)
            .order_by('-count')
        )

    def _get_top_matches(self, players, seasons, tournaments):
        return (
            players.annotate(
                count=Count(
                    'played_matches',
                    filter=Q(played_matches__league__in=tournaments, played_matches__league__championship__in=seasons),
                ),
                rank=Window(
                    expression=RowNumber(),
                    order_by=('-count',),
                ),
            )
            .filter(count__gt=0)
            .order_by('-count')
        )

    def _get_top_wins(self, players, seasons, tournaments):
        return (
            players.annotate(
                count=Count(
                    'played_matches',
                    filter=Q(
                        played_matches__match__result__winner=F('played_matches__team'),
                        played_matches__league__in=tournaments,
                        played_matches__league__championship__in=seasons,
                    ),
                ),
                rank=Window(
                    expression=RowNumber(),
                    order_by=('-count',),
                ),
            )
            .filter(count__gt=0)
            .order_by('-count')
        )

    def _get_top_winrates(self, players, seasons, tournaments):
        return (
            players.annotate(
                matches_count=Count(
                    'played_matches',
                    filter=Q(played_matches__league__in=tournaments, played_matches__league__championship__in=seasons),
                ),
                wins_count=Count(
                    'played_matches',
                    filter=Q(
                        played_matches__match__result__winner=F('played_matches__team'),
                        played_matches__league__in=tournaments,
                        played_matches__league__championship__in=seasons,
                    ),
                ),
            )
            .filter(matches_count__gt=25)
            .annotate(
                winrate=Cast(F('wins_count'), FloatField()) / F('matches_count') * 100,
                rank=Window(expression=RowNumber(), order_by=('-winrate',)),
            )
            .filter(winrate__gt=0)
            .order_by('-winrate')
        )
