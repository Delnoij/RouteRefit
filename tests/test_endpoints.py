# SPDX-License-Identifier: GPL-3.0-only
import unittest, sys, copy
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gpx_core import *
from endpoint_edit import *
from auto_alignment import ReviewIssue


class EndpointEditing(unittest.TestCase):
    def setUp(self):
        nodes = "".join(
            f'<node id="{i + 2}" lat="{50 + i * 0.0001}" lon="6"/>' for i in range(-10, 31)
        )
        ids = "".join(f'<nd ref="{i + 2}"/>' for i in range(-10, 31))
        self.road = RoadMap(
            f'<osm>{nodes}<way id="1">{ids}<tag k="highway" v="path"/></way></osm>'.encode()
        )
        self.s = [
            [
                Point(
                    50 + i * 0.0001,
                    6,
                    100 + i,
                    datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=i * 10),
                )
                for i in range(21)
            ]
        ]
        self.a = [[0, 5, 10, 15, 20]]

    def test_start_changes_only_short_prefix(self):
        before = copy.deepcopy(self.s)
        boundary = connection_boundary(self.s[0], self.a[0], True)
        out, anchors, _, changes = move_endpoints(
            self.road, self.s, self.a, "start", Point(49.9998, 6), "walk", 10
        )
        self.assertEqual(self.s, before)
        self.assertEqual(out[0][changes[0].new_count - 1 :], self.s[0][boundary:])
        self.assertAlmostEqual(out[0][0].lat, 49.9998)
        self.assertEqual(anchors[0][-1], len(out[0]) - 1)

    def test_end_changes_only_short_suffix(self):
        boundary = connection_boundary(self.s[0], self.a[0], False)
        out, _, _, _ = move_endpoints(
            self.road, self.s, self.a, "end", Point(50.0022, 6), "walk", 10
        )
        self.assertEqual(out[0][: boundary + 1], self.s[0][: boundary + 1])
        self.assertAlmostEqual(out[0][-1].lat, 50.0022)

    def test_both_preserve_middle_and_close_at_same_place(self):
        out, anchors, _, changes = move_endpoints(
            self.road, self.s, self.a, "both", Point(49.9998, 6), "walk", 10
        )
        self.assertAlmostEqual(out[0][0].lat, out[0][-1].lat)
        for original in self.s[0][5:16]:
            self.assertIn(original, out[0])
        self.assertEqual(anchors[0], sorted(set(anchors[0])))
        self.assertEqual(len(changes), 2)

    def test_failure_is_atomic(self):
        before = copy.deepcopy(self.s)
        with self.assertRaises(AlignmentError):
            move_endpoints(self.road, self.s, self.a, "start", Point(50, 6.1), "walk", 10)
        self.assertEqual(self.s, before)
        self.assertEqual(self.a, [[0, 5, 10, 15, 20]])

    def test_inner_segments_are_never_connected_or_changed(self):
        segments = [self.s[0][:8], self.s[0][8:13], self.s[0][13:]]
        a = [[0, 7], [0, 4], [0, 7]]
        out, _, _, _ = move_endpoints(self.road, segments, a, "both", Point(50.001, 6), "walk", 10)
        self.assertEqual(out[1], segments[1])
        self.assertEqual(len(out), 3)

    def test_two_point_route_is_retained_when_extending(self):
        s = [[self.s[0][0], self.s[0][-1]]]
        out, _, _, _ = move_endpoints(self.road, s, [[0, 1]], "both", Point(49.9998, 6), "walk", 10)
        for p in s[0]:
            self.assertIn(p, out[0])

    def test_issues_outside_changed_connection_are_reindexed(self):
        issues = [ReviewIssue(0, 5, 10, "gap"), ReviewIssue(0, 0, 2, "old gap")]
        result = remap_issues(issues, [EndpointChange(0, 0, 2, 5)])
        self.assertEqual([(p.start, p.end) for p in result], [(7, 12)])
