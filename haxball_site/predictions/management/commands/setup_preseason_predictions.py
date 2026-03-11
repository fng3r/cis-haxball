import random
from datetime import time

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from predictions.models import (
    PreseasonPredictionItem,
    PreseasonPredictionsTournament,
    PreseasonPredictionSubmission,
)
from tournament.models import League


class Command(BaseCommand):
    help = 'Set up test preseason prediction tournament with sample data'

    def add_arguments(self, parser):
        parser.add_argument(
            'tournament',
            type=str,
            help='Slug of the existing league to create preseason predictions for',
        )
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
            help='List of usernames to include in the preseason prediction tournament',
        )
        parser.add_argument(
            '--real-users',
            action='store_true',
            help='Use real random users instead of test users',
        )
        parser.add_argument(
            '-c',
            type=int,
            default=40,
            help='Number of users to generate predictions for (default: 40)',
        )

    def handle(self, *args, **options):
        tournament = options['tournament']

        if options['clean'] or options['clean_only']:
            self.clean_test_data(tournament)
        if options['clean_only']:
            return
        with transaction.atomic():
            self.create_test_environment(
                tournament=tournament,
                users=options.get('users', []),
                real_users=options.get('real_users', False),
                num_users=options.get('c', 40),
            )
        self.stdout.write(self.style.SUCCESS('Preseason prediction environment created successfully!'))

    def clean_test_data(self, tournament):
        """Clean existing preseason prediction data for the specified league"""
        self.stdout.write(f'Cleaning existing preseason prediction data for league: {tournament}...')

        try:
            league = League.objects.get(slug=tournament)

            # Delete existing preseason predictions for this league
            PreseasonPredictionItem.objects.filter(submission__tournament__league=league).delete()
            PreseasonPredictionSubmission.objects.filter(tournament__league=league).delete()

            # Delete the preseason predictions tournament if it exists
            PreseasonPredictionsTournament.objects.filter(league=league).delete()

            self.stdout.write(self.style.SUCCESS(f'Preseason prediction data cleaned for league: {league.title}'))

        except League.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'League with slug "{tournament}" not found'))
            return

    def create_test_environment(self, tournament, users=None, real_users=False, num_users=40):
        """Create complete preseason prediction environment for existing league"""
        if users is None:
            users = []
        self.stdout.write(f'Creating preseason prediction environment for league: {tournament}...')

        # Get existing league
        try:
            tournament = League.objects.get(slug=tournament)
        except League.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'League with slug "{tournament}" not found'))
            return

        # Get teams from the existing league
        teams = list(tournament.teams.all())
        if not teams:
            self.stdout.write(self.style.ERROR(f'League "{tournament.title}" has no teams'))
            return

        self.stdout.write(f'Found {len(teams)} teams in league: {tournament.title}')

        # Create preseason prediction tournament
        first_tour = tournament.tours.order_by('number').first()
        if first_tour:
            close_at = timezone.make_aware(timezone.datetime.combine(first_tour.date_from, time(18, 0)))
        else:
            close_at = timezone.localtime() + timezone.timedelta(days=7)
        preseason_tournament, created = PreseasonPredictionsTournament.objects.get_or_create(
            league=tournament, defaults={'locked_at': close_at}
        )

        # Select users for preseason predictions
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

        # Add additional users to reach the target number
        excluded_usernames = [u.username for u in test_users]
        if real_users:
            additional_users = list(
                User.objects.exclude(username__in=excluded_usernames).order_by('?')[: num_users - len(test_users)]
            )
            test_users.extend(additional_users)
            if additional_users:
                self.stdout.write(f'Added real users: {", ".join([u.username for u in additional_users])}')
        else:
            for i in range(1, num_users - len(test_users) + 1):
                username = f'preseason-test-user-{i}'
                if username not in excluded_usernames:
                    user, _ = User.objects.get_or_create(username=username, defaults={'is_active': True})
                    test_users.append(user)
                    self.stdout.write(f'Added test user: {user.username}')

        if not test_users:
            self.stdout.write(self.style.ERROR('No users found to create preseason predictions for.'))
            return

        self.stdout.write(
            f'Using {len(test_users)} users for preseason predictions: {", ".join([u.username for u in test_users])}'
        )

        # Helper functions for creating realistic predictions
        def create_team_tiers(teams):
            """Create realistic team tiers (favorites, mid-table, outsiders)"""
            num_teams = len(teams)

            # Define tiers: top 20% = favorites, bottom 30% = outsiders, rest = mid-table
            favorites_count = max(1, num_teams // 5)  # Top 20%
            outsiders_count = max(1, (num_teams * 3) // 10)  # Bottom 30%
            mid_table_count = num_teams - favorites_count - outsiders_count

            tiers = {
                'favorites': teams[:favorites_count],
                'mid_table': teams[favorites_count : favorites_count + mid_table_count],
                'outsiders': teams[favorites_count + mid_table_count :],
            }

            return tiers

        def generate_realistic_predictions(team_tiers, total_teams):
            """Generate realistic predictions with favorites and outsiders"""
            predicted_positions = []

            # Start with favorites - they should mostly finish in top positions
            favorites = team_tiers['favorites'].copy()
            random.shuffle(favorites)  # Some variation in favorites order

            # Add some randomness but keep favorites in top half
            for i, team in enumerate(favorites):
                # Favorites mostly finish in top 40% of positions
                max_position = max(1, (total_teams * 4) // 10)
                position = random.randint(1, max_position)
                predicted_positions.append((team, position))

            # Mid-table teams - more variation but mostly in middle
            mid_table = team_tiers['mid_table'].copy()
            random.shuffle(mid_table)

            for i, team in enumerate(mid_table):
                # Mid-table teams finish in middle 40% of positions
                min_position = max(1, (total_teams * 3) // 10)
                max_position = min(total_teams, (total_teams * 7) // 10)
                position = random.randint(min_position, max_position)
                predicted_positions.append((team, position))

            # Outsiders - mostly finish in bottom positions
            outsiders = team_tiers['outsiders'].copy()
            random.shuffle(outsiders)

            for i, team in enumerate(outsiders):
                # Outsiders mostly finish in bottom 40% of positions
                min_position = max(1, (total_teams * 6) // 10)
                position = random.randint(min_position, total_teams)
                predicted_positions.append((team, position))

            # Sort by predicted position and return teams in order
            predicted_positions.sort(key=lambda x: x[1])
            return [team for team, position in predicted_positions]

        # Create preseason predictions for users
        for user in test_users:
            submission, created = PreseasonPredictionSubmission.objects.get_or_create(
                user=user, tournament=preseason_tournament
            )

            # Generate realistic preseason predictions with favorites and outsiders
            # Create different tiers of teams to simulate real-world scenarios
            team_tiers = create_team_tiers(teams)

            # Generate predictions with realistic variation between users
            predicted_positions = generate_realistic_predictions(team_tiers, len(teams))

            # Create prediction items for each team with their predicted position
            for position, team in enumerate(predicted_positions, 1):
                prediction_item, created = PreseasonPredictionItem.objects.get_or_create(
                    submission=submission,
                    team=team,
                    defaults={'position': position},
                )

        self.stdout.write(f'Created preseason predictions for {len(test_users)} users')
        self.stdout.write(f'Each user has predictions for {len(teams)} teams')

        # Show current status
        self.stdout.write(f'Users with preseason predictions: {", ".join([u.username for u in test_users])}')
        self.stdout.write(f'Teams in league: {", ".join([t.title for t in teams])}')
        self.stdout.write(f'Each user has predictions for {len(teams)} teams')

        # Show current status
        self.stdout.write(f'Users with preseason predictions: {", ".join([u.username for u in test_users])}')
        self.stdout.write(f'Teams in tournament: {", ".join([t.title for t in teams])}')
