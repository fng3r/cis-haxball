from django.contrib.auth.models import User
from django.db import models

from tournament.models import League, Player, TourNumber


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

    player = models.ForeignKey(
        Player, verbose_name='Игрок', on_delete=models.CASCADE, related_name='fantasy_squad_players'
    )
    position = models.CharField('Позиция', max_length=2, choices=Position.choices)

    class Meta:
        verbose_name = 'Игрок состава'
        verbose_name_plural = 'Игроки составов'
        unique_together = ['player', 'position']

    def __str__(self):
        return f'{self.player.nickname} ({self.get_position_display()})'


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

    main_squad = models.ManyToManyField(
        SquadPlayer, verbose_name='Основной состав', related_name='main_squad_submissions'
    )
    bench_players = models.ManyToManyField(
        SquadPlayer, verbose_name='Скамейка', related_name='bench_players_submissions'
    )

    captain_player = models.ForeignKey(
        Player,
        verbose_name='Капитан',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fantasy_captaincies',
    )

    class Meta:
        verbose_name = 'Отправка состава'
        verbose_name_plural = 'Отправки составов'
        unique_together = ['user', 'tour', 'tournament']

    def __str__(self):
        return f'Состав {self.user.username} для {self.tour}'
