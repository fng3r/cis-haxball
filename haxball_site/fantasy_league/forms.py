from django import forms

from tournament.models import Player

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

    def __init__(self, *args, tournament, **kwargs):
        super().__init__(*args, **kwargs)
        tournament = tournament
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

        # Check for duplicate players between primary and secondary squads
        all_players = primary_players + secondary_players
        if len(set(all_players)) != 8:
            raise forms.ValidationError('Каждый игрок может быть выбран только один раз')

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
