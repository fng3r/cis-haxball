from datetime import datetime, time, timedelta

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from .models import Replay, ReservationEntry, ReservationHost
from .templatetags.reservation_extras import teams_can_reserve


class ReservationList(ListView):
    queryset = ReservationEntry.objects.filter(match__is_played=False).order_by('time_date')
    context_object_name = 'reservations'
    template_name = 'reservation/reservation_list.html'

    def get_context_data(self, *, object_list=None, **kwargs):
        context = super(ReservationList, self).get_context_data()
        context['active_hosts'] = ReservationHost.objects.filter(is_active=True)
        return context

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

        reserved = ReservationEntry.objects.filter(time_date__range=[prev_match_date, next_match_date], host_id=host_id)
        if reserved.count() == 0:
            ReservationEntry.objects.create(
                author=request.user, time_date=match_date, match_id=match_id, host_id=host_id
            )
            return redirect('reservation:host_reservation')
        else:
            return render(
                request,
                'reservation/reservation_list.html',
                {
                    'reservations': ReservationEntry.objects.filter(match__is_played=False).order_by('-time_date'),
                    'active_hosts': ReservationHost.objects.filter(is_active=True),
                    'message': 'Выбранное время занято!!',
                },
            )


class ReplaysList(ListView):
    queryset = Replay.objects.all().order_by('created')
    context_object_name = 'replays'
    template_name = 'reservation/replays_list.html'
    paginate_by = 20


@require_POST
def delete_entry(request, pk):
    reserved_match = get_object_or_404(ReservationEntry, pk=pk)
    t = teams_can_reserve(request.user)

    if (reserved_match.match.team_home in t) or (reserved_match.match.team_guest in t):
        reserved_match.delete()
        return redirect('reservation:host_reservation')
    else:
        return HttpResponse('Ошибка доступа')
