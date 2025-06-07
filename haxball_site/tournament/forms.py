from django import forms

from colorfield.widgets import ColorWidget

from .models import FreeAgent, Player, Season, Team


class FreeAgentForm(forms.ModelForm):
    class Meta:
        model = FreeAgent
        fields = ('position_main', 'description')


class EditTeamProfileForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ('color_1', 'color_2')
        widgets = {
            'color_1': ColorWidget,
            'color_2': ColorWidget,
        }


class ComparePlayersForm(forms.Form):
    class MatchesSelection:
        ALL = 'all'
        SAME_TEAM = 'same_team'
        HEAD_TO_HEAD = 'head_to_head'

    player1 = forms.ModelChoiceField(label='Игрок 1', queryset=Player.objects.all(), required=True)
    player2 = forms.ModelChoiceField(label='Игрок 2', queryset=Player.objects.all(), required=True)
    season = forms.ModelChoiceField(
        label='Сезон',
        queryset=Season.objects.filter(number__gt=5),
        empty_label='Все',
        required=False,
    )
    tournament = forms.ChoiceField(
        label='Турнир',
        choices=(
            ('', 'Все'),
            ('Высшая лига', 'Высшая лига'),
            ('Единая лига', 'Единая лига'),
            ('Высшая лига|Единая лига', 'Высшая + Единая лига'),
            ('Первая лига', 'Первая лига'),
            ('Вторая лига', 'Вторая лига'),
            ('Кубок России', 'Кубок России'),
            ('Лига Чемпионов', 'Лига Чемпионов'),
            ('Кубок Высшей лиги', 'Кубок Высшей лиги'),
            ('Кубок Первой лиги', 'Кубок Первой лиги'),
            ('Кубок Второй лиги', 'Кубок Второй лиги'),
            ('Кубок лиги', 'Кубок лиги'),
            ('Итоговый турнир', 'Итоговый турнир'),
        ),
        required=False,
    )
    matches_selection = forms.ChoiceField(
        label='Выборка матчей',
        choices=(
            (MatchesSelection.ALL, 'Все'),
            (MatchesSelection.SAME_TEAM, 'Только в одной команде'),
            (MatchesSelection.HEAD_TO_HEAD, 'Только очные матчи'),
        ),
        required=False,
    )


class CompareTeamsForm(forms.Form):
    class MatchesSelection:
        ALL = 'all'
        HEAD_TO_HEAD = 'head_to_head'

    team1 = forms.ModelChoiceField(label='Команда 1', queryset=Team.objects.all().order_by('title'), required=True)
    team2 = forms.ModelChoiceField(label='Команда 2', queryset=Team.objects.all().order_by('title'), required=True)
    season = forms.ModelChoiceField(
        label='Сезон',
        queryset=Season.objects.filter(number__gt=5),
        empty_label='Все',
        required=False,
    )
    tournament = forms.ChoiceField(
        label='Турнир',
        choices=(
            ('', 'Все'),
            ('Высшая лига', 'Высшая лига'),
            ('Единая лига', 'Единая лига'),
            ('Высшая лига|Единая лига', 'Высшая + Единая лига'),
            ('Первая лига', 'Первая лига'),
            ('Вторая лига', 'Вторая лига'),
            ('Кубок России', 'Кубок России'),
            ('Лига Чемпионов', 'Лига Чемпионов'),
            ('Кубок Высшей лиги', 'Кубок Высшей лиги'),
            ('Кубок Первой лиги', 'Кубок Первой лиги'),
            ('Кубок Второй лиги', 'Кубок Второй лиги'),
            ('Кубок лиги', 'Кубок лиги'),
            ('Итоговый турнир', 'Итоговый турнир'),
        ),
        required=False,
    )
    matches_selection = forms.ChoiceField(
        label='Выборка матчей',
        choices=(
            (MatchesSelection.ALL, 'Все'),
            (MatchesSelection.HEAD_TO_HEAD, 'Только очные матчи'),
        ),
        required=False,
    )
