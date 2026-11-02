# SPDX-License-Identifier: GPL-3.0-only
"""Arrival direction matters at anchors near junctions and roundabouts."""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gpx_core import RoadMap, Point


def p(x, y=0):
    return Point(50 + y / 111195, 6 + x / (111195 * math.cos(math.radians(50))))


def roads(nodes, ways):
    xml = "".join(f'<node id="{i}" lat="{q.lat}" lon="{q.lon}"/>' for i, q in enumerate(nodes, 1))
    for i, (ids, tags) in enumerate(ways, 1):
        xml += f'<way id="{i}">' + "".join(f'<nd ref="{n}"/>' for n in ids)
        xml += "".join(f'<tag k="{k}" v="{v}"/>' for k, v in tags.items()) + "</way>"
    return RoadMap(("<osm>" + xml + "</osm>").encode())


def junction():
    return roads(
        [p(0), p(100), p(140), p(100, 100)],
        [([1, 2, 3], {"highway": "residential"}), ([2, 4], {"highway": "residential"})],
    )


class JunctionContinuity(unittest.TestCase):
    def test_bicycle_does_not_overshoot_junction_and_immediately_turn_back(self):
        out, _ = junction().snap(
            [[p(0), p(120), p(100, 100)]], "bike", 35, control_indices=[[0, 1, 2]]
        )
        self.assertTrue(all(q.lon <= p(101).lon for q in out[0]))

    def test_walking_keeps_precise_recorded_anchor(self):
        out, _ = junction().snap(
            [[p(0), p(120), p(100, 100)]], "walk", 35, control_indices=[[0, 1, 2]]
        )
        self.assertTrue(any(q.lon >= p(119).lon for q in out[0]))

    def test_intentional_recorded_u_turn_remains(self):
        out, _ = junction().snap([[p(0), p(120), p(80)]], "bike", 35, control_indices=[[0, 1, 2]])
        self.assertTrue(any(q.lon >= p(119).lon for q in out[0]))

    def test_road_roundabout_obeys_its_implicit_oneway(self):
        road = roads(
            [p(0), p(100), p(100, 100), p(0, 100)],
            [([1, 2, 3, 4, 1], {"highway": "secondary", "junction": "roundabout"})],
        )
        out, _ = road.snap([[p(0), p(0, 100)]], "bike", 1, control_indices=[[0, 1]])
        self.assertTrue(any(q.lon > p(90).lon for q in out[0]))

    def test_separate_two_way_cyclepath_does_not_inherit_car_roundabout_direction(self):
        road = roads(
            [p(0), p(100), p(100, 100), p(0, 100)],
            [([1, 2, 3, 4, 1], {"highway": "cycleway", "oneway": "no"})],
        )
        out, _ = road.snap([[p(0), p(0, 100)]], "bike", 1, control_indices=[[0, 1]])
        self.assertTrue(all(q.lon < p(1).lon for q in out[0]))


if __name__ == "__main__":
    unittest.main()
