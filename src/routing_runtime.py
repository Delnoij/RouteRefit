# SPDX-License-Identifier: GPL-3.0-only
"""Cooperative stop and throttled progress, isolated per routing worker."""
from contextlib import contextmanager
from contextvars import ContextVar
import time

_runtime = ContextVar('routing_runtime', default=None)
_source_lengths = ContextVar('source_lengths', default=None)


@contextmanager
def source_lengths(segments):
    """Distances of the worker's unmodified source, for this operation only."""
    from gpx_core import cumulative
    values = {id(row): (row, tuple(cumulative(row))) for row in segments}
    token = _source_lengths.set(values)
    try:
        yield
    finally:
        _source_lengths.reset(token)


def route_cumulative(points):
    values = _source_lengths.get()
    cached = values.get(id(points)) if values is not None else None
    if cached is not None and cached[0] is points:
        return cached[1]
    from gpx_core import cumulative
    return cumulative(points)


class RoutingCancelled(ValueError):
    pass


@contextmanager
def routing_runtime(cancelled, emit):
    token = _runtime.set([cancelled, emit, 0.0])
    try:
        yield
    finally:
        _runtime.reset(token)


def checkpoint(message=None):
    state = _runtime.get()
    if state is None:
        return
    if state[0]():
        raise RoutingCancelled('Uitlijnen gestopt.')
    if message is not None:
        now = time.monotonic()
        if now - state[2] >= 0.25:
            state[2] = now
            state[1](message)
