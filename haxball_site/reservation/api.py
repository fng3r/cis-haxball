import re
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from tournament.match_context import PublicMatchContext

from .models import ReservationEntry


@require_GET
def reservations(request):
    dates = request.GET.getlist('date')
    try:
        if len(dates) != 1 or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', dates[0]):
            raise ValueError
        day = date.fromisoformat(dates[0])
        site_timezone = timezone.get_default_timezone()
        start = timezone.make_aware(datetime.combine(day, time.min), site_timezone)
        end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min), site_timezone)
    except (ValueError, OverflowError):
        return JsonResponse({'error': 'Provide one valid date in YYYY-MM-DD format (before 9999-12-31).'}, status=400)

    entries = (
        ReservationEntry.objects.filter(
            time_date__gte=start,
            time_date__lt=end,
            is_cancelled=False,
            match__is_played=False,
            host__is_active=True,
        )
        .select_related(
            'host',
            'match__team_home',
            'match__team_guest',
            'match__league__championship',
            'match__stage__league',
            'match__group',
            'match__numb_tour__stage__playoffstage',
        )
        .order_by('time_date', 'pk')
    )
    entries = list(entries)
    context = PublicMatchContext(entry.match for entry in entries)
    return JsonResponse(
        {
            'date': day.isoformat(),
            'timezone': settings.TIME_ZONE,
            'reservations': [
                {
                    'id': entry.pk,
                    'startsAt': timezone.localtime(entry.time_date, site_timezone).isoformat(),
                    'host': {'codename': entry.host.codename, 'name': entry.host.name},
                    **context.serialize(entry.match),
                }
                for entry in entries
            ],
        }
    )
