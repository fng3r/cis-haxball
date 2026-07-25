from collections import defaultdict
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models, transaction
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone

from colorfield.fields import ColorField
from model_utils import FieldTracker
from polymorphic.models import PolymorphicModel
from smart_selects.db_fields import ChainedForeignKey

from core.models import NewComment


class TeamIsNotMatchParticipantError(Exception):
    def __init__(self, team, match):
        message = f'Team {team} is not a participant of the match {match}'
        super().__init__(message)


class FreeAgent(models.Model):
    TOP_FORWARD = 'Верхний нападающий'
    BOT_FORWARD = 'Нижний нападающий'
    FORWARD = 'Нападающий'
    DEF_MIDDLE = 'Опорник'
    GOALKEEPER = 'Вратарь'
    BACK = 'Задняя линия'
    GK_FWD = 'Нападающий/вратарь'
    DM_FWD = 'Нападающий/опорник'
    ANY = 'Любая'
    POSITION = (
        (TOP_FORWARD, 'Верхний нападающий'),
        (BOT_FORWARD, 'Нижний нападающий'),
        (FORWARD, 'Нападающий'),
        (DEF_MIDDLE, 'Опорник'),
        (GOALKEEPER, 'Вратарь'),
        (BACK, 'Задняя линия'),
        (DM_FWD, 'Нападающий/Опорник'),
        (GK_FWD, 'Нападающий/Вратарь'),
        (ANY, 'Любая'),
    )

    player = models.OneToOneField(User, verbose_name='Игрок', on_delete=models.CASCADE, related_name='user_free_agent')
    description = models.TextField('Комментарий к заявке', max_length=200, blank=True)
    position_main = models.CharField(max_length=40, choices=POSITION, default=ANY)
    created = models.DateTimeField('Оставлена', default=timezone.now)
    deleted = models.DateTimeField('Снята', auto_now_add=True)
    is_active = models.BooleanField('Активно', default=True)

    def __str__(self):
        return f'CA {self.player.username}'

    class Meta:
        verbose_name = 'Свободный агент'
        verbose_name_plural = 'Свободные агенты'


class Season(models.Model):
    class Type(models.TextChoices):
        RUSSIAN_CHAMPIONSHIP = 'russian_championship', 'Чемпионат России'
        CHAMPIONS_LEAGUE = 'champions_league', 'Лига Чемпионов'
        FINAL_TOURNAMENT = 'final_tournament', 'Итоговый турнир'

    title = models.CharField('Название Розыгрыша', max_length=128)
    short_title = models.CharField('Короткое название', max_length=15, null=True, blank=True)
    number = models.SmallIntegerField('Номер сезона')
    type = models.CharField('Тип сезона', max_length=32, choices=Type.choices)
    is_active = models.BooleanField('Текущий')
    created = models.DateTimeField('Создана', auto_now_add=True)
    bound_season = models.ForeignKey(
        'self', verbose_name='Связанный сезон', null=True, blank=True, on_delete=models.SET_NULL
    )

    @property
    def is_primary(self):
        return self.type == self.Type.RUSSIAN_CHAMPIONSHIP

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-number']
        verbose_name = 'Сезон'
        verbose_name_plural = 'Сезоны'


class Team(models.Model):
    title = models.CharField('Название', max_length=128)
    slug = models.SlugField(max_length=250)
    date_found = models.DateField('Дата основания', default=timezone.now)
    short_title = models.CharField('Сокращение', help_text='До 5 символов', max_length=5)
    logo = models.ImageField('Логотип', upload_to='team_logos/', default='team_logos/default.png')
    owner = models.ForeignKey(
        User, verbose_name='Владелец', null=True, on_delete=models.SET_NULL, related_name='owned_teams'
    )
    captain = models.OneToOneField(
        'Player', verbose_name='Капитан', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    captain_assistant = models.OneToOneField(
        'Player', verbose_name='Ассистент капитана', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    office_link = models.URLField('Офис', blank=True)
    roster_slots = models.PositiveSmallIntegerField('Количество слотов', null=False, default=9)
    color_1 = ColorField(default='#FFFFFF', verbose_name='Цвет 1')
    color_2 = ColorField(default='#FFFFFF', verbose_name='Цвет 2')
    color_table = ColorField(default='#FFFFFF', verbose_name='Цвет Таблички')

    def get_absolute_url(self):
        return reverse('tournament:team_detail', args=[self.slug])

    def get_active_leagues(self):
        return self.leagues.filter(championship__is_active=True)

    def get_postponements(self, league):
        return (
            self.postponements.filter(cancelled_at__isnull=True, match__league=league)
            .select_related('match__team_home', 'match__team_guest', 'match__numb_tour')
            .order_by('taken_at')
        )

    @staticmethod
    @receiver(post_save, sender='tournament.PlayerTransfer')
    def clean_executives_if_needed(sender, instance, created, **kwargs):
        transfer = instance
        player = transfer.trans_player
        team = transfer.from_team
        if team is not None:
            if player == team.captain:
                team.captain = None
                team.save(update_fields=['captain'])
            if player == team.captain_assistant:
                team.captain_assistant = None
                team.save(update_fields=['captain_assistant'])

    def __str__(self):
        return f'{self.title}'

    class Meta:
        verbose_name = 'Команда'
        verbose_name_plural = 'Команды'


class League(models.Model):
    class Type(models.TextChoices):
        PREMIER_LEAGUE = 'premier_league', 'Высшая лига'
        FIRST_LEAGUE = 'first_league', 'Первая лига'
        SECOND_LEAGUE = 'second_league', 'Вторая лига'
        RUSSIAN_CUP = 'russian_cup', 'Кубок России'
        PREMIER_LEAGUE_CUP = 'premier_league_cup', 'Кубок Высшей лиги'
        FIRST_LEAGUE_CUP = 'first_league_cup', 'Кубок Первой лиги'
        SECOND_LEAGUE_CUP = 'second_league_cup', 'Кубок Второй лиги'
        LEAGUE_CUP = 'league_cup', 'Кубок лиги'
        CHAMPIONS_LEAGUE = 'champions_league', 'Лига Чемпионов'
        FINALS = 'finals', 'Итоговый турнир'

    championship = models.ForeignKey(
        Season,
        verbose_name='Сезон',
        related_name='tournaments_in_season',
        null=True,
        on_delete=models.CASCADE,
    )
    type = models.CharField('Тип турнира', max_length=32, choices=Type.choices)
    title = models.CharField('Название турнира', max_length=128)
    logo = models.ImageField('Логотип турнира', upload_to='tournament_logos/', null=True, blank=True)
    priority = models.SmallIntegerField('Приоритет турнира', help_text='1-высшая, 2-пердив, 3-втордив', blank=True)
    slug = models.SlugField(max_length=250)
    created = models.DateTimeField('Создана', auto_now_add=True)
    teams = models.ManyToManyField(
        Team,
        related_name='leagues',
        related_query_name='leagues',
        verbose_name='Команды в турнире',
        blank=True,
    )
    comments = GenericRelation(NewComment, related_query_name='league_comments')
    commentable = models.BooleanField('Комментируемый турнир', default=True)

    def __str__(self):
        return f'{self.title}, {self.championship}'

    def get_postponement_slots(self):
        return self.postponement_slots

    def get_absolute_url(self):
        return reverse('tournament:league', args=[self.slug])

    def is_multistage_league(self):
        return self.stages.count() > 1

    class Meta:
        ordering = ['championship', '-created']
        verbose_name = 'Турнир'
        verbose_name_plural = 'Турниры'


class TournamentWinner(models.Model):
    season = models.ForeignKey(Season, verbose_name='Сезон', related_name='winners', on_delete=models.CASCADE)
    league = ChainedForeignKey(
        League,
        verbose_name='Турнир',
        chained_field='season',
        chained_model_field='championship',
        related_name='winners',
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )
    winner = ChainedForeignKey(
        Team,
        verbose_name='Победитель',
        chained_field='league',
        chained_model_field='leagues',
        related_name='winners',
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )

    def __str__(self):
        return f'{self.winner.title} - {self.league}'

    class Meta:
        verbose_name = 'Победитель турнира'
        verbose_name_plural = 'Победители турниров'
        ordering = ['season', 'league']
        unique_together = [('season', 'league')]


class Nation(models.Model):
    country = models.CharField(
        'Страна',
        max_length=100,
    )
    flag = models.ImageField('Флаг', upload_to='country_flag/')

    def __str__(self):
        return self.country

    class Meta:
        ordering = ('country',)
        verbose_name = 'Страна'
        verbose_name_plural = 'Страны'


class TournamentStage(PolymorphicModel):
    class StageType(models.TextChoices):
        REGULAR = 'REG', 'Регулярка'
        GROUPS = 'GROUPS', 'Групповой этап'
        PLAYOFF = 'PO', 'Плей-офф'

    type = models.CharField('Тип', max_length=10, choices=StageType.choices, null=False, blank=True)
    name = models.CharField('Название (опционально)', max_length=50, null=True, blank=True)
    league = models.ForeignKey(League, verbose_name='Турнир', related_name='stages', on_delete=models.CASCADE)
    teams = models.ManyToManyField(Team, verbose_name='Команды', related_name='stages', blank=True)
    order = models.PositiveSmallIntegerField('Порядковый номер этапа')
    postponable = models.BooleanField('Можно ли переносить матчи этапа', default=False, blank=True)
    use_buchholz = models.BooleanField('Использовать коэффициент Бухгольца при равенстве очков', default=False)

    @property
    def stage_name(self):
        return self.name or self.get_type_display()

    @property
    def is_playoff(self):
        return self.type == self.StageType.PLAYOFF

    @property
    def is_regular(self):
        return self.type == self.StageType.REGULAR

    @property
    def is_group_stage(self):
        return self.type == self.StageType.GROUPS

    def save(self, *args, **kwargs):
        if not self.pk and not self.type:
            self.type = self._type

        if not self.pk:
            self.postponable = self._postponable

        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.league.title} – {self.stage_name}'

    class Meta:
        verbose_name = 'Этап турнира'
        verbose_name_plural = 'Этапы турниров'
        ordering = ['league', 'order']


class RegularStage(TournamentStage):
    _type = TournamentStage.StageType.REGULAR
    _postponable = True

    awarded_count = models.PositiveSmallIntegerField(
        'Кол-во команд, награждаемых медалями',
        choices=[(i, i) for i in range(0, 4)],
        default=3,
    )
    promoted_count = models.PositiveSmallIntegerField(
        'Кол-во команд, поднимающихся в лигу выше',
        choices=[(i, i) for i in range(0, 17)],
        default=4,
        null=False,
    )
    relegated_count = models.PositiveSmallIntegerField(
        'Кол-во команд, вылетающих в лигу ниже',
        choices=[(i, i) for i in range(0, 17)],
        default=2,
    )
    is_round_robin = models.BooleanField(
        'Используется круговая система',
        default=True,
    )
    round_robin_rounds = models.PositiveSmallIntegerField(
        'Количество кругов',
        default=2,
        help_text='Количество раз, которое каждая команда играет с каждой',
    )

    class Meta:
        verbose_name = 'Регулярка'
        verbose_name_plural = 'Регулярки'


class GroupStage(TournamentStage):
    _type = TournamentStage.StageType.GROUPS
    _postponable = True

    promoted_count = models.PositiveSmallIntegerField(
        'Кол-во команд, проходящих в следующий этап',
        choices=[(i, i) for i in range(1, 11)],
        default=2,
    )
    promoted_extra_count = models.PositiveSmallIntegerField(
        'Кол-во команд, дополнительно проходящих в следующий этап',
        choices=[(i, i) for i in range(0, 11)],
        default=0,
    )

    class Meta:
        verbose_name = 'Групповой этап'
        verbose_name_plural = 'Групповые этапы'


class Group(models.Model):
    stage = models.ForeignKey(
        GroupStage, verbose_name='Групповой этап', related_name='groups', on_delete=models.CASCADE
    )
    teams = models.ManyToManyField(Team, verbose_name='Команды', related_name='groups', blank=True)

    name = models.CharField('Название группы', max_length=50)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Группа'
        verbose_name_plural = 'Группы'


class PlayOffStage(TournamentStage):
    _type = TournamentStage.StageType.PLAYOFF
    _postponable = False

    class PlayOffType(models.TextChoices):
        SE = 'SE', 'Single-elimination'
        DE = 'DE', 'Double-elimination'

    class Bracket(models.IntegerChoices):
        LOWER = 0, 'Нижняя сетка'
        UPPER = 1, 'Верхняя сетка'

    class WinnerDeterminator(models.TextChoices):
        GOALS = 'GOALS', 'По сумме голов'
        MATCHES = 'MATCHES', 'По сумме выигранных матчей'

    playoff_type = models.CharField('Формат', choices=PlayOffType.choices, default=PlayOffType.SE, max_length=10)
    has_match_for_third_place = models.BooleanField('Есть матч за 3-е место', default=False)
    show_bracket_slot_labels = models.BooleanField('Показывать метки для слотов', default=False)
    winner_determinator = models.CharField(
        'Как определяется победитель',
        choices=WinnerDeterminator.choices,
        default=WinnerDeterminator.GOALS,
        max_length=15,
    )

    def is_single_elimination(self):
        return self.playoff_type == PlayOffStage.PlayOffType.SE

    def is_double_elimination(self):
        return self.playoff_type == PlayOffStage.PlayOffType.DE

    class Meta:
        verbose_name = 'Плей-офф'
        verbose_name_plural = 'Плей-офф'


class PlayoffBracketSlotStub(models.Model):
    playoff_stage = models.ForeignKey(
        PlayOffStage, verbose_name='Стадия ПО', null=False, blank=False, on_delete=models.CASCADE
    )
    tour = ChainedForeignKey(
        'TourNumber',
        verbose_name='Раунд',
        chained_field='playoff_stage',
        chained_model_field='stage',
        related_name='stubs',
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )
    slot = models.PositiveSmallIntegerField('Номер слота в раунде')
    top_team = ChainedForeignKey(
        Team,
        verbose_name='Команда в верхней строчке слота',
        chained_field='playoff_stage',
        chained_model_field='stages',
        related_name='stubs_top',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    top_team_placeholder = models.CharField(
        'Плейсхолдер для команды в верхней строчке слота', max_length=20, null=True, blank=True
    )
    bottom_team = ChainedForeignKey(
        Team,
        verbose_name='Команда в нижней строчке слота',
        chained_field='playoff_stage',
        chained_model_field='stages',
        related_name='stubs_bottom',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    bottom_team_placeholder = models.CharField(
        'Плейсхолдер для команды в нижней строчке слота', max_length=20, null=True, blank=True
    )

    def __str__(self):
        bracket_prefix = f'{self.tour.get_bracket_display()}, ' if self.tour.bracket is not None else ''
        return f'{bracket_prefix}{self.tour.number} тур - слот {self.slot}'

    class Meta:
        ordering = ('tour', 'slot')
        verbose_name = 'Заглушка для слота сетки плей-офф'
        verbose_name_plural = 'Заглушки для слотов сетки плей-офф'


class TeamPenaltyPoints(models.Model):
    stage = models.ForeignKey(
        TournamentStage,
        verbose_name='Этап турнира',
        related_name='penalties',
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )
    team = ChainedForeignKey(
        Team,
        verbose_name='Команда',
        chained_field='stage',
        chained_model_field='stages',
        related_name='penalties',
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )
    penalty_points = models.PositiveSmallIntegerField('Штрафные очки')

    class Meta:
        verbose_name = 'Штраф по очкам'
        verbose_name_plural = 'Штрафы по очкам'
        unique_together = ('stage', 'team')

    def __str__(self):
        return f'{self.team} (- {self.penalty_points} очк.)'


class Player(models.Model):
    class Position(models.TextChoices):
        ST = 'ST', 'Нападающий'
        DM = 'DM', 'Опорник'
        GK = 'GK', 'Вратарь'

    name = models.OneToOneField(
        User, verbose_name='Пользователь', null=True, blank=True, on_delete=models.SET_NULL, related_name='user_player'
    )

    nickname = models.CharField(
        'Никнейм игрока',
        max_length=150,
    )

    team = models.ForeignKey(
        Team, verbose_name='Команда', related_name='players_in_team', blank=True, null=True, on_delete=models.SET_NULL
    )

    player_nation = models.ForeignKey(
        Nation, verbose_name='Национальность', related_name='country_players', null=True, on_delete=models.SET_NULL
    )

    positions = ArrayField(
        models.CharField('Позиция', max_length=2, choices=Position.choices),
        null=True,
        blank=True,
        default=list,
        verbose_name='Позиции',
    )

    @staticmethod
    @receiver(post_save, sender=User)
    def create_comment_history_item(sender, instance, created, **kwargs):
        if not created:
            player = Player.objects.filter(name=instance).first()
            if not player:
                return

            if player.nickname != instance.username:
                player.nickname = instance.username
                player.save()

    def __str__(self):
        return f'{self.nickname}'

    class Meta:
        verbose_name = 'Игрок'
        verbose_name_plural = 'Игроки'
        ordering = ('nickname',)


class TourNumber(models.Model):
    number = models.SmallIntegerField('Номер тура')
    name = models.CharField('Название тура/раунда (опционально)', max_length=30, null=True, blank=True)
    date_from = models.DateField('Дата начала тура', default=date.today, blank=True, null=True)
    date_to = models.DateField('Дата окончания тура', default=date.today, blank=True, null=True)
    league = models.ForeignKey(League, verbose_name='Турнир', related_name='tours', on_delete=models.CASCADE)
    stage = ChainedForeignKey(
        TournamentStage,
        chained_field='league',
        chained_model_field='league',
        related_name='tours',
        verbose_name='Этап',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    bracket = models.PositiveSmallIntegerField('Сетка', choices=PlayOffStage.Bracket.choices, null=True, blank=True)

    @property
    def is_actual(self):
        today = timezone.localdate()
        return today >= self.date_from and any(not match.is_played for match in self.tour_matches.all())

    @property
    def is_started(self):
        return timezone.now().date() >= self.date_from

    @property
    def is_ended(self):
        return timezone.now().date() > self.date_to

    def __str__(self):
        bracket_postfix = ''
        if (
            type(self.stage) is PlayOffStage
            and self.stage.playoff_type == PlayOffStage.PlayOffType.DE
            and self.bracket is not None
        ):
            bracket_postfix = f', {self.get_bracket_display()}'

        if self.league.is_multistage_league():
            return f'{self.number} тур ({self.league.title} – {self.stage.stage_name}{bracket_postfix})'

        return f'{self.number} тур ({self.league.title}{bracket_postfix})'

    class Meta:
        verbose_name = 'Тур'
        verbose_name_plural = 'Туры'
        ordering = ['league', 'stage__order', 'number', 'date_from']
        indexes = [
            models.Index(fields=['league', 'number']),
        ]


class Match(models.Model):
    league = models.ForeignKey(
        League,
        verbose_name='Турнир',
        related_name='matches_in_league',
        related_query_name='matches_in_league',
        on_delete=models.CASCADE,
    )
    stage = ChainedForeignKey(
        TournamentStage,
        chained_field='league',
        chained_model_field='league',
        verbose_name='Этап',
        related_name='matches',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    group = ChainedForeignKey(
        Group,
        chained_field='stage',
        chained_model_field='stage',
        verbose_name='Группа',
        related_name='matches',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    numb_tour = ChainedForeignKey(
        TourNumber,
        chained_field='stage',
        chained_model_field='stage',
        verbose_name='Тур',
        related_name='tour_matches',
        on_delete=models.CASCADE,
        null=True,
    )
    bracket_slot = models.PositiveSmallIntegerField(
        'Слот сетки',
        default=0,
        null=False,
        help_text='Номер слота в сетке ПО. Слоты нумеруются сверху вниз, в каждом раунде нумерация начинется с единицы',
    )

    match_date = models.DateField('Дата матча', default=None, blank=True, null=True)
    duration = models.DurationField('Длительность матча', default=timedelta(minutes=16))
    replays = ArrayField(models.URLField(), verbose_name='Ссылки на реплеи', default=list, blank=True)
    inspector = models.ForeignKey(
        User,
        verbose_name='Проверил',
        limit_choices_to={'is_staff': True},
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    updated = models.DateTimeField('Обновлено', auto_now=True)
    team_home = ChainedForeignKey(
        Team,
        chained_field='stage',
        chained_model_field='stages',
        on_delete=models.CASCADE,
        related_name='home_matches',
        verbose_name='Хозяева',
    )
    team_guest = ChainedForeignKey(
        Team,
        chained_field='stage',
        chained_model_field='stages',
        on_delete=models.CASCADE,
        related_name='guest_matches',
        verbose_name='Гости',
    )

    score_home = models.SmallIntegerField('Забито хозяевами', default=0)
    score_guest = models.SmallIntegerField('Забито гостями', default=0)

    team_home_start = models.ManyToManyField(
        Player, related_name='home_matches', verbose_name='Состав хозяев', blank=True
    )
    team_guest_start = models.ManyToManyField(
        Player, related_name='guest_matches', verbose_name='Состав гостей', blank=True
    )
    match_participants = models.ManyToManyField(Player, verbose_name='Участники матча', through='PlayerMatchStatistics')

    is_played = models.BooleanField('Сыгран', default=False)

    comment = models.TextField('Комментарий к матчу', max_length=1024, blank=True, null=True)

    comments = GenericRelation(NewComment, related_query_name='match_comments')
    commentable = models.BooleanField('Комментируемый матч', default=True)

    tracker = FieldTracker()

    @property
    def can_be_postponed(self):
        if self.is_played:
            return False

        if self.stage and not self.stage.postponable:
            return False

        start_date = self.numb_tour.date_from
        end_date = self.numb_tour.date_to
        if self.is_postponed:
            last_postponement = self.get_last_postponement()
            start_date = last_postponement.starts_at
            end_date = last_postponement.ends_at

        start_datetime = timezone.datetime.combine(start_date, timezone.datetime.min.time())
        end_datetime = timezone.datetime.combine(end_date, timezone.datetime.min.time()) + timezone.timedelta(days=1)

        return start_datetime.timestamp() <= timezone.now().timestamp() <= end_datetime.timestamp()

    @property
    def is_postponed(self):
        return self.postponements.filter(cancelled_at__isnull=True).count() > 0

    def get_last_postponement(self):
        return self.postponements.filter(cancelled_at__isnull=True).order_by('-ends_at').first()

    @property
    def winner(self) -> Team | None:
        if self.result:
            return self.result.winner

        return None

    def is_win(self, team):
        return team == self.winner

    def is_loss(self, team):
        return not self.is_draw() and team != self.winner

    def is_draw(self):
        return self.result.value == MatchResult.DRAW

    def is_tech_defeat(self):
        return (
            self.result.value == MatchResult.HOME_DEF_WIN
            or self.result.value == MatchResult.AWAY_DEF_WIN
            or self.result.value == MatchResult.MUTUAL_TECH_DEFEAT
        )

    def scored_by(self, team):
        if team == self.team_home:
            return self.score_home
        if team == self.team_guest:
            return self.score_guest

        raise TeamIsNotMatchParticipantError(team, self)

    def conceded_by(self, team):
        if team == self.team_home:
            return self.score_guest
        if team == self.team_guest:
            return self.score_home

        raise TeamIsNotMatchParticipantError(team, self)

    def opponent_of(self, team):
        team_id = getattr(team, 'pk', team)
        if team_id == self.team_home_id:
            return self.team_guest
        if team_id == self.team_guest_id:
            return self.team_home

        raise TeamIsNotMatchParticipantError(team, self)

    def get_absolute_url(self):
        return reverse('tournament:match_detail', args=[self.id])

    def __str__(self):
        return f'Матч {self.team_home.short_title} - {self.team_guest.short_title}. {self.numb_tour.number} тур'

    class Meta:
        verbose_name = 'Матч'
        verbose_name_plural = 'Матчи'
        ordering = ['league', 'stage', 'numb_tour', 'id']
        indexes = [
            models.Index(fields=['league', 'numb_tour']),
        ]


class MatchResult(models.Model):
    HOME_WIN = 'HW'
    DRAW = 'D'
    AWAY_WIN = 'AW'
    HOME_DEF_WIN = 'HDW'
    AWAY_DEF_WIN = 'ADW'
    MUTUAL_TECH_DEFEAT = 'MTD'

    results = [
        (HOME_WIN, 'Победа хозяев'),
        (DRAW, 'Ничья'),
        (AWAY_WIN, 'Победа гостей'),
        (HOME_DEF_WIN, 'ТП гостям'),
        (AWAY_DEF_WIN, 'ТП хозяевам'),
        (MUTUAL_TECH_DEFEAT, 'Обоюдное ТП'),
    ]

    match = models.OneToOneField(
        Match, verbose_name='Матч', related_name='result', primary_key=True, on_delete=models.CASCADE
    )
    value = models.CharField(verbose_name='Результат', choices=results, null=False, blank=False)
    set_manually = models.BooleanField(
        'Указать вручную',
        default=False,
        help_text='По умолчанию результат определяется автоматически на основе '
        + 'итогового счета. Использовать только в том случае, если нужно '
        + 'вручную разметить результат (ТП/обоюдное ТП)',
    )
    winner = models.ForeignKey(
        Team, verbose_name='Победитель', related_name='won_matches', on_delete=models.CASCADE, null=True, blank=True
    )

    def save(self, *args, **kwargs):
        if not self.set_manually:  # determine result automatically if it is not specified explicitly
            self.value = self.get_result_from_scores()

        if self.value == MatchResult.HOME_WIN or self.value == MatchResult.HOME_DEF_WIN:
            self.winner = self.match.team_home
        elif self.value == MatchResult.AWAY_WIN or self.value == MatchResult.AWAY_DEF_WIN:
            self.winner = self.match.team_guest
        else:
            self.winner = None
        super(MatchResult, self).save(*args, **kwargs)

    @staticmethod
    @receiver(post_save, sender=Match)
    def create_or_update_result(sender, instance, created, **kwargs):
        if not instance.is_played:
            return

        result = MatchResult.objects.filter(match=instance).first()
        if not result:
            result = MatchResult(match=instance)
        result.save()

    def get_result_from_scores(self):
        if self.match.score_home == self.match.score_guest:
            return MatchResult.DRAW
        if self.match.score_home > self.match.score_guest:
            return MatchResult.HOME_WIN
        return MatchResult.AWAY_WIN

    def __str__(self):
        return self.get_value_display()

    class Meta:
        ordering = ['value']
        verbose_name = 'Результат матча'
        verbose_name_plural = 'Результат матча'


class MatchReplayStatsStatus(models.Model):
    """Fetch status for replay-based stats (one per Match)."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидание'
        SUCCESS = 'success', 'Успешно'
        PARTIAL = 'partial', 'Частично'
        FAILED = 'failed', 'Ошибка'

    match = models.OneToOneField(
        Match,
        verbose_name='Матч',
        related_name='replay_stats_status',
        on_delete=models.CASCADE,
        primary_key=True,
    )
    status = models.CharField(
        'Статус',
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    error_message = models.TextField('Сообщение об ошибке', blank=True)
    fetched_at = models.DateTimeField('Время обновления', null=True, blank=True)

    class Meta:
        verbose_name = 'Статус загрузки статистики реплея'
        verbose_name_plural = 'Статусы загрузки статистики реплеев'


class MatchReplay(models.Model):
    """
    One per replay URL in a match. Stores fetch metadata and raw analyzer response.
    """

    class ReplayStatus(models.TextChoices):
        PENDING = 'pending', 'Ожидание загрузки'
        AWAITING_STATS = 'awaiting_stats', 'Ожидание статистики'
        READY = 'ready', 'Готово'
        FAILED = 'failed', 'Ошибка'

    match = models.ForeignKey(
        Match,
        verbose_name='Матч',
        related_name='match_replays',
        on_delete=models.CASCADE,
    )
    replay_url = models.URLField('URL реплея', max_length=512)
    analyzer_replay_id = models.CharField(
        'ID реплея в анализаторе',
        max_length=32,
        blank=True,
        help_text='ID, возвращённый Haxball Analyzer после загрузки',
    )
    raw_stats_json = models.JSONField(
        'Сырой ответ API (stats)',
        default=list,
        blank=True,
        help_text='Массив частей матча из ответа /stats/<id>.json',
    )
    status = models.CharField(
        'Статус',
        max_length=24,
        choices=ReplayStatus.choices,
        default=ReplayStatus.PENDING,
    )
    error_message = models.TextField('Сообщение об ошибке', blank=True)
    fetched_at = models.DateTimeField('Время загрузки', null=True, blank=True)

    class Meta:
        verbose_name = 'Реплей матча'
        verbose_name_plural = 'Реплеи матчей'
        ordering = ['match_id', 'replay_url']
        constraints = [
            models.UniqueConstraint(fields=['match', 'replay_url'], name='tournament_matchreplay_match_url_unique'),
        ]

    def __str__(self):
        return f'{self.replay_url}'


class MatchReplayStats(models.Model):
    """Stats for specific replay part."""

    class PartLabel(models.TextChoices):
        FIRST_HALF = '1H', '1 тайм'
        SECOND_HALF = '2H', '2 тайм'
        EXTRA_TIME = 'ET', 'Доп. время'

    match = models.ForeignKey(
        Match,
        verbose_name='Матч',
        related_name='replay_stats',
        on_delete=models.CASCADE,
    )
    match_replay = models.ForeignKey(
        MatchReplay,
        verbose_name='Реплей',
        related_name='parts',
        on_delete=models.CASCADE,
    )
    part_order = models.PositiveSmallIntegerField(
        'Порядок части',
        default=0,
        help_text='Глобальный порядок части в матче (среди всех реплеев)',
    )
    part_label = models.CharField(
        'Часть матча',
        max_length=2,
        choices=PartLabel.choices,
        default=PartLabel.FIRST_HALF,
    )
    red_is_home = models.BooleanField(
        'Красные = хозяева',
        default=True,
        help_text='True: красные в реплее = team_home. False: синие в реплее = team_home.',
    )

    # Scores and teams
    score_red = models.IntegerField('Голы красных', default=0)
    score_blue = models.IntegerField('Голы синих', default=0)

    # Match duration
    game_ticks = models.IntegerField('Тики игры', default=0)
    minutes = models.IntegerField('Минуты', default=0)

    # Possession and shots
    poss_red = models.IntegerField('Владение (красные)', default=0)
    poss_blue = models.IntegerField('Владение (синие)', default=0)
    shots_red = models.IntegerField('Удары (красные)', default=0)
    shots_blue = models.IntegerField('Удары (синие)', default=0)
    shots_off_target_red = models.IntegerField('Мимо (красные)', default=0)
    shots_off_target_blue = models.IntegerField('Мимо (синие)', default=0)
    shots_total_red = models.IntegerField('Всего ударов (красные)', default=0)
    shots_total_blue = models.IntegerField('Всего ударов (синие)', default=0)
    kicks_red = models.IntegerField('Удары по мячу красные', default=0)
    kicks_blue = models.IntegerField('Удары по мячу (синие)', default=0)
    thirds_red = models.IntegerField('Тики в трети красных', default=0)
    thirds_mid = models.IntegerField('Тики в центре', default=0)
    thirds_blue = models.IntegerField('Тики в трети синих', default=0)

    # Stadium and mode
    stadium_name = models.CharField('Название стадиона', max_length=255, blank=True)

    # Team nicks (from API redTeam / blueTeam)
    red_team_nicks = ArrayField(
        models.CharField(max_length=150, blank=True),
        verbose_name='Ники красных',
        default=list,
        blank=True,
    )
    blue_team_nicks = ArrayField(
        models.CharField(max_length=150, blank=True),
        verbose_name='Ники синих',
        default=list,
        blank=True,
    )
    mvp_nick = models.CharField('MVP (ник)', max_length=150, blank=True)

    class Meta:
        verbose_name = 'Статистика матча (реплеи)'
        verbose_name_plural = 'Статистика матчей (реплеи)'
        ordering = ['part_order']

    def get_match_team_for_replay_side(self, replay_side: str):
        """Return match team (team_home or team_guest) for replay side 'red' or 'blue'."""
        if (replay_side or '').lower() == 'red':
            return self.match.team_home if self.red_is_home else self.match.team_guest
        return self.match.team_guest if self.red_is_home else self.match.team_home

    def home_guest(self, red_val, blue_val):
        """Return (home_value, guest_value) for display, from replay red/blue values."""
        return (red_val, blue_val) if self.red_is_home else (blue_val, red_val)

    def __str__(self):
        return (
            f'{self.match.team_home.short_title} - {self.match.team_guest.short_title}'
            + f' — {self.match.numb_tour} ({self.get_part_label_display()})'
        )


class MatchReplayStatsPlayer(models.Model):
    """Per-player stats for one part (one MatchReplayStats)."""

    class Position(models.TextChoices):
        GK = 'GK', 'GK'
        DM = 'DM', 'DM'
        AM = 'AM', 'AM'
        LW = 'LW', 'LW'
        RW = 'RW', 'RW'
        ST = 'ST', 'ST'

    replay_stats = models.ForeignKey(
        MatchReplayStats,
        verbose_name='Статистика части',
        related_name='players',
        on_delete=models.CASCADE,
    )
    player = models.ForeignKey(
        Player,
        verbose_name='Игрок',
        related_name='replay_stats_entries',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text='Сопоставлен по нику (красные=хозяева, синие=гости)',
    )
    nick = models.CharField('Ник в реплее', max_length=150)
    avatar = models.CharField('Аватар', max_length=2, null=True, blank=True)
    team = models.ForeignKey(
        Team,
        verbose_name='Команда',
        related_name='replay_stats_player_entries',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text='Хозяева (красные) или гости (синие) по реплею',
    )

    goals = models.IntegerField('Голы', default=0)
    assists = models.IntegerField('Голевые передачи', default=0)
    played_ticks = models.IntegerField('Сыграно тиков', default=0)
    position = models.CharField(
        'Позиция',
        max_length=2,
        choices=Position.choices,
        null=True,
        blank=True,
    )
    rating = models.FloatField('Рейтинг', null=True, blank=True)

    shots_total = models.IntegerField('Ударов всего', default=0)
    shots_on_target = models.IntegerField('Ударов в створ', default=0)
    shots_off_target = models.IntegerField('Ударов мимо', default=0)

    passes_completed = models.IntegerField('Передач выполнено', default=0)
    pass_attempts = models.IntegerField('Передач попыток', default=0)
    pass_completion_rate = models.FloatField('% передач', null=True, blank=True)

    touches = models.IntegerField('Касаний', default=0)
    saves = models.IntegerField('Сейвов', default=0)
    clearances = models.IntegerField('Отборов', default=0)
    interceptions = models.IntegerField('Перехватов', default=0)
    duel_wins = models.IntegerField('Дуэли выиграно', default=0)
    duel_losses = models.IntegerField('Дуэли проиграно', default=0)
    xg = models.FloatField('xG', null=True, blank=True)

    class Meta:
        verbose_name = 'Статистика игрока (реплеи)'
        verbose_name_plural = 'Статистика игроков (реплеи)'

    def __str__(self):
        return f'{self.nick}: {self.replay_stats}'


class GoalQuerySet(models.QuerySet):
    def regular(self):
        return self.filter(kind=Goal.Kind.REGULAR)

    def own_goals(self):
        return self.filter(kind=Goal.Kind.OWN_GOAL)

    def scored_by(self, player):
        return self.regular().filter(author=player)

    def committed_by(self, player):
        return self.own_goals().filter(own_goal_author=player)

    def credited_to(self, team):
        return self.filter(team=team)

    def committed_for(self, team):
        return self.own_goals().filter(own_goal_team=team)


class Goal(models.Model):
    class Kind(models.TextChoices):
        REGULAR = 'REG', 'Гол'
        OWN_GOAL = 'OG', 'Автогол'

    match = models.ForeignKey(
        Match, verbose_name='Матч', related_name='match_goal', null=True, blank=True, on_delete=models.CASCADE
    )

    kind = models.CharField('Тип гола', max_length=3, choices=Kind.choices, default=Kind.REGULAR, db_index=True)

    team = models.ForeignKey(
        Team, verbose_name='Команда забила', related_name='goals', null=True, on_delete=models.SET_NULL
    )

    author = ChainedForeignKey(
        Player,
        chained_field='team',
        chained_model_field='team',
        verbose_name='Автор гола',
        related_name='goals',
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    assistent = ChainedForeignKey(
        Player,
        chained_field='team',
        chained_model_field='team',
        verbose_name='Ассистент',
        related_name='assists',
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    time_min = models.PositiveSmallIntegerField('Минута')
    time_sec = models.PositiveSmallIntegerField(
        'Секунда',
        validators=[MaxValueValidator(59, message='Значение должно быть от 0 до 59')],
    )

    own_goal_team = models.ForeignKey(
        Team,
        verbose_name='Команда автора автогола',
        related_name='own_goals',
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )
    own_goal_author = ChainedForeignKey(
        Player,
        chained_field='own_goal_team',
        chained_model_field='team',
        verbose_name='Автор автогола',
        related_name='own_goals',
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    legacy_event = models.OneToOneField(
        'OtherEvents',
        verbose_name='Исходное событие автогола',
        related_name='migrated_goal',
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )

    objects = GoalQuerySet.as_manager()

    @classmethod
    def create_regular(cls, *, match, team, author, time_min, time_sec, assistent=None):
        goal = cls(
            match=match,
            kind=cls.Kind.REGULAR,
            team=team,
            author=author,
            assistent=assistent,
            time_min=time_min,
            time_sec=time_sec,
        )
        goal.save()
        return goal

    @classmethod
    def create_own_goal(cls, *, match, offending_team, author, time_min, time_sec):
        goal = cls(
            match=match,
            kind=cls.Kind.OWN_GOAL,
            own_goal_team=offending_team,
            own_goal_author=author,
            time_min=time_min,
            time_sec=time_sec,
        )
        goal.save()
        return goal

    def clean(self):
        super().clean()
        if self.kind == self.Kind.OWN_GOAL and self.match_id and self.own_goal_team_id:
            self.team = self.match.opponent_of(self.own_goal_team_id)

        errors = {}
        if self.match_id and self.team_id not in (self.match.team_home_id, self.match.team_guest_id):
            errors['team'] = 'Команда, которой засчитан гол, не участвует в матче'

        if self.kind == self.Kind.REGULAR:
            participants = (('author', self.author_id), ('assistent', self.assistent_id))
            participant_team_id = self.team_id
        else:
            participants = (('own_goal_author', self.own_goal_author_id),)
            participant_team_id = self.own_goal_team_id

        for field, player_id in participants:
            if not self.match_id or not participant_team_id or not player_id:
                continue
            has_match_team = PlayerMatchStatistics.objects.filter(
                match_id=self.match_id,
                player_id=player_id,
                team_id=participant_team_id,
            ).exists()
            has_any_match_team = PlayerMatchStatistics.objects.filter(
                match_id=self.match_id,
                player_id=player_id,
            ).exists()
            has_current_team = Player.objects.filter(pk=player_id, team_id=participant_team_id).exists()
            if not has_match_team and (has_any_match_team or not has_current_team):
                errors[field] = 'Игрок не относится к выбранной команде в этом матче'

        if errors:
            raise ValidationError(errors)

    def _normalize(self):
        if self.kind == self.Kind.OWN_GOAL:
            if not self.match_id or not self.own_goal_team_id:
                raise ValueError('An own goal requires match and own_goal_team')
            self.team = self.match.opponent_of(self.own_goal_team_id)
            self.author = None
            self.assistent = None
        else:
            self.own_goal_team = None
            self.own_goal_author = None

    @staticmethod
    def _apply_score_delta(match_id, team_id, delta):
        match = Match.objects.only('team_home_id', 'team_guest_id').get(pk=match_id)
        if team_id == match.team_home_id:
            Match.objects.filter(pk=match_id).update(score_home=models.F('score_home') + delta)
        elif team_id == match.team_guest_id:
            Match.objects.filter(pk=match_id).update(score_guest=models.F('score_guest') + delta)
        else:
            raise TeamIsNotMatchParticipantError(team_id, match)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            previous = None
            if self.pk:
                previous = Goal.objects.filter(pk=self.pk).values('match_id', 'team_id').first()

            self._normalize()
            self.full_clean()
            if kwargs.get('update_fields') is not None:
                kwargs['update_fields'] = set(kwargs['update_fields']) | {
                    'team',
                    'author',
                    'assistent',
                    'own_goal_team',
                    'own_goal_author',
                }
            super().save(*args, **kwargs)

            current = {'match_id': self.match_id, 'team_id': self.team_id}
            if previous != current:
                if previous and previous['match_id'] and previous['team_id']:
                    self._apply_score_delta(previous['match_id'], previous['team_id'], -1)
                if current['match_id'] and current['team_id']:
                    self._apply_score_delta(current['match_id'], current['team_id'], 1)

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            match_id = self.match_id
            team_id = self.team_id
            result = super().delete(*args, **kwargs)
            if match_id and team_id:
                self._apply_score_delta(match_id, team_id, -1)
            return result

    def __str__(self):
        if self.kind == self.Kind.OWN_GOAL:
            return f'🔴 {self.time_min:02d}:{self.time_sec:02d} {self.team} - {self.own_goal_author} (АГ)'
        assistant = f' ({self.assistent})' if self.assistent else ''
        return f'⚽ {self.time_min:02d}:{self.time_sec:02d} {self.team} - {self.author}{assistant}'

    class Meta:
        verbose_name = 'Гол'
        verbose_name_plural = 'Голы'
        ordering = ['time_min', 'time_sec']
        indexes = [
            models.Index(fields=['author', 'match']),
            models.Index(fields=['assistent', 'match']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        kind='REG',
                        author__isnull=False,
                        own_goal_team__isnull=True,
                        own_goal_author__isnull=True,
                    )
                    | models.Q(
                        kind='OG',
                        author__isnull=True,
                        assistent__isnull=True,
                        own_goal_team__isnull=False,
                        own_goal_author__isnull=False,
                    )
                ),
                name='goal_fields_match_kind',
            ),
        ]


class Substitution(models.Model):
    match = models.ForeignKey(
        Match, verbose_name='Матч', related_name='match_substitutions', null=True, on_delete=models.CASCADE
    )

    team = models.ForeignKey(
        Team, verbose_name='Замена в команде', related_name='substitutions', null=True, on_delete=models.SET_NULL
    )

    player_out = ChainedForeignKey(
        Player,
        chained_field='team',
        chained_model_field='team',
        verbose_name='Ушёл',
        related_name='replaced',
        null=True,
        on_delete=models.CASCADE,
    )
    player_in = ChainedForeignKey(
        Player,
        chained_field='team',
        chained_model_field='team',
        verbose_name='Вышел',
        related_name='join_game',
        null=True,
        on_delete=models.CASCADE,
    )
    time_min = models.PositiveSmallIntegerField('Минута')
    time_sec = models.PositiveSmallIntegerField(
        'Секунда',
        validators=[MaxValueValidator(59, message='Значение должно быть от 0 до 59')],
    )

    def __str__(self):
        return f'🔁 {self.time_min:02d}:{self.time_sec:02d} {self.team} ({self.player_out} -> {self.player_in})'

    class Meta:
        verbose_name = 'Замена'
        verbose_name_plural = 'Замены'


class PlayerMatchStatistics(models.Model):
    match = models.ForeignKey(Match, verbose_name='Матч', null=False, blank=False, on_delete=models.CASCADE)
    player = models.ForeignKey(
        Player, verbose_name='Игрок', related_name='played_matches', null=False, blank=False, on_delete=models.CASCADE
    )
    team = models.ForeignKey(
        Team, verbose_name='Команда', related_name='played_matches', null=False, blank=False, on_delete=models.CASCADE
    )
    league = models.ForeignKey(League, verbose_name='Турнир', null=False, blank=False, on_delete=models.CASCADE)

    @staticmethod
    @receiver(m2m_changed, sender=Match.team_home_start.through)
    def match_team_home_start_changed(sender, instance, action, **kwargs):
        if action in ('post_add', 'post_remove'):
            PlayerMatchStatistics.update_match_participants(instance)

    @staticmethod
    @receiver(m2m_changed, sender=Match.team_guest_start.through)
    def match_team_guest_start_changed(sender, instance, action, **kwargs):
        if action in ('post_add', 'post_remove'):
            PlayerMatchStatistics.update_match_participants(instance)

    @staticmethod
    @receiver([post_save, post_delete], sender=Substitution)
    def match_substitutions_changed(sender, instance, **kwargs):
        PlayerMatchStatistics.update_match_participants(instance.match)

    @staticmethod
    def update_match_participants(match):
        match.match_participants.clear()
        for player in match.team_home_start.all():
            match.match_participants.add(
                player, through_defaults={'match': match, 'team': match.team_home, 'league': match.league}
            )
        for player in match.team_guest_start.all():
            match.match_participants.add(
                player, through_defaults={'match': match, 'team': match.team_guest, 'league': match.league}
            )
        for substitution in match.match_substitutions.all():
            match.match_participants.add(
                substitution.player_in,
                through_defaults={'match': match, 'team': substitution.team, 'league': match.league},
            )

    class Meta:
        verbose_name = 'Статистика игрока в матче'
        verbose_name_plural = 'Статистика игроков в матчах'
        unique_together = ('match', 'player')
        indexes = [
            models.Index(fields=['player', 'league']),
            models.Index(fields=['league', 'player']),
        ]


class Disqualification(models.Model):
    match = models.ForeignKey(
        Match, verbose_name='Матч', related_name='disqualifications', null=False, on_delete=models.CASCADE
    )
    team = models.ForeignKey(
        Team, verbose_name='Команда', related_name='disqualifications', null=False, on_delete=models.CASCADE
    )
    player = ChainedForeignKey(
        Player,
        verbose_name='Игрок',
        chained_field='team',
        chained_model_field='team',
        related_name='disqualifications',
        null=False,
        on_delete=models.CASCADE,
    )
    reason = models.CharField('Причина дисквалификации', max_length=150, null=True)
    tours = models.ManyToManyField(
        TourNumber,
        verbose_name='Туры',
        related_name='disqualifications',
        blank=False,
        help_text='Туры, на которые распостраняется дисквалификация',
    )
    lifted_tours = models.ManyToManyField(
        TourNumber,
        verbose_name='Отмененные туры',
        related_name='lifted_disqualifications',
        blank=True,
        help_text='Туры, на которые дисквалификация была снята. Должно являться '
        'подмножеством списка туров, на которые дисквалификация была выдана',
    )
    created = models.DateTimeField('Выдана', auto_now_add=True)

    class Meta:
        ordering = ('-created',)
        verbose_name = 'Дисквалификация'
        verbose_name_plural = 'Дисквалификации'

    def __str__(self):
        return f'{self.player.nickname} ({self.match.team_home.short_title} - {self.match.team_guest.short_title})'


class CardQuerySet(models.QuerySet):
    def yellow(self):
        return self.filter(kind=Card.Kind.YELLOW)

    def red(self):
        return self.filter(kind=Card.Kind.RED)


class Card(models.Model):
    class Kind(models.TextChoices):
        YELLOW = 'YEL', 'Жёлтая'
        RED = 'RED', 'Красная'

    match = models.ForeignKey(Match, verbose_name='Матч', related_name='cards', on_delete=models.CASCADE)
    team = models.ForeignKey(Team, verbose_name='Команда', related_name='cards', on_delete=models.PROTECT)
    author = ChainedForeignKey(
        Player,
        chained_field='team',
        chained_model_field='team',
        verbose_name='Автор',
        related_name='cards',
        on_delete=models.PROTECT,
    )
    kind = models.CharField('Тип карточки', max_length=3, choices=Kind.choices, db_index=True)
    time_min = models.PositiveSmallIntegerField('Минута')
    time_sec = models.PositiveSmallIntegerField(
        'Секунда',
        validators=[
            MaxValueValidator(59, message='Значение должно быть от 0 до 59'),
        ],
    )
    reason = models.CharField(
        'Причина',
        max_length=300,
        blank=True,
        help_text='Указывать в формате "за нарушение гл. 1 ст. 2 ч. 3 Регламента..." для отображения на странице матча',
    )
    legacy_event = models.OneToOneField(
        'OtherEvents',
        verbose_name='Исходное событие',
        related_name='migrated_card',
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )

    objects = CardQuerySet.as_manager()

    def __str__(self):
        icon = '🟨' if self.kind == self.Kind.YELLOW else '🟥'
        return f'{icon} {self.time_min:02d}:{self.time_sec:02d} {self.author} ({self.team})'

    class Meta:
        verbose_name = 'Карточка'
        verbose_name_plural = 'Карточки'
        ordering = ('time_min', 'time_sec', 'pk')
        indexes = [
            models.Index(fields=('kind', 'match')),
            models.Index(fields=('author', 'match')),
            models.Index(fields=('team', 'match')),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(time_sec__lt=60), name='card_time_sec_lt_60'),
        ]


class CleanSheet(models.Model):
    class Period(models.TextChoices):
        FIRST_HALF = 'H1', 'Первый тайм'
        SECOND_HALF = 'H2', 'Второй тайм'
        EXTRA_TIME = 'ET', 'Дополнительное время'

    match = models.ForeignKey(Match, verbose_name='Матч', related_name='clean_sheets', on_delete=models.CASCADE)
    team = models.ForeignKey(Team, verbose_name='Команда', related_name='clean_sheets', on_delete=models.PROTECT)
    author = ChainedForeignKey(
        Player,
        chained_field='team',
        chained_model_field='team',
        verbose_name='Автор',
        related_name='clean_sheets',
        on_delete=models.PROTECT,
    )
    period = models.CharField('Период', max_length=2, choices=Period.choices, db_index=True)
    legacy_event = models.OneToOneField(
        'OtherEvents',
        verbose_name='Исходное событие',
        related_name='migrated_clean_sheet',
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )

    @property
    def time_min(self):
        if self.period == self.Period.FIRST_HALF:
            return 8
        if self.period == self.Period.SECOND_HALF:
            return 16
        return int(self.match.duration.total_seconds()) // 60

    @property
    def time_sec(self):
        if self.period != self.Period.EXTRA_TIME:
            return 0
        return int(self.match.duration.total_seconds()) % 60

    def __str__(self):
        return f'🧤 {self.time_min:02d}:{self.time_sec:02d} {self.author} ({self.team})'

    class Meta:
        verbose_name = 'Сухой тайм'
        verbose_name_plural = 'Сухие таймы'
        ordering = ('match_id', 'period', 'pk')
        indexes = [
            models.Index(fields=('period', 'match')),
            models.Index(fields=('author', 'match')),
            models.Index(fields=('team', 'match')),
        ]


class OtherEventsQuerySet(models.QuerySet):
    def cards(self):
        return self.filter(event__in=[OtherEvents.YELLOW_CARD, OtherEvents.RED_CARD])

    def yellow_cards(self):
        return self.filter(event=OtherEvents.YELLOW_CARD)

    def red_cards(self):
        return self.filter(event=OtherEvents.RED_CARD)

    def cs(self):
        return self.filter(event=OtherEvents.CLEAN_SHEET)

    def ogs(self):
        return self.filter(event=OtherEvents.OWN_GOAL)


class OtherEvents(models.Model):
    match = models.ForeignKey(
        Match, verbose_name='Матч', related_name='match_event', null=True, on_delete=models.CASCADE
    )

    team = models.ForeignKey(
        Team, verbose_name='Команда', related_name='team_events', null=True, on_delete=models.SET_NULL
    )

    author = ChainedForeignKey(
        Player,
        chained_field='team',
        chained_model_field='team',
        verbose_name='Автор',
        related_name='event',
        null=True,
        on_delete=models.CASCADE,
    )
    time_min = models.PositiveSmallIntegerField('Минута')
    time_sec = models.PositiveSmallIntegerField(
        'Секунда',
        validators=[MaxValueValidator(59, message='Значение должно быть от 0 до 59')],
    )

    YELLOW_CARD = 'YEL'
    RED_CARD = 'RED'
    CLEAN_SHEET = 'CLN'
    OWN_GOAL = 'OG'
    EVENT = [
        (YELLOW_CARD, 'Жёлтая'),
        (RED_CARD, 'Красная'),
        (CLEAN_SHEET, 'Сухой тайм'),
        (OWN_GOAL, 'Автогол'),
    ]

    event = models.CharField(max_length=3, choices=EVENT, default=CLEAN_SHEET, verbose_name='Тип события')
    card_reason = models.CharField(
        max_length=300,
        verbose_name='За что выдана карточка',
        null=True,
        blank=True,
        help_text='Только для карточек. Указывать в формате "за нарушение гл. 1 ст. 2 ч. 3 Регламента..." '
        'для корректного отображения на странице матча',
    )

    objects = OtherEventsQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if self.match.team_home == self.team and self.event == 'OG':
            self.match.score_guest += 1
            self.match.save(update_fields=['score_guest'])
        elif self.team == self.match.team_guest and self.event == 'OG':
            self.match.score_home += 1
            self.match.save(update_fields=['score_home'])
        super(OtherEvents, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.match.team_home == self.team and self.event == 'OG':
            self.match.score_guest -= 1
            self.match.save(update_fields=['score_guest'])
        elif self.team == self.match.team_guest and self.event == 'OG':
            self.match.score_home -= 1
            self.match.save(update_fields=['score_home'])
        super(OtherEvents, self).delete(*args, **kwargs)

    def __str__(self):
        match self.event:
            case OtherEvents.CLEAN_SHEET:
                emoji = '🧤'
            case OtherEvents.YELLOW_CARD:
                emoji = '🟨'
            case OtherEvents.RED_CARD:
                emoji = '🟥'
            case _:
                emoji = self.event

        return f'{emoji} {self.time_min:02d}:{self.time_sec:02d} {self.author} ({self.team})'

    class Meta:
        verbose_name = 'Событие [OBSOLETE])'
        verbose_name_plural = 'События [OBSOLETE]'
        indexes = [
            models.Index(fields=['event', 'match']),
        ]


class PlayerTransfer(models.Model):
    trans_player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='teams_all', verbose_name='Игрок')
    from_team = models.ForeignKey(
        Team,
        verbose_name='Из команды',
        related_name='outgoing_transfers',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    to_team = models.ForeignKey(
        Team,
        verbose_name='В команду',
        related_name='incoming_transfers',
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    date_join = models.DateField(verbose_name='Дата трансфера', default=None)
    season_join = models.ForeignKey(
        Season, on_delete=models.CASCADE, verbose_name='В каком сезоне', related_name='transfers'
    )
    is_technical = models.BooleanField(
        'Технический',
        default=False,
        help_text='Используется для того, чтобы помечать трансферы по сбросу всех игроков в СА перед началом сезона',
    )

    tracker = FieldTracker(['to_team'])

    def save(self, *args, **kwargs):
        if not self.pk or self.tracker.has_changed('to_team'):
            if self.to_team:
                self.trans_player.team = self.to_team
            else:
                self.trans_player.team = None
            self.trans_player.save()

        super(PlayerTransfer, self).save(*args, **kwargs)

    def __str__(self):
        return f'Переход {self.trans_player} в команду {self.to_team} (из {self.from_team})'

    class Meta:
        verbose_name = 'Трансфер'
        verbose_name_plural = 'Трансферы'
        indexes = [
            models.Index(fields=['trans_player', 'season_join']),
            models.Index(fields=['to_team']),
        ]


class Postponement(models.Model):
    match = models.ForeignKey(
        Match, verbose_name='Матч', related_name='postponements', null=False, on_delete=models.CASCADE
    )
    is_emergency = models.BooleanField('Экстренный', default=False)
    teams = models.ManyToManyField(Team, verbose_name='На кого взят перенос', related_name='postponements')
    starts_at = models.DateField('Дата старта переноса', null=False, blank=False)
    ends_at = models.DateField('Дата окончания переноса', null=False, blank=False)
    taken_at = models.DateTimeField('Дата офомления переноса', default=timezone.now)
    taken_by = models.ForeignKey(
        User,
        verbose_name='Кем оформлен перенос',
        related_name='taken_postponements',
        null=True,
        on_delete=models.SET_NULL,
    )
    is_cancelled = models.GeneratedField(
        verbose_name='Отменен',
        expression=models.Case(
            models.When(cancelled_at__isnull=False, then=True),
            default=False,
            output_field=models.BooleanField(),
        ),
        db_persist=True,
        output_field=models.BooleanField(),
    )
    cancelled_at = models.DateTimeField('Дата отмены переноса', null=True, blank=True)
    cancelled_by = models.ForeignKey(
        User,
        verbose_name='Кем отменен перенос',
        related_name='cancelled_postponements',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    @property
    def is_mutual(self):
        return self.teams.count() > 1

    @property
    def can_be_cancelled(self):
        return not self.is_cancelled and timezone.localdate() < self.starts_at

    @property
    def league(self):
        return self.match.league

    def cancel(self, cancelled_by: User):
        self.cancelled_at = timezone.now()
        self.cancelled_by = cancelled_by

    def __str__(self):
        return 'Перенос матча {} - {}, {} тур ({} - {})'.format(
            self.match.team_home,
            self.match.team_guest,
            self.match.numb_tour.number,
            self.starts_at.strftime('%d.%m'),
            self.ends_at.strftime('%d.%m'),
        )

    class Meta:
        verbose_name = 'Перенос'
        verbose_name_plural = 'Переносы'


class PostponementSlots(models.Model):
    league = models.OneToOneField(
        League,
        verbose_name='Турнир',
        related_name='postponement_slots',
        null=False,
        blank=False,
        on_delete=models.CASCADE,
    )
    common_count = models.PositiveSmallIntegerField('Количество обычных переносов', default=3)
    emergency_count = models.PositiveSmallIntegerField('Количество экстренных переносов', default=3)
    extra_count = models.PositiveSmallIntegerField('Количество дополнительных (платных) переносов', default=3)

    @property
    def total_count(self):
        return self.common_count + self.emergency_count + self.extra_count

    def __str__(self):
        return f'{self.league} ({self.common_count}, {self.emergency_count}, {self.extra_count})'

    class Meta:
        verbose_name = 'Слоты переноса'
        verbose_name_plural = 'Слоты переноса'


class AchievementCategory(models.Model):
    title = models.CharField('Название категории', max_length=50)
    description = models.CharField('Описание категории', max_length=150)
    order = models.SmallIntegerField('Порядок категории при отображении в профиле')

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['order']
        verbose_name = 'Категория медалек'
        verbose_name_plural = 'Категории медалек'


class Achievements(models.Model):
    title = models.CharField('Название', max_length=100)
    description = models.CharField('Описание', max_length=200)
    image = models.ImageField('Изображение медали', upload_to='medals/', null=True)
    player = models.ManyToManyField(Player, verbose_name='Игрок', related_name='achievements', blank=True)
    position_number = models.SmallIntegerField('Позиция', default=0)
    category = models.ForeignKey(
        AchievementCategory,
        verbose_name='Категория',
        related_name='player_achievements',
        on_delete=models.SET_NULL,
        null=True,
    )

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['category__order', 'position_number']
        verbose_name = 'Медаль'
        verbose_name_plural = 'Медали'


class TeamAchievement(models.Model):
    title = models.CharField('Название', max_length=100)
    description = models.CharField('Описание', max_length=200)
    image = models.ImageField('Изображение медали', upload_to='medals/', null=True)
    team = models.ManyToManyField(Team, verbose_name='Команда', related_name='achievements')
    season = models.ForeignKey(Season, verbose_name='Сезон', on_delete=models.CASCADE, null=True)
    players_raw_list = models.CharField('Состав', max_length=150, default='', blank=True)
    position_number = models.SmallIntegerField('Позиция', default=0)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['season__number', 'position_number']
        verbose_name = 'Медаль (командная)'
        verbose_name_plural = 'Медали (командные)'


class SeasonTeamRating(models.Model):
    season = models.ForeignKey(Season, verbose_name='Сезон', on_delete=models.CASCADE)
    team = models.ForeignKey(Team, verbose_name='Команда', on_delete=models.CASCADE)
    points_for_matches = models.FloatField(verbose_name='Очки за матчи')
    points_for_result = models.FloatField(verbose_name='Очки за итоговый результат', default=0)

    def total_points(self):
        return self.points_for_matches + self.points_for_result

    class Meta:
        verbose_name = 'Сезонный рейтинг команды'
        verbose_name_plural = 'Сезонный рейтинг команд'


class TeamRatingVersion(models.Model):
    number = models.PositiveSmallIntegerField(verbose_name='Версия', primary_key=True)
    date = models.DateField(verbose_name='Дата')
    related_season = models.ForeignKey(Season, verbose_name='Связанный сезон', on_delete=models.CASCADE)

    def __str__(self):
        return f'Рейтинг от {self.date.strftime("%d.%m.%y")} ({self.related_season.short_title})'

    class Meta:
        ordering = ['-number']
        verbose_name = 'Версия рейтинга команд'
        verbose_name_plural = 'Версии рейтинга команд'


class TeamRating(models.Model):
    version = models.ForeignKey(TeamRatingVersion, verbose_name='Версия рейтинга', on_delete=models.CASCADE)
    team = models.ForeignKey(Team, verbose_name='Команда', on_delete=models.CASCADE)
    rank = models.PositiveSmallIntegerField(verbose_name='Место в рейтинге')
    total_points = models.FloatField(verbose_name='Общее количество очков')

    class Meta:
        ordering = ['-version__number', 'rank']
        verbose_name = 'Рейтинг команды'
        verbose_name_plural = 'Рейтинг команд'


class PlayerRatingVersion(models.Model):
    number = models.PositiveSmallIntegerField(verbose_name='Версия', primary_key=True)
    date = models.DateField(verbose_name='Дата')

    def __str__(self):
        return f'Рейтинг от {self.date.strftime("%d.%m.%y")}'

    class Meta:
        ordering = ['-number']
        verbose_name = 'Версия рейтинга игроков'
        verbose_name_plural = 'Версии рейтинга игроков'


class PlayerRating(models.Model):
    class Grade(models.TextChoices):
        S = 'S', 'S'
        A = 'A', 'A'
        B_PLUS = 'B+', 'B+'
        B = 'B', 'B'
        C = 'C', 'C'
        D = 'D', 'D'
        E = 'E', 'E'

    class RatingUpdateStatus(models.TextChoices):
        """Why this rating was set: expert re-evaluation, inactivity decrease, or frozen after 1+ year inactivity."""

        EXPERT_REVIEW = 'expert_review', 'Пересмотрен экспертами'
        INACTIVITY_DECREASE = 'inactivity_decrease', 'Снижение за неактивность'
        FROZEN = 'frozen', 'Заморожен (не играл больше года)'

    version = models.ForeignKey(PlayerRatingVersion, verbose_name='Версия рейтинга', on_delete=models.CASCADE)
    player = models.ForeignKey(Player, verbose_name='Игрок', on_delete=models.CASCADE)
    raw_rating_points = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    rating_points = models.PositiveSmallIntegerField('Рейтинг')
    grade = models.CharField(verbose_name='Грейд', max_length=2, choices=Grade.choices)
    rating_update_status = models.CharField(
        verbose_name='Тип обновления рейтинга',
        max_length=20,
        choices=RatingUpdateStatus.choices,
        default=RatingUpdateStatus.EXPERT_REVIEW,
        help_text='Пересмотрен экспертами, снижен за неактивность или заморожен после года+ неактивности.',
    )

    def __str__(self):
        return f'{self.player.nickname} ({self.grade}: {self.rating_points})'

    class Meta:
        ordering = ['-version__number', '-rating_points', '-raw_rating_points']
        verbose_name = 'Рейтинг игрока'
        verbose_name_plural = 'Рейтинг игроков'


class AwardNomination(models.Model):
    """Catalog of award nomination categories (e.g., Best striker, Best defender)"""

    class Code(models.TextChoices):
        BEST_STRIKER = 'BEST_STRIKER', 'Нападающий сезона'
        BEST_DEFENDER = 'BEST_DEFENDER', 'Опорник сезона'
        BEST_GOALKEEPER = 'BEST_GOALKEEPER', 'Вратарь сезона'
        BEST_PLAYER = 'BEST_PLAYER', 'Игрок сезона'
        BEST_CAPTAIN = 'BEST_CAPTAIN', 'Капитан сезона'
        BREAKTHROUGH = 'BREAKTHROUGH', 'Прорыв сезона'

    name = models.CharField('Название', max_length=100)
    code = models.CharField('Код', max_length=50, unique=True, choices=Code.choices)
    order = models.IntegerField('Порядок отображения', default=0)
    logo = models.ImageField('Логотип', upload_to='award_nominations/', null=True, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['order']
        verbose_name = 'Номинация награды'
        verbose_name_plural = 'Номинации наград'


class AwardCampaign(models.Model):
    """Container for all awards in a season with shared voting dates"""

    season = models.ForeignKey(
        Season,
        verbose_name='Сезон',
        related_name='award_campaigns',
        on_delete=models.CASCADE,
    )
    voting_start_date = models.DateTimeField('Дата начала голосования')
    voting_end_date = models.DateTimeField('Дата окончания голосования')
    results_public_date = models.DateTimeField('Дата публикации результатов')

    @property
    def is_voting_active(self):
        """Check if voting period is currently active"""
        now = timezone.now()
        return self.voting_start_date <= now <= self.voting_end_date

    @property
    def is_voting_ended(self):
        """Check if voting period has ended"""
        now = timezone.now()
        return self.voting_end_date < now

    @property
    def is_results_public(self):
        """Check if results are currently public"""
        now = timezone.now()
        return self.results_public_date <= now

    def __str__(self):
        return f'Награды сезона - {self.season.title}'

    class Meta:
        verbose_name = 'Кампания наград'
        verbose_name_plural = 'Кампании наград'


class Award(models.Model):
    """Links award nominations to specific tournaments/leagues"""

    campaign = models.ForeignKey(
        AwardCampaign,
        verbose_name='Кампания наград',
        related_name='awards',
        on_delete=models.CASCADE,
    )
    league = models.ForeignKey(
        League,
        verbose_name='Турнир',
        related_name='awards',
        on_delete=models.CASCADE,
    )
    nomination = models.ForeignKey(
        AwardNomination,
        verbose_name='Номинация',
        related_name='awards',
        on_delete=models.CASCADE,
    )
    max_nominees = models.PositiveSmallIntegerField(
        'Максимальное количество номинантов',
        null=True,
        blank=True,
        help_text='Оставьте пустым, если ограничения нет',
    )

    @property
    def voting_start_date(self):
        """Convenience property to access voting_start_date through campaign"""
        return self.campaign.voting_start_date

    @property
    def voting_end_date(self):
        """Convenience property to access voting_end_date through campaign"""
        return self.campaign.voting_end_date

    @property
    def results_public_date(self):
        """Convenience property to access results_public_date through campaign"""
        return self.campaign.results_public_date

    def __str__(self):
        return f'{self.nomination.name} ({self.league.title}. {self.campaign.season.title})'

    def recalculate_results(self):
        """Calculate and update AwardResult records for all nominees"""
        from django.db.models import Sum

        # Delete existing results
        AwardResult.objects.filter(award=self).delete()

        # Get all nominees for this award
        nominees = self.nominees.all()

        for nominee in nominees:
            votes = AwardVote.objects.filter(
                award=self,
                nominee=nominee,
            ).select_related('submission')

            # Calculate total points
            total_points = votes.aggregate(total=Sum('points'))['total'] or 0

            # Count votes by place
            first_place_votes = votes.filter(place=1).count()
            second_place_votes = votes.filter(place=2).count()
            third_place_votes = votes.filter(place=3).count()

            # Create result record
            AwardResult.objects.create(
                award=self,
                nominee=nominee,
                total_points=total_points,
                first_place_votes=first_place_votes,
                second_place_votes=second_place_votes,
                third_place_votes=third_place_votes,
            )

        # Initialize all results with None for points_excluding_involved_teams
        AwardResult.objects.filter(award=self).update(points_excluding_involved_teams=None)

        # Calculate points_excluding_involved_teams for tie-breaking
        # Group results by total_points to identify ties
        results_by_points = defaultdict(list)
        all_results = AwardResult.objects.filter(award=self).select_related('nominee__team')
        for result in all_results:
            results_by_points[result.total_points].append(result)

        # Only calculate for nominees who are actually in a tie (more than 1 nominee with same points)
        for points, tied_results in results_by_points.items():
            if len(tied_results) <= 1:
                # No tie, skip calculation (already set to None)
                continue

            involved_teams = {result.nominee.team_id for result in tied_results}

            for result in tied_results:
                votes = AwardVote.objects.filter(
                    award=self,
                    nominee=result.nominee,
                ).select_related('submission')

                points_excluding_involved = (
                    votes.exclude(submission__voter_record__team_id__in=involved_teams).aggregate(total=Sum('points'))[
                        'total'
                    ]
                    or 0
                )
                result.points_excluding_involved_teams = points_excluding_involved
                result.save(update_fields=['points_excluding_involved_teams'])

        # Assign final ranks based on tie-breaking criteria
        results = AwardResult.objects.filter(award=self).order_by(
            '-total_points',
            '-points_excluding_involved_teams',
            '-first_place_votes',
            '-second_place_votes',
            '-third_place_votes',
        )

        rank = 1
        for result in results:
            result.final_rank = rank
            result.save(update_fields=['final_rank'])
            rank += 1

    def auto_populate_best_player_nominees(self):
        """Auto-populate nominees for 'Best player' from all nominees of striker/defender/goalkeeper nominations"""
        if self.nomination.code != AwardNomination.Code.BEST_PLAYER:
            return 0

        source_nominations = [
            AwardNomination.Code.BEST_STRIKER,
            AwardNomination.Code.BEST_DEFENDER,
            AwardNomination.Code.BEST_GOALKEEPER,
        ]

        source_awards = Award.objects.filter(
            campaign=self.campaign,
            league=self.league,
            nomination__code__in=source_nominations,
        )

        players_to_nominate = set()
        for source_award in source_awards:
            for nominee in source_award.nominees.all():
                players_to_nominate.add(nominee.player)

        created_count = 0
        for player in players_to_nominate:
            nominee, created = AwardNominee.objects.get_or_create(
                award=self, player=player, defaults={'team': player.team}
            )
            if created:
                created_count += 1

        return created_count

    def auto_populate_best_captain_nominees(self):
        """Auto-populate nominees for 'Best captain' from all captains of teams in the league"""
        if self.nomination.code != AwardNomination.Code.BEST_CAPTAIN:
            return 0

        teams = self.league.teams.all()

        created_count = 0
        for team in teams:
            nominee, created = AwardNominee.objects.get_or_create(
                award=self, player=team.captain, defaults={'team': team}
            )
            if created:
                created_count += 1

        return created_count

    class Meta:
        unique_together = [('campaign', 'league', 'nomination')]
        verbose_name = 'Награда'
        verbose_name_plural = 'Награды'


class AwardNominee(models.Model):
    """Players nominated for a specific award"""

    award = models.ForeignKey(
        'Award',
        verbose_name='Награда',
        related_name='nominees',
        on_delete=models.CASCADE,
    )
    team = models.ForeignKey(
        Team,
        verbose_name='Команда',
        related_name='award_nominees',
        on_delete=models.CASCADE,
    )
    player = models.ForeignKey(
        Player,
        verbose_name='Игрок',
        related_name='award_nominations',
        on_delete=models.CASCADE,
    )

    def __str__(self):
        return f'{self.player.nickname} ({self.team.title}) - {self.award.nomination.name}'

    class Meta:
        unique_together = [('award', 'team', 'player')]
        verbose_name = 'Номинант'
        verbose_name_plural = 'Номинанты'


class AwardVoter(models.Model):
    """Represents who is eligible to vote for all awards in a tournament during campaign"""

    campaign = models.ForeignKey(
        'AwardCampaign',
        verbose_name='Кампания наград',
        related_name='voters',
        on_delete=models.CASCADE,
    )
    league = models.ForeignKey(
        'League',
        verbose_name='Турнир',
        related_name='award_voters',
        on_delete=models.CASCADE,
    )
    team = models.ForeignKey(
        Team,
        verbose_name='Команда',
        related_name='award_voters',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text='Команда, от имени которой голосует игрок. Оставьте пустым для независимого голосующего.',
    )
    voter = models.ForeignKey(
        Player,
        verbose_name='Голосующий',
        related_name='award_voting_records',
        on_delete=models.CASCADE,
    )

    def __str__(self):
        team_str = self.team.title if self.team else 'Независимый представитель'
        return f'{team_str} - {self.voter.nickname} ({self.campaign.season.title}, {self.league.title})'

    class Meta:
        unique_together = [('campaign', 'league', 'voter')]
        verbose_name = 'Голосующий'
        verbose_name_plural = 'Голосующие'


class AwardSubmission(models.Model):
    """Represents a complete voting submission for a campaign from a specific voter"""

    campaign = models.ForeignKey(
        'AwardCampaign',
        verbose_name='Кампания наград',
        related_name='submissions',
        on_delete=models.CASCADE,
    )
    league = models.ForeignKey(
        'League',
        verbose_name='Турнир',
        related_name='award_submissions',
        on_delete=models.CASCADE,
    )
    voter_record = models.ForeignKey(
        'AwardVoter',
        verbose_name='Голосующий',
        related_name='submissions',
        on_delete=models.CASCADE,
        help_text='Запись о голосующем, от имени которого подается голосование',
    )
    submitted_at = models.DateTimeField('Дата подачи голосования')

    def __str__(self):
        submission_time = self.submitted_at.strftime('%d.%m.%Y %H:%M')
        team_str = self.voter_record.team.title if self.voter_record.team else 'Независимый представитель'
        return f'{team_str} - {self.voter_record.voter.nickname} ({self.campaign.season.title}) ({submission_time})'

    class Meta:
        unique_together = [('voter_record',)]
        verbose_name = 'Отправка голосования'
        verbose_name_plural = 'Отправки голосований'


class AwardVote(models.Model):
    """Individual vote (nominee + place) for a specific award"""

    PLACE_CHOICES = [
        (1, '1 место'),
        (2, '2 место'),
        (3, '3 место'),
    ]

    submission = models.ForeignKey(
        'AwardSubmission',
        verbose_name='Отправка голосования',
        related_name='votes',
        on_delete=models.CASCADE,
    )
    award = models.ForeignKey(
        'Award',
        verbose_name='Награда',
        related_name='votes',
        on_delete=models.CASCADE,
    )
    nominee = models.ForeignKey(
        'AwardNominee',
        verbose_name='Номинант',
        related_name='votes_received',
        on_delete=models.CASCADE,
    )
    place = models.PositiveSmallIntegerField('Место', choices=PLACE_CHOICES)
    points = models.PositiveSmallIntegerField(
        'Очки',
        help_text='Автоматически: 3 за 1 место, 2 за 2 место, 1 за 3 место',
    )

    def save(self, *args, **kwargs):
        if self.place == 1:
            self.points = 3
        elif self.place == 2:
            self.points = 2
        elif self.place == 3:
            self.points = 1
        super().save(*args, **kwargs)

    @property
    def nomination(self):
        """Convenience property to access nomination through award"""
        return self.award.nomination

    def __str__(self):
        team_str = (
            self.submission.voter_record.team.title
            if self.submission.voter_record.team
            else 'Независимый представитель'
        )
        return f'{team_str} - {self.nominee.player.nickname} ({self.place} место) - {self.award.nomination.name}'

    class Meta:
        unique_together = [('submission', 'award', 'place')]
        verbose_name = 'Голос'
        verbose_name_plural = 'Голоса'


class AwardResult(models.Model):
    """Calculated results for each nominee in each nomination"""

    award = models.ForeignKey(
        'Award',
        verbose_name='Награда',
        related_name='results',
        on_delete=models.CASCADE,
    )
    nominee = models.ForeignKey(
        'AwardNominee',
        verbose_name='Номинант',
        related_name='results',
        on_delete=models.CASCADE,
    )
    total_points = models.IntegerField('Всего очков', default=0)
    points_excluding_involved_teams = models.IntegerField(
        'Очки без учета команд участников ничьей',
        null=True,
        blank=True,
        help_text=(
            'Используется как первый тай-брейкер: очки без учета всех команд игроков с одинаковым количеством очков.'
        ),
    )
    first_place_votes = models.IntegerField('Голосов за 1 место', default=0)
    second_place_votes = models.IntegerField('Голосов за 2 место', default=0)
    third_place_votes = models.IntegerField('Голосов за 3 место', default=0)
    final_rank = models.PositiveSmallIntegerField('Финальное место', null=True, blank=True)
    last_calculated_at = models.DateTimeField('Последний расчет', auto_now=True)

    def __str__(self):
        return f'{self.nominee.player.nickname} - {self.award.nomination.name} ({self.total_points} очков)'

    class Meta:
        unique_together = [('award', 'nominee')]
        ordering = [
            '-total_points',
            '-points_excluding_involved_teams',
            '-first_place_votes',
            '-second_place_votes',
            '-third_place_votes',
        ]
        verbose_name = 'Результат голосования за награду'
        verbose_name_plural = 'Результаты голосований за награды'
