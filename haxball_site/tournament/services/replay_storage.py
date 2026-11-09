"""Permanent replay archive shared by ingestion, playback and backfill."""

import hashlib

from django.core.files.base import ContentFile
from django.db import connections, transaction

from tournament.models import ReplayRecording
from tournament.replay_stats_client import download_replay


def lock_archive(name, using):
    # Different recording rows can reference the same content-addressed file.
    key = int.from_bytes(hashlib.sha256(name.encode()).digest()[:8], signed=True)
    with connections[using].cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(%s)', [key])


def delete_unused_archive(storage, name, using):
    with transaction.atomic(using=using):
        lock_archive(name, using)
        if not ReplayRecording.objects.using(using).filter(replay_file=name).exists():
            storage.delete(name)


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
            field = stored._meta.get_field('replay_file')
            name = field.generate_filename(stored, f'{checksum}.hbr2')
            storage = stored.replay_file.storage
            lock_archive(name, stored._state.db)
            if storage.exists(name):
                with storage.open(name, 'rb') as source:
                    existing = source.read(32 * 1024 * 1024 + 1)
                if hashlib.sha256(existing).hexdigest() != checksum:
                    raise ValueError('Stored replay checksum does not match its filename')
                stored.replay_file.name = name
            else:
                stored.replay_file.save(f'{checksum}.hbr2', ContentFile(data), save=False)
            stored.content_sha256 = checksum
            stored.save(update_fields=['replay_file', 'content_sha256'])
        recording.replay_file = stored.replay_file.name
        recording.content_sha256 = checksum
        return data
