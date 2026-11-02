# SPDX-License-Identifier: GPL-3.0-only
"""Reviewable connections across recording gaps; never infer a recorded journey."""

import math
import copy
from dataclasses import dataclass, replace
from datetime import timedelta
from gpx_core import Point, AlignmentError, cumulative, distance, choose_anchors


@dataclass
class JoinProposal:
    line: list
    via: list
    length: float
    notes: list
    estimated_time: bool


def local_connection_map(road, source, radius):
    """Keep every edge that can occur within the matcher's distance bound.

    A short connection should not rebuild a graph for an entire day's ride.
    Whole intersecting ways are retained, including edges crossing the box
    without an interior node. Access and topology are unchanged.
    """
    longest = max((distance(a, b) for a, b in zip(source, source[1:])), default=0)
    margin = max(150, longest * 2.5 + 60) + 2 * radius + 20
    lat_margin = margin / 110000
    lat_bound = min(89.9, max(abs(p.lat) for p in source) + lat_margin)
    lon_margin = margin / (110000 * math.cos(math.radians(lat_bound)))
    south = min(p.lat for p in source) - lat_margin
    north = max(p.lat for p in source) + lat_margin
    west = min(p.lon for p in source) - lon_margin
    east = max(p.lon for p in source) + lon_margin
    ways = [];selected_ids=[]
    from turn_policy import way_ids
    ids = set()
    for wid,(nodes, tags) in zip(way_ids(road),road.ways):
        points = [road.nodes[n] for n in nodes if n in road.nodes]
        if not points:
            continue
        if (
            max(p.lat for p in points) < south
            or min(p.lat for p in points) > north
            or max(p.lon for p in points) < west
            or min(p.lon for p in points) > east
        ):
            continue
        ways.append((nodes, tags))
        selected_ids.append(wid)
        ids.update(nodes)
    local = copy.copy(road)
    local.ways = ways
    local._index_way_ids=selected_ids
    local.nodes = {n: road.nodes[n] for n in ids if n in road.nodes}
    local.node_tags = {n: tags for n, tags in road.node_tags.items() if n in ids}
    return local


def find_connection(
    road, left, right, mode, radius=35, via=(), allow_private=False, *, local_graph=True
):
    if not left or not right:
        raise ValueError("Geen routepunten.")
    if not math.isfinite(radius) or not 5 <= radius <= 150:
        raise ValueError("Gebruik een zoekafstand van 5–150 meter.")
    a, b = left[-1], right[0]
    via = list(via)
    controls = [a, *via, b]
    if any(
        not math.isfinite(p.lat + p.lon) or not -85 <= p.lat <= 85 or not -180 <= p.lon <= 180
        for p in controls
    ):
        raise ValueError("Ongeldige kaartpositie.")
    if len(via) > 50 or cumulative(controls)[-1] > 50_000:
        raise ValueError("Gebruik maximaal 50 tussenpunten en een verbinding van maximaal 50 km.")
    notes = []
    if not via and distance(a, b) < 2:
        line = [a, b]
    else:
        # Short approach/departure context helps select the right directed path.
        before = left[-2:-1] if len(left) > 1 and distance(left[-2], a) > 0.2 else []
        after = right[1:2] if len(right) > 1 and distance(b, right[1]) > 0.2 else []
        source = [*before, *controls, *after]
        if local_graph:
            road = local_connection_map(road, source, radius)
        try:
            out, notes, mapped = road.snap(
                [source],
                mode,
                radius,
                control_indices=[list(range(len(source)))],
                with_controls=True,
                allow_private=allow_private,
            )
        except AlignmentError as exc:
            raise ValueError(
                "Geen geschikte verbinding gevonden. Verplaats de tussenpunten naar toegankelijke wegen "
                "of haal weggegevens voor dit gat op. Er wordt geen rechte lijn door ontbrekende wegen getrokken."
            ) from exc
        indices = mapped[0]
        start, end = indices[len(before)], indices[len(before) + len(controls) - 1]
        line = list(out[0][start : end + 1])
        if not line:
            raise ValueError("Geen geschikte verbinding gevonden.")
        # Preserve ALL recorded samples. Short off-road GPS offsets remain visible
        # as explicit endpoint connections, bounded by the user's search radius.
        offset = max(distance(a, line[0]), distance(b, line[-1]))
        if offset > radius + 0.1:
            raise ValueError("De route-einden liggen te ver van de gevonden wegen.")
        while line and distance(a, line[0]) < 0.01:
            line.pop(0)
        while line and distance(b, line[-1]) < 0.01:
            line.pop()
        line = [a, *line, b]
        if offset > 2:
            notes.append(
                "De aansluiting op de opgenomen punten bevat een korte GPS-verschuiving. Controleer beide route-einden."
            )
    lengths = cumulative(line)
    total = lengths[-1]
    timed = bool(a.time and b.time and b.time > a.time)
    rebuilt = [a]
    for i, p in enumerate(line[1:-1], 1):
        fraction = lengths[i] / total if total else 0
        # No sensor/extension values are copied onto manufactured samples.
        rebuilt.append(
            Point(
                p.lat,
                p.lon,
                a.ele + (b.ele - a.ele) * fraction
                if a.ele is not None and b.ele is not None
                else None,
                a.time + (b.time - a.time) * fraction if timed else None,
            )
        )
    rebuilt.append(b)
    notes.append(
        "Verbinding gereconstrueerd; dit is geen opgenomen GPS-spoor. Controleer of dit de werkelijk gemaakte route is."
    )
    notes.append("Hoogtes op de verbinding zijn geschat uit de route-einden.")
    notes.append(
        "Tijden op de verbinding zijn geschat tussen de opnamen, inclusief eventuele pauze."
        if timed
        else "Tijden op de verbinding ontbreken; bereken zo nodig een nieuw tijdprofiel."
    )
    return JoinProposal(
        rebuilt,
        [replace(p, time=None, ele=None, element=None) for p in via],
        cumulative(rebuilt)[-1],
        list(dict.fromkeys(notes)),
        timed,
    )


def merge_connection(segments, anchors, manual_sections, index, proposal):
    """Return new state, preserving original objects and shifting protected ranges."""
    if type(index) is not int or not 0 <= index < len(segments) - 1:
        raise ValueError("Kies twee opeenvolgende routedelen.")
    left, right = segments[index : index + 2]
    if not left or not right or proposal.line[0] != left[-1] or proposal.line[-1] != right[0]:
        raise ValueError("De route-einden zijn gewijzigd. Bereken de verbinding opnieuw.")
    offset = len(left) + len(proposal.line) - 2
    joined = [*left, *proposal.line[1:-1], *right]
    out = [list(s) for s in segments]
    out[index : index + 2] = [joined]
    controls = [list(row) for row in anchors]
    extra = [len(left) - 1 + i for i in choose_anchors([proposal.line])[0]]
    extra += [
        len(left) - 1 + min(range(len(proposal.line)), key=lambda i: distance(p, proposal.line[i]))
        for p in proposal.via
    ]
    controls[index : index + 2] = [
        sorted(set([*controls[index], *extra, *(i + offset for i in controls[index + 1])]))
    ]
    protected = set()
    for key in manual_sections:
        si = key[0]
        protected.add((si if si <= index else si - 1, *key[1:]))
    return out, controls, protected


def connection_record(index, proposal):
    a, b = proposal.line[0], proposal.line[-1]
    return dict(
        kind="reconstructed_recording_gap",
        after_segment=index + 1,
        start=[a.lat, a.lon],
        end=[b.lat, b.lon],
        via=[[p.lat, p.lon] for p in proposal.via],
        metres=proposal.length,
        time_status="interpolated_including_possible_pause"
        if proposal.estimated_time
        else "missing",
        start_time=a.time.isoformat() if a.time else None,
        end_time=b.time.isoformat() if b.time else None,
        elevation_status="interpolated_from_endpoints",
        recorded=False,
    )


def average_speed(segments):
    if not segments or any(not s for s in segments):
        return None
    if any(p.time is None for s in segments for p in s):
        return None
    if any(b.time < a.time for s in segments for a, b in zip(s, s[1:])):
        return None
    seconds = sum((s[-1].time - s[0].time).total_seconds() for s in segments)
    metres = sum(cumulative(s)[-1] for s in segments)
    return metres / seconds if seconds > 0 and metres > 0 else None


def retime_at_previous_average(original, edited):
    """Make an estimated distance-based schedule at the previous mean speed.

    Recorded timestamps stay in the archived original. Stops are redistributed
    in the new schedule; this is intentionally not presented as a measured ride.
    """
    speed = average_speed(original)
    if speed is None or len(original) != len(edited):
        raise ValueError(
            "Geen betrouwbare gemiddelde snelheid beschikbaar. Controleer eerst de tijden."
        )
    if sum(cumulative(s)[-1] for s in edited if s) <= 0:
        raise ValueError("Na deze bewerking blijft geen route met lengte over.")
    result = []
    for i, segment in enumerate(edited):
        if not segment:
            raise ValueError("Geen routepunten.")
        start = (
            original[0][0].time
            if i == 0
            else result[-1][-1].time + (original[i][0].time - original[i - 1][-1].time)
        )
        lengths = cumulative(segment)
        result.append(
            [
                replace(p, time=start + timedelta(seconds=metres / speed))
                for p, metres in zip(segment, lengths)
            ]
        )
    return result
