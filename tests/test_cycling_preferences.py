# SPDX-License-Identifier: GPL-3.0-only
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gpx_core import RoadMap, Point, Track, AlignmentError, allowed, distance
from cycling_policy import BIKE_HEADWAY_WARNING


def parallel_map(path_tags="", road_tags="", path_oneway=""):
    return RoadMap(
        (
            """<osm>
    <node id="1" lat="50" lon="6"/><node id="2" lat="50.003" lon="6"/>
    <node id="3" lat="50" lon="6.00015"/><node id="4" lat="50.003" lon="6.00015"/>
    <way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="secondary"/>"""
            + road_tags
            + """</way>
    <way id="2"><nd ref="3"/><nd ref="4"/><tag k="highway" v="cycleway"/>"""
            + path_tags
            + path_oneway
            + """</way></osm>"""
        ).encode()
    )


class CyclingPreferences(unittest.TestCase):
    def setUp(self):
        self.route = [[Point(50, 6.00001), Point(50.003, 6.00001)]]

    def test_suitable_parallel_cycleway_beats_closer_provincial_road(self):
        road = parallel_map()
        out, notes = road.snap(self.route, "bike", 35, control_indices=[[0, 1]])
        self.assertTrue(all(abs(p.lon - 6.00015) < 1e-7 for p in out[0]))
        self.assertNotIn(BIKE_HEADWAY_WARNING, notes)
        self.assertAlmostEqual(self.route[0][0].lon, 6.00001)

    def test_connected_junctions_still_prefer_cycleway(self):
        raw = b"""<osm><node id="1" lat="50" lon="6"/><node id="2" lat="50.0015" lon="6"/><node id="3" lat="50.003" lon="6"/><node id="4" lat="50.0015" lon="6.00015"/>
        <way id="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/><tag k="highway" v="secondary"/></way>
        <way id="2"><nd ref="1"/><nd ref="4"/><nd ref="3"/><tag k="highway" v="cycleway"/></way></osm>"""
        out, _ = RoadMap(raw).snap(
            [[Point(50, 6), Point(50.003, 6)]], "bike", 35, control_indices=[[0, 1]]
        )
        self.assertTrue(any(p.lon > 6.0001 for p in out[0]))

    def test_forbidden_or_private_cycleway_is_not_preferred(self):
        for restriction in ('<tag k="bicycle" v="no"/>', '<tag k="access" v="private"/>'):
            out, notes = parallel_map(path_tags=restriction).snap(
                self.route, "bike", 35, control_indices=[[0, 1]]
            )
            self.assertTrue(all(abs(p.lon - 6) < 1e-7 for p in out[0]))
            self.assertIn(BIKE_HEADWAY_WARNING, notes)

    def test_oneway_cycleway_is_not_used_backwards(self):
        out, notes = parallel_map(path_oneway='<tag k="oneway" v="-1"/>').snap(
            self.route, "bike", 35, control_indices=[[0, 1]]
        )
        self.assertTrue(all(abs(p.lon - 6) < 1e-7 for p in out[0]))
        self.assertIn(BIKE_HEADWAY_WARNING, notes)

    def test_directional_bicycle_restriction_is_respected(self):
        road = parallel_map(path_tags='<tag k="bicycle:forward" v="no"/>')
        out, _ = road.snap(self.route, "bike", 35, control_indices=[[0, 1]])
        self.assertTrue(all(abs(p.lon - 6) < 1e-7 for p in out[0]))

    def test_no_preference_outside_the_search_radius(self):
        out, _ = parallel_map().snap(self.route, "bike", 5, control_indices=[[0, 1]])
        self.assertTrue(all(abs(p.lon - 6) < 1e-7 for p in out[0]))

    def test_explicit_sidepath_and_motorroad_are_not_cycling_candidates(self):
        for tags in (
            {"highway": "secondary", "bicycle": "use_sidepath"},
            {"highway": "primary", "motorroad": "yes"},
        ):
            self.assertFalse(allowed(tags, "bike"))

    def test_mapped_separate_cycleway_is_not_itself_an_access_prohibition(self):
        self.assertTrue(allowed({"highway": "secondary", "cycleway": "separate"}, "bike"))

    def test_fixed_repair_endpoints_are_not_moved_to_parallel_path(self):
        exact = [[Point(50, 6), Point(50.003, 6)]]
        out, _ = parallel_map().snap(
            exact, "bike", 35, control_indices=[[0, 1]], endpoint_radius=0.35
        )
        self.assertLess(distance(exact[0][0], out[0][0]), 0.35)
        self.assertLess(distance(exact[0][-1], out[0][-1]), 0.35)

    def test_layer_crossing_without_shared_osm_node_is_not_a_junction(self):
        for layer in ("1", "-1"):
            raw = (
                f'<osm><node id="1" lat="50" lon="6"/><node id="2" lat="50.001" lon="6"/><node id="3" lat="50.002" lon="6"/>'
                '<node id="4" lat="50.001" lon="5.999"/><node id="5" lat="50.001" lon="6"/><node id="6" lat="50.001" lon="6.001"/>'
                '<way id="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/><tag k="highway" v="cycleway"/>'
                f'<tag k="layer" v="{layer}"/><tag k="bridge" v="yes"/></way>'
                '<way id="2"><nd ref="4"/><nd ref="5"/><nd ref="6"/><tag k="highway" v="residential"/><tag k="layer" v="0"/></way></osm>'
            ).encode()
            road = RoadMap(raw)
            # Identical crossing coordinates use different OSM node IDs.
            with self.assertRaises(AlignmentError):
                road.snap(
                    [[Point(50, 6), Point(50.001, 6.001)]], "bike", 5, control_indices=[[0, 1]]
                )
            out, _ = road.snap(
                [[Point(50, 6), Point(50.002, 6)]], "bike", 5, control_indices=[[0, 1]]
            )
            self.assertTrue(all(abs(p.lon - 6) < 1e-8 for p in out[0]))

    def test_shared_node_connects_bridge_approach_across_layer_change(self):
        raw = b'<osm><node id="1" lat="50" lon="6"/><node id="2" lat="50.001" lon="6"/><node id="3" lat="50.002" lon="6"/><way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="cycleway"/><tag k="layer" v="0"/></way><way id="2"><nd ref="2"/><nd ref="3"/><tag k="highway" v="cycleway"/><tag k="bridge" v="yes"/><tag k="layer" v="1"/></way></osm>'
        out, _ = RoadMap(raw).snap(
            [[Point(50, 6), Point(50.002, 6)]], "bike", 5, control_indices=[[0, 1]]
        )
        self.assertAlmostEqual(out[0][-1].lat, 50.002)

    def test_ebike_type_is_recognized_and_ambiguous_types_are_not_guessed(self):
        def track(types):
            body = "".join(
                f'<trk><type>{kind}</type><trkseg><trkpt lat="50" lon="6"/><trkpt lat="50.001" lon="6"/></trkseg></trk>'
                for kind in types
            )
            return Track(("<gpx>" + body + "</gpx>").encode())

        self.assertEqual(track(["e_bike_fitness"]).activity_mode, "bike")
        self.assertEqual(track(["hiking"]).activity_mode, "walk")
        self.assertIsNone(track(["cycling", "hiking"]).activity_mode)
        self.assertIsNone(track(["unknown"]).activity_mode)


if __name__ == "__main__":
    unittest.main()
