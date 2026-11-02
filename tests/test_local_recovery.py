# SPDX-License-Identifier: GPL-3.0-only
import copy, sys, unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gpx_core import RoadMap, Point, AlignmentError, distance
from local_recovery import find_recovery, corridor_deviation
from auto_alignment import ReviewIssue
from werkbank import App


def road(tags=""):
    return RoadMap(
        (
            '<osm><node id="1" lat="50" lon="6"/><node id="2" lat="50.002" lon="6"/><way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="path"/>'
            + tags
            + "</way></osm>"
        ).encode()
    )


class RecoveryTests(unittest.TestCase):
    def test_wider_search_recovers_offset_control_without_mutation(self):
        s = [Point(50, 6, 10), Point(50.001, 6.0008, 20), Point(50.002, 6, 30)]
        before = copy.deepcopy(s)
        r = road()
        with self.assertRaises(AlignmentError):
            r.snap([s], "walk", 35, control_indices=[[0, 1, 2]])
        # Prevent control omission: same deliberately shifted line remains within
        # the wider search and can be compared as an explicit candidate.
        proposal = find_recovery(r, s, [0, 1, 2], "walk")
        self.assertEqual(s, before)
        self.assertEqual(proposal.radius, 75)
        self.assertEqual(proposal.line[0], s[0])
        self.assertEqual(proposal.line[-1], s[-1])
        self.assertFalse(proposal.relaxed_controls)

    def test_relaxes_bad_interior_control_within_corridor(self):
        r = road()
        s = [Point(50, 6), Point(50.001, 6.0002), Point(50.002, 6)]
        # An internal control can cause a routing failure even within 35 m.
        original = r.snap

        def snap(*args, **kwargs):
            if len(kwargs["control_indices"][0]) > 2:
                raise AlignmentError("verkeerd hoofdpunt", 0, 0, 2)
            return original(*args, **kwargs)

        r.snap = snap
        p = find_recovery(r, s, [0, 1, 2], "walk")
        self.assertTrue(p.relaxed_controls)
        self.assertEqual(p.radius, 35)

    def test_private_and_prohibited_paths_are_not_silently_enabled(self):
        s = [Point(50, 6), Point(50.002, 6)]
        with self.assertRaises(ValueError):
            find_recovery(road('<tag k="access" v="private"/>'), s, [0, 1], "walk")
        self.assertTrue(
            find_recovery(
                road('<tag k="access" v="private"/>'), s, [0, 1], "walk", allow_private=True
            ).line
        )
        with self.assertRaises(ValueError):
            find_recovery(road('<tag k="foot" v="no"/>'), s, [0, 1], "walk", allow_private=True)

    def test_fixed_boundaries_reject_discontinuous_repair(self):
        s = [Point(50, 6.0002), Point(50.002, 6)]
        with self.assertRaisesRegex(ValueError, "grenzen"):
            find_recovery(road(), s, [0, 1], "walk")

    def test_disconnected_paths_cannot_be_bridged_by_wider_search(self):
        r = RoadMap(
            b'<osm><node id="1" lat="50" lon="6"/><node id="2" lat="50.0005" lon="6"/><node id="3" lat="50.0045" lon="6"/><node id="4" lat="50.005" lon="6"/><way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="path"/></way><way id="2"><nd ref="3"/><nd ref="4"/><tag k="highway" v="path"/></way></osm>'
        )
        with self.assertRaises(ValueError):
            find_recovery(r, [Point(50, 6), Point(50.005, 6)], [0, 1], "walk")

    def test_polyline_comparison_samples_edges_and_detects_shortcuts(self):
        a = [Point(50, 6), Point(50.002, 6)]
        b = [Point(50, 6), Point(50.001, 6.002), Point(50.002, 6)]
        self.assertGreater(corridor_deviation(a, b), 140)

    def test_oversized_section_rejected_before_routing(self):
        with self.assertRaisesRegex(ValueError, "5 km"):
            find_recovery(road(), [Point(50, 6), Point(50.1, 6)], [0, 1], "walk")

    def test_wider_search_keeps_connections_on_original_parallel_path(self):
        r = RoadMap(
            b'<osm><node id="1" lat="50" lon="6"/><node id="2" lat="50.002" lon="6"/><node id="3" lat="50" lon="6.00014"/><node id="4" lat="50.002" lon="6.00014"/><way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="path"/></way><way id="2"><nd ref="3"/><nd ref="4"/><tag k="highway" v="path"/></way></osm>'
        )
        s = [Point(50, 6), Point(50.001, 6.00084), Point(50.002, 6)]
        unconstrained = r.snap([s], "walk", 75, control_indices=[[0, 1, 2]])[0][0]
        self.assertGreater(distance(unconstrained[0], s[0]), 2)
        proposal = find_recovery(r, s, [0, 1, 2], "walk")
        self.assertEqual(proposal.radius, 75)
        self.assertTrue(all(abs(p.lon - 6) < 0.00000001 for p in proposal.line))

    def test_invalid_endpoint_search_radius_rejected(self):
        with self.assertRaises(ValueError):
            road().snap([[Point(50, 6), Point(50.002, 6)]], "walk", 35, endpoint_radius=75)

    def ui_proposal(self):
        value = lambda v: SimpleNamespace(get=lambda: v)
        s = [
            Point(49.999, 6),
            Point(50, 6, 10),
            Point(50.001, 6.0008, 20),
            Point(50.002, 6, 30),
            Point(50.003, 6),
        ]
        app = SimpleNamespace(
            busy=False,
            range_selection=(0, 1, 3),
            roadmap=road(),
            snapradius=value("35"),
            routing_key=lambda: app.edit_revision,
            edit_revision=1,
            edit_segments=[s],
            track=SimpleNamespace(segments=[s]),
            flat=value("4.5"),
            anchor_indices=[[0, 1, 2, 3, 4]],
            profile=value("Wandelen · normaal"),
            routing_mode=lambda: "walk",
            private_roads=value(False),
            auto_timer=None,
            density=value("Normaal"),
            auto_checked_key=1,
            auto_issues=[
                ReviewIssue(0, 0, 1, "voor"),
                ReviewIssue(0, 1, 3, "gekozen"),
                ReviewIssue(0, 3, 4, "na"),
            ],
            auto_notes=[],
            remember=Mock(),
            auto_summary=Mock(),
            messages=Mock(),
            draw=Mock(),
            status=Mock(),
            navigate_problem=Mock(),
            canvas=Mock(),
        )
        # Use an actual density label from the implementation.
        from gpx_core import ANCHOR_DENSITY

        app.density = value(next(iter(ANCHOR_DENSITY)))

        def changed(*args, **kwargs):
            app.edit_revision += 1
            app.auto_issues = []
            app.auto_checked_key = None

        app.geometry_changed = changed
        app.job = lambda fn, done, message: done(fn())
        buttons = {}

        def button(*args, **kwargs):
            buttons[kwargs["text"]] = kwargs["command"]
            return Mock()

        with (
            patch("werkbank.tk.Toplevel", return_value=Mock()),
            patch("werkbank.ttk.Label", return_value=Mock()),
            patch("werkbank.ttk.Frame", return_value=Mock()),
            patch("werkbank.ttk.Button", side_effect=button),
            patch("werkbank.RouteMap", return_value=Mock()),
        ):
            App.recover_range(app)
        return app, s, buttons

    def test_preview_does_not_apply_until_accepted_and_preserves_other_issues(self):
        app, source, buttons = self.ui_proposal()
        self.assertEqual(app.edit_segments, [source])
        app.remember.assert_not_called()
        buttons["Gebruik dit voorstel"]()
        app.remember.assert_called_once()
        out = app.edit_segments[0]
        self.assertEqual(out[0], source[0])
        self.assertEqual(out[-1], source[-1])
        self.assertEqual(out[1], source[1])
        self.assertEqual(out[-2], source[3])
        self.assertEqual([i.reason for i in app.auto_issues], ["voor", "na"])
        self.assertEqual(app.auto_issues[-1].end, len(out) - 1)
        self.assertEqual(app.auto_checked_key, app.routing_key())

    def test_stale_preview_cannot_replace_changed_route(self):
        app, source, buttons = self.ui_proposal()
        app.edit_revision += 1
        buttons["Gebruik dit voorstel"]()
        app.remember.assert_not_called()
        self.assertEqual(app.edit_segments, [source])

    def test_cancelling_preview_keeps_geometry_and_issues(self):
        app, source, buttons = self.ui_proposal()
        buttons["Annuleren"]()
        app.remember.assert_not_called()
        self.assertEqual(app.edit_segments, [source])
        self.assertEqual(len(app.auto_issues), 3)
