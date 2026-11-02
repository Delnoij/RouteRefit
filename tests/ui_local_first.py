# SPDX-License-Identifier: GPL-3.0-only
"""Real Tk local-first preview, independent downloads, explicit supplement and lifecycle."""
import sys,tempfile,time,threading
from pathlib import Path
from unittest.mock import patch,Mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
import werkbank as wb
import tkinter as tk
from tkinter import ttk
from osm_canvas import TileStore
from test_resilient_alignment import source,osm
from test_road_download import blocked
from ui_simple_alignment import pump
from ui_profile_settings import fields,press,dialog,widgets
from resilient_alignment import PARTIAL_NOTICE
from road_transport import _cooldowns,_slot
from local_first_ui import READY,FAILED,PARTLY_READY
from i18n import tr


def settle(app,seconds=.3):
    until=time.monotonic()+seconds
    while time.monotonic()<until:app.update();time.sleep(.01)


def button(window,label):
    return next(w for w in widgets(window) if isinstance(w,ttk.Button) and w.cget('text')==tr(label))


def main():
    TileStore.request=lambda *a:None
    with tempfile.TemporaryDirectory(dir=ROOT/'tests') as temp:
        folder=Path(temp);wb.DATA=folder/'data';wb.DATA.mkdir()
        route=folder/'synthetic.gpx'
        raw=('<gpx><trk><type>cycling</type><trkseg>'+''.join(
            f'<trkpt lat="{p.lat}" lon="{p.lon}"><ele>{p.ele}</ele><time>{p.time.isoformat()}</time></trkpt>'
            for p in source()[0])+'</trkseg></trk></gpx>').encode();route.write_bytes(raw)
        for language in ('nl','en','de','fr','es','pt'):
            wb.MAPS=folder/language;(wb.MAPS/'Vakken').mkdir(parents=True)
            (wb.MAPS/'Vakken'/'5.99,49.99,6.01,50.009.osm').write_bytes(osm())
            app=wb.App(language=language);gate=threading.Event();entered=threading.Event()
            proposals=[];original=app.review_route_proposal
            def review(out,apply,**kwargs):
                proposals.append((fields(out),kwargs.get('notes',[])));return original(out,apply,**kwargs)
            app.review_route_proposal=review
            def slow(*args,**kwargs):entered.set();gate.wait(5);return osm()
            try:
                app.load(route,None);app.update();app.anchor_indices=[list(range(5))]
                before=fields(app.edit_segments);_cooldowns.clear()
                with patch.object(wb,'fetch',side_effect=slow) as fetch:
                    start=time.monotonic();app.automatic_button.invoke();pump(app,lambda:app.alignment_token is not None)
                    assert time.monotonic()-start<3,'Local proposal waited for service'
                    window=dialog(app);snapshot=proposals[-1][0]
                    assert PARTIAL_NOTICE in proposals[-1][1]
                    assert app.enrichment_job['running'] and not app.busy
                    assert app.alignment_feedback.winfo_manager()==''
                    assert str(button(window,'Voorstel aanvullen').cget('state'))=='disabled'
                    pump(app,lambda:not entered.is_set());key=app.alignment_key()
                    gate.set();pump(app,lambda:app.enrichment_job['running'])
                    assert app.enrichment_message.get()==READY
                    assert app.alignment_key()==key and app.roadmap is None
                    assert len(proposals)==1 and proposals[0][0]==snapshot
                    assert fields(app.edit_segments)==before
                    requests=fetch.call_count
                    press(window,'Voorstel aanvullen');pump(app,lambda:app.alignment_token is not None)
                    assert fetch.call_count==requests,'Supplement must never trigger a retry'
                    assert len(proposals)==2 and PARTIAL_NOTICE not in proposals[-1][1]
                    press(dialog(app),'Voorstel overnemen');app.undo()
                    assert fields(app.edit_segments)==before

                # Missing every tile: no false proposal, then explicit local recompute.
                wb.MAPS=folder/(language+'-empty');wb.MAPS.mkdir();app.load(route,None)
                entered.clear();gate.clear();count=len(proposals)
                with patch.object(wb,'fetch',side_effect=slow),patch.object(wb.messagebox,'showinfo') as info,patch.object(wb.messagebox,'showerror') as error:
                    app.automatic_button.invoke();pump(app,lambda:app.alignment_token is not None)
                    assert len(proposals)==count and app.enrichment_job['running']
                    info.assert_not_called();error.assert_not_called()
                    gate.set();pump(app,lambda:app.enrichment_job['running'])
                    app.supplement_proposal();pump(app,lambda:app.alignment_token is not None)
                    press(dialog(app),'Annuleren')

                # A busy service ends in one attempt. No automatic retry countdown.
                wb.MAPS=folder/(language+'-failed');(wb.MAPS/'Vakken').mkdir(parents=True)
                (wb.MAPS/'Vakken'/'5.99,49.99,6.01,50.009.osm').write_bytes(osm())
                app.load(route,None);app.anchor_indices=[list(range(5))];_cooldowns.clear()
                with patch.object(wb,'fetch',side_effect=blocked(503)) as fetch:
                    app.automatic_button.invoke();pump(app,lambda:app.alignment_token is not None)
                    pump(app,lambda:app.enrichment_job['running']);settle(app)
                    assert fetch.call_count==1 and app.enrichment_message.get().startswith(FAILED)
                    assert 'De wegendienst is tijdelijk niet beschikbaar.' in app.enrichment_message.get()
                    assert fields(app.edit_segments)==before
                    press(dialog(app),'Annuleren')

                # Route/settings changes cancel a pending download and reject late results.
                _cooldowns.clear();entered.clear();gate.clear()
                with patch.object(wb,'fetch',side_effect=slow) as fetch:
                    app.automatic_button.invoke();pump(app,lambda:app.alignment_token is not None)
                    pump(app,lambda:not entered.is_set())
                    app.flat.set('19');pump(app,lambda:app.enrichment_job is not None)
                    gate.set();settle(app)
                    assert fetch.call_count==1 and app.roadmap is None
                    assert fields(app.edit_segments)==before
                    dialog(app).destroy()
                assert route.read_bytes()==raw
                print(language+': fast local preview; background success/failure; explicit supplement; no implicit route changes; stale results rejected; undo preserved.',flush=True)
            finally:
                gate.set();app.destroy();_cooldowns.clear()
                assert _slot.acquire(timeout=2);_slot.release()


if __name__=='__main__':main()
