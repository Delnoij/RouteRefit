# SPDX-License-Identifier: GPL-3.0-only
"""Offline integration: accept access warnings, preserve all points, undo, export, reopen."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]
import werkbank as wb
from gpx_core import Track
from i18n import LANGUAGES
from osm_canvas import TileStore
from test_access_review import road


def main():
    TileStore.request = lambda *a: None
    with tempfile.TemporaryDirectory(dir=ROOT/'tests') as temp:
        folder = Path(temp)
        wb.DATA, wb.MAPS = folder/'data', folder/'maps'
        wb.DATA.mkdir()
        wb.MAPS.mkdir()
        source = folder/'source.gpx'
        raw = b'<gpx><trk><type>biking</type><trkseg><trkpt lat="50" lon="6"><ele>12</ele><time>2026-01-01T00:00:00Z</time></trkpt><trkpt lat="50.001" lon="6"><ele>15</ele><time>2026-01-01T00:01:00Z</time></trkpt><trkpt lat="50.002" lon="6"><ele>19</ele><time>2026-01-01T00:02:00Z</time></trkpt></trkseg></trk></gpx>'
        source.write_bytes(raw)
        for code in LANGUAGES:
            app = wb.App(language=code)
            try:
                app.load(source, None, autoload_roads=False)
                app.auto_mode.set(True)
                app.snapradius.set('5')
                app.roadmap = road('<tag k="bicycle" v="no"/>')
                app.anchor_indices = [[0, 1, 2]]
                if app.auto_timer:
                    app.after_cancel(app.auto_timer)
                    app.auto_timer = None
                app.job = lambda fn, done, message, **kwargs: done(fn())
                app.start_auto_alignment()
                assert app.auto_issues
                points = [list(s) for s in app.edit_segments]
                anchors = copy.deepcopy(app.anchor_indices)
                issues = copy.deepcopy(app.auto_issues)
                history_size = len(app.history)
                with patch('access_review_ui.messagebox.askyesno', return_value=False):
                    app.accept_access_issues()
                assert len(app.history) == history_size and app.auto_issues == issues
                with patch('access_review_ui.messagebox.askyesno', return_value=True):
                    app.accept_access_issues()
                assert app.edit_segments == points and not app.auto_issues, (app.busy, app.auto_checked_key, app.routing_key(), app.auto_issues, app.status.get())
                assert app.access_reviews and app.manual_sections
                app.undo()
                assert app.edit_segments == points and app.anchor_indices == anchors
                assert app.auto_issues == issues and not app.access_reviews and not app.manual_sections
                with patch('access_review_ui.messagebox.askyesno', return_value=True):
                    app.accept_access_issues()
                output = folder/f'access-{code}.gpx'
                with patch.object(wb.filedialog, 'asksaveasfilename', return_value=str(output)), patch.object(wb.messagebox, 'showinfo'):
                    app.save()
                report = json.loads(output.with_suffix('.controle.json').read_text(encoding='utf-8'))
                assert report['accepted_access_issues'][0]['geometry_changed'] is False
                assert report['accepted_access_issues'][0]['mode'] == 'bike'
                assert not report['pending_alignment_issues']
                assert any('Toegangsmeldingen' in note for note in report['warnings'])
                fields = lambda rows: [[(p.lat, p.lon, p.ele, p.time) for p in s] for s in rows]
                assert fields(Track(output.read_bytes()).segments) == fields(points)
                app.load(output, None, autoload_roads=False)
                assert app.access_reviews and app.manual_sections
                app.change_profile()
                assert app.access_reviews and app.manual_sections  # tempo changes are not access changes
                app.transport.set('Lopen')
                app.transport_changed()
                assert not app.access_reviews and not app.manual_sections
                assert source.read_bytes() == raw
                print(f'{code}: cancel, access review, unchanged geometry/elevation/times, undo, report, reopen and reset passed.', flush=True)
            finally:
                app.destroy()


if __name__ == '__main__':
    main()
