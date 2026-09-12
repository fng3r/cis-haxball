from collections import defaultdict

from django.core.management.base import BaseCommand

from ...models import Match, MatchSeries


class Command(BaseCommand):
    help = (
        'Create MatchSeries for playoff matches and link matches to them. '
        'Run after migrating from the legacy bracket_slot-based data. '
        'Idempotent: existing series and links are kept intact. '
        'First fixes malformed bracket_slot=0 values before wiring matches to series.'
    )

    def handle(self, *args, **options):
        self.fix_zero_bracket_slots()

        matches = (
            Match.objects.filter(bracket_slot__gt=0, numb_tour_id__isnull=False)
            .order_by('-id')
            .only('id', 'numb_tour_id', 'bracket_slot', 'team_home_id', 'team_guest_id', 'series_id')
        )

        groups = defaultdict(list)
        for match in matches:
            key = (
                match.numb_tour_id,
                match.bracket_slot,
                frozenset((match.team_home_id, match.team_guest_id)),
            )
            groups[key].append(match)

        created = linked = skipped = 0
        existing_series = {
            (series.tour_id, series.bracket_slot): series
            for series in MatchSeries.objects.all().only('id', 'tour_id', 'bracket_slot')
        }

        for (tour_id, bracket_slot, _), grouped_matches in groups.items():
            series = existing_series.get((tour_id, bracket_slot))
            if series is None:
                first_match = grouped_matches[0]
                series = MatchSeries.objects.create(
                    tour_id=tour_id,
                    bracket_slot=bracket_slot,
                    team_home_id=first_match.team_home_id,
                    team_guest_id=first_match.team_guest_id,
                )
                existing_series[(tour_id, bracket_slot)] = series
                created += 1

            for match in grouped_matches:
                if match.series_id == series.id:
                    skipped += 1
                    continue
                Match.objects.filter(id=match.id).update(series=series)
                linked += 1

        self.stdout.write(
            self.style.SUCCESS(f'Match series: {created} created, {linked} matches linked, {skipped} already linked')
        )

    def fix_zero_bracket_slots(self):
        """Malformed bracket_slot=0 means the slot was never assigned.

        Recover the real slot from the sibling leg of the same pair within the
        same tour (playoff legs share one bracket slot).
        """
        zero_matches = list(
            Match.objects.filter(numb_tour__stage__type='PO', bracket_slot=0).only(
                'id', 'numb_tour_id', 'team_home_id', 'team_guest_id'
            )
        )
        if not zero_matches:
            self.stdout.write('No malformed bracket_slot=0 matches to fix')
            return

        by_pair = defaultdict(list)
        for match in Match.objects.filter(numb_tour__stage__type='PO').only(
            'id', 'numb_tour_id', 'bracket_slot', 'team_home_id', 'team_guest_id'
        ):
            key = (match.numb_tour_id, frozenset((match.team_home_id, match.team_guest_id)))
            by_pair[key].append(match)

        fixed = 0
        for match in zero_matches:
            key = (match.numb_tour_id, frozenset((match.team_home_id, match.team_guest_id)))
            slots = {
                sibling.bracket_slot for sibling in by_pair[key]
                if sibling.id != match.id and sibling.bracket_slot > 0
            }
            if len(slots) != 1:
                self.stderr.write(
                    self.style.WARNING(
                        f'Match {match.id} (tour {match.numb_tour_id}, '
                        f'pair {sorted(key[1])}): cannot recover slot, found {sorted(slots)}'
                    )
                )
                continue

            Match.objects.filter(id=match.id).update(bracket_slot=slots.pop())
            fixed += 1

        self.stdout.write(self.style.SUCCESS(f'Fixed {fixed} malformed bracket_slot=0 matches'))
