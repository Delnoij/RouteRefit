# SPDX-License-Identifier: GPL-3.0-only
"""Real Tk: six activities and official browser handoff, without any real uploads."""
import sys,tempfile,json
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
import werkbank as wb
from osm_canvas import TileStore
from i18n import LANGUAGES,tr
from profile_settings import TRANSPORTS
from navigation_upload import SERVICES,show_navigation_upload
from ui_profile_settings import fields,press,dialog

def main():
    TileStore.request=lambda *a:None
    with tempfile.TemporaryDirectory(dir=ROOT/'tests') as temp:
        folder=Path(temp);wb.DATA=folder/'data';wb.MAPS=folder/'maps';wb.DATA.mkdir();wb.MAPS.mkdir()
        source=folder/'source.gpx';raw=b'<gpx><trk><type>cycling</type><trkseg><trkpt lat="50" lon="6"><ele>12</ele></trkpt><trkpt lat="50.001" lon="6.001"><ele>16</ele></trkpt></trkseg></trk></gpx>';source.write_bytes(raw)
        for code in LANGUAGES:
            app=wb.App(language=code);app.withdraw()
            try:
                app.load(source,None,autoload_roads=False);app.job=lambda fn,done,msg,**kw:done(fn())
                before=fields(app.edit_segments)
                for activity in TRANSPORTS:
                    app.transport.set(activity);app.transport_changed();app.flat.set('80' if activity in ('Auto','Motor') else '5.4')
                    assert app.routing_mode()==TRANSPORTS[activity][0]
                    target=folder/f'{code}-{activity}.gpx'
                    with patch.object(wb.filedialog,'asksaveasfilename',return_value=str(target)),patch.object(wb.messagebox,'showinfo'):
                        app.save()
                    app.load(target,None,autoload_roads=False)
                    assert app.transport.get()==activity and fields(app.edit_segments)==before
                    assert float(app.flat.get())==(80 if activity in ('Auto','Motor') else 5.4)
                app.transport.set('Gravelfiets');app.transport_changed()
                snapshot=(fields(app.edit_segments),app.settings_key(),app.dirty)
                assert set(app.navigation_buttons)==set(SERVICES)
                for service in SERVICES:
                    app.navigation_buttons[service].invoke();window=dialog(app)
                    output=folder/f'{code}-{service}-nav.gpx'
                    with patch.object(wb.filedialog,'asksaveasfilename',return_value=str(output)),patch('webbrowser.open',return_value=True) as browser:
                        press(window,'GPX opslaan en uploadpagina openen')
                        browser.assert_called_once_with(SERVICES[service][1])
                    assert output.exists() and all(p.time is None for s in wb.Track(output.read_bytes()).segments for p in s)
                    assert snapshot==(fields(app.edit_segments),app.settings_key(),app.dirty)
                    window.destroy()
                # Cancelling the save chooser never opens a service or changes a route.
                window=show_navigation_upload(app,'Komoot')
                with patch.object(wb.filedialog,'asksaveasfilename',return_value=''),patch('webbrowser.open') as browser:
                    press(window,'GPX opslaan en uploadpagina openen');browser.assert_not_called()
                window.destroy()
                assert source.read_bytes()==raw
                print(code+': six activities persist; three navigation exports open only the official import page; cancel preserves data.',flush=True)
            finally:app.destroy()

if __name__=='__main__':main()
