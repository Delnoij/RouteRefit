import sys
from pathlib import Path
import unittest
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from gpx_core import Point,distance
from export_timing import prepare_activity

class ExportTimingTests(unittest.TestCase):
    def test_target_average_and_terrain_distribution(self):
        source = [[Point(50+i*.001,6,100+(i if i<5 else 10-i)*10) for i in range(11)]]
        for transport,speed in [('Lopen',4.5),('Fiets',20),('MTB',14)]:
            start=datetime(2026,6,1,8,tzinfo=timezone.utc)
            out,report=prepare_activity(source,transport,speed,start)
            elapsed=(out[-1][-1].time-out[0][0].time).total_seconds()
            self.assertAlmostEqual(report['distance_km']/elapsed*3600,speed,places=5)
            uphill=(out[0][2].time-out[0][1].time).total_seconds()
            downhill=(out[0][9].time-out[0][8].time).total_seconds()
            self.assertGreater(uphill,downhill)
            self.assertEqual(out[0][0].time,start)
            self.assertIsNone(source[0][0].time)

    def test_missing_elevations_and_unrealistic_speed_rejected(self):
        start=datetime(2026,6,1,tzinfo=timezone.utc)
        with self.assertRaises(ValueError):prepare_activity([[Point(50,6),Point(50.1,6)]],'Lopen',4,start)
        with self.assertRaises(ValueError):prepare_activity([[Point(50,6,10),Point(50.1,6,10)]],'Lopen',50,start)
