from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.db.models import Prefetch

from tournament.models import Team

from .models import LikeDislike, NewComment


def strtobool(val: str) -> bool:
    """Convert a string representation of truth to true (1) or false (0).

    True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
    are 'n', 'no', 'f', 'false', 'off', and '0'.  Raises ValueError if
    'val' is anything else.
    """
    val = val.lower()
    if val in ('y', 'yes', 't', 'true', 'on', '1'):
        return True

    if val in ('n', 'no', 'f', 'false', 'off', '0'):
        return False

    raise ValueError(f'invalid truth value {val!r}')


def get_comments_for_object(model, obj_id):
    prefetch_likes = Prefetch(
        'votes',
        queryset=LikeDislike.objects.likes().prefetch_related('user__user_profile__user_icon'),
        to_attr='likes',
    )
    prefetch_dislikes = Prefetch(
        'votes',
        queryset=LikeDislike.objects.dislikes().prefetch_related('user__user_profile__user_icon'),
        to_attr='dislikes',
    )
    prefetch_owned_teams = Prefetch(
        'author__owned_teams',
        queryset=Team.objects.filter(leagues__championship__is_active=True).distinct(),
        to_attr='active_owned_teams',
    )

    return prefetch_recursively(
        'content_object',
        'author__user_profile__user_icon',
        'author__user_player__team__owner',
        'author__user_player__team__captain',
        'author__user_player__team__captain_assistant',
        prefetch_owned_teams,
        prefetch_likes,
        prefetch_dislikes,
    ).filter(content_type=ContentType.objects.get_for_model(model), object_id=obj_id, parent=None)


def get_paginated_comments(comments, page, per_page=20):
    paginator = Paginator(comments, per_page)

    return paginator.get_page(page)


def prefetch_recursively(*prefetches, depth=15):
    qs = NewComment.objects.prefetch_related(*prefetches)

    current_depth = 1
    while current_depth < depth:
        children_prefix = 'childs' + '__childs' * (current_depth - 1)
        qs = qs.prefetch_related(Prefetch(children_prefix, queryset=NewComment.objects.prefetch_related(*prefetches)))
        current_depth += 1

    return qs
