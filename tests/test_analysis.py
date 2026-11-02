# SPDX-License-Identifier: GPL-3.0-only
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gpx_core import Point, Track
from route_analysis import analyze_route, display_samples, nearest_elevation
from route_formats import read_route
from workspace_ui import WorkspaceUI, inspect_folder


class AnalysisTests(unittest.TestCase):
    def test_gaps_and_segment_boundaries_remain_separate(self):
        analysis = analyze_route(
            [
                [
                    Point(50, 6, 10),
                    Point(50, 6.001, 20),
                    Point(50, 6.002, None),
                    Point(50, 6.003, 100),
                ],
                [Point(51, 7, 1000), Point(51, 7.001, 980)],
            ]
        )
        self.assertEqual([len(run) for run in analysis.elevation_runs], [2, 1, 2])
        self.assertEqual(analysis.stats["ascent"], 10)
        self.assertEqual(analysis.stats["descent"], 20)
        self.assertLess(analysis.stats["km"], 1)

    def test_drawing_reduction_keeps_peaks_valleys_and_order(self):
        run = tuple(
            (i / 1000, 1000 if i == 5151 else -500 if i == 5152 else i % 20) for i in range(10000)
        )
        drawn = display_samples(run, 10, 300)
        self.assertEqual(drawn[0], run[0])
        self.assertEqual(drawn[-1], run[-1])
        self.assertIn(run[5151], drawn)
        self.assertIn(run[5152], drawn)
        self.assertEqual(sorted(drawn), list(drawn))
        self.assertLessEqual(len(drawn), 4 * 301)

    def test_nearest_sample_uses_original_values_and_first_tie(self):
        analysis = SimpleNamespace(
            sample_distances=(0, 1, 1, 2), samples=((0, 10), (1, 20), (1, 30), (2, 40))
        )
        self.assertEqual(nearest_elevation(analysis, 1), (1, 20))
        self.assertEqual(nearest_elevation(analysis, 0.5), (0, 10))
        self.assertEqual(nearest_elevation(analysis, 5), (2, 40))
        self.assertIsNone(nearest_elevation(SimpleNamespace(sample_distances=()), 1))

    def test_invalid_timestamps_disable_duration_and_speeds(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for end in (None, start - timedelta(seconds=1)):
            result = analyze_route([[Point(50, 6, 10, start), Point(50.01, 6, 20, end)]]).stats
            self.assertIsNone(result["seconds"])
            self.assertIsNone(result["peak"])
            self.assertIsNone(result["average"])

    def test_nonfinite_elevations_are_missing_data(self):
        analysis = analyze_route(
            [[Point(50, 6, 10), Point(50.001, 6, float("nan")), Point(50.002, 6, 20)]]
        )
        self.assertEqual(analysis.stats["elevation_count"], 2)
        self.assertEqual(analysis.stats["ascent"], 0)
        self.assertEqual(len(analysis.elevation_runs), 2)

    def test_cached_statistics_refresh_after_edits_and_new_preview(self):
        segments = [[Point(50, 6, 10), Point(50.001, 6, 20)]]
        app = SimpleNamespace(
            track=SimpleNamespace(hash="original"), edit_revision=0, _statistics_cache={}
        )
        first = WorkspaceUI.statistics_analysis(app, "Bewerkte route", segments)
        self.assertIs(first, WorkspaceUI.statistics_analysis(app, "Bewerkte route", segments))
        segments[0][1] = Point(50.001, 6, 30)
        app.edit_revision += 1
        second = WorkspaceUI.statistics_analysis(app, "Bewerkte route", segments)
        self.assertEqual(second.stats["ascent"], 20)
        self.assertIsNot(first, second)
        preview = [[Point(50, 6, 10), Point(50.002, 6, 15)]]
        self.assertEqual(
            WorkspaceUI.statistics_analysis(app, "Voorstel", preview).stats["ascent"], 5
        )


class ImportEfficiencyTests(unittest.TestCase):
    def test_gpx_is_validated_once_and_bad_input_still_fails(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as tmp:
            path = Path(tmp) / "route.gpx"
            path.write_bytes(
                b'<gpx><trk><trkseg><trkpt lat="50" lon="6"/><trkpt lat="50.01" lon="6"/></trkseg></trk></gpx>'
            )
            with patch("route_formats.Track", wraps=Track) as parser:
                imported = read_route(path)
                self.assertIs(imported.track, imported.track)
                self.assertEqual(parser.call_count, 1)
            path.write_bytes(b"<bad")
            with self.assertRaises(Exception):
                read_route(path)

    def test_same_kml_contents_with_different_filenames_are_duplicates(self):
        raw = b"<kml><Placemark><LineString><coordinates>6,50,100 6.001,50.001,120</coordinates></LineString></Placemark></kml>"
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as tmp:
            folder = Path(tmp)
            (folder / "one.kml").write_bytes(raw)
            (folder / "two.kml").write_bytes(raw)
            rows, errors = inspect_folder(folder)
            self.assertFalse(errors)
            self.assertEqual(sum(r["duplicate"] for r in rows), 2)

    def test_manual_import_schedules_work_without_loading_on_ui_thread(self):
        app = SimpleNamespace(job=Mock(), load=Mock())
        WorkspaceUI.safe_load(app, Path("example.gpx"))
        app.job.assert_called_once()
        app.load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
