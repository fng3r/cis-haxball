from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from balance.services import BalanceService
from fantasy_league.models import FantasyTournament
from fantasy_league.utils import calculate_tour_rewards as calculate_fantasy_tour_rewards
from predictions.models import PredictionsContestTournament
from predictions.utils import calculate_tour_rewards as calculate_predictions_tour_rewards
from tournament.models import TourNumber


class Command(BaseCommand):
    help = 'Начислить монеты за награды фэнтези или турнира прогнозистов'

    def add_arguments(self, parser):
        parser.add_argument(
            'activity',
            choices=['fantasy', 'predictions'],
            help='Режим начисления: fantasy или predictions',
        )
        parser.add_argument('league_slug', type=str, help='Slug лиги')
        parser.add_argument('--from', type=int, required=True, dest='tour_from', help='Начальный тур')
        parser.add_argument('--to', type=int, dest='tour_to', help='Конечный тур (включительно)')
        parser.add_argument('--dry-run', action='store_true', help='Показать начисления без создания транзакций')

    def handle(self, *args, **options):
        activity = options['activity']
        league_slug = options['league_slug']
        tour_from = options['tour_from']
        tour_to = options['tour_to']
        dry_run = options['dry_run']

        config = self._get_mode_config(activity)
        tournament = self._get_tournament(config['tournament_model'], league_slug, activity)
        tours = self._get_tours(tournament, tour_from, tour_to)

        if dry_run:
            self._handle_dry_run(tournament, tours, config)
            return

        created_transactions_count = 0
        distributed_tours_count = 0

        for tour in tours:
            if not self._is_tour_completed(tour):
                self.stdout.write(
                    self.style.WARNING(f'Тур {tour.number}: не все матчи сыграны, начисление наград пропущено')
                )
                continue

            description = self._build_description(tour, tournament, config['label'])
            rewards_data = config['calculate_tour_rewards'](tour, tournament)

            transactions_count = 0
            total_amount = Decimal('0.00')

            with transaction.atomic():
                for reward in rewards_data['user_rewards']:
                    amount = reward['reward_amount']
                    if amount <= 0:
                        continue

                    BalanceService.add_coins(
                        user=reward['user'],
                        amount=amount,
                        description=description,
                    )
                    transactions_count += 1
                    total_amount += amount

            created_transactions_count += transactions_count

            if transactions_count > 0:
                distributed_tours_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Тур {tour.number}: создано {transactions_count} транзакций '
                        f'на сумму {total_amount} ("{description}")'
                    )
                )
            else:
                self.stdout.write(f'Тур {tour.number}: нет положительных наград для начисления ("{description}")')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Туров с начислениями: {distributed_tours_count}'))
        self.stdout.write(self.style.SUCCESS(f'Создано транзакций: {created_transactions_count}'))

    def _get_mode_config(self, activity):
        if activity == 'fantasy':
            return {
                'tournament_model': FantasyTournament,
                'calculate_tour_rewards': calculate_fantasy_tour_rewards,
                'label': 'фэнтези',
            }

        return {
            'tournament_model': PredictionsContestTournament,
            'calculate_tour_rewards': calculate_predictions_tour_rewards,
            'label': 'турнира прогнозистов',
        }

    def _get_tournament(self, model, league_slug, activity):
        try:
            return model.objects.select_related('league').get(league__slug=league_slug)
        except model.DoesNotExist as exc:
            raise CommandError(f'Турнир "{activity}" для лиги "{league_slug}" не найден') from exc

    def _get_tours(self, tournament, tour_from, tour_to):
        if tour_to is None:
            tour_to = tour_from

        if tour_to < tour_from:
            raise CommandError('tour_to не может быть меньше tour_from')

        tours = TourNumber.objects.filter(league=tournament.league).order_by('number', 'date_from', 'id')
        tours = tours.filter(number__gte=tour_from, number__lte=tour_to)

        tours = list(tours)
        if not tours:
            raise CommandError(f'Не найдено туров для начисления в диапазоне {tour_from}-{tour_to}')

        return tours

    def _handle_dry_run(self, tournament, tours, config):
        total_transactions_count = 0
        total_amount = Decimal('0.00')

        for tour in tours:
            if not self._is_tour_completed(tour):
                self.stdout.write(
                    self.style.WARNING(f'Тур {tour.number}: не все матчи сыграны, начисление наград будет пропущено')
                )
                continue

            description = self._build_description(tour, tournament, config['label'])
            rewards_data = config['calculate_tour_rewards'](tour, tournament)
            positive_rewards = [reward for reward in rewards_data['user_rewards'] if reward['reward_amount'] > 0]
            tour_total_amount = sum((reward['reward_amount'] for reward in positive_rewards), Decimal('0.00'))

            total_transactions_count += len(positive_rewards)
            total_amount += tour_total_amount

            self.stdout.write(
                f'Тур {tour.number}: транзакций={len(positive_rewards)}, сумма={tour_total_amount}, '
                f'описание="{description}"'
            )

        self.stdout.write('')
        self.stdout.write(self.style.WARNING(f'[DRY RUN] Найдено транзакций: {total_transactions_count}'))
        self.stdout.write(self.style.WARNING(f'[DRY RUN] Общая сумма начислений: {total_amount}'))

    def _build_description(self, tour, tournament, label):
        return f'Награды за {tour.number} тур {label} ({tournament.league.title})'

    def _is_tour_completed(self, tour):
        matches = tour.tour_matches.all()
        return matches.exists() and not matches.filter(is_played=False).exists()
