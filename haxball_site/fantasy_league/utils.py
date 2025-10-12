from datetime import time
from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Count, F
from django.utils import timezone

from tournament.models import (
    Goal,
    Match,
    OtherEvents,
    Player,
    PlayerMatchStatistics,
    PlayerRating,
    PlayerRatingVersion,
    TourNumber,
)

from .models import FantasyTournament, PlayerCost, SquadSubmission
from .points_service import (
    calculate_submission_penalty_points,
    calculate_submission_total_points,
    calculate_total_points,
)


def is_tour_open_for_fantasy(tour):
    """Check if a tour is currently open for fantasy league submissions"""
    now = timezone.localtime()

    closed_at = get_tour_start_datetime(tour)
    open_at = get_tour_opening_datetime(tour)

    return open_at <= now <= closed_at


def get_tour_opening_datetime(tour):
    start_datetime = get_tour_start_datetime(tour)

    return start_datetime - timezone.timedelta(days=3) + timezone.timedelta(minutes=30)


def get_tour_start_datetime(tour):
    start_datetime = timezone.datetime.combine(tour.date_from, time(18, 0))
    start_datetime = timezone.make_aware(start_datetime)

    return start_datetime


def is_tour_not_open_yet(tour):
    """Check if a tour is not open yet"""
    opening_datetime = get_tour_opening_datetime(tour)

    return timezone.localtime() < opening_datetime


def get_user_tour_points(user, tour, tournament):
    """Get total points for a user in a specific tour"""
    preloaded_data = preload_fantasy_data(tournament)

    submission = (
        SquadSubmission.objects.filter(user=user, tour=tour, tournament=tournament)
        .prefetch_related('squad_players__player')
        .select_related('tour')
        .first()
    )
    if submission:
        return calculate_submission_total_points(submission, preloaded_data)
    return None


def get_user_tournament_total_points(user, tournament):
    """Get total points for a user in a tournament"""
    preloaded_data = preload_fantasy_data(tournament)

    submissions = (
        SquadSubmission.objects.filter(user=user, tournament=tournament)
        .prefetch_related('squad_players__player')
        .select_related('tour')
    )

    total_points = 0
    for submission in submissions:
        total_points += calculate_submission_total_points(submission, preloaded_data)

    return total_points


def get_tournament_standings(tournament):
    """Get tournament standings sorted by total points"""
    preloaded_data = preload_fantasy_data(tournament)

    users_with_submissions = (
        User.objects.filter(fantasy_squad_submissions__tournament=tournament).select_related('user_profile').distinct()
    )

    all_submissions = (
        SquadSubmission.objects.filter(tournament=tournament)
        .prefetch_related('squad_players__player', 'user')
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
        penalty_points = 0
        tour_points = {}

        for submission in user_submissions:
            submission_total = calculate_submission_total_points(submission, preloaded_data)
            submission_penalty = calculate_submission_penalty_points(submission)

            total_points += submission_total
            penalty_points += submission_penalty
            tour_points[submission.tour_id] = submission_total

        total_points -= penalty_points

        standings.append(
            {
                'user': user,
                'total_points': total_points,
                'penalty_points': penalty_points,
                'tour_points': tour_points,
            }
        )

    standings.sort(key=lambda x: x['total_points'], reverse=True)

    return standings


def get_player_fantasy_stats(tournament: FantasyTournament):
    """Get fantasy statistics for all players"""
    preloaded_data = preload_fantasy_data(tournament)

    players_ids = (
        PlayerMatchStatistics.objects.filter(league=tournament.league_id).values_list('player', flat=True).distinct()
    )
    players = Player.objects.filter(id__in=players_ids).prefetch_related('name__user_profile')

    all_submissions = SquadSubmission.objects.filter(tournament=tournament).prefetch_related(
        'squad_players__player', 'tour'
    )

    total_submissions = all_submissions.count()

    matches_by_player = (
        PlayerMatchStatistics.objects.filter(league=tournament.league_id)
        .values('player')
        .annotate(matches_count=Count('match'))
    )
    matches_by_player_map = {match['player']: match['matches_count'] for match in matches_by_player}

    pick_counts = (
        SquadSubmission.objects.filter(tournament=tournament)
        .values('squad_players__player')
        .annotate(pick_count=Count('id', distinct=True))
    )
    pick_counts_map = {pick['squad_players__player']: pick['pick_count'] for pick in pick_counts}

    stats = []

    matches = preloaded_data.get('tour_matches')
    match_participants = preloaded_data.get('match_participants')
    for player in players:
        primary_position = player.positions[0] if player.positions else None
        matches_played = matches_by_player_map.get(player.id, 0)
        if not primary_position or matches_played == 0:
            continue

        total_fp = 0
        for match in matches:
            if player.id in match_participants.get(match.id, []):
                match_goals = preloaded_data['match_goals'].get(match.id, [])
                match_cs = preloaded_data['match_cs'].get(match.id, [])

                match_points = calculate_total_points(player, match, primary_position, match_goals, match_cs)
                total_fp += match_points

        total_picked = pick_counts_map.get(player.id, 0)

        pickrate = total_picked / max(total_submissions, 1)
        fp_per_match = total_fp / matches_played

        stats.append(
            {
                'player': player,
                'position': primary_position,
                'matches_played': matches_played,
                'pickrate': pickrate,
                'fp_per_match': fp_per_match,
                'total_fp': total_fp,
                'primary_position': primary_position,
            }
        )

    stats.sort(key=lambda x: x['total_fp'], reverse=True)

    return stats


def preload_fantasy_data(tournament):
    tours = tournament.league.tours.all()

    matches = list(
        Match.objects.filter(numb_tour__in=tours, is_played=True)
        .select_related('team_home', 'team_guest', 'numb_tour')
        .prefetch_related(
            'team_home_start',
            'team_guest_start',
            'match_participants__team',
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
        'tour_matches': matches,
        'match_participants': match_participants,
        'match_goals': match_goals,
        'match_cs': match_cs,
    }


def get_blocking_tours(user, tour, tournament):
    """Get blocking tours for a user"""
    blocking_tours = []
    previous_tours = TourNumber.objects.filter(league=tour.league, number__lt=tour.number).order_by('number')
    for previous_tour in previous_tours:
        if is_tour_open_for_fantasy(previous_tour):
            has_submission = SquadSubmission.objects.filter(
                user=user, tour=previous_tour, tournament=tournament
            ).exists()

            if not has_submission:
                blocking_tours.append(previous_tour)

    return blocking_tours


def get_reverse_blocking_tours(user, tour, tournament):
    """
    Get tours that are blocked by this tour (reverse blocking).
    When a later tour is submitted, earlier tours become locked for modification.
    """
    reverse_blocking_tours = []
    later_tours = TourNumber.objects.filter(league=tour.league, number__gt=tour.number).order_by('number')

    for later_tour in later_tours:
        if is_tour_open_for_fantasy(later_tour):
            has_submission = SquadSubmission.objects.filter(user=user, tour=later_tour, tournament=tournament).exists()

            if has_submission:
                reverse_blocking_tours.append(later_tour)

    return reverse_blocking_tours


# ===== Budget and player cost helpers (shared between forms and setup scripts) =====

PRICE_RANGES = {
    PlayerRating.Grade.S: (30, 40),
    PlayerRating.Grade.A: (19, 29),
    PlayerRating.Grade.B_PLUS: (13, 18),
    PlayerRating.Grade.B: (8.5, 12.5),
    PlayerRating.Grade.C: (5, 8.2),
    PlayerRating.Grade.D: (2.5, 4.8),
    PlayerRating.Grade.E: (1, 2.4),
}

RATING_RANGES = {
    PlayerRating.Grade.S: (91, 100),
    PlayerRating.Grade.A: (76, 90),
    PlayerRating.Grade.B_PLUS: (61, 75),
    PlayerRating.Grade.B: (46, 60),
    PlayerRating.Grade.C: (31, 45),
    PlayerRating.Grade.D: (16, 30),
    PlayerRating.Grade.E: (0, 15),
}

BUDGET_LIMITS = {
    'Высшая лига': 110.0,
    'Первая лига': 65.0,
    'Вторая лига': 40.0,
}


def get_league_budget_limit(league):
    return BUDGET_LIMITS.get(league.title)


def calculate_player_cost(player_rating, player):
    """Calculate player cost in millions based on rating, custom cost, or default"""
    if player_rating:
        grade = player_rating.grade
        rating_points = player_rating.rating_points

        price_range = PRICE_RANGES.get(grade)
        rating_range = RATING_RANGES.get(grade)

        min_price, max_price = price_range
        min_rating, max_rating = rating_range

        if max_rating == min_rating:
            position_ratio = 0.0
        else:
            position_ratio = (rating_points - min_rating) / (max_rating - min_rating)
        position_ratio = max(0.0, min(1.0, position_ratio))
        cost = min_price + (max_price - min_price) * position_ratio

        return round(cost, 1)

    custom_cost = PlayerCost.objects.filter(player=player).first()
    if custom_cost:
        return float(custom_cost.cost)

    return PRICE_RANGES.get(PlayerRating.Grade.E)[1]


def get_players_costs(league):
    """Return {player_id: cost} for players in the given league's teams."""
    latest_rating_version = PlayerRatingVersion.objects.order_by('-number').first()
    league_player_ids = list(Player.objects.filter(team__in=league.teams.all()).values_list('id', flat=True))
    ratings = PlayerRating.objects.filter(player_id__in=league_player_ids, version=latest_rating_version)
    player_rating_map = {r.player_id: r for r in ratings}

    costs = {}
    for pid in league_player_ids:
        player = Player.objects.get(id=pid)
        player_rating = player_rating_map.get(pid)
        costs[pid] = calculate_player_cost(player_rating, player)

    return costs


def get_total_cost_for_players(players, player_costs):
    """Sum total cost for a list of Player objects using provided cost map."""
    return sum(player_costs.get(p.id, 0) for p in players if p)


def get_available_players_in_league(league):
    """
    Get all players that are currently available in the given league.
    Returns a set of player IDs for efficient lookup.
    """
    return set(Player.objects.filter(team__in=league.teams.all()).values_list('id', flat=True))


def get_unavailable_players_in_submission(submission: SquadSubmission):
    """
    Get list of players in a submission that are no longer available in the league.
    Returns a list of SquadPlayer objects that need to be replaced.
    """
    league = submission.tournament.league
    available_player_ids = get_available_players_in_league(league)

    unavailable_players = []
    for squad_player in submission.squad_players.all():
        if squad_player.player_id not in available_player_ids:
            unavailable_players.append(squad_player)

    return unavailable_players


def get_players_with_changed_positions(submission: SquadSubmission):
    """
    Get list of players in a submission that have positions changed since submission was made.
    """
    squad_players = submission.squad_players.select_related('player').annotate(
        current_position=F('player__positions__0')
    )

    result = {
        player.player_id: {
            'player': player,
            'prev_position': player.position,
            'current_position': player.current_position,
        }
        for player in squad_players
        if player.position != player.current_position
    }

    return result


def calculate_tour_rewards(tour, tournament):
    """Calculate rewards distribution for a specific tour in fantasy league"""
    submissions = SquadSubmission.objects.filter(tour=tour, tournament=tournament).prefetch_related(
        'squad_players__player', 'user__user_profile'
    )

    if not submissions.exists():
        return {'total_participants': 0, 'total_prize_pool': 0, 'user_rewards': []}

    total_participants = submissions.count()
    total_prize_pool = total_participants * 10

    preloaded_data = preload_fantasy_data(tournament)

    user_points = []
    for submission in submissions:
        points = calculate_submission_total_points(submission, preloaded_data)
        user_points.append({'user': submission.user, 'points': points})

    total_points = sum(up['points'] for up in user_points if up['points'] >= 0)

    user_rewards = []
    for up in user_points:
        if up['points'] < 0:
            reward_amount = Decimal('0.00')
        elif total_points > 0:
            proportion = up['points'] / total_points
            reward_amount = Decimal(str(total_prize_pool)) * Decimal(str(proportion))
            reward_amount = reward_amount.quantize(Decimal('0.01'))
        else:
            reward_amount = Decimal('0.00')

        user_rewards.append({'user': up['user'], 'points': up['points'], 'reward_amount': reward_amount})

    user_rewards.sort(key=lambda x: x['points'], reverse=True)

    return {
        'total_participants': total_participants,
        'total_prize_pool': total_prize_pool,
        'user_rewards': user_rewards,
    }
