from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from tournament.models import League, Match, Team, TourNumber


class PredictionsContestTournament(models.Model):
    """Tournament that is available for predictions contest"""

    class ScoringMethod(models.TextChoices):
        LEGACY = 'legacy', 'Классические очки'
        COEFFICIENT = 'coefficient', 'Коэффициенты'

    league = models.OneToOneField(
        League, verbose_name='Турнир', on_delete=models.CASCADE, related_name='predictions_contest_tournament'
    )
    is_active = models.BooleanField('Активен для прогнозов', default=True)
    scoring_method = models.CharField(
        'Формат начисления очков',
        max_length=16,
        choices=ScoringMethod.choices,
        default=ScoringMethod.LEGACY,
        help_text='"Классические очки" — прежний формат (1/3 очка, особые матчи). '
        '"Коэффициенты" — 5 исходов матча с коэффициентами, очки = номинальные × коэффициент',
    )
    nominal_points = models.DecimalField(
        'Номинальные очки',
        default=100,
        max_digits=5,
        decimal_places=2,
        help_text='Очки за верный прогноз до умножения на коэффициент (формат "Коэффициенты")',
    )
    points_for_win_prediction = models.DecimalField(
        'Очки за верный прогноз победителя',
        default=1,
        max_digits=5,
        decimal_places=2,
        help_text='Для классического формата',
    )
    points_for_draw_prediction = models.DecimalField(
        'Очки за верный прогноз ничьей',
        default=3,
        max_digits=5,
        decimal_places=2,
        help_text='Для классического формата',
    )
    special_match_points_delta = models.DecimalField(
        'Бонус/штраф за особый прогноз',
        default=0.5,
        max_digits=5,
        decimal_places=2,
        help_text='Для классического формата',
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
    locked_at = models.DateTimeField('Дата закрытия сбора прогнозов')

    @property
    def is_active(self):
        return timezone.localtime() < self.locked_at

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
        HOME_WIN_OR_DRAW = 'HWD', '1Х'
        DRAW = 'D', 'X'
        AWAY_WIN_OR_DRAW = 'AWD', 'Х2'
        AWAY_WIN = 'AW', 'П2'
        HANDICAP = 'FH', 'Фора'

    submission = models.ForeignKey(
        PredictionSubmission, verbose_name='Отправка', on_delete=models.CASCADE, related_name='predictions'
    )
    match = models.ForeignKey(Match, verbose_name='Матч', on_delete=models.CASCADE, related_name='predictions')
    predicted_result = models.CharField('Предсказанный результат', max_length=3, choices=Result.choices)
    handicap = models.ForeignKey(
        'MatchPredictionHandicap',
        verbose_name='Фора',
        on_delete=models.CASCADE,
        related_name='predictions',
        null=True,
        blank=True,
        help_text='Заполняется, когда выбран исход "Фора"',
    )
    is_special = models.BooleanField('Особый прогноз', default=False)

    @property
    def outcome_label(self):
        if self.handicap_id:
            return self.handicap.display_label
        return self.get_predicted_result_display()

    class Meta:
        verbose_name = 'Прогноз'
        verbose_name_plural = 'Прогнозы'
        unique_together = ['submission', 'match']

    def __str__(self):
        return f'{self.submission.user.username}: {self.match} - {self.get_predicted_result_display()}'


class MatchPredictionCoefficients(models.Model):
    """Coefficients of prediction outcomes for a match.

    A match is available for predictions in the "coefficients" format only
    when this row exists for it.
    """

    match = models.OneToOneField(
        Match,
        verbose_name='Матч',
        on_delete=models.CASCADE,
        related_name='prediction_coefficients',
    )
    home_win = models.DecimalField('Коэффициент П1', max_digits=5, decimal_places=2)
    home_win_or_draw = models.DecimalField('Коэффициент 1Х', max_digits=5, decimal_places=2)
    draw = models.DecimalField('Коэффициент Х', max_digits=5, decimal_places=2)
    away_win_or_draw = models.DecimalField('Коэффициент Х2', max_digits=5, decimal_places=2)
    away_win = models.DecimalField('Коэффициент П2', max_digits=5, decimal_places=2)

    COEFFICIENT_FIELD_BY_RESULT = {
        Prediction.Result.HOME_WIN: 'home_win',
        Prediction.Result.HOME_WIN_OR_DRAW: 'home_win_or_draw',
        Prediction.Result.DRAW: 'draw',
        Prediction.Result.AWAY_WIN_OR_DRAW: 'away_win_or_draw',
        Prediction.Result.AWAY_WIN: 'away_win',
    }

    def coefficient_for(self, result_value):
        """Return Decimal coefficient for a Prediction.Result value or None."""
        field_name = self.COEFFICIENT_FIELD_BY_RESULT.get(result_value)
        if field_name is None:
            return None
        return getattr(self, field_name)

    def __str__(self):
        return f'Коэффициенты: {self.match.team_home.short_title} - {self.match.team_guest.short_title}'

    class Meta:
        verbose_name = 'Коэффициенты прогноза на матч'
        verbose_name_plural = 'Коэффициенты прогнозов на матчи'


def format_handicap_value(value) -> str:
    """Format a signed handicap value to one decimal digit, e.g. -5.5 / +5.5 / 0."""
    decimal_value = Decimal(value)
    if decimal_value < 0:
        return f'-{abs(decimal_value.quantize(Decimal("0.1")).normalize())}'
    if decimal_value > 0:
        return f'+{decimal_value.quantize(Decimal("0.1")).normalize()}'
    return '0'


class MatchPredictionHandicap(models.Model):
    """A single handicap outcome (Ф1/Ф2 with a value and coefficient) for a match.

    Handicaps belong to a MatchPredictionCoefficients row and are managed in
    the admin as an inline of it. A match can have zero or more handicaps, each
    becoming an extra outcome to predict on in the "coefficients" format.
    """

    class Team(models.TextChoices):
        HOME = 'home', 'Ф1'
        AWAY = 'away', 'Ф2'

    coefficients = models.ForeignKey(
        MatchPredictionCoefficients,
        verbose_name='Коэффициенты матча',
        on_delete=models.CASCADE,
        related_name='handicaps',
    )
    team = models.CharField(
        'Команда',
        max_length=4,
        choices=Team.choices,
        default=Team.HOME,
        help_text='Ф1 — хозяева, Ф2 — гости',
    )
    value = models.DecimalField(
        'Значение форы',
        max_digits=6,
        decimal_places=2,
        help_text='Со знаком: -5.5 для Ф1 (-5.5) или +5.5 для Ф2 (+5.5). '
        'Прогноз верен, если счёт команды с форой больше счёта соперника.',
    )
    coefficient = models.DecimalField('Коэффициент', max_digits=5, decimal_places=2)

    @property
    def display_label(self):
        return f'{self.get_team_display()} ({format_handicap_value(self.value)})'

    def __str__(self):
        return f'{self.coefficients.match}: {self.display_label}'

    class Meta:
        verbose_name = 'Фора на матч'
        verbose_name_plural = 'Форы на матчи'


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
