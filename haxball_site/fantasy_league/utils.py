from datetime import time

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from tournament.models import Goal, Match, OtherEvents, Player

from .models import SquadSubmission


def is_tour_open_for_fantasy(tour):
    """Check if a tour is currently open for fantasy league submissions"""
    now = timezone.now()
    today = now.date()

    # Tour opens 3 days before start date
    open_date = tour.date_from - timezone.timedelta(days=3)

    # Tour closes at 18:00 on the start date
    close_datetime = timezone.datetime.combine(tour.date_from, time(18, 0))
    close_datetime = timezone.make_aware(close_datetime)

    return open_date <= today and now <= close_datetime


def is_tour_not_open_yet(tour):
    """Check if a tour is not open yet"""
    now = timezone.now()
    return tour.date_from > now.date()


def get_tour_opening_date(tour):
    """Get the opening date of a tour"""
    return tour.date_from - timezone.timedelta(days=3)


def get_user_tour_points(user, tour, tournament):
    """Get total points for a user in a specific tour"""
    # Preload fantasy data for this tournament
    preloaded_data = preload_fantasy_data(tournament)

    submission = (
        SquadSubmission.objects.filter(user=user, tour=tour, tournament=tournament)
        .prefetch_related('main_squad__player', 'bench_players__player')
        .select_related('tour')
        .first()
    )
    if submission:
        return submission.get_total_points(preloaded_data)
    return None


def get_user_tournament_total_points(user, tournament):
    """Get total points for a user in a tournament"""
    # Preload fantasy data for this tournament
    preloaded_data = preload_fantasy_data(tournament)

    submissions = (
        SquadSubmission.objects.filter(user=user, tournament=tournament)
        .prefetch_related('main_squad__player', 'bench_players__player')
        .select_related('tour')
    )

    total_points = 0
    for submission in submissions:
        total_points += submission.get_total_points(preloaded_data)

    return total_points


def get_tournament_standings(tournament):
    """Get tournament standings sorted by total points"""
    preloaded_data = preload_fantasy_data(tournament)

    users_with_submissions = (
        User.objects.filter(fantasy_squad_submissions__tournament=tournament).select_related('user_profile').distinct()
    )

    all_submissions = (
        SquadSubmission.objects.filter(tournament=tournament)
        .prefetch_related('main_squad__player', 'bench_players__player', 'user')
        .select_related('user', 'user__user_profile')
    )

    submissions_by_user = {}
    for submission in all_submissions:
        if submission.user_id not in submissions_by_user:
            submissions_by_user[submission.user_id] = []
        submissions_by_user[submission.user_id].append(submission)

    standings = []
    for user in users_with_submissions:
        user_submissions = submissions_by_user.get(user.id, [])
        total_points = 0
        for submission in user_submissions:
            total_points += submission.get_total_points(preloaded_data)

        standings.append({'user': user, 'total_points': total_points})

    standings.sort(key=lambda x: x['total_points'], reverse=True)

    for i, standing in enumerate(standings):
        standing['place'] = i + 1

    return standings


def get_player_fantasy_stats(tournament=None):
    """Get fantasy statistics for all players"""
    if tournament:
        preloaded_data = preload_fantasy_data(tournament)
    else:
        preloaded_data = None

    players_queryset = Player.objects.filter(fantasy_squad_players__isnull=False).select_related('team').distinct()

    if tournament:
        players_queryset = players_queryset.filter(
            models.Q(fantasy_squad_players__main_squad_submissions__tournament=tournament)
            | models.Q(fantasy_squad_players__bench_players_submissions__tournament=tournament)
        )

    submissions_filter = {}
    if tournament:
        submissions_filter['tournament'] = tournament

    all_submissions = SquadSubmission.objects.filter(**submissions_filter).prefetch_related(
        'main_squad__player', 'bench_players__player', 'tour'
    )

    total_submissions = all_submissions.count()

    primary_submissions_by_player = {}
    bench_submissions_by_player = {}

    for submission in all_submissions:
        for squad_player in submission.main_squad.all():
            player_id = squad_player.player.id
            if player_id not in primary_submissions_by_player:
                primary_submissions_by_player[player_id] = []
            primary_submissions_by_player[player_id].append((submission, squad_player))

        for squad_player in submission.bench_players.all():
            player_id = squad_player.player.id
            if player_id not in bench_submissions_by_player:
                bench_submissions_by_player[player_id] = []
            bench_submissions_by_player[player_id].append((submission, squad_player))

    stats = []

    for player in players_queryset:
        primary_submissions = primary_submissions_by_player.get(player.id, [])
        secondary_submissions = bench_submissions_by_player.get(player.id, [])

        primary_count = len(primary_submissions)
        bench_count = len(secondary_submissions)
        total_picked = primary_count + bench_count

        total_points = 0

        for submission, squad_player in primary_submissions:
            points = submission._calculate_player_points(
                squad_player, squad_player.player_id == submission.captain_player_id, preloaded_data
            )
            total_points += points

        for submission, squad_player in secondary_submissions:
            points = (
                submission._calculate_player_points(
                    squad_player, squad_player.player_id == submission.captain_player_id, preloaded_data
                )
                * 0.5
            )
            total_points += points

        popularity = (total_picked / total_submissions) if total_submissions > 0 else 0.0
        points_per_pick = (total_points / total_picked) if total_picked > 0 else 0.0

        stats.append(
            {
                'player': player,
                'total_picked': total_picked,
                'main_picked': primary_count,
                'bench_picked': bench_count,
                'total_points': total_points,
                'popularity': popularity,
                'points_per_pick': points_per_pick,
            }
        )

    stats.sort(key=lambda x: x['total_points'], reverse=True)

    return stats


def preload_fantasy_data(tournament):
    tours = tournament.league.tours.all()

    matches = (
        Match.objects.filter(numb_tour__in=tours, is_played=True)
        .select_related('team_home', 'team_guest', 'numb_tour')
        .prefetch_related(
            'team_home_start',
            'team_guest_start',
            'match_participants',
            'match_substitutions',
            'match_substitutions__team',
        )
    )

    match_participants = {}
    for match in matches:
        match_participants[match.id] = [p.id for p in match.match_participants.all()]

    match_goals = {}
    goals = Goal.objects.filter(match__in=matches).select_related('author', 'assistent')
    for goal in goals:
        if goal.match_id not in match_goals:
            match_goals[goal.match_id] = []
        match_goals[goal.match_id].append(goal)

    events = OtherEvents.objects.filter(match__in=matches, event=OtherEvents.CLEAN_SHEET).select_related(
        'author', 'team'
    )
    match_cs = {}
    for event in events:
        if event.match_id not in match_cs:
            match_cs[event.match_id] = []
        match_cs[event.match_id].append(event)

    return {
        'tour_matches': list(matches),
        'match_participants': match_participants,
        'match_goals': match_goals,
        'match_cs': match_cs,
    }
