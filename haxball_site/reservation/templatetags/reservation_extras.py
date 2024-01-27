from datetime import timedelta

from django import template
from django.db.models import Q
from django.db.models.functions import datetime
from django.utils import timezone
from tournament.models import Player, Team, League, TourNumber, Match
from reservation.models import ReservationHost

register = template.Library()


def teams_can_reserv(user):
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
def user_can_reserv(user):
    if teams_can_reserv(user):
        return True
    else:
        return False


@register.inclusion_tag('reservation/reservation_form.html')
def reservation_form(user):
    t = teams_can_reserv(user)
    actual_tour = TourNumber.objects.filter(league__championship__is_active=True, is_actual=True,
                                            league__teams__in=t).distinct()

    if actual_tour is None:
        return {
            'matches': []
        }

    # Матчи, которые можно будет выбрать
    matches_to_choose = []

    # Просматриваем все активные туры и смотрим матчи, которые не сыграны и на которых нету брони
    for tour in actual_tour:
        matches_unplayed = \
            (Match.objects
                .filter((Q(team_home__in=t) | Q(team_guest__in=t)), is_played=False,
                        numb_tour__number__lte=tour.number, league=tour.league,
                        match_reservation=None)
                .distinct()
                .order_by('-numb_tour__number'))
        matches_to_choose.extend(matches_unplayed)

    hosts = ReservationHost.objects.filter(is_active=True)
    today = datetime.datetime.today().date()
    tomorrow = today + timedelta(days=1)
    hours_list = list(range(18, 24))
    minutes_list = [0, 15, 30, 45]
    return {
        'matches': matches_to_choose,
        'user': user,
        'date_today': today,
        'date_tomorrow': tomorrow,
        'hours_list': hours_list,
        'minutes_list': minutes_list,
        'hosts': hosts
    }


@register.filter
def match_can_delete(user, match):
    if user.is_anonymous:
        return False
    try:
        a = user.user_player
    except:
        return False
    t = teams_can_reserv(user)
    delt_time = match.match_reservation.time_date - timezone.now()
    if ((match.team_home in t) or (match.team_guest in t)) and delt_time > timedelta(minutes=30):
        return True
    else:
        return False


@register.filter
def match_dates(reserved):
    datess = set()
    for i in reserved:
        datess.add(i.time_date.date())
    # dats = [datess]
    return sorted(datess)


@register.filter
def cols_span(hosts):
    return round(100 / hosts)


@register.filter
def date_equal(date, day):
    if date.date() == day:
        return True
    else:
        return False


@register.filter
def round_name(tour, all_tours):
    if tour == all_tours:
        return 'Финал'
    elif tour == all_tours - 1:
        return '1/2 Финала'
    elif tour == all_tours - 2:
        return '1/4 Финала'
    elif tour == all_tours - 3:
        return '1/8 Финала'
    else:
        return '{} Раунд'.format(tour)


'''
@register.filter
def match_can_reserv(user):
    t = teams_can_reserv(user)
    actual_tour = TourNumber.objects.filter(league__championship__is_active=True, is_actual=True).first()

    matches_unplayed = Match.objects.filter((Q(team_home__in=t) | Q(team_guest__in=t)), is_played=False,
                                            numb_tour__number__lte=actual_tour.number,
                                            )
    return matches_unplayed
'''
