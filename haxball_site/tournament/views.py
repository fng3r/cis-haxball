import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import groupby

from django.contrib import messages
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Count, Exists, F, Max, Min, OuterRef, Prefetch, Q, Subquery, Window
from django.db.models.functions import Coalesce, Rank
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, TemplateView

from django_filters import ChoiceFilter, FilterSet, ModelChoiceFilter
from django_htmx.http import trigger_client_event

from core.forms import NewCommentForm
from core.utils import get_comments_for_object, get_paginated_comments
from fantasy_league.models import FantasyTournament
from haxball_site import settings
from predictions.models import PredictionsContestTournament

from .charts import StatCharts
from .forms import (
    AwardVotingForm,
    ComparePlayersForm,
    CompareTeamsForm,
    EditTeamProfileForm,
    FreeAgentForm,
    TeamsYearlyRatingForm,
)
from .models import (
    Award,
    AwardCampaign,
    AwardResult,
    AwardSubmission,
    AwardVote,
    AwardVoter,
    Card,
    CleanSheet,
    Disqualification,
    FreeAgent,
    Goal,
    League,
    Match,
    MatchReplayStats,
    MatchReplayStatsStatus,
    MatchResult,
    Nation,
    Player,
    PlayerRating,
    PlayerRatingVersion,
    PlayerTransfer,
    Postponement,
    Season,
    SeasonTeamRating,
    Substitution,
    Team,
    TeamRating,
    TeamRatingVersion,
    TournamentWinner,
    TourNumber,
)
from .services.hall_of_fame import HallOfFameService
from .services.replay_stats import MatchReplayStatsAggregator
from .services.structured_medals import get_team_medals
from .templatetags.tournament_extras import get_team_squad_stats, get_user_teams


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


class CardFilter(FilterSet):
    season = ModelChoiceFilter(
        field_name='match__league__championship',
        label='Сезон',
        queryset=Season.objects.filter(number__gt=5).order_by('-number'),
    )
    team = ModelChoiceFilter(queryset=Team.objects.all())
    player = ModelChoiceFilter(
        field_name='author',
        label='Игрок',
        queryset=Player.objects.all(),
    )
    card_type = ChoiceFilter(
        field_name='kind',
        label='Тип',
        empty_label='Все',
        choices=(
            (Card.Kind.YELLOW, 'ЖК'),
            (Card.Kind.RED, 'КК'),
        ),
    )
    inspector = ModelChoiceFilter(
        field_name='match__inspector',
        label='Инспектор',
        queryset=User.objects.filter(Exists(Match.objects.filter(inspector=OuterRef('pk')))),
    )

    class Meta:
        model = Card
        fields = ['season', 'team', 'player', 'card_type', 'inspector']


class CardsList(ListView):
    queryset = (
        Card.objects.all()
        .select_related(
            'team',
            'author__name__user_profile',
            'match__inspector__user_profile',
            'match__team_home',
            'match__team_guest',
            'match__league__championship',
        )
        .order_by('-match__league__championship__number', '-match__match_date')
    )
    current_season = Season.objects.order_by('-number').first()
    template_name = 'tournament/card/cards.html'
    paginate_by = 25

    def get(self, request, **kwargs):
        filter = CardFilter(request.GET, queryset=self.queryset)
        paginator = Paginator(filter.qs, self.paginate_by)
        page = request.GET.get('page')
        cards = paginator.get_page(page)

        if request.htmx:
            return render(request, 'tournament/card/partials/cards_list.html', {'cards': cards})

        return render(request, self.template_name, {'cards': cards, 'filter': filter})


class DisqualificationFilter(FilterSet):
    season = ModelChoiceFilter(
        field_name='match__league__championship',
        label='Сезон',
        queryset=Season.objects.filter(number__gt=14).order_by('-number'),
    )
    team = ModelChoiceFilter(queryset=Team.objects.filter(leagues__championship__number__gt=14).distinct())
    player = ModelChoiceFilter(queryset=Player.objects.all())
    inspector = ModelChoiceFilter(
        field_name='match__inspector',
        label='Инспектор',
        queryset=User.objects.filter(
            Exists(Match.objects.filter(inspector=OuterRef('pk'), league__championship__number__gt=14))
        ),
    )

    class Meta:
        model = Disqualification
        fields = ['season', 'team', 'player', 'inspector']


class DisqualificationsList(ListView):
    queryset = (
        Disqualification.objects.select_related(
            'team',
            'player__name__user_profile',
            'match__inspector__user_profile',
            'match__team_home',
            'match__team_guest',
            'match__league__championship',
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
                {'disqualifications': disqualifications},
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
                {'transfers': transfers},
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
        fa = FreeAgent.objects.filter(player=request.user).first()
        fa_form = FreeAgentForm(data=request.POST, instance=fa)
        if fa_form.is_valid():
            free_agent = fa_form.save(commit=False)
            free_agent.player = request.user
            free_agent.created = timezone.now()
            free_agent.is_active = True
            free_agent.save()

        paginator = Paginator(self.queryset, self.paginate_by)
        free_agents = paginator.get_page(1)
        context = {'agents': free_agents}

        return render(request, 'tournament/free_agents/free_agents.html#content-container', context)


def remove_free_agent_entry(request, pk):
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


def update_free_agent_entry(request, pk):
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

    def get_template_names(self):
        if self.request.htmx:
            return 'tournament/teams/partials/edit_team_form.html'

        return 'tournament/teams/edit_team.html'

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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        team = context['team']
        team_seasons = Season.objects.filter(tournaments_in_season__teams=team).distinct()
        context['seasons'] = team_seasons
        context['tournaments'] = get_team_tournaments(team)
        context['structured_medals'] = get_team_medals(team)
        context['medals_view'] = self.request.GET.get('medals', 'legacy')

        latest_rating_version = PlayerRatingVersion.objects.aggregate(number=Max('number'))['number']
        rating = PlayerRating.objects.select_related('player').filter(
            player__in=team.players_in_team.all(),
            version__number=latest_rating_version,
        )
        current_squad_rating = {}
        for rating_entry in rating:
            current_squad_rating[rating_entry.player] = rating_entry
        context['current_squad_rating'] = current_squad_rating

        return context

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


def get_team_tournaments(team, season=None):
    tournaments = League.objects.filter(teams=team).select_related('championship')
    if season:
        return tournaments.filter(championship=season).distinct().order_by('priority', 'title')

    return tournaments.order_by('title', 'priority', '-championship__number').distinct('title')


class TeamList(ListView):
    queryset = Team.objects.all().order_by('-title')
    context_object_name = 'teams'
    template_name = 'tournament/teams/teams_list.html'


class LeagueDetail(DetailView):
    context_object_name = 'league'
    model = League
    template_name = 'tournament/tournament/tournament_detail.html'

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .prefetch_related(
                'stages',
                'stages__tours__stubs',
                'stages__tours__league',
                'stages__tours__tour_matches__team_home',
                'stages__tours__tour_matches__team_guest',
                'stages__tours__tour_matches__result__winner',
                'stages__tours__tour_matches__group',
                'stages__tours__tour_matches__stage',
                'tours__tour_matches__team_home',
                'tours__tour_matches__team_guest',
                'tours__stage',
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        league = context['league']

        page = self.request.GET.get('page')
        comments_obj = get_comments_for_object(League, league.id)
        comments = get_paginated_comments(comments_obj, page)
        comment_form = NewCommentForm()

        winners = self._get_all_winners(league)
        default_stage = self._get_default_stage(league)
        quick_links = self._get_quick_links(league)

        context['page'] = page
        context['comments'] = comments
        context['comment_form'] = comment_form
        context['winners'] = winners
        context['default_stage'] = default_stage
        context['quick_links'] = quick_links
        return context

    def _get_quick_links(self, league: League):
        quick_links = []

        fantasy_tournament = FantasyTournament.objects.filter(league=league).first()
        if fantasy_tournament:
            quick_links.append(
                {
                    'label': 'Fantasy League',
                    'url': (
                        f'{reverse("fantasy_league:main")}'
                        f'?season={league.championship_id}&tournament={fantasy_tournament.id}'
                    ),
                }
            )

        predictions_tournament = PredictionsContestTournament.objects.filter(league=league).first()
        if predictions_tournament:
            quick_links.append(
                {
                    'label': 'Прогнозы',
                    'url': (
                        f'{reverse("predictions:main")}'
                        f'?season={league.championship_id}&tournament={predictions_tournament.id}'
                    ),
                }
            )

        now = timezone.now()
        has_awards = (
            AwardCampaign.objects.filter(season=league.championship, voting_start_date__lte=now).exists()
            and Award.objects.filter(league=league).exists()
        )
        if has_awards:
            quick_links.append(
                {
                    'label': 'Награды',
                    'url': reverse('tournament:awards_main', kwargs={'slug': league.slug}),
                }
            )

        return quick_links

    def _get_all_winners(self, league: League):
        winners = (
            TournamentWinner.objects.filter(league__type=league.type)
            .select_related('season', 'winner')
            .order_by('-season__number')
        )

        return {season: list(winners) for season, winners in groupby(winners, key=lambda x: x.season)}

    def _get_default_stage(self, league: League):
        if league.championship.is_active:
            now = timezone.now()
            default_stage = (
                league.stages.annotate(start_date=Min('tours__date_from'))
                .filter(start_date__lt=now)
                .order_by('-start_date', 'order')
            ).first()
            if not default_stage:
                default_stage = league.stages.first()
        else:
            default_stage = league.stages.first()

        return default_stage


class MatchDetail(DetailView):
    model = Match
    context_object_name = 'match'
    template_name = 'tournament/match/detail.html'

    def get_queryset(self):
        return (
            Match.objects.select_related(
                'team_home', 'team_guest', 'numb_tour', 'league__championship', 'inspector__user_profile'
            )
            .prefetch_related(
                'team_home_start__name__user_profile',
                'team_home_start__player_nation',
                'team_guest_start__name__user_profile',
                'team_guest_start__player_nation',
                'disqualifications__team',
                'disqualifications__player__name__user_profile',
                'disqualifications__tours__league',
                Prefetch(
                    'replay_stats',
                    queryset=MatchReplayStats.objects.select_related('match_replay').prefetch_related(
                        'players__player__name__user_profile',
                        'players__team',
                    ),
                ),
            )
            .select_related('replay_stats_status')
        )

    def get_time_played_by_player(self, match: Match) -> dict[int, str]:
        time_played = defaultdict(int)
        full_match_time = int(match.duration.total_seconds())
        start_players = match.team_home_start.all() | match.team_guest_start.all()

        for player in start_players:
            time_played[player.id] = full_match_time

        for substitution in match.match_substitutions.all():
            player_in = substitution.player_in.id
            player_out = substitution.player_out.id
            time_until_match_end = int(
                full_match_time
                - timedelta(minutes=substitution.time_min, seconds=substitution.time_sec).total_seconds()
            )
            time_played[player_in] += time_until_match_end
            time_played[player_out] -= time_until_match_end

        return {player_id: datetime.fromtimestamp(sec).strftime('%M:%S') for player_id, sec in time_played.items()}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        match: Match = context['match']

        page = self.request.GET.get('page')
        comments_obj = get_comments_for_object(Match, match.id)
        comments = get_paginated_comments(comments_obj, page)

        context['page'] = page
        context['comments'] = comments
        comment_form = NewCommentForm()
        context['comment_form'] = comment_form

        context['latest_matches'] = {
            'team_home': self.get_latest_matches(match, match.team_home),
            'team_guest': self.get_latest_matches(match, match.team_guest),
        }

        if match.stage.is_playoff and match.bracket_slot:
            series_matches = (
                Match.objects.filter(
                    numb_tour=match.numb_tour,
                    bracket_slot=match.bracket_slot,
                )
                .filter(
                    Q(team_home=match.team_home, team_guest=match.team_guest)
                    | Q(team_home=match.team_guest, team_guest=match.team_home)
                )
                .order_by('id')
            )
            context['series_matches'] = series_matches
        else:
            context['series_matches'] = []

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

        regular_goals = match.match_goal.regular().values('author').annotate(goals=Count('author')).order_by('author')
        goals_by_player = {d['author']: d['goals'] for d in regular_goals}
        context['goals_by_player'] = goals_by_player

        assists = (
            match.match_goal.exclude(assistent=None)
            .values('assistent')
            .annotate(assists=Count('assistent'))
            .order_by('assistent')
        )
        assists_by_player = {d['assistent']: d['assists'] for d in assists}
        context['assists_by_player'] = assists_by_player

        clean_sheets = match.clean_sheets.all().values('author').annotate(cs=Count('author')).order_by('author')
        clean_sheets_by_player = {d['author']: d['cs'] for d in clean_sheets}
        context['clean_sheets_by_player'] = clean_sheets_by_player

        context['time_played_by_player'] = self.get_time_played_by_player(match)

        cards = match.cards.select_related('team', 'author__name__user_profile').order_by('team')
        context['cards'] = cards

        # Replay-based advanced stats (Haxball Analyzer)
        replay_status = getattr(match, 'replay_stats_status', None)
        context['replay_stats_status'] = replay_status
        if replay_status and replay_status.status in {
            MatchReplayStatsStatus.Status.SUCCESS,
            MatchReplayStatsStatus.Status.PARTIAL,
        }:
            parts = list(match.replay_stats.all())
            context['match_replay_stats_aggregated'] = MatchReplayStatsAggregator(match=match, parts=parts).build()
        else:
            context['match_replay_stats_aggregated'] = None

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

        h2h_matches = all_matches_between.select_related('league__championship', 'team_home', 'team_guest').order_by(
            '-match_date', '-id'
        )
        context['h2h_matches'] = h2h_matches

        player_stats = {}
        player_stats[match.team_home] = self.get_player_stats(match.team_home, h2h_matches)
        player_stats[match.team_guest] = self.get_player_stats(match.team_guest, h2h_matches)
        context['player_stats'] = player_stats

        return context

    def get_latest_matches(self, match: Match, team: Team):
        match_date_condition = ~Q(pk__in=[])
        if match.is_played:
            match_date = match.match_date or match.numb_tour.date_to
            match_date_condition = Q(match_date__lt=match_date) | Q(
                match_date=match_date,
                stage__order__lte=match.stage.order,
                numb_tour__lt=match.numb_tour,
            )

        return reversed(
            Match.objects.filter(
                Q(team_home=team) | Q(team_guest=team),
                ~Q(id=match.id),
                match_date_condition,
                league=match.league,
                is_played=True,
            )
            .select_related('team_home', 'team_guest', 'numb_tour', 'league__championship', 'stage', 'group', 'result')
            .order_by('-match_date', '-numb_tour', '-id')[:5]
        )

    def get_player_stats(self, team: Team, selected_matches) -> dict:
        top_matches = (
            team.played_matches.filter(match__in=selected_matches)
            .values(pl=F('player__nickname'))
            .annotate(count=Count('player'))
            .order_by('-count')
            .first()
        )
        top_goals = (
            team.goals.regular()
            .filter(match__in=selected_matches)
            .values(pl=F('author__nickname'))
            .annotate(count=Count('author'))
            .order_by('-count')
            .first()
        )
        top_assists = (
            team.goals.filter(match__in=selected_matches, assistent__isnull=False)
            .values(pl=F('assistent__nickname'))
            .annotate(count=Count('assistent'))
            .order_by('-count')
            .first()
        )
        top_cs = (
            team.clean_sheets.all()
            .filter(match__in=selected_matches)
            .values(pl=F('author__nickname'))
            .annotate(count=Count('author'))
            .order_by('-count')
            .first()
        )

        return {
            'matches': top_matches or {'pl': '–', 'count': 0},
            'goals': top_goals or {'pl': '–', 'count': 0},
            'assists': top_assists or {'pl': '–', 'count': 0},
            'cs': top_cs or {'pl': '–', 'count': 0},
        }


class PostponementFilter(FilterSet):
    tournament = ModelChoiceFilter(
        field_name='match__league',
        label='Турнир',
        empty_label=None,
        queryset=(
            League.objects.annotate(stages_with_postponements=Count('stages', filter=Q(stages__postponable=True)))
            .filter(championship__is_active=True, stages_with_postponements__gt=0)
            .select_related('postponement_slots')
        ),
    )

    class Meta:
        model = Postponement
        fields = ['tournament']


def get_postponements_queryset():
    return (
        Postponement.objects.filter(match__league__championship__is_active=True)
        .select_related('match__team_home', 'match__team_guest', 'match__numb_tour')
        .prefetch_related(
            'teams',
            'taken_by__user_profile__user_icon',
            'cancelled_by__user_profile__user_icon',
            'taken_by__user_player__team__owner',
            'taken_by__user_player__team__captain',
            'taken_by__user_player__team__captain_assistant',
            'cancelled_by__user_player__team__owner',
            'cancelled_by__user_player__team__captain',
            'cancelled_by__user_player__team__captain_assistant',
            Prefetch(
                'taken_by__owned_teams',
                queryset=Team.objects.filter(leagues__championship__is_active=True).distinct(),
                to_attr='active_owned_teams',
            ),
            Prefetch(
                'cancelled_by__owned_teams',
                queryset=Team.objects.filter(leagues__championship__is_active=True).distinct(),
                to_attr='active_owned_teams',
            ),
        )
        .order_by('-taken_at')
    )


class PostponementsList(ListView):
    default_tournament = League.objects.filter(championship__is_active=True).order_by('priority').first()
    queryset = get_postponements_queryset()
    template_name = 'tournament/postponements/postponements.html'

    def get(self, request, **kwargs):
        league_id = self.request.GET.get('tournament', None)
        league = League.objects.get(pk=league_id) if league_id else self.default_tournament
        filter = PostponementFilter({'tournament': league}, queryset=self.queryset)

        paginator = Paginator(filter.qs, 20)
        page = self.request.GET.get('page')

        postponements = paginator.get_page(page)

        context = {
            'league': league,
            'postponements': postponements,
            'teams': league.teams.all(),
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
        tournament = data.get('tournament')

        postponements_count = match.postponements.filter(is_cancelled=False).count()
        if postponements_count >= 2:
            messages.error(request, 'Матч не может быть перенесен более 2 раз')
            return self.redirect_to_postponements_page(tournament)

        if postponements_count > 0 and type == 'common':
            messages.error(request, 'На уже перенесенный матч может быть взят только экcтренный перенос')
            return self.redirect_to_postponements_page(tournament)

        if team == 'mutual':
            teams = [match.team_home, match.team_guest]
        else:
            team_id = int(team)
            teams = [Team.objects.get(pk=team_id)]
        is_emergency = type == 'emergency'
        slots = match.league.get_postponement_slots()
        for team in teams:
            all_postponements = team.get_postponements(match.league)
            if all_postponements.count() + 1 > slots.total_count:
                messages.error(
                    request,
                    f'Команда {team.title} исчерпала лимит переносов',
                )

                return self.redirect_to_postponements_page(tournament)

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

        return self.redirect_to_postponements_page(tournament)

    def redirect_to_postponements_page(self, tournament):
        return redirect(reverse('tournament:postponements') + f'?tournament={tournament}')


class PostponementsEvents(ListView):
    def get(self, request, **kwargs):
        league_id = self.request.GET['tournament']
        league = League.objects.get(id=league_id)
        all_postponements = get_postponements_queryset().filter(match__league=league)
        paginator = Paginator(all_postponements, 20)
        page = self.request.GET.get('page')
        postponements = paginator.get_page(page)

        context = {
            'postponements': postponements,
            'league': league,
        }

        return render(request, 'tournament/postponements/postponements.html#postponements-events', context)


@require_POST
def cancel_postponement(request, pk):
    data = request.POST
    postponement = get_object_or_404(Postponement, pk=pk)
    user_teams = get_user_teams(request.user)

    if (postponement.match.team_home in user_teams) or (postponement.match.team_guest in user_teams):
        postponement.cancel(request.user)
        postponement.save()
    else:
        messages.error(request, 'Ошибка доступа')

    return redirect(reverse('tournament:postponements') + f'?tournament={data.get("tournament")}')


class HallOfFamePlayerFilter(FilterSet):
    nation = ModelChoiceFilter(queryset=Nation.objects.all(), label='Страна', empty_label='Любая')
    season = ModelChoiceFilter(queryset=Season.objects.filter(number__gt=5), label='Сезон', empty_label='Все')
    tournament = ChoiceFilter(
        choices=League.Type.choices,
        label='Турнир',
        empty_label='Все',
    )


class HallOfFameTeamFilter(FilterSet):
    season = ModelChoiceFilter(queryset=Season.objects.filter(number__gt=5), label='Сезон', empty_label='Все')
    tournament = ChoiceFilter(
        choices=League.Type.choices,
        label='Турнир',
        empty_label='Все',
    )


def hall_of_fame(request):
    nation_id = request.GET.get('nation', None)
    nation = Nation.objects.get(id=nation_id) if nation_id else None

    season_id = request.GET.get('season', None)
    seasons = Season.objects.filter(id=season_id) if season_id else Season.objects.filter(number__gt=5)

    tournament_type = request.GET.get('tournament', '')
    tournaments = League.objects.filter(type=tournament_type) if tournament_type else League.objects.all()

    service = HallOfFameService()
    players = service.get_players_tops(seasons, tournaments, nation)
    teams = service.get_teams_tops(seasons, tournaments)

    return render(
        request,
        'tournament/hall_of_fame/hall_of_fame.html',
        {
            'players_tops': players,
            'players_filter': HallOfFamePlayerFilter(request.GET, queryset=Player.objects.none()),
            'teams_tops': teams,
            'teams_filter': HallOfFameTeamFilter(request.GET, queryset=Team.objects.none()),
        },
    )


def players_hall_of_fame(request):
    nation_id = request.GET.get('nation', None)
    nation = Nation.objects.get(id=nation_id) if nation_id else None

    season_id = request.GET.get('season', None)
    seasons = Season.objects.filter(id=season_id) if season_id else Season.objects.filter(number__gt=5)

    tournament_type = request.GET.get('tournament', '')
    tournaments = League.objects.filter(type=tournament_type) if tournament_type else League.objects.all()

    service = HallOfFameService()
    players = service.get_players_tops(seasons, tournaments, nation)

    return render(
        request,
        'tournament/hall_of_fame/partials/players_hall_of_fame.html#players-content',
        {
            'players_tops': players,
            'players_filter': HallOfFamePlayerFilter(request.GET, queryset=Player.objects.none()),
        },
    )


def players_top_by_stat(request):
    nation_id = request.GET.get('nation', None)
    nation = Nation.objects.get(id=nation_id) if nation_id else None

    season_id = request.GET.get('season', None)
    seasons = Season.objects.filter(id=season_id) if season_id else Season.objects.filter(number__gt=5)

    tournament_type = request.GET.get('tournament', '')
    tournaments = League.objects.filter(type=tournament_type) if tournament_type else League.objects.all()

    stat = request.GET.get('stat')
    page = request.GET.get('page')

    service = HallOfFameService()
    players = service.get_players_top_by_stat(seasons, tournaments, nation, stat, page)

    return render(
        request,
        'tournament/hall_of_fame/partials/players_top.html#players_top_list',
        {
            'players': players,
            'stat': stat,
            'players_filter': HallOfFamePlayerFilter(request.GET, queryset=Player.objects.none()),
        },
    )


def teams_hall_of_fame(request):
    season_id = request.GET.get('season', None)
    seasons = Season.objects.filter(id=season_id) if season_id else Season.objects.filter(number__gt=5)

    tournament_type = request.GET.get('tournament', '')
    tournaments = League.objects.filter(type=tournament_type) if tournament_type else League.objects.all()

    service = HallOfFameService()
    teams = service.get_teams_tops(seasons, tournaments)

    return render(
        request,
        'tournament/hall_of_fame/partials/teams_hall_of_fame.html#teams-content',
        {
            'teams_tops': teams,
            'teams_filter': HallOfFameTeamFilter(request.GET, queryset=Team.objects.none()),
        },
    )


class TeamsRatingFilter(FilterSet):
    version = ModelChoiceFilter(
        queryset=TeamRatingVersion.objects.select_related('related_season').all(), label='Версия', empty_label=None
    )

    class Meta:
        model = TeamRating
        fields = ['version']


class TeamsRatingView(ListView):
    queryset = TeamRating.objects.select_related('team').all()
    template_name = 'tournament/teams_rating/teams_rating.html'

    def get(self, request, **kwargs):
        latest_rating_version = TeamRatingVersion.objects.order_by('-number').first()
        params = request.GET or {'version': latest_rating_version.number}
        filter = TeamsRatingFilter(params, queryset=self.queryset)
        selected_version = int(params['version'])
        source_season = (
            TeamRatingVersion.objects.select_related('related_season').get(number=selected_version).related_season
        )
        previous_seasons = Season.objects.filter(
            number__gt=5,
            number__lt=source_season.number,
            type=Season.Type.RUSSIAN_CHAMPIONSHIP,
        ).order_by('-number')[:5]
        earliest_season_taken_into_account = None
        if previous_seasons.count() > 0:
            earliest_season_taken_into_account = list(previous_seasons)[-1]

        seasons_weights = self.get_seasons_weights(source_season, earliest_season_taken_into_account)
        seasons = list(sorted(seasons_weights, key=lambda s: s.number))
        weighted_seasons_rating = self.get_weighted_seasons_rating(seasons, seasons_weights)
        selected_season_teams = [team for team in weighted_seasons_rating[source_season]]

        previous_rating_version = TeamRating.objects.select_related('team').filter(version__number=selected_version - 1)
        previous_rating = {item.team: item.rank for item in previous_rating_version.all()}

        context = {
            'seasons_rating': weighted_seasons_rating,
            'seasons_weights': seasons_weights,
            'previous_rating': previous_rating,
            'selected_season_teams': selected_season_teams,
            'filter': filter,
        }

        if request.htmx:
            return render(request, 'tournament/teams_rating/partials/rating_table.html', context)

        return render(request, self.template_name, context)

    @staticmethod
    def get_seasons_weights(source_season, earliest_season=None):
        weights = [1, 1, 1, 0.9, 0.8, 0.7]
        season_weights = {}
        earliest_season = earliest_season or source_season
        seasons = (
            Season.objects.select_related('bound_season')
            .filter(number__gte=earliest_season.number, number__lte=source_season.number)
            .order_by('-number')
        )
        season_count = 0
        for season in seasons:
            if season.is_primary:
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


class TeamsYearlyRatingView(ListView):
    template_name = 'tournament/teams_rating/yearly_rating_tab.html'

    def get(self, request, **kwargs):
        params = request.GET or {'year': timezone.now().year}
        form = TeamsYearlyRatingForm(params)
        form.full_clean()

        selected_year = form.cleaned_data['year']
        seasons = Season.objects.filter(number__gt=5).annotate(
            start_date=Subquery(
                TourNumber.objects.values('date_from')
                .filter(league__championship=OuterRef('id'))
                .order_by('date_from')[:1]
            )
        )
        seasons_in_year = (
            seasons.exclude(type=Season.Type.FINAL_TOURNAMENT).filter(start_date__year=selected_year).order_by('number')
        )

        teams_rating = {}
        seasons_rating = self.get_seasons_rating(seasons_in_year)
        for season in seasons_rating:
            for team in seasons_rating[season]:
                if team not in teams_rating:
                    teams_rating[team] = 0
                teams_rating[team] += seasons_rating[season][team]
        teams_rating = sorted(teams_rating.items(), key=lambda x: x[1], reverse=True)

        context = {
            'form': form,
            'selected_year': selected_year,
            'seasons_rating': seasons_rating,
            'seasons': seasons_rating.keys(),
            'teams_rating': teams_rating,
        }

        return render(request, self.template_name, context)

    @staticmethod
    def get_seasons_rating(seasons):
        result = {}
        seasons_rating = (
            SeasonTeamRating.objects.select_related('team', 'season')
            .filter(season__in=seasons)
            .order_by('season__number')
        )
        for rating_entry in seasons_rating:
            season = rating_entry.season
            team = rating_entry.team
            if season not in result:
                result[season] = {}
            if team not in result[season]:
                result[season][team] = round(rating_entry.total_points(), 2)

        return result


class TeamPlayersRatingView(View):
    class SeasonPhase(models.TextChoices):
        NOW = 'now'
        START = 'start'
        FIRST_HALF_END = 'first-half-end'
        SECOND_HALF_START = 'second-half-start'
        END = 'end'

    def get(self, request):
        season_id = request.GET.get('season')
        phase = request.GET.get('phase')
        league = request.GET.get('league')

        if season_id:
            season = get_object_or_404(Season, id=season_id)
        else:
            season = Season.objects.filter(number__gte=16).order_by('-number').first()
        if not phase:
            phase = self.SeasonPhase.NOW if season.is_active else self.SeasonPhase.START

        selected_phase_date = self.get_phase_date(season, phase)
        start_phase_date = self.get_phase_date(season, self.SeasonPhase.START)
        rating_version = PlayerRatingVersion.objects.filter(date__lte=start_phase_date).order_by('-number').first()
        if not rating_version:
            rating_version = PlayerRatingVersion.objects.order_by('-number').first()

        team_players_rating = []

        teams_in_season = Team.objects.filter(leagues__championship=season).distinct()
        if league and season.is_primary:
            teams_in_season = teams_in_season.filter(leagues__type=league, leagues__championship=season)

        for team in teams_in_season:
            team_players = (
                Player.objects.filter(
                    Exists(
                        PlayerTransfer.objects.filter(
                            trans_player=OuterRef('id'), season_join=season, is_technical=False, to_team=team
                        )
                    )
                )
                .annotate(
                    latest_transfer_team=Subquery(
                        PlayerTransfer.objects.filter(
                            trans_player=OuterRef('id'),
                            season_join=season,
                            date_join__lte=selected_phase_date,
                            is_technical=False,
                        )
                        .order_by('-date_join', '-id')
                        .values('to_team')[:1]
                    )
                )
                .filter(latest_transfer_team=team)
            )

            team_player_ratings = (
                PlayerRating.objects.filter(version=rating_version, player__in=team_players)
                .select_related('player__name__user_profile')
                .order_by('-rating_points')
            )

            all_player_ratings = {pr.player: pr for pr in team_player_ratings}
            for player in team_players:
                if player not in all_player_ratings:
                    all_player_ratings[player] = None

            all_ratings = [pr.rating_points for pr in team_player_ratings]
            top4_ratings = all_ratings[:4] if len(all_ratings) >= 4 else []
            top5_ratings = all_ratings[:5] if len(all_ratings) >= 5 else []

            all_avg = statistics.mean(all_ratings) if all_ratings else None
            top4_avg = statistics.mean(top4_ratings) if top4_ratings else None
            top5_avg = statistics.mean(top5_ratings) if top5_ratings else None

            team_players_rating.append(
                {
                    'team': team,
                    'top4_avg': top4_avg,
                    'top5_avg': top5_avg,
                    'all_avg': all_avg,
                    'players': all_player_ratings,
                }
            )

        team_players_rating.sort(
            key=lambda x: (x['top4_avg'] or 0, x['top5_avg'] or 0, x['all_avg'] or 0), reverse=True
        )

        context = {
            'season': season,
            'rating_version': rating_version,
            'team_players_rating': team_players_rating,
            'phase_date': selected_phase_date,
            'phase': phase,
        }

        return render(request, 'tournament/rating/partials/team_players_rating_table.html', context)

    def get_phase_date(self, season, phase):
        """Determine the date for the selected phase of the season."""
        if phase == self.SeasonPhase.NOW:
            return timezone.now().date()

        if phase == self.SeasonPhase.START:
            earliest_tour = TourNumber.objects.filter(league__championship=season).order_by('date_from').first()

            if earliest_tour:
                return earliest_tour.date_from

        if phase == self.SeasonPhase.END:
            latest_tour = TourNumber.objects.filter(league__championship=season).order_by('-date_to').first()

            if latest_tour:
                return latest_tour.date_to

        # These phases are only applicable for primary seasons (ЧР)
        if phase in [self.SeasonPhase.FIRST_HALF_END, self.SeasonPhase.SECOND_HALF_START] and season.is_primary:
            league = League.objects.filter(
                championship=season,
                type__in=[League.Type.PREMIER_LEAGUE, League.Type.FIRST_LEAGUE, League.Type.SECOND_LEAGUE],
            ).first()
            if not league:
                return timezone.now().date()

            tours = list(TourNumber.objects.filter(league=league).order_by('date_from'))

            if not tours:
                return timezone.now().date()

            total_tours = len(tours)
            half_point = total_tours // 2

            if phase == self.SeasonPhase.FIRST_HALF_END:
                first_half_tours = tours[:half_point]
                if first_half_tours:
                    return first_half_tours[-1].date_to
                return tours[0].date_to

            if phase == self.SeasonPhase.SECOND_HALF_START:
                second_half_tours = tours[half_point:]
                if second_half_tours:
                    return second_half_tours[0].date_from
                return tours[-1].date_from

        return timezone.now().date()


class PlayerRatingFilter(FilterSet):
    version = ModelChoiceFilter(
        queryset=PlayerRatingVersion.objects.all().order_by('-number'),
        label='Версия рейтинга',
        empty_label=None,
    )

    class Meta:
        model = PlayerRating
        fields = ['version']


class PlayersRatingView(ListView):
    queryset = PlayerRating.objects.select_related('player__name__user_profile', 'player__team', 'version').all()
    template_name = 'tournament/rating/players_rating.html'
    latest_rating_version = PlayerRatingVersion.objects.order_by('-number').first()

    def get(self, request, **kwargs):
        params = request.GET or {'version': self.latest_rating_version.number}
        filter = PlayerRatingFilter(params, queryset=self.queryset)
        selected_version = int(filter.data.get('version'))
        previous_ratings_qs = PlayerRating.objects.filter(version__number=selected_version - 1)
        previous_ratings = {r.player_id: {'points': r.rating_points, 'grade': r.grade} for r in previous_ratings_qs}

        seasons = Season.objects.filter(number__gte=16).order_by('-number')
        selected_season = seasons.first()
        active_season = Season.objects.filter(is_active=True).order_by('-number').first()

        rating_items = []
        for rating_entry in filter.qs:
            prev = previous_ratings.get(rating_entry.player_id)
            item = {'rating_entry': rating_entry, 'is_new': prev is None}
            if prev is not None:
                item['prev'] = {
                    'points': prev['points'],
                    'grade': prev['grade'],
                    'grade_changed': rating_entry.grade != prev['grade'],
                    'points_diff': rating_entry.rating_points - prev['points'],
                }
            else:
                item['prev'] = None
            rating_items.append(item)

        sort = request.GET.get('sort', 'rating__desc')
        sort_field, sort_order = sort.split('__')
        reverse = sort_order == 'desc'
        sort_order_sign = -1 if reverse else 1
        if sort_field == 'rating_diff':
            rating_items.sort(
                # always place players with no previous rating at the end
                key=lambda x: x['prev']['points_diff'] if x['prev'] is not None else (float('inf') * sort_order_sign),
                reverse=reverse,
            )
        elif sort_field == 'rating':
            rating_items.sort(key=lambda x: x['rating_entry'].rating_points, reverse=reverse)

        context = {
            'filter': filter,
            'previous_rating_exists': len(previous_ratings) > 0,
            'seasons': seasons,
            'selected_season': selected_season,
            'active_season': active_season,
            'seasons_data': [{'id': s.id, 'title': s.title, 'is_primary': s.is_primary} for s in seasons],
            'rating_items': rating_items,
            'sort': sort,
        }

        if request.htmx:
            return render(request, 'tournament/rating/partials/players_rating_table.html', context)

        return render(request, self.template_name, context)


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
            'clean_sheets', queryset=CleanSheet.objects.filter(author=player, match__is_played=True), to_attr='cs'
        ),
        Prefetch(
            'match_substitutions',
            queryset=Substitution.objects.filter(player_out=player, match__is_played=True),
            to_attr='subs_out',
        ),
        Prefetch(
            'match_substitutions',
            queryset=Substitution.objects.filter(player_in=player, match__is_played=True),
            to_attr='subs_in',
        ),
        Prefetch(
            'match_goal',
            queryset=Goal.objects.own_goals().filter(own_goal_author=player, match__is_played=True),
            to_attr='ogs',
        ),
        Prefetch(
            'cards',
            queryset=Card.objects.yellow().filter(author=player, match__is_played=True),
            to_attr='yellow_cards',
        ),
        Prefetch(
            'cards',
            queryset=Card.objects.red().filter(author=player, match__is_played=True),
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
        .distinct()
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
    all_clean_sheets = CleanSheet.objects.filter(author=player, match__is_played=True)
    all_subs_out = Substitution.objects.filter(player_out=player, match__is_played=True)
    all_subs_in = Substitution.objects.filter(player_in=player, match__is_played=True)
    all_ogs = Goal.objects.own_goals().filter(own_goal_author=player, match__is_played=True)
    all_yellow_cards = Card.objects.yellow().filter(author=player, match__is_played=True)
    all_red_cards = Card.objects.red().filter(author=player, match__is_played=True)

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

    overall_stats = {
        'matches': overall_matches,
        'goals': overall_goals,
        'assists': overall_assists,
        'goals_assists': overall_goals_assists,
        'clean_sheets': overall_clean_sheets,
        'subs_out': overall_subs_out,
        'subs_in': overall_subs_in,
        'ogs': overall_ogs,
        'yellow_cards': overall_yellow_cards,
        'red_cards': overall_red_cards,
    }

    overall_avg_goals = overall_goals / (overall_matches or 1)
    overall_avg_assists = overall_assists / (overall_matches or 1)
    overall_avg_goals_assists = overall_goals_assists / (overall_matches or 1)
    overall_avg_clean_sheets = overall_clean_sheets / (overall_matches or 1)
    overall_avg_yellow_cards = overall_yellow_cards / (overall_matches or 1)
    overall_avg_red_cards = overall_red_cards / (overall_matches or 1)
    overall_avg_own_goals = overall_ogs / (overall_matches or 1)
    overall_avg_subs_in = overall_subs_in / (overall_matches or 1)
    overall_avg_subs_out = overall_subs_out / (overall_matches or 1)

    overall_extra_stats = {
        'matches': overall_matches,
        'avg_goals': overall_avg_goals,
        'avg_assists': overall_avg_assists,
        'avg_goals_assists': overall_avg_goals_assists,
        'avg_clean_sheets': overall_avg_clean_sheets,
        'avg_subs_out': overall_avg_subs_out,
        'avg_subs_in': overall_avg_subs_in,
        'avg_own_goals': overall_avg_own_goals,
        'avg_yellow_cards': overall_avg_yellow_cards,
        'avg_red_cards': overall_avg_red_cards,
    }

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
        CleanSheet.objects.filter(author=player, match__league__championship=OuterRef('id'))
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

    ranks = get_player_ranks(player)

    context = {
        'user': user,
        'player': player,
        'stats': stats_by_season,
        'extra_stats': extra_stats_by_season,
        'overall_stats': overall_stats,
        'overall_extra_stats': overall_extra_stats,
        'other_stats': other_stats,
        'ranks': ranks,
    }

    return render(request, 'tournament/player/player_profile.html', context)


def get_player_ranks(player):
    matches_top = Player.objects.annotate(
        count=Count('played_matches'), rank=Window(expression=Rank(), order_by=('-count',))
    ).filter(count__gt=0)
    matches_rank = next(filter(lambda p: p.id == player.id, matches_top), None)
    matches_top_count = matches_top.count()

    goals_top = Player.objects.annotate(
        count=Count('goals'), rank=Window(expression=Rank(), order_by=('-count',))
    ).filter(count__gt=0)
    goals_rank = next(filter(lambda p: p.id == player.id, goals_top), None)
    goals_top_count = goals_top.count()

    assists_top = Player.objects.annotate(
        count=Count('assists'), rank=Window(expression=Rank(), order_by=('-count',))
    ).filter(count__gt=0)
    assists_rank = next(filter(lambda p: p.id == player.id, assists_top), None)
    assists_top_count = assists_top.count()

    cs_top = Player.objects.annotate(
        count=Count('clean_sheets'),
        rank=Window(expression=Rank(), order_by=('-count',)),
    ).filter(count__gt=0)
    cs_rank = next(filter(lambda p: p.id == player.id, cs_top), None)
    cs_top_count = cs_top.count()

    return {
        'matches': {'rank': matches_rank.rank if matches_rank else None, 'total': matches_top_count},
        'goals': {'rank': goals_rank.rank if goals_rank else None, 'total': goals_top_count},
        'assists': {'rank': assists_rank.rank if assists_rank else None, 'total': assists_top_count},
        'clean_sheets': {'rank': cs_rank.rank if cs_rank else None, 'total': cs_top_count},
    }


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
        Prefetch(
            'match_goal',
            queryset=Goal.objects.filter(team=team, assistent__isnull=False, match__is_played=True),
            to_attr='assists',
        ),
        Prefetch('clean_sheets', queryset=CleanSheet.objects.filter(team=team, match__is_played=True), to_attr='cs'),
        Prefetch(
            'match_substitutions',
            queryset=Substitution.objects.filter(team=team, match__is_played=True),
            to_attr='subs',
        ),
        Prefetch(
            'match_goal',
            queryset=Goal.objects.own_goals().filter(own_goal_team=team, match__is_played=True),
            to_attr='ogs',
        ),
        Prefetch(
            'cards',
            queryset=Card.objects.yellow().filter(team=team, match__is_played=True),
            to_attr='yellow_cards',
        ),
        Prefetch(
            'cards',
            queryset=Card.objects.red().filter(team=team, match__is_played=True),
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
        stats_by_league['goals'] += match.scored_by(team)
        stats_by_league['conceded_goals'] += match.conceded_by(team)
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
    all_clean_sheets = CleanSheet.objects.filter(team=team, match__is_played=True)
    all_subs = Substitution.objects.filter(team=team, match__is_played=True)
    all_ogs = Goal.objects.own_goals().filter(own_goal_team=team, match__is_played=True)
    all_yellow_cards = Card.objects.yellow().filter(team=team, match__is_played=True)
    all_red_cards = Card.objects.red().filter(team=team, match__is_played=True)

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

    most_biggest_cards_given = (
        (team.home_matches.all() | team.guest_matches.all())
        .annotate(cards_count=Count('cards'))
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

    greatest_goalscorer = (
        team.goals.regular().values('author').annotate(goals=Count('author')).order_by('-goals').first()
    )
    greatest_assistant = (
        team.goals.filter(assistent__isnull=False)
        .values('assistent')
        .annotate(assists=Count('assistent'))
        .order_by('-assists')
        .first()
    )
    greatest_goalkeeper = team.clean_sheets.all().values('author').annotate(cs=Count('author')).order_by('-cs').first()

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
        Match.objects.filter(
            Q(team_home_start=OuterRef('id')) | Q(team_guest_start=OuterRef('id')),
            match_substitutions__player_in=OuterRef('id'),
            is_played=True,
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

    return render(request, 'tournament/teams/partials/team_statistics.html', context)


def team_squad_statistics(request, pk):
    team = Team.objects.get(pk=pk)
    season_number = request.GET.get('season', None)
    tournament_id = request.GET.get('tournament', None)

    season = Season.objects.filter(number=season_number).first() if season_number else None
    tournaments = get_team_tournaments(team, season)
    selected_tournament = tournaments.filter(id=tournament_id).first() if tournament_id else None

    stats = get_team_squad_stats(team, season=season, tournament=selected_tournament)
    seasons = Season.objects.filter(tournaments_in_season__teams=team).distinct()
    context = {
        'team': team,
        'team_squad': stats,
        'seasons': seasons,
        'tournaments': tournaments,
        'selected_season': season,
        'selected_tournament': selected_tournament,
        'display_rating': False,
    }

    return render(request, 'tournament/teams/partials/team_squad_stats_panel.html', context)


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


class ComparePlayersView(View):
    def get_template_names(self) -> list[str]:
        if self.request.htmx:
            return ['tournament/compare_players.html#players-comparison']

        return ['tournament/compare_players.html']

    def get(self, request):
        form = ComparePlayersForm(request.GET)
        if not form.is_valid():
            player1 = form.cleaned_data.get('player1', None)
            player2 = form.cleaned_data.get('player2', None)
            return render(
                request,
                self.get_template_names(),
                {
                    'compare_form': form,
                    'player1': {'player': player1},
                    'player2': {'player': player2},
                },
            )

        player1 = form.cleaned_data['player1']
        player2 = form.cleaned_data['player2']
        season = form.cleaned_data['season']
        tournament = form.cleaned_data['tournament']
        matches_selection = form.cleaned_data['matches_selection']

        player1_matches, player2_matches = self.get_selected_matches(
            player1, player2, season, tournament, matches_selection
        )
        player1_stats = self.get_player_stats(player1, player1_matches)
        player2_stats = self.get_player_stats(player2, player2_matches)

        return render(
            request,
            self.get_template_names(),
            {
                'compare_form': form,
                'player1': {'player': player1, 'stats': player1_stats},
                'player2': {'player': player2, 'stats': player2_stats},
            },
        )

    def get_selected_matches(self, player1, player2, season, tournament, matches_selection):
        season_condition = Q(league__championship=season) if season else ~Q(league__championship__in=[])
        tournament_condition = Q(league__type=tournament) if tournament else Q()

        player1_matches = player1.played_matches.filter(
            season_condition, tournament_condition, match__is_played=True
        ).select_related('team', 'match')
        player2_matches = player2.played_matches.filter(
            season_condition, tournament_condition, match__is_played=True
        ).select_related('team', 'match')

        selected_matches = None
        if matches_selection == ComparePlayersForm.MatchesSelection.SAME_TEAM:
            player1_matches_in_team = set((x.match.id, x.team.id) for x in player1_matches)
            player2_matches_in_team = set((x.match.id, x.team.id) for x in player2_matches)
            selected_matches = [x[0] for x in player1_matches_in_team.intersection(player2_matches_in_team)]
        elif matches_selection == ComparePlayersForm.MatchesSelection.HEAD_TO_HEAD:
            selected_matches = [
                pm1.match.id
                for pm1 in player1_matches
                for pm2 in player2_matches
                if pm1.match == pm2.match and pm1.team != pm2.team
            ]

        if selected_matches is not None:
            return selected_matches, selected_matches

        return (
            player1_matches.values_list('match__id', flat=True),
            player2_matches.values_list('match__id', flat=True),
        )

    def get_player_stats(self, player: Player, selected_matches) -> dict:
        matches = player.played_matches.filter(match__in=selected_matches).count()
        wins = player.played_matches.filter(match__in=selected_matches, match__result__winner=F('team')).count()
        winrate = round(float(wins) / matches * 100, 1) if matches else 0
        goals = player.goals.filter(match__in=selected_matches).count()
        goals_per_match = round(float(goals) / matches, 2) if matches else 0
        assists = player.assists.filter(match__in=selected_matches).count()
        assists_per_match = round(float(assists) / matches, 2) if matches else 0
        goals_assists = goals + assists
        goals_assists_per_match = round(float(goals_assists) / matches, 2) if matches else 0
        cs = player.clean_sheets.filter(match__in=selected_matches).count()
        cs_per_match = round(float(cs) / matches, 2) if matches else 0

        return {
            'matches': matches,
            'wins': wins,
            'winrate': winrate,
            'goals': goals,
            'goals_per_match': goals_per_match,
            'assists': assists,
            'assists_per_match': assists_per_match,
            'goals_assists': goals_assists,
            'goals_assists_per_match': goals_assists_per_match,
            'cs': cs,
            'cs_per_match': cs_per_match,
            'yellow_cards': player.cards.yellow().filter(match__in=selected_matches).count(),
            'red_cards': player.cards.red().filter(match__in=selected_matches).count(),
        }


class CompareTeamsView(View):
    def get_template_names(self) -> list[str]:
        if self.request.htmx:
            return ['tournament/compare_teams.html#teams-comparison']

        return ['tournament/compare_teams.html']

    def get(self, request):
        form = CompareTeamsForm(request.GET)
        if not form.is_valid():
            team1 = form.cleaned_data.get('team1', None)
            team2 = form.cleaned_data.get('team2', None)
            return render(
                request,
                self.get_template_names(),
                {
                    'compare_form': form,
                    'team1': {'team': team1},
                    'team2': {'team': team2},
                },
            )

        team1 = form.cleaned_data['team1']
        team2 = form.cleaned_data['team2']
        season = form.cleaned_data['season']
        tournament = form.cleaned_data['tournament']
        matches_selection = form.cleaned_data['matches_selection']

        team1_matches, team2_matches = self.get_selected_matches(team1, team2, season, tournament, matches_selection)
        team1_stats = self.get_team_stats(team1, team1_matches)
        team2_stats = self.get_team_stats(team2, team2_matches)

        team1_player_stats = self.get_player_stats(team1, team1_matches)
        team2_player_stats = self.get_player_stats(team2, team2_matches)

        return render(
            request,
            self.get_template_names(),
            {
                'compare_form': form,
                'team1': {'team': team1, 'stats': team1_stats, 'player_stats': team1_player_stats},
                'team2': {'team': team2, 'stats': team2_stats, 'player_stats': team2_player_stats},
            },
        )

    def get_selected_matches(self, team1, team2, season, tournament, matches_selection):
        season_condition = Q(league__championship=season) if season else ~Q(league__championship__in=[])
        tournament_condition = Q(league__type=tournament) if tournament else Q()

        team1_matches = Match.objects.filter(
            season_condition, tournament_condition, Q(team_home=team1) | Q(team_guest=team1), is_played=True
        ).distinct()
        team2_matches = Match.objects.filter(
            season_condition, tournament_condition, Q(team_home=team2) | Q(team_guest=team2), is_played=True
        ).distinct()

        selected_matches = None
        if matches_selection == ComparePlayersForm.MatchesSelection.HEAD_TO_HEAD:
            team1_matches_set = set(x.id for x in team1_matches)
            team2_matches_set = set(x.id for x in team2_matches)
            selected_matches = team1_matches_set.intersection(team2_matches_set)

        if selected_matches is not None:
            return selected_matches, selected_matches

        return (team1_matches.values_list('id', flat=True), team2_matches.values_list('id', flat=True))

    def get_team_stats(self, team: Team, selected_matches) -> dict:
        matches = len(selected_matches)
        wins = team.won_matches.filter(match__in=selected_matches).count()
        winrate = round(float(wins) / matches * 100, 1) if matches else 0
        goals = team.goals.filter(match__in=selected_matches).count()
        goals_per_match = round(float(goals) / matches, 2) if matches else 0
        conceded_goals = Goal.objects.filter(
            Q(match__team_home=team) | Q(match__team_guest=team), ~Q(team=team), match__in=selected_matches
        ).count()
        conceded_goals_per_match = round(float(conceded_goals) / matches, 2) if matches else 0
        assists = team.goals.filter(assistent__isnull=False, match__in=selected_matches).count()
        assists_per_match = round(float(assists) / matches, 2) if matches else 0
        cs = team.clean_sheets.filter(match__in=selected_matches).count()
        cs_per_match = round(float(cs) / matches, 2) if matches else 0

        return {
            'matches': matches,
            'wins': wins,
            'winrate': winrate,
            'goals': goals,
            'goals_per_match': goals_per_match,
            'assists': assists,
            'assists_per_match': assists_per_match,
            'conceded_goals': conceded_goals,
            'conceded_goals_per_match': conceded_goals_per_match,
            'cs': cs,
            'cs_per_match': cs_per_match,
            'yellow_cards': team.cards.yellow().filter(match__in=selected_matches).count(),
            'red_cards': team.cards.red().filter(match__in=selected_matches).count(),
        }

    def get_player_stats(self, team: Team, selected_matches) -> dict:
        top_matches = (
            team.played_matches.filter(match__in=selected_matches)
            .values(pl=F('player__nickname'))
            .annotate(count=Count('player'))
            .order_by('-count')
            .first()
        )
        top_wins = (
            team.played_matches.filter(match__in=selected_matches, match__result__winner=team)
            .values(pl=F('player__nickname'))
            .annotate(count=Count('player'))
            .order_by('-count')
            .first()
        )
        top_goals = (
            team.goals.regular()
            .filter(match__in=selected_matches)
            .values(pl=F('author__nickname'))
            .annotate(count=Count('author'))
            .order_by('-count')
            .first()
        )
        top_assists = (
            team.goals.filter(match__in=selected_matches, assistent__isnull=False)
            .values(pl=F('assistent__nickname'))
            .annotate(count=Count('assistent'))
            .order_by('-count')
            .first()
        )
        top_goals_assists = (
            Player.objects.annotate(
                goals_count=Coalesce(self.get_player_goals_subquery(selected_matches, team), 0),
                assists_count=Coalesce(self.get_player_assists_subquery(selected_matches, team), 0),
                count=F('goals_count') + F('assists_count'),
                pl=F('nickname'),
            )
            .filter(count__gt=0)
            .order_by('-count')
            .first()
        )
        top_cs = (
            team.clean_sheets.all()
            .filter(match__in=selected_matches)
            .values(pl=F('author__nickname'))
            .annotate(count=Count('author'))
            .order_by('-count')
            .first()
        )

        return {
            'matches': top_matches or {'pl': '–', 'count': 0},
            'wins': top_wins or {'pl': '–', 'count': 0},
            'goals': top_goals or {'pl': '–', 'count': 0},
            'assists': top_assists or {'pl': '–', 'count': 0},
            'goals_assists': top_goals_assists or {'pl': '–', 'count': 0},
            'cs': top_cs or {'pl': '–', 'count': 0},
        }

    @staticmethod
    def get_player_goals_subquery(selected_matches, team):
        return Subquery(
            Goal.objects.filter(
                author=OuterRef('id'),
                match__in=selected_matches,
                team=team,
            )
            .order_by()
            .values('author')
            .annotate(c=Count('id', distinct=True))
            .values('c')
        )

    @staticmethod
    def get_player_assists_subquery(selected_matches, team):
        return Subquery(
            Goal.objects.filter(
                assistent=OuterRef('id'),
                match__in=selected_matches,
                team=team,
            )
            .order_by()
            .values('assistent')
            .annotate(c=Count('id', distinct=True))
            .values('c')
        )


def awards_main(request, slug):
    """Main awards page with tabs for a specific league"""
    league = get_object_or_404(League, slug=slug)
    campaign = get_object_or_404(AwardCampaign, season=league.championship)

    awards = (
        Award.objects.filter(league=league)
        .select_related('nomination', 'league', 'campaign')
        .prefetch_related('nominees__player', 'nominees__team')
        .order_by('nomination__order')
    )

    voting_tab_html = voting_tab(request, league=league, awards=awards, initial_context=True)

    context = {
        'league': league,
        'campaign': campaign,
        'awards': awards,
        'voting_tab_html': voting_tab_html,
        'now': timezone.now(),
    }

    if request.htmx:
        return render(request, 'tournament/awards/main.html#awards-tabs', context)

    return render(request, 'tournament/awards/main.html', context)


def voting_tab(request, slug=None, league=None, awards=None, initial_context=False):
    """Tab for voting interface - display mode"""
    if not league:
        league_slug = slug or request.GET.get('league_slug') or request.resolver_match.kwargs.get('slug')
        league = get_object_or_404(League, slug=league_slug)

    campaign = get_object_or_404(AwardCampaign, season=league.championship)

    if not awards:
        awards = (
            Award.objects.filter(league=league)
            .select_related('nomination', 'campaign')
            .prefetch_related('nominees__player', 'nominees__team')
            .order_by('nomination__order')
        )

    user_player = getattr(request.user, 'user_player', None)
    user_team = user_player.team if user_player else None

    submission = None
    votes_by_award = {}
    if user_player and awards:
        voter_record = AwardVoter.objects.filter(campaign=campaign, league=league, voter=user_player).first()
        if voter_record:
            submission = AwardSubmission.objects.filter(voter_record=voter_record).first()
            if submission:
                votes = submission.votes.select_related(
                    'submission',
                    'award__nomination',
                    'nominee__player__name__user_profile',
                    'nominee__team',
                ).order_by('award__nomination__order', 'place')
                for vote in votes:
                    if vote.award.id not in votes_by_award:
                        votes_by_award[vote.award.id] = {}
                    votes_by_award[vote.award.id][vote.place] = vote

    is_eligible_to_vote = AwardVoter.objects.filter(campaign=campaign, league=league, voter=user_player).exists()

    allow_editing = settings.ALLOW_AWARDS_VOTE_EDITING

    context = {
        'campaign': campaign,
        'league': league,
        'awards': awards,
        'user_player': user_player,
        'user_team': user_team,
        'submission': submission,
        'votes_by_award': votes_by_award,
        'is_eligible_to_vote': is_eligible_to_vote,
        'allow_editing': allow_editing,
    }

    if initial_context:
        return render_to_string('tournament/awards/tabs/voting_tab.html', context, request=request)

    return render(request, 'tournament/awards/tabs/voting_tab.html', context)


def results_tab(request, slug):
    """Tab for viewing award results"""
    league = get_object_or_404(League, slug=slug)
    campaign = get_object_or_404(AwardCampaign, season=league.championship)
    awards = (
        Award.objects.filter(league=league)
        .select_related('nomination', 'campaign')
        .prefetch_related('results__nominee__player', 'nominees__player')
        .order_by('nomination__order')
    )

    results_by_award = {}

    for award in awards:
        results = (
            AwardResult.objects.filter(award=award)
            .select_related('nominee__player__name__user_profile', 'nominee__team')
            .order_by('final_rank')
        )

        votes = (
            AwardVote.objects.filter(award=award)
            .select_related(
                'submission__voter_record',
                'submission__voter_record__team',
                'submission__voter_record__voter',
                'nominee__player',
                'nominee__team',
            )
            .order_by('submission__voter_record__team__title', 'place')
        )
        votes_by_submission = {}
        for vote in votes:
            submission_id = vote.submission.id
            if submission_id not in votes_by_submission:
                votes_by_submission[submission_id] = {
                    'submission': vote.submission,
                    'team': vote.submission.voter_record.team,
                    'voter': vote.submission.voter_record.voter,
                    'votes': [],
                }
            votes_by_submission[submission_id]['votes'].append(vote)

        for submission_data in votes_by_submission.values():
            votes_by_place = {1: None, 2: None, 3: None}
            for vote in submission_data['votes']:
                votes_by_place[vote.place] = vote
            submission_data['votes_by_place'] = votes_by_place

        all_voters = (
            AwardVoter.objects.filter(campaign=campaign, league=league)
            .select_related('team', 'voter')
            .order_by('team__title', 'voter__nickname')
        )
        voters_with_votes = {vote.submission.voter_record.voter_id for vote in votes}
        non_voting_voters = [
            {
                'team': voter.team,
                'voter': voter.voter,
            }
            for voter in all_voters
            if voter.voter_id not in voters_with_votes
        ]

        results_by_award[award.id] = {
            'award': award,
            'results': results,
            'votes_by_submission': votes_by_submission,
            'non_voting_voters': non_voting_voters,
        }

    context = {
        'league': league,
        'awards': awards,
        'results_by_award': results_by_award,
        'campaign': campaign,
    }

    return render(request, 'tournament/awards/tabs/results_tab.html', context)


def status_tab(request, slug):
    """Tab for viewing voting status"""
    league = get_object_or_404(League, slug=slug)
    campaign = get_object_or_404(AwardCampaign, season=league.championship)
    awards = Award.objects.filter(league=league).select_related('nomination', 'campaign').order_by('nomination__order')

    submissions_by_voter = {}
    votes_by_submission = {}
    if awards.exists():
        voters = (
            AwardVoter.objects.filter(campaign=campaign, league=league)
            .select_related('team', 'voter')
            .order_by('team__title', 'voter__nickname')
        )
        submissions = AwardSubmission.objects.filter(campaign=campaign, league=league).select_related(
            'voter_record', 'voter_record__voter', 'voter_record__team'
        )
        submissions_by_voter = {submission.voter_record.voter_id: submission for submission in submissions}

        if submissions.exists():
            votes = (
                AwardVote.objects.filter(submission__in=submissions)
                .select_related(
                    'submission',
                    'award__nomination',
                    'nominee__player__name__user_profile',
                    'nominee__team',
                )
                .order_by('award__nomination__order', 'place')
            )
            for vote in votes:
                submission_id = vote.submission.id
                if submission_id not in votes_by_submission:
                    votes_by_submission[submission_id] = {}
                award_id = vote.award.id
                if award_id not in votes_by_submission[submission_id]:
                    votes_by_submission[submission_id][award_id] = {}
                votes_by_submission[submission_id][award_id][vote.place] = vote
    else:
        voters = AwardVoter.objects.none()

    context = {
        'league': league,
        'campaign': campaign,
        'awards': awards,
        'voters': voters,
        'submissions_by_voter': submissions_by_voter,
        'votes_by_submission': votes_by_submission,
    }

    return render(request, 'tournament/awards/tabs/status_tab.html', context)


def award_voting_edit(request, slug):
    """View for editing votes - shows the form"""

    league = get_object_or_404(League, slug=slug)
    campaign = get_object_or_404(AwardCampaign, season=league.championship)

    awards = (
        Award.objects.filter(league=league)
        .select_related('nomination', 'campaign')
        .prefetch_related('nominees__player', 'nominees__team')
        .order_by('nomination__order')
    )

    if not awards.exists():
        messages.error(request, 'Для этого турнира пока нет наград')
        return voting_tab(request, league=league)

    user_player = request.user.user_player
    voter_record = AwardVoter.objects.filter(campaign=campaign, league=league, voter=user_player).first()
    if not voter_record:
        messages.error(request, 'Вы не являетесь назначенным голосующим для этого турнира')
        return voting_tab(request, league=league, awards=awards)

    user_team = voter_record.team

    existing_votes = {}
    submission = AwardSubmission.objects.filter(voter_record=voter_record).first()

    allow_editing = settings.ALLOW_AWARDS_VOTE_EDITING
    if submission and not allow_editing:
        messages.error(request, 'Редактирование голосов после подачи запрещено')
        return voting_tab(request, league=league, awards=awards)

    if submission:
        votes = AwardVote.objects.filter(submission=submission).select_related('nominee', 'award__nomination')
        for vote in votes:
            key = f'{vote.award.nomination.code}_place_{vote.place}'
            existing_votes[key] = vote.nominee.id

    form = AwardVotingForm(awards=awards, user_team=user_team, user_player=user_player, initial=existing_votes)

    context = {
        'league': league,
        'awards': awards,
        'form': form,
        'user_player': user_player,
        'user_team': user_team,
        'allow_editing': allow_editing,
    }

    return render(request, 'tournament/awards/tabs/voting_edit.html', context)


class AwardVotingView(View):
    """View for voting in season awards - handles HTMX form submission"""

    def post(self, request, slug):
        league = get_object_or_404(League, slug=slug)
        campaign = get_object_or_404(AwardCampaign, season=league.championship)

        all_awards = (
            Award.objects.filter(league=league)
            .select_related('nomination', 'campaign')
            .prefetch_related('nominees__player', 'nominees__team')
            .order_by('nomination__order')
        )

        if not all_awards.exists():
            messages.error(request, 'Для этого турнира пока нет наград')
            return voting_tab(request, league=league)

        user_player = request.user.user_player
        voter_record = AwardVoter.objects.filter(campaign=campaign, league=league, voter=user_player).first()
        if not voter_record:
            messages.error(request, 'Вы не являетесь назначенным голосующим для этого турнира')
            return voting_tab(request, league=league, awards=all_awards)

        submission = AwardSubmission.objects.filter(voter_record=voter_record).first()

        allow_editing = settings.ALLOW_AWARDS_VOTE_EDITING
        if submission and not allow_editing:
            messages.error(request, 'Редактирование голосов после подачи запрещено')
            return voting_tab(request, league=league)

        user_team = voter_record.team

        form = AwardVotingForm(request.POST, awards=all_awards, user_team=user_team, user_player=user_player)

        if form.is_valid():
            form.save()
            messages.success(request, 'Ваши голоса успешно отправлены!')
            response = voting_tab(request, league=league, awards=all_awards)
            response = trigger_client_event(response, 'awardVotingSubmitted')
            return response

        context = {
            'league': league,
            'awards': all_awards,
            'form': form,
            'user_player': user_player,
            'user_team': user_team,
        }
        return render(request, 'tournament/awards/tabs/voting_edit.html', context)


class ArchiveView(TemplateView):
    template_name = 'tournament/archive/archive.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tournaments = League.objects.order_by('priority', 'title').prefetch_related(
            Prefetch(
                'winners',
                queryset=TournamentWinner.objects.select_related('winner'),
                to_attr='archive_winners',
            )
        )
        seasons = (
            Season.objects.filter(tournaments_in_season__isnull=False)
            .annotate(
                has_completed_tournaments=Exists(TournamentWinner.objects.filter(league__championship=OuterRef('pk')))
            )
            .filter(has_completed_tournaments=True)
            .annotate(
                start_date=Min('tournaments_in_season__tours__date_from'),
                end_date=Max('tournaments_in_season__tours__date_to'),
            )
            .distinct()
            .prefetch_related(Prefetch('tournaments_in_season', queryset=tournaments, to_attr='archive_tournaments'))
            .order_by('-number')
        )

        for season in seasons:
            for tournament in season.archive_tournaments:
                tournament.winner = tournament.archive_winners[0].winner if tournament.archive_winners else None

        old_seasons = [
            {
                'season_title': 'ЧР, 4 сезон',
                'short_title': 'ЧР #4',
                'type': Season.Type.RUSSIAN_CHAMPIONSHIP,
                'post_link': reverse('core:post_detail', args=(49, 'season_4')),
            },
            {
                'season_title': 'ЛЧ, 1 сезон',
                'short_title': 'ЛЧ #1',
                'type': Season.Type.CHAMPIONS_LEAGUE,
                'post_link': reverse('core:post_detail', args=(50, 'champions_league_1')),
            },
            {
                'season_title': 'ЧР, 3 сезон',
                'short_title': 'ЧР #3',
                'type': Season.Type.RUSSIAN_CHAMPIONSHIP,
                'post_link': reverse('core:post_detail', args=(48, 'season_3')),
            },
            {
                'season_title': 'ЧР, 2 сезон',
                'short_title': 'ЧР #2',
                'type': Season.Type.RUSSIAN_CHAMPIONSHIP,
                'post_link': reverse('core:post_detail', args=(47, 'season_2')),
            },
            {
                'season_title': 'ЧР, 1 сезон',
                'short_title': 'ЧР #1',
                'type': Season.Type.RUSSIAN_CHAMPIONSHIP,
                'post_link': reverse('core:post_detail', args=(46, 'season_1')),
            },
        ]

        context['seasons'] = seasons
        context['old_seasons'] = old_seasons
        return context
