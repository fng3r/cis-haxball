from django.utils import timezone

from tournament.models import Match


def running_line_context(request):
    today = timezone.now().today()
    two_days_ago = today - timezone.timedelta(days=2)
    latest_matches = Match.objects.filter(is_played=True, match_date__range=[two_days_ago, today]).order_by('-match_date')
    animation_duration = 20 + 3 * latest_matches.count()

    return {'latest_matches': latest_matches, 'animation_duration': animation_duration}
