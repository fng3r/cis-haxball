from django.contrib.contenttypes.models import ContentType
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Prefetch

from .models import LikeDislike, NewComment


def get_comments_for_object(model, obj_id):
    prefetch_likes = Prefetch(
        'votes', queryset=LikeDislike.objects.likes().prefetch_related('user__user_profile'), to_attr='likes'
    )
    prefetch_dislikes = Prefetch(
        'votes', queryset=LikeDislike.objects.dislikes().prefetch_related('user__user_profile'), to_attr='dislikes'
    )
    comments = (
        NewComment.objects.select_related('author__user_profile')
        .prefetch_related(
            'author__user_profile__user_icon',
            'childs__author__user_profile__user_icon',
            # tweak for prefetching recursive field
            'childs__childs__childs__childs__childs',
            prefetch_likes,
            prefetch_dislikes,
        )
        .filter(content_type=ContentType.objects.get_for_model(model), object_id=obj_id, parent=None)
    )

    return comments


def get_paginated_comments(comments, page, per_page=20):
    paginator = Paginator(comments, per_page)

    try:
        comments = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer deliver the first page
        comments = paginator.page(1)
    except EmptyPage:
        # If page is out of range deliver last page of results
        comments = paginator.page(paginator.num_pages)

    return comments
