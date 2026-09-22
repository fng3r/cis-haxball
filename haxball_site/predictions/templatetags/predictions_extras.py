from decimal import Decimal
from math import ceil

from django import template
from django.utils import timezone

from .. import utils
from ..points_service import calculate_prediction_points, is_prediction_correct, is_prediction_void

register = template.Library()


@register.filter
def get_prediction_points(prediction):
    """Return points (positive or negative) earned for a single prediction, or 0."""
    return calculate_prediction_points(prediction)


@register.filter
def net_win(nominal, coefficient):
    """Return betting-style net win for a coefficient: nominal * (coefficient - 1)."""
    if nominal is None or coefficient is None:
        return None
    return Decimal(nominal) * (Decimal(coefficient) - 1)


@register.filter
def format_points(value):
    """Format points with an explicit sign: '+240' / '-100'."""
    if value is None:
        return ''
    value = Decimal(value).quantize(Decimal('0.01'))
    if value == value.to_integral_value():
        value = value.quantize(Decimal('1'))
    if value < 0:
        return str(value)
    return f'+{value}'


@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key"""
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def get_coefficient(coefficients, result_value):
    """Get the coefficient for a given outcome value from MatchPredictionCoefficients."""
    if coefficients is None:
        return None
    return coefficients.coefficient_for(result_value)


@register.filter
def is_open_for_predictions(tour):
    """Template filter to check if a tour is open for predictions"""
    return utils.is_tour_open_for_predictions(tour)


@register.filter
def is_not_open_yet(tour):
    """Template filter to check if a tour hasn't opened for predictions yet (future)"""
    open_datetime = utils.get_tour_opening_datetime(tour)

    return timezone.localtime() < open_datetime


@register.filter
def is_closed_for_predictions(tour):
    """Template filter to check if a tour is closed for predictions"""
    return not is_open_for_predictions(tour) and not is_not_open_yet(tour)


@register.filter
def get_tour_opening_datetime(tour):
    """Template filter to get the date when a tour opens for predictions"""
    return utils.get_tour_opening_datetime(tour)


@register.filter
def is_tour_actual(tour):
    """Check if a tour is actual"""
    return tour.date_to + timezone.timedelta(days=7) >= timezone.localdate()


@register.filter
def hours_until_start(tournament):
    if tournament is None:
        return None
    delta = tournament.locked_at - timezone.now()
    return max(0, ceil(delta.total_seconds() / 3600))


@register.filter
def prediction_is_correct(prediction):
    return is_prediction_correct(prediction)


@register.filter
def prediction_is_void(prediction):
    return is_prediction_void(prediction)
