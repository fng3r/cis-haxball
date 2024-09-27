from collections import defaultdict
from datetime import datetime, timedelta
from functools import reduce

from core.forms import NewCommentForm
from core.utils import get_comments_for_object, get_paginated_comments
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Case, Count, F, FloatField, OuterRef, Prefetch, Q, Subquery, When
from django.db.models.functions import Cast, Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView
from django_filters import ChoiceFilter, FilterSet, ModelChoiceFilter

from .charts import StatCharts
from .forms import EditTeamProfileForm, FreeAgentForm
from .models import (
    Disqualification,
    FreeAgent,
    Goal,
    League,
    Match,
    MatchResult,
    OtherEvents,
    Player,
    PlayerTransfer,
    Postponement,
    RatingVersion,
    Season,
    SeasonTeamRating,
    Substitution,
    Team,
    TeamRating,
)
from .templatetags.tournament_extras import get_user_teams


class DefaultFilterSet(FilterSet):
    def __init__(self, data=None, *args, **kwargs):
        # if filterset is bound, use initial values as defaults
        if data is not None:
            # get a mutable copy of the QueryDict
            data = data.copy()

            for name, f in self.base_filters.items():
                initial = f.extra.get('initial')

                # filter param is either missing or empty, use initial as default
                if not data.get(name) and initial:
                    data[name] = initial

        super().__init__(data, *args, **kwargs)


class DisqualificationFilter(DefaultFilterSet):
    season = ModelChoiceFilter(
        field_name='match__league__championship',
        label='Сезон',
        empty_label=None,
        queryset=Season.objects.filter(number__gt=14).order_by('-number'),
        initial=Season.objects.order_by('-number').first(),
    )
    team = ModelChoiceFilter(queryset=Team.objects.filter(leagues__championship__number__gt=14).distinct())
    player = ModelChoiceFilter(queryset=Player.objects.all())

    class Meta:
        model = Disqualification
        fields = ['season', 'team']


class DisqualificationsList(ListView):
    queryset = (
        Disqualification.objects.select_related(
            'team', 'match__team_home', 'match__team_guest', 'player__name__user_profile'
        )
        .prefetch_related('tours__league', 'lifted_tours__league')
        .filter(match__league__championship__number__gt=14)
        .order_by('-created')
    )
    template_name = 'tournament/disqualification/disqualifications.html'
    paginate_by = 25

    def get(self, request, **kwargs):
        filter = DisqualificationFilter(request.GET, queryset=self.queryset)
        paginator = Paginator(filter.qs, self.paginate_by)
        page = request.GET.get('page')
        disqualifications = paginator.get_page(page)

        if request.htmx:
            return render(
                request,
                'tournament/disqualification/partials/disqualifications_list.html',
                {'disqualifications': disqualifications}
            )

        return render(request, self.template_name, {'disqualifications': disqualifications, 'filter': filter})


class TransferFilter(DefaultFilterSet):
    initial_season = Season.objects.order_by('-number').first()
    teams_qs = Team.objects.filter(leagues__championship__number__gt=14).distinct()

    season = ModelChoiceFilter(
        field_name='season_join',
        label='Сезон',
        empty_label=None,
        queryset=Season.objects.filter(number__gt=14).order_by('-number'),
        initial=initial_season,
    )
    team_from = ModelChoiceFilter(field_name='from_team', null_label='Свободный агент', queryset=teams_qs)
    team_to = ModelChoiceFilter(field_name='to_team', null_label='Свободный агент', queryset=teams_qs)
    player = ModelChoiceFilter(field_name='trans_player', queryset=Player.objects.all())

    class Meta:
        model = PlayerTransfer
        fields = ['season', 'team_from', 'team_to', 'player']


class TransfersList(ListView):
    from_date = datetime(2024, 3, 13)
    queryset = (
        PlayerTransfer.objects.select_related('trans_player__name__user_profile', 'from_team', 'to_team')
        .filter(date_join__gte=from_date, is_technical=False)
        .order_by('-date_join', '-id')
    )
    template_name = 'tournament/transfers/transfers.html'
    paginate_by = 25

    def get(self, request, **kwargs):
        filter = TransferFilter(request.GET, queryset=self.queryset)
        paginator = Paginator(filter.qs, self.paginate_by)
        page = request.GET.get('page')
        transfers = paginator.get_page(page)

        if request.htmx:
            return render(
                request,
                'tournament/transfers/partials/transfers_list.html',
                {'transfers': transfers}
            )

        return render(request, self.template_name, {'transfers': transfers, 'filter': filter})


class FreeAgentList(ListView):
    queryset = FreeAgent.objects.select_related('player__user_profile').filter(is_active=True).order_by('-created')
    context_object_name = 'agents'
    template_name = 'tournament/free_agents/free_agents.html'
    paginate_by = 20

    def get(self, request, **kwargs):
        paginator = Paginator(self.queryset, self.paginate_by)
        page = request.GET.get('page', 1)
        free_agents = paginator.get_page(page)
        context = {'agents': free_agents}

        if request.htmx:
            return render(request, 'tournament/free_agents/partials/free_agents_list.html', context)

        return render(request, self.template_name, context)

    def post(self, request):
        free_agent = FreeAgent.objects.filter(player=request.user).first()
        if free_agent:
            fa_form = FreeAgentForm(data=request.POST, instance=free_agent)
        else:
            fa_form = FreeAgentForm(data=request.POST)
        if fa_form.is_valid():
            free_agent = fa_form.save(commit=False)
            free_agent.created = timezone.now()
            free_agent.is_active = True
            free_agent.team = request.user
            free_agent.save()

        paginator = Paginator(self.queryset, self.paginate_by)
        free_agents = paginator.get_page(1)
        context = {'agents': free_agents}

        return render(request, 'tournament/free_agents/free_agents.html#content-container', context)


def remove_entry(request, pk):
    free_agent = get_object_or_404(FreeAgent, pk=pk)
    if request.method == 'POST':
        if request.user == free_agent.player:
            free_agent.is_active = False
            free_agent.deleted = timezone.now()
            free_agent.save()
        else:
            messages.error(request, 'Ошибка доступа')

    all_agents = FreeAgent.objects.select_related('player__user_profile').filter(is_active=True).order_by('-created')
    paginator = Paginator(all_agents, 20)
    free_agents = paginator.get_page(1)
    context = {'agents': free_agents}

    return render(request, 'tournament/free_agents/free_agents.html#content-container', context)


def update_entry(request, pk):
    free_agent = get_object_or_404(FreeAgent, pk=pk)
    if request.method == 'POST':
        if request.user == free_agent.player:
            free_agent.created = timezone.now()
            free_agent.save()
        else:
            messages.error(request, 'Ошибка доступа')

    all_agents = FreeAgent.objects.select_related('player__user_profile').filter(is_active=True).order_by('-created')
    paginator = Paginator(all_agents, 20)
    free_agents = paginator.get_page(1)
    context = {'agents': free_agents}

    return render(request, 'tournament/free_agents/free_agents.html#content-container', context)


class EditTeamView(DetailView, View):
    model = Team
    context_object_name = 'team'
    template_name = 'tournament/teams/edit_team.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = EditTeamProfileForm(instance=context['team'])

        return context

    def post(self, request, slug):
        team = get_object_or_404(Team, slug=slug)
        if request.user == team.owner or request.user.is_superuser:
            form = EditTeamProfileForm(request.POST, instance=team)
            if form.is_valid():
                team = form.save(commit=False)
                team.save()
        else:
            return HttpResponse('Ошибка доступа')

        return redirect(team.get_absolute_url())


class TeamDetail(DetailView):
    model = Team
    context_object_name = 'team'
    template_name = 'tournament/teams/team_page.html'

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related('owner')
            .prefetch_related(
                Prefetch(
                    'players_in_team', queryset=Player.objects.select_related('name__user_profile', 'player_nation')
                )
            )
        )

    def get_template_names(self):
        if self.request.htmx:
            return 'tournament/teams/team_page.html#team-page-container'

        return self.template_name



class TeamList(ListView):
    queryset = Team.objects.all().order_by('-title')
    context_object_name = 'teams'
    template_name = 'tournament/teams/teams_list.html'


class LeagueDetail(DetailView):
    context_object_name = 'league'
    model = League
    template_name = 'tournament/premier_league/team_table.html'

    def get_queryset(self):
        return (
            super().get_queryset().prefetch_related('tours__tour_matches__team_home', 'tours__tour_matches__team_guest')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        league = context['league']

        page = self.request.GET.get('page')
        comments_obj = get_comments_for_object(League, league.id)
        comments = get_paginated_comments(comments_obj, page)

        context['page'] = page
        context['comments'] = comments
        comment_form = NewCommentForm()
        context['comment_form'] = comment_form
        return context


class MatchDetail(DetailView):
    model = Match
    context_object_name = 'match'
    template_name = 'tournament/match/detail.html'

    def get_queryset(self):
        return Match.objects.select_related(
            'team_home', 'team_guest', 'numb_tour', 'league__championship', 'inspector'
        ).prefetch_related(
            'team_home_start__name__user_profile',
            'team_home_start__player_nation',
            'team_guest_start__name__user_profile',
            'team_guest_start__player_nation',
            'disqualifications__player__team',
            'disqualifications__tours__league',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        match = context['match']

        page = self.request.GET.get('page')
        comments_obj = get_comments_for_object(Match, match.id)
        comments = get_paginated_comments(comments_obj, page)

        context['page'] = page
        context['comments'] = comments
        comment_form = NewCommentForm()
        context['comment_form'] = comment_form

        all_matches_between = Match.objects.filter(
            Q(team_guest=match.team_guest, team_home=match.team_home, is_played=True)
            | Q(team_guest=match.team_home, team_home=match.team_guest, is_played=True)
        ).select_related('team_home', 'team_guest')

        substitutes = {match.team_home: set(), match.team_guest: set()}
        team_home_start = match.team_home_start.all()
        team_guest_start = match.team_guest_start.all()
        substitutions = match.match_substitutions.select_related(
            'team',
            'player_in__name__user_profile',
            'player_in__player_nation',
            'player_out__name__user_profile',
            'player_out__player_nation',
        )
        for substitution in substitutions:
            team = substitution.team
            player_in = substitution.player_in
            if player_in not in team_home_start and player_in not in team_guest_start:
                substitutes[team].add(player_in)
        context['team_home_substitutes'] = substitutes[match.team_home]
        context['team_guest_substitutes'] = substitutes[match.team_guest]

        goals = match.match_goal.values('author').annotate(goals=Count('author')).order_by('author')
        goals_by_player = {d['author']: d['goals'] for d in goals}
        context['goals_by_player'] = goals_by_player

        assists = (
            match.match_goal.exclude(assistent=None)
            .values('assistent')
            .annotate(assists=Count('assistent'))
            .order_by('assistent')
        )
        assists_by_player = {d['assistent']: d['assists'] for d in assists}
        context['assists_by_player'] = assists_by_player

        clean_sheets = (
            match.match_event.filter(event=OtherEvents.CLEAN_SHEET)
            .values('author')
            .annotate(cs=Count('author'))
            .order_by('author')
        )
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
            time_until_match_end = int(
                full_match_time
                - timedelta(minutes=substitution.time_min, seconds=substitution.time_sec).total_seconds()
            )
            time_played[player_in] += time_until_match_end
            time_played[player_out] -= time_until_match_end
        time_played_by_player = {p: datetime.fromtimestamp(sec).strftime('%M:%S') for (p, sec) in time_played.items()}
        context['time_played_by_player'] = time_played_by_player

        cards = match.cards().select_related('author', 'team')
        context['cards'] = cards

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
        for face_to_face_match in all_matches_between:
            if face_to_face_match.score_home + face_to_face_match.score_guest > score:
                score = face_to_face_match.score_home + face_to_face_match.score_guest
                the_most_score = face_to_face_match

            if face_to_face_match.team_home == match.team_home:
                if face_to_face_match.score_home > face_to_face_match.score_guest:
                    win_home += 1
                elif face_to_face_match.score_home == face_to_face_match.score_guest:
                    draws += 1
                else:
                    win_guest += 1
            else:
                if face_to_face_match.score_home < face_to_face_match.score_guest:
                    win_home += 1
                elif face_to_face_match.score_home == face_to_face_match.score_guest:
                    draws += 1
                else:
                    win_guest += 1

            if face_to_face_match.team_home == match.team_home:
                score_home_all += face_to_face_match.score_home
                score_guest_all += face_to_face_match.score_guest
            else:
                score_guest_all += face_to_face_match.score_home
                score_home_all += face_to_face_match.score_guest

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
        ('Кубок лиги – Группа', 'Кубок лиги'),
    )

    tournament = ChoiceFilter(
        field_name='title', label='Турнир', empty_label=None, choices=CHOICES, lookup_expr='icontains'
    )

    class Meta:
        model = League
        fields = ['tournament']


class PostponementsList(ListView):
    queryset = (
        Postponement.objects.filter(match__league__championship__is_active=True)
        .select_related('match__team_home', 'match__team_guest', 'match__numb_tour')
        .prefetch_related('teams', 'taken_by__user_profile__user_icon', 'cancelled_by__user_profile__user_icon')
        .order_by('-taken_at')
    )
    template_name = 'tournament/postponements/postponements.html'

    def get(self, request, **kwargs):
        filter = LeagueByTitleFilter(
            {'tournament': self.request.GET.get('tournament', 'Высшая лига')},
            queryset=League.objects.filter(championship__is_active=True).prefetch_related('postponement_slots'),
        )
        leagues = filter.qs
        teams = reduce(lambda acc, league: acc.union(league.teams.all()), leagues, set())
        postponements = self.queryset.filter(match__league__in=leagues)

        paginator = Paginator(postponements, 20)
        page = self.request.GET.get('page')

        postponements = paginator.get_page(page)

        context = {
            'postponements': postponements,
            'teams': teams,
            'filter': filter,
        }

        if request.htmx:
            return render(request, 'tournament/postponements/postponements.html#content-container', context)

        return render(self.request, self.template_name, context)

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
        slots = match.league.get_postponement_slots()
        tournament = data.get('tournament')
        for team in teams:
            all_postponements = team.get_postponements(leagues=[match.league])
            emergency_postponements = all_postponements.filter(is_emergency=True)
            if (all_postponements.count() + 1 > slots.total_count or
                    (is_emergency and emergency_postponements.count() + 1 > slots.emergency_count + slots.extra_count)):
                messages.error(request, f'Команда {team.title} исчерпала лимит переносов')

                return redirect(reverse('tournament:postponements') + f'?tournament={tournament}')

        taken_by = request.user
        match_expiration_date = match.numb_tour.date_to
        if match.is_postponed:
            match_expiration_date = match.get_last_postponement().ends_at

        starts_at = match_expiration_date + timezone.timedelta(days=1)
        ends_at = match_expiration_date + timezone.timedelta(days=7)

        postponement = Postponement.objects.create(
            match=match, is_emergency=is_emergency, taken_by=taken_by, starts_at=starts_at, ends_at=ends_at
        )
        postponement.teams.set(teams)

        return redirect(reverse('tournament:postponements') + f'?tournament={tournament}')


class PostponementsEvents(ListView):
    def get(self, request, **kwargs):
        filter = LeagueByTitleFilter(
            {'tournament': self.request.GET.get('tournament', 'Высшая лига')},
            queryset=League.objects.filter(championship__is_active=True).prefetch_related('postponement_slots'),
        )
        leagues = filter.qs
        all_postponements = (
            Postponement.objects.filter(match__league__championship__is_active=True, match__league__in=leagues)
            .select_related('match__team_home', 'match__team_guest', 'match__numb_tour')
            .prefetch_related('teams', 'taken_by__user_profile__user_icon', 'cancelled_by__user_profile__user_icon')
            .order_by('-taken_at')
        )

        paginator = Paginator(all_postponements, 20)
        page = self.request.GET.get('page')
        postponements = paginator.get_page(page)

        context = {
            'postponements': postponements,
            'filter': filter,
        }

        return render(request, 'tournament/postponements/postponements.html#postponements-events', context)


@require_POST
def cancel_postponement(request, pk):
    data = request.POST
    postponement = get_object_or_404(Postponement, pk=pk)
    user_teams = get_user_teams(request.user)

    if (postponement.match.team_home in user_teams) or (postponement.match.team_guest in user_teams):
        postponement.cancelled_at = timezone.now()
        postponement.cancelled_by = request.user
        postponement.save()
    else:
        messages.error(request, 'Ошибка доступа')

    return redirect(reverse('tournament:postponements') + f'?tournament={data["tournament"]}')


def halloffame(request):
    players = players_halloffame()
    teams = teams_halloffame()

    return render(request, 'tournament/hall_of_fame.html', {'players': players, 'teams': teams})


def players_halloffame():
    players = Player.objects.select_related('team', 'name__user_profile')

    top_goalscorers = (
        players.annotate(goals_count=Count('goals__match__league'))
        .filter(goals_count__gt=0)
        .order_by('-goals_count')
    )

    top_assistants = (
        players.annotate(assists_count=Count('assists__match__league'))
        .filter(assists_count__gt=0)
        .order_by('-assists_count')
    )

    top_cs = (
        players.filter(event__event=OtherEvents.CLEAN_SHEET)
        .annotate(cs_count=Count('event__match__league'))
        .filter(cs_count__gt=0)
        .order_by('-cs_count')
    )

    top_ogs = (
        players.filter(event__event=OtherEvents.OWN_GOAL)
        .annotate(og_count=Count('event__match__league'))
        .filter(og_count__gt=0)
        .order_by('-og_count')
    )

    top_yellow_cards = (
        players.filter(event__event=OtherEvents.YELLOW_CARD)
        .annotate(yellow_cards_count=Count('event__match__league'))
        .filter(yellow_cards_count__gt=0)
        .order_by('-yellow_cards_count')
    )

    top_red_cards = (
        players.filter(event__event=OtherEvents.RED_CARD)
        .annotate(red_cards_count=Count('event__match__league'))
        .filter(red_cards_count__gt=0)
        .order_by('-red_cards_count')
    )

    top_subs_in = (
        players
        .annotate(subs_in_count=Count('join_game__player_in'))
        .filter(subs_in_count__gt=0)
        .order_by('-subs_in_count')
    )

    top_subs_out = (
        players
        .annotate(subs_out_count=Count('replaced__player_out'))
        .filter(subs_out_count__gt=0)
        .order_by('-subs_out_count')
    )

    home_matches_subquery = (
        Match.objects.filter(team_home_start=OuterRef('id'), is_played=True)
        .order_by().values('team_home_start')
        .annotate(c=Count('*')).values('c')
    )
    guest_matches_subquery = (
        Match.objects.filter(team_guest_start=OuterRef('id'), is_played=True)
        .order_by().values('team_guest_start')
        .annotate(c=Count('*')).values('c')
    )

    sub_matches_subquery = (
        Match.objects.filter(~(Q(team_guest_start=OuterRef('id')) | Q(team_home_start=OuterRef('id'))),
                             match_substitutions__player_in=OuterRef('id'), is_played=True)
        .order_by().values('match_substitutions__player_in')
        .annotate(c=Count('*')).values('c')
    )

    top_matches = (
        players
        .annotate(home_matches_count=Coalesce(Subquery(home_matches_subquery), 0),
                  guest_matches_count=Coalesce(Subquery(guest_matches_subquery), 0),
                  sub_matches_count=Coalesce(Subquery(sub_matches_subquery), 0),
                  matches_count=F('home_matches_count') + F('guest_matches_count') + F('sub_matches_count'))
        .filter(matches_count__gt=0)
        .order_by('-matches_count'))

    return {
        'goals': top_goalscorers,
        'assists': top_assistants,
        'clean_sheets': top_cs,
        'yellow_cards': top_yellow_cards,
        'red_cards': top_red_cards,
        'ogs': top_ogs,
        'player_matches': top_matches,
        'subs_in': top_subs_in,
        'subs_out': top_subs_out,
    }


def teams_halloffame():
    top_goalscorers = (
        Team.objects.annotate(goals_count=Count('goals__match__league'))
        .filter(goals_count__gt=0)
        .order_by('-goals_count')
    )

    top_assistants = (
        Team.objects.annotate(assists_count=Count('goals__match__league', filter=Q(goals__assistent__isnull=False)))
        .filter(assists_count__gt=0)
        .order_by('-assists_count')
    )

    top_cs = (
        Team.objects.filter(team_events__event=OtherEvents.CLEAN_SHEET)
        .annotate(cs_count=Count('team_events__match__league'))
        .filter(cs_count__gt=0)
        .order_by('-cs_count')
    )

    top_ogs = (
        Team.objects.filter(team_events__event=OtherEvents.OWN_GOAL)
        .annotate(og_count=Count('team_events__match__league'))
        .filter(og_count__gt=0)
        .order_by('-og_count')
    )

    top_yellow_cards = (
        Team.objects.filter(team_events__event=OtherEvents.YELLOW_CARD)
        .annotate(yellow_cards_count=Count('team_events__match__league'))
        .filter(yellow_cards_count__gt=0)
        .order_by('-yellow_cards_count')
    )

    top_red_cards = (
        Team.objects.filter(team_events__event=OtherEvents.RED_CARD)
        .annotate(red_cards_count=Count('team_events__match__league'))
        .filter(red_cards_count__gt=0)
        .order_by('-red_cards_count')
    )

    top_subs = (
        Team.objects
        .annotate(subs_count=Count('substitutions'))
        .filter(subs_count__gt=0)
        .order_by('-subs_count')
    )

    home_matches_subquery = (
        Match.objects.filter(team_home=OuterRef('id'), is_played=True)
        .order_by().values('team_home')
        .annotate(c=Count('*')).values('c')
    )
    guest_matches_subquery = (
        Match.objects.filter(team_guest=OuterRef('id'), is_played=True)
        .order_by().values('team_guest')
        .annotate(c=Count('*')).values('c')
    )

    matches = (
        Team.objects
        .annotate(home_matches_count=Coalesce(Subquery(home_matches_subquery), 0),
                  guest_matches_count=Coalesce(Subquery(guest_matches_subquery), 0),
                  matches_count=F('home_matches_count') + F('guest_matches_count'))
        .filter(matches_count__gt=0)
        .annotate(wins_count=Count('won_matches'),
                  winrate=Cast(F('wins_count'), FloatField()) / F('matches_count') * 100)
        .order_by()
    )

    top_matches = matches.order_by('-matches_count')
    top_wins = matches.order_by('-wins_count')
    top_winrate = matches.filter(matches_count__gt=10).order_by('-winrate')

    return {
        'goals': top_goalscorers,
        'assists': top_assistants,
        'clean_sheets': top_cs,
        'yellow_cards': top_yellow_cards,
        'red_cards': top_red_cards,
        'ogs': top_ogs,
        'team_matches': top_matches,
        'wins': top_wins,
        'winrates': top_winrate,
        'subs': top_subs,
    }


class TeamRatingFilter(FilterSet):
    version = ModelChoiceFilter(
        queryset=RatingVersion.objects.select_related('related_season').all(), label='Версия', empty_label=None
    )

    class Meta:
        model = TeamRating
        fields = ['version']


class TeamRatingView(ListView):
    queryset = TeamRating.objects.select_related('team').all()
    template_name = 'tournament/team_rating.html'
    latest_rating_version = RatingVersion.objects.order_by('-number').first()

    def get(self, request,  **kwargs):
        params = request.GET or {'version': self.latest_rating_version.number}
        filter = TeamRatingFilter(params, queryset=self.queryset)
        selected_version = int(params['version'])
        source_season = (
            RatingVersion.objects.select_related('related_season').get(number=selected_version).related_season
        )
        previous_seasons = Season.objects.filter(
            number__lt=source_season.number, number__gt=5, title__contains='ЧР'
        ).order_by('-number')
        earliest_season_taken_into_account = None
        if previous_seasons.count() > 0:
            earliest_season_taken_into_account = list(previous_seasons[:5])[-1]

        seasons_weights = self.get_seasons_weights(source_season, earliest_season_taken_into_account)
        seasons = list(sorted(seasons_weights, key=lambda s: s.number))
        weighted_seasons_rating = self.get_weighted_seasons_rating(seasons, seasons_weights)

        previous_rating_version = TeamRating.objects.select_related('team').filter(version__number=selected_version - 1)
        previous_rating = {item.team: item.rank for item in previous_rating_version.all()}

        context = {
            'seasons_rating': weighted_seasons_rating,
            'seasons_weights': seasons_weights,
            'previous_rating': previous_rating,
            'filter': filter,
        }

        if request.htmx:
            return render(request, 'tournament/partials/team_rating_table.html', context)

        return render(request, self.template_name, context)

    @staticmethod
    def get_seasons_weights(source_season, earliest_season):
        weights = [1, 1, 1, 0.9, 0.8, 0.7]
        season_weights = {source_season: 1}
        season_count = 1
        if earliest_season:
            previous_seasons = (
                Season.objects.select_related('bound_season')
                .filter(number__gte=earliest_season.number, number__lt=source_season.number)
                .order_by('-number')
            )
            for season in previous_seasons:
                if season.title.startswith('ЧР'):
                    season_weights[season] = weights[season_count]
                    if season.bound_season:
                        season_weights[season.bound_season] = weights[season_count]
                    season_count += 1

        return season_weights

    @staticmethod
    def get_weighted_seasons_rating(seasons, seasons_weights):
        weighted_seasons_rating = {}
        seasons_rating = (
            SeasonTeamRating.objects.select_related('team', 'season')
            .filter(season__in=seasons)
            .order_by('season__number')
        )
        for rating_entry in seasons_rating:
            season = rating_entry.season
            season_weight = seasons_weights[season]
            team = rating_entry.team
            if season not in weighted_seasons_rating:
                weighted_seasons_rating[season] = {}
            if team not in weighted_seasons_rating[season]:
                weighted_seasons_rating[season][team] = round(rating_entry.total_points() * season_weight, 2)

        return weighted_seasons_rating


def player_detailed_statistics(request, pk):
    user = User.objects.filter(id=pk).select_related('user_player').first()
    try:
        player = user.user_player
    except:
        return HttpResponse(200)

    prefetches = (
        Prefetch('match_goal', queryset=Goal.objects.filter(author=player, match__is_played=True), to_attr='goals'),
        Prefetch(
            'match_goal', queryset=Goal.objects.filter(assistent=player, match__is_played=True), to_attr='assists'
        ),
        Prefetch(
            'match_event', queryset=OtherEvents.objects.cs().filter(author=player, match__is_played=True), to_attr='cs'
        ),
        Prefetch(
            'match_event',
            queryset=Substitution.objects.filter(player_out=player, match__is_played=True),
            to_attr='subs_out',
        ),
        Prefetch(
            'match_event',
            queryset=Substitution.objects.filter(player_in=player, match__is_played=True),
            to_attr='subs_in',
        ),
        Prefetch(
            'match_event',
            queryset=OtherEvents.objects.ogs().filter(author=player, match__is_played=True),
            to_attr='ogs',
        ),
        Prefetch(
            'match_event',
            queryset=OtherEvents.objects.yellow_cards().filter(author=player, match__is_played=True),
            to_attr='yellow_cards',
        ),
        Prefetch(
            'match_event',
            queryset=OtherEvents.objects.red_cards().filter(author=player, match__is_played=True),
            to_attr='red_cards',
        ),
    )

    matches = Match.objects.select_related('league__championship')
    home_matches = (
        matches.filter(team_home_start=player, is_played=True)
        .select_related('league__championship')
        .prefetch_related(Prefetch('team_home', to_attr='player_team'), *prefetches)
    )
    guest_matches = (
        matches.filter(team_guest_start=player, is_played=True)
        .select_related('league__championship')
        .prefetch_related(Prefetch('team_guest', to_attr='player_team'), *prefetches)
    )
    sub_matches = (
        Match.objects.filter(
            ~(Q(team_guest_start=player) | Q(team_home_start=player)),
            is_played=True,
            match_substitutions__player_in=player,
        )
        .select_related('league__championship')
        .prefetch_related(
            Prefetch(
                'match_substitutions',
                queryset=Substitution.objects.filter(player_in=player, match__is_played=True).select_related('team'),
                to_attr='player_subs',
            ),
            *prefetches,
        )
    )

    all_matches = list(sub_matches) + list(home_matches) + list(guest_matches)

    stats_by_season = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(int))))
    for match in all_matches:
        team = match.player_team if hasattr(match, 'player_team') else match.player_subs[0].team
        league = match.league
        season = league.championship

        stats_by_league = stats_by_season[season][team][league]
        stats_by_league['matches'] += 1
        stats_by_league['goals'] += len(match.goals)
        stats_by_league['assists'] += len(match.assists)
        stats_by_league['goals_assists'] += len(match.goals) + len(match.assists)
        stats_by_league['cs'] += len(match.cs)
        stats_by_league['subs_out'] += len(match.subs_out)
        stats_by_league['subs_in'] += len(match.subs_in)
        stats_by_league['ogs'] += len(match.ogs)
        stats_by_league['yellow_cards'] += len(match.yellow_cards)
        stats_by_league['red_cards'] += len(match.red_cards)

    all_goals = Goal.objects.filter(author=player, match__is_played=True)
    all_assists = Goal.objects.filter(assistent=player, match__is_played=True)
    all_clean_sheets = OtherEvents.objects.cs().filter(author=player, match__is_played=True)
    all_subs_out = Substitution.objects.filter(player_out=player, match__is_played=True)
    all_subs_in = Substitution.objects.filter(player_in=player, match__is_played=True)
    all_ogs = OtherEvents.objects.ogs().filter(author=player, match__is_played=True)
    all_yellow_cards = OtherEvents.objects.yellow_cards().filter(author=player, match__is_played=True)
    all_red_cards = OtherEvents.objects.red_cards().filter(author=player, match__is_played=True)

    overall_matches = len(all_matches)
    overall_goals = all_goals.count()
    overall_assists = all_assists.count()
    overall_goals_assists = overall_goals + overall_assists
    overall_clean_sheets = all_clean_sheets.count()
    overall_subs_out = all_subs_out.count()
    overall_subs_in = all_subs_in.count()
    overall_ogs = all_ogs.count()
    overall_yellow_cards = all_yellow_cards.count()
    overall_red_cards = all_red_cards.count()

    overall_stats = [
        overall_matches,
        overall_goals,
        overall_assists,
        overall_goals_assists,
        overall_clean_sheets,
        overall_subs_out,
        overall_subs_in,
        overall_ogs,
        overall_yellow_cards,
        overall_red_cards,
    ]

    overall_avg_goals = overall_goals / (overall_matches or 1)
    overall_avg_assists = overall_assists / (overall_matches or 1)
    overall_avg_goals_assists = overall_goals_assists / (overall_matches or 1)
    overall_avg_clean_sheets = overall_clean_sheets / (overall_matches or 1)
    overall_avg_yellow_cards = overall_yellow_cards / (overall_matches or 1)
    overall_avg_red_cards = overall_red_cards / (overall_matches or 1)
    overall_avg_own_goals = overall_ogs / (overall_matches or 1)
    overall_avg_subs_in = overall_subs_in / (overall_matches or 1)
    overall_avg_subs_out = overall_subs_out / (overall_matches or 1)

    overall_extra_stats = [
        overall_matches,
        overall_avg_goals,
        overall_avg_assists,
        overall_avg_goals_assists,
        overall_avg_clean_sheets,
        overall_avg_subs_out,
        overall_avg_subs_in,
        overall_avg_own_goals,
        overall_avg_yellow_cards,
        overall_avg_red_cards,
    ]

    extra_stats_by_season = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(float))))
    if overall_matches > 0:
        for season in stats_by_season:
            for team in stats_by_season[season]:
                for league in stats_by_season[season][team]:
                    league_stats = stats_by_season[season][team][league]
                    league_matches_count = league_stats['matches']
                    if league_matches_count == 0:
                        continue

                    extra_stats_by_league = extra_stats_by_season[season][team][league]
                    extra_stats_by_league['matches'] = league_stats['matches']
                    extra_stats_by_league['goals'] = league_stats['goals'] / league_matches_count
                    extra_stats_by_league['assists'] = league_stats['assists'] / league_matches_count
                    extra_stats_by_league['goals_assists'] = league_stats['goals_assists'] / league_matches_count
                    extra_stats_by_league['cs'] = league_stats['cs'] / league_matches_count
                    extra_stats_by_league['subs_out'] = league_stats['subs_out'] / league_matches_count
                    extra_stats_by_league['subs_in'] = league_stats['subs_in'] / league_matches_count
                    extra_stats_by_league['ogs'] = league_stats['ogs'] / league_matches_count
                    extra_stats_by_league['yellow_cards'] = league_stats['yellow_cards'] / league_matches_count
                    extra_stats_by_league['red_cards'] = league_stats['red_cards'] / league_matches_count

    first_match = (
        Match.objects.filter(
            Q(team_home_start=player) | Q(team_guest_start=player) | Q(match_substitutions__player_in=player)
        )
        .filter(is_played=True, match_date__isnull=False)
        .select_related('team_home', 'team_guest', 'league__championship')
        .order_by('match_date')
        .first()
    )

    fastest_goal = (
        Goal.objects.filter(author=player)
        .select_related('match__team_home', 'match__team_guest', 'match__league__championship')
        .order_by('time_min', 'time_sec')
        .first()
    )
    latest_goal = (
        Goal.objects.filter(author=player)
        .select_related('match__team_home', 'match__team_guest', 'match__league__championship')
        .order_by('-time_min', '-time_sec')
        .first()
    )
    most_goals_in_match = (
        Match.objects.filter(match_goal__author=player)
        .select_related('team_home', 'team_guest', 'league__championship')
        .annotate(goals=Count('id', filter=Q(match_goal__author=player)))
        .order_by('-goals')
        .first()
    )
    most_assists_in_match = (
        Match.objects.filter(match_goal__assistent=player)
        .select_related('team_home', 'team_guest', 'league__championship')
        .annotate(assists=Count('id', filter=Q(match_goal__assistent=player)))
        .order_by('-assists')
        .first()
    )
    most_goals_assists_in_match = (
        Match.objects.filter(Q(match_goal__author=player) | Q(match_goal__assistent=player))
        .select_related('team_home', 'team_guest', 'league__championship')
        .annotate(actions=Count('id', filter=Q(match_goal__assistent=player) | Q(match_goal__author=player)))
        .order_by('-actions')
        .first()
    )

    goals_subquery = (
        Goal.objects.filter(author=player, match__league__championship=OuterRef('id'))
        .order_by()
        .values('match__league__championship')
        .annotate(c=Count('*'))
        .values('c')
    )

    assists_subquery = (
        Goal.objects.filter(assistent=player, match__league__championship=OuterRef('id'))
        .order_by()
        .values('match__league__championship')
        .annotate(c=Count('*'))
        .values('c')
    )

    goals_assists_subquery = (
        Goal.objects.filter(Q(author=player) | Q(assistent=player), match__league__championship=OuterRef('id'))
        .order_by()
        .values('match__league__championship')
        .annotate(c=Count('*'))
        .values('c')
    )

    cs_subquery = (
        OtherEvents.objects.cs()
        .filter(author=player, match__league__championship=OuterRef('id'))
        .order_by()
        .values('match__league__championship')
        .annotate(c=Count('*'))
        .values('c')
    )

    most_goals_in_season = (
        Season.objects.annotate(goals=Subquery(goals_subquery)).filter(goals__isnull=False).order_by('-goals').first()
    )
    most_assists_in_season = (
        Season.objects.annotate(assists=Subquery(assists_subquery))
        .filter(assists__isnull=False)
        .order_by('-assists')
        .first()
    )
    most_goals_assists_in_season = (
        Season.objects.annotate(actions=Subquery(goals_assists_subquery))
        .filter(actions__isnull=False)
        .order_by('-actions')
        .first()
    )
    most_cs_in_season = (
        Season.objects.annotate(cs=Subquery(cs_subquery)).filter(cs__isnull=False).order_by('-cs').first()
    )

    other_stats = {
        'first_match': first_match,
        'fastest_goal': fastest_goal,
        'latest_goal': latest_goal,
        'most_goals_in_match': most_goals_in_match,
        'most_assists_in_match': most_assists_in_match,
        'most_goals_assists_in_match': most_goals_assists_in_match,
        'most_goals_in_season': most_goals_in_season,
        'most_assists_in_season': most_assists_in_season,
        'most_goals_assists_in_season': most_goals_assists_in_season,
        'most_cs_in_season': most_cs_in_season,
    }

    context = {
        'user': user,
        'stats': stats_by_season,
        'extra_stats': extra_stats_by_season,
        'overall_stats': overall_stats,
        'overall_extra_stats': overall_extra_stats,
        'other_stats': other_stats,
    }

    return render(request, 'tournament/partials/player_detailed_statistics.html', context)


def player_statistics_charts(request, pk):
    user = User.objects.filter(id=pk).select_related('user_player').first()
    try:
        player = user.user_player
    except:
        return HttpResponse(200)

    player_charts = StatCharts.for_player(player)
    matches_charts = player_charts.matches()
    goals_assists_charts = player_charts.goals_assists()
    cs_charts = player_charts.cs()
    cards_charts = player_charts.cards()

    context = {
        'matches_charts': matches_charts,
        'goals_assists_charts': goals_assists_charts,
        'cs_charts': cs_charts,
        'cards_charts': cards_charts,
    }

    return render(request, 'tournament/partials/player_stats_charts.html', context)


def team_statistics(request, pk):
    team = Team.objects.get(pk=pk)
    prefetches = (
        Prefetch('match_goal', queryset=Goal.objects.filter(team=team, match__is_played=True), to_attr='goals'),
        Prefetch(
            'match_goal', queryset=Goal.objects.filter(~Q(team=team), match__is_played=True), to_attr='conceded_goals'
        ),
        Prefetch(
            'match_goal',
            queryset=Goal.objects.filter(team=team, assistent__isnull=False, match__is_played=True),
            to_attr='assists',
        ),
        Prefetch(
            'match_event', queryset=OtherEvents.objects.cs().filter(team=team, match__is_played=True), to_attr='cs'
        ),
        Prefetch('match_event', queryset=Substitution.objects.filter(team=team, match__is_played=True), to_attr='subs'),
        Prefetch(
            'match_event', queryset=OtherEvents.objects.ogs().filter(team=team, match__is_played=True), to_attr='ogs'
        ),
        Prefetch(
            'match_event',
            queryset=OtherEvents.objects.yellow_cards().filter(team=team, match__is_played=True),
            to_attr='yellow_cards',
        ),
        Prefetch(
            'match_event',
            queryset=OtherEvents.objects.red_cards().filter(team=team, match__is_played=True),
            to_attr='red_cards',
        ),
    )

    all_matches = (
        Match.objects.filter(Q(team_home=team) | Q(team_guest=team), is_played=True)
        .select_related('league__championship', 'result__winner')
        .prefetch_related(*prefetches)
    )

    stats_by_season = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for match in all_matches:
        league = match.league
        season = league.championship

        stats_by_league = stats_by_season[season][league]
        stats_by_league['matches'] += 1
        stats_by_league['wins'] = stats_by_league['wins']
        stats_by_league['draws'] = stats_by_league['draws']
        stats_by_league['losses'] = stats_by_league['losses']
        if match.winner == team:
            stats_by_league['wins'] += 1
        elif match.is_draw():
            stats_by_league['draws'] += 1
        else:
            stats_by_league['losses'] += 1
        stats_by_league['winrate'] = 0
        stats_by_league['goals'] += len(match.goals)
        stats_by_league['conceded_goals'] += len(match.conceded_goals)
        stats_by_league['assists'] += len(match.assists)
        stats_by_league['cs'] += len(match.cs)
        stats_by_league['subs'] += len(match.subs)
        stats_by_league['ogs'] += len(match.ogs)
        stats_by_league['yellow_cards'] += len(match.yellow_cards)
        stats_by_league['red_cards'] += len(match.red_cards)

    for season in stats_by_season:
        for league in stats_by_season[season]:
            league_stats = stats_by_season[season][league]
            league_matches = league_stats['matches']
            league_wins = league_stats['wins']
            league_stats['winrate'] = float(league_wins) / (league_matches or 1) * 100

    all_wins = Match.objects.filter(Q(team_home=team) | Q(team_guest=team), result__winner=team, is_played=True)
    all_draws = Match.objects.filter(
        Q(team_home=team) | Q(team_guest=team), result__value=MatchResult.DRAW, is_played=True
    )
    all_losses = Match.objects.filter(
        Q(team_home=team) | Q(team_guest=team),
        ~Q(result__winner=team),
        ~Q(result__value=MatchResult.DRAW),
        is_played=True,
    )
    all_goals = Goal.objects.filter(team=team, match__is_played=True)
    all_conceded_goals = Goal.objects.filter(
        Q(match__team_home=team) | Q(match__team_guest=team), ~Q(team=team), match__is_played=True
    )
    all_assists = Goal.objects.filter(team=team, assistent__isnull=False, match__is_played=True)
    all_clean_sheets = OtherEvents.objects.cs().filter(team=team, match__is_played=True)
    all_subs = Substitution.objects.filter(team=team, match__is_played=True)
    all_ogs = OtherEvents.objects.ogs().filter(team=team, match__is_played=True)
    all_yellow_cards = OtherEvents.objects.yellow_cards().filter(team=team, match__is_played=True)
    all_red_cards = OtherEvents.objects.red_cards().filter(team=team, match__is_played=True)

    overall_matches = len(all_matches)
    overall_wins = all_wins.count()
    overall_draws = all_draws.count()
    overall_losses = all_losses.count()
    overall_winrate = float(overall_wins) / (overall_matches or 1) * 100
    overall_goals = all_goals.count()
    overall_conceded_goals = all_conceded_goals.count()
    overall_assists = all_assists.count()
    overall_clean_sheets = all_clean_sheets.count()
    overall_subs = all_subs.count()
    overall_ogs = all_ogs.count()
    overall_yellow_cards = all_yellow_cards.count()
    overall_red_cards = all_red_cards.count()

    overall_stats = [
        overall_matches,
        overall_wins,
        overall_draws,
        overall_losses,
        overall_winrate,
        overall_goals,
        overall_conceded_goals,
        overall_assists,
        overall_clean_sheets,
        overall_subs,
        overall_ogs,
        overall_yellow_cards,
        overall_red_cards,
    ]

    overall_avg_goals = overall_goals / (overall_matches or 1)
    overall_avg_conceded_goals = overall_conceded_goals / (overall_matches or 1)
    overall_avg_assists = overall_assists / (overall_matches or 1)
    overall_avg_clean_sheets = overall_clean_sheets / (overall_matches or 1)
    overall_avg_yellow_cards = overall_yellow_cards / (overall_matches or 1)
    overall_avg_red_cards = overall_red_cards / (overall_matches or 1)
    overall_avg_own_goals = overall_ogs / (overall_matches or 1)
    overall_avg_subs = overall_subs / (overall_matches or 1)

    overall_avg_stats = [
        overall_matches,
        overall_avg_goals,
        overall_avg_conceded_goals,
        overall_avg_assists,
        overall_avg_clean_sheets,
        overall_avg_subs,
        overall_avg_own_goals,
        overall_avg_yellow_cards,
        overall_avg_red_cards,
    ]

    extra_stats_by_season = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    if overall_matches > 0:
        for season in stats_by_season:
            for league in stats_by_season[season]:
                league_stats = stats_by_season[season][league]
                league_matches_count = league_stats['matches']
                if league_matches_count == 0:
                    continue

                extra_stats_by_league = extra_stats_by_season[season][league]
                extra_stats_by_league['matches'] = league_stats['matches']
                extra_stats_by_league['goals'] = league_stats['goals'] / league_matches_count
                extra_stats_by_league['conceded_goals'] = league_stats['conceded_goals'] / league_matches_count
                extra_stats_by_league['assists'] = league_stats['assists'] / league_matches_count
                extra_stats_by_league['cs'] = league_stats['cs'] / league_matches_count
                extra_stats_by_league['subs'] = league_stats['subs'] / league_matches_count
                extra_stats_by_league['ogs'] = league_stats['ogs'] / league_matches_count
                extra_stats_by_league['yellow_cards'] = league_stats['yellow_cards'] / league_matches_count
                extra_stats_by_league['red_cards'] = league_stats['red_cards'] / league_matches_count

    other_stats = {}

    first_match = (
        (team.home_matches.all() | team.guest_matches.all())
        .filter(is_played=True, match_date__isnull=False)
        .select_related('league__championship')
        .order_by('match_date')
        .first()
    )

    biggest_home_win = (
        team.home_matches.filter(score_home__gt=F('score_guest'))
        .annotate(goal_diff=F('score_home') - F('score_guest'))
        .select_related('league__championship')
        .order_by('-goal_diff')
        .first()
    )

    biggest_guest_win = (
        team.guest_matches.filter(score_guest__gt=F('score_home'))
        .annotate(goal_diff=F('score_guest') - F('score_home'))
        .select_related('league__championship')
        .order_by('-goal_diff')
        .first()
    )

    biggest_home_loss = (
        team.home_matches.filter(score_home__lt=F('score_guest'))
        .annotate(goal_diff=F('score_home') - F('score_guest'))
        .select_related('league__championship')
        .order_by('goal_diff')
        .first()
    )

    biggest_guest_loss = (
        team.guest_matches.filter(score_guest__lt=F('score_home'))
        .annotate(goal_diff=F('score_guest') - F('score_home'))
        .select_related('league__championship')
        .order_by('goal_diff')
        .first()
    )

    most_effective_draw = (
        (team.home_matches.all() | team.guest_matches.all())
        .filter(score_guest=F('score_home'))
        .annotate(scored_total=F('score_home') + F('score_guest'))
        .select_related('league__championship')
        .order_by('-scored_total')
        .first()
    )

    cards_filter = Q(match_event__event=OtherEvents.YELLOW_CARD) | Q(match_event__event=OtherEvents.RED_CARD)
    most_biggest_cards_given = (
        (team.home_matches.all() | team.guest_matches.all())
        .annotate(cards_count=Count('match_event', filter=cards_filter))
        .select_related('league__championship')
        .order_by('-cards_count')
    ).first()

    fastest_goal = (
        Goal.objects.filter(team=team)
        .select_related('match__team_home', 'match__team_guest', 'match__league__championship')
        .order_by('time_min', 'time_sec')
        .first()
    )
    latest_goal = (
        Goal.objects.filter(team=team)
        .select_related('match__team_home', 'match__team_guest', 'match__league__championship')
        .order_by('-time_min', '-time_sec')
        .first()
    )

    greatest_goalscorer = team.goals.values('author').annotate(goals=Count('author')).order_by('-goals').first()
    greatest_assistant = (
        team.goals.values('assistent').annotate(assists=Count('assistent')).order_by('-assists').first()
    )
    greatest_goalkeeper = (
        team.team_events.filter(event=OtherEvents.CLEAN_SHEET)
        .values('author')
        .annotate(cs=Count('author'))
        .order_by('-cs')
        .first()
    )

    home_matches = (
        Match.objects.filter(team_home=team, is_played=True)
        .values(player=F('team_home_start__id'))
        .annotate(matches=Count('team_home_start__id'))
        .order_by('-matches')
    )
    guest_matches = (
        Match.objects.filter(team_guest=team, is_played=True)
        .values(player=F('team_guest_start__id'))
        .annotate(matches=Count('team_guest_start__id'))
        .order_by('-matches')
    )
    sub_matches = (
        Substitution.objects.filter(team=team)
        .values(player=F('player_in'))
        .distinct()
        .annotate(matches=Count('match', distinct=True))
        .order_by('-matches')
    )

    all_team_matches = list(home_matches) + list(guest_matches) + list(sub_matches)

    # find all matches where player was in start but then also appeared on the field as a substitute
    # to eliminate duplicates while calculating total matches count per player
    all_team_players = set((player_matches['player'] for player_matches in all_team_matches))
    dup_matches_subqery = (
        Match.objects
        .filter(
            Q(team_home_start=OuterRef('id')) | Q(team_guest_start=OuterRef('id')),
            match_substitutions__player_in=OuterRef('id'),
            is_played=True
        )
        .order_by()
        .values('match_substitutions__player_in')
        .annotate(c=Count('id', distinct=True))
        .values('c')
    )
    dup_matches = (
        Player.objects.filter(pk__in=all_team_players)
        .values(player=F('id'))
        .annotate(matches=Coalesce(Subquery(dup_matches_subqery), 0))
    )
    dup_matches_dict = {item['player']: item['matches'] for item in dup_matches}

    matches_by_player = defaultdict(int)
    for player_matches in all_team_matches:
        matches_by_player[player_matches['player']] += player_matches['matches']
    for player in all_team_players:
        if player in dup_matches_dict:
            matches_by_player[player] -= dup_matches_dict[player]

    greatest_player = None
    if len(all_team_matches) > 0:
        greatest_player = sorted(matches_by_player.items(), key=lambda kv: kv[1], reverse=True)[0]

    greatest_sub_in = sub_matches.first()

    other_stats['first_match'] = first_match
    other_stats['biggest_home_win'] = biggest_home_win
    other_stats['biggest_guest_win'] = biggest_guest_win
    other_stats['biggest_home_loss'] = biggest_home_loss
    other_stats['biggest_guest_loss'] = biggest_guest_loss
    other_stats['most_effective_draw'] = most_effective_draw
    other_stats['most_biggest_cards_given'] = most_biggest_cards_given
    other_stats['fastest_goal'] = fastest_goal
    other_stats['latest_goal'] = latest_goal

    if greatest_goalscorer:
        other_stats['greatest_goalscorer'] = {
            'player': User.objects.get(user_player=greatest_goalscorer['author']),
            'count': greatest_goalscorer['goals'],
        }
    if greatest_assistant:
        other_stats['greatest_assistant'] = {
            'player': User.objects.get(user_player=greatest_assistant['assistent']),
            'count': greatest_assistant['assists'],
        }
    if greatest_goalkeeper:
        other_stats['greatest_goalkeeper'] = {
            'player': User.objects.get(user_player=greatest_goalkeeper['author']),
            'count': greatest_goalkeeper['cs'],
        }
    if greatest_player:
        other_stats['greatest_player'] = {
            'player': User.objects.get(user_player=greatest_player[0]),
            'count': greatest_player[1],
        }
    if greatest_sub_in:
        other_stats['greatest_sub_in'] = {
            'player': User.objects.get(user_player=greatest_sub_in['player']),
            'count': greatest_sub_in['matches'],
        }

    context = {
        'team': team,
        'stats': stats_by_season,
        'extra_stats': extra_stats_by_season,
        'overall_stats': overall_stats,
        'overall_avg_stats': overall_avg_stats,
        'other_stats': other_stats,
    }

    return render(request, 'tournament/partials/team_statistics.html', context)


def team_statistics_charts(request, pk):
    team = Team.objects.filter(id=pk).first()

    team_charts = StatCharts.for_team(team)
    matches_charts = team_charts.matches()
    goals_assists_charts = team_charts.goals_assists()
    cs_charts = team_charts.cs()
    cards_charts = team_charts.cards()

    context = {
        'matches_charts': matches_charts,
        'goals_assists_charts': goals_assists_charts,
        'cs_charts': cs_charts,
        'cards_charts': cards_charts,
    }

    return render(request, 'tournament/partials/team_stats_charts.html', context)
