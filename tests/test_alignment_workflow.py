# SPDX-License-Identifier: GPL-3.0-only
import unittest, tempfile, sys
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from alignment_workflow import covers_rectangle, compact_tiles, cached_section, road_for_section, alignment_chunks, estimated_schedule
from gpx_core import Point, RoadMap, route_anchor_edit

OSM=b'<osm><node id="1" lat="50" lon="6"/><node id="2" lat="50.001" lon="6"/><node id="3" lat="50.002" lon="6"/><way id="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/><tag k="highway" v="path"/></way></osm>'

class AlignmentWorkflowTests(unittest.TestCase):
    def test_coverage_requires_the_middle_not_only_corners(self):
        self.assertFalse(covers_rectangle((0,0,2,2),[(0,0,.5,2),(1.5,0,2,2)]))
        self.assertTrue(covers_rectangle((0,0,2,2),[(0,0,1,2),(1,0,2,2)]))

    def test_batching_never_adds_an_off_route_area(self):
        tiles=[(6+x*.02,50+y*.01,6+(x+1)*.02,50+(y+1)*.01) for y in range(4) for x in range(4) if (x,y)!=(3,3)]
        grouped=compact_tiles(tiles)
        self.assertLess(len(grouped),len(tiles))
        area=lambda boxes:sum((e-w)*(n-s) for w,s,e,n in boxes)
        self.assertAlmostEqual(area(tiles),area(grouped))
        for box in grouped: self.assertTrue(covers_rectangle(box,tiles))

    def test_changed_section_reuses_covering_saved_tiles(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            folder=Path(tmp); (folder/'Vakken').mkdir()
            (folder/'Vakken'/'5.9,49.9,6.1,50.1.osm').write_bytes(OSM)
            rows=[[Point(50,6),Point(50.001,6)]]
            self.assertIn(b'node',cached_section(folder,rows))
            download=Mock(side_effect=AssertionError('unnecessary download'))
            road=road_for_section(folder,rows,download,'trekking')
            self.assertEqual(len(road.ways),1)
            download.assert_not_called()

    def test_anchor_removal_discards_all_old_interior_samples(self):
        source=[[Point(49.9999,6),Point(50,6),Point(50.0005,6.01),Point(50.001,6.02),Point(50.0015,6.01),Point(50.002,6),Point(50.0021,6)]]
        anchors=[[0,1,3,5,6]]
        before=list(source[0])
        out,mapped,selected,notes=route_anchor_edit(RoadMap(OSM),source,anchors,0,3,'walk',5,remove=True)
        self.assertEqual(source[0],before)
        self.assertTrue(all(p.lon==6 for p in out[0]))
        self.assertIs(out[0][0],source[0][0]); self.assertIs(out[0][-1],source[0][-1])
        self.assertEqual(len(mapped[0]),4)
        self.assertEqual(anchors,[[0,1,3,5,6]])

    def test_chunks_never_connect_recording_gaps(self):
        rows=[[Point(50,6),Point(50.04,6),Point(50.08,6)],[Point(51,6),Point(51.001,6)]]
        chunks=list(alignment_chunks(rows,[[0,1,2],[0,1]],maximum=3000))
        self.assertEqual([(s,a,b) for s,a,b,c in chunks],[(0,0,1),(0,1,2),(1,0,1)])

    def test_unchanged_geometry_keeps_recorded_pause_timestamps(self):
        from datetime import datetime,timedelta,timezone
        start=datetime(2026,1,1,tzinfo=timezone.utc)
        source=[[Point(50,6,time=start),Point(50.001,6,time=start+timedelta(minutes=10)),Point(50.002,6,time=start+timedelta(minutes=11))]]
        result=estimated_schedule(source,source)
        self.assertEqual(result[0][1].time,source[0][1].time)

    def test_cancelled_download_never_starts_a_new_request(self):
        from road_download import fetch_road_data
        fetch=Mock(side_effect=AssertionError('request after cancellation'))
        with self.assertRaisesRegex(ValueError,'gestopt'):
            fetch_road_data(fetch,'url',cancelled=lambda:True)
        fetch.assert_not_called()

if __name__=='__main__':unittest.main()
