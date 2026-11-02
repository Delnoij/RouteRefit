# SPDX-License-Identifier: GPL-3.0-only
"""Desktop contract: independent settings, cancel/stale review, explicit commit and persistence."""
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
import werkbank as wb
from i18n import LANGUAGES,tr
from osm_canvas import TileStore
from test_access_review import road


def fields(rows):
    return [[(p.lat,p.lon,p.ele,p.time) for p in s] for s in rows]


def widgets(parent):
    for child in parent.winfo_children():
        yield child
        yield from widgets(child)


def dialog(app):
    return next(w for w in app.winfo_children() if isinstance(w,tk.Toplevel) and w.winfo_exists())


def press(window,label):
    next(w for w in widgets(window) if isinstance(w,ttk.Button) and w.cget('text')==tr(label)).invoke()


def stop_auto(app):
    if app.auto_timer:
        app.after_cancel(app.auto_timer)
        app.auto_timer=None


def main():
    TileStore.request=lambda *a:None
    with tempfile.TemporaryDirectory(dir=ROOT/'tests') as temp:
        folder=Path(temp)
        wb.DATA,wb.MAPS=folder/'data',folder/'maps'
        wb.DATA.mkdir();wb.MAPS.mkdir()
        source=folder/'source.gpx'
        raw=b'<gpx><trk><type>biking</type><trkseg><trkpt lat="50" lon="6.00001"><ele>12</ele><time>2026-01-01T00:00:00Z</time></trkpt><trkpt lat="50.001" lon="6.00001"><ele>15</ele><time>2026-01-01T00:01:00Z</time></trkpt><trkpt lat="50.002" lon="6.00001"><ele>19</ele><time>2026-01-01T00:02:00Z</time></trkpt></trkseg></trk></gpx>'
        source.write_bytes(raw)
        for code in LANGUAGES:
            app=wb.App(language=code)
            try:
                app.load(source,None,autoload_roads=False)
                assert app.transport.get()=='Fiets'
                app.roadmap=road()
                app.anchor_indices=[[0,1,2]]
                app.snapradius.set('5')
                stop_auto(app)
                app.job=lambda fn,done,message,**kw:done(fn())
                key=app.routing_key()
                before=fields(app.edit_segments)
                app.time_preset.set(tr('Sportief'))
                app.time_preset_changed()
                assert app.flat.get()=='27'
                assert app.routing_key()==key
                assert fields(app.edit_segments)==before
                app.calculate()
                assert app.candidate is not None and fields(app.edit_segments)==before
                assert len([w for w in app.winfo_children() if isinstance(w,tk.Toplevel)])==1
                press(dialog(app),'Annuleren')
                assert app.candidate is None and fields(app.edit_segments)==before
                app.start_auto_alignment()
                assert fields(app.edit_segments)==before
                press(dialog(app),'Annuleren')
                assert fields(app.edit_segments)==before
                app.start_auto_alignment()
                app.flat.set('23.4')  # review values are now stale
                press(dialog(app),'Voorstel overnemen')
                assert fields(app.edit_segments)==before
                app.start_auto_alignment()
                press(dialog(app),'Voorstel overnemen')
                assert fields(app.edit_segments)!=before
                assert app.auto_checked_key==app.routing_key()
                app.transport.set('MTB')
                app.transport_changed()
                stop_auto(app)
                assert app.flat.get()=='23.4'
                assert app.routing_style()=='mountainbike'
                assert app.auto_checked_key is None
                output=folder/f'settings-{code}.gpx'
                app.timing.set('model')
                app.target.set('01:23')
                app.start.set('2026-03-01 10:15')
                with patch.object(wb.filedialog,'asksaveasfilename',return_value=str(output)),patch.object(wb.messagebox,'showinfo'):
                    app.save()
                saved=json.loads(output.with_suffix('.controle.json').read_text(encoding='utf-8'))['settings']
                assert saved['transport']=='MTB' and saved['route_preference']=='Meest logisch'
                assert saved['timing_mode']=='model' and saved['flat_speed']==23.4
                app.load(output,None,autoload_roads=False)
                stop_auto(app)
                assert app.transport.get()=='MTB' and app.flat.get()=='23.4'
                assert app.timing.get()=='model' and app.target.get()=='01:23'
                assert app.start.get()=='2026-03-01 10:15'
                # The central time calculation also waits for explicit acceptance.
                app.snap.set(False)
                app.auto_mode.set(False)
                before=fields(app.edit_segments)
                app.calculate()
                assert app.candidate is not None and fields(app.edit_segments)==before
                press(dialog(app),'Annuleren')
                assert app.candidate is None and fields(app.edit_segments)==before
                app.calculate()
                press(dialog(app),'Voorstel overnemen')
                assert fields(app.edit_segments)!=before
                assert app.applied_time_estimates
                timed_output=folder/f'timed-{code}.gpx'
                with patch.object(wb.filedialog,'asksaveasfilename',return_value=str(timed_output)),patch.object(wb.messagebox,'showinfo'):
                    app.save()
                assert json.loads(timed_output.with_suffix('.controle.json').read_text(encoding='utf-8'))['settings']['estimated']
                app.undo()
                assert fields(app.edit_segments)==before
                assert not app.applied_time_estimates
                assert source.read_bytes()==raw
                print(f'{code}: separate transport/pace, review/cancel/stale/accept/undo and report migration passed.',flush=True)
            finally:
                app.destroy()


if __name__=='__main__':
    main()
