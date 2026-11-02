# SPDX-License-Identifier: GPL-3.0-only
import sys,unittest
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from access_policy import way_permitted
from cycling_policy import travel_directions,quality_factor
from activity_policy import suitable,barrier_blocked
from gpx_core import RoadMap,Point
from profile_settings import TRANSPORTS,restored_settings
from export_timing import prepare_activity
from prepared_roads import prepare_roads
from turn_policy import restricted_path

def junction(restriction='no_right_turn',extra='',via_way=False):
    nodes={1:(50,6),2:(50.001,6),3:(50.001,6.001),4:(50.0016,6),5:(50.0016,6.001)}
    ways={10:[1,2],20:[2,3],30:[2,4],40:[4,5,3]}
    via='<member type="way" ref="30" role="via"/>' if via_way else '<member type="node" ref="2" role="via"/>'
    to=40 if via_way else 20
    xml='<osm>'+''.join(f'<node id="{n}" lat="{a}" lon="{b}"/>' for n,(a,b) in nodes.items())
    xml+=''.join(f'<way id="{w}">'+''.join(f'<nd ref="{n}"/>' for n in refs)+'<tag k="highway" v="residential"/></way>' for w,refs in ways.items())
    xml+=f'<relation id="100"><member type="way" ref="10" role="from"/>{via}<member type="way" ref="{to}" role="to"/><tag k="type" v="restriction"/><tag k="restriction" v="{restriction}"/>{extra}</relation></osm>'
    return RoadMap(xml.encode())

class ActivityRoutingTests(unittest.TestCase):
    def test_six_activities_migrate_and_no_speedpedelec(self):
        self.assertEqual(set(TRANSPORTS),{'Lopen','Fiets','MTB','Gravelfiets','Auto','Motor'})
        for activity in TRANSPORTS:
            self.assertEqual(restored_settings({'activity':activity},'Wandelen · normaal')[0],activity)
        self.assertEqual(restored_settings({'transport':'MTB'},'Fietsen · mountainbike')[0],'MTB')

    def test_motor_access_is_separate_from_walk_and_bike(self):
        self.assertTrue(way_permitted({'highway':'motorway'},'motorcar'))
        self.assertFalse(way_permitted({'highway':'motorway'},'bike'))
        self.assertFalse(way_permitted({'highway':'cycleway','bicycle':'yes'},'motorcycle'))
        self.assertFalse(way_permitted({'highway':'residential','motorcycle':'no'},'motorcycle'))
        self.assertTrue(way_permitted({'highway':'residential','motor_vehicle':'no','motorcycle':'yes'},'motorcycle'))
        self.assertFalse(way_permitted({'highway':'residential','motor_vehicle':'no','motorcycle':'yes'},'motorcar'))
        self.assertFalse(way_permitted({'highway':'track','tracktype':'grade5','motorcar':'yes'},'motorcar'))
        self.assertTrue(barrier_blocked({'barrier':'bollard'},'motorcar'))

    def test_direction_tags_do_not_leak_between_activities(self):
        tags={'highway':'residential','oneway':'yes','oneway:bicycle':'no'}
        self.assertEqual(travel_directions(tags,'bike'),(True,True))
        self.assertEqual(travel_directions(tags,'motorcar'),(True,False))
        self.assertEqual(travel_directions({'highway':'motorway'},'motorcar'),(True,False))
        self.assertEqual(travel_directions(dict(tags,**{'motorcycle:forward':'no'}),'motorcycle'),(False,False))

    def test_gravel_has_own_surface_preferences_and_terrain_limits(self):
        self.assertLess(quality_factor({'surface':'gravel'},'gravel'),quality_factor({'surface':'gravel'},'trekking'))
        self.assertTrue(suitable({'highway':'track','surface':'compacted','tracktype':'grade2'},'bike','gravel'))
        for tags in ({'surface':'mud'},{'tracktype':'grade5'},{'mtb:scale':'3'},{'highway':'steps'}):
            self.assertFalse(suitable(tags,'bike','gravel'))

    def test_times_for_all_six_activities_preserve_requested_average(self):
        source=[[Point(50,6,100),Point(50.001,6,110),Point(50.002,6,100)]]
        for activity,speed in [('Lopen',4.5),('Fiets',20),('MTB',14),('Gravelfiets',22),('Auto',80),('Motor',90)]:
            out,report=prepare_activity(source,activity,speed,datetime(2026,1,1,tzinfo=timezone.utc))
            elapsed=(out[0][-1].time-out[0][0].time).total_seconds()
            self.assertAlmostEqual(report['distance_km']/elapsed*3600,speed,places=4)
            self.assertEqual([(p.lat,p.lon,p.ele) for p in out[0]],[(p.lat,p.lon,p.ele) for p in source[0]])

    def test_node_turn_restriction_routes_around_for_motor_and_except_bicycle(self):
        road=junction(extra='<tag k="except" v="bicycle"/>')
        for mode,expected in [('motorcar',[1,2,4,5,3]),('motorcycle',[1,2,4,5,3])]:
            p=prepare_roads(road,mode,'road',False,road.nodes[1])
            answer=restricted_path(p.graph,p.edge_ways,p.turns,1,3,1000)
            self.assertEqual(answer[0],expected)
        self.assertFalse(prepare_roads(road,'bike','trekking',False,road.nodes[1]).turns)

    def test_arrival_survives_a_control_point_exactly_at_the_restricted_junction(self):
        road=junction();p=prepare_roads(road,'motorcar','road',False,road.nodes[1])
        first=restricted_path(p.graph,p.edge_ways,p.turns,1,2,1000)
        second=restricted_path(p.graph,p.edge_ways,p.turns,2,3,1000,first[3])
        self.assertEqual(second[0],[2,4,5,3])
        source=[[Point(50,6,100),Point(50.001,6,100),Point(50.001,6.001,100)]]
        out,notes=road.snap(source,'motorcar',5,control_indices=[[0,1,2]])
        self.assertTrue(any(p.lat>50.0015 for p in out[0]))

    def test_via_way_restriction_retains_history_and_avoids_forbidden_sequence(self):
        road=junction(via_way=True);p=prepare_roads(road,'motorcar','road',False,road.nodes[1])
        first=restricted_path(p.graph,p.edge_ways,p.turns,1,4,1000)
        self.assertIsNotNone(first)
        self.assertIsNone(p.turns.step(first[3],4,5,next(i for i,w in enumerate(p.edge_ways) if w==40),p.edge_ways))

    def test_only_turn_and_vehicle_specific_restriction(self):
        road=junction('only_right_turn',extra='<tag k="restriction:bicycle" v="no_right_turn"/>')
        motor=prepare_roads(road,'motorcar','road',False,road.nodes[1])
        self.assertEqual(restricted_path(motor.graph,motor.edge_ways,motor.turns,1,3,1000)[0],[1,2,3])
        bicycle=prepare_roads(road,'bike','trekking',False,road.nodes[1])
        self.assertEqual(restricted_path(bicycle.graph,bicycle.edge_ways,bicycle.turns,1,3,1000)[0],[1,2,4,5,3])

    def test_coverage_crop_and_index_roundtrip_keep_turn_restrictions(self):
        from road_index import road_xml
        from resilient_alignment import restrict_to_coverage
        road=RoadMap(road_xml(junction()))
        restrict_to_coverage(road,[(5.99,49.99,6.02,50.02)])
        p=prepare_roads(road,'motorcar','road',False,road.nodes[1])
        self.assertEqual(restricted_path(p.graph,p.edge_ways,p.turns,1,3,1000)[0],[1,2,4,5,3])

    def test_conditional_turns_and_spaced_exceptions(self):
        road=junction('none',extra='<tag k="restriction:conditional" v="no_right_turn @ (Mo-Fr 07:00-09:00)"/>')
        p=prepare_roads(road,'motorcar','road',False,road.nodes[1])
        self.assertTrue(p.turns.conditional)
        self.assertEqual(restricted_path(p.graph,p.edge_ways,p.turns,1,3,1000)[0],[1,2,4,5,3])
        road=junction(extra='<tag k="except" v="bus; bicycle"/>')
        self.assertFalse(prepare_roads(road,'bike','trekking',False,road.nodes[1]).turns)

    def test_turn_aware_search_only_skipped_when_no_junction_is_reachable(self):
        road=junction();p=prepare_roads(road,'motorcar','road',False,road.nodes[1])
        self.assertTrue(p.turns.reachable(p.coords,1,3,1000,None))
        self.assertFalse(p.turns.reachable(p.coords,4,5,80,None))
        # Active via-way restrictions must survive any distance-based shortcut.
        self.assertTrue(p.turns.reachable(p.coords,4,5,80,(0,1,((0,1),))))

if __name__=='__main__':unittest.main()
