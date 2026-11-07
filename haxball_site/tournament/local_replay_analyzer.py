"""Boundary adapter for the original analyzer. Never applies to replay.hax.ma payloads."""

import json
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings


def analyze_local_replay(data):
    if len(data) > 32 * 1024 * 1024 or data[:4] != b'HBR2':
        raise ValueError('Expected an HBR2 recording up to 32 MiB')
    script = Path(settings.REPLAY_ANALYZER_CLI)
    with tempfile.NamedTemporaryFile(suffix='.hbr2') as recording:
        recording.write(data)
        recording.flush()
        result = subprocess.run(
            [settings.REPLAY_ANALYZER_NODE, '--max-old-space-size=512', str(script), recording.name],
            capture_output=True,
            timeout=settings.REPLAY_ANALYZER_TIMEOUT,
            check=False,
        )
    if result.returncode:
        raise ValueError(f'Local replay analysis failed: {result.stderr.decode(errors="replace")[:1000]}')
    payload = json.loads(result.stdout)
    if payload.get('schemaVersion') != 1 or payload.get('engine') != 'haxball-replay-analyzer-poc':
        raise ValueError('Unexpected local analyzer schema/engine')
    return payload
