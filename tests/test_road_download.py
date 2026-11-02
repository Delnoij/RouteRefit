# SPDX-License-Identifier: GPL-3.0-only
"""A failed road request stops without countdowns or automatic child requests."""
import io, sys, tempfile, unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, parse_qs
from unittest.mock import Mock, patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from road_download import retry_delay, fetch_road_data, DownloadBudget, road_query_url, RoadServiceUnavailable
from road_transport import _cooldowns, cooldown
from routing_runtime import RoutingCancelled
from gpx_core import Point
import werkbank as wb
URL='https://overpass-api.de/api/interpreter'
OSM=b'<osm><node id="1" lat="50" lon="6"/><node id="2" lat="50.001" lon="6"/><way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="path"/></way></osm>'

def blocked(code=509,body=b'Please try again in 17 seconds.',headers=None):
    return HTTPError(URL,code,'temporarily unavailable',headers or {},io.BytesIO(body))

class RoadDownloadTests(unittest.TestCase):
    def setUp(self):
        _cooldowns.clear();self.addCleanup(_cooldowns.clear)

    def test_service_failures_stop_after_one_request_without_countdown(self):
        for code in (429,502,503,504,509):
            with self.subTest(code=code):
                _cooldowns.clear();fetch=Mock(side_effect=[blocked(code),OSM]);waiting=Mock()
                with patch('road_download.time.sleep') as sleep:
                    with self.assertRaisesRegex(RoadServiceUnavailable,'niet automatisch opnieuw'):
                        fetch_road_data(fetch,URL,waiting=waiting,allow_split=True)
                self.assertEqual(fetch.call_count,1)
                waiting.assert_not_called();sleep.assert_not_called()

    def test_cooldown_blocks_manual_attempt_until_server_deadline(self):
        fetch=Mock(side_effect=[blocked(headers={'Retry-After':'120'}),OSM])
        with self.assertRaises(RoadServiceUnavailable):fetch_road_data(fetch,URL)
        self.assertGreater(cooldown(URL),120)
        with self.assertRaises(RoadServiceUnavailable):fetch_road_data(fetch,URL)
        self.assertEqual(fetch.call_count,1)
        _cooldowns.clear() # Simulate elapsed cooldown; never wait inside the app.
        self.assertEqual(fetch_road_data(fetch,URL),OSM)
        self.assertEqual(fetch.call_count,2)

    def test_connection_failure_keeps_route_and_stops(self):
        for error in (URLError('offline'),TimeoutError('slow')):
            _cooldowns.clear();fetch=Mock(side_effect=error)
            with self.assertRaisesRegex(RoadServiceUnavailable,'route en opgeslagen kaartvakken zijn behouden'):
                fetch_road_data(fetch,URL)
            self.assertEqual(fetch.call_count,1)

    def test_default_timeout_is_bounded_and_cancellable(self):
        fetch=Mock(return_value=OSM)
        self.assertEqual(fetch_road_data(fetch,URL),OSM)
        self.assertLessEqual(fetch.call_args.kwargs['timeout'],20)
        self.assertTrue(callable(fetch.call_args.kwargs['cancelled']))
        self.assertEqual(DownloadBudget().seconds,30)

    def test_legacy_unlimited_budget_cannot_disable_deadline(self):
        budget=DownloadBudget(seconds=None);fetch=Mock(return_value=OSM)
        fetch_road_data(fetch,URL,budget=budget)
        self.assertEqual(budget.seconds,30)
        self.assertLessEqual(fetch.call_args.kwargs['timeout'],20)

    def test_cancelled_and_expired_requests_do_not_contact_service(self):
        fetch=Mock()
        with self.assertRaises(RoutingCancelled):fetch_road_data(fetch,URL,cancelled=lambda:True)
        with self.assertRaises(RoadServiceUnavailable):fetch_road_data(fetch,URL,budget=DownloadBudget(seconds=0))
        fetch.assert_not_called()

    def test_resource_errors_never_split_or_cache_partial_results(self):
        responses=(blocked(504),blocked(400,b'Too many nodes'),
            b'<osm><remark>runtime error: Query timed out</remark></osm>',
            b'<osm><remark>runtime error: out of memory</remark></osm>',
            b'<osm><remark>runtime error: timeout</remark></osm>')
        for response in responses:
            _cooldowns.clear()
            with self.subTest(response=type(response).__name__),tempfile.TemporaryDirectory(dir=ROOT/'tests') as folder:
                fetch=Mock(side_effect=[response,OSM])
                with patch.object(wb,'MAPS',Path(folder)),patch.object(wb,'fetch',fetch):
                    with self.assertRaises(ValueError):wb.download_map([[Point(50,6),Point(50.001,6)]])
                self.assertEqual(fetch.call_count,1)
                self.assertFalse(list(Path(folder).rglob('*.osm')))

    def test_completed_tiles_survive_and_manual_resume_only_downloads_missing(self):
        rows=[[Point(50,6),Point(50.025,6)]]
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as folder,patch.object(wb,'MAPS',Path(folder)),patch.object(wb.time,'sleep'):
            fetch=Mock(side_effect=[OSM,blocked(429)])
            with patch.object(wb,'fetch',fetch):
                with self.assertRaises(RoadServiceUnavailable):wb.download_map(rows)
            self.assertEqual(fetch.call_count,2)
            completed=list((Path(folder)/'Vakken').glob('*.osm'))
            self.assertEqual(len(completed),1);before=completed[0].read_bytes()
            _cooldowns.clear()
            with patch.object(wb,'fetch',return_value=OSM) as resumed:
                self.assertTrue(wb.download_map(rows).exists())
            self.assertEqual(resumed.call_count,1)
            self.assertEqual(completed[0].read_bytes(),before)

    def test_failed_refresh_keeps_all_existing_tiles(self):
        rows=[[Point(50,6),Point(50.025,6)]]
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as folder,patch.object(wb,'MAPS',Path(folder)),patch.object(wb.time,'sleep'):
            with patch.object(wb,'fetch',return_value=OSM):wb.download_map(rows)
            before={p.name:p.read_bytes() for p in (Path(folder)/'Vakken').glob('*.osm')}
            with patch.object(wb,'fetch',side_effect=[OSM,blocked(503)]) as failed:
                with self.assertRaises(RoadServiceUnavailable):wb.download_map(rows,refresh=True)
            self.assertEqual(failed.call_count,2)
            self.assertEqual({p.name:p.read_bytes() for p in (Path(folder)/'Vakken').glob('*.osm')},before)

    def test_complete_cache_works_during_service_cooldown(self):
        rows=[[Point(50,6),Point(50.001,6)]]
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as folder,patch.object(wb,'MAPS',Path(folder)):
            with patch.object(wb,'fetch',return_value=OSM):path=wb.download_map(rows)
            cooldown(URL,120)
            with patch.object(wb,'fetch',side_effect=AssertionError('must use cache')):
                self.assertEqual(wb.download_map(rows),path)

    def test_server_body_and_headers_are_respected(self):
        self.assertEqual(retry_delay({},'Please try again in 17 seconds.',0),18)
        self.assertEqual(retry_delay({'Retry-After':'30'},'Please try again in 17 seconds.',0),31)
        now=datetime(2026,10,30,tzinfo=timezone.utc)
        self.assertEqual(retry_delay({'Retry-After':format_datetime(now+timedelta(seconds=40))},'',0,now),41)

    def test_nonretryable_error_keeps_body_for_caller(self):
        with self.assertRaises(HTTPError) as seen:fetch_road_data(Mock(side_effect=blocked(403,b'forbidden')),URL)
        self.assertEqual(seen.exception.read(),b'forbidden');seen.exception.close()

    def test_request_budget_never_starts_extra_request(self):
        fetch=Mock()
        with self.assertRaises(RoadServiceUnavailable):fetch_road_data(fetch,URL,budget=DownloadBudget(requests=400))
        fetch.assert_not_called()

    def test_query_only_contains_road_area_and_read_only_filters(self):
        url=road_query_url((6,50,6.03,50.02))
        self.assertEqual(urlparse(url).hostname,'overpass-api.de')
        query=parse_qs(urlparse(url).query)['data'][0]
        self.assertIn('way["highway"](50.0000000,6.0000000,50.0200000,6.0300000)',query)
        self.assertIn('rel(bw.roads)["type"="restriction"]',query)
        self.assertNotIn('trkpt',query)

if __name__=='__main__':unittest.main()
