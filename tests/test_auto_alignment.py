# SPDX-License-Identifier: GPL-3.0-only
import unittest, sys, copy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gpx_core import *
from auto_alignment import *


class AutomaticAlignment(unittest.TestCase):
    def roads(self, private=False):
        tags = '<tag k="access" v="private"/>' if private else ""
        return RoadMap(
            (
                '<osm><node id="1" lat="50" lon="6"/><node id="2" lat="50.001" lon="6"/><node id="3" lat="50.002" lon="6"/><node id="4" lat="50.003" lon="6"/><way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="path"/>'
                + tags
                + '</way><way id="2"><nd ref="3"/><nd ref="4"/><tag k="highway" v="path"/>'
                + tags
                + "</way></osm>"
            ).encode()
        )

    def test_routes_both_sides_of_gap_and_preserves_gap(self):
        s = [
            [
                Point(50, 6.00001, 10),
                Point(50.001, 6, 11),
                Point(50.0015, 6.0001, 21),
                Point(50.002, 6, 31),
                Point(50.003, 6.00001, 40),
            ]
        ]
        before = copy.deepcopy(s)
        out, notes, controls, issues = automatic_alignment(
            self.roads(), s, [[0, 1, 3, 4]], "walk", 10
        )
        self.assertEqual(s, before)
        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertEqual(out[0][issue.start : issue.end + 1], s[0][1:4])
        self.assertAlmostEqual(out[0][0].lon, 6)
        self.assertAlmostEqual(out[0][-1].lon, 6)
        self.assertEqual(issue_controls(controls, issues), [[controls[0][1], controls[0][2]]])
        self.assertFalse(any(n.startswith("Handmatig behouden:") for n in notes))

    def test_all_unroutable_finishes_and_returns_every_leg(self):
        s = [[Point(50 + i * 0.001, 6.01, i) for i in range(5)]]
        out, _, controls, issues = automatic_alignment(
            self.roads(), s, [[0, 1, 2, 3, 4]], "walk", 10
        )
        self.assertEqual(out, s)
        self.assertEqual(len(issues), 1)
        self.assertEqual((issues[0].start, issues[0].end), (0, 4))
        self.assertEqual(controls, [[0, 1, 2, 3, 4]])

    def test_explicit_manual_choice_resolves_gap(self):
        s = [[Point(50, 6), Point(50.001, 6), Point(50.002, 6), Point(50.003, 6)]]
        _, notes, _, issues = automatic_alignment(
            self.roads(), s, [[0, 1, 2, 3]], "walk", 10, {(0, 1, 2)}
        )
        self.assertEqual(issues, [])
        self.assertTrue(any(n.startswith("Handmatig behouden:") for n in notes))

    def test_private_setting_propagates_and_segments_stay_separate(self):
        s = [[Point(50, 6), Point(50.001, 6)], [Point(50.002, 6), Point(50.003, 6)]]
        self.assertEqual(
            len(automatic_alignment(self.roads(True), s, [[0, 1], [0, 1]], "walk", 10)[3]), 2
        )
        out, _, _, issues = automatic_alignment(
            self.roads(True), s, [[0, 1], [0, 1]], "walk", 10, allow_private=True
        )
        self.assertEqual(len(out), 2)
        self.assertEqual(issues, [])

    def test_no_problem_means_no_visible_main_points(self):
        s = [[Point(50, 6.00001), Point(50.001, 6.00001)]]
        _, _, controls, issues = automatic_alignment(self.roads(), s, [[0, 1]], "walk", 10)
        self.assertEqual(issue_controls(controls, issues), [[]])
