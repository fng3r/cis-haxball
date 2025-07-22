import random
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from predictions.models import Prediction, PredictionSubmission, PredictionTournament
from tournament.models import League, Match, MatchResult, RegularStage, Season, Team, TourNumber


class Command(BaseCommand):
    help = 'Set up test prediction tournament with sample data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clean',
            action='store_true',
            help='Clean existing test data before creating new',
        )
        parser.add_argument(
            '--clean-only',
            action='store_true',
            help='Only clean test data and exit',
        )
        parser.add_argument(
            '--users',
            nargs='+',
            type=str,
            help='List of usernames to include in the prediction tournament',
        )
        parser.add_argument(
            '--real-teams',
            action='store_true',
            help='Use real random teams instead of test teams',
        )
        parser.add_argument(
            '--real-users',
            action='store_true',
            help='Use real random users instead of test users',
        )

    def handle(self, *args, **options):
        if options['clean'] or options['clean_only']:
            self.clean_test_data()
        if options['clean_only']:
            return
        with transaction.atomic():
            self.create_test_environment(
                users=options.get('users', []),
                real_teams=options.get('real_teams', False),
                real_users=options.get('real_users', False),
            )
        self.stdout.write(self.style.SUCCESS('Test prediction environment created successfully!'))

    def clean_test_data(self):
        """Clean existing test data"""
        self.stdout.write('Cleaning existing test data...')

        # Delete test predictions
        Prediction.objects.filter(submission__tournament__league__title__icontains='test').delete()
        PredictionSubmission.objects.filter(tournament__league__title__icontains='test').delete()
        PredictionTournament.objects.filter(league__title__icontains='test').delete()

        # Delete test matches and results
        MatchResult.objects.filter(match__league__title__icontains='test').delete()
        Match.objects.filter(league__title__icontains='test').delete()

        # Delete test tours
        TourNumber.objects.filter(league__title__icontains='test').delete()

        # Delete test tournament
        League.objects.filter(title__icontains='test').delete()

        # Do NOT delete users or teams
        self.stdout.write(self.style.SUCCESS('Test data cleaned'))

    def create_test_environment(self, users=None, real_teams=False, real_users=False):
        """Create complete test environment"""
        if users is None:
            users = []
        self.stdout.write('Creating test prediction environment...')

        # Create or get active season
        season, created = Season.objects.get_or_create(
            number=999, defaults={'title': 'Test Season for Predictions', 'short_title': 'TEST', 'is_active': True}
        )

        # Create test tournament
        tournament, created = League.objects.get_or_create(
            title='Test Prediction Tournament',
            defaults={'championship': season, 'slug': 'test-prediction-tournament', 'priority': 1},
        )

        # Create regular stage
        stage, created = RegularStage.objects.get_or_create(
            league=tournament, defaults={'order': 1, 'awarded_count': 3, 'promoted_count': 2, 'relegated_count': 2}
        )

        if real_teams:
            teams = list(Team.objects.exclude(title__startswith='Test Team').order_by('?')[:10])
        else:
            teams = []
            for i in range(1, 11):
                team, _ = Team.objects.get_or_create(
                    title=f'Test Team {i}',
                    defaults={
                        'slug': f'test-team-{i}',
                        'short_title': f'TT{i}',
                        'date_found': timezone.now().date(),
                    },
                )
                teams.append(team)
        tournament.teams.set(teams)
        stage.teams.set(teams)

        # Create prediction tournament
        prediction_tournament, created = PredictionTournament.objects.get_or_create(
            league=tournament, defaults={'is_active': True}
        )

        # Create tours with different dates - place us in the middle of the season
        today = timezone.now().date()
        tours = []

        for i in range(1, 11):  # Create 10 tours
            # Tours 1-4: Past (closed for predictions)
            # Tours 5-7: Currently open for predictions (starting within 3 days)
            # Tours 8-10: Future (not yet open for predictions)
            if i <= 4:
                # Past tours (weeks ago)
                tour_date = today - timedelta(days=(4 - i) * 7)
            elif i <= 7:
                # Currently open tours (starting within 3 days)
                # Tour 5: starts tomorrow
                # Tour 6: starts day after tomorrow
                # Tour 7: starts in 3 days
                tour_date = today + timedelta(days=i - 4)
            else:
                # Future tours (weeks ahead)
                tour_date = today + timedelta(days=(i - 3) * 7)

            tour, created = TourNumber.objects.get_or_create(
                league=tournament,
                number=i,
                defaults={
                    'date_from': tour_date,
                    'date_to': tour_date + timedelta(days=6),
                    'stage': stage,
                },
            )
            tours.append(tour)

        # Create matches for each tour
        matches = []
        for tour in tours:
            # Create 5 matches per tour, ensuring each team plays at most once
            available_teams = teams.copy()
            tour_matches = []

            for j in range(5):
                if len(available_teams) < 2:
                    break
                team1 = available_teams.pop(0)
                team2 = available_teams.pop(0)
                match, created = Match.objects.get_or_create(
                    league=tournament,
                    numb_tour=tour,
                    team_home=team1,
                    team_guest=team2,
                    defaults={
                        'stage': stage,
                        'match_date': tour.date_from + timedelta(days=j),
                    },
                )
                tour_matches.append(match)

            matches.extend(tour_matches)

        # Generate match results for completed matches
        for match in matches:
            match.is_played = match.numb_tour.date_from < today
            if match.is_played:
                result_types = [
                    MatchResult.HOME_WIN,
                    MatchResult.AWAY_WIN,
                    MatchResult.DRAW,
                    MatchResult.HOME_DEF_WIN,
                    MatchResult.AWAY_DEF_WIN,
                    MatchResult.MUTUAL_TECH_DEFEAT,
                ]
                result_value = random.choice(result_types)

                if result_value == MatchResult.HOME_WIN:
                    score_home = random.randint(1, 3)
                    score_guest = random.randint(0, score_home - 1)
                elif result_value == MatchResult.AWAY_WIN:
                    score_guest = random.randint(1, 3)
                    score_home = random.randint(0, score_guest - 1)
                elif result_value == MatchResult.DRAW:
                    score_home = random.randint(0, 2)
                    score_guest = score_home
                elif result_value == MatchResult.HOME_DEF_WIN:
                    score_home = 3
                    score_guest = 0
                elif result_value == MatchResult.AWAY_DEF_WIN:
                    score_home = 0
                    score_guest = 3
                elif result_value == MatchResult.MUTUAL_TECH_DEFEAT:
                    score_home = 0
                    score_guest = 0

                match.score_home = score_home
                match.score_guest = score_guest
                match.save()

        # Select users for predictions
        test_users = []

        # Add specified users first
        if users:
            for username in users:
                try:
                    user = User.objects.get(username=username)
                    test_users.append(user)
                    self.stdout.write(f'Added specified user: {user.username}')
                except User.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f'User "{username}" not found, skipping.'))

        # Add admin user if not already included (only if specified in users argument)
        if 'admin' not in [u.username for u in test_users] and 'admin' in users:
            try:
                admin_user = User.objects.get(username='admin')
                test_users.append(admin_user)
                self.stdout.write(f'Added admin user: {admin_user.username}')
            except User.DoesNotExist:
                self.stdout.write(self.style.WARNING('Admin user not found.'))
        # Add test users to reach at least 15 total users
        excluded_usernames = [u.username for u in test_users]
        if real_users:
            additional_users = list(
                User.objects.exclude(username__in=excluded_usernames).order_by('?')[: 15 - len(test_users)]
            )
            test_users.extend(additional_users)
            if additional_users:
                self.stdout.write(f'Added real users: {", ".join([u.username for u in additional_users])}')
        else:
            for i in range(1, 16 - len(test_users) + 1):
                username = f'predictions-test-user-{i}'
                if username not in excluded_usernames:
                    user, _ = User.objects.get_or_create(username=username, defaults={'is_active': True})
                    test_users.append(user)
                    self.stdout.write(f'Added test user: {user.username}')
        if not test_users:
            self.stdout.write(self.style.ERROR('No users found to create predictions for.'))
            return
        self.stdout.write(
            f'Using {len(test_users)} users for predictions: {", ".join([u.username for u in test_users])}'
        )

        # Create predictions for users
        for user in test_users:
            for tour in tours:
                # Only create predictions for one open tour (tour 5) to leave others blank
                should_create_predictions = tour.number <= 5
                if should_create_predictions:
                    submission, created = PredictionSubmission.objects.get_or_create(
                        user=user, tour=tour, tournament=prediction_tournament
                    )
                    tour_matches = [m for m in matches if m.numb_tour == tour]
                    # Randomly select up to 2 matches to be special
                    special_matches = set(random.sample([m.id for m in tour_matches], k=min(2, len(tour_matches))))
                    for match in tour_matches:
                        # Generate random prediction
                        prediction_value = random.choice(['HW', 'D', 'AW'])
                        is_special = match.id in special_matches
                        prediction, created = Prediction.objects.get_or_create(
                            submission=submission,
                            match=match,
                            defaults={'predicted_result': prediction_value, 'is_special': is_special},
                        )

        self.stdout.write(f'Created test tournament: {tournament.title}')
        self.stdout.write(f'Created {len(tours)} tours')
        self.stdout.write(f'Created {len(matches)} matches')
        self.stdout.write(f'Created predictions for {len(test_users)} users')

        # Show current status
        open_tours = [t for t in tours if timedelta(days=0) <= t.date_from - today <= timedelta(days=3)]
        closed_tours = [t for t in tours if t.date_from < today]

        self.stdout.write(f'Open tours for predictions: {len(open_tours)}')
        self.stdout.write(f'Closed tours: {len(closed_tours)}')
        self.stdout.write(f'Users with predictions: {", ".join([u.username for u in test_users])}')
