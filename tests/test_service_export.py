import sys
from pathlib import Path
import unittest
from datetime import datetime, timedelta, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from gpx_core import Point, Track
from service_export import navigation_gpx


class ServiceExportTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.points = [Point(50, 6, 100, self.start),
                       Point(50.001, 6.001, 101, self.start + timedelta(seconds=40))]

    def test_activity_preserves_adjusted_times(self):
        result = Track(navigation_gpx([self.points], True))
        self.assertEqual([p.time for p in result.segments[0]], [p.time for p in self.points])

    def test_navigation_removes_times_and_preserves_geometry(self):
        result = Track(navigation_gpx([self.points]))
        self.assertTrue(all(p.time is None for p in result.segments[0]))
        self.assertEqual([(p.lat,p.lon,p.ele) for p in result.segments[0]],
                         [(p.lat,p.lon,p.ele) for p in self.points])

    def test_missing_and_reversed_times_rejected(self):
        with self.assertRaises(ValueError): navigation_gpx([list(reversed(self.points))], True)
        with self.assertRaises(ValueError): navigation_gpx([[Point(50,6),Point(50.1,6)]], True)

    def test_segment_breaks_preserved(self):
        result = Track(navigation_gpx([self.points, self.points]))
        self.assertEqual(list(map(len,result.segments)), [2,2])

    def test_invalid_coordinates_rejected(self):
        with self.assertRaises(ValueError): navigation_gpx([[Point(float('nan'),6),Point(50,6)]])
