"""Shared protocol identities for replay classification and read-only audits."""

from collections import defaultdict

from tournament.models import Player
from tournament.services.replay_audit import normalize_nick


def player_aliases():
    aliases = defaultdict(set)
    for player in Player.objects.select_related('name').prefetch_related('name__usernicknamehistoryitem_set'):
        names = [player.nickname]
        if player.name_id:
            names.extend(h.nickname for h in player.name.usernicknamehistoryitem_set.all())
        for name in names:
            if name and name.strip():
                aliases[normalize_nick(name)].add(player.pk)
    return aliases


def protocol_players(match):
    """Use the full protocol, not current team membership or only starting players."""
    home = set(match.team_home_start.values_list('pk', flat=True))
    away = set(match.team_guest_start.values_list('pk', flat=True))
    for player_id, team_id in match.match_participants.through.objects.filter(match=match).values_list(
        'player_id', 'team_id'
    ):
        if team_id == match.team_home_id:
            home.add(player_id)
        elif team_id == match.team_guest_id:
            away.add(player_id)
    for sub in match.match_substitutions.all():
        target = home if sub.team_id == match.team_home_id else away if sub.team_id == match.team_guest_id else None
        if target is not None:
            target.update(pk for pk in (sub.player_in_id, sub.player_out_id) if pk is not None)
    # Contradictory protocol identities cannot safely resolve side evidence.
    overlap = home & away
    return {'home': home - overlap, 'away': away - overlap}
