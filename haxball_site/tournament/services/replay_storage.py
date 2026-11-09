"""Permanent replay archive shared by ingestion, playback and backfill."""

import hashlib

from django.core.files.base import ContentFile
from django.db import transaction

from tournament.models import ReplayRecording
from tournament.replay_stats_client import download_replay


def recording_bytes(recording):
    # Serialize first downloads without holding a match lock in playback requests.
    with transaction.atomic():
        stored = ReplayRecording.objects.select_for_update().defer('raw_response').get(pk=recording.pk)
        data = None
        if stored.replay_file:
            try:
                with stored.replay_file.open('rb') as source:
                    data = source.read(32 * 1024 * 1024 + 1)
            except FileNotFoundError:
                pass
        if data is None:
            data = download_replay(stored.replay_url)
        if not data or len(data) > 32 * 1024 * 1024:
            raise ValueError('Missing or oversized replay data')
        checksum = hashlib.sha256(data).hexdigest()
        if stored.content_sha256 and checksum != stored.content_sha256:
            raise ValueError('Recording bytes changed; review the source before remapping existing parts')
        if not stored.replay_file or not stored.replay_file.storage.exists(stored.replay_file.name):
            stored.replay_file.save(f'{stored.pk}/{checksum}.hbr2', ContentFile(data), save=False)
            stored.content_sha256 = checksum
            stored.save(update_fields=['replay_file', 'content_sha256'])
        recording.replay_file = stored.replay_file.name
        recording.content_sha256 = checksum
        return data
