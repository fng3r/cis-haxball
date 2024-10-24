from datetime import date
from typing import Optional

from colorfield.fields import ColorField
from core.models import NewComment
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.db.models import Case, Q, Value, When
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from model_utils import FieldTracker
from smart_selects.db_fields import ChainedForeignKey


class TeamIsNotMatchParticipantError(Exception):
    def __init__(self, team, match):
        message = 'Team {} is not a participant of the match {}'.format(team, match)
        super().__init__(message)


class FreeAgent(models.Model):
    player = models.OneToOneField(User, verbose_name='Игрок', on_delete=models.CASCADE, related_name='user_free_agent')
    description = models.TextField('Комментарий к заявке', max_length=200, blank=True)
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
    position_main = models.CharField(max_length=40, choices=POSITION, default=ANY)
    created = models.DateTimeField('Оставлена', default=timezone.now)
    deleted = models.DateTimeField('Снята', auto_now_add=True)
    is_active = models.BooleanField('Активно', default=True)

    def __str__(self):
        return 'CA {}'.format(self.player.username)

    class Meta:
        verbose_name = 'Свободный агент'
        verbose_name_plural = 'Свободные агенты'


class Season(models.Model):
    title = models.CharField('Название Розыгрыша', max_length=128)
    short_title = models.CharField('Короткое название', max_length=15, null=True, blank=True)
    number = models.SmallIntegerField('Номер сезона')
    is_active = models.BooleanField('Текущий')
    created = models.DateTimeField('Создана', auto_now_add=True)
    is_round_robin = models.BooleanField(
        'Круговой розыгрыш', help_text='Галочка, если обычный ЧР, если нету - ЛЧ или иже с ним', default=True
    )
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
    slug = models.SlugField('слаг', max_length=250)
    date_found = models.DateField(
        'Дата основания',
        default=date.today,
    )
    short_title = models.CharField('Сокращение', help_text='До 10 символов', max_length=11)
    logo = models.ImageField('Логотип', upload_to='team_logos/', default='team_logos/default.png')
    color_1 = ColorField(default='#FFFFFF', verbose_name='Цвет 1')
    color_2 = ColorField(default='#FFFFFF', verbose_name='Цвет 2')
    color_table = ColorField(default='#FFFFFF', verbose_name='Цвет Таблички')
    owner = models.ForeignKey(
        User, verbose_name='Владелец', null=True, on_delete=models.SET_NULL, related_name='team_owner'
    )
    office_link = models.URLField('Офис', blank=True)
    rating = models.SmallIntegerField('Рейтинг команды', blank=True, null=True)

    def get_absolute_url(self):
        return reverse('tournament:team_detail', args=[self.slug])

    def get_active_leagues(self):
        return self.leagues.filter(championship__is_active=True)

    def get_postponements(self, leagues):
        return (
            self.postponements.filter(cancelled_at__isnull=True, match__league__in=leagues)
            .select_related('match__team_home', 'match__team_guest', 'match__numb_tour')
            .order_by('taken_at')
        )

    def __str__(self):
        return '{}'.format(self.title)

    class Meta:
        verbose_name = 'Команда'
        verbose_name_plural = 'Команды'


class League(models.Model):
    championship = models.ForeignKey(
        Season, verbose_name='Сезон', related_name='tournaments_in_season', null=True, on_delete=models.CASCADE
    )
    title = models.CharField('Название турнира', max_length=128)
    is_cup = models.BooleanField('Кубок', help_text='галочка, если кубок', default=False)
    priority = models.SmallIntegerField('Приоритет турнира', help_text='1-высшая, 2-пердив, 3-втордив', blank=True)
    slug = models.SlugField(max_length=250)
    created = models.DateTimeField('Создана', auto_now_add=True)
    teams = models.ManyToManyField(
        Team, related_name='leagues', related_query_name='leagues', verbose_name='Команды в лиге'
    )
    comments = GenericRelation(NewComment, related_query_name='league_comments')
    commentable = models.BooleanField('Комментируемый турнир', default=True)

    def __str__(self):
        return '{}, {}'.format(self.title, self.championship)

    def get_postponement_slots(self):
        return self.postponement_slots.first()

    def get_absolute_url(self):
        return reverse('tournament:league', args=[self.slug])

    class Meta:
        ordering = ['-created']
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
        verbose_name = 'Страна'
        verbose_name_plural = 'Страны'


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
    JUST_PLAYER = 'PL'
    CAPTAIN = 'C'
    ASSISTENT = 'AC'
    ROLES = [(JUST_PLAYER, 'Игрок'), (CAPTAIN, 'Капитан'), (ASSISTENT, 'Ассистент')]

    role = models.CharField('Должность', max_length=2, choices=ROLES, default=JUST_PLAYER)

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
        return '{}'.format(self.nickname)

    class Meta:
        verbose_name = 'Игрок'
        verbose_name_plural = 'Игроки'
        ordering = ('nickname',)


class TourNumber(models.Model):
    number = models.SmallIntegerField('Номер тура')
    date_from = models.DateField('Дата тура с', default=date.today, blank=True, null=True)
    date_to = models.DateField('Дата тура по', default=date.today, blank=True, null=True)
    league = models.ForeignKey(League, verbose_name='В какой лиге', related_name='tours', on_delete=models.CASCADE)

    @property
    def is_actual(self):
        today = timezone.now().date()
        return today >= self.date_from and self.tour_matches.filter(is_played=False).exists()

    def __str__(self):
        return '{} тур ({})'.format(self.number, self.league.title)

    class Meta:
        verbose_name = 'Тур'
        verbose_name_plural = 'Туры'
        ordering = ['number']


class Match(models.Model):
    league = models.ForeignKey(
        League,
        verbose_name='В лиге',
        related_name='matches_in_league',
        related_query_name='matches_in_league',
        on_delete=models.CASCADE,
    )
    numb_tour = ChainedForeignKey(
        TourNumber,
        chained_field='league',
        chained_model_field='league',
        verbose_name='Номер тура',
        related_name='tour_matches',
        on_delete=models.CASCADE,
        null=True,
    )
    match_date = models.DateField('Дата матча', default=None, blank=True, null=True)
    replay_link = models.URLField('Ссылка на реплей', blank=True)
    replay_link_second = models.URLField('Ссылка на реплей(2ой, если два)', blank=True, null=True)
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
        chained_field='league',
        chained_model_field='leagues',
        on_delete=models.CASCADE,
        related_name='home_matches',
        verbose_name='Хозяева',
    )
    team_guest = ChainedForeignKey(
        Team,
        chained_field='league',
        chained_model_field='leagues',
        on_delete=models.CASCADE,
        related_name='guest_matches',
        verbose_name='Гости',
    )

    score_home = models.SmallIntegerField('Забито хозявами', default=0)
    score_guest = models.SmallIntegerField('Забито гостями', default=0)

    team_home_start = models.ManyToManyField(
        Player, related_name='home_matches', verbose_name='Состав хозяев', blank=True
    )
    team_guest_start = models.ManyToManyField(
        Player, related_name='guest_matches', verbose_name='Состав Гостей', blank=True
    )

    is_played = models.BooleanField('Сыгран', default=False)

    comment = models.TextField('Комментарий к матчу', max_length=1024, blank=True, null=True)

    comments = GenericRelation(NewComment, related_query_name='match_comments')
    commentable = models.BooleanField('Комментируемый матч', default=True)

    def cards(self):
        return self.match_event.filter(Q(event=OtherEvents.YELLOW_CARD) | Q(event=OtherEvents.RED_CARD)).order_by(
            'team'
        )

    @property
    def can_be_postponed(self):
        if self.is_played:
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
    def winner(self) -> Optional[Team]:
        if self.result:
            return self.result.winner

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
        return 'Матч {} - {}, {} тур'.format(
            self.team_home.short_title, self.team_guest.short_title, self.numb_tour.number
        )

    class Meta:
        verbose_name = 'Матч'
        verbose_name_plural = 'Матчи'
        ordering = ['id']


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
    winner = models.ForeignKey(Team, verbose_name='Победитель', related_name='won_matches',
                               on_delete=models.CASCADE, null=True, blank=True)

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
        return 'на {:02d}:{:02d} от {}({}) в {}'.format(
            self.time_min, self.time_sec, self.author, self.assistent, self.match
        )

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
        return 'в {:02d}:{:02d} {} на {}'.format(self.time_min, self.time_sec, self.player_out, self.player_in)

    class Meta:
        verbose_name = 'Замена'
        verbose_name_plural = 'Замены'


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
        null=False,
        help_text='Туры, на которые распостраняется дисквалификация',
    )
    lifted_tours = models.ManyToManyField(
        TourNumber,
        verbose_name='Отмененные туры',
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
        return '{} ({} - {})'.format(
            self.player.nickname, self.match.team_home.short_title, self.match.team_guest.short_title
        )


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
                    then=Value('Высшая лига')
                ),
                When(match__league__title__istartswith='Первая', then=Value('Первая лига')),
                When(match__league__title__istartswith='Вторая', then=Value('Вторая лига')),
                When(
                    Q(match__league__title__istartswith='Кубок Высшей') |
                    Q(match__league__title__istartswith='Кубок Первой') |
                    Q(match__league__title__istartswith='Кубок Второй') |
                    Q(match__league__title__istartswith='Кубок лиги'),
                    then=Value('Кубок лиги')
                ),
                When(match__league__title__istartswith='Лига Чемпионов', then=Value('Лига Чемпионов')),
                When(match__league__title__istartswith='Кубок России', then=Value('Кубок России')),
                default=Value('Unknown')
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
        return '{:02d}:{:02d} {} в {}'.format(self.time_min, self.time_sec, self.event, self.match)

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
    date_join = models.DateField(default=None)
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
        return 'Переход {} в команду {} (из {})'.format(self.trans_player, self.to_team, self.from_team)

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
        return not self.is_cancelled and timezone.now().date() < self.starts_at

    @property
    def is_cancelled(self):
        return self.cancelled_at is not None

    @property
    def league(self):
        return self.match.league

    def __str__(self):
        return 'Переноса матча {} - {}, {} тур ({} - {})'.format(
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
    league = models.ForeignKey(
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
        return '{}'.format(self.league)

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
    image = models.ImageField('Изображение медальки в профиле', upload_to='medals/', null=True)
    mini_image = models.ImageField('Изображение медальки в комменты', upload_to='medals/', null=True)
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
        verbose_name = 'Медалька'
        verbose_name_plural = 'Медальки'


class TeamAchievement(models.Model):
    title = models.CharField('Название', max_length=100)
    description = models.CharField('Описание', max_length=200)
    image = models.ImageField('Изображение медальки в профиле команды', upload_to='medals/', null=True)
    team = models.ManyToManyField(Team, verbose_name='Команда', related_name='achievements', null=True)
    season = models.ForeignKey(Season, verbose_name='Сезон', on_delete=models.CASCADE, null=True)
    players_raw_list = models.CharField('Состав', max_length=150, default='', blank=True)
    position_number = models.SmallIntegerField('Позиция', default=0)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['season__number', 'position_number']
        verbose_name = 'Медалька (командная)'
        verbose_name_plural = 'Медальки (командные)'


class TeamRatingLeagueWeight(models.Model):
    league = models.OneToOneField(League, verbose_name='Турнир', on_delete=models.CASCADE)
    weight = models.FloatField(verbose_name='Вес турнира')

    def __str__(self):
        return '{} ({})'.format(self.league, self.weight)

    class Meta:
        verbose_name = 'Коэффицент лиги в рейтинге'
        verbose_name_plural = 'Коэффиценты лиг в рейтинге'


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


class RatingVersion(models.Model):
    number = models.PositiveSmallIntegerField(verbose_name='Версия', primary_key=True)
    date = models.DateField(verbose_name='Дата')
    related_season = models.OneToOneField(Season, verbose_name='Связанный сезон', on_delete=models.CASCADE)

    def __str__(self):
        return 'Рейтинг на {} ({})'.format(self.date.strftime('%d.%m.%y'), self.related_season.short_title)

    class Meta:
        ordering = ['-number']
        verbose_name = 'Версия рейтинга'
        verbose_name_plural = 'Версии рейтинга'


class TeamRating(models.Model):
    version = models.ForeignKey(RatingVersion, verbose_name='Версия рейтинга', on_delete=models.CASCADE)
    team = models.ForeignKey(Team, verbose_name='Команда', on_delete=models.CASCADE)
    rank = models.PositiveSmallIntegerField(verbose_name='Место в рейтинге')
    total_points = models.FloatField(verbose_name='Общее количество очков')

    class Meta:
        ordering = ['-version__number', 'rank']
        verbose_name = 'Командный рейтинг'
        verbose_name_plural = 'Командный рейтинг'
