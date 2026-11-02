# SPDX-License-Identifier: GPL-3.0-only
"""Topology-aware matching with explicit, geometry-preserving manual exceptions."""

import math, heapq, bisect
from dataclasses import replace
from gpx_core import Point, AlignmentError, distance
from prepared_roads import prepare_roads, split_graph, cache_lock
from path_reuse import PathReuse
from activity_policy import MOTOR_MODES, motor_anchor_cost
from turn_policy import restricted_path
from routing_runtime import checkpoint, route_cumulative as cumulative
from cycling_policy import (
    cycling_anchor_cost,
    BIKE_HEADWAY_WARNING,
    heading_penalty,
    reversal_penalty,
)


def leg_key(segment, a, b):
    return (segment, round(a.lat, 8), round(a.lon, 8), round(b.lat, 8), round(b.lon, 8))


def manual_intervals(segments, controls, keys):
    kept = set()
    for si, (s, indices) in enumerate(zip(segments, controls)):
        locations = {(round(p.lat, 8), round(p.lon, 8)): [] for p in s}
        for i, p in enumerate(s):
            locations[(round(p.lat, 8), round(p.lon, 8))].append(i)
        for key in keys:
            if key[0] != si:
                continue
            starts = locations.get(tuple(key[1:3]), [])
            ends = locations.get(tuple(key[3:5]), [])
            # Repeated crossing coordinates are ambiguous: retain only a unique range.
            ranges = [(a, b) for a in starts for b in ends if a < b]
            if len(ranges) != 1:
                continue
            start, end = ranges[0]
            kept.update((si, a, b) for a, b in zip(indices, indices[1:]) if start <= a < b <= end)
    return kept


def robust_snap(
    road,
    segments,
    mode,
    radius=35,
    control_indices=None,
    with_controls=False,
    keep_intervals=None,
    allow_private=False,
    endpoint_radius=None,
):
    if not math.isfinite(radius) or not 0 < radius <= 1000:
        raise ValueError("Ongeldige zoekafstand.")
    if endpoint_radius is not None and (
        not math.isfinite(endpoint_radius) or not 0 < endpoint_radius <= radius
    ):
        raise ValueError("Ongeldige zoekafstand voor aansluitpunten.")
    keep = set(keep_intervals or ())
    warnings = []
    cycling_style = getattr(road, "cycling_style", "trekking")
    if not segments or any(not s for s in segments):
        raise ValueError("Geen routepunten.")
    origin = segments[0][0]
    scale = 111195 * math.cos(math.radians(origin.lat))
    xy = lambda p: ((p.lon - origin.lon) * scale, (p.lat - origin.lat) * 111195)
    prepared = prepare_roads(road, mode, cycling_style, allow_private, origin)
    coords = dict(prepared.coords)
    edges, edge_tags, grid = prepared.edges, prepared.tags, prepared.grid
    cell = 80
    indices_by_segment = []
    if control_indices is not None and len(control_indices) != len(segments):
        raise ValueError("De hoofdpunten horen niet bij deze routedelen.")
    for si, s in enumerate(segments):
        cum = cumulative(s)
        if control_indices is None:
            indices = [0]
            last = 0
            for i in range(1, len(s) - 1):
                if cum[i] - cum[last] >= 20:
                    indices.append(i)
                    last = i
            if len(s) > 1:
                indices.append(len(s) - 1)
        else:
            indices = list(control_indices[si])
        if (
            not indices
            or indices[0] != 0
            or indices[-1] != len(s) - 1
            or indices != sorted(set(indices))
            or any(type(i) is not int or not 0 <= i < len(s) for i in indices)
        ):
            raise ValueError("Ongeldige hoofdpunten.")
        indices_by_segment.append(indices)
    valid_legs = {
        (si, i, j)
        for si, indices in enumerate(indices_by_segment)
        for i, j in zip(indices, indices[1:])
    }
    if not keep <= valid_legs:
        raise ValueError(
            "De handmatige stukken horen niet meer bij de hoofdpunten. Kies het stuk opnieuw."
        )
    splits = {}
    rows = []
    virtual = -1
    shifts = []
    for si, (s, indices) in enumerate(zip(segments, indices_by_segment)):
        route_cum = cumulative(s)
        row = []
        for ordinal, i in enumerate(indices):
            checkpoint()
            heading = None
            if mode != "walk" and len(s) > 1:
                left = max(0, min(i - 1, bisect.bisect_left(route_cum, route_cum[i] - 35)))
                right = min(
                    len(s) - 1, max(i + 1, bisect.bisect_right(route_cum, route_cum[i] + 35) - 1)
                )
                before, at, after = xy(s[left]), xy(s[i]), xy(s[right])
                incoming = (at[0] - before[0], at[1] - before[1])
                outgoing = (after[0] - at[0], after[1] - at[1])
                # At a real hairpin, a single tangent would erase the intended turn.
                if incoming[0] * outgoing[0] + incoming[1] * outgoing[1] >= 0:
                    dx, dy = after[0] - before[0], after[1] - before[1]
                    length = math.hypot(dx, dy)
                    if length >= 10:
                        heading = (dx / length, dy / length)
            search = (
                endpoint_radius
                if endpoint_radius is not None and ordinal in (0, len(indices) - 1)
                else radius
            )
            x, y = xy(s[i])
            gx, gy = math.floor(x / cell), math.floor(y / cell)
            reach = math.ceil(search / cell)
            nearby = set(
                e
                for dx in range(-reach, reach + 1)
                for dy in range(-reach, reach + 1)
                for e in grid.get((gx + dx, gy + dy), ())
            )
            ranked = []
            for eid in nearby:
                a, b, _ = edges[eid]
                ax, ay = coords[a]
                bx, by = coords[b]
                dx = bx - ax
                dy = by - ay
                den = dx * dx + dy * dy
                if not den:
                    continue
                f = max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / den))
                gap = math.hypot(x - ax - f * dx, y - ay - f * dy)
                if gap <= search:
                    score = (
                        cycling_anchor_cost(edge_tags[eid], gap, cycling_style)
                        if mode == "bike"
                        else motor_anchor_cost(edge_tags[eid],gap) if mode in MOTOR_MODES
                        else gap * gap / 16
                    )
                    if mode != "walk":
                        score += heading_penalty(
                            heading,
                            (dx, dy),
                            prepared.directions[eid],
                        )
                    ranked.append((score, eid, f, gap))
            candidates = []
            seen_nodes = set()
            # Keep alternatives rather than committing to a driveway or parallel path.
            for score, eid, f, gap in sorted(ranked):
                a, b, _ = edges[eid]
                if f < 1e-7:
                    n = a
                elif f > 1 - 1e-7:
                    n = b
                else:
                    n = virtual
                    virtual -= 1
                    coords[n] = (
                        coords[a][0] + f * (coords[b][0] - coords[a][0]),
                        coords[a][1] + f * (coords[b][1] - coords[a][1]),
                    )
                    splits.setdefault(eid, []).append((f, n))
                if n not in seen_nodes:
                    candidates.append((n, gap, score))
                    seen_nodes.add(n)
                if len(candidates) >= 6:
                    break
            before = ordinal > 0 and (si, indices[ordinal - 1], i) in keep
            after = ordinal < len(indices) - 1 and (si, i, indices[ordinal + 1]) in keep
            exclusively_manual = (ordinal == 0 or before) and (ordinal == len(indices) - 1 or after)
            if not candidates:
                if exclusively_manual:
                    n = virtual
                    virtual -= 1
                    coords[n] = (x, y)
                    candidates = [(n, 0, 0)]
                else:
                    left = indices[max(0, ordinal - 1)]
                    right = indices[min(len(indices) - 1, ordinal + 1)]
                    raise AlignmentError(
                        f"Bij de rode markering vindt de uitlijner binnen {radius:g} meter geen geschikt pad voor deze activiteit. Dit bewijst geen fout in OSM of de GPX. Verschuif het hoofdpunt, kies een stuk om te repareren of behoud de bestaande lijn handmatig.",
                        si,
                        left,
                        right,
                    )
            row.append(candidates)
        rows.append(row)
    # Route projections form a small overlay on the reusable directed network.
    graph, busy_edges = split_graph(prepared, splits, coords)
    cache = {}
    reuse = PathReuse(prepared, splits)

    def with_arrival(answer,arrival):
        if answer is None or not prepared.turns:return answer
        ids,length,weight=answer
        following=arrival
        if len(ids)>1:
            u,v=ids[-2:]
            arc=min((arc for arc in graph.get(u,()) if arc[0]==v),key=lambda arc:arc[1]*arc[2])
            following=(arc[3],u,())
        return ids,length,weight,following

    def path(start, end, limit, arrival=None):
        key = start, end, limit, arrival if prepared.turns else None
        if key in cache:
            return cache[key]
        if prepared.turns and prepared.turns.reachable(coords,start,end,limit,arrival):
            answer=restricted_path(graph,prepared.edge_ways,prepared.turns,start,end,limit,arrival)
            cache[key]=answer
            return answer
        hit, previous_answer = reuse.lookup(start, end, limit)
        if hit:
            cache[key] = with_arrival(previous_answer,arrival)
            return cache[key]
        with cache_lock(prepared):
            prepared.stats['searches'] += 1
        dependencies = set()
        lower, upper = 0.0, float('inf')
        todo = [(0, start)]
        cost = {start: 0}
        physical = {start: 0}
        previous = {}
        visits = 0
        while todo:
            weight, u = heapq.heappop(todo)
            if weight != cost[u]:
                continue
            length = physical[u]
            if length > limit:
                break
            if u == end:
                route = [end]
                while route[-1] != start:
                    route.append(previous[route[-1]])
                answer = list(reversed(route)), length, weight
                cache[key] = with_arrival(answer,arrival)
                reuse.store(start, end, limit, answer, dependencies, lower, upper)
                return cache[key]
            visits += 1
            if visits % 256 == 0: checkpoint()
            if visits > 60000:
                break
            for v, d, factor, eid in graph.get(u, ()):
                dependencies.add(eid)
                metres = length + d
                if metres > limit:
                    upper = min(upper, metres)
                    continue
                lower = max(lower, metres)
                nd = weight + d * factor
                if nd < cost.get(v, float("inf")):
                    cost[v] = nd
                    physical[v] = metres
                    previous[v] = u
                    heapq.heappush(todo, (nd, v))
        cache[key] = None
        reuse.store(start, end, limit, None, dependencies, lower, upper)
        return None

    result = []
    used_major_road = False
    mapped_all = []
    for si, (s, indices, candidates) in enumerate(zip(segments, indices_by_segment, rows)):
        cum = cumulative(s)
        # Keep arrival direction as part of the state. A node alone cannot
        # distinguish continuing through a junction from immediately turning back.
        states = {(n, None, None): score for n, gap, score in candidates[0]}
        back = []
        for k in range(1, len(indices)):
            checkpoint(f"Route uitlijnen: {k}/{len(indices)-1}")
            i, j = indices[k - 1 : k + 1]
            span = cum[j] - cum[i]
            nxt = {}
            prevmap = {}
            for v, gap, score in candidates[k]:
                for state, old_cost in states.items():
                    u, arrived_from, arrival = state
                    answer = None if (si, i, j) in keep else path(u, v, max(150, span * 2.5 + 60),arrival)
                    if answer is None and (si, i, j) not in keep:
                        continue
                    penalty = (
                        0
                        if answer is None
                        else abs(answer[1] - span) * 0.6 + (answer[2] - answer[1]) * 0.25
                    )
                    tail = (
                        None
                        if answer is None
                        else answer[0][-2]
                        if len(answer[0]) > 1
                        else arrived_from
                    )
                    if (
                        mode != "walk"
                        and arrived_from is not None
                        and answer is not None
                        and len(answer[0]) > 1
                        and k > 1
                    ):
                        before, at, after = xy(s[indices[k - 2]]), xy(s[i]), xy(s[j])
                        here, prior, nextp = coords[u], coords[arrived_from], coords[answer[0][1]]
                        penalty += reversal_penalty(
                            (here[0] - prior[0], here[1] - prior[1]),
                            (nextp[0] - here[0], nextp[1] - here[1]),
                            (at[0] - before[0], at[1] - before[1]),
                            (after[0] - at[0], after[1] - at[1]),
                        )
                    value = old_cost + score + penalty
                    following=answer[3] if answer is not None and len(answer)>3 else None
                    target = (v, tail, following)
                    if value < nxt.get(target, float("inf")):
                        nxt[target] = value
                        prevmap[target] = state
            if not nxt:
                raise AlignmentError(
                    "De uitlijner vindt geen bruikbare verbinding tussen deze hoofdpunten. Mogelijke oorzaken zijn een verkeerd gekozen zijpad, rijrichting, toegang of ontbrekende verbindingsgegevens. Je kunt dit stuk opnieuw leggen of de bestaande lijn handmatig behouden; de rest kan daarna verder.",
                    si,
                    i,
                    j,
                )
            states = nxt
            back.append(prevmap)
        chosen = [min(states, key=states.get)]
        for previous in reversed(back):
            chosen.append(previous[chosen[-1]])
        chosen.reverse()
        chosen_states=chosen
        chosen = [state[0] for state in chosen_states]
        dst = []
        mapped = [0]
        for k, (i, j) in enumerate(zip(indices, indices[1:])):
            if (si, i, j) in keep:
                if dst:
                    dst[-1] = s[i]
                    dst.extend(s[i + 1 : j + 1])
                else:
                    dst.extend(s[i : j + 1])
                warnings.append(
                    f"Handmatig behouden: routedeel {si + 1}, {cum[i] / 1000:.2f}–{cum[j] / 1000:.2f} km. Dit stuk is niet automatisch op de kaart uitgelijnd."
                )
            else:
                answer=path(chosen[k], chosen[k + 1], max(150, (cum[j] - cum[i]) * 2.5 + 60),chosen_states[k][2])
                ids=answer[0]
                if any((a, b) in busy_edges for a, b in zip(ids, ids[1:])):
                    used_major_road = True
                line = [coords[n] for n in ids]
                if len(line) == 1:
                    line.append(line[0])
                if k and (si, indices[k - 1], i) in keep:
                    line.insert(0, xy(s[i]))
                if k + 2 < len(indices) and (si, j, indices[k + 2]) in keep:
                    line.append(xy(s[j]))
                lengths = [0.0]
                for a, b in zip(line, line[1:]):
                    lengths.append(lengths[-1] + math.dist(a, b))
                for z, (x, y) in enumerate(line):
                    if dst and z == 0:
                        continue
                    f = lengths[z] / lengths[-1] if lengths[-1] else z / max(1, len(line) - 1)
                    sourcepos = cum[i] + f * (cum[j] - cum[i])
                    ix = min(j - 1, max(i, bisect.bisect_right(cum, sourcepos) - 1))
                    fraction = (sourcepos - cum[ix]) / max(0.0001, cum[ix + 1] - cum[ix])
                    a, b = s[ix], s[ix + 1]
                    ele = (
                        a.ele + fraction * (b.ele - a.ele)
                        if a.ele is not None and b.ele is not None
                        else None
                    )
                    time = a.time + (b.time - a.time) * fraction if a.time and b.time else None
                    dst.append(Point(origin.lat + y / 111195, origin.lon + x / scale, ele, time))
                shifts.extend(
                    [
                        distance(
                            s[i],
                            Point(
                                origin.lat + coords[chosen[k]][1] / 111195,
                                origin.lon + coords[chosen[k]][0] / scale,
                            ),
                        ),
                        distance(
                            s[j],
                            Point(
                                origin.lat + coords[chosen[k + 1]][1] / 111195,
                                origin.lon + coords[chosen[k + 1]][0] / scale,
                            ),
                        ),
                    ]
                )
            mapped.append(len(dst) - 1)
        if not dst:
            dst = [s[0]]
        # Spatial interpolation cannot distinguish consecutive stationary samples.
        # Keep metadata at every source anchor, including the segment endpoints.
        for source_index, target_index in zip(indices, mapped):
            dst[target_index] = replace(
                dst[target_index], ele=s[source_index].ele, time=s[source_index].time
            )
        result.append(dst)
        mapped_all.append(mapped)
    old = sum(cumulative(s)[-1] for s in segments)
    new = sum(cumulative(s)[-1] for s in result)
    if old and abs(new / old - 1) > 0.03:
        warnings.append(
            f"Afstand verandert {100 * (new / old - 1):+.1f}%. Controleer omwegen en afgesneden lussen."
        )
    if max(shifts, default=0) > 20:
        warnings.append(
            f"Een hoofdpunt verschuift maximaal {max(shifts):.0f} meter; controleer de gekozen paden."
        )
    if prepared.turns and prepared.turns.conditional:
        warnings.append(
            "Voorwaardelijke afslagbeperkingen worden uit voorzorg altijd toegepast. Controleer tijdvensters en bebording."
        )
    if allow_private:
        warnings.append(
            "Sta privéwegen toe staat aan: de route kan wegen en paden met een privé-tag gebruiken. Dit zegt niets over jouw feitelijke toegang ter plaatse."
        )
    if used_major_road:
        warnings.append(BIKE_HEADWAY_WARNING)
    warnings.append(
        "Uitlijning is een voorstel. Hoogtes komen uit de oorspronkelijke opname; kaartcontrole bewijst geen actuele toegankelijkheid."
    )
    return (result, warnings, mapped_all) if with_controls else (result, warnings)
