# SPDX-License-Identifier: GPL-3.0-only
"""Exercise real UI download entry points with a failed service and no retries."""
import sys, tempfile, time
from pathlib import Path
from unittest.mock import patch, Mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
import werkbank as wb
from osm_canvas import TileStore
from test_resilient_alignment import source, osm
from test_road_download import blocked
from road_transport import _cooldowns
from ui_simple_alignment import pump
from ui_profile_settings import fields, press, dialog
from resilient_alignment import PARTIAL_NOTICE


def settle(app):
    until=time.monotonic()+.4
    while time.monotonic()<until:
        app.update();time.sleep(.01)


def main():
    TileStore.request=lambda *a:None
    with tempfile.TemporaryDirectory(dir=ROOT/'tests') as temp:
        folder=Path(temp);wb.DATA=folder/'data';wb.DATA.mkdir()
        route=folder/'synthetic.gpx'
        raw=('<gpx><trk><type>cycling</type><trkseg>'+''.join(
            f'<trkpt lat="{p.lat}" lon="{p.lon}"><ele>{p.ele}</ele><time>{p.time.isoformat()}</time></trkpt>'
            for p in source()[0])+'</trkseg></trk></gpx>').encode()
        route.write_bytes(raw)
        for language in ('nl','en','de','fr','es','pt'):
            wb.MAPS=folder/language;(wb.MAPS/'Vakken').mkdir(parents=True)
            _cooldowns.clear();app=wb.App(language=language)
            try:
                app.load(route,None);app.update();app.anchor_indices=[list(range(5))]
                app.auto_mode.set(True);app.snap.set(True)
                before=fields(app.edit_segments);settings=app.settings_key()[1:]
                failed=Mock(side_effect=lambda *a,**kw:(_ for _ in ()).throw(blocked(503)))
                with patch.object(wb,'fetch',failed),patch.object(wb.messagebox,'askyesno',return_value=True):
                    app.get_map();token=app.road_loading
                    pump(app,lambda:app.road_loading is not None)
                    settle(app)
                    assert app.status.get().startswith('Wegdownload gestopt'),app.status.get()
                    assert failed.call_count==1
                    # A queued earlier progress update must not revive the status.
                    app.progress.put((token,'Weggegevens op achtergrond: 1/2'))
                    settle(app)
                    assert app.status.get().startswith('Wegdownload gestopt')
                    app.get_map();pump(app,lambda:app.road_loading is not None)
                    assert failed.call_count==1,'Cooldown must prevent even a manual early retry'
                    _cooldowns.clear()
                    old=wb.RoadMap(osm());app.roadmap=old
                    app.refresh_map();pump(app,lambda:app.road_loading is not None)
                    settle(app)
                    assert app.roadmap is old
                    assert app.status.get().startswith('Wegdownload gestopt')
                    assert failed.call_count==2
                    app.roadmap=None;_cooldowns.clear()
                    with patch.object(wb.messagebox,'showinfo') as info,patch.object(wb.messagebox,'showerror') as error:
                        app.automatic_button.invoke();pump(app,lambda:app.alignment_token is not None)
                        pump(app,lambda:app.enrichment_job['running'])
                        info.assert_not_called();error.assert_not_called()
                    settle(app);assert failed.call_count==3
                    assert not app.busy and app.alignment_token is None
                    # Same actual failure path with a usable partial local map.
                    _cooldowns.clear()
                    (wb.MAPS/'Vakken'/'5.99,49.99,6.01,50.009.osm').write_bytes(osm())
                    app.automatic_button.invoke();pump(app,lambda:app.alignment_token is not None)
                    pump(app,lambda:app.enrichment_job['running'])
                    assert failed.call_count==4
                    press(dialog(app),'Voorstel overnemen')
                    assert PARTIAL_NOTICE in app.auto_notes
                    app.undo()
                assert fields(app.edit_segments)==before
                assert app.settings_key()[1:]==settings
                assert route.read_bytes()==raw
                print(language+': one request per action; no countdown/retry; stopped status; cache, route, settings and undo preserved.',flush=True)
            finally:app.destroy();_cooldowns.clear()


if __name__=='__main__':main()
