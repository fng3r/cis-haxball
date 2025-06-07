from datetime import timedelta

from django import template
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.utils import timezone

from reservation.models import ReservationEntry, ReservationHost
from tournament.models import Match, Player, Team

register = template.Library()


def get_managed_teams(user: User):
    try:
        player: Player = user.user_player
    except:
        return []
    teams = []
    current_team = player.team
    if current_team is not None and (player == current_team.captain or player == current_team.captain_assistant):
        teams.append(current_team)

    owned_teams = Team.objects.filter(owner=user, leagues__championship__is_active=True)
    for team in owned_teams:
        teams.append(team)

    return teams


@register.filter
def can_reserve_host(user):
    return len(get_managed_teams(user)) > 0


@register.inclusion_tag('reservation/reservation_form.html')
def reservation_form(user):
    teams = get_managed_teams(user)
    today = timezone.localdate()
    tomorrow = today + timedelta(days=1)
    matches_to_choose = (
        Match.objects.annotate(
            reservations_count=Count('match_reservations', filter=Q(match_reservations__is_cancelled=False))
        )
        .filter(
            Q(team_home__in=teams) | Q(team_guest__in=teams),
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
def can_cancel_reservation(user: User, reservation: ReservationEntry):
    if user.is_anonymous:
        return False
    try:
        user.user_player
    except:
        return False
    teams = get_managed_teams(user)
    delt_time = reservation.time_date - timezone.now()

    # fmt: off
    return (
        (reservation.match.team_home in teams or reservation.match.team_guest in teams)
        and delt_time > timedelta(minutes=30)
    )
    # fmt: on


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
