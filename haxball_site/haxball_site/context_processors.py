from django.utils import timezone
from online_users.models import OnlineUserActivity
from reservation.models import ReservationEntry
from tournament.models import Match


def latest_matches_context(request):
    today = timezone.now().today()
    three_days_ago = today - timezone.timedelta(days=3)
    latest_matches = (
        Match.objects
        .filter(is_played=True, match_date__range=[three_days_ago, today])
        .order_by('league__priority', 'league__created', '-match_date')
        .select_related('league', 'stage', 'numb_tour', 'team_home', 'team_guest')
    )
    
    return {'latest_matches': latest_matches}


def upcoming_matches_context(request):
    today = timezone.localdate()
    upcoming_matches = (
        ReservationEntry.objects
        .filter(time_date__range=[today, today + timezone.timedelta(days=2)])
        .order_by('time_date', 'match__league__priority',)
        .select_related(
            'match', 'match__league', 'match__stage', 'match__numb_tour', 'match__team_home', 'match__team_guest'
        )
    )
    
    return {'upcoming_matches': upcoming_matches}


def online_users_context(request):
    user_activity_objects = OnlineUserActivity.get_user_activities(
        time_delta=timezone.timedelta(minutes=5)
    ).select_related('user__user_profile')
    users_online = [user_activity.user for user_activity in user_activity_objects]

    return {'users_online': users_online, 'users_online_count': len(users_online)}
