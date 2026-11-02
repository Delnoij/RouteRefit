# SPDX-License-Identifier: GPL-3.0-only
import sys, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from werkbank import App


class MissingTimes(unittest.TestCase):
    def test_switch_requires_user_choice_and_clears_stale_pauses(self):
        app = SimpleNamespace(
            timing=Mock(), found=["stale"], pausebox=Mock(), invalidate=Mock(), status=Mock()
        )
        app.pausebox.get_children.return_value = ("0",)
        with patch("werkbank.messagebox.askyesno", return_value=True):
            self.assertTrue(App.offer_modeled_times(app))
        app.timing.set.assert_called_once_with("model")
        self.assertEqual(app.found, [])
        app.invalidate.assert_called_once()

    def test_declining_preserves_recording_mode(self):
        app = SimpleNamespace(timing=Mock())
        with patch("werkbank.messagebox.askyesno", return_value=False):
            self.assertFalse(App.offer_modeled_times(app))
        app.timing.set.assert_not_called()

    def test_pause_button_offers_new_profile_for_working_geometry(self):
        for accept in (False, True):
            app = SimpleNamespace(
                require_track=lambda: True,
                busy=False,
                track=Mock(),
                edit_segments=[["working"]],
                offer_modeled_times=Mock(return_value=accept),
                calculate=Mock(),
            )
            app.track.stats.return_value = {"valid_time": False}
            self.assertFalse(App.find_pauses(app))
            app.track.stats.assert_called_once_with(app.edit_segments)
            self.assertEqual(app.calculate.call_count, int(accept))
