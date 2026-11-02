# SPDX-License-Identifier: GPL-3.0-only
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gpx_core import Point, distance
from segment_join import average_speed, retime_at_previous_average
from route_context import RouteContextUI, nearest_line_point


class SectionTiming(unittest.TestCase):
    def setUp(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        coords = [(50, 6), (50.001, 6), (50.001, 6.002), (50.001, 6), (50.002, 6)]
        self.original = [
            [
                Point(lat, lon, 100 + i, start + timedelta(seconds=i * 60))
                for i, (lat, lon) in enumerate(coords)
            ]
        ]

    def test_remove_wrong_turn_keeps_mean_speed_and_corresponding_point_times(self):
        before = copy.deepcopy(self.original)
        edited = [[self.original[0][i] for i in (0, 1, 4)]]
        result = retime_at_previous_average(self.original, edited)
        self.assertEqual(self.original, before)
        self.assertEqual(result[0][0].time, self.original[0][0].time)
        self.assertLess(result[0][-1].time, self.original[0][-1].time)
        self.assertAlmostEqual(average_speed(result), average_speed(self.original), places=7)
        for a, b in zip(result[0], result[0][1:]):
            self.assertAlmostEqual(
                distance(a, b) / (b.time - a.time).total_seconds(),
                average_speed(self.original),
                places=7,
            )
        self.assertEqual(
            [(p.lat, p.lon, p.ele) for p in result[0]], [(p.lat, p.lon, p.ele) for p in edited[0]]
        )

    def test_missing_times_and_zero_distance_do_not_invent_an_average(self):
        self.original[0][1].time = None
        with self.assertRaises(ValueError):
            retime_at_previous_average(self.original, self.original)
        self.setUp()
        with self.assertRaises(ValueError):
            retime_at_previous_average(self.original, [[self.original[0][0], self.original[0][0]]])

    def test_gaps_between_separate_segments_are_not_removed_by_retiming(self):
        second = copy.deepcopy(self.original[0])
        for p in second:
            p.time += timedelta(hours=1)
        original = [self.original[0], second]
        edited = [[s[0], s[1], s[-1]] for s in original]
        result = retime_at_previous_average(original, edited)
        self.assertAlmostEqual(average_speed(result), average_speed(original), places=7)
        self.assertEqual(
            result[1][0].time - result[0][-1].time, original[1][0].time - original[0][-1].time
        )


class ContextActions(unittest.TestCase):
    def test_long_drawn_edge_is_selectable_without_a_nearby_recorded_point(self):
        segments = [[Point(0, 0), Point(0, 100)]]
        self.assertEqual(nearest_line_point(segments, lambda p: (p.lon, p.lat), 50, 1), (0, 0))
        self.assertIsNone(nearest_line_point(segments, lambda p: (p.lon, p.lat), 50, 100))

    def test_same_junction_can_be_the_start_and_later_end_of_a_wrong_turn(self):
        s = [[Point(0, 0), Point(0, 100), Point(100, 100), Point(0, 0), Point(0, -100)]]
        pixel = lambda p: (p.lon, p.lat)
        self.assertEqual(nearest_line_point(s, pixel, 0, 0), (0, 0))
        self.assertEqual(nearest_line_point(s, pixel, 0, 0, after=(0, 0)), (0, 3))

    def test_two_context_clicks_open_only_the_chosen_section(self):
        app = SimpleNamespace(
            busy=False, range_anchor=(0, 3), draw=Mock(), replace_range_with_via=Mock(), quick_section_alignment=Mock()
        )
        RouteContextUI.context_end(app, (0, 8))
        self.assertEqual(app.range_selection, (0, 3, 8))
        self.assertIsNone(app.range_anchor)
        app.quick_section_alignment.assert_called_once_with(0, 3, 8)
        app.connection_editor = Mock()
        RouteContextUI.replace_range_with_via(app)
        app.connection_editor.assert_called_once_with(0, section=(3, 8))

    def test_right_click_exposes_start_action_without_altering_geometry(self):
        segments = [[Point(0, 0), Point(0, 100)]]
        app = SimpleNamespace(
            busy=False,
            track=object(),
            auto_timer=None,
            edit_segments=segments,
            range_anchor=None,
            range_selection=None,
            auto_issues=[],
            history=[],
            canvas=SimpleNamespace(pixel=lambda p: (p.lon, p.lat), point=lambda x,y:Point(y,x)),
            anchor_indices=[[0,1]], automatic_alignment_action=Mock(), manual_alignment=Mock(), add_waypoint=Mock(), cancel_alignment=Mock(), stop_alignment=Mock(),
            context_start=Mock(),
            undo=Mock(),
            reset_view=Mock(),
        )
        event = SimpleNamespace(x=50, y=0, x_root=100, y_root=100)
        with patch("route_context.tk.Menu") as factory:
            RouteContextUI.route_context_menu(app, event)
            entries = factory.return_value.add_command.call_args_list
            entry = next(
                c.kwargs for c in entries if c.kwargs["label"] == "Begin te verwijderen stuk hier"
            )
            entry["command"]()
            app.context_start.assert_called_once_with((0, 0))
            self.assertEqual(app.edit_segments, segments)


if __name__ == "__main__":
    unittest.main()
