# SPDX-License-Identifier: GPL-3.0-only
import sys, unittest, tempfile
from pathlib import Path
from dataclasses import replace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gpx_core import *
from waypoint_ui import portable_photo_links, validate_photo
from urllib.parse import unquote


def p(x, y=0):
    return Point(50 + y / 111195, 6 + x / (111195 * math.cos(math.radians(50))), 100)


def road():
    return RoadMap(
        (
            "<osm>"
            + "".join(
                f'<node id="{i + 1}" lat="{p(i * 100).lat}" lon="{p(i * 100).lon}"/>'
                for i in range(11)
            )
            + '<way id="1">'
            + "".join(f'<nd ref="{i + 1}"/>' for i in range(11))
            + '<tag k="highway" v="residential"/></way></osm>'
        ).encode()
    )


def track():
    return Track(
        b'<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1"><trk><name>Route</name><trkseg><trkpt lat="50" lon="6"><ele>100</ele></trkpt><trkpt lat="50.001" lon="6"><ele>110</ele></trkpt></trkseg></trk></gpx>'
    )


class Anchors(unittest.TestCase):
    def test_density_independent_of_sampling(self):
        dense = [p(i) for i in range(2001)]
        sparse = [p(i) for i in range(0, 2001, 10)]
        a = choose_anchors([dense])[0]
        b = choose_anchors([sparse])[0]
        self.assertEqual(len(a), len(b))
        self.assertLessEqual(len(a), 8)
        self.assertEqual((a[0], a[-1]), (0, 2000))

    def test_closed_loop_shape_preserved(self):
        s = [p(0), p(200), p(200, 200), p(0, 200), p(0)]
        self.assertEqual(choose_anchors([s])[0], [0, 1, 2, 3, 4])

    def test_more_controls_means_shorter_intervals(self):
        s = [p(i) for i in range(3001)]
        self.assertGreater(
            len(choose_anchors([s], "Veel")[0]), len(choose_anchors([s], "Weinig")[0])
        )

    def test_router_returns_main_point_mapping(self):
        s = [p(i * 10, 3) for i in range(101)]
        result, notes, controls = road().snap(
            [s], "walk", control_indices=[[0, 50, 100]], with_controls=True
        )
        self.assertEqual(len(controls[0]), 3)
        self.assertEqual(controls[0][0], 0)
        self.assertEqual(controls[0][-1], len(result[0]) - 1)
        self.assertAlmostEqual(result[0][controls[0][1]].lon, p(500).lon, 6)

    def test_drag_only_changes_neighboring_legs(self):
        s = [p(i * 100) for i in range(11)]
        source = [s]
        anchors = [[0, 2, 5, 8, 10]]
        result, controls, selected, notes = route_anchor_edit(
            road(), source, anchors, 0, 5, "walk", 35, position=p(550, 4)
        )
        self.assertEqual(result[0][:2], s[:2])
        self.assertEqual(result[0][-2:], s[-2:])
        self.assertEqual(len(controls[0]), 5)
        self.assertEqual(anchors, [[0, 2, 5, 8, 10]])
        self.assertAlmostEqual(result[0][selected].lon, p(550).lon, 6)

    def test_failed_edit_leaves_original_intact(self):
        s = [p(0), p(500), p(1000)]
        anchors = [[0, 1, 2]]
        with self.assertRaises(AlignmentError):
            route_anchor_edit(road(), [s], anchors, 0, 1, "walk", 35, position=p(500, 300))
        self.assertEqual(s[1].lat, 50)
        self.assertEqual(anchors, [[0, 1, 2]])

    def test_deleting_anchor_connects_neighbors(self):
        s = [p(i * 100) for i in range(11)]
        anchors = [[0, 2, 5, 8, 10]]
        result, controls, selected, notes = route_anchor_edit(
            road(), [s], anchors, 0, 5, "walk", 35, remove=True
        )
        self.assertEqual(len(controls[0]), 4)
        self.assertEqual(result[0][:2], s[:2])
        self.assertEqual(result[0][-2:], s[-2:])

    def test_endpoint_cannot_be_deleted(self):
        with self.assertRaises(ValueError):
            route_anchor_edit(
                road(), [[p(0), p(500), p(1000)]], [[0, 1, 2]], 0, 0, "walk", 35, remove=True
            )

    def test_invalid_control_indices_rejected(self):
        with self.assertRaises(ValueError):
            road().snap([[p(0), p(100)]], "walk", control_indices=[[0, 2]])


class Waypoints(unittest.TestCase):
    def test_name_and_description_roundtrip(self):
        t = track()
        w = Waypoint(50, 6, "Uitzicht & rust", "Bovenaan <de heuvel> 🌳")
        raw = t.export(t.segments, waypoints=[w], modification_note="Waypoints toegevoegd.")
        r = Track(raw)
        self.assertEqual(r.name, "Route")
        self.assertEqual(r.waypoints[0].name, w.name)
        self.assertEqual(r.waypoints[0].description, w.description)
        self.assertEqual(t.waypoints, [])

    def test_limit_1500(self):
        w = Waypoint(50, 6, "Plek", "x" * 1500)
        w.validate()
        with self.assertRaises(ValueError):
            replace(w, description="x" * 1501).validate()

    def test_empty_name_rejected(self):
        with self.assertRaises(ValueError):
            Waypoint(50, 6, "  ").validate()

    def test_photo_copied_and_relative_link_exported(self):
        from PIL import Image

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as d:
            folder = Path(d)
            photo = folder / "origineel.png"
            Image.new("RGB", (20, 20), "green").save(photo)
            w = Waypoint(50, 6, "Bospad", "Foto van het bospad", str(photo))
            gpx = folder / "bewerkt.gpx"
            links = portable_photo_links([w], gpx, {w.key})
            self.assertTrue((folder / links[w.key]).is_file())
            t = track()
            gpx.write_bytes(t.export(t.segments, waypoints=[w], photo_links=links))
            r = Track(gpx.read_bytes())
            self.assertEqual(r.waypoints[0].photo, links[w.key])
            self.assertNotIn(str(folder), r.waypoints[0].photo)
            self.assertEqual((folder / links[w.key]).read_bytes(), photo.read_bytes())

    def test_unapproved_photo_never_read(self):
        w = Waypoint(50, 6, "Onbekende link", photo="C:/geen-toestemming/geheim.jpg")
        self.assertEqual(portable_photo_links([w], Path("niet-geschreven.gpx"), set()), {})

    def test_delete_all_waypoints(self):
        t = track()
        raw = t.export(t.segments, waypoints=[Waypoint(50, 6, "Weg")])
        r = Track(raw)
        self.assertEqual(Track(r.export(r.segments, waypoints=[])).waypoints, [])

    def test_invalid_photo_rejected_before_copy(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as d:
            pth = Path(d) / "fake.jpg"
            pth.write_text("geen foto")
            with self.assertRaises(ValueError):
                validate_photo(pth)

    def test_photo_link_with_spaces_remains_portable(self):
        from PIL import Image

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as d:
            folder = Path(d)
            photo = folder / "foto.png"
            Image.new("RGB", (4, 4), "green").save(photo)
            w = Waypoint(50, 6, "Naam met spaties", photo=str(photo))
            links = portable_photo_links([w], folder / "mijn wandeling.gpx", {w.key})
            self.assertIn("%20", links[w.key])
            self.assertTrue((folder / unquote(links[w.key])).exists())

    def test_photos_only_export_does_not_invent_times(self):
        t = track()
        raw = t.export(
            t.segments,
            waypoints=[Waypoint(50, 6, "Plek")],
            modification_note="Waypoints toegevoegd; tijd ongewijzigd.",
        )
        self.assertIsNone(Track(raw).stats()["seconds"])

    def test_waypoints_only_preserve_recorded_point_extensions(self):
        t = track()
        node = t.segments[0][0].element
        ext = ET.SubElement(node, tag("extensions"))
        ET.SubElement(ext, "{urn:sensor}speed").text = "4.75"
        raw = t.export(t.segments, waypoints=[Waypoint(50, 6, "Nieuwe plek")], preserve_points=True)
        self.assertIn(b"4.75", raw)
        self.assertEqual(Track(raw).stats()["points"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
