from collections import defaultdict
from datetime import datetime, timedelta
from functools import reduce

from core.forms import NewCommentForm
from core.utils import get_comments_for_object, get_paginated_comments
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count, Prefetch, Q, OuterRef, Subquery, F, FloatField
from django.db.models.functions import Coalesce, Cast
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView
from django_filters import ChoiceFilter, FilterSet, ModelChoiceFilter

from .forms import EditTeamProfileForm, FreeAgentForm
from .models import (
    Disqualification,
    FreeAgent,
    League,
    Match,
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
    context_object_name = 'disqualifications'
    template_name = 'tournament/disqualification/disqualifications_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = DisqualificationFilter(self.request.GET, queryset=self.queryset)

        return context


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
    context_object_name = 'transfers'
    template_name = 'tournament/transfers/transfers_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = TransferFilter(self.request.GET, queryset=self.queryset)

        return context


class FreeAgentList(ListView):
    queryset = FreeAgent.objects.select_related('player__user_profile').filter(is_active=True).order_by('-created')
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

        return HttpResponse('Ошибка доступа')

    return redirect('tournament:free_agent')


def update_entry(request, pk):
    free_agent = get_object_or_404(FreeAgent, pk=pk)
    if request.method == 'POST':
        if request.user == free_agent.player:
            free_agent.created = timezone.now()
            free_agent.save()
            return redirect('tournament:free_agent')

        return HttpResponse('Ошибка доступа')

    return redirect('tournament:free_agent')


def edit_team_profile(request, slug):
    team = get_object_or_404(Team, slug=slug)
    if request.method == 'POST' and (request.user == team.owner or request.user.is_superuser):
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

        substitutes = {match.team_home: [], match.team_guest: []}
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
                substitutes[team].append(player_in)
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
    context_object_name = 'all_postponements'
    template_name = 'tournament/postponements/postponements.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filter = LeagueByTitleFilter(
            {'tournament': self.request.GET.get('tournament', 'Высшая лига')},
            queryset=League.objects.filter(championship__is_active=True).prefetch_related('postponement_slots'),
        )
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
        tournament = request.GET.get('tournament', 'Высшая лига')
        for team in teams:
            team_postponements = team.get_postponements(leagues=[match.league])
            if team_postponements.count() + 1 > total_slots_count:
                request.session['show_exceeded_limit_modal'] = True
                request.session['exceeded_limit_message'] = f'Команда {team.title} исчерпала лимит переносов'
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


@require_POST
def cancel_postponement(request, pk):
    postponement = get_object_or_404(Postponement, pk=pk)
    user_teams = get_user_teams(request.user)

    if (postponement.match.team_home in user_teams) or (postponement.match.team_guest in user_teams):
        postponement.cancelled_at = timezone.now()
        postponement.cancelled_by = request.user
        postponement.save()

        return redirect(reverse('tournament:postponements') + '?tournament={}'.format(request.GET['tournament']))

    return HttpResponse('Ошибка доступа')


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
        Match.objects.filter(team_home=OuterRef('id'))
        .order_by().values('team_home')
        .annotate(c=Count('*')).values('c')
    )
    guest_matches_subquery = (
        Match.objects.filter(team_guest=OuterRef('id'))
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
    context_object_name = 'team_rating'
    template_name = 'tournament/team_rating.html'
    latest_rating_version = RatingVersion.objects.order_by('-number').first()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET or {'version': self.latest_rating_version.number}
        context['filter'] = TeamRatingFilter(params, queryset=self.queryset)
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
        context['seasons_rating'] = weighted_seasons_rating
        context['seasons_weights'] = seasons_weights

        previous_rating_version = TeamRating.objects.select_related('team').filter(version__number=selected_version - 1)
        context['previous_rating'] = {item.team: item.rank for item in previous_rating_version.all()}

        return context

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
