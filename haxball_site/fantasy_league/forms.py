from django import forms
from django.db.models import Case, IntegerField, OuterRef, Subquery, Value, When

from tournament.models import League, Player, PlayerRating, PlayerRatingVersion, TourNumber

from .models import BoosterType, FantasyTournament, SquadSubmission
from .utils import get_available_players_in_league, get_later_blocking_tours, get_league_budget_limit, get_players_costs


class TournamentFilterForm(forms.Form):
    """Form for filtering tournaments"""

    tournament = forms.ModelChoiceField(
        queryset=FantasyTournament.objects.filter(is_active=True).order_by('league__priority'),
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


class TourFilterForm(forms.Form):
    """Form for selecting a tour within a league"""

    tour = forms.ModelChoiceField(
        queryset=TourNumber.objects.none(),
        empty_label=None,
        required=False,
        label='Тур',
    )

    def __init__(self, *args, league: League | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if league is not None:
            self.fields['tour'].queryset = TourNumber.objects.filter(league=league).order_by('number')


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

    used_booster = forms.ChoiceField(
        choices=BoosterType.choices,
        required=False,
        label='Бустер',
    )

    def __init__(
        self, *args, tournament: League, previous_player_ids: list[int] | None = None, user=None, tour=None, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.tournament = tournament
        self.previous_player_ids = previous_player_ids or []
        self.user = user
        self.tour = tour
        latest_rating_version = PlayerRatingVersion.objects.order_by('-number').first()
        self.player_costs = get_players_costs(self.tournament)
        self.available_player_ids = get_available_players_in_league(self.tournament)
        self.available_boosters = []

        if user and tour:
            total_tours = tournament.tours.count()
            if tour.number != 1 and tour.number != (total_tours / 2 + 1):
                used_booster_types = SquadSubmission.objects.filter(
                    user=user,
                    tournament=tournament.fantasy_tournament,
                    tour__number__lt=tour.number,
                    used_booster__isnull=False,
                ).values_list('used_booster', flat=True)

                self.available_boosters = [
                    booster for booster in BoosterType.values if booster not in used_booster_types
                ]

        team_filter = {'team__in': tournament.teams.all()}

        latest_rating_subquery = PlayerRating.objects.filter(
            player_id=OuterRef('pk'), version=latest_rating_version
        ).values('rating_points')[:1]

        annotated_players = Player.objects.filter(**team_filter).annotate(
            latest_rating=Subquery(latest_rating_subquery, output_field=IntegerField()),
        )

        players_list = list(annotated_players)
        players_list.sort(key=lambda p: self.player_costs.get(p.id, 0), reverse=True)
        player_ids = [p.id for p in players_list]

        annotated_players = (
            Player.objects.filter(**team_filter)
            .annotate(
                latest_rating=Subquery(latest_rating_subquery, output_field=IntegerField()),
                sort_order=Case(
                    *[When(id=pid, then=Value(i)) for i, pid in enumerate(player_ids)],
                    default=Value(len(player_ids)),
                    output_field=IntegerField(),
                ),
            )
            .order_by('sort_order')
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

        self.validate_later_blocking_tours()

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
        self.validate_players_availability(all_players)
        self.validate_booster_usage()
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

    def is_player_available(self, player):
        """Check if a player is available in the current league"""
        return player.id in self.available_player_ids

    def validate_later_blocking_tours(self):
        """Ensure no later blocking tours exist for this tour"""
        later_blocking_tours = get_later_blocking_tours(self.user, self.tour, self.tournament.fantasy_tournament)
        if later_blocking_tours:
            raise forms.ValidationError(
                f'Cостав не может быть изменен, так как уже выбран состав для следующих туров: '
                f'{", ".join([f"{tour.number} тур" for tour in later_blocking_tours])}'
            )

    def validate_budget_limit(self, players):
        """Ensure total cost of players does not exceed budget limit"""
        booster = self.cleaned_data.get('used_booster')

        if booster == BoosterType.LIMITLESS:
            return

        total_cost = sum(self.player_costs[p.id] for p in players if p)
        budget_limit = get_league_budget_limit(self.tournament)
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
                raise forms.ValidationError(f'Состав содержит более 2 игроков из одной команды ({team.title})')

    def validate_transfers_limit(self, players):
        """Ensure no more than 4 transfers in (2 free + 2 penalty)"""
        booster = self.cleaned_data.get('used_booster')

        if booster in [BoosterType.JOKER, BoosterType.LIMITLESS]:
            return

        if not self.previous_player_ids:
            return

        selected_ids = {p.id for p in players if p}
        prev_ids = set(self.previous_player_ids)
        transfers_in = len(selected_ids - prev_ids)
        if transfers_in > 4:
            raise forms.ValidationError(f'Превышен лимит трансферов: {transfers_in}/4')

    def validate_players_availability(self, players):
        """Ensure all selected players are available in the current league"""
        available_player_ids = get_available_players_in_league(self.tournament)
        unavailable_players = []

        for player in players:
            if player and player.id not in available_player_ids:
                unavailable_players.append(player.nickname)

        if unavailable_players:
            players_list = ', '.join(unavailable_players)
            raise forms.ValidationError(
                f'Следующие игроки больше не доступны в лиге и должны быть заменены: {players_list}'
            )

    def validate_booster_usage(self):
        """Validate that booster hasn't been used before in this tournament"""
        booster = self.cleaned_data.get('used_booster')
        if not booster or not self.user or not self.tour:
            return

        total_tours = self.tournament.tours.count()
        if self.tour.number == 1 or self.tour.number == (total_tours / 2 + 1):
            raise forms.ValidationError('Бустеры не могут быть использованы в текущем туре')

        previous_usage = SquadSubmission.objects.filter(
            user=self.user,
            tournament=self.tournament.fantasy_tournament,
            used_booster=booster,
            tour__number__lt=self.tour.number,
        ).exists()

        if previous_usage:
            booster_name = dict(BoosterType.choices)[booster]
            raise forms.ValidationError(
                f'Бустер "{booster_name}" уже был использован в этом турнире. '
                f'Каждый тип бустера можно использовать только один раз за турнир.'
            )
