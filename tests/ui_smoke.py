# SPDX-License-Identifier: GPL-3.0-only
"""Optional desktop checks in all six languages; uses synthetic data and no network."""

from pathlib import Path
import json
import sys
import tempfile
from types import SimpleNamespace
from dataclasses import replace
from tkinter import messagebox, ttk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import werkbank as wb
from i18n import LANGUAGES, tr
from osm_canvas import TileStore
from route_formats import read_route


def main():
    TileStore.request = lambda *args: None

    def error(title, message, **kwargs):
        raise AssertionError(f"{title}: {message}")

    messagebox.showerror = error
    with tempfile.TemporaryDirectory(dir=ROOT / "tests") as temporary:
        wb.DATA = Path(temporary) / "data"
        wb.DATA.mkdir()
        wb.MAPS = Path(temporary) / "maps"
        wb.MAPS.mkdir()

        def offline(*args, **kwargs):
            raise OSError("offline test")

        wb.download_map = offline
        for code in LANGUAGES:
            app = wb.App(language=code)
            try:

                def job(fn, done, message, on_error=None):
                    try:
                        done(fn())
                    except OSError as exc:
                        if on_error:
                            on_error(exc)
                        else:
                            raise

                app.job = job
                app.road_job = job
                app.load(ROOT / "examples/demo.gpx", None)
                assert app.track is not None
                assert app.roadmap is None
                assert "Route geopend" in app.status.get()
                app.auto_mode.set(False)
                app.show_statistics()
                app.update()
                app.refresh_statistics()
                assert app.profile_samples
                app.profile_hover(SimpleNamespace(x=app.elevation_canvas.winfo_width() / 2))
                assert app.elevation_canvas.find_withtag("hover")
                app.edit_segments[0][1] = replace(app.edit_segments[0][1], ele=150)
                app.geometry_changed("Synthetic elevation edit", automatic=False)
                assert app.metric_vars["Stijging"].get() == "50 m"
                app.statistics_source.set("Voorstel")
                app.refresh_statistics()
                assert app.statistics_note.get() == tr("Er is nog geen voorstel berekend.")
                app.statistics_source.set("Origineel")
                app.refresh_statistics()
                app.show_settings()
                app.update()
                # Notebook tab labels bypass the generic widget translation hook.
                assert app.tabs.tab(app.edit, "text") == tr("Route bewerken")
                assert app.tabs.tab(app.stats_tab, "text") == tr("Hoogteprofiel en statistieken")

                def widgets(parent):
                    for child in parent.winfo_children():
                        yield child
                        yield from widgets(child)

                app.transport.set("Lopen")
                app.transport_changed()
                profile = app.time_preset_box
                key = app.routing_key()
                profile.current(2)
                app.time_preset_changed()
                app.update()
                assert app.profile.get() == "Wandelen · stevig"
                assert app.routing_key() == key
                app.transport.set("Fiets")
                app.transport_changed()
                app.update()
                assert profile.get() == tr("Eigen snelheid")
                assert app.routing_mode() == "bike"
                app.geometry("1100x720")
                app.show_statistics()
                app.update()
                app.refresh_statistics()
                assert app.elevation_canvas.winfo_height() > 100
                assert app.profile_bounds[3] < app.elevation_canvas.winfo_height()
                app.toggle_map_focus()
                assert len(app.editor_panes.panes()) == 1
                adjusted = Path(temporary) / "comparison.gpx"
                adjusted.write_bytes(app.track.export(app.edit_segments))
                app.load_comparison(ROOT / "examples/demo.gpx", adjusted)
                app.update()
                assert app.mapmode.get() == "view"
                assert not app.auto_mode.get()
                assert not app.dirty
                assert app.canvas.original
                assert app.canvas.working
                assert not app.canvas.controls
                assert app.track.hash != read_route(adjusted).track.hash
                adjusted.with_suffix(".controle.json").write_text(
                    json.dumps(
                        {
                            "result_sha256": read_route(adjusted).track.hash,
                            "previous_sha256": read_route(ROOT / "examples/demo.gpx").track.hash,
                            "review_sections": [
                                {"title": "Synthetic crossing", "lat": 50.001, "lon": 6.001},
                                {"title": "Invalid coordinate", "lat": float("nan"), "lon": 6},
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                app.load_comparison(ROOT / "examples/demo.gpx", adjusted)
                assert len(app.comparison_spots) == 1
                assert "vorige versie" in app.pointinfo.get()
                app.show_changed_spot()
                assert "Synthetic crossing" in app.status.get()
                print(
                    f"{code}: import survives offline roads; profile, hover, language settings and resize passed.",
                    flush=True,
                )
            finally:
                app.destroy()


if __name__ == "__main__":
    main()
