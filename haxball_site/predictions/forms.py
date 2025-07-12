from django import forms
from django.contrib.auth.models import User

from tournament.models import TourNumber

from .models import Prediction, PredictionSubmission, PredictionTournament
from .utils import get_open_tours


class PredictionForm(forms.ModelForm):
    """Form for making predictions"""

    class Meta:
        model = Prediction
        fields = ['predicted_result']
        widgets = {'predicted_result': forms.RadioSelect()}


class TournamentFilterForm(forms.Form):
    """Form for filtering by tournament"""

    tournament = forms.ModelChoiceField(
        queryset=PredictionTournament.objects.filter(is_active=True),
        empty_label='Выберите турнир',
        label='Турнир',
        required=False,
    )


class UserFilterForm(forms.Form):
    """Form for filtering by user"""

    user = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        empty_label='Выберите пользователя',
        label='Пользователь',
        required=False,
    )


class PredictionSubmissionForm(forms.ModelForm):
    """Form for creating/updating prediction submissions"""

    class Meta:
        model = PredictionSubmission
        fields = ['tour', 'tournament']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            # Filter tournaments to only active ones
            self.fields['tournament'].queryset = PredictionTournament.objects.filter(is_active=True)

            # Filter tours to only those that are open for predictions
            open_tours = get_open_tours()
            self.fields['tour'].queryset = TourNumber.objects.filter(id__in=open_tours)
