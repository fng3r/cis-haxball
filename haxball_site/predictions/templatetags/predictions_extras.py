from datetime import timedelta

from django import template
from django.utils import timezone

from ..utils import is_tour_open_for_predictions

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key"""
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def is_open_for_predictions(tour):
    """Template filter to check if a tour is open for predictions"""
    return is_tour_open_for_predictions(tour)


@register.filter
def is_not_open_yet(tour):
    """Template filter to check if a tour hasn't opened for predictions yet (future)"""
    today = timezone.now().date()
    open_date = get_tour_opening_date(tour)

    return today < open_date


@register.filter
def get_tour_opening_date(tour):
    """Template filter to get the date when a tour opens for predictions"""
    return tour.date_from - timedelta(days=3)
