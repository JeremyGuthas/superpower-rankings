"""One polite HTTP session for every fetch the project makes."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    # Deliberately no "br": several outlets return an empty body when brotli
    # is offered but the client cannot actually decode it.
    "Accept-Encoding": "gzip, deflate",
}

_MIN_INTERVAL = 1.5  # seconds between hits on the same host
_last_hit: dict[str, float] = {}


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


SESSION = _session()


def _throttle(url: str) -> None:
    host = url.split("/")[2]
    wait = _MIN_INTERVAL - (time.monotonic() - _last_hit.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.monotonic()


def get(url: str, *, cache_hours: float = 6.0, timeout: int = 30) -> str:
    """GET a URL as text, with a small on-disk cache."""
    CACHE_DIR.mkdir(exist_ok=True)
    key = hashlib.sha256(url.encode()).hexdigest()[:24]
    path = CACHE_DIR / f"{key}.txt"
    if cache_hours and path.exists():
        if time.time() - path.stat().st_mtime < cache_hours * 3600:
            return path.read_text(encoding="utf-8")

    _throttle(url)
    log.info("GET %s", url)
    r = SESSION.get(url, timeout=timeout)
    r.raise_for_status()
    if not r.text.strip():
        raise RuntimeError(f"empty body from {url} (status {r.status_code})")
    path.write_text(r.text, encoding="utf-8")
    return r.text


def get_json(url: str, *, cache_hours: float = 6.0, timeout: int = 30):
    return json.loads(get(url, cache_hours=cache_hours, timeout=timeout))
