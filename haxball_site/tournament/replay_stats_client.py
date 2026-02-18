"""
Client for fetching replay files and uploading them to Haxball Analyzer.

- Powtorki (replay.thehax.pl): extract replay id from URL, download .hbr2 from /<id>/download
- Haxball Analyzer (replay.hax.ma): POST /save-replay with raw bytes, poll GET /stats/<id>.json
"""

import time
from urllib.parse import urlparse

import requests

# Config (could be moved to Django settings)
POWTORKI_BASE = 'https://replay.thehax.pl'
ANALYZER_BASE = 'https://replay.hax.ma'
DOWNLOAD_TIMEOUT = 60
UPLOAD_TIMEOUT = 120
STATS_POLL_INTERVAL = 3
STATS_POLL_MAX_WAIT = 60


def is_powtorki_url(url: str) -> bool:
    """Return True if URL is a Powtorki replay page (replay.thehax.pl)."""
    try:
        parsed = urlparse(url)
        return parsed.netloc == 'replay.thehax.pl' and parsed.path.strip('/')
    except Exception:
        return False


def get_powtorki_replay_id(url: str) -> str | None:
    """
    Extract replay id from a Powtorki URL.
    e.g. https://replay.thehax.pl/7fa610525dbe630c8bd68dd55c266b4f -> 7fa610525dbe630c8bd68dd55c266b4f
    """
    try:
        parsed = urlparse(url)
        if parsed.netloc != 'replay.thehax.pl':
            return None
        path = parsed.path.strip('/')
        if not path:
            return None
        # id is the first path segment (ignore e.g. /download)
        return path.split('/')[0] or None
    except Exception:
        return None


def download_powtorki_replay(url: str) -> bytes:
    """
    Download .hbr2 replay from Powtorki. Raises on non-200 or network error.
    """
    replay_id = get_powtorki_replay_id(url)
    if not replay_id:
        raise ValueError(f'Not a valid Powtorki replay URL: {url}')
    download_url = f'{POWTORKI_BASE}/{replay_id}/download'
    resp = requests.get(download_url, timeout=DOWNLOAD_TIMEOUT)
    resp.raise_for_status()
    return resp.content


def upload_replay_to_analyzer(data: bytes) -> str:
    """
    Upload raw .hbr2 bytes to Haxball Analyzer. Returns the analyzer replay id (32-char hex).
    """
    url = f'{ANALYZER_BASE}/save-replay'
    resp = requests.post(url, data=data, timeout=UPLOAD_TIMEOUT)
    resp.raise_for_status()
    body = resp.json()
    replay_id = body.get('id')
    if not replay_id:
        raise ValueError(f'Analyzer response missing "id": {body}')
    return str(replay_id)


def fetch_analyzer_stats(replay_id: str) -> dict:
    """
    Poll GET /stats/<replay_id>.json until 200, then return parsed JSON.
    Extracts and returns the "stats" array from the response.
    Raises TimeoutError if not ready within STATS_POLL_MAX_WAIT seconds.
    """
    url = f'{ANALYZER_BASE}/stats/{replay_id}.json'
    deadline = time.monotonic() + STATS_POLL_MAX_WAIT
    while time.monotonic() < deadline:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('stats', [])
        if resp.status_code != 404:
            resp.raise_for_status()
        time.sleep(STATS_POLL_INTERVAL)
    raise TimeoutError(f'Stats for {replay_id} not ready within {STATS_POLL_MAX_WAIT}s')
