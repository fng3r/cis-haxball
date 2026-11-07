"""Same-origin, match-scoped integration; public reads follow the public match page."""

import json

from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import LocalReplayAnalysis, Match
from .replay_stats_client import download_replay
from .services.local_replays import match_recordings, match_rosters


def can_map(request):
    return request.user.has_perm('tournament.change_localreplayanalysis')


@require_GET
@ensure_csrf_cookie
def match_manifest(request, pk):
    match = get_object_or_404(
        Match.objects.select_related('league__championship', 'stage', 'numb_tour', 'group', 'team_home', 'team_guest'),
        pk=pk,
    )

    rosters = match_rosters(match)
    recordings = []
    for index, url in match_recordings(match):
        analysis = match.local_replay_analyses.filter(replay_url=url).first()
        mappings = (
            {str(i): analysis.game_mapping(i) for i in range(len(analysis.result.get('games', [])))} if analysis else {}
        )
        recordings.append(
            {
                'index': index,
                'name': f'match-{pk}-{index + 1}.hbr2',
                'url': reverse('tournament:analyzer_recording', args=[pk, index]),
                'mappingUrl': reverse('tournament:analyzer_mapping', args=[pk, index]),
                'mappings': mappings,
                'sha256': analysis.content_sha256 if analysis else None,
            }
        )

    def team(obj):
        return {'id': obj.pk, 'name': obj.title, 'logo': obj.logo.url if obj.logo else None}

    def reference(obj):
        return {'id': obj.pk, 'name': str(obj)} if obj else None

    response = JsonResponse(
        {
            'schemaVersion': 1,
            'match': {
                'id': pk,
                'url': match.get_absolute_url(),
                'season': reference(match.league.championship),
                'league': reference(match.league),
                'stage': reference(match.stage),
                'group': reference(match.group),
                'tour': reference(match.numb_tour),
                'date': str(match.match_date) if match.match_date else None,
                'officialScore': [match.score_home, match.score_guest],
                'isPlayed': match.is_played,
            },
            'teams': {'home': team(match.team_home), 'away': team(match.team_guest)},
            'rosters': {key: sorted(value) for key, value in rosters.items()},
            'recordings': recordings,
            'canMap': can_map(request),
        }
    )
    response['Cache-Control'] = 'private, no-store'
    return response


@require_GET
def match_recording(request, pk, index):
    match = get_object_or_404(Match, pk=pk)
    url = dict(match_recordings(match)).get(index)
    if url is None:
        return JsonResponse({'error': 'Recording not found'}, status=404)
    try:
        data = download_replay(url)
    except Exception:
        return JsonResponse({'error': 'Could not download this recording. Please retry.'}, status=502)
    response = HttpResponse(data, content_type='application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="match-{pk}-{index + 1}.hbr2"'
    response['Cache-Control'] = 'private, max-age=300'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@require_POST
def match_mapping(request, pk, index):
    if not can_map(request):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    try:
        if len(request.body) > 1024:
            raise ValueError
        body = json.loads(request.body)
        game = body['game']
        mapping = body['redIsHome']
        if type(game) is not int or game < 0 or (mapping is not None and type(mapping) is not bool):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        return JsonResponse({'error': 'Expected game index and redIsHome boolean or null'}, status=400)
    with transaction.atomic():
        match = get_object_or_404(Match.objects.select_for_update(), pk=pk)
        url = dict(match_recordings(match)).get(index)
        analysis = get_object_or_404(LocalReplayAnalysis.objects.select_for_update(), match=match, replay_url=url)
        if game >= len(analysis.result.get('games', [])):
            return JsonResponse({'error': 'Game not found'}, status=404)
        analysis.side_overrides[str(game)] = mapping
        analysis.mapping_audit[str(game)] = {'user': request.user.pk, 'at': timezone.now().isoformat()}
        analysis.save(update_fields=['side_overrides', 'mapping_audit'])
    return JsonResponse({'redIsHome': mapping})
