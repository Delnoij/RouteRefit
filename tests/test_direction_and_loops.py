# SPDX-License-Identifier: GPL-3.0-only
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cycling_policy import travel_directions, heading_penalty
from gpx_core import RoadMap, Point
from auto_alignment import unwanted_loop


def p(x, y=0):
    return Point(50 + y / 111195, 6 + x / (111195 * math.cos(math.radians(50))))


class DirectionAndLoops(unittest.TestCase):
    def test_forward_reverse_and_explicit_bicycle_exception(self):
        self.assertEqual(travel_directions({"oneway": "yes"}, "bike"), (True, False))
        self.assertEqual(travel_directions({"oneway": "-1"}, "bike"), (False, True))
        self.assertEqual(
            travel_directions({"oneway": "yes", "oneway:bicycle": "no"}, "bike"), (True, True)
        )
        self.assertEqual(travel_directions({"oneway": "yes"}, "walk"), (True, True))

    def test_heading_is_not_an_access_override(self):
        self.assertEqual(travel_directions({"bicycle:forward": "no"}, "bike"), (False, True))
        self.assertEqual(heading_penalty((1, 0), (1, 0), (True, False)), 0)
        self.assertEqual(heading_penalty((1, 0), (-1, 0), (True, False)), 240)
        self.assertEqual(heading_penalty(None, (-1, 0), (True, False)), 0)

    def test_appropriate_direction_beats_closer_wrong_side_on_connected_cyclepaths(self):
        nodes = [p(-10, 0), p(-10, 300), p(10, 300), p(10, 0)]
        xml = "".join(
            f'<node id="{i}" lat="{q.lat}" lon="{q.lon}"/>' for i, q in enumerate(nodes, 1)
        )
        ways = "".join(
            f'<way id="{i}"><nd ref="{a}"/><nd ref="{b}"/><tag k="highway" v="cycleway"/><tag k="oneway" v="yes"/></way>'
            for i, (a, b) in enumerate([(1, 2), (2, 3), (3, 4), (4, 1)], 1)
        )
        out, _ = RoadMap(("<osm>" + xml + ways + "</osm>").encode()).snap(
            [[p(8, 20), p(8, 150), p(8, 280)]], "bike", 35, control_indices=[[0, 1, 2]]
        )
        self.assertTrue(all(q.lon < 6 for q in out[0]))

    def test_new_circuit_is_detected(self):
        source = [[p(0), p(60), p(120)]]
        output = [[p(0), p(40), p(60, 30), p(40, 30), p(40), p(120)]]
        self.assertIsNotNone(unwanted_loop(source, [[0, 1, 2]], output, [[0, 3, 5]], set()))

    def test_intentional_recorded_circuit_and_manual_section_are_preserved(self):
        output = [[p(0), p(40), p(60, 30), p(40, 30), p(40), p(120)]]
        self.assertIsNone(
            unwanted_loop(output, [[0, 1, 2, 3, 4, 5]], output, [[0, 1, 2, 3, 4, 5]], set())
        )
        source = [[p(0), p(60), p(120)]]
        self.assertIsNone(unwanted_loop(source, [[0, 1, 2]], output, [[0, 3, 5]], {(0, 0, 1)}))

    def test_crossing_separate_segments_never_counts_as_loop(self):
        source = [[p(0), p(100)], [p(100), p(0)]]
        self.assertIsNone(unwanted_loop(source, [[0, 1], [0, 1]], source, [[0, 1], [0, 1]], set()))


if __name__ == "__main__":
    unittest.main()
