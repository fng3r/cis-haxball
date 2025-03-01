from django.utils import timezone
from online_users.models import OnlineUserActivity
from tournament.models import Match


def running_line_context(request):
    today = timezone.now().today()
    three_days_ago = today - timezone.timedelta(days=3)
    latest_matches = Match.objects.filter(is_played=True, match_date__range=[three_days_ago, today]).order_by(
        'league__priority', 'league__created', '-match_date'
    )
    base_duration = 15
    added_duration = 3 * latest_matches.count()
    animation_duration = base_duration + added_duration

    return {'latest_matches': latest_matches, 'animation_duration': animation_duration}


def online_users_context(request):
    user_activity_objects = OnlineUserActivity.get_user_activities(
        time_delta=timezone.timedelta(minutes=5)
    ).select_related('user__user_profile')
    users_online = [user_activity.user for user_activity in user_activity_objects]

    return {'users_online': users_online, 'users_online_count': len(users_online)}
