# SPDX-License-Identifier: GPL-3.0-only
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gpx_core import Point, cumulative
from map_plan import plan_route_tiles, map_cache_name
from werkbank import App
import werkbank as wb

OSM = b'<osm><node id="1" lat="50" lon="6"/><node id="2" lat="50.001" lon="6"/><way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="path"/></way></osm>'


class MapPlanningTests(unittest.TestCase):
    def test_two_hundred_km_route_fits_budget(self):
        segments = [[Point(50 + i * 0.0018, 6) for i in range(1001)]]
        self.assertGreater(cumulative(segments[0])[-1], 200000)
        tiles = plan_route_tiles(segments)
        self.assertGreater(len(tiles), 36)
        self.assertLessEqual(len(tiles), 200)
        for w, s, e, n in tiles:
            self.assertLessEqual(e - w, 0.03000001)
            self.assertLessEqual(n - s, 0.02000001)

    def test_sparse_edges_are_covered_without_connecting_segments(self):
        connected = plan_route_tiles([[Point(50, 6), Point(50.3, 6)]])
        separated = plan_route_tiles([[Point(50, 6)], [Point(50.3, 6)]])
        self.assertGreater(len(connected), len(separated))
        self.assertLess(len(separated), 5)

    def test_cache_identity_includes_the_actual_corridor(self):
        diagonal = [[Point(50, 6), Point(50.1, 6.2)]]
        elbow = [[Point(50, 6), Point(50, 6.2), Point(50.1, 6.2)]]
        self.assertNotEqual(
            map_cache_name(plan_route_tiles(diagonal)), map_cache_name(plan_route_tiles(elbow))
        )
        self.assertEqual(plan_route_tiles(diagonal), plan_route_tiles(diagonal))

    def test_budget_failure_happens_before_network_requests(self):
        segments = [[Point(45 + i * 0.01, 6) for i in range(1001)]]
        with patch.object(wb, "fetch") as fetch:
            with self.assertRaisesRegex(ValueError, "200"):
                wb.download_map(segments)
            fetch.assert_not_called()

    def test_progress_reaches_the_complete_plan_and_cache_reuses_network(self):
        segments = [[Point(50, 6), Point(50.07, 6)]]
        progress = Mock()
        with (
            tempfile.TemporaryDirectory(dir=ROOT / "tests") as tmp,
            patch.object(wb, "MAPS", Path(tmp)),
            patch.object(wb.time, "sleep"),
        ):
            with patch.object(wb, "fetch", return_value=OSM):
                path = wb.download_map(segments, progress=progress)
            self.assertTrue(path.exists())
            total = len(plan_route_tiles(segments))
            self.assertEqual(progress.call_args.args, (total, total))
            with patch.object(wb, "fetch", side_effect=AssertionError("unexpected network")):
                self.assertEqual(wb.download_map(segments), path)

    def test_saved_tiles_have_no_artificial_delay(self):
        segments = [[Point(50, 6), Point(50.07, 6)]]
        with tempfile.TemporaryDirectory() as tmp, patch.object(wb, "MAPS", Path(tmp)):
            with patch.object(wb, "fetch", return_value=OSM), patch.object(wb.time, "sleep"):
                merged = wb.download_map(segments)
            merged.unlink()
            with patch.object(wb, "fetch", side_effect=AssertionError("network")), patch.object(wb.time, "sleep") as sleep:
                self.assertTrue(wb.download_map(segments).exists())
                sleep.assert_not_called()

    def test_missing_road_data_does_not_change_loaded_route(self):
        route = [[Point(50, 6), Point(50.01, 6)]]
        app = SimpleNamespace(
            edit_segments=route, mapinfo=Mock(), auto_summary=Mock(), status=Mock(), track=object()
        )
        track = app.track
        App.map_download_unavailable(app, OSError("offline"))
        self.assertIs(app.edit_segments, route)
        self.assertIs(app.track, track)
        app.status.set.assert_called_once()


if __name__ == "__main__":
    unittest.main()
