from django import template
from django.utils import timezone

from .. import utils
from ..points_service import (
    calculate_player_breakdown,
    calculate_submission_penalty_points,
    calculate_submission_total_points,
)

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key"""
    return dictionary.get(key)


@register.filter
def in_list(value, list_obj):
    """Check if value is in list"""
    return value in list_obj


@register.filter
def sort_squad_players(squad_players):
    """Sort squad players by position in correct order: GK, DM, ST"""
    position_order = {'GK': 0, 'DM': 1, 'ST': 2}

    def get_position_sort_key(squad_player):
        return position_order.get(squad_player.position)

    return sorted(squad_players, key=get_position_sort_key)


@register.filter
def is_tour_open_for_fantasy(tour):
    """Check if a tour is open for fantasy"""
    return utils.is_tour_open_for_fantasy(tour)


@register.filter
def is_tour_not_open_yet(tour):
    """Check if a tour is not open yet"""
    return utils.is_tour_not_open_yet(tour)


@register.filter
def is_tour_closed(tour):
    """Check if a tour is closed"""
    return not is_tour_open_for_fantasy(tour) and not is_tour_not_open_yet(tour)


@register.filter
def get_tour_opening_date(tour):
    """Get the opening date of a tour"""
    return utils.get_tour_opening_date(tour)


@register.filter
def is_tour_actual(tour):
    """Check if a tour is actual"""
    return tour.date_to + timezone.timedelta(days=7) > timezone.localdate()


@register.filter
def get_total_points(submission, preloaded_data):
    """Get total points for a submission with preloaded data"""
    if submission and preloaded_data:
        return calculate_submission_total_points(submission, preloaded_data)
    return 0


@register.filter
def get_penalty_points(submission):
    """Get penalty points for a submission"""
    if submission:
        return calculate_submission_penalty_points(submission)
    return 0


@register.simple_tag(takes_context=True)
def player_points_breakdown(context, squad_player, role: str = 'main'):
    """Return per-player points breakdown dict for the given `squad_player`.

    role: 'main' or 'bench' to apply correct multipliers.
    """
    preloaded_data = context.get('preloaded_data')
    submission = context.get('submission')

    return calculate_player_breakdown(submission, squad_player, role, preloaded_data)


@register.filter
def get_player_by_id(players, player_id: int | str | None):
    if not player_id:
        return None

    if isinstance(player_id, str):
        player_id = int(player_id)

    return next((player for player in players if player.id == player_id), None)


@register.simple_tag
def get_positions():
    return ['main_squad_gk', 'main_squad_dm', 'main_squad_st1', 'main_squad_st2', 'bench_gk', 'bench_dm', 'bench_st']
