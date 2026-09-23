from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from tournament.models import League, Match, MatchResult, Team, TourNumber


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
        '"Коэффициенты" — 5 исходов матча с коэффициентами, очки = номинал × (коэффициент − 1) '
        'за верный прогноз, −номинал за неверный',
    )
    nominal_points = models.DecimalField(
        'Номинальные очки',
        default=100,
        max_digits=5,
        decimal_places=2,
        help_text='Базовые очки формата "Коэффициенты": +номинал × (коэффициент − 1) за верный прогноз, '
        '−номинал за неверный',
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
        DRAW = 'D', 'X'
        AWAY_WIN = 'AW', 'П2'

    submission = models.ForeignKey(
        PredictionSubmission, verbose_name='Отправка', on_delete=models.CASCADE, related_name='predictions'
    )
    match = models.ForeignKey(Match, verbose_name='Матч', on_delete=models.CASCADE, related_name='predictions')
    predicted_result = models.CharField(
        'Предсказанный результат',
        max_length=3,
        choices=Result.choices,
        null=True,
        blank=True,
        help_text='Только для legacy-конкурсов. '
        'Прогнозы формата "Коэффициенты" используют унифицированный исход (outcome).',
    )
    outcome = models.ForeignKey(
        'MatchPredictionOutcome',
        verbose_name='Исход',
        on_delete=models.CASCADE,
        related_name='predictions',
        null=True,
        blank=True,
        help_text='Унифицированный исход (формат "Коэффициенты"): результат, фора или тотал. '
        'Для legacy-конкурсов не используется',
    )
    is_special = models.BooleanField('Особый прогноз', default=False)

    @property
    def outcome_label(self):
        if self.outcome_id and self.outcome is not None:
            return self.outcome.display_label
        if self.predicted_result:
            return self.get_predicted_result_display()
        return ''

    def clean(self):
        """Enforce one prediction path depending on the contest format.

        Legacy contests use `predicted_result` (П1/X/П2) only;
        coefficient contests use `outcome` only.
        """
        # Assigned-but-unsaved relations (admin inlines, tests) live in the
        # descriptor cache while their *_id is still None.
        submission = self.__dict__.get('submission') or self.submission
        if submission is None:
            return
        outcome = self.__dict__.get('outcome') or self.outcome
        tournament = submission.tournament
        is_legacy = tournament.scoring_method == PredictionsContestTournament.ScoringMethod.LEGACY
        if is_legacy:
            if outcome is not None:
                raise ValidationError({'outcome': 'Legacy-конкурс использует только предсказанный результат'})
            if not self.predicted_result:
                raise ValidationError({'predicted_result': 'Обязательное поле для legacy-конкурса'})
            if self.predicted_result not in (
                self.Result.HOME_WIN,
                self.Result.DRAW,
                self.Result.AWAY_WIN,
            ):
                raise ValidationError({'predicted_result': 'Legacy-конкурс допускает только П1/Х/П2'})
        else:
            if outcome is None:
                raise ValidationError({'outcome': 'Обязательное поле для формата "Коэффициенты"'})
            if self.predicted_result:
                raise ValidationError(
                    {'predicted_result': 'Формат "Коэффициенты" использует только унифицированный исход'}
                )
            if self.is_special:
                raise ValidationError({'is_special': 'Особые прогнозы только для legacy-конкурсов'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    class Meta:
        verbose_name = 'Прогноз'
        verbose_name_plural = 'Прогнозы'
        unique_together = ['submission', 'match']

    def __str__(self):
        return f'{self.submission.user.username}: {self.match} - {self.outcome_label}'


def format_handicap_value(value) -> str:
    """Format a signed handicap value to one decimal digit, e.g. -5.5 / +5.5 / 0."""
    decimal_value = Decimal(value)
    if decimal_value < 0:
        return f'-{abs(decimal_value.quantize(Decimal("0.1")).normalize())}'
    if decimal_value > 0:
        return f'+{decimal_value.quantize(Decimal("0.1")).normalize()}'
    return '0'


def format_total_value(value) -> str:
    """Format a total line without sign, e.g. 5.5 / 5."""
    return f'{Decimal(value).quantize(Decimal("0.1")).normalize()}'


class MatchPredictionOffer(models.Model):
    """Betting card for a single match: aggregates all unified outcomes.

    Exists (and published) = the match is open for predictions in the
    "coefficients" format. Keeps predictions-related configuration out of
    the tournament's Match model and its admin.
    """

    match = models.OneToOneField(
        Match,
        verbose_name='Матч',
        on_delete=models.CASCADE,
        related_name='prediction_offer',
    )
    is_published = models.BooleanField(
        'Опубликовано',
        default=True,
        help_text='Снимите, чтобы скрыть все исходы матча из формы прогнозов, не удаляя их',
    )

    @property
    def results(self):
        return self.outcomes.filter(market=MatchPredictionOutcome.Market.RESULT)

    @property
    def handicaps(self):
        return self.outcomes.filter(market=MatchPredictionOutcome.Market.HANDICAP)

    @property
    def totals(self):
        return self.outcomes.filter(market=MatchPredictionOutcome.Market.TOTAL)

    def __str__(self):
        return f'Исходы: {self.match.team_home.short_title} - {self.match.team_guest.short_title}'

    class Meta:
        verbose_name = 'Исходы матча для прогнозов'
        verbose_name_plural = 'Исходы матчей для прогнозов'


class MatchPredictionOutcome(models.Model):
    """A single bettable outcome (event + coefficient) for a match.

    Unifies all markets: match results, handicaps, totals and individual
    totals live in one table, distinguished by (market, selection, line).
    Settlement logic is a single MatchPredictionOutcome.settle() instead of
    per-type branches.
    """

    class Market(models.TextChoices):
        RESULT = 'RESULT', 'Исход'
        HANDICAP = 'HANDICAP', 'Фора'
        TOTAL = 'TOTAL', 'Тотал'
        INDIVIDUAL_TOTAL = 'ITOTAL', 'Инд. тотал'

    MARKET_ORDER = ['RESULT', 'HANDICAP', 'TOTAL', 'ITOTAL']

    class Selection(models.TextChoices):
        # RESULT market
        HOME_WIN = 'HW', 'П1'
        HOME_WIN_OR_DRAW = 'HWD', '1X'
        DRAW = 'D', 'X'
        AWAY_WIN_OR_DRAW = 'AWD', 'X2'
        AWAY_WIN = 'AW', 'П2'
        # HANDICAP market
        HOME_HANDICAP = 'F1', 'Ф1'
        AWAY_HANDICAP = 'F2', 'Ф2'
        # TOTAL market
        OVER = 'OVER', 'ТБ'
        UNDER = 'UNDER', 'ТМ'
        # INDIVIDUAL_TOTAL market
        HOME_OVER = 'HT_OVER', 'ИТБ1'
        HOME_UNDER = 'HT_UNDER', 'ИТМ1'
        AWAY_OVER = 'AT_OVER', 'ИТБ2'
        AWAY_UNDER = 'AT_UNDER', 'ИТМ2'

    # Allowed selections per market. Single source of truth for clean(),
    # CheckConstraint and admin/form choice filtering.
    SELECTIONS_BY_MARKET = {
        Market.RESULT: {
            Selection.HOME_WIN,
            Selection.HOME_WIN_OR_DRAW,
            Selection.DRAW,
            Selection.AWAY_WIN_OR_DRAW,
            Selection.AWAY_WIN,
        },
        Market.HANDICAP: {Selection.HOME_HANDICAP, Selection.AWAY_HANDICAP},
        Market.TOTAL: {Selection.OVER, Selection.UNDER},
        Market.INDIVIDUAL_TOTAL: {
            Selection.HOME_OVER,
            Selection.HOME_UNDER,
            Selection.AWAY_OVER,
            Selection.AWAY_UNDER,
        },
    }

    offer = models.ForeignKey(
        MatchPredictionOffer,
        verbose_name='Исходы матча',
        on_delete=models.CASCADE,
        related_name='outcomes',
    )
    market = models.CharField('Рынок', max_length=8, choices=Market.choices)
    selection = models.CharField('Исход', max_length=8, choices=Selection.choices)
    line = models.DecimalField(
        'Линия',
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Значение форы или тотала. Пусто для основных исходов.',
    )
    coefficient = models.DecimalField('Коэффициент', max_digits=5, decimal_places=2)

    @property
    def match(self):
        return self.offer.match

    @property
    def display_label(self):
        if self.market == self.Market.HANDICAP:
            return f'{self.get_selection_display()} ({format_handicap_value(self.line)})'
        if self.market in (self.Market.TOTAL, self.Market.INDIVIDUAL_TOTAL):
            return f'{self.get_selection_display()} ({format_total_value(self.line)})'
        return self.get_selection_display()

    def settle(self, match) -> bool | None:
        """Settle the outcome against a played match.

        Returns True (win), False (loss) or None (void/push: unsupported
        result such as mutual tech defeat, or total exactly on the line).
        """
        if not match.is_played:
            return None
        result_value = match.result.value if getattr(match, 'result', None) else None
        if result_value not in RESULT_SELECTIONS_BY_MATCH_RESULT:
            return None

        if self.market == self.Market.RESULT:
            return self.selection in RESULT_SELECTIONS_BY_MATCH_RESULT[result_value]

        if self.market == self.Market.HANDICAP:
            home_score = Decimal(match.score_home)
            away_score = Decimal(match.score_guest)
            if self.selection == self.Selection.HOME_HANDICAP:
                return home_score + self.line > away_score
            return away_score + self.line > home_score

        if self.market == self.Market.TOTAL:
            total = Decimal(match.score_home + match.score_guest)
            if total == self.line:
                return None
            return total > self.line if self.selection == self.Selection.OVER else total < self.line

        if self.market == self.Market.INDIVIDUAL_TOTAL:
            if self.selection in (self.Selection.HOME_OVER, self.Selection.HOME_UNDER):
                team_score = Decimal(match.score_home)
            else:
                team_score = Decimal(match.score_guest)
            if team_score == self.line:
                return None
            if self.selection in (self.Selection.HOME_OVER, self.Selection.AWAY_OVER):
                return team_score > self.line
            return team_score < self.line

        return None

    def clean(self):
        allowed = self.SELECTIONS_BY_MARKET.get(self.market, set())
        if self.selection not in allowed:
            raise ValidationError({'selection': f'Исход {self.selection} не относится к рынку {self.market}'})
        if self.market == self.Market.RESULT and self.line is not None:
            raise ValidationError({'line': 'Линия должна быть пустой для основных исходов'})
        if self.market in (self.Market.HANDICAP, self.Market.TOTAL, self.Market.INDIVIDUAL_TOTAL) and self.line is None:
            raise ValidationError({'line': 'Линия обязательна для фор и тоталов'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.offer.match}: {self.display_label} ×{self.coefficient}'

    class Meta:
        verbose_name = 'Исход для прогноза'
        verbose_name_plural = 'Исходы для прогнозов'
        constraints = [
            # Partial indexes: plain NULLS NOT DISTINCT needs Postgres 15+,
            # these two are enforceable everywhere.
            models.UniqueConstraint(
                fields=['offer', 'market', 'selection'],
                condition=Q(line__isnull=True),
                name='unique_outcome_per_offer_no_line',
            ),
            models.UniqueConstraint(
                fields=['offer', 'market', 'selection', 'line'],
                condition=Q(line__isnull=False),
                name='unique_outcome_per_offer_with_line',
            ),
            models.CheckConstraint(
                condition=(
                    Q(market='RESULT', selection__in=['HW', 'HWD', 'D', 'AWD', 'AW'])
                    | Q(market='HANDICAP', selection__in=['F1', 'F2'])
                    | Q(market='TOTAL', selection__in=['OVER', 'UNDER'])
                    | Q(market='ITOTAL', selection__in=['HT_OVER', 'HT_UNDER', 'AT_OVER', 'AT_UNDER'])
                ),
                name='outcome_selection_matches_market',
            ),
            models.CheckConstraint(
                condition=(
                    Q(market='RESULT', line__isnull=True)
                    | Q(market__in=['HANDICAP', 'TOTAL', 'ITOTAL'], line__isnull=False)
                ),
                name='outcome_line_required_by_market',
            ),
        ]


# Maps a MatchResult value to the set of RESULT selections it satisfies.
# Shared by MatchPredictionOutcome.settle() and points_service (single source).
RESULT_SELECTIONS_BY_MATCH_RESULT = {
    MatchResult.HOME_WIN: {'HW', 'HWD'},
    MatchResult.HOME_DEF_WIN: {'HW', 'HWD'},
    MatchResult.AWAY_WIN: {'AW', 'AWD'},
    MatchResult.AWAY_DEF_WIN: {'AW', 'AWD'},
    MatchResult.DRAW: {'D', 'HWD', 'AWD'},
}


class _MarketManager(models.Manager):
    """Base manager for proxy models: filters the shared table by market."""

    market = None

    def get_queryset(self):
        return super().get_queryset().filter(market=self.market)


class ResultOutcomeManager(_MarketManager):
    market = MatchPredictionOutcome.Market.RESULT


class HandicapOutcomeManager(_MarketManager):
    market = MatchPredictionOutcome.Market.HANDICAP


class TotalOutcomeManager(_MarketManager):
    market = MatchPredictionOutcome.Market.TOTAL


class IndividualTotalOutcomeManager(_MarketManager):
    market = MatchPredictionOutcome.Market.INDIVIDUAL_TOTAL


class ResultOutcome(MatchPredictionOutcome):
    """Proxy for administering RESULT outcomes (separate inline, own form)."""

    objects = ResultOutcomeManager()

    class Meta:
        proxy = True
        verbose_name = 'Исход (основной)'
        verbose_name_plural = 'Основные исходы'


class HandicapOutcome(MatchPredictionOutcome):
    """Proxy for administering HANDICAP outcomes (separate inline, own form)."""

    objects = HandicapOutcomeManager()

    class Meta:
        proxy = True
        verbose_name = 'Фора'
        verbose_name_plural = 'Форы (унифицированные)'


class TotalOutcome(MatchPredictionOutcome):
    """Proxy for administering TOTAL outcomes (separate inline, own form)."""

    objects = TotalOutcomeManager()

    class Meta:
        proxy = True
        verbose_name = 'Тотал'
        verbose_name_plural = 'Тоталы'


class IndividualTotalOutcome(MatchPredictionOutcome):
    """Proxy for administering INDIVIDUAL_TOTAL outcomes (separate inline, own form)."""

    objects = IndividualTotalOutcomeManager()

    class Meta:
        proxy = True
        verbose_name = 'Инд. тотал'
        verbose_name_plural = 'Индивидуальные тоталы'


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
