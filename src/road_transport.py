# SPDX-License-Identifier: GPL-3.0-only
"""Bounded foreground waits for read-only map requests; one in-flight request.

The socket worker cannot touch Tk, routes or cache files. A late reply is discarded.
Even a stuck DNS lookup cannot create an unbounded number of background workers.
"""
import queue
import threading
import time
import io
from urllib.error import HTTPError
from urllib.parse import urlsplit

_slot = threading.Lock()
_cooldowns = {}
_guard = threading.Lock()


def cooldown(url, seconds=None):
    host = urlsplit(url).netloc
    with _guard:
        if seconds is not None:
            _cooldowns[host] = max(_cooldowns.get(host, 0), time.monotonic() + seconds)
        return max(0, _cooldowns.get(host, 0) - time.monotonic())


def bounded_fetch(fetch, url, budget, refresh, cancelled):
    from road_download import RoadServiceUnavailable
    budget.check(cancelled)
    if not _slot.acquire(blocking=False):
        raise RoadServiceUnavailable('De vorige wegdownload wordt nog afgerond. Je route is behouden.',reason='active')
    results = queue.Queue(maxsize=1)
    abandoned = threading.Event()
    timeout = min(budget.request_seconds, budget.remaining())
    deadline = time.monotonic() + timeout

    def work():
        try:
            raw = fetch(url, refresh=refresh, timeout=timeout, cancelled=abandoned.is_set)
            result = raw, None
        except HTTPError as exc:
            try:
                body=exc.read(2000)
                error=HTTPError(exc.url,exc.code,exc.reason,exc.headers,io.BytesIO(body))
            except Exception as error_reading_body:
                error=error_reading_body
            finally:
                exc.close()
            result = None, error
        except Exception as exc:
            result = None, exc
        finally:
            _slot.release()
        # Publish only after releasing the slot, so the next healthy tile can
        # start immediately without mistaking a completed request for an active one.
        results.put(result)

    threading.Thread(target=work, daemon=True, name='RouteRefit-wegdownload').start()
    last = 0.0
    try:
        while True:
            budget.check(cancelled)
            now = time.monotonic()
            if now >= deadline:
                # A disconnected query may still be running on the public server.
                cooldown(url, 20)
                raise RoadServiceUnavailable('De wegendienst antwoordt te traag. Je route en opgeslagen kaartvakken zijn behouden.',reason='slow',seconds=timeout)
            if budget.status and now - last >= .5:
                last = now
                budget.status(f'Wegen ophalen: {int(budget.elapsed())} s (maximaal {int(budget.seconds)} s online).')
            try:
                raw, error = results.get(timeout=min(.1, deadline-now))
            except queue.Empty:
                continue
            budget.check(cancelled)
            if error is not None:
                raise error
            return raw
    finally:
        abandoned.set()

