# SPDX-License-Identifier: GPL-3.0-only
"""Offline desktop integration: guide, invalidate, recalculate, save, undo, reopen."""

import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
import werkbank as wb
from test_segment_join import network
from gpx_core import Point, Track
from i18n import LANGUAGES, tr
from osm_canvas import RouteMap, TileStore
from segment_join import average_speed


def widgets(parent):
    for child in parent.winfo_children():
        yield child
        yield from widgets(child)


def main():
    TileStore.request = lambda *args: None
    raw = b"""<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><name>Synthetic gap</name><type>biking</type><trkseg><trkpt lat="50" lon="6"><time>2026-01-01T00:00:00Z</time></trkpt><trkpt lat="50.001" lon="6"><time>2026-01-01T00:01:00Z</time></trkpt></trkseg><trkseg><trkpt lat="50.002" lon="6"><time>2026-01-01T00:10:00Z</time></trkpt><trkpt lat="50.003" lon="6"><time>2026-01-01T00:11:00Z</time></trkpt></trkseg></trk></gpx>"""
    with tempfile.TemporaryDirectory(dir=ROOT / "tests") as temporary:
        folder = Path(temporary)
        wb.DATA = folder / "data"
        wb.MAPS = folder / "maps"
        wb.DATA.mkdir()
        wb.MAPS.mkdir()
        original = folder / "source.gpx"
        original.write_bytes(raw)
        for language in LANGUAGES:
            app = wb.App(language=language)
            try:
                app.withdraw()
                app.load(original, None, autoload_roads=False)
                app.auto_mode.set(False)
                app.roadmap = network()
                app.snapradius.set("5")
                if app.auto_timer:
                    app.after_cancel(app.auto_timer)
                    app.auto_timer = None

                def job(fn, done, message, on_error=None):
                    done(fn())

                app.job = job
                app.connection_editor(0)
                app.after(350, app.quit)
                app.mainloop()
                window = next(w for w in app.winfo_children() if isinstance(w, tk.Toplevel))
                preview = next(w for w in widgets(window) if isinstance(w, RouteMap))

                def button(text):
                    return next(
                        w
                        for w in widgets(window)
                        if isinstance(w, ttk.Button) and w.cget("text") == tr(text)
                    )

                accept = button("Verbinding overnemen")
                assert str(accept.cget("state")) == "normal"
                first_length = len(preview.proposal[0])
                preview.on_waypoint(Point(50.001, 6.003))
                preview.on_waypoint(Point(50.002, 6.003))
                assert str(accept.cget("state")) == "disabled"
                assert not preview.proposal
                button("Verbinding berekenen").invoke()
                assert len(preview.proposal[0]) > first_length
                preview.on_waypoint_move("1", Point(50.002, 6.0029))
                assert str(accept.cget("state")) == "disabled"
                button("Verbinding berekenen").invoke()
                accept.invoke()
                assert len(app.edit_segments) == 1
                assert app.segment_groups == [[0, 1]]
                assert len(app.joined_gaps[0]["via"]) == 2
                output = folder / f"joined-{language}.gpx"
                with (
                    patch.object(wb.filedialog, "asksaveasfilename", return_value=str(output)),
                    patch.object(wb.messagebox, "showinfo"),
                    patch.object(wb.messagebox, "showerror", side_effect=AssertionError),
                ):
                    app.save()
                assert output.is_file()
                assert len(Track(output.read_bytes()).segments) == 1
                report = json.loads(
                    output.with_suffix(".controle.json").read_text(encoding="utf-8")
                )
                assert report["reconstructed_gaps"][0]["recorded"] is False
                assert report["source_segment_groups"] == [[0, 1]]
                app.undo()
                assert len(app.edit_segments) == 2
                assert not app.joined_gaps
                app.load(output, None, autoload_roads=False)
                assert len(app.edit_segments) == 1
                assert len(app.joined_gaps) == 1
                assert app.segment_groups == [[0]]
                # Replace the manufactured detour, retaining the previous mean
                # speed and generating corresponding point timestamps.
                old_speed = average_speed(app.edit_segments)
                old_end = app.edit_segments[0][-1].time
                app.roadmap = network()
                app.snapradius.set("5")
                app.range_selection = (0, 1, len(app.edit_segments[0]) - 2)
                app.replace_range_with_via()
                app.after(350, app.quit)
                app.mainloop()
                window = next(w for w in app.winfo_children() if isinstance(w, tk.Toplevel))
                button("Gebruik dit voorstel").invoke()
                assert abs(average_speed(app.edit_segments) - old_speed) < 1e-6
                assert app.edit_segments[0][-1].time < old_end
                assert (
                    app.joined_gaps[-1]["time_status"]
                    == "estimated_distance_schedule_at_previous_average"
                )
                scheduled = folder / f"scheduled-{language}.gpx"
                with (
                    patch.object(wb.filedialog, "asksaveasfilename", return_value=str(scheduled)),
                    patch.object(wb.messagebox, "showinfo"),
                    patch.object(wb.messagebox, "showerror", side_effect=AssertionError),
                ):
                    app.save()
                scheduled_track = Track(scheduled.read_bytes())
                assert abs(average_speed(scheduled_track.segments) - old_speed) < 1e-5
                scheduled_report = json.loads(
                    scheduled.with_suffix(".controle.json").read_text(encoding="utf-8")
                )
                assert scheduled_report["settings"]["estimated"]
                print(
                    language
                    + ": via points, save/report, undo/reopen, replace detour and preserve average speed passed.",
                    flush=True,
                )
            finally:
                app.destroy()
        assert original.read_bytes() == raw


if __name__ == "__main__":
    main()
