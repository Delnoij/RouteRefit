# SPDX-License-Identifier: GPL-3.0-only
"""Local proposals must never wait for or invoke a road service."""
import copy,sys,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from test_resilient_alignment import source,osm
from resilient_alignment import run_local_alignment,run_alignment,PARTIAL_NOTICE,MISSING_ROADS
from road_download import RoadServiceUnavailable
from routing_runtime import RoutingCancelled


class LocalFirstTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'tests');self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name);(self.folder/'Vakken').mkdir()
        self.rows=source();self.before=copy.deepcopy(self.rows)
        self.cancel=threading.Event()

    def seed(self,full=False):
        (self.folder/'Vakken'/('5.9,49.9,6.1,50.1.osm' if full else '5.99,49.99,6.01,50.009.osm')).write_bytes(osm())

    def arguments(self):
        return (self.folder,self.rows,[list(range(5))],'bike','trekking',35,set(),False,None,self.cancel,lambda s:None)

    def test_partial_geometry_matches_previous_fallback_without_waiting_or_downloading(self):
        self.seed()
        previous=run_alignment(*self.arguments(),Mock(side_effect=RoadServiceUnavailable('offline')))
        with patch('werkbank.fetch',side_effect=AssertionError('No network in local calculation')):
            result,missing=run_local_alignment(*self.arguments())
        self.assertTrue(missing);self.assertEqual(result[:3],previous[:3])
        self.assertEqual(result[3][2:],previous[3][2:]);self.assertIsNone(result[4])
        issue=next(i for i in result[2] if i.reason==MISSING_ROADS)
        self.assertEqual(result[0][0][issue.start:issue.end+1],self.rows[0][1:])
        self.assertEqual(self.rows,self.before)

    def test_complete_cache_has_identical_result_and_needs_no_download(self):
        self.seed(full=True)
        no_download=Mock(side_effect=AssertionError('Network'))
        previous=run_alignment(*self.arguments(),no_download)
        result,missing=run_local_alignment(*self.arguments())
        self.assertFalse(missing);self.assertEqual(result[:4],previous[:4])
        no_download.assert_not_called();self.assertNotIn(PARTIAL_NOTICE,result[3])

    def test_no_cache_returns_no_false_proposal_and_requests_background_work(self):
        with patch('werkbank.fetch',side_effect=AssertionError('Network')):
            result,missing=run_local_alignment(*self.arguments())
        self.assertIsNone(result);self.assertTrue(missing);self.assertEqual(self.rows,self.before)

    def test_cancel_does_not_produce_a_proposal_or_download_request(self):
        self.seed();self.cancel.set()
        with self.assertRaises((RoutingCancelled,ValueError)):
            run_local_alignment(*self.arguments())
        self.assertEqual(self.rows,self.before)

    def test_calculation_failure_is_not_disguised_as_missing_data(self):
        self.seed(full=True)
        with self.assertRaisesRegex(ValueError,'calculation failed'):
            run_local_alignment(*self.arguments(),matcher=Mock(side_effect=ValueError('calculation failed')))
