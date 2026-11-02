# SPDX-License-Identifier: GPL-3.0-only
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gpx_core import Point, RoadMap, Track, distance
from routing_repair import leg_key
from segment_join import find_connection, merge_connection, connection_record
from werkbank import App


def network(tags="", disconnected=False):
    coords = {
        1: (50, 6),
        2: (50.001, 6),
        3: (50.002, 6),
        4: (50.003, 6),
        5: (50.001, 6.003),
        6: (50.002, 6.003),
    }
    nodes = "".join(f'<node id="{i}" lat="{lat}" lon="{lon}"/>' for i, (lat, lon) in coords.items())
    paths = [[1, 2], [3, 4]] if disconnected else [[1, 2, 3, 4], [2, 5, 6, 3]]
    ways = "".join(
        f'<way id="{i}">'
        + "".join(f'<nd ref="{n}"/>' for n in ns)
        + '<tag k="highway" v="residential"/>'
        + tags
        + "</way>"
        for i, ns in enumerate(paths)
    )
    return RoadMap(f"<osm>{nodes}{ways}</osm>".encode())


class JoinTests(unittest.TestCase):
    def setUp(self):
        t = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.left = [Point(50, 6, 10, t), Point(50.001, 6, 20, t + timedelta(seconds=60))]
        self.right = [
            Point(50.002, 6, 40, t + timedelta(seconds=1260)),
            Point(50.003, 6, 50, t + timedelta(seconds=1320)),
        ]

    def test_via_point_selects_actual_detour_instead_of_shortest_connection(self):
        road = network()
        short = find_connection(road, self.left, self.right, "bike", 5)
        via = [Point(50.001, 6.003), Point(50.002, 6.003)]
        guided = find_connection(road, self.left, self.right, "bike", 5, via)
        self.assertGreater(guided.length, short.length * 3)
        for p in via:
            self.assertLess(min(distance(p, q) for q in guided.line), 1)
        # Editing the via points invalidates/recalculates just this proposal.
        edited = find_connection(road, self.left, self.right, "bike", 5, [])
        self.assertAlmostEqual(edited.length, short.length)

    def test_local_graph_preserves_the_full_graph_proposal(self):
        road = network()
        via = [Point(50.001, 6.003), Point(50.002, 6.003)]
        full = find_connection(road, self.left, self.right, "bike", 5, via, local_graph=False)
        local = find_connection(road, self.left, self.right, "bike", 5, via)
        self.assertEqual(full.line, local.line)
        self.assertEqual(full.notes, local.notes)

    def test_joins_only_chosen_gap_and_preserves_every_original_sample(self):
        segments = [self.left, self.right, [Point(50.004, 6), Point(50.005, 6)]]
        before = copy.deepcopy(segments)
        anchors = [[0, 1]] * 3
        protected = {leg_key(i, s[0], s[-1]) for i, s in enumerate(segments)}
        proposal = find_connection(network(), self.left, self.right, "bike", 5)
        out, controls, kept = merge_connection(segments, anchors, protected, 0, proposal)
        self.assertEqual(segments, before)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0][: len(self.left)], self.left)
        self.assertEqual(out[0][-len(self.right) :], self.right)
        self.assertIs(out[0][0], self.left[0])
        self.assertIs(out[0][-1], self.right[-1])
        self.assertEqual(out[1], segments[2])
        self.assertEqual(controls[0][-1], len(out[0]) - 1)
        self.assertEqual({k[0] for k in kept}, {0, 1})

    def test_gap_times_interpolate_without_retiming_recorded_points(self):
        via = [Point(50.001, 6.003), Point(50.002, 6.003)]
        proposal = find_connection(network(), self.left, self.right, "bike", 5, via)
        self.assertTrue(proposal.estimated_time)
        self.assertIs(proposal.line[0], self.left[-1])
        self.assertIs(proposal.line[-1], self.right[0])
        self.assertTrue(all(a.time <= b.time for a, b in zip(proposal.line, proposal.line[1:])))
        self.assertTrue(all(p.element is None for p in proposal.line[1:-1]))
        record = connection_record(0, proposal)
        self.assertFalse(record["recorded"])
        self.assertIn("possible_pause", record["time_status"])
        self.assertEqual(len(record["via"]), 2)

    def test_missing_or_reversed_times_do_not_create_fake_measurements(self):
        for endtime in (None, self.left[0].time):
            right = [copy.copy(p) for p in self.right]
            right[0].time = endtime
            proposal = find_connection(
                network(), self.left, right, "walk", 5, [Point(50.001, 6.003), Point(50.002, 6.003)]
            )
            self.assertFalse(proposal.estimated_time)
            self.assertTrue(all(p.time is None for p in proposal.line[1:-1]))

    def test_disconnected_roads_never_fall_back_to_a_straight_line(self):
        with self.assertRaises(ValueError):
            find_connection(network(disconnected=True), self.left, self.right, "bike", 5)

    def test_prohibited_and_wrong_way_roads_remain_prohibited(self):
        for tags in (
            '<tag k="bicycle" v="no"/>',
            '<tag k="oneway" v="-1"/>',
            '<tag k="access" v="private"/>',
        ):
            with self.subTest(tags=tags), self.assertRaises(ValueError):
                find_connection(network(tags), self.left, self.right, "bike", 5)
        self.assertTrue(
            find_connection(
                network('<tag k="access" v="private"/>'),
                self.left,
                self.right,
                "bike",
                5,
                allow_private=True,
            ).line
        )

    def test_coincident_lap_boundaries_join_without_a_road_network(self):
        right = [copy.copy(self.left[-1]), *self.right]
        p = find_connection(None, self.left, right, "bike", 5)
        out, _, _ = merge_connection([self.left, right], [[0, 1], [0, 2]], set(), 0, p)
        self.assertEqual(out, [self.left + right])

    def test_stale_proposal_cannot_be_applied_to_different_endpoints(self):
        p = find_connection(network(), self.left, self.right, "bike", 5)
        with self.assertRaises(ValueError):
            merge_connection([self.right, self.left], [[0, 1], [0, 1]], set(), 0, p)

    def test_export_reimports_joined_track_and_preserves_extensions(self):
        raw = b"""<gpx xmlns="http://www.topografix.com/GPX/1/1" xmlns:x="urn:test"><metadata><name>Original</name></metadata><trk><name>Ride</name><trkseg><trkpt lat="50" lon="6"><extensions><x:hr>123</x:hr></extensions></trkpt><trkpt lat="50.001" lon="6"/><extensions><x:part>A</x:part></extensions></trkseg><trkseg><trkpt lat="50.002" lon="6"/><trkpt lat="50.003" lon="6"/><extensions><x:part>B</x:part></extensions></trkseg></trk></gpx>"""
        track = Track(raw)
        p = find_connection(network(), *track.segments, "bike", 5)
        out, _, _ = merge_connection(track.segments, [[0, 1], [0, 1]], set(), 0, p)
        exported = track.export(out, segment_groups=[[0, 1]], modification_note="Reconstructed")
        result = Track(exported)
        self.assertEqual(len(result.segments), 1)
        tree = ET.fromstring(exported)
        self.assertEqual(tree.find(".//{urn:test}hr").text, "123")
        self.assertEqual([n.text for n in tree.findall(".//{urn:test}part")], ["A", "B"])
        segment = tree.find(".//{http://www.topografix.com/GPX/1/1}trkseg")
        self.assertTrue(segment[-1].tag.endswith("extensions"))
        self.assertEqual(track.raw, raw)
        for groups in ([[0], [1]], [[1, 0]], [[0, 0]], [[True, 0]]):
            with self.assertRaises(ValueError):
                track.export(out, segment_groups=groups)

    def test_undo_restores_gap_report_grouping_and_manual_protection(self):
        app = SimpleNamespace(
            edit_segments=[self.left, self.right],
            selection=None,
            anchor_indices=[[0, 1], [0, 1]],
            manual_sections=set(),
            joined_gaps=[],
            segment_groups=[[0], [1]],
            auto_notes=[],
            history=[],
            busy=False,
            geometry_changed=Mock(),
            clear_access_reviews=lambda: None,
            mapmode=SimpleNamespace(get=lambda: "view"),
        )
        App.remember(app)
        app.joined_gaps.append({"recorded": False})
        app.segment_groups[:] = [[0, 1]]
        app.edit_segments = [self.left + self.right]
        App.undo(app)
        self.assertEqual(app.edit_segments, [self.left, self.right])
        self.assertEqual(app.joined_gaps, [])
        self.assertEqual(app.segment_groups, [[0], [1]])


if __name__ == "__main__":
    unittest.main()
