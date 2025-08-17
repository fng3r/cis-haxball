from django.contrib.auth.models import User
from django.db import models

from tournament.models import League, Match, MatchResult, Team, TourNumber


class PredictionTournament(models.Model):
    """Tournament that is available for predictions"""

    league = models.OneToOneField(
        League, verbose_name='Турнир', on_delete=models.CASCADE, related_name='prediction_tournament'
    )
    is_active = models.BooleanField('Активен для прогнозов', default=True)

    def __str__(self):
        return f'{self.league.title}'

    class Meta:
        verbose_name = 'Турнир для прогнозов'
        verbose_name_plural = 'Турниры для прогнозов'


class PredictionSubmission(models.Model):
    """User's prediction submission for a specific tour"""

    user = models.ForeignKey(
        User, verbose_name='Пользователь', on_delete=models.CASCADE, related_name='prediction_submissions'
    )
    tour = models.ForeignKey(
        TourNumber, verbose_name='Тур', on_delete=models.CASCADE, related_name='prediction_submissions'
    )
    tournament = models.ForeignKey(
        PredictionTournament, verbose_name='Турнир', on_delete=models.CASCADE, related_name='submissions'
    )
    created = models.DateTimeField('Создано', auto_now_add=True)
    updated = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Отправка прогнозов'
        verbose_name_plural = 'Отправки прогнозов'
        unique_together = ['user', 'tour', 'tournament']

    def __str__(self):
        return f'Прогнозы {self.user.username} для {self.tour}'

    def get_total_points(self):
        """Get total points for this submission"""
        return sum(prediction.get_earned_points() for prediction in self.predictions.all())


class Prediction(models.Model):
    """Individual prediction for a match"""

    class Result(models.TextChoices):
        HOME_WIN = 'HW', 'П1'
        DRAW = 'D', 'X'
        AWAY_WIN = 'AW', 'П2'

    submission = models.ForeignKey(
        PredictionSubmission, verbose_name='Отправка', on_delete=models.CASCADE, related_name='predictions'
    )
    match = models.ForeignKey(Match, verbose_name='Матч', on_delete=models.CASCADE, related_name='predictions')
    predicted_result = models.CharField('Предсказанный результат', max_length=2, choices=Result.choices)
    is_special = models.BooleanField('Особый прогноз', default=False)

    class Meta:
        verbose_name = 'Прогноз'
        verbose_name_plural = 'Прогнозы'
        unique_together = ['submission', 'match']

    def __str__(self):
        return f'{self.submission.user.username}: {self.match} - {self.get_predicted_result_display()}'

    def get_earned_points(self):
        """Calculate points based on match result and prediction"""
        if not self.match.is_played:
            return 0

        match_result = self.match.result.value
        if match_result in [MatchResult.HOME_WIN, MatchResult.HOME_DEF_WIN]:
            match_result_for_prediction = self.Result.HOME_WIN
        elif match_result in [MatchResult.AWAY_WIN, MatchResult.AWAY_DEF_WIN]:
            match_result_for_prediction = self.Result.AWAY_WIN
        elif match_result == MatchResult.DRAW:
            match_result_for_prediction = self.Result.DRAW
        else:
            return 0

        base_points = 0
        if self.predicted_result == match_result_for_prediction:
            if self.predicted_result == self.Result.DRAW:
                base_points = 3
            else:
                base_points = 1
        # Special prediction logic
        if self.is_special:
            if self.predicted_result == match_result_for_prediction:
                base_points += 1
            else:
                base_points -= 1
        return base_points


class LongTermPredictionSubmission(models.Model):
    """User's long-term prediction for final standings in a tournament (league).

    Stores one ordered list per (user, tournament).
    """

    user = models.ForeignKey(
        User, verbose_name='Пользователь', on_delete=models.CASCADE, related_name='longterm_submissions'
    )
    tournament = models.ForeignKey(
        PredictionTournament,
        verbose_name='Турнир',
        on_delete=models.CASCADE,
        related_name='longterm_submissions',
    )
    created = models.DateTimeField('Создано', auto_now_add=True)
    updated = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Долгосрочный прогноз'
        verbose_name_plural = 'Долгосрочные прогнозы'
        unique_together = ['user', 'tournament']

    def __str__(self):
        return f'Прогноз {self.user.username} на турнир {self.tournament.league.title}'


class LongTermPredictionItem(models.Model):
    """Single item in a long-term prediction list: team with its predicted position."""

    submission = models.ForeignKey(
        LongTermPredictionSubmission,
        verbose_name='Отправка итоговой таблицы',
        on_delete=models.CASCADE,
        related_name='items',
    )
    team = models.ForeignKey(Team, verbose_name='Команда', on_delete=models.CASCADE)
    position = models.PositiveSmallIntegerField('Позиция')

    class Meta:
        verbose_name = 'Итоговая позиция команды'
        verbose_name_plural = 'Итоговые позиции команд'
        ordering = ['position']
        unique_together = [
            ('submission', 'team'),
            ('submission', 'position'),
        ]

    def __str__(self):
        return f'{self.position}. {self.team}'
