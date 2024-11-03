from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.db.models import Prefetch

from .models import LikeDislike, NewComment


def get_comments_for_object(model, obj_id):
    prefetch_likes = Prefetch(
        'votes',
        queryset=LikeDislike.objects.likes().prefetch_related('user__user_profile__user_icon'),
        to_attr='likes'
    )
    prefetch_dislikes = Prefetch(
        'votes',
        queryset=LikeDislike.objects.dislikes().prefetch_related('user__user_profile__user_icon'),
        to_attr='dislikes'
    )

    return (
        prefetch_recursively(
            'author__user_profile__user_icon',
            prefetch_likes,
            prefetch_dislikes,
        )
        .filter(content_type=ContentType.objects.get_for_model(model), object_id=obj_id, parent=None)
    )


def get_paginated_comments(comments, page, per_page=20):
    paginator = Paginator(comments, per_page)

    return paginator.get_page(page)


def prefetch_recursively(*prefetches, depth=15):
    qs = NewComment.objects.prefetch_related(*prefetches)
    
    current_depth = 1
    while current_depth < depth:
        children_prefix = 'childs' + '__childs' * (current_depth - 1)
        qs = qs.prefetch_related(
            Prefetch(
                children_prefix,
                queryset=NewComment.objects.prefetch_related(*prefetches)
            )
        )
        current_depth += 1
        
    return qs
