from django.utils import timezone

from tournament.models import Match


def running_line_context(request):
    today = timezone.now().today()
    three_days_ago = today - timezone.timedelta(days=3)
    latest_matches = (Match.objects
                      .filter(is_played=True, match_date__range=[three_days_ago, today])
                      .order_by('league__priority', 'league__created', '-match_date'))
    base_duration = 20
    added_duration = 3 * latest_matches.count()
    animation_duration = base_duration + added_duration

    return {'latest_matches': latest_matches, 'animation_duration': animation_duration}
