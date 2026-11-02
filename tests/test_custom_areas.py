# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import test_region_packages as fixtures
from test_region_packages import ROWS
from contextlib import closing
from custom_area import polygon,definition
from custom_download import install,Client,safe_url
from package_index import PackageCancelled
from region_packages import installed,due_packages,save_custom,custom_regions
from road_provider import cached_road


class Areas(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.PackageTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.maps=self.fixture.maps
        self.region=definition('Alleen lokaal',[(5.98,49.98),(6.04,49.98),(6.04,50.04),(5.98,50.04)])
        fixture=self.fixture
        class Fake:
            posts=0;downloads=0;ready=True;stamp='2026-10-29T21:00:00Z'
            def status(self,job=''):
                return {'Complete':self.ready} if job else {'Timestamp':self.stamp}
            def submit(self,ring):self.posts+=1;return '11111111-1111-1111-1111-111111111111'
            def download(self,job,dest,cancelled,progress):
                self.downloads+=1;dest.write_bytes(fixture.payload);return len(fixture.payload)
        self.client=Fake()

    def run_install(self,**kwargs):return install(self.maps,self.region,kwargs.pop('cancelled',lambda:False),lambda *a:None,client=self.client,**kwargs)

    def test_polygon_rejects_crossing_large_degenerate_and_invalid(self):
        for points in [[(6,50),(6.1,50.1),(6,50.1),(6.1,50)],[(6,50),(8,50),(8,53),(6,53)],[(6,50)]*3,[(float('nan'),50),(6,50),(6,51)]]:
            with self.subTest(points=points),self.assertRaises(ValueError):polygon(points)

    def test_custom_boundary_preserved_cross_border_no_route_needed(self):
        save_custom(self.maps,self.region)
        self.assertEqual(custom_regions(self.maps)[0]['name'],'Alleen lokaal')
        result=self.run_install()
        self.assertEqual(result['stats']['ways'],2)
        self.assertEqual(len(installed(self.maps)),1)
        road=cached_road(self.maps,ROWS,'trekking')
        self.assertIsNotNone(road);self.assertEqual(road.restrictions,1)
        self.assertEqual(road.node_tags[1],{'barrier':'gate'})
        self.assertEqual(due_packages(self.maps,now=result['checked']+30*86400),[])

    def test_unchanged_server_does_not_submit_again(self):
        first=self.run_install();second=self.run_install()
        self.assertEqual(second['result'],'unchanged')
        self.assertEqual(first['snapshot'],second['snapshot']);self.assertEqual(self.client.posts,1)

    def test_timeout_resumes_one_job_without_duplicate_post(self):
        self.client.ready=False;now=[0]
        def pause(seconds):now[0]+=seconds
        with patch('custom_download.MAX_WAIT',10),self.assertRaisesRegex(ValueError,'dezelfde aanvraag'):
            self.run_install(clock=lambda:now[0],pause=pause)
        self.assertEqual(self.client.posts,1);self.assertEqual(installed(self.maps),[])
        self.client.ready=True;self.run_install()
        self.assertEqual(self.client.posts,1)

    def test_cancel_preserves_original_and_resumes_pending_job(self):
        first=self.run_install();self.client.stamp='2026-10-30T21:00:00Z';self.client.ready=False
        stopped=[False]
        with self.assertRaises(PackageCancelled):
            self.run_install(cancelled=lambda:stopped[0],pause=lambda s:stopped.__setitem__(0,True))
        self.assertEqual(installed(self.maps)[0]['snapshot'],first['snapshot'])
        self.client.ready=True;self.run_install();self.assertEqual(self.client.posts,2)

    def test_failed_download_keeps_package_and_no_auto_retry(self):
        first=self.run_install();self.client.stamp='2026-10-30T21:00:00Z'
        with patch.object(self.client,'download',side_effect=TimeoutError),self.assertRaises(TimeoutError):self.run_install()
        self.assertEqual(installed(self.maps)[0]['snapshot'],first['snapshot'])
        self.assertEqual(self.client.posts,2)

    def test_request_contains_only_geometry_and_constant_name(self):
        captured=[]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return b'11111111-1111-1111-1111-111111111111'
        def opened(url,data=None):captured.append(json.loads(data));return Response()
        with patch.object(Client,'open',side_effect=opened):Client().submit(self.region['polygon'][0][1])
        self.assertEqual(set(captured[0]),{'Name','RegionType','RegionData'})
        self.assertEqual(captured[0]['Name'],'none')
        self.assertNotIn('Alleen lokaal',json.dumps(captured))

    def test_other_hosts_and_paths_are_rejected(self):
        for url in ['http://slice.openstreetmap.us/api/','https://evil.invalid/api/','https://slice.openstreetmap.us/api/?x=route','https://slice.openstreetmap.us/../../file']:
            with self.assertRaises(ValueError):safe_url(url)

    def test_compact_nodes_keep_all_coordinates_and_tags(self):
        result=self.run_install();dbpath=self.maps/'Gebiedspakketten'/self.region['id']/result['snapshot']/'Wegenindex/wegen.sqlite3'
        with closing(sqlite3.connect(dbpath)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM package_nodes').fetchone()[0],4)
            self.assertEqual(db.execute('SELECT lat,lon FROM nodes WHERE id=4').fetchone(),(50.003,6.0))
            self.assertEqual(db.execute('SELECT tags FROM package_nodes WHERE id=4').fetchone()[0],None)


if __name__=='__main__':unittest.main()
