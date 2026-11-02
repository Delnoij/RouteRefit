# SPDX-License-Identifier: GPL-3.0-only
import sys,tempfile,unittest,json
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from gpx_core import Point,Track
from navigation_upload import write_navigation_export,SERVICES

class NavigationUploadTests(unittest.TestCase):
    def test_each_service_gets_navigable_track_without_recording_times(self):
        rows=[[Point(50,6,10,datetime(2026,1,1,tzinfo=timezone.utc)),Point(50.001,6.001,20)]]
        with tempfile.TemporaryDirectory() as folder:
            for service in SERVICES:
                path=write_navigation_export(Path(folder)/(service+'.gpx'),rows,'Gravelfiets',service)
                track=Track(path.read_bytes())
                self.assertEqual([(p.lat,p.lon,p.ele) for p in track.segments[0]],[(p.lat,p.lon,p.ele) for p in rows[0]])
                self.assertTrue(all(p.time is None for p in track.segments[0]))
                self.assertFalse(json.loads(path.with_suffix('.export.json').read_text())['uploaded'])
                before=path.read_bytes()
                with self.assertRaises(FileExistsError):write_navigation_export(path,rows,'Fiets',service)
                self.assertEqual(path.read_bytes(),before)

if __name__=='__main__':unittest.main()
