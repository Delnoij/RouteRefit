# SPDX-License-Identifier: GPL-3.0-only
"""Exercise native drawing, privacy flow, responsiveness and route preservation."""
from pathlib import Path
import sys,time
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
import werkbank as wb
from osm_canvas import TileStore
from i18n import LANGUAGES
from ui_profile_settings import fields
from ui_packages import pump
import test_region_packages as fixtures
from region_packages import custom_regions


def main():
    TileStore.request=lambda *a:None
    for language in LANGUAGES:
        f=fixtures.PackageTests();f.setUp();wb.DATA=f.folder/'data';wb.DATA.mkdir();wb.MAPS=f.maps
        app=wb.App(language=language)
        try:
            source=f.folder/'route.gpx';source.write_text('<gpx><trk><trkseg><trkpt lat="50" lon="6"/><trkpt lat="50.001" lon="6"/></trkseg></trk></gpx>')
            app.load(source,None,autoload_roads=False);app.update()
            before=(fields(app.edit_segments),app.settings_key(),app.dirty,len(app.history))
            ui=app.packages;ui.show();app.update();assert not ui.background.get()
            ui.draw_area();app.update();dialog=ui.area_dialog;map=dialog.map
            map.center=(50,6);map.zoom=12;map.render();app.update()
            map.event_generate('<ButtonPress-1>',x=100,y=80)
            map.event_generate('<B1-Motion>',x=400,y=210)
            map.event_generate('<ButtonRelease-1>',x=400,y=210);app.update()
            assert len(map.points)==4 and str(dialog.download['state'])=='normal'
            assert dialog.download.winfo_rooty()+dialog.download.winfo_height()<dialog.window.winfo_rooty()+dialog.window.winfo_height(),'Download button clipped'
            dialog.clear();dialog.mode.set('polygon');dialog.set_mode()
            for tick,(x,y) in enumerate([(100,80),(400,80),(350,210),(100,200)],10):
                map.event_generate('<ButtonPress-1>',x=x,y=y,time=tick*1000);map.event_generate('<ButtonRelease-1>',x=x,y=y,time=tick*1000+10)
            app.update();assert len(map.points)==4
            with patch.object(ui,'start') as start:
                dialog.submit();app.update();assert start.call_count==1
                region=start.call_args[0][0][0];assert region['provider']=='sliceosm'
            assert len(custom_regions(wb.MAPS))==1
            assert (fields(app.edit_segments),app.settings_key(),app.dirty,len(app.history))==before
            assert ui.background_check.winfo_rooty()+ui.background_check.winfo_height()<ui.window.winfo_rooty()+ui.window.winfo_height()
            print(language,'draw rectangle / polygon / saved selection / opt-in off / route unchanged',flush=True)
        finally:app.destroy();f.doCleanups()


if __name__=='__main__':main()
