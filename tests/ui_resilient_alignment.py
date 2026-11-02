# SPDX-License-Identifier: GPL-3.0-only
"""Real Tk workflow: offline partial proposal, undo, and no-cache preservation."""
import sys,tempfile,threading,time
from pathlib import Path
from unittest.mock import patch,Mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
import werkbank as wb
from osm_canvas import TileStore
from test_resilient_alignment import source,osm
from ui_simple_alignment import pump
from ui_profile_settings import fields,press,dialog
from resilient_alignment import PARTIAL_NOTICE, MISSING_ROADS
from road_download import RoadServiceUnavailable
from i18n import tr


def labels(widget):
    result=[]
    for child in widget.winfo_children():
        try:result.append(str(child.cget('text')))
        except Exception:pass
        result.extend(labels(child))
    return result


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
            tile=wb.MAPS/'Vakken'/'5.99,49.99,6.01,50.009.osm';tile.write_bytes(osm())
            app=wb.App(language=language)
            try:
                app.load(route,None);app.update();app.anchor_indices=[list(range(5))]
                before=fields(app.edit_segments)
                with patch('alignment_workflow.action_download',side_effect=RoadServiceUnavailable('offline')):
                    app.automatic_button.invoke();pump(app,lambda:app.alignment_token is not None)
                    window=dialog(app)
                    assert tr(PARTIAL_NOTICE) in '\n'.join(labels(window))
                    assert fields(app.edit_segments)==before
                    press(window,'Annuleren')
                    app.automatic_button.invoke();pump(app,lambda:app.alignment_token is not None)
                    press(dialog(app),'Voorstel overnemen')
                    assert app.auto_issues
                    assert PARTIAL_NOTICE in app.auto_notes
                    app.undo();assert fields(app.edit_segments)==before
                    wb.MAPS=folder/(language+'-empty');wb.MAPS.mkdir()
                    with patch.object(wb.messagebox,'showinfo') as info,patch.object(wb.messagebox,'showerror') as error:
                        app.automatic_button.invoke();pump(app,lambda:app.alignment_token is not None)
                        pump(app,lambda:app.enrichment_job['running'])
                        info.assert_not_called();error.assert_not_called()
                    assert fields(app.edit_segments)==before
                assert route.read_bytes()==raw
                print(language+': partial warning visible; cancel/accept/undo; missing roads remain unresolved; no-cache state preserves route.',flush=True)
            finally:app.destroy()

if __name__=='__main__':main()
