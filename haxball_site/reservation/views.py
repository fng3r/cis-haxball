from datetime import datetime, time, timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from tournament.models import Match, Team

from .models import Replay, ReservationEntry, ReservationHost
from .templatetags.reservation_extras import get_managed_teams


def get_reservatons_queryset():
    return (
        ReservationEntry.objects.filter(match__league__championship__is_active=True)
        .select_related(
            'match__team_home',
            'match__team_guest',
            'match__numb_tour',
            'match__league',
            'host',
        )
        .prefetch_related(
            'match__stage',
            'match__numb_tour__stage',
            'author__user_profile__user_icon',
            'author__user_profile__favorite_medals__medal__medal_type',
            'author__user_profile__favorite_medals__medal__season',
            'author__user_profile__favorite_medals__medal__league',
            'author__user_profile__favorite_medals__medal__player_medals',
            'author__user_player__medals',
            'cancelled_by__user_profile__user_icon',
            'cancelled_by__user_profile__favorite_medals__medal__medal_type',
            'cancelled_by__user_profile__favorite_medals__medal__season',
            'cancelled_by__user_profile__favorite_medals__medal__league',
            'cancelled_by__user_profile__favorite_medals__medal__player_medals',
            'cancelled_by__user_player__medals',
            'author__user_player__team__owner',
            'author__user_player__team__captain',
            'author__user_player__team__captain_assistant',
            'cancelled_by__user_player__team__owner',
            'cancelled_by__user_player__team__captain',
            'cancelled_by__user_player__team__captain_assistant',
            Prefetch(
                'author__owned_teams',
                queryset=Team.objects.filter(leagues__championship__is_active=True).distinct(),
                to_attr='active_owned_teams',
            ),
            Prefetch(
                'cancelled_by__owned_teams',
                queryset=Team.objects.filter(leagues__championship__is_active=True).distinct(),
                to_attr='active_owned_teams',
            ),
        )
        .order_by('-created')
    )


class ReservationList(ListView):
    template_name = 'reservation/reservation_list.html'

    def get(self, request, **kwargs):
        reservations = (
            ReservationEntry.objects.filter(match__is_played=False, is_cancelled=False)
            .select_related('match__team_home', 'match__team_guest', 'match__numb_tour', 'host')
            .prefetch_related('match__stage', 'match__numb_tour__stage')
            .order_by('time_date')
        )
        active_hosts = ReservationHost.objects.filter(is_active=True)
        all_reservations = get_reservatons_queryset()
        paginator = Paginator(all_reservations, 20)
        page = self.request.GET.get('page')
        all_reservations = paginator.get_page(page)

        if request.htmx:
            self.template_name = 'reservation/reservation_list.html#content-container'

        return render(
            request,
            self.template_name,
            {
                'reservations': reservations,
                'all_reservations': all_reservations,
                'active_hosts': active_hosts,
            },
        )

    def post(self, request):
        data = request.POST

        match_id = int(data['match'])
        host_id = int(data['match_host'])
        match_date = timezone.make_aware(
            datetime.combine(
                datetime.strptime(data['match_date'], '%Y-%m-%d').date(),
                time(hour=int(data['match_hour']), minute=int(data['match_minute'])),
            ),
            timezone.get_current_timezone(),
        )
        prev_match_date = match_date - timedelta(minutes=15)
        next_match_date = match_date + timedelta(minutes=15)

        if match_date <= timezone.now():
            messages.error(request, 'Дата и время бронирования должны быть больше текущего времени!')
            return redirect(reverse('reservation:host_reservation'))

        match = get_object_or_404(Match, pk=match_id)
        teams = [match.team_home, match.team_guest]
        teams_have_other_reservations = ReservationEntry.objects.filter(
            Q(match__team_home__in=teams) | Q(match__team_guest__in=teams),
            time_date__range=[prev_match_date, next_match_date],
            is_cancelled=False,
        ).exists()

        is_host_reserved = ReservationEntry.objects.filter(
            time_date__range=[prev_match_date, next_match_date],
            host_id=host_id,
            is_cancelled=False,
        ).exists()
        if is_host_reserved:
            messages.error(request, 'Выбранный хост занят в это время!')
        elif teams_have_other_reservations:
            messages.error(
                request,
                'Одна из команд уже имеет активную бронь в промежуток '
                + f'с {prev_match_date.strftime("%H:%M")} по {next_match_date.strftime("%H:%M")}',
            )
        else:
            ReservationEntry.objects.create(
                author=request.user, time_date=match_date, match_id=match_id, host_id=host_id
            )

        return redirect(reverse('reservation:host_reservation'))


class ReservationEvents(ListView):
    template_name = 'reservation/reservations_events.html'
    context_object_name = 'reservations'
    paginate_by = 20

    def get_queryset(self):
        return get_reservatons_queryset()

    def get_context_data(self, **kwargs):
        paginator = Paginator(self.get_queryset(), self.paginate_by)
        page = self.request.GET.get('page')
        reservations = paginator.get_page(page)

        context = super().get_context_data(**kwargs)
        context['reservations'] = reservations

        return context


class ReplaysList(ListView):
    queryset = Replay.objects.all().order_by('created')
    context_object_name = 'replays'
    template_name = 'reservation/replays_list.html'
    paginate_by = 20


@require_POST
def delete_entry(request, pk):
    reserved_match = get_object_or_404(ReservationEntry, pk=pk)
    user_teams = get_managed_teams(request.user)

    if (reserved_match.match.team_home in user_teams) or (reserved_match.match.team_guest in user_teams):
        reserved_match.cancelled_at = timezone.now()
        reserved_match.cancelled_by = request.user
        reserved_match.save(update_fields=['cancelled_at', 'cancelled_by'])
    else:
        messages.error(request, 'Ошибка доступа')

    return redirect(reverse('reservation:host_reservation'))
