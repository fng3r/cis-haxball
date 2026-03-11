from __future__ import annotations

from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Min, Q

from core.models import Reaction, ReactionType


def _get_request_reactions_cache(request) -> dict[str, Any]:
    if request is None:
        return {}

    cache = getattr(request, '_reactions_cache', None)
    if cache is None:
        cache = {}
        setattr(request, '_reactions_cache', cache)

    return cache


def build_reactions_context(obj, user, *, request=None) -> dict[str, Any]:
    request_cache = _get_request_reactions_cache(request)
    content_type = ContentType.objects.get_for_model(obj)
    object_cache_key = (content_type.id, obj.pk, user.id if user.is_authenticated else 0)
    object_contexts = request_cache.setdefault('object_contexts', {})
    if object_cache_key in object_contexts:
        return object_contexts[object_cache_key]

    counts_rows = (
        Reaction.objects.filter(content_type=content_type, object_id=obj.pk)
        .values('reaction_type_id')
        .annotate(
            total=Count('id'),
            mine=Count('id', filter=Q(user=user)) if user.is_authenticated else Count('id', filter=Q(pk=-1)),
            first_created=Min('created'),
        )
    )
    counts = {row['reaction_type_id']: row['total'] for row in counts_rows}
    current_user_reaction_ids = {row['reaction_type_id'] for row in counts_rows if row['mine'] > 0}
    first_created_map = {row['reaction_type_id']: row['first_created'] for row in counts_rows}

    reaction_type_ids = list(counts.keys())
    if not reaction_type_ids:
        result = {
            'reaction_chips': [],
            'has_reactions': False,
        }
        object_contexts[object_cache_key] = result
        return result

    reaction_types_map = request_cache.get('reaction_types_map')
    if reaction_types_map is None:
        reaction_types_map = {}
        request_cache['reaction_types_map'] = reaction_types_map

    missing_ids = [
        reaction_type_id for reaction_type_id in reaction_type_ids if reaction_type_id not in reaction_types_map
    ]
    if missing_ids:
        for reaction_type in ReactionType.objects.filter(id__in=missing_ids):
            reaction_types_map[reaction_type.id] = reaction_type

    visible_types = [
        reaction_types_map[reaction_type_id]
        for reaction_type_id in reaction_type_ids
        if reaction_type_id in reaction_types_map
    ]
    visible_types.sort(
        key=lambda reaction_type: (
            first_created_map.get(reaction_type.id),
            reaction_type.id,
        )
    )

    chips = []
    for reaction_type in visible_types:
        chips.append(
            {
                'id': reaction_type.id,
                'code': reaction_type.code,
                'emoji': reaction_type.emoji,
                'label': reaction_type.name,
                'count': counts.get(reaction_type.id, 0),
                'selected': reaction_type.id in current_user_reaction_ids,
            }
        )

    result = {
        'reaction_chips': chips,
        'has_reactions': bool(chips),
    }
    object_contexts[object_cache_key] = result
    return result
