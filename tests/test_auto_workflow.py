# SPDX-License-Identifier: GPL-3.0-only
import unittest, sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from werkbank import App


def value(v):
    return SimpleNamespace(get=lambda: v)


class ReviewWorkflow(unittest.TestCase):
    def app(self):
        return SimpleNamespace(
            require_track=lambda: True,
            busy=False,
            track=object(),
            snap=value(True),
            roadmap=object(),
            auto_mode=value(True),
            routing_key=lambda: "current",
            auto_checked_key="old",
            auto_issues=[],
            start_auto_alignment=Mock(),
            navigate_problem=Mock(),
            status=Mock(),
            candidate=[[object()]],
        )

    def test_calculation_waits_for_current_alignment(self):
        app = self.app()
        App.calculate(app)
        app.start_auto_alignment.assert_called_once()
        self.assertTrue(app.calculate_after_auto)

    def test_unresolved_issues_prevent_time_proposal(self):
        app = self.app()
        app.auto_checked_key = "current"
        app.auto_issues = [object()]
        App.calculate(app)
        app.navigate_problem.assert_called_once_with(0)
        app.start_auto_alignment.assert_not_called()

    def test_unresolved_issues_cannot_be_saved_as_approved(self):
        app = self.app()
        app.auto_checked_key = "current"
        app.auto_issues = [object()]
        App.save(app)
        app.status.set.assert_called_once()

    def test_manual_editor_keeps_unresolved_issue_review_before_timing(self):
        app = self.app()
        app.simple_workflow = True
        app.auto_mode = value(False)
        app.roadmap = None
        app.auto_issues = [object()]
        App.calculate(app)
        app.navigate_problem.assert_called_once_with(0)
        app.start_auto_alignment.assert_not_called()
