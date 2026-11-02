# SPDX-License-Identifier: GPL-3.0-only
"""Accept, stop, route switch, partial downloads and close during background work."""
import sys,tempfile,threading
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
import werkbank as wb
from osm_canvas import TileStore
from test_resilient_alignment import source,osm
from test_road_download import blocked
from ui_simple_alignment import pump
from ui_profile_settings import fields,press,dialog
from ui_local_first import settle
from road_transport import _cooldowns,_slot
from local_first_ui import READY,PARTLY_READY
from resilient_alignment import PARTIAL_NOTICE


def main():
    TileStore.request=lambda *a:None
    with tempfile.TemporaryDirectory(dir=ROOT/'tests') as temp:
        folder=Path(temp);wb.DATA=folder/'data';wb.DATA.mkdir()
        route=folder/'synthetic.gpx'
        raw=('<gpx><trk><type>cycling</type><trkseg>'+''.join(
            f'<trkpt lat="{p.lat}" lon="{p.lon}"><ele>{p.ele}</ele><time>{p.time.isoformat()}</time></trkpt>'
            for p in source()[0])+'</trkseg></trk></gpx>').encode();route.write_bytes(raw)
        for case in ('accept','stop','switch','partial','close'):
            wb.MAPS=folder/case;(wb.MAPS/'Vakken').mkdir(parents=True)
            (wb.MAPS/'Vakken'/'5.99,49.99,6.01,50.009.osm').write_bytes(osm())
            old_tiles={p:p.read_bytes() for p in wb.MAPS.rglob('*.osm')}
            app=wb.App(language='nl');gate=threading.Event();entered=threading.Event();closed=False
            def slow(*args,**kwargs):entered.set();gate.wait(5);return osm()
            app.load(route,None);app.anchor_indices=[list(range(5))];before=fields(app.edit_segments)
            _cooldowns.clear()
            try:
                effect=[osm(),blocked(503)] if case=='partial' else slow
                with patch.object(wb,'fetch',side_effect=effect) as fetch:
                    app.automatic_button.invoke();pump(app,lambda:app.alignment_token is not None)
                    window=dialog(app)
                    if case!='partial':pump(app,lambda:not entered.is_set())
                    if case=='accept':
                        press(window,'Voorstel overnemen')
                        accepted=fields(app.edit_segments);revision=app.edit_revision
                        assert app.enrichment_job['running']
                        gate.set();pump(app,lambda:app.enrichment_job['running'])
                        assert app.enrichment_message.get()==READY
                        assert fields(app.edit_segments)==accepted and app.edit_revision==revision
                        app.undo();settle(app);assert fields(app.edit_segments)==before
                    elif case=='stop':
                        press(window,'Download stoppen');assert app.enrichment_job is None
                        gate.set();settle(app,.5);assert fields(app.edit_segments)==before
                        assert {p:p.read_bytes() for p in wb.MAPS.rglob('*.osm')}==old_tiles
                        press(window,'Annuleren')
                    elif case=='switch':
                        app.load(route,None);window.destroy();gate.set();settle(app,.5)
                        assert app.enrichment_job is None and app.roadmap is None
                        assert fields(app.edit_segments)==before
                    elif case=='partial':
                        pump(app,lambda:app.enrichment_job['running'])
                        assert fetch.call_count==2 and app.enrichment_message.get().startswith(PARTLY_READY)
                        press(window,'Voorstel aanvullen');pump(app,lambda:app.alignment_token is not None)
                        assert fetch.call_count==2,'Partial supplement must not retry online'
                        press(dialog(app),'Voorstel overnemen')
                        assert PARTIAL_NOTICE in app.auto_notes
                        app.undo();assert fields(app.edit_segments)==before
                    else:
                        app.destroy();closed=True;gate.set()
                    if case!='partial':assert fetch.call_count>=1
                assert route.read_bytes()==raw
                print(case+': lifecycle and route preservation passed.',flush=True)
            finally:
                gate.set()
                if not closed:app.destroy()
                assert _slot.acquire(timeout=2);_slot.release();_cooldowns.clear()


if __name__=='__main__':main()
