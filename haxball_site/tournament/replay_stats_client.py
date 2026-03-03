"""
Client for fetching replay files and uploading them to Haxball Analyzer.

- Powtorki (replay.thehax.pl): extract replay id from URL, download .hbr2 from /<id>/download
- Haxball Analyzer (replay.hax.ma): POST /save-replay with raw bytes, poll GET /stats/<id>.json
"""

import time
from urllib.parse import parse_qs, urlparse

import requests

# Config (could be moved to Django settings)
POWTORKI_BASE = 'https://replay.thehax.pl'
SAVIOLA_BASE = 'https://hax.saviola.de'
ANALYZER_BASE = 'https://replay.hax.ma'
DOWNLOAD_TIMEOUT = 60
UPLOAD_TIMEOUT = 120
STATS_POLL_INTERVAL = 3
STATS_POLL_MAX_WAIT = 60


def is_powtorki_url(url: str) -> bool:
    """Return True if URL is a supported replay link for stats fetch."""
    return get_replay_source_and_id(url) is not None


def get_powtorki_replay_id(url: str) -> str | None:
    """
    Extract replay id from supported Powtorki URLs.
    Examples:
    - https://replay.thehax.pl/7fa610525dbe630c8bd68dd55c266b4f -> 7fa610525dbe630c8bd68dd55c266b4f
    - https://thehax.pl/forum/powtorki.php?nagranie=7fa610525dbe630c8bd68dd55c266b4f -> 7fa610525dbe630c8bd68dd55c266b4f
    """
    try:
        parsed = urlparse(url)
        host = (parsed.netloc or '').lower()

        if host == 'replay.thehax.pl':
            path = parsed.path.strip('/')
            if not path:
                return None
            # id is the first path segment (ignore e.g. /download)
            return path.split('/')[0] or None

        if host in {'thehax.pl', 'www.thehax.pl'} and parsed.path == '/forum/powtorki.php':
            nagranie = parse_qs(parsed.query).get('nagranie', [None])[0]
            return (nagranie or '').strip() or None

        # VK external redirect wrapper:
        # https://vk.com/away.php?to=<urlencoded_powtorki_url>&utf=1
        if host in {'vk.com', 'www.vk.com'} and parsed.path.startswith('/away.php'):
            target_url = parse_qs(parsed.query).get('to', [None])[0]
            if target_url and target_url != url:
                return get_powtorki_replay_id(target_url)

        return None
    except Exception:
        return None


def get_saviola_replay_id(url: str) -> str | None:
    """
    Extract replay id from supported Saviola links.
    Examples:
    - https://hax.saviola.de/r/?h=2e8852030d898e000f4ec22ede3598a5
    - https://www.haxball.com/replay?v=3#https://hax.saviola.de/r/?h=882e0d590580b32138704d5cb3f1fecf.hbr2
    """
    try:
        parsed = urlparse(url)
        host = (parsed.netloc or '').lower()

        if host in {'hax.saviola.de', 'www.hax.saviola.de'} and parsed.path == '/r/':
            replay_id = parse_qs(parsed.query).get('h', [None])[0]
            if not replay_id:
                return None
            replay_id = replay_id.strip()
            if replay_id.lower().endswith('.hbr2'):
                replay_id = replay_id[:-5]
            return replay_id or None

        if host in {'haxball.com', 'www.haxball.com'} and parsed.path == '/replay' and parsed.fragment:
            inner = parsed.fragment
            if not inner.startswith('http'):
                return None
            return get_saviola_replay_id(inner)

        return None
    except Exception:
        return None


def get_replay_source_and_id(url: str) -> tuple[str, str] | None:
    """
    Return tuple (source, replay_id):
    - ('powtorki', id)
    - ('saviola', id)
    """
    replay_id = get_powtorki_replay_id(url)
    if replay_id:
        return 'powtorki', replay_id

    replay_id = get_saviola_replay_id(url)
    if replay_id:
        return 'saviola', replay_id

    return None


def download_replay(url: str) -> bytes | None:
    """
    Download .hbr2 replay from a supported source.
    Returns None for unsupported sources.
    Raises on non-200 or network error for supported sources.
    """
    source_and_id = get_replay_source_and_id(url)
    if not source_and_id:
        return None

    source, replay_id = source_and_id
    if source == 'powtorki':
        download_url = f'{POWTORKI_BASE}/{replay_id}/download'
    elif source == 'saviola':
        download_url = f'{SAVIOLA_BASE}/r/?h={replay_id}.hbr2'
    else:
        return None

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
