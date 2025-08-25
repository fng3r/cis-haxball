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
    """Form for submitting a squad (4 main + 2 bench)"""

    main_squad_gk = forms.ModelChoiceField(
        queryset=Player.objects.filter(positions__contains=[Player.Position.GK]),
        label='Вратарь (основной)',
        required=True,
    )
    main_squad_dm = forms.ModelChoiceField(
        queryset=Player.objects.filter(positions__contains=[Player.Position.DM]),
        label='Опорник (основной)',
        required=True,
    )
    main_squad_st1 = forms.ModelChoiceField(
        queryset=Player.objects.filter(positions__contains=[Player.Position.ST]),
        label='Нападающий 1 (основной)',
        required=True,
    )
    main_squad_st2 = forms.ModelChoiceField(
        queryset=Player.objects.filter(positions__contains=[Player.Position.ST]),
        label='Нападающий 2 (основной)',
        required=True,
    )

    bench_gk = forms.ModelChoiceField(
        queryset=Player.objects.filter(positions__contains=[Player.Position.GK]),
        label='Вратарь (скамейка)',
        required=False,
    )
    bench_dm = forms.ModelChoiceField(
        queryset=Player.objects.filter(positions__contains=[Player.Position.DM]),
        label='Опорник (скамейка)',
        required=False,
    )
    bench_st = forms.ModelChoiceField(
        queryset=Player.objects.filter(positions__contains=[Player.Position.ST]),
        label='Нападающий (скамейка)',
        required=False,
    )

    captain_player_id = forms.IntegerField(
        widget=forms.HiddenInput(),
        required=False,
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
        'Высшая лига': 85.0,
        'Первая лига': 55.0,
        'Вторая лига': 40.0,
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

    def __init__(self, *args, tournament: League, previous_player_ids: list[int] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tournament = tournament
        self.previous_player_ids = previous_player_ids or []
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

        self.fields['main_squad_gk'].queryset = annotated_players.filter(positions__contains=[Player.Position.GK])
        self.fields['main_squad_dm'].queryset = annotated_players.filter(positions__contains=[Player.Position.DM])
        self.fields['main_squad_st1'].queryset = annotated_players.filter(positions__contains=[Player.Position.ST])
        self.fields['main_squad_st2'].queryset = annotated_players.filter(positions__contains=[Player.Position.ST])
        self.fields['bench_gk'].queryset = annotated_players.filter(positions__contains=[Player.Position.GK])
        self.fields['bench_dm'].queryset = annotated_players.filter(positions__contains=[Player.Position.DM])
        self.fields['bench_st'].queryset = annotated_players.filter(positions__contains=[Player.Position.ST])

    def clean(self):
        cleaned_data = super().clean()

        primary_players = [
            cleaned_data.get('main_squad_gk'),
            cleaned_data.get('main_squad_dm'),
            cleaned_data.get('main_squad_st1'),
            cleaned_data.get('main_squad_st2'),
        ]

        bench_players = [
            cleaned_data.get('bench_gk'),
            cleaned_data.get('bench_dm'),
            cleaned_data.get('bench_st'),
        ]

        if any(p is None for p in primary_players):
            raise forms.ValidationError('Основной состав должен быть полностью укомплектован')

        filled_bench = [p for p in bench_players if p is not None]
        if len(filled_bench) != 2:
            raise forms.ValidationError('На скамейке должно быть ровно 2 игрока (из разных позиций)')

        if len(set(primary_players)) != 4:
            raise forms.ValidationError('В основном составе не может быть дублирующихся игроков')

        all_players = primary_players + filled_bench
        if len(set(all_players)) != 6:
            raise forms.ValidationError('Каждый игрок может быть выбран только один раз')

        captain_id = cleaned_data.get('captain_player_id')
        if not captain_id:
            raise forms.ValidationError('Нужно выбрать капитана')
        if captain_id not in [p.id for p in all_players if p]:
            raise forms.ValidationError('Капитан должен быть одним из выбранных игроков')
        if captain_id not in [p.id for p in primary_players if p]:
            raise forms.ValidationError('Капитан должен быть игроком основного состава')

        self.validate_team_limitations(all_players)
        self.validate_transfers_limit(all_players)
        self.validate_budget_limit(all_players)

        return cleaned_data

    def get_main_squad_players(self):
        """Get list of main squad players from cleaned data"""
        if not self.is_valid():
            return []

        return [
            self.cleaned_data['main_squad_gk'],
            self.cleaned_data['main_squad_dm'],
            self.cleaned_data['main_squad_st1'],
            self.cleaned_data['main_squad_st2'],
        ]

    def get_bench_players(self):
        """Get list of bench players from cleaned data (2 items)"""
        if not self.is_valid():
            return []

        bench = [
            self.cleaned_data.get('bench_gk'),
            self.cleaned_data.get('bench_dm'),
            self.cleaned_data.get('bench_st'),
        ]
        return [p for p in bench if p]

    def validate_budget_limit(self, players):
        """Ensure total cost of players does not exceed budget limit"""
        total_cost = sum(self.player_costs[p.id] for p in players if p)
        budget_limit = self.get_league_budget_limit(self.tournament)
        if total_cost > budget_limit:
            raise forms.ValidationError(f'Превышен общий бюджет команды: {total_cost:.1f}M > {budget_limit}M')

    def validate_team_limitations(self, players):
        """Ensure no more than 2 players from the same team in provided list."""
        from collections import Counter

        team_counts = Counter()
        for p in players:
            if p and p.team:
                team_counts[p.team] += 1
        for team, count in team_counts.items():
            if count > 2:
                raise forms.ValidationError(f'Команда {team.title} имеет {count} игроков (максимум 2)')

    def validate_transfers_limit(self, players):
        """Ensure no more than 2 transfers in"""
        if not self.previous_player_ids:
            return

        selected_ids = {p.id for p in players if p}
        prev_ids = set(self.previous_player_ids)
        transfers_in = len(selected_ids - prev_ids)
        if transfers_in > 2:
            raise forms.ValidationError(f'Превышен лимит трансферов: {transfers_in}/2')
