# SPDX-License-Identifier: GPL-3.0-only
"""Cycling preferences are costs, not overrides of access or direction restrictions."""

import re

BIKE_HEADWAY_WARNING = "De fietsroute volgt ook een hoofdweg. Controleer de wegkeuze en eventuele parallelle fietspaden."
RESTRICTED = {
    "no",
    "private",
    "use_sidepath",
    "dismount",
    "customers",
    "delivery",
    "agricultural",
    "forestry",
    "destination",
}


def dedicated_cycleway(tags):
    return tags.get("highway") == "cycleway" or (
        tags.get("highway") in ("path", "footway")
        and tags.get("bicycle") in ("yes", "designated", "official", "permissive")
    )


def major_road(tags):
    return tags.get("highway") in ("primary", "primary_link", "secondary", "secondary_link") or (
        not dedicated_cycleway(tags) and bool(re.match(r"^N\s*\d", tags.get("ref", "")))
    )


def quality_factor(tags, style="trekking"):
    """Known physical quality affects preference; missing tags are not proof of quality."""
    rough = tags.get("surface") in {
        "ground",
        "dirt",
        "earth",
        "mud",
        "sand",
        "grass",
        "woodchips",
        "unpaved",
    }
    factor = 1.0
    if rough:
        factor = max(factor, 1.25 if style == "mountainbike" else 1.8 if style == 'gravel' else 3.5)
    if tags.get("surface") in {"gravel", "fine_gravel", "compacted", "cobblestone", "sett"}:
        factor = max(factor, 1.1 if style in ("mountainbike",'gravel') else 1.5)
    if tags.get("smoothness") in {"bad", "very_bad", "horrible", "very_horrible", "impassable"}:
        factor = max(factor, 1.8 if style == "mountainbike" else 5.0)
    width = re.match(r"^\s*(\d+(?:[.,]\d+)?)\s*(?:m|metres|meters)?\s*$", tags.get("width", ""))
    if width and float(width[1].replace(",", ".")) < 1.2:
        factor = max(factor, 1.5 if style == "mountainbike" else 4.0)
    if tags.get("tracktype") in {"grade3", "grade4", "grade5"}:
        factor = max(factor, 1.3 if style == "mountainbike" else 3.5)
    return factor


def cycling_cost(tags, style="trekking"):
    if dedicated_cycleway(tags):
        return quality_factor(tags, style)
    if major_road(tags):
        return 2.0 * quality_factor(tags, style)
    if tags.get("highway") == "service":
        return {"driveway": 8.0, "parking_aisle": 7.0, "alley": 3.0}.get(
            tags.get("service"), 2.0
        ) * quality_factor(tags, style)
    return {
        "tertiary": 1.1,
        "tertiary_link": 1.1,
        "residential": 1.1,
        "unclassified": 1.2,
        "service": 1.3,
        "path": 1.3 if style == "mountainbike" else 1.7 if style == 'gravel' else 2.5,
        "track": 1.3 if style in ("mountainbike",'gravel') else 2.5,
        "footway": 2.5,
        "pedestrian": 3.0,
        "steps": 12.0,
    }.get(tags.get("highway"), 1.5) * quality_factor(tags, style)


def cycling_anchor_cost(tags, gap, style="trekking"):
    penalty = 0 if dedicated_cycleway(tags) else 20 if major_road(tags) else 6
    if tags.get("highway") in ("tertiary", "tertiary_link"):
        penalty = 4
    if tags.get("highway") == "service":
        penalty = {"driveway": 160, "parking_aisle": 140, "alley": 50}.get(tags.get("service"), 35)
    if tags.get("highway") in ("path", "track") and not dedicated_cycleway(tags):
        penalty = 8 if style == "mountainbike" else 18 if style == 'gravel' else 45
    return gap * gap / 16 + penalty + 20 * (quality_factor(tags, style) - 1)


def direction_permitted(tags, mode, forward, allow_private=False):
    from activity_policy import permission_keys
    suffix=":forward" if forward else ":backward"
    permission=next((tags[key+suffix] for key in permission_keys(mode) if key+suffix in tags),None)
    if allow_private and permission == "private":
        return True
    return permission not in RESTRICTED


def travel_directions(tags, mode, allow_private=False):
    """OSM forward/backward refer to way geometry, independent of compass bearing."""
    if mode == "walk":
        direction = tags.get("oneway:foot", "no")
    elif mode=='bike':
        direction = tags.get(
            "oneway:bicycle",
            tags.get("oneway", "yes" if tags.get("junction") == "roundabout" else "no"),
        )
    else:
        from activity_policy import permission_keys
        direction=next((tags['oneway:'+key] for key in permission_keys(mode) if 'oneway:'+key in tags),
                       tags.get('oneway','yes' if tags.get('junction')=='roundabout' or tags.get('highway') in ('motorway','motorway_link') else 'no'))
    direction = str(direction).strip().lower()
    return (
        direction not in ("-1", "reverse") and direction_permitted(tags, mode, True, allow_private),
        direction not in ("yes", "1", "true")
        and direction_permitted(tags, mode, False, allow_private),
    )


def heading_penalty(heading, edge, directions):
    """Prefer the parallel path carrying traffic in the recorded travel direction.

    A cost, not a permission: a changed junction may require a legitimate detour.
    True U-turns have no reliable single heading and are passed as None.
    """
    if heading is None:
        return 0.0
    import math

    length = math.hypot(*edge)
    if not length:
        return 0.0
    dot = max(-1.0, min(1.0, (heading[0] * edge[0] + heading[1] * edge[1]) / length))
    scores = []
    if directions[0]:
        scores.append(dot)
    if directions[1]:
        scores.append(-dot)
    return 120.0 * (1.0 - max(scores)) if scores else float("inf")


def reversal_penalty(incoming, outgoing, source_incoming, source_outgoing):
    """Discourage a new about-face at an anchor without removing recorded U-turns."""
    import math

    def cosine(a, b):
        length = math.hypot(*a) * math.hypot(*b)
        return (a[0] * b[0] + a[1] * b[1]) / length if length > 0.01 else None

    actual = cosine(incoming, outgoing)
    recorded = cosine(source_incoming, source_outgoing)
    if actual is None or recorded is None or recorded < -0.7 or actual >= -0.7:
        return 0.0
    return 240.0 * (-actual)
