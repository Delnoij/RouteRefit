# SPDX-License-Identifier: GPL-3.0-only
"""Real Tk file exports, timing selection, cancellation and stale-route guards."""
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import tkinter as tk
from tkinter import ttk

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
import werkbank as wb
from i18n import LANGUAGES, tr
from osm_canvas import TileStore
from file_export import FORMATS, show_file_export
from route_formats import tcx, kml
from ui_profile_settings import widgets, fields, press, dialog, stop_auto
from export_timing import LABELS


def choose(window, kind):
    next(w for w in widgets(window) if isinstance(w,ttk.Radiobutton) and w.cget('value') == kind).invoke()


def main():
    TileStore.request=lambda *a:None
    with tempfile.TemporaryDirectory(dir=ROOT/'tests') as temp:
        folder=Path(temp);wb.DATA=folder/'data';wb.MAPS=folder/'maps';wb.DATA.mkdir();wb.MAPS.mkdir()
        raw=b'<gpx><trk><trkseg><trkpt lat="50" lon="6"><ele>12</ele><time>2026-01-01T09:00:00Z</time></trkpt><trkpt lat="50.001" lon="6.001"><ele>16</ele><time>2026-01-01T09:01:00Z</time></trkpt></trkseg></trk></gpx>'
        source=folder/'source.gpx';source.write_bytes(raw)
        for code in LANGUAGES:
            app=wb.App(language=code);app.withdraw()
            errors=[];app.report_callback_exception=lambda kind,value,tb:errors.append(value)
            try:
                app.load(source,None,autoload_roads=False);stop_auto(app)
                app.job=lambda fn,done,msg,**kwargs:done(fn())
                before=(fields(app.edit_segments),app.settings_key(),app.dirty)
                app.file_export_button.invoke();window=dialog(app)
                assert window.title()==tr('Routebestand exporteren…')
                for kind in FORMATS:
                    choose(window,kind);target=folder/f'{code}.{kind.lower()}'
                    with patch.object(wb.filedialog,'asksaveasfilename',return_value=str(target)), patch('webbrowser.open') as browser:
                        press(window,'Bestand opslaan…');browser.assert_not_called()
                    assert target.exists(),(code,kind,errors)
                    parsed=wb.Track(target.read_bytes() if kind=='GPX' else {'TCX':tcx,'KML':kml}[kind](target.read_bytes(),'export'))
                    assert [[(p.lat,p.lon,p.ele) for p in s] for s in parsed.segments]==[[(p.lat,p.lon,p.ele) for p in s] for s in app.edit_segments]
                    assert before==(fields(app.edit_segments),app.settings_key(),app.dirty)
                with patch.object(wb.filedialog,'asksaveasfilename',return_value=''),patch('webbrowser.open') as browser:
                    press(window,'Bestand opslaan…');browser.assert_not_called()
                assert before==(fields(app.edit_segments),app.settings_key(),app.dirty)
                # Real calendar/time picker and confirmation generate a TCX course.
                choose(window,'TCX')
                next(w for w in widgets(window) if isinstance(w,ttk.Checkbutton)).invoke()
                press(window,'Bestand opslaan…')
                timing=next(w for w in app.winfo_children() if isinstance(w,tk.Toplevel) and w is not window)
                assert app.grab_current() is timing
                target=folder/f'{code}-adjusted.tcx'
                with patch.object(wb.messagebox,'askyesno',return_value=True),patch.object(wb.filedialog,'asksaveasfilename',return_value=str(target)):
                    next(w for w in widgets(timing) if isinstance(w,ttk.Button) and w.cget('text')==LABELS[code][6]).invoke()
                assert target.exists(),errors
                assert app.grab_current() is window
                assert before==(fields(app.edit_segments),app.settings_key(),app.dirty)
                # Cancelling the timing window returns focus without saving anything.
                press(window,'Bestand opslaan…')
                timing=next(w for w in app.winfo_children() if isinstance(w,tk.Toplevel) and w is not window)
                timing.destroy();assert app.grab_current() is window
                # An editor change invalidates the snapshot and blocks the chooser.
                app.edit_revision+=1
                with patch.object(wb.filedialog,'asksaveasfilename') as chooser,patch.object(wb.messagebox,'showinfo') as info:
                    press(window,'Bestand opslaan…');chooser.assert_not_called();info.assert_called_once()
                app.edit_revision-=1;window.destroy()
                # No usable times automatically opens the real timing form.
                for row in app.edit_segments:
                    for point in row:point.time=None
                window=show_file_export(app);choose(window,'TCX');press(window,'Bestand opslaan…')
                timing=next(w for w in app.winfo_children() if isinstance(w,tk.Toplevel) and w is not window)
                timing.destroy();window.destroy()
                # Unreviewed proposals cannot be exported as final navigation files.
                app.candidate=[list(s) for s in app.edit_segments];app.approved.set(False)
                with patch.object(wb.messagebox,'showinfo') as info:
                    assert show_file_export(app) is None;info.assert_called_once()
                assert source.read_bytes()==raw
                assert not errors,errors
                print(code+': GPX/TCX/KML, real TCX calendar, cancel, stale route and proposal guards passed; no upload or editor changes.',flush=True)
            finally:app.destroy()


if __name__=='__main__':main()
