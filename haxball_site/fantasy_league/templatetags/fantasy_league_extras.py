from django import template

from .. import utils

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
def get_tour_opening_date(tour):
    """Get the opening date of a tour"""
    return utils.get_tour_opening_date(tour)


@register.filter
def get_total_points_with_data(submission, preloaded_data):
    """Get total points for a submission with preloaded data"""
    if submission and preloaded_data:
        return submission.get_total_points(preloaded_data)
    return 0
