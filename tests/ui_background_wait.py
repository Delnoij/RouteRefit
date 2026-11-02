# SPDX-License-Identifier: GPL-3.0-only
"""A valid response after 26.5 s must reach the cache while the preview stays usable."""
import sys,tempfile,time,threading
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
import werkbank as wb
from osm_canvas import TileStore
from test_resilient_alignment import source,osm
from ui_simple_alignment import pump
from ui_profile_settings import fields,press,dialog
from road_transport import _cooldowns,_slot
from local_first_ui import READY
from resilient_alignment import PARTIAL_NOTICE


def main():
    TileStore.request=lambda *a:None
    with tempfile.TemporaryDirectory(dir=ROOT/'tests') as temp:
        folder=Path(temp);wb.DATA=folder/'data';wb.DATA.mkdir();wb.MAPS=folder/'maps'
        (wb.MAPS/'Vakken').mkdir(parents=True)
        (wb.MAPS/'Vakken'/'5.99,49.99,6.01,50.009.osm').write_bytes(osm())
        route=folder/'synthetic.gpx'
        raw=('<gpx><trk><type>cycling</type><trkseg>'+''.join(
            f'<trkpt lat="{p.lat}" lon="{p.lon}"><ele>{p.ele}</ele><time>{p.time.isoformat()}</time></trkpt>'
            for p in source()[0])+'</trkseg></trk></gpx>').encode();route.write_bytes(raw)
        app=wb.App(language='nl');app.withdraw();release=threading.Event();calls=[];proposals=[]
        old_review=app.review_route_proposal
        def review(out,apply,**kwargs):proposals.append(kwargs.get('notes',[]));return old_review(out,apply,**kwargs)
        app.review_route_proposal=review
        def slow(url,**kwargs):
            calls.append(url);assert 0<kwargs['timeout']<=45
            if len(calls)==1:
                assert kwargs['timeout']==45
                release.wait(26.5)
            return osm()
        _cooldowns.clear()
        try:
            app.load(route,None);app.anchor_indices=[list(range(5))];app.update();before=fields(app.edit_segments)
            with patch.object(wb,'fetch',side_effect=slow):
                start=time.monotonic();app.automatic_button.invoke();pump(app,lambda:app.alignment_token is not None)
                preview=time.monotonic()-start
                assert preview<3 and PARTIAL_NOTICE in proposals[0]
                print(f'Local proposal: {preview:.3f} s; background request still running.',flush=True)
                while time.monotonic()-start<22:app.update();time.sleep(.01)
                assert app.enrichment_job['running'] and len(calls)==1 and len(proposals)==1
                assert fields(app.edit_segments)==before
                pump(app,lambda:app.enrichment_job['running'],limit=15)
                elapsed=time.monotonic()-start
                assert app.enrichment_message.get()==READY
                assert len(calls)==len(set(calls)),'No duplicate request permitted'
                assert len(proposals)==1 and fields(app.edit_segments)==before
                requests=len(calls)
                press(dialog(app),'Voorstel aanvullen');pump(app,lambda:app.alignment_token is not None)
                assert len(calls)==requests and PARTIAL_NOTICE not in proposals[-1]
                press(dialog(app),'Annuleren');assert fields(app.edit_segments)==before
                assert route.read_bytes()==raw
                print(f'Valid delayed reply accepted: {elapsed:.3f} s; explicit supplement; no retries; route preserved.',flush=True)
        finally:
            release.set();app.destroy();_cooldowns.clear();assert _slot.acquire(timeout=2);_slot.release()


if __name__=='__main__':main()
