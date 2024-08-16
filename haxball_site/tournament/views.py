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
    Postponement, PlayerTransfer, TeamRating, RatingVersion
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
        context['filter'] = DisqualificationFilter(self.request.GET, queryset=self.queryset)

        return context


class TransfersList(ListView):
    from_date = datetime(2024, 3, 13)
    queryset = PlayerTransfer.objects.filter(season_join__is_active=True,
                                             date_join__gte=from_date).order_by('-date_join', '-id')
    context_object_name = 'transfers'
    template_name = 'tournament/transfers/transfers_list.html'


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
                .filter(event=OtherEvents.CLEAN_SHEET)
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
        filter = LeagueByTitleFilter(self.request.GET or {'title': 'Высшая лига'},
                                     queryset=League.objects.filter(championship__is_active=True))
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
        if self.request.session.get('show_exceeded_limit_modal'):
            context['show_exceeded_limit_modal'] = True
            context['exceeded_limit_message'] = self.request.session.get('exceeded_limit_message')
            self.request.session['show_exceeded_limit_modal'] = False
            self.request.session['exceeded_limit_message'] = ''

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
        total_slots_count = match.league.get_postponement_slots().total_count
        for team in teams:
            team_postponements = team.get_postponements(leagues=[match.league])
            if team_postponements.count() + 1 > total_slots_count:
                request.session['show_exceeded_limit_modal'] = True
                request.session['exceeded_limit_message'] = 'Команда {} исчерпала лимит переносов'.format(team.title)
                return redirect(reverse('tournament:postponements') + '?title={}'.format(request.GET['title']))
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
    players = players_halloffame()
    teams = teams_halloffame()

    return render(request, 'tournament/hall_of_fame.html', {
        'players': players,
        'teams': teams
    })


def players_halloffame():
    top_goalscorers = Player.objects.annotate(
        goals_count=Count('goals__match__league')).filter(goals_count__gt=0).order_by('-goals_count')

    top_assistants = Player.objects.annotate(
        assists_count=Count('assists__match__league')).filter(assists_count__gt=0).order_by('-assists_count')

    top_cs = Player.objects.filter(event__event=OtherEvents.CLEAN_SHEET).annotate(
        cs_count=Count('event__match__league')).filter(cs_count__gt=0).order_by('-cs_count')

    top_ogs = Player.objects.filter(event__event=OtherEvents.OWN_GOAL).annotate(
        og_count=Count('event__match__league')).filter(og_count__gt=0).order_by('-og_count')

    top_yellow_cards = Player.objects.filter(event__event=OtherEvents.YELLOW_CARD).annotate(
        yellow_cards_count=Count('event__match__league')).filter(yellow_cards_count__gt=0).order_by('-yellow_cards_count')

    top_red_cards = Player.objects.filter(event__event=OtherEvents.RED_CARD).annotate(
        red_cards_count=Count('event__match__league')).filter(red_cards_count__gt=0).order_by('-red_cards_count')

    player_matches = []
    subs_in = []
    subs_out = []
    for player in Player.objects.all():
        matches = Match.objects.filter(
            team_guest_start=player).count() + Match.objects.filter(
            team_home_start=player).count() + Match.objects.filter(
            ~(Q(team_guest_start=player) | Q(team_home_start=player)),

            match_substitutions__player_in=player
        ).distinct().count()
        if matches > 0:
            player_matches.append([player, matches])
        player_subs_in = Substitution.objects.filter(player_in=player).count()
        if player_subs_in > 0:
            subs_in.append([player, player_subs_in])

        player_subs_out = Substitution.objects.filter(player_out=player).count()
        if player_subs_out > 0:
            subs_out.append([player, player_subs_out])

    sorted_matches = sorted(player_matches, key=lambda x: x[1], reverse=True)
    sorted_subs_in = sorted(subs_in, key=lambda x: x[1], reverse=True)
    sorted_subs_out = sorted(subs_out, key=lambda x: x[1], reverse=True)

    return {
        'goals': top_goalscorers,
        'assists': top_assistants,
        'clean_sheets': top_cs,
        'yellow_cards': top_yellow_cards,
        'red_cards': top_red_cards,
        'ogs': top_ogs,
        'player_matches': sorted_matches,
        'subs_in': sorted_subs_in,
        'subs_out': sorted_subs_out,
    }


def teams_halloffame():
    top_goalscorers = Team.objects.annotate(
        goals_count=Count('goals__match__league')).filter(goals_count__gt=0).order_by('-goals_count')

    top_assistants = (Team.objects
                      .annotate(assists_count=Count('goals__match__league',
                                                    filter=Q(goals__assistent__isnull=False)))
                      .filter(assists_count__gt=0).order_by('-assists_count'))

    top_cs = Team.objects.filter(team_events__event=OtherEvents.CLEAN_SHEET).annotate(
        cs_count=Count('team_events__match__league')).filter(cs_count__gt=0).order_by('-cs_count')

    top_ogs = Team.objects.filter(team_events__event=OtherEvents.OWN_GOAL).annotate(
        og_count=Count('team_events__match__league')).filter(og_count__gt=0).order_by('-og_count')

    top_yellow_cards = Team.objects.filter(team_events__event=OtherEvents.YELLOW_CARD).annotate(
        yellow_cards_count=Count('team_events__match__league')).filter(yellow_cards_count__gt=0).order_by('-yellow_cards_count')

    top_red_cards = Team.objects.filter(team_events__event=OtherEvents.RED_CARD).annotate(
        red_cards_count=Count('team_events__match__league')).filter(red_cards_count__gt=0).order_by('-red_cards_count')

    team_matches = []
    team_wins = []
    team_winrates = []
    subs = []
    for team in Team.objects.all():
        matches = Match.objects.filter(Q(team_home=team) | Q(team_guest=team), is_played=True).count()
        wins = (Match.objects.filter(team_home=team, score_home__gt=F('score_guest'), is_played=True).count() +
                Match.objects.filter(team_guest=team, score_guest__gt=F('score_home'), is_played=True).count())
        winrate = wins / (matches or 1) * 100
        if matches > 0:
            team_matches.append([team, matches])
        if wins > 0:
            team_wins.append([team, wins])
        if winrate > 0:
            team_winrates.append([team, winrate])
        teams_subs = Substitution.objects.filter(team=team).count()
        if teams_subs > 0:
            subs.append([team, teams_subs])

    sorted_matches = sorted(team_matches, key=lambda x: x[1], reverse=True)
    sorted_wins = sorted(team_wins, key=lambda x: x[1], reverse=True)
    sorted_winrates = sorted(team_winrates, key=lambda x: x[1], reverse=True)
    sorted_subs = sorted(subs, key=lambda x: x[1], reverse=True)

    return {
        'goals': top_goalscorers,
        'assists': top_assistants,
        'clean_sheets': top_cs,
        'yellow_cards': top_yellow_cards,
        'red_cards': top_red_cards,
        'ogs': top_ogs,
        'team_matches': sorted_matches,
        'wins': sorted_wins,
        'winrates': sorted_winrates,
        'subs': sorted_subs
    }


class TeamRatingFilter(FilterSet):
    version = ModelChoiceFilter(queryset=RatingVersion.objects.all())

    class Meta:
        model = TeamRating
        fields = ['version']


class TeamRatingView(ListView):
    queryset = TeamRating.objects.all()
    context_object_name = 'team_rating'
    template_name = 'tournament/team_rating.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET or {'version': 7}
        context['filter'] = TeamRatingFilter(params, queryset=self.queryset)
        current_version = int(params['version'])
        previous_rating_version = TeamRating.objects.filter(version__number=current_version-1)
        if previous_rating_version:
            context['previous_rating'] = {item.team: item.rank
                                          for item in previous_rating_version.all()}

        return context
