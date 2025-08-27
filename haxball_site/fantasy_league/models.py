from typing import Literal

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

    POINTS_CONFIG = {
        'goals': {
            SquadPlayer.Position.ST: 3,
            SquadPlayer.Position.DM: 4,
            SquadPlayer.Position.GK: 6,
        },
        'assists': {
            SquadPlayer.Position.ST: 2,
            SquadPlayer.Position.DM: 3,
            SquadPlayer.Position.GK: 4,
        },
        'clean_sheet': {
            SquadPlayer.Position.ST: 2,
            SquadPlayer.Position.DM: 6,
            SquadPlayer.Position.GK: 15,
        },
        'conceded_goals': {
            (1, 2): {
                SquadPlayer.Position.ST: 0,
                SquadPlayer.Position.DM: -1,
                SquadPlayer.Position.GK: -1,
            },
            (3, 5): {
                SquadPlayer.Position.ST: -1,
                SquadPlayer.Position.DM: -2,
                SquadPlayer.Position.GK: -2,
            },
            (6, 10): {
                SquadPlayer.Position.ST: -2,
                SquadPlayer.Position.DM: -4,
                SquadPlayer.Position.GK: -5,
            },
            (11, 15): {
                SquadPlayer.Position.ST: -3,
                SquadPlayer.Position.DM: -6,
                SquadPlayer.Position.GK: -8,
            },
            (16, float('inf')): {
                SquadPlayer.Position.ST: -5,
                SquadPlayer.Position.DM: -10,
                SquadPlayer.Position.GK: -12,
            },
        },
    }

    def get_total_points(self, preloaded_data):
        """Get total points for this submission"""
        main_squad_points = sum(
            self._calculate_player_points(
                squad_player,
                False,
                preloaded_data,
            )
            for squad_player in self.main_squad.all()
        )
        bench_points = sum(
            self._calculate_player_points(
                squad_player,
                True,
                preloaded_data,
            )
            for squad_player in self.bench_players.all()
        )

        return main_squad_points + bench_points

    def _calculate_player_points(self, squad_player, is_bench_player, preloaded_data):
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
                total_points += match_points['total']
                break

        is_captain = self.captain_player_id == squad_player.player_id
        if is_captain:
            total_points *= 2
        if is_bench_player:
            total_points *= 0.5

        return total_points

    def _calculate_match_points_from_data(self, match, squad_player, match_goals, match_cs):
        """Calculate base (no multipliers) points breakdown for a specific match using preloaded data"""
        player = squad_player.player
        position = squad_player.position

        goals_count = sum(1 for goal in match_goals if goal.author_id == player.id)
        assists_count = sum(1 for goal in match_goals if goal.assistent_id == player.id)

        player_team = self._get_player_team_for_match(player, match)
        cs_count = 0
        if player_team is not None:
            cs_count = sum(1 for cs in match_cs if cs.team_id == player_team.id)

        goals_points = goals_count * self.POINTS_CONFIG['goals'][position]
        assists_points = assists_count * self.POINTS_CONFIG['assists'][position]
        cs_points = cs_count * self.POINTS_CONFIG['clean_sheet'][position]

        seconds_played = self._get_player_playtime(player, match)
        if seconds_played >= 12 * 60:
            playtime_points = 3
        elif seconds_played >= 4 * 60:
            playtime_points = 2
        elif seconds_played > 0:
            playtime_points = 1
        else:
            playtime_points = 0

        conceded_goals_count = self._get_player_conceded_goals_count(player, match, match_goals, seconds_played)
        conceded_points = self._get_conceded_goals_penalty(position, conceded_goals_count)

        total_points = goals_points + assists_points + cs_points + playtime_points + conceded_points

        return {
            'goals': {'count': goals_count, 'points': goals_points},
            'assists': {'count': assists_count, 'points': assists_points},
            'cs': {'count': cs_count, 'points': cs_points},
            'playtime': {'seconds': seconds_played, 'points': playtime_points},
            'conceded_goals': {'count': conceded_goals_count, 'points': conceded_points},
            'total': total_points,
        }

    def _get_player_conceded_goals_count(self, player, match, match_goals, seconds_played):
        """Get number of conceded goals for a player in a match"""
        conceded_goals_count = 0
        player_team = self._get_player_team_for_match(player, match)
        if seconds_played > 0 and player_team is not None:
            intervals = self._get_player_intervals(player, match)
            if intervals:
                opponent_team_id = match.team_guest_id if player_team.id == match.team_home_id else match.team_home_id
                for goal in match_goals:
                    if goal.team_id != opponent_team_id:
                        continue
                    goal_time = goal.time_min * 60 + goal.time_sec
                    for start, end in intervals:
                        if start <= goal_time <= end:
                            conceded_goals_count += 1
                            break
        return conceded_goals_count

    def _get_player_team_for_match(self, player, match):
        """Infer player's team for the given match from starts/substitutions."""
        for participant in match.match_participants.all():
            if participant.id == player.id:
                return participant.team
        return None

    def _get_player_intervals(self, player, match):
        """Return list of (start_sec, end_sec) intervals when player was on pitch."""
        full_match_seconds = 16 * 60
        if player not in match.match_participants.all():
            return []

        events = []  # (sec, type)
        started = player in match.team_home_start.all() or player in match.team_guest_start.all()
        for subs in match.match_substitutions.all():
            t = subs.time_min * 60 + subs.time_sec
            if subs.player_in_id == player.id:
                events.append((t, 'in'))
            if subs.player_out_id == player.id:
                events.append((t, 'out'))
        events.sort(key=lambda x: x[0])

        intervals = []
        in_play = started
        current_start = 0 if started else None
        for t, kind in events:
            if kind == 'out' and in_play:
                intervals.append((current_start, t))
                in_play = False
                current_start = None
            elif kind == 'in' and not in_play:
                in_play = True
                current_start = t
        if in_play and current_start is not None:
            intervals.append((current_start, full_match_seconds))
        return intervals

    def _get_player_playtime(self, player, match):
        full_match_seconds = 16 * 60
        seconds_played = 0
        if player in match.match_participants.all():
            started = player in match.team_home_start.all() or player in match.team_guest_start.all()
            if started:
                seconds_played = full_match_seconds
            for subs in match.match_substitutions.all():
                if subs.player_in_id == player.id:
                    seconds_played += full_match_seconds - (subs.time_min * 60 + subs.time_sec)
                if subs.player_out_id == player.id:
                    seconds_played -= full_match_seconds - (subs.time_min * 60 + subs.time_sec)

        return seconds_played

    def _get_conceded_goals_penalty(self, position, goals_count):
        penalty_ranges = self.POINTS_CONFIG['conceded_goals']

        for (start, end), penalties in penalty_ranges.items():
            if start <= goals_count <= end:
                return penalties[position]

        return 0

    def get_player_points_breakdown(self, squad_player, role: Literal['main', 'bench'], preloaded_data):
        """Calculate per-player points for this submission's tour and return a breakdown"""
        tour_matches = preloaded_data.get('tour_matches')
        match_participants = preloaded_data.get('match_participants')
        match_goals = preloaded_data.get('match_goals')
        match_cs = preloaded_data.get('match_cs')

        player = squad_player.player

        match_points = {
            'total': 0,
            'goals': {'count': 0, 'points': 0},
            'assists': {'count': 0, 'points': 0},
            'cs': {'count': 0, 'points': 0},
            'conceded_goals': {'count': 0, 'points': 0},
            'playtime': {'seconds': 0, 'points': 0},
        }

        tour_matches = [match for match in tour_matches if match.numb_tour_id == self.tour_id]
        for match in tour_matches:
            if player.id in match_participants.get(match.id):
                match_points = self._calculate_match_points_from_data(
                    match, squad_player, match_goals.get(match.id, []), match_cs.get(match.id, [])
                )
                break

        is_captain = self.captain_player_id == player.id
        is_bench = role == 'bench'
        multiplier = 1.0
        if is_captain:
            multiplier = 2.0
        if is_bench:
            multiplier = 0.5

        base_total = match_points['total']
        total_points = base_total * multiplier

        seconds_played = match_points['playtime']['seconds']
        formatted_playtime = f'{seconds_played // 60}:{seconds_played % 60:02d}' if seconds_played > 0 else '—'

        return {
            'total': total_points,
            'items': [
                {'name': 'Время на поле', 'value': formatted_playtime, 'points': match_points['playtime']['points']},
                {'name': 'Голы', 'value': match_points['goals']['count'], 'points': match_points['goals']['points']},
                {
                    'name': 'Передачи',
                    'value': match_points['assists']['count'],
                    'points': match_points['assists']['points'],
                },
                {'name': 'Сухие таймы', 'value': match_points['cs']['count'], 'points': match_points['cs']['points']},
                {
                    'name': 'Пропущенные голы',
                    'value': match_points['conceded_goals']['count'],
                    'points': match_points['conceded_goals']['points'],
                },
            ],
            'multipliers': {'captain': is_captain, 'bench': is_bench, 'multiplier': multiplier},
        }
