import operator
from collections import defaultdict
from datetime import datetime, time, timedelta
from functools import reduce

from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db.models import Count, F, Q, Sum
from django.urls import reverse
from django.views.decorators.http import require_POST
from django_filters import FilterSet, ModelChoiceFilter, ChoiceFilter
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import ListView, DetailView

from .forms import FreeAgentForm, EditTeamProfileForm
from .models import FreeAgent, Team, Match, League, Player, Substitution, Season, OtherEvents, Disqualification, \
    Postponement
from core.forms import NewCommentForm
from core.models import NewComment, Profile

from .templatetags.tournament_extras import get_user_teams


class DisqualificationFilter(FilterSet):
    team = ModelChoiceFilter(queryset=Team.objects.filter(leagues__championship__is_active=True).distinct())

    class Meta:
        model = Disqualification
        fields = ['team']


class DisqualificationsList(ListView):
    queryset = Disqualification.objects.filter(match__league__championship__is_active=True).order_by('-created')
    context_object_name = 'disqualifications'
    template_name = 'tournament/disqualification/disqualifications_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        print(self.request.GET)
        context['filter'] = DisqualificationFilter(self.request.GET, queryset=self.queryset)

        return context


class FreeAgentList(ListView):
    queryset = FreeAgent.objects.filter(is_active=True).order_by('-created')
    context_object_name = 'agents'
    template_name = 'tournament/free_agent/free_agents_list.html'

    def post(self, request):
        if request.method == 'POST':
            try:
                fa = FreeAgent.objects.get(player=request.user)
                fa_form = FreeAgentForm(data=request.POST, instance=fa)
                if fa_form.is_valid():
                    fa = fa_form.save(commit=False)
                    fa.created = timezone.now()
                    fa.is_active = True
                    fa.save()
                    agents = FreeAgent.objects.filter(is_active=True).order_by('-created')
                    return redirect('tournament:free_agent')
            except:
                fa_form = FreeAgentForm(data=request.POST)
                if fa_form.is_valid():
                    fa = fa_form.save(commit=False)
                    fa.player = request.user
                    fa.created = timezone.now()
                    fa.is_active = True
                    fa.save()
                    return redirect('tournament:free_agent')
        return redirect('tournament:free_agent')


def remove_entry(request, pk):
    free_agent = get_object_or_404(FreeAgent, pk=pk)
    if request.method == 'POST':
        if request.user == free_agent.player:
            free_agent.is_active = False
            free_agent.deleted = timezone.now()
            free_agent.save()
            return redirect('tournament:free_agent')
        else:
            return HttpResponse('Ошибка доступа')
    else:
        redirect('tournament:free_agent')


def update_entry(request, pk):
    free_agent = get_object_or_404(FreeAgent, pk=pk)
    if request.method == 'POST':
        if request.user == free_agent.player:
            free_agent.created = timezone.now()
            free_agent.save()
            return redirect('tournament:free_agent')
        else:
            return HttpResponse('Ошибка доступа')
    else:
        redirect('tournament:free_agent')


def edit_team_profile(request, slug):
    team = get_object_or_404(Team, slug=slug)
    if request.method == "POST" and (request.user == team.owner or request.user.is_superuser):
        form = EditTeamProfileForm(request.POST, instance=team)
        if form.is_valid():
            team = form.save(commit=False)
            team.save()
            return redirect(team.get_absolute_url())
    else:
        if request.user == team.owner or request.user.is_superuser:
            form = EditTeamProfileForm(instance=team)
        else:
            return HttpResponse('Ошибка доступа')
    return render(request, 'tournament/teams/edit_team.html', {'form': form})


class TeamDetail(DetailView):
    model = Team
    context_object_name = 'team'
    template_name = 'tournament/teams/team_page.html'


class TeamList(ListView):
    queryset = Team.objects.all().order_by('-title')
    context_object_name = 'teams'
    template_name = 'tournament/teams/teams_list.html'


class LeagueDetail(DetailView):
    context_object_name = 'league'
    model = League
    # queryset = League.objects.filter(is_cup=False, championship__is_active=True)
    template_name = 'tournament/premier_league/team_table.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        league = context['league']

        comments_obj = NewComment.objects.filter(content_type=ContentType.objects.get_for_model(League),
                                                 object_id=league.id,
                                                 parent=None)

        paginate = Paginator(comments_obj, 25)
        page = self.request.GET.get('page')

        try:
            comments = paginate.page(page)
        except PageNotAnInteger:
            # If page is not an integer deliver the first page
            comments = paginate.page(1)
        except EmptyPage:
            # If page is out of range deliver last page of results
            comments = paginate.page(paginate.num_pages)

        context['page'] = page
        context['comments'] = comments
        comment_form = NewCommentForm()
        context['comment_form'] = comment_form
        return context


class MatchDetail(DetailView):
    model = Match
    context_object_name = 'match'
    template_name = 'tournament/match/detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        match = context['match']

        comments_obj = NewComment.objects.filter(content_type=ContentType.objects.get_for_model(Match),
                                                 object_id=match.id,
                                                 parent=None)
        paginate = Paginator(comments_obj, 25)
        page = self.request.GET.get('page')

        try:
            comments = paginate.page(page)
        except PageNotAnInteger:
            # If page is not an integer deliver the first page
            comments = paginate.page(1)
        except EmptyPage:
            # If page is out of range deliver last page of results
            comments = paginate.page(paginate.num_pages)

        context['page'] = page
        context['comments'] = comments
        comment_form = NewCommentForm()
        context['comment_form'] = comment_form
        all_matches_between = Match.objects.filter(
            Q(team_guest=match.team_guest, team_home=match.team_home, is_played=True) | Q(team_guest=match.team_home,
                                                                                          team_home=match.team_guest,
                                                                                          is_played=True))

        substitutes = {match.team_home: [], match.team_guest: []}
        team_home_start = match.team_home_start.all()
        team_guest_start = match.team_guest_start.all()
        for substitution in match.match_substitutions.all():
            team = substitution.team
            player_in = substitution.player_in
            if player_in not in team_home_start and player_in not in team_guest_start:
                substitutes[team].append(player_in)
        context['team_home_substitutes'] = substitutes[match.team_home]
        context['team_guest_substitutes'] = substitutes[match.team_guest]

        goals = match.match_goal.values('author').annotate(goals=Count('author')).order_by('author')
        goals_by_player = {d['author']: d['goals'] for d in goals}
        context['goals_by_player'] = goals_by_player

        assists = \
            (match.match_goal
             .exclude(assistent=None)
             .values('assistent')
             .annotate(assists=Count('assistent'))
             .order_by('assistent'))
        assists_by_player = {d['assistent']: d['assists'] for d in assists}
        context['assists_by_player'] = assists_by_player

        clean_sheets = \
            (match.match_event
                .filter(event=OtherEvents.CLEAN_SHIT)
                .values('author')
                .annotate(cs=Count('author'))
                .order_by('author'))
        clean_sheets_by_player = {d['author']: d['cs'] for d in clean_sheets}
        context['clean_sheets_by_player'] = clean_sheets_by_player

        time_played = defaultdict(int)
        substitutions = match.match_substitutions.all()
        full_match_time = int(timedelta(minutes=16, seconds=0).total_seconds())
        start_players = match.team_home_start.all() | match.team_guest_start.all()
        for player in start_players:
            time_played[player.id] = full_match_time

        for substitution in substitutions:
            player_in = substitution.player_in.id
            player_out = substitution.player_out.id
            time_until_match_end = int(full_match_time - timedelta(minutes=substitution.time_min,
                                                                   seconds=substitution.time_sec).total_seconds())
            time_played[player_in] += time_until_match_end
            time_played[player_out] -= time_until_match_end
        time_played_by_player = {p: datetime.fromtimestamp(sec).strftime('%M:%S') for (p, sec) in time_played.items()}
        context['time_played_by_player'] = time_played_by_player

        if all_matches_between.count() == 0:
            context['no_history'] = True
            return context
        the_most_score = all_matches_between.first()
        score = the_most_score.score_home + the_most_score.score_guest
        win_home = 0
        draws = 0
        win_guest = 0
        score_home_all = 0
        score_guest_all = 0
        for i in all_matches_between:
            if i.score_home + i.score_guest > score:
                score = i.score_home + i.score_guest
                the_most_score = i

            if i.team_home == match.team_home:
                if i.score_home > i.score_guest:
                    win_home += 1
                elif i.score_home == i.score_guest:
                    draws += 1
                else:
                    win_guest += 1
            else:
                if i.score_home < i.score_guest:
                    win_home += 1
                elif i.score_home == i.score_guest:
                    draws += 1
                else:
                    win_guest += 1

            if i.team_home == match.team_home:
                score_home_all += i.score_home
                score_guest_all += i.score_guest
            else:
                score_guest_all += i.score_home
                score_home_all += i.score_guest

        win_home_percentage = round(100 * win_home / all_matches_between.count())
        draws_percentage = round(100 * draws / all_matches_between.count())
        win_guest_percentage = 100 - win_home_percentage - draws_percentage
        context['all_matches_between'] = all_matches_between
        context['the_most_score'] = the_most_score
        context['win_home'] = win_home
        context['win_guest'] = win_guest
        context['draws'] = draws
        context['win_home_percentage'] = win_home_percentage
        context['win_guest_percentage'] = win_guest_percentage
        context['draws_percentage'] = draws_percentage
        context['score_home_all'] = score_home_all
        context['score_guest_all'] = score_guest_all
        context['score_home_average'] = round(score_home_all / all_matches_between.count(), 2)
        context['score_guest_average'] = round(score_guest_all / all_matches_between.count(), 2)
        return context


class LeagueByTitleFilter(FilterSet):
    CHOICES = (
        ('Высшая лига', 'Высшая лига'),
        ('Первая лига', 'Первая лига'),
        ('Вторая лига', 'Вторая лига'),
        ('Кубок Высшей лиги', 'Кубок Высшей лиги'),
        ('Кубок Первой лиги', 'Кубок Первой лиги'),
        ('Кубок Второй лиги', 'Кубок Второй лиги'),
    )

    title = ChoiceFilter(choices=CHOICES, lookup_expr='icontains', label='Турнир', empty_label=None)

    class Meta:
        model = League
        fields = ['title']


class PostponementsList(ListView):
    queryset = (Postponement.objects
                .filter(match__league__championship__is_active=True)
                .order_by('-taken_at'))
    context_object_name = 'all_postponements'
    template_name = 'tournament/postponements/postponements.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filter = LeagueByTitleFilter(self.request.GET, queryset=League.objects.filter(championship__is_active=True))
        leagues = filter.qs
        teams = reduce(lambda acc, league: acc.union(league.teams.all()), leagues, set())
        postponements = context['all_postponements'].filter(match__league__in=leagues)

        paginator = Paginator(postponements, 20)
        page = self.request.GET.get('page')

        try:
            postponements = paginator.page(page)
        except PageNotAnInteger:
            # If page is not an integer deliver the first page
            postponements = paginator.page(1)
        except EmptyPage:
            # If page is out of range deliver last page of results
            postponements = paginator.page(paginator.num_pages)

        context['postponements'] = postponements
        context['teams'] = teams
        context['filter'] = filter
        return context

    def post(self, request):
        data = request.POST

        match_id = int(data['match_id'])
        match = Match.objects.get(pk=match_id)
        team = data['team']
        type = data['type']

        if team == 'mutual':
            teams = [match.team_home, match.team_guest]
        else:
            team_id = int(team)
            teams = [Team.objects.get(pk=team_id)]
        is_emergency = type == 'emergency'
        taken_by = request.user
        match_expiration_date = match.numb_tour.date_to
        if match.is_postponed:
            match_expiration_date = match.get_last_postponement().ends_at

        starts_at = match_expiration_date + timezone.timedelta(days=1)
        ends_at = match_expiration_date + timezone.timedelta(days=7)

        postponement = Postponement.objects.create(match=match, is_emergency=is_emergency, taken_by=taken_by,
                                                   starts_at=starts_at, ends_at=ends_at)
        postponement.teams.set(teams)

        return redirect(reverse('tournament:postponements') + '?title={}'.format(request.GET['title']))


@require_POST
def cancel_postponement(request, pk):
    postponement = get_object_or_404(Postponement, pk=pk)
    user_teams = get_user_teams(request.user)

    if (postponement.match.team_home in user_teams) or (postponement.match.team_guest in user_teams):
        postponement.cancelled_at = timezone.now()
        postponement.cancelled_by = request.user
        postponement.save()

        return redirect(reverse('tournament:postponements') + '?title={}'.format(request.GET['title']))
    else:
        return HttpResponse('Ошибка доступа')


def halloffame(request):
    top_goalscorers = Player.objects.annotate(
        goals_c=Count('goals__match__league')).filter(goals_c__gt=0).order_by('-goals_c')

    top_assistent = Player.objects.annotate(
        ass_c=Count('assists__match__league')).filter(ass_c__gt=0).order_by('-ass_c')
    top_clean_sheets = Player.objects.filter(event__event='CLN').annotate(
        event_c=Count('event__match__league')).filter(event_c__gt=0).order_by('-event_c')

    player_matches = []
    subs_in = []
    subs_out = []
    for player in Player.objects.all():
        m_played = Match.objects.filter(
            team_guest_start=player).count() + Match.objects.filter(
            team_home_start=player).count() + Match.objects.filter(
            ~(Q(team_guest_start=player) | Q(team_home_start=player)),

            match_substitutions__player_in=player
        ).distinct().count()
        if m_played > 0:
            player_matches.append([player, m_played])
        subin_pl = Substitution.objects.filter(player_in=player).count()
        if subin_pl > 0:
            subs_in.append([player, subin_pl])

        subout_pl = Substitution.objects.filter(player_out=player).count()
        if subout_pl > 0:
            subs_out.append([player, subout_pl])

    pl = sorted(player_matches, key=lambda x: x[1], reverse=True)
    subs_inn = sorted(subs_in, key=lambda x: x[1], reverse=True)
    subs_outt = sorted(subs_out, key=lambda x: x[1], reverse=True)
    return render(request, 'tournament/hall_of_fame.html', {'goalscorers': top_goalscorers,
                                                            'assistents': top_assistent,
                                                            'clean_sheeters': top_clean_sheets,
                                                            'player_matches': pl,
                                                            'subs_in': subs_inn,
                                                            'subs_out': subs_outt,
                                                            })


def team_rating(request):
    t = Team.objects.all()
    for s in t:
        s.rating = 0
        s.save(update_fields=['rating'])
        print(s)

    seasons = Season.objects.filter(is_round_robin=True, is_active=False).order_by('number')[:2]
    for s in seasons:
        a = s.tournaments_in_season.filter(is_cup=False).first()
        print(a)

    return render(request, 'tournament/team_all_time_rating.html', {'teams': t, 'seas': seasons})
