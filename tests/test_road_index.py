# SPDX-License-Identifier: GPL-3.0-only
"""Area reuse, topology, refresh and failure guarantees for the private index."""
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from road_index import RoadIndex, bounds, missing_rectangles, road_xml
from road_provider import cached_road, import_region, routing_query
from gpx_core import Point, RoadMap
from map_plan import plan_route_tiles, map_cache_name
import werkbank as wb

BOX=(5.99,49.99,6.02,50.02)
ROWS=[[Point(50,6),Point(50.001,6)]]
OSM=b'''<osm><node id="1" lat="50" lon="6"><tag k="barrier" v="gate"/></node>
<node id="2" lat="50.001" lon="6"/><node id="3" lat="50.002" lon="6"/>
<way id="100"><nd ref="1"/><nd ref="2"/><tag k="highway" v="path"/><tag k="bicycle" v="no"/></way>
<way id="200"><nd ref="2"/><nd ref="3"/><tag k="highway" v="track"/><tag k="oneway" v="yes"/></way>
<relation id="300"><member type="way" ref="100" role="from"/><member type="node" ref="2" role="via"/><member type="way" ref="200" role="to"/><tag k="type" v="restriction"/><tag k="restriction:bicycle" v="no_left_turn"/></relation></osm>'''


class RoadIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tests')
        self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)

    def save(self,raw=OSM,box=BOX,stamp=1_800_000_000_000_000_000):
        path=self.folder/'Vakken'/(','.join(map(str,box))+'.osm')
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(raw)
        os.utime(path,ns=(stamp,stamp))
        return path

    def test_missing_middle_is_not_covered_by_corners(self):
        self.assertTrue(missing_rectangles([(0,0,3,3)],[(0,0,1,3),(2,0,3,3)]))
        self.assertFalse(missing_rectangles([(0,0,3,3)],[(0,0,1,3),(1,0,3,3)]))

    def test_only_missing_strip_is_requested_after_route_changes(self):
        path=self.save()
        with RoadIndex(self.folder) as index:
            index.sync([BOX])
            self.assertEqual(index.missing([(6,50,6.03,50.01)]),[(6.02,50,6.03,50.01)])

    def test_restart_keeps_index_without_reparsing_raw_xml(self):
        self.save()
        first=cached_road(self.folder,ROWS,'trekking')
        with patch('road_index.ET.fromstring',side_effect=AssertionError('raw XML parsed twice')):
            second=cached_road(self.folder,ROWS,'trekking')
        self.assertEqual(second.ways,first.ways)
        self.assertEqual(second._index_generation,first._index_generation)

    def test_original_osm_ids_access_tags_and_restrictions_roundtrip(self):
        self.save()
        road=cached_road(self.folder,ROWS,'trekking')
        xml=ET.fromstring(road_xml(road))
        self.assertEqual([w.get('id') for w in xml.findall('way')],['100','200'])
        self.assertEqual(xml.find('relation/member').get('ref'),'100')
        parsed=RoadMap(road_xml(road))
        self.assertEqual(parsed.ways,road.ways)
        self.assertEqual(parsed.node_tags[1],{'barrier':'gate'})
        self.assertEqual(parsed.restrictions,1)

    def test_same_loaded_object_reused_only_with_same_generation(self):
        self.save()
        road=cached_road(self.folder,ROWS,'trekking')
        self.assertIs(cached_road(self.folder,ROWS,'trekking',road),road)
        self.save(OSM.replace(b'v="no"',b'v="yes"'),stamp=1_900_000_000_000_000_000)
        updated=cached_road(self.folder,ROWS,'trekking',road)
        self.assertIsNot(updated,road)
        self.assertEqual(updated.ways[0][1]['bicycle'],'yes')

    def test_empty_tile_is_known_coverage_without_invented_roads(self):
        self.save(b'<osm/>')
        with RoadIndex(self.folder) as index:
            index.sync([BOX]);self.assertFalse(index.missing([BOX]))
            self.assertIsNone(index.read([BOX]))
        with self.assertRaisesRegex(ValueError,'Geen wegen'):
            cached_road(self.folder,ROWS,'trekking')

    def test_refresh_removes_deleted_ways_and_old_tile_cannot_resurrect_them(self):
        self.save()
        with RoadIndex(self.folder) as index:index.sync([BOX])
        newer=OSM.replace(b'<way id="100">',b'<way id="100"><tag k="unrelated" v="test"/>')
        root=ET.fromstring(newer)
        root.remove(root.find('way'))
        self.save(ET.tostring(root),stamp=1_900_000_000_000_000_000)
        with RoadIndex(self.folder) as index:
            index.sync([BOX]);self.assertEqual(index.read([BOX])._index_way_ids,[200])
        self.save(OSM,box=(5.98,49.98,6.03,50.03),stamp=1_700_000_000_000_000_000)
        with RoadIndex(self.folder) as index:
            index.sync([BOX]);self.assertEqual(index.read([BOX])._index_way_ids,[200])

    def test_old_tile_cannot_override_fresh_access_tags(self):
        self.save(OSM.replace(b'v="no"',b'v="yes"'),stamp=1_900_000_000_000_000_000)
        with RoadIndex(self.folder) as index:index.sync([BOX])
        self.save(OSM,box=(5.98,49.98,6.03,50.03),stamp=1_700_000_000_000_000_000)
        with RoadIndex(self.folder) as index:
            index.sync([BOX]);self.assertEqual(index.read([BOX]).ways[0][1]['bicycle'],'yes')

    def test_failed_multi_file_update_is_rolled_back(self):
        first=self.save()
        with RoadIndex(self.folder) as index:
            index.sync([BOX]);generation=index.generation
            changed=self.save(OSM.replace(b'v="no"',b'v="yes"'),stamp=1_900_000_000_000_000_000)
            broken=self.save(b'<osm><way id="9"><nd ref="999"/><tag k="highway" v="path"/></way></osm>',box=(6,50,6.04,50.04))
            with self.assertRaises(ValueError):index.ingest_files([(changed,[BOX]),(broken,[BOX])])
            self.assertEqual(index.generation,generation)
            self.assertEqual(index.read([BOX]).ways[0][1]['bicycle'],'no')

    def test_rebuild_from_raw_cache_when_index_is_corrupt(self):
        self.save();old=cached_road(self.folder,ROWS,'trekking')
        database=self.folder/'Wegenindex'/'wegen.sqlite3'
        database.write_bytes(b'broken disposable index')
        new=cached_road(self.folder,ROWS,'trekking',old)
        self.assertEqual(new.ways,old.ways)
        self.assertIsNot(new,old)
        self.assertTrue(list(database.parent.glob('wegen-beschadigd-*.sqlite3')))

    def test_only_exact_legacy_route_hash_can_claim_coverage(self):
        exact=self.folder/map_cache_name(plan_route_tiles(ROWS));exact.write_bytes(OSM)
        road=cached_road(self.folder,ROWS,'trekking')
        self.assertEqual(len(road.ways),2)
        self.assertIsNone(cached_road(self.folder,[[Point(51,7),Point(51.001,7)]],'trekking'))

    def test_bounded_import_preserves_original_and_serves_later_routes(self):
        source=self.folder/'original.xml'
        raw=OSM.replace(b'<osm>',b'<osm><bounds minlon="5.99" minlat="49.99" maxlon="6.02" maxlat="50.02"/>')
        source.write_bytes(raw)
        dest,road=import_region(self.folder,source)
        self.assertEqual(source.read_bytes(),raw)
        self.assertEqual(dest.read_bytes(),raw)
        self.assertEqual(len(cached_road(self.folder,ROWS,'trekking').ways),2)

    def test_unbounded_import_does_not_claim_entire_envelope_coverage(self):
        source=self.folder/'original.xml';source.write_bytes(OSM)
        import_region(self.folder,source)
        self.assertIsNone(cached_road(self.folder,ROWS,'trekking'))

    def test_cancellation_leaves_raw_files_untouched(self):
        path=self.save();before=path.read_bytes()
        with RoadIndex(self.folder) as index:
            with self.assertRaisesRegex(ValueError,'gestopt'):index.sync([BOX],cancelled=lambda:True)
        self.assertEqual(path.read_bytes(),before)

    def test_downloader_fetches_only_missing_area(self):
        self.save()
        wanted=[(6,50,6.03,50.01)]
        with patch.object(wb,'MAPS',self.folder),patch.object(wb,'fetch',return_value=OSM) as fetch:
            result=wb.download_map(ROWS,tiles=wanted)
        self.assertTrue(result.is_file())
        self.assertEqual(fetch.call_count,1)
        query=parse_qs(urlparse(fetch.call_args.args[0]).query)['data'][0]
        self.assertIn('50.0000000,6.0200000,50.0100000,6.0300000',query)

    def test_failed_refresh_keeps_index_generation_and_access(self):
        with patch.object(wb,'MAPS',self.folder),patch.object(wb,'fetch',return_value=OSM):wb.download_map(ROWS)
        before=cached_road(self.folder,ROWS,'trekking')
        with patch.object(wb,'MAPS',self.folder),patch.object(wb,'fetch',side_effect=OSError('offline')):
            with self.assertRaises(OSError):wb.download_map(ROWS,refresh=True)
        after=cached_road(self.folder,ROWS,'trekking')
        self.assertEqual(before._index_generation,after._index_generation)
        self.assertEqual(before.ways,after.ways)

    def test_incomplete_refresh_never_overwrites_raw_cache(self):
        with patch.object(wb,'MAPS',self.folder),patch.object(wb,'fetch',return_value=OSM):wb.download_map(ROWS)
        before={p:p.read_bytes() for p in self.folder.rglob('*.osm')}
        bad=b'<osm><way id="99"><nd ref="1"/><nd ref="2"/><tag k="highway" v="path"/></way></osm>'
        with patch.object(wb,'MAPS',self.folder),patch.object(wb,'fetch',return_value=bad):
            with self.assertRaises(ValueError):wb.download_map(ROWS,refresh=True)
        self.assertTrue(all(p.read_bytes()==raw for p,raw in before.items()))

    def test_osm_snapshot_time_beats_local_copy_time(self):
        fresh=OSM.replace(b'<osm>',b'<osm><meta osm_base="2026-10-31T00:00:00Z"/>').replace(b'v="no"',b'v="yes"')
        old=OSM.replace(b'<osm>',b'<osm><meta osm_base="2026-01-01T00:00:00Z"/>')
        self.save(fresh,stamp=1_700_000_000_000_000_000)
        with RoadIndex(self.folder) as index:index.sync([BOX])
        self.save(old,box=(5.98,49.98,6.03,50.03),stamp=1_900_000_000_000_000_000)
        with RoadIndex(self.folder) as index:
            index.sync([BOX]);self.assertEqual(index.read([BOX]).ways[0][1]['bicycle'],'yes')

    def test_same_coordinates_do_not_create_a_new_junction(self):
        raw=OSM.replace(b'<node id="2"',b'<node id="4" lat="50" lon="6"/><node id="2"')
        raw=raw.replace(b'<nd ref="2"/><nd ref="3"/>',b'<nd ref="4"/><nd ref="3"/>')
        self.save(raw)
        with RoadIndex(self.folder) as index:
            index.sync([BOX]);road=index.read([BOX])
        self.assertEqual(road.ways[0][0],[1,2])
        self.assertEqual(road.ways[1][0],[4,3])
        self.assertEqual(len(road.nodes),4)

    def test_reader_observes_previous_generation_until_batch_commit(self):
        self.save()
        with RoadIndex(self.folder) as writer:
            writer.sync([BOX])
            generation=writer.generation
            writer.db.execute('BEGIN')
            writer.db.execute("UPDATE ways SET tags=? WHERE id=100",('{"highway":"path","bicycle":"yes"}',))
            with RoadIndex(self.folder) as reader:
                self.assertEqual(reader.read([BOX]).ways[0][1]['bicycle'],'no')
                writer.db.rollback()
                self.assertEqual(reader.generation,generation)

    def test_removed_restriction_does_not_survive_refresh_or_old_overlap(self):
        self.save()
        with RoadIndex(self.folder) as index:index.sync([BOX])
        root=ET.fromstring(OSM);root.remove(root.find('relation'))
        self.save(ET.tostring(root),stamp=1_900_000_000_000_000_000)
        with RoadIndex(self.folder) as index:
            index.sync([BOX]);self.assertEqual(index.read([BOX]).restrictions,0)

        self.save(OSM,box=(5.98,49.98,6.03,50.03),stamp=1_700_000_000_000_000_000)
        with RoadIndex(self.folder) as index:
            index.sync([BOX]);self.assertEqual(index.read([BOX]).restrictions,0)

    def test_query_retains_full_automatic_recovery_search_window(self):
        rows=[[Point(50+i*.0003,6) for i in range(50)]]
        query=routing_query(rows,[list(range(50))],35)[0]
        self.assertGreater((50-query[1])*110000,3800)


if __name__=='__main__':unittest.main()
