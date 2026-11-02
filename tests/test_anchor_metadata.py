# SPDX-License-Identifier: GPL-3.0-only
import sys
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gpx_core import RoadMap, Point


class AnchorMetadata(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 8, 27, tzinfo=timezone.utc)
        self.road = RoadMap(
            b'<osm><node id="1" lat="50" lon="6"/><node id="2" lat="50.001" lon="6"/><node id="3" lat="50.002" lon="6"/><way id="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/><tag k="highway" v="cycleway"/></way></osm>'
        )

    def p(self, lat, seconds, ele=100):
        return Point(lat, 6, ele, self.start + timedelta(seconds=seconds))

    def test_stationary_boundary_samples_keep_their_timestamps_and_heights(self):
        source = [[self.p(50, 0), self.p(50, 1, 102), self.p(50.001, 60), self.p(50.001, 61, 101)]]
        out, _ = self.road.snap(source, "bike", 5, control_indices=[[0, 3]])
        self.assertEqual(out[0][0].time, source[0][0].time)
        self.assertEqual(out[0][0].ele, 100)
        self.assertEqual(out[0][-1].time, source[0][-1].time)
        self.assertEqual(out[0][-1].ele, 101)

    def test_stationary_interior_anchors_keep_pause_metadata(self):
        source = [
            [self.p(50, 0), self.p(50.001, 60), self.p(50.001, 120, None), self.p(50.002, 180)]
        ]
        out, _, mapped = self.road.snap(
            source, "bike", 5, control_indices=[[0, 1, 2, 3]], with_controls=True
        )
        for original, index in zip(source[0], mapped[0]):
            self.assertEqual(out[0][index].time, original.time)
            self.assertEqual(out[0][index].ele, original.ele)


if __name__ == "__main__":
    unittest.main()
