# SPDX-License-Identifier: GPL-3.0-only
import io
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src")]
tempfile.tempdir = str(ROOT / "tests")
from route_formats import read_route
from gpx_core import Track

KML = b'<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><name>Test</name><LineString><coordinates>6,50,100 6.001,50.001,120</coordinates></LineString></Placemark><Placemark><name>Top</name><Point><coordinates>6.001,50.001,120</coordinates></Point></Placemark></Document></kml>'
TCX = b"<TrainingCenterDatabase><Courses><Course><Track><Trackpoint><Time>2026-01-01T08:00:00Z</Time><Position><LatitudeDegrees>50</LatitudeDegrees><LongitudeDegrees>6</LongitudeDegrees></Position><AltitudeMeters>100</AltitudeMeters></Trackpoint><Trackpoint><Time>2026-01-01T08:01:00Z</Time><Position><LatitudeDegrees>50.001</LatitudeDegrees><LongitudeDegrees>6.001</LongitudeDegrees></Position><AltitudeMeters>120</AltitudeMeters></Trackpoint></Track></Course></Courses></TrainingCenterDatabase>"
GEO = b'{"type":"FeatureCollection","features":[{"type":"Feature","properties":{},"geometry":{"type":"MultiLineString","coordinates":[[[6,50,100],[6.001,50.001,120]],[[7,51,200],[7.001,51.001,210]]]}},{"type":"Feature","properties":{"name":"Top"},"geometry":{"type":"Point","coordinates":[6,50,100]}}]}'


def crc(raw):
    result = 0
    for byte in raw:
        result ^= byte
        for _ in range(8):
            result = (result >> 1) ^ 0xA001 if result & 1 else result >> 1
    return result


def sample_fit():
    # FIT global record 20: timestamp(uint32), lat/lon(sint32), altitude(uint16).
    data = (
        b"\x40\x00\x00"
        + struct.pack("<H", 20)
        + b"\x04"
        + bytes([253, 4, 0x86, 0, 4, 0x85, 1, 4, 0x85, 2, 2, 0x84])
    )
    for i in range(3):
        data += b"\x00" + struct.pack(
            "<IiiH",
            1136188800 + i * 60,
            int((50 + i * 0.001) / 180 * 2**31),
            int((6 + i * 0.001) / 180 * 2**31),
            int((100 + i * 10 + 500) * 5),
        )
    header = struct.pack("<BBHI4s", 14, 0x10, 2100, len(data), b".FIT")
    header += struct.pack("<H", crc(header))
    return header + data + struct.pack("<H", crc(header + data))


class Formats(unittest.TestCase):
    def read(self, suffix, raw):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / ("route" + suffix)
            p.write_bytes(raw)
            imported = read_route(p)
            self.assertEqual(p.read_bytes(), raw)
            self.assertEqual(imported.original, raw)
            return Track(imported.gpx)

    def test_kml_lines_heights_waypoints(self):
        track = self.read(".kml", KML)
        self.assertEqual(len(track.segments[0]), 2)
        self.assertEqual(track.segments[0][1].ele, 120)
        self.assertEqual(track.waypoints[0].name, "Top")

    def test_kmz_no_extraction(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("../../doc.kml", KML)
        self.assertEqual(self.read(".kmz", stream.getvalue()).stats()["points"], 2)

    def test_multiple_kml_not_silently_discarded(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("one.kml", KML)
            archive.writestr("two.kml", KML)
        with self.assertRaises(ValueError):
            self.read(".kmz", stream.getvalue())

    def test_tcx_times_and_heights(self):
        track = self.read(".tcx", TCX)
        self.assertEqual(track.stats()["seconds"], 60)
        self.assertEqual(track.segments[0][0].ele, 100)

    def test_geojson_preserves_separate_segments(self):
        track = self.read(".geojson", GEO)
        self.assertEqual(len(track.segments), 2)
        self.assertEqual(len(track.waypoints), 1)
        self.assertLess(track.stats()["km"], 1)

    def test_kml_gx_track_preserves_times(self):
        track = self.read(
            ".kml",
            b'<kml xmlns:gx="http://www.google.com/kml/ext/2.2"><Placemark><gx:Track><when>2026-01-01T00:00:00Z</when><when>2026-01-01T00:01:00Z</when><gx:coord>6 50 100</gx:coord><gx:coord>6.001 50.001 120</gx:coord></gx:Track></Placemark></kml>',
        )
        self.assertEqual(track.stats()["seconds"], 60)

    def test_fit_crc_positions_altitude_time(self):
        track = self.read(".fit", sample_fit())
        self.assertEqual(track.stats()["points"], 3)
        self.assertAlmostEqual(track.segments[0][0].lat, 50, places=5)
        self.assertEqual(track.segments[0][0].ele, 100)
        self.assertEqual(track.stats()["seconds"], 120)

    def test_corrupt_fit_rejected(self):
        data = bytearray(sample_fit())
        data[-1] ^= 1
        with self.assertRaises(Exception):
            self.read(".fit", bytes(data))

    def test_sensor_only_fit_rejected(self):
        data = b"\x40\x00\x00" + struct.pack("<H", 20) + b"\x01" + bytes([3, 1, 2]) + b"\x00\x70"
        header = struct.pack("<BBHI4s", 12, 0x10, 2100, len(data), b".FIT")
        with self.assertRaises(ValueError):
            self.read(".fit", header + data + struct.pack("<H", crc(header + data)))

    def test_entities_invalid_coords_polygon_rejected(self):
        for suffix, raw in [
            (".kml", b'<!DOCTYPE kml [<!ENTITY a "bad">]><kml/>'),
            (".geojson", b'{"type":"LineString","coordinates":[[181,50],[6,50]]}'),
            (".geojson", b'{"type":"Polygon","coordinates":[]}'),
        ]:
            with self.assertRaises(ValueError):
                self.read(suffix, raw)


if __name__ == "__main__":
    unittest.main()
