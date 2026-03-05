from django.contrib.auth.models import User
from django.db import models

from tournament.models import League, Match, Team, TourNumber


class PredictionsContestTournament(models.Model):
    """Tournament that is available for predictions contest"""

    league = models.OneToOneField(
        League, verbose_name='Турнир', on_delete=models.CASCADE, related_name='predictions_contest_tournament'
    )
    is_active = models.BooleanField('Активен для прогнозов', default=True)
    points_for_win_prediction = models.DecimalField(
        'Очки за верный прогноз победителя', default=1, max_digits=5, decimal_places=2
    )
    points_for_draw_prediction = models.DecimalField(
        'Очки за верный прогноз ничьей', default=3, max_digits=5, decimal_places=2
    )
    special_match_points_delta = models.DecimalField(
        'Бонус/штраф за особый прогноз', default=0.5, max_digits=5, decimal_places=2
    )

    def __str__(self):
        return f'{self.league.title}'

    class Meta:
        verbose_name = 'Турнир для прогнозов'
        verbose_name_plural = 'Турниры для прогнозов'


class PreseasonPredictionsTournament(models.Model):
    """Tournament that is available for preseason predictions"""

    league = models.OneToOneField(
        League, verbose_name='Турнир', on_delete=models.CASCADE, related_name='preseason_predictions_tournament'
    )
    is_active = models.BooleanField('Сбор прогнозов открыт', default=True)

    def __str__(self):
        return f'{self.league.title}'

    class Meta:
        verbose_name = 'Турнир для предсезонных прогнозов'
        verbose_name_plural = 'Турниры для предсезонных прогнозов'


class PredictionSubmission(models.Model):
    """User's prediction submission for a specific tour"""

    user = models.ForeignKey(
        User, verbose_name='Пользователь', on_delete=models.CASCADE, related_name='prediction_submissions'
    )
    tour = models.ForeignKey(
        TourNumber, verbose_name='Тур', on_delete=models.CASCADE, related_name='prediction_submissions'
    )
    tournament = models.ForeignKey(
        PredictionsContestTournament, verbose_name='Турнир', on_delete=models.CASCADE, related_name='submissions'
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
    is_special = models.BooleanField('Особый прогноз', default=False)

    class Meta:
        verbose_name = 'Прогноз'
        verbose_name_plural = 'Прогнозы'
        unique_together = ['submission', 'match']

    def __str__(self):
        return f'{self.submission.user.username}: {self.match} - {self.get_predicted_result_display()}'


class PreseasonPredictionSubmission(models.Model):
    """User's preseason prediction for final standings in a tournament (league).

    Stores one ordered list per (user, tournament).
    """

    user = models.ForeignKey(
        User, verbose_name='Пользователь', on_delete=models.CASCADE, related_name='preseason_submissions'
    )
    tournament = models.ForeignKey(
        PreseasonPredictionsTournament,
        verbose_name='Турнир',
        on_delete=models.CASCADE,
        related_name='preseason_submissions',
    )
    created = models.DateTimeField('Создано', auto_now_add=True)
    updated = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Предсезонный прогноз'
        verbose_name_plural = 'Предсезонные прогнозы'
        unique_together = ['user', 'tournament']

    def __str__(self):
        return f'Прогноз {self.user.username} на турнир {self.tournament.league.title}'


class PreseasonPredictionItem(models.Model):
    """Single item in a preseason prediction list: team with its predicted position."""

    submission = models.ForeignKey(
        PreseasonPredictionSubmission,
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
