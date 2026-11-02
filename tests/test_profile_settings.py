# SPDX-License-Identifier: GPL-3.0-only
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from profile_settings import restored_settings, TRANSPORTS
from gpx_core import Point
from proposal_summary import proposal_summary
from proposal_review_ui import same_route


class ProfileSettingsTests(unittest.TestCase):
    def test_legacy_profiles_migrate_to_transport_and_timing(self):
        for old, vehicle, tempo in [('Wandelen · stevig','Lopen','Stevig'), ('Fietsen · sportief','Fiets','Sportief'), ('Fietsen · mountainbike','MTB','Normaal')]:
            self.assertEqual(restored_settings({},old),(vehicle,'Meest logisch',tempo,old))

    def test_explicit_transport_is_not_overridden_by_old_timing_profile(self):
        self.assertEqual(restored_settings({'transport':'Lopen','timing_profile':'Fietsen · sportief'},'Fietsen · trekking'),
                         ('Lopen','Meest logisch','Normaal','Wandelen · normaal'))

    def test_unknown_or_malformed_fields_do_not_enable_unsupported_profiles(self):
        for vehicle in ('Trein', 'Speed Pedelec', [], {}, None):
            self.assertEqual(restored_settings({'transport':vehicle},'Fietsen · trekking')[0],'Fiets')
        self.assertEqual(restored_settings([], 'Wandelen · rustig')[0],'Lopen')

    def test_estimated_duration_preserves_available_mean_speed(self):
        start=datetime(2026,1,1,tzinfo=timezone.utc)
        before=[[Point(50,6,time=start),Point(50.001,6,time=start+timedelta(seconds=60))]]
        after=[[Point(50,6),Point(50.002,6)]]
        summary=proposal_summary(before,before,after,40)
        self.assertAlmostEqual(summary['seconds'],120,places=3)
        self.assertTrue(summary['geometry_changed'])
        self.assertGreater(summary['original_delta_km'],0)
        self.assertIsNone(after[0][0].time)

    def test_missing_elevation_is_unknown_and_partial_is_identified(self):
        no_height=[[Point(50,6),Point(50.001,6)]]
        partial=[[Point(50,6,10),Point(50.001,6,20),Point(50.002,6)]]
        self.assertIsNone(proposal_summary(no_height,no_height,no_height,4.5)['ascent'])
        summary=proposal_summary(no_height,no_height,partial,4.5)
        self.assertEqual(summary['ascent'],10)
        self.assertAlmostEqual(summary['elevation_coverage'],2/3)

    def test_segment_gaps_are_not_added_as_distance_or_ascent(self):
        route=[[Point(50,6,0),Point(50.001,6,10)], [Point(51,6,1000),Point(51.001,6,1005)]]
        summary=proposal_summary(route,route,route,4.5)
        self.assertEqual(summary['ascent'],15)
        self.assertLess(summary['km'],1)

    def test_invalid_speed_does_not_fabricate_travel_time(self):
        route=[[Point(50,6),Point(50.001,6)]]
        for speed in (None,0,float('nan'),float('inf')):
            self.assertIsNone(proposal_summary(route,route,route,speed)['seconds'])

    def test_elevation_or_time_changes_also_require_proposal_acceptance(self):
        first=[[Point(50,6,10),Point(50.001,6,20)]]
        self.assertTrue(same_route(first,[list(first[0])]))
        self.assertFalse(same_route(first,[[Point(50,6,11),Point(50.001,6,20)]]))


if __name__=='__main__':
    unittest.main()
