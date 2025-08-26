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
def is_tour_closed(tour):
    """Check if a tour is closed"""
    return not is_tour_open_for_fantasy(tour) and not is_tour_not_open_yet(tour)


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


@register.simple_tag(takes_context=True)
def squad_player_stats(context, squad_player):
    """Return stats string for a SquadPlayer: 'xG yA zCS', omitting zero stats."""
    preloaded_data = context.get('preloaded_data')
    submission = context.get('submission')
    if not preloaded_data or not submission:
        return ''

    tour_matches = [m for m in preloaded_data['tour_matches'] if m.numb_tour_id == submission.tour_id]
    player = squad_player.player
    goals = 0
    assists = 0
    cs = 0
    for match in tour_matches:
        match_goals = preloaded_data['match_goals'].get(match.id, [])
        goals += sum(1 for g in match_goals if g.author_id == player.id)
        assists += sum(1 for g in match_goals if g.assistent_id == player.id)
        match_cs = preloaded_data.get('match_cs', {}).get(match.id, [])
        cs += sum(1 for e in match_cs if e.author_id == player.id)
    parts = []
    if goals:
        parts.append(f'{goals}G')
    if assists:
        parts.append(f'{assists}A')
    if cs:
        parts.append(f'{cs}CS')
    return ' '.join(parts)


@register.simple_tag(takes_context=True)
def player_points_breakdown(context, squad_player, role: str = 'main'):
    """Return per-player points breakdown dict for the given `squad_player`.

    role: 'main' or 'bench' to apply correct multipliers.
    """
    preloaded_data = context.get('preloaded_data')
    submission = context.get('submission')

    return submission.get_player_points_breakdown(squad_player, role, preloaded_data)


@register.filter
def get_player_by_id(players, player_id: int | str | None):
    if not player_id:
        return None

    if isinstance(player_id, str):
        player_id = int(player_id)

    return next((player for player in players if player.id == player_id), None)
