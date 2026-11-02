# SPDX-License-Identifier: GPL-3.0-only
"""Adopt times, keep manual corrections, and resume a saved route without routing."""
import json
import sys
import tempfile
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
import werkbank as wb
from i18n import LANGUAGES,tr
from osm_canvas import TileStore
from test_access_review import road
from ui_profile_settings import fields,press,dialog,widgets


def geometry(rows):
    return [[(p.lat,p.lon,p.ele) for p in s] for s in rows]


def main():
    TileStore.request=lambda *a:None
    with tempfile.TemporaryDirectory(dir=ROOT/'tests') as temp:
        folder=Path(temp);wb.DATA=folder/'data';wb.MAPS=folder/'maps'
        wb.DATA.mkdir();wb.MAPS.mkdir()
        source=folder/'source.gpx'
        raw=b'<gpx><trk><type>walking</type><trkseg><trkpt lat="50" lon="6"><ele>10</ele><time>2026-01-01T10:00:00Z</time></trkpt><trkpt lat="50.001" lon="6.001"><ele>20</ele><time>2026-01-01T10:01:00Z</time></trkpt><trkpt lat="50.002" lon="6"><ele>15</ele><time>2026-01-01T10:02:00Z</time></trkpt></trkseg></trk></gpx>'
        source.write_bytes(raw)
        for code in LANGUAGES:
            app=wb.App(language=code)
            try:
                app.load(source,None,autoload_roads=False)
                app.job=lambda fn,done,message,**kw:done(fn())
                app.snap.set(True)
                app.timing.set('model');app.flat.set('5.4')
                app.start.set('2026-11-02 11:30')
                # The visible radio is available without the automatic button.
                def choose(label):
                    next(w for w in widgets(app) if isinstance(w,ttk.Radiobutton)
                         and w.cget('text')==tr(label)).invoke()
                choose('Losse punten')
                app.point_moved(0,1,wb.Point(50.0012,6.0015))
                manual=fields(app.edit_segments);line=geometry(app.edit_segments)
                with patch.object(app,'start_auto_alignment',side_effect=AssertionError('Unexpected global alignment')), \
                     patch.object(wb,'download_map',side_effect=AssertionError('Timing must work offline')), \
                     patch.object(wb.RoadMap,'snap',side_effect=AssertionError('Timing must preserve manual geometry')):
                    for have_roads in (False,True):
                        app.roadmap=road() if have_roads else None
                        app.calculate()
                        assert fields(app.edit_segments)==manual
                        assert geometry(app.candidate)==line
                        assert app.result_info['preserved_existing_route']
                        assert not app.result_info['snapped']
                        press(dialog(app),'Annuleren')
                        assert fields(app.edit_segments)==manual
                    app.calculate();press(dialog(app),'Voorstel overnemen')
                    assert geometry(app.edit_segments)==line
                    assert fields(app.edit_segments)!=manual
                    assert app.canvas.mode==app.mapmode.get()=='edit'
                    assert not app.auto_mode.get() and app.auto_timer is None
                    timed=fields(app.edit_segments)
                    app.point_moved(0,1,wb.Point(50.0013,6.0016))
                    assert fields(app.edit_segments)!=timed
                    app.undo();assert fields(app.edit_segments)==timed
                    output=folder/f'manual-{code}.gpx'
                    with patch.object(wb.filedialog,'asksaveasfilename',return_value=str(output)),patch.object(wb.messagebox,'showinfo'):
                        app.save()
                    assert json.loads(output.with_suffix('.controle.json').read_text(encoding='utf-8'))['settings']['editor_mode']=='edit'
                    app.load(output,None,autoload_roads=False)
                    assert geometry(app.edit_segments)==line
                    assert all(abs((p.time-old[3]).total_seconds())<.001
                               for seg,old_seg in zip(app.edit_segments,timed)
                               for p,old in zip(seg,old_seg))
                    timed=fields(app.edit_segments)  # GPX stores millisecond precision.
                    assert app.mapmode.get()==app.canvas.mode=='edit'
                    assert app.flat.get()=='5.4' and app.start.get()=='2026-11-02 11:30'
                    assert app.canvas.controls==app.anchor_indices
                    app.point_moved(0,1,wb.Point(50.0014,6.0017))
                    assert fields(app.edit_segments)!=timed
                    app.undo();assert fields(app.edit_segments)==timed
                    choose('Hoofdpunten')
                    assert app.canvas.mode=='anchor' and app.canvas.controls==app.anchor_indices
                assert source.read_bytes()==raw
                print(code+': direct manual edits, timing preserves geometry offline, cancel/accept/undo and save/reopen passed.',flush=True)
            finally:
                app.destroy()


if __name__=='__main__':main()
