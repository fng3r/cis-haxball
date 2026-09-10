from collections import defaultdict

from django.core.management.base import BaseCommand

from ...models import Match, MatchSeries


class Command(BaseCommand):
    help = (
        'Create MatchSeries for playoff matches and link matches to them. '
        'Run after migrating from the legacy bracket_slot-based data. '
        'Idempotent: existing series and links are kept intact.'
    )

    def handle(self, *args, **options):
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
