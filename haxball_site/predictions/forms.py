from django import forms
from django.contrib.auth.models import User

from tournament.models import League, Season, TourNumber

from .models import PredictionsContestTournament, PreseasonPredictionsTournament


class SeasonFilterForm(forms.Form):
    """Form for filtering by season."""

    season = forms.ModelChoiceField(
        queryset=Season.objects.none(),
        empty_label=None,
        label='Сезон',
        required=False,
    )

    def __init__(self, available_seasons, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['season'].queryset = available_seasons


class TournamentFilterForm(forms.Form):
    """Form for filtering by tournament"""

    tournament = forms.ModelChoiceField(
        queryset=PredictionsContestTournament.objects.none(),
        empty_label=None,
        label='Турнир',
        required=False,
    )

    def __init__(self, *args, season: Season | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = PredictionsContestTournament.objects.all()
        if season is not None:
            queryset = queryset.filter(league__championship=season)
        self.fields['tournament'].queryset = queryset.order_by('league__priority')


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


class PreseasonPredictionsTournamentFilterForm(forms.Form):
    """Form for filtering by preseason predictions tournament"""

    tournament = forms.ModelChoiceField(
        queryset=PreseasonPredictionsTournament.objects.none(),
        empty_label=None,
        label='Турнир',
        required=False,
    )

    def __init__(self, *args, season: Season | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = PreseasonPredictionsTournament.objects.all()
        if season is not None:
            queryset = queryset.filter(league__championship=season)
        self.fields['tournament'].queryset = queryset.order_by('league__priority')


class UserFilterForm(forms.Form):
    """Form for filtering by user"""

    user = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        empty_label=None,
        label='Пользователь',
        required=False,
    )
