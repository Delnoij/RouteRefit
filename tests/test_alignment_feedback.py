# SPDX-License-Identifier: GPL-3.0-only
"""Worker feedback and cancellation without opening desktop windows."""
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from alignment_workflow import AlignmentWorkflow


class Value:
    def set(self,value): self.value=value


class Harness(AlignmentWorkflow):
    def __init__(self):
        self.alignment_feedback=Mock()
        self.alignment_spinner=Mock()
        self.alignment_phase=Value()
        self.alignment_elapsed=Value()
        self.status=Value()
        self.tabs=object()
        self.busy=False
        self.pending=[]
        self.draw=Mock()
    def alignment_key(self): return 'same route and settings'
    def after(self,delay,callback): self.pending.append(callback)
    def poll(self): self.pending.pop(0)()


class AlignmentFeedbackTests(unittest.TestCase):
    def test_elapsed_time_phase_and_stop_discard_late_result(self):
        app=Harness();entered=threading.Event();release=threading.Event();done=Mock()
        def work(cancel,emit):
            emit('Weggegevens gereed. Route uitlijnen…')
            entered.set();release.wait(2)
            return 'late proposal'
        try:
            with patch('alignment_workflow.time.monotonic',return_value=100):
                app.alignment_task(work,done,'Dit kan even duren.')
            self.assertTrue(entered.wait(1))
            with patch('alignment_workflow.time.monotonic',return_value=161):app.poll()
            self.assertEqual(app.alignment_elapsed.value,'Verstreken: 01:01')
            self.assertEqual(app.alignment_phase.value,'Weggegevens gereed. Route uitlijnen…')
            app.alignment_spinner.start.assert_called_once_with(80)
            app.stop_alignment();release.set()
            app.poll()
            self.assertTrue(app.alignment_cancel.is_set())
            self.assertIsNone(app.alignment_token)
            app.alignment_feedback.pack_forget.assert_called()
            app.alignment_spinner.stop.assert_called()
            done.assert_not_called()
        finally:release.set()

    def test_success_hides_feedback_and_delivers_proposal_once(self):
        app=Harness();done=Mock()
        app.alignment_task(lambda cancel,emit:'proposal',done,'Dit kan even duren.')
        deadline=time.monotonic()+2
        while app.alignment_token is not None and time.monotonic()<deadline:
            app.poll();time.sleep(.005)
        done.assert_called_once_with('proposal')
        self.assertIsNone(app.alignment_token)
        app.alignment_feedback.pack_forget.assert_called()
        app.alignment_spinner.stop.assert_called()


if __name__=='__main__':unittest.main()
