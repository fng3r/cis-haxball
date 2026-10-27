from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from balance.services import BalanceService
from custom_notifications.notifications import (
    get_notification_actor,
    notify_combined_match_rewards,
    notify_combined_rewards,
    notify_match_reward,
    notify_reward,
)
from fantasy_league.models import FantasyTournament
from fantasy_league.utils import calculate_tour_rewards as calculate_fantasy_tour_rewards
from predictions.models import PredictionsContestTournament
from predictions.utils import calculate_tour_rewards as calculate_predictions_tour_rewards
from tournament.models import League, Match, PlayerMatchStatistics, TourNumber


def parse_tours_spec(raw):
    """Parse '4' / '1-4' / '1,3,5-7' into a sorted set of tour numbers."""
    numbers = set()
    for part in raw.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            try:
                start_raw, end_raw = part.split('-', 1)
                start, end = int(start_raw), int(end_raw)
            except ValueError as exc:
                raise CommandError(f'Invalid tour range "{part}": expected like "1-4"') from exc
            if start > end:
                raise CommandError(f'Invalid tour range "{part}": start is greater than end')
            numbers.update(range(start, end + 1))
        else:
            try:
                numbers.add(int(part))
            except ValueError as exc:
                raise CommandError(f'Invalid tour number "{part}"') from exc
    if not numbers:
        raise CommandError('No tours specified')
    return numbers


MATCH_PARTICIPATION_REWARD = Decimal('10.00')
MATCH_WIN_BONUS = Decimal('5.00')


def calculate_match_tour_rewards(tour, league_or_tournament):
    """Calculate payouts for played matches in a tour.

    Grants MATCH_PARTICIPATION_REWARD for each played match a user took part in,
    plus MATCH_WIN_BONUS for each win. Amounts are aggregated per user within
    the tour so the command creates a single transaction per user per tour.

    Accepts either a League or a tournament object with a ``league`` attribute
    (to match the ``calculate_tour_rewards(tour, tournament)`` signature used
    by the fantasy/predictions modes).
    """
    league = getattr(league_or_tournament, 'league', league_or_tournament)

    matches = list(
        Match.objects.filter(numb_tour=tour, is_played=True).select_related(
            'team_home', 'team_guest', 'result', 'numb_tour'
        )
    )
    if not matches:
        return {'total_participants': 0, 'total_prize_pool': Decimal('0.00'), 'user_rewards': []}

    stats = (
        PlayerMatchStatistics.objects.filter(match__in=matches, league=league)
        .select_related('player__name', 'team', 'match__result')
        .order_by('match_id')
    )

    # user_id -> {'user': User, 'reward_amount': Decimal, 'matches_played': int, 'wins': int}
    payouts: dict[int, dict] = {}
    for stat in stats:
        player = stat.player
        user = getattr(player, 'name', None)
        if user is None:
            continue

        amount = MATCH_PARTICIPATION_REWARD
        wins = 0
        winner_id = getattr(getattr(stat.match, 'result', None), 'winner_id', None)
        if winner_id is not None and stat.team_id == winner_id:
            amount += MATCH_WIN_BONUS
            wins = 1

        entry = payouts.setdefault(
            user.id, {'user': user, 'reward_amount': Decimal('0.00'), 'matches_played': 0, 'wins': 0}
        )
        entry['reward_amount'] += amount
        entry['matches_played'] += 1
        entry['wins'] += wins

    user_rewards = sorted(payouts.values(), key=lambda item: item['reward_amount'], reverse=True)
    total_prize_pool = sum((item['reward_amount'] for item in user_rewards), Decimal('0.00'))

    return {
        'total_participants': len(user_rewards),
        'total_prize_pool': total_prize_pool,
        'user_rewards': user_rewards,
    }


class Command(BaseCommand):
    help = 'Начислить монеты за награды фэнтези, турнира прогнозистов или участие в матчах'

    def add_arguments(self, parser):
        parser.add_argument(
            'activity',
            choices=['fantasy', 'predictions', 'matches'],
            help='Режим начисления: fantasy, predictions или matches',
        )
        parser.add_argument('league_slug', type=str, help='Slug лиги')
        parser.add_argument(
            '--tours',
            required=True,
            help='Номера туров, например "5", "1-4" или "1,3,5-7"',
        )
        parser.add_argument(
            '--stage',
            type=int,
            default=1,
            help='Порядковый номер этапа турнира (по умолчанию 1)',
        )
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
        tour_numbers = parse_tours_spec(options['tours'])
        stage_order = options['stage']
        dry_run = options['dry_run']
        send_notifications, single_notification = self._parse_notification_modes(options['notifications'])

        config = self._get_mode_config(activity)
        tournament = self._get_tournament(config, league_slug, activity)
        league = tournament if activity == 'matches' else tournament.league
        tours = self._get_tours(league, tour_numbers, stage_order)

        if dry_run:
            self._handle_dry_run(tournament, tours, config, send_notifications, single_notification, activity)
            return

        actor = get_notification_actor() if send_notifications else None
        # user_id -> {'user': User, 'total_amount': Decimal, 'details': [{'tour_number': int, 'amount': Decimal}]}
        combined_payouts: dict[int, dict] = {}

        created_transactions_count = 0
        distributed_tours_count = 0
        notifications_count = 0

        for tour in tours:
            tour_display = self._tour_display(tour)
            if not tour.tour_matches.exists():
                self.stdout.write(f'{tour_display}: нет матчей, начисление наград пропущено')
                continue
            if not self._is_tour_completed(tour):
                self.stdout.write(
                    self.style.WARNING(f'{tour_display}: не все матчи сыграны, начисление наград пропущено')
                )
                continue

            description = self._build_description(tour, tournament, config['label'], activity)
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
                        description=self._build_description(
                            tour, tournament, config['label'], activity, matches_played=reward.get('matches_played', 1)
                        ),
                    )
                    transactions_count += 1
                    total_amount += amount
                    extra = None
                    if activity == 'matches':
                        extra = {
                            'matches_played': reward.get('matches_played', 0),
                            'wins': reward.get('wins', 0),
                        }
                    tour_payouts.append((reward['user'], amount, extra))

            created_transactions_count += transactions_count

            if transactions_count > 0:
                distributed_tours_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'{tour_display}: создано {transactions_count} транзакций '
                        f'на сумму {total_amount} ("{description}")'
                    )
                )
                if send_notifications:
                    if single_notification:
                        self._accumulate_payouts(combined_payouts, tour, tour_payouts)
                    else:
                        notifications_count += self._send_tour_notifications(
                            tour, tour_payouts, tournament, config['label'], actor, activity
                        )
            else:
                self.stdout.write(f'{tour_display}: нет положительных наград для начисления ("{description}")')

        if send_notifications and single_notification and combined_payouts:
            notifications_count += self._send_combined_notifications(
                combined_payouts, tournament, config['label'], actor, activity
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

        if activity == 'matches':
            return {
                'tournament_model': League,
                'calculate_tour_rewards': calculate_match_tour_rewards,
                'label': 'матчей',
            }

        return {
            'tournament_model': PredictionsContestTournament,
            'calculate_tour_rewards': calculate_predictions_tour_rewards,
            'label': 'турнира прогнозистов',
        }

    def _get_tournament(self, config, league_slug, activity):
        model = config['tournament_model']
        if model is League:
            try:
                return League.objects.get(slug=league_slug)
            except League.DoesNotExist as exc:
                raise CommandError(f'Лига "{league_slug}" не найдена') from exc
        try:
            return model.objects.select_related('league').get(league__slug=league_slug)
        except model.DoesNotExist as exc:
            raise CommandError(f'Турнир "{activity}" для лиги "{league_slug}" не найден') from exc

    def _get_tours(self, league, tour_numbers, stage_order):
        stage = league.stages.filter(order=stage_order).first()
        if stage is None:
            available_orders = list(league.stages.order_by('order').values_list('order', flat=True))
            raise CommandError(
                f'Этап с порядковым номером {stage_order} не найден '
                f'(доступные этапы: {available_orders or "нет этапов"})'
            )

        tours = list(
            TourNumber.objects.filter(league=league, stage__order=stage_order, number__in=tour_numbers)
            .select_related('stage')
            .order_by('number', 'date_from', 'id')
        )
        if not tours:
            raise CommandError(
                f'Не найдено туров для начисления среди {sorted(tour_numbers)} '
                f'для этапа {stage_order} ({stage.stage_name})'
            )

        found_numbers = {tour.number for tour in tours}
        missing = sorted(tour_numbers - found_numbers)
        if missing:
            self.stdout.write(
                self.style.WARNING(f'Туры не найдены на этапе {stage_order} ({stage.stage_name}): {missing}, пропущены')
            )

        return tours

    def _handle_dry_run(
        self, tournament, tours, config, send_notifications=True, single_notification=False, activity=None
    ):
        total_transactions_count = 0
        total_amount = Decimal('0.00')

        for tour in tours:
            tour_display = self._tour_display(tour)
            if not tour.tour_matches.exists():
                self.stdout.write(f'{tour_display}: нет матчей, начисление наград будет пропущено')
                continue
            if not self._is_tour_completed(tour):
                self.stdout.write(
                    self.style.WARNING(f'{tour_display}: не все матчи сыграны, начисление наград будет пропущено')
                )
                continue

            description = self._build_description(tour, tournament, config['label'], activity)
            rewards_data = config['calculate_tour_rewards'](tour, tournament)
            positive_rewards = [reward for reward in rewards_data['user_rewards'] if reward['reward_amount'] > 0]
            tour_total_amount = sum((reward['reward_amount'] for reward in positive_rewards), Decimal('0.00'))

            total_transactions_count += len(positive_rewards)
            total_amount += tour_total_amount

            self.stdout.write(
                f'{tour_display}: транзакций={len(positive_rewards)}, сумма={tour_total_amount}, '
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
        for payout in tour_payouts:
            user, amount = payout[0], payout[1]
            extra = payout[2] if len(payout) > 2 else None
            entry = combined_payouts.setdefault(user.id, {'user': user, 'total_amount': Decimal('0.00'), 'details': []})
            entry['total_amount'] += amount
            detail = {'tour_number': tour.number, 'amount': amount}
            if extra:
                detail.update(extra)
            entry['details'].append(detail)

    def _send_tour_notifications(self, tour, tour_payouts, tournament, label, actor, activity=None):
        count = 0
        league_title = self._resolve_league_title(tournament)
        for payout in tour_payouts:
            user, amount = payout[0], payout[1]
            extra = payout[2] if len(payout) > 2 else None
            if activity == 'matches':
                notify_match_reward(
                    recipient=user,
                    amount=amount,
                    tour_number=tour.number,
                    league_title=league_title,
                    matches_played=(extra or {}).get('matches_played', 0),
                    wins=(extra or {}).get('wins', 0),
                    actor=actor,
                )
            else:
                notify_reward(
                    recipient=user,
                    amount=amount,
                    tour_number=tour.number,
                    activity_label=label,
                    league_title=league_title,
                    actor=actor,
                )
            count += 1
        self.stdout.write(f'{self._tour_display(tour)}: отправлено {count} уведомлений')
        return count

    def _send_combined_notifications(self, combined_payouts, tournament, label, actor, activity=None):
        count = 0
        league_title = self._resolve_league_title(tournament)
        for entry in combined_payouts.values():
            if activity == 'matches':
                notify_combined_match_rewards(
                    recipient=entry['user'],
                    total_amount=entry['total_amount'],
                    tour_details=entry['details'],
                    league_title=league_title,
                    actor=actor,
                )
            else:
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

    def _build_description(self, tour, tournament, label, activity=None, matches_played=1):
        league_title = self._resolve_league_title(tournament)
        if activity == 'matches':
            match_label = 'матчах' if matches_played > 1 else 'матче'
            return f'Награды за участие в {match_label} {tour.number} тура ({league_title})'
        return f'Награды за {tour.number} тур {label} ({league_title})'

    @staticmethod
    def _resolve_league_title(tournament):
        league = getattr(tournament, 'league', tournament)
        return league.title if league is not None else str(tournament)

    @staticmethod
    def _tour_display(tour):
        return f'Тур {tour.number} ({tour.stage.stage_name})'

    def _is_tour_completed(self, tour):
        matches = tour.tour_matches.all()
        return matches.exists() and not matches.filter(is_played=False).exists()
