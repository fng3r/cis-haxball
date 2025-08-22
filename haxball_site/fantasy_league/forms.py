from django import forms
from django.db.models import IntegerField, OuterRef, Subquery

from tournament.models import League, Player, PlayerRating, PlayerRatingVersion

from .models import FantasyTournament


class TournamentFilterForm(forms.Form):
    """Form for filtering tournaments"""

    tournament = forms.ModelChoiceField(
        queryset=FantasyTournament.objects.filter(is_active=True),
        empty_label=None,
        required=False,
        label='Турнир',
    )


class UserFilterForm(forms.Form):
    """Form for filtering users"""

    user = forms.ModelChoiceField(
        queryset=None,
        empty_label=None,
        required=False,
        label='Пользователь',
    )


class SquadSubmissionForm(forms.Form):
    """Form for submitting a squad"""

    primary_gk = forms.ModelChoiceField(
        queryset=Player.objects.filter(positions__contains=[Player.Position.GK]),
        label='Вратарь (основной)',
        required=True,
    )
    primary_dm = forms.ModelChoiceField(
        queryset=Player.objects.filter(positions__contains=[Player.Position.DM]),
        label='Опорник (основной)',
        required=True,
    )
    primary_st1 = forms.ModelChoiceField(
        queryset=Player.objects.filter(positions__contains=[Player.Position.ST]),
        label='Нападающий 1 (основной)',
        required=True,
    )
    primary_st2 = forms.ModelChoiceField(
        queryset=Player.objects.filter(positions__contains=[Player.Position.ST]),
        label='Нападающий 2 (основной)',
        required=True,
    )

    secondary_gk = forms.ModelChoiceField(
        queryset=Player.objects.filter(positions__contains=[Player.Position.GK]),
        label='Вратарь (запасной)',
        required=True,
    )
    secondary_dm = forms.ModelChoiceField(
        queryset=Player.objects.filter(positions__contains=[Player.Position.DM]),
        label='Опорник (запасной)',
        required=True,
    )
    secondary_st1 = forms.ModelChoiceField(
        queryset=Player.objects.filter(positions__contains=[Player.Position.ST]),
        label='Нападающий 1 (запасной)',
        required=True,
    )
    secondary_st2 = forms.ModelChoiceField(
        queryset=Player.objects.filter(positions__contains=[Player.Position.ST]),
        label='Нападающий 2 (запасной)',
        required=True,
    )

    # Price ranges in millions (M) for each grade
    PRICE_RANGES = {
        PlayerRating.Grade.S: (24, 27),
        PlayerRating.Grade.A: (18, 23),
        PlayerRating.Grade.B_PLUS: (13, 17),
        PlayerRating.Grade.B: (9, 12),
        PlayerRating.Grade.C: (6, 8),
        PlayerRating.Grade.D: (3, 5),
        PlayerRating.Grade.E: (1, 2),
        None: (1, 2),  # No rating - same as E
    }

    # Rating point ranges for each grade
    RATING_RANGES = {
        PlayerRating.Grade.S: (91, 100),
        PlayerRating.Grade.A: (76, 90),
        PlayerRating.Grade.B_PLUS: (61, 75),
        PlayerRating.Grade.B: (61, 75),
        PlayerRating.Grade.C: (31, 45),
        PlayerRating.Grade.D: (16, 30),
        PlayerRating.Grade.E: (0, 15),
        None: (0, 15),  # No rating - same as E
    }

    BUDGET_LIMITS = {
        'Высшая лига': 70.0,
        'Первая лига': 45.0,
        'Вторая лига': 30.0,
    }

    def get_league_budget_limit(self, league):
        return self.BUDGET_LIMITS.get(league.title)

    def calculate_player_cost(self, player_rating):
        """Calculate player cost in millions based on grade and rating points"""
        if not player_rating:
            grade = None
            rating_points = 0
        else:
            grade = player_rating.grade
            rating_points = player_rating.rating_points

        price_range = self.PRICE_RANGES.get(grade, (1, 2))
        rating_range = self.RATING_RANGES.get(grade, (0, 15))

        min_price, max_price = price_range
        min_rating, max_rating = rating_range

        if max_rating == min_rating:
            position_ratio = 0.0
        else:
            position_ratio = (rating_points - min_rating) / (max_rating - min_rating)

        position_ratio = max(0.0, min(1.0, position_ratio))
        cost = min_price + (max_price - min_price) * position_ratio

        return round(cost, 1)

    def __init__(self, *args, tournament: League, **kwargs):
        super().__init__(*args, **kwargs)
        self.tournament = tournament
        latest_rating_version = PlayerRatingVersion.objects.order_by('-number').first()
        league_player_ids = list(Player.objects.filter(team__in=tournament.teams.all()).values_list('id', flat=True))
        ratings = PlayerRating.objects.filter(player_id__in=league_player_ids, version=latest_rating_version)
        player_rating_map = {r.player_id: r for r in ratings}
        self.player_costs = {pid: self.calculate_player_cost(player_rating_map.get(pid)) for pid in league_player_ids}

        team_filter = {'team__in': tournament.teams.all()}

        latest_rating_subquery = PlayerRating.objects.filter(
            player_id=OuterRef('pk'), version=latest_rating_version
        ).values('rating_points')[:1]

        annotated_players = (
            Player.objects.filter(**team_filter)
            .annotate(
                latest_rating=Subquery(latest_rating_subquery, output_field=IntegerField()),
            )
            .order_by('-latest_rating')
        )

        self.fields['primary_gk'].queryset = annotated_players.filter(positions__contains=[Player.Position.GK])
        self.fields['secondary_gk'].queryset = annotated_players.filter(positions__contains=[Player.Position.GK])
        self.fields['primary_dm'].queryset = annotated_players.filter(positions__contains=[Player.Position.DM])
        self.fields['secondary_dm'].queryset = annotated_players.filter(positions__contains=[Player.Position.DM])
        self.fields['primary_st1'].queryset = annotated_players.filter(positions__contains=[Player.Position.ST])
        self.fields['primary_st2'].queryset = annotated_players.filter(positions__contains=[Player.Position.ST])
        self.fields['secondary_st1'].queryset = annotated_players.filter(positions__contains=[Player.Position.ST])
        self.fields['secondary_st2'].queryset = annotated_players.filter(positions__contains=[Player.Position.ST])

    def clean(self):
        cleaned_data = super().clean()

        primary_players = [
            cleaned_data.get('primary_gk'),
            cleaned_data.get('primary_dm'),
            cleaned_data.get('primary_st1'),
            cleaned_data.get('primary_st2'),
        ]

        if len(set(primary_players)) != 4:
            raise forms.ValidationError('В основном составе не может быть дублирующихся игроков')

        secondary_players = [
            cleaned_data.get('secondary_gk'),
            cleaned_data.get('secondary_dm'),
            cleaned_data.get('secondary_st1'),
            cleaned_data.get('secondary_st2'),
        ]

        if len(set(secondary_players)) != 4:
            raise forms.ValidationError('В запасном составе не может быть дублирующихся игроков')

        all_players = primary_players + secondary_players
        if len(set(all_players)) != 8:
            raise forms.ValidationError('Каждый игрок может быть выбран только один раз')

        # Budget limit checks
        latest_rating_version = PlayerRatingVersion.objects.order_by('-number').first()
        budget_limit = self.get_league_budget_limit(self.tournament)
        player_ids = [p.id for p in all_players if p]
        ratings = PlayerRating.objects.filter(player_id__in=player_ids, version=latest_rating_version)
        player_rating_map = {r.player_id: r for r in ratings}

        def get_cost(player):
            player_rating = player_rating_map.get(player.id, None)
            return self.calculate_player_cost(player_rating)

        primary_cost = sum(get_cost(p) for p in primary_players if p)
        if primary_cost > budget_limit:
            raise forms.ValidationError(f'Превышен бюджет для основного состава: {primary_cost}M > {budget_limit}M')

        secondary_cost = sum(get_cost(p) for p in secondary_players if p)
        if secondary_cost > budget_limit:
            raise forms.ValidationError(f'Превышен бюджет для запасного состава: {secondary_cost}M > {budget_limit}M')

        return cleaned_data

    def get_primary_squad_players(self):
        """Get list of primary squad players from cleaned data"""
        if not self.is_valid():
            return []

        return [
            self.cleaned_data['primary_gk'],
            self.cleaned_data['primary_dm'],
            self.cleaned_data['primary_st1'],
            self.cleaned_data['primary_st2'],
        ]

    def get_secondary_squad_players(self):
        """Get list of secondary squad players from cleaned data"""
        if not self.is_valid():
            return []

        return [
            self.cleaned_data['secondary_gk'],
            self.cleaned_data['secondary_dm'],
            self.cleaned_data['secondary_st1'],
            self.cleaned_data['secondary_st2'],
        ]
