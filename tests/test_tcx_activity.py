# SPDX-License-Identifier: GPL-3.0-only
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from route_formats import tcx
from gpx_core import Track


def trackpoint(lat=50, lon=6, time="2026-08-27T08:00:00Z"):
    position = (
        f"<Position><LatitudeDegrees>{lat}</LatitudeDegrees><LongitudeDegrees>{lon}</LongitudeDegrees></Position>"
        if lat is not None
        else ""
    )
    return f"<Trackpoint><Time>{time}</Time>{position}<AltitudeMeters>100</AltitudeMeters></Trackpoint>"


def activity(sport, body=None):
    if body is None:
        body = trackpoint() + trackpoint(50.001, 6.001, "2026-08-27T08:01:00Z")
    return f'<Activity Sport="{sport}"><Lap><Track>{body}</Track></Lap></Activity>'


def convert(body):
    return Track(
        tcx(
            (
                "<TrainingCenterDatabase><Activities>"
                + body
                + "</Activities></TrainingCenterDatabase>"
            ).encode(),
            "test",
        )
    )


class TcxActivity(unittest.TestCase):
    def test_shared_lap_boundaries_form_one_track_without_losing_samples(self):
        first = trackpoint() + trackpoint(50.001, 6.001, "2026-08-27T08:01:00Z")
        second = trackpoint(50.001, 6.001, "2026-08-27T08:01:00Z") + trackpoint(
            50.002, 6.002, "2026-08-27T08:02:00Z"
        )
        body = (
            '<Activity Sport="Biking"><Lap><Track>'
            + first
            + "</Track></Lap><Lap><Track>"
            + second
            + "</Track></Lap></Activity>"
        )
        t = convert(body)
        self.assertEqual(len(t.segments), 1)
        self.assertEqual(t.stats()["points"], 4)
        self.assertEqual(t.stats()["seconds"], 120)

    def test_normal_sampling_across_lap_boundary_does_not_make_a_gap(self):
        first = trackpoint() + trackpoint(50.001, 6.001, "2026-08-27T08:01:00Z")
        second = trackpoint(50.00105, 6.00105, "2026-08-27T08:01:01Z") + trackpoint(
            50.002, 6.002, "2026-08-27T08:02:00Z"
        )
        body = (
            '<Activity Sport="Biking"><Lap><Track>'
            + first
            + "</Track></Lap><Lap><Track>"
            + second
            + "</Track></Lap></Activity>"
        )
        self.assertEqual(len(convert(body).segments), 1)

    def test_missing_position_at_lap_edge_and_different_sessions_stay_separate(self):
        first = trackpoint() + trackpoint(50.001, 6.001, "2026-08-27T08:01:00Z")
        second = trackpoint(50.001, 6.001, "2026-08-27T08:01:00Z") + trackpoint(
            50.002, 6.002, "2026-08-27T08:02:00Z"
        )
        for tail in (trackpoint(None), ""):
            if tail:
                body = (
                    '<Activity Sport="Biking"><Lap><Track>'
                    + first
                    + tail
                    + "</Track></Lap><Lap><Track>"
                    + second
                    + "</Track></Lap></Activity>"
                )
            else:
                body = activity("Biking", first) + activity("Biking", second)
            self.assertEqual(len(convert(body).segments), 2)

    def test_long_gap_across_laps_is_not_drawn_as_a_recorded_straight_line(self):
        first = trackpoint() + trackpoint(50.001, 6.001, "2026-08-27T08:01:00Z")
        second = trackpoint(50.01, 6.01, "2026-08-27T08:11:00Z") + trackpoint(
            50.011, 6.011, "2026-08-27T08:12:00Z"
        )
        body = (
            '<Activity Sport="Biking"><Lap><Track>'
            + first
            + "</Track></Lap><Lap><Track>"
            + second
            + "</Track></Lap></Activity>"
        )
        self.assertEqual(len(convert(body).segments), 2)

    def test_biking_declaration_survives_conversion_and_selects_bicycle_mode(self):
        t = convert(activity("Biking"))
        self.assertEqual(t.activity_mode, "bike")
        self.assertEqual(t.stats()["points"], 2)
        self.assertEqual(t.stats()["seconds"], 60)

    def test_mixed_activities_do_not_infer_one_shared_mode(self):
        self.assertIsNone(convert(activity("Biking") + activity("Running")).activity_mode)
        self.assertIsNone(convert(activity("Biking") + activity("")).activity_mode)

    def test_other_and_course_without_sport_are_not_assumed_to_be_cycling(self):
        self.assertIsNone(convert(activity("Other")).activity_mode)
        raw = (
            "<TrainingCenterDatabase><Courses><Course><Track>"
            + trackpoint()
            + trackpoint(50.001, 6.001)
            + "</Track></Course></Courses></TrainingCenterDatabase>"
        ).encode()
        self.assertIsNone(Track(tcx(raw, "course")).activity_mode)

    def test_missing_position_separates_tracks_without_inventing_a_bridge(self):
        body = trackpoint() + trackpoint(50.001, 6.001, "2026-08-27T08:01:00Z")
        body += trackpoint(None, time="2026-08-27T09:00:00Z")
        body += trackpoint(51, 7, "2026-08-27T09:01:00Z") + trackpoint(
            51.001, 7.001, "2026-08-27T09:02:00Z"
        )
        t = convert(activity("Biking", body))
        self.assertEqual(len(t.segments), 2)
        self.assertEqual(t.stats()["points"], 4)
        self.assertLess(t.stats()["km"], 1)
        self.assertEqual(t.stats()["seconds"], 120)


if __name__ == "__main__":
    unittest.main()
