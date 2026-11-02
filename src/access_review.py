# SPDX-License-Identifier: GPL-3.0-only
"""Identify access-only failures without changing the recorded line or map data."""

import copy
from gpx_core import AlignmentError
from access_policy import permission
from cycling_policy import RESTRICTED
from activity_policy import permission_keys

ACCESS_REVIEW_WARNING = "Toegangsmeldingen door gebruiker geaccepteerd; de bestaande lijn is behouden. Neem plaatselijke regels en bebording in acht."


def access_relaxed_map(road, mode):
    """Diagnostic copy: relax access tags, retain one-way rules and physical barriers."""
    result = copy.copy(road)
    keys = permission_keys(mode)

    def relax(tags):
        tags = dict(tags)
        # Do not remove an explicit permission and expose a less specific denial.
        if permission(tags, mode) in RESTRICTED:
            for key in keys:
                tags.pop(key, None)
        return tags

    result.ways = [(ids, relax(tags)) for ids, tags in road.ways]
    result.node_tags = {node: relax(tags) for node, tags in road.node_tags.items()}
    return result


def access_only_issues(road, segments, controls, issues, mode, radius, allow_private=False):
    """Only accept failures reproducibly resolved by relaxing access, not missing roads.

    Both probes use the current control points. Their output is discarded: this
    operation reviews warnings and never replaces points, elevation or timestamps.
    """
    relaxed = access_relaxed_map(road, mode)
    accepted = []
    for issue in issues:
        si, a, b = issue.segment, issue.start, issue.end
        section = segments[si][a:b + 1]
        anchors = sorted({0, b-a} | {i-a for i in controls[si] if a < i < b})
        options = dict(control_indices=[anchors], allow_private=allow_private)
        try:
            road.snap([section], mode, radius, **options)
        except AlignmentError:
            try:
                relaxed.snap([section], mode, radius, **options)
            except AlignmentError:
                continue
            accepted.append(issue)
    return accepted
