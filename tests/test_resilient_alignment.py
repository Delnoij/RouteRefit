# SPDX-License-Identifier: GPL-3.0-only
import copy, io, sys, tempfile, threading, time, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from gpx_core import Point
from road_download import DownloadBudget, RoadServiceUnavailable, fetch_road_data
from road_transport import bounded_fetch
from routing_runtime import RoutingCancelled, routing_runtime
from resilient_alignment import run_alignment, partial_road, edge_covered, NoUsableRoads, MISSING_ROADS, PARTIAL_NOTICE


def source():
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    return [[Point(50+y,6.00001,100+i,start+timedelta(minutes=i))
             for i,y in enumerate((0,.001,.02,.021,.04))]]


def osm():
    return ('<osm>'+''.join(f'<node id="{i}" lat="{p.lat}" lon="6"/>' for i,p in enumerate(source()[0],1))+
        '<way id="1">'+''.join(f'<nd ref="{i}"/>' for i in range(1,6))+
        '<tag k="highway" v="path"/></way></osm>').encode()


class ResilientAlignmentTests(unittest.TestCase):
    def setUp(self):
        import road_transport
        road_transport._cooldowns.clear()
        self.addCleanup(road_transport._cooldowns.clear)
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tests')
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        (self.folder/'Vakken').mkdir()

    def cached(self,full=False):
        name='5.9,49.9,6.1,50.1.osm' if full else '5.99,49.99,6.01,50.009.osm'
        path=self.folder/'Vakken'/name;path.write_bytes(osm());return path

    def run_route(self,download,rows=None,cancel=None):
        rows=rows or source()
        return run_alignment(self.folder,rows,[list(range(5))],'bike','trekking',35,set(),False,
                             None,cancel or threading.Event(),lambda s:None,download)

    def test_offline_preserves_unknown_geometry_heights_times_and_reports_issue(self):
        self.cached();rows=source();before=copy.deepcopy(rows)
        out,mapped,issues,notes,road=self.run_route(Mock(side_effect=RoadServiceUnavailable('offline')),rows)
        self.assertEqual(rows,before)
        self.assertIn(PARTIAL_NOTICE,notes[:2])
        self.assertIsNone(road) # Partial map must never become the trusted global map.
        missing=[i for i in issues if i.reason==MISSING_ROADS]
        self.assertEqual(len(missing),1)
        self.assertEqual(out[0][missing[0].start:missing[0].end+1],rows[0][1:])
        self.assertAlmostEqual(out[0][0].lon,6)
        self.assertFalse(any(n.startswith('Handmatig behouden:') for n in notes))
        self.assertFalse(any('geen onopgeloste' in n for n in notes))

    def test_coverage_does_not_infer_roads_between_known_endpoints(self):
        p,q=Point(50,6),Point(50,6.01)
        self.assertFalse(edge_covered(p,q,[(5.99,49.9,6.004,50.1),(6.006,49.9,6.02,50.1)]))
        self.assertTrue(edge_covered(p,q,[(5.99,49.9,6.005,50.1),(6.005,49.9,6.02,50.1)]))

    def test_partial_network_drops_edges_outside_downloaded_area(self):
        self.cached()
        road,missing=partial_road(self.folder,source(),[list(range(5))],'trekking',35)
        self.assertTrue(missing)
        self.assertEqual([refs for refs,tags in road.ways],[[1,2]])

    def test_no_cache_never_returns_a_false_success(self):
        rows=source();before=copy.deepcopy(rows)
        with self.assertRaisesRegex(NoUsableRoads,'route, bewerkingen en instellingen zijn behouden'):
            self.run_route(Mock(side_effect=RoadServiceUnavailable('offline')),rows)
        self.assertEqual(rows,before)

    def test_complete_cache_needs_no_network_and_has_no_missing_data_issues(self):
        self.cached(full=True)
        download=Mock(side_effect=AssertionError('network must not be used'))
        result=self.run_route(download)
        download.assert_not_called()
        self.assertFalse(any(i.reason==MISSING_ROADS for i in result[2]))
        self.assertNotIn(PARTIAL_NOTICE,result[3])

    def test_new_completed_tile_survives_failed_later_download_and_is_used(self):
        def download(*args):
            self.cached()
            raise RoadServiceUnavailable('second tile failed')
        result=self.run_route(download)
        self.assertIn(PARTIAL_NOTICE,result[3])
        self.assertTrue(list((self.folder/'Vakken').glob('*.osm')))

    def test_cancel_during_download_never_presents_a_partial_proposal(self):
        self.cached();cancel=threading.Event()
        def download(*args):
            cancel.set();raise ValueError('cancelled')
        with self.assertRaises(RoutingCancelled):self.run_route(download,cancel=cancel)

    def test_slow_call_is_bounded_late_reply_ignored_and_inflight_count_bounded(self):
        entered=threading.Event();release=threading.Event();finished=threading.Event()
        def slow(*args,**kwargs):
            entered.set();release.wait(3);finished.set();return b'late'
        try:
            started=time.monotonic()
            with self.assertRaises(RoadServiceUnavailable):
                bounded_fetch(slow,'https://example.test/api',DownloadBudget(seconds=.08),False,None)
            self.assertLess(time.monotonic()-started,1)
            self.assertTrue(entered.is_set())
            second=Mock()
            with self.assertRaises(RoadServiceUnavailable):
                bounded_fetch(second,'https://example.test/api',DownloadBudget.foreground(),False,None)
            second.assert_not_called()
        finally:
            release.set();self.assertTrue(finished.wait(1))
            # Worker releases its slot after publishing the result.
            import road_transport
            self.assertTrue(road_transport._slot.acquire(timeout=1));road_transport._slot.release()

    def test_stop_interrupts_an_active_network_wait(self):
        release=threading.Event();cancel=threading.Event();entered=threading.Event()
        def slow(*args,**kwargs):entered.set();release.wait(3);return b'late'
        timer=threading.Timer(.08,cancel.set);timer.start()
        try:
            start=time.monotonic()
            with self.assertRaises(RoutingCancelled):
                bounded_fetch(slow,'https://example.test/api',DownloadBudget.foreground(),False,cancel.is_set)
            self.assertLess(time.monotonic()-start,1)
            self.assertTrue(entered.is_set())
        finally:
            release.set();timer.cancel()
            import road_transport
            self.assertTrue(road_transport._slot.acquire(timeout=1));road_transport._slot.release()

    def test_server_cooldown_is_preserved_across_new_alignment_attempts(self):
        url='https://example.test/api'
        fetch=Mock(side_effect=HTTPError(url,429,'busy',{'Retry-After':'120'},io.BytesIO(b'')))
        with self.assertRaises(RoadServiceUnavailable):
            fetch_road_data(fetch,url,budget=DownloadBudget.foreground())
        self.assertEqual(fetch.call_count,1)
        with self.assertRaises(RoadServiceUnavailable):
            fetch_road_data(fetch,url,budget=DownloadBudget.foreground())
        self.assertEqual(fetch.call_count,1)

    def test_fast_request_returns_bytes_and_budget_is_shared(self):
        fetch=Mock(return_value=b'<osm/>');budget=DownloadBudget.foreground()
        self.assertEqual(fetch_road_data(fetch,'https://example.test/api',budget=budget),b'<osm/>')
        self.assertEqual(budget.requests,1)
        self.assertEqual(budget.downloaded,6)
        self.assertLessEqual(fetch.call_args.kwargs['timeout'],20)

    def test_expired_download_budget_never_starts_another_request(self):
        fetch=Mock()
        with self.assertRaises(RoadServiceUnavailable):
            fetch_road_data(fetch,'https://example.test/api',budget=DownloadBudget(seconds=0))
        fetch.assert_not_called()
