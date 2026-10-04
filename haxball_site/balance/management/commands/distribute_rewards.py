from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from balance.services import BalanceService
from custom_notifications.notifications import (
    get_notification_actor,
    notify_combined_rewards,
    notify_reward,
)
from fantasy_league.models import FantasyTournament
from fantasy_league.utils import calculate_tour_rewards as calculate_fantasy_tour_rewards
from predictions.models import PredictionsContestTournament
from predictions.utils import calculate_tour_rewards as calculate_predictions_tour_rewards
from tournament.models import TournamentStage, TourNumber


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
        parser.add_argument(
            '--notifications',
            nargs='+',
            choices=['per-tour', 'single', 'off'],
            default=['per-tour'],
            help=(
                'Режим уведомлений о начисленных наградах (по умолчанию per-tour): '
                'per-tour — отдельное уведомление за каждый тур, '
                'single — одно уведомление за все туры, '
                'off — без уведомлений'
            ),
        )

    def handle(self, *args, **options):
        activity = options['activity']
        league_slug = options['league_slug']
        tour_from = options['tour_from']
        tour_to = options['tour_to']
        dry_run = options['dry_run']
        send_notifications, single_notification = self._parse_notification_modes(options['notifications'])

        config = self._get_mode_config(activity)
        tournament = self._get_tournament(config['tournament_model'], league_slug, activity)
        tours = self._get_tours(tournament, tour_from, tour_to)

        if dry_run:
            self._handle_dry_run(tournament, tours, config, send_notifications, single_notification)
            return

        actor = get_notification_actor() if send_notifications else None
        # user_id -> {'user': User, 'total_amount': Decimal, 'details': [{'tour_number': int, 'amount': Decimal}]}
        combined_payouts: dict[int, dict] = {}

        created_transactions_count = 0
        distributed_tours_count = 0
        notifications_count = 0

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
            tour_payouts: list[tuple] = []

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
                    tour_payouts.append((reward['user'], amount))

            created_transactions_count += transactions_count

            if transactions_count > 0:
                distributed_tours_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Тур {tour.number}: создано {transactions_count} транзакций '
                        f'на сумму {total_amount} ("{description}")'
                    )
                )
                if send_notifications:
                    if single_notification:
                        self._accumulate_payouts(combined_payouts, tour, tour_payouts)
                    else:
                        notifications_count += self._send_tour_notifications(
                            tour, tour_payouts, tournament, config['label'], actor
                        )
            else:
                self.stdout.write(f'Тур {tour.number}: нет положительных наград для начисления ("{description}")')

        if send_notifications and single_notification and combined_payouts:
            notifications_count += self._send_combined_notifications(
                combined_payouts, tournament, config['label'], actor
            )

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Туров с начислениями: {distributed_tours_count}'))
        self.stdout.write(self.style.SUCCESS(f'Создано транзакций: {created_transactions_count}'))
        if send_notifications:
            self.stdout.write(self.style.SUCCESS(f'Отправлено уведомлений: {notifications_count}'))
        else:
            self.stdout.write('Уведомления отключены (--notifications off)')

    @staticmethod
    def _parse_notification_modes(notification_modes):
        modes = list(notification_modes or [])
        if 'off' in modes and len(modes) > 1:
            raise CommandError("Значение 'off' нельзя сочетать с другими режимами --notifications")
        if 'per-tour' in modes and 'single' in modes:
            raise CommandError("Значения 'per-tour' и 'single' взаимно исключают друг друга")
        send_notifications = 'off' not in modes
        single_notification = 'single' in modes
        return send_notifications, single_notification

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

        tours_in_range = TourNumber.objects.filter(league=tournament.league, number__gte=tour_from, number__lte=tour_to)
        playoff_numbers = list(
            tours_in_range.filter(stage__type=TournamentStage.StageType.PLAYOFF)
            .order_by('number')
            .values_list('number', flat=True)
        )
        for number in playoff_numbers:
            self.stdout.write(f'Тур {number}: этап плей-офф, начисление наград пропущено')

        tours = list(
            tours_in_range.exclude(stage__type=TournamentStage.StageType.PLAYOFF).order_by('number', 'date_from', 'id')
        )
        if not tours:
            raise CommandError(
                f'Не найдено туров для начисления в диапазоне {tour_from}-{tour_to} (туры плей-офф исключаются)'
            )

        return tours

    def _handle_dry_run(self, tournament, tours, config, send_notifications=True, single_notification=False):
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
        if send_notifications:
            if single_notification:
                self.stdout.write(self.style.WARNING('[DRY RUN] Уведомления: по одному на пользователя за все туры'))
            else:
                self.stdout.write(self.style.WARNING('[DRY RUN] Уведомления: по одному на пользователя за каждый тур'))
        else:
            self.stdout.write(self.style.WARNING('[DRY RUN] Уведомления отключены (--notifications off)'))

    @staticmethod
    def _accumulate_payouts(combined_payouts, tour, tour_payouts):
        for user, amount in tour_payouts:
            entry = combined_payouts.setdefault(user.id, {'user': user, 'total_amount': Decimal('0.00'), 'details': []})
            entry['total_amount'] += amount
            entry['details'].append({'tour_number': tour.number, 'amount': amount})

    def _send_tour_notifications(self, tour, tour_payouts, tournament, label, actor):
        count = 0
        league_title = tournament.league.title
        for user, amount in tour_payouts:
            notify_reward(
                recipient=user,
                amount=amount,
                tour_number=tour.number,
                activity_label=label,
                league_title=league_title,
                actor=actor,
            )
            count += 1
        self.stdout.write(f'Тур {tour.number}: отправлено {count} уведомлений')
        return count

    def _send_combined_notifications(self, combined_payouts, tournament, label, actor):
        count = 0
        league_title = tournament.league.title
        for entry in combined_payouts.values():
            notify_combined_rewards(
                recipient=entry['user'],
                total_amount=entry['total_amount'],
                tour_details=entry['details'],
                activity_label=label,
                league_title=league_title,
                actor=actor,
            )
            count += 1
        tour_numbers = sorted(
            {detail['tour_number'] for entry in combined_payouts.values() for detail in entry['details']}
        )
        self.stdout.write(self.style.SUCCESS(f'Отправлено {count} объединённых уведомлений за туры {tour_numbers}'))
        return count

    def _build_description(self, tour, tournament, label):
        return f'Награды за {tour.number} тур {label} ({tournament.league.title})'

    def _is_tour_completed(self, tour):
        matches = tour.tour_matches.all()
        return matches.exists() and not matches.filter(is_played=False).exists()
