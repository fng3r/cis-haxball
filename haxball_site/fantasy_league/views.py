from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string

from django_htmx.http import trigger_client_event

from tournament.models import Player, TourNumber

from .forms import SquadSubmissionForm, TourFilterForm, TournamentFilterForm, UserFilterForm
from .models import FantasyTournament, SquadPlayer, SquadSubmission
from .points_service import calculate_submission_total_points, calculate_user_total_points
from .utils import (
    get_blocking_tours,
    get_league_budget_limit,
    get_player_fantasy_stats,
    get_players_with_changed_positions,
    get_tournament_standings,
    get_unavailable_players_in_submission,
    is_tour_open_for_fantasy,
    preload_fantasy_data,
)


def get_default_tournament():
    return (
        FantasyTournament.objects.filter(is_active=True)
        .select_related('league', 'league__championship')
        .order_by('league__priority')
        .first()
    )


def resolve_selected_tournament(request, selected_tournament=None):
    """Resolve selected tournament from GET or provided value and return (tournament, TournamentFilterForm).

    Ensures the tournament is enriched with league and prefetches tours for later use.
    """
    default_tournament = get_default_tournament()
    if not selected_tournament:
        if request.GET.get('tournament'):
            selected_tournament = FantasyTournament.objects.filter(pk=request.GET.get('tournament')).first()
        elif default_tournament:
            selected_tournament = default_tournament

    if selected_tournament:
        selected_tournament = (
            FantasyTournament.objects.filter(pk=selected_tournament.pk)
            .select_related('league')
            .prefetch_related('league__tours')
            .first()
        )

    tournament_form = TournamentFilterForm(
        initial={'tournament': selected_tournament.pk if selected_tournament else None}
    )

    return selected_tournament, tournament_form


def get_users_with_submissions(tournament=None):
    """Get users who have made at least one squad submission"""
    if tournament:
        return (
            User.objects.filter(fantasy_squad_submissions__tournament=tournament)
            .select_related('user_profile')
            .distinct()
        )
    return User.objects.filter(fantasy_squad_submissions__isnull=False).select_related('user_profile').distinct()


def fantasy_main(request):
    """Main fantasy league page with four tabs"""
    selected_tournament = None
    selected_user = None
    selected_tournament, tournament_form = resolve_selected_tournament(request)
    user_form = UserFilterForm(initial={'user': selected_user.pk if selected_user else None})

    active_tournaments = FantasyTournament.objects.filter(is_active=True)

    make_squad_tab_html = make_squad_tab(request, initial_context=True, selected_tournament=selected_tournament)

    context = {
        'tournament_form': tournament_form,
        'user_form': user_form,
        'selected_tournament': selected_tournament,
        'active_tournaments': active_tournaments,
        'make_squad_tab_html': make_squad_tab_html,
    }
    if request.htmx:
        return render(request, 'fantasy_league/main.html#tabs', context)
    return render(request, 'fantasy_league/main.html', context)


def make_squad_tab(request, initial_context=False, selected_tournament=None):
    """Tab for making squad submissions"""
    if not request.user.is_authenticated:
        return render_to_string('fantasy_league/make_squad_tab.html', {'user': request.user}, request=request)

    selected_tournament, tournament_form = resolve_selected_tournament(request, selected_tournament)

    user_squads = {}
    is_tournament_ended = False
    if selected_tournament:
        preloaded_data = preload_fantasy_data(selected_tournament)

        tours = list(TourNumber.objects.filter(league=selected_tournament.league).order_by('number'))

        submissions = (
            SquadSubmission.objects.filter(user=request.user, tournament=selected_tournament)
            .prefetch_related('squad_players__player', 'tour')
            .select_related('tour')
        )

        submissions_lookup = {sub.tour_id: sub for sub in submissions}

        for tour in tours:
            submission = submissions_lookup.get(tour.id)

            blocking_tours = get_blocking_tours(request.user, tour, selected_tournament)
            can_submit = len(blocking_tours) == 0

            if submission:
                primary_players = list(submission.main_squad.all())
                secondary_players = list(submission.bench_players.all())
                unavailable_players = (
                    get_unavailable_players_in_submission(submission) if is_tour_open_for_fantasy(tour) else []
                )
                user_squads[tour.id] = {
                    'submission': submission,
                    'primary_players': primary_players,
                    'secondary_players': secondary_players,
                    'can_submit': can_submit,
                    'blocking_tours': blocking_tours,
                    'unavailable_players': unavailable_players,
                }
            else:
                user_squads[tour.id] = {
                    'submission': None,
                    'primary_players': [],
                    'secondary_players': [],
                    'can_submit': can_submit,
                    'blocking_tours': blocking_tours,
                    'unavailable_players': [],
                }

        is_tournament_ended = all(tour.is_ended for tour in tours)

    context = {
        'tournament_form': tournament_form,
        'selected_tournament': selected_tournament,
        'is_tournament_ended': is_tournament_ended,
        'user_squads': user_squads,
        'user': request.user,
        'preloaded_data': preloaded_data if selected_tournament else None,
    }
    if initial_context:
        return render_to_string('fantasy_league/make_squad_tab.html', context, request=request)
    return render(request, 'fantasy_league/make_squad_tab.html', context)


def view_squads_tab(request):
    """Tab for viewing other users' squad submissions"""
    selected_tournament, tournament_form = resolve_selected_tournament(request)
    users_with_submissions = get_users_with_submissions(selected_tournament)

    user_id = request.GET.get('user')
    selected_user = None
    if user_id:
        selected_user = User.objects.filter(pk=user_id).select_related('user_profile').first()
    elif users_with_submissions:
        selected_user = users_with_submissions.first()

    if not users_with_submissions:
        return render(
            request,
            'fantasy_league/view_squads_tab.html',
            {
                'tournament_form': tournament_form,
                'user_form': UserFilterForm(),
                'selected_tournament': selected_tournament,
                'selected_user': selected_user,
                'squads_data': {},
                'preloaded_data': None,
            },
        )

    user_form = UserFilterForm(initial={'user': selected_user.pk if selected_user else None})

    if users_with_submissions:
        user_form.fields['user'].queryset = users_with_submissions

    squads_data = {}
    if selected_tournament and selected_user:
        preloaded_data = preload_fantasy_data(selected_tournament)

        tours = TourNumber.objects.filter(league=selected_tournament.league).order_by('number')

        submissions = (
            SquadSubmission.objects.filter(user=selected_user, tournament=selected_tournament)
            .prefetch_related('squad_players__player', 'tour')
            .select_related('tour')
        )

        submissions_lookup = {sub.tour_id: sub for sub in submissions}
        for tour in tours:
            submission = submissions_lookup.get(tour.id)
            squads_data[tour.id] = submission

    context = {
        'tournament_form': tournament_form,
        'user_form': user_form,
        'selected_tournament': selected_tournament,
        'selected_user': selected_user,
        'squads_data': squads_data,
        'preloaded_data': preloaded_data if selected_tournament and selected_user else None,
    }

    return render(request, 'fantasy_league/view_squads_tab.html', context)


def top_squads_tab(request):
    """Tab for viewing top-3 squad submissions per tour"""
    selected_tournament, tournament_form = resolve_selected_tournament(request)

    tour = None
    tour_form = None
    if selected_tournament:
        tour_qs = TourNumber.objects.filter(league=selected_tournament.league).order_by('number')
        initial_tour = None
        if request.GET.get('tour'):
            initial_tour = tour_qs.filter(pk=request.GET.get('tour')).first()
        if not initial_tour and tour_qs.exists():
            initial_tour = tour_qs.first()
        tour = initial_tour
        tour_form = TourFilterForm(
            initial={'tour': initial_tour.pk if initial_tour else None},
            league=selected_tournament.league,
        )

    top_submissions = []
    preloaded_data = None
    if selected_tournament and tour:
        preloaded_data = preload_fantasy_data(selected_tournament)

        if is_tour_open_for_fantasy(tour):
            top_submissions = []
        else:
            submissions = (
                SquadSubmission.objects.filter(tournament=selected_tournament, tour=tour)
                .prefetch_related('squad_players__player')
                .select_related('tour', 'user', 'user__user_profile')
            )
            top_submissions = sorted(
                submissions,
                key=lambda s: calculate_submission_total_points(s, preloaded_data),
                reverse=True,
            )[:3]

    context = {
        'tournament_form': tournament_form,
        'selected_tournament': selected_tournament,
        'selected_tour': tour,
        'tour_form': tour_form,
        'top_submissions': top_submissions,
        'preloaded_data': preloaded_data if selected_tournament else None,
    }

    return render(request, 'fantasy_league/top_squads_tab.html', context)


def standings_tab(request):
    """Tab for tournament standings"""
    selected_tournament, tournament_form = resolve_selected_tournament(request)

    standings = []
    tour_points = {}
    penalty_points = {}

    if selected_tournament:
        standings = get_tournament_standings(selected_tournament)

        tours = TourNumber.objects.filter(league=selected_tournament.league).order_by('number')

        preloaded_data = preload_fantasy_data(selected_tournament)
        all_submissions = (
            SquadSubmission.objects.filter(tournament=selected_tournament)
            .prefetch_related('squad_players__player')
            .select_related('user', 'tour')
        )

        submissions_lookup = {}
        for submission in all_submissions:
            key = (submission.user_id, submission.tour_id)
            submissions_lookup[key] = submission

        for standing in standings:
            user = standing['user']
            tour_points[user.id] = {}

            user_points = calculate_user_total_points(user, selected_tournament, preloaded_data)
            penalty_points[user.id] = user_points['penalty_points']

            for tour in tours:
                submission = submissions_lookup.get((user.id, tour.id))
                if submission:
                    tour_points[user.id][tour.id] = calculate_submission_total_points(submission, preloaded_data)
                else:
                    tour_points[user.id][tour.id] = None

    context = {
        'tournament_form': tournament_form,
        'selected_tournament': selected_tournament,
        'standings': standings,
        'tour_points': tour_points,
        'penalty_points': penalty_points,
    }

    return render(request, 'fantasy_league/standings_tab.html', context)


def statistics_tab(request):
    """Tab for player statistics"""
    selected_tournament, tournament_form = resolve_selected_tournament(request)

    player_stats = []
    if selected_tournament:
        player_stats = get_player_fantasy_stats(selected_tournament)

    context = {
        'tournament_form': tournament_form,
        'selected_tournament': selected_tournament,
        'player_stats': player_stats,
    }

    return render(request, 'fantasy_league/statistics_tab.html', context)


def tour_detail(request, tour_id):
    """Return tour content for HTMX requests"""
    tour = get_object_or_404(TourNumber, pk=tour_id)
    tournament = FantasyTournament.objects.filter(league=tour.league, is_active=True).first()

    if not tournament:
        return render(request, 'fantasy_league/partials/tour_closed.html', {'tour': tour})

    preloaded_data = preload_fantasy_data(tournament)

    submission = (
        SquadSubmission.objects.filter(user=request.user, tournament=tournament, tour=tour)
        .prefetch_related('squad_players__player')
        .first()
    )

    blocking_tours = get_blocking_tours(request.user, tour, tournament)
    can_submit = len(blocking_tours) == 0
    unavailable_players = get_unavailable_players_in_submission(submission) if submission else []

    context = {
        'tour': tour,
        'tournament': tournament,
        'submission': submission,
        'is_open': is_tour_open_for_fantasy(tour),
        'preloaded_data': preloaded_data,
        'can_submit': can_submit,
        'blocking_tours': blocking_tours,
        'unavailable_players': unavailable_players,
    }

    return render(request, 'fantasy_league/partials/tour_card.html', context)


@login_required
def edit_squad(request, tour_id):
    """Edit squad for a specific tour"""
    tour = get_object_or_404(TourNumber, pk=tour_id)

    if not is_tour_open_for_fantasy(tour):
        messages.error(request, 'Тур уже закрыт для отправки составов')
        return redirect('fantasy_league:main')

    prev_submission = (
        SquadSubmission.objects.filter(user=request.user, tournament__league=tour.league, tour__number__lt=tour.number)
        .order_by('-tour__number')
        .prefetch_related('squad_players__player')
    ).first()
    prev_player_ids = []
    players_with_changed_positions = {}
    if prev_submission:
        prev_player_ids = [sp.player_id for sp in prev_submission.main_squad.all()] + [
            sp.player_id for sp in prev_submission.bench_players.all()
        ]
        players_with_changed_positions = get_players_with_changed_positions(prev_submission)

    submission = SquadSubmission.objects.filter(
        user=request.user,
        tour=tour,
        tournament__league=tour.league,
    ).first()

    budget_limit = get_league_budget_limit(tour.league)
    unavailable_players = get_unavailable_players_in_submission(submission) if submission else []

    if request.method == 'POST':
        form = SquadSubmissionForm(request.POST, tournament=tour.league, previous_player_ids=prev_player_ids)
        if form.is_valid():
            with transaction.atomic():
                if not submission:
                    submission, _ = SquadSubmission.objects.get_or_create(
                        user=request.user,
                        tour=tour,
                        tournament__league=tour.league,
                        defaults={'tournament': tour.league.fantasy_tournament},
                    )
                submission.squad_players.all().delete()

                main_squad_data = [
                    (form.cleaned_data['main_squad_gk'], SquadPlayer.Position.GK),
                    (form.cleaned_data['main_squad_dm'], SquadPlayer.Position.DM),
                    (form.cleaned_data['main_squad_st1'], SquadPlayer.Position.ST),
                    (form.cleaned_data['main_squad_st2'], SquadPlayer.Position.ST),
                ]

                for player, position in main_squad_data:
                    SquadPlayer.objects.create(
                        submission=submission,
                        player=player,
                        team=player.team,
                        position=position,
                        squad_type=SquadPlayer.SquadType.MAIN,
                    )

                bench_players_data = [
                    (form.cleaned_data.get('bench_gk'), SquadPlayer.Position.GK),
                    (form.cleaned_data.get('bench_dm'), SquadPlayer.Position.DM),
                    (form.cleaned_data.get('bench_st'), SquadPlayer.Position.ST),
                ]

                for player, position in bench_players_data:
                    if player:
                        SquadPlayer.objects.create(
                            submission=submission,
                            player=player,
                            team=player.team,
                            position=position,
                            squad_type=SquadPlayer.SquadType.BENCH,
                        )

                captain_player_id = form.cleaned_data.get('captain_player_id')
                if captain_player_id:
                    submission.captain_player = Player.objects.filter(pk=captain_player_id).first()

                selected_ids = {p.id for p in form.get_main_squad_players() + form.get_bench_players() if p}
                prev_ids = set(prev_player_ids)
                transfers_in = len(selected_ids - prev_ids) if prev_ids else 0
                penalized_transfers = max(0, transfers_in - 2)
                submission.penalized_transfers = penalized_transfers

                submission.save()

                fantasy_tournament = tour.league.fantasy_tournament
                blocking_tours = get_blocking_tours(request.user, tour, fantasy_tournament)
                can_submit = len(blocking_tours) == 0

                response = render(
                    request,
                    'fantasy_league/partials/tour_card.html',
                    {
                        'tour': tour,
                        'tournament': fantasy_tournament,
                        'submission': submission,
                        'is_open': is_tour_open_for_fantasy(tour),
                        'preloaded_data': preload_fantasy_data(submission.tournament),
                        'can_submit': can_submit,
                        'blocking_tours': blocking_tours,
                    },
                )
                response = trigger_client_event(response, 'tour-submitted', {'tour_number': tour.number})
                return response
        else:
            player_fields = [
                'main_squad_gk',
                'main_squad_dm',
                'main_squad_st1',
                'main_squad_st2',
                'bench_gk',
                'bench_dm',
                'bench_st',
            ]

            for field_name in player_fields:
                player_id = request.POST.get(field_name)
                if player_id:
                    form.initial[field_name] = Player.objects.filter(pk=player_id).first()

            captain_player_id = request.POST.get('captain_player_id')
            if captain_player_id:
                form.initial['captain_player_id'] = captain_player_id

            context = {
                'form': form,
                'tour': tour,
                'submission': submission,
                'budget_limit': budget_limit,
                'previous_player_ids': prev_player_ids,
                'unavailable_players': unavailable_players,
                'players_with_changed_positions': players_with_changed_positions,
            }

            return render(request, 'fantasy_league/edit_squad.html', context)
    else:
        initial_data = {}
        submission = SquadSubmission.objects.filter(
            user=request.user, tour=tour, tournament__league=tour.league
        ).first()

        actual_submission = submission or prev_submission
        if actual_submission:
            primary_squad_players = list(actual_submission.main_squad.select_related('player'))
            if len(primary_squad_players) >= 4:
                gk_players = [sp for sp in primary_squad_players if sp.position == SquadPlayer.Position.GK]
                dm_players = [sp for sp in primary_squad_players if sp.position == SquadPlayer.Position.DM]
                st_players = [sp for sp in primary_squad_players if sp.position == SquadPlayer.Position.ST]

                if gk_players:
                    initial_data['main_squad_gk'] = gk_players[0].player
                if dm_players:
                    initial_data['main_squad_dm'] = dm_players[0].player
                if len(st_players) >= 1:
                    initial_data['main_squad_st1'] = st_players[0].player
                if len(st_players) >= 2:
                    initial_data['main_squad_st2'] = st_players[1].player

            bench_squad_players = list(actual_submission.bench_players.select_related('player'))
            initial_data['bench_gk'] = next(
                (sp.player for sp in bench_squad_players if sp.position == SquadPlayer.Position.GK), None
            )
            initial_data['bench_dm'] = next(
                (sp.player for sp in bench_squad_players if sp.position == SquadPlayer.Position.DM), None
            )
            initial_data['bench_st'] = next(
                (sp.player for sp in bench_squad_players if sp.position == SquadPlayer.Position.ST), None
            )

            initial_data['captain_player_id'] = (
                actual_submission.captain_player.id if actual_submission.captain_player else None
            )

        form = SquadSubmissionForm(initial=initial_data, tournament=tour.league, previous_player_ids=prev_player_ids)

    context = {
        'form': form,
        'tour': tour,
        'submission': submission,
        'budget_limit': budget_limit,
        'previous_player_ids': prev_player_ids,
        'unavailable_players': unavailable_players,
        'players_with_changed_positions': players_with_changed_positions,
    }

    return render(request, 'fantasy_league/edit_squad.html', context)
