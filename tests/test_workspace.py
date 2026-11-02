# SPDX-License-Identifier: GPL-3.0-only
import unittest
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from workspace_ui import inspect_folder, route_statistics
from gpx_core import Point

GPX = b'<gpx><trk><trkseg><trkpt lat="50" lon="6"><ele>10</ele></trkpt><trkpt lat="50.001" lon="6"><ele>20</ele></trkpt></trkseg></trk></gpx>'
tempfile.tempdir = str(Path(__file__).resolve().parent)


class WorkspaceTests(unittest.TestCase):
    def test_check_reports_are_not_misidentified_as_geojson_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            (folder/'route.controle.json').write_text('{"issues":[]}',encoding='utf-8')
            (folder/'line.json').write_text('{"type":"LineString","coordinates":[[6,50],[6,50.001]]}',encoding='utf-8')
            rows,errors=inspect_folder(folder)
            self.assertEqual([row['name'] for row in rows],['line.json'])
            self.assertTrue(rows[0]['valid'])
            self.assertTrue((folder/'route.controle.json').is_file())
    def test_folder_reports_duplicates_invalid_and_uppercase_without_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name, raw in [
                ("route.GPX", GPX),
                ("copy.gpx", GPX),
                ("bad.gpx", b"<bad"),
                ("ignore.txt", GPX),
            ]:
                (folder / name).write_bytes(raw)
            before = {p.name: p.read_bytes() for p in folder.iterdir()}
            rows, errors = inspect_folder(folder)
            self.assertEqual(len(rows), 3)
            self.assertEqual(sum(r["valid"] for r in rows), 2)
            self.assertEqual(sum(r["duplicate"] for r in rows), 2)
            self.assertFalse(errors)
            self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})

    def test_subfolders_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "sub").mkdir()
            (folder / "sub" / "route.gpx").write_bytes(GPX)
            self.assertEqual(inspect_folder(folder)[0], [])
            self.assertEqual(len(inspect_folder(folder, True)[0]), 1)

    def test_missing_folder_is_reported(self):
        with self.assertRaises(ValueError):
            inspect_folder(Path("not-existing-folder-test"))

    def test_heights_do_not_bridge_missing_data_or_segments(self):
        stats = route_statistics(
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
        self.assertEqual(stats["ascent"], 10)
        self.assertEqual(stats["descent"], 20)
        self.assertLess(stats["km"], 1)
        self.assertEqual(stats["elevation_count"], 5)
        self.assertIsNone(stats["seconds"])

    def test_times_exclude_segment_gaps_and_report_total_average(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        stats = route_statistics(
            [
                [Point(50, 6, 0, start), Point(50.01, 6, 20, start + timedelta(hours=1))],
                [
                    Point(51, 6, 100, start + timedelta(days=1)),
                    Point(51.01, 6, 80, start + timedelta(days=1, hours=1)),
                ],
            ]
        )
        self.assertEqual(stats["seconds"], 7200)
        self.assertAlmostEqual(stats["average"], stats["km"] / 2)
        self.assertEqual(stats["ascent"], 20)
        self.assertEqual(stats["descent"], 20)

    def test_decreasing_or_missing_times_disable_speed_and_duration(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for end in [None, start - timedelta(seconds=1)]:
            stats = route_statistics([[Point(50, 6, None, start), Point(50.01, 6, None, end)]])
            self.assertIsNone(stats["seconds"])
            self.assertIsNone(stats["peak"])
            self.assertIsNone(stats["ascent"])


if __name__ == "__main__":
    unittest.main()
