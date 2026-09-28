from collections import defaultdict
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from ...models import Player, PlayerMatchStatistics, PlayerTransfer, Season, Team


def resolve_season(ref):
    if ref is None:
        season = Season.objects.filter(is_active=True).order_by('-number').first()
        if season is None:
            raise CommandError('No active season found. Pass a season explicitly.')
        return season

    ref = str(ref).strip()
    # Numeric ref: match id or global season number (numbers are unique across types).
    if ref.isdigit():
        season = Season.objects.filter(Q(id=int(ref)) | Q(number=int(ref))).order_by('-number').first()
        if season is None:
            raise CommandError(f'Season not found for id/number "{ref}".')
        return season

    season = Season.objects.filter(Q(short_title__iexact=ref) | Q(title__iexact=ref)).first()
    if season is not None:
        return season

    matches = list(Season.objects.filter(Q(short_title__icontains=ref) | Q(title__icontains=ref)))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        options = ', '.join(f'{s.short_title} (id={s.id}, number={s.number})' for s in matches)
        raise CommandError(f'Ambiguous season "{ref}". Matches: {options}')
    raise CommandError(f'Season "{ref}" not found. Use id, number, short_title (e.g. "ЛЧ #6") or title.')


class Command(BaseCommand):
    help = (
        'Detect players who played at least one match for a team in a season '
        'but have no incoming transfer to that team in the same season. Output is grouped by team.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'season',
            nargs='?',
            default=None,
            help='Season id, number, short_title (e.g. "ЛЧ #6") or title. Defaults to the active season.',
        )
        parser.add_argument(
            '--include-unplayed',
            action='store_true',
            help='Also count match participations from matches not marked as played.',
        )
        parser.add_argument(
            '--csv',
            action='store_true',
            help='Additionally print "team_title,username" lines suitable for generate_transfers CSV.',
        )
        parser.add_argument(
            '--create-missing',
            action='store_true',
            help='Create the missing transfers (from free agency) via bulk_create. Requires --date.',
        )
        parser.add_argument(
            '--date',
            type=str,
            default=None,
            help='Transfer date for created transfers (DD-MM-YYYY). Required with --create-missing.',
        )

    def handle(self, *args, **options):
        season = resolve_season(options['season'])
        self.stdout.write(f'Season: {season.title} ({season.short_title}, id={season.id}, number={season.number})')

        stats_qs = PlayerMatchStatistics.objects.filter(match__league__championship=season)
        if not options['include_unplayed']:
            stats_qs = stats_qs.filter(match__is_played=True)
        stats_qs = stats_qs.select_related('player', 'player__name', 'team', 'match', 'match__numb_tour')

        appearances = defaultdict(list)
        for stat in stats_qs.order_by('match__match_date', 'match_id'):
            appearances[(stat.player_id, stat.team_id)].append(stat)

        if not appearances:
            self.stdout.write('No match participations found for this season.')
            return

        incoming = set(
            PlayerTransfer.objects.filter(season_join=season)
            .exclude(to_team__isnull=True)
            .values_list('trans_player_id', 'to_team_id')
        )

        missing = {pair: stats for pair, stats in appearances.items() if pair not in incoming}

        total_pairs = len(appearances)
        self.stdout.write(
            f'Played (player, team) pairs: {total_pairs},'
            f' with incoming transfer: {total_pairs - len(missing)}, missing: {len(missing)}'
        )
        if not missing:
            self.stdout.write(self.style.SUCCESS('No missing transfers.'))
            return

        player_ids = {player_id for player_id, _ in missing}
        team_ids = {team_id for _, team_id in missing}
        players = {p.id: p for p in Player.objects.filter(id__in=player_ids).select_related('name')}
        teams = {t.id: t for t in Team.objects.filter(id__in=team_ids)}

        other_transfers = defaultdict(list)
        for tr in (
            PlayerTransfer.objects.filter(season_join=season, trans_player_id__in=player_ids)
            .exclude(to_team__isnull=True)
            .select_related('to_team')
            .order_by('date_join', 'id')
        ):
            other_transfers[tr.trans_player_id].append(tr)

        by_team = defaultdict(list)
        for (player_id, team_id), stats in missing.items():
            first = min(stats, key=lambda s: (s.match.match_date or s.match_id, s.match_id))
            opponent = None
            match = first.match
            if match.team_home_id == team_id:
                opponent = match.team_guest
            elif match.team_guest_id == team_id:
                opponent = match.team_home
            others = [tr for tr in other_transfers.get(player_id, []) if tr.to_team_id != team_id]
            by_team[team_id].append(
                {
                    'player': players.get(player_id),
                    'player_id': player_id,
                    'matches': len(stats),
                    'first_match': match,
                    'opponent': opponent,
                    'other_transfers': others,
                }
            )

        for team_id in sorted(by_team, key=lambda tid: teams[tid].title.lower()):
            team = teams[team_id]
            entries = sorted(by_team[team_id], key=lambda e: e['player'].nickname.lower() if e['player'] else '')
            self.stdout.write('')
            self.stdout.write(f'{team.title} (id={team.id}) — missing: {len(entries)}')
            for entry in entries:
                player = entry['player']
                nickname = player.nickname if player else f'<player_id={entry["player_id"]}>'
                match = entry['first_match']
                date = match.match_date.isoformat() if match.match_date else 'no date'
                tour = match.numb_tour.number if match.numb_tour_id else '?'
                opponent = f' vs {entry["opponent"].title}' if entry['opponent'] else ''
                others = ', '.join(
                    f'{tr.to_team.title} ({tr.date_join.isoformat()})' for tr in entry['other_transfers']
                )
                other_info = self.style.WARNING(f' — also transferred in season: {others}') if others else ''
                self.stdout.write(
                    f'  - {nickname} (player_id={entry["player_id"]})'
                    f' — matches: {entry["matches"]}, first: {date} (tour {tour}, match {match.id}{opponent})'
                    f'{other_info}'
                )

        self.stdout.write('')
        self.stdout.write(
            self.style.WARNING(f'Total missing: {len(missing)} (player, team) pairs across {len(by_team)} teams.')
        )

        if options['create_missing']:
            self._create_missing_transfers(season, missing, players, teams, other_transfers, options['date'])

        if options['csv']:
            self.stdout.write('')
            self.stdout.write('team,username')
            for team_id in sorted(by_team, key=lambda tid: teams[tid].title.lower()):
                for entry in sorted(
                    by_team[team_id], key=lambda e: e['player'].nickname.lower() if e['player'] else ''
                ):
                    player = entry['player']
                    if player and player.name_id:
                        self.stdout.write(f'{teams[team_id].title},{player.name.username}')

    def _create_missing_transfers(self, season, missing, players, teams, other_transfers, date_raw):
        if not date_raw:
            raise CommandError('--date (DD-MM-YYYY) is required with --create-missing.')
        try:
            transfer_date = datetime.strptime(date_raw, '%d-%m-%Y').date()
        except ValueError:
            raise CommandError(f'Invalid --date "{date_raw}". Expected format: DD-MM-YYYY.')

        skipped = []
        creatable = []
        for player_id, team_id in sorted(missing):
            others = [tr for tr in other_transfers.get(player_id, []) if tr.to_team_id != team_id]
            if others:
                player = players.get(player_id)
                nickname = player.nickname if player else f'<player_id={player_id}>'
                skipped.append((nickname, player_id, teams[team_id].title, others))
            else:
                creatable.append((player_id, team_id))

        late = []
        for (player_id, _), stats in missing.items():
            first = min(stats, key=lambda s: (s.match.match_date or transfer_date, s.match_id))
            if first.match.match_date and first.match.match_date < transfer_date:
                player = players.get(player_id)
                nickname = player.nickname if player else f'<player_id={player_id}>'
                late.append((nickname, first))
        for nickname, first in sorted(late, key=lambda item: item[0].lower()):
            self.stdout.write(
                self.style.WARNING(
                    f'  ! {nickname}: transfer date {transfer_date.isoformat()} is after '
                    f'first appearance {first.match.match_date.isoformat()} (match {first.match.id})'
                )
            )

        # Snapshot current teams: bulk_create bypasses PlayerTransfer.save(), which would
        # otherwise overwrite Player.team (current-season state) with the backfilled team.
        teams_before = {pid: player.team_id for pid, player in players.items()}

        transfers = [
            PlayerTransfer(
                trans_player=players[player_id],
                from_team=None,
                to_team=teams[team_id],
                season_join=season,
                date_join=transfer_date,
                is_technical=False,
            )
            for player_id, team_id in creatable
        ]
        with transaction.atomic():
            PlayerTransfer.objects.bulk_create(transfers)
            changed = [
                pid
                for pid in teams_before
                if Player.objects.filter(id=pid).values_list('team_id', flat=True).first() != teams_before[pid]
            ]
            if changed:
                raise CommandError(
                    f'Aborted: Player.team changed for player_ids={sorted(changed)}. Rolled back, no transfers created.'
                )

        if transfers:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Created {len(transfers)} missing transfers for {season.short_title} '
                    f'with date {transfer_date.isoformat()} (from free agency, via bulk_create).'
                )
            )
        else:
            self.stdout.write('No transfers created.')

        if skipped:
            self.stdout.write('')
            self.stdout.write(
                self.style.WARNING(
                    f'Skipped {len(skipped)}: already have in-season transfer(s) to other team(s), not created:'
                )
            )
            for nickname, player_id, team_title, others in sorted(skipped, key=lambda item: item[0].lower()):
                dests = ', '.join(f'{tr.to_team.title} ({tr.date_join.isoformat()})' for tr in others)
                self.stdout.write(
                    f'  - {nickname} (player_id={player_id}): played for {team_title}, transferred to {dests}'
                )
