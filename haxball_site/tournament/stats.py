from django.db.models import Case, Count, Exists, F, FloatField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Cast, Coalesce

from .models import Card, CleanSheet, Goal, League, Match, MatchResult, Player, Season


def _tournament_case(league_path):
    type_lookup = f'{league_path}__type'
    return Case(
        When(**{type_lookup: League.Type.PREMIER_LEAGUE, 'then': Value('Высшая лига')}),
        When(**{type_lookup: League.Type.FIRST_LEAGUE, 'then': Value('Первая лига')}),
        When(**{type_lookup: League.Type.SECOND_LEAGUE, 'then': Value('Вторая лига')}),
        When(
            **{
                f'{type_lookup}__in': [
                    League.Type.PREMIER_LEAGUE_CUP,
                    League.Type.FIRST_LEAGUE_CUP,
                    League.Type.SECOND_LEAGUE_CUP,
                    League.Type.LEAGUE_CUP,
                ],
                'then': Value('Кубок лиги'),
            }
        ),
        When(**{type_lookup: League.Type.CHAMPIONS_LEAGUE, 'then': Value('Лига Чемпионов')}),
        When(**{type_lookup: League.Type.RUSSIAN_CUP, 'then': Value('Кубок России')}),
        When(**{type_lookup: League.Type.FINALS, 'then': Value('Итоговый турнир')}),
        default=Value('Unknown'),
    )


class PlayerStatsSource:
    def __init__(self, player):
        self.player = player

    def get_matches_by_season(self):
        player = self.player
        return (
            Match.objects.filter(
                Q(team_home_start=player) | Q(team_guest_start=player) | Q(match_substitutions__player_in=player),
                is_played=True,
            )
            .values(season_title=F('league__championship__short_title'))
            .annotate(
                matches=Count('pk', distinct=True),
                team=Case(
                    When(team_home_start=player, then=F('team_home')),
                    When(team_guest_start=player, then=F('team_guest')),
                    When(match_substitutions__player_in=player, then=F('match_substitutions__team')),
                    default=None,
                ),
            )
            .filter(matches__gt=0)
            .annotate(
                wins=Count('pk', distinct=True, filter=Q(result__winner=F('team'))),
                draws=Count('pk', distinct=True, filter=Q(result__value=MatchResult.DRAW)),
                losses=Count(
                    'pk', distinct=True, filter=~Q(result__value=MatchResult.DRAW) & ~Q(result__winner=F('team'))
                ),
            )
            .order_by('league__championship__number')
        )

    def get_matches_by_team(self):
        player = self.player
        return (
            Match.objects.filter(
                Q(team_home_start=player) | Q(team_guest_start=player) | Q(match_substitutions__player_in=player),
                is_played=True,
            )
            .annotate(
                team=Case(
                    When(team_home_start=player, then=F('team_home__title')),
                    When(team_guest_start=player, then=F('team_guest__title')),
                    When(match_substitutions__player_in=player, then=F('match_substitutions__team__title')),
                    default=Value('Unknown'),
                )
            )
            .values('team')
            .annotate(matches=Count('pk', distinct=True))
            .filter(matches__gt=0)
            .order_by('-team')
        )

    def get_matches_by_tournament(self):
        player = self.player
        return (
            Match.objects.filter(
                Q(team_home_start=player) | Q(team_guest_start=player) | Q(match_substitutions__player_in=player),
                is_played=True,
            )
            .annotate(tournament=_tournament_case('league'))
            .values('tournament')
            .annotate(matches=Count('pk', distinct=True))
            .filter(matches__gt=0)
            .order_by('-matches')
        )

    def get_goals_by_season(self):
        player = self.player
        matches_subquery = (
            Match.objects.filter(
                Q(team_home_start=player) | Q(team_guest_start=player) | Q(match_substitutions__player_in=player),
                league__championship=OuterRef('id'),
                is_played=True,
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
            Season.objects.values(season_title=F('short_title'))
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

    def get_goals_by_team(self):
        player = self.player
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

    def get_goals_by_tournament(self):
        player = self.player
        return (
            Goal.objects.filter(Q(author=player) | Q(assistent=player))
            .annotate(tournament=_tournament_case('match__league'))
            .values('tournament')
            .annotate(
                goals=Count('author', filter=Q(author=player)),
                assists=Count('assistent', filter=Q(assistent=player)),
                goals_assists=F('goals') + F('assists'),
            )
            .order_by('-goals')
        )

    def get_cs_by_season(self):
        player = self.player
        matches_subquery = (
            Match.objects.filter(
                Q(team_home_start=player) | Q(team_guest_start=player) | Q(match_substitutions__player_in=player),
                league__championship=OuterRef('id'),
                is_played=True,
            )
            .order_by()
            .values('league__championship')
            .annotate(c=Count('id', distinct=True))
            .values('c')
        )
        cs_subquery = (
            CleanSheet.objects.filter(match__league__championship=OuterRef('id'), author=player)
            .order_by()
            .values('match__league__championship')
            .annotate(c=Count('*'))
            .values('c')
        )

        return (
            Season.objects.values(season_title=F('short_title'))
            .annotate(
                matches=Coalesce(Subquery(matches_subquery), 0),
                cs=Coalesce(Subquery(cs_subquery), 0),
            )
            .filter(matches__gt=0)
            .annotate(cs_per_match=Cast(F('cs'), FloatField()) / F('matches'))
            .order_by('number')
        )

    def get_cs_by_team(self):
        return (
            CleanSheet.objects.filter(author=self.player)
            .values(team_title=F('team__title'))
            .annotate(cs=Count('*'))
            .order_by('-cs')
        )

    def get_cs_by_tournament(self):
        return (
            CleanSheet.objects.filter(author=self.player)
            .annotate(tournament=_tournament_case('match__league'))
            .values('tournament')
            .annotate(cs=Count('*'))
            .order_by('-cs')
        )

    def get_cards_by_season(self):
        player = self.player
        matches_subquery = (
            Match.objects.filter(
                Q(team_home_start=player) | Q(team_guest_start=player) | Q(match_substitutions__player_in=player),
                league__championship=OuterRef('id'),
                is_played=True,
            )
            .order_by()
            .values('league__championship')
            .annotate(c=Count('id', distinct=True))
            .values('c')
        )
        yellow_cards_subquery = (
            Card.objects.filter(match__league__championship=OuterRef('id'), author=player)
            .order_by()
            .values('match__league__championship')
            .annotate(c=Count('id', filter=Q(kind=Card.Kind.YELLOW)))
            .values('c')
        )
        red_cards_subquery = (
            Card.objects.filter(match__league__championship=OuterRef('id'), author=player)
            .order_by()
            .values('match__league__championship')
            .annotate(c=Count('id', filter=Q(kind=Card.Kind.RED)))
            .values('c')
        )

        return (
            Season.objects.values(season_title=F('short_title'))
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

    def get_cards_by_team(self):
        return (
            Card.objects.filter(author=self.player)
            .values(team_title=F('team__title'))
            .annotate(
                yellow_cards=Count('id', filter=Q(kind=Card.Kind.YELLOW)),
                red_cards=Count('id', filter=Q(kind=Card.Kind.RED)),
                cards=F('yellow_cards') + F('red_cards'),
            )
            .filter(cards__gt=0)
            .order_by('-cards')
        )

    def get_cards_by_tournament(self):
        return (
            Card.objects.filter(author=self.player)
            .annotate(tournament=_tournament_case('match__league'))
            .values('tournament')
            .annotate(
                yellow_cards=Count('id', filter=Q(kind=Card.Kind.YELLOW)),
                red_cards=Count('id', filter=Q(kind=Card.Kind.RED)),
                cards=F('yellow_cards') + F('red_cards'),
            )
            .filter(cards__gt=0)
            .order_by('-cards')
        )


class TeamStatsSource:
    def __init__(self, team):
        self.team = team

    def get_matches_by_season(self):
        team = self.team
        return (
            Match.objects.filter(Q(team_home=team) | Q(team_guest=team), is_played=True)
            .values(season_title=F('league__championship__short_title'))
            .annotate(
                matches=Count('pk', distinct=True),
                team=Case(
                    When(team_home=team, then=F('team_home')),
                    When(team_guest=team, then=F('team_guest')),
                    default=None,
                ),
            )
            .filter(matches__gt=0)
            .annotate(
                wins=Count('pk', distinct=True, filter=Q(result__winner=F('team'))),
                draws=Count('pk', distinct=True, filter=Q(result__value=MatchResult.DRAW)),
                losses=Count(
                    'pk',
                    distinct=True,
                    filter=~Q(result__value=MatchResult.DRAW) & ~Q(result__winner=F('team')),
                ),
            )
            .order_by('league__championship__number')
        )

    def get_matches_in_league_by_season(self):
        team = self.team
        return (
            Match.objects.filter(Q(team_home=team) | Q(team_guest=team), is_played=True)
            .filter(
                league__type__in=[
                    League.Type.PREMIER_LEAGUE,
                    League.Type.FIRST_LEAGUE,
                    League.Type.SECOND_LEAGUE,
                ]
            )
            .values(season_title=F('league__championship__short_title'))
            .annotate(
                matches=Count('pk', distinct=True),
                team=Case(
                    When(team_home=team, then=F('team_home')),
                    When(team_guest=team, then=F('team_guest')),
                    default=None,
                ),
            )
            .filter(matches__gt=0)
            .annotate(
                wins=Count('pk', distinct=True, filter=Q(result__winner=F('team'))),
                draws=Count('pk', distinct=True, filter=Q(result__value=MatchResult.DRAW)),
                losses=Count(
                    'pk', distinct=True, filter=~Q(result__value=MatchResult.DRAW) & ~Q(result__winner=F('team'))
                ),
                points=F('wins') * 3 + F('draws'),
                points_per_match=Cast(F('points'), FloatField()) / F('matches'),
            )
            .order_by('league__championship__number')
        )

    def get_matches_by_tournament(self):
        team = self.team
        return (
            Match.objects.filter(Q(team_home=team) | Q(team_guest=team), is_played=True)
            .annotate(tournament=_tournament_case('league'))
            .values('tournament')
            .annotate(matches=Count('pk', distinct=True))
            .filter(matches__gt=0)
            .order_by('-matches')
        )

    def get_top_players_by_matches(self, top_n=10):
        return self._get_players_with_matches().filter(matches__gt=0).order_by('-matches')[:top_n]

    def get_goals_by_season(self):
        team = self.team
        matches_subquery = (
            Match.objects.filter(
                Q(team_home=team) | Q(team_guest=team), league__championship=OuterRef('id'), is_played=True
            )
            .order_by()
            .values('league__championship')
            .annotate(c=Count('id', distinct=True))
            .values('c')
        )
        goals_subquery = (
            Goal.objects.filter(match__league__championship=OuterRef('id'), team=team)
            .order_by()
            .values('match__league__championship')
            .annotate(c=Count('*'))
            .values('c')
        )
        conceded_goals_subquery = (
            Goal.objects.filter(
                Q(match__team_home=team) | Q(match__team_guest=team),
                ~Q(team=team),
                match__league__championship=OuterRef('id'),
            )
            .order_by()
            .values('match__league__championship')
            .annotate(c=Count('*'))
            .values('c')
        )
        assists_subquery = (
            Goal.objects.filter(
                match__league__championship=OuterRef('id'),
                team=team,
                assistent__isnull=False,
            )
            .order_by()
            .values('match__league__championship')
            .annotate(c=Count('*'))
            .values('c')
        )

        return (
            Season.objects.values(season_title=F('short_title'))
            .annotate(
                matches=Coalesce(Subquery(matches_subquery), 0),
                goals=Coalesce(Subquery(goals_subquery), 0),
                conceded_goals=Coalesce(Subquery(conceded_goals_subquery), 0),
                assists=Coalesce(Subquery(assists_subquery), 0),
                goal_diff=F('goals') - F('conceded_goals'),
            )
            .filter(matches__gt=0)
            .annotate(
                goals_per_match=Cast(F('goals'), FloatField()) / F('matches'),
                conceded_goals_per_match=Cast(F('conceded_goals'), FloatField()) / F('matches'),
                assists_per_match=Cast(F('assists'), FloatField()) / F('matches'),
                goals_assists_per_match=Cast(F('goals') + F('assists'), FloatField()) / F('matches'),
                goal_diff_per_match=F('goals_per_match') - F('conceded_goals_per_match'),
            )
            .order_by('number')
        )

    def get_goals_by_tournament(self):
        team = self.team
        return (
            Goal.objects.filter(team=team)
            .annotate(tournament=_tournament_case('match__league'))
            .values('tournament')
            .annotate(
                goals=Count('team'),
                assists=Count('team', filter=Q(assistent__isnull=False)),
                goals_assists=F('goals') + F('assists'),
            )
            .order_by('-goals')
        )

    def get_top_players_by_goals(self, top_n=10):
        return (
            Goal.objects.regular()
            .filter(team=self.team)
            .values(player=F('author__nickname'))
            .annotate(goals=Count('*'))
            .filter(goals__gt=0)
            .order_by('-goals')[:top_n]
        )

    def get_top_players_by_goals_per_match(self, top_n=10):
        team = self.team

        goals_subquery = (
            Goal.objects.filter(author=OuterRef('id'), team=team)
            .order_by()
            .values('author')
            .annotate(c=Count('id', distinct=True))
            .values('c')
        )

        return (
            self._get_players_with_matches()
            .annotate(
                goals=Coalesce(Subquery(goals_subquery), 0),
            )
            .filter(matches__gte=10, goals__gt=0)
            .annotate(goals_per_match=Cast(F('goals'), FloatField()) / F('matches'))
            .order_by('-goals_per_match')[:top_n]
        )

    def _get_players_with_matches(self):
        team = self.team
        home_matches_subquery = (
            Match.objects.filter(team_home=team, team_home_start=OuterRef('id'), is_played=True)
            .order_by()
            .values('team_home_start')
            .annotate(c=Count('id', distinct=True))
            .values('c')
        )
        guest_matches_subquery = (
            Match.objects.filter(team_guest=team, team_guest_start=OuterRef('id'), is_played=True)
            .order_by()
            .values('team_guest_start')
            .annotate(c=Count('id', distinct=True))
            .values('c')
        )
        sub_matches_subquery = (
            Match.objects.filter(
                match_substitutions__team=team,
                match_substitutions__player_in=OuterRef('id'),
                is_played=True,
            )
            .order_by()
            .values('match_substitutions__player_in')
            .annotate(c=Count('id', distinct=True))
            .values('c')
        )
        dup_matches_subquery = (
            Match.objects.filter(
                (Q(team_home=team) & Q(team_home_start=OuterRef('id')))
                | (Q(team_guest=team) & Q(team_guest_start=OuterRef('id'))),
                match_substitutions__player_in=OuterRef('id'),
                is_played=True,
            )
            .order_by()
            .values('match_substitutions__player_in')
            .annotate(c=Count('id', distinct=True))
            .values('c')
        )

        return (
            Player.objects.filter(Exists(Match.objects.filter(team_home=team, team_home_start=OuterRef('id'))))
            .values(player=F('nickname'))
            .annotate(
                home_matches_c=Coalesce(Subquery(home_matches_subquery), 0),
                guest_matches_c=Coalesce(Subquery(guest_matches_subquery), 0),
                sub_matches=Coalesce(Subquery(sub_matches_subquery), 0),
                dup_matches=Coalesce(Subquery(dup_matches_subquery), 0),
                matches=F('home_matches_c') + F('guest_matches_c') + F('sub_matches') - F('dup_matches'),
            )
        )

    def get_top_players_by_assists(self, top_n=10):
        return (
            Goal.objects.filter(team=self.team, assistent__isnull=False)
            .values(player=F('assistent__nickname'))
            .annotate(assists=Count('*'))
            .filter(assists__gt=0)
            .order_by('-assists')[:top_n]
        )

    def get_top_players_by_assists_per_match(self, top_n=10):
        team = self.team
        assists_subquery = (
            Goal.objects.filter(assistent=OuterRef('id'), team=team)
            .order_by()
            .values('assistent')
            .annotate(c=Count('id', distinct=True))
            .values('c')
        )

        return (
            self._get_players_with_matches()
            .annotate(
                assists=Coalesce(Subquery(assists_subquery), 0),
            )
            .filter(matches__gte=10, assists__gt=0)
            .annotate(assists_per_match=Cast(F('assists'), FloatField()) / F('matches'))
            .order_by('-assists_per_match')[:top_n]
        )

    def get_cs_by_season(self):
        team = self.team
        matches_subquery = (
            Match.objects.filter(
                Q(team_home=team) | Q(team_guest=team),
                league__championship=OuterRef('id'),
                is_played=True,
            )
            .order_by()
            .values('league__championship')
            .annotate(c=Count('id', distinct=True))
            .values('c')
        )
        cs_subquery = (
            CleanSheet.objects.filter(match__league__championship=OuterRef('id'), team=team)
            .order_by()
            .values('match__league__championship')
            .annotate(c=Count('*'))
            .values('c')
        )

        return (
            Season.objects.values(season_title=F('short_title'))
            .annotate(
                matches=Coalesce(Subquery(matches_subquery), 0),
                cs=Coalesce(Subquery(cs_subquery), 0),
            )
            .filter(matches__gt=0)
            .annotate(cs_per_match=Cast(F('cs'), FloatField()) / F('matches'))
            .order_by('number')
        )

    def get_cs_by_tournament(self):
        return (
            CleanSheet.objects.filter(team=self.team)
            .annotate(tournament=_tournament_case('match__league'))
            .values('tournament')
            .annotate(cs=Count('*'))
            .order_by('-cs')
        )

    def get_top_players_by_cs(self, top_n=5):
        return (
            CleanSheet.objects.filter(team=self.team)
            .values(player=F('author__nickname'))
            .annotate(cs=Count('*'))
            .filter(cs__gt=0)
            .order_by('-cs')[:top_n]
        )

    def get_top_players_by_cs_per_match(self, top_n=5):
        team = self.team
        cs_subquery = (
            CleanSheet.objects.filter(author=OuterRef('id'), team=team)
            .order_by()
            .values('author')
            .annotate(c=Count('id', distinct=True))
            .values('c')
        )

        return (
            self._get_players_with_matches()
            .annotate(
                cs=Coalesce(Subquery(cs_subquery), 0),
            )
            .filter(matches__gte=10, cs__gt=0)
            .annotate(cs_per_match=Cast(F('cs'), FloatField()) / F('matches'))
            .order_by('-cs_per_match')[:top_n]
        )

    def get_cards_by_season(self):
        team = self.team
        matches_subquery = (
            Match.objects.filter(
                Q(team_home=team) | Q(team_guest=team), league__championship=OuterRef('id'), is_played=True
            )
            .order_by()
            .values('league__championship')
            .annotate(c=Count('id', distinct=True))
            .values('c')
        )
        yellow_cards_subquery = (
            Card.objects.filter(match__league__championship=OuterRef('id'), team=team)
            .order_by()
            .values('match__league__championship')
            .annotate(c=Count('id', filter=Q(kind=Card.Kind.YELLOW)))
            .values('c')
        )
        red_cards_subquery = (
            Card.objects.filter(match__league__championship=OuterRef('id'), team=team)
            .order_by()
            .values('match__league__championship')
            .annotate(c=Count('id', filter=Q(kind=Card.Kind.RED)))
            .values('c')
        )

        return (
            Season.objects.values(season_title=F('short_title'))
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

    def get_cards_by_tournament(self):
        return (
            Card.objects.filter(team=self.team)
            .annotate(tournament=_tournament_case('match__league'))
            .values('tournament')
            .annotate(
                yellow_cards=Count('id', filter=Q(kind=Card.Kind.YELLOW)),
                red_cards=Count('id', filter=Q(kind=Card.Kind.RED)),
                cards=F('yellow_cards') + F('red_cards'),
            )
            .filter(cards__gt=0)
            .order_by('-cards')
        )

    def get_top_players_by_cards(self, card_type, top_n=5):
        return (
            Card.objects.filter(team=self.team, kind=card_type)
            .values(player=F('author__nickname'))
            .annotate(cards=Count('*'))
            .filter(cards__gt=0)
            .order_by('-cards')[:top_n]
        )
