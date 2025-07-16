from datetime import time

from django.contrib.auth.models import User
from django.utils import timezone

from tournament.models import Goal, Match, Substitution, TourNumber

from .models import SquadSubmission


def get_open_tours():
    """Get tours that are currently open for fantasy league submissions"""
    now = timezone.now()
    today = now.date()

    # Calculate the date range for open tours
    # Tours open 3 days before start date and close at 18:00 on start date
    open_date = today - timezone.timedelta(days=3)
    close_date = today + timezone.timedelta(days=1)  # Include today

    # Get all tours that could be open in one query with all related data
    potential_open_tours = TourNumber.objects.filter(
        league__fantasy_tournament__is_active=True, date_from__gte=open_date, date_from__lte=close_date
    ).select_related('league', 'league__fantasy_tournament')

    open_tours = []
    for tour in potential_open_tours:
        if is_tour_open_for_fantasy(tour):
            open_tours.append(tour.id)

    return open_tours


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
        .prefetch_related('primary_squad__player', 'secondary_squad__player')
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
        .prefetch_related('primary_squad__player', 'secondary_squad__player')
        .select_related('tour')
    )

    total_points = 0
    for submission in submissions:
        total_points += submission.get_total_points(preloaded_data)

    return total_points


def get_tournament_standings(tournament):
    """Get tournament standings sorted by total points"""
    # Preload all fantasy data to avoid N+1 queries
    preloaded_data = preload_fantasy_data(tournament)

    # Get all users with submissions for this tournament in one query with all related data
    users_with_submissions = (
        User.objects.filter(fantasy_squad_submissions__tournament=tournament).select_related('user_profile').distinct()
    )

    # Get all submissions for this tournament in one query with all related data
    all_submissions = (
        SquadSubmission.objects.filter(tournament=tournament)
        .prefetch_related('primary_squad__player', 'secondary_squad__player', 'user')
        .select_related('user', 'user__user_profile')
    )

    # Group submissions by user for efficient access
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
    from django.db import models

    from tournament.models import Player

    # Preload all fantasy data to avoid N+1 queries
    if tournament:
        preloaded_data = preload_fantasy_data(tournament)
    else:
        preloaded_data = None

    # Get all players who have been picked in fantasy with all related data
    players_queryset = Player.objects.filter(fantasy_squad_players__isnull=False).select_related('team').distinct()

    if tournament:
        players_queryset = players_queryset.filter(
            models.Q(fantasy_squad_players__primary_squad_submissions__tournament=tournament)
            | models.Q(fantasy_squad_players__secondary_squad_submissions__tournament=tournament)
        )

    # Get all relevant submissions in one query
    submissions_filter = {}
    if tournament:
        submissions_filter['tournament'] = tournament

    all_submissions = SquadSubmission.objects.filter(**submissions_filter).prefetch_related(
        'primary_squad__player', 'secondary_squad__player', 'tour'
    )

    # Create lookup dictionaries for efficient access
    primary_submissions_by_player = {}
    secondary_submissions_by_player = {}

    for submission in all_submissions:
        # Group primary squad submissions by player
        for squad_player in submission.primary_squad.all():
            player_id = squad_player.player.id
            if player_id not in primary_submissions_by_player:
                primary_submissions_by_player[player_id] = []
            primary_submissions_by_player[player_id].append((submission, squad_player))

        # Group secondary squad submissions by player
        for squad_player in submission.secondary_squad.all():
            player_id = squad_player.player.id
            if player_id not in secondary_submissions_by_player:
                secondary_submissions_by_player[player_id] = []
            secondary_submissions_by_player[player_id].append((submission, squad_player))

    stats = []

    for player in players_queryset:
        # Get counts from lookup dictionaries
        primary_submissions = primary_submissions_by_player.get(player.id, [])
        secondary_submissions = secondary_submissions_by_player.get(player.id, [])

        primary_count = len(primary_submissions)
        secondary_count = len(secondary_submissions)
        total_picked = primary_count + secondary_count

        # Calculate total points granted
        total_points = 0

        # Points from primary squad submissions
        for submission, squad_player in primary_submissions:
            points = submission._calculate_player_points(squad_player, preloaded_data)
            total_points += points

        # Points from secondary squad submissions (0.5x)
        for submission, squad_player in secondary_submissions:
            points = submission._calculate_player_points(squad_player, preloaded_data) * 0.5
            total_points += points

        stats.append(
            {
                'player': player,
                'total_picked': total_picked,
                'primary_picked': primary_count,
                'secondary_picked': secondary_count,
                'total_points': total_points,
            }
        )

    # Sort by total points descending
    stats.sort(key=lambda x: x['total_points'], reverse=True)

    return stats


def preload_fantasy_data(tournament):
    tours = tournament.league.tours.all()

    matches = (
        Match.objects.filter(numb_tour__in=tours, is_played=True)
        .select_related('team_home', 'team_guest', 'numb_tour')
        .prefetch_related('team_home_start', 'team_guest_start', 'match_participants')
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

    match_substitutions = {}
    substitutions = Substitution.objects.filter(match__in=matches).select_related('team')
    for sub in substitutions:
        if sub.match_id not in match_substitutions:
            match_substitutions[sub.match_id] = []
        match_substitutions[sub.match_id].append(sub)

    return {
        'tour_matches': list(matches),
        'match_participants': match_participants,
        'match_goals': match_goals,
        'match_substitutions': match_substitutions,
    }
