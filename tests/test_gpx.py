# SPDX-License-Identifier: GPL-3.0-only
import unittest, sys, tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gpx_core import *

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def p(x, y=0, t=None, h=100):
    return Point(
        50 + y / 111195,
        6 + x / (111195 * math.cos(math.radians(50))),
        h,
        START + timedelta(seconds=t) if t is not None else None,
    )


def xml(points, namespace=NS):
    return (
        '<gpx xmlns="'
        + namespace
        + '" version="1.1" creator="test"><wpt lat="50" lon="6"><name>Bewaren</name></wpt><trk><name>Test</name><trkseg>'
        + "".join(
            f'<trkpt lat="{q.lat}" lon="{q.lon}"><ele>{q.ele}</ele>'
            + (f"<time>{q.time.isoformat()}</time>" if q.time else "")
            + '<extensions><x:speed xmlns:x="urn:test">100</x:speed><x:hr xmlns:x="urn:test">120</x:hr></extensions></trkpt>'
            for q in points
        )
        + "</trkseg></trk></gpx>"
    ).encode()


def osm(waytags="", nodeextras="", disconnected=False):
    nodes = [(1, 0, 0), (2, 100, 0), (3, 200, 0), (4, 300, 0)]
    return (
        '<osm version="0.6">'
        + "".join(
            f'<node id="{i}" lat="{p(x, y).lat}" lon="{p(x, y).lon}">{nodeextras if i == 2 else ""}</node>'
            for i, x, y in nodes
        )
        + '<way id="1">'
        + "".join(f'<nd ref="{i}"/>' for i in ([1, 2] if disconnected else [1, 2, 3, 4]))
        + '<tag k="highway" v="residential"/>'
        + waytags
        + "</way>"
        + (
            '<way id="2"><nd ref="3"/><nd ref="4"/><tag k="highway" v="residential"/></way>'
            if disconnected
            else ""
        )
        + "</osm>"
    ).encode()


class Timing(unittest.TestCase):
    def test_real_pause_removed_motion_unchanged(self):
        s = (
            [p(0, t=0), p(100, t=100)]
            + [p(100, t=i) for i in range(110, 701, 10)]
            + [p(200, t=800)]
        )
        found = pauses([s])
        self.assertEqual(len(found), 1)
        self.assertFalse(found[0].uncertain)
        result, removed = remove_pauses([s], found)
        self.assertEqual(removed, 600)
        self.assertEqual((result[0][-1].time - result[0][0].time).total_seconds(), 200)
        self.assertEqual((result[0][-1].time - result[0][-2].time).total_seconds(), 100)

    def test_sparse_gap_not_preselected(self):
        found = pauses([[p(0, t=0), p(100, t=100), p(100, t=10000), p(200, t=10100)]])
        self.assertTrue(found[0].uncertain)
        self.assertFalse(found[0].selected)

    def test_long_travel_gap_is_not_pause(self):
        self.assertEqual(pauses([[p(0, t=0), p(1000, t=3600)]]), [])

    def test_missing_time_rejected(self):
        with self.assertRaises(ValueError):
            pauses([[p(0), p(100)]])

    def test_backwards_time_rejected(self):
        with self.assertRaises(ValueError):
            pauses([[p(0, t=100), p(100, t=0)]])

    def test_flat_target_duration_exact(self):
        out = modeled_times([[p(0), p(100), p(500)]], "Wandelen · normaal", 4.5, START, 600)
        self.assertAlmostEqual((out[0][-1].time - START).total_seconds(), 600, places=4)

    def test_hills_change_speed(self):
        out = modeled_times(
            [[p(0, h=100), p(100, h=100), p(200, h=120), p(300, h=140)]],
            "Wandelen · normaal",
            4.5,
            START,
        )
        self.assertGreater(
            (out[0][-1].time - out[0][-2].time).total_seconds(),
            (out[0][1].time - out[0][0].time).total_seconds(),
        )

    def test_bicycle_faster_than_walking(self):
        s = [[p(0), p(1000)]]
        walk = modeled_times(s, "Wandelen · normaal", 4.5, START)
        bike = modeled_times(s, "Fietsen · trekking", 20, START)
        self.assertLess(bike[-1][-1].time, walk[-1][-1].time)

    def test_no_invented_heights(self):
        with self.assertRaises(ValueError):
            modeled_times([[p(0, h=None), p(100, h=None)]], "Wandelen · normaal", 4.5, START)

    def test_multisegment_gap_excluded(self):
        out = modeled_times([[p(0), p(100)], [p(500), p(600)]], "Wandelen · normaal", 4.5, START)
        self.assertEqual(out[0][-1].time, out[1][0].time)
        tr = Track(xml([p(0), p(100)]))
        self.assertAlmostEqual(tr.stats(out)["km"], 0.2, places=3)


class Files(unittest.TestCase):
    def test_export_preserves_waypoint_and_hr_clears_speed(self):
        raw = xml([p(0), p(100)])
        tr = Track(raw)
        out = modeled_times(tr.segments, "Wandelen · normaal", 4.5, START)
        data = tr.export(out, True)
        r = Track(data)
        self.assertIn(b"Bewaren", data)
        self.assertIn(b"120", data)
        self.assertNotIn(b":speed", data)
        self.assertTrue(r.stats()["valid_time"])
        self.assertEqual(tr.raw, raw)

    def test_gpx10_normalized(self):
        tr = Track(xml([p(0, t=0), p(100, t=100)], "http://www.topografix.com/GPX/1/0"))
        out = tr.export(tr.segments)
        self.assertNotIn(b"GPX/1/0", out)
        self.assertTrue(Track(out).stats()["valid_time"])

    def test_dtd_rejected(self):
        with self.assertRaises(ValueError):
            Track(b"<!DOCTYPE gpx><gpx/>")

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as tmp:
            path = Path(tmp) / "x"
            write_new(path, b"original")
            with self.assertRaises(FileExistsError):
                write_new(path, b"changed")
            self.assertEqual(path.read_bytes(), b"original")

    def test_rte_supported(self):
        raw = (
            xml([p(0, t=0), p(100, t=100)])
            .replace(b"<trk>", b"<rte>")
            .replace(b"</trk>", b"</rte>")
            .replace(b"<trkseg>", b"")
            .replace(b"</trkseg>", b"")
            .replace(b"trkpt", b"rtept")
        )
        tr = Track(raw)
        self.assertTrue(Track(tr.export(tr.segments)).stats()["valid_time"])


class Roads(unittest.TestCase):
    def test_match_to_road_offline(self):
        s = [[p(20, 5, t=0), p(100, 5, t=100), p(180, 5, t=200)]]
        out, notes = RoadMap(osm()).snap(s, "walk")
        self.assertTrue(all(abs(q.lat - 50) < 0.000001 for q in out[0]))
        self.assertEqual(out[0][0].time, START)
        self.assertEqual(out[0][-1].time, s[0][-1].time)

    def test_private_access_blocked(self):
        with self.assertRaises(ValueError):
            RoadMap(osm('<tag k="access" v="private"/>')).snap([[p(20), p(180)]], "walk")

    def test_explicit_foot_override(self):
        out, _ = RoadMap(osm('<tag k="access" v="private"/><tag k="foot" v="yes"/>')).snap(
            [[p(20), p(180)]], "walk"
        )
        self.assertTrue(out)

    def test_bicycle_oneway_honored(self):
        rm = RoadMap(osm('<tag k="oneway" v="yes"/>'))
        with self.assertRaises(ValueError):
            rm.snap([[p(180), p(20)]], "bike")
        self.assertTrue(rm.snap([[p(180), p(20)]], "walk")[0])

    def test_disconnected_network_not_bridged(self):
        with self.assertRaises(ValueError):
            RoadMap(osm(disconnected=True)).snap([[p(20), p(280)]], "walk")

    def test_no_way_outside_radius(self):
        with self.assertRaises(ValueError):
            RoadMap(osm()).snap([[p(20, 100), p(180, 100)]], "walk")

    def test_motorway_excluded(self):
        self.assertFalse(allowed({"highway": "motorway"}, "bike"))

    def test_barrier_access(self):
        with self.assertRaises(ValueError):
            RoadMap(osm(nodeextras='<tag k="barrier" v="wall"/>')).snap([[p(20), p(280)]], "walk")


if __name__ == "__main__":
    unittest.main(verbosity=2)
