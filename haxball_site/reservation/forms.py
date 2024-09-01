from django import forms

from .models import ReservationEntry


class ReservationEntryForm(forms.ModelForm):
    class Meta:
        model = ReservationEntry
        fields = (
            'author',
            'match',
            'time_date',
        )
