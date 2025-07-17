from django import forms

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

    # Primary squad fields
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

    # Secondary squad fields
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

    RP_COSTS = {
        PlayerRating.Grade.S: 3,
        PlayerRating.Grade.A: 2.5,
        PlayerRating.Grade.B_PLUS: 2,
        PlayerRating.Grade.B: 1.5,
        PlayerRating.Grade.C: 1,
        PlayerRating.Grade.D: 0.5,
        PlayerRating.Grade.E: 0.5,
        None: 0.5,  # No rating
    }

    RP_LIMITS = {
        'Высшая лига': 9.5,
        'Первая лига': 8,
        'Вторая лига': 5,
    }

    def get_league_rp_limit(self, league):
        return self.RP_LIMITS.get(league.title, 9.5)

    def __init__(self, *args, tournament: League, **kwargs):
        super().__init__(*args, **kwargs)
        self.tournament = tournament
        latest_rating_version = PlayerRatingVersion.objects.order_by('-number').first()
        league_player_ids = list(Player.objects.filter(team__in=tournament.teams.all()).values_list('id', flat=True))
        ratings = PlayerRating.objects.filter(player_id__in=league_player_ids, version=latest_rating_version)
        player_grade_map = {r.player_id: r.grade for r in ratings}
        self.player_rp_costs = {pid: self.RP_COSTS.get(player_grade_map.get(pid)) for pid in league_player_ids}

        team_filter = {'team__in': tournament.teams.all()}
        self.fields['primary_gk'].queryset = Player.objects.filter(
            positions__contains=[Player.Position.GK], **team_filter
        )
        self.fields['secondary_gk'].queryset = Player.objects.filter(
            positions__contains=[Player.Position.GK], **team_filter
        )
        self.fields['primary_dm'].queryset = Player.objects.filter(
            positions__contains=[Player.Position.DM], **team_filter
        )
        self.fields['secondary_dm'].queryset = Player.objects.filter(
            positions__contains=[Player.Position.DM], **team_filter
        )
        self.fields['primary_st1'].queryset = Player.objects.filter(
            positions__contains=[Player.Position.ST], **team_filter
        )
        self.fields['primary_st2'].queryset = Player.objects.filter(
            positions__contains=[Player.Position.ST], **team_filter
        )
        self.fields['secondary_st1'].queryset = Player.objects.filter(
            positions__contains=[Player.Position.ST], **team_filter
        )
        self.fields['secondary_st2'].queryset = Player.objects.filter(
            positions__contains=[Player.Position.ST], **team_filter
        )

        def label_with_rp(player):
            rp = self.player_rp_costs.get(player.id, 0.5)
            return f'{player.nickname} ({rp} RP)'

        for fname in [
            'primary_gk',
            'primary_dm',
            'primary_st1',
            'primary_st2',
            'secondary_gk',
            'secondary_dm',
            'secondary_st1',
            'secondary_st2',
        ]:
            self.fields[fname].label_from_instance = label_with_rp

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

        # RP limit checks
        latest_rating_version = PlayerRatingVersion.objects.order_by('-number').first()
        rp_limit = self.get_league_rp_limit(self.tournament)
        player_ids = [p.id for p in all_players if p]
        ratings = PlayerRating.objects.filter(player_id__in=player_ids, version=latest_rating_version)
        player_grade_map = {r.player_id: r.grade for r in ratings}

        def get_rp(player):
            grade = player_grade_map.get(player.id, None)
            return self.RP_COSTS.get(grade)

        primary_rp = sum(get_rp(p) for p in primary_players if p)
        if primary_rp > rp_limit:
            raise forms.ValidationError(f'Превышен лимит RP для основного состава: {primary_rp} > {rp_limit}')

        secondary_rp = sum(get_rp(p) for p in secondary_players if p)
        if secondary_rp > rp_limit:
            raise forms.ValidationError(f'Превышен лимит RP для запасного состава: {secondary_rp} > {rp_limit}')

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
