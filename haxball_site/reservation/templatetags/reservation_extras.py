from datetime import timedelta

from django import template
from django.db.models import Count, Q
from django.utils import timezone
from tournament.models import Match, Team

from reservation.models import ReservationEntry, ReservationHost

register = template.Library()


def teams_can_reserve(user):
    try:
        a = user.user_player
    except:
        return False
    t = []
    if a.role == 'C' or a.role == 'AC':
        t.append(a.team)

    tt = Team.objects.filter(owner=user)
    active_teams = Team.objects.filter(leagues__championship__is_active=True)
    for i in tt:
        if i in active_teams:
            t.append(i)

    return t


@register.filter
def can_reserve_host(user):
    return bool(teams_can_reserve(user))


@register.inclusion_tag('reservation/reservation_form.html')
def reservation_form(user):
    teams = teams_can_reserve(user)
    today = timezone.localdate()
    tomorrow = today + timedelta(days=1)
    matches_to_choose = (
        Match.objects
        .annotate(reservations_count=Count('match_reservations', filter=Q(match_reservations__cancelled_at__isnull=True)))
        .filter(
            (Q(team_home__in=teams) | Q(team_guest__in=teams)),
            reservations_count=0,
            is_played=False,
            league__championship__is_active=True,
            numb_tour__date_from__lte=tomorrow,
        )
        .distinct()
        .order_by('league', 'numb_tour__number')
    )

    hosts = ReservationHost.objects.filter(is_active=True)

    hours_list = list(range(18, 24))
    minutes_list = [0, 15, 30, 45]
    return {
        'matches': matches_to_choose,
        'user': user,
        'date_today': today,
        'date_tomorrow': tomorrow,
        'hours_list': hours_list,
        'minutes_list': minutes_list,
        'hosts': hosts,
    }


@register.filter
def match_can_delete(user, reservation: ReservationEntry):
    if user.is_anonymous:
        return False
    try:
        user.user_player
    except:
        return False
    teams = teams_can_reserve(user)
    delt_time = reservation.time_date - timezone.now()
    
    return (
        (reservation.match.team_home in teams or reservation.match.team_guest in teams)
        and delt_time > timedelta(minutes=30)
    )


@register.filter
def match_dates(reserved):
    dates = set()
    for i in reserved:
        dates.add(i.time_date.date())
    return sorted(dates)


@register.filter
def cols_span(hosts):
    return round(100 / hosts)


@register.filter
def date_equal(date, day):
    return date.date() == day
