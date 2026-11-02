# SPDX-License-Identifier: GPL-3.0-only
import sys, threading, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from gpx_core import Point, RoadMap
from prepared_roads import prepare_roads, retain_primary_preparation, recovery_endpoints_possible, verified_road_snapshot
from routing_runtime import routing_runtime, checkpoint, RoutingCancelled
from auto_alignment import automatic_alignment


def roads():
    return RoadMap(('<osm>'+''.join(f'<node id="{i+1}" lat="{50+i*.001}" lon="6"/>' for i in range(20))+
        '<way id="1">'+''.join(f'<nd ref="{i+1}"/>' for i in range(20))+
        '<tag k="highway" v="path"/></way></osm>').encode())


class RoutingPerformanceTests(unittest.TestCase):
    def test_changed_content_during_snapshot_discards_result_and_next_call_refreshes(self):
        road=roads();origin=Point(50,6)
        with self.assertRaisesRegex(ValueError,'Weggegevens gewijzigd'):
            with verified_road_snapshot(road):
                old=prepare_roads(road,'bike','trekking',False,origin)
                road.ways[0][1]['bicycle']='no'
        fresh=prepare_roads(road,'bike','trekking',False,origin)
        self.assertIsNot(old,fresh)
        self.assertFalse(fresh.edges)

    def test_repeated_preparation_hashes_only_at_operation_boundaries(self):
        import prepared_roads
        road=roads();origin=Point(50,6)
        with patch('prepared_roads.road_signature',wraps=prepared_roads.road_signature) as signature:
            with verified_road_snapshot(road):
                for _ in range(12):prepare_roads(road,'bike','trekking',False,origin)
            self.assertEqual(signature.call_count,2)

    def test_source_distances_do_not_leak_across_operations(self):
        from routing_runtime import source_lengths,route_cumulative
        from gpx_core import cumulative
        source=[[Point(50,6),Point(50.001,6)]]
        expected=cumulative(source[0])
        with source_lengths(source):
            first=route_cumulative(source[0]);second=route_cumulative(source[0])
            self.assertIs(first,second)
            self.assertEqual(list(first),expected)
        source[0][1]=Point(50.002,6)
        self.assertGreater(route_cumulative(source[0])[-1],expected[-1])

    def test_primary_survives_multiple_recovery_origins_with_two_graph_limit(self):
        road=roads();origin=Point(50,6)
        with retain_primary_preparation(road,'bike',False,origin):
            primary=prepare_roads(road,'bike','trekking',False,origin)
            for i in range(1,10):
                prepare_roads(road,'bike','trekking',False,Point(50+i*.001,6))
                self.assertIs(prepare_roads(road,'bike','trekking',False,origin),primary)
                self.assertLessEqual(len(road._prepared_roads),2)
            road.ways[0][1]['bicycle']='no'
            self.assertIsNot(prepare_roads(road,'bike','trekking',False,origin),primary)

    def test_precheck_preserves_exact_local_radius_decision(self):
        road=roads();source=[[Point(50,6),Point(50.019,6)]]
        for offset in (0,.00001,.00048,.00050,.002):
            section=[Point(50.005,6+offset),Point(50.006,6+offset)]
            actual=recovery_endpoints_possible(road,source,section,'bike',35,False)
            import math
            self.assertEqual(actual,offset*111195*math.cos(math.radians(section[0].lat))<=35)
        road.ways[0][1]['bicycle']='no'
        self.assertFalse(recovery_endpoints_possible(road,source,source[0],'bike',35,False))

    def test_precheck_keeps_result_and_avoids_impossible_local_graphs(self):
        source=[[Point(50+i*.001,6.01,100) for i in range(12)]]
        controls=[list(range(12))]
        with patch('prepared_roads.recovery_endpoints_possible',return_value=True):
            reference=automatic_alignment(roads(),source,controls,'bike',35)
        road=roads();actual=automatic_alignment(road,source,controls,'bike',35)
        self.assertEqual(actual,reference)
        self.assertEqual(road._preparation_stats['builds'],1)

    def test_cancellation_aborts_work_and_context_does_not_leak(self):
        stop=threading.Event();stop.set()
        with routing_runtime(stop.is_set,lambda message:None):
            with self.assertRaises(RoutingCancelled):
                automatic_alignment(roads(),[[Point(50,6),Point(50.001,6)]],[[0,1]],'walk')
        checkpoint()
        automatic_alignment(roads(),[[Point(50,6),Point(50.001,6)]],[[0,1]],'walk')

    def test_progress_is_throttled(self):
        messages=[]
        with routing_runtime(lambda:False,messages.append):
            with patch('routing_runtime.time.monotonic',return_value=10):
                for _ in range(1000):checkpoint('Route uitlijnen: 1/2')
        self.assertEqual(messages,['Route uitlijnen: 1/2'])

    def test_stop_during_calculation_aborts_before_returning_a_proposal(self):
        stop=threading.Event();messages=[]
        def progress(message):
            messages.append(message)
            stop.set()
        with routing_runtime(stop.is_set,progress):
            with self.assertRaises(RoutingCancelled):
                automatic_alignment(roads(),[[Point(50,6),Point(50.001,6)]],[[0,1]],'walk')
        self.assertTrue(messages)
