from datetime import datetime, time, timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from .models import Replay, ReservationEntry, ReservationHost
from .templatetags.reservation_extras import teams_can_reserve


class ReservationList(ListView):
    template_name = 'reservation/reservation_list.html'

    def get(self, request, **kwargs):
        reservations = (
            ReservationEntry.objects
            .filter(match__is_played=False, cancelled_at__isnull=True)
            .select_related('match__team_home', 'match__team_guest', 'match__numb_tour',
                            'match__stage', 'match__numb_tour__stage', 'host')
            .order_by('time_date')
        )
        active_hosts = ReservationHost.objects.filter(is_active=True)
        all_reservations = (
            ReservationEntry.objects
            .filter(match__league__championship__is_active=True)
            .select_related(
                'match__team_home', 'match__team_guest', 'match__numb_tour',
                'match__league', 'match__stage', 'match__numb_tour__stage', 'host',
            )
            .prefetch_related('author__user_profile__user_icon', 'cancelled_by__user_profile__user_icon')
            .order_by('-created')
        )
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
        match_date = datetime.combine(
            datetime.strptime(data['match_date'], '%Y-%m-%d').date(),
            time(hour=int(data['match_hour']), minute=int(data['match_minute'])),
        )
        prev_match_date = match_date - timedelta(minutes=29)
        next_match_date = match_date + timedelta(minutes=29)

        reserved = ReservationEntry.objects.filter(
            time_date__range=[prev_match_date, next_match_date],
            host_id=host_id,
            cancelled_at__isnull=True,
        )
        if not reserved.exists():
            ReservationEntry.objects.create(
                author=request.user, time_date=match_date, match_id=match_id, host_id=host_id
            )
        else:
            messages.error(request, 'Выбранное время занято!')

        return redirect(reverse('reservation:host_reservation'))


class ReservationEvents(ListView):
    template_name = 'reservation/reservations_events.html'
    context_object_name = 'reservations'
    paginate_by = 20

    def get_queryset(self):
        return (
            ReservationEntry.objects
            .filter(match__league__championship__is_active=True)
            .select_related(
                'match__team_home', 'match__team_guest', 'match__numb_tour',
                'match__league', 'match__stage', 'match__numb_tour__stage', 'host',
            )
            .prefetch_related('author__user_profile__user_icon', 'cancelled_by__user_profile__user_icon')
            .order_by('-created')
        )
    
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
    user_teams = teams_can_reserve(request.user)

    if (reserved_match.match.team_home in user_teams) or (reserved_match.match.team_guest in user_teams):
        reserved_match.cancelled_at = timezone.now()
        reserved_match.cancelled_by = request.user
        reserved_match.save(update_fields=['cancelled_at', 'cancelled_by'])
    else:
        messages.error(request, 'Ошибка доступа')

    return redirect(reverse('reservation:host_reservation'))
