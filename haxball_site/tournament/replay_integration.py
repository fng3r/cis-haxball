"""Public, read-only manifests and bounded match-scoped replay downloads."""

from collections import Counter
from functools import wraps
from urllib.parse import urlparse

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import require_GET

from .models import Match, ReplayRecording
from .replay_stats_client import download_replay
from .services.local_replays import active_parts, recording_sources
from .templatetags.tournament_extras import cup_round_name, tour_name


def analyzer_cors(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        response = view(request, *args, **kwargs)
        origin = request.headers.get('Origin')
        configured_origin = urlparse(settings.REPLAY_ANALYZER_URL)
        origins = set(settings.REPLAY_ANALYZER_ORIGINS)
        if configured_origin.netloc:
            origins.add(f'{configured_origin.scheme}://{configured_origin.netloc}')
        patch_vary_headers(response, ['Origin'])
        if origin in origins:
            response['Access-Control-Allow-Origin'] = origin
        return response

    return wrapped


@analyzer_cors
@require_GET
def match_manifest(request, pk):
    match = get_object_or_404(
        Match.objects.select_related('league__championship', 'stage', 'group', 'numb_tour', 'team_home', 'team_guest'),
        pk=pk,
    )
    records = {r.source_key: r for r in match.replay_recordings.defer('raw_response').all()}
    recordings = []
    for key, _ in recording_sources(match):
        recording = records.get(key)
        if recording is None:
            return JsonResponse({'error': 'Match statistics have not been prepared yet'}, status=409)
        if recording:
            recordings.append(
                {
                    'id': recording.pk,
                    'name': f'match-{pk}-replay-{recording.pk}.hbr2',
                    'url': request.build_absolute_uri(
                        reverse('tournament:analyzer_recording', args=[pk, recording.pk])
                    ),
                    'sha256': recording.content_sha256 or None,
                }
            )
    parts = [
        {
            'id': part.pk,
            'recordingId': part.game.recording_id,
            'gameId': part.game.engine_game_id,
            'label': part.label,
            'order': part.order,
            'included': part.included,
            'redIsHome': part.red_is_home,
            'startTick': part.game.start_tick,
        }
        for part in active_parts(match)
    ]

    totals = Counter(part['label'] for part in parts if part['included'])
    seen = Counter()
    for part in parts:
        label = part['label']
        if part['included']:
            seen[label] += 1
        part['displayLabel'] = f'{label} [{seen[label]}]' if part['included'] and totals[label] > 1 else label
    stage = match.stage if match.stage_id and match.league.is_multistage_league() else None
    tour = match.numb_tour
    tour.stage = tour.stage.get_real_instance()
    tour_label = cup_round_name(tour) if tour.stage.is_playoff else tour_name(tour)
    series_context = None
    if match.series_id:
        series_matches = list(
            Match.objects.filter(series_id=match.series_id).order_by('pk').values_list('pk', flat=True)
        )
        if len(series_matches) > 1:
            series_context = {'id': match.series_id, 'matchNumber': series_matches.index(match.pk) + 1}

    if len(recordings) > 128 or len(parts) > 2048:
        return JsonResponse({'error': 'Match context exceeds the supported limit'}, status=400)

    def ref(obj, name=None):
        return {'id': obj.pk, 'name': name if name is not None else str(obj)} if obj else None

    def team(obj):
        return {
            'id': obj.pk,
            'name': obj.title,
            'shortName': obj.short_title,
            'logo': request.build_absolute_uri(obj.logo.url) if obj.logo else None,
        }

    response = JsonResponse(
        {
            'schemaVersion': 2,
            'match': {
                'id': match.pk,
                'url': request.build_absolute_uri(match.get_absolute_url()),
                'season': ref(match.league.championship),
                'league': ref(match.league, match.league.title),
                'stage': ref(stage),
                'group': ref(match.group),
                'tour': ref(tour, tour_label),
                'series': series_context,
                'date': str(match.match_date) if match.match_date else None,
                'officialScore': [match.score_home, match.score_guest],
                'isPlayed': match.is_played,
            },
            'teams': {'home': team(match.team_home), 'away': team(match.team_guest)},
            'recordings': recordings,
            'parts': parts,
        }
    )

    response['Cache-Control'] = 'no-store'
    return response


@analyzer_cors
@require_GET
def match_recording(request, pk, index):
    match = get_object_or_404(Match, pk=pk)
    keys = [key for key, _ in recording_sources(match)]
    recording = get_object_or_404(ReplayRecording, pk=index, match=match, source_key__in=keys)
    try:
        data = download_replay(recording.replay_url)
    except Exception:
        return JsonResponse({'error': 'Could not download the recording. Please retry.'}, status=502)
    response = HttpResponse(data, content_type='application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="match-{pk}-replay-{index}.hbr2"'
    response['Cache-Control'] = 'public, max-age=300'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
