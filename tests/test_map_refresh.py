# SPDX-License-Identifier: GPL-3.0-only
import sys, tempfile, unittest, copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import werkbank as wb
from gpx_core import Point, RoadMap, allowed


def osm(access):
    return (
        '<osm><node id="1" lat="50" lon="6"/><node id="2" lat="50.001" lon="6"/><way id="361609286"><nd ref="1"/><nd ref="2"/><tag k="highway" v="track"/>'
        + access
        + "</way></osm>"
    ).encode()


OLD = osm('<tag k="access" v="agricultural"/>')
NEW = osm('<tag k="motor_vehicle" v="agricultural"/>')


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temp.cleanup)
        self.maps = Path(self.temp.name)
        self.patch = patch.object(wb, "MAPS", self.maps)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.segments = [[Point(50, 6), Point(50.001, 6)]]

    def seed(self, segments=None):
        with patch.object(wb, "fetch", return_value=OLD), patch.object(wb.time, "sleep"):
            return wb.download_map(segments or self.segments)

    def test_ordinary_download_reuses_cache_without_network(self):
        p = self.seed()
        with patch.object(wb, "fetch", side_effect=AssertionError("network")):
            self.assertEqual(wb.download_map(self.segments), p)

    def test_refresh_bypasses_both_caches_and_updates_access(self):
        p = self.seed()
        self.assertFalse(allowed(RoadMap(p.read_bytes()).ways[0][1], "walk"))
        with patch.object(wb, "fetch", return_value=NEW) as fetch:
            self.assertEqual(wb.download_map(self.segments, refresh=True), p)
            self.assertTrue(fetch.call_args.kwargs["refresh"])
        self.assertTrue(allowed(RoadMap(p.read_bytes()).ways[0][1], "walk"))
        self.assertEqual(next((self.maps / "Vakken").glob("*.osm")).read_bytes(), NEW)
        with patch.object(wb, "fetch", side_effect=AssertionError("network")):
            self.assertTrue(
                allowed(RoadMap(wb.download_map(self.segments).read_bytes()).ways[0][1], "walk")
            )

    def test_partial_download_failure_keeps_all_old_cache_contents(self):
        segments = [[Point(50, 6), Point(50.021, 6)]]
        self.seed(segments)
        before = {p.relative_to(self.maps): p.read_bytes() for p in self.maps.rglob("*.osm")}
        with (
            patch.object(wb, "fetch", side_effect=[NEW, OSError("offline")]),
            patch.object(wb.time, "sleep"),
        ):
            with self.assertRaises(OSError):
                wb.download_map(segments, refresh=True)
        self.assertEqual(
            before, {p.relative_to(self.maps): p.read_bytes() for p in self.maps.rglob("*.osm")}
        )

    def test_invalid_response_never_replaces_saved_network(self):
        self.seed()
        before = {p: p.read_bytes() for p in self.maps.rglob("*.osm")}
        for response in [b"<html/>", b"<osm/>", b"not xml"]:
            with patch.object(wb, "fetch", return_value=response):
                with self.assertRaises(Exception):
                    wb.download_map(self.segments, refresh=True)
            self.assertTrue(all(p.read_bytes() == raw for p, raw in before.items()))

    def app(self):
        label = SimpleNamespace(value="")
        label.set = lambda text: setattr(label, "value", text)
        label.get = lambda: label.value
        app = SimpleNamespace(
            require_track=lambda: True,
            clear_access_reviews=lambda: None,
            busy=False,
            auto_timer=None,
            edit_segments=copy.deepcopy(self.segments),
            roadmap=RoadMap(OLD),
            auto_checked_key="previous",
            endpoint_edit_key="previous",
            endpoint_fully_checked=True,
            auto_mode=SimpleNamespace(get=lambda: True),
            profile=SimpleNamespace(get=lambda: "Fietsen · trekking"),
            routing_style=lambda: "trekking",
            snap=SimpleNamespace(get=lambda: True),
            mapinfo=label,
            status=Mock(),
            invalidate=Mock(),
            draw=Mock(),
            schedule_auto=Mock(),
            map_download_unavailable=Mock(),
        )
        app.set_map = lambda result: wb.App.set_map(app, result)
        app.job = lambda fn, done, message, **kwargs: done(fn())
        app.road_job = app.job
        return app

    def test_success_invalidates_old_checks_and_schedules_new_alignment(self):
        p = self.maps / "new.osm"
        p.write_bytes(NEW)
        app = self.app()
        before = copy.deepcopy(app.edit_segments)
        with patch.object(wb, "download_map", return_value=p) as download:
            wb.App.refresh_map(app)
            self.assertTrue(download.call_args.kwargs["refresh"])
        self.assertTrue(allowed(app.roadmap.ways[0][1], "walk"))
        self.assertIsNone(app.auto_checked_key)
        self.assertIsNone(app.endpoint_edit_key)
        self.assertFalse(app.endpoint_fully_checked)
        self.assertEqual(app.map_revision, 1)
        app.schedule_auto.assert_called_once()
        app.invalidate.assert_called_once()
        self.assertEqual(app.edit_segments, before)

    def test_failed_refresh_keeps_loaded_map_route_and_check_state(self):
        app = self.app()
        road = app.roadmap
        before = copy.deepcopy(app.edit_segments)
        with patch.object(wb, "download_map", side_effect=OSError("offline")):
            with self.assertRaises(OSError):
                wb.App.refresh_map(app)
        self.assertIs(app.roadmap, road)
        self.assertEqual(app.edit_segments, before)
        self.assertEqual(app.auto_checked_key, "previous")
        app.invalidate.assert_not_called()

    def test_http_refresh_requests_revalidation(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = NEW
        with patch.object(wb.urllib.request, "urlopen", return_value=response) as urlopen:
            self.assertEqual(
                wb.fetch(
                    "https://api.openstreetmap.org/api/0.6/map?bbox=6,50,6.1,50.1", refresh=True
                ),
                NEW,
            )
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Cache-control"), "no-cache")
        self.assertEqual(request.get_header("Pragma"), "no-cache")
