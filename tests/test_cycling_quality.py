# SPDX-License-Identifier: GPL-3.0-only
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cycling_policy import cycling_cost, cycling_anchor_cost, quality_factor
from gpx_core import RoadMap, Point, AlignmentError


def parallel(tags):
    return RoadMap(
        (
            """<osm><node id="1" lat="50" lon="6"/><node id="2" lat="50.003" lon="6"/>
    <node id="3" lat="50" lon="6.00015"/><node id="4" lat="50.003" lon="6.00015"/>
    <way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="secondary"/></way>
    <way id="2"><nd ref="3"/><nd ref="4"/>"""
            + tags
            + "</way></osm>"
        ).encode()
    )


class CyclingQuality(unittest.TestCase):
    def test_known_surface_width_smoothness_and_track_grade_affect_cost(self):
        for tags in (
            {"surface": "mud"},
            {"width": "0.8 m"},
            {"smoothness": "bad"},
            {"tracktype": "grade4"},
        ):
            self.assertGreater(quality_factor(tags), 1)
        self.assertEqual(quality_factor({}), 1)
        self.assertEqual(quality_factor({"width": "unknown"}), 1)
        self.assertEqual(quality_factor({"width": "2.5"}), 1)

    def test_mountainbike_keeps_a_distinct_rough_surface_preference(self):
        t = {"highway": "cycleway", "surface": "ground"}
        self.assertLess(cycling_cost(t, "mountainbike"), cycling_cost(t, "trekking"))
        r = parallel('<tag k="highway" v="cycleway"/><tag k="surface" v="ground"/>')
        route = [[Point(50, 6.00014), Point(50.003, 6.00014)]]
        r.cycling_style = "mountainbike"
        out, _ = r.snap(route, "bike", 35, control_indices=[[0, 1]])
        self.assertTrue(all(p.lon > 6.0001 for p in out[0]))

    def test_trekking_prefers_usable_road_to_narrow_or_rough_cycleway(self):
        for detail in ('<tag k="width" v="0.7"/>', '<tag k="surface" v="mud"/>'):
            r = parallel('<tag k="highway" v="cycleway"/>' + detail)
            out, _ = r.snap(
                [[Point(50, 6.00014), Point(50.003, 6.00014)]], "bike", 35, control_indices=[[0, 1]]
            )
            self.assertTrue(all(abs(p.lon - 6) < 1e-7 for p in out[0]))

    def test_driveway_and_parking_are_not_shortcuts_from_main_road(self):
        for service in ("driveway", "parking_aisle"):
            self.assertGreater(
                cycling_anchor_cost({"highway": "service", "service": service}, 0),
                cycling_anchor_cost({"highway": "secondary"}, 10),
            )
            r = parallel(f'<tag k="highway" v="service"/><tag k="service" v="{service}"/>')
            route = [[Point(50, 6.00014), Point(50.003, 6.00014)]]
            out, _ = r.snap(route, "bike", 35, control_indices=[[0, 1]])
            self.assertTrue(all(abs(p.lon - 6) < 1e-7 for p in out[0]))

    def test_explicit_destination_on_a_driveway_remains_reachable(self):
        r = parallel('<tag k="highway" v="service"/><tag k="service" v="driveway"/>')
        out, _ = r.snap(
            [[Point(50, 6.00015), Point(50.003, 6.00015)]], "bike", 1, control_indices=[[0, 1]]
        )
        self.assertTrue(all(abs(p.lon - 6.00015) < 1e-7 for p in out[0]))

    def test_kissing_gate_and_dismount_node_are_not_ridable_connections(self):
        for tags in ('<tag k="barrier" v="kissing_gate"/>', '<tag k="bicycle" v="dismount"/>'):
            raw = (
                '<osm><node id="1" lat="50" lon="6"/><node id="2" lat="50.001" lon="6">'
                + tags
                + '</node><node id="3" lat="50.002" lon="6"/><way id="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/><tag k="highway" v="cycleway"/></way></osm>'
            ).encode()
            with self.assertRaises(AlignmentError):
                RoadMap(raw).snap(
                    [[Point(50, 6), Point(50.002, 6)]], "bike", 5, control_indices=[[0, 1]]
                )

    def test_quality_preferences_do_not_remove_direction_restrictions(self):
        r = parallel(
            '<tag k="highway" v="cycleway"/><tag k="oneway" v="-1"/><tag k="surface" v="asphalt"/>'
        )
        out, _ = r.snap(
            [[Point(50, 6.00014), Point(50.003, 6.00014)]], "bike", 35, control_indices=[[0, 1]]
        )
        self.assertTrue(all(abs(p.lon - 6) < 1e-7 for p in out[0]))

    def test_changing_mountainbike_style_invalidates_route_identity(self):
        from types import SimpleNamespace
        import werkbank as wb

        value = {"style": "trekking"}
        field = lambda v: SimpleNamespace(get=lambda: v)
        app = SimpleNamespace(
            edit_revision=1,
            density=field("Normaal"),
            routing_mode=lambda: "bike",
            routing_style=lambda: value["style"],
            route_preference=field("Meest logisch"),
            snapradius=field("35"),
            private_roads=field(False),
            snap=field(True),
        )
        before = wb.App.routing_key(app)
        value["style"] = "mountainbike"
        self.assertNotEqual(before, wb.App.routing_key(app))


if __name__ == "__main__":
    unittest.main()
