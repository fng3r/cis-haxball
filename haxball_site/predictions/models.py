from django.contrib.auth.models import User
from django.db import models

from tournament.models import League, Match, MatchResult, TourNumber


class PredictionTournament(models.Model):
    """Tournament that is available for predictions"""

    league = models.OneToOneField(
        League, verbose_name='Турнир', on_delete=models.CASCADE, related_name='prediction_tournament'
    )
    is_active = models.BooleanField('Активен для прогнозов', default=True)

    def __str__(self):
        return f'Прогнозы: {self.league.title}'

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

        actual_result = self.match.result.value
        if actual_result in [MatchResult.HOME_WIN, MatchResult.HOME_DEF_WIN]:
            actual_result_for_prediction = self.Result.HOME_WIN
        elif actual_result in [MatchResult.AWAY_WIN, MatchResult.AWAY_DEF_WIN]:
            actual_result_for_prediction = self.Result.AWAY_WIN
        elif actual_result == MatchResult.DRAW:
            actual_result_for_prediction = self.Result.DRAW
        else:
            return 0

        # Compare prediction with actual result
        if self.predicted_result == actual_result_for_prediction:
            return 1
        return 0
