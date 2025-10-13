from django.contrib.auth.models import User
from django.db import models

from tournament.models import League, Player, Team, TourNumber


class FantasyTournament(models.Model):
    """Tournament that is available for fantasy league"""

    league = models.OneToOneField(
        League, verbose_name='Турнир', on_delete=models.CASCADE, related_name='fantasy_tournament'
    )
    is_active = models.BooleanField('Активен для фэнтези', default=True)

    def __str__(self):
        return f'Фэнтези: {self.league.title}'

    class Meta:
        verbose_name = 'Турнир для фэнтези'
        verbose_name_plural = 'Турниры для фэнтези'


class SquadPlayer(models.Model):
    """Player in the context of a squad submission with specific position"""

    class Position(models.TextChoices):
        GK = 'GK', 'Вратарь'
        DM = 'DM', 'Опорник'
        ST = 'ST', 'Нападающий'

    class SquadType(models.TextChoices):
        MAIN = 'main', 'Основной состав'
        BENCH = 'bench', 'Скамейка'

    submission = models.ForeignKey(
        'SquadSubmission', verbose_name='Отправка состава', related_name='squad_players', on_delete=models.CASCADE
    )
    player = models.ForeignKey(Player, verbose_name='Игрок', on_delete=models.CASCADE)
    team = models.ForeignKey(Team, verbose_name='Команда', on_delete=models.CASCADE, null=False, blank=False)
    position = models.CharField('Позиция', max_length=2, choices=Position.choices)
    squad_type = models.CharField('Тип состава', max_length=5, choices=SquadType.choices, default=SquadType.MAIN)

    @property
    def is_main_squad_player(self):
        return self.squad_type == self.SquadType.MAIN

    @property
    def is_bench_player(self):
        return self.squad_type == self.SquadType.BENCH

    class Meta:
        verbose_name = 'Игрок состава'
        verbose_name_plural = 'Игроки составов'
        ordering = ['squad_type', 'position']
        unique_together = ['submission', 'player']

    def __str__(self):
        return f'{self.player.nickname} ({self.get_position_display()})'


class BoosterType(models.TextChoices):
    JOKER = 'joker', 'Джокер'
    LIMITLESS = 'limitless', 'Безлимитный'


class SquadSubmission(models.Model):
    """User's squad submission for a specific tour"""

    user = models.ForeignKey(
        User, verbose_name='Пользователь', on_delete=models.CASCADE, related_name='fantasy_squad_submissions'
    )
    tour = models.ForeignKey(
        TourNumber, verbose_name='Тур', on_delete=models.CASCADE, related_name='fantasy_squad_submissions'
    )
    tournament = models.ForeignKey(
        FantasyTournament, verbose_name='Турнир', on_delete=models.CASCADE, related_name='squad_submissions'
    )
    created = models.DateTimeField('Создано', auto_now_add=True)
    updated = models.DateTimeField('Обновлено', auto_now=True)

    captain_player = models.ForeignKey(
        Player,
        verbose_name='Капитан',
        on_delete=models.DO_NOTHING,
        null=True,
        blank=True,
        related_name='fantasy_captaincies',
    )

    penalized_transfers = models.PositiveIntegerField(
        verbose_name='Штрафуемые трансферы',
        default=0,
        help_text='Количество использованных трансферов сверх лимита доступных бесплатных трансферов',
    )

    used_booster = models.CharField(
        verbose_name='Использованный бустер',
        max_length=10,
        choices=BoosterType.choices,
        null=True,
        blank=True,
        help_text='Бустер, использованный при выборе состава',
    )

    class Meta:
        verbose_name = 'Отправка состава'
        verbose_name_plural = 'Отправки составов'
        unique_together = ['user', 'tour', 'tournament']

    def __str__(self):
        return f'Состав {self.user.username} для {self.tour}'

    @property
    def main_squad(self):
        """Get main squad players"""
        return self.squad_players.filter(squad_type=SquadPlayer.SquadType.MAIN)

    @property
    def bench_players(self):
        """Get bench players"""
        return self.squad_players.filter(squad_type=SquadPlayer.SquadType.BENCH)


class PlayerCost(models.Model):
    """Custom cost for a player across all fantasy tournaments"""

    player = models.OneToOneField(Player, verbose_name='Игрок', on_delete=models.CASCADE, related_name='fantasy_cost')
    cost = models.DecimalField('Стоимость', max_digits=4, decimal_places=1, help_text='Стоимость игрока в миллионах')

    class Meta:
        verbose_name = 'Стоимость игрока'
        verbose_name_plural = 'Стоимости игроков'
        ordering = ['player__nickname']

    def __str__(self):
        return f'{self.player.nickname} - {self.cost}M'
