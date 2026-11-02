# SPDX-License-Identifier: GPL-3.0-only
import unittest, sys, tempfile
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gpx_core import *
from osm_canvas import world, location, TileStore, RouteMap
from types import SimpleNamespace
from unittest.mock import patch


class MapEditing(unittest.TestCase):
    def setUp(self):
        self.segments = [
            [
                Point(50, 6, 100, datetime(2026, 1, 1, tzinfo=timezone.utc)),
                Point(50.001, 6, 120, datetime(2026, 1, 1, 0, 2, tzinfo=timezone.utc)),
                Point(50.002, 6, 130, datetime(2026, 1, 1, 0, 3, tzinfo=timezone.utc)),
            ]
        ]

    def test_projection_roundtrip(self):
        for lat, lon in [(50.923, 5.99), (46.54, 11.61), (-33.8, 151.2), (0, 179.9)]:
            for z in [2, 13, 19]:
                a, b = location(*world(lat, lon, z), z)
                self.assertAlmostEqual(a, lat, 7)
                self.assertAlmostEqual(b, lon, 7)

    def test_move_preserves_original_and_timestamps(self):
        out = move_point(self.segments, 0, 1, Point(50.0012, 6.0001))
        self.assertEqual(self.segments[0][1].lon, 6)
        self.assertEqual(out[0][1].lon, 6.0001)
        self.assertEqual(out[0][1].time, self.segments[0][1].time)

    def test_insert_interpolates_elevation_and_time(self):
        out = insert_point(self.segments, 0, 0, 0.5, Point(50.0005, 6))
        self.assertEqual(len(out[0]), 4)
        self.assertEqual(len(self.segments[0]), 3)
        self.assertEqual(out[0][1].ele, 110)
        self.assertEqual(out[0][1].time.minute, 1)

    def test_delete_does_not_mutate_source(self):
        out = delete_point(self.segments, 0, 1)
        self.assertEqual(len(out[0]), 2)
        self.assertEqual(len(self.segments[0]), 3)
        with self.assertRaises(ValueError):
            delete_point(out, 0, 0)

    def test_errors_include_map_position(self):
        raw = b'<osm><node id="1" lat="50" lon="6"/><node id="2" lat="50.001" lon="6"/><way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="path"/></way></osm>'
        with self.assertRaises(AlignmentError) as context:
            RoadMap(raw).snap([[Point(50, 6.01), Point(50.001, 6.01)]], "walk")
        self.assertEqual(context.exception.segment, 0)
        self.assertEqual(context.exception.index, 0)
        self.assertIn("rode markering", str(context.exception))

    def test_disconnection_has_both_bounds(self):
        raw = b'<osm><node id="1" lat="50" lon="6"/><node id="2" lat="50.001" lon="6"/><node id="3" lat="50.002" lon="6"/><node id="4" lat="50.003" lon="6"/><way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="path"/></way><way id="2"><nd ref="3"/><nd ref="4"/><tag k="highway" v="path"/></way></osm>'
        with self.assertRaises(AlignmentError) as context:
            RoadMap(raw).snap([[Point(50.0001, 6), Point(50.0029, 6)]], "walk")
        self.assertEqual(context.exception.end_index, 1)

    def test_cached_visible_tile_does_not_use_network(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as d:
            store = TileStore(d)
            p = Path(d) / "13/4232/2761.png"
            p.parent.mkdir(parents=True)
            p.write_bytes(b"cached PNG")
            with patch(
                "osm_canvas.urlopen", side_effect=AssertionError("Netwerk mag niet worden gebruikt")
            ):
                store.load((13, 4232, 2761), lambda key: True)
            key, data, error = store.results.get_nowait()
            self.assertIsNone(error)
            self.assertEqual(data, b"cached PNG")
            store.close()

    def test_invisible_tile_not_downloaded_or_cached(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as d:
            store = TileStore(d)
            with patch(
                "osm_canvas.urlopen",
                side_effect=AssertionError("Onzichtbare tegel mag niet worden opgehaald"),
            ):
                store.load((13, 4232, 2761), lambda key: False)
            self.assertTrue(store.results.empty())
            self.assertEqual(list(Path(d).rglob("*.png")), [])
            store.close()

    def test_dragging_marker_keeps_anchor_offset(self):
        moved = []
        canvas = SimpleNamespace(
            dragging=dict(hit=(0, 1), offset=(2, 21)),
            mode="edit",
            moved=True,
            delete=lambda *args: None,
            on_move=lambda *args: moved.append(args),
            point=lambda x, y: (x, y),
        )
        RouteMap.up(canvas, SimpleNamespace(x=80, y=100))
        self.assertEqual(moved, [(0, 1, (82, 121))])
        self.assertIsNone(canvas.dragging)

    def test_expired_cache_survives_network_failure(self):
        with tempfile.TemporaryDirectory() as d:
            store = TileStore(d)
            p = Path(d) / "13/4232/2761.png"
            p.parent.mkdir(parents=True)
            p.write_bytes(b"cached PNG")
            p.with_suffix(".json").write_text('{"expires": 0}')
            with patch("osm_canvas.urlopen", side_effect=OSError("offline")):
                store.load((13, 4232, 2761), lambda key: True)
            self.assertEqual(store.results.get_nowait(), ((13, 4232, 2761), b"cached PNG", None))
            store.close()

    def test_download_still_displayed_when_cache_is_read_only(self):
        from unittest.mock import MagicMock
        raw = b"\x89PNG\r\n\x1a\nimage"
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = raw
        response.headers = {}
        with tempfile.TemporaryDirectory() as d:
            store = TileStore(d)
            with patch("osm_canvas.urlopen", return_value=response), patch.object(Path, "mkdir", side_effect=PermissionError("read only")):
                store.load((13, 4232, 2761), lambda key: True)
            self.assertEqual(store.results.get_nowait(), ((13, 4232, 2761), raw, None))
            store.close()

    def test_failed_visible_tiles_retry_without_panning(self):
        from unittest.mock import Mock
        due, recent, hidden = (13, 1, 1), (13, 1, 2), (13, 1, 3)
        canvas = SimpleNamespace(visible={due, recent}, failed={due: 0, recent: 95, hidden: 0}, store=SimpleNamespace(request=Mock()))
        with patch("osm_canvas.time.time", return_value=100):
            RouteMap.retry_failed_tiles(canvas)
        canvas.store.request.assert_called_once()
        self.assertEqual(canvas.store.request.call_args.args[0], due)
        self.assertFalse(canvas.store.request.call_args.args[1](hidden))


if __name__ == "__main__":
    unittest.main(verbosity=2)
