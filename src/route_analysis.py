# SPDX-License-Identifier: GPL-3.0-only
"""Route statistics and elevation samples, independent of the desktop interface."""

from bisect import bisect_left
from dataclasses import dataclass
import math

from gpx_core import distance


@dataclass(frozen=True)
class RouteAnalysis:
    stats: dict
    elevation_runs: tuple
    samples: tuple
    sample_distances: tuple


def analyze_route(segments):
    """Measure each edge once without connecting segments or missing elevations."""
    kilometres = ascent = descent = seconds = 0.0
    points = elevation_count = 0
    minimum = maximum = peak = None
    valid_time = True
    runs, samples = [], []

    for segment in segments:
        previous = None
        run = []
        for point in segment:
            points += 1
            valid_time = valid_time and point.time is not None
            elevation = point.ele
            has_elevation = elevation is not None and math.isfinite(elevation)
            if previous is not None:
                metres = distance(previous, point)
                kilometres += metres / 1000
                if previous.time is not None and point.time is not None:
                    elapsed = (point.time - previous.time).total_seconds()
                    valid_time = valid_time and elapsed >= 0
                    if elapsed > 0:
                        speed = metres / elapsed * 3.6
                        peak = speed if peak is None else max(peak, speed)
                if has_elevation and previous.ele is not None and math.isfinite(previous.ele):
                    change = elevation - previous.ele
                    ascent += max(0, change)
                    descent += max(0, -change)
            if has_elevation:
                elevation_count += 1
                minimum = elevation if minimum is None else min(minimum, elevation)
                maximum = elevation if maximum is None else max(maximum, elevation)
                sample = (kilometres, elevation)
                run.append(sample)
                samples.append(sample)
            elif run:
                runs.append(tuple(run))
                run = []
            previous = point
        if run:
            runs.append(tuple(run))
        if segment and segment[0].time is not None and segment[-1].time is not None:
            seconds += (segment[-1].time - segment[0].time).total_seconds()

    valid_time = bool(points) and valid_time
    stats = dict(
        km=kilometres,
        points=points,
        segments=len(segments),
        seconds=seconds if valid_time else None,
        minimum=minimum,
        maximum=maximum,
        ascent=ascent if elevation_count else None,
        descent=descent if elevation_count else None,
        elevation_count=elevation_count,
        average=kilometres / (seconds / 3600) if valid_time and seconds else None,
        peak=peak if valid_time else None,
    )
    return RouteAnalysis(stats, tuple(runs), tuple(samples), tuple(s[0] for s in samples))


def route_statistics(segments):
    """Compatibility entry point for callers that only need the totals."""
    return analyze_route(segments).stats


def nearest_elevation(analysis, kilometres):
    """Find the nearest original sample in logarithmic time; prefer the first tie."""
    positions = analysis.sample_distances
    if not positions:
        return None
    index = bisect_left(positions, kilometres)
    if index == len(positions):
        index = bisect_left(positions, positions[-1])
    elif index and kilometres - positions[index - 1] <= positions[index] - kilometres:
        index = bisect_left(positions, positions[index - 1])
    return analysis.samples[index]


def display_samples(run, total_km, pixels):
    """Keep first/last and elevation extremes per pixel, in their original order.

    This changes drawing detail only. Statistics and hover values use every point.
    Call independently for each run so missing heights remain visible as gaps.
    """
    pixels = max(1, int(pixels))
    if len(run) <= pixels * 4:
        return run
    scale = pixels / max(total_km, 0.001)
    output, bucket = [], []
    current_column = None

    def flush():
        if bucket:
            indices = {
                0,
                len(bucket) - 1,
                min(range(len(bucket)), key=lambda i: bucket[i][1]),
                max(range(len(bucket)), key=lambda i: bucket[i][1]),
            }
            output.extend(bucket[i] for i in sorted(indices))

    for sample in run:
        column = int(sample[0] * scale)
        if current_column is not None and column != current_column:
            flush()
            bucket = []
        bucket.append(sample)
        current_column = column
    flush()
    return tuple(output)
