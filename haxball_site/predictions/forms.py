from django import forms
from django.contrib.auth.models import User

from .models import PredictionsContestTournament, PreseasonPredictionsTournament


class TournamentFilterForm(forms.Form):
    """Form for filtering by tournament"""

    tournament = forms.ModelChoiceField(
        queryset=PredictionsContestTournament.objects.filter(is_active=True).order_by('league__priority'),
        empty_label=None,
        label='Турнир',
        required=False,
    )


class PreseasonPredictionsTournamentFilterForm(forms.Form):
    """Form for filtering by preseason predictions tournament"""

    tournament = forms.ModelChoiceField(
        queryset=PreseasonPredictionsTournament.objects.order_by('league__priority'),
        empty_label=None,
        label='Турнир',
        required=False,
    )


class UserFilterForm(forms.Form):
    """Form for filtering by user"""

    user = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        empty_label=None,
        label='Пользователь',
        required=False,
    )
