import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from tournament.models import (
    Award,
    AwardCampaign,
    AwardNomination,
    AwardNominee,
    AwardSubmission,
    AwardVote,
    AwardVoter,
    League,
    Player,
)


class Command(BaseCommand):
    help = 'Generate test nominations for a league with players based on positions and team captains as representatives'

    def add_arguments(self, parser):
        parser.add_argument('league_slug', type=str, help='Slug of the league to create awards for')
        parser.add_argument(
            '--generate-votes',
            action='store_true',
            help='Generate random vote submissions for all voters',
        )

    def handle(self, *args, **options):
        league_slug = options['league_slug']
        generate_votes = options.get('generate_votes', False)

        try:
            league = League.objects.get(slug=league_slug)
        except League.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'League with slug "{league_slug}" does not exist'))
            return

        self.stdout.write(f'Generating test awards for league: {league.title}')

        # Create or get award nominations
        nominations_data = [
            ('Нападающий сезона', AwardNomination.Code.BEST_STRIKER, 1),
            ('Опорник сезона', AwardNomination.Code.BEST_DEFENDER, 2),
            ('Вратарь сезона', AwardNomination.Code.BEST_GOALKEEPER, 3),
            ('Игрок сезона', AwardNomination.Code.BEST_PLAYER, 4),
            ('Капитан сезона', AwardNomination.Code.BEST_CAPTAIN, 5),
            ('Прорыв сезона', AwardNomination.Code.BREAKTHROUGH, 6),
        ]

        nominations = {}
        for name, code, order in nominations_data:
            nomination, created = AwardNomination.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'order': order,
                },
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created nomination: {name}'))
            nominations[code] = nomination

        teams = league.teams.all()
        if not teams.exists():
            self.stdout.write(self.style.ERROR('No teams found in this league'))
            return

        season = league.championship
        now = timezone.now()
        voting_start = now
        voting_end = now + timedelta(days=7)
        results_public = now + timedelta(days=10)

        # Create or get AwardCampaign
        campaign, campaign_created = AwardCampaign.objects.get_or_create(
            season=season,
            defaults={
                'is_active': True,
                'voting_start_date': voting_start,
                'voting_end_date': voting_end,
                'results_public_date': results_public,
            },
        )
        if campaign_created:
            self.stdout.write(self.style.SUCCESS(f'Created award campaign for {season.title}'))

        # Create Award entries
        awards_created = 0
        for code, nomination in nominations.items():
            award, created = Award.objects.get_or_create(
                campaign=campaign,
                league=league,
                nomination=nomination,
            )
            if created:
                awards_created += 1
                self.stdout.write(self.style.SUCCESS(f'Created award: {nomination.name}'))

        # Get players from teams in the league
        league_players = Player.objects.filter(team__in=teams).select_related('team')

        # Create nominees based on positions
        # Nominee counts: Best Striker - 8, Best Player - unlimited (auto-populated),
        # Best Captain - unlimited (all captains), others - 6
        nominee_counts = {
            AwardNomination.Code.BEST_STRIKER: 8,
            AwardNomination.Code.BEST_DEFENDER: 6,
            AwardNomination.Code.BEST_GOALKEEPER: 6,
            AwardNomination.Code.BEST_PLAYER: None,  # Will be auto-populated
            AwardNomination.Code.BEST_CAPTAIN: None,  # All captains
            AwardNomination.Code.BREAKTHROUGH: 6,
        }

        position_mapping = {
            AwardNomination.Code.BEST_STRIKER: [Player.Position.ST],
            AwardNomination.Code.BEST_DEFENDER: [Player.Position.DM],
            AwardNomination.Code.BEST_GOALKEEPER: [Player.Position.GK],
            # All positions
            AwardNomination.Code.BEST_PLAYER: [Player.Position.ST, Player.Position.DM, Player.Position.GK],
            AwardNomination.Code.BEST_CAPTAIN: [],  # Will be filled with captains
            # All positions
            AwardNomination.Code.BREAKTHROUGH: [Player.Position.ST, Player.Position.DM, Player.Position.GK],
        }

        nominees_created = 0
        for award in Award.objects.filter(campaign=campaign, league=league).select_related('nomination'):
            nomination_code = award.nomination.code
            nominee_count = nominee_counts.get(nomination_code, 6)

            if nomination_code == AwardNomination.Code.BEST_PLAYER:
                # Skip Best Player - it will be auto-populated from other nominations
                self.stdout.write(f'Skipping {award.nomination.name} - will be auto-populated')
                continue

            if nomination_code == AwardNomination.Code.BEST_CAPTAIN:
                # Get all captains from teams in the league (no limit)
                eligible_players = []
                for team in teams:
                    if team.captain:
                        eligible_players.append(team.captain)
            else:
                # Get players by position
                positions = position_mapping.get(nomination_code, [])
                if positions:
                    query = league_players.filter(positions__overlap=positions).distinct()
                    if nominee_count:
                        query = query[:nominee_count]
                    eligible_players = list(query)
                else:
                    eligible_players = list(league_players[:nominee_count] if nominee_count else league_players)

            # Create nominees
            for player in eligible_players:
                nominee, created = AwardNominee.objects.get_or_create(
                    award=award,
                    player=player,
                    defaults={'is_auto_nominated': nomination_code == AwardNomination.Code.BEST_PLAYER},
                )
                if created:
                    nominees_created += 1

            self.stdout.write(f'Created {len(eligible_players)} nominees for {award.nomination.name}')

        # Auto-populate Best Player nominees from other nominations
        best_player_award = Award.objects.filter(
            campaign=campaign, league=league, nomination__code=AwardNomination.Code.BEST_PLAYER
        ).first()
        if best_player_award:
            auto_nominees_count = best_player_award.auto_populate_best_player_nominees()
            if auto_nominees_count > 0:
                nominees_created += auto_nominees_count
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Auto-populated {auto_nominees_count} nominees for {best_player_award.nomination.name}'
                    )
                )

        # Create AwardVoter entries using team captains
        voters_created = 0
        for team in teams:
            captain = team.captain
            if not captain:
                # If no captain, use the first player from the team
                captain = team.players_in_team.first()
                if not captain:
                    self.stdout.write(self.style.WARNING(f'Team {team.title} has no players, skipping voter creation'))
                    continue

            # Create one voter per team per campaign per league (not per award)
            voter, created = AwardVoter.objects.get_or_create(
                campaign=campaign,
                league=league,
                team=team,
                defaults={'voter': captain},
            )
            if created:
                voters_created += 1

        # Generate random votes if requested
        submissions_created = 0
        votes_created = 0
        if generate_votes:
            self.stdout.write('\nGenerating random vote submissions...')
            awards = Award.objects.filter(campaign=campaign, league=league).select_related('nomination')
            # Only get eligible voters (those with an assigned voter/player)
            voters = AwardVoter.objects.filter(campaign=campaign, league=league, voter__isnull=False).select_related(
                'team', 'voter'
            )

            for voter_record in voters:
                team = voter_record.team
                voter_player = voter_record.voter

                # Create or get one submission for this team and campaign
                submission, created = AwardSubmission.objects.get_or_create(
                    campaign=campaign,
                    team=team,
                    defaults={'voter': voter_player, 'league': league, 'submitted_at': timezone.now()},
                )
                # Update voter and league in case they changed
                if submission.voter != voter_player or submission.league != league:
                    submission.voter = voter_player
                    submission.league = league
                    submission.save(update_fields=['voter', 'league'])
                if created:
                    submissions_created += 1

                # Delete existing votes if any
                AwardVote.objects.filter(submission=submission).delete()

                # Track own-team players selected across all awards (count selections, not unique players)
                own_team_selections = []

                # Create votes for all awards in this campaign and league
                for award in awards:
                    nominees = list(award.nominees.all().select_related('player'))

                    if len(nominees) < 3:
                        self.stdout.write(
                            self.style.WARNING(
                                f'Skipping {award.nomination.name} for {team.title} - '
                                f'not enough nominees ({len(nominees)} < 3)'
                            )
                        )
                        continue

                    # If limit of 3 own-team selections is reached, exclude own-team players from pool
                    if len(own_team_selections) >= 3:
                        nominees = [n for n in nominees if n.player.team != team]

                    if len(nominees) < 3:
                        self.stdout.write(
                            self.style.WARNING(
                                f'Skipping {award.nomination.name} for {team.title} - '
                                f'not enough eligible nominees after filtering ({len(nominees)} < 3)'
                            )
                        )
                        continue

                    # Randomly select 3 different players for places 1, 2, 3
                    selected_players = random.sample(nominees, 3)
                    random.shuffle(selected_players)  # Randomize the order

                    # Track own-team selections
                    for nominee in selected_players:
                        if nominee.player.team == team:
                            own_team_selections.append(nominee.player)

                    # Create votes for this award
                    for place in [1, 2, 3]:
                        player = selected_players[place - 1].player
                        AwardVote.objects.create(
                            submission=submission,
                            award=award,
                            player=player,
                            place=place,
                        )
                        votes_created += 1

                # Update submitted_at timestamp
                submission.submitted_at = timezone.now()
                submission.save(update_fields=['submitted_at'])

            self.stdout.write(
                self.style.SUCCESS(f'Generated {submissions_created} submissions with {votes_created} votes')
            )

        summary = (
            f'\nSummary:\n'
            f'  - Awards created: {awards_created}\n'
            f'  - Nominees created: {nominees_created}\n'
            f'  - Voters created: {voters_created}\n'
        )
        if generate_votes:
            summary += f'  - Submissions created: {submissions_created}\n  - Votes created: {votes_created}\n'
        summary += (
            f'  - Voting period: {voting_start.strftime("%d.%m.%Y %H:%M")} - '
            f'{voting_end.strftime("%d.%m.%Y %H:%M")}\n'
            f'  - Results public: {results_public.strftime("%d.%m.%Y %H:%M")}'
        )
        self.stdout.write(self.style.SUCCESS(summary))
