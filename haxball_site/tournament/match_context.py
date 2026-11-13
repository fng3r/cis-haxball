"""Public match/teams context matching the analyzer schemaVersion 2 manifest.

Only tournament models are needed; replay ingestion is deliberately independent.
Batch related counts so serializing a schedule never queries once per match.
"""

from collections import defaultdict
from copy import copy
from urllib.parse import urljoin

from django.conf import settings
from django.db.models import Count

from .models import Match, TournamentStage, TourNumber
from .templatetags.tournament_extras import round_name, tour_name


class PublicMatchContext:
    def __init__(self, matches):
        matches = list(matches)
        league_ids = {match.league_id for match in matches}
        self.stage_counts = dict(
            TournamentStage.objects.filter(league_id__in=league_ids)
            .order_by()
            .values('league_id')
            .annotate(total=Count('pk'))
            .values_list('league_id', 'total')
        )
        playoff_stage_ids = {match.numb_tour.stage_id for match in matches if match.numb_tour.stage.is_playoff}
        self.tour_counts = {
            (row['stage_id'], row['bracket']): row['total']
            for row in TourNumber.objects.filter(stage_id__in=playoff_stage_ids)
            .order_by()
            .values('stage_id', 'bracket')
            .annotate(total=Count('pk'))
        }
        series_ids = {match.series_id for match in matches if match.series_id}
        self.series_matches = defaultdict(list)
        for series_id, match_id in (
            Match.objects.filter(series_id__in=series_ids).order_by('pk').values_list('series_id', 'pk')
        ):
            self.series_matches[series_id].append(match_id)

    @staticmethod
    def absolute_url(path):
        return urljoin(settings.BASE_URL.rstrip('/') + '/', path)

    def serialize(self, match):
        def ref(obj, name=None):
            return {'id': obj.pk, 'name': name if name is not None else str(obj)} if obj else None

        def team(obj):
            return {
                'id': obj.pk,
                'name': obj.title,
                'shortName': obj.short_title,
                'logo': self.absolute_url(obj.logo.url) if obj.logo else None,
            }

        stage = match.stage if match.stage_id and self.stage_counts.get(match.league_id, 0) > 1 else None
        tour = copy(match.numb_tour)
        if tour.stage.is_playoff:
            # select_related loads the concrete playoff row without polymorphic per-row queries.
            tour.stage = tour.stage.playoffstage
            tour_label = round_name(tour, self.tour_counts.get((tour.stage_id, tour.bracket), 0))
        else:
            tour_label = tour_name(tour)
        series = self.series_matches[match.series_id]
        return {
            'match': {
                'id': match.pk,
                'url': self.absolute_url(match.get_absolute_url()),
                'season': ref(match.league.championship),
                'league': ref(match.league, match.league.title),
                'stage': ref(stage),
                'group': ref(match.group),
                'tour': ref(tour, tour_label),
                'series': {'id': match.series_id, 'matchNumber': series.index(match.pk) + 1}
                if len(series) > 1
                else None,
                'date': str(match.match_date) if match.match_date else None,
                'officialScore': [match.score_home, match.score_guest],
                'isPlayed': match.is_played,
            },
            'teams': {'home': team(match.team_home), 'away': team(match.team_guest)},
        }
