# SPDX-License-Identifier: GPL-3.0-only
"""Visible heartbeat and stop during a worker that cannot predict its duration."""
import sys,time,tempfile,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
import werkbank as wb
from i18n import LANGUAGES
from osm_canvas import TileStore


def main():
    TileStore.request=lambda *a:None
    with tempfile.TemporaryDirectory(dir=ROOT/'tests') as temp:
        folder=Path(temp);wb.DATA=folder/'data';wb.MAPS=folder/'maps'
        wb.DATA.mkdir();wb.MAPS.mkdir()
        for code in LANGUAGES:
            app=wb.App(language=code);gate=threading.Event();entered=threading.Event();done=[]
            def work(cancel,emit):
                emit('Weggegevens gereed. Route uitlijnen…');entered.set();gate.wait(5);return True
            try:
                app.alignment_task(work,done.append,'Automatisch uitlijnen gestart. Dit kan even duren; je route blijft behouden.')
                app.update()
                stop = next(child for child in app.alignment_feedback.winfo_children()
                            if child.winfo_class() == 'TButton')
                assert stop.winfo_ismapped()
                assert stop.winfo_x() >= 0
                assert stop.winfo_x()+stop.winfo_width() <= app.alignment_feedback.winfo_width()
                start=time.monotonic()
                while time.monotonic()-start<1.2:app.update();time.sleep(.01)
                assert entered.is_set() and app.alignment_feedback.winfo_ismapped()
                assert '00:01' in app.alignment_elapsed.get()
                assert 'uitlijnen' in app.alignment_phase.get()
                assert app.alignment_token is not None and not app.busy
                app.stop_alignment();app.update()
                assert not app.alignment_feedback.winfo_ismapped()
                gate.set()
                for _ in range(20):app.update();time.sleep(.01)
                assert not done and app.alignment_token is None
                print(code+': visible elapsed time, animated indicator, active phase and stop passed.',flush=True)
            finally:gate.set();app.destroy()


if __name__=='__main__':main()
