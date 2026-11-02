# SPDX-License-Identifier: GPL-3.0-only
"""Automatic local alignment that keeps failures visible for review."""

from dataclasses import dataclass
import bisect
from gpx_core import AlignmentError, distance
from local_recovery import corridor_deviation
from routing_runtime import checkpoint, source_lengths, route_cumulative as cumulative

ADAPTED_ROAD_WARNING = "Gewijzigde wegvakken aangepast: controleer het nieuwe verloop in de kaart."


def unwanted_loop(segments, controls, out, mapped, protected):
    """Find a new short circuit caused by forcing anchors across a junction.

    Repeated coordinates alone are not an error. Keep recorded circuits, true
    out-and-backs, explicit manual sections and separate route segments intact.
    """
    for si, line in enumerate(out):
        cum = cumulative(line)
        old_cum = cumulative(segments[si])
        seen = {}
        for end, p in enumerate(line):
            if end % 256 == 0: checkpoint()
            key = (round(p.lat, 7), round(p.lon, 7))
            start = seen.get(key)
            seen[key] = end
            if start is None or not 40 <= cum[end] - cum[start] <= 800:
                continue
            lo = max(0, bisect.bisect_right(mapped[si], start) - 1)
            hi = min(len(controls[si]) - 1, bisect.bisect_left(mapped[si], end))
            left, right = controls[si][lo], controls[si][hi]
            if any(sj == si and a < right and b > left for sj, a, b in protected):
                continue
            source = segments[si]
            recorded = False
            for a in range(left, right):
                checkpoint()
                for b in range(a + 1, right + 1):
                    along = old_cum[b] - old_cum[a]
                    gap = distance(source[a], source[b])
                    if along > 60 and gap < 25 and along > 3 * gap:
                        recorded = True
                        break
                if recorded:
                    break
            if not recorded:
                return AlignmentError(
                    "Oude tussenpunten veroorzaken een extra rondje bij een kruising. Controleer de rijrichting en fietspadzijde.",
                    si,
                    left,
                    right,
                )
    return None


def relax_changed_section(
    road, segments, controls, failure, mode, radius, protected, allow_private, adapted
):
    """Try a bounded current-road connection around obsolete intermediate anchors.

    Endpoints stay within the configured snap radius. Interior geometry may move
    at most 150 m. Manual sections, route boundaries and large detours are guarded.
    The final matcher still routes through real OSM nodes and access rules.
    """
    si = failure.segment
    source = segments[si]
    indices = controls[si]
    end = failure.end_index if failure.end_index is not None else failure.index + 1
    cum = cumulative(source)
    for margin in (60, 120, 240, 400):
        left = max((i for i in indices if cum[i] <= cum[failure.index] - margin), default=0)
        right = min(
            (i for i in indices if cum[i] >= cum[min(end, len(source) - 1)] + margin),
            default=len(source) - 1,
        )
        for sj, a, b in adapted:
            if sj == si and a <= right and b >= left:
                left, right = min(left, a), max(right, b)
        inside = [i for i in indices if left < i < right]
        if not inside or cum[right] - cum[left] > 1500:
            continue
        if any(sj == si and a < right and b > left for sj, a, b in protected):
            continue
        section = source[left : right + 1]
        from prepared_roads import recovery_endpoints_possible
        if not recovery_endpoints_possible(road, segments, section, mode, radius, allow_private):
            continue
        try:
            out, _ = road.snap(
                [section],
                mode,
                radius,
                control_indices=[[0, len(section) - 1]],
                allow_private=allow_private,
            )
        except AlignmentError:
            continue
        old_length = cumulative(section)[-1]
        new_length = cumulative(out[0])[-1]
        if not old_length or not 0.5 <= new_length / old_length <= 1.8:
            continue
        if corridor_deviation(section, out[0]) > 150:
            continue
        revised = [list(row) for row in controls]
        revised[si] = [i for i in indices if not left < i < right]
        return revised, (si, left, right)
    return None


@dataclass
class ReviewIssue:
    segment: int
    start: int
    end: int
    reason: str


def automatic_alignment(
    road, segments, controls, mode, radius=35, keep_intervals=None, allow_private=False,
    unavailable_intervals=None
):
    from prepared_roads import retain_primary_preparation, verified_road_snapshot
    checkpoint()
    if not segments or any(not row for row in segments):
        raise ValueError("Geen routepunten.")
    with verified_road_snapshot(road), source_lengths(segments), retain_primary_preparation(road, mode, allow_private, segments[0][0]):
        return _automatic_alignment(road, segments, controls, mode, radius, keep_intervals, allow_private, unavailable_intervals)


def _automatic_alignment(
    road, segments, controls, mode, radius=35, keep_intervals=None, allow_private=False,
    unavailable_intervals=None
):
    """Route the whole track, temporarily preserve failed legs, and return every issue.

    Temporary exceptions are never returned as approved manual exceptions.
    All failed coordinates and metadata stay intact until the user repairs or keeps them.
    """
    approved = set(keep_intervals or ())
    controls = [list(row) for row in controls]
    original_controls = [list(row) for row in controls]
    adapted = []
    pending = {leg: reason for leg,reason in (unavailable_intervals or {}).items() if leg not in approved}
    rejected = set(pending)
    legs = {(si, a, b) for si, indices in enumerate(controls) for a, b in zip(indices, indices[1:])}
    if not approved <= legs:
        raise ValueError("Handmatige stukken horen niet bij de hoofdpunten.")
    if not pending.keys() <= legs:
        raise ValueError('Ontbrekende weggegevens horen niet bij de hoofdpunten.')
    for attempt in range(3 * len(legs) + 1):
        checkpoint(f"Route controleren: {attempt+1}")
        try:
            out, notes, mapped = road.snap(
                segments,
                mode,
                radius,
                control_indices=controls,
                with_controls=True,
                keep_intervals=approved | pending.keys(),
                allow_private=allow_private,
            )
            invalid = []
            for si, left, right in adapted:
                row = controls[si]
                start, stop = mapped[si][row.index(left)], mapped[si][row.index(right)]
                old = segments[si][left : right + 1]
                new = out[si][start : stop + 1]
                old_length = cumulative(old)[-1]
                if (
                    len(new) < 2
                    or not old_length
                    or not 0.5 <= cumulative(new)[-1] / old_length <= 1.8
                    or corridor_deviation(old, new) > 150
                ):
                    invalid.append((si, left, right))
            if invalid:
                for si, left, right in invalid:
                    controls[si] = sorted(
                        set(controls[si] + [i for i in original_controls[si] if left < i < right])
                    )
                    for a, b in zip(controls[si], controls[si][1:]):
                        if left <= a < b <= right:
                            pending[(si, a, b)] = (
                                "Geen begrensde aanpassing aan het huidige wegennet gevonden."
                            )
                            rejected.add((si, a, b))
                    adapted.remove((si, left, right))
                continue
            loop = unwanted_loop(segments, controls, out, mapped, approved | pending.keys())
            if loop is not None:
                raise loop
            break
        except AlignmentError as exc:
            if not 0 <= exc.segment < len(controls):
                raise
            indices = controls[exc.segment]
            repair = relax_changed_section(
                road,
                segments,
                controls,
                exc,
                mode,
                radius,
                approved | rejected,
                allow_private,
                adapted,
            )
            if repair is not None:
                controls, window = repair
                si, left, right = window
                pending = {
                    leg: reason
                    for leg, reason in pending.items()
                    if leg[0] != si or leg[2] <= left or leg[1] >= right
                }
                adapted = [(sj, a, b) for sj, a, b in adapted if sj != si or b < left or a > right]
                adapted.append(window)
                continue
            end = exc.end_index if exc.end_index is not None else exc.index + 1
            affected = {
                (exc.segment, a, b)
                for a, b in zip(indices, indices[1:])
                if a < end and b > exc.index
            }
            added = affected - approved - pending.keys()
            if not added:
                raise
            for leg in added:
                pending[leg] = str(exc)
    else:
        raise ValueError("Automatische controle kon niet worden afgerond.")
    issues = []
    for (si, a, b), reason in sorted(pending.items()):
        indices = controls[si]
        start, end = mapped[si][indices.index(a)], mapped[si][indices.index(b)]
        if (
            issues
            and issues[-1].segment == si
            and issues[-1].end == start
            and issues[-1].reason == reason
        ):
            issues[-1].end = end
        else:
            issues.append(ReviewIssue(si, start, end, reason))
    # The underlying matcher calls any skipped leg manual. Only deliberate choices are manual.
    notes = [n for n in notes if not n.startswith("Handmatig behouden:")]
    if adapted:
        notes.append(ADAPTED_ROAD_WARNING)
        for si, left, right in adapted:
            cum = cumulative(segments[si])
            notes.append(
                f"Aangepast aan huidig wegennet: routedeel {si + 1}, {cum[left] / 1000:.2f}–{cum[right] / 1000:.2f} km. Oude tussenpunten losgelaten; controleer het voorstel."
            )
    for si, a, b in sorted(approved):
        cum = cumulative(segments[si])
        notes.append(
            f"Handmatig behouden: routedeel {si + 1}, {cum[a] / 1000:.2f}–{cum[b] / 1000:.2f} km."
        )
    if issues:
        notes.append(
            f"{len(issues)} stukken vragen aandacht. Daar is de bestaande lijn voorlopig behouden; ze zijn nog niet goedgekeurd."
        )
    else:
        notes.append(
            "Automatische uitlijning afgerond: geen onopgeloste uitlijnproblemen gevonden."
        )
    return out, notes, mapped, issues


def issue_controls(controls, issues):
    visible = [set() for _ in controls]
    for issue in issues:
        visible[issue.segment].update(
            i for i in controls[issue.segment] if issue.start <= i <= issue.end
        )
    return [sorted(indices) for indices in visible]
