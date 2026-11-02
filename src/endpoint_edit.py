# SPDX-License-Identifier: GPL-3.0-only
"""Move route termini by replacing only their short connection to the route."""

import bisect, math
from dataclasses import dataclass, replace
from gpx_core import Point, distance, cumulative, choose_anchors, replace_anchor_section


@dataclass
class EndpointChange:
    segment: int
    left: int
    right: int
    new_count: int


def connection_boundary(points, controls, at_start):
    if len(points) < 3:
        return 0 if at_start else len(points) - 1
    cum = cumulative(points)
    limit = min(200, cum[-1] * 0.1)
    if at_start:
        existing = next((i for i in controls if 0 < i < len(points) - 1), None)
        return (
            existing
            if existing is not None and cum[existing] <= limit
            else min(len(points) - 2, max(1, bisect.bisect_left(cum, limit)))
        )
    existing = next((i for i in reversed(controls) if 0 < i < len(points) - 1), None)
    return (
        existing
        if existing is not None and cum[-1] - cum[existing] <= limit
        else max(1, min(len(points) - 2, bisect.bisect_right(cum, cum[-1] - limit) - 1))
    )


def move_endpoints(
    road, segments, controls, target, position, mode, radius=35, allow_private=False
):
    if target not in ("start", "end", "both"):
        raise ValueError("Kies start, einde of beide.")
    if (
        not math.isfinite(position.lat + position.lon)
        or not -85 <= position.lat <= 85
        or not -180 <= position.lon <= 180
    ):
        raise ValueError("Ongeldige kaartpositie.")
    if not segments or any(not s for s in segments):
        raise ValueError("Geen routepunten.")
    short_segments = {si for si, s in enumerate(segments) if len(s) < 3}
    out = [list(s) for s in segments]
    anchors = [list(a) for a in controls]
    notes = []
    changes = []
    for side in ("start", "end") if target == "both" else (target,):
        first = side == "start"
        si = 0 if first else len(out) - 1
        s = out[si]
        boundary = (
            (0 if first else len(s) - 1)
            if si in short_segments
            else connection_boundary(s, anchors[si], first)
        )
        join = s[boundary]
        old = s[0 if first else -1]
        new = Point(position.lat, position.lon, old.ele, None)
        source = [new, join] if first else [join, new]
        routed, warnings = road.snap(
            [source], mode, radius, control_indices=[[0, 1]], allow_private=allow_private
        )
        line = list(routed[0])
        join_index = -1 if first else 0
        gap = distance(line[join_index], join)
        if gap > 2:
            raise ValueError(
                f"Het vaste aansluitpunt ligt {gap:.0f} meter naast het gevonden pad. Lijn eerst dit kleine aansluitstuk uit; de bestaande route is behouden."
            )
        # Exact shared junction: preserve its coordinates, height, time and GPX extensions.
        line[join_index] = join
        if si in short_segments:
            if first:
                delta = len(line) - 1
                out[si] = line + s[1:]
                anchors[si] = sorted(set([0] + [i + delta for i in anchors[si]]))
            else:
                out[si] = s[:-1] + line
                anchors[si] = sorted(set(anchors[si] + [len(out[si]) - 1]))
            left = right = boundary
        else:
            left, right = (0, boundary) if first else (boundary, len(s) - 1)
            anchors[si] = sorted(set(anchors[si] + [left, right]))
            replacement_controls = choose_anchors([line])[0]
            out, anchors = replace_anchor_section(
                out, anchors, si, left, right, line, replacement_controls
            )
        changes.append(EndpointChange(si, left, right, len(line)))
        notes.extend(warnings)
        notes.append(
            ("Startpunt" if first else "Eindpunt")
            + " verplaatst. Alleen de aansluiting is opnieuw over de wegen gelegd; de overige routepunten zijn behouden."
        )
    notes.append(
        "Bereken de tijden opnieuw. Hoogtes op de nieuwe aansluiting zijn benaderd uit de bestaande route."
    )
    return out, anchors, list(dict.fromkeys(notes)), changes


def remap_issues(issues, changes):
    result = list(issues)
    for change in changes:
        mapped = []
        a, b = change.left, change.right
        delta = change.new_count - (b - a + 1)
        for issue in result:
            if issue.segment != change.segment:
                mapped.append(issue)
                continue
            start, end = issue.start, issue.end
            if a == b:  # Extension retains every original point, including the old terminus.
                if a == 0:
                    start += delta
                    end += delta
            elif end <= a:
                pass
            elif start >= b:
                start += delta
                end += delta
            elif start < a and end > b:
                end += delta
            elif start < a:
                end = a
            elif end > b:
                start = a + change.new_count - 1
                end += delta
            else:
                continue
            if start < end:
                mapped.append(replace(issue, start=start, end=end))
        result = mapped
    return result
