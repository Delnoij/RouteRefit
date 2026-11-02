# SPDX-License-Identifier: GPL-3.0-only
import gzip
import hashlib
import sqlite3
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import osmium

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from region_packages import (install_or_update,installed,catalog,
                             safe_url,due_packages,set_weekly)
from package_geometry import parse_poly,covered_boxes,classify
from package_index import PackageCancelled
from road_provider import cached_road
from road_index import road_xml
from gpx_core import Point

REGION={'id':'test-region','name':'Test region','url':'https://download.geofabrik.de/europe/test-region-latest.osm.pbf'}
BASE='https://download.geofabrik.de/europe/test-region-updates'
POLY='test\n1\n 5.8 49.8\n 6.3 49.8\n 6.3 50.3\n 5.8 50.3\n 5.8 49.8\nEND\nEND\n'
ROWS=[[Point(50,6),Point(50.001,6)]]
OSM='''<osm version="0.6"><node id="1" version="1" lat="50" lon="6"><tag k="barrier" v="gate"/></node>
<node id="2" version="1" lat="50.001" lon="6"/><node id="3" version="1" lat="50.002" lon="6"/>
<node id="4" version="1" lat="50.003" lon="6"/>
<way id="10" version="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="path"/><tag k="bicycle" v="no"/></way>
<way id="20" version="1"><nd ref="2"/><nd ref="3"/><tag k="highway" v="track"/><tag k="oneway" v="yes"/></way>
<relation id="30" version="1"><member type="way" ref="10" role="from"/><member type="node" ref="2" role="via"/><member type="way" ref="20" role="to"/><tag k="type" v="restriction"/><tag k="restriction" v="no_left_turn"/></relation></osm>'''


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tests');self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name);self.maps=self.folder/'maps';self.maps.mkdir()
        source=self.folder/'synthetic.osm';source.write_text(OSM,encoding='utf-8')
        pbf=self.folder/'synthetic.osm.pbf';header=osmium.io.Header()
        for k,v in [('osmosis_replication_base_url',BASE),('osmosis_replication_sequence_number','1'),('osmosis_replication_timestamp','2026-10-29T21:00:00Z')]:header.set(k,v)
        with osmium.SimpleWriter(str(pbf),header=header) as writer:
            for obj in osmium.FileProcessor(str(source)):writer.add(obj)
        self.payload=pbf.read_bytes();self.sequence=1;self.requests=[];self.delta=b''

    def fetch(self,url,dest,cancelled,progress,limit):
        self.requests.append(url)
        if url.endswith('.poly'):raw=POLY.encode()
        elif url.endswith('/state.txt'):raw=f'sequenceNumber={self.sequence}\ntimestamp=2026-10-{28+self.sequence:02d}T21\\:00\\:00Z\n'.encode()
        elif url.endswith('.md5'):raw=hashlib.md5(self.payload).hexdigest().encode()
        elif url.endswith('.pbf'):raw=self.payload
        elif url.endswith('.osc.gz'):raw=gzip.compress(self.delta)
        else:raise AssertionError(url)
        dest.write_bytes(raw);return len(raw)

    def install(self,**kwargs):return install_or_update(self.maps,REGION,fetch=self.fetch,**kwargs)

    def test_full_install_and_offline_corridor_reuse(self):
        result=self.install();self.assertEqual(result['stats']['ways'],2)
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('network')):
            road=cached_road(self.maps,ROWS,'trekking')
            self.assertEqual(len(road.ways),2);self.assertEqual(road.restrictions,1)
            self.assertEqual(road.node_tags[1],{'barrier':'gate'})
            again=cached_road(self.maps,ROWS,'trekking',road)
            self.assertIs(again,road)
        self.assertNotIn('user',road_xml(road).decode())

    def test_unchanged_checks_do_not_download_pbf_or_reindex(self):
        original=self.install();self.requests.clear()
        with patch('region_packages.ingest',side_effect=AssertionError('reindex')):result=self.install()
        self.assertEqual(result['result'],'unchanged');self.assertEqual(result['snapshot'],original['snapshot'])
        self.assertFalse(any(u.endswith('.pbf') for u in self.requests))

    def test_incremental_update_moves_nodes_deletes_road_and_adds_road_using_old_nonroad_node(self):
        self.install();before=cached_road(self.maps,ROWS,'trekking')
        self.sequence=2;self.requests.clear()
        self.delta=b'''<osmChange version="0.6"><modify><node id="2" version="2" lat="50.0011" lon="6"/>
        <way id="10" version="2"><nd ref="1"/><nd ref="2"/><tag k="highway" v="path"/><tag k="bicycle" v="yes"/></way></modify>
        <delete><way id="20" version="2"/><relation id="30" version="2"/></delete>
        <create><way id="40" version="1"><nd ref="2"/><nd ref="4"/><tag k="highway" v="footway"/></way></create></osmChange>'''
        result=self.install();self.assertEqual(result['result'],'updated')
        self.assertFalse(any(u.endswith('.pbf') for u in self.requests))
        after=cached_road(self.maps,ROWS,'trekking',before)
        self.assertNotIn(20,after._index_way_ids);self.assertIn(40,after._index_way_ids)
        self.assertEqual(after.nodes[2].lat,50.0011);self.assertEqual(after.restrictions,0)
        self.assertEqual(before.nodes[2].lat,50.001)

    def test_failed_update_leaves_active_snapshot_byte_identical(self):
        old=self.install();path=self.maps/'Gebiedspakketten'/REGION['id']/old['snapshot']/'Wegenindex/wegen.sqlite3'
        digest=hashlib.sha256(path.read_bytes()).digest();self.sequence=2
        self.delta=b'<osmChange version="0.6"><create><way id="55" version="1"><nd ref="1"/><nd ref="999"/><tag k="highway" v="path"/></way></create></osmChange>'
        with self.assertRaisesRegex(ValueError,'onvolledige'):self.install()
        self.assertEqual(installed(self.maps)[0]['snapshot'],old['snapshot'])
        self.assertEqual(hashlib.sha256(path.read_bytes()).digest(),digest)

    def test_legacy_package_updates_without_forced_rebuild(self):
        from contextlib import closing
        old=self.install();path=self.maps/'Gebiedspakketten'/REGION['id']/old['snapshot']/'Wegenindex/wegen.sqlite3'
        with closing(sqlite3.connect(path)) as db:
            db.executescript('''CREATE TABLE old_nodes(id INTEGER PRIMARY KEY,lat REAL,lon REAL,tags TEXT,stamp INTEGER);
                INSERT INTO old_nodes SELECT * FROM nodes;
                DROP VIEW nodes; DROP TABLE package_nodes;
                ALTER TABLE old_nodes RENAME TO nodes;
                DELETE FROM meta WHERE key='package_schema';''')
        self.sequence=2;self.requests.clear()
        self.delta=b'<osmChange version="0.6"><create><way id="40" version="1"><nd ref="2"/><nd ref="4"/><tag k="highway" v="footway"/></way></create></osmChange>'
        result=self.install();self.assertEqual(result['result'],'updated')
        self.assertFalse(any(u.endswith('.pbf') for u in self.requests))
        road=cached_road(self.maps,ROWS,'trekking');self.assertIn(40,road._index_way_ids)
        self.assertEqual(road.nodes[4].lat,50.003)

    def test_checksum_failure_preserves_previous_package(self):
        old=self.install()
        def broken(url,*args):
            size=self.fetch(url,*args)
            if url.endswith('.pbf'):args[0].write_bytes(b'broken')
            return size
        with self.assertRaisesRegex(ValueError,'downloadcontrole'):
            install_or_update(self.maps,REGION,fetch=broken,full=True)
        self.assertEqual(installed(self.maps)[0]['snapshot'],old['snapshot'])

    def test_cancel_during_preparation_never_publishes(self):
        flag=[False]
        def report(*args):flag[0]=True
        with self.assertRaises(PackageCancelled):self.install(cancelled=lambda:flag[0],progress=report)
        self.assertEqual(installed(self.maps),[])

    def test_old_update_requires_explicit_full_download(self):
        old=self.install()
        with patch('region_packages.parse_state',return_value=(200,old['stamp']+10)):
            self.requests.clear()
            with self.assertRaisesRegex(ValueError,'volledig nieuw'):self.install()
        self.assertFalse(any(u.endswith('.pbf') for u in self.requests))

    def test_weekly_checks_are_opt_out_and_failures_are_not_retry_loop(self):
        result=self.install();now=result['checked']+8*86400
        self.assertEqual(len(due_packages(self.maps,now)),1)
        set_weekly(self.maps,False);self.assertEqual(due_packages(self.maps,now),[])
        set_weekly(self.maps,True);self.assertEqual(due_packages(self.maps,result['checked']+3600),[])

    def test_polygon_holes_and_outside_never_claimed_as_coverage(self):
        rings=parse_poly(POLY);self.assertEqual(classify((5.9,49.9,6.1,50.1),rings),1)
        rings.append((True,[(5.99,49.99),(6.01,49.99),(6.01,50.01),(5.99,50.01),(5.99,49.99)]))
        self.assertNotEqual(classify((5.9,49.9,6.1,50.1),rings),1)
        self.assertEqual(covered_boxes([(6,50,6.001,50.001)],rings),[])
        self.assertEqual(covered_boxes([(1,1,2,2)],rings),[])

    def test_external_or_personal_urls_rejected(self):
        for url in ('http://download.geofabrik.de/a','https://other.invalid/a','https://download.geofabrik.de/a?route=secret'):
            with self.assertRaises(ValueError):safe_url(url)
        self.assertTrue(all(safe_url(r['url']) for r in catalog()))

    def test_damaged_published_package_never_becomes_empty_coverage(self):
        item=self.install()
        path=self.maps/'Gebiedspakketten'/REGION['id']/item['snapshot']/'Wegenindex/wegen.sqlite3'
        path.write_bytes(b'broken database')
        with self.assertRaises(sqlite3.DatabaseError):cached_road(self.maps,ROWS,'trekking')
        self.assertEqual(path.read_bytes(),b'broken database')

    def test_two_adjacent_packages_jointly_cover_border_route(self):
        def left(url,dest,*args):
            size=self.fetch(url,dest,*args)
            if url.endswith('.poly'):dest.write_text(POLY.replace('6.3','6.001'),encoding='utf-8')
            return size
        install_or_update(self.maps,REGION,fetch=left)
        self.assertIsNone(cached_road(self.maps,ROWS,'trekking'))
        second=dict(REGION,id='adjacent-region',name='Adjacent country')
        def right(url,dest,*args):
            size=self.fetch(url,dest,*args)
            if url.endswith('.poly'):dest.write_text(POLY.replace('5.8','5.999'),encoding='utf-8')
            return size
        install_or_update(self.maps,second,fetch=right)
        self.assertEqual(len(installed(self.maps)),2)
        road=cached_road(self.maps,ROWS,'trekking')
        self.assertIsNotNone(road);self.assertEqual(len(road.ways),2)
        self.assertEqual(road.restrictions,1)


if __name__=='__main__':unittest.main()
