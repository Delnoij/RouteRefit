# SPDX-License-Identifier: GPL-3.0-only
import copy,sys,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from dataclasses import replace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from gpx_core import Point,RoadMap,AlignmentError
from access_review import access_relaxed_map


def road():
    xml='<osm>'+''.join(f'<node id="{i+1}" lat="{50+i*.001}" lon="6"/>' for i in range(9))
    xml+='<way id="1">'+''.join(f'<nd ref="{i+1}"/>' for i in range(9))+'<tag k="highway" v="path"/></way></osm>'
    return RoadMap(xml.encode())


def fields(value):
    out,notes,mapped=value
    return [[(p.lat,p.lon,p.ele,p.time) for p in row] for row in out],notes,mapped


class PreparedRoadTests(unittest.TestCase):
    def setUp(self):
        self.road=road()
        self.source=[[Point(50+i*.001,6) for i in range(9)]]
        self.options=dict(control_indices=[[0,2,4,6,8]],with_controls=True)

    def snap(self,source=None,mode='bike',**options):
        return self.road.snap(source or self.source,mode,5,**(self.options|options))

    def prepared(self):return next(iter(self.road._prepared_roads.values()))

    def test_repeat_reuses_network_and_searches_without_changing_result(self):
        cold=self.snap();prepared=self.prepared();searches=prepared.stats['searches']
        warm=self.snap()
        self.assertEqual(fields(cold),fields(warm))
        self.assertEqual(self.road._preparation_stats,dict(builds=1,hits=1))
        self.assertEqual(prepared.stats['searches'],searches)
        self.assertGreater(prepared.stats['path_hits'],0)

    def test_one_changed_control_reuses_unaffected_searches(self):
        self.snap();prepared=self.prepared();searches=prepared.stats['searches']
        edited=copy.deepcopy(self.source)
        edited[0][4]=replace(edited[0][4],lat=edited[0][4].lat+.0001)
        result=self.snap(edited)
        fresh=road().snap(edited,'bike',5,**self.options)
        self.assertEqual(fields(result),fields(fresh))
        self.assertGreater(prepared.stats['searches'],searches)
        self.assertGreater(prepared.stats['path_hits'],0)
        self.assertEqual(self.road._preparation_stats['builds'],1)

    def test_reused_geometry_does_not_replay_old_times_or_heights(self):
        self.snap();start=datetime(2026,1,1,tzinfo=timezone.utc)
        timed=[[replace(p,ele=100+i,time=start+timedelta(minutes=i)) for i,p in enumerate(self.source[0])]]
        out,notes,mapped=self.snap(timed)
        self.assertEqual(out[0][mapped[0][2]].time,timed[0][4].time)
        self.assertEqual(out[0][mapped[0][2]].ele,104)
        self.assertIsNone(self.source[0][4].time)
        self.assertGreater(self.prepared().stats['path_hits'],0)

    def test_in_place_access_change_invalidates_the_network(self):
        self.snap();prepared=self.prepared()
        self.road.ways[0][1]['bicycle']='no'
        with self.assertRaises(AlignmentError):self.snap()
        self.assertIsNot(self.prepared(),prepared)

    def test_in_place_direction_change_does_not_reuse_forbidden_path(self):
        self.snap()
        self.road.ways[0][1]['oneway:bicycle']='-1'
        with self.assertRaises(AlignmentError):self.snap()

    def test_new_physical_barrier_invalidates_the_network(self):
        self.snap()
        self.road.node_tags[5]={'barrier':'wall'}
        with self.assertRaises(AlignmentError):self.snap()

    def test_profile_and_private_access_have_separate_preparation(self):
        self.snap();first=self.prepared()
        self.road.cycling_style='mountainbike';self.snap()
        self.assertIsNot(list(self.road._prepared_roads.values())[-1],first)
        self.road.ways[0][1]['access']='private'
        self.snap(allow_private=True)
        with self.assertRaises(AlignmentError):self.snap(allow_private=False)

    def test_diagnostic_relaxation_never_contaminates_the_strict_map(self):
        self.road.ways[0][1]['access']='private'
        with self.assertRaises(AlignmentError):self.snap()
        relaxed=access_relaxed_map(self.road,'bike')
        relaxed.snap(self.source,'bike',5,**self.options)
        with self.assertRaises(AlignmentError):self.snap()

    def test_other_route_projection_invalidates_affected_search_dependencies(self):
        a,b=self.source[0][0],self.source[0][-1]
        source=[[a,b],[self.source[0][2],self.source[0][6]]]
        options=dict(control_indices=[[0,1],[0,1]],with_controls=True)
        self.road.snap(source,'walk',5,**options)
        edited=[source[0],[Point(50.0025,6),source[1][-1]]]
        cached=self.road.snap(edited,'walk',5,**options)
        fresh=road().snap(edited,'walk',5,**options)
        self.assertEqual(fields(cached),fields(fresh))

    def test_profile_preparation_is_bounded_in_memory(self):
        for mode,style,private in [('bike','trekking',False),('bike','mountainbike',False),('walk','trekking',False),('walk','trekking',True)]:
            self.road.cycling_style=style;self.snap(mode=mode,allow_private=private)
        self.assertLessEqual(len(self.road._prepared_roads),2)

    def test_changed_node_geometry_invalidates_preparation(self):
        self.snap();previous=self.prepared()
        self.road.nodes[5]=Point(50.0041,6)
        actual=self.snap()
        fresh=road();fresh.nodes[5]=Point(50.0041,6)
        expected=fresh.snap(self.source,'bike',5,**self.options)
        self.assertEqual(fields(actual),fields(expected))
        self.assertIsNot(self.prepared(),previous)

    def test_simultaneous_edits_share_preparation_without_mixing_paths(self):
        from concurrent.futures import ThreadPoolExecutor
        sources=[];expected=[]
        for i in range(4):
            source=copy.deepcopy(self.source)
            source[0][4]=replace(source[0][4],lat=source[0][4].lat+i*.00004)
            sources.append(source)
            expected.append(fields(road().snap(source,'bike',5,**self.options)))
        def run(i):return i,fields(self.snap(sources[i]))
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(run,[i%4 for i in range(32)]))
        for index,result in results:self.assertEqual(result,expected[index])
        self.assertEqual(self.road._preparation_stats['builds'],1)

if __name__=='__main__':unittest.main()
