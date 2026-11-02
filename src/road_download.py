# SPDX-License-Identifier: GPL-3.0-only
"""Read-only OSM requests: stop on failure, retain cooldown for a later user action."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from dataclasses import dataclass
import math
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
DOWNLOAD_STOPPED = 'Wegdownload gestopt. Er wordt niet automatisch opnieuw geprobeerd. Je route en opgeslagen kaartvakken zijn behouden.'


class RoadServiceUnavailable(ValueError):
    """Road download unavailable; never implies that the GPX is invalid."""
    def __init__(self,message,reason='unavailable',seconds=None):
        super().__init__(message)
        self.reason=reason
        self.seconds=seconds


@dataclass
class DownloadBudget:
    requests: int = 0
    waited: int = 0
    downloaded: int = 0
    seconds: float | None = 30
    request_seconds: float = 20
    query_seconds: int = 15
    started: float | None = None
    status: object = None

    @classmethod
    def foreground(cls, status=None):
        return cls(seconds=30, status=status)

    @classmethod
    def background(cls, status=None):
        # Allow queueing + execution + transfer while the local proposal remains usable.
        return cls(seconds=60,request_seconds=45,query_seconds=25,status=status)

    def elapsed(self):
        return 0 if self.started is None else time.monotonic()-self.started

    def remaining(self):
        return float('inf') if self.seconds is None else max(0, self.seconds-self.elapsed())

    def check(self, cancelled=None):
        if cancelled and cancelled():
            from routing_runtime import RoutingCancelled
            raise RoutingCancelled('Uitlijnen gestopt.')
        if self.started is None:
            self.started=time.monotonic()
        if self.remaining() <= 0:
            raise RoadServiceUnavailable('De online wachttijd is bereikt. Je route en opgeslagen kaartvakken zijn behouden.',reason='budget',seconds=self.seconds)


def road_query_url(bounds, timeout=35):
    west, south, east, north = bounds
    box = f"{south:.7f},{west:.7f},{north:.7f},{east:.7f}"
    query = (
        f'[out:xml][timeout:{int(timeout)}][maxsize:67108864];way["highway"]({box})->.roads;'
        '(.roads;rel(bw.roads)["type"="restriction"];);(._;>;);out body;'
    )
    return OVERPASS_ENDPOINT + "?" + urlencode({"data": query})


def retry_delay(headers, reason, attempt, now=None):
    """Never shorten a server-provided wait; add one second to numeric cooldowns."""
    delays = []
    retry_after = headers.get("Retry-After") if headers is not None else None
    if retry_after:
        try:
            value = float(retry_after)
            if math.isfinite(value) and value >= 0:
                delays.append(math.ceil(value) + 1)
        except ValueError:
            try:
                deadline = parsedate_to_datetime(retry_after)
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)
                current = now or datetime.now(timezone.utc)
                delays.append(max(1, math.ceil((deadline - current).total_seconds()) + 1))
            except (ValueError, TypeError, OverflowError):
                pass
    match = re.search(r"try\s+again\s+in\s+(\d+(?:\.\d+)?)\s*seconds?", reason, re.I)
    if match:
        delays.append(math.ceil(float(match[1])) + 1)
    return max(delays) if delays else min(120, 20 * 2**attempt)


def fetch_road_data(fetch, url, refresh=False, waiting=None, budget=None, cancelled=None, allow_split=False):
    """One request only, on every UI path. Compatibility callbacks never schedule retries."""
    from road_transport import bounded_fetch, cooldown
    budget = budget if budget is not None else DownloadBudget()
    if budget.seconds is None:budget.seconds=30
    budget.check(cancelled)
    if cooldown(url)>0:
        raise RoadServiceUnavailable(DOWNLOAD_STOPPED,reason='cooldown')
    if budget.requests>=400:
        raise RoadServiceUnavailable(DOWNLOAD_STOPPED,reason='limit')
    budget.requests+=1
    request_limit=min(budget.request_seconds,budget.remaining())
    try:
        raw=bounded_fetch(fetch,url,budget,refresh,cancelled)
        budget.downloaded+=len(raw)
        if budget.downloaded>128_000_000:
            raise RoadServiceUnavailable(DOWNLOAD_STOPPED,reason='limit')
        return raw
    except HTTPError as exc:
        if exc.code not in (429,502,503,504,509):raise
        reason=exc.read(2000).decode('utf-8',errors='replace')
        exc.close()
        cooldown(url,retry_delay(exc.headers,reason,0))
        raise RoadServiceUnavailable(DOWNLOAD_STOPPED,reason='rate' if exc.code in (429,509) else 'busy') from exc
    except (URLError,TimeoutError) as exc:
        cooldown(url,20)
        timed_out=isinstance(exc,TimeoutError) or isinstance(getattr(exc,'reason',None),TimeoutError)
        raise RoadServiceUnavailable(DOWNLOAD_STOPPED,reason='slow' if timed_out else 'connection',
                                     seconds=request_limit if timed_out else None) from exc
