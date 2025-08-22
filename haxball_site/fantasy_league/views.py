from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string

from tournament.models import TourNumber

from .forms import SquadSubmissionForm, TournamentFilterForm, UserFilterForm
from .models import FantasyTournament, SquadPlayer, SquadSubmission
from .utils import (
    get_player_fantasy_stats,
    get_tournament_standings,
    is_tour_open_for_fantasy,
    preload_fantasy_data,
)


def get_default_tournament():
    return FantasyTournament.objects.filter(is_active=True).select_related('league', 'league__championship').first()


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
    default_tournament = get_default_tournament()
    selected_tournament = None
    selected_user = None

    if request.GET.get('tournament'):
        selected_tournament = FantasyTournament.objects.filter(pk=request.GET.get('tournament')).first()
    elif default_tournament:
        selected_tournament = default_tournament

    tournament_form = TournamentFilterForm(
        initial={'tournament': selected_tournament.pk if selected_tournament else None}
    )
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
    return render(request, 'fantasy_league/main.html', context)


def make_squad_tab(request, initial_context=False, selected_tournament=None):
    """Tab for making squad submissions"""
    if not request.user.is_authenticated:
        return render_to_string('fantasy_league/make_squad_tab.html', {'user': request.user}, request=request)

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

    user_squads = {}
    if selected_tournament:
        preloaded_data = preload_fantasy_data(selected_tournament)

        tours = TourNumber.objects.filter(league=selected_tournament.league).order_by('number')

        submissions = (
            SquadSubmission.objects.filter(user=request.user, tournament=selected_tournament)
            .prefetch_related('primary_squad__player', 'secondary_squad__player', 'tour')
            .select_related('tour')
        )

        # Create lookup dictionary for efficient access
        submissions_lookup = {sub.tour_id: sub for sub in submissions}

        # Build user_squads dictionary
        for tour in tours:
            submission = submissions_lookup.get(tour.id)
            if submission:
                # Data is already prefetched, so this is efficient
                primary_players = list(submission.primary_squad.all())
                secondary_players = list(submission.secondary_squad.all())
                user_squads[tour.id] = {
                    'submission': submission,
                    'primary_players': primary_players,
                    'secondary_players': secondary_players,
                }
            else:
                user_squads[tour.id] = {'submission': None, 'primary_players': [], 'secondary_players': []}

    context = {
        'tournament_form': tournament_form,
        'selected_tournament': selected_tournament,
        'user_squads': user_squads,
        'user': request.user,
        'preloaded_data': preloaded_data if selected_tournament else None,
    }
    if initial_context:
        return render_to_string('fantasy_league/make_squad_tab.html', context, request=request)
    return render(request, 'fantasy_league/make_squad_tab.html', context)


def view_squads_tab(request):
    """Tab for viewing other users' squad submissions"""
    default_tournament = get_default_tournament()

    selected_tournament = None
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

    user_id = request.GET.get('user')
    selected_user = None
    if user_id:
        selected_user = User.objects.filter(pk=user_id).select_related('user_profile').first()
    elif get_users_with_submissions(selected_tournament):
        selected_user = get_users_with_submissions(selected_tournament).first()
    if not selected_user:
        selected_user = User.objects.select_related('user_profile').first()

    tournament_form = TournamentFilterForm(
        initial={'tournament': selected_tournament.pk if selected_tournament else None}
    )
    user_form = UserFilterForm(initial={'user': selected_user.pk if selected_user else None})

    if get_users_with_submissions(selected_tournament):
        user_form.fields['user'].queryset = get_users_with_submissions(selected_tournament)

    squads_data = {}
    if selected_tournament and selected_user:
        preloaded_data = preload_fantasy_data(selected_tournament)

        tours = TourNumber.objects.filter(league=selected_tournament.league).order_by('number')

        submissions = (
            SquadSubmission.objects.filter(user=selected_user, tournament=selected_tournament)
            .prefetch_related('primary_squad__player', 'secondary_squad__player', 'tour')
            .select_related('tour')
        )

        submissions_lookup = {sub.tour_id: sub for sub in submissions}
        for tour in tours:
            submission = submissions_lookup.get(tour.id)
            if submission and not is_tour_open_for_fantasy(tour):
                squads_data[tour.id] = submission
            else:
                squads_data[tour.id] = None

    context = {
        'tournament_form': tournament_form,
        'user_form': user_form,
        'selected_tournament': selected_tournament,
        'selected_user': selected_user,
        'squads_data': squads_data,
        'preloaded_data': preloaded_data if selected_tournament and selected_user else None,
    }

    return render(request, 'fantasy_league/view_squads_tab.html', context)


def standings_tab(request):
    """Tab for tournament standings"""
    default_tournament = get_default_tournament()

    selected_tournament = None
    if request.GET.get('tournament'):
        selected_tournament = FantasyTournament.objects.filter(pk=request.GET.get('tournament')).first()
    elif default_tournament:
        selected_tournament = default_tournament

    tournament_form = TournamentFilterForm(
        initial={'tournament': selected_tournament.pk if selected_tournament else None}
    )

    standings = []
    tour_points = {}

    if selected_tournament:
        standings = get_tournament_standings(selected_tournament)

        tours = TourNumber.objects.filter(league=selected_tournament.league).order_by('number')

        preloaded_data = preload_fantasy_data(selected_tournament)
        all_submissions = (
            SquadSubmission.objects.filter(tournament=selected_tournament)
            .prefetch_related('primary_squad__player', 'secondary_squad__player')
            .select_related('user', 'tour')
        )

        submissions_lookup = {}
        for submission in all_submissions:
            key = (submission.user_id, submission.tour_id)
            submissions_lookup[key] = submission

        for standing in standings:
            user = standing['user']
            tour_points[user.id] = {}
            for tour in tours:
                submission = submissions_lookup.get((user.id, tour.id))
                if submission:
                    tour_points[user.id][tour.id] = submission.get_total_points(preloaded_data)
                else:
                    tour_points[user.id][tour.id] = None

    context = {
        'tournament_form': tournament_form,
        'selected_tournament': selected_tournament,
        'standings': standings,
        'tour_points': tour_points,
    }

    return render(request, 'fantasy_league/standings_tab.html', context)


def statistics_tab(request):
    """Tab for player statistics"""
    default_tournament = get_default_tournament()

    selected_tournament = None
    if request.GET.get('tournament'):
        selected_tournament = FantasyTournament.objects.filter(pk=request.GET.get('tournament')).first()
    elif default_tournament:
        selected_tournament = default_tournament

    tournament_form = TournamentFilterForm(
        initial={'tournament': selected_tournament.pk if selected_tournament else None}
    )

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
        .prefetch_related('primary_squad__player', 'secondary_squad__player')
        .first()
    )

    context = {
        'tour': tour,
        'tournament': tournament,
        'submission': submission,
        'is_open': is_tour_open_for_fantasy(tour),
        'preloaded_data': preloaded_data,
    }

    return render(request, 'fantasy_league/partials/tour_card.html', context)


@login_required
def edit_squad(request, tour_id):
    """Edit squad for a specific tour"""
    tour = get_object_or_404(TourNumber, pk=tour_id)

    if not is_tour_open_for_fantasy(tour):
        messages.error(request, 'Тур уже закрыт для отправки составов')
        return redirect('fantasy_league:main')

    if request.method == 'POST':
        submission, _ = SquadSubmission.objects.get_or_create(
            user=request.user,
            tour=tour,
            tournament__league=tour.league,
            defaults={'tournament': tour.league.fantasy_tournament},
        )

        form = SquadSubmissionForm(request.POST, tournament=tour.league)
        if form.is_valid():
            with transaction.atomic():
                submission.primary_squad.clear()
                submission.secondary_squad.clear()

                primary_players_data = [
                    (form.cleaned_data['primary_gk'], SquadPlayer.Position.GK),
                    (form.cleaned_data['primary_dm'], SquadPlayer.Position.DM),
                    (form.cleaned_data['primary_st1'], SquadPlayer.Position.ST),
                    (form.cleaned_data['primary_st2'], SquadPlayer.Position.ST),
                ]

                for player, position in primary_players_data:
                    squad_player, _ = SquadPlayer.objects.get_or_create(player=player, position=position)
                    submission.primary_squad.add(squad_player)

                secondary_players_data = [
                    (form.cleaned_data['secondary_gk'], SquadPlayer.Position.GK),
                    (form.cleaned_data['secondary_dm'], SquadPlayer.Position.DM),
                    (form.cleaned_data['secondary_st1'], SquadPlayer.Position.ST),
                    (form.cleaned_data['secondary_st2'], SquadPlayer.Position.ST),
                ]

                for player, position in secondary_players_data:
                    squad_player, _ = SquadPlayer.objects.get_or_create(player=player, position=position)
                    submission.secondary_squad.add(squad_player)

                submission.save()

                return render(
                    request,
                    'fantasy_league/partials/tour_card.html',
                    {
                        'submission': submission,
                        'tour': tour,
                        'is_open': is_tour_open_for_fantasy(tour),
                        'preloaded_data': preload_fantasy_data(submission.tournament),
                    },
                )
    else:
        submission = SquadSubmission.objects.filter(
            user=request.user, tour=tour, tournament__league=tour.league
        ).first()
        initial_data = {}

        primary_squad_players = list(submission.primary_squad.all().select_related('player')) if submission else []
        if len(primary_squad_players) >= 4:
            gk_players = [sp for sp in primary_squad_players if sp.position == SquadPlayer.Position.GK]
            dm_players = [sp for sp in primary_squad_players if sp.position == SquadPlayer.Position.DM]
            st_players = [sp for sp in primary_squad_players if sp.position == SquadPlayer.Position.ST]

            if gk_players:
                initial_data['primary_gk'] = gk_players[0].player
            if dm_players:
                initial_data['primary_dm'] = dm_players[0].player
            if len(st_players) >= 1:
                initial_data['primary_st1'] = st_players[0].player
            if len(st_players) >= 2:
                initial_data['primary_st2'] = st_players[1].player

        secondary_squad_players = list(submission.secondary_squad.all().select_related('player')) if submission else []
        if len(secondary_squad_players) >= 4:
            gk_players = [sp for sp in secondary_squad_players if sp.position == SquadPlayer.Position.GK]
            dm_players = [sp for sp in secondary_squad_players if sp.position == SquadPlayer.Position.DM]
            st_players = [sp for sp in secondary_squad_players if sp.position == SquadPlayer.Position.ST]

            if gk_players:
                initial_data['secondary_gk'] = gk_players[0].player
            if dm_players:
                initial_data['secondary_dm'] = dm_players[0].player
            if len(st_players) >= 1:
                initial_data['secondary_st1'] = st_players[0].player
            if len(st_players) >= 2:
                initial_data['secondary_st2'] = st_players[1].player

        form = SquadSubmissionForm(initial=initial_data, tournament=tour.league)

    budget_limit = SquadSubmissionForm(tournament=tour.league).get_league_budget_limit(tour.league)

    context = {
        'form': form,
        'tour': tour,
        'submission': submission,
        'budget_limit': budget_limit,
    }
    print('render edit squad')

    return render(request, 'fantasy_league/edit_squad.html', context)
