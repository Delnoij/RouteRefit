# SPDX-License-Identifier: GPL-3.0-only
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gpx_core import Point, RoadMap, allowed
from access_policy import permission
from access_review import access_only_issues
from auto_alignment import automatic_alignment, ReviewIssue
from routing_repair import manual_intervals


def road(tags='', node_tags=''):
    return RoadMap((f'<osm><node id="1" lat="50" lon="6"/><node id="2" lat="50.001" lon="6">{node_tags}</node><node id="3" lat="50.002" lon="6"/><way id="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/><tag k="highway" v="path"/>{tags}</way></osm>').encode())


class AccessReviewTests(unittest.TestCase):
    def setUp(self):
        self.segments = [[Point(50, 6, 12), Point(50.001, 6, 15), Point(50.002, 6, 19)]]
        self.controls = [[0, 1, 2]]

    def test_missing_mode_tags_do_not_forbid_normal_roads_or_paths(self):
        for h in ('residential', 'secondary', 'trunk', 'path', 'track', 'footway', 'pedestrian', 'cycleway'):
            for mode in ('walk', 'bike'):
                self.assertTrue(allowed({'highway': h}, mode), (h, mode))

    def test_specific_access_overrides_generic_and_ignores_other_activity(self):
        self.assertEqual(permission({'access': 'no', 'vehicle': 'yes'}, 'bike'), 'yes')
        self.assertEqual(permission({'access': 'no', 'vehicle': 'yes'}, 'walk'), 'no')
        self.assertTrue(allowed({'highway': 'path', 'foot': 'no'}, 'bike'))
        self.assertTrue(allowed({'highway': 'path', 'bicycle': 'no'}, 'walk'))
        self.assertTrue(allowed({'highway': 'path', 'access': 'no', 'bicycle': 'yes'}, 'bike'))
        self.assertFalse(allowed({'highway': 'path', 'vehicle': 'no', 'bicycle': ' NO '}, 'bike'))

    def test_explicit_restrictions_and_nonroads_remain_blocked(self):
        for value in ('no', 'private', 'use_sidepath', 'dismount', 'destination'):
            self.assertFalse(allowed({'highway': 'path', 'bicycle': value}, 'bike'))
        for h in ('motorway', 'motorway_link', 'construction', 'proposed'):
            self.assertFalse(allowed({'highway': h}, 'bike'))
        self.assertFalse(allowed({'highway': 'trunk', 'motorroad': 'yes'}, 'walk'))

    def test_access_failure_identified_without_changing_any_input(self):
        network = road('<tag k="bicycle" v="no"/>')
        before = copy.deepcopy((network.ways, network.node_tags, self.segments))
        out, _, controls, issues = automatic_alignment(network, self.segments, self.controls, 'bike', 5)
        accepted = access_only_issues(network, out, controls, issues, 'bike', 5)
        self.assertEqual(accepted, issues)
        self.assertTrue(accepted)
        self.assertEqual((network.ways, network.node_tags, self.segments), before)
        self.assertEqual(out, self.segments)

    def test_access_on_node_honors_vehicle_hierarchy(self):
        network = road(node_tags='<tag k="vehicle" v="no"/>')
        out, _, controls, issues = automatic_alignment(network, self.segments, self.controls, 'bike', 5)
        self.assertTrue(issues)
        self.assertEqual(access_only_issues(network, out, controls, issues, 'bike', 5), issues)

    def test_direction_and_physical_barrier_are_not_access_exceptions(self):
        cases = [road('<tag k="oneway" v="-1"/>'), road(node_tags='<tag k="barrier" v="wall"/>'),
                 road('<tag k="bicycle:forward" v="no"/>')]
        for network in cases:
            out, _, controls, issues = automatic_alignment(network, self.segments, self.controls, 'bike', 5)
            self.assertTrue(issues)
            self.assertEqual(access_only_issues(network, out, controls, issues, 'bike', 5), [])

    def test_missing_network_is_not_an_access_exception(self):
        network = road()
        network.ways = []
        issue = ReviewIssue(0, 0, 2, 'missing road')
        self.assertEqual(access_only_issues(network, self.segments, self.controls, [issue], 'bike', 5), [])

    def test_already_routable_issue_is_not_silently_accepted(self):
        issue = ReviewIssue(0, 0, 2, 'loop or geometry warning')
        self.assertEqual(access_only_issues(road(), self.segments, self.controls, [issue], 'bike', 5), [])

    def test_mixed_route_keeps_missing_road_issue_unresolved(self):
        network = road('<tag k="bicycle" v="no"/>')
        segments = self.segments + [[Point(51, 6), Point(51.001, 6)]]
        controls = self.controls + [[0, 1]]
        issues = [ReviewIssue(0, 0, 2, 'access'), ReviewIssue(1, 0, 1, 'missing road')]
        self.assertEqual(access_only_issues(network, segments, controls, issues, 'bike', 5), issues[:1])

    def test_access_warning_is_translated_as_a_complete_dialog(self):
        import i18n
        from access_review_ui import ACCESS_REVIEW_PROMPT
        try:
            for code in ('en', 'de', 'fr'):
                i18n.configure(code, Path(__file__).resolve().parents[1] / 'src')
                translated = i18n.tr(ACCESS_REVIEW_PROMPT)
                self.assertNotIn('Neem plaatselijke', translated)
                self.assertNotIn('Toegangsmeldingen accepteren voor', translated)
                self.assertNotIn('Alleen problemen', translated)
        finally:
            i18n.configure('nl', Path(__file__).resolve().parents[1] / 'src')


if __name__ == '__main__':
    unittest.main()
