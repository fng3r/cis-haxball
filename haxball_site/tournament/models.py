from datetime import date

from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.db.models import Case, Q, Value, When
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
    title = models.CharField('Название Розыгрыша', max_length=128)
    short_title = models.CharField('Короткое название', max_length=15, null=True, blank=True)
    number = models.SmallIntegerField('Номер сезона')
    is_active = models.BooleanField('Текущий')
    created = models.DateTimeField('Создана', auto_now_add=True)
    bound_season = models.ForeignKey(
        'self', verbose_name='Связанный сезон', null=True, blank=True, on_delete=models.SET_NULL
    )

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
    color_1 = ColorField(default='#FFFFFF', verbose_name='Цвет 1')
    color_2 = ColorField(default='#FFFFFF', verbose_name='Цвет 2')
    color_table = ColorField(default='#FFFFFF', verbose_name='Цвет Таблички')
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
    rating = models.SmallIntegerField('Рейтинг команды', blank=True, null=True)

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
    championship = models.ForeignKey(
        Season,
        verbose_name='Сезон',
        related_name='tournaments_in_season',
        null=True,
        on_delete=models.CASCADE,
    )
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
        return self.is_playoff and self.has_match_for_third_place

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

    class Meta:
        verbose_name = 'Регулярка'


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
        TournamentStage, verbose_name='Этап турнира', related_name='penalties', on_delete=models.CASCADE
    )
    team = ChainedForeignKey(
        Team,
        verbose_name='Команда',
        chained_field='stage',
        chained_model_field='stages',
        related_name='penalties',
        null=True,
        blank=True,
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
    name = models.OneToOneField(
        User, verbose_name='Пользователь', null=True, blank=True, on_delete=models.SET_NULL, related_name='user_player'
    )

    nickname = models.CharField(
        'Никнейм игрока',
        max_length=150,
    )

    FORWARD = 'FW'
    DEF_MIDDLE = 'DM'
    GOALKEEPER = 'GK'
    POSITIONS = (
        (FORWARD, 'Нападающий'),
        (DEF_MIDDLE, 'Опорник'),
        (GOALKEEPER, 'Вратарь'),
    )
    position = models.CharField('Позиция', max_length=2, choices=POSITIONS, null=True, blank=True)

    team = models.ForeignKey(
        Team, verbose_name='Команда', related_name='players_in_team', blank=True, null=True, on_delete=models.SET_NULL
    )

    player_nation = models.ForeignKey(
        Nation, verbose_name='Национальность', related_name='country_players', null=True, on_delete=models.SET_NULL
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
    replay_link = models.URLField('Ссылка на реплей', blank=True)
    replay_link_second = models.URLField('Ссылка на реплей(2-й, если два)', blank=True, null=True)
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

    def cards(self):
        return self.match_event.filter(Q(event=OtherEvents.YELLOW_CARD) | Q(event=OtherEvents.RED_CARD)).order_by(
            'team'
        )

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
        # match can be postponed during 12h since tour/previous postponement end date
        end_datetime = timezone.datetime.combine(end_date, timezone.datetime.min.time()) + timezone.timedelta(
            days=1, hours=12
        )

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

    def get_absolute_url(self):
        return reverse('tournament:match_detail', args=[self.id])

    def __str__(self):
        return f'Матч {self.team_home.short_title} - {self.team_guest.short_title}. {self.numb_tour.number} тур'

    class Meta:
        verbose_name = 'Матч'
        verbose_name_plural = 'Матчи'
        ordering = ['league', 'stage', 'numb_tour', 'id']


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


class Goal(models.Model):
    match = models.ForeignKey(
        Match, verbose_name='Матч', related_name='match_goal', null=True, blank=True, on_delete=models.CASCADE
    )

    team = models.ForeignKey(
        Team, verbose_name='Команда забила', related_name='goals', null=True, on_delete=models.SET_NULL
    )

    author = ChainedForeignKey(
        Player,
        chained_field='team',
        chained_model_field='team',
        verbose_name='Автор гола',
        related_name='goals',
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
    time_min = models.SmallIntegerField('Минута')
    time_sec = models.SmallIntegerField('Секунда')

    def save(self, *args, **kwargs):
        if self.pk is None:  # update score only when goal is created
            if self.team == self.match.team_home:
                self.match.score_home += 1
                self.match.save(update_fields=['score_home'])
            elif self.team == self.match.team_guest:
                self.match.score_guest += 1
                self.match.save(update_fields=['score_guest'])
        super(Goal, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.team == self.match.team_home:
            self.match.score_home -= 1
            self.match.save(update_fields=['score_home'])
        elif self.team == self.match.team_guest:
            self.match.score_guest -= 1
            self.match.save(update_fields=['score_guest'])
        super(Goal, self).delete(*args, **kwargs)

    def __str__(self):
        assistant = f' ({self.assistent})' if self.assistent else ''
        return f'⚽ {self.time_min:02d}:{self.time_sec:02d} {self.team} - {self.author}{assistant}'

    class Meta:
        verbose_name = 'Гол'
        verbose_name_plural = 'Голы'
        ordering = ['time_min', 'time_sec']


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
    time_min = models.SmallIntegerField('Минута')
    time_sec = models.SmallIntegerField('Секунда')

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
        indexes = [models.Index(fields=['player', 'league'])]


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

    def annotate_with_tournament(self):
        return self.annotate(
            tournament=Case(
                When(
                    Q(match__league__title__istartswith='Высшая') | Q(match__league__title__istartswith='Единая'),
                    then=Value('Высшая лига'),
                ),
                When(match__league__title__istartswith='Первая', then=Value('Первая лига')),
                When(match__league__title__istartswith='Вторая', then=Value('Вторая лига')),
                When(
                    Q(match__league__title__istartswith='Кубок Высшей')
                    | Q(match__league__title__istartswith='Кубок Первой')
                    | Q(match__league__title__istartswith='Кубок Второй')
                    | Q(match__league__title__istartswith='Кубок лиги'),
                    then=Value('Кубок лиги'),
                ),
                When(match__league__title__istartswith='Лига Чемпионов', then=Value('Лига Чемпионов')),
                When(match__league__title__istartswith='Кубок России', then=Value('Кубок России')),
                default=Value('Unknown'),
            )
        )


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
    time_min = models.SmallIntegerField('Минута')
    time_sec = models.SmallIntegerField('Секунда')

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
        verbose_name = 'Событие'
        verbose_name_plural = 'События'


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
    player = models.ManyToManyField(Player, verbose_name='Игрок', related_name='achievements', blank=True, null=True)
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
    team = models.ManyToManyField(Team, verbose_name='Команда', related_name='achievements', null=True)
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
    related_season = models.OneToOneField(Season, verbose_name='Связанный сезон', on_delete=models.CASCADE)

    def __str__(self):
        return f'Рейтинг на {self.date.strftime('%d.%m.%y')} ({self.related_season.short_title})'

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
        return f'Рейтинг на {self.date.strftime('%d.%m.%y')}'

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

    version = models.ForeignKey(PlayerRatingVersion, verbose_name='Версия рейтинга', on_delete=models.CASCADE)
    player = models.ForeignKey(Player, verbose_name='Игрок', on_delete=models.CASCADE)
    rating_points = models.PositiveSmallIntegerField()
    grade = models.CharField(verbose_name='Грейд', max_length=2, choices=Grade.choices)

    def __str__(self):
        return f'{self.player.nickname} ({self.grade}: {self.rating_points})'

    class Meta:
        ordering = ['-version__number', '-rating_points']
        verbose_name = 'Рейтинг игрока'
        verbose_name_plural = 'Рейтинг игроков'
