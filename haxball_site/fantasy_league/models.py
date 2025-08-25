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

    def get_total_points(self, preloaded_data):
        """Get total points for this submission"""
        primary_points = sum(
            self._calculate_player_points(
                squad_player,
                self.captain_player_id == squad_player.player_id,
                preloaded_data,
            )
            for squad_player in self.main_squad.all()
        )
        secondary_points = (
            sum(
                self._calculate_player_points(
                    squad_player,
                    self.captain_player_id == squad_player.player_id,
                    preloaded_data,
                )
                for squad_player in self.bench_players.all()
            )
            * 0.5
        )

        return primary_points + secondary_points

    def _calculate_player_points(self, squad_player, is_captain, preloaded_data):
        """Calculate points for a specific squad player in this tour"""
        tour_matches = preloaded_data.get('tour_matches')
        match_participants = preloaded_data.get('match_participants')
        match_goals = preloaded_data.get('match_goals')
        match_cs = preloaded_data.get('match_cs')

        total_points = 0
        player_id = squad_player.player.id

        tour_matches = [match for match in tour_matches if match.numb_tour_id == self.tour_id]

        for match in tour_matches:
            if player_id in match_participants.get(match.id):
                match_points = self._calculate_match_points_from_data(
                    match, squad_player, match_goals.get(match.id, []), match_cs.get(match.id, [])
                )
                total_points += match_points

        if is_captain:
            total_points *= 2

        return total_points

    def _calculate_match_points_from_data(self, match, squad_player, match_goals, match_cs):
        """Calculate points for a specific match using preloaded data"""
        points = 0
        player = squad_player.player
        position = squad_player.position
        # Goals (3 points for ST, 5 points for DM, 8 points for GK)
        goals = sum(1 for goal in match_goals if goal.author_id == player.id)
        if position == SquadPlayer.Position.ST:
            points += goals * 3
        elif position == SquadPlayer.Position.DM:
            points += goals * 5
        elif position == SquadPlayer.Position.GK:
            points += goals * 8
        # Assists (2 points for ST, 3 points for DM, 5 points for GK)
        assists = sum(1 for goal in match_goals if goal.assistent_id == player.id)
        if position == SquadPlayer.Position.ST:
            points += assists * 2
        elif position == SquadPlayer.Position.DM:
            points += assists * 3
        elif position == SquadPlayer.Position.GK:
            points += assists * 5

        cs_events = [e for e in match_cs if e.author_id == player.id]
        points += 15 * len(cs_events)
        return points
