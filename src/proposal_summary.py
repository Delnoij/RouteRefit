# SPDX-License-Identifier: GPL-3.0-only
"""Quantify a proposal without mutating source points or bridging recording gaps."""
from gpx_core import duration
from route_analysis import analyze_route
from segment_join import average_speed


def proposal_summary(original, working, proposed, fallback_speed):
    source = analyze_route(original).stats
    before = analyze_route(working).stats
    after = analyze_route(proposed).stats
    speed = average_speed(working)
    seconds = after['seconds']
    basis = 'Tijdschema van het voorstel' if seconds is not None else 'Schatting met behoud van gemiddelde snelheid'
    if seconds is None:
        if speed is not None and speed > 0:
            seconds = after['km'] * 1000 / speed
        elif isinstance(fallback_speed, (int, float)) and 0.5 <= fallback_speed <= 160:
            seconds = after['km'] / fallback_speed * 3600
            basis = 'Schatting met ingestelde snelheid'
        else:
            basis = 'Reistijd onbekend; stel een geldige snelheid in.'
    coverage = after['elevation_count'] / after['points'] if after['points'] else 0
    return dict(km=after['km'], seconds=seconds, time_basis=basis,
                ascent=after['ascent'], elevation_coverage=coverage,
                original_delta_km=after['km']-source['km'],
                working_delta_km=after['km']-before['km'],
                geometry_changed=([[ (p.lat,p.lon) for p in s] for s in original] !=
                                  [[ (p.lat,p.lon) for p in s] for s in proposed]))


def summary_rows(summary):
    ascent = 'Onbekend' if summary['ascent'] is None else f"{summary['ascent']:.0f} m"
    if summary['ascent'] is not None and summary['elevation_coverage'] < 1:
        ascent += ' · gedeeltelijke hoogtegegevens'
    return [('Afstand', f"{summary['km']:.2f} km"),
            ('Geschatte reistijd / tijdschema', duration(summary['seconds'])),
            ('Stijging', ascent),
            ('Verschil met origineel', f"{summary['original_delta_km']:+.2f} km"),
            ('Verschil met bewerkte route', f"{summary['working_delta_km']:+.2f} km"),
            ('Lijnverloop ten opzichte van origineel', 'Gewijzigd' if summary['geometry_changed'] else 'Ongewijzigd')]
