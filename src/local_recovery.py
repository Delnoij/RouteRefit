# SPDX-License-Identifier: GPL-3.0-only
"""Conservative, reviewable recovery of one selected route section."""

import math
from dataclasses import dataclass
from gpx_core import AlignmentError, cumulative, distance
from routing_runtime import checkpoint


@dataclass
class RecoveryProposal:
    line: list
    radius: float
    relaxed_controls: bool
    deviation: float
    old_length: float
    new_length: float
    notes: list


def corridor_deviation(source, line):
    """Compare both polylines, sampling long edges as well as recorded points."""
    origin = source[0]
    scale = 111195 * math.cos(math.radians(origin.lat))

    def xy(p):
        return ((p.lon - origin.lon) * scale, (p.lat - origin.lat) * 111195)

    def directed(a, b):
        worst = 0
        for p, q in zip(a, a[1:]):
            steps = max(1, math.ceil(math.dist(p, q) / 10))
            for i in range(steps + 1):
                if i % 256 == 0: checkpoint()
                x = p[0] + (q[0] - p[0]) * i / steps
                y = p[1] + (q[1] - p[1]) * i / steps
                nearest = float("inf")
                for u, v in zip(b, b[1:]):
                    dx = v[0] - u[0]
                    dy = v[1] - u[1]
                    den = dx * dx + dy * dy
                    f = max(0, min(1, ((x - u[0]) * dx + (y - u[1]) * dy) / den)) if den else 0
                    nearest = min(nearest, math.hypot(x - u[0] - f * dx, y - u[1] - f * dy))
                worst = max(worst, nearest)
        return worst

    a = list(map(xy, source))
    b = list(map(xy, line))
    return max(directed(a, b), directed(b, a))


def find_recovery(road, source, controls, mode, radius=35, allow_private=False):
    """Return a proposal, never modify a route or relax access permissions.

    Fixed endpoints prevent an accepted local repair from introducing a gap into
    the unchanged route. Interior controls may be omitted, with corridor and
    distance checks to reject shortcuts and large detours.
    """
    if len(source) < 2:
        raise ValueError("Kies een stuk met twee verschillende grenspunten.")
    if not math.isfinite(radius) or not 5 <= radius <= 150:
        raise ValueError("Gebruik een zoekafstand van 5–150 meter.")
    old = cumulative(source)[-1]
    if old <= 0:
        raise ValueError("Het gekozen stuk heeft geen lengte.")
    if old > 5000:
        raise ValueError("Kies voor plaatselijk herstel een stuk van maximaal 5 km.")
    indices = sorted(set([0, len(source) - 1] + list(controls)))
    if any(type(i) is not int or not 0 <= i < len(source) for i in indices):
        raise ValueError("Ongeldige hoofdpunten.")
    boundaries = [0, len(source) - 1]
    last_reason = "Geen verbinding in het geladen wegennet."
    for search in sorted(set([radius, max(radius, 75), 150])):
        for chosen in [indices, boundaries] if indices != boundaries else [indices]:
            relaxed = chosen != indices
            try:
                out, notes = road.snap(
                    [source],
                    mode,
                    search,
                    control_indices=[chosen],
                    allow_private=allow_private,
                    endpoint_radius=2,
                )
            except AlignmentError as exc:
                last_reason = str(exc)
                continue
            line = list(out[0])
            if max(distance(source[0], line[0]), distance(source[-1], line[-1])) > 2:
                last_reason = "De grenzen van het gekozen stuk liggen naast het gevonden pad. Kies twee grenspunten op de aansluitende paden."
                continue
            line[0] = source[0]
            line[-1] = source[-1]
            new = cumulative(line)[-1]
            if not 0.5 <= new / old <= 1.8:
                last_reason = "De gevonden verbinding zou te veel afsnijden of omrijden. Kies extra hoofdpunten of een kleiner stuk."
                continue
            deviation = corridor_deviation(source, line)
            if deviation > search + 2:
                last_reason = "De gevonden verbinding wijkt te ver van de bestaande lijn af. Kies extra hoofdpunten of een kleiner stuk."
                continue
            return RecoveryProposal(line, search, relaxed, deviation, old, new, notes)
    raise ValueError(
        "Geen passend herstelvoorstel gevonden tot 150 meter.\n\n"
        + last_reason
        + "\n\nControleer de geladen uitlijngegevens, de activiteit en of de grenzen op de aansluitende paden liggen. Je kunt twee andere grenspunten kiezen, hoofdpunten verplaatsen of de bestaande lijn handmatig behouden. Privéwegen worden alleen gebruikt als je die optie zelf hebt aangezet."
    )
