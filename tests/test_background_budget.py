# SPDX-License-Identifier: GPL-3.0-only
import sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from urllib.error import URLError
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from road_download import DownloadBudget,RoadServiceUnavailable,fetch_road_data
from road_transport import bounded_fetch,_cooldowns,_slot
from local_first_ui import failure_detail
from test_road_download import blocked,OSM,URL
from gpx_core import Point
from routing_runtime import RoutingCancelled
import werkbank as wb
import i18n


class BackgroundBudgetTests(unittest.TestCase):
    def setUp(self):
        _cooldowns.clear();self.addCleanup(_cooldowns.clear)
        i18n.configure('nl',ROOT/'src')

    def test_only_background_allows_queue_execution_and_transfer(self):
        fore=DownloadBudget.foreground();back=DownloadBudget.background()
        self.assertEqual((fore.seconds,fore.request_seconds,fore.query_seconds),(30,20,15))
        self.assertEqual((back.seconds,back.request_seconds,back.query_seconds),(60,45,25))
        fetch=Mock(return_value=OSM)
        self.assertEqual(fetch_road_data(fetch,URL,budget=back),OSM)
        self.assertEqual(fetch.call_args.kwargs['timeout'],45)
        self.assertEqual(back.requests,1)

    def test_map_query_uses_the_background_server_limit(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as tmp,patch.object(wb,'MAPS',Path(tmp)),patch.object(wb,'fetch',return_value=OSM) as fetch:
            wb.download_map([[Point(50,6),Point(50.001,6)]],budget=DownloadBudget.background())
            from urllib.parse import parse_qs,urlsplit
            query=parse_qs(urlsplit(fetch.call_args.args[0]).query)['data'][0]
            self.assertIn('[timeout:25]',query)
            self.assertEqual(fetch.call_args.kwargs['timeout'],45)

    def test_entire_background_budget_stays_bounded(self):
        budget=DownloadBudget.background();budget.started=time.monotonic()-60
        fetch=Mock()
        with self.assertRaises(RoadServiceUnavailable) as seen:fetch_road_data(fetch,URL,budget=budget)
        self.assertEqual(seen.exception.reason,'budget');fetch.assert_not_called()
        self.assertIn('60',failure_detail(seen.exception))

    def test_service_causes_remain_distinguishable_without_private_details(self):
        cases=[(blocked(429),'rate'),(blocked(503),'busy'),(URLError('private/path'),'connection'),
               (TimeoutError('private/path'),'slow'),(URLError(TimeoutError('private/path')),'slow')]
        for error,reason in cases:
            _cooldowns.clear()
            with self.assertRaises(RoadServiceUnavailable) as seen:
                fetch_road_data(Mock(side_effect=error),URL,budget=DownloadBudget.background())
            self.assertEqual(seen.exception.reason,reason)
            self.assertNotIn('private/path',failure_detail(seen.exception))
        self.assertNotIn('private',failure_detail(ValueError('private coordinates and path')))

    def test_hanging_background_response_is_stopped_and_late_reply_discarded(self):
        release=threading.Event()
        def slow(*args,**kwargs):release.wait(3);return b'late'
        budget=DownloadBudget.background();budget.request_seconds=.08
        try:
            with self.assertRaises(RoadServiceUnavailable) as seen:
                bounded_fetch(slow,URL,budget,False,None)
            self.assertEqual(seen.exception.reason,'slow')
        finally:
            release.set();self.assertTrue(_slot.acquire(timeout=1));_slot.release()

    def test_stopping_interrupts_background_wait_without_waiting_45_seconds(self):
        release=threading.Event();cancel=threading.Event()
        def slow(*args,**kwargs):release.wait(3);return OSM
        timer=threading.Timer(.08,cancel.set);timer.start();started=time.monotonic()
        try:
            with self.assertRaises(RoutingCancelled):
                bounded_fetch(slow,URL,DownloadBudget.background(),False,cancel.is_set)
            self.assertLess(time.monotonic()-started,1)
        finally:
            release.set();timer.cancel();self.assertTrue(_slot.acquire(timeout=1));_slot.release()
