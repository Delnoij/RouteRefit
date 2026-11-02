# SPDX-License-Identifier: GPL-3.0-only
import unittest, sys, copy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gpx_core import *
from routing_repair import *


class Repairs(unittest.TestCase):
    def road(self, tags):
        return RoadMap(
            (
                '<osm><node id="1" lat="50" lon="6"/><node id="2" lat="50.001" lon="6"/><way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="path"/>'
                + tags
                + "</way></osm>"
            ).encode()
        )

    def test_private_is_opt_in_and_does_not_change_tags(self):
        r = self.road('<tag k="access" v="private"/>')
        before = copy.deepcopy(r.ways)
        s = [[Point(50, 6), Point(50.001, 6)]]
        with self.assertRaises(AlignmentError):
            r.snap(s, "walk")
        out, notes = r.snap(s, "walk", allow_private=True)
        self.assertEqual(r.ways, before)
        self.assertTrue(any("privé" in n for n in notes))
        with self.assertRaises(AlignmentError):
            r.snap(s, "walk")

    def test_explicit_mode_prohibition_remains(self):
        for mode, key in [("walk", "foot"), ("bike", "bicycle")]:
            r = self.road(f'<tag k="access" v="private"/><tag k="{key}" v="no"/>')
            with self.assertRaises(AlignmentError):
                r.snap([[Point(50, 6), Point(50.001, 6)]], mode, allow_private=True)

    def test_manual_interval_preserves_geometry_and_metadata(self):
        r = self.road('<tag k="access" v="private"/>')
        s = [[Point(50, 6, 10), Point(50.0003, 6.0002, 23), Point(50.001, 6, 15)]]
        out, notes, controls = r.snap(
            s, "walk", control_indices=[[0, 2]], keep_intervals={(0, 0, 2)}, with_controls=True
        )
        self.assertEqual(out, s)
        self.assertEqual(controls, [[0, 2]])
        self.assertTrue(any("Handmatig" in n for n in notes))

    def test_connected_alternative_to_nearest_dead_end(self):
        r = RoadMap(
            b'<osm><node id="1" lat="50" lon="6"/><node id="2" lat="50.0001" lon="6"/><node id="3" lat="50" lon="6.0001"/><node id="4" lat="50.001" lon="6.0001"/><way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="path"/></way><way id="2"><nd ref="3"/><nd ref="4"/><tag k="highway" v="path"/></way></osm>'
        )
        out, _ = r.snap(
            [[Point(50, 6), Point(50.001, 6.0001)]], "walk", 35, control_indices=[[0, 1]]
        )
        self.assertAlmostEqual(out[0][0].lon, 6.0001, 6)

    def test_adding_main_point_keeps_manual_exception(self):
        s = [[Point(50, 6), Point(50.0003, 6.0002), Point(50.001, 6)]]
        key = leg_key(0, s[0][0], s[0][2])
        self.assertEqual(manual_intervals(s, [[0, 1, 2]], {key}), {(0, 0, 1), (0, 1, 2)})
