# SPDX-License-Identifier: GPL-3.0-only
"""Real Tk: optional install, background cancellation and unchanged user work."""
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
import werkbank as wb
from i18n import LANGUAGES
from osm_canvas import TileStore
from test_region_packages import PackageTests,REGION
from region_packages import install_or_update,installed
from ui_profile_settings import fields


def pump(app,condition,timeout=15):
    end=time.monotonic()+timeout
    while condition():
        app.update();time.sleep(.01)
        if time.monotonic()>end:raise AssertionError('UI wait exceeded')
    app.update()


def main():
    TileStore.request=lambda *a:None
    for language in LANGUAGES:
        fixture=PackageTests();fixture.setUp()
        wb.DATA=fixture.folder/'data';wb.DATA.mkdir();wb.MAPS=fixture.maps
        source=fixture.folder/'route.gpx'
        source.write_text('<gpx><trk><type>walking</type><trkseg><trkpt lat="50" lon="6"/><trkpt lat="50.001" lon="6"/></trkseg></trk></gpx>')
        app=wb.App(language=language)
        try:
            app.load(source,None,autoload_roads=False);app.update()
            before=(fields(app.edit_segments),app.settings_key(),app.dirty,len(app.history))
            neighbour=dict(REGION,id='neighbour-region',name='Neighbour country',parent='Neighbourland')
            ui=app.packages;ui.regions=[dict(REGION,parent='Demonstratie'),neighbour];ui.show();app.update()
            ui.tree.selection_set(REGION['id'])
            app.update();ui.filter.set('Neighbour');app.update()
            ui.tree.selection_set(neighbour['id']);app.update()
            assert ui.selected_ids=={REGION['id'],neighbour['id']},'Search lost an earlier selected region'
            def install(folder,region,cancel,progress,full):
                return install_or_update(folder,region,cancel,progress,full,fetch=fixture.fetch)
            with patch('package_ui.install_or_update',side_effect=install):
                ui.selected();assert ui.running and not app.busy
                pump(app,lambda:ui.running)
                assert len(installed(wb.MAPS))==2
                assert ui.percent.get()==100
                assert ui.stop.winfo_rooty()+ui.stop.winfo_height()<ui.window.winfo_rooty()+ui.window.winfo_height(),'Controls clipped'
            prior=installed(wb.MAPS)[0]['snapshot'];entered=threading.Event()
            def slow(folder,region,cancel,progress,full):
                entered.set()
                while not cancel():time.sleep(.02)
                from package_index import PackageCancelled
                raise PackageCancelled()
            with patch('package_ui.install_or_update',side_effect=slow):
                ui.selected();pump(app,lambda:not entered.is_set())
                ui.stop_job();pump(app,lambda:ui.running)
                assert 'gestopt' in ui.message.get()
                assert installed(wb.MAPS)[0]['snapshot']==prior
            assert (fields(app.edit_segments),app.settings_key(),app.dirty,len(app.history))==before
            # Download optional: close manager, align entirely locally, no calls.
            ui.window.destroy();ui.window=None
            with patch.object(wb,'fetch',side_effect=AssertionError('Road download should not be needed')):
                app.automatic_button.invoke();pump(app,lambda:app.alignment_token is not None)
                assert not getattr(app,'enrichment_job',None)
            print(language,'package UI / stop / local alignment / user work preserved',flush=True)
        finally:app.destroy();fixture.doCleanups()


if __name__=='__main__':main()
