# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
import test_region_packages as fixtures
import package_background as bg
from region_packages import installed


class BackgroundTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PackageTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.folder=self.f.maps;self.register=[]

    def enable(self):bg.configure(self.folder,True,lambda *a:self.register.append(a))

    def test_default_off_does_not_spawn_register_or_download(self):
        self.assertFalse(bg.settings(self.folder)['enabled'])
        with patch('package_background.subprocess.Popen',side_effect=AssertionError('spawn')):
            bg.launch(self.folder);bg.run(self.folder)
        with self.assertRaises(ValueError):bg.enqueue(self.folder,[fixtures.REGION])

    def test_explicit_enable_disable_cancels_queue_and_removes_start(self):
        self.enable();job=bg.enqueue(self.folder,[fixtures.REGION])
        bg.configure(self.folder,False,lambda *a:self.register.append(a))
        self.assertEqual([r[2] for r in self.register],[True,False])
        self.assertEqual(self.register[0][0],self.register[1][0])
        self.assertFalse(bg.settings(self.folder)['enabled'])
        self.assertTrue((bg.jobs_dir(self.folder)/(job+'.stop')).exists())
        bg.run(self.folder);self.assertEqual(installed(self.folder),[])

    def test_failed_registration_does_not_enable(self):
        with self.assertRaises(ValueError):
            bg.configure(self.folder,True,lambda *a:(_ for _ in ()).throw(ValueError('Windows')))
        self.assertFalse(bg.settings(self.folder)['enabled'])

    def test_worker_finishes_explicit_queue_without_gui(self):
        self.enable();job=bg.enqueue(self.folder,[fixtures.REGION])
        def install(folder,region,cancelled,progress,full):
            return fixtures.install_or_update(folder,region,cancelled,progress,full,fetch=self.f.fetch)
        with patch.object(bg,'install_or_update',side_effect=install):bg.run(self.folder)
        self.assertEqual(bg.status(self.folder,job)['state'],'done')
        self.assertEqual(len(installed(self.folder)),1)

    def test_worker_failure_is_not_retried(self):
        self.enable();job=bg.enqueue(self.folder,[fixtures.REGION])
        with patch.object(bg,'install_or_update',side_effect=TimeoutError) as install:
            bg.run(self.folder);bg.run(self.folder)
        self.assertEqual(install.call_count,1);self.assertEqual(bg.status(self.folder,job)['state'],'error')

    def test_interrupted_job_requires_review_not_silent_retry(self):
        self.enable();job=bg.enqueue(self.folder,[fixtures.REGION]);item=bg.status(self.folder,job)
        item['state']='running';bg.atomic_json(bg.jobs_dir(self.folder)/(job+'.json'),item)
        with patch.object(bg,'install_or_update',side_effect=AssertionError('retry')):bg.run(self.folder)
        self.assertEqual(bg.status(self.folder,job)['state'],'error')

    def test_dead_helper_does_not_leave_ui_waiting_forever(self):
        self.enable();job=bg.enqueue(self.folder,[fixtures.REGION])
        bg.mark_abandoned(self.folder,job)
        self.assertEqual(bg.status(self.folder,job)['state'],'error')


if __name__=='__main__':unittest.main()
