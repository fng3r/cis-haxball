import logging

from django.utils import timezone

from notifications.models import Notification
from online_users.models import OnlineUserActivity

from core.services.youtube import YoutubeService
from haxball_site import settings
from reservation.models import ReservationEntry
from tournament.models import Match

logger = logging.getLogger('haxball_site')


def latest_matches_context(request):
    today = timezone.now().today()
    three_days_ago = today - timezone.timedelta(days=3)
    latest_matches = (
        Match.objects.filter(is_played=True, match_date__range=[three_days_ago, today])
        .order_by('-match_date', 'league__priority')
        .select_related('league', 'stage', 'numb_tour', 'team_home', 'team_guest')
    )

    return {'latest_matches': latest_matches}


def upcoming_matches_context(request):
    today = timezone.localdate()
    upcoming_matches = (
        ReservationEntry.objects.filter(
            time_date__range=[today, today + timezone.timedelta(days=2)], is_cancelled=False
        )
        .order_by('time_date', 'match__league__priority')
        .select_related(
            'match', 'match__league', 'match__stage', 'match__numb_tour', 'match__team_home', 'match__team_guest'
        )
    )

    return {'upcoming_matches': upcoming_matches}


def online_users_context(request):
    user_activity_objects = OnlineUserActivity.get_user_activities(
        time_delta=timezone.timedelta(minutes=5)
    ).select_related('user__user_profile')

    users_online = [
        user_activity.user
        for user_activity in user_activity_objects
        if not (user_activity.user.user_profile.invisibility_enabled)
    ]

    return {'users_online': users_online, 'users_online_count': len(users_online)}


def notifications_context(request):
    """
    Add unread notifications to the context for all templates.
    """
    context = {}
    if request.user.is_authenticated:
        context['user_notifications'] = Notification.objects.filter(
            recipient=request.user,
            unread=True,
        ).order_by('-timestamp')[:10]
        context['unread_count'] = Notification.objects.filter(recipient=request.user, unread=True).count()
    return context


def youtube_context(request):
    """
    Add featured YouTube videos to the context for all templates.
    """
    try:
        youtube_service = YoutubeService()
        livestreams = youtube_service.search_channel_livestreams(settings.YOUTUBE_CHANNEL_ID)
        videos = youtube_service.get_videos_by_ids(settings.YOUTUBE_FEATURED_VIDEO_IDS)

        return {
            'livestreams': (livestreams['active'] + livestreams['completed'])[:2],
            'featured_videos': videos[:2],
        }
    except Exception as e:
        logger.error(f'Error fetching YouTube videos and livestreams for sidebars: {str(e)}')
        return {'featured_videos': [], 'livestreams': []}


def themes_context(request):
    """
    Add available themes to the context for all templates.
    """
    themes = [
        {'value': 'light', 'label': 'Default'},
        {'value': 'dark', 'label': 'Dark'},
        {'value': 'cupcake', 'label': 'Cupcake'},
        {'value': 'bumblebee', 'label': 'Bumblebee'},
        {'value': 'emerald', 'label': 'Emerald'},
        {'value': 'corporate', 'label': 'Corporate'},
        {'value': 'synthwave', 'label': 'Synthwave'},
        {'value': 'retro', 'label': 'Retro'},
        {'value': 'cyberpunk', 'label': 'Cyberpunk'},
        {'value': 'valentine', 'label': 'Valentine'},
        {'value': 'halloween', 'label': 'Halloween'},
        {'value': 'garden', 'label': 'Garden'},
        {'value': 'forest', 'label': 'Forest'},
        {'value': 'aqua', 'label': 'Aqua'},
        {'value': 'lofi', 'label': 'Lofi'},
        {'value': 'pastel', 'label': 'Pastel'},
        {'value': 'fantasy', 'label': 'Fantasy'},
        {'value': 'wireframe', 'label': 'Wireframe'},
        {'value': 'black', 'label': 'Black'},
        {'value': 'luxury', 'label': 'Luxury'},
        {'value': 'dracula', 'label': 'Dracula'},
        {'value': 'cmyk', 'label': 'CMYK'},
        {'value': 'autumn', 'label': 'Autumn'},
        {'value': 'business', 'label': 'Business'},
        {'value': 'acid', 'label': 'Acid'},
        {'value': 'lemonade', 'label': 'Lemonade'},
        {'value': 'night', 'label': 'Night'},
        {'value': 'coffee', 'label': 'Coffee'},
        {'value': 'winter', 'label': 'Winter'},
        {'value': 'dim', 'label': 'Dim'},
        {'value': 'nord', 'label': 'Nord'},
        {'value': 'sunset', 'label': 'Sunset'},
    ]
    return {'themes': themes}


def settings_context(request):
    return {'project_settings': settings}
