# SPDX-License-Identifier: GPL-3.0-only
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from package_resources import Resources,competing_load


class ResourceTests(unittest.TestCase):
    def test_own_work_is_not_counted_as_competing_work(self):
        self.assertEqual(competing_load((0,0,0,0),(50,60,40,50)),0)
        self.assertAlmostEqual(competing_load((0,0,0,0),(10,30,70,10)),.8)

    def test_busy_work_yields_and_spare_work_does_not(self):
        r=Resources()
        with patch('package_resources.time.sleep') as sleep:
            r.cooperate();sleep.assert_not_called();r.busy=True;r.cooperate();sleep.assert_called_once()

    def test_windows_monitor_starts_and_restores_priority(self):
        import os,time
        if os.name!='nt':self.skipTest('Windows only')
        with Resources() as r:
            self.assertIsNotNone(r.handle);self.assertIn(r.cache_kib,(32768,131072))
            first=r.sample();time.sleep(.02);second=r.sample()
            # Windows aggregates per-processor counters, which need not be
            # monotonic over a 20 ms interval. The policy handles total <= 0.
            self.assertTrue(all(isinstance(value,int) and value>=0 for value in first+second))
            self.assertGreater(second[1]+second[2],0)
        self.assertFalse(r.thread.is_alive())

    def test_competing_load_lowers_priority_then_recovers(self):
        from unittest.mock import Mock
        r=Resources();r.handle=1;r.priority=0;r.headless=False;r.kernel=Mock()
        r.stop=Mock();r.stop.wait.side_effect=[False,False,False,False,True]
        r.sample=Mock(return_value=(0,0,0,0))
        with patch('package_resources.competing_load',side_effect=[.8,.05,.05,.05]):r.monitor()
        priorities=[call.args[1] for call in r.kernel.SetThreadPriority.call_args_list]
        self.assertEqual(priorities,[-1,-1,-1,0]);self.assertFalse(r.busy)


if __name__=='__main__':unittest.main()
