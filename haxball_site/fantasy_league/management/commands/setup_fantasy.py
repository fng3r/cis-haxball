import random
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from fantasy_league.models import FantasyTournament, SquadPlayer, SquadSubmission
from tournament.models import League, Player, TourNumber


class Command(BaseCommand):
    help = 'Set up test fantasy league with sample data for an existing league'

    def add_arguments(self, parser):
        parser.add_argument(
            'league',
            type=str,
            help='League slug or title to create fantasy tournament for',
        )
        parser.add_argument(
            '--clean',
            action='store_true',
            help='Clean existing fantasy data for this league before creating new',
        )
        parser.add_argument(
            '--clean-only',
            action='store_true',
            help='Only clean fantasy data for this league and exit',
        )
        parser.add_argument(
            '--users',
            nargs='+',
            type=str,
            help='List of usernames to include in the fantasy tournament',
        )
        parser.add_argument(
            '--real-users',
            action='store_true',
            help='Use real random users instead of test users',
        )
        parser.add_argument(
            '--tours',
            nargs='+',
            type=int,
            help='Specific tour numbers to create submissions for (default: all tours)',
        )

    def handle(self, *args, **options):
        # Find the league
        league = self.find_league(options['league'])
        if not league:
            self.stdout.write(self.style.ERROR(f'League "{options["league"]}" not found.'))
            return

        if options['clean'] or options['clean_only']:
            self.clean_fantasy_data(league)
        if options['clean_only']:
            return

        with transaction.atomic():
            self.create_fantasy_environment(
                league=league,
                users=options.get('users', []),
                real_users=options.get('real_users', False),
                specific_tours=options.get('tours', []),
            )
        self.stdout.write(self.style.SUCCESS(f'Fantasy league environment created successfully for {league.title}!'))

    def find_league(self, league_identifier):
        """Find league by slug"""
        try:
            return League.objects.get(slug=league_identifier)
        except League.DoesNotExist:
            return None

    def clean_fantasy_data(self, league):
        """Clean existing fantasy data for the league"""
        self.stdout.write(f'Cleaning existing fantasy data for {league.title}...')

        SquadSubmission.objects.filter(tournament__league=league).delete()
        FantasyTournament.objects.filter(league=league).delete()

        # Note: We don't delete SquadPlayer instances as they might be used by other leagues
        # They will be cleaned up automatically if not referenced anywhere

        self.stdout.write(self.style.SUCCESS(f'Fantasy data cleaned for {league.title}'))

    def create_fantasy_environment(self, league, users=None, real_users=False, specific_tours=None):
        """Create fantasy environment for the league"""
        if users is None:
            users = []
        self.stdout.write(f'Creating fantasy environment for {league.title}...')

        fantasy_tournament, created = FantasyTournament.objects.get_or_create(
            league=league, defaults={'is_active': True}
        )
        if created:
            self.stdout.write(f'Created fantasy tournament for {league.title}')
        else:
            self.stdout.write(f'Using existing fantasy tournament for {league.title}')

        # Get all tours for this league
        all_tours = TourNumber.objects.filter(league=league).order_by('number')
        if specific_tours:
            tours = all_tours.filter(number__in=specific_tours)
            self.stdout.write(f'Using specific tours: {list(specific_tours)}')
        else:
            tours = all_tours
            self.stdout.write(f'Using all {tours.count()} tours')

        if not tours.exists():
            self.stdout.write(self.style.ERROR(f'No tours found for league {league.title}'))
            return

        available_players = Player.objects.filter(team__in=league.teams.all()).distinct()

        if not available_players.exists():
            self.stdout.write(self.style.ERROR(f'No players found for teams in league {league.title}'))
            return

        test_users = []

        if users:
            for username in users:
                try:
                    user = User.objects.get(username=username)
                    test_users.append(user)
                    self.stdout.write(f'Added specified user: {user.username}')
                except User.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f'User "{username}" not found, skipping.'))

        # Add admin user if not already included
        if 'admin' not in [u.username for u in test_users]:
            try:
                admin_user = User.objects.get(username='admin')
                test_users.append(admin_user)
                self.stdout.write(f'Added admin user: {admin_user.username}')
            except User.DoesNotExist:
                self.stdout.write(self.style.WARNING('Admin user not found.'))

        # Add additional users to reach at least 15 total users
        excluded_usernames = [u.username for u in test_users]
        if real_users:
            additional_users = list(
                User.objects.exclude(username__in=excluded_usernames).order_by('?')[: 15 - len(test_users)]
            )
            test_users.extend(additional_users)
            if additional_users:
                self.stdout.write(f'Added real users: {", ".join([u.username for u in additional_users])}')
        else:
            for i in range(1, 15 - len(test_users) + 1):
                username = f'fantasy-test-user-{i}'
                if username not in excluded_usernames:
                    user, _ = User.objects.get_or_create(username=username, defaults={'is_active': True})
                    test_users.append(user)
                    self.stdout.write(f'Added test user: {user.username}')

        if not test_users:
            self.stdout.write(self.style.ERROR('No users found to create fantasy submissions for.'))
            return

        self.stdout.write(f'Using {len(test_users)} users for fantasy: {", ".join([u.username for u in test_users])}')

        squad_players = {}
        positions = [SquadPlayer.Position.GK, SquadPlayer.Position.DM, SquadPlayer.Position.ST]

        for player in available_players:
            for position in positions:
                squad_player, created = SquadPlayer.objects.get_or_create(player=player, position=position)
                squad_players[(player.id, position)] = squad_player

        submissions_created = 0
        for user in test_users:
            for tour in tours:
                submission, created = SquadSubmission.objects.get_or_create(
                    user=user,
                    tour=tour,
                    tournament=fantasy_tournament,
                )

                if created:
                    submissions_created += 1
                    main_squad, bench_players = self.generate_random_team(available_players, squad_players)
                    submission.main_squad.set(main_squad)
                    submission.bench_players.set(bench_players)

                if not submission.captain_player_id:
                    if created:
                        main_squad_players = list(main_squad)
                    else:
                        main_squad_players = list(submission.main_squad.all())
                    random.shuffle(main_squad_players)
                    submission.captain_player = main_squad_players[0].player
                    submission.save()

        self.stdout.write(f'Created {submissions_created} fantasy submissions')
        self.stdout.write(
            f'Created SquadPlayer instances for {len(available_players)} players in {len(positions)} positions'
        )

        today = timezone.now().date()
        open_tours = [t for t in tours if timedelta(days=0) <= t.date_from - today <= timedelta(days=3)]
        closed_tours = [t for t in tours if t.date_from < today]

        self.stdout.write(f'Open tours for fantasy: {len(open_tours)}')
        self.stdout.write(f'Closed tours: {len(closed_tours)}')
        self.stdout.write(f'Users with fantasy submissions: {", ".join([u.username for u in test_users])}')

    def generate_random_team(self, available_players, squad_players):
        """Generate team: 4 main (GK, DM, ST, ST) + 2 bench (distinct positions)."""
        used_players = set()
        team_counts: dict[int, int] = {}

        def can_pick(player):
            # Respect 2-per-team limit for players that have a team
            if player.id in used_players:
                return False

            return team_counts.get(player.team_id, 0) < 2

        def apply_pick(player):
            if player is None:
                return None
            used_players.add(player.id)
            if getattr(player, 'team_id', None):
                team_counts[player.team_id] = team_counts.get(player.team_id, 0) + 1
            return player

        def pick_from_pool(players_pool):
            candidates = [p for p in players_pool if can_pick(p)]
            if not candidates:
                return None
            return apply_pick(random.choice(candidates))

        def pick_any():
            candidates = [p for p in available_players if can_pick(p)]
            if not candidates:
                return None
            return apply_pick(random.choice(candidates))

        gk_players = [p for p in available_players if SquadPlayer.Position.GK in p.positions]
        dm_players = [p for p in available_players if SquadPlayer.Position.DM in p.positions]
        st_players = [p for p in available_players if SquadPlayer.Position.ST in p.positions]

        primary = []
        gk = pick_from_pool(gk_players) or pick_any()
        if gk:
            primary.append((gk, SquadPlayer.Position.GK))
        dm = pick_from_pool(dm_players) or pick_any()
        if dm:
            primary.append((dm, SquadPlayer.Position.DM))
        st1 = pick_from_pool(st_players) or pick_any()
        if st1:
            primary.append((st1, SquadPlayer.Position.ST))
        st2 = pick_from_pool(st_players) or pick_any()
        if st2:
            primary.append((st2, SquadPlayer.Position.ST))

        # Bench: choose exactly 2, at most one per position, skipping one random position
        bench = []
        bench_positions = [SquadPlayer.Position.GK, SquadPlayer.Position.DM, SquadPlayer.Position.ST]
        random.shuffle(bench_positions)
        bench_positions = bench_positions[:2]
        for pos in bench_positions:
            pool = (
                gk_players
                if pos == SquadPlayer.Position.GK
                else dm_players
                if pos == SquadPlayer.Position.DM
                else st_players
            )
            b = pick_from_pool(pool) or pick_any()
            if b:
                bench.append((b, pos))

        # Ensure no duplicates within the team and fill missing bench spots if any
        all_players = [p[0].id for p in primary + bench]
        if len(set(all_players)) < 6:
            for p in available_players:
                if len(bench) >= 2:
                    break
                if can_pick(p):
                    # Prefer ST if possible; keep one-per-position bench constraint
                    # Determine allowed bench positions left
                    bench_pos_left = {SquadPlayer.Position.GK, SquadPlayer.Position.DM, SquadPlayer.Position.ST}
                    for _, pos in bench:
                        if pos in bench_pos_left:
                            bench_pos_left.remove(pos)
                    # Try to map player's positions to an allowed bench position
                    desired_pos = None
                    if getattr(p, 'positions', None):
                        if SquadPlayer.Position.ST in p.positions and SquadPlayer.Position.ST in bench_pos_left:
                            desired_pos = SquadPlayer.Position.ST
                        elif SquadPlayer.Position.DM in p.positions and SquadPlayer.Position.DM in bench_pos_left:
                            desired_pos = SquadPlayer.Position.DM
                        elif SquadPlayer.Position.GK in p.positions and SquadPlayer.Position.GK in bench_pos_left:
                            desired_pos = SquadPlayer.Position.GK
                    if desired_pos is None and bench_pos_left:
                        desired_pos = next(iter(bench_pos_left))
                    if desired_pos is not None:
                        apply_pick(p)
                        bench.append((p, desired_pos))
            # Final safety: relax team cap only to complete structure if severely constrained
            if len(bench) < 2:
                remaining = 2 - len(bench)
                fallback_pool = [p for p in available_players if p.id not in used_players]
                for p in fallback_pool[:remaining]:
                    # choose any allowed position left
                    bench_pos_left = {
                        SquadPlayer.Position.GK,
                        SquadPlayer.Position.DM,
                        SquadPlayer.Position.ST,
                    }
                    for _, pos in bench:
                        if pos in bench_pos_left:
                            bench_pos_left.remove(pos)
                    desired_pos = next(iter(bench_pos_left)) if bench_pos_left else SquadPlayer.Position.ST
                    used_players.add(p.id)
                    bench.append((p, desired_pos))

        main_squad = [squad_players[(p.id, pos)] for p, pos in primary if (p.id, pos) in squad_players]
        bench_players = [squad_players[(p.id, pos)] for p, pos in bench if (p.id, pos) in squad_players]
        return main_squad, bench_players
