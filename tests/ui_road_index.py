# SPDX-License-Identifier: GPL-3.0-only
"""Restart, offline indexed alignment, proposal cancellation/acceptance and undo."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
import werkbank as wb
from osm_canvas import TileStore
from ui_simple_alignment import pump
from ui_profile_settings import fields,press,dialog
from i18n import tr


def main():
    TileStore.request=lambda *a:None
    with tempfile.TemporaryDirectory(dir=ROOT/'tests') as temp:
        folder=Path(temp);wb.DATA=folder/'data';wb.MAPS=folder/'maps'
        wb.DATA.mkdir();(wb.MAPS/'Vakken').mkdir(parents=True)
        source=folder/'source.gpx'
        raw=b'<gpx><trk><type>walking</type><trkseg><trkpt lat="50" lon="6.00001"><ele>10</ele><time>2026-01-01T00:00:00Z</time></trkpt><trkpt lat="50.001" lon="6.00001"><ele>15</ele><time>2026-01-01T00:01:00Z</time></trkpt><trkpt lat="50.002" lon="6.00001"><ele>20</ele><time>2026-01-01T00:02:00Z</time></trkpt></trkseg></trk></gpx>'
        source.write_bytes(raw)
        osm=b'<osm><node id="1" lat="50" lon="6"/><node id="2" lat="50.001" lon="6"/><node id="3" lat="50.002" lon="6"/><way id="42"><nd ref="1"/><nd ref="2"/><nd ref="3"/><tag k="highway" v="path"/></way></osm>'
        (wb.MAPS/'Vakken'/'5.99,49.99,6.02,50.02.osm').write_bytes(osm)
        with patch.object(wb,'fetch',side_effect=AssertionError('offline alignment must not download')):
            for code in ('nl','en','de','fr','es','pt'):
                app=wb.App(language=code)
                try:
                    app.load(source,None);app.update()
                    app.transport.set('Lopen');app.transport_changed()
                    app.anchor_indices=[[0,1,2]];app.snapradius.set('10')
                    before=fields(app.edit_segments)
                    assert app.roadmap is None
                    app.automatic_button.invoke()
                    pump(app,lambda:app.alignment_token is not None)
                    assert fields(app.edit_segments)==before
                    assert hasattr(app.roadmap,'_index_generation')
                    assert ' Gegevens van ' in app.mapinfo.get()
                    assert road_date_visible(app.mapinfo.get())
                    press(dialog(app),'Annuleren')
                    assert fields(app.edit_segments)==before
                    loaded=app.roadmap
                    app.automatic_button.invoke()
                    pump(app,lambda:app.alignment_token is not None)
                    assert app.roadmap is loaded
                    press(dialog(app),'Voorstel overnemen')
                    assert fields(app.edit_segments)!=before
                    app.undo();assert fields(app.edit_segments)==before
                    assert source.read_bytes()==raw
                    assert (wb.MAPS/'Wegenindex'/'wegen.sqlite3').is_file()
                    print(code+': offline persistent index; preview/cancel/accept/undo; original retained passed.',flush=True)
                finally:app.destroy()


def road_date_visible(text):
    import re
    match = re.search(r'\b\d{2}-\d{2}-\d{4}\b', text)
    return match is not None and match.group() in tr(text)


if __name__=='__main__':main()
