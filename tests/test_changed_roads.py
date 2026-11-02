# SPDX-License-Identifier: GPL-3.0-only
"""Old recordings may contain anchors on roads superseded by a new cycle bridge."""

import copy
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gpx_core import Point, RoadMap
from auto_alignment import automatic_alignment, ADAPTED_ROAD_WARNING


def point(x, y=0):
    return Point(50 + y / 111195, 6 + x / (111195 * math.cos(math.radians(50))), ele=x / 10)


def current_roads(height=70, forbidden=False):
    vertices = [point(0), point(60), point(200, height), point(400, height), point(540), point(600)]
    nodes = "".join(
        f'<node id="{i}" lat="{p.lat}" lon="{p.lon}"/>' for i, p in enumerate(vertices, 1)
    )
    refs = "".join(f'<nd ref="{i}"/>' for i in range(1, 7))
    access = '<tag k="bicycle" v="no"/>' if forbidden else ""
    return RoadMap(
        (
            f'<osm>{nodes}<way id="1">{refs}<tag k="highway" v="cycleway"/><tag k="bridge" v="yes"/><tag k="layer" v="1"/>{access}</way></osm>'
        ).encode()
    )


class ChangedRoads(unittest.TestCase):
    def setUp(self):
        self.source = [[point(x) for x in range(0, 601, 20)]]
        self.controls = [list(range(31))]

    def test_obsolete_points_are_replaced_by_current_connected_bridge(self):
        original = copy.deepcopy(self.source)
        out, notes, mapped, issues = automatic_alignment(
            current_roads(), self.source, self.controls, "bike", 35
        )
        self.assertEqual(issues, [])
        self.assertIn(ADAPTED_ROAD_WARNING, notes)
        self.assertTrue(any(p.lat > point(0, 60).lat for p in out[0]))
        self.assertLess(len(mapped[0]), len(self.controls[0]))
        self.assertEqual(self.source, original)
        self.assertEqual(mapped[0], sorted(set(mapped[0])))
        self.assertEqual(mapped[0][-1], len(out[0]) - 1)

    def test_manual_sections_are_never_relaxed(self):
        kept = {(0, a, a + 1) for a in range(1, 29)}
        out, notes, _, _ = automatic_alignment(
            current_roads(), self.source, self.controls, "bike", 35, kept
        )
        self.assertNotIn(ADAPTED_ROAD_WARNING, notes)
        for p in self.source[0][1:30]:
            self.assertIn(p, out[0])

    def test_far_away_replacement_is_left_for_review(self):
        _, notes, _, issues = automatic_alignment(
            current_roads(180), self.source, self.controls, "bike", 35
        )
        self.assertTrue(issues)
        self.assertNotIn(ADAPTED_ROAD_WARNING, notes)

    def test_new_bridge_does_not_override_bicycle_prohibition(self):
        out, notes, _, issues = automatic_alignment(
            current_roads(forbidden=True), self.source, self.controls, "bike", 35
        )
        self.assertEqual(out, self.source)
        self.assertTrue(issues)
        self.assertNotIn(ADAPTED_ROAD_WARNING, notes)


if __name__ == "__main__":
    unittest.main()
