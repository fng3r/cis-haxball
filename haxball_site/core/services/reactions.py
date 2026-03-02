from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q

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

    active_types = request_cache.get('active_types')
    if active_types:
        print('active_types cached')
    if active_types is None:
        active_types = list(ReactionType.objects.filter(is_active=True).order_by('sort_order', 'id'))
        request_cache['active_types'] = active_types

    time_start = time.time()
    print(f'{time_start - request_cache.get("time_end", 0)} before counts_rows')
    counts_rows = (
        Reaction.objects.filter(content_type=content_type, object_id=obj.pk)
        .values('reaction_type_id')
        .annotate(
            total=Count('id'),
            mine=Count('id', filter=Q(user=user)) if user.is_authenticated else Count('id', filter=Q(pk=-1)),
        )
    )
    counts = {row['reaction_type_id']: row['total'] for row in counts_rows}
    current_user_reaction_ids = {row['reaction_type_id'] for row in counts_rows if row['mine'] > 0}

    visible_types = [reaction_type for reaction_type in active_types if counts.get(reaction_type.id, 0) > 0]
    visible_types.sort(
        key=lambda reaction_type: (-counts.get(reaction_type.id, 0), reaction_type.sort_order, reaction_type.id)
    )

    for reaction_type in active_types:
        if reaction_type.id in current_user_reaction_ids and reaction_type.id not in {
            item.id for item in visible_types
        }:
            visible_types.insert(0, reaction_type)

    chips = []
    for reaction_type in visible_types:
        chips.append(
            {
                'id': reaction_type.id,
                'code': reaction_type.code,
                'emoji': reaction_type.emoji,
                'label': reaction_type.label,
                'count': counts.get(reaction_type.id, 0),
                'selected': reaction_type.id in current_user_reaction_ids,
            }
        )

    picker = []
    for reaction_type in active_types:
        picker.append(
            {
                'id': reaction_type.id,
                'code': reaction_type.code,
                'emoji': reaction_type.emoji,
                'label': reaction_type.label,
                'category': reaction_type.category or 'Other',
                'selected': reaction_type.id in current_user_reaction_ids,
            }
        )

    picker_groups_map: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for item in picker:
        picker_groups_map.setdefault(item['category'], []).append(item)

    picker_groups = [
        {
            'id': f'group-{index}',
            'category': category,
            'icon': items[0]['emoji'] if items else '•',
            'items': items,
        }
        for index, (category, items) in enumerate(picker_groups_map.items(), start=1)
    ]
    time_end = time.time()
    request_cache['time_end'] = time_end
    print(f'build_reactions_context time: {time_end - time_start:} seconds')

    result = {
        'reaction_chips': chips,
        'picker_reactions': picker,
        'picker_groups': picker_groups,
        'current_user_reactions': [],
        'total_reactions': sum(counts.values()),
    }
    object_contexts[object_cache_key] = result
    return result
