# SPDX-License-Identifier: GPL-3.0-only
"""Access interpretation, separate from the unchanged road preference weights."""

from cycling_policy import RESTRICTED
from activity_policy import permission_keys, MOTOR_MODES, explicit_permission, suitable


def permission(tags, mode):
    """A more specific transport tag overrides a general access tag."""
    keys = permission_keys(mode)
    for key in keys:
        value = str(tags.get(key, "")).strip().lower()
        if value:
            return value
    return "yes"


def access_permitted(tags, mode, allow_private=False):
    value = permission(tags, mode)
    return value not in RESTRICTED or (allow_private and value == "private")


def way_permitted(tags, mode, allow_private=False):
    highway = tags.get("highway", "")
    if not highway or highway in {
        "construction", "proposed", "raceway", "bus_guideway"
    } or tags.get("area") == "yes":
        return False
    if mode not in MOTOR_MODES and (highway in ('motorway','motorway_link') or tags.get('motorroad')=='yes'):return False
    if mode in MOTOR_MODES:
        if not suitable(tags,mode):return False
        ordinary={'motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link',
                  'tertiary','tertiary_link','residential','unclassified','living_street','service','road'}
        if highway not in ordinary and not explicit_permission(tags,mode):return False
    # Missing foot/bicycle tags do not establish a prohibition. In particular,
    # cycleway=separate describes mapping, whereas bicycle=use_sidepath is access.
    return access_permitted(tags, mode, allow_private)
