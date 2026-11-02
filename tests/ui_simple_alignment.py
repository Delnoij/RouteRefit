# SPDX-License-Identifier: GPL-3.0-only
"""One action per mode; anchor detours are replaced only after reviewing the result."""
import sys,tempfile,time,threading
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import tkinter as tk
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
import werkbank as wb
from osm_canvas import TileStore
from segment_join import average_speed
from ui_profile_settings import fields,press,dialog
from i18n import tr

def pump(app,condition,limit=6):
    until=time.monotonic()+limit
    while condition() and time.monotonic()<until:
        app.update();time.sleep(.01)
    assert not condition(),"Alignment task timed out"

def main():
    TileStore.request=lambda *a:None
    with tempfile.TemporaryDirectory(dir=ROOT/'tests') as temp:
        folder=Path(temp);wb.DATA=folder/'data';wb.MAPS=folder/'maps'
        wb.DATA.mkdir();wb.MAPS.mkdir()
        coords=[(49.9999,6),(50,6),(50.0005,6.002),(50.001,6.003),(50.0015,6.002),(50.002,6),(50.0021,6)]
        from datetime import datetime,timedelta,timezone
        start=datetime(2026,1,1,tzinfo=timezone.utc)
        raw=('<gpx><trk><type>walking</type><trkseg>'+''.join(f'<trkpt lat="{a}" lon="{b}"><ele>{100+i}</ele><time>{(start+timedelta(minutes=i)).isoformat()}</time></trkpt>' for i,(a,b) in enumerate(coords))+'</trkseg></trk></gpx>').encode()
        source=folder/'route.gpx';source.write_bytes(raw)
        osm=('<osm>'+''.join(f'<node id="{i}" lat="{a}" lon="6"/>' for i,a in enumerate([49.9999,50,50.001,50.002,50.0021]))+'<way id="1">'+''.join(f'<nd ref="{i}"/>' for i in range(5))+'<tag k="highway" v="path"/></way></osm>').encode()
        for code in ('nl','en','de','fr','es','pt'):
            app=wb.App(language=code)
            gate=threading.Event()
            try:
                with patch.object(wb,'download_map',side_effect=AssertionError('Opening must not download')):
                    app.load(source,None);app.update()
                app.roadmap=wb.RoadMap(osm)
                app.anchor_indices=[[0,1,3,5,6]]
                app.manual_button.invoke()
                assert app.mapmode.get()=='anchor' and not app.auto_mode.get()
                assert app.show_all_anchors.get()
                before=fields(app.edit_segments);speed=average_speed(app.edit_segments)
                app.edit_anchor(0,3,remove=True)
                assert fields(app.edit_segments)==before and not app.busy
                pump(app,lambda:app.alignment_token is not None)
                press(dialog(app),'Annuleren')
                assert fields(app.edit_segments)==before
                app.edit_anchor(0,3,remove=True)
                pump(app,lambda:app.alignment_token is not None)
                press(dialog(app),'Voorstel overnemen')
                assert all(p.lon==6 for p in app.edit_segments[0])
                assert len(app.anchor_indices[0])==4
                assert app.applied_time_estimates
                assert abs(average_speed(app.edit_segments)-speed)<1e-6
                app.undo();assert fields(app.edit_segments)==before
                assert not app.applied_time_estimates
                # Context menu exposes the exact anchor action and disables endpoints.
                app.draw();app.update()
                for index,disabled in [(3,False),(0,True)]:
                    x,y=app.canvas.pixel(app.edit_segments[0][index])
                    event=SimpleNamespace(x=x,y=y,x_root=100,y_root=100)
                    with patch.object(tk.Menu,'tk_popup'):
                        app.route_context_menu(event)
                    menu=app.route_popup
                    row=next(i for i in range(menu.index('end')+1) if menu.type(i)=='command' and tr('Hoofdpunt verwijderen en opnieuw verbinden') == str(menu.entrycget(i,'label')))
                    assert (str(menu.entrycget(row,'state'))=='disabled')==disabled
                app.automatic_button.invoke()
                assert not app.busy
                pump(app,lambda:app.alignment_token is not None)
                assert fields(app.edit_segments)==before
                press(dialog(app),'Annuleren')
                app.automatic_button.invoke()
                pump(app,lambda:app.alignment_token is not None)
                press(dialog(app),'Voorstel overnemen')
                assert app.auto_issues, 'Unresolved detours must stay marked after acceptance'
                assert app.mapmode.get() == app.canvas.mode == 'anchor'
                assert not app.auto_mode.get() and app.auto_timer is None
                assert app.canvas.controls == app.anchor_indices
                accepted=fields(app.edit_segments)
                # Continue straight from the accepted automatic proposal. No
                # toolbar mode or global alignment action is needed again.
                with patch.object(app,'start_auto_alignment',side_effect=AssertionError('Unexpected global alignment')):
                    detour=max(app.anchor_indices[0][1:-1],key=lambda i:app.edit_segments[0][i].lon)
                    app.edit_anchor(0,detour,remove=True)
                    pump(app,lambda:app.alignment_token is not None)
                    press(dialog(app),'Voorstel overnemen')
                    first_edit=fields(app.edit_segments)
                    assert first_edit != accepted and app.canvas.mode == 'anchor'
                    app.point_moved(0,app.anchor_indices[0][1],wb.Point(50.0002,6))
                    pump(app,lambda:app.alignment_token is not None)
                    press(dialog(app),'Voorstel overnemen')
                    assert fields(app.edit_segments) != first_edit
                    assert not app.auto_mode.get() and app.auto_timer is None
                    app.undo();assert fields(app.edit_segments)==first_edit
                    app.undo();assert fields(app.edit_segments)==accepted
                app.undo();assert fields(app.edit_segments)==before
                # Refreshing road data invalidates an in-flight result, even when
                # the editable line and vehicle settings stay unchanged.
                gate.clear();entered=threading.Event();engine=wb.automatic_alignment
                def waiting_engine(*a,**kw):
                    entered.set();gate.wait(5);return engine(*a,**kw)
                with patch.object(wb,'automatic_alignment',side_effect=waiting_engine):
                    app.automatic_button.invoke()
                    pump(app,lambda:not entered.is_set())
                    app.map_revision=getattr(app,"map_revision",0)+1
                    pump(app,lambda:app.alignment_token is not None)
                    gate.set()
                    for _ in range(20):app.update();time.sleep(.01)
                assert not any(isinstance(w,tk.Toplevel) for w in app.winfo_children())
                assert fields(app.edit_segments)==before
                # Switching modes immediately cancels an in-flight action.
                def stalled(*a,**kw):gate.wait(5);return wb.RoadMap(osm)
                with patch('alignment_workflow.road_for_section',side_effect=stalled):
                    app.automatic_button.invoke()
                    app.manual_button.invoke()
                    assert app.alignment_token is None
                    gate.set()
                    for _ in range(20):app.update();time.sleep(.01)
                assert not any(isinstance(w,tk.Toplevel) for w in app.winfo_children())
                assert fields(app.edit_segments)==before and source.read_bytes()==raw
                print(code+': two direct modes; remove entire detour; cancel/accept/undo; mean speed; context actions; cancel running work passed.',flush=True)
            finally:
                gate.set();app.destroy()

if __name__=='__main__':main()
