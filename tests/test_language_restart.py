# SPDX-License-Identifier: GPL-3.0-only
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import werkbank
from workspace_ui import WorkspaceUI


class LanguageRestart(unittest.TestCase):
    def test_comparison_reopens_both_files_after_language_change(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(werkbank, "BASE", Path(tmp)),
            patch("subprocess.Popen") as launch,
        ):
            app = SimpleNamespace(
                may_replace=lambda: True,
                comparison_paths=(Path("before.gpx"), Path("after.gpx")),
                source=Path("archived.gpx"),
                destroy=Mock(),
            )
            WorkspaceUI.change_language(app, "fr")
            self.assertEqual(
                launch.call_args.args[0][-3:], ["--compare", "before.gpx", "after.gpx"]
            )
            self.assertEqual(
                json.loads((Path(tmp) / "voorkeuren.json").read_text())["language"], "fr"
            )
            app.destroy.assert_called_once()

    def test_ordinary_route_still_reopens_normally(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(werkbank, "BASE", Path(tmp)),
            patch("subprocess.Popen") as launch,
        ):
            app = SimpleNamespace(
                may_replace=lambda: True,
                comparison_paths=None,
                source=Path("original.gpx"),
                destroy=Mock(),
            )
            WorkspaceUI.change_language(app, "en")
            self.assertEqual(launch.call_args.args[0][-1], "original.gpx")
            self.assertNotIn("--compare", launch.call_args.args[0])

    def test_cancel_does_not_write_preferences_or_close_the_route(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(werkbank, "BASE", Path(tmp)),
            patch("subprocess.Popen") as launch,
        ):
            app = SimpleNamespace(may_replace=lambda: False, destroy=Mock())
            WorkspaceUI.change_language(app, "de")
            launch.assert_not_called()
            app.destroy.assert_not_called()
            self.assertFalse((Path(tmp) / "voorkeuren.json").exists())


if __name__ == "__main__":
    unittest.main()
