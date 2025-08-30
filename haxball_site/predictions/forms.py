from django import forms
from django.contrib.auth.models import User

from .models import PredictionTournament


class TournamentFilterForm(forms.Form):
    """Form for filtering by tournament"""

    tournament = forms.ModelChoiceField(
        queryset=PredictionTournament.objects.filter(is_active=True),
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
