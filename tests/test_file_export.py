# SPDX-License-Identifier: GPL-3.0-only
import sys
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from file_export import FORMATS, TCX_NS, KML_NS, navigation_file, usable_times, write_file_export
from gpx_core import Point, Track, distance
from route_formats import tcx, kml
from export_timing import prepare_activity


def route():
    start = datetime(2026, 1, 1, 10, tzinfo=timezone(timedelta(hours=1)))
    return [[Point(50, 6, 15, start), Point(50.001, 6.001, 18, start + timedelta(minutes=1))],
            [Point(51, 7, None, start + timedelta(minutes=2)), Point(51.001, 7.001, 24, start + timedelta(minutes=3))]]


class FileExportTests(unittest.TestCase):
    def test_round_trip_geometry_elevation_segments_and_times(self):
        rows = route()
        for kind in FORMATS:
            raw = navigation_file(rows, kind)
            parsed = Track(raw if kind == 'GPX' else {'TCX': tcx, 'KML': kml}[kind](raw, 'export'))
            self.assertEqual([[(p.lat,p.lon,p.ele) for p in s] for s in parsed.segments],
                             [[(p.lat,p.lon,p.ele) for p in s] for s in rows])
            self.assertEqual([[p.time for p in s] for s in parsed.segments],
                             [[p.time if kind == 'TCX' else None for p in s] for s in rows])

    def test_tcx_course_times_and_distance_do_not_bridge_gaps(self):
        rows = route(); root = ET.fromstring(navigation_file(rows, 'TCX'))
        ns = {'t': TCX_NS}
        self.assertIsNone(root.find('t:Activities', ns))
        tracks = root.findall('t:Courses/t:Course/t:Track', ns)
        self.assertEqual(len(tracks), 2)
        points = root.findall('.//t:Trackpoint', ns)
        metres = [float(p.findtext('t:DistanceMeters', namespaces=ns)) for p in points]
        self.assertAlmostEqual(metres[-1], sum(distance(s[0], s[1]) for s in rows), places=3)
        self.assertEqual(metres[1], metres[2])
        self.assertEqual(points[0].findtext('t:Time', namespaces=ns), '2026-01-01T09:00:00Z')
        for point in points:
            names = [p.tag.split('}')[-1] for p in point]
            self.assertEqual(names[:2], ['Time', 'Position'])
            self.assertEqual(names[-1], 'DistanceMeters')

    def test_adjusted_tcx_times_and_average_are_retained(self):
        rows = route()[:1]
        adjusted, report = prepare_activity(rows, 'Lopen', 4.2, rows[0][0].time)
        result = Track(tcx(navigation_file(adjusted, 'TCX'), 'adjusted'))
        self.assertEqual([p.time for p in result.segments[0]], [p.time for p in adjusted[0]])
        elapsed = (result.segments[0][-1].time - result.segments[0][0].time).total_seconds()
        self.assertAlmostEqual(distance(*result.segments[0]) / elapsed * 3.6, 4.2, places=5)
        self.assertTrue(report['estimated'])

    def test_kml_coordinate_order_and_missing_elevation(self):
        root = ET.fromstring(navigation_file(route(), 'KML'))
        ns = {'k': KML_NS}
        lines = root.findall('.//k:LineString', ns)
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0].findtext('k:coordinates', namespaces=ns).split()[0], '6,50,15')
        self.assertEqual(lines[1].findtext('k:coordinates', namespaces=ns).split()[0], '7,51')
        self.assertFalse(root.findall('.//k:NetworkLink', ns))
        self.assertFalse(root.findall('.//k:TimeStamp', ns))

    def test_no_source_metadata_and_no_input_mutation(self):
        rows = route()
        rows[0][0].element = ET.fromstring('<trkpt><desc>private note</desc><extensions>sensor</extensions></trkpt>')
        snapshot = repr(rows)
        for kind in FORMATS:
            raw = navigation_file(rows, kind)
            self.assertNotIn(b'private note', raw)
            self.assertNotIn(b'sensor', raw)
            self.assertEqual(snapshot, repr(rows))

    def test_invalid_coordinates_and_times_do_not_create_files(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            for kind in FORMATS:
                for lat,lon in [(float('nan'),6),(50,float('inf')),(91,6),(50,181)]:
                    rows = route(); rows[0][0].lat,rows[0][0].lon = lat,lon
                    with self.assertRaises(ValueError):
                        write_file_export(Path(temp)/('route.'+kind.lower()), rows, 'Fiets', kind)
            self.assertFalse(list(Path(temp).iterdir()))
        for replacement in (None, datetime(2026,1,1), route()[0][0].time - timedelta(days=1)):
            rows = route(); rows[0][1].time = replacement
            self.assertFalse(usable_times(rows))
            with self.assertRaises(ValueError): navigation_file(rows, 'TCX')
            self.assertTrue(navigation_file(rows, 'GPX'))
            self.assertTrue(navigation_file(rows, 'KML'))

    def test_all_formats_coexist_and_never_overwrite(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            for kind in FORMATS:
                path = Path(temp)/('route.'+kind.lower())
                write_file_export(path, route(), 'Fiets', kind)
                before = path.read_bytes()
                self.assertFalse(json.loads(path.with_name(path.name+'.export.json').read_text())['uploaded'])
                with self.assertRaises(FileExistsError): write_file_export(path, route(), 'Fiets', kind)
                self.assertEqual(before,path.read_bytes())
            self.assertEqual(len(list(Path(temp).iterdir())), 6)

    def test_existing_report_and_write_failure_preserve_existing_files(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            path = Path(temp)/'route.kml'; report = path.with_name(path.name+'.export.json')
            report.write_bytes(b'keep')
            with self.assertRaises(FileExistsError): write_file_export(path, route(), 'Fiets', 'KML')
            self.assertFalse(path.exists()); self.assertEqual(report.read_bytes(),b'keep')
            # A competing writer creates the report after the initial exists check.
            original_exists = Path.exists
            with patch.object(Path, 'exists', lambda p: False if p == report else original_exists(p)):
                with self.assertRaises(FileExistsError): write_file_export(path, route(), 'Fiets', 'KML')
            self.assertFalse(path.exists()); self.assertEqual(report.read_bytes(),b'keep')

    def test_suffix_empty_singleton_and_dateline(self):
        with self.assertRaises(ValueError): write_file_export('route.gpx', route(), 'Fiets', 'TCX')
        for kind in FORMATS:
            with self.assertRaises(ValueError): navigation_file([[]], kind)
        rows = route(); rows[1] = rows[1][:1]
        with self.assertRaises(ValueError): navigation_file(rows, 'KML')
        self.assertTrue(navigation_file(rows, 'TCX'))
        self.assertTrue(navigation_file(rows, 'GPX'))
        rows[0][0].lon = 180
        root = ET.fromstring(navigation_file(rows, 'TCX'))
        self.assertEqual(root.findtext('.//{'+TCX_NS+'}LongitudeDegrees'), '-180.0')


if __name__ == '__main__': unittest.main()
