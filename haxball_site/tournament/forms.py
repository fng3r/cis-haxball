from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from colorfield.widgets import ColorWidget

from .models import (
    AwardSubmission,
    AwardVote,
    FreeAgent,
    Player,
    Season,
    Team,
)


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


def get_years_choices():
    earliest_year = 2024
    current_year = timezone.now().year

    return [(year, str(year)) for year in range(earliest_year, current_year + 1)]


class TeamsYearlyRatingForm(forms.Form):
    year = forms.ChoiceField(
        label='Год',
        choices=get_years_choices,
    )


class AwardVotingForm(forms.Form):
    """Form for voting in season awards"""

    def __init__(self, *args, awards=None, user_team=None, user_player=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.awards = awards or []
        self.user_team = user_team
        self.user_player = user_player

        # Create fields for each award/nomination
        for award in self.awards:
            nomination = award.nomination
            nominees = award.nominees.all()
            # Get Player queryset from nominees
            player_ids = nominees.values_list('player_id', flat=True)
            players_queryset = Player.objects.filter(id__in=player_ids)

            # Create 3 fields for places 1, 2, 3
            for place in [1, 2, 3]:
                field_name = f'{nomination.code}_place_{place}'
                self.fields[field_name] = forms.ModelChoiceField(
                    queryset=players_queryset,
                    required=True,
                    label=f'{nomination.name} - {place} место',
                    empty_label='Выберите игрока',
                )

    def clean(self):
        cleaned_data = super().clean()

        now = timezone.now()

        # Track players from own team across all nominations (only if voter has a team)
        own_team_players = []

        # Validate each nomination
        for award in self.awards:
            nomination = award.nomination

            # Check voting period
            if not (award.voting_start_date <= now <= award.voting_end_date):
                raise ValidationError(
                    f'Голосование для "{nomination.name}" не доступно в данный момент. '
                    f'Период голосования: {award.voting_start_date.strftime("%d.%m.%Y %H:%M")} - '
                    f'{award.voting_end_date.strftime("%d.%m.%Y %H:%M")}'
                )

            # Get selected players for this nomination
            selected_players = []
            for place in [1, 2, 3]:
                field_name = f'{nomination.code}_place_{place}'
                player = cleaned_data.get(field_name)
                if player:
                    selected_players.append((place, player))

            # Validate: exactly 3 players must be selected
            if len(selected_players) != 3:
                raise ValidationError(f'Для номинации "{nomination.name}" необходимо выбрать ровно 3 игроков')

            # Validate: all 3 players must be different
            players_list = [p for _, p in selected_players]
            if len(set(players_list)) != 3:
                raise ValidationError(f'Для номинации "{nomination.name}" необходимо выбрать 3 разных игроков')

            if self.user_team:
                for _, player in selected_players:
                    if player.team == self.user_team:
                        own_team_players.append(player)

        # Validate: no more than 3 selections total from own team across all nominations
        # Same player selected in multiple nominations counts multiple times
        if self.user_team and len(own_team_players) > 3:
            raise ValidationError(
                'Можно выбрать не более 3 игроков из своей команды во всех номинациях (с учетом повторений)'
            )

        return cleaned_data

    def save(self):
        """Save votes to database for all awards at once"""
        if not self.awards:
            raise ValueError('Не указаны награды')
        if not self.user_player:
            raise ValueError('Не указан голосующий игрок')

        now = timezone.now()
        votes = []

        # Get campaign and league from first award (all awards should be in the same campaign and league)
        campaign = self.awards[0].campaign
        league = self.awards[0].league

        # Create or get one submission for the entire campaign (use voter for uniqueness, team can be null)
        submission, created = AwardSubmission.objects.get_or_create(
            campaign=campaign,
            voter=self.user_player,
            defaults={'team': self.user_team, 'league': league, 'submitted_at': now},
        )
        if (
            submission.team != self.user_team
            or submission.voter != self.user_player
            or submission.league != league
            or not submission.submitted_at
        ):
            submission.team = self.user_team
            submission.voter = self.user_player
            submission.league = league
            submission.submitted_at = now
            submission.save(update_fields=['team', 'voter', 'league', 'submitted_at'])

        # Delete existing votes for this submission
        AwardVote.objects.filter(submission=submission).delete()

        # Create votes for all awards
        for award in self.awards:
            nomination = award.nomination
            for place in [1, 2, 3]:
                field_name = f'{nomination.code}_place_{place}'
                player = self.cleaned_data.get(field_name)
                if player:
                    # Calculate points: 3 for 1st, 2 for 2nd, 1 for 3rd
                    points = 4 - place
                    vote = AwardVote(
                        submission=submission,
                        award=award,
                        player=player,
                        place=place,
                        points=points,
                    )
                    votes.append(vote)

        # Bulk create all votes at once
        AwardVote.objects.bulk_create(votes)

        # Update submitted_at timestamp
        submission.submitted_at = now
        submission.save(update_fields=['submitted_at'])

        return [submission]
