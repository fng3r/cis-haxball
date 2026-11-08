"""Original-engine role contract and game/match selection policy; no legacy rewrites."""

import math

POSITION_CODES = frozenset({'GK', 'DM', 'AM', 'ST', 'LW', 'RW'})
MIN_POSITION_TICKS = 15 * 60
MIN_SECONDARY_SHARE = 0.25


def select_positions(roles, observed_ticks):
    """Same ranking and thresholds as engine/positions.js, using unrounded evidence."""
    ranked = sorted(roles, key=lambda role: (-role['ticks'], -role.get('confidenceTicks', 0)))
    supported = [role for role in ranked if role['ticks'] >= MIN_POSITION_TICKS]
    primary = supported[0] if observed_ticks >= MIN_POSITION_TICKS and supported else None
    secondary = supported[1] if primary and len(supported) > 1 else None
    if secondary and secondary['ticks'] / observed_ticks < MIN_SECONDARY_SHARE:
        secondary = None

    def confidence(role):
        # Match JS Math.round for nonnegative values, including half-way cases.
        return math.floor(role.get('confidenceTicks', 0) / observed_ticks * 1000 + 0.5) / 1000 if role else 0

    return {
        'primary_position': primary['position'] if primary else None,
        'secondary_position': secondary['position'] if secondary else None,
        'primary_position_confidence': confidence(primary),
        'secondary_position_confidence': confidence(secondary),
    }


def player_position_fields(player):
    """Extract only computed roles. Older cached responses remain explicitly unavailable."""
    empty = {
        'primary_position': None,
        'secondary_position': None,
        'primary_position_confidence': None,
        'secondary_position_confidence': None,
        'position_observed_ticks': None,
        'position_roles': [],
    }
    if 'primaryPosition' not in player or 'positionObservedTicks' not in player:
        return empty
    primary, secondary = player['primaryPosition'], player.get('secondaryPosition')
    if any(position is not None and position not in POSITION_CODES for position in (primary, secondary)):
        raise ValueError('Unsupported replay player position')
    if secondary and (not primary or primary == secondary):
        raise ValueError('Invalid secondary replay player position')
    observed = player['positionObservedTicks']
    if not isinstance(observed, int) or isinstance(observed, bool) or not 0 <= observed <= player['playedTicks']:
        raise ValueError('Invalid position observation time')
    roles, seen = [], set()
    for role in player.get('positionRoles', []):
        position, ticks = role['position'], role['ticks']
        if position not in POSITION_CODES or position in seen or not isinstance(ticks, int) or ticks < 0:
            raise ValueError('Invalid replay position evidence')
        score = role.get('confidenceTicks')
        if not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= ticks:
            raise ValueError('Invalid replay position confidence evidence')
        seen.add(position)
        roles.append({'position': position, 'ticks': ticks, 'confidenceTicks': score})
    if sum(role['ticks'] for role in roles) > observed:
        raise ValueError('Replay position evidence exceeds observed play')
    by_position = {role['position']: role for role in roles}
    if any(
        position and (position not in seen or by_position[position]['ticks'] < MIN_POSITION_TICKS)
        for position in (primary, secondary)
    ):
        raise ValueError('Replay position has insufficient role evidence')
    if secondary and by_position[secondary]['ticks'] / observed < MIN_SECONDARY_SHARE:
        raise ValueError('Replay secondary position has insufficient share')
    if observed < MIN_POSITION_TICKS and (primary or secondary or roles):
        raise ValueError('Replay positions require fifteen seconds of observed play')
    for key in ('primaryPositionConfidence', 'secondaryPositionConfidence'):
        score = player.get(key, 0)
        if not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError('Invalid replay player position confidence')
    # Exports rank roles by support. Preserve actual first-observed order in
    # domain evidence so whole-match ties use chronology across ordered parts.
    first_seen = {}
    for index, period in enumerate(player.get('positionPeriods', [])):
        first_seen.setdefault(period['position'], index)
    roles.sort(key=lambda role: first_seen.get(role['position'], math.inf))
    return {
        'primary_position': primary,
        'secondary_position': secondary,
        'primary_position_confidence': player.get('primaryPositionConfidence', 0),
        'secondary_position_confidence': player.get('secondaryPositionConfidence', 0),
        'position_observed_ticks': observed,
        'position_roles': roles,
    }
