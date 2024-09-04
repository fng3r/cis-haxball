from datetime import date, datetime

from django import template
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Page
from django.db.models import Count, Prefetch, Q
from django.utils import timezone
from online_users.models import OnlineUserActivity
from tournament.models import League, Player, PlayerTransfer, Team

from haxball_site import settings

from ..models import NewComment, Post, Subscription

register = template.Library()


@register.filter
def get_class(value):
    return value.__class__.__name__


@register.filter
def subtract(value, arg):
    return value - arg


# тег для поискса кармы юзера(профиля), будем писать в профиль
# !!Пока что ищет ток по комментам карму, хз, могу допилить и по постам!
# ! Добавил и по постам
"""
@register.inclusion_tag('core/include/profile/karma.html')
def karma(profile):
    s = 0
    samo = 0
    for comment in Comment.objects.filter(author=profile.name):
        s += comment.votes.sum_rating()
        samo += comment.votes.filter(user=profile.name, vote=1).count() - comment.votes.filter(user=profile.name,
                                                                                               vote=-1).count()
    for post in Post.objects.filter(author=profile.name):
        s += post.votes.sum_rating()
        samo += post.votes.filter(user=profile.name, vote=1).count() - post.votes.filter(user=profile.name,
                                                                                         vote=-1).count()
    print(profile.karma)
    profile.karma = s - samo
    profile.save(update_fields=['karma'])
    return {'k': s - samo}
"""


# Упоролся и написал своё вычисление возраста 1 цифрой, т.к. встроенный
# таймсинс обрезает с месяцами... хз, надо доработать будет, чтобы писало возраст красиво, но хз зачем так из-за такой
# мелочи упарываться
@register.simple_tag
def age(born_date):
    if date.today().month > born_date.month:
        return date.today().year - born_date.year
    if born_date.month == date.today().month and date.today().day > born_date.day:
        return date.today().year - born_date.year

    return date.today().year - born_date.year - 1


@register.filter
def can_edit(comment: NewComment):
    return timezone.now() - comment.created < timezone.timedelta(minutes=settings.EDIT_COMMENT_TIME_LIMIT)


@register.filter
def exceeds_edit_limit(comment: NewComment):
    return comment.version > settings.EDIT_COMMENT_LIMIT


@register.inclusion_tag('core/include/profile/last_actuvity.html')
def user_last_activity(user):
    try:
        user_activity = OnlineUserActivity.objects.get(user=user)
        is_online = timezone.now() - user_activity.last_activity < timezone.timedelta(minutes=15)
    except:
        return None

    return {'last_seen': user_activity.last_activity, 'is_online': is_online}


# Тег для отображения последней активности на форуме
@register.inclusion_tag('core/include/forum/last_activity_in_category.html')
def forum_last_activity(category):
    last_post = Post.objects.filter(category=category).order_by('-created').first()
    last_comment = (
        NewComment.objects.filter(
            content_type=ContentType.objects.get_for_model(Post), post_comments__category=category
        )
        .order_by('-created')
        .first()
    )

    if last_comment is None and last_post is None:
        return {'last_act': None}
    if last_comment is None:
        return {'last_act': last_post.created}
    if last_post is None:
        return {'last_act': last_comment.created}

    if last_comment.created > last_post.created:
        return {'last_act': last_comment.created}

    return {'last_act': last_post.created}


# Сайдбар для пользователей онлайн(по дефолту 15 минут)
@register.inclusion_tag('core/include/sidebar_for_users.html')
def show_users_online():
    user_activity_objects = OnlineUserActivity.get_user_activities(
        time_delta=timezone.timedelta(minutes=5)
    ).select_related('user__user_profile')
    users_online_count = user_activity_objects.count()
    users_online = (user.user for user in user_activity_objects)

    return {'users_online': users_online, 'users_online_count': users_online_count}


# Сайд-бар для last activity (выводит последние оставленные комментарии
# но максимум 1 для каждого поста(если 3 коммента в одном посте были последними - выведет 1)
@register.inclusion_tag('core/include/sidebar_for_last_activity.html')
def show_last_activity(count=10):
    # Последняя активность ваще везде-везде
    latest_comments = (
        NewComment.objects.select_related('author')
        .prefetch_related('content_object', 'content_object__comments')
        .order_by('-created')[:150]
    )
    selected_objects = set()
    last_comments = []
    for comment in latest_comments:
        if len(selected_objects) >= count:
            break

        if comment.content_object in selected_objects:
            continue

        last_comments.append(comment)
        selected_objects.add(comment.content_object)

    return {'last_comments': last_comments}


# Топ лайков за ТЕКУЩИЙ день, неделя, месяц, год
@register.inclusion_tag('core/include/sidebar_for_top_comments.html')
def show_top_comments(count=5):
    my_date = datetime.now()
    year, week, day_of_week = my_date.isocalendar()
    day = my_date.day
    month = my_date.month

    comments = (
        NewComment.objects.select_related('author')
        .prefetch_related('votes', 'content_object', 'content_object__comments')
        .annotate(likes_count=Count('votes', filter=Q(votes__vote__gt=0)))
        .annotate(dislikes_count=Count('votes', filter=Q(votes__vote__lt=0)))
    )

    top_com_today = comments.filter(created__year=year, created__month=month, created__day=day).order_by(
        '-likes_count'
    )[:count]
    top_com_month = comments.filter(created__year=year, created__month=month).order_by('-likes_count')[:count]
    top_com_year = comments.filter(created__year=year).order_by('-likes_count')[:count]

    week_start = my_date - timezone.timedelta(days=day_of_week - 1, hours=my_date.hour, minutes=my_date.minute)

    week_end = my_date + timezone.timedelta(days=7 - day_of_week, hours=23 - my_date.hour, minutes=60 - my_date.minute)
    top_com_week = comments.filter(created__gt=week_start, created__lt=week_end).order_by('-likes_count')[:count]

    return {
        'top_comments_day': top_com_today,
        'top_comments_month': top_com_month,
        'top_comments_year': top_com_year,
        'top_comments_week': top_com_week,
    }


# Сайд-бар для отображеня топа лайков постов за всё время
# (Потом надо будет переделать, чтобы в параметр передавать за какое время, для переключения)
@register.inclusion_tag('core/include/sidebar_for_likes.html')
def show_post_with_top_likes(count=5):
    posts = (
        Post.objects.annotate(like_count=Count('votes', filter=Q(votes__vote__gt=0)))
        .annotate(dislike_count=Count('votes', filter=Q(votes__vote__lt=0)))
        .filter(created__year=2020)
        .order_by('-like_count')[:count]
    )

    return {'liked_posts': posts}


# Фильтр, возращающий свежий ли пост или нет в зависимости от оффсета
@register.filter
def is_fresh(value, hours):
    x = timezone.now() - value
    if x.days >= 1:
        return False
    sec = 3600 * hours
    return x.seconds < sec


# Фильтр для проверки юзера в объекте(Типа, если лайк уже ставил или диз)
# except на ТайпЕррор, надо бы добавить, а то НоН обжект хэв но филтер ёба
@register.filter
def user_in(objects, user):
    if user.is_authenticated:
        try:
            return objects.filter(user=user).exists()
        except:
            return False
    return False


@register.filter
def user_in_list(objects, user):
    if objects and user.is_authenticated:
        return any(obj.user == user for obj in objects)

    return False


@register.filter
def can_edit_profile_bg(user: User):
    if user.is_superuser:
        return True

    subscriptions = Subscription.objects.by_user(user).active().order_by('tier')
    return subscriptions.count() > 0


@register.filter
def is_executive(user: User, leagues):
    try:
        player = user.user_player
    except:
        return False

    has_team_in_leagues = Player.objects.filter(id=player.id, team__leagues__in=leagues).exists()
    if has_team_in_leagues and (player.role == Player.CAPTAIN or player.role == Player.ASSISTENT):
        return True

    is_owner = Team.objects.filter(owner=user, leagues__in=leagues).exists()

    return is_owner


@register.filter
def usernames_list(likes):
    return ', '.join(map(lambda like: like.user.username, likes))


@register.filter
def can_view_likes_details(user: User):
    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    subscriptions = Subscription.objects.by_user(user).active().order_by('tier')
    return subscriptions.count() > 0


@register.filter
def get_likes(comment: NewComment):
    if hasattr(comment, 'likes'):
        return comment.likes

    return comment.votes.likes()


@register.filter
def get_dislikes(comment: NewComment):
    if hasattr(comment, 'dislikes'):
        return comment.dislikes

    return comment.votes.dislikes()


@register.filter
def likes_count(comment: NewComment):
    if hasattr(comment, 'likes'):
        return len(comment.likes)

    return comment.votes.likes().count()


@register.filter
def dislikes_count(comment: NewComment):
    if hasattr(comment, 'dislikes'):
        return len(comment.dislikes)

    return comment.votes.dislikes().count()


@register.inclusion_tag('core/include/teams_in_navbar.html')
def teams_in_navbar():
    primary_leagues = ['Высшая лига', 'Первая лига', 'Вторая лига']
    leagues = (
        League.objects.filter(title__in=primary_leagues, championship__is_active=True)
        .prefetch_related(Prefetch('teams', queryset=Team.objects.order_by('title')))
        .order_by('priority')
    )

    return {'leagues': leagues}


@register.filter
def pages_to_show(page: Page):
    pages_show_count = 15
    pages_total = page.paginator.num_pages
    if pages_total <= pages_show_count:
        yield from range(1, pages_total + 1)
        return

    is_page_at_start = page.number <= pages_show_count // 2
    is_page_at_end = pages_total - page.number <= pages_show_count // 2

    # selected page is in the middle
    if not is_page_at_start and not is_page_at_end:
        pages_show_count -= 4
        yield 1
        yield None
        yield from range(page.number - pages_show_count // 2, page.number + pages_show_count // 2 + 1)
        yield None
        yield page.paginator.num_pages
        return

    if is_page_at_start:
        pages_show_count -= 2
        pages_before = page.number - 1
        pages_after = pages_show_count - pages_before - 1
        yield from range(1, page.number + pages_after + 1)
        yield None
        yield pages_total
        return

    if is_page_at_end:
        pages_show_count -= 2
        pages_after = pages_total - page.number
        pages_before = pages_show_count - pages_after - 1
        yield 1
        yield None
        yield from range(page.number - pages_before, pages_total + 1)
        return


@register.inclusion_tag('core/include/sidebar_for_transfers.html')
def show_last_transfers():
    from_date = datetime(2024, 3, 13)
    last_transfers = (
        PlayerTransfer.objects.select_related('trans_player__name__user_profile', 'from_team', 'to_team')
        .filter(season_join__is_active=True, date_join__gte=from_date, is_technical=False)
        .order_by('-date_join', '-id')[:5]
    )

    return {'transfers': last_transfers}
