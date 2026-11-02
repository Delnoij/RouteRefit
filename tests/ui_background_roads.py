# SPDX-License-Identifier: GPL-3.0-only
"""A deliberately stalled road service must never block manual editing."""
from pathlib import Path
import sys, tempfile, threading, time
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import werkbank as wb
from osm_canvas import TileStore

ROOT = Path(__file__).resolve().parents[1]
TileStore.request = lambda *args: None

def pump(app, condition, limit=3):
    end = time.monotonic() + limit
    while condition() and time.monotonic() < end:
        app.update()
        time.sleep(.01)
    assert not condition(), "Background operation did not finish"

with tempfile.TemporaryDirectory(dir=ROOT / "tests") as tmp:
    wb.DATA = Path(tmp) / "data"; wb.DATA.mkdir()
    wb.MAPS = Path(tmp) / "maps"; wb.MAPS.mkdir()
    for language in ("nl", "en", "de", "fr", "es", "pt"):
        app = wb.App(language=language)
        release = threading.Event()
        try:
            path = ROOT / "examples/demo.gpx"
            app.load(path, None, autoload_roads=False)
            app.auto_mode.set(False)
            original = path.read_bytes()
            finished, failed = Mock(), Mock()
            app.road_job(lambda: release.wait(10), finished, "Loading", on_error=failed)
            assert not app.busy
            token = app.road_loading
            app.road_job(lambda: None, Mock(), "Duplicate")
            assert app.road_loading is token
            app.mapmode.set("edit"); app.map_mode_changed()
            before = app.edit_segments[0][1]
            app.point_moved(0, 1, wb.Point(before.lat + .0001, before.lon))
            assert app.edit_segments[0][1].lat != before.lat
            assert not app.auto_mode.get()
            app.undo()
            assert app.edit_segments[0][1] == before
            # Even a completed download must defer to a running foreground calculation.
            app.busy = True
            release.set()
            for _ in range(25): app.update(); time.sleep(.01)
            finished.assert_not_called()
            assert app.busy
            app.busy = False
            pump(app, lambda: app.road_loading is not None)
            finished.assert_called_once()
            failed.assert_not_called()
            # An imported/newer map takes priority over an older background request.
            release.clear(); superseded = Mock()
            app.road_job(lambda: release.wait(10), superseded, "Loading")
            app.map_revision = getattr(app, "map_revision", 0) + 1
            release.set()
            pump(app, lambda: app.road_loading is not None)
            superseded.assert_not_called()
            # A late completion must never apply road data to a different open route.
            release.clear(); stale = Mock()
            app.road_job(lambda: release.wait(10), stale, "Loading")
            app.dirty = False
            app.load(path, None, autoload_roads=False)
            release.set()
            for _ in range(25): app.update(); time.sleep(.01)
            stale.assert_not_called()
            assert original == path.read_bytes()
            print(language + ": manual move/undo during stalled download, duplicate guard, foreground deferral and stale-route protection passed.")
        finally:
            release.set()
            app.destroy()
